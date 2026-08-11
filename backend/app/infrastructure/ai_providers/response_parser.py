"""Central validated provider-response parser for chat completions.

Candidate generation and other pipeline stages must consume
``ProviderGenerationResult`` only. Raw OpenRouter / OpenAI / Ollama
payloads must never be indexed with ``response["choices"]`` outside this
module.

Policy revision: 2026-07-28.candidate-provider.4
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence

from app.infrastructure.ai_providers.error_classification import (
    ProviderErrorCode,
    classify_provider_error,
    normalize_error_object,
    redact_error_message,
)

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

ChatContentKind = Literal["absent", "null", "string", "parts", "invalid"]

# Content-part object types that carry assistant output text. Reasoning parts
# are deliberately excluded: hidden reasoning is never assistant output.
_TEXT_PART_TYPES = frozenset({"text", "output_text", "input_text"})


@dataclass(frozen=True)
class ProviderToolCall:
    """One assistant tool call, with arguments kept as the raw JSON string."""

    call_id: str
    name: str
    arguments: str

    @property
    def arguments_sha256(self) -> str:
        return payload_sha256(self.arguments)

    def to_diagnostics(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "name": self.name,
            "arguments_chars": len(self.arguments or ""),
            "arguments_sha256": self.arguments_sha256,
            # Never include argument values: they carry generated source.
        }


@dataclass(frozen=True)
class ChatMessageEnvelope:
    """Structural description of ``choices[0]`` with no generated content.

    ``content_text``, ``parsed_payload``, and tool-call arguments are carried
    for in-process extraction only. ``to_diagnostics`` never emits them.
    """

    choice_count: int = 0
    finish_reason: str = ""
    message_present: bool = False
    message_keys: tuple[str, ...] = ()
    content_kind: ChatContentKind = "absent"
    content_text: str | None = None
    content_part_types: tuple[str, ...] = ()
    content_part_count: int = 0
    content_parts_invalid: bool = False
    tool_calls: tuple[ProviderToolCall, ...] = ()
    parsed_payload: Any | None = None
    has_parsed: bool = False
    refusal_text: str = ""
    has_reasoning: bool = False
    reasoning_chars: int = 0

    @property
    def has_structured_payload(self) -> bool:
        return self.has_parsed or bool(self.tool_calls)

    def to_diagnostics(self) -> dict[str, Any]:
        return {
            "choice_count": self.choice_count,
            "finish_reason": self.finish_reason,
            "message_present": self.message_present,
            "message_keys": list(self.message_keys),
            "content_kind": self.content_kind,
            "content_chars": len(self.content_text or ""),
            "content_part_types": list(self.content_part_types),
            "content_part_count": self.content_part_count,
            "content_parts_invalid": self.content_parts_invalid,
            "tool_call_count": len(self.tool_calls),
            "tool_calls": [item.to_diagnostics() for item in self.tool_calls],
            "has_parsed": self.has_parsed,
            "has_refusal": bool(self.refusal_text),
            "has_reasoning": self.has_reasoning,
            "reasoning_chars": self.reasoning_chars,
            # Never include content text, parsed values, or reasoning content.
        }


def _tool_calls_from_message(message: Mapping[str, Any]) -> tuple[ProviderToolCall, ...]:
    raw = message.get("tool_calls")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    calls: list[ProviderToolCall] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        function = item.get("function")
        if not isinstance(function, Mapping):
            continue
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            argument_text = arguments
        elif isinstance(arguments, (Mapping, list)):
            # Some gateways pre-decode arguments; re-encode canonically rather
            # than guessing at a textual form.
            argument_text = json.dumps(arguments, sort_keys=True)
        else:
            argument_text = ""
        calls.append(
            ProviderToolCall(
                call_id=str(item.get("id") or ""),
                name=str(function.get("name") or ""),
                arguments=argument_text,
            )
        )
    return tuple(calls)


def _content_shape(
    message: Mapping[str, Any],
) -> tuple[ChatContentKind, str | None, tuple[str, ...], int, bool]:
    """Return ``(kind, text, part_types, part_count, parts_invalid)``."""

    if "content" not in message:
        return "absent", None, (), 0, False
    content = message.get("content")
    if content is None:
        return "null", None, (), 0, False
    if isinstance(content, str):
        return "string", content, (), 0, False
    if isinstance(content, list):
        part_types: list[str] = []
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                part_types.append("bare_string")
                chunks.append(item)
                continue
            if not isinstance(item, Mapping):
                part_types.append("invalid")
                continue
            part_type = str(item.get("type") or "")
            part_types.append(part_type or "untyped")
            text = item.get("text")
            if not isinstance(text, str):
                continue
            # Untyped parts carrying text are accepted; reasoning parts are not.
            if part_type and part_type not in _TEXT_PART_TYPES:
                continue
            chunks.append(text)
        joined = "".join(chunks)
        parts_invalid = bool(content) and not chunks
        return "parts", joined, tuple(part_types), len(content), parts_invalid
    return "invalid", None, (), 0, True


def describe_chat_envelope(body: Any) -> ChatMessageEnvelope:
    """Describe ``choices[0]`` of an OpenAI-compatible body, fail-soft."""

    if not isinstance(body, Mapping):
        return ChatMessageEnvelope()
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return ChatMessageEnvelope(choice_count=0)
    first = choices[0]
    if not isinstance(first, Mapping):
        return ChatMessageEnvelope(choice_count=len(choices))
    finish_reason = str(first.get("finish_reason") or "")
    message = first.get("message")
    if not isinstance(message, Mapping):
        return ChatMessageEnvelope(
            choice_count=len(choices),
            finish_reason=finish_reason,
        )

    kind, text, part_types, part_count, parts_invalid = _content_shape(message)
    refusal = message.get("refusal")
    refusal_text = refusal.strip() if isinstance(refusal, str) else ""
    # ``parsed`` may sit on the message (OpenAI SDK) or on the choice.
    parsed = message.get("parsed")
    if parsed is None:
        parsed = first.get("parsed")
    reasoning = message.get("reasoning")
    reasoning_chars = len(reasoning) if isinstance(reasoning, str) else 0
    has_reasoning = bool(
        reasoning_chars
        or message.get("reasoning_details")
        or message.get("reasoning_content")
    )
    return ChatMessageEnvelope(
        choice_count=len(choices),
        finish_reason=finish_reason,
        message_present=True,
        message_keys=tuple(sorted(str(key) for key in message.keys())),
        content_kind=kind,
        content_text=text,
        content_part_types=part_types,
        content_part_count=part_count,
        content_parts_invalid=parts_invalid,
        tool_calls=_tool_calls_from_message(message),
        parsed_payload=parsed,
        has_parsed=parsed is not None,
        refusal_text=refusal_text,
        has_reasoning=has_reasoning,
        reasoning_chars=reasoning_chars,
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
    error_type: str = ""
    error_metadata_keys: tuple[str, ...] = ()
    tool_calls: tuple[ProviderToolCall, ...] = ()
    envelope: ChatMessageEnvelope = field(default_factory=ChatMessageEnvelope)

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
            "error_type": self.error_type,
            "error_metadata_keys": list(self.error_metadata_keys),
            "structured_payload_present": self.structured_payload is not None,
            "envelope": self.envelope.to_diagnostics(),
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
    return redact_error_message(message, limit=limit)


def retryable_for_status(http_status: int) -> bool:
    return http_status in {408, 409, 425, 429, 500, 502, 503, 504}


def error_code_for_http_status(http_status: int) -> ProviderErrorCode:
    code, _retryable, _message, _keys = classify_provider_error(
        http_status=http_status,
        error_obj=None,
        fallback_message="",
    )
    return code


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


def _looks_like_refusal(finish_reason: str) -> bool:
    """Whether the *provider* says it refused — read off `finish_reason` only.

    This used to take the assistant's own output text as well, under the
    parameter name `error_message`, and scan it for `_REFUSAL_HINTS`. So any
    answer that merely used the word *safety* was classified
    `provider_content_refused`, `retryable=False`, and the ladder above it
    correctly declined to re-ask a refusal — killing the run.

    Requests 152 and 159, both Copperline Hardware, both today, both dead at the
    blueprint stage 11 seconds in. A hardware store that hires out tools has
    every reason to write "safety" into its own business summary, and the
    pipeline read the business back to itself and called it a moderation event.
    Across the 138 stored blueprints the scan never fired once, which is why it
    survived: it is not a check that mostly works, it is a check that had never
    been exercised until a brief happened to say the word.

    The content side of a genuine refusal is already covered, and covered
    properly: `_message_text` returns `refused=True` when the provider populates
    the OpenAI `refusal` field, and the caller tests that first.
    """
    return any(hint in (finish_reason or "").lower() for hint in _REFUSAL_HINTS)


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
    error_type: str = "",
    error_metadata_keys: tuple[str, ...] = (),
    envelope: ChatMessageEnvelope | None = None,
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
        error_type=error_type,
        error_metadata_keys=error_metadata_keys,
        envelope=envelope or ChatMessageEnvelope(),
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
        response_format: ProviderResponseFormat = "unknown"
        err_obj: dict[str, Any] = {}
        if isinstance(body, Mapping):
            if "error" in body:
                err_obj = normalize_error_object(body.get("error"))
                response_format = "provider_error"
            elif "detail" in body:
                detail = body.get("detail")
                err_obj = {
                    "message": (
                        detail
                        if isinstance(detail, str)
                        else redact_provider_message(json.dumps(detail)[:500])
                    )
                }
                response_format = "gateway_detail_error"
            else:
                err_obj = {"message": redact_provider_message(str(body)[:500])}
        code, retryable, message, meta_keys = classify_provider_error(
            http_status=http_status,
            error_obj=err_obj,
            fallback_message=f"Provider HTTP {http_status}.",
        )
        refusal = code == "provider_content_refused"
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
            retryable=retryable,
            refusal=refusal,
            error_type=str(err_obj.get("type") or err_obj.get("code") or ""),
            error_metadata_keys=meta_keys,
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
        err_obj = normalize_error_object(body.get("error"))
        code, retryable, message, meta_keys = classify_provider_error(
            http_status=http_status,
            error_obj=err_obj,
            fallback_message="Provider error payload without choices.",
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
            retryable=retryable,
            refusal=code == "provider_content_refused",
            error_type=str(err_obj.get("type") or err_obj.get("code") or ""),
            error_metadata_keys=meta_keys,
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

    envelope = describe_chat_envelope(body)
    finish_reason = envelope.finish_reason
    message_obj = first.get("message")
    text, refused = _message_text(message_obj)
    prompt_t, completion_t, total_t, cost = _usage_from_openai(body)
    request_id = str(body.get("id") or "")

    if refused or _looks_like_refusal(finish_reason):
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
            envelope=envelope,
        )

    # A cap-exhausted completion is truncation even when no content survived:
    # reasoning-style models can spend the whole output budget and return a
    # null content field. Classify before the missing/empty content branches.
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
            envelope=envelope,
        )

    # A structured answer is a complete answer. Tool-call and provider-native
    # parsed responses legitimately carry a null ``content``, so they must not
    # fall into the missing/empty content branches below.
    if envelope.has_structured_payload and not str(text or "").strip():
        return ProviderGenerationResult(
            provider=provider,
            model=model,
            provider_request_id=request_id,
            response_format="openai_chat_completion",
            text="",
            structured_payload=(
                envelope.parsed_payload
                if isinstance(envelope.parsed_payload, dict)
                else None
            ),
            finish_reason=finish_reason or "tool_calls",
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
            tool_calls=envelope.tool_calls,
            envelope=envelope,
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
            envelope=envelope,
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
            envelope=envelope,
        )

    return ProviderGenerationResult(
        provider=provider,
        model=model,
        provider_request_id=request_id,
        response_format="openai_chat_completion",
        text=str(text),
        structured_payload=(
            envelope.parsed_payload
            if isinstance(envelope.parsed_payload, dict)
            else None
        ),
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
        tool_calls=envelope.tool_calls,
        envelope=envelope,
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
    "ChatContentKind",
    "ChatMessageEnvelope",
    "ProviderErrorCode",
    "ProviderGenerationError",
    "ProviderGenerationResult",
    "ProviderResponseFormat",
    "ProviderToolCall",
    "describe_chat_envelope",
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
