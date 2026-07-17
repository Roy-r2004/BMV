"""AppSpec transition validation."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, List, Tuple

from app.domain.appspec.validation.collector import _Collector, _require_reference
from app.domain.appspec.validation.effects import _validate_effect
from app.domain.schemas.app_spec import AppSpec, EntityField

def _validate_transitions(
    spec: AppSpec,
    collector: _Collector,
    *,
    entities: Dict[str, Any],
    fields: Dict[str, EntityField],
    states: Dict[str, Any],
    actions: Dict[str, Any],
) -> None:
    outgoing: Dict[str, List[Any]] = defaultdict(list)
    transition_keys: Dict[Tuple[str, str], str] = {}
    actions_with_transition = set()
    for index, transition in enumerate(spec.transitions):
        base = ("transitions", index)
        action = _require_reference(
            collector,
            transition.action_id,
            actions,
            base + ("action_id",),
            "action",
        )
        source = _require_reference(
            collector,
            transition.from_state_id,
            states,
            base + ("from_state_id",),
            "state",
        )
        target = _require_reference(
            collector,
            transition.to_state_id,
            states,
            base + ("to_state_id",),
            "state",
        )
        key = (transition.from_state_id.casefold(), transition.action_id.casefold())
        previous = transition_keys.get(key)
        if previous:
            collector.add(
                "ambiguous_transition",
                f"State/action pair already has transition {previous!r}.",
                base,
                (previous, transition.id),
            )
        else:
            transition_keys[key] = transition.id
        if source is not None:
            outgoing[source.id].append(transition)
        if action is not None:
            actions_with_transition.add(action.id)
        if action is not None and source is not None and action.page_id != source.page_id:
            collector.add(
                "transition_action_page_mismatch",
                f"Action {action.id!r} is not on source state {source.id!r}'s page.",
                base + ("action_id",),
                (transition.id, action.id, source.id),
            )
        if action is not None and source is not None and target is not None:
            if action.kind != "navigate" and source.page_id != target.page_id:
                collector.add(
                    "cross_page_transition_requires_navigation",
                    "Only navigate actions may transition between pages.",
                    base + ("to_state_id",),
                    (transition.id, action.id, source.page_id, target.page_id),
                )
        for effect_index, effect in enumerate(transition.effects):
            _validate_effect(
                collector,
                effect,
                base + ("effects", effect_index),
                entities,
                fields,
            )

    for index, action in enumerate(spec.actions):
        if action.id not in actions_with_transition:
            collector.add(
                "action_without_transition",
                f"Action {action.id!r} has no state transition.",
                ("actions", index, "id"),
                (action.id,),
            )
    for index, state in enumerate(spec.states):
        if not state.terminal and not outgoing.get(state.id):
            collector.add(
                "nonterminal_state_dead_end",
                f"Nonterminal state {state.id!r} has no outgoing transition.",
                ("states", index, "terminal"),
                (state.id,),
            )

    initial_ids = [state.id for state in spec.states if state.initial]
    reachable = set(initial_ids)
    queue = deque(initial_ids)
    while queue:
        state_id = queue.popleft()
        for transition in outgoing.get(state_id, ()):
            if transition.to_state_id in states and transition.to_state_id not in reachable:
                reachable.add(transition.to_state_id)
                queue.append(transition.to_state_id)
    for index, state in enumerate(spec.states):
        if state.id not in reachable:
            collector.add(
                "unreachable_state",
                f"State {state.id!r} is unreachable from every page's initial state.",
                ("states", index, "id"),
                (state.id,),
            )
