"""Strict structured-output runner for the two Phase 3A AI stages."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextvars import copy_context
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from app.application.appspec.source import canonical_json
from app.application.composition_contract.policy import (
    CompositionStagePolicy,
)
from app.application.services.ai_context import (
    ai_run_scope,
    capture_ai_stage_telemetry,
)
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.schemas.composition_contract import (
    CompositionStageMetrics,
    CompositionValidationReport,
)
from app.shared.json_utils import extract_json_from_text


ArtifactT = TypeVar("ArtifactT", bound=BaseModel)


class CompositionStageError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        stage: str,
        retry_reasons: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.retry_reasons = retry_reasons


@dataclass(frozen=True)
class BuiltCompositionArtifact:
    artifact: BaseModel
    validation: CompositionValidationReport
    metrics: CompositionStageMetrics


def _invoke_with_timeout(
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
        raise CompositionStageError(
            f"{stage} exceeded its wall timeout of "
            f"{timeout_seconds:.1f} seconds.",
            stage=stage,
        ) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


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


def build_ai_composition_artifact(
    *,
    request_id: int,
    policy: CompositionStagePolicy,
    schema: type[ArtifactT],
    prompt_template: str,
    prompt_values: dict[str, Any],
    validator: Callable[[ArtifactT], CompositionValidationReport],
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    phase_deadline: float,
) -> BuiltCompositionArtifact:
    if not policy.ai_authored:
        raise ValueError("Deterministic stages cannot call the AI builder")
    started = time.monotonic()
    provider_calls = 0
    retry_reasons: list[str] = []
    final_artifact: ArtifactT | None = None
    final_report: CompositionValidationReport | None = None
    with ai_run_scope(request_id, purpose=f"v2_{policy.stage}"):
        with capture_ai_stage_telemetry() as captured:
            for attempt in range(policy.max_attempts):
                remaining = min(
                    phase_deadline - time.monotonic(),
                    policy.timeout_seconds - (time.monotonic() - started),
                )
                if remaining <= 0:
                    raise CompositionStageError(
                        f"{policy.stage} exceeded the Phase 3A deadline.",
                        stage=policy.stage,
                        retry_reasons=tuple(retry_reasons),
                    )
                prompt = template_renderer.render(
                    prompt_template,
                    **prompt_values,
                    output_schema_json=canonical_json(
                        schema.model_json_schema()
                    ),
                    prompt_revision=policy.prompt_revision,
                    validation_retry_json=(
                        retry_reasons[-1] if retry_reasons else "{}"
                    ),
                )

                def invoke() -> str:
                    return ai_provider.ask_chat(
                        policy.model,
                        [{"role": "user", "content": prompt}],
                        max_tokens=policy.max_tokens,
                        temperature=policy.temperature,
                    )

                provider_calls += 1
                raw = _invoke_with_timeout(
                    invoke,
                    timeout_seconds=remaining,
                    stage=policy.stage,
                )
                parse_error: Exception | None = None
                report: CompositionValidationReport | None = None
                try:
                    payload = extract_json_from_text(raw)
                    if not isinstance(payload, dict):
                        raise ValueError(
                            "Structured output must be one JSON object"
                        )
                    candidate = schema.model_validate(payload)
                    report = validator(candidate)
                    if report.passed:
                        final_artifact = candidate
                        final_report = report
                        break
                except Exception as exc:
                    parse_error = exc
                reason = _retry_reason(parse_error, report)
                if attempt + 1 >= policy.max_attempts:
                    raise CompositionStageError(
                        f"{policy.stage} failed strict validation.",
                        stage=policy.stage,
                        retry_reasons=tuple(retry_reasons + [reason]),
                    )
                retry_reasons.append(reason)

    if final_artifact is None or final_report is None:
        raise CompositionStageError(
            f"{policy.stage} produced no valid artifact.",
            stage=policy.stage,
            retry_reasons=tuple(retry_reasons),
        )
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
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    return BuiltCompositionArtifact(
        artifact=final_artifact,
        validation=final_report,
        metrics=metrics,
    )


__all__ = [
    "BuiltCompositionArtifact",
    "CompositionStageError",
    "build_ai_composition_artifact",
]
