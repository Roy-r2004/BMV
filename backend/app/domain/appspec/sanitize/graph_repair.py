"""Bounded deterministic AppSpec graph repairs for membership consistency.

Canonical ownership: ``action.page_id`` / ``state.page_id`` / ``evidence.page_id``
are authoritative. Page membership lists may only contain objects they own.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping


REPAIRABLE_ISSUE_CODES = frozenset(
    {
        "page_membership_mismatch",
        "action_missing_from_page",
        "state_missing_from_page",
        "evidence_missing_from_page",
        "state_evidence_page_mismatch",
    }
)

NON_REPAIRABLE_WITHOUT_INVENTION = frozenset(
    {
        "missing_canonical_owner",
        "ambiguous_action_ownership",
        "duplicate_object_definition",
        "conflicting_duplicate_object",
    }
)


@dataclass
class GraphRepairResult:
    """Outcome of one deterministic graph-repair attempt."""

    payload: dict[str, Any]
    changed_paths: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    refused_reasons: list[str] = field(default_factory=list)
    applied: bool = False
    original_sha256: str = ""
    repaired_sha256: str = ""
    repairable_issue_codes: list[str] = field(default_factory=list)

    @property
    def result_label(self) -> str:
        if self.refused_reasons and not self.applied:
            return "rejected"
        if self.applied:
            return "repaired"
        return "unchanged"


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _issue_codes(validation_payload: Mapping[str, Any] | None) -> set[str]:
    if not validation_payload:
        return set()
    codes: set[str] = set()
    for issue in validation_payload.get("issues") or []:
        if isinstance(issue, Mapping):
            code = str(issue.get("code") or "")
            if code:
                codes.add(code)
    return codes


def validation_has_repairable_graph_issues(
    validation_payload: Mapping[str, Any] | None,
) -> bool:
    return bool(_issue_codes(validation_payload) & REPAIRABLE_ISSUE_CODES)


def _index_by_id(
    items: list[Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    indexed: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        if item_id in indexed:
            duplicates.append(item_id)
            continue
        indexed[item_id] = item
    return indexed, duplicates


def _dedupe_preserve(values: list[Any]) -> tuple[list[str], bool]:
    out: list[str] = []
    seen: set[str] = set()
    changed = False
    for value in values:
        text = str(value or "")
        if not text:
            changed = True
            continue
        if text in seen:
            changed = True
            continue
        seen.add(text)
        out.append(text)
    return out, changed


def _collect_ownership_refusals(
    *,
    kind: str,
    objects: dict[str, dict[str, Any]],
    pages_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    refusals: list[str] = []
    for object_id, obj in objects.items():
        owner = str(obj.get("page_id") or "").strip()
        if not owner:
            refusals.append(f"ambiguous_{kind}_ownership:{object_id}")
            continue
        if owner not in pages_by_id:
            refusals.append(f"missing_canonical_owner:{object_id}:{owner}")
    return refusals


def _align_page_membership(
    *,
    pages: list[dict[str, Any]],
    field_name: str,
    objects_by_id: dict[str, dict[str, Any]],
    kind: str,
    changed_paths: list[str],
    actions_log: list[str],
) -> None:
    for page_index, page in enumerate(pages):
        page_id = str(page.get("id") or "")
        raw_ids = list(page.get(field_name) or [])
        deduped, deduped_changed = _dedupe_preserve(raw_ids)
        kept: list[str] = []
        field_changed = deduped_changed
        for object_id in deduped:
            obj = objects_by_id.get(object_id)
            if obj is None:
                actions_log.append(f"drop_stale_{kind}_ref:{page_id}:{object_id}")
                field_changed = True
                continue
            owner = str(obj.get("page_id") or "")
            if owner != page_id:
                actions_log.append(
                    f"remove_{kind}_from_non_owner:{page_id}:{object_id}->{owner}"
                )
                field_changed = True
                continue
            kept.append(object_id)
        if field_changed:
            changed_paths.append(f"pages.{page_index}.{field_name}")
            if deduped_changed:
                actions_log.append(f"dedupe_{kind}_ids:{page_id}")
        page[field_name] = kept

    for object_id, obj in objects_by_id.items():
        owner = str(obj.get("page_id") or "")
        owner_page = next(
            (page for page in pages if str(page.get("id") or "") == owner),
            None,
        )
        if owner_page is None:
            continue
        owner_index = pages.index(owner_page)
        membership = list(owner_page.get(field_name) or [])
        if object_id not in membership:
            membership.append(object_id)
            owner_page[field_name] = membership
            changed_paths.append(f"pages.{owner_index}.{field_name}")
            actions_log.append(f"add_{kind}_to_owner:{owner}:{object_id}")


def repair_app_spec_graph(
    payload: Mapping[str, Any],
    validation_payload: Mapping[str, Any] | None = None,
) -> GraphRepairResult:
    """Apply one bounded membership/graph repair pass.

    Returns a deep-copied payload. Does not invent pages, actions, or product
    meaning. Refuses when canonical owners are missing or ownership is ambiguous.
    """

    original = copy.deepcopy(dict(payload))
    original_sha = _canonical_sha256(original)
    codes = sorted(_issue_codes(validation_payload) & REPAIRABLE_ISSUE_CODES)
    result = GraphRepairResult(
        payload=original,
        original_sha256=original_sha,
        repaired_sha256=original_sha,
        repairable_issue_codes=codes,
    )

    working = copy.deepcopy(original)
    pages = [item for item in (working.get("pages") or []) if isinstance(item, dict)]
    actions = [item for item in (working.get("actions") or []) if isinstance(item, dict)]
    states = [item for item in (working.get("states") or []) if isinstance(item, dict)]
    evidence = [
        item for item in (working.get("evidence") or []) if isinstance(item, dict)
    ]

    pages_by_id, page_dupes = _index_by_id(pages)
    actions_by_id, action_dupes = _index_by_id(actions)
    states_by_id, state_dupes = _index_by_id(states)
    evidence_by_id, evidence_dupes = _index_by_id(evidence)

    for collection, dupes in (
        ("pages", page_dupes),
        ("actions", action_dupes),
        ("states", state_dupes),
        ("evidence", evidence_dupes),
    ):
        for item_id in dupes:
            result.refused_reasons.append(
                f"duplicate_object_definition:{collection}:{item_id}"
            )
    if result.refused_reasons:
        return result

    result.refused_reasons.extend(
        _collect_ownership_refusals(
            kind="action",
            objects=actions_by_id,
            pages_by_id=pages_by_id,
        )
    )
    result.refused_reasons.extend(
        _collect_ownership_refusals(
            kind="state",
            objects=states_by_id,
            pages_by_id=pages_by_id,
        )
    )
    result.refused_reasons.extend(
        _collect_ownership_refusals(
            kind="evidence",
            objects=evidence_by_id,
            pages_by_id=pages_by_id,
        )
    )
    if result.refused_reasons:
        return result

    changed_paths: list[str] = []
    actions_log: list[str] = []

    _align_page_membership(
        pages=pages,
        field_name="action_ids",
        objects_by_id=actions_by_id,
        kind="action",
        changed_paths=changed_paths,
        actions_log=actions_log,
    )
    _align_page_membership(
        pages=pages,
        field_name="state_ids",
        objects_by_id=states_by_id,
        kind="state",
        changed_paths=changed_paths,
        actions_log=actions_log,
    )
    _align_page_membership(
        pages=pages,
        field_name="evidence_ids",
        objects_by_id=evidence_by_id,
        kind="evidence",
        changed_paths=changed_paths,
        actions_log=actions_log,
    )

    for state_index, state in enumerate(states):
        state_id = str(state.get("id") or "")
        page_id = str(state.get("page_id") or "")
        raw_ids = list(state.get("evidence_ids") or [])
        deduped, deduped_changed = _dedupe_preserve(raw_ids)
        kept: list[str] = []
        field_changed = deduped_changed
        for evidence_id in deduped:
            item = evidence_by_id.get(evidence_id)
            if item is None:
                actions_log.append(
                    f"drop_stale_state_evidence:{state_id}:{evidence_id}"
                )
                field_changed = True
                continue
            if str(item.get("page_id") or "") != page_id:
                actions_log.append(
                    f"remove_state_evidence_page_mismatch:{state_id}:{evidence_id}"
                )
                field_changed = True
                continue
            kept.append(evidence_id)
        if field_changed:
            changed_paths.append(f"states.{state_index}.evidence_ids")
            if deduped_changed:
                actions_log.append(f"dedupe_state_evidence:{state_id}")
        state["evidence_ids"] = kept

    unique_paths = sorted(dict.fromkeys(changed_paths))
    unique_actions = list(dict.fromkeys(actions_log))
    repaired_sha = _canonical_sha256(working)
    result.payload = working
    result.changed_paths = unique_paths
    result.actions = unique_actions
    result.repaired_sha256 = repaired_sha
    result.applied = bool(unique_actions) and repaired_sha != original_sha
    return result


__all__ = [
    "GraphRepairResult",
    "NON_REPAIRABLE_WITHOUT_INVENTION",
    "REPAIRABLE_ISSUE_CODES",
    "repair_app_spec_graph",
    "validation_has_repairable_graph_issues",
]
