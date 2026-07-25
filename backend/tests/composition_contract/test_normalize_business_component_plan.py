"""Deterministic heal for AI-authored business component plans."""
from __future__ import annotations

import time

import pytest

from app.application.appspec.source import canonical_json
from app.application.composition_contract.builder import (
    CompositionStageError,
    build_ai_composition_artifact,
)
from app.application.composition_contract.context import load_composition_context
from app.application.composition_contract.normalize import (
    normalize_business_component_plan,
)
from app.application.composition_contract.policy import (
    resolve_composition_stage_policy,
)
from app.application.composition_contract.projections import project_page_purpose
from app.application.composition_contract.validation import (
    validate_business_component_plan,
)
from app.application.prompts import PromptTemplate
from app.core.config import settings
from app.domain.schemas.business_component_plan import (
    BusinessComponent,
    BusinessComponentPlan,
    ComponentStateBinding,
    PageComponentComposition,
)
from app.domain.schemas.composition_contract import (
    CompositionArtifactRef,
    CompositionValidationIssue,
    CompositionValidationReport,
)
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.composition_contract.helpers import (
    CompositionFixtureAI,
    prepare_phase2,
)


def test_normalize_repairs_coverage_and_binding_mismatches() -> None:
    prepared = prepare_phase2(request_id=3401, page_count=6)
    try:
        context = load_composition_context(
            prepared.db,
            request_id=prepared.req.id,
            phase2_result=prepared.phase2_result,
        )
        page_purpose = project_page_purpose(context)
        page_purpose_ref = CompositionArtifactRef(
            id=77,
            artifact_kind="page_purpose_contract",
            schema_version="1.0",
            sha256="b" * 64,
        )
        first_page = page_purpose.pages[0]
        capability_ids = first_page.capability_ids[:1] or (
            context.tier_1.references.capability_ids[:1]
        )
        messy = BusinessComponentPlan(
            contract_refs=context.refs,
            page_purpose_ref=page_purpose_ref,
            components=(
                BusinessComponent(
                    component_id="COMP-MESSY",
                    name="Dashboard",
                    purpose="Display useful information for users.",
                    component_kind="business_content",
                    domain_language=("information",),
                    page_ids=(first_page.page_id,),
                    role_ids=("RoleMissing",),
                    requirement_ids=(),
                    entity_ids=(),
                    capability_ids=capability_ids,
                    state_ids=(),
                    action_ids=(),
                    evidence_ids=(),
                    content_responsibilities=("Show details.",),
                    data_responsibilities=("List rows.",),
                    interaction_responsibilities=(),
                    requires_component_ids=("COMP-DOES-NOT-EXIST",),
                    shared_across_pages=False,
                ),
            ),
            page_compositions=(
                PageComponentComposition(
                    page_id=first_page.page_id,
                    ordered_component_ids=("COMP-MESSY",),
                ),
            ),
            action_trigger_bindings=(),
            component_state_bindings=(
                ComponentStateBinding(
                    component_id="COMP-MESSY",
                    state_id="StateMissing",
                    visible_evidence_ids=("EvidenceMissing",),
                ),
            ),
        )

        healed = normalize_business_component_plan(
            messy,
            context=context,
            page_purpose=page_purpose,
            page_purpose_ref=page_purpose_ref,
        )
        report = validate_business_component_plan(
            healed,
            context=context,
            page_purpose=page_purpose,
            page_purpose_ref=page_purpose_ref,
        )
        assert report.passed, report.model_dump()
        assert len(healed.page_compositions) == len(page_purpose.pages)
        assert tuple(b.action_id for b in healed.action_trigger_bindings) == (
            context.tier_1.references.action_ids
        )
    finally:
        prepared.db.close()


def test_composition_stage_error_includes_issue_codes() -> None:
    prepared = prepare_phase2(request_id=3402, page_count=6)
    try:
        context = load_composition_context(
            prepared.db,
            request_id=prepared.req.id,
            phase2_result=prepared.phase2_result,
        )
        page_purpose = project_page_purpose(context)
        page_purpose_ref = CompositionArtifactRef(
            id=78,
            artifact_kind="page_purpose_contract",
            schema_version="1.0",
            sha256="c" * 64,
        )
        policy = resolve_composition_stage_policy("business_component_plan")
        ai = CompositionFixtureAI()

        def always_fail(_artifact: BusinessComponentPlan) -> CompositionValidationReport:
            return CompositionValidationReport(
                passed=False,
                issues=(
                    CompositionValidationIssue(
                        code="page_outcome_not_covered",
                        path="page_compositions",
                        related_ids=(),
                        message="forced",
                    ),
                ),
            )

        with pytest.raises(CompositionStageError) as exc:
            build_ai_composition_artifact(
                request_id=prepared.req.id,
                policy=policy,
                schema=BusinessComponentPlan,
                prompt_template=PromptTemplate.V2_BUSINESS_COMPONENT_PLAN,
                prompt_values={
                    "stage_input_json": canonical_json(
                        {
                            "composition_contract_refs": context.refs.model_dump(
                                mode="json"
                            ),
                            "canonical_app_spec": context.app_spec.model_dump(
                                mode="json"
                            ),
                            "page_purpose_contract": page_purpose.model_dump(
                                mode="json"
                            ),
                            "page_purpose_ref": page_purpose_ref.model_dump(
                                mode="json"
                            ),
                        }
                    )
                },
                validator=always_fail,
                ai_provider=ai,
                template_renderer=JinjaTemplateRenderer(settings.TEMPLATES_DIR),
                phase_deadline=time.monotonic() + 60,
            )
        assert "page_outcome_not_covered" in str(exc.value)
    finally:
        prepared.db.close()
