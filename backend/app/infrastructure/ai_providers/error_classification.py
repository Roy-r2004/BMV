"""Classify OpenAI-compatible / OpenRouter error payloads by body, not status alone.

Policy revision: 2026-07-26.candidate-provider.2
"""
from __future__ import annotations

import json
from typing import Any, Literal, Mapping

ProviderErrorCode = Literal[
    "provider_auth_failed",
    "provider_insufficient_credits",
    "provider_rate_limited",
    "provider_model_unavailable",
    "provider_upstream_unavailable",
    "provider_request_schema_invalid",
    "provider_parameter_unsupported",
    "provider_context_length_exceeded",
    "provider_content_refused",
    "provider_server_error",
    "provider_bad_request",
    "provider_response_shape_invalid",
    "provider_timeout",
    "provider_empty_response",
    "provider_malformed_json",
    "provider_truncated_output",
    "provider_structured_output_invalid",
]

_REFUSAL_HINTS = (
    "content_filter",
    "content filter",
    "refusal",
    "refused",
    "safety",
    "moderation",
)

_CONTEXT_HINTS = (
    "max_num_tokens",
    "context length",
    "context_length",
    "maximum context",
    "prompt is too long",
    "prompt length",
    "token limit",
    "too many tokens",
    "exceeds the model",
    "exceed context",
)

_RATE_HINTS = ("rate limit", "rate_limit", "too many requests", "rpm", "tpm")
_CREDIT_HINTS = (
    "insufficient credits",
    "insufficient_quota",
    "payment required",
    "quota exceeded",
    "billing",
)
_AUTH_HINTS = (
    "invalid api key",
    "unauthorized",
    "authentication",
    "not authenticated",
    "forbidden",
)
_MODEL_HINTS = (
    "model not found",
    "model_not_found",
    "no endpoints found",
    "is not a valid model",
    "unavailable model",
)
_UPSTREAM_HINTS = (
    "upstream",
    "provider unavailable",
    "temporarily unavailable",
    "overloaded",
    "capacity",
)
_SCHEMA_HINTS = (
    "json schema",
    "response_format",
    "structured output",
    "invalid schema",
    "schema validation",
)
_PARAM_HINTS = (
    "unsupported parameter",
    "unknown parameter",
    "invalid parameter",
    "does not support",
    "not supported",
)


def normalize_error_object(err: Any) -> dict[str, Any]:
    """Unwrap stringified OpenRouter error objects into a mapping."""

    if isinstance(err, Mapping):
        payload = dict(err)
    elif isinstance(err, str):
        text = err.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return {"message": text}
            if isinstance(parsed, Mapping):
                payload = dict(parsed)
            else:
                return {"message": text}
        else:
            return {"message": text}
    else:
        return {"message": str(err)}

    # Some gateways nest another error object.
    nested = payload.get("error")
    if isinstance(nested, Mapping) and "message" not in payload:
        merged = dict(nested)
        for key, value in payload.items():
            if key != "error" and key not in merged:
                merged[key] = value
        payload = merged
    return payload


def error_metadata_keys(err_obj: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(str(key) for key in err_obj.keys()))


def redact_error_message(message: str, *, limit: int = 500) -> str:
    text = " ".join(str(message or "").split())
    lowered = text.lower()
    for needle in ("bearer ", "api_key", "authorization", "sk-"):
        idx = lowered.find(needle)
        if idx >= 0:
            text = text[:idx] + "[redacted]"
            break
    return text[:limit]


def classify_provider_error(
    *,
    http_status: int,
    error_obj: Mapping[str, Any] | None,
    fallback_message: str = "",
) -> tuple[ProviderErrorCode, bool, str, tuple[str, ...]]:
    """Return (code, retryable, redacted_message, metadata_keys)."""

    obj = dict(error_obj or {})
    meta_keys = error_metadata_keys(obj)
    raw_message = str(
        obj.get("message")
        or obj.get("msg")
        or fallback_message
        or obj.get("code")
        or ""
    )
    message = redact_error_message(raw_message)
    blob = f"{message} {obj.get('type', '')} {obj.get('code', '')}".lower()
    err_type = str(obj.get("type") or "").lower()
    err_code = str(obj.get("code") or "").lower()

    def _hit(hints: tuple[str, ...]) -> bool:
        return any(hint in blob for hint in hints)

    # Body-first classification (covers HTTP 200 error envelopes).
    if _hit(_AUTH_HINTS) or http_status in {401, 403}:
        return "provider_auth_failed", False, message, meta_keys
    if _hit(_CREDIT_HINTS) or http_status == 402:
        return "provider_insufficient_credits", False, message, meta_keys
    if _hit(_RATE_HINTS) or http_status == 429 or err_code in {"429", "rate_limit"}:
        return "provider_rate_limited", True, message, meta_keys
    if _hit(_CONTEXT_HINTS):
        return "provider_context_length_exceeded", False, message, meta_keys
    if _hit(_REFUSAL_HINTS):
        return "provider_content_refused", False, message, meta_keys
    if _hit(_MODEL_HINTS):
        return "provider_model_unavailable", True, message, meta_keys
    if _hit(_UPSTREAM_HINTS) or err_type in {"server_error", "api_error"}:
        return "provider_upstream_unavailable", True, message, meta_keys
    if _hit(_SCHEMA_HINTS):
        return "provider_request_schema_invalid", False, message, meta_keys
    if _hit(_PARAM_HINTS):
        return "provider_parameter_unsupported", False, message, meta_keys

    if http_status == 408:
        return "provider_timeout", True, message or "Provider timed out.", meta_keys
    if 500 <= http_status <= 599:
        return (
            "provider_server_error",
            True,
            message or f"Provider HTTP {http_status}.",
            meta_keys,
        )
    if http_status == 400 or err_code in {"400", "bad_request"} or err_type in {
        "badrequesterror",
        "invalid_request_error",
    }:
        return (
            "provider_bad_request",
            False,
            message or "Provider rejected the request.",
            meta_keys,
        )
    if http_status >= 400:
        return (
            "provider_bad_request",
            False,
            message or f"Provider HTTP {http_status}.",
            meta_keys,
        )
    # HTTP 200 + error object without a more specific match.
    if "upstream" in message.lower() or "internal" in message.lower():
        return "provider_server_error", True, message, meta_keys
    return (
        "provider_bad_request",
        False,
        message or "Provider error payload without choices.",
        meta_keys,
    )


__all__ = [
    "ProviderErrorCode",
    "classify_provider_error",
    "error_metadata_keys",
    "normalize_error_object",
    "redact_error_message",
]
