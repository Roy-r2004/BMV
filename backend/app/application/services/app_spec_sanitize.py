"""Deterministic repairs for common AppSpec authoring mistakes before schema parse."""
from __future__ import annotations

import copy
import re
from typing import Any, Mapping

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

_VALID_EVIDENCE_KINDS = {
    "text",
    "metric",
    "list",
    "table",
    "chart",
    "form",
    "status",
    "navigation",
    "media",
}
_VALID_ASSERTION_KINDS = {
    "route",
    "visible",
    "state",
    "data",
    "count",
    "accessibility",
    "no_runtime_errors",
}
_EVIDENCE_KIND_ALIASES = {
    "data": "status",
    "email": "text",
    "confirmation": "text",
    "message": "text",
}
_ASSERTION_KIND_ALIASES = {
    "list": "visible",
    "form": "visible",
    "text": "visible",
    "status": "state",
    "metric": "count",
    "table": "visible",
    "chart": "visible",
    "navigation": "route",
    "media": "visible",
}


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


def _sanitize_page_evidence_ids(
    page: dict[str, Any],
    evidence_by_page: dict[str, list[str]],
    synthetic_evidence: list[dict[str, Any]],
) -> None:
    evidence_ids = list(page.get("evidence_ids") or [])
    if evidence_ids:
        return
    page_id = str(page.get("id") or "")
    linked = evidence_by_page.get(page_id, [])
    if linked:
        page["evidence_ids"] = [linked[0]]
        return

    capability_ids = [
        str(value)
        for value in (page.get("capability_ids") or [])
        if str(value).strip()
    ]
    if not capability_ids:
        capability_ids = ["CAP-UNSPECIFIED"]
    evidence_id = f"EVIDENCE-{page_id.replace('PAGE-', '')}-SURFACE"
    suffix = 2
    existing_ids = {
        str(item.get("id"))
        for item in synthetic_evidence
        if isinstance(item, dict) and item.get("id")
    }
    while evidence_id in existing_ids:
        evidence_id = f"EVIDENCE-{page_id.replace('PAGE-', '')}-SURFACE-{suffix}"
        suffix += 1
    synthetic_evidence.append(
        {
            "id": evidence_id,
            "page_id": page_id,
            "name": f"{page.get('name', 'Page')} surface",
            "description": (
                "Observable page surface used to satisfy schema traceability for "
                f"{page.get('name', 'this page')}."
            ),
            "kind": "navigation",
            "capability_ids": capability_ids[:1],
        }
    )
    page["evidence_ids"] = [evidence_id]
    evidence_by_page.setdefault(page_id, []).append(evidence_id)


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


def _normalize_kind(
    value: Any,
    *,
    valid: set[str],
    aliases: Mapping[str, str],
    default: str,
) -> str:
    text = str(value or default).strip().casefold()
    if text in valid:
        return text
    mapped = aliases.get(text)
    if mapped in valid:
        return mapped
    return default


def _humanize_identifier(identifier: str) -> str:
    text = str(identifier or "").strip()
    for prefix in ("FIELD-", "ENTITY-", "REQ-", "PAGE-", "CAP-"):
        if text.upper().startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.replace("-", " ").replace("_", " ").title() or "Unnamed"


def _sanitize_entities(payload: dict[str, Any]) -> None:
    for entity in payload.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        for field in entity.get("fields") or []:
            if not isinstance(field, dict):
                continue
            if not str(field.get("name") or "").strip():
                field["name"] = _humanize_identifier(str(field.get("id") or "Field"))


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


def _sanitize_evidence_and_assertions(payload: dict[str, Any]) -> None:
    for item in payload.get("evidence") or []:
        if isinstance(item, dict):
            item["kind"] = _normalize_kind(
                item.get("kind"),
                valid=_VALID_EVIDENCE_KINDS,
                aliases=_EVIDENCE_KIND_ALIASES,
                default="text",
            )

    for test in payload.get("acceptance_tests") or []:
        if not isinstance(test, dict):
            continue
        for assertion in test.get("assertions") or []:
            if isinstance(assertion, dict):
                assertion["kind"] = _normalize_kind(
                    assertion.get("kind"),
                    valid=_VALID_ASSERTION_KINDS,
                    aliases=_ASSERTION_KIND_ALIASES,
                    default="visible",
                )


def _sanitize_visible_assertion_evidence(payload: dict[str, Any]) -> None:
    evidence_by_page: dict[str, list[str]] = {}
    for item in payload.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        page_id = str(item.get("page_id") or "")
        evidence_id = str(item.get("id") or "")
        if page_id and evidence_id:
            evidence_by_page.setdefault(page_id, []).append(evidence_id)

    for test in payload.get("acceptance_tests") or []:
        if not isinstance(test, dict):
            continue
        for assertion in test.get("assertions") or []:
            if not isinstance(assertion, dict):
                continue
            if str(assertion.get("kind")) != "visible":
                continue
            if assertion.get("evidence_id"):
                continue
            page_id = str(assertion.get("page_id") or "")
            candidates = evidence_by_page.get(page_id) or []
            if candidates:
                assertion["evidence_id"] = candidates[0]


def _sanitize_transition_effects(payload: dict[str, Any]) -> None:
    field_types: dict[tuple[str, str], str] = {}
    field_enums: dict[tuple[str, str], list[Any]] = {}
    for entity in payload.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        entity_id = str(entity.get("id") or "")
        for field in entity.get("fields") or []:
            if not isinstance(field, dict):
                continue
            field_id = str(field.get("id") or "")
            if entity_id and field_id:
                field_types[(entity_id, field_id)] = str(field.get("type") or "string")
                if field.get("enum_values"):
                    field_enums[(entity_id, field_id)] = list(field["enum_values"])

    for transition in payload.get("transitions") or []:
        if not isinstance(transition, dict):
            continue
        for effect in transition.get("effects") or []:
            if not isinstance(effect, dict):
                continue
            if effect.get("value") is not None:
                continue
            operation = str(effect.get("operation") or "")
            if operation not in {"set", "append"}:
                continue
            key = (str(effect.get("entity_id") or ""), str(effect.get("field_id") or ""))
            field_type = field_types.get(key, "string")
            if field_type == "boolean":
                effect["value"] = True
            elif field_type in {"integer", "number"}:
                effect["value"] = 0
            elif field_type == "enum":
                enum_values = field_enums.get(key) or []
                effect["value"] = enum_values[0] if enum_values else "updated"
            else:
                effect["value"] = "updated"


def _evidence_by_id(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in (payload.get("evidence") or [])
        if isinstance(item, dict) and item.get("id")
    }


def _sanitize_state_and_journey_evidence(payload: dict[str, Any]) -> None:
    evidence = _evidence_by_id(payload)
    for state in payload.get("states") or []:
        if not isinstance(state, dict):
            continue
        page_id = str(state.get("page_id") or "")
        state["evidence_ids"] = [
            evidence_id
            for evidence_id in (state.get("evidence_ids") or [])
            if str(evidence.get(str(evidence_id), {}).get("page_id") or "") == page_id
        ]

    for journey in payload.get("journeys") or []:
        if not isinstance(journey, dict):
            continue
        for step in journey.get("steps") or []:
            if not isinstance(step, dict):
                continue
            page_id = str(step.get("expected_page_id") or "")
            step["evidence_ids"] = [
                evidence_id
                for evidence_id in (step.get("evidence_ids") or [])
                if str(evidence.get(str(evidence_id), {}).get("page_id") or "") == page_id
            ]


def _sanitize_state_graph(payload: dict[str, Any]) -> None:
    states = [item for item in (payload.get("states") or []) if isinstance(item, dict)]
    transitions = [
        item for item in (payload.get("transitions") or []) if isinstance(item, dict)
    ]
    referenced: set[str] = set()
    incoming: set[str] = set()
    outgoing: set[str] = set()
    for transition in transitions:
        from_id = str(transition.get("from_state_id") or "")
        to_id = str(transition.get("to_state_id") or "")
        if from_id:
            outgoing.add(from_id)
            referenced.add(from_id)
        if to_id:
            incoming.add(to_id)
            referenced.add(to_id)

    kept: list[dict[str, Any]] = []
    removed: set[str] = set()
    for state in states:
        state_id = str(state.get("id") or "")
        if not state_id:
            continue
        is_initial = bool(state.get("initial"))
        has_edge = state_id in referenced
        if not is_initial and not has_edge:
            removed.add(state_id)
            continue
        if not state.get("terminal") and state_id not in outgoing:
            state["terminal"] = True
        kept.append(state)
    payload["states"] = kept

    if removed:
        for page in payload.get("pages") or []:
            if not isinstance(page, dict):
                continue
            page["state_ids"] = [
                state_id
                for state_id in (page.get("state_ids") or [])
                if str(state_id) not in removed
            ]
        for journey in payload.get("journeys") or []:
            if not isinstance(journey, dict):
                continue
            if str(journey.get("start_state_id") or "") in removed:
                page_id = str(journey.get("start_page_id") or "")
                fallback = next(
                    (
                        str(state.get("id"))
                        for state in kept
                        if str(state.get("page_id")) == page_id and state.get("initial")
                    ),
                    None,
                )
                if fallback:
                    journey["start_state_id"] = fallback
            for step in journey.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                if str(step.get("expected_state_id") or "") in removed:
                    page_id = str(step.get("expected_page_id") or "")
                    fallback = next(
                        (
                            str(state.get("id"))
                            for state in kept
                            if str(state.get("page_id")) == page_id and state.get("initial")
                        ),
                        None,
                    )
                    if fallback:
                        step["expected_state_id"] = fallback
        for test in payload.get("acceptance_tests") or []:
            if not isinstance(test, dict):
                continue
            for assertion in test.get("assertions") or []:
                if not isinstance(assertion, dict):
                    continue
                state_id = str(assertion.get("state_id") or "")
                if state_id not in removed:
                    continue
                page_id = str(assertion.get("page_id") or "")
                fallback = next(
                    (
                        str(state.get("id"))
                        for state in kept
                        if str(state.get("page_id")) == page_id and state.get("initial")
                    ),
                    None,
                )
                assertion["state_id"] = fallback


def _sanitize_orphan_actions(payload: dict[str, Any]) -> None:
    """Ensure every action has a transition; prefer synthetic self-transitions over deletion."""

    transitions = [
        item for item in (payload.get("transitions") or []) if isinstance(item, dict)
    ]
    transition_action_ids = {
        str(item.get("action_id")) for item in transitions if item.get("action_id")
    }
    states = {
        str(item.get("id")): item
        for item in (payload.get("states") or [])
        if isinstance(item, dict) and item.get("id")
    }
    initial_by_page: dict[str, str] = {}
    for state in states.values():
        page_id = str(state.get("page_id") or "")
        if state.get("initial") and page_id and page_id not in initial_by_page:
            initial_by_page[page_id] = str(state.get("id"))

    for action in payload.get("actions") or []:
        if not isinstance(action, dict):
            continue
        action_id = str(action.get("id") or "")
        if not action_id or action_id in transition_action_ids:
            continue
        page_id = str(action.get("page_id") or "")
        state_id = initial_by_page.get(page_id)
        if state_id is None:
            state_id = next(
                (
                    sid
                    for sid, state in states.items()
                    if str(state.get("page_id") or "") == page_id
                ),
                None,
            )
        if state_id is None:
            continue
        pair_exists = any(
            str(item.get("from_state_id") or "") == state_id
            and str(item.get("action_id") or "") == action_id
            for item in transitions
        )
        if pair_exists:
            transition_action_ids.add(action_id)
            continue
        transitions.append(
            {
                "id": f"TRANSITION-{action_id.replace('ACTION-', '')}",
                "action_id": action_id,
                "from_state_id": state_id,
                "to_state_id": state_id,
                "description": f"Complete {action.get('name') or action_id}.",
                "preconditions": [],
                "postconditions": [],
                "effects": [],
            }
        )
        transition_action_ids.add(action_id)
    payload["transitions"] = transitions


def _sanitize_journey_step_actions(payload: dict[str, Any]) -> None:
    transitions = {
        str(item.get("id")): item
        for item in (payload.get("transitions") or [])
        if isinstance(item, dict) and item.get("id")
    }
    transition_list = [
        item for item in (payload.get("transitions") or []) if isinstance(item, dict)
    ]
    actions = {
        str(item.get("id")): item
        for item in (payload.get("actions") or [])
        if isinstance(item, dict) and item.get("id")
    }
    action_list = [item for item in (payload.get("actions") or []) if isinstance(item, dict)]
    states = {
        str(item.get("id")): item
        for item in (payload.get("states") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for journey in payload.get("journeys") or []:
        if not isinstance(journey, dict):
            continue
        current_state_id = str(journey.get("start_state_id") or "")
        for step_index, step in enumerate(journey.get("steps") or []):
            if not isinstance(step, dict):
                continue
            transition_id = str(step.get("transition_id") or "")
            transition = transitions.get(transition_id)
            if transition is None:
                continue
            from_state = str(transition.get("from_state_id") or "")
            action_id = str(transition.get("action_id") or "")
            if current_state_id and from_state != current_state_id:
                # Prefer an existing transition for this state/action pair.
                existing = next(
                    (
                        item
                        for item in transition_list
                        if str(item.get("from_state_id") or "") == current_state_id
                        and str(item.get("action_id") or "") == action_id
                    ),
                    None,
                )
                if existing is not None:
                    step["transition_id"] = str(existing.get("id"))
                    transition = existing
                else:
                    # Clone with a dedicated action so (from_state, action) stays unique.
                    action = actions.get(action_id)
                    action_clone_id = action_id
                    if action is not None:
                        action_clone_id = f"{action_id}-J{step_index+1}"
                        if action_clone_id not in actions:
                            action_clone = dict(action)
                            action_clone["id"] = action_clone_id
                            current_state = states.get(current_state_id)
                            if current_state is not None:
                                action_clone["page_id"] = str(current_state.get("page_id") or "")
                            action_list.append(action_clone)
                            actions[action_clone_id] = action_clone
                    clone_id = f"{transition_id}-J{step_index+1}"
                    if clone_id not in transitions:
                        clone = dict(transition)
                        clone["id"] = clone_id
                        clone["from_state_id"] = current_state_id
                        clone["action_id"] = action_clone_id
                        transition_list.append(clone)
                        transitions[clone_id] = clone
                    else:
                        transitions[clone_id]["from_state_id"] = current_state_id
                        transitions[clone_id]["action_id"] = action_clone_id
                    step["transition_id"] = clone_id
                    transition = transitions[clone_id]
                    action_id = action_clone_id

            action_id = str(transition.get("action_id") or action_id)
            action = actions.get(action_id)
            current_state = states.get(current_state_id)
            if action is not None and current_state is not None:
                current_page = str(current_state.get("page_id") or "")
                if current_page and str(action.get("page_id") or "") != current_page:
                    action_clone_id = f"{action_id}-ON-{current_page}"
                    if action_clone_id not in actions:
                        action_clone = dict(action)
                        action_clone["id"] = action_clone_id
                        action_clone["page_id"] = current_page
                        action_list.append(action_clone)
                        actions[action_clone_id] = action_clone
                    # Avoid ambiguous (from_state, action) when rewriting action_id.
                    conflict = any(
                        str(item.get("id")) != str(transition.get("id"))
                        and str(item.get("from_state_id") or "")
                        == str(transition.get("from_state_id") or "")
                        and str(item.get("action_id") or "") == action_clone_id
                        for item in transition_list
                    )
                    if not conflict:
                        transition["action_id"] = action_clone_id
                        action_id = action_clone_id
                    to_state = states.get(str(transition.get("to_state_id") or ""))
                    if to_state is not None and str(to_state.get("page_id") or "") != current_page:
                        actions[str(transition.get("action_id") or action_id)]["kind"] = "navigate"
            if action_id:
                step["action_id"] = action_id
            to_state_id = str(transition.get("to_state_id") or "")
            if to_state_id:
                step["expected_state_id"] = to_state_id
                state = states.get(to_state_id)
                if state is not None:
                    step["expected_page_id"] = str(state.get("page_id") or "")
                current_state_id = to_state_id
    payload["transitions"] = transition_list
    payload["actions"] = action_list


def _sanitize_ambiguous_transitions(payload: dict[str, Any]) -> None:
    """Drop duplicate (from_state, action) transitions, keeping the first."""

    seen: set[tuple[str, str]] = set()
    kept: list[dict[str, Any]] = []
    removed: set[str] = set()
    for transition in payload.get("transitions") or []:
        if not isinstance(transition, dict):
            continue
        key = (
            str(transition.get("from_state_id") or "").casefold(),
            str(transition.get("action_id") or "").casefold(),
        )
        transition_id = str(transition.get("id") or "")
        if key in seen and key[0] and key[1]:
            removed.add(transition_id)
            continue
        seen.add(key)
        kept.append(transition)
    payload["transitions"] = kept
    if not removed:
        return
    # Retarget journey steps that pointed at removed transitions.
    by_pair: dict[tuple[str, str], str] = {
        (
            str(item.get("from_state_id") or "").casefold(),
            str(item.get("action_id") or "").casefold(),
        ): str(item.get("id"))
        for item in kept
    }
    for journey in payload.get("journeys") or []:
        if not isinstance(journey, dict):
            continue
        for step in journey.get("steps") or []:
            if not isinstance(step, dict):
                continue
            transition_id = str(step.get("transition_id") or "")
            if transition_id not in removed:
                continue
            key = (
                str(step.get("expected_state_id") or "").casefold(),  # may be wrong
                str(step.get("action_id") or "").casefold(),
            )
            # Prefer transition matching the step action from journey current is unknown;
            # fall back to any kept transition with the same action.
            replacement = next(
                (
                    str(item.get("id"))
                    for item in kept
                    if str(item.get("action_id") or "") == str(step.get("action_id") or "")
                ),
                None,
            )
            if replacement:
                step["transition_id"] = replacement


def _sanitize_page_initial_states(payload: dict[str, Any]) -> None:
    states_by_page: dict[str, list[dict[str, Any]]] = {}
    for state in payload.get("states") or []:
        if not isinstance(state, dict):
            continue
        page_id = str(state.get("page_id") or "")
        if page_id:
            states_by_page.setdefault(page_id, []).append(state)
    for page_id, states in states_by_page.items():
        initials = [state for state in states if state.get("initial")]
        if len(initials) == 1:
            continue
        if len(initials) > 1:
            for state in initials[1:]:
                state["initial"] = False
            continue
        if states:
            states[0]["initial"] = True


def _sanitize_route_assertions(payload: dict[str, Any]) -> None:
    pages = [
        item for item in (payload.get("pages") or []) if isinstance(item, dict) and item.get("id")
    ]
    route_to_page = {
        _sanitize_route(page.get("route")): str(page.get("id")) for page in pages
    }
    for test in payload.get("acceptance_tests") or []:
        if not isinstance(test, dict):
            continue
        for assertion in test.get("assertions") or []:
            if not isinstance(assertion, dict):
                continue
            if str(assertion.get("kind")) != "route":
                continue
            if assertion.get("page_id"):
                continue
            expected = _sanitize_route(assertion.get("expected") or "/")
            page_id = route_to_page.get(expected)
            if page_id is None:
                # Longest matching prefix among known routes.
                matches = [
                    (route, pid)
                    for route, pid in route_to_page.items()
                    if expected.startswith(route.rstrip("/") + "/") or expected == route
                ]
                matches.sort(key=lambda item: len(item[0]), reverse=True)
                page_id = matches[0][1] if matches else (str(pages[0].get("id")) if pages else None)
            if page_id:
                assertion["page_id"] = page_id


def _sanitize_trace_journeys_and_tests(payload: dict[str, Any]) -> None:
    journeys = {
        str(item.get("id")): item
        for item in (payload.get("journeys") or [])
        if isinstance(item, dict) and item.get("id")
    }
    tests = {
        str(item.get("id")): item
        for item in (payload.get("acceptance_tests") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for link in payload.get("traceability") or []:
        if not isinstance(link, dict):
            continue
        requirement_id = str(link.get("requirement_id") or "")
        if not requirement_id:
            continue
        journey_ids = [str(value) for value in (link.get("journey_ids") or [])]
        kept_journeys: list[str] = []
        for journey_id in journey_ids:
            journey = journeys.get(journey_id)
            if journey is None:
                continue
            reqs = [str(value) for value in (journey.get("requirement_ids") or [])]
            if requirement_id not in reqs:
                reqs.append(requirement_id)
                journey["requirement_ids"] = reqs
            kept_journeys.append(journey_id)
        link["journey_ids"] = kept_journeys

        test_ids = [str(value) for value in (link.get("acceptance_test_ids") or [])]
        for test_id in test_ids:
            test = tests.get(test_id)
            if test is None:
                continue
            reqs = [str(value) for value in (test.get("requirement_ids") or [])]
            if requirement_id not in reqs:
                reqs.append(requirement_id)
                test["requirement_ids"] = reqs
            if kept_journeys and not test.get("journey_id"):
                test["journey_id"] = kept_journeys[0]
            elif kept_journeys and str(test.get("journey_id")) not in kept_journeys:
                test["journey_id"] = kept_journeys[0]


def _sanitize_action_capability_page_alignment(payload: dict[str, Any]) -> None:
    pages = {
        str(item.get("id")): item
        for item in (payload.get("pages") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for action in payload.get("actions") or []:
        if not isinstance(action, dict):
            continue
        page = pages.get(str(action.get("page_id") or ""))
        if page is None:
            continue
        page_caps = [str(value) for value in (page.get("capability_ids") or [])]
        action_caps = [str(value) for value in (action.get("capability_ids") or [])]
        aligned = [cap for cap in action_caps if cap in page_caps]
        if aligned:
            action["capability_ids"] = aligned
            continue
        if page_caps:
            action["capability_ids"] = page_caps[:1]
            continue
        # Keep at least one capability id for schema; page will be repaired later.
        if not action_caps:
            action["capability_ids"] = ["CAP-UNSPECIFIED"]


def _sanitize_page_state_membership(payload: dict[str, Any]) -> None:
    states_by_page: dict[str, list[str]] = {}
    for state in payload.get("states") or []:
        if not isinstance(state, dict):
            continue
        page_id = str(state.get("page_id") or "")
        state_id = str(state.get("id") or "")
        if page_id and state_id:
            states_by_page.setdefault(page_id, []).append(state_id)
    for page in payload.get("pages") or []:
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("id") or "")
        merged: list[str] = []
        seen: set[str] = set()
        for state_id in list(page.get("state_ids") or []) + states_by_page.get(page_id, []):
            text = str(state_id)
            if text and text not in seen:
                merged.append(text)
                seen.add(text)
        page["state_ids"] = merged


def _sanitize_traceability_alignment(payload: dict[str, Any]) -> None:
    pages = {
        str(item.get("id")): item
        for item in (payload.get("pages") or [])
        if isinstance(item, dict) and item.get("id")
    }
    evidence = _evidence_by_id(payload)
    capabilities = {
        str(item.get("id")): item
        for item in (payload.get("capabilities") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for link in payload.get("traceability") or []:
        if not isinstance(link, dict):
            continue
        requirement_id = str(link.get("requirement_id") or "")
        capability_ids = [
            str(value)
            for value in (link.get("capability_ids") or [])
            if str(value) in capabilities
        ]
        if not capability_ids:
            continue
        if requirement_id:
            for capability_id in capability_ids:
                capability = capabilities[capability_id]
                reqs = [str(value) for value in (capability.get("requirement_ids") or [])]
                if requirement_id not in reqs:
                    reqs.append(requirement_id)
                    capability["requirement_ids"] = reqs
        capability_set = set(capability_ids)
        page_ids = [
            page_id
            for page_id in (link.get("page_ids") or [])
            if page_id in pages
            and capability_set.intersection(
                {str(value) for value in (pages[page_id].get("capability_ids") or [])}
            )
        ]
        if not page_ids:
            # Prefer pages that expose any traced capability.
            page_ids = [
                page_id
                for page_id, page in pages.items()
                if capability_set.intersection(
                    {str(value) for value in (page.get("capability_ids") or [])}
                )
            ][:3]
        page_set = set(page_ids)
        evidence_ids = [
            evidence_id
            for evidence_id in (link.get("evidence_ids") or [])
            if evidence_id in evidence
            and str(evidence[evidence_id].get("page_id") or "") in page_set
            and capability_set.intersection(
                {str(value) for value in (evidence[evidence_id].get("capability_ids") or [])}
            )
        ]
        if not evidence_ids:
            evidence_ids = [
                evidence_id
                for evidence_id, item in evidence.items()
                if str(item.get("page_id") or "") in page_set
                and capability_set.intersection(
                    {str(value) for value in (item.get("capability_ids") or [])}
                )
            ][:5]
        link["capability_ids"] = capability_ids
        if page_ids:
            link["page_ids"] = page_ids
        if evidence_ids:
            link["evidence_ids"] = evidence_ids


def _sanitize_page_evidence_membership(payload: dict[str, Any]) -> None:
    evidence_by_page: dict[str, list[str]] = {}
    for item in payload.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        page_id = str(item.get("page_id") or "")
        evidence_id = str(item.get("id") or "")
        if page_id and evidence_id:
            evidence_by_page.setdefault(page_id, []).append(evidence_id)
    for page in payload.get("pages") or []:
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("id") or "")
        known = evidence_by_page.get(page_id, [])
        known_set = set(known)
        merged: list[str] = []
        seen: set[str] = set()
        for evidence_id in list(page.get("evidence_ids") or []) + known:
            text = str(evidence_id)
            if text in known_set and text not in seen:
                merged.append(text)
                seen.add(text)
        page["evidence_ids"] = merged


def _sanitize_interaction_requirements_without_journeys(payload: dict[str, Any]) -> None:
    """Demote interaction requirements that have no traced journey to content mode."""

    journey_ids = {
        str(item.get("id"))
        for item in (payload.get("journeys") or [])
        if isinstance(item, dict) and item.get("id")
    }
    traced_with_journey: set[str] = set()
    for link in payload.get("traceability") or []:
        if not isinstance(link, dict):
            continue
        if any(str(value) in journey_ids for value in (link.get("journey_ids") or [])):
            traced_with_journey.add(str(link.get("requirement_id") or ""))

    for requirement in payload.get("requirements") or []:
        if not isinstance(requirement, dict):
            continue
        if str(requirement.get("verification_mode")) != "interaction":
            continue
        requirement_id = str(requirement.get("id") or "")
        if requirement_id and requirement_id not in traced_with_journey:
            requirement["verification_mode"] = "content"


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


def sanitize_app_spec_payload(
    payload: Mapping[str, Any],
    source_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a deep copy with common schema-breaking authoring mistakes repaired."""

    sanitized = copy.deepcopy(dict(payload))
    requirements = list(sanitized.get("requirements") or [])
    deferred_additions: list[dict[str, Any]] = []
    existing_deferred = _existing_deferred_requirement_ids(sanitized)

    for requirement in requirements:
        if isinstance(requirement, dict):
            _sanitize_requirement_source_refs(
                requirement,
                source_snapshot=source_snapshot,
                deferred_scope=deferred_additions,
                existing_deferred_requirement_ids=existing_deferred,
            )
    sanitized["requirements"] = requirements

    if deferred_additions:
        deferred_ids = {
            str(req_id)
            for item in deferred_additions
            for req_id in (item.get("requirement_ids") or [])
        }
        sanitized["traceability"] = _remove_traceability_for_requirements(
            list(sanitized.get("traceability") or []),
            deferred_ids,
        )
        sanitized["deferred_scope"] = _merge_deferred_scope(
            list(sanitized.get("deferred_scope") or []),
            deferred_additions,
        )

    _sanitize_capabilities(sanitized)
    _sanitize_entities(sanitized)
    _sanitize_deferred_scope(sanitized)
    _sanitize_page_routes(sanitized)
    _sanitize_page_action_ids(sanitized)
    _sanitize_blocking_open_questions(sanitized)
    _sanitize_cross_page_navigation(sanitized)
    _sanitize_evidence_and_assertions(sanitized)
    _sanitize_visible_assertion_evidence(sanitized)
    _sanitize_transition_effects(sanitized)
    _sanitize_state_and_journey_evidence(sanitized)
    _sanitize_state_graph(sanitized)
    _sanitize_page_initial_states(sanitized)
    _sanitize_orphan_actions(sanitized)
    _sanitize_journey_step_actions(sanitized)
    _sanitize_ambiguous_transitions(sanitized)
    _sanitize_action_capability_page_alignment(sanitized)
    _sanitize_page_state_membership(sanitized)
    _sanitize_page_action_ids(sanitized)
    _sanitize_route_assertions(sanitized)

    evidence_items = [
        item for item in (sanitized.get("evidence") or []) if isinstance(item, dict)
    ]
    evidence_by_page: dict[str, list[str]] = {}
    for item in evidence_items:
        page_id = str(item.get("page_id") or "")
        evidence_id = str(item.get("id") or "")
        if page_id and evidence_id:
            evidence_by_page.setdefault(page_id, []).append(evidence_id)

    synthetic_evidence: list[dict[str, Any]] = []
    pages = list(sanitized.get("pages") or [])
    for page in pages:
        if isinstance(page, dict):
            _sanitize_page_evidence_ids(page, evidence_by_page, synthetic_evidence)
    sanitized["pages"] = pages
    if synthetic_evidence:
        sanitized["evidence"] = evidence_items + synthetic_evidence

    _sanitize_page_evidence_membership(sanitized)
    _sanitize_traceability_alignment(sanitized)
    _sanitize_trace_journeys_and_tests(sanitized)
    _sanitize_interaction_requirements_without_journeys(sanitized)
    # Journey evidence may need a second pass after step retargeting.
    _sanitize_state_and_journey_evidence(sanitized)
    # Journey cloning can orphan the original action; repair transitions again.
    _sanitize_orphan_actions(sanitized)
    _sanitize_ambiguous_transitions(sanitized)
    _sanitize_journey_step_actions(sanitized)
    _sanitize_ambiguous_transitions(sanitized)
    _sanitize_cross_page_navigation(sanitized)
    _sanitize_page_action_ids(sanitized)
    _sanitize_state_and_journey_evidence(sanitized)

    return sanitized


__all__ = ["sanitize_app_spec_payload"]
