"""AppSpec journey validation."""
from __future__ import annotations

from typing import Any, Dict

from app.domain.appspec.validation.collector import (
    _Collector,
    _reject_duplicate_references,
    _require_reference,
)
from app.domain.schemas.app_spec import AppSpec

def _validate_journeys(
    spec: AppSpec,
    collector: _Collector,
    *,
    requirements: Dict[str, Any],
    roles: Dict[str, Any],
    pages: Dict[str, Any],
    states: Dict[str, Any],
    actions: Dict[str, Any],
    transitions: Dict[str, Any],
    evidence: Dict[str, Any],
) -> None:
    for index, journey in enumerate(spec.journeys):
        base = ("journeys", index)
        role = _require_reference(
            collector, journey.role_id, roles, base + ("role_id",), "role"
        )
        start_page = _require_reference(
            collector, journey.start_page_id, pages, base + ("start_page_id",), "page"
        )
        start_state = _require_reference(
            collector, journey.start_state_id, states, base + ("start_state_id",), "state"
        )
        if start_page is not None and start_state is not None and start_state.page_id != start_page.id:
            collector.add(
                "journey_start_mismatch",
                f"Journey start state {start_state.id!r} is not on page {start_page.id!r}.",
                base + ("start_state_id",),
                (journey.id, start_page.id, start_state.id),
            )
        if role is not None and start_page is not None and role.id not in start_page.role_ids:
            collector.add(
                "journey_role_page_mismatch",
                f"Journey role {role.id!r} cannot access start page {start_page.id!r}.",
                base + ("role_id",),
                (journey.id, role.id, start_page.id),
            )
        _reject_duplicate_references(
            collector, journey.requirement_ids, base + ("requirement_ids",)
        )
        for ref_index, value in enumerate(journey.requirement_ids):
            _require_reference(
                collector,
                value,
                requirements,
                base + ("requirement_ids", ref_index),
                "requirement",
            )
        current_state_id = journey.start_state_id
        for step_index, step in enumerate(journey.steps):
            step_base = base + ("steps", step_index)
            action = _require_reference(
                collector, step.action_id, actions, step_base + ("action_id",), "action"
            )
            transition = _require_reference(
                collector,
                step.transition_id,
                transitions,
                step_base + ("transition_id",),
                "transition",
            )
            expected_page = _require_reference(
                collector,
                step.expected_page_id,
                pages,
                step_base + ("expected_page_id",),
                "page",
            )
            expected_state = _require_reference(
                collector,
                step.expected_state_id,
                states,
                step_base + ("expected_state_id",),
                "state",
            )
            if transition is not None:
                if transition.action_id != step.action_id:
                    collector.add(
                        "journey_step_action_mismatch",
                        f"Transition {transition.id!r} uses action {transition.action_id!r}.",
                        step_base + ("action_id",),
                        (journey.id, step.id, transition.id),
                    )
                if transition.from_state_id != current_state_id:
                    collector.add(
                        "journey_step_chain_broken",
                        f"Transition starts at {transition.from_state_id!r}, expected {current_state_id!r}.",
                        step_base + ("transition_id",),
                        (journey.id, step.id, transition.id),
                    )
                if transition.to_state_id != step.expected_state_id:
                    collector.add(
                        "journey_step_state_mismatch",
                        f"Transition ends at {transition.to_state_id!r}, not {step.expected_state_id!r}.",
                        step_base + ("expected_state_id",),
                        (journey.id, step.id, transition.id),
                    )
            if action is not None and action.role_id != journey.role_id:
                collector.add(
                    "journey_step_role_mismatch",
                    f"Action {action.id!r} belongs to role {action.role_id!r}, not journey role {journey.role_id!r}.",
                    step_base + ("action_id",),
                    (journey.id, step.id, action.id),
                )
            if expected_page is not None and expected_state is not None and expected_state.page_id != expected_page.id:
                collector.add(
                    "journey_step_page_mismatch",
                    f"Expected state {expected_state.id!r} is not on expected page {expected_page.id!r}.",
                    step_base + ("expected_page_id",),
                    (journey.id, step.id, expected_page.id, expected_state.id),
                )
            _reject_duplicate_references(
                collector, step.evidence_ids, step_base + ("evidence_ids",)
            )
            for ref_index, value in enumerate(step.evidence_ids):
                item = _require_reference(
                    collector,
                    value,
                    evidence,
                    step_base + ("evidence_ids", ref_index),
                    "evidence",
                )
                if item is not None and item.page_id != step.expected_page_id:
                    collector.add(
                        "journey_evidence_page_mismatch",
                        f"Evidence {item.id!r} is not on expected page {step.expected_page_id!r}.",
                        step_base + ("evidence_ids", ref_index),
                        (journey.id, step.id, item.id),
                    )
            current_state_id = step.expected_state_id
