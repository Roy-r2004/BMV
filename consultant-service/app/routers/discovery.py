"""Discovery questions — the intake step that makes the numbers honest.

One cheap fast-model call reads the brief and writes the 3-6 questions a
consultant would open with, tailored to THIS business and its stage
(operating vs. not-yet-launched). The answers flow into the decomposition
stage, which is only allowed to compute with numbers the owner gave.

Fails open: any failure returns a generic-but-sane fallback set for the
stage, marked source="fallback" — the intake never blocks on this call.
"""

import json
import logging

from fastapi import APIRouter, Depends, Form, Header, HTTPException
from sqlalchemy.orm import Session

from app import auth_client
from app.ai import provider
from app.config import settings
from app.database import get_db
from app.pipeline._shared import build_engagement_register, extract_json_from_text, log_usage
from app.templating import render

logger = logging.getLogger("consultant.discovery")

router = APIRouter(prefix="/api/discovery", tags=["discovery"])

_ALLOWED_ENGAGEMENT_TYPES = {"full", "capability"}

# The stage-generic sets used when the tailoring call fails. Deliberately
# phrased to fit any business; the AI's whole job is to beat these.
_FALLBACK_OPERATING = [
    {
        "id": "admin-hours",
        "label": "How many hours a week go to repetitive admin?",
        "placeholder": "e.g. 12 hours on bookings, follow-ups, paperwork",
        "why": "Time is the first cost your system removes — this sizes it.",
    },
    {
        "id": "avg-value",
        "label": "What is one sale, visit or job worth on average?",
        "placeholder": "e.g. $85",
        "why": "Lets every recovered hour and missed sale be valued at your own prices.",
    },
    {
        "id": "monthly-volume",
        "label": "How many customers, orders or jobs in a typical month?",
        "placeholder": "e.g. 340",
        "why": "Sets the scale every other number multiplies against.",
    },
    {
        "id": "loss-rate",
        "label": "What share of bookings or leads never turn into money?",
        "placeholder": "e.g. about 20% no-show or go quiet",
        "why": "Recovered losses are usually the fastest payback — this sizes them.",
    },
]

_FALLBACK_CAPABILITY = [
    {
        "id": "problem-frequency",
        "label": "How often does this problem happen — per day or per week?",
        "placeholder": "e.g. 15 times a week",
        "why": "Frequency times cost is the size of the problem.",
    },
    {
        "id": "hours-lost",
        "label": "How many hours a week does dealing with it take?",
        "placeholder": "e.g. 6 hours",
        "why": "The time this capability hands back, in your own hours.",
    },
    {
        "id": "value-lost",
        "label": "What does one missed or mishandled case cost you?",
        "placeholder": "e.g. a $120 booking",
        "why": "Puts your own price on every failure the fix prevents.",
    },
    {
        "id": "current-tooling",
        "label": "What do you spend monthly on tools for this today, if anything?",
        "placeholder": "e.g. $50/month",
        "why": "The honest baseline any new tool must beat.",
    },
]

_FALLBACK_OPENING = [
    {
        "id": "planned-price",
        "label": "What do you plan to charge for one sale, visit or job?",
        "placeholder": "e.g. $30",
        "why": "Anchors every capacity and payback calculation in your own pricing.",
    },
    {
        "id": "planned-capacity",
        "label": "How many customers or orders are you built to handle per week at launch?",
        "placeholder": "e.g. 200",
        "why": "Your target capacity is what the system has to keep full.",
    },
    {
        "id": "planned-hires",
        "label": "How many people do you plan to hire for phones, bookings or admin?",
        "placeholder": "e.g. 1 part-time",
        "why": "Every role the system covers is a hire you can delay.",
    },
    {
        "id": "launch-budget",
        "label": "What is your launch budget for tools and software?",
        "placeholder": "e.g. $5,000",
        "why": "Keeps every recommendation inside what you actually planned to spend.",
    },
]


def _sanitize(questions: list) -> list[dict]:
    """Keep only well-formed questions, clamped to the configured maximum."""
    cleaned = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        label = str(q.get("label") or "").strip()
        if not label:
            continue
        cleaned.append(
            {
                "id": str(q.get("id") or f"q-{len(cleaned) + 1}").strip()[:60],
                "label": label[:200],
                "placeholder": str(q.get("placeholder") or "").strip()[:120],
                "why": str(q.get("why") or "").strip()[:200],
            }
        )
    return cleaned[: settings.MAX_DISCOVERY_QUESTIONS]


@router.post("/questions")
def discovery_questions(
    business_name: str = Form(...),
    business_description: str = Form(...),
    industry: str | None = Form(None),
    operating_stage: str | None = Form(None),
    engagement_type: str | None = Form(None),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    if auth_client.resolve_user(authorization) is None:
        raise HTTPException(status_code=401, detail="Sign in to start your engagement")
    operating = operating_stage != "opening"
    if engagement_type == "capability":
        fallback = _FALLBACK_CAPABILITY
    else:
        fallback = _FALLBACK_OPERATING if operating else _FALLBACK_OPENING

    try:
        prompt = render(
            "discovery.j2",
            business_name=business_name,
            business_description=business_description,
            industry=industry or "unspecified",
            operating=operating,
            capability=engagement_type == "capability",
            min_questions=settings.MIN_DISCOVERY_QUESTIONS,
            max_questions=settings.MAX_DISCOVERY_QUESTIONS,
        )
        body = provider.chat(
            settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=1200,
        )
        questions = _sanitize(extract_json_from_text(body["choices"][0]["message"]["content"]).get("questions") or [])
        # No request exists yet — the call is still ledgered, unattributed.
        log_usage(
            db, None,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="discovery",
            usage=body.get("usage"), success=True,
        )
        if len(questions) < settings.MIN_DISCOVERY_QUESTIONS:
            return {"questions": fallback, "source": "fallback"}
        return {"questions": questions, "source": "ai"}
    except Exception as exc:
        log_usage(
            db, None,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="discovery",
            success=False, error=str(exc)[:500],
        )
        logger.warning("discovery tailoring failed, serving fallback: %s", exc)
        return {"questions": fallback, "source": "fallback"}


def _format_numbers(raw: str | None) -> str:
    """The discovery answers as prompt lines — same tolerance as the intake:
    malformed client JSON reads as 'none given', never a 500."""
    if not raw:
        return "none given"
    try:
        pairs = json.loads(raw)
    except ValueError:
        return "none given"
    if not isinstance(pairs, list):
        return "none given"
    lines = [
        f"- {p.get('question')}: {p.get('answer')}"
        for p in pairs
        if isinstance(p, dict) and p.get("question") and p.get("answer")
    ]
    return "\n".join(lines) or "none given"


def _format_conversation(raw: str | None) -> str:
    if not raw:
        return "(empty)"
    try:
        messages = json.loads(raw)
    except ValueError:
        return "(empty)"
    if not isinstance(messages, list):
        return "(empty)"
    lines = []
    for m in messages[-10:]:
        if not (isinstance(m, dict) and m.get("content")):
            continue
        who = "CLIENT" if m.get("role") == "user" else "YOU"
        lines.append(f"{who}: {str(m['content'])[:600]}")
    return "\n".join(lines) or "(empty)"


@router.post("/brief")
def discovery_brief(
    business_name: str = Form(...),
    business_description: str = Form(...),
    industry: str | None = Form(None),
    target_customers: str | None = Form(None),
    main_problem: str | None = Form(None),
    desired_outcome: str | None = Form(None),
    operating_stage: str | None = Form(None),
    engagement_type: str | None = Form(None),
    needs_ai: str | None = Form(None),
    ops_numbers: str | None = Form(None),
    messages: str | None = Form(None),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    if auth_client.resolve_user(authorization) is None:
        raise HTTPException(status_code=401, detail="Sign in to start your engagement")
    """The pre-launch briefing chat: the consultant plays back the brief and
    absorbs corrections. One fast call per turn. Fails open with ok=false —
    the frontend then launches directly; this chat may never block a run."""
    try:
        prompt = render(
            "brief.j2",
            engagement_register=build_engagement_register(
                engagement_type if engagement_type in _ALLOWED_ENGAGEMENT_TYPES else None,
                needs_ai, main_problem, desired_outcome,
            ),
            business_name=business_name,
            business_description=business_description,
            industry=industry or "unspecified",
            target_customers=target_customers or "unspecified",
            main_problem=main_problem or "unspecified",
            desired_outcome=desired_outcome or "unspecified",
            operating_stage="not launched yet — this is a plan" if operating_stage == "opening" else "already operating",
            owner_numbers=_format_numbers(ops_numbers),
            conversation=_format_conversation(messages),
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=900)
        result = extract_json_from_text(body["choices"][0]["message"]["content"])
        reply = str(result.get("reply") or "").strip()
        if not reply:
            raise ValueError("brief turn had no reply")
        addendum = result.get("brief_addendum")
        addendum = str(addendum).strip() if addendum else None
        log_usage(
            db, None,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="brief",
            usage=body.get("usage"), success=True,
        )
        return {"ok": True, "reply": reply[:2500], "brief_addendum": addendum[:2000] if addendum else None}
    except Exception as exc:
        log_usage(
            db, None,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="brief",
            success=False, error=str(exc)[:500],
        )
        logger.warning("brief turn failed open: %s", exc)
        return {"ok": False}
