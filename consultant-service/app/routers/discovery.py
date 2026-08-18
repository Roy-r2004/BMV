"""Discovery questions — the intake step that makes the numbers honest.

One cheap fast-model call reads the brief and writes the 3-6 questions a
consultant would open with, tailored to THIS business and its stage
(operating vs. not-yet-launched). The answers flow into the decomposition
stage, which is only allowed to compute with numbers the owner gave.

Fails open: any failure returns a generic-but-sane fallback set for the
stage, marked source="fallback" — the intake never blocks on this call.
"""

import logging

from fastapi import APIRouter, Depends, Form
from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.database import get_db
from app.pipeline._shared import extract_json_from_text, log_usage
from app.templating import render

logger = logging.getLogger("consultant.discovery")

router = APIRouter(prefix="/api/discovery", tags=["discovery"])

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
    db: Session = Depends(get_db),
):
    operating = operating_stage != "opening"
    fallback = _FALLBACK_OPERATING if operating else _FALLBACK_OPENING

    try:
        prompt = render(
            "discovery.j2",
            business_name=business_name,
            business_description=business_description,
            industry=industry or "unspecified",
            operating=operating,
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
