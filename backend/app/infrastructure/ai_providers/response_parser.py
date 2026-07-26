"""Central validated provider-response parser for chat completions.

Candidate generation and other pipeline stages must consume
``ProviderGenerationResult`` only. Raw OpenRouter / OpenAI / Ollama
payloads must never be indexed with ``response["choices"]`` outside this
module.

Policy revision: 2026-07-26.candidate-provider.1
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Mapping

ProviderErrorCode = Literal[
    "provider_auth_failed",
    "provider_rate_limited",
    "provider_timeout",
    "provider_server_error",
    "provider_bad_request",
    "provider_content_refused",
    "provider_empty_response",
    "provider_response_shape_invalid",
    "provider_malformed_json",
    "provider_truncated_output",
    "provider_structured_output_invalid",
]

ProviderResponseFormat = Literal[
    "openai_chat_completion",
    "openai_chat_completion_stream_aggregate",
    "ollama_chat",
    "provider_error",
    "gateway_detail_error",
    "unknown",
    "empty",
]

_REFUSAL_HINTS = (
    "content_filter",
    "content filter",
    "refusal",
    "refused",
    "safety",
    "moderation",
)


@dataclass(frozen=True)
class ProviderGenerationResult:
    provider: str
    model: str
    provider_request_id: str
    response_format: ProviderResponseFormat
    text: str
    structured_payload: dict[str, Any] | None
    finish_reason: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    http_status: int
    raw_payload_sha256: str
    is_success: bool
    error_code: str
    error_message_redacted: str
    retryable: bool
    refusal: bool
    truncated: bool
    latency_ms: int
    response_top_level_keys: tuple[str, ...] = ()
    cost_usd: float | None = None

    def to_diagnostics(self) -> dict[str, Any]:
        """Redacted diagnostics safe for admin persistence."""
        return {
            "provider": self.provider,
            "model": self.model,
            "provider_request_id": self.provider_request_id,
            "response_format": self.response_format,
            "finish_reason": self.finish_reason,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "http_status": self.http_status,
            "raw_payload_sha256": self.raw_payload_sha256,
            "is_success": self.is_success,
            "error_code": self.error_code,
            "error_message_redacted": self.error_message_redacted,
            "retryable": self.retryable,
            "refusal": self.refusal,
            "truncated": self.truncated,
            "latency_ms": self.latency_ms,
            "response_top_level_keys": list(self.response_top_level_keys),
            "cost_usd": self.cost_usd,
            "text_chars": len(self.text or ""),
            # Never include raw text, prompts, or full payload bodies.
        }


class ProviderGenerationError(RuntimeError):
    """Typed provider failure; never a raw KeyError on payload fields."""

    def __init__(
        self,
        message: str,
        *,
        result: ProviderGenerationResult,
    ) -> None:
        super().__init__(message)
        self.result = result
        self.error_code: str = result.error_code or "provider_response_shape_invalid"
        self.retryable: bool = bool(result.retryable)

    def to_failure_dict(self) -> dict[str, Any]:
        return {
            "kind": "generation",
            "error_type": "ProviderGenerationError",
            "message": str(self)[:4000],
            "provider_error_code": self.error_code,
            "retryable": self.retryable,
            "provider_diagnostics": self.result.to_diagnostics(),
            "root_cause": "candidate_provider_failure",
            "phase4_ran": False,
        }


def payload_sha256(raw_text: str | bytes | None) -> str:
    if raw_text is None:
        data = b""
    elif isinstance(raw_text, bytes):
        data = raw_text
    else:
        data = raw_text.encode("utf-8", errors="replace")
    return hashlib.sha256(data).hexdigest()


def top_level_keys(body: Any) -> tuple[str, ...]:
    if isinstance(body, Mapping):
        return tuple(sorted(str(key) for key in body.keys()))
    return ()


def redact_provider_message(message: str, *, limit: int = 500) -> str:
    text = " ".join(str(message or "").split())
    # Strip anything that looks like a bearer/token fragment.
    lowered = text
    for needle in ("bearer ", "api_key", "authorization", "sk-"):
        idx = lowered.lower().find(needle)
        if idx >= 0:
            lowered = lowered[:idx] + "[redacted]"
            break
    return lowered[:limit]


def retryable_for_status(http_status: int) -> bool:
    return http_status in {408, 409, 425, 429, 500, 502, 503, 504}


def error_code_for_http_status(http_status: int) -> ProviderErrorCode:
    if http_status in {401, 403}:
        return "provider_auth_failed"
    if http_status == 429:
        return "provider_rate_limited"
    if http_status == 408:
        return "provider_timeout"
    if http_status == 400:
        return "provider_bad_request"
    if 500 <= http_status <= 599:
        return "provider_server_error"
    if http_status == 404:
        return "provider_bad_request"
    if http_status >= 400:
        return "provider_bad_request"
    return "provider_server_error"


def _usage_from_openai(body: Mapping[str, Any]) -> tuple[int, int, int, float | None]:
    usage = body.get("usage") or {}
    if not isinstance(usage, Mapping):
        return 0, 0, 0, None
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or (prompt + completion))
    cost = usage.get("cost")
    if cost is None:
        cost = usage.get("total_cost")
    try:
        cost_f = float(cost) if cost is not None else None
    except (TypeError, ValueError):
        cost_f = None
    return prompt, completion, total, cost_f


def _message_text(message: Any) -> tuple[str | None, bool]:
    """Extract assistant text; second flag is True when content was refused."""
    if not isinstance(message, Mapping):
        return None, False
    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        return refusal.strip(), True
    content = message.get("content")
    if isinstance(content, str):
        return content, False
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, Mapping):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        joined = "".join(parts)
        return joined, False
    return None, False


def _looks_like_refusal(finish_reason: str, error_message: str) -> bool:
    blob = f"{finish_reason} {error_message}".lower()
    return any(hint in blob for hint in _REFUSAL_HINTS)


def _failure_result(
    *,
    provider: str,
    model: str,
    http_status: int,
    body: Any,
    raw_text: str | None,
    latency_ms: int,
    error_code: ProviderErrorCode,
    message: str,
    response_format: ProviderResponseFormat,
    retryable: bool | None = None,
    refusal: bool = False,
    truncated: bool = False,
    finish_reason: str = "",
    provider_request_id: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    cost_usd: float | None = None,
) -> ProviderGenerationResult:
    keys = top_level_keys(body)
    if not provider_request_id and isinstance(body, Mapping):
        provider_request_id = str(
            body.get("id") or body.get("request_id") or ""
        )
    return ProviderGenerationResult(
        provider=provider,
        model=model,
        provider_request_id=provider_request_id,
        response_format=response_format,
        text="",
        structured_payload=None,
        finish_reason=finish_reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        http_status=http_status,
        raw_payload_sha256=payload_sha256(raw_text),
        is_success=False,
        error_code=error_code,
        error_message_redacted=redact_provider_message(message),
        retryable=(
            retryable_for_status(http_status)
            if retryable is None
            else bool(retryable)
        ),
        refusal=refusal,
        truncated=truncated,
        latency_ms=max(0, latency_ms),
        response_top_level_keys=keys,
        cost_usd=cost_usd,
    )


def parse_json_body(raw_text: str | None) -> tuple[Any | None, str | None]:
    """Return (body, malformed_error). body is None when empty or invalid."""
    if raw_text is None:
        return None, None
    text = raw_text.strip()
    if not text:
        return None, None
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def parse_openai_compatible_chat_response(
    *,
    provider: str,
    model: str,
    http_status: int,
    body: Any,
    raw_text: str | None,
    latency_ms: int = 0,
) -> ProviderGenerationResult:
    """Parse an OpenAI-compatible chat completion HTTP response.

    HTTP status is checked before success-body parsing.
    """
    keys = top_level_keys(body)

    if http_status == 0:
        return _failure_result(
            provider=provider,
            model=model,
            http_status=0,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_timeout",
            message="Provider request timed out or returned no HTTP status.",
            response_format="unknown",
            retryable=True,
        )

    # Malformed JSON with non-success status still maps to status first when
    # we have a status; empty/invalid body on 2xx is malformed_json.
    if body is None and (raw_text or "").strip():
        # Caller already failed to parse JSON.
        code: ProviderErrorCode
        if http_status >= 400:
            code = error_code_for_http_status(http_status)
            return _failure_result(
                provider=provider,
                model=model,
                http_status=http_status,
                body=body,
                raw_text=raw_text,
                latency_ms=latency_ms,
                error_code=code,
                message="Provider returned a non-JSON error body.",
                response_format="unknown",
            )
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_malformed_json",
            message="Provider returned malformed JSON.",
            response_format="unknown",
            retryable=True,
        )

    if http_status >= 400:
        code = error_code_for_http_status(http_status)
        message = ""
        response_format: ProviderResponseFormat = "unknown"
        refusal = False
        if isinstance(body, Mapping):
            if "error" in body and isinstance(body.get("error"), Mapping):
                err = body["error"]
                message = str(err.get("message") or err.get("code") or "")
                response_format = "provider_error"
                err_type = str(err.get("type") or err.get("code") or "")
                if _looks_like_refusal(err_type, message):
                    code = "provider_content_refused"
                    refusal = True
            elif "detail" in body:
                detail = body.get("detail")
                message = (
                    detail
                    if isinstance(detail, str)
                    else redact_provider_message(json.dumps(detail)[:500])
                )
                response_format = "gateway_detail_error"
            else:
                message = redact_provider_message(str(body)[:500])
        if not message:
            message = f"Provider HTTP {http_status}."
        if refusal or _looks_like_refusal("", message):
            code = "provider_content_refused"
            refusal = True
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code=code,
            message=message,
            response_format=response_format,
            retryable=False if refusal or code == "provider_auth_failed" else None,
            refusal=refusal,
        )

    # Success status path — require a supported shape. Never guess nested text.
    if not isinstance(body, Mapping):
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_response_shape_invalid",
            message="Provider success body was not a JSON object.",
            response_format="unknown",
            retryable=True,
        )

    # Explicit provider/gateway error payloads on HTTP 200.
    if "error" in body and "choices" not in body:
        err = body.get("error")
        message = ""
        if isinstance(err, Mapping):
            message = str(err.get("message") or err.get("code") or "upstream error")
        elif isinstance(err, str):
            message = err
        else:
            message = "Provider error payload without choices."
        # Prefer server_error when message suggests upstream; else bad_request.
        code = (
            "provider_server_error"
            if "upstream" in message.lower() or "internal" in message.lower()
            else "provider_bad_request"
        )
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code=code,
            message=message,
            response_format="provider_error",
            retryable=code == "provider_server_error",
        )

    if "detail" in body and "choices" not in body:
        detail = body.get("detail")
        message = detail if isinstance(detail, str) else "Gateway detail error."
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_bad_request",
            message=str(message),
            response_format="gateway_detail_error",
            retryable=False,
        )

    if "choices" not in body:
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_response_shape_invalid",
            message=(
                "Provider success body missing OpenAI-compatible 'choices'. "
                f"Top-level keys: {list(keys)}"
            ),
            response_format="unknown",
            retryable=True,
        )

    choices = body.get("choices")
    if not isinstance(choices, list):
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_response_shape_invalid",
            message="Provider 'choices' was not a list.",
            response_format="openai_chat_completion",
            retryable=True,
        )
    if not choices:
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_empty_response",
            message="Provider returned an empty choices list.",
            response_format="openai_chat_completion",
            retryable=True,
        )

    first = choices[0]
    if not isinstance(first, Mapping):
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_response_shape_invalid",
            message="Provider choices[0] was not an object.",
            response_format="openai_chat_completion",
            retryable=True,
        )

    finish_reason = str(first.get("finish_reason") or "")
    message_obj = first.get("message")
    text, refused = _message_text(message_obj)
    prompt_t, completion_t, total_t, cost = _usage_from_openai(body)
    request_id = str(body.get("id") or "")

    if refused or _looks_like_refusal(finish_reason, text or ""):
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_content_refused",
            message=text or "Provider refused to generate content.",
            response_format="openai_chat_completion",
            retryable=False,
            refusal=True,
            finish_reason=finish_reason,
            provider_request_id=request_id,
            input_tokens=prompt_t,
            output_tokens=completion_t,
            total_tokens=total_t,
            cost_usd=cost,
        )

    if text is None:
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_response_shape_invalid",
            message="Provider choice message content was missing.",
            response_format="openai_chat_completion",
            retryable=True,
            finish_reason=finish_reason,
            provider_request_id=request_id,
            input_tokens=prompt_t,
            output_tokens=completion_t,
            total_tokens=total_t,
            cost_usd=cost,
        )

    if not str(text).strip():
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_empty_response",
            message="Provider choice message content was empty.",
            response_format="openai_chat_completion",
            retryable=True,
            finish_reason=finish_reason,
            provider_request_id=request_id,
            input_tokens=prompt_t,
            output_tokens=completion_t,
            total_tokens=total_t,
            cost_usd=cost,
        )

    truncated = finish_reason in {"length", "max_tokens"}
    if truncated:
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_truncated_output",
            message="Provider output was truncated.",
            response_format="openai_chat_completion",
            retryable=True,
            truncated=True,
            finish_reason=finish_reason,
            provider_request_id=request_id,
            input_tokens=prompt_t,
            output_tokens=completion_t,
            total_tokens=total_t,
            cost_usd=cost,
        )

    return ProviderGenerationResult(
        provider=provider,
        model=model,
        provider_request_id=request_id,
        response_format="openai_chat_completion",
        text=str(text),
        structured_payload=None,
        finish_reason=finish_reason or "stop",
        input_tokens=prompt_t,
        output_tokens=completion_t,
        total_tokens=total_t,
        http_status=http_status,
        raw_payload_sha256=payload_sha256(raw_text),
        is_success=True,
        error_code="",
        error_message_redacted="",
        retryable=False,
        refusal=False,
        truncated=False,
        latency_ms=max(0, latency_ms),
        response_top_level_keys=keys,
        cost_usd=cost,
    )


def parse_ollama_chat_response(
    *,
    provider: str,
    model: str,
    http_status: int,
    body: Any,
    raw_text: str | None,
    latency_ms: int = 0,
) -> ProviderGenerationResult:
    """Parse an Ollama ``/api/chat`` non-streaming response."""
    if http_status >= 400 or http_status == 0:
        # Reuse OpenAI status mapping for HTTP failures.
        return parse_openai_compatible_chat_response(
            provider=provider,
            model=model,
            http_status=http_status if http_status else 408,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
        )

    if body is None and (raw_text or "").strip():
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_malformed_json",
            message="Ollama returned malformed JSON.",
            response_format="unknown",
            retryable=True,
        )

    if not isinstance(body, Mapping):
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_response_shape_invalid",
            message="Ollama success body was not a JSON object.",
            response_format="unknown",
            retryable=True,
        )

    if "error" in body and "message" not in body:
        err = body.get("error")
        message = err if isinstance(err, str) else "Ollama error."
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_server_error",
            message=str(message),
            response_format="provider_error",
            retryable=True,
        )

    message_obj = body.get("message")
    if not isinstance(message_obj, Mapping):
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_response_shape_invalid",
            message="Ollama response missing message object.",
            response_format="ollama_chat",
            retryable=True,
        )

    content = message_obj.get("content")
    if not isinstance(content, str) or not content.strip():
        return _failure_result(
            provider=provider,
            model=model,
            http_status=http_status,
            body=body,
            raw_text=raw_text,
            latency_ms=latency_ms,
            error_code="provider_empty_response",
            message="Ollama message content was empty or missing.",
            response_format="ollama_chat",
            retryable=True,
        )

    prompt_t = int(body.get("prompt_eval_count") or 0)
    completion_t = int(body.get("eval_count") or 0)
    return ProviderGenerationResult(
        provider=provider,
        model=model,
        provider_request_id="",
        response_format="ollama_chat",
        text=content,
        structured_payload=None,
        finish_reason="stop" if body.get("done") else "",
        input_tokens=prompt_t,
        output_tokens=completion_t,
        total_tokens=prompt_t + completion_t,
        http_status=http_status,
        raw_payload_sha256=payload_sha256(raw_text),
        is_success=True,
        error_code="",
        error_message_redacted="",
        retryable=False,
        refusal=False,
        truncated=False,
        latency_ms=max(0, latency_ms),
        response_top_level_keys=top_level_keys(body),
        cost_usd=0.0,
    )


def raise_if_unsuccessful(result: ProviderGenerationResult) -> str:
    """Return text on success; raise ProviderGenerationError otherwise."""
    if result.is_success:
        return result.text
    raise ProviderGenerationError(
        result.error_message_redacted
        or f"Provider call failed: {result.error_code}",
        result=result,
    )


__all__ = [
    "ProviderErrorCode",
    "ProviderGenerationError",
    "ProviderGenerationResult",
    "ProviderResponseFormat",
    "error_code_for_http_status",
    "parse_json_body",
    "parse_ollama_chat_response",
    "parse_openai_compatible_chat_response",
    "payload_sha256",
    "raise_if_unsuccessful",
    "redact_provider_message",
    "retryable_for_status",
    "top_level_keys",
]
