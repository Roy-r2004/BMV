"""Strict structured-output runner for the three Phase 2 AI stages."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextvars import copy_context
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from app.application.appspec.source import canonical_json
from app.application.design_contract.policy import DesignStagePolicy
from app.application.services.ai_context import (
    ai_run_scope,
    capture_ai_stage_telemetry,
)
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.schemas.design_contract import (
    DesignStageMetrics,
    DesignValidationReport,
)
from app.shared.json_utils import extract_json_from_text


ArtifactT = TypeVar("ArtifactT", bound=BaseModel)


class DesignStageError(RuntimeError):
    """A stage timed out or exhausted strict schema/validation attempts."""

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
class BuiltDesignArtifact:
    artifact: BaseModel
    validation: DesignValidationReport
    metrics: DesignStageMetrics


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
        raise DesignStageError(
            f"{stage} exceeded its wall timeout of "
            f"{timeout_seconds:.1f} seconds.",
            stage=stage,
        ) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _parse_artifact(raw: str, schema: type[ArtifactT]) -> ArtifactT:
    payload = extract_json_from_text(raw)
    if not isinstance(payload, dict):
        raise ValueError("Structured stage output must be one JSON object")
    return schema.model_validate(payload)


def _retry_reason(
    *,
    parse_error: Exception | None,
    report: DesignValidationReport | None,
) -> str:
    if parse_error is not None:
        if isinstance(parse_error, ValidationError):
            errors = parse_error.errors(include_url=False)
            return canonical_json(
                {
                    "kind": "schema_validation",
                    "errors": errors[:20],
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


def build_structured_artifact(
    *,
    request_id: int,
    policy: DesignStagePolicy,
    schema: type[ArtifactT],
    prompt_template: str,
    prompt_values: dict[str, Any],
    validator: Callable[[ArtifactT], DesignValidationReport],
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    phase_deadline: float,
    vision_image_path: str | None = None,
    normalize: Callable[[ArtifactT], ArtifactT] | None = None,
) -> BuiltDesignArtifact:
    """Generate one valid artifact, retrying only strict validation failures."""

    phase_started = time.monotonic()
    provider_calls = 0
    retry_reasons: list[str] = []
    final_artifact: ArtifactT | None = None
    final_report: DesignValidationReport | None = None
    with ai_run_scope(request_id, purpose=f"v2_{policy.stage}"):
        with capture_ai_stage_telemetry() as captured:
            for attempt in range(policy.max_attempts):
                remaining_phase = phase_deadline - time.monotonic()
                # Each attempt gets a fresh stage budget so retries are useful.
                timeout = min(remaining_phase, float(policy.timeout_seconds))
                if timeout <= 0:
                    raise DesignStageError(
                        f"{policy.stage} exceeded the design-contract deadline.",
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
                    if policy.use_vision:
                        if not vision_image_path:
                            raise DesignStageError(
                                "Vision routing requires a local reference image.",
                                stage=policy.stage,
                            )
                        return ai_provider.ask_vision(
                            policy.model,
                            prompt,
                            vision_image_path,
                        )
                    return ai_provider.ask_chat(
                        policy.model,
                        [{"role": "user", "content": prompt}],
                        max_tokens=policy.max_tokens,
                        temperature=policy.temperature,
                    )

                provider_calls += 1
                raw = _invoke_with_timeout(
                    invoke,
                    timeout_seconds=timeout,
                    stage=policy.stage,
                )
                parse_error: Exception | None = None
                report: DesignValidationReport | None = None
                try:
                    candidate = _parse_artifact(raw, schema)
                    if normalize is not None:
                        candidate = normalize(candidate)
                    report = validator(candidate)
                    if report.passed:
                        final_artifact = candidate
                        final_report = report
                        break
                except Exception as exc:
                    parse_error = exc
                reason = _retry_reason(
                    parse_error=parse_error,
                    report=report,
                )
                if attempt + 1 >= policy.max_attempts:
                    issue_codes = []
                    if report is not None:
                        issue_codes = [
                            issue.code for issue in report.issues[:8]
                        ]
                    detail = (
                        f" issues={issue_codes}" if issue_codes else ""
                    )
                    raise DesignStageError(
                        f"{policy.stage} failed strict validation.{detail}",
                        stage=policy.stage,
                        retry_reasons=tuple(retry_reasons + [reason]),
                    )
                retry_reasons.append(reason)

    if final_artifact is None or final_report is None:
        raise DesignStageError(
            f"{policy.stage} produced no valid artifact.",
            stage=policy.stage,
            retry_reasons=tuple(retry_reasons),
        )
    usage_events = captured.usage_events
    prompt_tokens = sum(int(item.get("prompt_tokens") or 0) for item in usage_events)
    completion_tokens = sum(
        int(item.get("completion_tokens") or 0) for item in usage_events
    )
    total_tokens = sum(
        int(
            item.get("total_tokens")
            or (
                int(item.get("prompt_tokens") or 0)
                + int(item.get("completion_tokens") or 0)
            )
        )
        for item in usage_events
    )
    metrics = DesignStageMetrics(
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
        cost_usd=float(
            sum(float(item.get("cost_usd") or 0.0) for item in usage_events)
        ),
        latency_ms=int((time.monotonic() - phase_started) * 1000),
    )
    return BuiltDesignArtifact(
        artifact=final_artifact,
        validation=final_report,
        metrics=metrics,
    )


__all__ = [
    "BuiltDesignArtifact",
    "DesignStageError",
    "build_structured_artifact",
]
