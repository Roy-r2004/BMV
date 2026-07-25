from __future__ import annotations

from app.application.design_contract.normalize import normalize_product_strategy_v2
from app.application.design_contract.validation import (
    DesignValidationContext,
    validate_product_strategy_v2,
)
from app.domain.schemas.product_strategy import (
    DifferentiatorV2,
    PositioningV2,
    PrioritizedOutcomeV2,
    ProductStrategyV2,
    SurfaceStrategyV2,
)
from tests.design_contract.helpers import prepare_phase1b
from app.application.design_contract.service import _load_phase1b_contract


def test_normalize_repairs_shuffled_outcomes_and_passes_validation() -> None:
    prepared = prepare_phase1b(request_id=2201, page_count=8)
    contract = _load_phase1b_contract(
        prepared.db,
        request_id=prepared.req.id,
        phase1_summary=prepared.phase1_result["preview_contract"],
    )
    context: DesignValidationContext = contract.validation_context
    tier1, _tier2, tier3 = context.tiers
    active = list(tier3.references.requirement_ids)
    assert len(active) >= 2

    messy = ProductStrategyV2(
        contract_refs=context.refs,
        positioning=PositioningV2(
            category="Booking",
            audience="Studio clients",
            promise="Book creative sessions easily",
            problem_frame="Scheduling is manual",
        ),
        primary_outcome_requirement_id=active[-1],
        prioritized_outcomes=tuple(
            PrioritizedOutcomeV2(
                requirement_id=requirement_id,
                tier=3,
                rationale=f"Why {requirement_id}",
            )
            for requirement_id in reversed(active)
        ),
        surfaces=(
            SurfaceStrategyV2(
                surface="ops",
                role_ids=(context.app_spec.roles[0].id,),
                outcome_requirement_ids=(active[0],),
                purpose="Ops surface",
            ),
            SurfaceStrategyV2(
                surface="public",
                role_ids=(context.app_spec.roles[0].id,),
                outcome_requirement_ids=(active[0],),
                purpose="Public surface",
            ),
        ),
        differentiators=(
            DifferentiatorV2(
                id="DIFF-1",
                statement="Clear booking preview",
                proof_requirement_ids=("REQ-DOES-NOT-EXIST",),
                design_implication="Keep booking primary",
            ),
        ),
    )

    healed = normalize_product_strategy_v2(messy, context=context)
    report = validate_product_strategy_v2(healed, context=context)
    assert report.passed, report.model_dump()
    assert healed.primary_outcome_requirement_id in set(
        tier1.references.requirement_ids
    )
    assert tuple(item.requirement_id for item in healed.prioritized_outcomes) == tuple(
        requirement.id
        for requirement in context.app_spec.requirements
        if requirement.id in set(tier3.references.requirement_ids)
    )
