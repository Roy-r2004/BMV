"""Deterministic AppSpec reference-integrity reconciliation.

Repairs misplaced evidence IDs that models put into entity-reference fields
(notably ``actions[].entity_id``), materializing matching evidence from the
owning page/action contract and clearing the invalid entity reference.

Never invents domain entities or product behavior. Never calls a provider.
Unknown non-evidence references are left for fail-closed validation.
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.application.appspec.source import canonical_json


def _evidence_shaped(value: str, *, entity_ids: set[str], evidence_ids: set[str]) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text in entity_ids:
        return False
    if text in evidence_ids:
        return True
    return text.upper().startswith("EVIDENCE-")


def _evidence_kind_for_action(action: Mapping[str, Any], evidence_id: str) -> str:
    upper = evidence_id.upper()
    if "LIST" in upper or "ITEMS" in upper:
        return "list"
    if "FORM" in upper or "FIELD" in upper:
        return "form"
    if "CALENDAR" in upper or "AVAILABILITY" in upper:
        return "form"
    if "SUBMIT" in upper or "BUTTON" in upper or "NAV" in upper or "BROWSE" in upper:
        return "navigation"
    kind = str(action.get("kind") or "").strip().lower()
    if kind in {"fill", "select", "submit"}:
        return "form"
    if kind in {"navigate", "click"}:
        return "navigation"
    return "text"


def _ensure_page_lists_evidence(page: dict[str, Any], evidence_id: str) -> None:
    ids = [str(value) for value in (page.get("evidence_ids") or [])]
    if evidence_id not in ids:
        ids.append(evidence_id)
        page["evidence_ids"] = ids


def _materialize_evidence(
    *,
    payload: dict[str, Any],
    evidence_id: str,
    page_id: str,
    action: Mapping[str, Any],
) -> str:
    evidence_items = [
        item for item in (payload.get("evidence") or []) if isinstance(item, dict)
    ]
    existing = next(
        (item for item in evidence_items if str(item.get("id") or "") == evidence_id),
        None,
    )
    pages = {
        str(item.get("id")): item
        for item in (payload.get("pages") or [])
        if isinstance(item, dict) and item.get("id")
    }
    page = pages.get(page_id)
    capability_ids = [
        str(value)
        for value in (action.get("capability_ids") or [])
        if str(value).strip()
    ]
    if not capability_ids and page is not None:
        capability_ids = [
            str(value)
            for value in (page.get("capability_ids") or [])
            if str(value).strip()
        ]
    if not capability_ids:
        capability_ids = ["CAP-UNSPECIFIED"]

    name = str(action.get("name") or evidence_id.replace("EVIDENCE-", "").replace("-", " "))
    description = str(
        action.get("description")
        or f"Observable UI evidence for {name} on {page_id}."
    )
    kind = _evidence_kind_for_action(action, evidence_id)
    if existing is None:
        evidence_items.append(
            {
                "id": evidence_id,
                "page_id": page_id,
                "name": name[:120],
                "description": description[:2000],
                "kind": kind,
                "capability_ids": capability_ids[:1],
            }
        )
        payload["evidence"] = evidence_items
        source = "action_contract"
    else:
        # Preserve canonical ID; align page/caps when empty.
        if not existing.get("page_id") and page_id:
            existing["page_id"] = page_id
        if not existing.get("capability_ids"):
            existing["capability_ids"] = capability_ids[:1]
        payload["evidence"] = evidence_items
        source = "existing_evidence"
    if page is not None:
        _ensure_page_lists_evidence(page, evidence_id)
    return source


@dataclass
class ReferenceIntegrityResult:
    applied: list[str] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    integrity_hash: str = ""
    provider_called: bool = False


def reconcile_reference_integrity(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], ReferenceIntegrityResult]:
    """Reconcile evidence-shaped IDs found in entity-reference fields.

    Returns ``(repaired_payload, result)``. Provider calls are never used.
    """

    repaired = copy.deepcopy(dict(payload))
    result = ReferenceIntegrityResult(provider_called=False)

    entity_ids = {
        str(item.get("id"))
        for item in (repaired.get("entities") or [])
        if isinstance(item, dict) and item.get("id")
    }
    evidence_ids = {
        str(item.get("id"))
        for item in (repaired.get("evidence") or [])
        if isinstance(item, dict) and item.get("id")
    }

    # 1) actions[].entity_id — request 38 production failure class
    for index, action in enumerate(repaired.get("actions") or []):
        if not isinstance(action, dict):
            continue
        raw_entity = action.get("entity_id")
        if raw_entity is None or raw_entity == "":
            continue
        entity_id = str(raw_entity)
        path = ["actions", index, "entity_id"]
        if entity_id in entity_ids:
            continue
        if not _evidence_shaped(
            entity_id, entity_ids=entity_ids, evidence_ids=evidence_ids
        ):
            result.diagnostics.append(
                {
                    "missing_reference_id": entity_id,
                    "referencing_entity": str(action.get("id") or ""),
                    "referencing_field": "actions.entity_id",
                    "path": path,
                    "deterministic_reconstruction_source": None,
                    "repair_result": "fail_closed",
                }
            )
            continue
        page_id = str(action.get("page_id") or "")
        if not page_id:
            result.diagnostics.append(
                {
                    "missing_reference_id": entity_id,
                    "referencing_entity": str(action.get("id") or ""),
                    "referencing_field": "actions.entity_id",
                    "path": path,
                    "deterministic_reconstruction_source": None,
                    "repair_result": "fail_closed",
                }
            )
            continue
        source = _materialize_evidence(
            payload=repaired,
            evidence_id=entity_id,
            page_id=page_id,
            action=action,
        )
        evidence_ids.add(entity_id)
        action["entity_id"] = None
        action_id = str(action.get("id") or index)
        applied = f"reference_integrity:actions.entity_id:{action_id}:{entity_id}"
        result.applied.append(applied)
        result.diagnostics.append(
            {
                "missing_reference_id": entity_id,
                "referencing_entity": action_id,
                "referencing_field": "actions.entity_id",
                "path": path,
                "deterministic_reconstruction_source": source,
                "repair_result": "reconstructed",
            }
        )

    # 2) capabilities[].entity_ids — drop evidence-shaped members
    for index, capability in enumerate(repaired.get("capabilities") or []):
        if not isinstance(capability, dict):
            continue
        original = [str(value) for value in (capability.get("entity_ids") or [])]
        kept: list[str] = []
        for ref_index, entity_id in enumerate(original):
            if entity_id in entity_ids:
                kept.append(entity_id)
                continue
            if _evidence_shaped(
                entity_id, entity_ids=entity_ids, evidence_ids=evidence_ids
            ):
                result.applied.append(
                    "reference_integrity:capabilities.entity_ids:"
                    f"{capability.get('id')}:{entity_id}"
                )
                result.diagnostics.append(
                    {
                        "missing_reference_id": entity_id,
                        "referencing_entity": str(capability.get("id") or ""),
                        "referencing_field": "capabilities.entity_ids",
                        "path": ["capabilities", index, "entity_ids", ref_index],
                        "deterministic_reconstruction_source": "strip_misplaced_evidence_id",
                        "repair_result": "stripped",
                    }
                )
                continue
            kept.append(entity_id)
        capability["entity_ids"] = kept

    # 3) entities[].fields[].reference_entity_id — fail closed for evidence-shaped
    for entity_index, entity in enumerate(repaired.get("entities") or []):
        if not isinstance(entity, dict):
            continue
        for field_index, field_item in enumerate(entity.get("fields") or []):
            if not isinstance(field_item, dict):
                continue
            ref = field_item.get("reference_entity_id")
            if ref is None or ref == "":
                continue
            ref_id = str(ref)
            if ref_id in entity_ids:
                continue
            if _evidence_shaped(
                ref_id, entity_ids=entity_ids, evidence_ids=evidence_ids
            ):
                field_item["reference_entity_id"] = None
                result.applied.append(
                    "reference_integrity:entities.fields.reference_entity_id:"
                    f"{entity.get('id')}:{ref_id}"
                )
                result.diagnostics.append(
                    {
                        "missing_reference_id": ref_id,
                        "referencing_entity": str(entity.get("id") or ""),
                        "referencing_field": "entities.fields.reference_entity_id",
                        "path": [
                            "entities",
                            entity_index,
                            "fields",
                            field_index,
                            "reference_entity_id",
                        ],
                        "deterministic_reconstruction_source": "strip_misplaced_evidence_id",
                        "repair_result": "stripped",
                    }
                )

    # 4) transition effects[].entity_id — evidence-shaped cannot be reconstructed
    # as domain entities; leave for fail-closed validation (do not invent entities).
    for t_index, transition in enumerate(repaired.get("transitions") or []):
        if not isinstance(transition, dict):
            continue
        for e_index, effect in enumerate(transition.get("effects") or []):
            if not isinstance(effect, dict):
                continue
            ref = effect.get("entity_id")
            if ref is None or ref == "":
                continue
            ref_id = str(ref)
            if ref_id in entity_ids:
                continue
            result.diagnostics.append(
                {
                    "missing_reference_id": ref_id,
                    "referencing_entity": str(transition.get("id") or ""),
                    "referencing_field": "transitions.effects.entity_id",
                    "path": ["transitions", t_index, "effects", e_index, "entity_id"],
                    "deterministic_reconstruction_source": None,
                    "repair_result": "fail_closed",
                }
            )

    # 5) Re-link page evidence membership for any evidence objects that exist
    pages = {
        str(item.get("id")): item
        for item in (repaired.get("pages") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for item in repaired.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("id") or "")
        page_id = str(item.get("page_id") or "")
        page = pages.get(page_id)
        if evidence_id and page is not None:
            before = list(page.get("evidence_ids") or [])
            _ensure_page_lists_evidence(page, evidence_id)
            if list(page.get("evidence_ids") or []) != before:
                result.applied.append(
                    f"reference_integrity:pages.evidence_ids:{page_id}:{evidence_id}"
                )

    # 6) Drop dangling page evidence refs that cannot be reconstructed
    evidence_ids = {
        str(item.get("id"))
        for item in (repaired.get("evidence") or [])
        if isinstance(item, dict) and item.get("id")
    }
    actions_by_page: dict[str, list[dict[str, Any]]] = {}
    for action in repaired.get("actions") or []:
        if isinstance(action, dict):
            actions_by_page.setdefault(str(action.get("page_id") or ""), []).append(
                action
            )

    for page in repaired.get("pages") or []:
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("id") or "")
        kept_refs: list[str] = []
        for evidence_id in [str(v) for v in (page.get("evidence_ids") or [])]:
            if evidence_id in evidence_ids:
                kept_refs.append(evidence_id)
                continue
            # Try reconstruct from an action on this page whose name/id implies it.
            donor = next(
                (
                    action
                    for action in actions_by_page.get(page_id, [])
                    if evidence_id.upper()
                    in (
                        str(action.get("name") or "")
                        + " "
                        + str(action.get("description") or "")
                        + " "
                        + str(action.get("id") or "")
                    ).upper()
                    or evidence_id.upper().startswith("EVIDENCE-")
                ),
                None,
            )
            # Prefer reconstructing any evidence-shaped dangling page ref from the
            # first action on the page when the ID itself is evidence-shaped.
            if donor is None and evidence_id.upper().startswith("EVIDENCE-"):
                page_actions = actions_by_page.get(page_id) or []
                donor = page_actions[0] if page_actions else None
            if donor is not None and evidence_id.upper().startswith("EVIDENCE-"):
                source = _materialize_evidence(
                    payload=repaired,
                    evidence_id=evidence_id,
                    page_id=page_id,
                    action=donor,
                )
                evidence_ids.add(evidence_id)
                kept_refs.append(evidence_id)
                result.applied.append(
                    f"reference_integrity:pages.evidence_ids.reconstruct:{page_id}:{evidence_id}"
                )
                result.diagnostics.append(
                    {
                        "missing_reference_id": evidence_id,
                        "referencing_entity": page_id,
                        "referencing_field": "pages.evidence_ids",
                        "path": ["pages", page_id, "evidence_ids"],
                        "deterministic_reconstruction_source": source,
                        "repair_result": "reconstructed",
                    }
                )
            else:
                result.diagnostics.append(
                    {
                        "missing_reference_id": evidence_id,
                        "referencing_entity": page_id,
                        "referencing_field": "pages.evidence_ids",
                        "path": ["pages", page_id, "evidence_ids"],
                        "deterministic_reconstruction_source": None,
                        "repair_result": "stripped",
                    }
                )
                result.applied.append(
                    f"reference_integrity:pages.evidence_ids.strip:{page_id}:{evidence_id}"
                )
        page["evidence_ids"] = kept_refs

    digest_payload = {
        "applied": list(result.applied),
        "diagnostics": list(result.diagnostics),
        "evidence_ids": sorted(
            str(item.get("id"))
            for item in (repaired.get("evidence") or [])
            if isinstance(item, dict) and item.get("id")
        ),
        "action_entity_ids": [
            str(action.get("entity_id") or "")
            for action in (repaired.get("actions") or [])
            if isinstance(action, dict)
        ],
    }
    result.integrity_hash = hashlib.sha256(
        canonical_json(digest_payload).encode("utf-8")
    ).hexdigest()
    return repaired, result


__all__ = [
    "ReferenceIntegrityResult",
    "reconcile_reference_integrity",
]
