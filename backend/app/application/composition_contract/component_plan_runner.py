"""Bounded business_component_plan runner with deadline propagation."""
from __future__ import annotations

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextvars import copy_context
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from pydantic import ValidationError

if TYPE_CHECKING:
    from app.application.composition_contract.call_budget import Phase3ACallBudget

from app.application.appspec.source import canonical_json
from app.application.composition_contract.builder import (
    BuiltCompositionArtifact,
    CompositionStageError,
)
from app.application.composition_contract.component_plan_budgets import (
    BusinessComponentPlanBudgets,
    resolve_business_component_plan_budgets,
)
from app.application.composition_contract.component_plan_prompt import (
    ComponentPlanPromptProjection,
    estimate_tokens,
    project_business_component_plan_prompt,
    repair_prompt_values,
)
from app.application.composition_contract.deadline import StageDeadline
from app.application.composition_contract.policy import CompositionStagePolicy
from app.application.services.ai_context import (
    ai_run_scope,
    capture_ai_stage_telemetry,
)
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.schemas.business_component_plan import BusinessComponentPlan
from app.domain.schemas.composition_contract import (
    CompositionArtifactRef,
    CompositionStageMetrics,
    CompositionValidationReport,
)
from app.domain.schemas.page_purpose_contract import PagePurposeContract
from app.shared.json_utils import extract_json_from_text


ResultClass = str


@dataclass
class TimingSpans:
    values: dict[str, int] = field(default_factory=dict)

    def mark(self, name: str, started: float) -> None:
        self.values[name] = int(max(0.0, time.monotonic() - started) * 1000)


@dataclass
class AttemptRecord:
    attempt_number: int
    provider: str
    model: str
    prompt_projection_hash: str
    estimated_input_tokens: int
    output_token_ceiling: int
    started_at: str
    completed_at: str | None = None
    provider_duration_ms: int = 0
    parse_duration_ms: int = 0
    validation_duration_ms: int = 0
    total_duration_ms: int = 0
    remaining_deadline_seconds_at_start: float = 0.0
    remaining_deadline_seconds_at_end: float = 0.0
    result: ResultClass = "invalid_output"
    redacted_failure_reason: str = ""
    partial_output_hash: str | None = None
    cancelled: bool = False
    transport_attempts: int = 1
    finish_reason: str = ""
    token_usage: dict[str, int] = field(default_factory=dict)
    timing_spans: dict[str, int] = field(default_factory=dict)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_reason(text: str) -> str:
    cleaned = " ".join(str(text).split())
    return cleaned[:500]


def _partial_hash(raw: str | None) -> str | None:
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _retry_reason(
    parse_error: Exception | None,
    report: CompositionValidationReport | None,
) -> str:
    if parse_error is not None:
        if isinstance(parse_error, ValidationError):
            return canonical_json(
                {
                    "kind": "schema_validation",
                    "errors": parse_error.errors(include_url=False)[:20],
                }
            )[:4000]
        return canonical_json(
            {
                "kind": "invalid_json_or_schema",
                "error": str(parse_error)[:2000],
            }
        )
    assert report is not None
    return canonical_json(
        {
            "kind": "deterministic_validation",
            "issues": report.model_dump(mode="json")["issues"],
        }
    )[:4000]


def _missing_page_ids(
    report: CompositionValidationReport | None,
    page_purpose: PagePurposeContract,
) -> tuple[str, ...]:
    if report is None:
        return tuple(page.page_id for page in page_purpose.pages)
    mentioned: list[str] = []
    for issue in report.issues:
        for related in issue.related_ids:
            if str(related).startswith("PAGE-") and related not in mentioned:
                mentioned.append(str(related))
        if "page_compositions" in issue.path or "coverage" in issue.code:
            return tuple(page.page_id for page in page_purpose.pages)
    return tuple(mentioned)


def _cancel_provider(ai_provider: AIProvider) -> bool:
    cancel = getattr(ai_provider, "cancel_inflight", None)
    if callable(cancel):
        cancel()
        return True
    return False


def _invoke_provider_call(
    fn: Callable[[], str],
    *,
    timeout_seconds: float,
    stage: str,
    ai_provider: AIProvider,
) -> str:
    executor = ThreadPoolExecutor(max_workers=1)
    context = copy_context()
    future = executor.submit(context.run, fn)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeout as exc:
        cancelled = _cancel_provider(ai_provider)
        future.cancel()
        raise CompositionStageError(
            f"{stage} exceeded its wall timeout of "
            f"{timeout_seconds:.1f} seconds.",
            stage=stage,
            result_class="provider_timeout",
            diagnostics={"provider_cancelled": cancelled},
        ) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _parse_strict(
    raw: str,
    schema: type[BusinessComponentPlan],
) -> BusinessComponentPlan:
    """Fail closed on truncated/guessed JSON; never invent required fields."""

    payload = extract_json_from_text(raw)
    if not isinstance(payload, dict):
        raise ValueError("Structured output must be one JSON object")
    # Reject empty/guessed skeletons from parsers that invent placeholders.
    if not payload.get("components") or not payload.get("page_compositions"):
        raise ValueError("Partial output missing mandatory plan sections")
    return schema.model_validate(payload)


def build_business_component_plan_artifact(
    *,
    request_id: int,
    policy: CompositionStagePolicy,
    prompt_template: str,
    context,
    page_purpose: PagePurposeContract,
    page_purpose_ref: CompositionArtifactRef,
    validator: Callable[[BusinessComponentPlan], CompositionValidationReport],
    normalize: Callable[[BusinessComponentPlan], BusinessComponentPlan],
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    phase_deadline: float,
    budgets: BusinessComponentPlanBudgets | None = None,
    budget: "Phase3ACallBudget | None" = None,
) -> BuiltCompositionArtifact:
    budgets = budgets or resolve_business_component_plan_budgets()
    stage_deadline = StageDeadline.start(
        policy.stage,
        min(
            budgets.stage_wall_seconds,
            max(0.0, phase_deadline - time.monotonic()),
        ),
    )
    spans = TimingSpans()
    attempts: list[AttemptRecord] = []
    retry_reasons: list[str] = []
    provider_calls = 0
    deterministic_repair_used = 0
    final_artifact: BusinessComponentPlan | None = None
    final_report: CompositionValidationReport | None = None
    stage_started = time.monotonic()

    prompt_started = time.monotonic()
    projection = project_business_component_plan_prompt(
        context,
        page_purpose=page_purpose,
        page_purpose_ref=page_purpose_ref,
    )
    spans.mark("prompt_construction", prompt_started)

    diagnostics_base = {
        "request_id": request_id,
        "stage": policy.stage,
        "tier_1_contract_hash": projection.source_hashes.get("tier_1"),
        "design_contract_hash": projection.source_hashes.get("design_dna"),
        "page_purpose_hash": projection.source_hashes.get(
            "page_purpose_contract"
        ),
        "prompt_projection_hash": projection.prompt_projection_hash,
        "estimated_input_tokens": projection.estimated_input_tokens,
        "input_chars": projection.input_chars,
        "omitted_sections": list(projection.omitted_sections),
        "source_artifact_hashes": projection.source_hashes,
        "budgets": {
            "stage_wall_seconds": budgets.stage_wall_seconds,
            "max_provider_calls": budgets.max_provider_calls,
            "per_call_timeout_seconds": budgets.per_call_timeout_seconds,
            "max_validation_retries": budgets.max_validation_retries,
            "max_input_tokens": budgets.max_input_tokens,
            "max_output_tokens": budgets.max_output_tokens,
            "max_deterministic_repair": budgets.max_deterministic_repair,
            "max_ai_repair": budgets.max_ai_repair,
            "min_call_budget_seconds": budgets.min_call_budget_seconds,
        },
        "stage_deadline_wall_seconds": stage_deadline.wall_seconds,
        "timing_spans": spans.values,
        "attempts": attempts,
    }

    def _raise_terminal(
        message: str,
        *,
        result_class: ResultClass,
        reasons: list[str] | None = None,
        failure_code: str | None = None,
    ) -> None:
        payload = {
            **diagnostics_base,
            "timing_spans": dict(spans.values),
            "attempts": [attempt.__dict__ for attempt in attempts],
            "terminal_result": result_class,
            "redacted_failure_reason": _redact_reason(message),
            "failure_code": failure_code or "",
        }
        raise CompositionStageError(
            message,
            stage=policy.stage,
            retry_reasons=tuple(reasons or retry_reasons),
            result_class=result_class,
            diagnostics=payload,
            failure_code=failure_code,
        )

    if projection.estimated_input_tokens > budgets.max_input_tokens:
        _raise_terminal(
            f"{policy.stage} prompt projection exceeds max input tokens "
            f"({projection.estimated_input_tokens} > "
            f"{budgets.max_input_tokens}).",
            result_class="invalid_output",
        )

    max_attempts = min(
        budgets.max_provider_calls,
        1 + budgets.max_ai_repair,
        1 + budgets.max_validation_retries,
    )

    with ai_run_scope(request_id, purpose=f"v2_{policy.stage}"):
        with capture_ai_stage_telemetry() as captured:
            for attempt_index in range(max_attempts):
                if stage_deadline.exhausted():
                    _raise_terminal(
                        f"{policy.stage} exceeded its stage deadline.",
                        result_class="stage_deadline_exceeded",
                    )
                call_timeout = stage_deadline.call_timeout(
                    per_call_timeout=budgets.per_call_timeout_seconds,
                    min_call_budget=budgets.min_call_budget_seconds,
                )
                if call_timeout is None:
                    _raise_terminal(
                        f"{policy.stage} refused provider call; remaining "
                        "time below minimum safe call budget.",
                        result_class="stage_deadline_exceeded",
                    )

                # Deny BEFORE provider construction when budget is unavailable.
                if budget is not None:
                    approved, budget_code = budget.approve(
                        policy.stage,
                        attempt_type="ai",
                        wall_remaining=stage_deadline.remaining(),
                    )
                    if not approved:
                        _raise_terminal(
                            f"{policy.stage} denied by call budget: {budget_code}.",
                            result_class="invalid_output",
                            failure_code=budget_code,
                        )

                is_recovery = attempt_index > 0
                model = (
                    budgets.recovery_model
                    if is_recovery
                    else policy.model
                )
                attempt = AttemptRecord(
                    attempt_number=attempt_index + 1,
                    provider=str(
                        getattr(ai_provider, "name", "unknown") or "unknown"
                    ),
                    model=model,
                    prompt_projection_hash=projection.prompt_projection_hash,
                    estimated_input_tokens=projection.estimated_input_tokens,
                    output_token_ceiling=budgets.max_output_tokens,
                    started_at=_utc_now(),
                    remaining_deadline_seconds_at_start=(
                        stage_deadline.remaining()
                    ),
                    transport_attempts=1,
                )
                attempts.append(attempt)

                render_started = time.monotonic()
                if is_recovery:
                    prior = retry_reasons[-1] if retry_reasons else "{}"
                    repair = repair_prompt_values(
                        projection,
                        prior_reason=prior,
                        missing_page_ids=_missing_page_ids(
                            final_report, page_purpose
                        ),
                    )
                    prompt_values = {
                        "stage_input_json": repair["stage_input_json"],
                    }
                    validation_retry_json = prior
                else:
                    prompt_values = {
                        "stage_input_json": projection.stage_input_json,
                    }
                    validation_retry_json = "{}"
                prompt = template_renderer.render(
                    prompt_template,
                    **prompt_values,
                    output_schema_json=canonical_json(
                        BusinessComponentPlan.model_json_schema()
                    ),
                    prompt_revision=policy.prompt_revision,
                    validation_retry_json=validation_retry_json,
                )
                spans.mark(
                    "prompt_render" if not is_recovery else "repair_prompt",
                    render_started,
                )
                prompt_tokens_est = estimate_tokens(prompt)
                attempt.estimated_input_tokens = prompt_tokens_est
                if prompt_tokens_est > budgets.max_input_tokens:
                    attempt.result = "invalid_output"
                    attempt.redacted_failure_reason = (
                        "prompt exceeded max input tokens"
                    )
                    attempt.completed_at = _utc_now()
                    _raise_terminal(
                        f"{policy.stage} rendered prompt exceeds max input "
                        "tokens.",
                        result_class="invalid_output",
                    )

                provider_started = time.monotonic()

                def invoke() -> str:
                    return ai_provider.ask_chat(
                        model,
                        [{"role": "user", "content": prompt}],
                        max_tokens=budgets.max_output_tokens,
                        temperature=policy.temperature,
                        timeout_seconds=call_timeout,
                        transport_attempts=1,
                    )

                provider_calls += 1
                raw: str | None = None
                try:
                    raw = _invoke_provider_call(
                        invoke,
                        timeout_seconds=call_timeout,
                        stage=policy.stage,
                        ai_provider=ai_provider,
                    )
                    attempt.finish_reason = "completed"
                except CompositionStageError as exc:
                    attempt.provider_duration_ms = int(
                        (time.monotonic() - provider_started) * 1000
                    )
                    spans.mark("provider_request", provider_started)
                    attempt.cancelled = bool(
                        (exc.diagnostics or {}).get("provider_cancelled")
                    )
                    attempt.result = "provider_timeout"
                    attempt.redacted_failure_reason = _redact_reason(str(exc))
                    attempt.completed_at = _utc_now()
                    attempt.remaining_deadline_seconds_at_end = (
                        stage_deadline.remaining()
                    )
                    attempt.total_duration_ms = int(
                        (time.monotonic() - stage_started) * 1000
                    )
                    # Allow one bounded recovery only when budget remains.
                    can_recover = (
                        is_recovery is False
                        and budgets.max_ai_repair >= 1
                        and attempt_index + 1 < max_attempts
                        and stage_deadline.call_timeout(
                            per_call_timeout=(
                                budgets.per_call_timeout_seconds
                            ),
                            min_call_budget=(
                                budgets.min_call_budget_seconds
                            ),
                        )
                        is not None
                    )
                    if can_recover:
                        retry_reasons.append(
                            canonical_json(
                                {
                                    "kind": "provider_timeout",
                                    "timeout_seconds": call_timeout,
                                }
                            )[:4000]
                        )
                        continue
                    _raise_terminal(
                        str(exc),
                        result_class="provider_timeout",
                        reasons=retry_reasons
                        + [attempt.redacted_failure_reason],
                    )
                attempt.provider_duration_ms = int(
                    (time.monotonic() - provider_started) * 1000
                )
                spans.mark("provider_request", provider_started)
                spans.mark("response_completion", provider_started)
                attempt.partial_output_hash = _partial_hash(raw)

                parse_error: Exception | None = None
                report: CompositionValidationReport | None = None
                parse_started = time.monotonic()
                try:
                    candidate = _parse_strict(raw or "", BusinessComponentPlan)
                    spans.mark("json_parsing", parse_started)
                    attempt.parse_duration_ms = spans.values.get(
                        "json_parsing", 0
                    )
                    if budgets.max_deterministic_repair >= 1:
                        repair_started = time.monotonic()
                        candidate = normalize(candidate)
                        deterministic_repair_used = 1
                        spans.mark("deterministic_repair", repair_started)
                    validate_started = time.monotonic()
                    report = validator(candidate)
                    spans.mark("schema_validation", validate_started)
                    attempt.validation_duration_ms = spans.values.get(
                        "schema_validation", 0
                    )
                    if report.passed:
                        final_artifact = candidate
                        final_report = report
                        attempt.result = "completed"
                        attempt.completed_at = _utc_now()
                        attempt.remaining_deadline_seconds_at_end = (
                            stage_deadline.remaining()
                        )
                        attempt.total_duration_ms = int(
                            (time.monotonic() - stage_started) * 1000
                        )
                        break
                except Exception as exc:
                    parse_error = exc
                    spans.mark("json_parsing", parse_started)
                    attempt.parse_duration_ms = spans.values.get(
                        "json_parsing", 0
                    )

                reason = _retry_reason(parse_error, report)
                attempt.result = (
                    "validation_failed"
                    if report is not None
                    else "invalid_output"
                )
                attempt.redacted_failure_reason = _redact_reason(reason)
                attempt.completed_at = _utc_now()
                attempt.remaining_deadline_seconds_at_end = (
                    stage_deadline.remaining()
                )
                final_report = report
                if attempt_index + 1 >= max_attempts:
                    issue_codes = []
                    if report is not None:
                        issue_codes = [
                            issue.code for issue in report.issues[:8]
                        ]
                    detail = (
                        f" issues={issue_codes}" if issue_codes else ""
                    )
                    if not issue_codes and parse_error is not None:
                        detail = f" error={parse_error}"
                    _raise_terminal(
                        f"{policy.stage} failed strict validation.{detail}",
                        result_class=attempt.result,
                        reasons=retry_reasons + [reason],
                    )
                can_recover = (
                    budgets.max_ai_repair >= 1
                    and stage_deadline.call_timeout(
                        per_call_timeout=budgets.per_call_timeout_seconds,
                        min_call_budget=budgets.min_call_budget_seconds,
                    )
                    is not None
                )
                if not can_recover:
                    _raise_terminal(
                        f"{policy.stage} exhausted recovery budget.",
                        result_class="stage_deadline_exceeded",
                        reasons=retry_reasons + [reason],
                    )
                retry_reasons.append(reason)
                spans.mark("retry", time.monotonic())

    if final_artifact is None or final_report is None:
        _raise_terminal(
            f"{policy.stage} produced no valid artifact.",
            result_class="invalid_output",
        )

    persist_started = time.monotonic()
    events = captured.usage_events
    prompt_tokens = sum(int(item.get("prompt_tokens") or 0) for item in events)
    completion_tokens = sum(
        int(item.get("completion_tokens") or 0) for item in events
    )
    total_tokens = sum(
        int(
            item.get("total_tokens")
            or (
                int(item.get("prompt_tokens") or 0)
                + int(item.get("completion_tokens") or 0)
            )
        )
        for item in events
    )
    for attempt in attempts:
        if attempt.result == "completed":
            attempt.token_usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
    spans.mark("persistence_prepare", persist_started)
    metrics = CompositionStageMetrics(
        stage=policy.stage,
        effective_model=policy.model,
        provider=str(getattr(ai_provider, "name", "unknown") or "unknown"),
        model_family=policy.model_family,
        prompt_revision=policy.prompt_revision,
        cache_hit=False,
        provider_call_count=provider_calls,
        validation_retry_count=len(retry_reasons),
        validation_retry_reasons=tuple(retry_reasons),
        transport_retry_count=captured.transport_retry_count,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=sum(float(item.get("cost_usd") or 0.0) for item in events),
        latency_ms=int((time.monotonic() - stage_started) * 1000),
    )
    return BuiltCompositionArtifact(
        artifact=final_artifact,
        validation=final_report,
        metrics=metrics,
        diagnostics={
            **diagnostics_base,
            "timing_spans": dict(spans.values),
            "attempts": [attempt.__dict__ for attempt in attempts],
            "terminal_result": "completed",
            "deterministic_repair_used": deterministic_repair_used,
            "skeleton_page_ids": list(
                projection.skeleton.get("required_page_ids") or []
            ),
        },
    )


__all__ = [
    "AttemptRecord",
    "TimingSpans",
    "build_business_component_plan_artifact",
]
