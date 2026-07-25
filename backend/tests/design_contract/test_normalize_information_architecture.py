from __future__ import annotations

from app.application.design_contract.normalize import (
    normalize_information_architecture,
)
from app.application.design_contract.service import _load_phase1b_contract
from app.application.design_contract.validation import (
    validate_information_architecture,
)
from app.domain.schemas.design_contract import DesignArtifactRef
from app.domain.schemas.information_architecture import (
    InformationArchitecture,
    MobileBehavior,
    NavigationGroup,
    PageArchitecture,
    RoleRouteAccess,
)
from tests.design_contract.helpers import prepare_phase1b


def test_normalize_repairs_page_and_role_access_mismatches() -> None:
    prepared = prepare_phase1b(request_id=3302, page_count=6)
    contract = _load_phase1b_contract(
        prepared.db,
        request_id=prepared.req.id,
        phase1_summary=prepared.phase1_result["preview_contract"],
    )
    context = contract.validation_context
    spec = context.app_spec
    strategy_ref = DesignArtifactRef(
        artifact_kind="product_strategy_v2",
        id=99,
        sha256="a" * 64,
        schema_version="2.0",
    )
    mobile = MobileBehavior(
        navigation="collapsed_menu",
        primary_action="sticky",
        content_priority=("booking",),
        data_presentation="stacked_cards",
        density_adjustment="preserve",
    )
    messy_pages = tuple(
        PageArchitecture(
            page_id=page.id,
            route=page.route,
            surface=page.surface,
            purpose="Preserved authored purpose.",
            role_ids=("RoleMissing",),
            required_outcome_requirement_ids=(),
            required_action_ids=(),
            required_evidence_ids=page.evidence_ids,
            journey_ids=(),
            navigation_visibility="primary",
            deep_link_reason=None,
            mobile=mobile,
        )
        for page in reversed(spec.pages)
    )
    messy = InformationArchitecture(
        contract_refs=context.refs,
        product_strategy_ref=strategy_ref,
        navigation_principle="Keep routes simple.",
        navigation_groups=(
            NavigationGroup(
                id="NAV-WRONG",
                label="Wrong",
                surface="public",
                role_ids=(spec.roles[0].id,),
                page_ids=(spec.pages[0].id,),
            ),
        ),
        role_access=(
            RoleRouteAccess(
                role_id=spec.roles[0].id,
                entry_page_id=spec.pages[-1].id,
                accessible_page_ids=(spec.pages[0].id,),
            ),
        ),
        pages=messy_pages,
        mobile_global_behavior="Stack content on small screens.",
        preserves_canonical_routes=False,
        preserves_all_tier_3_pages=False,
    )

    healed = normalize_information_architecture(
        messy,
        context=context,
        product_strategy_ref=strategy_ref,
    )
    report = validate_information_architecture(
        healed,
        context=context,
        product_strategy_ref=strategy_ref,
    )
    assert report.passed, report.model_dump()
