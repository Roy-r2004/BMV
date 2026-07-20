"""AppSpec sanitize — ordered repair pipeline."""
from __future__ import annotations

import copy
from typing import Any, Mapping

from app.domain.appspec.sanitize.alignment import (
    _sanitize_action_capability_page_alignment,
    _sanitize_action_capability_role_alignment,
    _sanitize_action_entity_capability_alignment,
    _sanitize_page_state_membership,
    _sanitize_trace_journeys_and_tests,
    _sanitize_traceability_acceptance_tests,
    _sanitize_traceability_alignment,
)
from app.domain.appspec.sanitize.evidence import (
    _sanitize_evidence_and_assertions,
    _sanitize_evidence_capability_page_alignment,
    _sanitize_page_evidence_ids,
    _sanitize_page_evidence_membership,
    _sanitize_route_assertions,
    _sanitize_state_and_journey_evidence,
    _sanitize_transition_effects,
    _sanitize_visible_assertion_evidence,
)
from app.domain.appspec.sanitize.source_refs import (
    _existing_deferred_requirement_ids,
    _merge_deferred_scope,
    _remove_traceability_for_requirements,
    _sanitize_requirement_source_refs,
)
from app.domain.appspec.sanitize.state_journeys import (
    _sanitize_acceptance_journey_requirements,
    _sanitize_ambiguous_transitions,
    _sanitize_interaction_requirements_without_journeys,
    _sanitize_journey_step_actions,
    _sanitize_orphan_actions,
    _sanitize_page_initial_states,
    _sanitize_state_graph,
    _sanitize_unique_journey_step_ids,
)
from app.domain.appspec.sanitize.structure import (
    _sanitize_blocking_open_questions,
    _sanitize_capabilities,
    _sanitize_cross_page_navigation,
    _sanitize_deferred_scope,
    _sanitize_entities,
    _sanitize_page_action_ids,
    _sanitize_page_routes,
)

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
    _sanitize_evidence_capability_page_alignment(sanitized)
    _sanitize_acceptance_journey_requirements(sanitized)
    _sanitize_state_and_journey_evidence(sanitized)
    _sanitize_state_graph(sanitized)
    _sanitize_page_initial_states(sanitized)
    _sanitize_orphan_actions(sanitized)
    _sanitize_unique_journey_step_ids(sanitized)
    _sanitize_journey_step_actions(sanitized)
    _sanitize_ambiguous_transitions(sanitized)
    _sanitize_action_capability_page_alignment(sanitized)
    _sanitize_action_capability_role_alignment(sanitized)
    _sanitize_action_entity_capability_alignment(sanitized)
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
    _sanitize_traceability_acceptance_tests(sanitized)
    _sanitize_trace_journeys_and_tests(sanitized)
    _sanitize_acceptance_journey_requirements(sanitized)
    _sanitize_action_entity_capability_alignment(sanitized)
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
