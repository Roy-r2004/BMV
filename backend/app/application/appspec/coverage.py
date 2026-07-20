"""Independent semantic coverage review for canonical AppSpecs."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.application.prompts import PromptTemplate
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
    "AppSpecCoverageReview",
    "CoverageFinding",
    "GoalCoverage",
    "coverage_requires_repair",
    "review_app_spec_coverage",
]
