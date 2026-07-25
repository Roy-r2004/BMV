"""Sequential three-call Phase 2 design-contract boundary."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.application.appspec.repository import load_json_object
from app.application.appspec.source import canonical_json
from app.application.design_contract.builder import (
    BuiltDesignArtifact,
    DesignStageError,
    build_structured_artifact,
)
from app.application.design_contract.normalize import (
    normalize_product_strategy_v2,
)
from app.application.design_contract.cache import (
    artifact_sha256,
    design_cache_key,
)
from app.application.design_contract.policy import (
    DesignStagePolicy,
    resolve_design_stage_policy,
)
from app.application.design_contract.repository import (
    DesignContractRepository,
    cache_hit_metrics,
    design_artifact_ref,
)
from app.application.design_contract.validation import (
    DesignValidationContext,
    validate_design_dna,
    validate_information_architecture,
    validate_product_strategy_v2,
)
from app.application.prompts import PromptTemplate
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models import (
    AppSpecRevision,
    CustomerSourceArtifact,
    PreviewTierArtifactRecord,
    ProductStrategyRevision,
    Request,
)
from app.domain.models.design_contract import DesignContractArtifactRecord
from app.domain.schemas.app_spec import AppSpec
from app.domain.schemas.customer_source import CustomerSourceSnapshotV2
from app.domain.schemas.design_contract import (
    DESIGN_CONTRACT_POLICY_REVISION,
    DesignArtifactRef,
    DesignContractRefs,
    DesignStageMetrics,
    TierArtifactRef,
)
from app.domain.schemas.design_dna import DESIGN_DNA_SCHEMA_VERSION, DesignDNA
from app.domain.schemas.information_architecture import (
    INFORMATION_ARCHITECTURE_SCHEMA_VERSION,
    InformationArchitecture,
)
from app.domain.schemas.preview_tier import (
    CanonicalAppSpecRef,
    CustomerSourceRef,
    PreviewTierArtifact,
    ProductStrategyRef,
)
from app.domain.schemas.product_strategy import (
    PRODUCT_STRATEGY_V2_SCHEMA_VERSION,
    ProductStrategy,
    ProductStrategyV2,
)


V2_DESIGN_CONTRACT_READY = "design_contract_ready"
ArtifactT = TypeVar("ArtifactT", bound=BaseModel)


@dataclass(frozen=True)
class LoadedPhase1BContract:
    refs: DesignContractRefs
    validation_context: DesignValidationContext
    source: CustomerSourceSnapshotV2
    seed: ProductStrategy
    app_spec: AppSpec
    tier_rows: tuple[
        PreviewTierArtifactRecord,
        PreviewTierArtifactRecord,
        PreviewTierArtifactRecord,
    ]


@dataclass(frozen=True)
class ResolvedDesignArtifact:
    artifact: BaseModel
    row: DesignContractArtifactRecord
    ref: DesignArtifactRef
    metrics: DesignStageMetrics


def _load_phase1b_contract(
    db: Session,
    *,
    request_id: int,
    phase1_summary: dict[str, Any],
) -> LoadedPhase1BContract:
    if phase1_summary.get("status") != "contract_ready":
        raise ValueError("Phase 2 requires a complete Phase 1B contract.")
    source_ref = phase1_summary.get("customer_source_ref") or {}
    seed_ref = phase1_summary.get("product_strategy_ref") or {}
    app_spec_ref = phase1_summary.get("app_spec_ref") or {}
    tier_ref_map = phase1_summary.get("tier_artifact_refs") or {}
    source_row = db.get(CustomerSourceArtifact, source_ref.get("id"))
    seed_row = db.get(ProductStrategyRevision, seed_ref.get("id"))
    app_spec_row = db.get(AppSpecRevision, app_spec_ref.get("id"))
    tier_rows = tuple(
        db.get(
            PreviewTierArtifactRecord,
            (tier_ref_map.get(f"tier_{tier}") or {}).get("id"),
        )
        for tier in (1, 2, 3)
    )
    if (
        source_row is None
        or seed_row is None
        or app_spec_row is None
        or any(row is None for row in tier_rows)
    ):
        raise ValueError("Phase 1B references do not resolve.")
    typed_tier_rows = tuple(tier_rows)
    refs = DesignContractRefs(
        request_id=request_id,
        customer_source_ref=CustomerSourceRef(
            id=source_row.id,
            sha256=source_row.sha256,
        ),
        product_strategy_seed_ref=ProductStrategyRef(
            id=seed_row.id,
            revision=seed_row.revision,
            sha256=seed_row.strategy_sha256,
        ),
        app_spec_ref=CanonicalAppSpecRef(
            id=app_spec_row.id,
            revision=app_spec_row.revision,
            schema_version=app_spec_row.schema_version,
            sha256=app_spec_row.app_spec_sha256,
        ),
        tier_refs=tuple(
            TierArtifactRef(
                id=row.id,
                tier=row.tier,
                sha256=row.artifact_sha256,
                selection_policy_revision=row.selection_policy_revision,
            )
            for row in typed_tier_rows
        ),
    )
    source = CustomerSourceSnapshotV2.model_validate(
        load_json_object(source_row.snapshot_json)
    )
    seed = ProductStrategy.model_validate(
        load_json_object(seed_row.strategy_json)
    )
    app_spec = AppSpec.model_validate(
        load_json_object(app_spec_row.app_spec_json)
    )
    tiers = tuple(
        PreviewTierArtifact.model_validate(
            load_json_object(row.artifact_json)
        )
        for row in typed_tier_rows
    )
    validation_context = DesignValidationContext(
        refs=refs,
        app_spec=app_spec,
        tiers=tiers,
    )
    return LoadedPhase1BContract(
        refs=refs,
        validation_context=validation_context,
        source=source,
        seed=seed,
        app_spec=app_spec,
        tier_rows=typed_tier_rows,
    )


def _reference_mode(
    req: Request,
    source: CustomerSourceSnapshotV2,
) -> tuple[Literal["none", "textual_analysis", "vision"], str | None]:
    raw_path = str(req.reference_file_path or "").strip()
    if raw_path:
        path = Path(raw_path)
        if path.is_file() and path.suffix.casefold() in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
        }:
            return "vision", str(path.resolve())
    evidence = source.reference_evidence
    if (
        evidence.screenshot_analysis
        or source.customer_input.reference_url
        or evidence.reference_metadata
    ):
        return "textual_analysis", None
    return "none", None


def _stage_input_json(
    contract: LoadedPhase1BContract,
    *,
    upstream: dict[str, Any] | None = None,
    reference_mode: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "contract_refs": contract.refs.model_dump(mode="json"),
        "customer_source": contract.source.model_dump(mode="json"),
        "phase_1a_strategy_seed": contract.seed.model_dump(mode="json"),
        "canonical_app_spec": contract.app_spec.model_dump(mode="json"),
        "tier_artifacts": [
            tier.model_dump(mode="json")
            for tier in contract.validation_context.tiers
        ],
    }
    if upstream:
        payload["upstream_artifacts"] = upstream
    if reference_mode:
        payload["reference_mode"] = reference_mode
    return canonical_json(payload)


def _ensure_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise DesignStageError(
            "The design-contract phase exceeded its total wall timeout.",
            stage="design_contract",
        )


def _cache_or_build(
    *,
    db: Session,
    repository: DesignContractRepository,
    contract: LoadedPhase1BContract,
    schema: type[ArtifactT],
    schema_version: str,
    policy: DesignStagePolicy,
    prompt_template: str,
    stage_input_json: str,
    validator: Callable[[ArtifactT], Any],
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    deadline: float,
    parent_artifact_id: int | None,
    upstream_hashes: tuple[str, ...],
    vision_image_path: str | None = None,
    normalize: Callable[[ArtifactT], ArtifactT] | None = None,
) -> ResolvedDesignArtifact:
    _ensure_deadline(deadline)
    cache_key = design_cache_key(
        refs=contract.refs,
        policy=policy,
        schema_version=schema_version,
        upstream_hashes=upstream_hashes,
    )
    cache_started = time.monotonic()
    cached = repository.find_cache(
        request_id=contract.refs.request_id,
        artifact_kind=policy.stage,
        cache_key=cache_key,
    )
    if cached is not None:
        repository.validate_cached_row_refs(cached, refs=contract.refs)
        if (
            cached.policy_revision != DESIGN_CONTRACT_POLICY_REVISION
            or cached.prompt_revision != policy.prompt_revision
            or cached.effective_model != policy.model
            or cached.model_family != policy.model_family
            or cached.parent_artifact_id != parent_artifact_id
        ):
            raise ValueError("Matching design cache metadata is inconsistent.")
        artifact = schema.model_validate(
            repository.load_artifact_json(cached)
        )
        if artifact_sha256(artifact) != cached.artifact_sha256:
            raise ValueError("Cached design artifact hash is corrupt.")
        validation = validator(artifact)
        if not validation.passed:
            raise ValueError(
                "Cached design artifact failed strict revalidation."
            )
        if (
            not cached.validation_passed
            or load_json_object(cached.validation_json)
            != validation.model_dump(mode="json")
        ):
            raise ValueError("Cached validation report is inconsistent.")
        return ResolvedDesignArtifact(
            artifact=artifact,
            row=cached,
            ref=design_artifact_ref(cached),
            metrics=cache_hit_metrics(
                cached,
                latency_ms=int((time.monotonic() - cache_started) * 1000),
            ),
        )

    built: BuiltDesignArtifact = build_structured_artifact(
        request_id=contract.refs.request_id,
        policy=policy,
        schema=schema,
        prompt_template=prompt_template,
        prompt_values={"stage_input_json": stage_input_json},
        validator=validator,
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        phase_deadline=deadline,
        vision_image_path=vision_image_path,
        normalize=normalize,
    )
    if built.metrics.cost_usd > settings.V2_DESIGN_CONTRACT_MAX_COST_USD:
        raise DesignStageError(
            f"{policy.stage} exceeded the design-contract cost budget.",
            stage=policy.stage,
        )
    persisted = repository.stage_artifact(
        artifact_kind=policy.stage,
        artifact=built.artifact,
        refs=contract.refs,
        cache_key=cache_key,
        prompt_revision=policy.prompt_revision,
        metrics=built.metrics,
        validation=built.validation,
        parent_artifact_id=parent_artifact_id,
    )
    return ResolvedDesignArtifact(
        artifact=built.artifact,
        row=persisted.row,
        ref=design_artifact_ref(persisted.row),
        metrics=built.metrics,
    )


def _bundle(req: Request) -> dict[str, Any]:
    if not req.generated_pages:
        return {}
    try:
        payload = json.loads(req.generated_pages)
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def build_v2_design_contract(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    *,
    req: Request,
    phase1_result: dict[str, Any],
) -> dict[str, Any]:
    """Run only Strategy, IA, and DesignDNA, then stop."""

    phase1_summary = dict(phase1_result.get("preview_contract") or {})
    contract = _load_phase1b_contract(
        db,
        request_id=request_id,
        phase1_summary=phase1_summary,
    )
    repository = DesignContractRepository(db)
    deadline = (
        time.monotonic() + settings.V2_DESIGN_CONTRACT_TIMEOUT_SECONDS
    )
    reference_mode, vision_image_path = _reference_mode(req, contract.source)

    strategy_policy = resolve_design_stage_policy("product_strategy_v2")
    strategy = _cache_or_build(
        db=db,
        repository=repository,
        contract=contract,
        schema=ProductStrategyV2,
        schema_version=PRODUCT_STRATEGY_V2_SCHEMA_VERSION,
        policy=strategy_policy,
        prompt_template=PromptTemplate.V2_PRODUCT_STRATEGY,
        stage_input_json=_stage_input_json(contract),
        validator=lambda artifact: validate_product_strategy_v2(
            artifact,
            context=contract.validation_context,
        ),
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        deadline=deadline,
        parent_artifact_id=None,
        upstream_hashes=(),
        normalize=lambda artifact: normalize_product_strategy_v2(
            artifact,
            context=contract.validation_context,
        ),
    )
    if not strategy.metrics.cache_hit:
        db.commit()

    strategy_payload = strategy.artifact.model_dump(mode="json")
    ia_policy = resolve_design_stage_policy("information_architecture")
    ia = _cache_or_build(
        db=db,
        repository=repository,
        contract=contract,
        schema=InformationArchitecture,
        schema_version=INFORMATION_ARCHITECTURE_SCHEMA_VERSION,
        policy=ia_policy,
        prompt_template=PromptTemplate.V2_INFORMATION_ARCHITECTURE,
        stage_input_json=_stage_input_json(
            contract,
            upstream={
                "product_strategy_v2": {
                    "ref": strategy.ref.model_dump(mode="json"),
                    "artifact": strategy_payload,
                }
            },
        ),
        validator=lambda artifact: validate_information_architecture(
            artifact,
            context=contract.validation_context,
            product_strategy_ref=strategy.ref,
        ),
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        deadline=deadline,
        parent_artifact_id=strategy.row.id,
        upstream_hashes=(strategy.ref.sha256, strategy.row.cache_key),
    )
    if (
        strategy.metrics.cost_usd + ia.metrics.cost_usd
        > settings.V2_DESIGN_CONTRACT_MAX_COST_USD
    ):
        db.rollback()
        raise DesignStageError(
            "The design-contract phase exceeded its total cost budget.",
            stage="information_architecture",
        )
    if not ia.metrics.cache_hit:
        db.commit()

    dna_policy = resolve_design_stage_policy(
        "design_dna",
        use_vision=reference_mode == "vision",
    )
    dna = _cache_or_build(
        db=db,
        repository=repository,
        contract=contract,
        schema=DesignDNA,
        schema_version=DESIGN_DNA_SCHEMA_VERSION,
        policy=dna_policy,
        prompt_template=PromptTemplate.V2_DESIGN_DNA,
        stage_input_json=_stage_input_json(
            contract,
            upstream={
                "product_strategy_v2": {
                    "ref": strategy.ref.model_dump(mode="json"),
                    "artifact": strategy_payload,
                },
                "information_architecture": {
                    "ref": ia.ref.model_dump(mode="json"),
                    "artifact": ia.artifact.model_dump(mode="json"),
                },
            },
            reference_mode=reference_mode,
        ),
        validator=lambda artifact: validate_design_dna(
            artifact,
            context=contract.validation_context,
            product_strategy_ref=strategy.ref,
            information_architecture_ref=ia.ref,
            expected_reference_mode=reference_mode,
        ),
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        deadline=deadline,
        parent_artifact_id=ia.row.id,
        upstream_hashes=(
            strategy.ref.sha256,
            strategy.row.cache_key,
            ia.ref.sha256,
            ia.row.cache_key,
        ),
        vision_image_path=vision_image_path,
    )
    _ensure_deadline(deadline)

    metrics = (strategy.metrics, ia.metrics, dna.metrics)
    total_cost = sum(item.cost_usd for item in metrics)
    if total_cost > settings.V2_DESIGN_CONTRACT_MAX_COST_USD:
        db.rollback()
        raise DesignStageError(
            "The design-contract phase exceeded its total cost budget.",
            stage="design_contract",
        )
    summary = {
        **phase1_summary,
        "status": V2_DESIGN_CONTRACT_READY,
        "design_artifact_refs": {
            "product_strategy_v2": strategy.ref.model_dump(mode="json"),
            "information_architecture": ia.ref.model_dump(mode="json"),
            "design_dna": dna.ref.model_dump(mode="json"),
        },
        "design_stage_metrics": {
            item.stage: item.model_dump(mode="json") for item in metrics
        },
        "design_contract_totals": {
            "provider_call_count": sum(
                item.provider_call_count for item in metrics
            ),
            "prompt_tokens": sum(item.prompt_tokens for item in metrics),
            "completion_tokens": sum(
                item.completion_tokens for item in metrics
            ),
            "total_tokens": sum(item.total_tokens for item in metrics),
            "cost_usd": total_cost,
            "latency_ms": sum(item.latency_ms for item in metrics),
        },
    }
    bundle = _bundle(req)
    bundle["preview_contract"] = summary
    req.generated_pages = json.dumps(bundle, ensure_ascii=False)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"preview_contract": summary}


__all__ = [
    "V2_DESIGN_CONTRACT_READY",
    "build_v2_design_contract",
]
