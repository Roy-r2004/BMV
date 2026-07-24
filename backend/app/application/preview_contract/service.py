"""Phase 1B contract-only coordinator for preview generator v2."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.application.appspec.generation import (
    AppSpecGenerationError,
    ensure_approved_app_spec,
)
from app.application.appspec.policy import v2_app_spec_policy
from app.application.appspec.repository import (
    app_spec_provenance,
    app_spec_revision_is_complete,
    load_json_object,
)
from app.application.appspec.source import capture_request_source_v2
from app.application.preview_contract.product_strategy import (
    project_product_strategy,
)
from app.application.preview_contract.repository import (
    PreviewContractRepository,
    strategy_sha256,
    tier_artifact_ref,
)
from app.application.preview_contract.tier_validation import (
    validate_preview_tiers,
)
from app.application.preview_contract.tiers import (
    TierContractContext,
    build_preview_tiers,
)
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models.request import Request
from app.domain.schemas.app_spec import AppSpec
from app.domain.schemas.preview_tier import (
    CanonicalAppSpecRef,
    CustomerSourceRef,
    ProductStrategyRef,
)


V2_APPSPEC_CONTRACT_READY = "app_spec_contract_ready"
V2_CONTRACT_READY = "contract_ready"


def _existing_bundle(req: Request) -> dict[str, Any]:
    if not req.generated_pages:
        return {}
    try:
        payload = json.loads(req.generated_pages)
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def build_v2_app_spec_contract(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    *,
    req: Request,
    app_spec_revision_id: int | None = None,
) -> dict[str, Any]:
    """Persist the complete v2 source/strategy/AppSpec/tier contract and stop."""

    source = capture_request_source_v2(req)
    strategy = project_product_strategy(req, source)
    repository = PreviewContractRepository(db)
    try:
        inputs = repository.stage_inputs(source=source, strategy=strategy)
        strategy_digest = strategy_sha256(strategy)
        policy = v2_app_spec_policy(
            source_artifact_id=inputs.source.id,
            product_strategy_revision_id=inputs.strategy.id,
            product_strategy_sha256=strategy_digest,
        )
        app_spec_result = ensure_approved_app_spec(
            db,
            request_id,
            ai_provider,
            template_renderer,
            source_snapshot_override=source.model_dump(mode="json"),
            derived_context_override={
                "product_strategy": strategy.model_dump(mode="json"),
            },
            policy=policy,
        )
    except Exception:
        db.rollback()
        raise

    revision = app_spec_result.revision_record
    if (
        app_spec_revision_id is not None
        and revision.id != app_spec_revision_id
    ):
        raise AppSpecGenerationError(
            "The requested AppSpec revision is not the current complete v2 "
            "contract.",
            revision_record=revision,
        )
    if not app_spec_revision_is_complete(
        revision,
        source_sha256=inputs.source.sha256,
        product_strategy_sha256=inputs.strategy.strategy_sha256,
    ):
        raise AppSpecGenerationError(
            "The v2 AppSpec was accepted but does not satisfy strict "
            "completeness policy.",
            revision_record=revision,
        )

    app_spec = AppSpec.model_validate(load_json_object(revision.app_spec_json))
    tier_context = TierContractContext(
        request_id=request_id,
        customer_source_ref=CustomerSourceRef(
            id=inputs.source.id,
            sha256=inputs.source.sha256,
        ),
        product_strategy_ref=ProductStrategyRef(
            id=inputs.strategy.id,
            revision=inputs.strategy.revision,
            sha256=inputs.strategy.strategy_sha256,
        ),
        app_spec_ref=CanonicalAppSpecRef(
            id=revision.id,
            revision=revision.revision,
            schema_version=revision.schema_version,
            sha256=revision.app_spec_sha256,
        ),
    )
    tiers = build_preview_tiers(
        spec=app_spec,
        strategy=strategy,
        context=tier_context,
    )
    tier_validation = validate_preview_tiers(
        tiers,
        spec=app_spec,
        strategy=strategy,
        context=tier_context,
    )
    if not tier_validation.passed:
        raise AppSpecGenerationError(
            "The v2 AppSpec could not produce a valid cumulative tier "
            "contract.",
            revision_record=revision,
        )

    try:
        persisted_tiers = repository.stage_tiers(
            tiers=tiers,
            validation=tier_validation,
        )
    except Exception:
        db.rollback()
        raise

    summary: dict[str, Any] = {
        "generator_version": "v2",
        "status": V2_CONTRACT_READY,
        "customer_source_ref": {
            "id": inputs.source.id,
            "schema_version": inputs.source.schema_version,
            "sha256": inputs.source.sha256,
        },
        "product_strategy_ref": {
            "id": inputs.strategy.id,
            "revision": inputs.strategy.revision,
            "schema_version": inputs.strategy.schema_version,
            "sha256": inputs.strategy.strategy_sha256,
            "source_sha256": inputs.strategy.source_sha256,
        },
        "app_spec_ref": {
            **app_spec_provenance(revision),
            "complete": True,
        },
        "tier_artifact_refs": {
            "tier_1": tier_artifact_ref(persisted_tiers.tier_1),
            "tier_2": tier_artifact_ref(persisted_tiers.tier_2),
            "tier_3": tier_artifact_ref(persisted_tiers.tier_3),
        },
    }
    bundle = _existing_bundle(req)
    bundle["preview_contract"] = summary
    req.generated_pages = json.dumps(bundle, ensure_ascii=False)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"preview_contract": summary}


__all__ = [
    "V2_APPSPEC_CONTRACT_READY",
    "V2_CONTRACT_READY",
    "build_v2_app_spec_contract",
]
