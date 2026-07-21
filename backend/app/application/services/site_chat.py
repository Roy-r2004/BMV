"""Public site chatbot — grounded answers, cheap model, no price hallucination."""
from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from threading import Lock

from app.application.services.site_chat_knowledge import PRICING_SAFE_REPLY, SITE_KNOWLEDGE
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.infrastructure.logging import get_logger

log = get_logger("SiteChat")

_MAX_HISTORY = 8
_MAX_MSG_CHARS = 800
_MAX_REPLY_TOKENS = 480

_SYSTEM_PROMPT = f"""You are the Build My Version site guide — a warm, curious host on the marketing site.
Talk like a helpful human, not a brochure. Keep it moving with questions.

Conversation style (required):
- Sound natural and friendly — short paragraphs, plain language
- Answer in 2–4 sentences using ONLY the grounded facts below
- ALWAYS end with one clear follow-up question (to learn their industry, goal, or next step)
- Ask about their business when useful: industry, biggest time-sink, what they want to automate
- Offer a next step with a path when it helps (/submit, /demo, /solutions, /about, /examples)
- Do NOT dump long lists and stop. Do NOT sound robotic or like FAQ copy-paste

Hard rules (never break):
1. NEVER invent or guess prices, fees, monthly costs, discounts, or currency amounts.
2. If asked about cost/pricing/budget: say pricing is a custom quote after scope; start free with the preview; name Launch / Growth / Custom + timelines only — no dollars; then ask a question.
3. If unsure: say you don't have that detail — do not invent — then ask what they're trying to do.
4. Never claim Stripe checkout or public price lists exist.
5. Never invent customer names, ROI $, or fake case studies.

GROUNDED FACTS:
{SITE_KNOWLEDGE}
"""

_PRICE_ASK = re.compile(
    r"\b("
    r"price|pricing|cost|costs|how\s+much|quote|budget|fee|fees|"
    r"expensive|cheap|afford|\$|€|£|usd|eur|gbp|per\s+month|monthly|"
    r"subscription|checkout|stripe"
    r")\b",
    re.I,
)

_MONEY_IN_REPLY = re.compile(
    r"(?:\$|€|£)\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|EUR|GBP|dollars?|euros?|pounds?)\b",
    re.I,
)

# Simple per-IP rate limit
_rate_lock = Lock()
_rate_hits: dict[str, deque[float]] = defaultdict(deque)
_RATE_WINDOW_S = 60.0
_RATE_MAX = 12


def rate_limit_ok(client_key: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        q = _rate_hits[client_key]
        while q and now - q[0] > _RATE_WINDOW_S:
            q.popleft()
        if len(q) >= _RATE_MAX:
            return False
        q.append(now)
        return True


def _sanitize_history(messages: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for m in messages[-_MAX_HISTORY:]:
        role = (m.get("role") or "").strip().lower()
        content = (m.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        cleaned.append({"role": role, "content": content[:_MAX_MSG_CHARS]})
    return cleaned


def _is_pricing_question(text: str) -> bool:
    return bool(_PRICE_ASK.search(text or ""))


def _scrub_money(text: str) -> str:
    if not text:
        return text
    if not _MONEY_IN_REPLY.search(text):
        return text.strip()
    # Model invented currency — replace whole reply with safe pricing copy
    return PRICING_SAFE_REPLY


_FOLLOWUPS = (
    "What kind of business are you running?",
    "What’s the biggest thing you’d love to automate first?",
    "Want me to point you to the free start at /submit, or browse /solutions for your industry?",
    "Curious — are you exploring, or ready to see a preview?",
)


def _ensure_question(text: str, last_user: str = "") -> str:
    """Nudge brochure-style replies into a real conversation."""
    cleaned = (text or "").strip().rstrip('"').rstrip("'")
    if not cleaned:
        return cleaned
    # Already conversational if any question mark appears
    if "?" in cleaned:
        return cleaned
    low = (last_user or "").lower()
    if any(w in low for w in ("solution", "industry", "healthcare", "restaurant", "retail")):
        q = "Which industry are you in — or should I walk you through /solutions?"
    elif any(w in low for w in ("package", "plan", "launch", "growth", "custom")):
        q = "Are you aiming to launch fast, or do you need staff roles and care (Growth)?"
    elif any(w in low for w in ("start", "begin", "how do", "preview")):
        q = "Want me to send you straight to /submit for the free preview?"
    else:
        q = _FOLLOWUPS[sum(ord(c) for c in cleaned[-12:]) % len(_FOLLOWUPS)]
    return f"{cleaned.rstrip('.')}. {q}"


def site_chat_model() -> str:
    if settings.AI_PROVIDER == "openrouter":
        return settings.SITE_CHAT_MODEL
    return settings.SITE_CHAT_MODEL or settings.TEXT_MODEL


def reply_site_chat(
    ai: AIProvider,
    *,
    messages: list[dict],
    page_path: str | None = None,
) -> str:
    history = _sanitize_history(messages)
    if not history or history[-1]["role"] != "user":
        return (
            "Hey — I’m here to help you find the right AI fit. "
            "What kind of business are you running?"
        )

    last_user = history[-1]["content"]

    # Deterministic pricing path — zero hallucination risk
    if _is_pricing_question(last_user):
        return PRICING_SAFE_REPLY

    if not ai.is_available():
        return (
            "I’m briefly offline, but the short version: we’re an AI consultancy — "
            "free preview at /submit, live builds at /demo, industry solutions at /solutions. "
            "Pricing is always a custom quote. What are you trying to automate?"
        )

    context_note = ""
    if page_path:
        context_note = f"\nThe visitor is currently on: {page_path[:120]}\n"

    llm_messages = [
        {"role": "system", "content": _SYSTEM_PROMPT + context_note},
        *history,
    ]

    model = site_chat_model()
    try:
        raw = ai.ask_chat(
            model,
            llm_messages,
            max_tokens=_MAX_REPLY_TOKENS,
            temperature=0.45,
        )
    except Exception as exc:
        log.warning("site chat failed (%s): %s", model, exc)
        return (
            "I hit a snag for a second — but you can still start free at /submit, "
            "browse /demo, or explore /solutions. What industry are you in?"
        )

    text = (raw or "").strip()
    if not text:
        return (
            "I didn’t quite catch that — no worries. "
            "Are you curious about what we do, packages, or how to start a free preview?"
        )

    return _ensure_question(_scrub_money(text), last_user)
