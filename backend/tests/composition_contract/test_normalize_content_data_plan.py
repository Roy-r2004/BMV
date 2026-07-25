"""Deterministic heal for AI-authored content/data plans."""
from __future__ import annotations

from app.application.composition_contract.context import load_composition_context
from app.application.composition_contract.normalize import (
    normalize_content_data_plan,
)
from app.application.composition_contract.projections import (
    project_business_component_plan,
    project_content_data_plan,
    project_page_purpose,
)
from app.application.composition_contract.validation import (
    validate_content_data_plan,
)
from app.domain.schemas.composition_contract import CompositionArtifactRef
from app.domain.schemas.content_data_plan import ContentItem
from tests.composition_contract.helpers import prepare_phase2


def test_normalize_strips_forbidden_markers_from_projected_copy() -> None:
    """Projected evidence text can include code markers that fail strict checks."""

    prepared = prepare_phase2(request_id=3502, page_count=6)
    try:
        context = load_composition_context(
            prepared.db,
            request_id=prepared.req.id,
            phase2_result=prepared.phase2_result,
        )
        page_purpose = project_page_purpose(context)
        page_ref = CompositionArtifactRef(
            id=91,
            artifact_kind="page_purpose_contract",
            schema_version="1.0",
            sha256="a" * 64,
        )
        component_plan = project_business_component_plan(
            context,
            page_purpose=page_purpose,
            page_purpose_ref=page_ref,
        )
        component_ref = CompositionArtifactRef(
            id=92,
            artifact_kind="business_component_plan",
            schema_version="1.0",
            sha256="b" * 64,
        )
        projected = project_content_data_plan(
            context,
            page_purpose=page_purpose,
            page_purpose_ref=page_ref,
            component_plan=component_plan,
            component_plan_ref=component_ref,
        )
        poisoned = projected.model_copy(
            update={
                "content_items": (
                    projected.content_items[0].model_copy(
                        update={
                            "value": (
                                "const booking = () => <div className=tsx>"
                            )
                        }
                    ),
                    *projected.content_items[1:],
                )
            }
        )
        healed = normalize_content_data_plan(
            poisoned,
            context=context,
            page_purpose=page_purpose,
            page_purpose_ref=page_ref,
            component_plan=component_plan,
            component_plan_ref=component_ref,
        )
        report = validate_content_data_plan(
            healed,
            context=context,
            page_purpose=page_purpose,
            page_purpose_ref=page_ref,
            component_plan=component_plan,
            component_plan_ref=component_ref,
        )
        assert report.passed, report.model_dump()
        blob = " ".join(item.value for item in healed.content_items).casefold()
        assert "const " not in blob
        assert "=>" not in blob
        assert "<div" not in blob
        assert "tsx" not in blob
    finally:
        prepared.db.close()


def test_normalize_repairs_content_coverage_and_bindings() -> None:
    prepared = prepare_phase2(request_id=3501, page_count=6)
    try:
        context = load_composition_context(
            prepared.db,
            request_id=prepared.req.id,
            phase2_result=prepared.phase2_result,
        )
        page_purpose = project_page_purpose(context)
        page_ref = CompositionArtifactRef(
            id=81,
            artifact_kind="page_purpose_contract",
            schema_version="1.0",
            sha256="d" * 64,
        )
        component_plan = project_business_component_plan(
            context,
            page_purpose=page_purpose,
            page_purpose_ref=page_ref,
        )
        component_ref = CompositionArtifactRef(
            id=82,
            artifact_kind="business_component_plan",
            schema_version="1.0",
            sha256="e" * 64,
        )
        projected = project_content_data_plan(
            context,
            page_purpose=page_purpose,
            page_purpose_ref=page_ref,
            component_plan=component_plan,
            component_plan_ref=component_ref,
        )
        broken_content = (
            ContentItem(
                content_id=projected.content_items[0].content_id,
                semantic_kind=projected.content_items[0].semantic_kind,
                value="placeholder",
                provenance="domain_safe_seed",
                page_ids=projected.content_items[0].page_ids,
                component_ids=projected.content_items[0].component_ids,
                requirement_ids=(),
            ),
            *projected.content_items[1:],
        )
        messy = projected.model_copy(
            update={
                "content_items": broken_content,
                "evidence_bindings": tuple(
                    reversed(projected.evidence_bindings)
                ),
                "action_input_bindings": (),
                "state_payloads": tuple(reversed(projected.state_payloads)),
            }
        )

        healed = normalize_content_data_plan(
            messy,
            context=context,
            page_purpose=page_purpose,
            page_purpose_ref=page_ref,
            component_plan=component_plan,
            component_plan_ref=component_ref,
        )
        report = validate_content_data_plan(
            healed,
            context=context,
            page_purpose=page_purpose,
            page_purpose_ref=page_ref,
            component_plan=component_plan,
            component_plan_ref=component_ref,
        )
        assert report.passed, report.model_dump()
        page_ids = {page.page_id for page in page_purpose.pages}
        expected_evidence = tuple(
            item.id
            for item in context.app_spec.evidence
            if item.id in set(context.tier_1.references.evidence_ids)
            and item.page_id in page_ids
        )
        assert (
            tuple(item.evidence_id for item in healed.evidence_bindings)
            == expected_evidence
        )
    finally:
        prepared.db.close()
