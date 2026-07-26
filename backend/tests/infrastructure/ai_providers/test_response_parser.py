"""Focused tests for the central provider-response parser (#33 class)."""
from __future__ import annotations

import pytest

from app.infrastructure.ai_providers.response_parser import (
    ProviderGenerationError,
    parse_ollama_chat_response,
    parse_openai_compatible_chat_response,
    raise_if_unsuccessful,
)


def test_missing_choices_never_raises_keyerror() -> None:
    result = parse_openai_compatible_chat_response(
        provider="openrouter",
        model="deepseek/deepseek-chat",
        http_status=200,
        body={"error": {"message": "upstream error"}},
        raw_text='{"error":{"message":"upstream error"}}',
    )
    assert result.is_success is False
    assert result.error_code == "provider_server_error"
    with pytest.raises(ProviderGenerationError) as exc:
        raise_if_unsuccessful(result)
    assert exc.value.error_code == "provider_server_error"
    assert "'choices'" not in str(exc.value)


def test_http_status_checked_before_success_parsing() -> None:
    result = parse_openai_compatible_chat_response(
        provider="openrouter",
        model="m",
        http_status=401,
        body={"choices": [{"message": {"content": "secret"}}]},
        raw_text="{}",
    )
    assert result.is_success is False
    assert result.error_code == "provider_auth_failed"
    assert result.retryable is False


def test_provider_error_payload_on_200() -> None:
    result = parse_openai_compatible_chat_response(
        provider="openrouter",
        model="m",
        http_status=200,
        body={"error": {"message": "upstream error", "type": "server_error"}},
        raw_text='{"error":{"message":"upstream error"}}',
    )
    assert result.error_code == "provider_server_error"
    assert result.retryable is True
    assert "error" in result.response_top_level_keys


def test_unexpected_200_output_shape() -> None:
    result = parse_openai_compatible_chat_response(
        provider="openrouter",
        model="m",
        http_status=200,
        body={"output": "not openai compatible"},
        raw_text='{"output":"not openai compatible"}',
    )
    assert result.error_code == "provider_response_shape_invalid"
    assert result.retryable is True


def test_empty_choices() -> None:
    result = parse_openai_compatible_chat_response(
        provider="openrouter",
        model="m",
        http_status=200,
        body={"choices": []},
        raw_text='{"choices":[]}',
    )
    assert result.error_code == "provider_empty_response"


def test_missing_message_content() -> None:
    result = parse_openai_compatible_chat_response(
        provider="openrouter",
        model="m",
        http_status=200,
        body={"choices": [{"message": {}}]},
        raw_text='{"choices":[{"message":{}}]}',
    )
    assert result.error_code in {
        "provider_empty_response",
        "provider_response_shape_invalid",
    }


def test_valid_openai_compatible_normalizes() -> None:
    raw = (
        '{"id":"gen-1","choices":[{"message":{"content":"hello"},'
        '"finish_reason":"stop"}],"usage":{"prompt_tokens":3,'
        '"completion_tokens":1,"total_tokens":4}}'
    )
    result = parse_openai_compatible_chat_response(
        provider="openrouter",
        model="deepseek/deepseek-chat",
        http_status=200,
        body={
            "id": "gen-1",
            "choices": [
                {"message": {"content": "hello"}, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 1,
                "total_tokens": 4,
            },
        },
        raw_text=raw,
    )
    assert result.is_success is True
    assert result.text == "hello"
    assert result.provider_request_id == "gen-1"
    assert result.input_tokens == 3
    assert result.raw_payload_sha256
    assert raise_if_unsuccessful(result) == "hello"


def test_rate_limit_is_retryable() -> None:
    result = parse_openai_compatible_chat_response(
        provider="openrouter",
        model="m",
        http_status=429,
        body={"error": {"message": "rate limited"}},
        raw_text='{"error":{"message":"rate limited"}}',
    )
    assert result.error_code == "provider_rate_limited"
    assert result.retryable is True


def test_malformed_json_on_200() -> None:
    result = parse_openai_compatible_chat_response(
        provider="openrouter",
        model="m",
        http_status=200,
        body=None,
        raw_text="{not-json",
    )
    assert result.error_code == "provider_malformed_json"


def test_ollama_missing_message_is_typed() -> None:
    result = parse_ollama_chat_response(
        provider="ollama",
        model="llama",
        http_status=200,
        body={"done": True},
        raw_text='{"done":true}',
    )
    assert result.error_code == "provider_response_shape_invalid"
    with pytest.raises(ProviderGenerationError):
        raise_if_unsuccessful(result)


def test_diagnostics_omit_raw_body_and_secrets() -> None:
    result = parse_openai_compatible_chat_response(
        provider="openrouter",
        model="m",
        http_status=200,
        body={"error": {"message": "Bearer sk-secret-value upstream"}},
        raw_text='{"error":{"message":"Bearer sk-secret-value upstream"}}',
    )
    diag = result.to_diagnostics()
    assert "raw_payload" not in diag
    assert "text" not in diag or diag.get("text_chars") == 0
    assert "sk-secret" not in diag["error_message_redacted"]
