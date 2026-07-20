"""AppSpec sanitize — state graph and journeys."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

def _sanitize_acceptance_journey_requirements(payload: dict[str, Any]) -> None:
    """Acceptance tests may only claim requirements exercised by their journey."""

    journeys = {
        str(item.get("id")): item
        for item in (payload.get("journeys") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for test in payload.get("acceptance_tests") or []:
        if not isinstance(test, dict):
            continue
        journey = journeys.get(str(test.get("journey_id") or ""))
        if journey is None:
            continue
        journey_reqs = [str(value) for value in (journey.get("requirement_ids") or [])]
        journey_set = set(journey_reqs)
        claimed = [str(value) for value in (test.get("requirement_ids") or [])]
        aligned = [req for req in claimed if req in journey_set]
        if aligned:
            test["requirement_ids"] = aligned
        elif journey_reqs:
            test["requirement_ids"] = journey_reqs[:1]

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

    # Drop states the model invented but never wired from an initial state
    # (e.g. STATE-PAYMENT-FAILED with no inbound transition) — otherwise AppSpec
    # validation blocks the whole preview.
    outgoing_map: dict[str, list[str]] = defaultdict(list)
    for transition in transitions:
        from_id = str(transition.get("from_state_id") or "")
        to_id = str(transition.get("to_state_id") or "")
        if from_id and to_id:
            outgoing_map[from_id].append(to_id)
    initials = [str(s.get("id")) for s in kept if s.get("initial") and s.get("id")]
    reachable: set[str] = set(initials)
    queue: deque[str] = deque(initials)
    while queue:
        current = queue.popleft()
        for nxt in outgoing_map.get(current, ()):
            if nxt not in reachable:
                reachable.add(nxt)
                queue.append(nxt)
    pruned: list[dict[str, Any]] = []
    for state in kept:
        state_id = str(state.get("id") or "")
        if state_id and state_id not in reachable:
            removed.add(state_id)
            continue
        pruned.append(state)
    kept = pruned
    payload["states"] = kept
    if removed:
        payload["transitions"] = [
            item
            for item in transitions
            if str(item.get("from_state_id") or "") not in removed
            and str(item.get("to_state_id") or "") not in removed
        ]

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

def _sanitize_unique_journey_step_ids(payload: dict[str, Any]) -> None:
    """Journey step IDs must be globally unique across the whole AppSpec."""

    seen: set[str] = set()
    for journey in payload.get("journeys") or []:
        if not isinstance(journey, dict):
            continue
        journey_id = str(journey.get("id") or "JOURNEY")
        journey_token = "".join(
            part[:1].upper() + part[1:].lower()
            for part in journey_id.replace("_", "-").split("-")
            if part
        ) or "Journey"
        for step_index, step in enumerate(journey.get("steps") or []):
            if not isinstance(step, dict):
                continue
            step_id = str(step.get("id") or f"STEP-{step_index + 1}")
            folded = step_id.casefold()
            if folded and folded not in seen:
                step["id"] = step_id
                seen.add(folded)
                continue
            candidate = f"STEP-{journey_token}-{step_index + 1}"
            suffix = 2
            while candidate.casefold() in seen:
                candidate = f"STEP-{journey_token}-{step_index + 1}-{suffix}"
                suffix += 1
            step["id"] = candidate
            seen.add(candidate.casefold())

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
