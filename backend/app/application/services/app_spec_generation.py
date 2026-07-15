"""End-to-end AppSpec generation, validation, coverage review, and persistence."""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.application.pipelines._shared import get_request
from app.application.services.app_spec_builder import (
    AppSpecBuildError,
    AppSpecCandidate,
    build_app_spec_candidate,
    parse_app_spec_candidate,
    repair_app_spec_candidate,
)
from app.application.services.app_spec_coverage import (
    AppSpecCoverageError,
    AppSpecCoverageReview,
    coverage_requires_repair,
    review_app_spec_coverage,
)
from app.application.services.app_spec_repository import (
    AppSpecRepository,
    load_json_object,
)
from app.application.services.app_spec_source import (
    capture_derived_context,
    capture_request_source,
    source_sha256 as calculate_source_sha256,
)
from app.application.services.app_spec_validation import (
    ValidationReport,
    validate_app_spec,
)
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models.app_spec import (
    APP_SPEC_STATUS_ACCEPTED,
    APP_SPEC_STATUS_REJECTED,
    AppSpecRevision,
)
from app.domain.schemas.app_spec import AppSpec


AppSpecMode = Literal["off", "shadow", "required_new", "required"]


class AppSpecGenerationError(RuntimeError):
    """No deterministic- and semantic-approved AppSpec could be produced."""

    def __init__(
        self,
        message: str,
        *,
        revision_record: AppSpecRevision | None = None,
    ) -> None:
        super().__init__(message)
        self.revision_record = revision_record


class AppSpecCallBudgetExceeded(AppSpecGenerationError):
    """The isolated AppSpec-stage model-call ceiling was exhausted."""


@dataclass(frozen=True)
class AppSpecGenerationResult:
    spec: AppSpec
    revision_record: AppSpecRevision
    validation_report: ValidationReport
    coverage_review: AppSpecCoverageReview | None
    source_sha256: str
    reused: bool
    calls_used: int
    repair_attempts: int


class _StageLimitedAIProvider:
    """Small per-stage ceiling layered over the request-wide provider budget."""

    def __init__(self, provider: AIProvider, max_calls: int) -> None:
        # Direct preview generation enters the preview-wide budget decorator
        # before it reaches this service. AppSpec has its own reserved ceiling,
        # so unwrap that specific budget lease instead of making contract calls
        # compete with page generation/critique calls.
        if (
            type(provider).__name__ == "BudgetedAIProvider"
            and hasattr(provider, "provider")
            and hasattr(provider, "budget")
        ):
            provider = provider.provider  # type: ignore[assignment, attr-defined]
        self.provider = provider
        self.max_calls = max(1, int(max_calls))
        self.calls_used = 0
        self._lock = threading.Lock()

    def _acquire(self) -> None:
        with self._lock:
            if self.calls_used >= self.max_calls:
                raise AppSpecCallBudgetExceeded(
                    f"AppSpec AI call budget exhausted ({self.calls_used}/{self.max_calls})."
                )
            self.calls_used += 1

    def ask_chat(self, model: str, messages: list[dict], **kwargs: Any) -> str:
        self._acquire()
        return self.provider.ask_chat(model, messages, **kwargs)

    def ask_vision(self, model: str, prompt: str, image_path: str) -> str:
        self._acquire()
        return self.provider.ask_vision(model, prompt, image_path)

    def is_available(self) -> bool:
        checker = getattr(self.provider, "is_available", None)
        return bool(checker()) if callable(checker) else True

    @property
    def name(self) -> str:
        return str(getattr(self.provider, "name", type(self.provider).__name__))


def app_spec_mode() -> AppSpecMode:
    """Return the normalized rollout mode selected in Settings."""

    mode = str(settings.APPSPEC_MODE).strip().lower()
    return mode if mode in {"off", "shadow", "required_new", "required"} else "off"  # type: ignore[return-value]


def app_spec_should_run(*, mode: str | None = None) -> bool:
    """Whether callers should invoke generation (shadow and required modes run)."""

    selected = (mode or app_spec_mode()).strip().lower()
    return selected in {"shadow", "required_new", "required"}


def app_spec_is_required(*, is_new_request: bool, mode: str | None = None) -> bool:
    """Resolve rollout policy without coupling it to an HTTP/orchestration layer."""

    selected = (mode or app_spec_mode()).strip().lower()
    return selected == "required" or (selected == "required_new" and is_new_request)


def app_spec_should_run_for_request(
    *, is_new_request: bool, mode: str | None = None
) -> bool:
    """Apply rollout policy to one concrete request.

    ``required_new`` deliberately leaves legacy previews untouched; shadow and
    required modes run for both new and existing requests.
    """

    selected = (mode or app_spec_mode()).strip().lower()
    if selected == "required_new":
        return is_new_request
    return selected in {"shadow", "required"}


def _validation_payload(
    report: ValidationReport | None,
    *,
    extra_issues: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if report is None:
        payload: dict[str, Any] = {"is_valid": False, "issues": []}
    else:
        payload = report.model_dump(mode="json")
        payload.setdefault("is_valid", bool(getattr(report, "is_valid", False)))
        payload.setdefault("issues", [])
    payload["issues"] = list(payload.get("issues") or []) + list(extra_issues or [])
    payload["passed"] = bool(payload.get("is_valid")) and not extra_issues
    return payload


def _coverage_payload(
    review: AppSpecCoverageReview | None,
    *,
    app_spec: AppSpec | None = None,
    source_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if review is None:
        return {"passed": False, "score": None, "verdict": "unavailable"}
    payload = review.model_dump(mode="json")
    payload["passed"] = not coverage_requires_repair(
        review,
        app_spec=app_spec,
        source_snapshot=source_snapshot,
    )
    return payload


def _candidate_payload(candidate: AppSpecCandidate | None) -> dict[str, Any]:
    return dict(candidate.payload) if candidate else {}


def _parse_validation_issue(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ValidationError):
        detail: Any = exc.errors(include_url=False)
    else:
        detail = str(exc)
    return {
        "severity": "blocking",
        "code": "app_spec_schema_parse_failed",
        "message": "Candidate did not validate against the AppSpec schema.",
        "path": "",
        "related_ids": [],
        "detail": detail,
    }


def _schema_version_issue(spec: AppSpec) -> dict[str, Any] | None:
    actual = str(getattr(spec, "schema_version", ""))
    if actual == settings.APPSPEC_SCHEMA_VERSION:
        return None
    return {
        "severity": "blocking",
        "code": "app_spec_schema_version_mismatch",
        "message": (
            f"Expected schema_version {settings.APPSPEC_SCHEMA_VERSION!r}, "
            f"received {actual!r}."
        ),
        "path": "schema_version",
        "related_ids": [],
    }


def _source_reference_issues(
    spec: AppSpec,
    source_snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    """Require every claimed requirement source path to resolve to real input."""

    issues: list[dict[str, Any]] = []
    for requirement_index, requirement in enumerate(spec.requirements):
        seen: set[str] = set()
        for ref_index, source_ref in enumerate(requirement.source_refs):
            folded = source_ref.casefold()
            path = f"requirements.{requirement_index}.source_refs.{ref_index}"
            if folded in seen:
                issues.append(
                    {
                        "severity": "blocking",
                        "code": "duplicate_requirement_source_ref",
                        "message": f"Requirement {requirement.id!r} repeats source ref {source_ref!r}.",
                        "path": path,
                        "related_ids": [requirement.id],
                    }
                )
                continue
            seen.add(folded)
            current: Any = source_snapshot
            for segment in source_ref.split("."):
                if not isinstance(current, dict) or segment not in current:
                    current = None
                    break
                current = current[segment]
            if current is None or current == "" or current == [] or current == {}:
                issues.append(
                    {
                        "severity": "blocking",
                        "code": "unresolved_requirement_source_ref",
                        "message": (
                            f"Requirement {requirement.id!r} cites {source_ref!r}, "
                            "but that path has no authoritative source value."
                        ),
                        "path": path,
                        "related_ids": [requirement.id],
                    }
                )
    return issues


def _load_persisted_review(row: AppSpecRevision) -> AppSpecCoverageReview | None:
    payload = load_json_object(row.semantic_coverage_json)
    if not payload:
        return None
    try:
        return AppSpecCoverageReview.model_validate(payload)
    except Exception:
        return None


def _generation_metadata(
    *,
    calls_used: int,
    repair_attempts: int,
    terminal_reason: str,
) -> dict[str, Any]:
    return {
        "prompt_revision": settings.APPSPEC_PROMPT_REVISION,
        "schema_version": settings.APPSPEC_SCHEMA_VERSION,
        "author_model": settings.APPSPEC_MODEL,
        "repair_model": settings.APPSPEC_REPAIR_MODEL,
        "coverage_model": settings.APPSPEC_COVERAGE_MODEL,
        "max_calls": settings.APPSPEC_MAX_CALLS,
        "calls_used": calls_used,
        "max_repair_attempts": settings.APPSPEC_MAX_REPAIR_ATTEMPTS,
        "repair_attempts": repair_attempts,
        "terminal_reason": terminal_reason,
    }


def _persist_rejected(
    *,
    repository: AppSpecRepository,
    request_id: int,
    source_snapshot: dict[str, Any],
    candidate: AppSpecCandidate | None,
    validation_payload: dict[str, Any],
    coverage_payload: dict[str, Any],
    parent_revision_id: int | None,
    calls_used: int,
    repair_attempts: int,
    terminal_reason: str,
) -> AppSpecRevision | None:
    try:
        return repository.save_attempt(
            request_id=request_id,
            source_snapshot=source_snapshot,
            app_spec=_candidate_payload(candidate),
            schema_version=settings.APPSPEC_SCHEMA_VERSION,
            deterministic_validation=validation_payload,
            semantic_coverage=coverage_payload,
            generation_metadata=_generation_metadata(
                calls_used=calls_used,
                repair_attempts=repair_attempts,
                terminal_reason=terminal_reason,
            ),
            status=APP_SPEC_STATUS_REJECTED,
            validation_passed=False,
            coverage_passed=False,
            coverage_score=coverage_payload.get("score"),
            parent_revision_id=parent_revision_id,
        )
    except Exception:
        # Preserve the generation failure as the primary error. Persistence
        # failures are surfaced independently by repository/integration tests.
        return None


def ensure_approved_app_spec(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    *,
    force_new_revision: bool = False,
) -> AppSpecGenerationResult:
    """Return a reusable accepted AppSpec or generate one and fail closed.

    The immutable customer snapshot is the only input to its content hash and the
    independent coverage reviewer. Blueprint/preview prose is passed separately as
    non-authoritative derived context to the author/repair stages only.
    """

    req = get_request(db, request_id)
    source_snapshot = capture_request_source(req)
    derived_context = capture_derived_context(req)
    source_digest = calculate_source_sha256(source_snapshot)
    repository = AppSpecRepository(db)

    if not force_new_revision:
        existing = repository.latest_accepted(
            request_id,
            source_sha256=source_digest,
            schema_version=settings.APPSPEC_SCHEMA_VERSION,
        )
        if existing:
            try:
                spec = AppSpec.model_validate(load_json_object(existing.app_spec_json))
                validation = validate_app_spec(spec)
                if validation.is_valid:
                    return AppSpecGenerationResult(
                        spec=spec,
                        revision_record=existing,
                        validation_report=validation,
                        coverage_review=_load_persisted_review(existing),
                        source_sha256=source_digest,
                        reused=True,
                        calls_used=0,
                        repair_attempts=0,
                    )
            except Exception:
                # A corrupt or no-longer-valid persisted artifact is never reused.
                pass

    parent = repository.latest_accepted(request_id)
    parent_revision_id = parent.id if parent else None
    provider = _StageLimitedAIProvider(ai_provider, settings.APPSPEC_MAX_CALLS)
    candidate: AppSpecCandidate | None = None
    spec: AppSpec | None = None
    validation: ValidationReport | None = None
    validation_payload: dict[str, Any] = _validation_payload(None)
    coverage: AppSpecCoverageReview | None = None
    coverage_payload = _coverage_payload(None)
    repairs = 0

    try:
        try:
            candidate = build_app_spec_candidate(
                source_snapshot=source_snapshot,
                derived_context=derived_context,
                ai_provider=provider,
                template_renderer=template_renderer,
            )
        except AppSpecBuildError as exc:
            validation_payload = _validation_payload(
                None,
                extra_issues=[
                    {
                        "severity": "blocking",
                        "code": "app_spec_authoring_output_invalid",
                        "message": str(exc),
                        "path": "",
                        "related_ids": [],
                    }
                ],
            )

        while True:
            parse_issue: dict[str, Any] | None = None
            if candidate is not None:
                try:
                    spec = parse_app_spec_candidate(candidate)
                except Exception as exc:
                    spec = None
                    parse_issue = _parse_validation_issue(exc)

            if spec is not None:
                validation = validate_app_spec(spec)
                version_issue = _schema_version_issue(spec)
                source_issues = _source_reference_issues(spec, source_snapshot)
                validation_payload = _validation_payload(
                    validation,
                    extra_issues=(
                        ([version_issue] if version_issue else []) + source_issues
                    ),
                )
            elif parse_issue:
                validation_payload = _validation_payload(
                    None,
                    extra_issues=[parse_issue],
                )

            if not validation_payload.get("passed"):
                if repairs >= settings.APPSPEC_MAX_REPAIR_ATTEMPTS:
                    reason = "deterministic_validation_failed"
                    rejected = _persist_rejected(
                        repository=repository,
                        request_id=request_id,
                        source_snapshot=source_snapshot,
                        candidate=candidate,
                        validation_payload=validation_payload,
                        coverage_payload=coverage_payload,
                        parent_revision_id=parent_revision_id,
                        calls_used=provider.calls_used,
                        repair_attempts=repairs,
                        terminal_reason=reason,
                    )
                    raise AppSpecGenerationError(
                        "AppSpec failed schema or deterministic validation after repair.",
                        revision_record=rejected,
                    )
                repairs += 1
                candidate = repair_app_spec_candidate(
                    source_snapshot=source_snapshot,
                    derived_context=derived_context,
                    candidate=candidate,
                    deterministic_report=validation_payload,
                    coverage_review=coverage_payload,
                    ai_provider=provider,
                    template_renderer=template_renderer,
                )
                spec = None
                validation = None
                continue

            assert spec is not None and validation is not None
            try:
                coverage = review_app_spec_coverage(
                    source_snapshot=source_snapshot,
                    app_spec=spec,
                    ai_provider=provider,
                    template_renderer=template_renderer,
                )
            except AppSpecCoverageError:
                # Retry one malformed independent review without changing a valid
                # contract. A second malformed result fails closed below.
                coverage = review_app_spec_coverage(
                    source_snapshot=source_snapshot,
                    app_spec=spec,
                    ai_provider=provider,
                    template_renderer=template_renderer,
                )
            coverage_payload = _coverage_payload(
                coverage,
                app_spec=spec,
                source_snapshot=source_snapshot,
            )
            if coverage_payload.get("passed"):
                row = repository.save_attempt(
                    request_id=request_id,
                    source_snapshot=source_snapshot,
                    app_spec=spec,
                    schema_version=settings.APPSPEC_SCHEMA_VERSION,
                    deterministic_validation=validation_payload,
                    semantic_coverage=coverage_payload,
                    generation_metadata=_generation_metadata(
                        calls_used=provider.calls_used,
                        repair_attempts=repairs,
                        terminal_reason="accepted",
                    ),
                    status=APP_SPEC_STATUS_ACCEPTED,
                    validation_passed=True,
                    coverage_passed=True,
                    coverage_score=coverage.score,
                    parent_revision_id=parent_revision_id,
                )
                return AppSpecGenerationResult(
                    spec=spec,
                    revision_record=row,
                    validation_report=validation,
                    coverage_review=coverage,
                    source_sha256=source_digest,
                    reused=False,
                    calls_used=provider.calls_used,
                    repair_attempts=repairs,
                )

            if repairs >= settings.APPSPEC_MAX_REPAIR_ATTEMPTS:
                reason = "semantic_coverage_failed"
                rejected = _persist_rejected(
                    repository=repository,
                    request_id=request_id,
                    source_snapshot=source_snapshot,
                    candidate=candidate,
                    validation_payload=validation_payload,
                    coverage_payload=coverage_payload,
                    parent_revision_id=parent_revision_id,
                    calls_used=provider.calls_used,
                    repair_attempts=repairs,
                    terminal_reason=reason,
                )
                raise AppSpecGenerationError(
                    "AppSpec did not preserve complete customer-goal coverage after repair.",
                    revision_record=rejected,
                )

            repairs += 1
            candidate = repair_app_spec_candidate(
                source_snapshot=source_snapshot,
                derived_context=derived_context,
                candidate=spec,
                deterministic_report=validation_payload,
                coverage_review=coverage_payload,
                ai_provider=provider,
                template_renderer=template_renderer,
            )
            spec = None
            validation = None
            coverage = None
            coverage_payload = _coverage_payload(None)

    except AppSpecCallBudgetExceeded as exc:
        rejected = _persist_rejected(
            repository=repository,
            request_id=request_id,
            source_snapshot=source_snapshot,
            candidate=candidate,
            validation_payload=validation_payload,
            coverage_payload=coverage_payload,
            parent_revision_id=parent_revision_id,
            calls_used=provider.calls_used,
            repair_attempts=repairs,
            terminal_reason="call_budget_exhausted",
        )
        raise AppSpecCallBudgetExceeded(
            str(exc),
            revision_record=rejected,
        ) from exc
    except AppSpecGenerationError:
        raise
    except Exception as exc:
        rejected = _persist_rejected(
            repository=repository,
            request_id=request_id,
            source_snapshot=source_snapshot,
            candidate=candidate,
            validation_payload=validation_payload,
            coverage_payload=coverage_payload,
            parent_revision_id=parent_revision_id,
            calls_used=provider.calls_used,
            repair_attempts=repairs,
            terminal_reason=type(exc).__name__,
        )
        raise AppSpecGenerationError(
            f"AppSpec generation failed closed: {exc}",
            revision_record=rejected,
        ) from exc


__all__ = [
    "AppSpecCallBudgetExceeded",
    "AppSpecGenerationError",
    "AppSpecGenerationResult",
    "app_spec_is_required",
    "app_spec_mode",
    "app_spec_should_run",
    "app_spec_should_run_for_request",
    "ensure_approved_app_spec",
]
