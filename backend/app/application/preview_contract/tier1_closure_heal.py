"""Bounded deterministic Tier 1 page-closure heal.

Keeps optional pages (AI hub, role-default ops pages, content seeds) out of
Tier 1 unless an explicit Tier 1 journey with acceptance proof requires them.
Never invents journeys/requirements/tests. Runs at most once per Tier 1 build.
"""
from __future__ import annotations

import hashlib
from typing import Any, Iterable, Mapping

from app.application.appspec.source import canonical_json
from app.domain.schemas.app_spec import AppSpec
from app.domain.schemas.preview_tier import PrimaryJourneyProof


class Tier1ClosureHealError(ValueError):
    """Mandatory Tier 1 page lacks journey-backed closure."""


Decision = str  # retained | excluded_optional_unclosed | excluded_unused | rejected_mandatory_unclosed

_REFERENCE_FIELDS = (
    "requirement_ids",
    "role_ids",
    "entity_ids",
    "capability_ids",
    "page_ids",
    "state_ids",
    "action_ids",
    "transition_ids",
    "evidence_ids",
    "journey_ids",
    "acceptance_test_ids",
)


def _objects(items: Iterable[object]) -> dict[str, object]:
    return {str(getattr(item, "id")): item for item in items}


def _decision_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        canonical_json(dict(payload)).encode("utf-8")
    ).hexdigest()


def journey_required_page_ids(
    spec: AppSpec,
    refs: Mapping[str, set[str]],
) -> dict[str, set[str]]:
    """Map page_id → in-tier journey IDs that require the page via tested hops."""

    journeys = _objects(spec.journeys)
    tests = _objects(spec.acceptance_tests)
    page_to_journeys: dict[str, set[str]] = {}
    tested_journey_ids = {
        str(getattr(tests[test_id], "journey_id"))
        for test_id in refs.get("acceptance_test_ids", set())
        if test_id in tests
        and getattr(tests[test_id], "journey_id", None) is not None
        and str(getattr(tests[test_id], "journey_id")) in refs.get("journey_ids", set())
    }
    for journey_id in refs.get("journey_ids", set()):
        if journey_id not in tested_journey_ids:
            continue
        journey = journeys.get(journey_id)
        if journey is None:
            continue
        for page_id in (
            getattr(journey, "start_page_id"),
            *(step.expected_page_id for step in getattr(journey, "steps")),
        ):
            page_to_journeys.setdefault(str(page_id), set()).add(journey_id)
    return page_to_journeys


def _supporting_requirement_ids(
    spec: AppSpec,
    refs: Mapping[str, set[str]],
    *,
    page_id: str,
    journey_ids: set[str],
) -> set[str]:
    """Match composition: requirements whose trace lists this page."""

    del journey_ids  # journey membership is checked separately
    traces = {link.requirement_id: link for link in spec.traceability}
    supported: set[str] = set()
    for requirement_id in refs.get("requirement_ids", set()):
        trace = traces.get(requirement_id)
        if trace is None:
            continue
        if page_id in getattr(trace, "page_ids"):
            supported.add(requirement_id)
    return supported


def _supporting_acceptance_test_ids(
    spec: AppSpec,
    refs: Mapping[str, set[str]],
    *,
    page_id: str,
    journey_ids: set[str],
    requirement_ids: set[str],
) -> set[str]:
    """Match composition: tests linked via page requirements or page journeys."""

    del page_id
    tests = _objects(spec.acceptance_tests)
    supported: set[str] = set()
    for test_id in refs.get("acceptance_test_ids", set()):
        test = tests.get(test_id)
        if test is None:
            continue
        journey_id = getattr(test, "journey_id", None)
        if journey_id is not None and str(journey_id) in journey_ids:
            supported.add(test_id)
            continue
        if set(getattr(test, "requirement_ids")) & requirement_ids:
            supported.add(test_id)
    return supported


def _inclusion_sources(
    spec: AppSpec,
    refs: Mapping[str, set[str]],
    *,
    page_id: str,
    journey_ids: set[str],
    primary_proof: PrimaryJourneyProof,
) -> list[str]:
    sources: list[str] = []
    if journey_ids:
        sources.append("tier1_journey")
    if page_id in primary_proof.page_ids:
        sources.append("primary_journey_proof")
    pages = _objects(spec.pages)
    roles = _objects(spec.roles)
    for role in roles.values():
        if getattr(role, "default_page_id", None) == page_id:
            sources.append("role_default")
            break
    page = pages.get(page_id)
    if page is not None and str(getattr(page, "route", "")).rstrip("/") == "/ai-features":
        sources.append("ai_hub_bind")
    if page_id == "PAGE-AI-FEATURES":
        if "ai_hub_bind" not in sources:
            sources.append("ai_hub_bind")
    traces = {link.requirement_id: link for link in spec.traceability}
    requirements = _objects(spec.requirements)
    for requirement_id in refs.get("requirement_ids", set()):
        trace = traces.get(requirement_id)
        if trace is None:
            continue
        if page_id not in getattr(trace, "page_ids"):
            continue
        sources.append("requirement_trace")
        requirement = requirements.get(requirement_id)
        if (
            requirement is not None
            and getattr(requirement, "verification_mode") == "content"
        ):
            sources.append("content_requirement")
    for evidence_id in refs.get("evidence_ids", set()):
        item = next((e for e in spec.evidence if e.id == evidence_id), None)
        if item is not None and item.page_id == page_id:
            sources.append("evidence_owner")
            break
    for state_id in refs.get("state_ids", set()):
        item = next((s for s in spec.states if s.id == state_id), None)
        if item is not None and item.page_id == page_id:
            sources.append("state_owner")
            break
    for action_id in refs.get("action_ids", set()):
        item = next((a for a in spec.actions if a.id == action_id), None)
        if item is not None and item.page_id == page_id:
            sources.append("action_owner")
            break
    for test_id in refs.get("acceptance_test_ids", set()):
        test = next((t for t in spec.acceptance_tests if t.id == test_id), None)
        if test is None:
            continue
        if any(assertion.page_id == page_id for assertion in test.assertions):
            sources.append("acceptance_assertion")
            break
    if page is not None and set(getattr(page, "capability_ids")) & refs.get(
        "capability_ids", set()
    ):
        sources.append("capability_page")
    if not sources:
        sources.append("seed_without_journey")
    # stable unique
    return list(dict.fromkeys(sources))


def _missing_closure(
    *,
    journey_ids: set[str],
    requirement_ids: set[str],
    acceptance_test_ids: set[str],
) -> list[str]:
    missing: list[str] = []
    if not journey_ids:
        missing.append("journey_ids")
    if not requirement_ids:
        missing.append("requirement_ids")
    if not acceptance_test_ids:
        missing.append("acceptance_test_ids")
    return missing


def _is_mandatory(sources: Iterable[str], journey_ids: set[str]) -> bool:
    source_set = set(sources)
    if journey_ids or "tier1_journey" in source_set or "primary_journey_proof" in source_set:
        return True
    return False


def _exclusive_orphans_for_pages(
    spec: AppSpec,
    refs: Mapping[str, set[str]],
    drop_pages: set[str],
) -> dict[str, set[str]]:
    """IDs that exist only to support excluded pages and should leave Tier 1."""

    drop: dict[str, set[str]] = {field: set() for field in _REFERENCE_FIELDS}
    drop["page_ids"] = set(drop_pages)

    for state in spec.states:
        if state.id in refs["state_ids"] and state.page_id in drop_pages:
            drop["state_ids"].add(state.id)
    for action in spec.actions:
        if action.id in refs["action_ids"] and action.page_id in drop_pages:
            drop["action_ids"].add(action.id)
    for evidence in spec.evidence:
        if evidence.id in refs["evidence_ids"] and evidence.page_id in drop_pages:
            drop["evidence_ids"].add(evidence.id)

    keep_pages = refs["page_ids"] - drop_pages
    traces = {link.requirement_id: link for link in spec.traceability}
    for requirement in spec.requirements:
        if requirement.id not in refs["requirement_ids"]:
            continue
        trace = traces.get(requirement.id)
        if trace is None:
            continue
        trace_pages = set(trace.page_ids)
        if not trace_pages:
            continue
        if trace_pages <= drop_pages and not (set(trace.journey_ids) & refs["journey_ids"]):
            if getattr(requirement, "verification_mode") == "content":
                drop["requirement_ids"].add(requirement.id)

    for capability in spec.capabilities:
        if capability.id not in refs["capability_ids"]:
            continue
        reqs = set(capability.requirement_ids)
        if reqs and reqs <= drop["requirement_ids"]:
            # only drop when no kept page still lists the capability
            still_needed = any(
                capability.id in page.capability_ids
                for page in spec.pages
                if page.id in keep_pages
            )
            if not still_needed:
                drop["capability_ids"].add(capability.id)

    for test in spec.acceptance_tests:
        if test.id not in refs["acceptance_test_ids"]:
            continue
        if test.journey_id is not None and test.journey_id in refs["journey_ids"]:
            continue
        assertion_pages = {
            assertion.page_id
            for assertion in test.assertions
            if assertion.page_id is not None
        }
        if assertion_pages and assertion_pages <= drop_pages:
            drop["acceptance_test_ids"].add(test.id)
        elif set(test.requirement_ids) and set(test.requirement_ids) <= drop[
            "requirement_ids"
        ]:
            drop["acceptance_test_ids"].add(test.id)

    for transition in spec.transitions:
        if transition.id not in refs["transition_ids"]:
            continue
        if transition.action_id in drop["action_ids"]:
            drop["transition_ids"].add(transition.id)

    return drop


def heal_tier1_page_closure(
    spec: AppSpec,
    refs: dict[str, set[str]],
    *,
    primary_proof: PrimaryJourneyProof,
    request_id: int,
    app_spec_revision: int,
) -> tuple[dict[str, set[str]], dict[str, Any]]:
    """Exclude optional unclosed Tier 1 pages; fail closed for mandatory gaps.

    Mutates a copy of ``refs``. Invoked at most once from Tier 1 artifact build.
    """

    before_pages = sorted(refs["page_ids"])
    page_journeys = journey_required_page_ids(spec, refs)
    decisions: list[dict[str, Any]] = []
    drop_pages: set[str] = set()

    for page_id in sorted(refs["page_ids"]):
        journey_ids = set(page_journeys.get(page_id, set()))
        requirement_ids = _supporting_requirement_ids(
            spec,
            refs,
            page_id=page_id,
            journey_ids=journey_ids,
        )
        acceptance_test_ids = _supporting_acceptance_test_ids(
            spec,
            refs,
            page_id=page_id,
            journey_ids=journey_ids,
            requirement_ids=requirement_ids,
        )
        sources = _inclusion_sources(
            spec,
            refs,
            page_id=page_id,
            journey_ids=journey_ids,
            primary_proof=primary_proof,
        )
        missing = _missing_closure(
            journey_ids=journey_ids,
            requirement_ids=requirement_ids,
            acceptance_test_ids=acceptance_test_ids,
        )
        mandatory = _is_mandatory(sources, journey_ids)
        classification = "mandatory" if mandatory else "optional"

        if not missing:
            if not journey_ids:
                decision: Decision = "excluded_unused"
                drop_pages.add(page_id)
            else:
                decision = "retained"
        elif mandatory:
            decision = "rejected_mandatory_unclosed"
            decisions.append(
                {
                    "page_id": page_id,
                    "inclusion_sources": sources,
                    "classification": classification,
                    "supporting_journey_ids": sorted(journey_ids),
                    "supporting_requirement_ids": sorted(requirement_ids),
                    "supporting_acceptance_test_ids": sorted(acceptance_test_ids),
                    "missing_closure_references": missing,
                    "decision": decision,
                }
            )
            raise Tier1ClosureHealError(
                "Tier 1 page "
                f"{page_id} is journey-required but lacks closed references: "
                + ", ".join(missing)
            )
        else:
            decision = "excluded_optional_unclosed"
            drop_pages.add(page_id)

        decisions.append(
            {
                "page_id": page_id,
                "inclusion_sources": sources,
                "classification": classification,
                "supporting_journey_ids": sorted(journey_ids),
                "supporting_requirement_ids": sorted(requirement_ids),
                "supporting_acceptance_test_ids": sorted(acceptance_test_ids),
                "missing_closure_references": missing,
                "decision": decision,
            }
        )

    healed = {field: set(values) for field, values in refs.items()}
    if drop_pages:
        orphans = _exclusive_orphans_for_pages(spec, healed, drop_pages)
        for field in _REFERENCE_FIELDS:
            healed[field].difference_update(orphans.get(field, set()))

    after_pages = sorted(healed["page_ids"])
    audit_core = {
        "repair_type": "deterministic_tier1_closure_heal",
        "request_id": request_id,
        "app_spec_revision": app_spec_revision,
        "target_tier": 1,
        "heal_passes": 1,
        "page_decisions": decisions,
        "before_page_ids": before_pages,
        "after_page_ids": after_pages,
        "excluded_page_ids": sorted(drop_pages),
    }
    audit = {
        **audit_core,
        "decision_hash": _decision_hash(audit_core),
    }
    return healed, audit


def empty_tier1_closure_audit() -> dict[str, Any]:
    return {
        "repair_type": "deterministic_tier1_closure_heal",
        "heal_passes": 0,
        "page_decisions": [],
        "before_page_ids": [],
        "after_page_ids": [],
        "excluded_page_ids": [],
        "decision_hash": _decision_hash(
            {
                "repair_type": "deterministic_tier1_closure_heal",
                "heal_passes": 0,
            }
        ),
    }


__all__ = [
    "Tier1ClosureHealError",
    "empty_tier1_closure_audit",
    "heal_tier1_page_closure",
    "journey_required_page_ids",
]
