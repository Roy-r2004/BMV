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
from app.application.appspec.schema_repair import repair_app_spec_schema_candidate
from app.application.appspec.coverage import (
    AppSpecCoverageError,
    AppSpecCoverageReview,
    AppSpecCoverageTransportError,
    coverage_requires_repair,
    coverage_retry_instruction,
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
from app.domain.appspec.sanitize.heal import (
    drop_unbindable_state_assertions,
    heal_app_spec_payload,
)
from app.domain.appspec.sanitize.pipeline import sanitize_app_spec_payload
from app.domain.appspec.sanitize.preparse_normalize import (
    normalize_app_spec_preparse,
)
from app.domain.appspec.sanitize.reference_integrity import (
    reconcile_reference_integrity,
)
from app.domain.appspec.sanitize.schema_diagnostics import (
    build_rejected_candidate_artifact,
    classify_schema_parse_exception,
)
from app.domain.appspec.sanitize.graph_repair import (
    repair_app_spec_graph,
    validation_has_repairable_graph_issues,
)
from app.domain.appspec.sanitize.trace_evidence_repair import (
    repair_trace_evidence_mismatch,
    validation_has_safe_trace_evidence_repair,
)
from app.domain.appspec.sanitize.graph_repair import GraphRepairResult
from app.domain.appspec.sanitize.schema_diagnostics import payload_sha256
from app.domain.appspec.sanitize.trace_evidence_repair import TraceEvidenceRepairResult
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

def _appspec_may_call_model() -> bool:
    """Whether the AppSpec stage may still pay for a repair call.

    AppSpec is a mandatory stage with no wall-clock cap of its own: the Phase
    0.6 census measured 2-7 calls per run at p95 67 s each, and 340 s on
    request 70. Every one of those is before a single page has been generated.

    Past the request deadline the stage does not stop — it stops *re-asking*.
    The deterministic fallback already exists for exactly this, and taking it
    is recorded so a run that skipped its repairs cannot describe itself like
    one that never needed them.
    """
    from app.application.services.request_deadline import claim_model_time

    return claim_model_time("appspec", mandatory=True)


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
    """AppSpec's AI ceiling, held per REQUEST and behind a runway reservation.

    Two bounds, and they fail differently:

    * `APPSPEC_MAX_CALLS` is spent against the deadline's tally, so entering the
      stage a second time continues the budget instead of minting a new one.
    * `APPSPEC_DOWNSTREAM_RESERVE_SECONDS` refuses a call that would leave the
      rest of the pipeline less time than any shipped run has ever needed.

    The second is the one that matters for the artifact. A call budget bounds
    how *often* the stage asks; only a runway bound stops it consuming the time
    `architect` and `codegen` still have to spend, which is how requests 92 and
    94 reached their deadline with an approved contract and no preview at all.
    """

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
        from app.application.services.request_deadline import current_deadline

        deadline = current_deadline()
        if deadline is None:
            # No armed deadline (admin re-runs, tests). Nothing request-scoped
            # exists to hold the tally, so the ceiling is per instance — the
            # historical behaviour, and safe because there is no clock to blow.
            with self._lock:
                if self.calls_used >= self.max_calls:
                    raise AppSpecCallBudgetExceeded(
                        f"AppSpec AI call budget exhausted ({self.calls_used}/{self.max_calls})."
                    )
                self.calls_used += 1
            return

        left = deadline.remaining()
        reserve = float(settings.APPSPEC_DOWNSTREAM_RESERVE_SECONDS)
        if left < reserve:
            # Recorded, never silent: a run whose contract stage ran out of
            # runway and a run that simply needed fewer calls must not describe
            # themselves the same way.
            deadline.record_degradation("appspec", "stopped_low_downstream_runway")
            raise AppSpecCallBudgetExceeded(
                f"AppSpec stopped with {left:.1f}s of runway; every run that "
                f"has ever shipped needed at least {reserve:.0f}s after this stage."
            )
        if not deadline.consume_stage_call("appspec", self.max_calls):
            deadline.record_degradation("appspec", "call_budget_exhausted")
            raise AppSpecCallBudgetExceeded(
                "AppSpec AI call budget exhausted "
                f"({deadline.stage_calls_used('appspec')}/{self.max_calls}) for the request."
            )
        with self._lock:
            self.calls_used += 1

    def _refund(self) -> None:
        """Give back the unit `_acquire` spent on an ask that raised.

        An errored $0 call (transport cut, provider raise) bought no answer;
        request 143's error-cut authoring attempt spent budget for nothing.
        The transport re-ask ladders bound retry COUNT on their own — the call
        budget's job is to bound answered asks.
        """

        from app.application.services.request_deadline import current_deadline

        deadline = current_deadline()
        if deadline is not None:
            deadline.refund_stage_call("appspec")
        with self._lock:
            if self.calls_used > 0:
                self.calls_used -= 1

    def ask_chat(self, model: str, messages: list[dict], **kwargs: Any) -> str:
        self._acquire()
        try:
            return self.provider.ask_chat(model, messages, **kwargs)
        except Exception:
            self._refund()
            raise

    def ask_vision(self, model: str, prompt: str, image_path: str) -> str:
        self._acquire()
        try:
            return self.provider.ask_vision(model, prompt, image_path)
        except Exception:
            self._refund()
            raise

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


def _issue_identity_signature(validation_payload: Mapping[str, Any]) -> str:
    """Canonical identity of a validator error set: sorted (code, path, message).

    Severity/ctx noise is excluded on purpose: two reports that reject the same
    paths for the same codes with the same messages are the same verdict, and a
    repair whose output reproduces its input's verdict has repaired nothing —
    re-asking on it is the R2 verbatim-retry defect inside the repair loop
    (request 143 revs 4-5; request 138's repair repeated its parent's error at
    the identical path). Any change to the set — one error fixed, one added —
    is progress and never matches.
    """

    triples = sorted(
        (
            str(issue.get("code") or ""),
            str(issue.get("path") or ""),
            str(issue.get("message") or ""),
        )
        for issue in (validation_payload.get("issues") or [])
        if isinstance(issue, Mapping)
    )
    return json.dumps(triples, ensure_ascii=False)


def _repair_collapsed_spec(
    parent_payload: Mapping[str, Any] | None,
    child_payload: Mapping[str, Any] | None,
) -> bool:
    """True when a repair emptied `pages`/`states` its parent populated.

    Request 143 rev 1: the ai_appspec_repair call replaced a 6-page authored
    spec with a 503-byte fragment — one acceptance-test object, empty `pages`
    and `states` — and three revisions died reconciling nothing. Both
    collections carry min_length=1, so an output in this shape can never
    validate; rejecting it deterministically is pure fail-closed (the taught
    anti-collapse line is the model-facing half, this guard is the code half —
    owner-ruled, session 24). A shrink that keeps the collections populated is
    never a collapse: repairs legitimately drop faulted objects.
    """

    if not isinstance(parent_payload, Mapping) or not isinstance(
        child_payload, Mapping
    ):
        return False
    for key in ("pages", "states"):
        parent_items = parent_payload.get(key)
        if (
            isinstance(parent_items, (list, tuple))
            and parent_items
            and not child_payload.get(key)
        ):
            return True
    return False


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


def _clone_candidate(
    candidate: AppSpecCandidate,
    payload: dict[str, Any],
    *,
    repair_type: str = "",
    parent_payload_sha256: str = "",
) -> AppSpecCandidate:
    return AppSpecCandidate(
        payload=payload,
        response_excerpt=candidate.response_excerpt,
        raw_response_sha256=candidate.raw_response_sha256,
        raw_char_count=candidate.raw_char_count,
        json_extraction=candidate.json_extraction,
        parent_payload_sha256=parent_payload_sha256
        or candidate.parent_payload_sha256
        or payload_sha256(candidate.payload),
        repair_type=repair_type or candidate.repair_type,
    )


def _sanitize_candidate(
    candidate: AppSpecCandidate | None,
    source_snapshot: dict[str, Any],
    diagnostics: dict[str, Any] | None = None,
) -> AppSpecCandidate | None:
    if candidate is None:
        return None
    sanitized = sanitize_app_spec_payload(
        candidate.payload, source_snapshot, diagnostics=diagnostics
    )
    from app.application.services.ai_features import (
        ai_features_from_source,
        bind_ai_features_to_app_spec,
    )

    ai_features = ai_features_from_source(source_snapshot)
    if ai_features:
        sanitized = bind_ai_features_to_app_spec(sanitized, ai_features)
    return _clone_candidate(candidate, sanitized)


def _with_trace_reference_audit(
    graph_repair_audit: Mapping[str, Any],
    trace_reference_audit: Mapping[str, Any],
    *,
    validation_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach one trace-reference reconciliation record to the attempt audit."""

    audit = dict(graph_repair_audit)
    if not trace_reference_audit:
        return audit
    audit["trace_reference_reconciliation"] = {
        **dict(trace_reference_audit),
        "final_validation_result": (
            "passed" if validation_payload.get("passed") else "failed"
        ),
    }
    return audit


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
    healed = _clone_candidate(
        candidate,
        healed_payload,
        repair_type="deterministic_heal",
        parent_payload_sha256=payload_sha256(candidate.payload),
    )
    return _sanitize_candidate(healed, source_snapshot), actions


def _salvage_unbindable_state_assertions(
    candidate: AppSpecCandidate | None,
    validation_payload: Mapping[str, Any],
) -> tuple[AppSpecCandidate | None, list[str]]:
    """Drop state assertions naming a state the spec never declared, then re-sanitize.

    Bounded to the one terminal branch that would otherwise discard the run. See
    `drop_unbindable_state_assertions` for why this is not a heal and must not run
    ahead of the model's repair pass.
    """
    if candidate is None:
        return None, []
    payload, actions = drop_unbindable_state_assertions(
        candidate.payload, validation_payload
    )
    if not actions:
        return candidate, []
    salvaged = _clone_candidate(
        candidate,
        payload,
        repair_type="state_assertion_salvage",
        parent_payload_sha256=payload_sha256(candidate.payload),
    )
    return salvaged, actions


def _graph_repair_candidate(
    candidate: AppSpecCandidate | None,
    validation_payload: Mapping[str, Any],
    source_snapshot: dict[str, Any],
) -> tuple[AppSpecCandidate | None, GraphRepairResult]:
    """Apply one bounded membership graph repair, then re-sanitize."""

    empty = GraphRepairResult(payload={})
    if candidate is None:
        return None, empty
    repair = repair_app_spec_graph(candidate.payload, validation_payload)
    if repair.refused_reasons or not repair.applied:
        return candidate, repair
    repaired = _clone_candidate(
        candidate,
        repair.payload,
        repair_type="deterministic_graph_repair",
        parent_payload_sha256=repair.original_sha256,
    )
    return _sanitize_candidate(repaired, source_snapshot), repair


def _trace_evidence_repair_candidate(
    candidate: AppSpecCandidate | None,
    validation_payload: Mapping[str, Any],
    source_snapshot: dict[str, Any],
) -> tuple[AppSpecCandidate | None, TraceEvidenceRepairResult]:
    empty = TraceEvidenceRepairResult(payload={})
    if candidate is None:
        return None, empty
    repair = repair_trace_evidence_mismatch(candidate.payload, validation_payload)
    if repair.refused_reasons or not repair.applied:
        return candidate, repair
    repaired = _clone_candidate(
        candidate,
        repair.payload,
        repair_type="deterministic_trace_repair",
        parent_payload_sha256=repair.original_sha256,
    )
    return _sanitize_candidate(repaired, source_snapshot), repair


def _parse_validation_issue(
    exc: Exception,
    *,
    candidate_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return classify_schema_parse_exception(
        exc,
        candidate_payload=candidate_payload,
    )

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
    graph_repair_audit: Mapping[str, Any] | None = None,
    schema_diagnostics: Mapping[str, Any] | None = None,
    lineage_audit: Mapping[str, Any] | None = None,
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
        "graph_repair": dict(graph_repair_audit or {}),
        "schema_diagnostics": dict(schema_diagnostics or {}),
        "lineage": dict(lineage_audit or {}),
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
    deterministic_heals: int = 0,
    heal_actions: list[str] | None = None,
    graph_repair_audit: Mapping[str, Any] | None = None,
    schema_diagnostics: Mapping[str, Any] | None = None,
    lineage_audit: Mapping[str, Any] | None = None,
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
                deterministic_heals=deterministic_heals,
                heal_actions=heal_actions,
                runtime_policy=runtime_policy,
                graph_repair_audit=graph_repair_audit,
                schema_diagnostics=schema_diagnostics,
                lineage_audit=lineage_audit,
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

    Pipeline: sanitize → validate → deterministic heal → deterministic graph
    repair (at most once) → AI repair (at most once after graph failures) →
    fallback only when explicitly enabled.
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
    # Bounded to one: the salvage removes an unrepairable claim, so a second
    # firing would mean the first changed nothing that mattered.
    state_assertion_salvages = 0
    heal_actions: list[str] = []
    graph_repairs = 0
    graph_repair_audit: dict[str, Any] = {}
    graph_repair_source_revision_id: int | None = None
    saw_graph_issues = False
    preparse_normalizations = 0
    schema_ai_repairs = 0
    trace_evidence_repairs = 0
    schema_diagnostics: dict[str, Any] = {}
    lineage_audit: dict[str, Any] = {"attempts": []}
    attempt_number = 0
    persisted_schema_payload_hashes: set[str] = set()
    trace_reference_audit: dict[str, Any] = {}
    # Set at each AI repair dispatch to the signature of the error set that
    # repair was asked to fix; compared exactly once against the next
    # iteration's fresh set. Deterministic rungs never set it.
    last_ai_repair_error_signature: str | None = None

    def _sanitize_tracked(
        pending: AppSpecCandidate | None,
        snapshot: dict[str, Any],
    ) -> AppSpecCandidate | None:
        """Sanitize one attempt payload and keep its trace-reconciliation record."""

        nonlocal trace_reference_audit
        sink: dict[str, Any] = {}
        sanitized = _sanitize_candidate(pending, snapshot, sink)
        record = sink.get("trace_reference_reconciliation")
        if isinstance(record, Mapping):
            trace_reference_audit = {
                **dict(record),
                "provider_calls_used": provider.calls_used,
            }
        return sanitized

    def _record_lineage(entry: Mapping[str, Any]) -> None:
        lineage_audit.setdefault("attempts", []).append(dict(entry))
        lineage_audit["attempts"] = lineage_audit["attempts"][:40]

    def _persist_schema_rejection(
        *,
        terminal_reason: str,
        parse_issue: Mapping[str, Any] | None,
        repair_type: str | None = None,
        before_sha256: str | None = None,
        after_sha256: str | None = None,
        changed_paths: list[str] | None = None,
        parent_id: int | None = None,
    ) -> AppSpecRevision | None:
        nonlocal attempt_number, schema_diagnostics, graph_repair_source_revision_id
        attempt_number += 1
        artifact = build_rejected_candidate_artifact(
            request_id=request_id,
            attempt_number=attempt_number,
            provider=str(getattr(ai_provider, "name", "unknown") or "unknown"),
            model=runtime_policy.author_model,
            prompt_revision=settings.APPSPEC_PROMPT_REVISION,
            raw_response=(candidate.response_excerpt if candidate else None),
            raw_response_sha256=(
                candidate.raw_response_sha256 if candidate else None
            ),
            candidate_payload=_candidate_payload(candidate),
            json_extraction=(
                dict(candidate.json_extraction or {}) if candidate else {}
            ),
            schema_issue=parse_issue,
            estimated_tokens=(
                max(1, (candidate.raw_char_count + 3) // 4) if candidate else None
            ),
            finish_reason=(
                ((candidate.authoring_diagnostics or {}).get("provider") or {}).get(
                    "finish_reason"
                )
                if candidate
                else None
            ),
            terminal_result=terminal_reason,
            parent_revision_id=parent_id
            or graph_repair_source_revision_id
            or parent_revision_id,
            repair_type=repair_type,
            before_sha256=before_sha256,
            after_sha256=after_sha256,
            changed_paths=changed_paths,
            authoring_diagnostics=(
                dict(candidate.authoring_diagnostics or {}) if candidate else None
            ),
        )
        schema_diagnostics = artifact
        row = _persist_rejected(
            repository=repository,
            request_id=request_id,
            source_snapshot=source_snapshot,
            candidate=candidate,
            validation_payload=validation_payload,
            coverage_payload=coverage_payload,
            parent_revision_id=parent_id
            or graph_repair_source_revision_id
            or parent_revision_id,
            calls_used=provider.calls_used,
            repair_attempts=repairs,
            terminal_reason=terminal_reason,
            runtime_policy=runtime_policy,
            deterministic_heals=deterministic_heals,
            heal_actions=heal_actions,
            graph_repair_audit=_with_trace_reference_audit(
                graph_repair_audit,
                trace_reference_audit,
                validation_payload=validation_payload,
            ),
            schema_diagnostics=artifact,
            lineage_audit=lineage_audit,
        )
        if row is not None:
            graph_repair_source_revision_id = row.id
            _record_lineage(
                {
                    "revision_id": row.id,
                    "revision": row.revision,
                    "terminal_reason": terminal_reason,
                    "repair_type": repair_type,
                    "app_spec_sha256": row.app_spec_sha256,
                    "parent_revision_id": row.parent_revision_id,
                }
            )
        return row

    def _fallback(reason: str) -> AppSpecGenerationResult:
        if not runtime_policy.allow_fallback:
            rejected = _persist_rejected(
                repository=repository,
                request_id=request_id,
                source_snapshot=source_snapshot,
                candidate=candidate,
                validation_payload=validation_payload,
                coverage_payload=coverage_payload,
                parent_revision_id=(
                    graph_repair_source_revision_id or parent_revision_id
                ),
                calls_used=provider.calls_used,
                repair_attempts=repairs,
                terminal_reason=reason,
                runtime_policy=runtime_policy,
                deterministic_heals=deterministic_heals,
                heal_actions=heal_actions,
                graph_repair_audit=graph_repair_audit,
                schema_diagnostics=schema_diagnostics,
                lineage_audit=lineage_audit,
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
            candidate = _sanitize_tracked(
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
            typed = getattr(exc, "typed_error", None) or "malformed_json"
            malformed = classify_schema_parse_exception(exc)
            # Prefer precise authoring typed child when JSON extraction failed.
            malformed = {
                **malformed,
                "issues": [
                    {
                        "severity": "blocking",
                        "code": typed,
                        "message": str(exc),
                        "path": "",
                        "related_ids": [],
                        "error_type": type(exc).__name__,
                        "offending_value_type": "str",
                    }
                ],
            }
            validation_payload = _validation_payload(
                None,
                extra_issues=[
                    {
                        "severity": "blocking",
                        "code": "app_spec_authoring_output_invalid",
                        "message": str(exc),
                        "path": "",
                        "related_ids": [],
                    },
                    malformed,
                    *list(malformed.get("issues") or []),
                ],
            )
            candidate = AppSpecCandidate(
                payload={},
                response_excerpt=exc.response_excerpt,
                raw_response_sha256=exc.raw_response_sha256,
                raw_char_count=len(exc.response_excerpt or ""),
                json_extraction=exc.json_extraction,
                authoring_diagnostics=getattr(exc, "authoring_diagnostics", None),
            )
            rejected = _persist_schema_rejection(
                terminal_reason="authoring_output_invalid",
                parse_issue=malformed,
                repair_type=None,
            )
            # Authoring JSON failure is terminal: do not continue with an empty
            # payload into schema/fallback persistence (request #43 triple-write).
            # Do not invoke AppSpec fallback for malformed authoring output.
            raise AppSpecGenerationError(
                _format_validation_failure(
                    (
                        "AppSpec failed (authoring_output_invalid)"
                        + (
                            " and fallback is disabled."
                            if not runtime_policy.allow_fallback
                            else "."
                        )
                    ),
                    validation_payload,
                ),
                revision_record=rejected,
            )

        while True:
            awaited_repair_signature = last_ai_repair_error_signature
            last_ai_repair_error_signature = None
            parse_issue: dict[str, Any] | None = None
            if candidate is not None and candidate.payload:
                try:
                    spec = parse_app_spec_candidate(candidate)
                except Exception as exc:
                    spec = None
                    parse_issue = _parse_validation_issue(
                        exc,
                        candidate_payload=candidate.payload if candidate else None,
                    )

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
                children = [
                    item
                    for item in (parse_issue.get("issues") or [])
                    if isinstance(item, dict)
                ]
                validation_payload = _validation_payload(
                    None,
                    extra_issues=[parse_issue, *children],
                )

            if not validation_payload.get("passed"):
                if validation_has_repairable_graph_issues(validation_payload):
                    saw_graph_issues = True

                has_schema_parse = any(
                    str(issue.get("code") or "") == "app_spec_schema_parse_failed"
                    for issue in (validation_payload.get("issues") or [])
                    if isinstance(issue, Mapping)
                )

                # 0a) Persist rejected schema candidate diagnostics (immutable).
                if has_schema_parse and candidate is not None:
                    sha = payload_sha256(candidate.payload)
                    if sha not in persisted_schema_payload_hashes:
                        persisted_schema_payload_hashes.add(sha)
                        _persist_schema_rejection(
                            terminal_reason="schema_parse_failed",
                            parse_issue=parse_issue
                            or next(
                                (
                                    issue
                                    for issue in (
                                        validation_payload.get("issues") or []
                                    )
                                    if isinstance(issue, Mapping)
                                    and issue.get("code")
                                    == "app_spec_schema_parse_failed"
                                ),
                                None,
                            ),
                            repair_type=candidate.repair_type or None,
                            before_sha256=candidate.parent_payload_sha256 or None,
                            after_sha256=sha,
                        )

                # 0a-bis) A repair that reproduces its parent's identical
                # validator error set has repaired nothing — every remaining
                # rung already had its chance at this exact set, so spending
                # further budget re-asks the same question (R2). Fail now,
                # with the artifact persisted above.
                if (
                    awaited_repair_signature is not None
                    and _issue_identity_signature(validation_payload)
                    == awaited_repair_signature
                ):
                    # Before throwing a paid run away: an assertion naming a
                    # state the spec never declared is the one issue the model
                    # cannot repair by rewriting what is there — it has to add an
                    # entity, and until the repair prompt said so it kept
                    # re-emitting the same `state_id: null`. That is how requests
                    # 149, 154 and 155 died. Once, and only here, drop the claim
                    # the spec cannot express rather than lose the whole run;
                    # anything else in the set still fails closed.
                    salvaged, salvage_actions = (
                        _salvage_unbindable_state_assertions(
                            candidate, validation_payload
                        )
                        if state_assertion_salvages < 1
                        else (candidate, [])
                    )
                    if salvage_actions:
                        state_assertion_salvages += 1
                        heal_actions.extend(salvage_actions)
                        candidate = salvaged
                        awaited_repair_signature = None
                        spec = None
                        validation = None
                        log.info(
                            "AppSpec salvage for request %s: %s",
                            request_id,
                            ", ".join(salvage_actions[:8]),
                        )
                        continue
                    log.info(
                        "AppSpec repair reproduced its parent's validator "
                        "error set for request %s — failing closed instead "
                        "of spending further repairs",
                        request_id,
                    )
                    return _fallback("repair_reproduced_parent_errors")

                # Empty authoring payload cannot be repaired meaningfully.
                if candidate is not None and not candidate.payload:
                    return _fallback("deterministic_validation_failed")

                # 0b) Deterministic pre-parse normalization (once).
                if (
                    has_schema_parse
                    and preparse_normalizations < 1
                    and candidate is not None
                    and candidate.payload
                ):
                    original_sha = payload_sha256(candidate.payload)
                    normalized = normalize_app_spec_preparse(candidate.payload)
                    preparse_normalizations = 1
                    if normalized.applied:
                        candidate = _clone_candidate(
                            candidate,
                            normalized.payload,
                            repair_type="deterministic_schema_normalization",
                            parent_payload_sha256=original_sha,
                        )
                        candidate = _sanitize_tracked(candidate, source_snapshot)
                        _record_lineage(
                            {
                                "repair_type": "deterministic_schema_normalization",
                                "original_sha256": normalized.original_sha256,
                                "result_sha256": normalized.normalized_sha256,
                                "changed_paths": normalized.changed_paths[:40],
                                "actions": normalized.actions[:40],
                                "trace_records": normalized.trace_records[:40],
                                "refused_reasons": normalized.refused_reasons[:40],
                            }
                        )
                        log.info(
                            "AppSpec pre-parse normalization for request %s: %s",
                            request_id,
                            ", ".join(normalized.actions[:8]),
                        )
                        spec = None
                        validation = None
                        continue

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

                # 1b) Bounded deterministic trace-evidence repair (once, safe only).
                if (
                    trace_evidence_repairs < 1
                    and candidate is not None
                    and validation_has_safe_trace_evidence_repair(
                        candidate.payload, validation_payload
                    )
                ):
                    original_row = _persist_rejected(
                        repository=repository,
                        request_id=request_id,
                        source_snapshot=source_snapshot,
                        candidate=candidate,
                        validation_payload=validation_payload,
                        coverage_payload=coverage_payload,
                        parent_revision_id=parent_revision_id,
                        calls_used=provider.calls_used,
                        repair_attempts=repairs,
                        terminal_reason="pre_trace_evidence_repair",
                        runtime_policy=runtime_policy,
                        deterministic_heals=deterministic_heals,
                        heal_actions=heal_actions,
                        graph_repair_audit=_with_trace_reference_audit(
                            graph_repair_audit,
                            trace_reference_audit,
                            validation_payload=validation_payload,
                        ),
                        schema_diagnostics=schema_diagnostics,
                        lineage_audit=lineage_audit,
                    )
                    if original_row is not None:
                        graph_repair_source_revision_id = original_row.id
                    repaired_candidate, repair = _trace_evidence_repair_candidate(
                        candidate, validation_payload, source_snapshot
                    )
                    trace_evidence_repairs = 1
                    graph_repair_audit = {
                        **graph_repair_audit,
                        "trace_evidence_repair": {
                            "repair_type": "deterministic_trace_repair",
                            "original_revision_id": (
                                original_row.id if original_row else None
                            ),
                            "original_sha256": repair.original_sha256,
                            "repaired_sha256": repair.repaired_sha256,
                            "changed_paths": repair.changed_paths[:80],
                            "actions": repair.actions[:80],
                            "reconciliations": repair.reconciliations[:80],
                            "refused_reasons": repair.refused_reasons[:40],
                            "result": repair.result_label,
                            "provider_calls_used": 0,
                        },
                    }
                    if repair.applied and repaired_candidate is not None:
                        candidate = repaired_candidate
                        spec = None
                        validation = None
                        log.info(
                            "AppSpec trace-evidence repair for request %s: %s",
                            request_id,
                            ", ".join(repair.actions[:8]),
                        )
                        continue

                # 2) Bounded deterministic graph/membership repair (once).
                if (
                    graph_repairs < 1
                    and candidate is not None
                    and validation_has_repairable_graph_issues(validation_payload)
                ):
                    pre_repair_errors = list(
                        validation_payload.get("issues") or []
                    )
                    original_row = _persist_rejected(
                        repository=repository,
                        request_id=request_id,
                        source_snapshot=source_snapshot,
                        candidate=candidate,
                        validation_payload=validation_payload,
                        coverage_payload=coverage_payload,
                        parent_revision_id=parent_revision_id,
                        calls_used=provider.calls_used,
                        repair_attempts=repairs,
                        terminal_reason="pre_graph_repair",
                        runtime_policy=runtime_policy,
                        deterministic_heals=deterministic_heals,
                        heal_actions=heal_actions,
                        graph_repair_audit={
                            "repair_type": "deterministic_graph_repair",
                            "result": "pending",
                            "validation_errors_before": pre_repair_errors[:40],
                        },
                        schema_diagnostics=schema_diagnostics,
                        lineage_audit=lineage_audit,
                    )
                    if original_row is not None:
                        graph_repair_source_revision_id = original_row.id
                    repaired_candidate, repair = _graph_repair_candidate(
                        candidate, validation_payload, source_snapshot
                    )
                    graph_repairs = 1
                    graph_repair_audit = {
                        "request_id": request_id,
                        "original_revision_id": (
                            original_row.id if original_row else None
                        ),
                        "original_sha256": repair.original_sha256,
                        "repaired_sha256": repair.repaired_sha256,
                        "repair_type": "deterministic_graph_repair",
                        "validation_errors_before": pre_repair_errors[:40],
                        "changed_paths": repair.changed_paths[:80],
                        "actions": repair.actions[:80],
                        "refused_reasons": repair.refused_reasons[:40],
                        "result": repair.result_label,
                    }
                    if repair.applied and repaired_candidate is not None:
                        candidate = repaired_candidate
                        spec = None
                        validation = None
                        log.info(
                            "AppSpec graph repair for request %s: %s",
                            request_id,
                            ", ".join(repair.actions[:8]),
                        )
                        continue
                    log.info(
                        "AppSpec graph repair refused for request %s: %s",
                        request_id,
                        ", ".join(repair.refused_reasons[:8]) or "no_changes",
                    )

                # 2b) Bounded AI schema repair for remaining parse failures.
                # Uses the configured APPSPEC_MAX_REPAIR_ATTEMPTS rather than a
                # hardcoded single attempt. The author intermittently emits empty
                # required tuples (invalid_trace_shape) or duplicate IDs, and one
                # schema-repair shot frequently does not clear them — which meant
                # a recoverable spec failed closed. Required empty traces cannot
                # be healed deterministically (that would invent traceability, see
                # domain/appspec/sanitize/empty_trace.py), so the AI repair is the
                # only legitimate path. Total provider calls remain hard-bounded by
                # _StageLimitedAIProvider(APPSPEC_MAX_CALLS).
                if (
                    has_schema_parse
                    and schema_ai_repairs < settings.APPSPEC_MAX_SCHEMA_REPAIR_ATTEMPTS
                    and candidate is not None
                    and candidate.payload
                ):
                    schema_ai_repairs += 1
                    last_ai_repair_error_signature = _issue_identity_signature(
                        validation_payload
                    )
                    parent_sha = payload_sha256(candidate.payload)
                    parent_row_id = graph_repair_source_revision_id
                    try:
                        repaired = repair_app_spec_schema_candidate(
                            candidate=candidate,
                            schema_issue=parse_issue
                            or {
                                "code": "app_spec_schema_parse_failed",
                                "issues": [
                                    issue
                                    for issue in (
                                        validation_payload.get("issues") or []
                                    )
                                    if isinstance(issue, Mapping)
                                ],
                            },
                            ai_provider=provider,
                            template_renderer=template_renderer,
                            model=runtime_policy.repair_model,
                        )
                    except Exception as exc:
                        log.info(
                            "AppSpec AI schema repair failed for request %s: %s",
                            request_id,
                            exc,
                        )
                        return _fallback("deterministic_validation_failed")
                    repaired_candidate = _sanitize_tracked(repaired, source_snapshot)
                    if _repair_collapsed_spec(
                        candidate.payload,
                        repaired_candidate.payload if repaired_candidate else None,
                    ):
                        log.info(
                            "AppSpec schema repair collapsed the spec for "
                            "request %s (pages/states emptied) — keeping the "
                            "parent and failing closed",
                            request_id,
                        )
                        return _fallback("repair_collapsed_parent_spec")
                    candidate = repaired_candidate
                    _record_lineage(
                        {
                            "repair_type": "ai_schema_repair",
                            "original_sha256": parent_sha,
                            "result_sha256": payload_sha256(
                                candidate.payload if candidate else {}
                            ),
                            "parent_revision_id": parent_row_id,
                            "model": runtime_policy.repair_model,
                        }
                    )
                    graph_repair_audit = {
                        **graph_repair_audit,
                        "ai_schema_repair": {
                            "repair_type": "ai_schema_repair",
                            "attempt": 1,
                            "model": runtime_policy.repair_model,
                            "original_sha256": parent_sha,
                            "result_sha256": payload_sha256(
                                candidate.payload if candidate else {}
                            ),
                        },
                    }
                    spec = None
                    validation = None
                    continue

                # Schema failures fail closed once the schema-repair attempts are spent.
                if has_schema_parse and schema_ai_repairs >= settings.APPSPEC_MAX_SCHEMA_REPAIR_ATTEMPTS:
                    return _fallback("deterministic_validation_failed")

                # 3) AI repair — at most once after graph-membership failures.
                ai_budget = (
                    1
                    if (saw_graph_issues or graph_repairs or trace_evidence_repairs)
                    else settings.APPSPEC_MAX_REPAIR_ATTEMPTS
                )
                # AppSpec is mandatory and was uncapped in wall clock: measured
                # 2-7 calls at p95 67 s each, 340 s on request 70. Past the
                # request deadline it stops buying repairs and takes the
                # deterministic fallback below — the spec still exists, it is
                # simply not re-asked for. Recorded, never silent.
                if not _appspec_may_call_model():
                    ai_budget = 0
                if repairs < ai_budget and candidate is not None:
                    repairs += 1
                    last_ai_repair_error_signature = _issue_identity_signature(
                        validation_payload
                    )
                    pre_ai_errors = list(validation_payload.get("issues") or [])
                    parent_payload_before_repair = candidate.payload
                    repaired_candidate = _sanitize_tracked(
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
                    if _repair_collapsed_spec(
                        parent_payload_before_repair,
                        repaired_candidate.payload if repaired_candidate else None,
                    ):
                        log.info(
                            "AppSpec repair collapsed the spec for request %s "
                            "(pages/states emptied) — keeping the parent and "
                            "failing closed",
                            request_id,
                        )
                        return _fallback("repair_collapsed_parent_spec")
                    candidate = repaired_candidate
                    graph_repair_audit = {
                        **graph_repair_audit,
                        "ai_repair": {
                            "repair_type": "ai_appspec_repair",
                            "attempt": repairs,
                            "model": runtime_policy.repair_model,
                            "provider": str(
                                getattr(ai_provider, "name", "unknown")
                                or "unknown"
                            ),
                            "validation_errors_before": pre_ai_errors[:40],
                        },
                    }
                    spec = None
                    validation = None
                    continue

                # 4) Safety-net fallback — only when explicitly enabled.
                return _fallback("deterministic_validation_failed")

            # Final reference-integrity pass before acceptance. Reconstruct
            # evidence-shaped entity refs when possible; otherwise fail closed
            # on the next validation loop.
            if candidate is not None and candidate.payload:
                original_sha = payload_sha256(candidate.payload)
                repaired_payload, integrity = reconcile_reference_integrity(
                    candidate.payload
                )
                graph_repair_audit = {
                    **graph_repair_audit,
                    "reference_integrity": {
                        "repair_type": "deterministic_reference_integrity",
                        "integrity_hash": integrity.integrity_hash,
                        "diagnostics": integrity.diagnostics[:40],
                        "applied": integrity.applied[:40],
                        "provider_called": False,
                    },
                }
                if integrity.applied:
                    candidate = _clone_candidate(
                        candidate,
                        repaired_payload,
                        repair_type="deterministic_reference_integrity",
                        parent_payload_sha256=original_sha,
                    )
                    candidate = _sanitize_tracked(candidate, source_snapshot)
                    heal_actions.extend(integrity.applied[:40])
                    _record_lineage(
                        {
                            "repair_type": "deterministic_reference_integrity",
                            "original_sha256": original_sha,
                            "result_sha256": payload_sha256(candidate.payload),
                            "integrity_hash": integrity.integrity_hash,
                            "diagnostics": integrity.diagnostics[:40],
                            "applied": integrity.applied[:40],
                            "provider_called": False,
                        }
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
                    model=runtime_policy.coverage_model,
                )
            except AppSpecCoverageError as coverage_error:
                # Retry one malformed independent review without changing a valid
                # contract. Run 133: a verbatim temperature-0 re-ask reproduced
                # the malformation byte-for-byte, so the retry is VARIED — a
                # compact corrective instruction naming the first failure — and
                # its telemetry attempt is bumped so the two coverage rows stay
                # distinguishable. A second failure fails closed below — except
                # the one case R1 carves out: when BOTH asks were cut in
                # transit (correlated weather at this site, the run-139 shape),
                # ONE ask goes to the cross-provider fallback model at
                # telemetry attempt 3 before failing closed. Malformation never
                # reaches that rung — a quality failure never takes a model
                # fallback — and a mixed sequence (one quality failure, one
                # cut) fails closed too: the rung needs transport proven
                # correlated, not merely present.
                first_was_transport = isinstance(
                    coverage_error, AppSpecCoverageTransportError
                )
                try:
                    coverage = review_app_spec_coverage(
                        source_snapshot=source_snapshot,
                        app_spec=spec,
                        ai_provider=provider,
                        template_renderer=template_renderer,
                        model=runtime_policy.coverage_model,
                        attempt=2,
                        corrective_instruction=coverage_retry_instruction(
                            coverage_error
                        ),
                    )
                except AppSpecCoverageTransportError as second_cut:
                    if not first_was_transport:
                        return _fallback("coverage_review_transport")
                    log.info(
                        "AppSpec coverage review cut twice in transit for "
                        "request %s — one ask on the cross-provider rung (%s)",
                        request_id,
                        settings.APPSPEC_TRANSPORT_FALLBACK_MODEL,
                    )
                    try:
                        coverage = review_app_spec_coverage(
                            source_snapshot=source_snapshot,
                            app_spec=spec,
                            ai_provider=provider,
                            template_renderer=template_renderer,
                            model=settings.APPSPEC_TRANSPORT_FALLBACK_MODEL,
                            attempt=3,
                            corrective_instruction=coverage_retry_instruction(
                                second_cut
                            ),
                        )
                    except AppSpecCoverageError:
                        return _fallback("coverage_review_transport")
                except AppSpecCoverageError:
                    return _fallback("coverage_review_malformed")
            coverage_payload = _coverage_payload(
                coverage,
                app_spec=spec,
                source_snapshot=source_snapshot,
            )
            if coverage_payload.get("passed"):
                if graph_repair_audit.get("result") == "repaired":
                    graph_repair_audit = {
                        **graph_repair_audit,
                        "validation_errors_after": [],
                        "result": "repaired",
                    }
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
                        graph_repair_audit=_with_trace_reference_audit(
                            graph_repair_audit,
                            trace_reference_audit,
                            validation_payload=validation_payload,
                        ),
                    ),
                    status=APP_SPEC_STATUS_ACCEPTED,
                    validation_passed=True,
                    coverage_passed=True,
                    coverage_score=coverage.score,
                    parent_revision_id=(
                        graph_repair_source_revision_id or parent_revision_id
                    ),
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

            if repairs < settings.APPSPEC_MAX_REPAIR_ATTEMPTS and _appspec_may_call_model():
                repairs += 1
                parent_payload_before_repair = spec.model_dump(mode="json")
                repaired_candidate = _sanitize_tracked(
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
                if _repair_collapsed_spec(
                    parent_payload_before_repair,
                    repaired_candidate.payload if repaired_candidate else None,
                ):
                    log.info(
                        "AppSpec coverage repair collapsed the spec for "
                        "request %s (pages/states emptied) — keeping the "
                        "parent and failing closed",
                        request_id,
                    )
                    return _fallback("repair_collapsed_parent_spec")
                candidate = repaired_candidate
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
            parent_revision_id=(
                graph_repair_source_revision_id or parent_revision_id
            ),
            calls_used=provider.calls_used,
            repair_attempts=repairs,
            terminal_reason=type(exc).__name__,
            runtime_policy=runtime_policy,
            deterministic_heals=deterministic_heals,
            heal_actions=heal_actions,
            graph_repair_audit=_with_trace_reference_audit(
                graph_repair_audit,
                trace_reference_audit,
                validation_payload=validation_payload,
            ),
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
