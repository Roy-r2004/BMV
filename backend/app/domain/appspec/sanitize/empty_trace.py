"""Bounded empty-trace classification, diagnostics, and optional normalization.

Does not invent requirements, evidence, journeys, pages, or acceptance tests.
Required empty traces remain invalid for AI schema repair / fail-closed handling.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

TraceClassification = Literal["optional", "required", "conditional"]

# TraceabilityLink field policy — mirrors AppSpec schema min_length rules.
_TRACE_LINK_FIELDS: dict[str, dict[str, Any]] = {
    "capability_ids": {
        "classification": "required",
        "min_items": 1,
        "referenced_object": "capabilities",
        "reason": "TraceabilityLink.capability_ids requires at least one capability ID.",
    },
    "page_ids": {
        "classification": "required",
        "min_items": 1,
        "referenced_object": "pages",
        "reason": "TraceabilityLink.page_ids requires at least one page ID.",
    },
    "evidence_ids": {
        "classification": "required",
        "min_items": 1,
        "referenced_object": "evidence",
        "reason": "TraceabilityLink.evidence_ids requires at least one evidence ID.",
    },
    "journey_ids": {
        "classification": "optional",
        "min_items": 0,
        "referenced_object": "journeys",
        "reason": "TraceabilityLink.journey_ids may be omitted when no journey proof exists.",
    },
    "acceptance_test_ids": {
        "classification": "required",
        "min_items": 1,
        "referenced_object": "acceptance_tests",
        "reason": "TraceabilityLink.acceptance_test_ids requires at least one acceptance test ID.",
    },
}

# Conditional: assertion claims evidence → evidence_id required when kind needs it.
_CONDITIONAL_ASSERTION_EVIDENCE = frozenset(
    {"visible", "state", "data", "count", "text", "metric", "status"}
)

EARLY_TRACE_CODES = frozenset(
    {
        "empty_required_trace",
        "empty_optional_trace",
        "trace_not_array",
        "trace_contains_empty_string",
        "trace_contains_unknown_id",
        "trace_contains_duplicate_id",
        "trace_wrong_object_type",
    }
)


@dataclass
class EmptyTraceNormalizeResult:
    payload: dict[str, Any]
    applied: bool = False
    changed_paths: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    refused_reasons: list[str] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)


def classify_trace_field(field_name: str) -> TraceClassification | None:
    meta = _TRACE_LINK_FIELDS.get(field_name)
    if meta is None:
        return None
    return meta["classification"]  # type: ignore[return-value]


def trace_field_constraints(field_name: str) -> dict[str, Any] | None:
    meta = _TRACE_LINK_FIELDS.get(field_name)
    if meta is None:
        return None
    return {
        "field": field_name,
        "classification": meta["classification"],
        "min_items": meta["min_items"],
        "referenced_object": meta["referenced_object"],
        "reason": meta["reason"],
    }


def collect_canonical_ids(payload: Mapping[str, Any]) -> dict[str, list[str]]:
    """Collect existing object IDs available for repair (no invention)."""

    groups = {
        "requirements": "requirements",
        "capabilities": "capabilities",
        "pages": "pages",
        "evidence": "evidence",
        "journeys": "journeys",
        "acceptance_tests": "acceptance_tests",
        "roles": "roles",
        "states": "states",
        "actions": "actions",
        "entities": "entities",
    }
    out: dict[str, list[str]] = {}
    for key, label in groups.items():
        ids: list[str] = []
        for item in payload.get(key) or []:
            if isinstance(item, dict) and item.get("id"):
                text = str(item["id"]).strip()
                if text:
                    ids.append(text)
        out[label] = ids
    return out


def _is_empty_collection(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 0


def _scan_id_list(
    *,
    values: Any,
    path: str,
    allowed_ids: set[str],
    classification: TraceClassification,
    min_items: int,
    issues: list[dict[str, Any]],
) -> None:
    if values is None:
        if classification == "required" or min_items > 0:
            issues.append(
                {
                    "severity": "blocking",
                    "code": "empty_required_trace",
                    "message": "Required trace field is null.",
                    "path": path,
                    "classification": classification,
                    "original_representation": None,
                    "min_items": min_items,
                }
            )
        return
    if not isinstance(values, (list, tuple)):
        issues.append(
            {
                "severity": "blocking",
                "code": "trace_not_array",
                "message": "Trace field must be an array of IDs.",
                "path": path,
                "classification": classification,
                "original_representation": type(values).__name__,
                "min_items": min_items,
            }
        )
        return

    if len(values) == 0:
        code = (
            "empty_optional_trace"
            if classification == "optional"
            else "empty_required_trace"
        )
        issues.append(
            {
                "severity": "info" if classification == "optional" else "blocking",
                "code": code,
                "message": (
                    "Optional trace collection is empty."
                    if classification == "optional"
                    else "Required trace collection is empty."
                ),
                "path": path,
                "classification": classification,
                "original_representation": list(values),
                "min_items": min_items,
            }
        )
        return

    seen: set[str] = set()
    for index, item in enumerate(values):
        item_path = f"{path}[{index}]"
        if not isinstance(item, str):
            issues.append(
                {
                    "severity": "blocking",
                    "code": "trace_wrong_object_type",
                    "message": "Trace ID must be a string.",
                    "path": item_path,
                    "classification": classification,
                    "original_representation": type(item).__name__,
                }
            )
            continue
        if not item.strip():
            issues.append(
                {
                    "severity": "blocking",
                    "code": "trace_contains_empty_string",
                    "message": "Trace ID cannot be an empty string.",
                    "path": item_path,
                    "classification": classification,
                    "original_representation": item,
                }
            )
            continue
        if item in seen:
            issues.append(
                {
                    "severity": "blocking",
                    "code": "trace_contains_duplicate_id",
                    "message": f"Duplicate trace ID {item!r}.",
                    "path": item_path,
                    "classification": classification,
                    "original_representation": item,
                }
            )
            continue
        seen.add(item)
        if allowed_ids and item not in allowed_ids:
            issues.append(
                {
                    "severity": "blocking",
                    "code": "trace_contains_unknown_id",
                    "message": f"Trace ID {item!r} is not present in the candidate.",
                    "path": item_path,
                    "classification": classification,
                    "original_representation": item,
                }
            )


def scan_empty_traces(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Lightweight structural diagnostics for trace collections (non-authoritative)."""

    data = dict(payload or {})
    canonical = collect_canonical_ids(data)
    issues: list[dict[str, Any]] = []

    for index, link in enumerate(data.get("traceability") or []):
        if not isinstance(link, dict):
            issues.append(
                {
                    "severity": "blocking",
                    "code": "trace_wrong_object_type",
                    "message": "Traceability link must be an object.",
                    "path": f"traceability[{index}]",
                    "classification": "required",
                    "original_representation": type(link).__name__,
                }
            )
            continue
        for field_name, meta in _TRACE_LINK_FIELDS.items():
            path = f"traceability[{index}].{field_name}"
            allowed = set(canonical.get(meta["referenced_object"]) or [])
            # Field missing: optional → ok; required → empty_required when present as []
            # Missing required fields are handled by pydantic missing_required_field.
            if field_name not in link:
                continue
            _scan_id_list(
                values=link.get(field_name),
                path=path,
                allowed_ids=allowed,
                classification=meta["classification"],
                min_items=int(meta["min_items"]),
                issues=issues,
            )

    # Conditional: assertions that claim evidence must name evidence_id when present.
    for t_index, test in enumerate(data.get("acceptance_tests") or []):
        if not isinstance(test, dict):
            continue
        for a_index, assertion in enumerate(test.get("assertions") or []):
            if not isinstance(assertion, dict):
                continue
            kind = str(assertion.get("kind") or "").casefold()
            path = f"acceptance_tests[{t_index}].assertions[{a_index}].evidence_id"
            if kind in _CONDITIONAL_ASSERTION_EVIDENCE:
                evidence_id = assertion.get("evidence_id")
                if evidence_id is None or (
                    isinstance(evidence_id, str) and not evidence_id.strip()
                ):
                    issues.append(
                        {
                            "severity": "blocking",
                            "code": "empty_required_trace",
                            "message": (
                                "Assertion kind requires evidence_id when claiming "
                                "observable proof."
                            ),
                            "path": path,
                            "classification": "conditional",
                            "condition": f"assertion.kind in {sorted(_CONDITIONAL_ASSERTION_EVIDENCE)}",
                            "original_representation": evidence_id,
                            "min_items": 1,
                        }
                    )
                elif isinstance(evidence_id, str):
                    allowed = set(canonical.get("evidence") or [])
                    if allowed and evidence_id not in allowed:
                        issues.append(
                            {
                                "severity": "blocking",
                                "code": "trace_contains_unknown_id",
                                "message": (
                                    f"Assertion evidence_id {evidence_id!r} is unknown."
                                ),
                                "path": path,
                                "classification": "conditional",
                                "original_representation": evidence_id,
                            }
                        )

    return issues[:80]


def normalize_optional_empty_traces(
    payload: Mapping[str, Any] | None,
) -> EmptyTraceNormalizeResult:
    """Remove optional empty trace collections; refuse to touch required empties."""

    original = copy.deepcopy(dict(payload or {}))
    working = copy.deepcopy(original)
    result = EmptyTraceNormalizeResult(payload=working)

    for index, link in enumerate(working.get("traceability") or []):
        if not isinstance(link, dict):
            continue
        for field_name, meta in _TRACE_LINK_FIELDS.items():
            if field_name not in link:
                continue
            path = f"traceability[{index}].{field_name}"
            value = link.get(field_name)
            classification = meta["classification"]
            if classification == "optional" and _is_empty_collection(value):
                # Schema allows omission / default empty — drop explicit empty array.
                original_repr = list(value) if isinstance(value, (list, tuple)) else value
                del link[field_name]
                result.applied = True
                result.changed_paths.append(path)
                result.actions.append(f"omit_optional_empty_trace:{path}")
                result.records.append(
                    {
                        "path": path,
                        "classification": "optional",
                        "original_representation": original_repr,
                        "normalized_representation": None,
                        "reason": (
                            "Optional empty trace collection omitted; schema default "
                            "allows empty/absent journey proof."
                        ),
                    }
                )
            elif classification == "required" and (
                _is_empty_collection(value) or value is None
            ):
                result.refused_reasons.append(
                    f"refuse_empty_required_trace:{path}"
                )
                result.records.append(
                    {
                        "path": path,
                        "classification": "required",
                        "original_representation": (
                            list(value) if isinstance(value, (list, tuple)) else value
                        ),
                        "normalized_representation": (
                            list(value) if isinstance(value, (list, tuple)) else value
                        ),
                        "reason": (
                            "Required empty trace retained for fail-closed / AI repair; "
                            "IDs are not invented."
                        ),
                    }
                )

    result.payload = working
    return result


def schema_repair_trace_context(
    payload: Mapping[str, Any] | None,
    *,
    schema_issue: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build repair-prompt context for invalid_trace_shape / empty required traces."""

    data = dict(payload or {})
    early = scan_empty_traces(data)
    canonical = collect_canonical_ids(data)
    field_notes: list[dict[str, Any]] = []
    paths: list[str] = []
    if isinstance(schema_issue, Mapping):
        for item in schema_issue.get("issues") or []:
            if not isinstance(item, Mapping):
                continue
            path = str(item.get("path") or "")
            if path:
                paths.append(path)
            code = str(item.get("code") or "")
            if "trace" in path.lower() or code in {
                "invalid_trace_shape",
                "empty_required_trace",
                "empty_optional_trace",
            }:
                field_name = path.rsplit(".", 1)[-1] if path else ""
                constraints = trace_field_constraints(field_name) or {
                    "field": field_name,
                    "classification": "unknown",
                    "min_items": None,
                }
                field_notes.append(
                    {
                        "path": path,
                        "issue_code": code,
                        "message": item.get("message"),
                        **constraints,
                        "available_canonical_ids": canonical.get(
                            str(constraints.get("referenced_object") or ""),
                            [],
                        ),
                    }
                )

    for issue in early:
        if issue.get("code") != "empty_required_trace":
            continue
        path = str(issue.get("path") or "")
        if path in paths:
            continue
        field_name = path.rsplit(".", 1)[-1] if path else ""
        constraints = trace_field_constraints(field_name) or {}
        field_notes.append(
            {
                "path": path,
                "issue_code": issue.get("code"),
                "message": issue.get("message"),
                **constraints,
                "available_canonical_ids": canonical.get(
                    str(constraints.get("referenced_object") or ""),
                    [],
                ),
            }
        )

    return {
        "canonical_ids": canonical,
        "early_trace_diagnostics": early,
        "trace_field_notes": field_notes[:40],
        "rules": [
            "never emit an empty array for a field with minItems=1",
            "omit optional trace fields when no trace exists",
            "required trace fields must contain at least one existing canonical ID",
            "never invent placeholder IDs, requirements, evidence, journeys, pages, or tests",
            "you may only reuse IDs already present in the rejected candidate",
        ],
    }


__all__ = [
    "EARLY_TRACE_CODES",
    "EmptyTraceNormalizeResult",
    "classify_trace_field",
    "collect_canonical_ids",
    "normalize_optional_empty_traces",
    "scan_empty_traces",
    "schema_repair_trace_context",
    "trace_field_constraints",
]
