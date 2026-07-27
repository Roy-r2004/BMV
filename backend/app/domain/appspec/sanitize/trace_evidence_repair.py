"""Deterministic repair for safe ``trace_evidence_mismatch`` cases only."""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class TraceEvidenceRepairResult:
    """Outcome of one bounded deterministic trace-evidence repair."""

    payload: dict[str, Any]
    applied: bool = False
    changed_paths: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    refused_reasons: list[str] = field(default_factory=list)
    original_sha256: str = ""
    repaired_sha256: str = ""
    repairable_issue_codes: list[str] = field(default_factory=list)
    reconciliations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def result_label(self) -> str:
        if self.refused_reasons and not self.applied:
            return "rejected"
        if self.applied:
            return "repaired"
        return "unchanged"


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _issue_list(validation_payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not validation_payload:
        return []
    out: list[dict[str, Any]] = []
    for issue in validation_payload.get("issues") or []:
        if isinstance(issue, Mapping):
            out.append(dict(issue))
    return out


def _index_by_id(items: list[Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        if item_id and item_id not in indexed:
            indexed[item_id] = item
    return indexed


def validation_has_safe_trace_evidence_repair(
    payload: Mapping[str, Any] | None,
    validation_payload: Mapping[str, Any] | None,
) -> bool:
    """True only when every trace_evidence_mismatch has an unambiguous safe fix."""

    probe = repair_trace_evidence_mismatch(payload or {}, validation_payload)
    return probe.applied and not probe.refused_reasons


def _canonical_on_trace(
    *,
    evidence_by_id: dict[str, dict[str, Any]],
    page_ids: set[str],
    capability_ids: set[str],
    kind: str | None,
    exclude_id: str,
) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for item_id, item in evidence_by_id.items():
        if item_id == exclude_id:
            continue
        if str(item.get("page_id") or "") not in page_ids:
            continue
        item_caps = {str(c) for c in (item.get("capability_ids") or [])}
        if not item_caps.intersection(capability_ids):
            continue
        if kind and str(item.get("kind") or "") != kind:
            continue
        matches.append(item)
    if len(matches) != 1:
        return None
    return matches[0]


def _replace_id_in_list(values: list[Any], old: str, new: str) -> tuple[list[str], bool]:
    out: list[str] = []
    changed = False
    seen: set[str] = set()
    for value in values:
        text = str(value or "")
        if text == old:
            text = new
            changed = True
        if not text or text in seen:
            if text in seen:
                changed = True
            continue
        seen.add(text)
        out.append(text)
    return out, changed


def repair_trace_evidence_mismatch(
    payload: Mapping[str, Any],
    validation_payload: Mapping[str, Any] | None = None,
) -> TraceEvidenceRepairResult:
    """Repair ``trace_evidence_mismatch`` only when the fix is unambiguous.

    Safe repairs:
    - attach exactly one uniquely proven capability when the owner page is already
      on the failing trace and the page↔trace pair proves that capability
    - restore a missing page→evidence reverse reference in the same pass
    - add the owner page onto a trace when ownership/capabilities are already clear
    - replace a stale/incorrect traced evidence ID with one unambiguous canonical
      evidence object already owned by the traced page + capability set
    - drop duplicate stale evidence IDs from the same trace after replacement

    Unsafe (refuse):
    - missing evidence object
    - multiple candidate capabilities or pages
    - ambiguous ownership / meaning
    - inference from evidence-id wording alone
    """

    original = copy.deepcopy(dict(payload))
    original_sha = _canonical_sha256(original)
    issues = [
        issue
        for issue in _issue_list(validation_payload)
        if str(issue.get("code") or "") == "trace_evidence_mismatch"
    ]
    result = TraceEvidenceRepairResult(
        payload=original,
        original_sha256=original_sha,
        repaired_sha256=original_sha,
        repairable_issue_codes=["trace_evidence_mismatch"] if issues else [],
    )
    if not issues:
        return result

    working = copy.deepcopy(original)
    evidence_by_id = _index_by_id(
        [item for item in (working.get("evidence") or []) if isinstance(item, dict)]
    )
    pages_by_id = _index_by_id(
        [item for item in (working.get("pages") or []) if isinstance(item, dict)]
    )
    capabilities_by_id = _index_by_id(
        [
            item
            for item in (working.get("capabilities") or [])
            if isinstance(item, dict)
        ]
    )
    traces = [
        item for item in (working.get("traceability") or []) if isinstance(item, dict)
    ]
    acceptance_tests = [
        item for item in (working.get("acceptance_tests") or []) if isinstance(item, dict)
    ]

    changed_paths: list[str] = []
    actions: list[str] = []
    refused: list[str] = []
    reconciliations: list[dict[str, Any]] = []

    for issue in issues:
        related = [str(item) for item in (issue.get("related_ids") or [])]
        requirement_id = related[0] if related else ""
        evidence_id = related[1] if len(related) > 1 else ""
        if not evidence_id:
            # Fall back to message parse: Evidence 'ID' is not attached...
            message = str(issue.get("message") or "")
            marker = "Evidence '"
            if marker in message:
                evidence_id = message.split(marker, 1)[1].split("'", 1)[0]
        if not evidence_id:
            refused.append("ambiguous_trace_evidence:missing_evidence_id")
            continue

        bad = evidence_by_id.get(evidence_id)
        link = next(
            (
                item
                for item in traces
                if str(item.get("requirement_id") or "") == requirement_id
            ),
            None,
        )
        if link is None and requirement_id:
            refused.append(f"missing_trace_link:{requirement_id}")
            continue
        if link is None:
            # Try to locate the link that references this evidence.
            link = next(
                (
                    item
                    for item in traces
                    if evidence_id in [str(x) for x in (item.get("evidence_ids") or [])]
                ),
                None,
            )
        if link is None:
            refused.append(f"missing_trace_link_for_evidence:{evidence_id}")
            continue

        page_ids = {str(x) for x in (link.get("page_ids") or [])}
        capability_ids = {str(x) for x in (link.get("capability_ids") or [])}

        # Case A: evidence object exists but is not attached to the failing
        # trace. Prefer reciprocal link closure over ID rewriting.
        if bad is not None:
            attached = (
                str(bad.get("page_id") or "") in page_ids
                and bool(
                    {str(c) for c in (bad.get("capability_ids") or [])}.intersection(
                        capability_ids
                    )
                )
            )
            if attached:
                continue
            owner_page = str(bad.get("page_id") or "")
            bad_caps = {str(c) for c in (bad.get("capability_ids") or [])}

            # Case A3: owner page is already on the failing trace, and exactly
            # one capability is uniquely proven by the existing page↔trace pair.
            if owner_page and owner_page in page_ids and owner_page in pages_by_id:
                page = pages_by_id[owner_page]
                page_caps = {str(c) for c in (page.get("capability_ids") or [])}
                candidates = sorted(
                    capability_ids.intersection(page_caps) - bad_caps
                )
                if len(candidates) != 1:
                    refused.append(
                        "trace_evidence_reconciliation_ambiguous:"
                        f"{evidence_id}"
                    )
                    continue
                capability_id = candidates[0]
                if capability_id not in capabilities_by_id:
                    refused.append(
                        "trace_evidence_reconciliation_ambiguous:"
                        f"{evidence_id}:missing_capability"
                    )
                    continue
                links_added: list[str] = []
                evidence_caps = list(bad.get("capability_ids") or [])
                if capability_id not in [str(c) for c in evidence_caps]:
                    evidence_caps.append(capability_id)
                    bad["capability_ids"] = evidence_caps
                    links_added.append("evidence_capability")
                    actions.append(
                        "add_capability_to_evidence:"
                        f"{evidence_id}:{capability_id}"
                    )
                    changed_paths.append(
                        f"evidence.{evidence_id}.capability_ids"
                    )
                page_evidence = list(page.get("evidence_ids") or [])
                if evidence_id not in [str(x) for x in page_evidence]:
                    page_evidence.append(evidence_id)
                    page["evidence_ids"] = page_evidence
                    links_added.append("page_evidence")
                    actions.append(
                        f"add_evidence_to_page:{owner_page}:{evidence_id}"
                    )
                    changed_paths.append(
                        f"pages.{owner_page}.evidence_ids"
                    )
                if not links_added:
                    continue
                reconciliations.append(
                    {
                        "evidence_id": evidence_id,
                        "page_id": owner_page,
                        "capability_id": capability_id,
                        "requirement_id": str(link.get("requirement_id") or ""),
                        "links_added": links_added,
                        "reason": "unique_trace_page_capability_attachment",
                        "before_sha256": original_sha,
                    }
                )
                continue

            # Case A2: evidence is canonical and only the trace page list is
            # missing its owner page — add page when ownership/caps are clear.
            if (
                owner_page
                and owner_page in pages_by_id
                and owner_page not in page_ids
                and bad_caps.intersection(capability_ids)
            ):
                page = pages_by_id[owner_page]
                page_caps = {str(c) for c in (page.get("capability_ids") or [])}
                if not page_caps.intersection(capability_ids):
                    refused.append(
                        f"ambiguous_trace_evidence:page_caps:{evidence_id}"
                    )
                    continue
                link_page_ids = list(link.get("page_ids") or [])
                link_page_ids.append(owner_page)
                link["page_ids"] = link_page_ids
                page_evidence = list(page.get("evidence_ids") or [])
                if evidence_id not in page_evidence:
                    page_evidence.append(evidence_id)
                    page["evidence_ids"] = page_evidence
                    actions.append(
                        f"add_evidence_to_page:{owner_page}:{evidence_id}"
                    )
                    changed_paths.append(f"pages.{owner_page}.evidence_ids")
                actions.append(
                    f"add_page_to_trace:{link.get('requirement_id')}:{owner_page}"
                )
                changed_paths.append(
                    f"traceability.{link.get('requirement_id')}.page_ids"
                )
                continue

            # Case A: swap to unambiguous canonical evidence already attached to
            # the traced pages/capabilities (stale ID rewrite).
            canonical = _canonical_on_trace(
                evidence_by_id=evidence_by_id,
                page_ids=page_ids,
                capability_ids=capability_ids,
                kind=str(bad.get("kind") or "") or None,
                exclude_id=evidence_id,
            )
            if canonical is None:
                refused.append(
                    "trace_evidence_reconciliation_ambiguous:"
                    f"{evidence_id}"
                )
                continue
            new_id = str(canonical.get("id") or "")
            if not new_id:
                refused.append(
                    "trace_evidence_reconciliation_ambiguous:"
                    f"{evidence_id}"
                )
                continue
            new_ids, changed = _replace_id_in_list(
                list(link.get("evidence_ids") or []), evidence_id, new_id
            )
            if changed:
                link["evidence_ids"] = new_ids
                actions.append(
                    f"replace_trace_evidence:{link.get('requirement_id')}:"
                    f"{evidence_id}->{new_id}"
                )
                changed_paths.append(
                    f"traceability.{link.get('requirement_id')}.evidence_ids"
                )
            for test in acceptance_tests:
                assertions = list(test.get("assertions") or [])
                assertion_changed = False
                for assertion in assertions:
                    if not isinstance(assertion, dict):
                        continue
                    if str(assertion.get("evidence_id") or "") == evidence_id:
                        assertion["evidence_id"] = new_id
                        assertion_changed = True
                if assertion_changed:
                    test["assertions"] = assertions
                    actions.append(
                        f"replace_assertion_evidence:{test.get('id')}:"
                        f"{evidence_id}->{new_id}"
                    )
                    changed_paths.append(
                        f"acceptance_tests.{test.get('id')}.assertions"
                    )
            continue

        # Case B: evidence id missing entirely — refuse (no invention).
        refused.append(f"missing_evidence_object:{evidence_id}")

    if refused and not actions:
        result.refused_reasons = refused[:40]
        return result

    if refused:
        # Mixed outcomes: refuse entirely rather than partially invent meaning.
        result.refused_reasons = refused[:40]
        result.actions = actions[:40]
        return result

    if not actions:
        result.refused_reasons = ["no_safe_trace_evidence_repair"]
        return result

    result.payload = working
    result.applied = True
    result.changed_paths = changed_paths[:80]
    result.actions = actions[:80]
    repaired_sha = _canonical_sha256(working)
    for item in reconciliations:
        item["after_sha256"] = repaired_sha
    result.reconciliations = reconciliations[:80]
    result.repaired_sha256 = repaired_sha
    return result


__all__ = [
    "TraceEvidenceRepairResult",
    "repair_trace_evidence_mismatch",
    "validation_has_safe_trace_evidence_repair",
]
