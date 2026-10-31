"""Pins for the silent-truncation defect found while freezing the golden set.

OpenRouter reports an upstream failure INSIDE an HTTP 200: `choices[0].error`
is set, `finish_reason` is "error", and `message.content` carries the partial
text that arrived before the failure. Checking only `resp.status_code` made
that look like a successful call, so:

  ui_spec parsed a JSON object cut off mid-string -> ValueError -> fell back
  to its generic deterministic specs. The lead gets a demo about "Alex" and
  "Bookings Today" instead of their own business, and the ledger records the
  call as a success.

Measured on the shared key 2026-08-11: 2 of 6 consecutive ui_spec calls came
back this way (upstream 429). These tests pin that such a response raises,
that transient ones are retried, and that a real response still returns.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import pytest

from unittest.mock import patch

from app.ai import provider

RATE_LIMITED_BODY = {
    "choices": [
        {
            "finish_reason": "error",
            "native_finish_reason": None,
            "error": {
                "code": 429,
                "message": "google/gemini-2.5-flash is temporarily rate-limited upstream.",
                "metadata": {"error_type": "rate_limit_exceeded"},
            },
            "message": {"role": "assistant", "content": '```json\n{\n  "archetype": "analytics-das'},
        }
    ],
    "usage": {"prompt_tokens": 900, "completion_tokens": 0, "cost": 0.0},
}

GOOD_BODY = {
    "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": '{"ok": true}'}}],
    "usage": {"prompt_tokens": 900, "completion_tokens": 120, "cost": 0.0004},
}


class _Resp:
    def __init__(self, body: dict, status_code: int = 200, text: str = ""):
        self.status_code = status_code
        self._body = body
        self.text = text

    def json(self) -> dict:
        return self._body


def test_the_suite_refuses_a_live_call_to_the_provider():
    """The guard in conftest.py: a test that forgot to stub the model fails,
    loudly and not as a failed call a stage could swallow, instead of making a
    paid call. (The key is set so the call gets as far as the network.)"""
    with patch.object(provider.settings, "OPENROUTER_API_KEY", "k"):
        with pytest.raises(pytest.fail.Exception, match="live provider"):
            provider.chat("google/gemini-2.5-flash", [{"role": "user", "content": "hi"}])


def test_truncated_upstream_error_is_not_a_success():
    with patch.object(provider.httpx, "post", return_value=_Resp(RATE_LIMITED_BODY)), \
         patch.object(provider.settings, "OPENROUTER_API_KEY", "k"), \
         patch.object(provider.time, "sleep"):
        with pytest.raises(provider.AiProviderError) as exc:
            provider.chat("google/gemini-2.5-flash", [{"role": "user", "content": "hi"}])
    assert "429" in str(exc.value)


def test_transient_upstream_error_is_retried_then_succeeds():
    responses = [_Resp(RATE_LIMITED_BODY), _Resp(GOOD_BODY)]

    with patch.object(provider.httpx, "post", side_effect=responses), \
         patch.object(provider.settings, "OPENROUTER_API_KEY", "k"), \
         patch.object(provider.time, "sleep"):
        body = provider.chat("google/gemini-2.5-flash", [{"role": "user", "content": "hi"}])
    assert body["choices"][0]["message"]["content"] == '{"ok": true}'


def test_retries_are_bounded_and_the_last_error_surfaces():
    calls = []

    def always_rate_limited(*_a, **_k):
        calls.append(1)
        return _Resp(RATE_LIMITED_BODY)

    with patch.object(provider.httpx, "post", side_effect=always_rate_limited), \
         patch.object(provider.settings, "OPENROUTER_API_KEY", "k"), \
         patch.object(provider.time, "sleep"):
        with pytest.raises(provider.AiProviderError):
            provider.chat("m", [{"role": "user", "content": "hi"}], retries=2)
    assert len(calls) == 3  # the attempt plus exactly two retries — never open-ended


def test_non_retryable_upstream_error_fails_immediately():
    body = {
        "choices": [{
            "finish_reason": "error",
            "error": {"code": 400, "message": "invalid model"},
            "message": {"content": ""},
        }]
    }
    calls = []

    with patch.object(provider.httpx, "post", side_effect=lambda *a, **k: (calls.append(1), _Resp(body))[1]), \
         patch.object(provider.settings, "OPENROUTER_API_KEY", "k"), \
         patch.object(provider.time, "sleep"):
        with pytest.raises(provider.AiProviderError):
            provider.chat("m", [{"role": "user", "content": "hi"}], retries=2)
    assert len(calls) == 1, "a 400 will fail identically on a retry — do not spend on it"


def test_ordinary_response_is_returned_unchanged():
    with patch.object(provider.httpx, "post", return_value=_Resp(GOOD_BODY)), \
         patch.object(provider.settings, "OPENROUTER_API_KEY", "k"):
        assert provider.chat("m", [{"role": "user", "content": "hi"}]) == GOOD_BODY


def test_transport_error_is_retried_on_the_text_path():
    responses = [httpx.ConnectError("peer closed connection"), _Resp(GOOD_BODY)]

    with patch.object(provider.httpx, "post", side_effect=responses), \
         patch.object(provider.settings, "OPENROUTER_API_KEY", "k"), \
         patch.object(provider.time, "sleep"):
        assert provider.chat("m", [{"role": "user", "content": "hi"}]) == GOOD_BODY
