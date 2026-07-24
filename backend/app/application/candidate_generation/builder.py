"""Strict two-call batch generation and node-scoped repair runner."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextvars import copy_context
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import ValidationError

from app.application.appspec.source import canonical_json
from app.application.candidate_generation.policy import CandidateStagePolicy
from app.application.services.ai_context import (
    ai_run_scope,
    capture_ai_stage_telemetry,
)
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.schemas.preview_candidate import (
    CandidateStageMetrics,
    GeneratedCandidateBatch,
)
from app.shared.json_utils import extract_json_from_text


class CandidateStageError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        stage: str,
        diagnostics: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.diagnostics = diagnostics


@dataclass(frozen=True)
class BuiltCandidateBatch:
    batch: GeneratedCandidateBatch
    metrics: CandidateStageMetrics


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
    return CandidateStageMetrics(
        stage=policy.stage if policy.stage != "validation" else "pages",
        effective_model=policy.model,
        provider=str(getattr(provider, "name", "unknown") or "unknown"),
        model_family=policy.model_family,
        prompt_revision=policy.prompt_revision,
        cache_hit=False,
        provider_call_count=2 if repair else 1,
        repair_call_count=1 if repair else 0,
        repair_reason=repair_reason,
        transport_retry_count=captured.transport_retry_count,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=sum(float(item.get("cost_usd") or 0.0) for item in events),
        latency_ms=int((time.monotonic() - started) * 1000),
    )


def build_ai_batch(
    *,
    request_id: int,
    policy: CandidateStagePolicy,
    prompt_template: str,
    prompt_values: dict[str, Any],
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    phase_deadline: float,
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
    with ai_run_scope(request_id, purpose=f"v2_candidate_{policy.stage}"):
        with capture_ai_stage_telemetry() as captured:

            def invoke() -> str:
                return ai_provider.ask_chat(
                    policy.model,
                    [{"role": "user", "content": prompt}],
                    max_tokens=policy.max_tokens,
                    temperature=policy.temperature,
                )

            raw = invoke_with_timeout(
                invoke,
                timeout_seconds=remaining,
                stage=policy.stage,
            )
    try:
        batch = _parse_batch(raw)
    except (ValueError, ValidationError) as exc:
        raise CandidateStageError(
            f"{policy.stage} returned invalid structured output.",
            stage=policy.stage,
            diagnostics=(str(exc)[:4000],),
        ) from exc
    if batch.batch_kind != policy.stage:
        raise CandidateStageError(
            f"{policy.stage} returned the wrong batch kind.",
            stage=policy.stage,
        )
    return BuiltCandidateBatch(
        batch=batch,
        metrics=_usage_metrics(
            policy=policy,
            provider=ai_provider,
            started=started,
            captured=captured,
            repair=False,
            repair_reason=None,
        ),
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
    with ai_run_scope(request_id, purpose=f"v2_candidate_{batch_stage}_repair"):
        with capture_ai_stage_telemetry() as captured:

            def invoke() -> str:
                return ai_provider.ask_chat(
                    policy.model,
                    [{"role": "user", "content": prompt}],
                    max_tokens=policy.max_tokens,
                    temperature=policy.temperature,
                )

            raw = invoke_with_timeout(
                invoke,
                timeout_seconds=remaining,
                stage=f"{batch_stage}_repair",
            )
    try:
        repaired = _parse_batch(raw)
    except Exception as exc:
        raise CandidateStageError(
            "Candidate repair returned invalid structured output.",
            stage=batch_stage,
            diagnostics=diagnostics + (str(exc)[:4000],),
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
    metrics = metrics.model_copy(
        update={"stage": batch_stage}
    )
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
            "provider_call_count": 2,
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
