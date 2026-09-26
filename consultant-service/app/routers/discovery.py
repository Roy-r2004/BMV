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
import os
import re

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
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


# ── the brief and the fact list ──────────────────────────────────────────────
# A serious engagement agrees the question before it asks anything, and works
# from a data request list: every fact needed to answer it and to write plans
# a team could build from. The list is written per business — how many facts,
# and which, depend on what they asked — and bounded, never fixed.

FACTS_MIN, FACTS_MAX = 10, 30
#: How many facts one round of the interview may add, when an answer shows
#: the list missed something. The list can grow; it cannot run away.
FACTS_ADDED_PER_ROUND = 4
FACT_STATUSES = ("need", "got", "estimate", "file")

_FALLBACK_FACTS = {
    "operating": [
        ("business_name", "The business", "Name", "business_name"),
        ("what_you_do", "The business", "What you do, and how big", "business_description"),
        ("customers", "Customers", "Who your customers are", "target_customers"),
        ("find_you", "Customers", "How customers find you", ""),
        ("volume", "Customers", "Customers or jobs a week", ""),
        ("price", "Money", "What you charge", ""),
        ("revenue", "Money", "How you make money", "revenue_today"),
        ("costs", "Money", "Monthly running costs", ""),
        ("capacity", "Capacity", "Most you can handle a week", ""),
        ("used", "Capacity", "How much of that is used", ""),
        ("tools", "How you run today", "Tools you run it on", ""),
        ("people", "How you run today", "Who does what", ""),
        ("success", "Goals and limits", "What success looks like", "desired_outcome"),
        ("timeline", "Goals and limits", "When you need it", ""),
        ("fixed", "Goals and limits", "What won't change", ""),
    ],
    "opening": [
        ("business_name", "The business", "Name", "business_name"),
        ("what_you_do", "The business", "What it will do, and how big", "business_description"),
        ("customers", "Customers", "Who it is for", "target_customers"),
        ("find_you", "Customers", "How they will find you", ""),
        ("where", "The business", "Where it will be", ""),
        ("price", "Money", "What you plan to charge", ""),
        ("revenue", "Money", "How it will make money", "revenue_today"),
        ("budget", "Money", "Budget to open", ""),
        ("costs", "Money", "Expected monthly costs", ""),
        ("capacity", "Capacity", "Most it could handle a week", ""),
        ("people", "Capacity", "Who will run it", ""),
        ("launch", "Goals and limits", "When you want to open", ""),
        ("success", "Goals and limits", "What success looks like", "desired_outcome"),
        ("fixed", "Goals and limits", "What won't change", ""),
    ],
}


def _slug(text: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", (text or "").casefold())).strip("_")[:40]


def fallback_facts(stage: str | None) -> list[dict]:
    rows = _FALLBACK_FACTS["opening" if stage == "opening" else "operating"]
    return [{"key": k, "group": g, "label": lbl, "field": f, "status": "need", "value": ""}
            for k, g, lbl, f in rows]


def _fact_value(value, quote, texts: list[str]) -> str:
    """A value read off their words, kept only when the words say it: the
    quote must be theirs, and every number in the value must be in the quote."""
    from app.pipeline import figures

    value = str(value or "").strip()[:60]
    quote = str(quote or "").strip()
    if not value or not quote or not figures.quoted(quote, texts):
        return ""
    in_quote = figures.given([quote])
    if not all(figures.holds(v, in_quote) for v in figures.numbers_in(value, words=True)):
        return ""
    return value


def shape_scope(raw: dict, main_problem: str) -> dict:
    """The brief and its fact list, bounded and checked. Pure.

    Anything missing is filled from a generic list rather than left thin: an
    interview with nothing to ask for would end before it started. The two
    facts the engagement cannot launch without are always on it.
    """
    raw = raw if isinstance(raw, dict) else {}

    def text(v, limit: int) -> str:
        return re.sub(r"\s+", " ", str(v or "")).strip()[:limit]

    stage = text(raw.get("operating_stage"), 12).lower()
    stage = stage if stage in ("operating", "opening") else None
    kind = text(raw.get("engagement_type"), 12).lower()
    kind = kind if kind in ("capability", "full") else None

    question = text(raw.get("question"), 240)
    if len(question) < 15 or not question.endswith("?"):
        question = ""
    lets_raw = raw.get("lets") if isinstance(raw.get("lets"), dict) else {}
    lets = {k: text(lets_raw.get(k), 120) for k in ("know", "see", "have")}
    in_scope = [s for s in (text(x, 90) for x in (raw.get("in_scope") or [])[:5]) if s]
    out_scope = [s for s in (text(x, 90) for x in (raw.get("out_scope") or [])[:4]) if s]

    facts: list[dict] = []
    seen_keys: set[str] = set()
    seen_fields: set[str] = set()
    for f in raw.get("facts") or []:
        if not isinstance(f, dict) or len(facts) >= FACTS_MAX:
            continue
        label = text(f.get("label"), 60)
        key = _slug(str(f.get("key") or label))
        if not label or not key or key in seen_keys:
            continue
        field = text(f.get("field"), 30)
        field = field if field in FILLABLE and field not in seen_fields else ""
        value = _fact_value(f.get("value"), f.get("quote"), [main_problem])
        facts.append({"key": key, "group": text(f.get("group"), 30) or "The business",
                      "label": label, "field": field,
                      "status": "got" if value else "need", "value": value})
        seen_keys.add(key)
        if field:
            seen_fields.add(field)

    # The engagement cannot launch without these two, so they are on the list
    # whatever the model wrote — first, where a person would expect them.
    for base in reversed(fallback_facts(stage)[:2]):
        if base["field"] not in seen_fields:
            key = base["key"] if base["key"] not in seen_keys else f"{base['key']}_1"
            facts.insert(0, {**base, "key": key})
            seen_keys.add(key)
            seen_fields.add(base["field"])
    for base in fallback_facts(stage):
        if len(facts) >= FACTS_MIN:
            break
        if base["key"] in seen_keys or (base["field"] and base["field"] in seen_fields):
            continue
        facts.append(base)
        seen_keys.add(base["key"])
        if base["field"]:
            seen_fields.add(base["field"])

    return {
        "question": question,
        "lets": lets,
        "in_scope": in_scope,
        "out_scope": out_scope,
        "facts": facts[:FACTS_MAX],
        "inferred": {"operating_stage": stage, "engagement_type": kind},
        "source": "ai" if question and raw.get("facts") else "fallback",
    }


@router.post("/scope")
def scope(
    main_problem: str = Form(...),
    site_url: str | None = Form(None),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """The brief: the question we will answer, and the list of facts we need.

    Shown to them before the first question, the way a serious engagement
    agrees its problem statement before any analysis. Fails open to a generic
    fact list and an empty question, which the page states plainly rather
    than inventing one.
    """
    if auth_client.resolve_user(authorization) is None:
        raise HTTPException(status_code=401, detail="Sign in to start your engagement")
    problem = (main_problem or "").strip()[:2000]
    if len(problem) < 10:
        raise HTTPException(status_code=422, detail="Tell us what you're trying to work out first")
    raw: dict = {}
    try:
        prompt = render("scope.j2", main_problem=problem, site_url=(site_url or "").strip()[:200],
                        facts_min=FACTS_MIN, facts_max=FACTS_MAX, fields=FILLABLE)
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}],
                             max_tokens=3000)
        raw = extract_json_from_text(body["choices"][0]["message"]["content"])
        log_usage(db, None, provider="openrouter", model=settings.ANALYSIS_MODEL,
                  purpose="scope", usage=body.get("usage"), success=True)
    except Exception as exc:
        log_usage(db, None, provider="openrouter", model=settings.ANALYSIS_MODEL,
                  purpose="scope", success=False, error=str(exc)[:500])
        logger.warning("scope failed open: %s", str(exc)[:200])
    return shape_scope(raw, problem)


@router.post("/read-file")
async def read_file(
    file: UploadFile = File(...),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """Read the figures out of a file dropped in during the interview, so the
    fact list fills from it at once instead of after launch. Every figure is
    checked against the cell it came from (`evidence.extract`); the same file
    is sent again with the engagement and read as evidence there."""
    from app.pipeline import evidence

    if auth_client.resolve_user(authorization) is None:
        raise HTTPException(status_code=401, detail="Sign in to start your engagement")
    name = os.path.basename(file.filename or "upload")[:120]
    if not name.lower().endswith(evidence.SUPPORTED):
        raise HTTPException(status_code=422, detail=f"We can't read {name}. Send a spreadsheet, CSV or PDF.")
    data = await file.read(evidence.MAX_FILE_BYTES + 1)
    if len(data) > evidence.MAX_FILE_BYTES:
        raise HTTPException(status_code=422, detail=f"{name} is larger than 8 MB.")
    try:
        tables = evidence.read_tables(data, name)
    except evidence.UnreadableFile as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    found, _ = evidence.extract(db, None, tables, name) if tables else ([], 0)
    lines = []
    for c in found:
        value = c.get("value")
        shown = f"{value:,.0f}" if isinstance(value, (int, float)) and float(value).is_integer() else str(value)
        lines.append(f"{shown} {c.get('unit') or ''}".strip() + (f": {c['text']}" if c.get("text") else "") + f" (from {name})")
    return {"file": name, "figures": lines[:40]}


def parse_facts(raw: str | None) -> list[dict]:
    """The fact list as the client sends it back: bounded, statuses checked."""
    try:
        items = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    out, seen = [], set()
    for f in items if isinstance(items, list) else []:
        if not isinstance(f, dict):
            continue
        key = _slug(str(f.get("key") or ""))
        label = str(f.get("label") or "").strip()[:60]
        if not key or not label or key in seen:
            continue
        status = str(f.get("status") or "need")
        out.append({"key": key, "group": str(f.get("group") or "").strip()[:30], "label": label,
                    "field": str(f.get("field") or "") if f.get("field") in FILLABLE else "",
                    "status": status if status in FACT_STATUSES else "need",
                    "value": str(f.get("value") or "").strip()[:60]})
        seen.add(key)
        if len(out) >= FACTS_MAX + FACTS_ADDED_PER_ROUND * 4:
            break
    return out


def shape_fact_updates(raw_updates, raw_new, facts: list[dict], texts: list[str]) -> tuple[list[dict], list[dict]]:
    """What their latest answers settled, and what the list was missing. Pure.

    A value is kept only when every number in it is one they gave — in an
    answer, a file, or what they first wrote. A fact they told us they don't
    know stays ours to estimate; an answer never overwrites that silently.
    """
    from app.pipeline import figures

    allowed = figures.given(texts)
    hours = figures.given_hours(texts)
    by_key = {f["key"]: f for f in facts}
    updates = []
    for u in raw_updates if isinstance(raw_updates, list) else []:
        if not isinstance(u, dict):
            continue
        key = _slug(str(u.get("key") or ""))
        value = re.sub(r"\s+", " ", str(u.get("value") or "")).strip()[:60]
        if key not in by_key or not value or by_key[key]["status"] == "estimate":
            continue
        # The prompt marks what we lack as "NOT KNOWN YET"; a model that
        # echoes that back has not learned the fact, it has read our note.
        if re.search(r"\b(not known|unknown|not (yet )?(given|stated|provided)|n/?a)\b", value, re.I):
            continue
        if figures.unsupported(value, allowed, lenient_below=0, hours=hours):
            continue
        updates.append({"key": key, "value": value})
    added = []
    room = max(0, min(FACTS_ADDED_PER_ROUND, FACTS_MAX + FACTS_ADDED_PER_ROUND * 4 - len(facts)))
    for n in raw_new if isinstance(raw_new, list) else []:
        if not isinstance(n, dict) or len(added) >= room:
            continue
        label = re.sub(r"\s+", " ", str(n.get("label") or "")).strip()[:60]
        key = _slug(str(n.get("key") or label))
        if not label or not key or key in by_key or any(a["key"] == key for a in added):
            continue
        added.append({"key": key, "group": str(n.get("group") or "More we need").strip()[:30],
                      "label": label, "field": "", "status": "need", "value": ""})
    return updates, added


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
    facts: str | None = Form(None),
    file_facts: str | None = Form(None),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """The next questions worth asking — or none, which ends the interview.

    With a fact list (the brief's data request list), the interview works
    through it: each round reads what their answers settled, asks about what
    is still needed, and ends only when nothing is — every fact gathered, or
    marked as one they don't know and we will estimate. That is the point of
    the list: we keep asking until we have what the plans need, and the
    owner never has to go and fetch anything.

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

    fact_list = parse_facts(facts)
    try:
        from_files = [str(x).strip()[:200] for x in json.loads(file_facts or "[]") if str(x).strip()][:40]
    except (TypeError, ValueError):
        from_files = []
    fact_lines = "\n".join(
        f"- {f['key']} [{f['group']}] {f['label']}: "
        + {"got": f"GOT — {f['value']}", "file": f"GOT FROM THEIR FILE — {f['value']}",
           "estimate": "THEY DON'T KNOW — we will estimate it; do not ask again"}.get(f["status"], "STILL NEEDED")
        for f in fact_list)

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
            facts=fact_lines,
            file_facts="\n".join(f"- {x}" for x in from_files),
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}],
                             max_tokens=2200)
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

    # What their answers settled, and what the list turned out to be missing.
    texts = [main_problem or "", answered, *from_files, *[v for v in filled.values() if v]]
    updates, added = shape_fact_updates(result.get("updates"), result.get("new_facts"), fact_list, texts)
    keys = {f["key"] for f in fact_list} | {a["key"] for a in added}
    for q in questions:
        src = by_id.get(q["id"]) or {}
        q["fills"] = [k for k in (_slug(str(x)) for x in (src.get("fills") or [])[:4]) if k in keys]
        q["options"] = [o for o in (re.sub(r"\s+", " ", str(x)).strip()[:40] for x in (src.get("options") or [])[:5]) if o]

    def choice(key: str, allowed: tuple[str, ...]) -> str | None:
        value = str(result.get(key) or "").strip().lower()
        return value if value in allowed else None

    # An engagement still missing a name or a description cannot be launched
    # at all, so the interview does not get to call itself finished while one
    # is blank — whatever it thinks about having enough numbers.
    blocked = [f for f in REQUIRED_FIELDS if not filled.get(f)]
    if fact_list:
        # With a list, the list decides: done when nothing on it is still
        # needed. The model saying "enough" is not enough while facts remain —
        # but a model with nothing left worth asking, or the round cap, ends
        # it, and whatever is still open becomes ours to estimate and label.
        settled = {u["key"] for u in updates}
        still = [f["key"] for f in fact_list if f["status"] == "need" and f["key"] not in settled]
        still += [a["key"] for a in added]
        done = not still or not questions or round >= settings.INTERVIEW_MAX_ROUNDS
    else:
        still = []
        done = (bool(result.get("enough")) or not questions
                or round >= settings.INTERVIEW_MAX_ROUNDS)
    if blocked and round < settings.INTERVIEW_MAX_ROUNDS:
        done = False

    return {"questions": [] if done and not blocked else questions, "done": done, "source": "ai",
            "because": str(result.get("because") or "")[:200],
            "inferred": {"engagement_type": choice("engagement_type", ("capability", "full")),
                         "operating_stage": choice("operating_stage", ("operating", "opening"))},
            "still_needed": blocked,
            "updates": updates, "new_facts": added,
            # Open when the interview ends: ours to estimate, labelled as ours.
            "estimate_rest": still if done else []}


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
