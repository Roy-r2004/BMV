"""End-to-end AppSpec generation, validation, coverage review, and persistence."""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.application.pipelines._shared import get_request
from app.application.appspec.builder import (
    AppSpecBuildError,
    AppSpecCandidate,
    build_app_spec_candidate,
    parse_app_spec_candidate,
    repair_app_spec_candidate,
)
from app.application.appspec.coverage import (
    AppSpecCoverageError,
    AppSpecCoverageReview,
    coverage_requires_repair,
    review_app_spec_coverage,
)
from app.application.appspec.repository import (
    AppSpecRepository,
    load_json_object,
)
from app.application.appspec.policy import (
    AppSpecGenerationPolicy,
    ModelFamilyAssignment,
    resolve_model_assignment,
)
from app.application.appspec.fallback import (
    build_fallback_app_spec,
    build_fallback_coverage_payload,
)
from app.domain.appspec.sanitize import heal_app_spec_payload, sanitize_app_spec_payload
from app.application.appspec.source import (
    capture_derived_context,
    capture_request_source,
    source_sha256 as calculate_source_sha256,
)
from app.application.preview_contract.tiers import (
    TierBuildError,
    select_primary_journey_proof,
)
from app.domain.schemas.product_strategy import ProductStrategy
from app.domain.appspec.validation import (
    ValidationReport,
    validate_app_spec,
)
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.infrastructure.logging import get_logger

log = get_logger("AppSpecGeneration")
from app.domain.models.app_spec import (
    APP_SPEC_STATUS_ACCEPTED,
    APP_SPEC_STATUS_REJECTED,
    AppSpecRevision,
)
from app.domain.schemas.app_spec import AppSpec

AppSpecMode = Literal["off", "on", "shadow"]

# Legacy rollout aliases still mean enforced AppSpec. ``shadow`` authors the
# contract but must not block preview when validation/coverage fails.
_LEGACY_ON_MODES = {"required_new", "required", "true", "1", "yes", "enabled"}

def _normalize_mode(mode: str | None) -> AppSpecMode:
    raw = str(settings.APPSPEC_MODE if mode is None else mode).strip().lower()
    if raw == "shadow":
        return "shadow"
    if raw == "on" or raw in _LEGACY_ON_MODES:
        return "on"
    return "off"

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


@dataclass(frozen=True)
class _ResolvedGenerationPolicy:
    policy: AppSpecGenerationPolicy
    author_model: str
    repair_model: str
    coverage_model: str
    model_families: ModelFamilyAssignment | None
    allow_fallback: bool

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
    """Return the normalized AppSpec toggle (``off``, ``on``, or ``shadow``)."""

    return _normalize_mode(None)

def app_spec_should_run(*, mode: str | None = None) -> bool:
    """Whether callers should invoke AppSpec generation."""

    return _normalize_mode(mode) in {"on", "shadow"}

def app_spec_is_required(*, is_new_request: bool = True, mode: str | None = None) -> bool:
    """True only for enforced AppSpec (``on``). ``shadow`` must not block preview."""

    return _normalize_mode(mode) == "on"

def app_spec_should_run_for_request(
    *, is_new_request: bool = True, mode: str | None = None
) -> bool:
    """Apply the AppSpec toggle to one concrete request."""

    return _normalize_mode(mode) in {"on", "shadow"}

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


def _format_validation_failure(prefix: str, validation_payload: Mapping[str, Any]) -> str:
    """Include a short issue digest so UI/logs show why validation failed closed."""

    issues = list(validation_payload.get("issues") or [])
    if not issues:
        return prefix
    parts: list[str] = []
    for issue in issues[:3]:
        if not isinstance(issue, Mapping):
            continue
        code = str(issue.get("code") or "issue").strip() or "issue"
        message = str(issue.get("message") or "").strip()
        if message:
            parts.append(f"{code}: {message}")
        else:
            parts.append(code)
    if not parts:
        return prefix
    return f"{prefix} ({'; '.join(parts)})"

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

def _sanitize_candidate(
    candidate: AppSpecCandidate | None,
    source_snapshot: dict[str, Any],
) -> AppSpecCandidate | None:
    if candidate is None:
        return None
    sanitized = sanitize_app_spec_payload(candidate.payload, source_snapshot)
    from app.application.services.ai_features import (
        ai_features_from_source,
        bind_ai_features_to_app_spec,
    )

    ai_features = ai_features_from_source(source_snapshot)
    if ai_features:
        sanitized = bind_ai_features_to_app_spec(sanitized, ai_features)
    return AppSpecCandidate(
        payload=sanitized,
        response_excerpt=candidate.response_excerpt,
    )


def _heal_candidate(
    candidate: AppSpecCandidate | None,
    validation_payload: Mapping[str, Any],
    source_snapshot: dict[str, Any],
) -> tuple[AppSpecCandidate | None, list[str]]:
    """Apply code-driven heals, then re-sanitize. Returns (candidate, actions)."""

    if candidate is None:
        return None, []
    healed_payload, actions = heal_app_spec_payload(
        candidate.payload,
        validation_payload,
        source_snapshot,
    )
    if not actions:
        return candidate, []
    healed = AppSpecCandidate(
        payload=healed_payload,
        response_excerpt=candidate.response_excerpt,
    )
    return _sanitize_candidate(healed, source_snapshot), actions

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

def _resolve_source_ref(source_snapshot: dict[str, Any], source_ref: str) -> Any:
    """Walk dotted source paths, including list indices (ai_features.0.description)."""
    current: Any = source_snapshot
    for segment in str(source_ref or "").split("."):
        if segment == "":
            return None
        if isinstance(current, dict):
            if segment not in current:
                return None
            current = current[segment]
            continue
        if isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if index < 0 or index >= len(current):
                return None
            current = current[index]
            continue
        return None
    return current


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
            current = _resolve_source_ref(source_snapshot, source_ref)
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
    deterministic_heals: int = 0,
    heal_actions: list[str] | None = None,
    used_fallback: bool = False,
    complete: bool = False,
    runtime_policy: _ResolvedGenerationPolicy | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt_revision": settings.APPSPEC_PROMPT_REVISION,
        "schema_version": settings.APPSPEC_SCHEMA_VERSION,
        "author_model": (
            runtime_policy.author_model
            if runtime_policy
            else settings.APPSPEC_MODEL
        ),
        "repair_model": (
            runtime_policy.repair_model
            if runtime_policy
            else settings.APPSPEC_REPAIR_MODEL
        ),
        "coverage_model": (
            runtime_policy.coverage_model
            if runtime_policy
            else settings.APPSPEC_COVERAGE_MODEL
        ),
        "max_calls": settings.APPSPEC_MAX_CALLS,
        "calls_used": calls_used,
        "max_repair_attempts": settings.APPSPEC_MAX_REPAIR_ATTEMPTS,
        "repair_attempts": repair_attempts,
        "deterministic_heals": deterministic_heals,
        "heal_actions": list(heal_actions or [])[:40],
        "used_fallback": used_fallback,
        "terminal_reason": terminal_reason,
    }
    if runtime_policy and runtime_policy.policy.name != "legacy_v1":
        payload.update(dict(runtime_policy.policy.metadata))
        payload.update(
            {
                "policy": runtime_policy.policy.name,
                "complete": bool(complete and not used_fallback),
                "coverage_review_kind": "independent_model",
                "model_families": (
                    {
                        "author": runtime_policy.model_families.author,
                        "repair": runtime_policy.model_families.repair,
                        "coverage": runtime_policy.model_families.coverage,
                    }
                    if runtime_policy.model_families
                    else {}
                ),
            }
        )
    return payload

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
    runtime_policy: _ResolvedGenerationPolicy | None = None,
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
                runtime_policy=runtime_policy,
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

def _accept_fallback_app_spec(
    *,
    repository: AppSpecRepository,
    request_id: int,
    source_snapshot: dict[str, Any],
    source_digest: str,
    parent_revision_id: int | None,
    calls_used: int,
    repair_attempts: int,
    deterministic_heals: int,
    heal_actions: list[str],
    prior_candidate: AppSpecCandidate | None,
    prior_validation: dict[str, Any],
    prior_coverage: dict[str, Any],
    reason: str,
    runtime_policy: _ResolvedGenerationPolicy | None = None,
) -> AppSpecGenerationResult:
    """Persist rejected AI attempt (best-effort), then accept a minimal valid spec."""

    _persist_rejected(
        repository=repository,
        request_id=request_id,
        source_snapshot=source_snapshot,
        candidate=prior_candidate,
        validation_payload=prior_validation,
        coverage_payload=prior_coverage,
        parent_revision_id=parent_revision_id,
        calls_used=calls_used,
        repair_attempts=repair_attempts,
        terminal_reason=f"fallback_after_{reason}",
        runtime_policy=runtime_policy,
    )
    spec = build_fallback_app_spec(source_snapshot)
    validation = validate_app_spec(spec)
    if not validation.is_valid:
        raise AppSpecGenerationError(
            "Fallback AppSpec failed deterministic validation unexpectedly.",
        )
    validation_payload = _validation_payload(validation)
    coverage_payload = build_fallback_coverage_payload(spec, source_snapshot)
    log.warning(
        "Accepting fallback AppSpec for request %s after %s (repairs=%s heals=%s)",
        request_id,
        reason,
        repair_attempts,
        deterministic_heals,
    )
    row = repository.save_attempt(
        request_id=request_id,
        source_snapshot=source_snapshot,
        app_spec=spec,
        schema_version=settings.APPSPEC_SCHEMA_VERSION,
        deterministic_validation=validation_payload,
        semantic_coverage=coverage_payload,
        generation_metadata=_generation_metadata(
            calls_used=calls_used,
            repair_attempts=repair_attempts,
            terminal_reason="accepted_fallback",
            deterministic_heals=deterministic_heals,
            heal_actions=heal_actions,
            used_fallback=True,
            runtime_policy=runtime_policy,
        ),
        status=APP_SPEC_STATUS_ACCEPTED,
        validation_passed=True,
        coverage_passed=True,
        coverage_score=100,
        parent_revision_id=parent_revision_id,
    )
    return AppSpecGenerationResult(
        spec=spec,
        revision_record=row,
        validation_report=validation,
        coverage_review=None,
        source_sha256=source_digest,
        reused=False,
        calls_used=calls_used,
        repair_attempts=repair_attempts,
    )


def ensure_approved_app_spec(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    *,
    force_new_revision: bool = False,
    source_snapshot_override: Mapping[str, Any] | None = None,
    derived_context_override: Mapping[str, Any] | None = None,
    policy: AppSpecGenerationPolicy | None = None,
) -> AppSpecGenerationResult:
    """Return a reusable accepted AppSpec, self-healing when authoring fails.

    Pipeline: sanitize → validate → deterministic heal → AI repair → fallback.
    Fallback keeps preview generation unblocked with a minimal valid contract.
    """

    active_policy = policy or AppSpecGenerationPolicy()
    (
        author_model,
        repair_model,
        coverage_model,
        model_families,
    ) = resolve_model_assignment(active_policy)
    runtime_policy = _ResolvedGenerationPolicy(
        policy=active_policy,
        author_model=author_model,
        repair_model=repair_model,
        coverage_model=coverage_model,
        model_families=model_families,
        allow_fallback=(
            settings.APPSPEC_FALLBACK_ENABLED
            if active_policy.allow_fallback is None
            else active_policy.allow_fallback
        ),
    )

    req = get_request(db, request_id)
    log.info("Ensuring approved AppSpec for request %s (force_new=%s)", request_id, force_new_revision)
    source_snapshot = dict(
        source_snapshot_override
        if source_snapshot_override is not None
        else capture_request_source(req)
    )
    derived_context = dict(
        derived_context_override
        if derived_context_override is not None
        else capture_derived_context(req)
    )
    source_digest = calculate_source_sha256(source_snapshot)
    repository = AppSpecRepository(db)

    if not force_new_revision:
        if active_policy.require_complete:
            strategy_digest = str(
                active_policy.metadata.get("product_strategy_sha256") or ""
            )
            if not strategy_digest:
                raise ValueError(
                    "A strict AppSpec policy requires product_strategy_sha256."
                )
            existing = repository.latest_complete(
                request_id,
                source_sha256=source_digest,
                schema_version=settings.APPSPEC_SCHEMA_VERSION,
                product_strategy_sha256=strategy_digest,
            )
        else:
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
    deterministic_heals = 0
    heal_actions: list[str] = []

    def _fallback(reason: str) -> AppSpecGenerationResult:
        if not runtime_policy.allow_fallback:
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
                runtime_policy=runtime_policy,
            )
            raise AppSpecGenerationError(
                _format_validation_failure(
                    f"AppSpec failed ({reason}) and fallback is disabled.",
                    validation_payload,
                ),
                revision_record=rejected,
            )
        return _accept_fallback_app_spec(
            repository=repository,
            request_id=request_id,
            source_snapshot=source_snapshot,
            source_digest=source_digest,
            parent_revision_id=parent_revision_id,
            calls_used=provider.calls_used,
            repair_attempts=repairs,
            deterministic_heals=deterministic_heals,
            heal_actions=heal_actions,
            prior_candidate=candidate,
            prior_validation=validation_payload,
            prior_coverage=coverage_payload,
            reason=reason,
            runtime_policy=runtime_policy,
        )

    try:
        try:
            candidate = _sanitize_candidate(
                build_app_spec_candidate(
                    source_snapshot=source_snapshot,
                    derived_context=derived_context,
                    ai_provider=provider,
                    template_renderer=template_renderer,
                    model=runtime_policy.author_model,
                ),
                source_snapshot,
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
                extra_issues = (
                    ([version_issue] if version_issue else []) + source_issues
                )
                strategy_payload = (derived_context or {}).get("product_strategy")
                if (
                    strategy_payload
                    and validation.passed
                    and not version_issue
                    and not source_issues
                ):
                    try:
                        select_primary_journey_proof(
                            spec,
                            ProductStrategy.model_validate(strategy_payload),
                        )
                    except (TierBuildError, ValidationError) as exc:
                        extra_issues.append(
                            {
                                "severity": "blocking",
                                "code": "tier1_primary_journey_incomplete",
                                "message": str(exc),
                                "path": "journeys",
                                "related_ids": [],
                            }
                        )
                validation_payload = _validation_payload(
                    validation,
                    extra_issues=extra_issues,
                )
            elif parse_issue:
                validation_payload = _validation_payload(
                    None,
                    extra_issues=[parse_issue],
                )

            if not validation_payload.get("passed"):
                # 1) Deterministic heal from issue codes (cheap, scalable).
                if deterministic_heals < settings.APPSPEC_MAX_DETERMINISTIC_HEALS:
                    healed, actions = _heal_candidate(
                        candidate, validation_payload, source_snapshot
                    )
                    if actions:
                        deterministic_heals += 1
                        heal_actions.extend(actions)
                        candidate = healed
                        spec = None
                        validation = None
                        log.info(
                            "AppSpec deterministic heal #%s for request %s: %s",
                            deterministic_heals,
                            request_id,
                            ", ".join(actions[:8]),
                        )
                        continue

                # 2) AI repair while budget remains.
                if repairs < settings.APPSPEC_MAX_REPAIR_ATTEMPTS and candidate is not None:
                    repairs += 1
                    candidate = _sanitize_candidate(
                        repair_app_spec_candidate(
                            source_snapshot=source_snapshot,
                            derived_context=derived_context,
                            candidate=candidate,
                            deterministic_report=validation_payload,
                            coverage_review=coverage_payload,
                            ai_provider=provider,
                            template_renderer=template_renderer,
                            model=runtime_policy.repair_model,
                        ),
                        source_snapshot,
                    )
                    spec = None
                    validation = None
                    continue

                # 3) Safety-net fallback — do not crash the run.
                return _fallback("deterministic_validation_failed")

            assert spec is not None and validation is not None
            try:
                coverage = review_app_spec_coverage(
                    source_snapshot=source_snapshot,
                    app_spec=spec,
                    ai_provider=provider,
                    template_renderer=template_renderer,
                    model=runtime_policy.coverage_model,
                )
            except AppSpecCoverageError:
                # Retry one malformed independent review without changing a valid
                # contract. A second malformed result fails closed below.
                try:
                    coverage = review_app_spec_coverage(
                        source_snapshot=source_snapshot,
                        app_spec=spec,
                        ai_provider=provider,
                        template_renderer=template_renderer,
                        model=runtime_policy.coverage_model,
                    )
                except AppSpecCoverageError:
                    return _fallback("coverage_review_malformed")
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
                        deterministic_heals=deterministic_heals,
                        heal_actions=heal_actions,
                        used_fallback=False,
                        complete=active_policy.require_complete,
                        runtime_policy=runtime_policy,
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

            if repairs < settings.APPSPEC_MAX_REPAIR_ATTEMPTS:
                repairs += 1
                candidate = _sanitize_candidate(
                    repair_app_spec_candidate(
                        source_snapshot=source_snapshot,
                        derived_context=derived_context,
                        candidate=spec,
                        deterministic_report=validation_payload,
                        coverage_review=coverage_payload,
                        ai_provider=provider,
                        template_renderer=template_renderer,
                        model=runtime_policy.repair_model,
                    ),
                    source_snapshot,
                )
                spec = None
                validation = None
                coverage = None
                coverage_payload = _coverage_payload(None)
                continue

            return _fallback("semantic_coverage_failed")

    except AppSpecCallBudgetExceeded:
        return _fallback("call_budget_exhausted")
    except AppSpecGenerationError:
        raise
    except Exception as exc:
        log.exception("AppSpec generation crashed for request %s: %s", request_id, exc)
        if runtime_policy.allow_fallback:
            try:
                return _fallback(type(exc).__name__)
            except Exception:
                pass
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
            runtime_policy=runtime_policy,
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
