"""Deterministic pre-parse normalization for syntax/representation-only AppSpec fixes."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.domain.schemas.app_spec import AppSpec

# Root keys that are never authoritative product content.
_NON_AUTHORITATIVE_ROOT_KEYS = frozenset(
    {
        "_meta",
        "__meta__",
        "metadata",
        "generator_notes",
        "debug",
        "_debug",
        "comments",
        "__comments__",
    }
)

# Optional collections that may default to empty when missing (schema defaults).
_OPTIONAL_EMPTY_LIST_FIELDS = frozenset(
    {
        "assumptions",
        "open_questions",
        "entities",
        "actions",
        "transitions",
        "journeys",
        "deferred_scope",
        "traceability",
    }
)

# Fields where a lone scalar is semantically equivalent to a one-item list.
_SCALAR_TO_LIST_FIELDS = frozenset(
    {
        "target_users",
        "success_metrics",
        "goals",
        "source_refs",
        "requirement_ids",
        "role_ids",
        "entity_ids",
        "capability_ids",
        "state_ids",
        "action_ids",
        "evidence_ids",
        "page_ids",
        "journey_ids",
        "acceptance_test_ids",
        "enum_values",
    }
)

_ENUM_FIELDS: dict[str, frozenset[str]] = {
    "priority": frozenset({"must", "should", "could"}),
    "verification_mode": frozenset({"interaction", "inspection", "analysis"}),
    "surface": frozenset({"public", "authenticated", "admin"}),
    "kind": frozenset(
        {
            # evidence kinds + assertion kinds (disjoint enough for unambiguous casefold)
            "text",
            "metric",
            "list",
            "table",
            "chart",
            "form",
            "status",
            "navigation",
            "media",
            "route",
            "visible",
            "state",
            "data",
            "count",
            "accessibility",
            "no_runtime_errors",
        }
    ),
    "type": frozenset(
        {
            "string",
            "number",
            "boolean",
            "enum",
            "reference",
            "datetime",
            "currency",
        }
    ),
}

_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


@dataclass
class PreparseNormalizeResult:
    """Outcome of one deterministic pre-parse normalization attempt."""

    payload: dict[str, Any]
    applied: bool = False
    changed_paths: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    refused_reasons: list[str] = field(default_factory=list)
    original_sha256: str = ""
    normalized_sha256: str = ""
    raw_json_repaired: bool = False

    @property
    def result_label(self) -> str:
        if self.refused_reasons and not self.applied:
            return "rejected"
        if self.applied:
            return "normalized"
        return "unchanged"


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def repair_trailing_commas(text: str) -> tuple[str, bool]:
    """Remove harmless trailing commas before ``}`` / ``]`` (bounded, non-semantic)."""

    original = text
    previous = None
    current = text
    # Bound iterations so pathological input cannot loop forever.
    for _ in range(32):
        if current == previous:
            break
        previous = current
        current = _TRAILING_COMMA_RE.sub(r"\1", current)
    return current, current != original


def extract_json_object_text(raw: str) -> tuple[str | None, dict[str, Any]]:
    """Extract one JSON object text from markdown/prose; return extraction meta."""

    text = (raw or "").strip()
    meta: dict[str, Any] = {"method": None, "ok": False}
    if not text:
        meta["error"] = "empty"
        return None, meta
    try:
        json.loads(text)
        meta.update({"method": "direct", "ok": True})
        return text, meta
    except Exception:
        pass

    fenced = text
    if text.startswith("```"):
        fenced = re.sub(
            r"^```(?:json|tsx?|javascript|typescript)?\s*\n?",
            "",
            text,
            count=1,
        )
        fenced = re.sub(r"\n?```\s*$", "", fenced, count=1).strip()
        try:
            json.loads(fenced)
            meta.update({"method": "markdown_fence", "ok": True})
            return fenced, meta
        except Exception:
            repaired, changed = repair_trailing_commas(fenced)
            if changed:
                try:
                    json.loads(repaired)
                    meta.update(
                        {
                            "method": "markdown_fence_trailing_comma",
                            "ok": True,
                            "trailing_comma_fixed": True,
                        }
                    )
                    return repaired, meta
                except Exception:
                    pass

    search_in = fenced if fenced != text else text
    start = search_in.find("{")
    if start == -1:
        meta["error"] = "no_object"
        return None, meta
    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(search_in[start:], start):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = search_in[start : i + 1]
                try:
                    json.loads(candidate)
                    meta.update({"method": "bracket_match", "ok": True})
                    return candidate, meta
                except Exception:
                    repaired, changed = repair_trailing_commas(candidate)
                    if changed:
                        try:
                            json.loads(repaired)
                            meta.update(
                                {
                                    "method": "bracket_match_trailing_comma",
                                    "ok": True,
                                    "trailing_comma_fixed": True,
                                }
                            )
                            return repaired, meta
                        except Exception as exc:
                            meta["error"] = str(exc)
                            return None, meta
                    meta["error"] = "invalid_object"
                    return None, meta
    meta["error"] = "unbalanced"
    return None, meta


def _normalize_enum_value(field_name: str, value: Any) -> tuple[Any, bool]:
    if not isinstance(value, str):
        return value, False
    allowed = _ENUM_FIELDS.get(field_name)
    if not allowed:
        return value, False
    folded = value.strip().casefold()
    matches = [item for item in allowed if item.casefold() == folded]
    if len(matches) != 1:
        return value, False
    if matches[0] == value:
        return value, False
    return matches[0], True


def _dedupe_list(values: list[Any]) -> tuple[list[Any], bool]:
    out: list[Any] = []
    seen: set[str] = set()
    changed = False
    for item in values:
        key = json.dumps(item, sort_keys=True, default=str) if not isinstance(item, str) else item
        if key in seen:
            changed = True
            continue
        seen.add(key)
        out.append(item)
    return out, changed


def _walk_normalize(
    node: Any,
    *,
    path: str,
    changed_paths: list[str],
    actions: list[str],
    parent_key: str | None = None,
) -> Any:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in list(node.items()):
            child_path = f"{path}.{key}" if path else str(key)
            if key in _NON_AUTHORITATIVE_ROOT_KEYS:
                actions.append(f"drop_non_authoritative:{child_path or key}")
                changed_paths.append(child_path or str(key))
                continue
            new_value = _walk_normalize(
                value,
                path=child_path,
                changed_paths=changed_paths,
                actions=actions,
                parent_key=str(key),
            )
            if (
                str(key) in _SCALAR_TO_LIST_FIELDS
                and new_value is not None
                and not isinstance(new_value, list)
                and isinstance(new_value, (str, int, float, bool))
            ):
                new_value = [new_value]
                actions.append(f"scalar_to_list:{child_path}")
                changed_paths.append(child_path)
            if isinstance(new_value, list):
                deduped, deduped_changed = _dedupe_list(new_value)
                if deduped_changed:
                    new_value = deduped
                    actions.append(f"dedupe_list:{child_path}")
                    changed_paths.append(child_path)
            if str(key) in _ENUM_FIELDS and isinstance(new_value, str):
                normalized, enum_changed = _normalize_enum_value(str(key), new_value)
                if enum_changed:
                    new_value = normalized
                    actions.append(f"enum_case:{child_path}")
                    changed_paths.append(child_path)
            out[key] = new_value
        return out
    if isinstance(node, list):
        return [
            _walk_normalize(
                item,
                path=f"{path}[{index}]",
                changed_paths=changed_paths,
                actions=actions,
                parent_key=parent_key,
            )
            for index, item in enumerate(node)
        ]
    if parent_key in _ENUM_FIELDS and isinstance(node, str):
        normalized, enum_changed = _normalize_enum_value(parent_key, node)
        if enum_changed:
            actions.append(f"enum_case:{path}")
            changed_paths.append(path)
            return normalized
    return node


def normalize_app_spec_preparse(
    payload: Mapping[str, Any] | None,
) -> PreparseNormalizeResult:
    """Apply one bounded representation-only normalization pass.

    Never invents pages, requirements, actions, evidence, or acceptance tests.
    """

    original = copy.deepcopy(dict(payload or {}))
    original_sha = _canonical_sha256(original)
    result = PreparseNormalizeResult(
        payload=original,
        original_sha256=original_sha,
        normalized_sha256=original_sha,
    )
    working = copy.deepcopy(original)
    changed_paths: list[str] = []
    actions: list[str] = []

    for field_name in _OPTIONAL_EMPTY_LIST_FIELDS:
        if field_name not in working:
            working[field_name] = []
            actions.append(f"default_optional_empty:{field_name}")
            changed_paths.append(field_name)
        elif working.get(field_name) is None:
            working[field_name] = []
            actions.append(f"null_optional_to_empty:{field_name}")
            changed_paths.append(field_name)

    # schema_version default only when missing/blank — never invent product content.
    if not working.get("schema_version"):
        working["schema_version"] = "1.0"
        actions.append("default_schema_version")
        changed_paths.append("schema_version")

    working = _walk_normalize(
        working,
        path="",
        changed_paths=changed_paths,
        actions=actions,
        parent_key=None,
    )

    # Drop duplicate empty optional noise only — do not delete required records.
    if actions:
        result.payload = working
        result.applied = True
        result.changed_paths = changed_paths[:80]
        result.actions = actions[:80]
        result.normalized_sha256 = _canonical_sha256(working)
    return result


def schema_fragments_for_paths(
    paths: list[str],
    *,
    max_fragments: int = 12,
) -> dict[str, Any]:
    """Return a small subset of the live AppSpec JSON schema for repair prompts."""

    schema = AppSpec.model_json_schema()
    defs = schema.get("$defs") or schema.get("definitions") or {}
    fragments: dict[str, Any] = {"root_required": schema.get("required"), "defs": {}}
    wanted = {
        "Page",
        "Action",
        "Evidence",
        "TraceabilityLink",
        "AcceptanceTest",
        "AcceptanceAssertion",
        "Requirement",
        "AppSpec",
    }
    for path in paths:
        lowered = path.lower()
        if "page" in lowered:
            wanted.add("Page")
        if "action" in lowered:
            wanted.add("Action")
        if "evidence" in lowered:
            wanted.add("Evidence")
        if "trace" in lowered:
            wanted.add("TraceabilityLink")
        if "acceptance" in lowered or "assertion" in lowered:
            wanted.add("AcceptanceTest")
            wanted.add("AcceptanceAssertion")
        if "requirement" in lowered:
            wanted.add("Requirement")
    for name in list(wanted)[:max_fragments]:
        if name in defs:
            fragments["defs"][name] = defs[name]
    return fragments


__all__ = [
    "PreparseNormalizeResult",
    "extract_json_object_text",
    "normalize_app_spec_preparse",
    "repair_trailing_commas",
    "schema_fragments_for_paths",
]
