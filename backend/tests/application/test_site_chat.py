"""The site's assistant answers the question asked, and stays honest about the firm."""
from __future__ import annotations

import pytest

from app.api.v1.routers import site_chat as router
from app.application.services import admin_ops, site_chat
from app.application.services.site_chat_knowledge import PRICING_SAFE_REPLY, SITE_KNOWLEDGE


class FakeAI:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def is_available(self) -> bool:
        return True

    def ask_chat_purposed(self, model, messages, *, purpose, max_tokens=None, temperature=None,
                          timeout_seconds=None, transport_attempts=None):
        self.calls.append({"model": model, "messages": messages, "purpose": purpose,
                           "timeout_seconds": timeout_seconds, "transport_attempts": transport_attempts})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture(autouse=True)
def _allowed_and_routed(monkeypatch):
    monkeypatch.setattr(site_chat, "ai_is_allowed", lambda purpose="pipeline": (True, ""))
    monkeypatch.setattr(site_chat.settings, "AI_PROVIDER", "openrouter")
    monkeypatch.setattr(site_chat.settings, "SITE_CHAT_MODEL", "primary/model")
    monkeypatch.setattr(site_chat.settings, "SITE_CHAT_FALLBACK_MODEL", "backup/model")


def ask(ai, text="What is the capital of Japan?", history=()):
    return site_chat.reply_site_chat(ai, messages=[*history, {"role": "user", "content": text}])


def test_a_question_that_mentions_cost_is_answered_by_the_model():
    ai = FakeAI("Cut waste first, then renegotiate suppliers.")
    assert ask(ai, "How do I reduce the cost of running a restaurant?") == "Cut waste first, then renegotiate suppliers."
    assert len(ai.calls) == 1


def test_the_answer_comes_back_as_written_with_no_scripted_question():
    assert ask(FakeAI("Tokyo.")) == "Tokyo."


def test_the_firm_facts_reach_the_model_with_the_question():
    ai = FakeAI("Tokyo.")
    ask(ai)
    system = ai.calls[0]["messages"][0]
    assert system["role"] == "system" and SITE_KNOWLEDGE in system["content"]


@pytest.mark.parametrize(
    "invented",
    [
        "A consultation is $500.",
        "Our packages start at $4,000 for a small build.",
        "Launch MVP is 9,000 USD.",
        "Build My Version charges €300 for this.",
    ],
)
def test_an_invented_price_for_the_firm_never_reaches_the_visitor(invented):
    assert ask(FakeAI(invented), "What do you charge?") == PRICING_SAFE_REPLY


def test_the_published_fee_is_stated_freely():
    reply = "A consultation is $200, and it ends with the answer and the full package."
    assert ask(FakeAI(reply), "How much is a consultation?") == reply


def test_money_in_a_general_answer_is_left_alone():
    reply = "A small unit there might rent for $60,000 a year. Budget $15,000 for the fit-out."
    assert ask(FakeAI(reply), "What does a small café cost to open?") == reply


def test_a_failed_model_falls_back_to_the_second_one():
    ai = FakeAI(RuntimeError("provider down"), "Tokyo.")
    assert ask(ai) == "Tokyo."
    assert [c["model"] for c in ai.calls] == ["primary/model", "backup/model"]


def test_an_empty_answer_falls_back_to_the_second_one():
    ai = FakeAI("   ", "Tokyo.")
    assert ask(ai) == "Tokyo."


def test_each_ask_fits_inside_the_browser_timeout():
    ai = FakeAI(RuntimeError("slow"), "Tokyo.")
    ask(ai)
    assert sum(c["timeout_seconds"] * c["transport_attempts"] for c in ai.calls) < 45


def test_when_both_models_fail_it_says_so_and_does_not_pitch():
    reply = ask(FakeAI(RuntimeError("a"), RuntimeError("b")))
    assert "couldn’t get an answer" in reply
    assert "industry" not in reply and "automate" not in reply


def test_a_long_conversation_keeps_its_context():
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(19)]
    ai = FakeAI("Tokyo.")
    ask(ai, history=history)
    assert len(ai.calls[0]["messages"]) == 21  # the system message and all twenty turns


def test_visitors_behind_the_proxy_each_get_their_own_limit():
    class Req:
        headers = {"x-forwarded-for": "6.6.6.6, 203.0.113.9"}
        client = type("C", (), {"host": "10.0.0.2"})()

    assert router.client_key(Req()) == "203.0.113.9"  # the last hop is the one the proxy saw


def test_a_direct_connection_cannot_forge_its_address():
    class Req:
        headers = {"x-forwarded-for": "6.6.6.6"}
        client = type("C", (), {"host": "8.8.8.8"})()

    assert router.client_key(Req()) == "8.8.8.8"


def test_without_a_proxy_the_connection_address_is_used():
    class Req:
        headers: dict = {}
        client = type("C", (), {"host": "10.0.0.2"})()

    assert router.client_key(Req()) == "10.0.0.2"


def test_the_assistant_stops_when_the_daily_budget_is_spent(monkeypatch):
    class Cfg:
        ai_enabled = True
        site_chat_enabled = True
        daily_budget_usd = 1.0
        request_budget_usd = None

    class Db:
        def close(self):
            pass

    monkeypatch.setattr(admin_ops, "get_settings", lambda: Cfg())
    monkeypatch.setattr(admin_ops, "SessionLocal", Db)
    monkeypatch.setattr(admin_ops, "cost_since", lambda db, start: 2.0)
    allowed, _ = admin_ops.ai_is_allowed("site_chat")
    assert allowed is False
