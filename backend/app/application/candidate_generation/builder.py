"""Strict two-call batch generation and node-scoped repair runner."""
from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextvars import copy_context
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import ValidationError

from app.application.appspec.source import canonical_json
from app.application.candidate_generation.call_budget import (
    CandidateCallBudget,
    CandidateProviderAttempt,
)
from app.application.candidate_generation.policy import CandidateStagePolicy
from app.application.services.ai_context import (
    ai_run_scope,
    capture_ai_stage_telemetry,
)
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.schemas.preview_candidate import (
    CandidateStageMetrics,
    GeneratedCandidateBatch,
)
from app.infrastructure.ai_providers.model_capabilities import (
    CAPABILITY_PROFILE_REVISION,
    CONTEXT_RESERVE_TOKENS,
    MINIMUM_VALID_OUTPUT_TOKENS,
    clamp_max_tokens,
    estimate_prompt_tokens,
    resolve_model_capability,
)
from app.infrastructure.ai_providers.response_parser import (
    ProviderGenerationError,
    ProviderGenerationResult,
)
from app.shared.json_utils import extract_json_from_text


class CandidateStageError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        stage: str,
        diagnostics: tuple[str, ...] = (),
        provider_error_code: str = "",
        provider_diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.diagnostics = diagnostics
        self.provider_error_code = provider_error_code
        self.provider_diagnostics = provider_diagnostics or {}


@dataclass(frozen=True)
class BuiltCandidateBatch:
    batch: GeneratedCandidateBatch
    metrics: CandidateStageMetrics
    provider_attempt_id: str = ""
    idempotency_key: str = ""


def invoke_with_timeout(
    fn: Callable[[], str],
    *,
    timeout_seconds: float,
    stage: str,
) -> str:
    executor = ThreadPoolExecutor(max_workers=1)
    context = copy_context()
    future = executor.submit(context.run, fn)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeout as exc:
        future.cancel()
        raise CandidateStageError(
            f"{stage} exceeded its wall timeout of {timeout_seconds:.1f}s.",
            stage=stage,
        ) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _parse_batch(raw: str) -> GeneratedCandidateBatch:
    payload = extract_json_from_text(raw)
    if not isinstance(payload, dict):
        raise ValueError("Candidate output must be one JSON object.")
    return GeneratedCandidateBatch.model_validate(payload)


def _usage_metrics(
    *,
    policy: CandidateStagePolicy,
    provider: AIProvider,
    started: float,
    captured,
    repair: bool,
    repair_reason: str | None,
    provider_call_count: int | None = None,
) -> CandidateStageMetrics:
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
    calls = (
        provider_call_count
        if provider_call_count is not None
        else 1
    )
    return CandidateStageMetrics(
        stage=policy.stage if policy.stage != "validation" else "pages",
        effective_model=policy.model,
        provider=str(getattr(provider, "name", "unknown") or "unknown"),
        model_family=policy.model_family,
        prompt_revision=policy.prompt_revision,
        cache_hit=False,
        provider_call_count=calls,
        repair_call_count=1 if repair else 0,
        repair_reason=repair_reason,
        transport_retry_count=captured.transport_retry_count,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=sum(float(item.get("cost_usd") or 0.0) for item in events),
        latency_ms=int((time.monotonic() - started) * 1000),
    )


def _invoke_provider_text(
    *,
    ai_provider: AIProvider,
    model: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """Call ask_chat; application owns retries so transport attempts stay at 1."""
    try:
        return ai_provider.ask_chat(
            model,
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            transport_attempts=1,  # type: ignore[call-arg]
        )
    except TypeError:
        return ai_provider.ask_chat(
            model,
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )


def _request_shape_hash(
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    prompt_chars: int,
    message_count: int = 1,
) -> str:
    shape = {
        "endpoint": "POST /chat/completions",
        "model": model,
        "message_roles": ["user"],
        "message_count": message_count,
        "content_representation": "string",
        "approx_input_chars": prompt_chars,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": None,
        "json_schema": None,
        "strict_schema": None,
        "tools": None,
        "tool_choice": None,
        "stream": False,
        "capability_profile_revision": CAPABILITY_PROFILE_REVISION,
    }
    raw = json.dumps(shape, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _local_context_error(
    *,
    model: str,
    estimated_input_tokens: int,
    context_window: int,
    request_shape_hash: str,
) -> ProviderGenerationError:
    message = (
        f"Estimated prompt tokens ({estimated_input_tokens}) exceed model "
        f"context window ({context_window}) for {model}."
    )
    result = ProviderGenerationResult(
        provider="openrouter",
        model=model,
        provider_request_id="",
        response_format="provider_error",
        text="",
        structured_payload=None,
        finish_reason="",
        input_tokens=estimated_input_tokens,
        output_tokens=0,
        total_tokens=estimated_input_tokens,
        http_status=0,
        raw_payload_sha256="",
        is_success=False,
        error_code="provider_context_length_exceeded",
        error_message_redacted=message,
        retryable=False,
        refusal=False,
        truncated=False,
        latency_ms=0,
        response_top_level_keys=(),
        cost_usd=None,
        error_type="context_preflight",
        error_metadata_keys=("estimated_input_tokens", "context_window"),
    )
    # Attach shape hash via diagnostics consumers reading message + result.
    result_diagnostics = result.to_diagnostics()
    result_diagnostics["request_shape_hash"] = request_shape_hash
    return ProviderGenerationError(message, result=result)


def _preflight_fields(
    *,
    estimated_input_tokens: int,
    requested_output_tokens: int,
    clamped_output_tokens: int,
    context_window: int,
    approval_decision: str,
) -> dict[str, Any]:
    return {
        "context_window": int(context_window),
        "estimated_input_tokens": int(estimated_input_tokens),
        "requested_output_tokens": int(requested_output_tokens),
        "clamped_output_tokens": int(clamped_output_tokens),
        "minimum_output_allowance": MINIMUM_VALID_OUTPUT_TOKENS,
        "context_reserve": CONTEXT_RESERVE_TOKENS,
        "approval_decision": approval_decision,
    }


def _record_provider_error_attempt(
    *,
    budget: CandidateCallBudget | None,
    request_id: int,
    candidate_revision_uuid: str,
    stage: str,
    ai_provider: AIProvider,
    model: str,
    exc: ProviderGenerationError,
    retry_attempted: bool,
    terminal_decision: str,
    parent_attempt_id: str = "",
    idempotency_key: str = "",
    request_shape_hash: str = "",
    retry_decision_reason: str = "",
    fallback_model_decision: str = "",
    estimated_input_tokens: int | None = None,
    requested_output_tokens: int | None = None,
    clamped_output_tokens: int | None = None,
    context_window: int | None = None,
    approval_decision: str = "",
    attempt_id: str = "",
) -> str:
    attempt_id = attempt_id or (
        budget.new_attempt_id() if budget is not None else ""
    )
    result = exc.result
    if budget is not None:
        budget.record_attempt(
            CandidateProviderAttempt(
                attempt_id=attempt_id,
                request_id=request_id,
                candidate_revision_uuid=candidate_revision_uuid,
                substage=stage,
                provider=str(
                    getattr(ai_provider, "name", result.provider) or result.provider
                ),
                model=model,
                http_status=result.http_status,
                response_top_level_keys=list(result.response_top_level_keys),
                response_format=result.response_format,
                provider_request_id=result.provider_request_id,
                raw_payload_sha256=result.raw_payload_sha256,
                duration_ms=result.latency_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                total_tokens=result.total_tokens,
                typed_result=result.error_code or "provider_error",
                error_code=result.error_code,
                retryable=result.retryable,
                retry_attempted=retry_attempted,
                terminal_decision=terminal_decision,
                parent_attempt_id=parent_attempt_id,
                idempotency_key=idempotency_key,
                error_type=result.error_type,
                error_message_redacted=result.error_message_redacted,
                error_metadata_keys=list(result.error_metadata_keys),
                request_shape_hash=request_shape_hash,
                capability_profile_revision=CAPABILITY_PROFILE_REVISION,
                retry_decision_reason=retry_decision_reason,
                fallback_model_decision=fallback_model_decision,
                calls_remaining=budget.remaining_total(),
                context_window=context_window,
                estimated_input_tokens=estimated_input_tokens,
                requested_output_tokens=requested_output_tokens,
                clamped_output_tokens=clamped_output_tokens,
                minimum_output_allowance=(
                    MINIMUM_VALID_OUTPUT_TOKENS
                    if estimated_input_tokens is not None
                    else None
                ),
                context_reserve=(
                    CONTEXT_RESERVE_TOKENS
                    if estimated_input_tokens is not None
                    else None
                ),
                approval_decision=approval_decision,
            )
        )
    return attempt_id


def _record_preflight_attempt(
    *,
    budget: CandidateCallBudget | None,
    request_id: int,
    candidate_revision_uuid: str,
    stage: str,
    provider_name: str,
    model: str,
    request_shape_hash: str,
    fallback_model_decision: str,
    estimated_input_tokens: int,
    requested_output_tokens: int,
    clamped_output_tokens: int,
    context_window: int,
    approval_decision: str,
    typed_result: str,
    error_code: str = "",
    terminal_decision: str = "preflight_passed",
) -> str:
    if budget is None:
        return ""
    attempt_id = budget.new_attempt_id()
    budget.record_attempt(
        CandidateProviderAttempt(
            attempt_id=attempt_id,
            request_id=request_id,
            candidate_revision_uuid=candidate_revision_uuid,
            substage=stage,
            provider=provider_name,
            model=model,
            http_status=0,
            response_top_level_keys=[],
            response_format="preflight",
            provider_request_id="",
            raw_payload_sha256="",
            duration_ms=0,
            input_tokens=estimated_input_tokens,
            output_tokens=0,
            total_tokens=estimated_input_tokens,
            typed_result=typed_result,
            error_code=error_code,
            retryable=False,
            retry_attempted=False,
            terminal_decision=terminal_decision,
            idempotency_key=f"{candidate_revision_uuid}:{stage}:preflight",
            request_shape_hash=request_shape_hash,
            capability_profile_revision=CAPABILITY_PROFILE_REVISION,
            retry_decision_reason="capability_preflight",
            fallback_model_decision=fallback_model_decision,
            calls_remaining=budget.remaining_total(),
            **_preflight_fields(
                estimated_input_tokens=estimated_input_tokens,
                requested_output_tokens=requested_output_tokens,
                clamped_output_tokens=clamped_output_tokens,
                context_window=context_window,
                approval_decision=approval_decision,
            ),
        )
    )
    return attempt_id


def _stage_model_configuration_error(
    *,
    stage: str,
    code: str,
    message: str,
) -> CandidateStageError:
    return CandidateStageError(
        message,
        stage=stage,
        diagnostics=(message,),
        provider_error_code=code,
        provider_diagnostics={"error_code": code, "stage": stage},
    )


def _provider_stage_error(
    *,
    stage: str,
    exc: ProviderGenerationError,
) -> CandidateStageError:
    return CandidateStageError(
        f"{stage} provider call failed: {exc.error_code}",
        stage=stage,
        diagnostics=(exc.result.error_message_redacted,),
        provider_error_code=exc.error_code,
        provider_diagnostics=exc.result.to_diagnostics(),
    )


def _resolve_effective_model(policy: CandidateStagePolicy) -> tuple[str, str]:
    """Return (model, fallback_decision)."""

    primary = policy.model
    fallback = str(
        getattr(settings, "V2_CANDIDATE_COMPONENT_FALLBACK_MODEL", "") or ""
    ).strip()
    if policy.stage != "business_components" or not fallback or fallback == primary:
        return primary, "primary_only"
    primary_cap = resolve_model_capability(primary)
    fallback_cap = resolve_model_capability(fallback)
    if not primary_cap.known:
        return primary, "primary_capability_unknown"
    if not fallback_cap.known:
        return primary, "fallback_capability_unknown"
    if fallback_cap.context_window <= primary_cap.context_window:
        return primary, "fallback_not_larger"
    return primary, f"fallback_available:{fallback}"


def build_ai_batch(
    *,
    request_id: int,
    policy: CandidateStagePolicy,
    prompt_template: str,
    prompt_values: dict[str, Any],
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    phase_deadline: float,
    call_budget: CandidateCallBudget | None = None,
    candidate_revision_uuid: str = "",
    on_in_flight: Callable[[dict[str, Any]], None] | None = None,
) -> BuiltCandidateBatch:
    if not policy.ai_authored or policy.stage not in {
        "business_components",
        "pages",
    }:
        raise ValueError("Only Phase 3B component/page policies may generate.")
    started = time.monotonic()
    remaining = min(
        phase_deadline - started,
        float(policy.timeout_seconds),
    )
    if remaining <= 0:
        raise CandidateStageError(
            "Phase 3B wall deadline expired.",
            stage=policy.stage,
        )
    prompt = template_renderer.render(
        prompt_template,
        **prompt_values,
        output_schema_json=canonical_json(
            GeneratedCandidateBatch.model_json_schema()
        ),
        prompt_revision=policy.prompt_revision,
    )
    provider_name = str(getattr(ai_provider, "name", "unknown") or "unknown")
    primary_model, fallback_decision = _resolve_effective_model(policy)
    model = primary_model

    # Components/pages: fail closed on missing/unknown model. Never inherit
    # PREVIEW_APP_MODEL or silently fall back to deepseek/deepseek-chat.
    if policy.stage in {"business_components", "pages"}:
        if policy.stage == "business_components":
            not_configured = "candidate_component_model_not_configured"
            capability_unknown = "candidate_component_model_capability_unknown"
            stage_label = "business_components"
            env_name = "V2_CANDIDATE_COMPONENT_MODEL"
            no_fallback_note = (
                "business_components stage fails closed without falling back "
                "to PREVIEW_APP_MODEL or deepseek/deepseek-chat."
            )
        else:
            not_configured = "candidate_page_model_not_configured"
            capability_unknown = "candidate_page_model_capability_unknown"
            stage_label = "pages"
            env_name = "V2_CANDIDATE_PAGE_MODEL"
            no_fallback_note = (
                "pages stage fails closed without falling back to the "
                "component model."
            )
        if not str(model or "").strip():
            raise _stage_model_configuration_error(
                stage=policy.stage,
                code=not_configured,
                message=(
                    f"{env_name} is not configured; {no_fallback_note}"
                ),
            )
        stage_capability = resolve_model_capability(model)
        if not stage_capability.known:
            _record_preflight_attempt(
                budget=call_budget,
                request_id=request_id,
                candidate_revision_uuid=candidate_revision_uuid,
                stage=policy.stage,
                provider_name=provider_name,
                model=model,
                request_shape_hash="",
                fallback_model_decision="primary_only",
                estimated_input_tokens=0,
                requested_output_tokens=policy.max_tokens,
                clamped_output_tokens=0,
                context_window=0,
                approval_decision="denied_preflight",
                typed_result=capability_unknown,
                error_code=capability_unknown,
                terminal_decision="fail_closed_preflight",
            )
            raise _stage_model_configuration_error(
                stage=policy.stage,
                code=capability_unknown,
                message=(
                    f"{stage_label} model {model!r} has no explicit "
                    f"capability profile; {no_fallback_note}"
                ),
            )

    capability = resolve_model_capability(model)
    estimated_input = estimate_prompt_tokens(prompt)
    effective_max_tokens = clamp_max_tokens(
        requested_max_tokens=policy.max_tokens,
        estimated_input_tokens=estimated_input,
        context_window=capability.context_window,
    )
    shape_hash = _request_shape_hash(
        model=model,
        max_tokens=effective_max_tokens,
        temperature=policy.temperature,
        prompt_chars=len(prompt),
    )

    # If primary context is too small, optionally switch to one approved fallback.
    # Pages never use the component fallback chain.
    fallback_model = str(
        getattr(settings, "V2_CANDIDATE_COMPONENT_FALLBACK_MODEL", "") or ""
    ).strip()
    if (
        policy.stage == "business_components"
        and capability.known
        and estimated_input >= capability.context_window
        and fallback_model
        and fallback_model != model
    ):
        fallback_cap = resolve_model_capability(fallback_model)
        if (
            fallback_cap.known
            and fallback_cap.context_window > capability.context_window
        ):
            model = fallback_model
            capability = fallback_cap
            effective_max_tokens = clamp_max_tokens(
                requested_max_tokens=policy.max_tokens,
                estimated_input_tokens=estimated_input,
                context_window=capability.context_window,
            )
            shape_hash = _request_shape_hash(
                model=model,
                max_tokens=effective_max_tokens,
                temperature=policy.temperature,
                prompt_chars=len(prompt),
            )
            fallback_decision = f"selected_fallback:{fallback_model}"

    if estimated_input >= capability.context_window or effective_max_tokens <= 0:
        preflight_exc = _local_context_error(
            model=model,
            estimated_input_tokens=estimated_input,
            context_window=capability.context_window,
            request_shape_hash=shape_hash,
        )
        _record_provider_error_attempt(
            budget=call_budget,
            request_id=request_id,
            candidate_revision_uuid=candidate_revision_uuid,
            stage=policy.stage,
            ai_provider=ai_provider,
            model=model,
            exc=preflight_exc,
            retry_attempted=False,
            terminal_decision="fail_closed_preflight",
            idempotency_key=f"{candidate_revision_uuid}:{policy.stage}:preflight",
            request_shape_hash=shape_hash,
            retry_decision_reason="context_preflight_non_retryable",
            fallback_model_decision=fallback_decision,
            estimated_input_tokens=estimated_input,
            requested_output_tokens=policy.max_tokens,
            clamped_output_tokens=effective_max_tokens,
            context_window=capability.context_window,
            approval_decision="denied_preflight",
        )
        raise _provider_stage_error(stage=policy.stage, exc=preflight_exc)

    _record_preflight_attempt(
        budget=call_budget,
        request_id=request_id,
        candidate_revision_uuid=candidate_revision_uuid,
        stage=policy.stage,
        provider_name=provider_name,
        model=model,
        request_shape_hash=shape_hash,
        fallback_model_decision=fallback_decision,
        estimated_input_tokens=estimated_input,
        requested_output_tokens=policy.max_tokens,
        clamped_output_tokens=effective_max_tokens,
        context_window=capability.context_window,
        approval_decision="approved_preflight",
        typed_result="preflight_passed",
    )

    idempotency = f"{candidate_revision_uuid}:{policy.stage}:gen:0"
    current_attempt_id = (
        call_budget.new_attempt_id() if call_budget is not None else ""
    )
    current_idempotency = idempotency
    if call_budget is not None:
        approved, deny_code = call_budget.approve(
            policy.stage,
            attempt_type="ai",
            provider=provider_name,
            model=model,
            idempotency_key=idempotency,
        )
        if not approved:
            raise CandidateStageError(
                f"{policy.stage} denied by candidate call budget ({deny_code}).",
                stage=policy.stage,
                provider_error_code=deny_code,
            )
    if on_in_flight is not None:
        on_in_flight(
            {
                "attempt_id": current_attempt_id,
                "candidate_revision_uuid": candidate_revision_uuid,
                "stage": policy.stage,
                "provider": provider_name,
                "model": model,
                "idempotency_key": current_idempotency,
                "request_shape_hash": shape_hash,
                "fallback_model_decision": fallback_decision,
            }
        )

    calls_used = 1
    successful_parent_attempt_id = ""
    with ai_run_scope(request_id, purpose=f"v2_candidate_{policy.stage}"):
        with capture_ai_stage_telemetry() as captured:

            def invoke() -> str:
                return _invoke_provider_text(
                    ai_provider=ai_provider,
                    model=model,
                    prompt=prompt,
                    max_tokens=effective_max_tokens,
                    temperature=policy.temperature,
                )

            try:
                raw = invoke_with_timeout(
                    invoke,
                    timeout_seconds=remaining,
                    stage=policy.stage,
                )
            except ProviderGenerationError as exc:
                parent_attempt = _record_provider_error_attempt(
                    budget=call_budget,
                    request_id=request_id,
                    candidate_revision_uuid=candidate_revision_uuid,
                    stage=policy.stage,
                    ai_provider=ai_provider,
                    model=model,
                    exc=exc,
                    retry_attempted=False,
                    terminal_decision=(
                        "retry_pending" if exc.retryable else "fail_closed"
                    ),
                    attempt_id=current_attempt_id,
                    idempotency_key=idempotency,
                    request_shape_hash=shape_hash,
                    retry_decision_reason=(
                        "retryable_provider_error"
                        if exc.retryable
                        else f"non_retryable:{exc.error_code}"
                    ),
                    fallback_model_decision=fallback_decision,
                )
                if not exc.retryable or call_budget is None:
                    raise _provider_stage_error(
                        stage=policy.stage, exc=exc
                    ) from exc
                retry_key = f"{candidate_revision_uuid}:{policy.stage}:gen:1"
                retry_attempt_id = call_budget.new_attempt_id()
                approved, deny_code = call_budget.approve(
                    policy.stage,
                    attempt_type="ai_retry",
                    provider=provider_name,
                    model=model,
                    idempotency_key=retry_key,
                )
                if not approved:
                    _record_provider_error_attempt(
                        budget=call_budget,
                        request_id=request_id,
                        candidate_revision_uuid=candidate_revision_uuid,
                        stage=policy.stage,
                        ai_provider=ai_provider,
                        model=model,
                        exc=exc,
                        retry_attempted=False,
                        terminal_decision="fail_closed_no_budget",
                        attempt_id=retry_attempt_id,
                        parent_attempt_id=parent_attempt,
                        idempotency_key=retry_key,
                        request_shape_hash=shape_hash,
                        retry_decision_reason=deny_code
                        or "candidate_no_budget_for_provider_retry",
                        fallback_model_decision=fallback_decision,
                    )
                    raise CandidateStageError(
                        (
                            f"{policy.stage} provider retry denied "
                            f"({deny_code or 'candidate_no_budget_for_provider_retry'})."
                        ),
                        stage=policy.stage,
                        diagnostics=(exc.result.error_message_redacted,),
                        provider_error_code=exc.error_code,
                        provider_diagnostics=exc.result.to_diagnostics(),
                    ) from exc
                if time.monotonic() >= phase_deadline:
                    raise CandidateStageError(
                        "Phase 3B wall deadline expired before provider retry.",
                        stage=policy.stage,
                        provider_error_code=exc.error_code,
                        provider_diagnostics=exc.result.to_diagnostics(),
                    ) from exc
                calls_used = 2
                successful_parent_attempt_id = parent_attempt
                current_attempt_id = retry_attempt_id
                current_idempotency = retry_key
                if on_in_flight is not None:
                    on_in_flight(
                        {
                            "attempt_id": current_attempt_id,
                            "candidate_revision_uuid": candidate_revision_uuid,
                            "stage": policy.stage,
                            "provider": provider_name,
                            "model": model,
                            "idempotency_key": current_idempotency,
                            "request_shape_hash": shape_hash,
                            "fallback_model_decision": fallback_decision,
                        }
                    )
                try:
                    raw = invoke_with_timeout(
                        invoke,
                        timeout_seconds=max(
                            1.0, phase_deadline - time.monotonic()
                        ),
                        stage=policy.stage,
                    )
                except ProviderGenerationError as retry_exc:
                    _record_provider_error_attempt(
                        budget=call_budget,
                        request_id=request_id,
                        candidate_revision_uuid=candidate_revision_uuid,
                        stage=policy.stage,
                        ai_provider=ai_provider,
                        model=model,
                        exc=retry_exc,
                        retry_attempted=True,
                        terminal_decision="fail_closed",
                        attempt_id=current_attempt_id,
                        parent_attempt_id=parent_attempt,
                        idempotency_key=retry_key,
                        request_shape_hash=shape_hash,
                        retry_decision_reason=f"retry_failed:{retry_exc.error_code}",
                        fallback_model_decision=fallback_decision,
                    )
                    raise _provider_stage_error(
                        stage=policy.stage, exc=retry_exc
                    ) from retry_exc
    try:
        batch = _parse_batch(raw)
    except (ValueError, ValidationError) as exc:
        raise CandidateStageError(
            f"{policy.stage} returned invalid structured output.",
            stage=policy.stage,
            diagnostics=(str(exc)[:4000],),
            provider_error_code="provider_structured_output_invalid",
        ) from exc
    if batch.batch_kind != policy.stage:
        raise CandidateStageError(
            f"{policy.stage} returned the wrong batch kind.",
            stage=policy.stage,
        )
    metrics = _usage_metrics(
        policy=policy,
        provider=ai_provider,
        started=started,
        captured=captured,
        repair=False,
        repair_reason=None,
        provider_call_count=calls_used,
    )
    if call_budget is not None and current_attempt_id:
        call_budget.record_attempt(
            CandidateProviderAttempt(
                attempt_id=current_attempt_id,
                request_id=request_id,
                candidate_revision_uuid=candidate_revision_uuid,
                substage=policy.stage,
                provider=provider_name,
                model=model,
                http_status=200,
                response_top_level_keys=sorted(
                    batch.model_dump(mode="json").keys()
                ),
                response_format="structured_json",
                provider_request_id="",
                raw_payload_sha256=hashlib.sha256(
                    raw.encode("utf-8")
                ).hexdigest(),
                duration_ms=metrics.latency_ms,
                input_tokens=metrics.prompt_tokens,
                output_tokens=metrics.completion_tokens,
                total_tokens=metrics.total_tokens,
                typed_result="completed",
                error_code="",
                retryable=False,
                retry_attempted=calls_used > 1,
                terminal_decision="completed",
                parent_attempt_id=successful_parent_attempt_id,
                idempotency_key=current_idempotency,
                error_type="",
                error_message_redacted="",
                error_metadata_keys=[],
                request_shape_hash=shape_hash,
                capability_profile_revision=CAPABILITY_PROFILE_REVISION,
                retry_decision_reason="",
                fallback_model_decision=fallback_decision,
                calls_remaining=call_budget.remaining_total(),
                context_window=capability.context_window,
                estimated_input_tokens=estimated_input,
                requested_output_tokens=policy.max_tokens,
                clamped_output_tokens=effective_max_tokens,
                minimum_output_allowance=MINIMUM_VALID_OUTPUT_TOKENS,
                context_reserve=CONTEXT_RESERVE_TOKENS,
                approval_decision="approved",
            )
        )
    return BuiltCandidateBatch(
        batch=batch,
        metrics=metrics,
        provider_attempt_id=current_attempt_id,
        idempotency_key=current_idempotency,
    )


def repair_ai_batch(
    *,
    request_id: int,
    batch_stage: str,
    policy: CandidateStagePolicy,
    batch: GeneratedCandidateBatch,
    diagnostics: tuple[str, ...],
    canonical_bindings: dict[str, Any],
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    prompt_template: str,
    phase_deadline: float,
    call_budget: CandidateCallBudget | None = None,
    candidate_revision_uuid: str = "",
) -> BuiltCandidateBatch:
    started = time.monotonic()
    remaining = min(
        phase_deadline - started,
        float(policy.timeout_seconds),
    )
    if remaining <= 0:
        raise CandidateStageError(
            "Candidate repair deadline expired.",
            stage=batch_stage,
            diagnostics=diagnostics,
        )
    prompt = template_renderer.render(
        prompt_template,
        batch_kind=batch_stage,
        failed_batch_json=canonical_json(batch.model_dump(mode="json")),
        diagnostics_json=canonical_json(list(diagnostics)),
        canonical_bindings_json=canonical_json(canonical_bindings),
        output_schema_json=canonical_json(
            GeneratedCandidateBatch.model_json_schema()
        ),
        prompt_revision=policy.prompt_revision,
    )
    provider_name = str(getattr(ai_provider, "name", "unknown") or "unknown")
    idempotency = f"{candidate_revision_uuid}:{batch_stage}:repair:0"
    if call_budget is not None:
        approved, deny_code = call_budget.approve(
            batch_stage,
            attempt_type="ai_repair",
            provider=provider_name,
            model=policy.model,
            idempotency_key=idempotency,
        )
        if not approved:
            raise CandidateStageError(
                f"{batch_stage} repair denied by candidate call budget ({deny_code}).",
                stage=batch_stage,
                diagnostics=diagnostics,
                provider_error_code=deny_code,
            )
    with ai_run_scope(request_id, purpose=f"v2_candidate_{batch_stage}_repair"):
        with capture_ai_stage_telemetry() as captured:

            def invoke() -> str:
                return _invoke_provider_text(
                    ai_provider=ai_provider,
                    model=policy.model,
                    prompt=prompt,
                    max_tokens=policy.max_tokens,
                    temperature=policy.temperature,
                )

            try:
                raw = invoke_with_timeout(
                    invoke,
                    timeout_seconds=remaining,
                    stage=f"{batch_stage}_repair",
                )
            except ProviderGenerationError as exc:
                _record_provider_error_attempt(
                    budget=call_budget,
                    request_id=request_id,
                    candidate_revision_uuid=candidate_revision_uuid,
                    stage=batch_stage,
                    ai_provider=ai_provider,
                    model=policy.model,
                    exc=exc,
                    retry_attempted=False,
                    terminal_decision="fail_closed",
                    idempotency_key=idempotency,
                )
                raise _provider_stage_error(
                    stage=batch_stage, exc=exc
                ) from exc
    try:
        repaired = _parse_batch(raw)
    except Exception as exc:
        raise CandidateStageError(
            "Candidate repair returned invalid structured output.",
            stage=batch_stage,
            diagnostics=diagnostics + (str(exc)[:4000],),
            provider_error_code="provider_structured_output_invalid",
        ) from exc
    original_paths = tuple(item.path for item in batch.files)
    repaired_paths = tuple(item.path for item in repaired.files)
    if (
        repaired.batch_kind != batch.batch_kind
        or repaired_paths != original_paths
    ):
        raise CandidateStageError(
            "Candidate repair attempted to change batch ownership.",
            stage=batch_stage,
            diagnostics=diagnostics,
        )
    metrics = _usage_metrics(
        policy=policy,
        provider=ai_provider,
        started=started,
        captured=captured,
        repair=True,
        repair_reason=canonical_json(list(diagnostics))[:4000],
    )
    metrics = metrics.model_copy(update={"stage": batch_stage})
    return BuiltCandidateBatch(batch=repaired, metrics=metrics)


def combine_generation_and_repair_metrics(
    generation: CandidateStageMetrics,
    repair: CandidateStageMetrics,
) -> CandidateStageMetrics:
    if generation.stage != repair.stage or repair.repair_call_count != 1:
        raise ValueError("Candidate repair metrics do not match generation.")
    return generation.model_copy(
        update={
            "effective_model": (
                f"{generation.effective_model};repair={repair.effective_model}"
            ),
            "model_family": (
                f"{generation.model_family};repair={repair.model_family}"
            ),
            "prompt_revision": (
                f"{generation.prompt_revision}+{repair.prompt_revision}"
            )[:64],
            "provider_call_count": (
                generation.provider_call_count + repair.repair_call_count
            ),
            "repair_call_count": 1,
            "repair_reason": repair.repair_reason,
            "transport_retry_count": (
                generation.transport_retry_count
                + repair.transport_retry_count
            ),
            "prompt_tokens": generation.prompt_tokens + repair.prompt_tokens,
            "completion_tokens": (
                generation.completion_tokens + repair.completion_tokens
            ),
            "total_tokens": generation.total_tokens + repair.total_tokens,
            "cost_usd": generation.cost_usd + repair.cost_usd,
            "latency_ms": generation.latency_ms + repair.latency_ms,
        }
    )


__all__ = [
    "BuiltCandidateBatch",
    "CandidateStageError",
    "build_ai_batch",
    "combine_generation_and_repair_metrics",
    "invoke_with_timeout",
    "repair_ai_batch",
]
