"""Classify AppSpec Pydantic/schema failures into typed diagnostic issues."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from pydantic import ValidationError

TYPED_SCHEMA_ISSUE_CODES = frozenset(
    {
        "missing_required_field",
        "unexpected_field",
        "invalid_field_type",
        "invalid_enum",
        "malformed_json",
        "duplicate_id",
        "null_not_allowed",
        "invalid_nested_object",
        "invalid_reference_shape",
        "invalid_acceptance_test_shape",
        "invalid_trace_shape",
        "invalid_page_shape",
        "invalid_action_shape",
        "invalid_evidence_shape",
        "invalid_field_constraint",
    }
)

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SECRETISH_RE = re.compile(
    r"(?i)\b(api[_-]?key|authorization|bearer|password|secret|token)\b"
)
_PHONE_RE = re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b")


def format_json_path(loc: Any) -> str:
    """Render a pydantic ``loc`` tuple as a dotted/bracket JSON path."""

    parts: list[str] = []
    for item in list(loc or []):
        if isinstance(item, int):
            if parts:
                parts[-1] = f"{parts[-1]}[{item}]"
            else:
                parts.append(f"[{item}]")
        else:
            text = str(item)
            if text in {"__root__", "body"}:
                continue
            parts.append(text)
    return ".".join(parts)


def _shape_code_for_path(path: str) -> str | None:
    lowered = path.lower()
    if lowered.startswith("acceptance_tests") or ".assertions" in lowered:
        return "invalid_acceptance_test_shape"
    if lowered.startswith("traceability") or ".trace." in lowered:
        return "invalid_trace_shape"
    if lowered.startswith("pages"):
        return "invalid_page_shape"
    if lowered.startswith("actions"):
        return "invalid_action_shape"
    if lowered.startswith("evidence"):
        return "invalid_evidence_shape"
    if any(
        token in lowered
        for token in (
            "requirement_ids",
            "capability_ids",
            "page_ids",
            "evidence_ids",
            "journey_ids",
            "acceptance_test_ids",
            "role_ids",
            "entity_ids",
            "state_ids",
            "action_ids",
            "source_refs",
        )
    ):
        return "invalid_reference_shape"
    return None


def classify_pydantic_error(err: Mapping[str, Any]) -> dict[str, Any]:
    """Map one pydantic error dict to a typed AppSpec schema issue."""

    err_type = str(err.get("type") or "")
    path = format_json_path(err.get("loc"))
    msg = str(err.get("msg") or "")
    input_value = err.get("input")
    value_type = type(input_value).__name__ if input_value is not None else "NoneType"

    code = "invalid_field_constraint"
    if err_type in {"missing", "missing_argument"}:
        code = "missing_required_field"
    elif err_type in {"extra_forbidden", "unexpected_keyword_argument"}:
        code = "unexpected_field"
    elif err_type in {"bool_type", "int_type", "float_type", "string_type", "list_type", "dict_type", "tuple_type", "model_type", "dataclass_type", "is_instance_of"}:
        code = "invalid_field_type"
    elif err_type in {"enum", "literal_error"}:
        code = "invalid_enum"
    elif err_type in {"none_not_allowed", "none_required"}:
        code = "null_not_allowed"
    elif err_type in {"value_error", "assertion_error"} and "unique" in msg.lower():
        code = "duplicate_id"
    elif err_type.startswith("model_attributes") or err_type in {
        "model_type",
        "dataclass_exact_type",
    }:
        code = "invalid_nested_object"
    else:
        shaped = _shape_code_for_path(path)
        if shaped:
            code = shaped
        elif "json" in err_type or "json" in msg.lower():
            code = "malformed_json"
        elif err_type in {"value_error", "string_pattern", "string_too_short", "string_too_long"}:
            shaped = _shape_code_for_path(path)
            code = shaped or "invalid_field_constraint"

    # Prefer collection-shape codes when the path clearly identifies them.
    shaped = _shape_code_for_path(path)
    if shaped and code in {
        "invalid_field_constraint",
        "invalid_nested_object",
        "invalid_field_type",
    }:
        code = shaped

    return {
        "severity": "blocking",
        "code": code,
        "message": msg,
        "path": path,
        "related_ids": [],
        "error_type": err_type,
        "offending_value_type": value_type,
        "ctx": dict(err.get("ctx") or {}) if isinstance(err.get("ctx"), Mapping) else {},
    }


def classify_schema_parse_exception(exc: Exception) -> dict[str, Any]:
    """Build the terminal ``app_spec_schema_parse_failed`` wrapper with child issues."""

    children: list[dict[str, Any]] = []
    detail: Any
    if isinstance(exc, ValidationError):
        detail = exc.errors(include_url=False)
        for err in detail:
            if isinstance(err, Mapping):
                children.append(classify_pydantic_error(err))
    elif isinstance(exc, json.JSONDecodeError):
        detail = str(exc)
        children.append(
            {
                "severity": "blocking",
                "code": "malformed_json",
                "message": str(exc),
                "path": "",
                "related_ids": [],
                "error_type": type(exc).__name__,
                "offending_value_type": "str",
            }
        )
    else:
        detail = str(exc)
        message = str(exc).lower()
        code = "malformed_json" if "json" in message else "invalid_field_constraint"
        children.append(
            {
                "severity": "blocking",
                "code": code,
                "message": str(exc),
                "path": "",
                "related_ids": [],
                "error_type": type(exc).__name__,
                "offending_value_type": "unknown",
            }
        )

    return {
        "severity": "blocking",
        "code": "app_spec_schema_parse_failed",
        "message": "Candidate did not validate against the AppSpec schema.",
        "path": "",
        "related_ids": [],
        "detail": detail,
        "issues": children,
    }


def redact_candidate_fragment(value: Any, *, depth: int = 0) -> Any:
    """Redact emails/phones/secret-ish keys from a candidate fragment."""

    if depth > 12:
        return "<redacted:max_depth>"
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _SECRETISH_RE.search(key_text):
                out[key_text] = "<redacted>"
            else:
                out[key_text] = redact_candidate_fragment(item, depth=depth + 1)
        return out
    if isinstance(value, list):
        if len(value) > 40:
            head = [redact_candidate_fragment(item, depth=depth + 1) for item in value[:20]]
            return head + [f"<redacted:{len(value) - 20}_more_items>"]
        return [redact_candidate_fragment(item, depth=depth + 1) for item in value]
    if isinstance(value, str):
        text = value
        if len(text) > 500:
            text = text[:500] + "…"
        text = _EMAIL_RE.sub("<redacted:email>", text)
        text = _PHONE_RE.sub("<redacted:phone>", text)
        if _SECRETISH_RE.search(text):
            return "<redacted>"
        return text
    return value


def payload_sha256(payload: Mapping[str, Any] | None) -> str:
    encoded = json.dumps(
        payload or {},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_rejected_candidate_artifact(
    *,
    request_id: int,
    attempt_number: int,
    provider: str | None,
    model: str | None,
    prompt_revision: str,
    raw_response: str | None = None,
    raw_response_sha256: str | None = None,
    candidate_payload: Mapping[str, Any] | None = None,
    json_extraction: Mapping[str, Any] | None = None,
    schema_issue: Mapping[str, Any] | None = None,
    estimated_tokens: int | None = None,
    finish_reason: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    terminal_result: str,
    parent_revision_id: int | None = None,
    repair_type: str | None = None,
    before_sha256: str | None = None,
    after_sha256: str | None = None,
    changed_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Build an admin-safe rejected-candidate diagnostic artifact."""

    raw = raw_response or ""
    raw_sha = raw_response_sha256 or (
        hashlib.sha256(raw.encode("utf-8")).hexdigest() if raw else ""
    )
    redacted = redact_candidate_fragment(dict(candidate_payload or {}))
    child_issues = []
    if isinstance(schema_issue, Mapping):
        child_issues = list(schema_issue.get("issues") or [])
    now = datetime.now(timezone.utc).isoformat()
    return {
        "request_id": request_id,
        "attempt_number": attempt_number,
        "provider": provider or "unknown",
        "model": model or "unknown",
        "prompt_revision": prompt_revision,
        "raw_response_sha256": raw_sha,
        "raw_response_chars": len(raw),
        "redacted_candidate": redacted,
        "candidate_size_bytes": len(
            json.dumps(candidate_payload or {}, default=str).encode("utf-8")
        ),
        "json_extraction": dict(json_extraction or {}),
        "schema_validation_errors": child_issues,
        "wrapper_issue": {
            "code": (schema_issue or {}).get("code"),
            "message": (schema_issue or {}).get("message"),
            "path": (schema_issue or {}).get("path") or "",
        },
        "estimated_token_usage": estimated_tokens,
        "finish_reason": finish_reason,
        "started_at": started_at,
        "completed_at": completed_at or now,
        "terminal_result": terminal_result,
        "parent_revision_id": parent_revision_id,
        "repair_type": repair_type,
        "original_sha256": before_sha256,
        "result_sha256": after_sha256 or payload_sha256(candidate_payload),
        "changed_paths": list(changed_paths or [])[:80],
    }


__all__ = [
    "TYPED_SCHEMA_ISSUE_CODES",
    "build_rejected_candidate_artifact",
    "classify_pydantic_error",
    "classify_schema_parse_exception",
    "format_json_path",
    "payload_sha256",
    "redact_candidate_fragment",
]
