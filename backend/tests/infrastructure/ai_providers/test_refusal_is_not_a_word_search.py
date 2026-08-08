"""A blueprint that says "safety" is not a moderation event.

Requests 152 and 159 — both Copperline Hardware, both today, both dead eleven
seconds in at the blueprint stage, on a business summary the model had written
perfectly well:

    ### 1. Business Summary
    Copperline Hardware is a multi-service independent retailer specializing in
    high-quality garden and tool lines alongside a professional tool-hire desk…

`_looks_like_refusal(finish_reason, error_message)` was called with the
assistant's **own output** as `error_message` and scanned it for
`_REFUSAL_HINTS` — `content_filter`, `content filter`, `refusal`, `refused`,
`safety`, `moderation`. A hardware store that hires out tools has every reason to
write "safety" into its own description, so the pipeline read the business back
to itself, classified it `provider_content_refused` with `retryable=False`, and
the transport ladder above it correctly declined to re-ask a refusal. The run
died with the model's own prose as the error message.

Across all 138 stored blueprints the scan had never matched once. It was not a
check that mostly worked — it was a check nothing had exercised until a brief
happened to say the word, and then it took the same brief out twice.

The provider's own signals are unaffected and are what a refusal actually looks
like: the OpenAI `refusal` field (handled by `_message_text`, tested below) and
`finish_reason: content_filter`.
"""
from __future__ import annotations

import pytest

from app.infrastructure.ai_providers.response_parser import (
    parse_openai_compatible_chat_response,
    raise_if_unsuccessful,
)

#: The words the scan looked for, in the shapes a real business writes them.
INNOCENT_CONTENT = [
    pytest.param(
        "Copperline Hardware hires out powered garden equipment. Every hire "
        "includes a safety briefing and a check of the safety guards.",
        id="hardware-safety",
    ),
    pytest.param(
        "Patients are refused an appointment only when the clinic is full; the "
        "waitlist then contacts them.",
        id="clinic-refused",
    ),
    pytest.param(
        "The forum has a moderation queue so members can report a listing.",
        id="marketplace-moderation",
    ),
    pytest.param(
        "Uploads pass through a content filter before they appear in the gallery.",
        id="gallery-content-filter",
    ),
    pytest.param(
        "Our refusal policy is published on the terms page.",
        id="policy-refusal",
    ),
]


def _completion(content: str, finish_reason: str = "stop") -> dict:
    return {
        "id": "gen-1",
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
    }


def _parse(body: dict):
    return parse_openai_compatible_chat_response(
        provider="openrouter",
        model="deepseek/deepseek-v4-pro",
        http_status=200,
        body=body,
        raw_text="{}",
    )


@pytest.mark.parametrize("content", INNOCENT_CONTENT)
def test_an_answer_that_mentions_a_hint_word_is_still_an_answer(content: str) -> None:
    result = _parse(_completion(content))
    assert result.is_success is True, result.error_code
    assert result.text == content
    assert raise_if_unsuccessful(result) == content


def test_the_copperline_business_summary_parses() -> None:
    """The text that killed two runs, in the shape the model actually sent it."""
    summary = (
        "### 1. Business Summary\n"
        "Copperline Hardware is a multi-service independent retailer specializing "
        "in high-quality garden and tool lines alongside a professional tool-hire "
        "desk. Hire items are inspected and safety-checked between customers.\n"
        "### 2. Reference Tool Summary\nN/A (Full custom build).\n"
    )
    result = _parse(_completion(summary))
    assert result.is_success is True
    assert result.text == summary


# --------------------------------------------------------------------------- #
# what a refusal actually looks like — both signals still fire


def test_the_providers_refusal_field_is_still_a_refusal() -> None:
    """The authoritative content-side signal, and the one worth keeping."""
    result = _parse(
        {
            "id": "gen-1",
            "choices": [
                {
                    "message": {"refusal": "I cannot help with that request."},
                    "finish_reason": "stop",
                }
            ],
        }
    )
    assert result.is_success is False
    assert result.error_code == "provider_content_refused"
    assert result.retryable is False


@pytest.mark.parametrize("reason", ["content_filter", "safety", "moderation"])
def test_a_refusing_finish_reason_is_still_a_refusal(reason: str) -> None:
    """`finish_reason` is the provider speaking; the content is the model.

    A refusal declared here is not retryable, and must not become one — re-asking
    a moderation decision spends budget on the same answer.
    """
    result = _parse(_completion("", finish_reason=reason))
    assert result.is_success is False
    assert result.error_code == "provider_content_refused"
    assert result.retryable is False


def test_a_refusing_finish_reason_wins_over_the_content() -> None:
    """Content present but the provider says filtered — the provider is right."""
    result = _parse(_completion("Here is the plan.", finish_reason="content_filter"))
    assert result.is_success is False
    assert result.error_code == "provider_content_refused"
