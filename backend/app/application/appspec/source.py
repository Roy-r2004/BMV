"""Capture and hash the immutable customer source used by AppSpec generation."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from app.application.services.ai_features import (
    extract_ai_features_from_blueprint,
    parse_ai_features,
)
from app.domain.models.request import Request


SOURCE_SCHEMA_VERSION = "1.0"


def _customer_ai_features(req: Request) -> list:
    """Authoritative AI inventory for AppSpec source (empty when needs_ai=no)."""
    if str(getattr(req, "needs_ai", None) or "").strip().lower() == "no":
        return []
    features = parse_ai_features(getattr(req, "ai_features", None))
    if features:
        return features
    return extract_ai_features_from_blueprint(getattr(req, "mvp_blueprint", None) or "")


def _json_ready(value: Any) -> Any:
    """Convert common domain/Pydantic values into deterministic JSON values."""
    if hasattr(value, "model_dump"):
        return _json_ready(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, set):
        return sorted((_json_ready(item) for item in value), key=lambda item: repr(item))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def canonical_json(value: Any) -> str:
    """Serialize a value in the one stable form used for persistence/hashes."""
    return json.dumps(
        _json_ready(value),
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def source_sha256(snapshot: Mapping[str, Any]) -> str:
    """Return a stable digest of a captured customer-source snapshot."""
    return hashlib.sha256(canonical_json(snapshot).encode("utf-8")).hexdigest()


def _parsed_json_or_text(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        # Preserve malformed/legacy evidence instead of silently discarding it.
        return {"raw_text": raw}


def _file_evidence(raw_path: str | None) -> dict[str, Any] | None:
    if not raw_path:
        return None
    path = Path(raw_path)
    evidence: dict[str, Any] = {
        # Never persist the host's absolute upload path in the product contract.
        "filename": path.name,
        "available_at_capture": path.is_file(),
    }
    if not path.is_file():
        return evidence

    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        evidence["sha256"] = digest.hexdigest()
        evidence["size_bytes"] = path.stat().st_size
    except OSError:
        # Availability is evidence too; hashing failure must not abort AppSpec.
        evidence["available_at_capture"] = False
    return evidence


def capture_request_source(req: Request) -> dict[str, Any]:
    """Capture authoritative customer input plus reference evidence.

    The snapshot deliberately excludes contact PII, admin notes, generation
    progress, blueprint prose, and preview artifacts.  A wall-clock
    ``captured_at`` is also omitted so repeated capture of unchanged input has
    the same SHA-256.  ``Request.created_at`` is stable source provenance.
    """
    created_at = getattr(req, "created_at", None)
    return {
        "source_schema_version": SOURCE_SCHEMA_VERSION,
        "request_id": getattr(req, "id", None),
        "request_created_at": created_at.isoformat() if created_at else None,
        "customer_input": {
            "business_name": getattr(req, "business_name", None),
            "industry": getattr(req, "industry", None),
            "business_description": getattr(req, "business_description", None),
            "target_customers": getattr(req, "target_customers", None),
            "main_problem": getattr(req, "main_problem", None),
            "reference_url": getattr(req, "reference_url", None),
            "what_you_like": getattr(req, "what_you_like", None),
            "desired_outcome": getattr(req, "desired_outcome", None),
            "project_type": getattr(req, "project_type", None),
            "existing_product_url": getattr(req, "existing_product_url", None),
            "needs_ai": getattr(req, "needs_ai", None),
            "budget_range": getattr(req, "budget_range", None),
            "timeline": getattr(req, "timeline", None),
            # Structured plan AI inventory — every item must ship in the preview.
            "ai_features": _customer_ai_features(req),
        },
        "reference_evidence": {
            "reference_metadata": _parsed_json_or_text(
                getattr(req, "reference_metadata", None)
            ),
            "screenshot_analysis": getattr(req, "screenshot_analysis", None),
            "uploaded_file": _file_evidence(
                getattr(req, "reference_file_path", None)
            ),
        },
    }


def capture_derived_context(req: Request) -> dict[str, Any]:
    """Return non-authoritative context that may help the AppSpec builder.

    This object is intentionally separate from ``capture_request_source`` and
    therefore never affects semantic source coverage or ``source_sha256``.
    """
    return {
        "derived_context": {
            "mvp_blueprint": getattr(req, "mvp_blueprint", None),
            "concept_name": getattr(req, "concept_name", None),
            "preview_summary": getattr(req, "preview_summary", None),
            "preview_features": _parsed_json_or_text(
                getattr(req, "preview_features", None)
            ),
        }
    }
