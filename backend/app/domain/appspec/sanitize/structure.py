"""AppSpec sanitize — routes, entities, capabilities, pages."""
from __future__ import annotations

import re
from typing import Any

from app.domain.appspec.sanitize.kinds import _humanize_identifier, _normalize_kind
from app.domain.appspec.sanitize.source_refs import (
    _existing_deferred_requirement_ids,
    _infer_deferred_requirement_id,
)

_ROUTE_PARAM_RE = re.compile(r"/:[A-Za-z0-9_]+")

_ROUTE_VALID_RE = re.compile(
    r"^/(?:[a-z0-9][a-z0-9_-]*(?:/[a-z0-9][a-z0-9_-]*)*)?$"
)

def _sanitize_route(route: Any) -> str:
    text = str(route or "/").strip() or "/"
    text = _ROUTE_PARAM_RE.sub("", text)
    text = re.sub(r"/{2,}", "/", text)
    if not text.startswith("/"):
        text = "/" + text
    if len(text) > 1:
        text = text.rstrip("/")
    text = text.casefold()
    if not _ROUTE_VALID_RE.match(text):
        # Fall back to a stable slug built from remaining alphanumeric segments.
        parts = [part for part in re.split(r"[^a-z0-9]+", text) if part]
        text = "/" + "/".join(parts) if parts else "/"
    return text if _ROUTE_VALID_RE.match(text) else "/"

def _sanitize_page_routes(payload: dict[str, Any]) -> None:
    seen: set[str] = set()
    for page in payload.get("pages") or []:
        if not isinstance(page, dict):
            continue
        route = _sanitize_route(page.get("route"))
        if route in seen:
            base = route.rstrip("/") or "/page"
            suffix = 2
            candidate = f"{base}/v{suffix}"
            while candidate in seen or not _ROUTE_VALID_RE.match(candidate):
                suffix += 1
                candidate = f"{base}/v{suffix}"
            route = candidate
        seen.add(route)
        page["route"] = route

def _sanitize_capabilities(payload: dict[str, Any]) -> None:
    requirements = {
        str(item.get("id")): item
        for item in (payload.get("requirements") or [])
        if isinstance(item, dict) and item.get("id")
    }
    if not requirements:
        return

    deferred_ids = _existing_deferred_requirement_ids(payload)
    trace_by_requirement: dict[str, dict[str, Any]] = {}
    for link in payload.get("traceability") or []:
        if isinstance(link, dict) and link.get("requirement_id"):
            trace_by_requirement[str(link["requirement_id"])] = link

    for capability in payload.get("capabilities") or []:
        if not isinstance(capability, dict):
            continue
        capability_id = str(capability.get("id") or "")
        valid_refs = [
            str(value)
            for value in (capability.get("requirement_ids") or [])
            if str(value) in requirements
        ]
        if valid_refs:
            capability["requirement_ids"] = valid_refs
            continue

        inferred: list[str] = []
        for page in payload.get("pages") or []:
            if not isinstance(page, dict):
                continue
            page_caps = {str(value) for value in (page.get("capability_ids") or [])}
            if capability_id not in page_caps:
                continue
            page_id = str(page.get("id") or "")
            for requirement_id, link in trace_by_requirement.items():
                page_ids = {str(value) for value in (link.get("page_ids") or [])}
                if page_id in page_ids and requirement_id not in inferred:
                    inferred.append(requirement_id)

        if not inferred:
            for requirement_id, requirement in requirements.items():
                if requirement_id.casefold() in deferred_ids:
                    continue
                if str(requirement.get("priority")) == "must":
                    inferred = [requirement_id]
                    break

        if not inferred:
            inferred = [next(iter(requirements))]

        capability["requirement_ids"] = inferred[:1]

def _sanitize_entities(payload: dict[str, Any]) -> None:
    for entity in payload.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        for field in entity.get("fields") or []:
            if not isinstance(field, dict):
                continue
            if not str(field.get("name") or "").strip():
                field["name"] = _humanize_identifier(str(field.get("id") or "Field"))

def _sanitize_deferred_scope(payload: dict[str, Any]) -> None:
    requirements = {
        str(item.get("id")): item
        for item in (payload.get("requirements") or [])
        if isinstance(item, dict) and item.get("id")
    }
    sanitized: list[dict[str, Any]] = []
    assigned_requirements: set[str] = set()
    for item in payload.get("deferred_scope") or []:
        if not isinstance(item, dict):
            continue
        req_ids = [str(value) for value in (item.get("requirement_ids") or []) if str(value).strip()]
        if not req_ids:
            inferred = _infer_deferred_requirement_id(item)
            if inferred and inferred in requirements:
                req_ids = [inferred]
        filtered: list[str] = []
        for req_id in req_ids:
            if req_id not in requirements:
                continue
            requirement = requirements[req_id]
            if str(requirement.get("priority")) == "must":
                continue
            folded = req_id.casefold()
            if folded in assigned_requirements:
                continue
            filtered.append(req_id)
            assigned_requirements.add(folded)
        if not filtered:
            continue
        payload_item = dict(item)
        payload_item["requirement_ids"] = filtered
        sanitized.append(payload_item)
    payload["deferred_scope"] = sanitized

def _sanitize_page_action_ids(payload: dict[str, Any]) -> None:
    actions_by_page: dict[str, list[str]] = {}
    for action in payload.get("actions") or []:
        if not isinstance(action, dict):
            continue
        page_id = str(action.get("page_id") or "")
        action_id = str(action.get("id") or "")
        if page_id and action_id:
            actions_by_page.setdefault(page_id, []).append(action_id)

    for page in payload.get("pages") or []:
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("id") or "")
        merged: list[str] = []
        seen: set[str] = set()
        for action_id in list(page.get("action_ids") or []) + actions_by_page.get(page_id, []):
            text = str(action_id)
            if text and text not in seen:
                merged.append(text)
                seen.add(text)
        page["action_ids"] = merged

def _sanitize_blocking_open_questions(payload: dict[str, Any]) -> None:
    for question in payload.get("open_questions") or []:
        if isinstance(question, dict):
            question["blocking"] = False

def _sanitize_cross_page_navigation(payload: dict[str, Any]) -> None:
    states = {
        str(item.get("id")): item
        for item in (payload.get("states") or [])
        if isinstance(item, dict) and item.get("id")
    }
    actions = {
        str(item.get("id")): item
        for item in (payload.get("actions") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for transition in payload.get("transitions") or []:
        if not isinstance(transition, dict):
            continue
        action = actions.get(str(transition.get("action_id") or ""))
        source = states.get(str(transition.get("from_state_id") or ""))
        target = states.get(str(transition.get("to_state_id") or ""))
        if action is None or source is None or target is None:
            continue
        if str(source.get("page_id")) != str(target.get("page_id")):
            action["kind"] = "navigate"
