"""Fail-closed customer projections for preview and progress responses."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping

from app.application.services.ai_features import ai_features_from_request
from app.application.services.preview_parser import parse_preview_features
from app.application.services.progress import (
    is_request_generating,
    parse_progress_snapshot,
)
from app.domain.schemas.request import (
    CustomerAIFeature,
    CustomerGeneratedPages,
    CustomerLifecycleStatus,
    CustomerPreviewApp,
    CustomerPreviewResponse,
    CustomerProgressResponse,
)

_GENERIC_GENERATION_ERROR = (
    "We could not generate the preview. Please try again."
)
_VALIDATION_ERROR = "The generated preview did not pass validation."
_VISUAL_REVIEW_ERROR = "The preview requires another generation attempt."

_EXPANDED_STATUS_MAP = {
    "requested": "requested",
    "approved": "requested",
    "generation_started": "in_progress",
    "generation_completed": "reviewing",
    "review_accepted": "reviewing",
    "review_rejected": "failed",
    "rejected": "failed",
    "generation_failed": "failed",
    "published": "ready",
}

_STATUS_LABELS: dict[CustomerLifecycleStatus, str] = {
    "queued": "Queued",
    "planning": "Planning your preview",
    "generating": "Generating your preview",
    "validating": "Validating your preview",
    "reviewing": "Reviewing your preview",
    "ready": "Your preview is ready",
    "failed": "Generation could not be completed",
    "expanded_preview_requested": "Expanded Preview requested",
    "expanded_preview_in_progress": "Generating your Expanded Preview",
}


def _json_object(raw: object) -> dict[str, Any]:
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _preview_bundle(req: object) -> dict[str, Any]:
    return _json_object(getattr(req, "generated_pages", None))


def _preview_contract(bundle: Mapping[str, Any]) -> dict[str, Any]:
    contract = bundle.get("preview_contract")
    return contract if isinstance(contract, dict) else {}


def _safe_preview_url(bundle: Mapping[str, Any], request_id: int) -> str | None:
    preview_app = bundle.get("preview_app")
    if not isinstance(preview_app, Mapping):
        return None
    candidate = preview_app.get("url")
    if not isinstance(candidate, str):
        return None
    candidate = candidate.strip()
    allowed_prefix = f"/api/preview-apps/{request_id}"
    if candidate == allowed_prefix or candidate.startswith(allowed_prefix + "/"):
        return candidate
    return None


def _failure_descriptor(
    contract: Mapping[str, Any],
    progress: Mapping[str, Any],
) -> str:
    failure = contract.get("failure")
    safe_failure = failure if isinstance(failure, Mapping) else {}
    parts = (
        contract.get("status"),
        progress.get("stage"),
        safe_failure.get("stage"),
        safe_failure.get("kind"),
        safe_failure.get("error_type"),
        safe_failure.get("root_cause"),
    )
    return " ".join(str(part or "").lower() for part in parts)


def _is_failed(
    req: object,
    contract: Mapping[str, Any],
    progress: Mapping[str, Any],
) -> bool:
    values = (
        getattr(req, "status", None),
        contract.get("status"),
        progress.get("stage"),
    )
    return any("fail" in str(value or "").lower() for value in values)


def _base_customer_status(
    req: object,
    contract: Mapping[str, Any],
    progress: Mapping[str, Any],
    *,
    preview_url: str | None,
) -> CustomerLifecycleStatus:
    if _is_failed(req, contract, progress):
        return "failed"

    internal = " ".join(
        (
            str(contract.get("status") or "").lower(),
            str(progress.get("stage") or "").lower(),
            str(getattr(req, "status", None) or "").lower(),
        )
    )
    request_status = str(getattr(req, "status", None) or "").lower()
    progress_stage = str(progress.get("stage") or "").lower()
    contract_status = str(contract.get("status") or "").lower()
    if (
        preview_url
        or contract_status == "candidate_visual_accepted"
        or request_status in {"ready", "done", "delivered", "approved"}
        or progress_stage in {"ready", "done", "refine_done"}
    ):
        return "ready"
    if any(marker in internal for marker in ("visual", "review", "critic")):
        return "reviewing"
    if any(
        marker in internal
        for marker in (
            "runtime",
            "validation",
            "candidate_build",
            "build",
        )
    ):
        return "validating"
    if any(
        marker in internal
        for marker in (
            "composition",
            "candidate",
            "codegen",
            "architect",
            "tech",
            "proposal",
        )
    ):
        return "generating"
    if any(
        marker in internal
        for marker in ("analyze", "blueprint", "appspec", "design", "planning")
    ):
        return "planning"
    return "queued"


def _customer_status(
    req: object,
    contract: Mapping[str, Any],
    progress: Mapping[str, Any],
    *,
    preview_url: str | None,
    expanded_status: str | None,
) -> CustomerLifecycleStatus:
    base = _base_customer_status(
        req,
        contract,
        progress,
        preview_url=preview_url,
    )
    if base == "failed":
        return base
    expanded = _EXPANDED_STATUS_MAP.get(str(expanded_status or "").lower())
    if expanded == "requested":
        return "expanded_preview_requested"
    if expanded in {"in_progress", "reviewing"}:
        return "expanded_preview_in_progress"
    return base


def _safe_error_message(
    req: object,
    contract: Mapping[str, Any],
    progress: Mapping[str, Any],
) -> str | None:
    if not _is_failed(req, contract, progress):
        return None
    descriptor = _failure_descriptor(contract, progress)
    if "composition" in descriptor:
        return _GENERIC_GENERATION_ERROR
    if any(marker in descriptor for marker in ("visual", "screenshot", "review")):
        return _VISUAL_REVIEW_ERROR
    if any(
        marker in descriptor
        for marker in ("runtime", "validation", "typescript", "vite", "build")
    ):
        return _VALIDATION_ERROR
    return _GENERIC_GENERATION_ERROR


def _progress_percentage(
    progress: Mapping[str, Any],
    status: CustomerLifecycleStatus,
) -> int:
    raw = progress.get("pct")
    try:
        value = int(raw or 0)
    except (TypeError, ValueError):
        value = 0
    if status == "ready":
        value = 100
    return max(0, min(100, value))


def _visual_demo_status(
    req: object,
    contract: Mapping[str, Any],
    progress: Mapping[str, Any],
) -> str:
    descriptor = _failure_descriptor(contract, progress)
    if _is_failed(req, contract, progress) and "visual" in descriptor:
        return "failed"
    if _json_object(getattr(req, "visual_demo_json", None)):
        return "available"
    return "pending"


def _safe_ai_features(req: object) -> list[CustomerAIFeature]:
    safe: list[CustomerAIFeature] = []
    for item in ai_features_from_request(req):
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        safe.append(
            CustomerAIFeature(
                id=str(item.get("id") or "").strip() or None,
                name=name,
                description=str(item.get("description") or "").strip() or None,
                category=str(item.get("category") or "").strip() or None,
                surface=str(item.get("surface") or "").strip() or None,
            )
        )
    return safe


def _safe_expanded_state(expanded_status: str | None) -> str | None:
    return _EXPANDED_STATUS_MAP.get(str(expanded_status or "").lower())


def customer_preview_response(
    req: object,
    *,
    expanded_status: str | None = None,
) -> CustomerPreviewResponse:
    bundle = _preview_bundle(req)
    contract = _preview_contract(bundle)
    progress = parse_progress_snapshot(getattr(req, "generation_log", None))
    request_id = int(getattr(req, "id"))
    preview_url = _safe_preview_url(bundle, request_id)
    status = _customer_status(
        req,
        contract,
        progress,
        preview_url=preview_url,
        expanded_status=expanded_status,
    )
    pct = _progress_percentage(progress, status)
    safe_expanded = _safe_expanded_state(expanded_status)
    generated_pages = (
        CustomerGeneratedPages(preview_app=CustomerPreviewApp(url=preview_url))
        if preview_url
        else None
    )
    return CustomerPreviewResponse(
        id=request_id,
        request_id=request_id,
        business_name=str(getattr(req, "business_name", "") or ""),
        business_fit_score=getattr(req, "business_fit_score", None),
        concept_name=getattr(req, "concept_name", None),
        preview_summary=getattr(req, "preview_summary", None),
        preview_features=parse_preview_features(
            getattr(req, "preview_features", None)
        ),
        ai_features=_safe_ai_features(req),
        status=status,
        stage_label=_STATUS_LABELS[status],
        progress_percentage=pct,
        error_message=_safe_error_message(req, contract, progress),
        preview_url=preview_url,
        generated_pages=generated_pages,
        visual_demo_status=_visual_demo_status(req, contract, progress),
        expanded_preview_status=safe_expanded,
        tier2_request_state=safe_expanded,
        is_generating=is_request_generating(req),
        industry=getattr(req, "industry", None),
        timeline=getattr(req, "timeline", None),
        budget_range=getattr(req, "budget_range", None),
        desired_outcome=getattr(req, "desired_outcome", None),
        main_problem=getattr(req, "main_problem", None),
        reference_url=getattr(req, "reference_url", None),
        what_you_like=getattr(req, "what_you_like", None),
        build_requested=bool(getattr(req, "build_requested", False)),
        created_at=getattr(req, "created_at", None),
        updated_at=getattr(req, "updated_at", None),
    )


def customer_progress_response(
    req: object,
    *,
    expanded_status: str | None = None,
) -> CustomerProgressResponse:
    bundle = _preview_bundle(req)
    contract = _preview_contract(bundle)
    progress = parse_progress_snapshot(getattr(req, "generation_log", None))
    request_id = int(getattr(req, "id"))
    preview_url = _safe_preview_url(bundle, request_id)
    status = _customer_status(
        req,
        contract,
        progress,
        preview_url=preview_url,
        expanded_status=expanded_status,
    )
    descriptor = _failure_descriptor(contract, progress)
    stage_label = (
        "Validating your preview"
        if status == "failed"
        and any(
            marker in descriptor
            for marker in ("runtime", "validation", "typescript", "vite", "build")
        )
        else _STATUS_LABELS[status]
    )
    pct = _progress_percentage(progress, status)
    safe_expanded = _safe_expanded_state(expanded_status)
    error_message = _safe_error_message(req, contract, progress)
    generating = is_request_generating(req)
    return CustomerProgressResponse(
        request_id=request_id,
        status=status,
        stage_label=stage_label,
        progress_percentage=pct,
        error_message=error_message,
        preview_url=preview_url,
        visual_demo_status=_visual_demo_status(req, contract, progress),
        expanded_preview_status=safe_expanded,
        tier2_request_state=safe_expanded,
        updated_at=progress.get("updated_at")
        or getattr(req, "updated_at", None),
        is_generating=generating,
        is_failed=status == "failed" and not generating,
        stage=status,
        label=stage_label,
        pct=pct,
        request_status=status,
    )


__all__ = [
    "customer_preview_response",
    "customer_progress_response",
]
