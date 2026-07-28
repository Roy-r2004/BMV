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
from app.domain.appspec.sanitize.reference_integrity import (
    reconcile_reference_integrity,
)
from app.domain.appspec.sanitize.trace_reference_reconcile import (
    TraceReferenceReconcileResult,
    reconcile_trace_references,
)
from app.domain.appspec.sanitize.structure import (
    _sanitize_blocking_open_questions,
    _sanitize_capabilities,
    _sanitize_cross_page_navigation,
    _sanitize_deferred_scope,
    _sanitize_entities,
    _sanitize_page_action_ids,
    _sanitize_page_routes,
    _sanitize_pages_for_internal_desk,
)

def _merge_trace_reconciliation(
    audit: dict[str, Any],
    result: TraceReferenceReconcileResult,
) -> None:
    """Fold one reconciliation pass into a single per-attempt audit record."""

    seen = {
        (item.get("trace_index"), tuple(item.get("fields_repaired") or ()))
        for item in audit.get("records") or []
    }
    records = list(audit.get("records") or [])
    for record in result.records:
        key = (record.get("trace_index"), tuple(record.get("fields_repaired") or ()))
        if key in seen:
            continue
        seen.add(key)
        records.append(record)
    audit["records"] = records[:80]
    audit["actions"] = (list(audit.get("actions") or []) + result.actions)[:80]
    audit["changed_paths"] = (
        list(audit.get("changed_paths") or []) + result.changed_paths
    )[:80]
    # Later passes are authoritative for what remains unproven.
    audit["unresolved"] = result.unresolved
    audit["unresolved_codes"] = result.unresolved_codes
    audit["applied"] = bool(audit.get("applied")) or result.applied
    audit.setdefault("original_sha256", result.original_sha256)
    audit["result_sha256"] = result.result_sha256
    audit["result"] = "reconciled" if audit["applied"] else result.result_label


def sanitize_app_spec_payload(
    payload: Mapping[str, Any],
    source_snapshot: Mapping[str, Any],
    *,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a deep copy with common schema-breaking authoring mistakes repaired."""

    sanitized = copy.deepcopy(dict(payload))
    trace_reference_audit: dict[str, Any] = {}
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
    _sanitize_pages_for_internal_desk(sanitized, source_snapshot)
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
    # Trace alignment skips rows whose capability_ids are empty, so prove those
    # references first; alignment then closes the reciprocal capability links.
    reconciled = reconcile_trace_references(sanitized)
    if reconciled.applied:
        sanitized = reconciled.payload
    _merge_trace_reconciliation(trace_reference_audit, reconciled)
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

    # Final reference-integrity pass: materialize evidence-shaped IDs that models
    # placed in entity-reference fields (request 38 class) before validation.
    sanitized, _integrity = reconcile_reference_integrity(sanitized)
    _sanitize_page_evidence_membership(sanitized)
    _sanitize_evidence_capability_page_alignment(sanitized)
    _sanitize_state_and_journey_evidence(sanitized)

    # Second pass: later passes can retarget pages/evidence. Idempotent when the
    # first pass already proved every reference.
    reconciled = reconcile_trace_references(sanitized)
    if reconciled.applied:
        sanitized = reconciled.payload
    _merge_trace_reconciliation(trace_reference_audit, reconciled)
    if diagnostics is not None and trace_reference_audit:
        diagnostics["trace_reference_reconciliation"] = trace_reference_audit

    return sanitized
