"""Strict Phase 5 visual-evaluation, review, and refinement contracts."""
from __future__ import annotations

from typing import Literal, Tuple

from pydantic import Field, StrictBool, StrictFloat, StrictInt, model_validator

from app.domain.schemas.composition_contract import Identifier
from app.domain.schemas.design_contract import (
    DesignContractRefs,
    Sha256,
    StrictDesignModel,
)
from app.domain.schemas.runtime_validation import ViewportName


VISUAL_EVALUATION_SCHEMA_VERSION = "1.0"
VISUAL_EVALUATION_POLICY_REVISION = "2026-07-24.1"
VISUAL_EVIDENCE_POLICY_REVISION = "2026-07-24.1"
VISUAL_HARD_GATE_POLICY_REVISION = "2026-07-24.1"
VISUAL_SCORE_BAND_POLICY_REVISION = "2026-07-24.1"
VISUAL_ACCEPTANCE_POLICY_REVISION = "2026-07-24.1"
VISUAL_IMAGE_BUNDLE_POLICY_REVISION = "2026-07-24.1"
VISUAL_REFINEMENT_POLICY_REVISION = "2026-07-24.1"

VisualTerminalStatus = Literal[
    "candidate_visual_accepted",
    "candidate_visual_rejected",
    "candidate_refinement_failed",
]
Repairability = Literal[
    "accepted",
    "rejected_not_repairable",
    "rejected_repairable",
]
EvaluationSubject = Literal["original", "refined"]
ScorecardActor = Literal["critic", "reviewer"]
FailureSeverity = Literal["none", "minor", "major", "blocking"]
FindingSource = Literal["deterministic", "critic", "reviewer"]
ComparisonMode = Literal["absolute_only", "blind_pair"]

VISUAL_DIMENSIONS = (
    "business_specificity",
    "product_story_clarity",
    "hierarchy_and_composition",
    "visual_coherence",
    "design_dna_adherence",
    "content_credibility",
    "interaction_clarity",
    "conversion_strength",
    "mobile_quality",
    "responsive_consistency",
    "density_and_readability",
    "evidence_visibility",
    "novelty",
    "trust_and_professionalism",
)
VisualDimension = Literal[
    "business_specificity",
    "product_story_clarity",
    "hierarchy_and_composition",
    "visual_coherence",
    "design_dna_adherence",
    "content_credibility",
    "interaction_clarity",
    "conversion_strength",
    "mobile_quality",
    "responsive_consistency",
    "density_and_readability",
    "evidence_visibility",
    "novelty",
    "trust_and_professionalism",
]


class VisualEvaluationRefs(StrictDesignModel):
    request_id: StrictInt = Field(ge=1)
    candidate_revision_id: StrictInt = Field(ge=1)
    candidate_revision_uuid: str = Field(
        min_length=36,
        max_length=36,
        pattern=(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            r"[0-9a-f]{4}-[0-9a-f]{12}$"
        ),
    )
    candidate_manifest_sha256: Sha256
    runtime_attempt_id: StrictInt = Field(ge=1)
    runtime_summary_id: StrictInt = Field(ge=1)
    runtime_summary_sha256: Sha256
    build_attempt_id: StrictInt = Field(ge=1)
    build_hash: Sha256
    screenshot_set_sha256: Sha256
    design_contract_refs: DesignContractRefs
    page_purpose_sha256: Sha256
    business_component_plan_sha256: Sha256
    content_data_plan_sha256: Sha256
    interaction_contract_sha256: Sha256
    component_dependency_graph_sha256: Sha256
    visual_policy_revision: str = Field(
        default=VISUAL_EVALUATION_POLICY_REVISION,
        pattern=r"^2026-07-24\.1$",
    )


class ModelCapabilityResolution(StrictDesignModel):
    provider: Literal["openrouter"]
    model: str = Field(min_length=1, max_length=240)
    family: str = Field(min_length=1, max_length=80)
    capability: Literal["multimodal_chat", "text_chat"]
    message_format: Literal["openai_content_parts", "openai_text_messages"]
    max_images: StrictInt = Field(ge=0, le=100)
    max_image_bytes: StrictInt = Field(ge=0)
    max_aggregate_image_bytes: StrictInt = Field(ge=0)
    registry_revision: str = Field(
        default="2026-07-24.1",
        pattern=r"^2026-07-24\.1$",
    )


class VisualStageRouting(StrictDesignModel):
    stage: Literal["critic", "reviewer", "refinement", "technical_repair"]
    capability: ModelCapabilityResolution
    prompt_revision: str = Field(min_length=1, max_length=64)
    temperature: StrictFloat = Field(ge=0, le=1)
    max_tokens: StrictInt = Field(ge=1, le=42_000)
    timeout_seconds: StrictInt = Field(ge=1, le=300)


class VisualEvaluationLimits(StrictDesignModel):
    phase_timeout_seconds: StrictInt = Field(ge=1, le=1_200)
    max_calls: StrictInt = Field(ge=2, le=6)
    max_output_tokens: StrictInt = Field(ge=1, le=42_000)
    max_cost_usd: StrictFloat = Field(ge=0.01, le=1.50)
    max_refinement_files: StrictInt = Field(ge=1, le=8)
    max_refinement_pages: StrictInt = Field(ge=1, le=4)
    max_refinement_batches: Literal[1] = 1
    max_technical_repairs: Literal[1] = 1


class ScreenshotVisualEvidence(StrictDesignModel):
    evidence_id: Identifier
    page_id: Identifier
    route: str = Field(min_length=1, max_length=300)
    viewport: ViewportName
    relative_path: str = Field(min_length=1, max_length=500)
    sha256: Sha256
    byte_count: StrictInt = Field(ge=1)
    width: StrictInt = Field(ge=320, le=4096)
    height: StrictInt = Field(ge=480, le=4096)
    mode: str = Field(min_length=1, max_length=20)
    alpha_opaque_ratio: StrictFloat = Field(ge=0, le=1)
    luminance_mean: StrictFloat = Field(ge=0, le=255)
    luminance_stddev: StrictFloat = Field(ge=0, le=128)
    entropy: StrictFloat = Field(ge=0, le=16)
    perceptual_sha256: Sha256
    structural_sha256: Sha256
    blank: StrictBool
    transparent: StrictBool
    materially_uniform: StrictBool


class ImageBundleGroup(StrictDesignModel):
    group_index: StrictInt = Field(ge=0, le=99)
    page_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    evidence_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    image_count: StrictInt = Field(ge=1, le=100)
    aggregate_image_bytes: StrictInt = Field(ge=1)
    group_sha256: Sha256

    @model_validator(mode="after")
    def _group_is_complete(self) -> "ImageBundleGroup":
        if (
            self.image_count != len(self.evidence_ids)
            or len(self.evidence_ids) != len(set(self.evidence_ids))
        ):
            raise ValueError("Image group membership is inconsistent")
        return self


class VisualEvidenceBundle(StrictDesignModel):
    schema_version: str = Field(
        default=VISUAL_EVALUATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    refs: VisualEvaluationRefs
    evidence_policy_revision: str = Field(
        default=VISUAL_EVIDENCE_POLICY_REVISION,
        pattern=r"^2026-07-24\.1$",
    )
    image_bundle_policy_revision: str = Field(
        default=VISUAL_IMAGE_BUNDLE_POLICY_REVISION,
        pattern=r"^2026-07-24\.1$",
    )
    capture_policy_revision: str = Field(min_length=1, max_length=64)
    browser_version: str = Field(min_length=1, max_length=120)
    ordered_screenshots: Tuple[ScreenshotVisualEvidence, ...] = Field(
        min_length=1,
        max_length=300,
    )
    grouping_manifest: Tuple[ImageBundleGroup, ...] = Field(
        min_length=1,
        max_length=6,
    )
    ordered_screenshot_hashes: Tuple[Sha256, ...] = Field(
        min_length=1,
        max_length=300,
    )
    screenshot_set_sha256: Sha256
    cache_key: Sha256

    @model_validator(mode="after")
    def _bundle_is_complete(self) -> "VisualEvidenceBundle":
        ids = tuple(item.evidence_id for item in self.ordered_screenshots)
        grouped = tuple(
            evidence_id
            for group in self.grouping_manifest
            for evidence_id in group.evidence_ids
        )
        if (
            ids != grouped
            or self.ordered_screenshot_hashes
            != tuple(item.sha256 for item in self.ordered_screenshots)
            or len(ids) != len(set(ids))
            or tuple(group.group_index for group in self.grouping_manifest)
            != tuple(range(len(self.grouping_manifest)))
        ):
            raise ValueError("Evidence bundle order or grouping is invalid")
        return self


class VisualHardGateFinding(StrictDesignModel):
    finding_id: Identifier
    code: str = Field(min_length=1, max_length=96)
    severity: Literal["advisory", "blocking"]
    evidence_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=300)
    routes: Tuple[str, ...] = Field(min_length=1, max_length=100)
    viewports: Tuple[ViewportName, ...] = Field(min_length=1, max_length=3)
    rationale: str = Field(min_length=10, max_length=4000)
    deterministic_support: Literal[True] = True


class VisualHardGateReport(StrictDesignModel):
    schema_version: str = Field(
        default=VISUAL_EVALUATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    refs: VisualEvaluationRefs
    policy_revision: str = Field(
        default=VISUAL_HARD_GATE_POLICY_REVISION,
        pattern=r"^2026-07-24\.1$",
    )
    cache_key: Sha256
    checks: Tuple[str, ...] = Field(min_length=1, max_length=50)
    findings: Tuple[VisualHardGateFinding, ...] = Field(
        default=(),
        max_length=300,
    )
    passed: StrictBool

    @model_validator(mode="after")
    def _passing_has_no_blocker(self) -> "VisualHardGateReport":
        blockers = any(item.severity == "blocking" for item in self.findings)
        if self.passed == blockers:
            raise ValueError("Hard-gate status is inconsistent")
        return self


class VisualDimensionAssessment(StrictDesignModel):
    dimension: VisualDimension
    score: StrictInt = Field(ge=0, le=100)
    confidence: StrictFloat = Field(ge=0, le=1)
    evidence_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=300)
    affected_routes: Tuple[str, ...] = Field(min_length=1, max_length=100)
    affected_viewports: Tuple[ViewportName, ...] = Field(
        min_length=1,
        max_length=3,
    )
    rationale: str = Field(min_length=20, max_length=4000)
    failure_severity: FailureSeverity
    deterministic_support: StrictBool


class VisualFinding(StrictDesignModel):
    finding_id: Identifier
    source: FindingSource
    issue_type: str = Field(min_length=1, max_length=96)
    severity: FailureSeverity
    dimension_ids: Tuple[VisualDimension, ...] = Field(
        min_length=1,
        max_length=14,
    )
    evidence_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=300)
    routes: Tuple[str, ...] = Field(min_length=1, max_length=100)
    viewports: Tuple[ViewportName, ...] = Field(min_length=1, max_length=3)
    page_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    component_ids: Tuple[Identifier, ...] = Field(default=(), max_length=200)
    rationale: str = Field(min_length=20, max_length=4000)
    deterministic_support: StrictBool


class VisualScorecard(StrictDesignModel):
    schema_version: str = Field(
        default=VISUAL_EVALUATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    actor: ScorecardActor
    subject: EvaluationSubject
    group_index: StrictInt | None = Field(default=None, ge=0, le=99)
    dimensions: Tuple[VisualDimensionAssessment, ...] = Field(
        min_length=14,
        max_length=14,
    )
    findings: Tuple[VisualFinding, ...] = Field(default=(), max_length=300)

    @model_validator(mode="after")
    def _exact_dimensions(self) -> "VisualScorecard":
        names = tuple(item.dimension for item in self.dimensions)
        if names != VISUAL_DIMENSIONS:
            raise ValueError(
                "Scorecard must contain the exact 14 dimensions in policy order"
            )
        return self


class ReviewerDisagreement(StrictDesignModel):
    disagreement_id: Identifier
    dimension: VisualDimension
    critic_score: StrictInt = Field(ge=0, le=100)
    reviewer_score: StrictInt = Field(ge=0, le=100)
    evidence_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=20, max_length=4000)


class BaselineDimensionComparison(StrictDesignModel):
    dimension: Literal[
        "clarity",
        "business_specificity",
        "visual_quality",
        "trust",
        "conversion_strength",
        "mobile_quality",
    ]
    preferred: Literal["a", "b", "equal", "inconclusive"]
    confidence: StrictFloat = Field(ge=0, le=1)
    evidence_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=20, max_length=4000)


class VisualReviewerDecision(StrictDesignModel):
    schema_version: str = Field(
        default=VISUAL_EVALUATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    subject: EvaluationSubject
    recommendation: Literal["accept", "reject"]
    confidence: StrictFloat = Field(ge=0, le=1)
    dimensions: Tuple[VisualDimensionAssessment, ...] = Field(
        min_length=14,
        max_length=14,
    )
    disagreements: Tuple[ReviewerDisagreement, ...] = Field(
        default=(),
        max_length=100,
    )
    blocking_findings: Tuple[VisualFinding, ...] = Field(
        default=(),
        max_length=100,
    )
    score_band_concerns: Tuple[str, ...] = Field(default=(), max_length=100)
    comparative_result: Literal[
        "not_applicable",
        "a_preferred",
        "b_preferred",
        "inconclusive",
    ] = "not_applicable"
    comparative_dimensions: Tuple[BaselineDimensionComparison, ...] = Field(
        default=(),
        max_length=6,
    )

    @model_validator(mode="after")
    def _exact_dimensions(self) -> "VisualReviewerDecision":
        if tuple(item.dimension for item in self.dimensions) != VISUAL_DIMENSIONS:
            raise ValueError("Reviewer must score the exact 14 dimensions")
        if self.recommendation == "accept" and self.blocking_findings:
            raise ValueError("An accepting reviewer cannot report blockers")
        if (
            self.comparative_result == "not_applicable"
            and self.comparative_dimensions
        ):
            raise ValueError("Absolute review cannot claim A/B comparison")
        if (
            self.comparative_result != "not_applicable"
            and len(self.comparative_dimensions) != 6
        ):
            raise ValueError("Blind review must compare all six dimensions")
        return self


class ScoreBandPolicy(StrictDesignModel):
    revision: str = Field(
        default=VISUAL_SCORE_BAND_POLICY_REVISION,
        pattern=r"^2026-07-24\.1$",
    )
    exceptional_min: Literal[90] = 90
    strong_min: Literal[80] = 80
    usable_min: Literal[70] = 70
    weak_min: Literal[50] = 50


class VisualAcceptancePolicy(StrictDesignModel):
    revision: str = Field(
        default=VISUAL_ACCEPTANCE_POLICY_REVISION,
        pattern=r"^2026-07-24\.1$",
    )
    weighted_overall_min: StrictInt = Field(default=80, ge=0, le=100)
    business_specificity_min: StrictInt = Field(default=80, ge=0, le=100)
    design_dna_adherence_min: StrictInt = Field(default=80, ge=0, le=100)
    conversion_strength_min: StrictInt = Field(default=75, ge=0, le=100)
    mobile_quality_min: StrictInt = Field(default=75, ge=0, le=100)
    trust_and_professionalism_min: StrictInt = Field(
        default=80,
        ge=0,
        le=100,
    )
    max_blocking_findings: Literal[0] = 0
    reviewer_recommendation: Literal["accept"] = "accept"
    critic_reviewer_agreement_required: Literal[True] = True


class VisualAcceptanceComputation(StrictDesignModel):
    weighted_overall: StrictFloat = Field(ge=0, le=100)
    critic_weighted_overall: StrictFloat = Field(ge=0, le=100)
    reviewer_weighted_overall: StrictFloat = Field(ge=0, le=100)
    dimension_scores: Tuple[Tuple[VisualDimension, StrictFloat], ...] = Field(
        min_length=14,
        max_length=14,
    )
    blocking_finding_count: StrictInt = Field(ge=0)
    critic_accepts: StrictBool
    reviewer_accepts: StrictBool
    agreement: StrictBool
    threshold_checks: Tuple[Tuple[str, StrictBool], ...] = Field(
        min_length=8,
        max_length=20,
    )
    accepted: StrictBool


class CandidateBaselineComparison(StrictDesignModel):
    schema_version: str = Field(
        default=VISUAL_EVALUATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    mode: ComparisonMode
    reason: str = Field(min_length=1, max_length=2000)
    attempt_hash: Sha256
    label_a_identity_sha256: Sha256 | None = None
    label_b_identity_sha256: Sha256 | None = None
    dimensions: Tuple[BaselineDimensionComparison, ...] = Field(
        default=(),
        max_length=6,
    )

    @model_validator(mode="after")
    def _mode_is_consistent(self) -> "CandidateBaselineComparison":
        if self.mode == "absolute_only":
            if self.label_a_identity_sha256 or self.label_b_identity_sha256:
                raise ValueError("Absolute evaluation cannot identify A/B")
            if self.dimensions:
                raise ValueError("Absolute evaluation cannot claim comparison")
        elif (
            not self.label_a_identity_sha256
            or not self.label_b_identity_sha256
            or len(self.dimensions) != 6
        ):
            raise ValueError("Blind comparison is incomplete")
        return self


class RefinementPlanItem(StrictDesignModel):
    finding_id: Identifier
    page_id: Identifier
    routes: Tuple[str, ...] = Field(min_length=1, max_length=20)
    component_ids: Tuple[Identifier, ...] = Field(default=(), max_length=200)
    allowed_files: Tuple[str, ...] = Field(min_length=1, max_length=8)
    original_hashes: Tuple[Tuple[str, Sha256], ...] = Field(
        min_length=1,
        max_length=8,
    )
    issue_type: str = Field(min_length=1, max_length=96)
    objective: str = Field(min_length=10, max_length=2000)
    evidence_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=300)
    immutable_constraints: Tuple[str, ...] = Field(min_length=1, max_length=100)
    validation_requirements: Tuple[str, ...] = Field(
        min_length=1,
        max_length=100,
    )
    priority: StrictInt = Field(ge=1, le=100)
    expected_dimension_impact: Tuple[VisualDimension, ...] = Field(
        min_length=1,
        max_length=14,
    )

    @model_validator(mode="after")
    def _file_hashes_match(self) -> "RefinementPlanItem":
        if tuple(self.allowed_files) != tuple(
            path for path, _digest in self.original_hashes
        ):
            raise ValueError("Allowed files and original hashes must align")
        return self


class RefinementPlan(StrictDesignModel):
    schema_version: str = Field(
        default=VISUAL_EVALUATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    refs: VisualEvaluationRefs
    policy_revision: str = Field(
        default=VISUAL_REFINEMENT_POLICY_REVISION,
        pattern=r"^2026-07-24\.1$",
    )
    cache_key: Sha256
    repairability: Literal["rejected_repairable"]
    items: Tuple[RefinementPlanItem, ...] = Field(min_length=1, max_length=100)
    allowed_files: Tuple[str, ...] = Field(min_length=1, max_length=8)
    affected_page_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=4,
    )


class RefinedSourceFile(StrictDesignModel):
    path: str = Field(
        min_length=1,
        max_length=240,
        pattern=r"^src/(?:pages|components/business)/[A-Za-z0-9_./-]+\.tsx$",
    )
    original_sha256: Sha256
    source: str = Field(min_length=1, max_length=500_000)


class RefinementOutput(StrictDesignModel):
    schema_version: str = Field(
        default=VISUAL_EVALUATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    files: Tuple[RefinedSourceFile, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _unique_paths(self) -> "RefinementOutput":
        paths = tuple(item.path for item in self.files)
        if len(paths) != len(set(paths)):
            raise ValueError("Refinement output cannot repeat files")
        return self


class VisualCallMetrics(StrictDesignModel):
    stage: Literal[
        "critic",
        "reviewer",
        "refinement",
        "technical_repair",
    ]
    group_index: StrictInt | None = Field(default=None, ge=0, le=99)
    model: str = Field(min_length=1, max_length=240)
    provider: str = Field(min_length=1, max_length=80)
    family: str = Field(min_length=1, max_length=80)
    capability: str = Field(min_length=1, max_length=80)
    prompt_revision: str = Field(min_length=1, max_length=64)
    temperature: StrictFloat = Field(ge=0, le=1)
    max_tokens: StrictInt = Field(ge=1, le=42_000)
    cache_hit: StrictBool
    provider_call_count: StrictInt = Field(ge=0, le=1)
    transport_retry_count: StrictInt = Field(ge=0)
    prompt_tokens: StrictInt = Field(ge=0)
    completion_tokens: StrictInt = Field(ge=0)
    total_tokens: StrictInt = Field(ge=0)
    cost_usd: StrictFloat = Field(ge=0)
    latency_ms: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def _accounting(self) -> "VisualCallMetrics":
        if self.total_tokens < self.prompt_tokens + self.completion_tokens:
            raise ValueError("Visual call token totals are inconsistent")
        if self.cache_hit and (
            self.provider_call_count
            or self.total_tokens
            or self.cost_usd
            or self.transport_retry_count
        ):
            raise ValueError("Visual cache hit cannot consume provider budget")
        if not self.cache_hit and self.provider_call_count != 1:
            raise ValueError("A visual invocation must count exactly one call")
        return self


class RefinementGeneration(StrictDesignModel):
    schema_version: str = Field(
        default=VISUAL_EVALUATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    original_candidate_revision_id: StrictInt = Field(ge=1)
    derived_candidate_revision_id: StrictInt = Field(ge=1)
    refinement_plan_sha256: Sha256
    output_sha256: Sha256
    allowed_file_hashes_before: Tuple[Tuple[str, Sha256], ...] = Field(
        min_length=1,
        max_length=8,
    )
    allowed_file_hashes_after: Tuple[Tuple[str, Sha256], ...] = Field(
        min_length=1,
        max_length=8,
    )
    unaffected_manifest_sha256_before: Sha256
    unaffected_manifest_sha256_after: Sha256
    phase3b_static_gate_sha256: Sha256
    phase3b_static_gate_passed: StrictBool
    phase4_summary_id: StrictInt = Field(ge=1)
    phase4_summary_sha256: Sha256
    technical_repair_count: StrictInt = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _unaffected_files_are_immutable(self) -> "RefinementGeneration":
        if (
            self.unaffected_manifest_sha256_before
            != self.unaffected_manifest_sha256_after
        ):
            raise ValueError("Refinement modified an unaffected file")
        return self


class VisualEvaluationSummary(StrictDesignModel):
    schema_version: str = Field(
        default=VISUAL_EVALUATION_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    refs: VisualEvaluationRefs
    attempt_uuid: str = Field(min_length=36, max_length=36)
    subject: EvaluationSubject
    status: VisualTerminalStatus
    repairability: Repairability
    evidence_bundle_sha256: Sha256
    hard_gate_sha256: Sha256
    critic_scorecard_sha256: Sha256 | None = None
    reviewer_decision_sha256: Sha256 | None = None
    baseline_comparison_sha256: Sha256
    acceptance_computation: VisualAcceptanceComputation | None = None
    refinement_plan_sha256: Sha256 | None = None
    refinement_generation_sha256: Sha256 | None = None
    original_summary_sha256: Sha256 | None = None
    call_metrics: Tuple[VisualCallMetrics, ...] = Field(default=(), max_length=6)
    provider_call_count: StrictInt = Field(ge=0, le=6)
    prompt_tokens: StrictInt = Field(ge=0)
    # Output-token ceiling is on completion_tokens; multimodal prompt input
    # regularly exceeds 42k aggregate total tokens.
    completion_tokens: StrictInt = Field(ge=0, le=42_000)
    total_tokens: StrictInt = Field(ge=0)
    cost_usd: StrictFloat = Field(ge=0, le=1.50)
    latency_ms: StrictInt = Field(ge=0)
    cache_hits: Tuple[str, ...] = Field(default=(), max_length=20)
    diagnostics: Tuple[str, ...] = Field(default=(), max_length=300)

    @model_validator(mode="after")
    def _summary_is_consistent(self) -> "VisualEvaluationSummary":
        if self.provider_call_count != sum(
            item.provider_call_count for item in self.call_metrics
        ):
            raise ValueError("Summary call accounting is inconsistent")
        if self.total_tokens < self.prompt_tokens + self.completion_tokens:
            raise ValueError("Summary token accounting is inconsistent")
        if self.status == "candidate_visual_accepted":
            if (
                self.repairability != "accepted"
                or self.acceptance_computation is None
                or not self.acceptance_computation.accepted
                or self.critic_scorecard_sha256 is None
                or self.reviewer_decision_sha256 is None
                or self.diagnostics
            ):
                raise ValueError("Accepted visual summary is incomplete")
        if self.hard_gate_sha256 and self.repairability == "accepted":
            if self.critic_scorecard_sha256 is None:
                raise ValueError("Accepted result requires a critic scorecard")
        return self


__all__ = [
    "CandidateBaselineComparison",
    "EvaluationSubject",
    "ImageBundleGroup",
    "ModelCapabilityResolution",
    "RefinedSourceFile",
    "RefinementGeneration",
    "RefinementOutput",
    "RefinementPlan",
    "RefinementPlanItem",
    "Repairability",
    "ScoreBandPolicy",
    "ScreenshotVisualEvidence",
    "VISUAL_ACCEPTANCE_POLICY_REVISION",
    "VISUAL_DIMENSIONS",
    "VISUAL_EVALUATION_POLICY_REVISION",
    "VISUAL_EVALUATION_SCHEMA_VERSION",
    "VisualAcceptanceComputation",
    "VisualAcceptancePolicy",
    "VisualCallMetrics",
    "VisualDimension",
    "VisualDimensionAssessment",
    "VisualEvaluationLimits",
    "VisualEvaluationRefs",
    "VisualEvaluationSummary",
    "VisualEvidenceBundle",
    "VisualFinding",
    "VisualHardGateFinding",
    "VisualHardGateReport",
    "VisualReviewerDecision",
    "VisualScorecard",
    "VisualStageRouting",
    "VisualTerminalStatus",
]
