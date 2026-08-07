"""Independent semantic coverage review for canonical AppSpecs."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.application.prompts import PromptTemplate
from app.application.services.ai_context import ai_call
from app.infrastructure.ai_providers.response_parser import ProviderGenerationError
from app.domain.appspec.validation import canonical_app_spec_json
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.schemas.app_spec import AppSpec
from app.shared.json_utils import extract_json_from_text


CoverageSeverity = Literal["blocking", "major", "minor"]


class CoverageFinding(BaseModel):
    # ignore: LLMs often invent sibling keys; required fields still validated.
    model_config = ConfigDict(extra="ignore")

    code: str
    severity: CoverageSeverity
    source_path: str = ""
    source_excerpt: str = ""
    app_spec_ids: list[str] = Field(default_factory=list)
    message: str
    repair_instruction: str = ""

    # Run 133: the reviewer sent explicit nulls for these DEFAULTED evidence
    # fields and the whole review failed on cosmetics — twice, byte-identical
    # at temperature 0. A null where the schema default is ""/[] is absence,
    # not substance. Required fields (code/severity/message) stay strict.
    @field_validator("source_path", "source_excerpt", "repair_instruction", mode="before")
    @classmethod
    def _null_str_is_absent(cls, value: Any) -> Any:
        return "" if value is None else value

    @field_validator("app_spec_ids", mode="before")
    @classmethod
    def _null_list_is_absent(cls, value: Any) -> Any:
        return [] if value is None else value


class GoalCoverage(BaseModel):
    # ignore: models invent keys like assumption_ids; do not fail closed on extras.
    model_config = ConfigDict(extra="ignore")

    source_path: str
    source_excerpt: str
    covered: bool
    requirement_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    acceptance_test_ids: list[str] = Field(default_factory=list)
    notes: str = ""

    # source_path/source_excerpt/covered stay strict: they are the proof
    # ledger `coverage_requires_repair` gates on, not optional evidence.
    @field_validator("notes", mode="before")
    @classmethod
    def _null_str_is_absent(cls, value: Any) -> Any:
        return "" if value is None else value

    @field_validator(
        "requirement_ids", "evidence_ids", "acceptance_test_ids", mode="before"
    )
    @classmethod
    def _null_list_is_absent(cls, value: Any) -> Any:
        return [] if value is None else value


class AppSpecCoverageReview(BaseModel):
    model_config = ConfigDict(extra="ignore")

    verdict: Literal["pass", "repair"]
    score: int = Field(ge=0, le=100)
    summary: str
    goal_coverage: list[GoalCoverage] = Field(default_factory=list)
    omissions: list[CoverageFinding] = Field(default_factory=list)
    contradictions: list[CoverageFinding] = Field(default_factory=list)
    unsupported_additions: list[CoverageFinding] = Field(default_factory=list)
    mislabeled_assumptions: list[CoverageFinding] = Field(default_factory=list)
    open_question_gaps: list[CoverageFinding] = Field(default_factory=list)

    # verdict/score/summary stay strict — a review without them is no review.
    @field_validator(
        "goal_coverage",
        "omissions",
        "contradictions",
        "unsupported_additions",
        "mislabeled_assumptions",
        "open_question_gaps",
        mode="before",
    )
    @classmethod
    def _null_list_is_absent(cls, value: Any) -> Any:
        return [] if value is None else value


class AppSpecCoverageError(RuntimeError):
    """The independent reviewer failed to return a usable review."""


class AppSpecCoverageTransportError(AppSpecCoverageError):
    """The review stream never arrived intact — weather, not the reviewer.

    Classification is the R1 boundary: only this class may ever reach the
    cross-provider rung in generation.py. A malformed review (the parent
    class) is a quality failure and never takes a model fallback.
    """


# Run 133: coverage_review returned byte-identical malformed output twice — a
# temperature-0 verbatim re-ask buys nothing on malformation. The one-shot
# retry in generation.py now appends this compact corrective instruction
# (mirroring the authoring loop's malformed retry) so the second ask is a
# different ask, and bumps the telemetry attempt so the rows stay
# distinguishable.
_COVERAGE_RETRY_INSTRUCTION = (
    "Your previous coverage review was rejected: {reason}. "
    "Return one complete JSON object that satisfies the supplied coverage "
    'schema. Use "" or [] instead of null for optional fields. '
    "No prose. No markdown. No code fences."
)


def coverage_retry_instruction(error: Exception) -> str:
    """The corrective second-ask message for one malformed/cut review."""

    return _COVERAGE_RETRY_INSTRUCTION.format(reason=str(error)[:500])


def _canonical_json(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def review_app_spec_coverage(
    *,
    source_snapshot: Mapping[str, Any],
    app_spec: AppSpec,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    model: str | None = None,
    max_tokens: int | None = None,
    minimum_score: int | None = None,
    attempt: int = 1,
    corrective_instruction: str | None = None,
) -> AppSpecCoverageReview:
    """Compare the approved-source candidate directly with immutable intake."""

    threshold = (
        settings.APPSPEC_MIN_COVERAGE_SCORE
        if minimum_score is None
        else min(100, max(0, int(minimum_score)))
    )
    prompt = template_renderer.render(
        PromptTemplate.APP_SPEC_COVERAGE,
        prompt_revision=settings.APPSPEC_PROMPT_REVISION,
        minimum_score=threshold,
        source_snapshot_json=_canonical_json(dict(source_snapshot)),
        app_spec_json=canonical_app_spec_json(app_spec),
        coverage_schema_json=_canonical_json(AppSpecCoverageReview.model_json_schema()),
    )
    # Lazy on purpose: a module-level `coverage -> builder` import closes the
    # long-standing generation/sanitize import cycle and breaks collection.
    from app.application.appspec.builder import _ask_appspec_chat

    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    if corrective_instruction:
        # Never resend the malformed output — one compact corrective message,
        # the same shape as the authoring loop's malformed retry.
        messages.append({"role": "user", "content": corrective_instruction})
    with ai_call("appspec", writer="coverage_review", attempt=attempt):
        try:
            raw, provider_diag = _ask_appspec_chat(
                ai_provider,
                model=model or settings.APPSPEC_COVERAGE_MODEL,
                messages=messages,
                max_tokens=max_tokens or settings.APPSPEC_COVERAGE_MAX_TOKENS,
                temperature=0.0,
            )
        except ProviderGenerationError as exc:
            if not exc.retryable:
                raise
            raise AppSpecCoverageTransportError(
                f"AppSpec coverage review stream failed in transit: {exc}"
            ) from exc
    # A review the provider cut mid-stream must not be adjudicated: the lenient
    # extractor below can recover a fragment that still carries verdict/score —
    # request 118's failure shape, unguarded here until session 20. Raising
    # AppSpecCoverageError hands the cut to generation.py's existing one-shot
    # coverage retry, which is this site's bounded re-ask (one layer, never
    # stacked with an in-function loop).
    if str(provider_diag.get("finish_reason") or "").lower() == "error":
        raise AppSpecCoverageTransportError(
            "AppSpec coverage review stream was cut by a provider error "
            "(finish_reason=error)"
        )
    try:
        payload = extract_json_from_text(raw)
        if not isinstance(payload, dict):
            raise ValueError("coverage response must be one JSON object")
        return AppSpecCoverageReview.model_validate(payload)
    except Exception as exc:
        raise AppSpecCoverageError(
            f"Independent AppSpec coverage review was malformed: {exc}"
        ) from exc


def _resolved_goal_proof(
    item: GoalCoverage,
    app_spec: AppSpec | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    evidence_ids = tuple(item.evidence_ids)
    test_ids = tuple(item.acceptance_test_ids)
    if app_spec is None or (evidence_ids and test_ids):
        return evidence_ids, test_ids
    trace_by_requirement = {link.requirement_id: link for link in app_spec.traceability}
    for requirement_id in item.requirement_ids:
        link = trace_by_requirement.get(requirement_id)
        if link is None:
            continue
        if not evidence_ids:
            evidence_ids = link.evidence_ids
        if not test_ids:
            test_ids = link.acceptance_test_ids
        if evidence_ids and test_ids:
            break
    return evidence_ids, test_ids


def coverage_requires_repair(
    review: AppSpecCoverageReview,
    *,
    minimum_score: int | None = None,
    app_spec: AppSpec | None = None,
    source_snapshot: Mapping[str, Any] | None = None,
) -> bool:
    """Fail closed on omissions, contradictions, or major unsupported claims."""

    threshold = (
        settings.APPSPEC_MIN_COVERAGE_SCORE
        if minimum_score is None
        else min(100, max(0, int(minimum_score)))
    )
    if review.verdict != "pass" or review.score < threshold:
        return True
    # A high self-reported score with an empty proof ledger is not coverage.
    if not review.goal_coverage:
        return True
    if any(not item.source_path.strip() or not item.source_excerpt.strip() for item in review.goal_coverage):
        return True
    if any(not item.covered for item in review.goal_coverage):
        return True
    for item in review.goal_coverage:
        if not item.requirement_ids:
            continue
        evidence_ids, test_ids = _resolved_goal_proof(item, app_spec)
        if not evidence_ids or not test_ids:
            return True
    if app_spec is not None:
        requirement_ids = {item.id for item in app_spec.requirements}
        deferred_requirement_ids = {
            requirement_id
            for item in app_spec.deferred_scope
            for requirement_id in item.requirement_ids
        }
        active_requirement_ids = requirement_ids - deferred_requirement_ids
        evidence_ids = {item.id for item in app_spec.evidence}
        test_ids = {item.id for item in app_spec.acceptance_tests}
        covered_requirement_ids: set[str] = set()
        for item in review.goal_coverage:
            if not set(item.requirement_ids).issubset(requirement_ids):
                return True
            resolved_evidence, resolved_tests = _resolved_goal_proof(item, app_spec)
            if not set(resolved_evidence).issubset(evidence_ids):
                return True
            if not set(resolved_tests).issubset(test_ids):
                return True
            covered_requirement_ids.update(item.requirement_ids)
        # Prefer the independent ledger, but accept AppSpec-native proof chains
        # when the reviewer omits an otherwise fully traced requirement.
        traced_requirement_ids = {
            link.requirement_id
            for link in app_spec.traceability
            if link.capability_ids
            and link.page_ids
            and link.evidence_ids
            and link.acceptance_test_ids
        }
        uncovered = active_requirement_ids - covered_requirement_ids - traced_requirement_ids
        if uncovered:
            return True
    if source_snapshot is not None:
        for item in review.goal_coverage:
            if not item.requirement_ids:
                continue
            current: Any = source_snapshot
            for segment in item.source_path.split("."):
                if isinstance(current, Mapping) and segment in current:
                    current = current[segment]
                    continue
                if isinstance(current, list) and segment.isdigit():
                    index = int(segment)
                    if index < 0 or index >= len(current):
                        return True
                    current = current[index]
                    continue
                return True
            if current is None or current == "" or current == [] or current == {}:
                return True
    for findings in (
        review.omissions,
        review.contradictions,
        review.unsupported_additions,
        review.mislabeled_assumptions,
        review.open_question_gaps,
    ):
        if any(item.severity in {"blocking", "major"} for item in findings):
            return True
    return False


__all__ = [
    "AppSpecCoverageError",
    "AppSpecCoverageTransportError",
    "AppSpecCoverageReview",
    "CoverageFinding",
    "GoalCoverage",
    "coverage_requires_repair",
    "coverage_retry_instruction",
    "review_app_spec_coverage",
]
