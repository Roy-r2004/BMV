"""Strict multimodal Phase 5 invocations with no schema retry."""
from __future__ import annotations

import base64
import mimetypes
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextvars import copy_context
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from app.application.appspec.source import canonical_json
from app.application.services.ai_context import (
    ai_run_scope,
    capture_ai_stage_telemetry,
)
from app.application.visual_evaluation.evidence import evidence_absolute_paths
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.schemas.visual_evaluation import (
    RefinementOutput,
    VisualCallMetrics,
    VisualEvidenceBundle,
    VisualReviewerDecision,
    VisualScorecard,
    VisualStageRouting,
)
from app.shared.json_utils import extract_json_from_text


class VisualStageError(RuntimeError):
    def __init__(self, message: str, *, stage: str) -> None:
        super().__init__(message)
        self.stage = stage


@dataclass(frozen=True)
class BuiltVisualArtifact:
    artifact: BaseModel
    metrics: VisualCallMetrics


def _invoke_with_timeout(
    fn: Callable[[], str],
    *,
    timeout_seconds: float,
    stage: str,
) -> str:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(copy_context().run, fn)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeout as exc:
        future.cancel()
        raise VisualStageError(
            f"{stage} exceeded its {timeout_seconds:.1f}s wall timeout",
            stage=stage,
        ) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _image_part(path: Path) -> dict:
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{encoded}"},
    }


def _usage_metrics(
    *,
    stage: str,
    group_index: int | None,
    routing: VisualStageRouting,
    provider: AIProvider,
    captured,
    started: float,
) -> VisualCallMetrics:
    events = captured.usage_events
    prompt_tokens = sum(int(item.get("prompt_tokens") or 0) for item in events)
    completion_tokens = sum(
        int(item.get("completion_tokens") or 0) for item in events
    )
    total_tokens = sum(
        int(
            item.get("total_tokens")
            or int(item.get("prompt_tokens") or 0)
            + int(item.get("completion_tokens") or 0)
        )
        for item in events
    )
    return VisualCallMetrics(
        stage=stage,
        group_index=group_index,
        model=routing.capability.model,
        provider=str(getattr(provider, "name", "unknown") or "unknown"),
        family=routing.capability.family,
        capability=routing.capability.capability,
        prompt_revision=routing.prompt_revision,
        temperature=routing.temperature,
        max_tokens=routing.max_tokens,
        cache_hit=False,
        provider_call_count=1,
        transport_retry_count=captured.transport_retry_count,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=sum(float(item.get("cost_usd") or 0.0) for item in events),
        latency_ms=int((time.monotonic() - started) * 1000),
    )


def invoke_structured(
    *,
    request_id: int,
    stage: str,
    group_index: int | None,
    routing: VisualStageRouting,
    template_name: str,
    template_values: dict[str, Any],
    output_schema: type[BaseModel],
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    phase_deadline: float,
    image_paths: tuple[Path, ...] = (),
) -> BuiltVisualArtifact:
    started = time.monotonic()
    remaining = min(
        phase_deadline - started,
        float(routing.timeout_seconds),
    )
    if remaining <= 0:
        raise VisualStageError("Phase 5 wall deadline expired", stage=stage)
    prompt = template_renderer.render(
        template_name,
        **template_values,
        output_schema_json=canonical_json(output_schema.model_json_schema()),
        prompt_revision=routing.prompt_revision,
    )
    content: list[dict] = [{"type": "text", "text": prompt}]
    content.extend(_image_part(path) for path in image_paths)
    messages = (
        [{"role": "user", "content": content}]
        if image_paths
        else [{"role": "user", "content": prompt}]
    )
    with ai_run_scope(request_id, purpose=f"v2_visual_{stage}"):
        with capture_ai_stage_telemetry() as captured:

            def invoke() -> str:
                return ai_provider.ask_chat(
                    routing.capability.model,
                    messages,
                    max_tokens=routing.max_tokens,
                    temperature=routing.temperature,
                )

            raw = _invoke_with_timeout(
                invoke,
                timeout_seconds=remaining,
                stage=stage,
            )
    try:
        payload = extract_json_from_text(raw)
        if not isinstance(payload, dict):
            raise ValueError("Structured output must be one JSON object")
        artifact = output_schema.model_validate(payload)
    except Exception as exc:
        raise VisualStageError(
            f"{stage} returned invalid structured output: {str(exc)[:2000]}",
            stage=stage,
        ) from exc
    return BuiltVisualArtifact(
        artifact=artifact,
        metrics=_usage_metrics(
            stage=stage,
            group_index=group_index,
            routing=routing,
            provider=ai_provider,
            captured=captured,
            started=started,
        ),
    )


def build_critic_group(
    *,
    request_id: int,
    group,
    bundle: VisualEvidenceBundle,
    routing: VisualStageRouting,
    contracts_json: str,
    hard_gate_json: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    phase_deadline: float,
    subject: str,
) -> BuiltVisualArtifact:
    return invoke_structured(
        request_id=request_id,
        stage="critic",
        group_index=group.group_index,
        routing=routing,
        template_name="prompts/v2_visual_critic.j2",
        template_values={
            "subject": subject,
            "group_index": group.group_index,
            "evidence_json": canonical_json(
                [
                    item.model_dump(mode="json")
                    for item in bundle.ordered_screenshots
                    if item.evidence_id in set(group.evidence_ids)
                ]
            ),
            "contracts_json": contracts_json,
            "hard_gate_json": hard_gate_json,
        },
        output_schema=VisualScorecard,
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        phase_deadline=phase_deadline,
        image_paths=evidence_absolute_paths(bundle, group.evidence_ids),
    )


def build_reviewer_group(
    *,
    request_id: int,
    group,
    bundle: VisualEvidenceBundle,
    routing: VisualStageRouting,
    contracts_json: str,
    hard_gate_json: str,
    critic_scorecard_json: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    phase_deadline: float,
    subject: str,
    blind_comparison_json: str = "{}",
    comparison_image_paths: tuple[Path, ...] = (),
) -> BuiltVisualArtifact:
    return invoke_structured(
        request_id=request_id,
        stage="reviewer",
        group_index=group.group_index,
        routing=routing,
        template_name="prompts/v2_visual_reviewer.j2",
        template_values={
            "subject": subject,
            "group_index": group.group_index,
            "evidence_json": canonical_json(
                [
                    item.model_dump(mode="json")
                    for item in bundle.ordered_screenshots
                    if item.evidence_id in set(group.evidence_ids)
                ]
            ),
            "contracts_json": contracts_json,
            "hard_gate_json": hard_gate_json,
            "critic_scorecard_json": critic_scorecard_json,
            "blind_comparison_json": blind_comparison_json,
        },
        output_schema=VisualReviewerDecision,
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        phase_deadline=phase_deadline,
        image_paths=(
            comparison_image_paths
            if comparison_image_paths
            else evidence_absolute_paths(bundle, group.evidence_ids)
        ),
    )


def build_refinement(
    *,
    request_id: int,
    routing: VisualStageRouting,
    prompt_values: dict[str, Any],
    image_paths: tuple[Path, ...],
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    phase_deadline: float,
) -> BuiltVisualArtifact:
    return invoke_structured(
        request_id=request_id,
        stage="refinement",
        group_index=None,
        routing=routing,
        template_name="prompts/v2_visual_refinement.j2",
        template_values=prompt_values,
        output_schema=RefinementOutput,
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        phase_deadline=phase_deadline,
        image_paths=image_paths,
    )


def build_technical_repair(
    *,
    request_id: int,
    routing: VisualStageRouting,
    prompt_values: dict[str, Any],
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    phase_deadline: float,
) -> BuiltVisualArtifact:
    return invoke_structured(
        request_id=request_id,
        stage="technical_repair",
        group_index=None,
        routing=routing,
        template_name="prompts/v2_visual_technical_repair.j2",
        template_values=prompt_values,
        output_schema=RefinementOutput,
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        phase_deadline=phase_deadline,
    )


__all__ = [
    "BuiltVisualArtifact",
    "VisualStageError",
    "build_critic_group",
    "build_refinement",
    "build_reviewer_group",
    "build_technical_repair",
]
