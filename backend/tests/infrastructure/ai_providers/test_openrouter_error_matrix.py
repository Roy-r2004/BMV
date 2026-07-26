"""OpenRouter HTTP-200 error classification matrix (#34)."""
from __future__ import annotations

import json

import pytest

from app.infrastructure.ai_providers.response_parser import (
    parse_openai_compatible_chat_response,
)


def _parse(body: dict, *, http_status: int = 200):
    return parse_openai_compatible_chat_response(
        provider="openrouter",
        model="deepseek/deepseek-chat",
        http_status=http_status,
        body=body,
        raw_text=json.dumps(body),
    )


@pytest.mark.parametrize(
    ("body", "code", "retryable"),
    [
        (
            {
                "error": {
                    "object": "error",
                    "message": (
                        "The sum of prompt length (38049.0), query length (0) "
                        "should not exceed max_num_tokens (32768)"
                    ),
                    "type": "BadRequestError",
                    "param": None,
                    "code": 400,
                }
            },
            "provider_context_length_exceeded",
            False,
        ),
        (
            {
                "error": json.dumps(
                    {
                        "object": "error",
                        "message": (
                            "The sum of prompt length (38049.0), query length (0) "
                            "should not exceed max_num_tokens (32768)"
                        ),
                        "type": "BadRequestError",
                        "param": None,
                        "code": 400,
                    }
                )
            },
            "provider_context_length_exceeded",
            False,
        ),
        (
            {"error": {"message": "Unsupported parameter: foo", "code": 400}},
            "provider_parameter_unsupported",
            False,
        ),
        (
            {"error": {"message": "Invalid JSON schema for response_format"}},
            "provider_request_schema_invalid",
            False,
        ),
        (
            {"error": {"message": "Model not found", "code": "model_not_found"}},
            "provider_model_unavailable",
            True,
        ),
        (
            {"error": {"message": "Provider unavailable / overloaded", "type": "server_error"}},
            "provider_upstream_unavailable",
            True,
        ),
        (
            {"error": {"message": "Rate limit exceeded", "code": 429}},
            "provider_rate_limited",
            True,
        ),
        (
            {"error": {"message": "Insufficient credits"}},
            "provider_insufficient_credits",
            False,
        ),
        (
            {"error": {"message": "Invalid API key"}},
            "provider_auth_failed",
            False,
        ),
        (
            {"error": {"message": "Content filtered by moderation"}},
            "provider_content_refused",
            False,
        ),
        (
            {"error": {"message": "Internal error", "type": "api_error"}},
            "provider_upstream_unavailable",
            True,
        ),
        (
            {"error": {"message": "Something odd happened", "type": "BadRequestError", "code": 400}},
            "provider_bad_request",
            False,
        ),
    ],
)
def test_openrouter_error_matrix(body, code, retryable) -> None:
    result = _parse(body)
    assert result.is_success is False
    assert result.error_code == code
    assert result.retryable is retryable
    assert result.response_format == "provider_error"
    assert "choices" not in result.response_top_level_keys
    assert result.error_message_redacted
    assert "sk-" not in result.error_message_redacted.lower()


def test_request34_exact_error_shape() -> None:
    """Exact production #34 OpenRouter envelope."""

    inner = {
        "object": "error",
        "message": (
            "The sum of prompt length (38049.0), query length (0) "
            "should not exceed max_num_tokens (32768)"
        ),
        "type": "BadRequestError",
        "param": None,
        "code": 400,
    }
    # Observed both as object and as stringified object.
    for err in (inner, json.dumps(inner)):
        result = _parse({"error": err})
        assert result.error_code == "provider_context_length_exceeded"
        assert result.retryable is False
        assert "max_num_tokens" in result.error_message_redacted
        assert set(result.error_metadata_keys) >= {"message", "type", "code"}
