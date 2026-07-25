"""Deterministic cumulative tier selection over a canonical AppSpec graph."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from app.domain.appspec.validation import validate_app_spec
from app.domain.schemas.app_spec import AppSpec, Requirement, TraceabilityLink
from app.domain.schemas.preview_tier import (
    CanonicalAppSpecRef,
    CustomerSourceRef,
    PreviewTierArtifact,
    PrimaryJourneyProof,
    ProductStrategyRef,
    RequirementCompletionProof,
    TIER_SELECTION_POLICY_REVISION,
    TierReferenceSet,
)
from app.domain.schemas.product_strategy import ProductStrategy


class TierBuildError(ValueError):
    """The accepted AppSpec cannot produce a closed cumulative tier set."""


@dataclass(frozen=True)
class TierContractContext:
    request_id: int
    customer_source_ref: CustomerSourceRef
    product_strategy_ref: ProductStrategyRef
    app_spec_ref: CanonicalAppSpecRef


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
_SPEC_COLLECTIONS = {
    "requirement_ids": "requirements",
    "role_ids": "roles",
    "entity_ids": "entities",
    "capability_ids": "capabilities",
    "page_ids": "pages",
    "state_ids": "states",
    "action_ids": "actions",
    "transition_ids": "transitions",
    "evidence_ids": "evidence",
    "journey_ids": "journeys",
    "acceptance_test_ids": "acceptance_tests",
}
_PRIORITY_RANK = {"must": 0, "should": 1, "could": 2}
_SOURCE_RANK = (
    "customer_input.desired_outcome",
    "customer_input.main_problem",
    "customer_input.business_description",
    "customer_input.target_customers",
)


def _objects(items: Iterable[object]) -> dict[str, object]:
    return {str(getattr(item, "id")): item for item in items}


def _empty_refs() -> dict[str, set[str]]:
    return {field: set() for field in _REFERENCE_FIELDS}


def _refs_from_model(references: TierReferenceSet) -> dict[str, set[str]]:
    return {
        field: set(getattr(references, field))
        for field in _REFERENCE_FIELDS
    }


def _deferred_requirement_ids(spec: AppSpec) -> set[str]:
    return {
        requirement_id
        for item in spec.deferred_scope
        for requirement_id in item.requirement_ids
    }


def _trace_map(spec: AppSpec) -> dict[str, TraceabilityLink]:
    return {link.requirement_id: link for link in spec.traceability}


def _add_many(target: set[str], values: Iterable[str]) -> bool:
    before = len(target)
    target.update(values)
    return len(target) != before


def expand_tier_graph(
    spec: AppSpec,
    seeds: dict[str, set[str]],
) -> dict[str, set[str]]:
    """Expand canonical references to a fixed point, rejecting deferred leaks."""

    refs = _empty_refs()
    for field in _REFERENCE_FIELDS:
        refs[field].update(seeds.get(field, set()))

    requirements = _objects(spec.requirements)
    roles = _objects(spec.roles)
    entities = _objects(spec.entities)
    capabilities = _objects(spec.capabilities)
    pages = _objects(spec.pages)
    states = _objects(spec.states)
    actions = _objects(spec.actions)
    transitions = _objects(spec.transitions)
    evidence = _objects(spec.evidence)
    journeys = _objects(spec.journeys)
    acceptance_tests = _objects(spec.acceptance_tests)
    traces = _trace_map(spec)
    deferred = _deferred_requirement_ids(spec)
    transition_ids_by_action: dict[str, list[str]] = {}
    for transition in spec.transitions:
        transition_ids_by_action.setdefault(transition.action_id, []).append(
            transition.id
        )
    maps = {
        "requirement_ids": requirements,
        "role_ids": roles,
        "entity_ids": entities,
        "capability_ids": capabilities,
        "page_ids": pages,
        "state_ids": states,
        "action_ids": actions,
        "transition_ids": transitions,
        "evidence_ids": evidence,
        "journey_ids": journeys,
        "acceptance_test_ids": acceptance_tests,
    }

    changed = True
    while changed:
        changed = False
        for field, object_map in maps.items():
            missing = refs[field] - set(object_map)
            if missing:
                raise TierBuildError(
                    f"{field} contains unknown canonical IDs: {sorted(missing)}"
                )

        leaked = refs["requirement_ids"] & deferred
        if leaked:
            raise TierBuildError(
                "Deferred requirements cannot enter an active tier: "
                + ", ".join(sorted(leaked))
            )

        for requirement_id in tuple(refs["requirement_ids"]):
            trace = traces.get(requirement_id)
            if trace is None:
                raise TierBuildError(
                    f"Active requirement {requirement_id!r} has no traceability link."
                )
            changed |= _add_many(
                refs["capability_ids"],
                trace.capability_ids,
            )
            changed |= _add_many(refs["page_ids"], trace.page_ids)
            changed |= _add_many(refs["evidence_ids"], trace.evidence_ids)
            changed |= _add_many(refs["journey_ids"], trace.journey_ids)
            changed |= _add_many(
                refs["acceptance_test_ids"],
                trace.acceptance_test_ids,
            )

        # Do not expand role.default_page_id into the tier. Operator/default
        # entry pages often lack journey/test closure; pulling them in here
        # makes Phase 3A page-purpose projection fail closed for the whole run.
        # Roles still enter via journeys/pages/capabilities; entry pages join
        # only when a journey, requirement trace, action, or evidence reaches them.

        for entity_id in tuple(refs["entity_ids"]):
            entity = entities[entity_id]
            changed |= _add_many(
                refs["entity_ids"],
                [
                    field.reference_entity_id
                    for field in getattr(entity, "fields")
                    if field.reference_entity_id is not None
                ],
            )

        for capability_id in tuple(refs["capability_ids"]):
            capability = capabilities[capability_id]
            changed |= _add_many(
                refs["requirement_ids"],
                getattr(capability, "requirement_ids"),
            )
            changed |= _add_many(
                refs["role_ids"],
                getattr(capability, "role_ids"),
            )
            changed |= _add_many(
                refs["entity_ids"],
                getattr(capability, "entity_ids"),
            )

        for page_id in tuple(refs["page_ids"]):
            page = pages[page_id]
            changed |= _add_many(refs["role_ids"], getattr(page, "role_ids"))
            changed |= _add_many(
                refs["capability_ids"],
                getattr(page, "capability_ids"),
            )
            changed |= _add_many(refs["state_ids"], getattr(page, "state_ids"))
            changed |= _add_many(refs["action_ids"], getattr(page, "action_ids"))
            changed |= _add_many(
                refs["evidence_ids"],
                getattr(page, "evidence_ids"),
            )

        for state_id in tuple(refs["state_ids"]):
            state = states[state_id]
            changed |= _add_many(refs["page_ids"], [getattr(state, "page_id")])
            changed |= _add_many(
                refs["evidence_ids"],
                getattr(state, "evidence_ids"),
            )

        for action_id in tuple(refs["action_ids"]):
            action = actions[action_id]
            changed |= _add_many(refs["page_ids"], [getattr(action, "page_id")])
            changed |= _add_many(refs["role_ids"], [getattr(action, "role_id")])
            changed |= _add_many(
                refs["capability_ids"],
                getattr(action, "capability_ids"),
            )
            if getattr(action, "entity_id") is not None:
                changed |= _add_many(
                    refs["entity_ids"],
                    [getattr(action, "entity_id")],
                )
            changed |= _add_many(
                refs["transition_ids"],
                transition_ids_by_action.get(action_id, ()),
            )

        for transition_id in tuple(refs["transition_ids"]):
            transition = transitions[transition_id]
            changed |= _add_many(
                refs["action_ids"],
                [getattr(transition, "action_id")],
            )
            changed |= _add_many(
                refs["state_ids"],
                [
                    getattr(transition, "from_state_id"),
                    getattr(transition, "to_state_id"),
                ],
            )
            changed |= _add_many(
                refs["entity_ids"],
                [effect.entity_id for effect in getattr(transition, "effects")],
            )

        for evidence_id in tuple(refs["evidence_ids"]):
            item = evidence[evidence_id]
            changed |= _add_many(refs["page_ids"], [getattr(item, "page_id")])
            changed |= _add_many(
                refs["capability_ids"],
                getattr(item, "capability_ids"),
            )

        for journey_id in tuple(refs["journey_ids"]):
            journey = journeys[journey_id]
            changed |= _add_many(refs["role_ids"], [getattr(journey, "role_id")])
            changed |= _add_many(
                refs["requirement_ids"],
                getattr(journey, "requirement_ids"),
            )
            changed |= _add_many(
                refs["page_ids"],
                [getattr(journey, "start_page_id")],
            )
            changed |= _add_many(
                refs["state_ids"],
                [getattr(journey, "start_state_id")],
            )
            for step in getattr(journey, "steps"):
                changed |= _add_many(
                    refs["action_ids"],
                    [step.action_id],
                )
                changed |= _add_many(
                    refs["transition_ids"],
                    [step.transition_id],
                )
                changed |= _add_many(
                    refs["page_ids"],
                    [step.expected_page_id],
                )
                changed |= _add_many(
                    refs["state_ids"],
                    [step.expected_state_id],
                )
                changed |= _add_many(refs["evidence_ids"], step.evidence_ids)

        for test_id in tuple(refs["acceptance_test_ids"]):
            test = acceptance_tests[test_id]
            changed |= _add_many(
                refs["requirement_ids"],
                getattr(test, "requirement_ids"),
            )
            if getattr(test, "journey_id") is not None:
                changed |= _add_many(
                    refs["journey_ids"],
                    [getattr(test, "journey_id")],
                )
            for assertion in getattr(test, "assertions"):
                if assertion.page_id is not None:
                    changed |= _add_many(refs["page_ids"], [assertion.page_id])
                if assertion.state_id is not None:
                    changed |= _add_many(refs["state_ids"], [assertion.state_id])
                if assertion.evidence_id is not None:
                    changed |= _add_many(
                        refs["evidence_ids"],
                        [assertion.evidence_id],
                    )

    return refs


def _canonical_reference_set(
    spec: AppSpec,
    refs: dict[str, set[str]],
) -> TierReferenceSet:
    payload = {}
    for field, collection_name in _SPEC_COLLECTIONS.items():
        payload[field] = [
            item.id
            for item in getattr(spec, collection_name)
            if item.id in refs[field]
        ]
    return TierReferenceSet.model_validate(payload)


def _source_rank(requirement: Requirement) -> int:
    for rank, preferred in enumerate(_SOURCE_RANK):
        if preferred in requirement.source_refs:
            return rank
    return len(_SOURCE_RANK)


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) > 2
    }


def _outcome_overlap(requirement: Requirement, strategy: ProductStrategy) -> int:
    expected = _tokens(strategy.primary_outcome)
    actual = _tokens(f"{requirement.title} {requirement.description}")
    return len(expected & actual)


def _primary_proof_for_requirement(
    spec: AppSpec,
    requirement: Requirement,
    trace: TraceabilityLink,
) -> PrimaryJourneyProof | None:
    states = _objects(spec.states)
    trace_journeys = set(trace.journey_ids)
    trace_tests = set(trace.acceptance_test_ids)
    evidence_order = {item.id: index for index, item in enumerate(spec.evidence)}

    for journey in spec.journeys:
        if (
            journey.id not in trace_journeys
            or requirement.id not in journey.requirement_ids
            or not journey.steps
        ):
            continue
        last_step = journey.steps[-1]
        final_state = states.get(last_step.expected_state_id)
        if final_state is None or not getattr(final_state, "terminal"):
            continue
        success_candidates = set(last_step.evidence_ids)
        success_candidates.update(getattr(final_state, "evidence_ids"))
        if not success_candidates:
            continue

        for acceptance_test in spec.acceptance_tests:
            if (
                acceptance_test.id not in trace_tests
                or acceptance_test.journey_id != journey.id
                or requirement.id not in acceptance_test.requirement_ids
            ):
                continue
            visible_success = {
                assertion.evidence_id
                for assertion in acceptance_test.assertions
                if assertion.kind == "visible"
                and assertion.evidence_id in success_candidates
                and (
                    assertion.page_id is None
                    or assertion.page_id == last_step.expected_page_id
                )
                and (
                    assertion.state_id is None
                    or assertion.state_id == last_step.expected_state_id
                )
            }
            if not visible_success:
                continue
            page_ids = {
                journey.start_page_id,
                *(step.expected_page_id for step in journey.steps),
            }
            action_ids = {step.action_id for step in journey.steps}
            transition_ids = {step.transition_id for step in journey.steps}
            return PrimaryJourneyProof(
                requirement_id=requirement.id,
                journey_id=journey.id,
                page_ids=tuple(
                    page.id for page in spec.pages if page.id in page_ids
                ),
                action_ids=tuple(
                    action.id
                    for action in spec.actions
                    if action.id in action_ids
                ),
                transition_ids=tuple(
                    transition.id
                    for transition in spec.transitions
                    if transition.id in transition_ids
                ),
                success_evidence_ids=tuple(
                    sorted(visible_success, key=evidence_order.__getitem__)
                ),
                acceptance_test_id=acceptance_test.id,
            )
    return None


def select_primary_journey_proof(
    spec: AppSpec,
    strategy: ProductStrategy,
) -> PrimaryJourneyProof:
    deferred = _deferred_requirement_ids(spec)
    traces = _trace_map(spec)
    candidates: list[tuple[tuple[int, int, int, int], PrimaryJourneyProof]] = []
    for index, requirement in enumerate(spec.requirements):
        if (
            requirement.id in deferred
            or requirement.verification_mode != "interaction"
        ):
            continue
        trace = traces.get(requirement.id)
        if trace is None:
            continue
        proof = _primary_proof_for_requirement(spec, requirement, trace)
        if proof is None:
            continue
        candidates.append(
            (
                (
                    _PRIORITY_RANK[requirement.priority],
                    _source_rank(requirement),
                    -_outcome_overlap(requirement, strategy),
                    index,
                ),
                proof,
            )
        )
    if not candidates:
        raise TierBuildError(
            "Tier 1 requires an active interaction requirement with a complete "
            "journey, action/transition chain, visible terminal evidence, and "
            "journey-backed acceptance test."
        )
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _completion_proofs(
    spec: AppSpec,
    references: TierReferenceSet,
) -> tuple[RequirementCompletionProof, ...]:
    traces = _trace_map(spec)
    evidence = set(references.evidence_ids)
    journeys = set(references.journey_ids)
    tests = set(references.acceptance_test_ids)
    proofs: list[RequirementCompletionProof] = []
    for requirement in spec.requirements:
        if requirement.id not in references.requirement_ids:
            continue
        trace = traces.get(requirement.id)
        if trace is None:
            raise TierBuildError(
                f"Requirement {requirement.id!r} lacks completion proof."
            )
        proof_evidence = tuple(
            item.id
            for item in spec.evidence
            if item.id in evidence and item.id in trace.evidence_ids
        )
        proof_journeys = tuple(
            item.id
            for item in spec.journeys
            if item.id in journeys and item.id in trace.journey_ids
        )
        proof_tests = tuple(
            item.id
            for item in spec.acceptance_tests
            if item.id in tests and item.id in trace.acceptance_test_ids
        )
        if not proof_evidence or not proof_tests:
            raise TierBuildError(
                f"Requirement {requirement.id!r} needs evidence and acceptance proof."
            )
        if requirement.verification_mode == "interaction" and not proof_journeys:
            raise TierBuildError(
                f"Interaction requirement {requirement.id!r} needs a journey proof."
            )
        proofs.append(
            RequirementCompletionProof(
                requirement_id=requirement.id,
                evidence_ids=proof_evidence,
                journey_ids=proof_journeys,
                acceptance_test_ids=proof_tests,
            )
        )
    return tuple(proofs)


def _build_artifact(
    *,
    spec: AppSpec,
    context: TierContractContext,
    tier: int,
    selection_policy_revision: str,
    primary_proof: PrimaryJourneyProof,
    seeds: dict[str, set[str]],
) -> PreviewTierArtifact:
    closed = expand_tier_graph(spec, seeds)
    references = _canonical_reference_set(spec, closed)
    return PreviewTierArtifact.model_validate(
        {
            "tier_schema_version": "1.0",
            "selection_policy_revision": selection_policy_revision,
            "tier": tier,
            "intent": {
                1: "primary_outcome",
                2: "all_must_requirements",
                3: "full_active_contract",
            }[tier],
            "request_id": context.request_id,
            "extends_tier": {1: None, 2: 1, 3: 2}[tier],
            "customer_source_ref": context.customer_source_ref,
            "product_strategy_ref": context.product_strategy_ref,
            "app_spec_ref": context.app_spec_ref,
            "primary_journey_proof": primary_proof,
            "references": references,
            "completion_proofs": _completion_proofs(spec, references),
        }
    )


def build_preview_tiers(
    *,
    spec: AppSpec,
    strategy: ProductStrategy,
    context: TierContractContext,
    selection_policy_revision: str = TIER_SELECTION_POLICY_REVISION,
) -> tuple[PreviewTierArtifact, PreviewTierArtifact, PreviewTierArtifact]:
    """Build Tier 1/2/3 in memory without persistence or provider calls."""

    report = validate_app_spec(spec)
    if not report.is_valid:
        raise TierBuildError("Tier construction requires a valid canonical AppSpec.")
    primary_proof = select_primary_journey_proof(spec, strategy)

    tier1_seeds = _empty_refs()
    tier1_seeds["requirement_ids"].add(primary_proof.requirement_id)
    tier1_seeds["journey_ids"].add(primary_proof.journey_id)
    tier1_seeds["page_ids"].update(primary_proof.page_ids)
    tier1_seeds["action_ids"].update(primary_proof.action_ids)
    tier1_seeds["transition_ids"].update(primary_proof.transition_ids)
    tier1_seeds["evidence_ids"].update(primary_proof.success_evidence_ids)
    tier1_seeds["acceptance_test_ids"].add(primary_proof.acceptance_test_id)
    tier1 = _build_artifact(
        spec=spec,
        context=context,
        tier=1,
        selection_policy_revision=selection_policy_revision,
        primary_proof=primary_proof,
        seeds=tier1_seeds,
    )

    tier2_seeds = _refs_from_model(tier1.references)
    tier2_seeds["requirement_ids"].update(
        requirement.id
        for requirement in spec.requirements
        if requirement.priority == "must"
    )
    tier2 = _build_artifact(
        spec=spec,
        context=context,
        tier=2,
        selection_policy_revision=selection_policy_revision,
        primary_proof=primary_proof,
        seeds=tier2_seeds,
    )

    deferred = _deferred_requirement_ids(spec)
    tier3_seeds = _refs_from_model(tier2.references)
    tier3_seeds["requirement_ids"].update(
        requirement.id
        for requirement in spec.requirements
        if requirement.id not in deferred
    )
    tier3_seeds["page_ids"].update(page.id for page in spec.pages)
    tier3 = _build_artifact(
        spec=spec,
        context=context,
        tier=3,
        selection_policy_revision=selection_policy_revision,
        primary_proof=primary_proof,
        seeds=tier3_seeds,
    )
    return tier1, tier2, tier3


__all__ = [
    "TierBuildError",
    "TierContractContext",
    "build_preview_tiers",
    "expand_tier_graph",
    "select_primary_journey_proof",
]
