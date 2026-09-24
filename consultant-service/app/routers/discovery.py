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
import re

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


#: Intake fields the conversation can fill, and how to ask for each. The
#: front door now asks one question — what is going wrong — so everything
#: else that used to be a form field is collected here, as dialogue.
FILLABLE = {
    "business_name": "the business's name",
    "business_description": "what the business does or will do, how big it is or will be (staff, rooms, vans, seats), and its hours",
    "target_customers": "who their customers are",
    "industry": "what trade or sector they are in",
    "desired_outcome": "what fixing this would get them",
    "revenue_today": "how they make money — fees, packages, subscriptions, retainers",
}
# `needs_ai` is deliberately NOT here. It is an enum the engagement register
# compares against exactly ("no" suppresses every AI recommendation), and a
# conversational answer — "open to anything that works" — stored into it
# matches nothing and silently reads as the default. It is also no longer
# worth asking: `decide` reaches "your problem is not software" from the
# evidence now, which is a better answer than one the client pre-declared
# before anybody had looked at their business.
#: Without these two, `POST /api/requests` refuses the engagement — so the
#: interview is not allowed to decide it has enough while they are blank.
REQUIRED_FIELDS = ("business_name", "business_description")


def _key(label: str) -> str:
    """A question's wording, reduced to what it is actually asking."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (label or "").casefold())).strip()


#: Words that carry no subject matter. Removed before comparing questions, so
#: "What is the typical length" and "what's the typical length" reduce to the
#: same thing — the contraction alone defeated plain substring matching.
_FILLER = frozenset(
    "a an and are as at be by can could do does for from give got had has have how "
    "i in is it its many me much of on or our roughly s so such that the their them "
    "then there these they this to typically us was we what when where which who why "
    "will with would you your about average".split())


def _content(key: str) -> frozenset[str]:
    return frozenset(w for w in key.split() if w not in _FILLER and len(w) > 2)


def _repeats(key: str, seen: set[str]) -> bool:
    """Is this the same question again, dressed differently?

    Exact matching is not enough. A round-2 question that went unanswered came
    back in round 3 with a clause bolted on the front — "You mentioned turning
    away work and a waitlist. To understand capacity, what's the typical
    length of an appointment?" — word-for-word the earlier question apart from
    a contraction, and it sailed straight past an equality check.

    So a question whose subject matter is wholly contained in one already
    asked is a repeat. The four-word floor stops a genuinely short question
    ("How many rooms?") from being swallowed by any long one that happens to
    mention rooms.
    """
    if not key:
        return True
    tokens = _content(key)
    for prior in seen:
        if key == prior:
            return True
        prior_tokens = _content(prior)
        if not tokens or not prior_tokens:
            continue
        smaller, larger = sorted((tokens, prior_tokens), key=len)
        if len(smaller) >= 4 and smaller <= larger:
            return True
    return False


@router.post("/interview")
def interview(
    # Optional, unlike `/questions`: the front door asks what is going wrong
    # and nothing else, so on the first round the business does not have a
    # name yet. Finding that out is this endpoint's job.
    business_name: str | None = Form(None),
    business_description: str | None = Form(None),
    industry: str | None = Form(None),
    operating_stage: str | None = Form(None),
    engagement_type: str | None = Form(None),
    needs_ai: str | None = Form(None),
    main_problem: str | None = Form(None),
    desired_outcome: str | None = Form(None),
    ops_numbers: str | None = Form(None),
    asked: str | None = Form(None),
    known: str | None = Form(None),
    round: int = Form(1),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """The next questions worth asking — or none, which ends the interview.

    Replaces the one-shot tailored set with a loop that reads what they have
    already answered. The static set asked four questions whatever you said;
    this one can follow "340 visits a month at $85" with "what caps that
    number", which is the question that decides whether their problem is
    demand or capacity.

    `done` is authoritative and the client stops on it. It goes true when the
    model says it has enough, when the round cap is reached, or when a round
    produced nothing usable — a failed call must END the interview rather
    than leave the client stuck on a step that will not advance. Round 1
    falls back to the static set, so the worst case is the behaviour that
    existed before this endpoint.
    """
    if auth_client.resolve_user(authorization) is None:
        raise HTTPException(status_code=401, detail="Sign in to start your engagement")

    operating = operating_stage != "opening"
    if engagement_type == "capability":
        fallback = _FALLBACK_CAPABILITY
    else:
        fallback = _FALLBACK_OPERATING if operating else _FALLBACK_OPENING

    round = max(1, min(int(round or 1), settings.INTERVIEW_MAX_ROUNDS))
    answered = _format_numbers(ops_numbers)

    answered_ids, answered_labels = set(), set()
    try:
        for p in json.loads(ops_numbers or "[]"):
            if isinstance(p, dict):
                answered_ids.add(str(p.get("id") or ""))
                answered_labels.add(str(p.get("question") or "").strip().casefold())
    except (TypeError, ValueError):
        pass

    # Questions they SKIPPED are the ones that get re-asked: the model sees
    # only the answers, so an unanswered question is invisible to it and comes
    # back every round under a fresh id. Filtering by id alone never caught it
    # — one run asked for the receptionist's hours three times in three
    # different wordings. The model is told what it already asked instead.
    skipped = []
    try:
        for label in json.loads(asked or "[]"):
            text = str(label).strip()
            if text and text.casefold() not in answered_labels:
                skipped.append(text)
    except (TypeError, ValueError):
        pass

    # What the conversation has not learned about them yet. Sent by the
    # client so one builder decides it, rather than the prompt guessing from
    # whichever fields happened to be passed as arguments.
    filled = {}
    try:
        raw_known = json.loads(known or "{}")
        if isinstance(raw_known, dict):
            filled = {k: str(v or "").strip() for k, v in raw_known.items()}
    except (TypeError, ValueError):
        pass
    missing = {k: v for k, v in FILLABLE.items() if not filled.get(k)}

    try:
        prompt = render(
            "interview.j2",
            business_name=filled.get("business_name") or business_name or "",
            business_description=filled.get("business_description") or business_description or "",
            industry=filled.get("industry") or industry or "unspecified",
            stage="not launched yet — this is a plan" if not operating else "already operating",
            main_problem=main_problem,
            desired_outcome=desired_outcome,
            engagement_register=build_engagement_register(
                engagement_type if engagement_type in _ALLOWED_ENGAGEMENT_TYPES else None,
                needs_ai, main_problem, desired_outcome,
            ),
            answered=answered,
            skipped="\n".join(f"- {s}" for s in skipped[:12]),
            missing="\n".join(f"- {k}: {v}" for k, v in missing.items()),
            round=round,
            max_rounds=settings.INTERVIEW_MAX_ROUNDS,
            max_questions=settings.INTERVIEW_MAX_PER_ROUND,
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}],
                             max_tokens=1400)
        result = extract_json_from_text(body["choices"][0]["message"]["content"])
        log_usage(db, None, provider="openrouter", model=settings.ANALYSIS_MODEL,
                  purpose=f"interview:{round}", usage=body.get("usage"), success=True)
    except Exception as exc:
        log_usage(db, None, provider="openrouter", model=settings.ANALYSIS_MODEL,
                  purpose=f"interview:{round}", success=False, error=str(exc)[:500])
        logger.warning("interview round %s failed: %s", round, exc)
        if round == 1:
            return {"questions": fallback, "done": True, "source": "fallback", "because": ""}
        return {"questions": [], "done": True, "source": "fallback", "because": ""}

    # Belt and braces behind the prompt: an id or a wording already put to
    # them cannot come back, whatever the model returns.
    seen = {_key(s) for s in skipped} | {_key(s) for s in answered_labels}
    questions = []
    for q in _sanitize(result.get("questions") or []):
        if q["id"] in answered_ids or _repeats(_key(q["label"]), seen):
            continue
        questions.append(q)
        seen.add(_key(q["label"]))
        if len(questions) >= settings.INTERVIEW_MAX_PER_ROUND:
            break

    if round == 1 and not questions:
        # Nothing to ask before anything has been asked is not a consultant
        # who has enough — it is a call that produced nothing.
        return {"questions": fallback, "done": True, "source": "fallback", "because": ""}

    # Which intake field each question fills, where it fills one. Anything
    # not in FILLABLE is dropped rather than trusted — a `field` we do not
    # recognise would write an arbitrary key into the client's form.
    by_id = {q.get("id"): q for q in (result.get("questions") or []) if isinstance(q, dict)}
    for q in questions:
        field = str((by_id.get(q["id"]) or {}).get("field") or "").strip()
        q["field"] = field if field in FILLABLE else ""

    def choice(key: str, allowed: tuple[str, ...]) -> str | None:
        value = str(result.get(key) or "").strip().lower()
        return value if value in allowed else None

    # An engagement still missing a name or a description cannot be launched
    # at all, so the interview does not get to call itself finished while one
    # is blank — whatever it thinks about having enough numbers.
    blocked = [f for f in REQUIRED_FIELDS if not filled.get(f)]
    done = (bool(result.get("enough")) or not questions
            or round >= settings.INTERVIEW_MAX_ROUNDS)
    if blocked and round < settings.INTERVIEW_MAX_ROUNDS:
        done = False

    return {"questions": questions, "done": done, "source": "ai",
            "because": str(result.get("because") or "")[:200],
            "inferred": {"engagement_type": choice("engagement_type", ("capability", "full")),
                         "operating_stage": choice("operating_stage", ("operating", "opening"))},
            "still_needed": blocked}


CASEFILE_MAX_FIGURES = 8


def casefile_sources(main_problem: str | None, ops_numbers: str | None,
                     known: str | None) -> dict[str, str]:
    """Everything they have said, by id — the lines a figure has to be in."""
    sources: dict[str, str] = {}
    if (main_problem or "").strip():
        sources["main_problem"] = main_problem.strip()[:2000]
    try:
        for p in json.loads(ops_numbers or "[]"):
            if isinstance(p, dict) and str(p.get("answer") or "").strip():
                qid = str(p.get("id") or f"q{len(sources)}")[:40]
                sources[qid] = f"{str(p.get('question') or '').strip()[:200]} — {str(p['answer']).strip()[:600]}"
    except (TypeError, ValueError):
        pass
    try:
        raw_known = json.loads(known or "{}")
        if isinstance(raw_known, dict):
            for k, v in raw_known.items():
                if k in FILLABLE and str(v or "").strip():
                    sources[f"field:{k}"] = str(v).strip()[:1000]
    except (TypeError, ValueError):
        pass
    return sources


def shape_casefile(raw: dict, sources: dict[str, str], playback: bool,
                   derived: list[float] | None = None) -> dict:
    """Keep only what is really in their words. Pure. `derived` are the
    capacity totals computed from those words, which the summary may use."""
    from app.pipeline import figures

    out: dict = {"figures": []}
    seen = set()
    for f in (raw.get("figures") or []) if isinstance(raw, dict) else []:
        if not isinstance(f, dict):
            continue
        src = str(f.get("source") or "")
        text = sources.get(src)
        token = str(f.get("token") or "").strip()
        value = str(f.get("value") or "").strip()[:24]
        label = str(f.get("label") or "").strip()[:60]
        if not text or not token or not value or not figures.quoted(token, [text]):
            continue
        in_token = figures.given([token])
        value_nums = figures.numbers_in(value, words=True)
        value_hours = figures.times_in(value)
        # A time on its own ("6pm — classes") is not a figure about the
        # business; it filled half the case file with clock faces.
        if not value_nums:
            continue
        if not all(figures.holds(v, in_token) for v in value_nums):
            continue
        if not set(value_hours) <= figures.given_hours([token]):
            continue
        if figures.unsupported(label, figures.given([text]), lenient_below=0,
                               hours=figures.given_hours([text])):
            continue
        key = (src, value.casefold())
        if key in seen:
            continue
        seen.add(key)
        out["figures"].append({"source": src, "token": token, "value": value, "label": label})
        if len(out["figures"]) >= CASEFILE_MAX_FIGURES:
            break
    if playback and isinstance(raw, dict):
        all_text = list(sources.values())
        summary = str(raw.get("summary") or "").strip()[:600]
        allowed = figures.given(all_text) | {float(v) for v in derived or []}
        hours = figures.given_hours(all_text)
        out["summary"] = summary if summary and not figures.unsupported(summary, allowed, hours=hours) else ""
        words = str(raw.get("their_words") or "").strip()[:400]
        out["their_words"] = words if words and figures.quoted(words, all_text) else ""
        fix = raw.get("their_fix")
        fix = str(fix).strip().rstrip(".")[:80] if fix else ""
        out["their_fix"] = fix if fix and not figures.unsupported(fix, figures.given(all_text), hours=hours) else None
    return out


@router.post("/casefile")
def casefile(
    main_problem: str | None = Form(None),
    ops_numbers: str | None = Form(None),
    known: str | None = Form(None),
    operating_stage: str | None = Form(None),
    playback: bool = Form(False),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """What they have told us so far, as figures — and their week, if it can
    be drawn yet. Called as they answer, so the case file on screen fills in
    while they talk; and once more before the diagnosis, to play it back.

    Two fast calls, in parallel. Every figure is checked against the line it
    was quoted from, and the week against their words (`capacity.shape`).
    Fails open to an empty file: this is a courtesy on screen, and a failure
    here must never stop the conversation.
    """
    from concurrent.futures import ThreadPoolExecutor

    from app.pipeline import capacity

    if auth_client.resolve_user(authorization) is None:
        raise HTTPException(status_code=401, detail="Sign in to start your engagement")
    sources = casefile_sources(main_problem, ops_numbers, known)
    if not sources:
        return {"figures": [], "capacity": None}

    def read_figures():
        prompt = render("casefile.j2", sources="\n".join(f"[{k}] {v}" for k, v in sources.items()),
                        max_figures=CASEFILE_MAX_FIGURES, playback=playback)
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}],
                             max_tokens=1600 if playback else 1100)
        return extract_json_from_text(body["choices"][0]["message"]["content"]), body.get("usage")

    stage = "not launched yet — this is a plan" if operating_stage == "opening" else "already operating"
    with ThreadPoolExecutor(max_workers=2) as pool:
        fig_future = pool.submit(read_figures)
        cap_future = pool.submit(capacity.read, list(sources.values()), stage)
        try:
            raw, usage = fig_future.result()
            log_usage(db, None, provider="openrouter", model=settings.ANALYSIS_MODEL,
                      purpose="casefile", usage=usage, success=True)
        except Exception as exc:
            log_usage(db, None, provider="openrouter", model=settings.ANALYSIS_MODEL,
                      purpose="casefile", success=False, error=str(exc)[:500])
            logger.warning("casefile failed open: %s", str(exc)[:200])
            raw = {}
        picture, cap_usage, cap_error = cap_future.result()
    if cap_usage is not None or cap_error is not None:
        log_usage(db, None, provider="openrouter", model=settings.ANALYSIS_MODEL,
                  purpose="casefile:capacity", usage=cap_usage, success=cap_error is None, error=cap_error)

    out = shape_casefile(raw, sources, playback,
                         [d["value"] for d in (picture or {}).get("derived") or []])
    out["capacity"] = picture
    return out


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
