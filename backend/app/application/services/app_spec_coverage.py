"""Independent semantic coverage review for canonical AppSpecs."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.application.prompts import PromptTemplate
from app.application.services.app_spec_validation import canonical_app_spec_json
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.schemas.app_spec import AppSpec
from app.shared.json_utils import extract_json_from_text


CoverageSeverity = Literal["blocking", "major", "minor"]


class CoverageFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: CoverageSeverity
    source_path: str = ""
    source_excerpt: str = ""
    app_spec_ids: list[str] = Field(default_factory=list)
    message: str
    repair_instruction: str = ""


class GoalCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str
    source_excerpt: str
    covered: bool
    requirement_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    acceptance_test_ids: list[str] = Field(default_factory=list)
    notes: str = ""


class AppSpecCoverageReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["pass", "repair"]
    score: int = Field(ge=0, le=100)
    summary: str
    goal_coverage: list[GoalCoverage] = Field(default_factory=list)
    omissions: list[CoverageFinding] = Field(default_factory=list)
    contradictions: list[CoverageFinding] = Field(default_factory=list)
    unsupported_additions: list[CoverageFinding] = Field(default_factory=list)
    mislabeled_assumptions: list[CoverageFinding] = Field(default_factory=list)
    open_question_gaps: list[CoverageFinding] = Field(default_factory=list)


class AppSpecCoverageError(RuntimeError):
    """The independent reviewer failed to return a usable review."""


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
    raw = ai_provider.ask_chat(
        model or settings.APPSPEC_COVERAGE_MODEL,
        [{"role": "user", "content": prompt}],
        max_tokens=max_tokens or settings.APPSPEC_COVERAGE_MAX_TOKENS,
        temperature=0.0,
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
    if any(
        not item.covered
        or not item.source_path.strip()
        or not item.source_excerpt.strip()
        or not item.requirement_ids
        or not item.evidence_ids
        or not item.acceptance_test_ids
        for item in review.goal_coverage
    ):
        return True
    if app_spec is not None:
        requirement_ids = {item.id for item in app_spec.requirements}
        evidence_ids = {item.id for item in app_spec.evidence}
        test_ids = {item.id for item in app_spec.acceptance_tests}
        covered_requirement_ids: set[str] = set()
        for item in review.goal_coverage:
            if not set(item.requirement_ids).issubset(requirement_ids):
                return True
            if not set(item.evidence_ids).issubset(evidence_ids):
                return True
            if not set(item.acceptance_test_ids).issubset(test_ids):
                return True
            covered_requirement_ids.update(item.requirement_ids)
        # Every confirmed requirement must appear in the independent proof
        # ledger, not only the subset the reviewer happened to mention.
        if not requirement_ids.issubset(covered_requirement_ids):
            return True
    if source_snapshot is not None:
        for item in review.goal_coverage:
            current: Any = dict(source_snapshot)
            for segment in item.source_path.split("."):
                if not isinstance(current, Mapping) or segment not in current:
                    return True
                current = current[segment]
            if current is None:
                return True
            source_text = (
                current
                if isinstance(current, str)
                else json.dumps(current, ensure_ascii=False, sort_keys=True)
            )
            if item.source_excerpt.casefold() not in source_text.casefold():
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
    "AppSpecCoverageReview",
    "CoverageFinding",
    "GoalCoverage",
    "coverage_requires_repair",
    "review_app_spec_coverage",
]
