"""AppSpec traceability validation."""
from __future__ import annotations

from typing import Any, Dict

from app.domain.appspec.validation.collector import (
    _Collector,
    _reject_duplicate_references,
    _require_reference,
)
from app.domain.schemas.app_spec import AppSpec

def _validate_traceability(
    spec: AppSpec,
    collector: _Collector,
    *,
    requirements: Dict[str, Any],
    capabilities: Dict[str, Any],
    pages: Dict[str, Any],
    evidence: Dict[str, Any],
    journeys: Dict[str, Any],
    acceptance_tests: Dict[str, Any],
) -> None:
    traced: Dict[str, int] = {}
    for index, link in enumerate(spec.traceability):
        base = ("traceability", index)
        requirement = _require_reference(
            collector,
            link.requirement_id,
            requirements,
            base + ("requirement_id",),
            "requirement",
        )
        folded = link.requirement_id.casefold()
        if folded in traced:
            collector.add(
                "duplicate_traceability_link",
                f"Requirement {link.requirement_id!r} has more than one traceability link.",
                base + ("requirement_id",),
                (link.requirement_id,),
            )
        else:
            traced[folded] = index
        resolved_capabilities = []
        resolved_pages = []
        resolved_evidence = []
        resolved_journeys = []
        resolved_tests = []
        groups = (
            ("capability_ids", link.capability_ids, capabilities, "capability", resolved_capabilities),
            ("page_ids", link.page_ids, pages, "page", resolved_pages),
            ("evidence_ids", link.evidence_ids, evidence, "evidence", resolved_evidence),
            ("journey_ids", link.journey_ids, journeys, "journey", resolved_journeys),
            ("acceptance_test_ids", link.acceptance_test_ids, acceptance_tests, "acceptance test", resolved_tests),
        )
        for field_name, values, objects, target, output in groups:
            _reject_duplicate_references(collector, values, base + (field_name,))
            for ref_index, value in enumerate(values):
                obj = _require_reference(
                    collector,
                    value,
                    objects,
                    base + (field_name, ref_index),
                    target,
                )
                if obj is not None:
                    output.append(obj)
        if requirement is None:
            continue
        for capability in resolved_capabilities:
            if requirement.id not in capability.requirement_ids:
                collector.add(
                    "trace_capability_requirement_mismatch",
                    f"Capability {capability.id!r} does not implement requirement {requirement.id!r}.",
                    base + ("capability_ids",),
                    (requirement.id, capability.id),
                )
        capability_ids = {item.id for item in resolved_capabilities}
        page_ids = {item.id for item in resolved_pages}
        for page in resolved_pages:
            if not capability_ids.intersection(page.capability_ids):
                collector.add(
                    "trace_page_capability_mismatch",
                    f"Page {page.id!r} exposes none of the traced capabilities.",
                    base + ("page_ids",),
                    (requirement.id, page.id),
                )
        for item in resolved_evidence:
            if item.page_id not in page_ids or not capability_ids.intersection(item.capability_ids):
                collector.add(
                    "trace_evidence_mismatch",
                    f"Evidence {item.id!r} is not attached to a traced page and capability.",
                    base + ("evidence_ids",),
                    (requirement.id, item.id),
                )
        for journey in resolved_journeys:
            if requirement.id not in journey.requirement_ids:
                collector.add(
                    "trace_journey_requirement_mismatch",
                    f"Journey {journey.id!r} does not exercise requirement {requirement.id!r}.",
                    base + ("journey_ids",),
                    (requirement.id, journey.id),
                )
        for test in resolved_tests:
            if requirement.id not in test.requirement_ids:
                collector.add(
                    "trace_test_requirement_mismatch",
                    f"Acceptance test {test.id!r} does not prove requirement {requirement.id!r}.",
                    base + ("acceptance_test_ids",),
                    (requirement.id, test.id),
                )
        if requirement.verification_mode == "interaction":
            if not resolved_journeys:
                collector.add(
                    "interaction_requirement_journey_required",
                    f"Interaction requirement {requirement.id!r} needs a traced journey.",
                    base + ("journey_ids",),
                    (requirement.id,),
                )
            if resolved_tests and not any(test.journey_id in {j.id for j in resolved_journeys} for test in resolved_tests):
                collector.add(
                    "interaction_requirement_journey_test_required",
                    f"Interaction requirement {requirement.id!r} needs a journey-backed acceptance test.",
                    base + ("acceptance_test_ids",),
                    (requirement.id,),
                )

    deferred: Dict[str, str] = {}
    for index, item in enumerate(spec.deferred_scope):
        base = ("deferred_scope", index, "requirement_ids")
        _reject_duplicate_references(collector, item.requirement_ids, base)
        for ref_index, value in enumerate(item.requirement_ids):
            requirement = _require_reference(
                collector, value, requirements, base + (ref_index,), "requirement"
            )
            folded = value.casefold()
            if folded in deferred:
                collector.add(
                    "requirement_deferred_multiple_times",
                    f"Requirement {value!r} is already deferred by {deferred[folded]!r}.",
                    base + (ref_index,),
                    (value, deferred[folded], item.id),
                )
            else:
                deferred[folded] = item.id
            if requirement is not None and requirement.priority == "must":
                collector.add(
                    "must_requirement_cannot_be_deferred",
                    f"Must requirement {requirement.id!r} cannot be deferred.",
                    base + (ref_index,),
                    (requirement.id, item.id),
                )

    for index, requirement in enumerate(spec.requirements):
        folded = requirement.id.casefold()
        is_traced = folded in traced
        is_deferred = folded in deferred
        if is_traced and is_deferred:
            collector.add(
                "requirement_traced_and_deferred",
                f"Requirement {requirement.id!r} cannot be both traced and deferred.",
                ("requirements", index, "id"),
                (requirement.id,),
            )
        elif not is_traced and not is_deferred:
            collector.add(
                "requirement_unaccounted_for",
                f"Requirement {requirement.id!r} must be traced or explicitly deferred.",
                ("requirements", index, "id"),
                (requirement.id,),
            )

    for index, question in enumerate(spec.open_questions):
        if question.blocking:
            collector.add(
                "blocking_open_question",
                f"Blocking question {question.id!r} must be resolved before approval.",
                ("open_questions", index, "blocking"),
                (question.id,),
            )
