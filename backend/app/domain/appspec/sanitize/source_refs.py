"""AppSpec sanitize — source reference repairs."""
from __future__ import annotations

import re
from typing import Any, Mapping

from app.domain.appspec.sanitize.kinds import _humanize_identifier

_SOURCE_REF_RE = re.compile(
    r"^(?:customer_input|reference_evidence)(?:\.[A-Za-z0-9_]+)+$"
)

_DERIVED_CONTEXT_PREFIX = "derived_context."

_FALLBACK_SOURCE_PATHS: tuple[str, ...] = (
    "customer_input.desired_outcome",
    "customer_input.main_problem",
    "customer_input.business_description",
    "customer_input.what_you_like",
    "customer_input.target_customers",
    "customer_input.business_name",
    "customer_input.industry",
    "reference_evidence.screenshot_analysis",
)

def _is_valid_source_ref(ref: str) -> bool:
    return bool(_SOURCE_REF_RE.match(str(ref).strip()))

def _ref_resolves(ref: str, snapshot: Mapping[str, Any]) -> bool:
    current: Any = snapshot
    for segment in ref.split("."):
        if not isinstance(current, dict) or segment not in current:
            return False
        current = current[segment]
    return current not in (None, "", [], {})

def _first_resolvable_source_ref(snapshot: Mapping[str, Any]) -> str | None:
    for path in _FALLBACK_SOURCE_PATHS:
        if _ref_resolves(path, snapshot):
            return path
    for root in ("customer_input", "reference_evidence"):
        section = snapshot.get(root)
        if not isinstance(section, dict):
            continue
        for key, value in section.items():
            if value in (None, "", [], {}):
                continue
            path = f"{root}.{key}"
            if _is_valid_source_ref(path):
                return path
    return None

def _existing_deferred_requirement_ids(payload: Mapping[str, Any]) -> set[str]:
    folded: set[str] = set()
    for item in payload.get("deferred_scope") or []:
        if not isinstance(item, dict):
            continue
        for req_id in item.get("requirement_ids") or []:
            folded.add(str(req_id).casefold())
    return folded

def _sanitize_requirement_source_refs(
    requirement: dict[str, Any],
    *,
    source_snapshot: Mapping[str, Any],
    deferred_scope: list[dict[str, Any]],
    existing_deferred_requirement_ids: set[str],
) -> None:
    raw_refs = list(requirement.get("source_refs") or [])
    valid_refs: list[str] = []
    had_derived_only = False
    for ref in raw_refs:
        text = str(ref).strip()
        if not text:
            continue
        if text.startswith(_DERIVED_CONTEXT_PREFIX) or not _is_valid_source_ref(text):
            had_derived_only = True
            continue
        if text not in valid_refs:
            valid_refs.append(text)

    if not valid_refs:
        fallback = _first_resolvable_source_ref(source_snapshot)
        if fallback is None:
            requirement["source_refs"] = ["customer_input.desired_outcome"]
        else:
            requirement["source_refs"] = [fallback]
        if had_derived_only or any(
            str(ref).strip().startswith(_DERIVED_CONTEXT_PREFIX) for ref in raw_refs
        ):
            if str(requirement.get("priority", "must")) == "must":
                requirement["priority"] = "should"
            requirement_id = str(requirement.get("id") or "REQ-UNKNOWN")
            if requirement_id.casefold() not in existing_deferred_requirement_ids:
                deferred_scope.append(
                    {
                        "id": f"DEFER-{requirement_id}",
                        "name": str(requirement.get("title") or requirement_id),
                        "description": str(
                            requirement.get("description")
                            or "Deferred because it was inferred from non-authoritative analysis."
                        ),
                        "reason": (
                            "This outcome was suggested by derived blueprint analysis rather than "
                            "direct customer input. It is deferred until explicitly confirmed."
                        ),
                        "requirement_ids": [requirement_id],
                        "target_release": "Later",
                    }
                )
        return

    requirement["source_refs"] = valid_refs

def _remove_traceability_for_requirements(
    traceability: list[dict[str, Any]],
    requirement_ids: set[str],
) -> list[dict[str, Any]]:
    folded = {value.casefold() for value in requirement_ids}
    return [
        link
        for link in traceability
        if str(link.get("requirement_id", "")).casefold() not in folded
    ]

def _infer_deferred_requirement_id(item: dict[str, Any]) -> str | None:
    for req_id in item.get("requirement_ids") or []:
        text = str(req_id).strip()
        if text:
            return text
    item_id = str(item.get("id") or "")
    for prefix in ("DEFERRED-", "DEFER-"):
        if item_id.startswith(prefix):
            suffix = item_id[len(prefix) :]
            return suffix if suffix.startswith("REQ-") else f"REQ-{suffix}"
    return None

def _merge_deferred_scope(
    existing: list[dict[str, Any]],
    additions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not additions:
        return existing
    merged = list(existing)
    seen_requirements = {
        str(req_id).casefold()
        for item in merged
        for req_id in (item.get("requirement_ids") or [])
    }
    seen_ids = {
        str(item.get("id", "")).casefold()
        for item in merged
        if isinstance(item, dict) and item.get("id")
    }
    for item in additions:
        item_id = str(item.get("id", ""))
        if item_id.casefold() in seen_ids:
            continue
        req_ids = [
            str(req_id)
            for req_id in (item.get("requirement_ids") or [])
            if str(req_id).casefold() not in seen_requirements
        ]
        if not req_ids:
            continue
        payload = dict(item)
        payload["requirement_ids"] = req_ids
        merged.append(payload)
        seen_ids.add(item_id.casefold())
        seen_requirements.update(value.casefold() for value in req_ids)
    return merged
