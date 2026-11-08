"""A thinking model spends its reply budget on its reasoning first.

On the first real run the plan summary asked gemini-2.5-pro for 3,500 tokens.
Two replies used 3,443 and 3,478 of them, and their visible JSON stopped after
about 400 characters, so a paid run ended on a limit set for the answer alone.
"""
import httpx

from app.ai import provider
from app.config import settings


def _capture(monkeypatch) -> dict:
    sent: dict = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.update(json)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(provider.httpx, "post", fake_post)
    return sent


def test_the_reasoning_model_gets_room_to_think_on_top_of_its_answer(monkeypatch):
    sent = _capture(monkeypatch)
    provider.chat(settings.REASONING_MODEL, [{"role": "user", "content": "x"}], max_tokens=3500)
    assert sent["max_tokens"] == 3500 + settings.REASONING_TOKEN_HEADROOM
    assert settings.REASONING_TOKEN_HEADROOM >= 4000


def test_other_models_keep_exactly_the_limit_they_asked_for(monkeypatch):
    monkeypatch.setattr(settings, "REASONING_MODEL", "some/thinking-model")
    sent = _capture(monkeypatch)
    provider.chat("some/fast-model", [{"role": "user", "content": "x"}], max_tokens=3500)
    assert sent["max_tokens"] == 3500
