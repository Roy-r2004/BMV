"""Canonical generated-data API: manifest, emitter, and strict handoff.

Request #40 failed deterministic pre-build validation because generated
business components imported ``getServiceSeedData`` from
``@/generated/content-data``, which only exported untyped ``as const`` values.
Every implicit-``any`` diagnostic in that run cascaded from the error-typed
import.

This module makes the generated data module's API explicit and deterministic:

* :func:`build_generated_data_api_manifest` derives a typed manifest from the
  accepted ContentDataPlan.
* :func:`render_generated_data_api_block` emits the TypeScript for that
  manifest, so the module and its declared contract cannot drift.
* :func:`validate_generated_data_imports` and
  :func:`heal_invented_generated_data_symbols` keep generated components and
  pages inside the declared surface.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.application.candidate_generation.cache import canonical_sha256, sha256_text
from app.application.candidate_generation.content_data_identifiers import (
    collection_seed_records,
    identifier_words,
    lower_camel,
    seed_record_property_keys,
    singularize,
    unique_alias,
    upper_camel,
)
from app.core.config import settings
from app.domain.schemas.content_data_plan import ContentDataPlan, DataCollection
from app.domain.schemas.generated_data_api import (
    GENERATED_DATA_API_MODULE_PATH,
    GENERATED_DATA_API_MODULE_SPECIFIER,
    GENERATED_DATA_API_POLICY_REVISION,
    GeneratedDataApiManifest,
    GeneratedDataCollectionApi,
    GeneratedDataExport,
    GeneratedDataFieldSignature,
)


_TYPE_SORT_ORDER = {
    "boolean": 0,
    "number": 1,
    "string": 2,
}
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
_EXPORT_DECL_RE = re.compile(
    r"^export\s+(?:declare\s+)?"
    r"(?:const|let|var|function|class|interface|type|enum)\s+"
    r"([A-Za-z_$][A-Za-z0-9_$]*)",
    re.MULTILINE,
)
_EXPORT_LIST_RE = re.compile(r"^export\s*\{([^}]*)\}", re.MULTILINE)
_CONTENT_DATA_IMPORT_RE = re.compile(
    r"import\s+(?P<type_only>type\s+)?"
    r"(?P<clause>\{[^{}]*\})\s+from\s+"
    r"(?P<quote>[\"'])(?P<specifier>[^\"']+)(?P=quote)"
    r"(?P<tail>;?[ \t]*\r?\n?)"
)
_MODULE_SPECIFIER_RE = re.compile(r"(?:^|/)generated/content-data$")
_ACCESSOR_PREFIXES = ("get", "use", "fetch", "load", "read", "select", "all")
_ACCESSOR_SUFFIXES = (
    "seeddata",
    "seedrecords",
    "seedrows",
    "seeds",
    "seed",
    "dataset",
    "data",
    "records",
    "record",
    "entries",
    "entries",
    "items",
    "rows",
    "list",
    "collection",
)


def _value_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (list, tuple)):
        inner = _union_type({_value_type(item) for item in value} or {"string"})
        if " | " in inner:
            return f"readonly ({inner})[]"
        return f"readonly {inner}[]"
    return "string"


def _union_type(names: Iterable[str]) -> str:
    ordered = sorted(
        set(names),
        key=lambda name: (
            _TYPE_SORT_ORDER.get(name, 3 if name != "null" else 9),
            name,
        ),
    )
    return " | ".join(ordered) if ordered else "string"


def _property_literal(name: str) -> str:
    if _IDENTIFIER_RE.match(name):
        return name
    return json.dumps(name, ensure_ascii=False)


def _reference_fields(
    plan: ContentDataPlan,
    collection_id: str,
) -> dict[str, tuple[str, str]]:
    references: dict[str, tuple[str, str]] = {}
    for relationship in getattr(plan, "relationships", ()) or ():
        if relationship.from_collection_id != collection_id:
            continue
        references.setdefault(
            relationship.from_field_id,
            (relationship.to_collection_id, relationship.to_field_id),
        )
    return references


def _collection_field_signatures(
    *,
    plan: ContentDataPlan,
    collection: DataCollection,
    records: Sequence[dict[str, object]],
) -> tuple[GeneratedDataFieldSignature, ...]:
    references = _reference_fields(plan, collection.collection_id)
    signatures: list[GeneratedDataFieldSignature] = []
    for field_id, property_name, alias_of in seed_record_property_keys(
        collection
    ):
        observed = {
            _value_type(record[property_name])
            for record in records
            if property_name in record
        }
        present = sum(1 for record in records if property_name in record)
        reference = references.get(field_id)
        signatures.append(
            GeneratedDataFieldSignature(
                field_id=field_id,
                property_name=property_name,
                typescript_type=_union_type(observed or {"string"}),
                optional=present < len(records),
                alias_of=alias_of,
                reference_collection_id=reference[0] if reference else None,
                reference_field_id=reference[1] if reference else None,
            )
        )
    return tuple(signatures)


def build_generated_data_api_manifest(
    *,
    content_data: ContentDataPlan,
    content_data_plan_sha256: str,
    reserved_symbols: Iterable[str] = (),
) -> GeneratedDataApiManifest:
    """Derive the canonical generated-data API from the accepted plan."""

    used: set[str] = set(reserved_symbols)
    collections: list[GeneratedDataCollectionApi] = []
    exports: list[GeneratedDataExport] = [
        GeneratedDataExport(
            symbol="contentDataPlan",
            export_kind="const",
            typescript_signature=(
                "const contentDataPlan: Readonly<ContentDataPlanJson>"
            ),
        ),
        GeneratedDataExport(
            symbol="contentDataSha256",
            export_kind="const",
            typescript_signature=(
                f'const contentDataSha256: "{content_data_plan_sha256}"'
            ),
        ),
        GeneratedDataExport(
            symbol="contentData",
            export_kind="const",
            typescript_signature=(
                "const contentData: typeof contentDataPlan.content_items"
            ),
        ),
        GeneratedDataExport(
            symbol="dataCollections",
            export_kind="const",
            typescript_signature=(
                "const dataCollections: typeof contentDataPlan.data_collections"
            ),
        ),
    ]
    for collection in content_data.data_collections:
        words = singularize(identifier_words(collection.entity_id))
        record_symbol = unique_alias(f"{upper_camel(words)}Record", used)
        seed_symbol = unique_alias(f"{lower_camel(words)}SeedData", used)
        accessor_symbol = unique_alias(
            f"get{upper_camel(words)}SeedData",
            used,
        )
        records = collection_seed_records(collection)
        collections.append(
            GeneratedDataCollectionApi(
                collection_id=collection.collection_id,
                entity_id=collection.entity_id,
                record_type_symbol=record_symbol,
                seed_value_symbol=seed_symbol,
                accessor_symbol=accessor_symbol,
                seed_record_count=len(records),
                field_signatures=_collection_field_signatures(
                    plan=content_data,
                    collection=collection,
                    records=records,
                ),
            )
        )
        exports.extend(
            (
                GeneratedDataExport(
                    symbol=record_symbol,
                    export_kind="type",
                    typescript_signature=f"interface {record_symbol}",
                    collection_id=collection.collection_id,
                ),
                GeneratedDataExport(
                    symbol=seed_symbol,
                    export_kind="const",
                    typescript_signature=(
                        f"const {seed_symbol}: readonly {record_symbol}[]"
                    ),
                    collection_id=collection.collection_id,
                ),
                GeneratedDataExport(
                    symbol=accessor_symbol,
                    export_kind="function",
                    typescript_signature=(
                        f"function {accessor_symbol}(): "
                        f"readonly {record_symbol}[]"
                    ),
                    collection_id=collection.collection_id,
                ),
            )
        )
    return GeneratedDataApiManifest(
        api_policy_revision=GENERATED_DATA_API_POLICY_REVISION,
        module_path=GENERATED_DATA_API_MODULE_PATH,
        module_specifier=GENERATED_DATA_API_MODULE_SPECIFIER,
        content_data_plan_sha256=content_data_plan_sha256,
        collections=tuple(collections),
        exports=tuple(exports),
    )


def render_generated_data_api_block(
    *,
    manifest: GeneratedDataApiManifest,
    content_data: ContentDataPlan,
) -> str:
    """Emit the typed portion of ``content-data.ts`` for the manifest."""

    if not manifest.collections:
        return ""
    records_by_collection = {
        item.collection_id: collection_seed_records(item)
        for item in content_data.data_collections
    }
    lines: list[str] = [
        "",
        "// Canonical generated-data API "
        f"({manifest.api_policy_revision}).",
        "// Business components and pages must import only these symbols.",
    ]
    for collection in manifest.collections:
        lines.append(f"export interface {collection.record_type_symbol} {{")
        for field in collection.field_signatures:
            optional = "?" if field.optional else ""
            lines.append(
                f"  readonly {_property_literal(field.property_name)}"
                f"{optional}: {field.typescript_type};"
            )
        lines.append("}")
        payload = json.dumps(
            records_by_collection.get(collection.collection_id, []),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        lines.append(
            f"export const {collection.seed_value_symbol}: "
            f"readonly {collection.record_type_symbol}[] = {payload};"
        )
        lines.append(
            f"export function {collection.accessor_symbol}(): "
            f"readonly {collection.record_type_symbol}[] {{"
        )
        lines.append(f"  return {collection.seed_value_symbol};")
        lines.append("}")
    return "\n".join(lines) + "\n"


def validate_generated_data_literals(
    *,
    manifest: GeneratedDataApiManifest,
    content_data: ContentDataPlan,
) -> tuple[dict[str, str], ...]:
    """Fail-closed validation of emitted seed records against the manifest."""

    records_by_collection = {
        collection.collection_id: collection_seed_records(collection)
        for collection in content_data.data_collections
    }
    issues: list[dict[str, str]] = []
    for collection in manifest.collections:
        fields = {
            field.property_name: field for field in collection.field_signatures
        }
        aliases = {
            field.property_name: field
            for field in collection.field_signatures
            if field.alias_of
        }
        for index, record in enumerate(
            records_by_collection.get(collection.collection_id, ())
        ):
            for property_name, field in fields.items():
                if field.optional or property_name in record:
                    continue
                issues.append(
                    {
                        "code": "generated_data_required_field_missing",
                        "message": (
                            f"{collection.collection_id}[{index}] lacks required "
                            f"manifest field {property_name!r}."
                        ),
                    }
                )
            for property_name in record:
                if property_name in fields:
                    continue
                issues.append(
                    {
                        "code": "generated_data_literal_manifest_mismatch",
                        "message": (
                            f"{collection.collection_id}[{index}] emits undeclared "
                            f"property {property_name!r}."
                        ),
                    }
                )
            for property_name, field in aliases.items():
                if property_name not in record:
                    issues.append(
                        {
                            "code": "generated_data_required_field_missing",
                            "message": (
                                f"{collection.collection_id}[{index}] lacks "
                                f"declared alias {property_name!r}."
                            ),
                        }
                    )
                    continue
                target = fields.get(field.alias_of)
                if target is None:
                    issues.append(
                        {
                            "code": "generated_data_alias_target_missing",
                            "message": (
                                f"Alias {property_name!r} references missing "
                                f"canonical field {field.alias_of!r}."
                            ),
                        }
                    )
                    continue
                if target.alias_of:
                    issues.append(
                        {
                            "code": "generated_data_alias_undeclared",
                            "message": (
                                f"Alias {property_name!r} targets another alias "
                                f"{field.alias_of!r}."
                            ),
                        }
                    )
                if field.typescript_type != target.typescript_type:
                    issues.append(
                        {
                            "code": "generated_data_alias_type_mismatch",
                            "message": (
                                f"Alias {property_name!r} and {field.alias_of!r} "
                                "have different manifest types."
                            ),
                        }
                    )
                if field.alias_of in record and (
                    record[property_name] != record[field.alias_of]
                ):
                    issues.append(
                        {
                            "code": "generated_data_alias_value_mismatch",
                            "message": (
                                f"Alias {property_name!r} differs from "
                                f"{field.alias_of!r}."
                            ),
                        }
                    )
    return tuple(issues)


def exported_symbols(source: str) -> frozenset[str]:
    """Return every symbol exported by a generated TypeScript module."""

    symbols = set(_EXPORT_DECL_RE.findall(source))
    for clause in _EXPORT_LIST_RE.findall(source):
        for entry in clause.split(","):
            parts = entry.replace("type ", "").strip().split(" as ")
            name = parts[-1].strip()
            if _IDENTIFIER_RE.match(name):
                symbols.add(name)
    return frozenset(symbols)


def _is_content_data_specifier(specifier: str) -> bool:
    normalized = specifier.strip().rstrip("/")
    if normalized.endswith((".ts", ".tsx")):
        normalized = normalized.rsplit(".", 1)[0]
    return bool(_MODULE_SPECIFIER_RE.search(normalized))


def _parse_named_specifiers(clause: str) -> list[tuple[str, str, bool]]:
    """Return ``(imported, local, type_only)`` for one ``{...}`` clause."""

    entries: list[tuple[str, str, bool]] = []
    for raw in clause.strip("{}").split(","):
        entry = raw.strip()
        if not entry:
            continue
        type_only = False
        if entry.startswith("type "):
            type_only = True
            entry = entry[5:].strip()
        parts = [part.strip() for part in entry.split(" as ")]
        imported = parts[0]
        local = parts[-1]
        if not _IDENTIFIER_RE.match(imported) or not _IDENTIFIER_RE.match(local):
            continue
        entries.append((imported, local, type_only))
    return entries


def generated_data_imports(source: str) -> list[tuple[str, str, bool]]:
    """Return every named import taken from the generated data module."""

    imports: list[tuple[str, str, bool]] = []
    for match in _CONTENT_DATA_IMPORT_RE.finditer(source):
        if not _is_content_data_specifier(match.group("specifier")):
            continue
        clause_type_only = bool(match.group("type_only"))
        for imported, local, type_only in _parse_named_specifiers(
            match.group("clause")
        ):
            imports.append((imported, local, clause_type_only or type_only))
    return imports


def _normalized_stem(symbol: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9]", "", symbol).lower()
    for prefix in _ACCESSOR_PREFIXES:
        if stem.startswith(prefix) and len(stem) > len(prefix):
            stem = stem[len(prefix) :]
            break
    changed = True
    while changed:
        changed = False
        for suffix in _ACCESSOR_SUFFIXES:
            if stem.endswith(suffix) and len(stem) > len(suffix):
                stem = stem[: -len(suffix)]
                changed = True
                break
    return "".join(singularize([stem])) if stem else stem


def canonical_symbol_replacements(
    manifest: GeneratedDataApiManifest,
) -> dict[str, str]:
    """Map normalized invented stems to their canonical seed-value symbol."""

    by_stem: dict[str, set[str]] = {}
    for collection in manifest.collections:
        stem = _normalized_stem(
            "".join(singularize(identifier_words(collection.entity_id)))
        )
        if not stem:
            continue
        by_stem.setdefault(stem, set()).add(collection.seed_value_symbol)
    return {
        stem: next(iter(symbols))
        for stem, symbols in by_stem.items()
        if len(symbols) == 1
    }


def resolve_invented_symbol(
    symbol: str,
    *,
    manifest: GeneratedDataApiManifest,
    replacements: dict[str, str] | None = None,
) -> str:
    """Return the canonical symbol an invented import most likely meant."""

    table = (
        replacements
        if replacements is not None
        else canonical_symbol_replacements(manifest)
    )
    return table.get(_normalized_stem(symbol), "")


def _replace_identifier(source: str, old: str, new: str) -> str:
    pattern = re.compile(rf"\b{re.escape(old)}\b\s*\(\s*\)")
    updated = pattern.sub(new, source)
    return re.sub(rf"\b{re.escape(old)}\b", new, updated)


def _rewrite_import_clause(
    source: str,
    *,
    drop_locals: set[str],
    add_symbols: set[str],
) -> str:
    """Drop healed locals everywhere, then re-add canonical symbols once."""

    pending = set(add_symbols)

    def _rewrite(match: re.Match[str]) -> str:
        if not _is_content_data_specifier(match.group("specifier")):
            return match.group(0)
        type_prefix = match.group("type_only") or ""
        kept: list[str] = []
        for imported, local, type_only in _parse_named_specifiers(
            match.group("clause")
        ):
            if local in drop_locals:
                continue
            prefix = "type " if type_only and not type_prefix else ""
            kept.append(
                f"{prefix}{imported}"
                if imported == local
                else f"{prefix}{imported} as {local}"
            )
        if not type_prefix:
            existing = {entry.split(" as ")[-1].strip() for entry in kept}
            additions = sorted(pending - existing)
            kept.extend(additions)
            pending.difference_update(additions)
        if not kept:
            return ""
        clause = "{ " + ", ".join(kept) + " }"
        quote = match.group("quote")
        specifier = match.group("specifier")
        tail = match.group("tail") or ";"
        if not tail.startswith(";"):
            tail = ";" + tail
        return (
            f"import {type_prefix}{clause} from {quote}{specifier}{quote}{tail}"
        )

    return _CONTENT_DATA_IMPORT_RE.sub(_rewrite, source)


def heal_generated_data_symbols(
    source: str,
    *,
    manifest: GeneratedDataApiManifest,
    allowed_symbols: frozenset[str],
) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Rewrite invented generated-data imports onto the canonical symbols."""

    replacements = canonical_symbol_replacements(manifest)
    applied: list[tuple[str, str]] = []
    drop_locals: set[str] = set()
    add_symbols: set[str] = set()
    updated = source
    for imported, local, _type_only in generated_data_imports(source):
        if imported in allowed_symbols:
            continue
        canonical = replacements.get(_normalized_stem(imported))
        if not canonical or canonical == imported:
            continue
        updated = _replace_identifier(updated, local, canonical)
        drop_locals.update({local, canonical})
        add_symbols.add(canonical)
        applied.append((imported, canonical))
    if not applied:
        return source, ()
    updated = _rewrite_import_clause(
        updated,
        drop_locals=drop_locals,
        add_symbols=add_symbols,
    )
    return updated, tuple(applied)


def heal_generated_data_record_shapes(
    source: str,
    *,
    path: str,
    manifest: GeneratedDataApiManifest,
    content_data_module: str,
) -> tuple[str, tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    """Apply compiler-AST-approved flat-record access edits exactly once.

    The JavaScript worker creates a TypeScript program containing the candidate
    file and the generated data module. It resolves generated-data imports and
    collection callbacks through TypeScript symbols, then returns only edits
    whose record type and field exist in ``manifest``. Python deliberately
    performs no source-pattern matching: it only applies those AST spans.
    """

    node = shutil.which("node")
    typescript = (
        settings.PREVIEW_TEMPLATE_DIR
        / "node_modules"
        / "typescript"
        / "lib"
        / "typescript.js"
    )
    script = Path(__file__).with_name("typescript") / (
        "heal_generated_data_record_shapes.mjs"
    )
    if not node or not typescript.is_file() or not script.is_file():
        return (
            source,
            (),
            (
                {
                    "code": "generated_data_record_shape_tool_unavailable",
                    "path": path,
                    "message": (
                        "The TypeScript compiler AST worker required to validate "
                        "generated-data record access is unavailable."
                    ),
                },
            ),
        )
    payload = {
        "workspace_root": str(settings.PREVIEW_TEMPLATE_DIR),
        "path": path,
        "source": source,
        "content_data_module": content_data_module,
        "manifest": manifest.model_dump(mode="json"),
    }
    try:
        result = subprocess.run(
            [node, str(script), str(typescript)],
            input=json.dumps(payload, separators=(",", ":")),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        response = json.loads(result.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return (
            source,
            (),
            (
                {
                    "code": "generated_data_record_shape_tool_error",
                    "path": path,
                    "message": f"TypeScript AST record-shape analysis failed: {exc}",
                },
            ),
        )
    if result.returncode or not isinstance(response, dict):
        return (
            source,
            (),
            (
                {
                    "code": "generated_data_record_shape_tool_error",
                    "path": path,
                    "message": (
                        "TypeScript AST record-shape analysis failed: "
                        f"{result.stderr.strip() or response}"
                    ),
                },
            ),
        )

    raw_issues = response.get("issues")
    issues = tuple(
        {
            "code": str(item.get("code") or "generated_data_record_shape_error"),
            "path": path,
            "message": str(item.get("message") or "Invalid record access."),
        }
        for item in (raw_issues if isinstance(raw_issues, list) else ())
        if isinstance(item, dict)
    )
    raw_edits = response.get("edits")
    edits = [
        item
        for item in (raw_edits if isinstance(raw_edits, list) else ())
        if isinstance(item, dict)
        and isinstance(item.get("start"), int)
        and isinstance(item.get("end"), int)
        and isinstance(item.get("replacement"), str)
        and 0 <= item["start"] <= item["end"] <= len(source)
    ]
    if issues or not edits:
        return source, (), issues

    updated = source
    accepted: list[dict[str, Any]] = []
    last_start = len(source) + 1
    for edit in sorted(edits, key=lambda item: (item["start"], item["end"]), reverse=True):
        start = edit["start"]
        end = edit["end"]
        if end > last_start or source[start:end] != edit.get("original"):
            return (
                source,
                (),
                (
                    {
                        "code": "generated_data_record_shape_edit_conflict",
                        "path": path,
                        "message": (
                            "TypeScript AST returned overlapping or stale "
                            "record-shape edits."
                        ),
                    },
                ),
            )
        updated = updated[:start] + edit["replacement"] + updated[end:]
        accepted.append(edit)
        last_start = start
    if updated == source:
        return source, (), ()
    manifest_sha256 = canonical_sha256(manifest)
    before_sha256 = sha256_text(source)
    after_sha256 = sha256_text(updated)
    evidence = tuple(
        {
            "path": path,
            "original_expression": edit["original"],
            "replacement": edit["replacement"],
            "reason": edit["reason"],
            "collection_id": edit["collection_id"],
            "record_type_symbol": edit["record_type_symbol"],
            "property_name": edit["property_name"],
            "typescript_type": edit["typescript_type"],
            "manifest_sha256": manifest_sha256,
            "file_sha256_before": before_sha256,
            "file_sha256_after": after_sha256,
        }
        for edit in reversed(accepted)
    )
    return updated, evidence, ()


def normalize_generated_candidate_types(
    source: str,
    *,
    path: str,
    manifest: GeneratedDataApiManifest,
    content_data_module: str,
) -> tuple[str, tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    """Normalize compiler-proven candidate type imports and React JSX types once."""

    node = shutil.which("node")
    typescript = (
        settings.PREVIEW_TEMPLATE_DIR
        / "node_modules"
        / "typescript"
        / "lib"
        / "typescript.js"
    )
    script = Path(__file__).with_name("typescript") / (
        "normalize_generated_candidate_types.mjs"
    )
    if not node or not typescript.is_file() or not script.is_file():
        return (
            source,
            (),
            (
                {
                    "code": "generated_candidate_type_normalizer_unavailable",
                    "path": path,
                    "message": (
                        "The TypeScript compiler AST worker required to normalize "
                        "generated candidate types is unavailable."
                    ),
                },
            ),
        )
    payload = {
        "workspace_root": str(settings.PREVIEW_TEMPLATE_DIR),
        "path": path,
        "source": source,
        "content_data_module": content_data_module,
        "manifest": manifest.model_dump(mode="json"),
    }
    try:
        result = subprocess.run(
            [node, str(script), str(typescript)],
            input=json.dumps(payload, separators=(",", ":")),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        response = json.loads(result.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return (
            source,
            (),
            (
                {
                    "code": "generated_candidate_type_normalizer_error",
                    "path": path,
                    "message": (
                        "TypeScript AST type normalization failed: "
                        f"{exc}"
                    ),
                },
            ),
        )
    if result.returncode or not isinstance(response, dict):
        return (
            source,
            (),
            (
                {
                    "code": "generated_candidate_type_normalizer_error",
                    "path": path,
                    "message": (
                        "TypeScript AST type normalization failed: "
                        f"{result.stderr.strip() or response}"
                    ),
                },
            ),
        )

    issues = tuple(
        {
            "code": str(item.get("code") or "generated_candidate_type_error"),
            "path": path,
            "message": str(item.get("message") or "Invalid candidate type use."),
        }
        for item in (response.get("issues") or ())
        if isinstance(item, dict)
    )
    edits = [
        item
        for item in (response.get("edits") or ())
        if isinstance(item, dict)
        and isinstance(item.get("start"), int)
        and isinstance(item.get("end"), int)
        and isinstance(item.get("replacement"), str)
        and 0 <= item["start"] <= item["end"] <= len(source)
    ]
    if issues or not edits:
        return source, (), issues

    updated = source
    accepted: list[dict[str, Any]] = []
    last_start = len(source) + 1
    for edit in sorted(edits, key=lambda item: (item["start"], item["end"]), reverse=True):
        start = edit["start"]
        end = edit["end"]
        if end > last_start or source[start:end] != edit.get("original"):
            return (
                source,
                (),
                (
                    {
                        "code": "generated_candidate_type_normalizer_conflict",
                        "path": path,
                        "message": (
                            "TypeScript AST returned overlapping or stale "
                            "candidate type edits."
                        ),
                    },
                ),
            )
        updated = updated[:start] + edit["replacement"] + updated[end:]
        accepted.append(edit)
        last_start = start
    if updated == source:
        return source, (), ()
    before_sha256 = sha256_text(source)
    after_sha256 = sha256_text(updated)
    evidence = tuple(
        {
            "path": path,
            "original_import": edit["original"],
            "replacement": edit["replacement"],
            "type_only_symbols": tuple(edit.get("type_symbols") or ()),
            "runtime_symbols": tuple(edit.get("value_symbols") or ()),
            "file_sha256_before": before_sha256,
            "file_sha256_after": after_sha256,
            "reason": edit.get("reason") or "normalize_candidate_types",
        }
        for edit in reversed(accepted)
    )
    return updated, evidence, ()


def validate_generated_data_imports(
    *,
    path: str,
    source: str,
    manifest: GeneratedDataApiManifest,
    allowed_symbols: frozenset[str],
) -> list[dict[str, Any]]:
    """Return one descriptor per import that the data module does not export."""

    invented: list[dict[str, Any]] = []
    replacements = canonical_symbol_replacements(manifest)
    for imported, _local, _type_only in generated_data_imports(source):
        if imported in allowed_symbols:
            continue
        suggestion = replacements.get(_normalized_stem(imported), "")
        invented.append(
            {
                "path": path,
                "symbol": imported,
                "suggestion": suggestion,
            }
        )
    return invented


def manifest_prompt_projection(
    manifest: GeneratedDataApiManifest,
) -> dict[str, Any]:
    """Compact, prompt-safe projection of the canonical generated-data API."""

    return {
        "api_policy_revision": manifest.api_policy_revision,
        "module_specifier": manifest.module_specifier,
        "module_path": manifest.module_path,
        "content_data_plan_sha256": manifest.content_data_plan_sha256,
        "import_rule": (
            "Import only the symbols listed in exports. The module exports no "
            "other member; inventing one fails deterministic pre-build "
            "validation."
        ),
        "strict_typescript": (
            "tsconfig.app.json sets strict and noImplicitAny. Annotate every "
            "callback parameter with the exported record type, for example "
            "(item: ServiceRecord) => item.id."
        ),
        "record_shape": (
            "Seed values are flat records keyed by the property_name entries "
            "below. They are not ContentDataPlan seed_records, so never read "
            ".seed_records, .values, .field_id, or .value off a seed record; "
            "read the property directly, for example record.serviceName."
        ),
        "exports": [
            {
                "symbol": item.symbol,
                "export_kind": item.export_kind,
                "typescript_signature": item.typescript_signature,
                "collection_id": item.collection_id,
            }
            for item in manifest.exports
        ],
        "collections": [
            {
                "collection_id": item.collection_id,
                "entity_id": item.entity_id,
                "record_type_symbol": item.record_type_symbol,
                "seed_value_symbol": item.seed_value_symbol,
                "accessor_symbol": item.accessor_symbol,
                "seed_record_count": item.seed_record_count,
                "fields": [
                    {
                        "field_id": field.field_id,
                        "property_name": field.property_name,
                        "typescript_type": field.typescript_type,
                        "optional": field.optional,
                        "alias_of": field.alias_of,
                        "reference_collection_id": (
                            field.reference_collection_id
                        ),
                        "reference_field_id": field.reference_field_id,
                    }
                    for field in item.field_signatures
                ],
            }
            for item in manifest.collections
        ],
    }


__all__ = [
    "build_generated_data_api_manifest",
    "canonical_symbol_replacements",
    "exported_symbols",
    "generated_data_imports",
    "heal_generated_data_record_shapes",
    "heal_generated_data_symbols",
    "manifest_prompt_projection",
    "render_generated_data_api_block",
    "resolve_invented_symbol",
    "validate_generated_data_imports",
]
