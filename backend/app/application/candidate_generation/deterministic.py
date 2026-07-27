"""Deterministic Phase 3B foundation, data, and route projections."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.application.appspec.source import canonical_json
from app.application.candidate_generation.cache import sha256_bytes, sha256_text
from app.application.candidate_generation.context import CandidateContext
from app.domain.schemas.preview_candidate import (
    CandidateArtifactKind,
    CandidateArtifactManifest,
    CandidateFileDescriptor,
    CandidateFileKind,
)


@dataclass(frozen=True)
class CandidateSourceFile:
    path: str
    file_kind: CandidateFileKind
    owner_contract_ids: tuple[str, ...]
    source: str


_FOUNDATION_FILES = (
    "package.json",
    "package-lock.json",
    "tsconfig.app.json",
    "tsconfig.json",
    "tsconfig.node.json",
    "vite.config.ts",
    "index.html",
)
_UNCOUNTABLE_ALIASES = frozenset({"availability"})
_TYPESCRIPT_RESERVED_IDENTIFIERS = frozenset(
    {
        "abstract",
        "any",
        "as",
        "asserts",
        "async",
        "await",
        "bigint",
        "boolean",
        "break",
        "case",
        "catch",
        "class",
        "const",
        "constructor",
        "continue",
        "debugger",
        "declare",
        "default",
        "delete",
        "do",
        "else",
        "enum",
        "export",
        "extends",
        "false",
        "finally",
        "for",
        "from",
        "function",
        "get",
        "if",
        "implements",
        "import",
        "in",
        "infer",
        "instanceof",
        "interface",
        "is",
        "keyof",
        "let",
        "module",
        "namespace",
        "never",
        "new",
        "null",
        "number",
        "object",
        "of",
        "override",
        "package",
        "private",
        "protected",
        "public",
        "readonly",
        "require",
        "return",
        "satisfies",
        "set",
        "static",
        "string",
        "super",
        "switch",
        "symbol",
        "this",
        "throw",
        "true",
        "try",
        "type",
        "typeof",
        "undefined",
        "unique",
        "unknown",
        "var",
        "void",
        "while",
        "with",
        "yield",
    }
)


def dependency_lock_sha256(template_dir: Path) -> str:
    return sha256_bytes((template_dir / "package-lock.json").read_bytes())


def _foundation_runtime_sources() -> tuple[CandidateSourceFile, ...]:
    return (
        CandidateSourceFile(
            path="src/vite-env.d.ts",
            file_kind="infrastructure",
            owner_contract_ids=("FOUNDATION",),
            source='/// <reference types="vite/client" />\n',
        ),
        CandidateSourceFile(
            path="src/runtime/styles.d.ts",
            file_kind="runtime",
            owner_contract_ids=("FOUNDATION",),
            source='declare module "*.css";\n',
        ),
        CandidateSourceFile(
            path="src/index.css",
            file_kind="infrastructure",
            owner_contract_ids=("FOUNDATION",),
            source=(
                '@import "tailwindcss";\n\n'
                ":root {\n"
                "  font-synthesis: none;\n"
                "  text-rendering: optimizeLegibility;\n"
                "  color-scheme: light;\n"
                "}\n\n"
                "* { box-sizing: border-box; }\n"
                "html { min-width: 320px; background: #fff; }\n"
                "body { margin: 0; min-width: 320px; min-height: 100vh; }\n"
                "button, input, select, textarea { font: inherit; }\n"
                "@media (prefers-reduced-motion: reduce) {\n"
                "  *, *::before, *::after {\n"
                "    scroll-behavior: auto !important;\n"
                "    animation-duration: 0.01ms !important;\n"
                "    animation-iteration-count: 1 !important;\n"
                "    transition-duration: 0.01ms !important;\n"
                "  }\n"
                "}\n"
            ),
        ),
        CandidateSourceFile(
            path="src/runtime/ErrorBoundary.tsx",
            file_kind="runtime",
            owner_contract_ids=("FOUNDATION",),
            source=(
                'import { Component, type ErrorInfo, type ReactNode } from "react";\n\n'
                "type Props = { children: ReactNode };\n"
                "type State = { failed: boolean };\n\n"
                "export class CandidateErrorBoundary extends Component<Props, State> {\n"
                "  state: State = { failed: false };\n\n"
                "  static getDerivedStateFromError(): State {\n"
                "    return { failed: true };\n"
                "  }\n\n"
                "  componentDidCatch(error: Error, info: ErrorInfo): void {\n"
                '    console.error("candidate-render-error", error, info);\n'
                "  }\n\n"
                "  render(): ReactNode {\n"
                "    if (this.state.failed) {\n"
                "      return <main role=\"alert\">This candidate could not render.</main>;\n"
                "    }\n"
                "    return this.props.children;\n"
                "  }\n"
                "}\n"
            ),
        ),
        CandidateSourceFile(
            path="src/runtime/RoleAccess.tsx",
            file_kind="runtime",
            owner_contract_ids=("FOUNDATION",),
            source=(
                'import type { ReactNode } from "react";\n\n'
                "type Props = {\n"
                "  pageId: string;\n"
                "  roleIds: readonly string[];\n"
                "  children: ReactNode;\n"
                "};\n\n"
                "export function RoleAccess({ pageId, roleIds, children }: Props) {\n"
                "  return (\n"
                "    <div\n"
                "      data-bmv-route-page-id={pageId}\n"
                "      data-bmv-role-ids={roleIds.join(\",\")}\n"
                "    >\n"
                "      {children}\n"
                "    </div>\n"
                "  );\n"
                "}\n"
            ),
        ),
        CandidateSourceFile(
            path="src/main.tsx",
            file_kind="infrastructure",
            owner_contract_ids=("FOUNDATION",),
            source=(
                'import { StrictMode } from "react";\n'
                'import { createRoot } from "react-dom/client";\n'
                'import { BrowserRouter } from "react-router-dom";\n'
                'import App from "./App";\n'
                'import { CandidateErrorBoundary } from "./runtime/ErrorBoundary";\n'
                'import "./index.css";\n\n'
                'const root = document.getElementById("root");\n'
                'if (!root) throw new Error("Missing #root mount point");\n\n'
                "createRoot(root).render(\n"
                "  <StrictMode>\n"
                "    <CandidateErrorBoundary>\n"
                "      <BrowserRouter>\n"
                "        <App />\n"
                "      </BrowserRouter>\n"
                "    </CandidateErrorBoundary>\n"
                "  </StrictMode>,\n"
                ");\n"
            ),
        ),
    )


def _foundation_ui_stub_sources() -> tuple[CandidateSourceFile, ...]:
    """Minimal stubs so common model-emitted @/components/ui imports resolve."""

    def _file(name: str, source: str) -> CandidateSourceFile:
        return CandidateSourceFile(
            path=f"src/components/ui/{name}.tsx",
            file_kind="infrastructure",
            owner_contract_ids=("FOUNDATION",),
            source=source,
        )

    return (
        _file(
            "button",
            'import type { ButtonHTMLAttributes, ReactNode } from "react";\n\n'
            "type Props = ButtonHTMLAttributes<HTMLButtonElement> & {\n"
            "  children?: ReactNode;\n"
            "  variant?: string;\n"
            "  size?: string;\n"
            "};\n\n"
            "export function Button({\n"
            "  children,\n"
            "  type = \"button\",\n"
            "  variant: _variant,\n"
            "  size: _size,\n"
            "  ...props\n"
            "}: Props) {\n"
            "  return (\n"
            "    <button type={type} {...props}>\n"
            "      {children}\n"
            "    </button>\n"
            "  );\n"
            "}\n",
        ),
        _file(
            "card",
            'import type { HTMLAttributes, ReactNode } from "react";\n\n'
            "type Props = HTMLAttributes<HTMLDivElement> & { children?: ReactNode };\n\n"
            "export function Card({ children, ...props }: Props) {\n"
            "  return <div {...props}>{children}</div>;\n"
            "}\n"
            "export function CardHeader({ children, ...props }: Props) {\n"
            "  return <div {...props}>{children}</div>;\n"
            "}\n"
            "export function CardTitle({ children, ...props }: Props) {\n"
            "  return <h2 {...props}>{children}</h2>;\n"
            "}\n"
            "export function CardDescription({ children, ...props }: Props) {\n"
            "  return <p {...props}>{children}</p>;\n"
            "}\n"
            "export function CardContent({ children, ...props }: Props) {\n"
            "  return <div {...props}>{children}</div>;\n"
            "}\n",
        ),
        _file(
            "label",
            'import type { LabelHTMLAttributes, ReactNode } from "react";\n\n'
            "type Props = LabelHTMLAttributes<HTMLLabelElement> & { children?: ReactNode };\n\n"
            "export function Label({ children, ...props }: Props) {\n"
            "  return <label {...props}>{children}</label>;\n"
            "}\n",
        ),
        _file(
            "input",
            'import type { InputHTMLAttributes } from "react";\n\n'
            "type Props = InputHTMLAttributes<HTMLInputElement>;\n\n"
            "export function Input(props: Props) {\n"
            "  return <input {...props} />;\n"
            "}\n",
        ),
        _file(
            "textarea",
            'import type { TextareaHTMLAttributes } from "react";\n\n'
            "type Props = TextareaHTMLAttributes<HTMLTextAreaElement>;\n\n"
            "export function Textarea(props: Props) {\n"
            "  return <textarea {...props} />;\n"
            "}\n",
        ),
        _file(
            "radio-group",
            'import type { HTMLAttributes, InputHTMLAttributes, ReactNode } from "react";\n\n'
            "type GroupProps = HTMLAttributes<HTMLDivElement> & {\n"
            "  value?: string;\n"
            "  onValueChange?: (value: string) => void;\n"
            "  children?: ReactNode;\n"
            "};\n\n"
            "export function RadioGroup({\n"
            "  value: _value,\n"
            "  onValueChange,\n"
            "  children,\n"
            "  onChange,\n"
            "  ...props\n"
            "}: GroupProps) {\n"
            "  return (\n"
            "    <div\n"
            "      role=\"radiogroup\"\n"
            "      {...props}\n"
            "      onChange={(event) => {\n"
            "        onChange?.(event);\n"
            "        const target = event.target as HTMLInputElement;\n"
            "        if (target?.type === \"radio\" && onValueChange) {\n"
            "          onValueChange(target.value);\n"
            "        }\n"
            "      }}\n"
            "    >\n"
            "      {children}\n"
            "    </div>\n"
            "  );\n"
            "}\n\n"
            "type ItemProps = InputHTMLAttributes<HTMLInputElement> & { value?: string };\n\n"
            "export function RadioGroupItem({ value, ...props }: ItemProps) {\n"
            "  return <input type=\"radio\" value={value} name=\"bmv-radio-group\" {...props} />;\n"
            "}\n",
        ),
        _file(
            "select",
            'import type { HTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";\n\n'
            "type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {\n"
            "  children?: ReactNode;\n"
            "};\n"
            "type BoxProps = HTMLAttributes<HTMLDivElement> & { children?: ReactNode };\n"
            "type TextProps = HTMLAttributes<HTMLSpanElement> & { children?: ReactNode };\n"
            "type ItemProps = HTMLAttributes<HTMLOptionElement> & {\n"
            "  children?: ReactNode;\n"
            "  value?: string;\n"
            "};\n\n"
            "export function Select({ children, ...props }: SelectProps) {\n"
            "  return <select {...props}>{children}</select>;\n"
            "}\n"
            "export function SelectTrigger({ children, ...props }: BoxProps) {\n"
            "  return <div {...props}>{children}</div>;\n"
            "}\n"
            "export function SelectValue({ children, ...props }: TextProps) {\n"
            "  return <span {...props}>{children}</span>;\n"
            "}\n"
            "export function SelectContent({ children, ...props }: BoxProps) {\n"
            "  return <div {...props}>{children}</div>;\n"
            "}\n"
            "export function SelectItem({ children, value, ...props }: ItemProps) {\n"
            "  return (\n"
            "    <option value={value} {...props}>\n"
            "      {children}\n"
            "    </option>\n"
            "  );\n"
            "}\n",
        ),
        _file(
            "calendar",
            'import type { HTMLAttributes, ReactNode } from "react";\n\n'
            "type Props = Omit<HTMLAttributes<HTMLDivElement>, \"onSelect\"> & {\n"
            "  selected?: Date;\n"
            "  onSelect?: (day: Date | undefined) => void;\n"
            "  mode?: string;\n"
            "  children?: ReactNode;\n"
            "};\n\n"
            "const DAYS = [\"2026-08-15\", \"2026-08-16\", \"2026-08-17\"];\n\n"
            "export function Calendar({ selected: _selected, onSelect, children, ...props }: Props) {\n"
            "  return (\n"
            "    <div data-bmv-calendar=\"true\" {...props}>\n"
            "      {DAYS.map((day) => (\n"
            "        <button\n"
            "          key={day}\n"
            "          type=\"button\"\n"
            "          onClick={() => onSelect?.(new Date(`${day}T10:00:00Z`))}\n"
            "        >\n"
            "          {day}\n"
            "        </button>\n"
            "      ))}\n"
            "      {children}\n"
            "    </div>\n"
            "  );\n"
            "}\n",
        ),
    )


def build_foundation_sources(template_dir: Path) -> tuple[CandidateSourceFile, ...]:
    files: list[CandidateSourceFile] = []
    for relpath in _FOUNDATION_FILES:
        source = (template_dir / relpath).read_text(encoding="utf-8")
        files.append(
            CandidateSourceFile(
                path=relpath,
                file_kind="infrastructure",
                owner_contract_ids=("FOUNDATION",),
                source=source,
            )
        )
    files.extend(_foundation_runtime_sources())
    files.extend(_foundation_ui_stub_sources())
    return tuple(files)


def _typescript_const(name: str, value: object) -> str:
    return (
        f"export const {name} = "
        f"{json.dumps(value, ensure_ascii=False, separators=(',', ':'))} "
        "as const;\n"
    )


def _identifier_words(identifier: str) -> list[str]:
    parts = [part.lower() for part in re.findall(r"[A-Za-z0-9]+", identifier)]
    filtered = [
        part
        for part in parts
        if part not in {"entity", "collection", "field", "record"}
    ]
    return filtered or ["data"]


def _lower_camel(words: list[str]) -> str:
    if not words:
        return "data"
    head, *tail = words
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def _typescript_prefix(name: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_$]", "", name)
    if not candidate:
        return "tsData"
    return f"ts{candidate[:1].upper()}{candidate[1:]}"


def _needs_typescript_prefix(name: str) -> bool:
    candidate = re.sub(r"[^A-Za-z0-9_$]", "", name)
    if not candidate:
        return True
    if not re.match(r"^[A-Za-z_$]", candidate):
        return True
    return candidate in _TYPESCRIPT_RESERVED_IDENTIFIERS


def _valid_typescript_identifier(name: str, *, force_prefix: bool = False) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_$]", "", name)
    if force_prefix or _needs_typescript_prefix(candidate):
        return _typescript_prefix(candidate)
    return candidate


def _singularize(words: list[str]) -> list[str]:
    if not words:
        return ["data"]
    last = words[-1]
    if last in _UNCOUNTABLE_ALIASES:
        return words
    if last.endswith("ies") and len(last) > 3:
        last = last[:-3] + "y"
    elif last.endswith("ses") and len(last) > 3:
        last = last[:-2]
    elif last.endswith("s") and len(last) > 1 and not last.endswith("ss"):
        last = last[:-1]
    return [*words[:-1], last]


def _pluralize(words: list[str]) -> list[str]:
    if not words:
        return ["data"]
    last = words[-1]
    if last in _UNCOUNTABLE_ALIASES:
        return words
    if last.endswith("y") and len(last) > 1 and last[-2] not in "aeiou":
        last = last[:-1] + "ies"
    elif last.endswith(("s", "x", "z", "ch", "sh")):
        last = last + "es"
    else:
        last = last + "s"
    return [*words[:-1], last]


def _unique_alias(base: str, used: set[str]) -> str:
    stem = _valid_typescript_identifier(base or "data")
    candidate = stem
    suffix = 1
    while candidate in used:
        suffix += 1
        candidate = _valid_typescript_identifier(f"{stem}{suffix}")
    used.add(candidate)
    return candidate


def _collection_seed_records(collection: object) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    entity_words = _identifier_words(str(getattr(collection, "entity_id", "")))
    for seed_record in getattr(collection, "seed_records", ()):
        payload: dict[str, object] = {}
        for item in getattr(seed_record, "values", ()):
            field_words = _identifier_words(str(getattr(item, "field_id", "")))
            value = getattr(item, "value", None)
            full_key = _lower_camel(field_words)
            payload[full_key] = value
            if (
                len(field_words) > len(entity_words)
                and field_words[: len(entity_words)] == entity_words
            ):
                short_key = _lower_camel(field_words[len(entity_words) :])
                payload.setdefault(short_key, value)
        records.append(payload)
    return records


def _collection_alias_exports(context: CandidateContext) -> str:
    used_aliases = {
        "contentDataPlan",
        "contentDataSha256",
        "contentData",
        "dataCollections",
    }
    exports: list[str] = []
    for collection in context.content_data.data_collections:
        base_words = _identifier_words(str(getattr(collection, "entity_id", "")))
        singular_base = _lower_camel(_singularize(base_words))
        plural_base = _lower_camel(_pluralize(base_words))
        force_prefix = _needs_typescript_prefix(singular_base) or _needs_typescript_prefix(
            plural_base
        )
        singular_alias = _unique_alias(
            _valid_typescript_identifier(singular_base, force_prefix=force_prefix),
            used_aliases,
        )
        if plural_base == singular_base:
            plural_alias = singular_alias
        else:
            plural_alias = _unique_alias(
                _valid_typescript_identifier(plural_base, force_prefix=force_prefix),
                used_aliases,
            )
        records = _collection_seed_records(collection)
        exports.append(_typescript_const(plural_alias, records))
        if singular_alias != plural_alias:
            exports.append(f"export const {singular_alias} = {plural_alias};\n")
    return "".join(exports)


def _contract_id_export_names(raw_id: str) -> tuple[str, ...]:
    """Map contract ids to TypeScript export names models commonly invent."""

    mixed = re.sub(r"[^A-Za-z0-9]+", "_", str(raw_id or "")).strip("_")
    if not mixed:
        return ()
    names: list[str] = []
    for candidate in (mixed.upper(), mixed, mixed.lower()):
        if not candidate or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", candidate):
            continue
        if candidate not in names:
            names.append(candidate)
    return tuple(names)


def _seed_records_for_contract_export(collection: object) -> list[dict[str, object]]:
    """Seed rows keyed by FIELD_* ids (and camelCase aliases) for DATA_* imports."""

    records: list[dict[str, object]] = []
    entity_words = _identifier_words(str(getattr(collection, "entity_id", "")))
    for seed_record in getattr(collection, "seed_records", ()):
        payload: dict[str, object] = {}
        for item in getattr(seed_record, "values", ()):
            field_id = str(getattr(item, "field_id", "") or "")
            raw_value = getattr(item, "value", None)
            # Keep seed values stringly-typed so DATA_*.map field access is
            # assignable to React key/value/ReactNode props under tsc.
            if raw_value is None:
                value: object = ""
            elif isinstance(raw_value, bool):
                value = "true" if raw_value else "false"
            else:
                value = str(raw_value)
            for name in _contract_id_export_names(field_id):
                payload.setdefault(name, value)
            field_words = _identifier_words(field_id)
            full_key = _lower_camel(field_words)
            payload.setdefault(full_key, value)
            if (
                len(field_words) > len(entity_words)
                and field_words[: len(entity_words)] == entity_words
            ):
                short_key = _lower_camel(field_words[len(entity_words) :])
                payload.setdefault(short_key, value)
        records.append(payload)
    return records


def _contract_id_alias_exports(context: CandidateContext) -> str:
    used: set[str] = {
        "contentDataPlan",
        "contentDataSha256",
        "contentData",
        "dataCollections",
    }
    exports: list[str] = []
    for index, item in enumerate(context.content_data.content_items):
        names = [
            name
            for name in _contract_id_export_names(item.content_id)
            if name not in used
        ]
        if not names:
            continue
        primary = names[0]
        used.add(primary)
        exports.append(
            f"export const {primary} = "
            f"contentDataPlan.content_items[{index}].value;\n"
        )
        for alias in names[1:]:
            if alias in used:
                continue
            used.add(alias)
            exports.append(f"export const {alias} = {primary};\n")
    for index, collection in enumerate(context.content_data.data_collections):
        names = [
            name
            for name in _contract_id_export_names(collection.collection_id)
            if name not in used
        ]
        if not names:
            continue
        primary = names[0]
        used.add(primary)
        # Dual runtime shape: array methods (.map) + collection (.seed_records).
        records_literal = json.dumps(
            _seed_records_for_contract_export(collection),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        exports.append(
            f"export const {primary} = Object.assign(\n"
            f"  {records_literal} as Array<Record<string, string>>,\n"
            f"  contentDataPlan.data_collections[{index}],\n"
            f");\n"
        )
        for alias in names[1:]:
            if alias in used:
                continue
            used.add(alias)
            exports.append(f"export const {alias} = {primary};\n")
    return "".join(exports)


def ensure_content_data_compat_aliases(
    source: str,
    *,
    context: CandidateContext | None = None,
) -> str:
    """Append stable aliases models commonly import from content-data.ts."""

    updated = source
    if "export const contentData " not in updated:
        updated += "export const contentData = contentDataPlan.content_items;\n"
    if "export const dataCollections " not in updated:
        updated += (
            "export const dataCollections = contentDataPlan.data_collections;\n"
        )
    if context is not None:
        updated += _contract_id_alias_exports(context)
    return updated


def build_data_sources(context: CandidateContext) -> tuple[CandidateSourceFile, ...]:
    content_payload = context.content_data.model_dump(mode="json")
    page_payload = context.page_purpose.model_dump(mode="json")
    interaction_payload = context.interactions.model_dump(mode="json")
    content_ids = tuple(
        item.content_id for item in context.content_data.content_items
    )
    collection_ids = tuple(
        item.collection_id for item in context.content_data.data_collections
    )
    page_ids = tuple(item.page_id for item in context.page_purpose.pages)
    action_ids = tuple(
        item.action_id for item in context.interactions.interactions
    )
    return (
        CandidateSourceFile(
            path="src/generated/content-data.json",
            file_kind="data",
            owner_contract_ids=content_ids + collection_ids,
            source=canonical_json(content_payload) + "\n",
        ),
        CandidateSourceFile(
            path="src/generated/content-data.ts",
            file_kind="data",
            owner_contract_ids=content_ids + collection_ids,
            source=ensure_content_data_compat_aliases(
                _typescript_const("contentDataPlan", content_payload)
                + _typescript_const(
                    "contentDataSha256",
                    context.refs.content_data_plan_ref.sha256,
                )
                + _collection_alias_exports(context),
                context=context,
            ),
        ),
        CandidateSourceFile(
            path="src/generated/canonical-contracts.ts",
            file_kind="contract",
            owner_contract_ids=page_ids + action_ids,
            source=(
                _typescript_const("pagePurposeContract", page_payload)
                + _typescript_const("interactionContract", interaction_payload)
            ),
        ),
    )


def _symbol(identifier: str, suffix: str = "") -> str:
    parts = re.findall(r"[A-Za-z0-9]+", identifier)
    return "".join(part[:1].upper() + part[1:].lower() for part in parts) + suffix


def page_export_symbol(page_id: str) -> str:
    return _symbol(page_id, "Page")


def component_export_symbol(component_id: str) -> str:
    return _symbol(component_id, "Component")


def _page_file_map(
    context: CandidateContext,
    page_sources: tuple[CandidateSourceFile, ...],
) -> dict[str, CandidateSourceFile]:
    result: dict[str, CandidateSourceFile] = {}
    tier_page_ids = {item.page_id for item in context.page_purpose.pages}
    for source in page_sources:
        owners = tier_page_ids.intersection(source.owner_contract_ids)
        if len(owners) != 1:
            raise ValueError(
                f"Page file {source.path} must own exactly one Tier 1 page."
            )
        page_id = next(iter(owners))
        if page_id in result:
            raise ValueError(f"Tier 1 page {page_id} has multiple page files.")
        result[page_id] = source
    if set(result) != tier_page_ids:
        raise ValueError("Every Tier 1 page requires exactly one page file.")
    return result


def build_route_sources(
    context: CandidateContext,
    page_sources: tuple[CandidateSourceFile, ...],
) -> tuple[CandidateSourceFile, ...]:
    page_file_map = _page_file_map(context, page_sources)
    ia_pages = {
        item.page_id: item for item in context.composition.information_architecture.pages
    }
    page_rows = []
    imports = []
    route_elements = []
    for page in context.page_purpose.pages:
        source = page_file_map[page.page_id]
        symbol = page_export_symbol(page.page_id)
        import_path = "./" + source.path.removeprefix("src/").removesuffix(".tsx")
        imports.append(f'import {{ {symbol} }} from "{import_path}";')
        page_rows.append(
            {
                "pageId": page.page_id,
                "route": page.route,
                "roleIds": list(page.role_ids),
                "surface": page.surface,
                "navigationVisibility": page.navigation_visibility,
                "mobile": page.mobile.model_dump(mode="json"),
            }
        )
        roles = json.dumps(list(page.role_ids), ensure_ascii=False)
        route_elements.append(
            "      <Route\n"
            f'        path="{page.route}"\n'
            "        element={\n"
            f'          <RoleAccess pageId="{page.page_id}" roleIds={{{roles}}}>\n'
            f"            <{symbol} />\n"
            "          </RoleAccess>\n"
            "        }\n"
            "      />"
        )

    tier_ids = {item.page_id for item in context.page_purpose.pages}
    navigation_groups = [
        {
            "id": group.id,
            "label": group.label,
            "surface": group.surface,
            "roleIds": list(group.role_ids),
            "pageIds": [
                page_id for page_id in group.page_ids if page_id in tier_ids
            ],
        }
        for group in context.composition.information_architecture.navigation_groups
        if any(page_id in tier_ids for page_id in group.page_ids)
    ]
    role_access = [
        {
            "roleId": item.role_id,
            "entryPageId": item.entry_page_id,
            "accessiblePageIds": [
                page_id
                for page_id in item.accessible_page_ids
                if page_id in tier_ids
            ],
        }
        for item in context.composition.information_architecture.role_access
        if item.entry_page_id in tier_ids
    ]
    first_route = context.page_purpose.pages[0].route
    app_source = (
        'import { Navigate, Route, Routes } from "react-router-dom";\n'
        + "\n".join(imports)
        + '\nimport { RoleAccess } from "./runtime/RoleAccess";\n\n'
        + "export default function App() {\n"
        + "  return (\n"
        + "    <Routes>\n"
        + "\n".join(route_elements)
        + "\n"
        + f'      <Route path="*" element={{<Navigate to="{first_route}" replace />}} />\n'
        + "    </Routes>\n"
        + "  );\n"
        + "}\n"
    )
    return (
        CandidateSourceFile(
            path="src/generated/route-manifest.ts",
            file_kind="route",
            owner_contract_ids=tuple(item.page_id for item in context.page_purpose.pages),
            source=(
                _typescript_const("routeManifest", page_rows)
                + _typescript_const(
                    "routeManifestSha256",
                    sha256_text(canonical_json(page_rows)),
                )
            ),
        ),
        CandidateSourceFile(
            path="src/generated/navigation.ts",
            file_kind="navigation",
            owner_contract_ids=tuple(item.page_id for item in context.page_purpose.pages),
            source=(
                _typescript_const("navigationGroups", navigation_groups)
                + _typescript_const("roleAccess", role_access)
            ),
        ),
        CandidateSourceFile(
            path="src/App.tsx",
            file_kind="route",
            owner_contract_ids=tuple(item.page_id for item in context.page_purpose.pages),
            source=app_source,
        ),
    )


def source_manifest(
    *,
    artifact_kind: CandidateArtifactKind,
    input_hashes: tuple[str, ...],
    sources: tuple[CandidateSourceFile, ...],
) -> CandidateArtifactManifest:
    return CandidateArtifactManifest(
        artifact_kind=artifact_kind,
        input_hashes=input_hashes,
        files=tuple(
            CandidateFileDescriptor(
                path=item.path,
                file_kind=item.file_kind,
                owner_contract_ids=item.owner_contract_ids,
                sha256=sha256_text(item.source),
                byte_count=len(item.source.encode("utf-8")),
            )
            for item in sources
        ),
    )


__all__ = [
    "CandidateSourceFile",
    "build_data_sources",
    "build_foundation_sources",
    "build_route_sources",
    "component_export_symbol",
    "dependency_lock_sha256",
    "ensure_content_data_compat_aliases",
    "page_export_symbol",
    "source_manifest",
]
