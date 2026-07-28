"""Bounded pre-schema reconciliation for traceability capability/evidence refs.

Runs after JSON parsing and before strict ``AppSpec`` validation. Two phases:

1. Normalize every trace ID collection: drop blanks, drop unknown IDs, dedupe,
   preserve first-seen order.
2. Repair a row whose ``capability_ids`` or ``evidence_ids`` is empty, using only
   relationships already written elsewhere in the same raw payload.

The reconciler never reads names, titles, descriptions, or ID wording, and never
creates capabilities, evidence, pages, requirements, traces, or relationships. A
row that cannot be proven uniquely is left empty and reported as unresolved so
strict validation still fails closed.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

# Trace field -> collection whose object IDs are legal values for that field.
_TRACE_FIELD_SOURCES: dict[str, str] = {
    "requirement_id": "requirements",
    "capability_ids": "capabilities",
    "page_ids": "pages",
    "evidence_ids": "evidence",
    "journey_ids": "journeys",
    "acceptance_test_ids": "acceptance_tests",
}

_ID_LIST_FIELDS = (
    "capability_ids",
    "page_ids",
    "evidence_ids",
    "journey_ids",
    "acceptance_test_ids",
)

CAPABILITIES_UNRESOLVED = "traceability_empty_capabilities_unresolved"
EVIDENCE_UNRESOLVED = "traceability_empty_evidence_unresolved"
REFS_AMBIGUOUS = "traceability_empty_refs_ambiguous"

UNRESOLVED_TRACE_REFERENCE_CODES = frozenset(
    {CAPABILITIES_UNRESOLVED, EVIDENCE_UNRESOLVED, REFS_AMBIGUOUS}
)

_MAX_RECORDS = 80


@dataclass
class TraceReferenceReconcileResult:
    """Outcome of one bounded trace-reference reconciliation pass."""

    payload: dict[str, Any]
    applied: bool = False
    changed_paths: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    original_sha256: str = ""
    result_sha256: str = ""

    @property
    def result_label(self) -> str:
        if self.unresolved and not self.applied:
            return "rejected"
        if self.applied:
            return "reconciled"
        return "unchanged"

    @property
    def unresolved_codes(self) -> list[str]:
        seen: list[str] = []
        for item in self.unresolved:
            code = str(item.get("code") or "")
            if code and code not in seen:
                seen.append(code)
        return seen


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _objects(payload: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    return [item for item in (payload.get(key) or []) if isinstance(item, dict)]


def _ids(payload: Mapping[str, Any], key: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in _objects(payload, key):
        item_id = str(item.get("id") or "").strip()
        if item_id and item_id not in indexed:
            indexed[item_id] = item
    return indexed


def _id_list(value: Any) -> list[str]:
    """Read a trace field as ordered strings without judging membership."""

    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                out.append(text)
    return out


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _normalize_field(
    *,
    link: dict[str, Any],
    field_name: str,
    allowed: set[str],
    path: str,
    changed_paths: list[str],
    actions: list[str],
) -> None:
    """Drop blanks/unknowns and dedupe one trace ID collection in place."""

    if field_name not in link:
        return
    raw = link.get(field_name)
    kept = _id_list(raw)
    blank_or_typed = isinstance(raw, (list, tuple)) and len(raw) != len(kept)
    deduped = _ordered_unique(kept)
    removed_duplicates = len(deduped) != len(kept)
    known = [value for value in deduped if value in allowed]
    dropped_unknown = sorted(set(deduped) - set(known))

    if list(raw or []) == known and isinstance(raw, (list, tuple)):
        return

    link[field_name] = known
    changed_paths.append(path)
    if blank_or_typed:
        actions.append(f"drop_blank_trace_id:{path}")
    if removed_duplicates:
        actions.append(f"dedupe_trace_ids:{path}")
    for unknown in dropped_unknown:
        actions.append(f"drop_unknown_trace_id:{path}:{unknown}")
    if not (blank_or_typed or removed_duplicates or dropped_unknown):
        actions.append(f"normalize_trace_ids:{path}")


def _capabilities_claiming(
    requirement_id: str, capabilities: Mapping[str, dict[str, Any]]
) -> list[str]:
    """Capabilities whose own ``requirement_ids`` name this requirement."""

    if not requirement_id:
        return []
    return [
        capability_id
        for capability_id, capability in capabilities.items()
        if requirement_id in _id_list(capability.get("requirement_ids"))
    ]


def _capabilities_on_pages(
    page_ids: list[str],
    pages: Mapping[str, dict[str, Any]],
    capabilities: Mapping[str, dict[str, Any]],
) -> list[str]:
    """Capabilities explicitly assigned to the traced pages."""

    found: list[str] = []
    for page_id in page_ids:
        page = pages.get(page_id)
        if page is None:
            continue
        for capability_id in _id_list(page.get("capability_ids")):
            if capability_id in capabilities:
                found.append(capability_id)
    return _ordered_unique(found)


def _evidence_from_acceptance_tests(
    acceptance_test_ids: list[str],
    acceptance_tests: Mapping[str, dict[str, Any]],
    evidence: Mapping[str, dict[str, Any]],
) -> list[str]:
    """Evidence named by the row's own acceptance-test assertions."""

    found: list[str] = []
    for test_id in acceptance_test_ids:
        test = acceptance_tests.get(test_id)
        if test is None:
            continue
        for assertion in test.get("assertions") or []:
            if not isinstance(assertion, dict):
                continue
            evidence_id = str(assertion.get("evidence_id") or "").strip()
            if evidence_id and evidence_id in evidence:
                found.append(evidence_id)
    return _ordered_unique(found)


def _evidence_for_capabilities_on_pages(
    page_ids: list[str],
    capability_ids: list[str],
    evidence: Mapping[str, dict[str, Any]],
) -> list[str]:
    """Evidence owned by a traced page and linked to a traced capability."""

    page_set = set(page_ids)
    capability_set = set(capability_ids)
    found: list[str] = []
    for evidence_id, item in evidence.items():
        if str(item.get("page_id") or "").strip() not in page_set:
            continue
        if not capability_set.intersection(set(_id_list(item.get("capability_ids")))):
            continue
        found.append(evidence_id)
    return _ordered_unique(found)


def _evidence_on_pages(
    page_ids: list[str],
    pages: Mapping[str, dict[str, Any]],
    evidence: Mapping[str, dict[str, Any]],
) -> list[str]:
    """Evidence explicitly assigned to the traced pages."""

    found: list[str] = []
    for page_id in page_ids:
        page = pages.get(page_id)
        if page is None:
            continue
        for evidence_id in _id_list(page.get("evidence_ids")):
            if evidence_id in evidence:
                found.append(evidence_id)
    for evidence_id, item in evidence.items():
        if str(item.get("page_id") or "").strip() in set(page_ids):
            found.append(evidence_id)
    return _ordered_unique(found)


def _decide(
    tiers: list[tuple[str, list[str]]],
    narrow_to: list[str] | None = None,
) -> tuple[str, str, list[str]]:
    """Pick the first tier that offers candidates and require a unique answer.

    Returns ``(resolved_id, source, candidates)``. ``resolved_id`` is empty when
    no tier offered a candidate (unresolved) or when the deciding tier stayed
    ambiguous. ``candidates`` describes the deciding tier for diagnostics.
    """

    for source, candidates in tiers:
        if not candidates:
            continue
        if len(candidates) == 1:
            return candidates[0], source, candidates
        if narrow_to:
            narrowed = [value for value in candidates if value in set(narrow_to)]
            if len(narrowed) == 1:
                return narrowed[0], f"{source}+requirement_capability", narrowed
        return "", source, candidates
    return "", "", []


def reconcile_trace_references(
    payload: Mapping[str, Any] | None,
) -> TraceReferenceReconcileResult:
    """Normalize trace ID collections and repair uniquely provable empty refs."""

    original = copy.deepcopy(dict(payload or {}))
    original_sha = _canonical_sha256(original)
    result = TraceReferenceReconcileResult(
        payload=original,
        original_sha256=original_sha,
        result_sha256=original_sha,
    )

    working = copy.deepcopy(original)
    links = [
        item for item in (working.get("traceability") or []) if isinstance(item, dict)
    ]
    if not links:
        return result

    capabilities = _ids(working, "capabilities")
    pages = _ids(working, "pages")
    evidence = _ids(working, "evidence")
    acceptance_tests = _ids(working, "acceptance_tests")
    allowed_by_field = {
        "capability_ids": set(capabilities),
        "page_ids": set(pages),
        "evidence_ids": set(evidence),
        "journey_ids": set(_ids(working, "journeys")),
        "acceptance_test_ids": set(acceptance_tests),
    }

    changed_paths: list[str] = []
    actions: list[str] = []
    records: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for index, link in enumerate(links):
        requirement_id = str(link.get("requirement_id") or "").strip()

        for field_name in _ID_LIST_FIELDS:
            _normalize_field(
                link=link,
                field_name=field_name,
                allowed=allowed_by_field[field_name],
                path=f"traceability[{index}].{field_name}",
                changed_paths=changed_paths,
                actions=actions,
            )

        page_ids = _id_list(link.get("page_ids"))
        capability_ids = _id_list(link.get("capability_ids"))
        evidence_ids = _id_list(link.get("evidence_ids"))
        test_ids = _id_list(link.get("acceptance_test_ids"))
        claimed = _capabilities_claiming(requirement_id, capabilities)

        fields_repaired: list[str] = []
        ids_added: dict[str, list[str]] = {}
        sources: dict[str, str] = {}

        if not capability_ids:
            path = f"traceability[{index}].capability_ids"
            resolved, source, candidates = _decide(
                [
                    ("requirement_capability", claimed),
                    (
                        "page_capability",
                        _capabilities_on_pages(page_ids, pages, capabilities),
                    ),
                ],
                narrow_to=claimed,
            )
            if resolved:
                link["capability_ids"] = [resolved]
                capability_ids = [resolved]
                changed_paths.append(path)
                actions.append(f"reconcile_trace_capability:{path}:{resolved}")
                fields_repaired.append("capability_ids")
                ids_added["capability_ids"] = [resolved]
                sources["capability_ids"] = source
            else:
                code = REFS_AMBIGUOUS if candidates else CAPABILITIES_UNRESOLVED
                unresolved.append(
                    {
                        "code": code,
                        "path": path,
                        "trace_index": index,
                        "requirement_id": requirement_id,
                        "field": "capability_ids",
                        "considered_source": source,
                        "candidates": candidates[:20],
                        "message": (
                            "Empty traceability.capability_ids stayed ambiguous: "
                            f"{len(candidates)} capabilities were equally proven."
                            if candidates
                            else (
                                "Empty traceability.capability_ids has no capability "
                                "proven by an existing AppSpec relationship."
                            )
                        ),
                    }
                )

        if not evidence_ids:
            path = f"traceability[{index}].evidence_ids"
            resolved, source, candidates = _decide(
                [
                    (
                        "acceptance_test_assertion_evidence",
                        _evidence_from_acceptance_tests(
                            test_ids, acceptance_tests, evidence
                        ),
                    ),
                    (
                        "capability_page_evidence",
                        _evidence_for_capabilities_on_pages(
                            page_ids, capability_ids, evidence
                        ),
                    ),
                    ("page_evidence", _evidence_on_pages(page_ids, pages, evidence)),
                ]
            )
            if resolved:
                link["evidence_ids"] = [resolved]
                changed_paths.append(path)
                actions.append(f"reconcile_trace_evidence:{path}:{resolved}")
                fields_repaired.append("evidence_ids")
                ids_added["evidence_ids"] = [resolved]
                sources["evidence_ids"] = source
            else:
                code = REFS_AMBIGUOUS if candidates else EVIDENCE_UNRESOLVED
                unresolved.append(
                    {
                        "code": code,
                        "path": path,
                        "trace_index": index,
                        "requirement_id": requirement_id,
                        "field": "evidence_ids",
                        "considered_source": source,
                        "candidates": candidates[:20],
                        "message": (
                            "Empty traceability.evidence_ids stayed ambiguous: "
                            f"{len(candidates)} evidence items were equally proven."
                            if candidates
                            else (
                                "Empty traceability.evidence_ids has no evidence "
                                "proven by an existing AppSpec relationship."
                            )
                        ),
                    }
                )

        if fields_repaired:
            records.append(
                {
                    "trace_index": index,
                    "requirement_id": requirement_id,
                    "fields_repaired": fields_repaired,
                    "ids_added": ids_added,
                    "reconciliation_source": sources,
                    "page_ids": page_ids,
                    "before_sha256": original_sha,
                }
            )

    result.unresolved = unresolved[:_MAX_RECORDS]
    if not changed_paths:
        return result

    result.payload = working
    result.applied = True
    result.changed_paths = _ordered_unique(changed_paths)[:_MAX_RECORDS]
    result.actions = actions[:_MAX_RECORDS]
    result_sha = _canonical_sha256(working)
    for record in records:
        record["after_sha256"] = result_sha
    result.records = records[:_MAX_RECORDS]
    result.result_sha256 = result_sha
    return result


def unresolved_trace_reference_issues(
    payload: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Typed blocking issues for trace refs that cannot be proven (read-only)."""

    probe = reconcile_trace_references(payload)
    return [
        {
            "severity": "blocking",
            "code": str(item.get("code") or REFS_AMBIGUOUS),
            "message": str(item.get("message") or ""),
            "path": str(item.get("path") or ""),
            "related_ids": [str(item.get("requirement_id") or "")],
            "trace_index": item.get("trace_index"),
            "field": item.get("field"),
            "considered_source": item.get("considered_source"),
            "candidates": item.get("candidates") or [],
        }
        for item in probe.unresolved
    ]


__all__ = [
    "CAPABILITIES_UNRESOLVED",
    "EVIDENCE_UNRESOLVED",
    "REFS_AMBIGUOUS",
    "UNRESOLVED_TRACE_REFERENCE_CODES",
    "TraceReferenceReconcileResult",
    "reconcile_trace_references",
    "unresolved_trace_reference_issues",
]
