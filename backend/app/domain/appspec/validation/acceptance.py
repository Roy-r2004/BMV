"""AppSpec acceptance-test validation."""
from __future__ import annotations

from typing import Any, Dict

from app.domain.appspec.validation.collector import (
    _Collector,
    _reject_duplicate_references,
    _require_reference,
)
from app.domain.schemas.app_spec import AppSpec

def _validate_acceptance_tests(
    spec: AppSpec,
    collector: _Collector,
    *,
    requirements: Dict[str, Any],
    journeys: Dict[str, Any],
    pages: Dict[str, Any],
    states: Dict[str, Any],
    evidence: Dict[str, Any],
) -> None:
    for index, test in enumerate(spec.acceptance_tests):
        base = ("acceptance_tests", index)
        _reject_duplicate_references(
            collector, test.requirement_ids, base + ("requirement_ids",)
        )
        for ref_index, value in enumerate(test.requirement_ids):
            _require_reference(
                collector,
                value,
                requirements,
                base + ("requirement_ids", ref_index),
                "requirement",
            )
        journey = None
        if test.journey_id is not None:
            journey = _require_reference(
                collector, test.journey_id, journeys, base + ("journey_id",), "journey"
            )
            if journey is not None:
                unrelated = sorted(set(test.requirement_ids) - set(journey.requirement_ids))
                if unrelated:
                    collector.add(
                        "acceptance_journey_requirement_mismatch",
                        "Acceptance test claims requirements that its journey does not exercise.",
                        base + ("requirement_ids",),
                        (test.id, journey.id, *unrelated),
                    )
        for assertion_index, assertion in enumerate(test.assertions):
            assertion_base = base + ("assertions", assertion_index)
            if assertion.kind == "route" and assertion.page_id is None:
                collector.add(
                    "route_assertion_page_required",
                    "A route assertion requires page_id.",
                    assertion_base + ("page_id",),
                    (test.id,),
                )
            if assertion.kind == "visible" and assertion.evidence_id is None:
                collector.add(
                    "visible_assertion_evidence_required",
                    "A visible assertion requires evidence_id.",
                    assertion_base + ("evidence_id",),
                    (test.id,),
                )
            if assertion.kind == "state" and assertion.state_id is None:
                collector.add(
                    "state_assertion_state_required",
                    "A state assertion requires state_id.",
                    assertion_base + ("state_id",),
                    (test.id,),
                )
            page = None
            state = None
            item = None
            if assertion.page_id is not None:
                page = _require_reference(
                    collector,
                    assertion.page_id,
                    pages,
                    assertion_base + ("page_id",),
                    "page",
                )
            if assertion.state_id is not None:
                state = _require_reference(
                    collector,
                    assertion.state_id,
                    states,
                    assertion_base + ("state_id",),
                    "state",
                )
            if assertion.evidence_id is not None:
                item = _require_reference(
                    collector,
                    assertion.evidence_id,
                    evidence,
                    assertion_base + ("evidence_id",),
                    "evidence",
                )
            if page is not None and state is not None and state.page_id != page.id:
                collector.add(
                    "assertion_state_page_mismatch",
                    f"State {state.id!r} is not on asserted page {page.id!r}.",
                    assertion_base + ("state_id",),
                    (test.id, page.id, state.id),
                )
            if page is not None and item is not None and item.page_id != page.id:
                collector.add(
                    "assertion_evidence_page_mismatch",
                    f"Evidence {item.id!r} is not on asserted page {page.id!r}.",
                    assertion_base + ("evidence_id",),
                    (test.id, page.id, item.id),
                )
