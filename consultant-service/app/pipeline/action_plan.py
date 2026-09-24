"""The plan the owner acts on next Monday — with or without the software.

When the answer is "this is not a software problem" the old pipeline could
only say so and stop, and the client left with a paragraph. When the answer
WAS software, the first thing they could do still waited ten weeks on a
build. Either way the most useful document — what to do this week, how to
tell whether it worked, and what to decide at the end — did not exist.

This writes it: first steps, a schedule, the message to send (when the change
has to be told to someone), the measures to track with their baselines, and
the rule that decides at the end. The measures are what the pilot tracker on
the package page records against, week by week.

Every number is checked the way the answer's are (`answer.allowed_numbers`):
money and percentages strictly, other figures above twelve strictly too —
twelve and under are left to the prose, where "in two weeks" lives. A
baseline has to be one of their figures by id or it is dropped to "measure in
week 1": a pilot measured against an invented starting point proves nothing.
"""

import json
import logging
import re

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.database import SessionLocal
from app.models import Request
from app.pipeline import answer as _answer
from app.pipeline import capacity as _capacity
from app.pipeline import figures
from app.pipeline._shared import build_engagement_register, extract_json_from_text, log_usage
from app.templating import render

logger = logging.getLogger("consultant.action_plan")

PLAN_TOKENS = 5000
LENIENT_BELOW = 13
WRITING, READY, FAILED = "writing", "ready", "failed"


def _text(v, limit: int) -> str:
    # The prompt names measures m1, m2... and the model echoes the ids into
    # prose ("Booking Admin Time (m1)"). They mean nothing to the owner.
    return re.sub(r"\s*\((?:m\d+(?:,\s*)?)+\)", "", str(v or "")).strip()[:limit]


def shape(raw: dict, claims: list[dict], allowed: set[float], weeks: int,
          hours: set[int] | None = None) -> tuple[dict | None, list[str]]:
    """(plan, problems). Pure. `hours` are the clock times they named."""
    if not isinstance(raw, dict):
        return None, ["the response was not an object"]
    allowed = set(allowed) | {float(weeks)}
    problems: list[str] = []

    def ok(text: str, what: str) -> bool:
        bad = figures.unsupported(text, allowed, lenient_below=LENIENT_BELOW, hours=hours)
        if bad:
            problems.append(f"{what} uses numbers they never gave: "
                            + ", ".join(f"{b:g}" for b in bad))
            return False
        return True

    title = _text(raw.get("title"), 60)
    if not title or not ok(title, "the title"):
        title = "Your first-weeks plan"
    summary = _text(raw.get("summary"), 400)
    if summary and not ok(summary, "the summary"):
        summary = ""
    try:
        weeks = max(2, min(12, int(raw.get("weeks") or weeks)))
    except (TypeError, ValueError):
        pass

    monday = []
    for i, s in enumerate(list(raw.get("monday") or [])[:5]):
        if not isinstance(s, dict):
            continue
        do, why = _text(s.get("do"), 240), _text(s.get("why"), 240)
        if do and ok(f"{do} {why}", f"Monday step {i + 1}"):
            monday.append({"do": do, "why": why})

    schedule = []
    for i, s in enumerate(list(raw.get("schedule") or [])[:8]):
        if not isinstance(s, dict):
            continue
        when, do = _text(s.get("when"), 40), _text(s.get("do"), 300)
        if when and do and ok(do, f"schedule row {i + 1}"):
            schedule.append({"when": when, "do": do})

    message = None
    m = raw.get("message")
    if isinstance(m, dict) and _text(m.get("text"), 1200):
        text = _text(m.get("text"), 1200)
        if ok(text, "the message"):
            message = {"to": _text(m.get("to"), 80) or "your customers", "text": text}

    by_id = {c["id"]: c for c in claims if c.get("id")}
    measures = []
    for i, x in enumerate(list(raw.get("measures") or [])[:5]):
        if not isinstance(x, dict) or not _text(x.get("name"), 60):
            continue
        baseline, source = None, None
        frm = _text(x.get("baseline_from"), 12)
        if frm in by_id and x.get("baseline") is not None:
            try:
                b = float(x.get("baseline"))
            except (TypeError, ValueError):
                b = None
            if b is not None and _answer._claim_matches(b, by_id[frm]):
                baseline, source = b, frm
        watch = _text(x.get("watch"), 8).lower()
        measures.append({
            "id": f"m{len(measures) + 1}",
            "name": _text(x.get("name"), 60),
            "unit": _text(x.get("unit"), 40),
            "watch": watch if watch in ("up", "down", "hold") else "up",
            "baseline": baseline, "baseline_from": source,
        })

    decision_rule = _text(raw.get("decision_rule"), 400)
    if decision_rule and not ok(decision_rule, "the decision rule"):
        decision_rule = ""
    assumptions = [a for a in (_text(x, 240) for x in (raw.get("assumptions") or [])[:5])
                   if a and ok(a, "an assumption")]
    if_it_fails = _text(raw.get("if_it_fails"), 400)
    if if_it_fails and not ok(if_it_fails, "the fallback"):
        if_it_fails = ""

    if len(monday) < 2:
        problems.append("fewer than two usable Monday steps")
        return None, problems
    return {
        "status": READY, "title": title, "summary": summary, "weeks": weeks,
        "monday": monday, "schedule": schedule, "message": message, "measures": measures,
        "decision_rule": decision_rule, "assumptions": assumptions, "if_it_fails": if_it_fails,
    }, problems


def _save(db: Session, request_id: int, plan: dict) -> None:
    req = db.get(Request, request_id)
    if req is not None:
        req.action_plan_json = json.dumps(plan)
        db.commit()


def write(db: Session, request_id: int, building: bool = False) -> dict | None:
    """Write, verify and persist the plan. Never raises."""
    from app.pipeline import diagnose

    req = db.get(Request, request_id)
    if req is None:
        return None
    _save(db, request_id, {"status": WRITING})
    try:
        decision = json.loads(req.consulting_recommendations_json) if req.consulting_recommendations_json else {}
        ans = _answer.load(req) or {}
        _, claims = diagnose._evidence_lines(req)
        texts = _capacity.owner_texts(req)
        move = ans.get("move")
        allowed = _answer.allowed_numbers(texts, claims, move)
        weeks = int((ans.get("action") or {}).get("weeks") or 6)
        base = dict(
            engagement_register=build_engagement_register(
                req.engagement_type, req.needs_ai, req.main_problem, req.desired_outcome,
                req.business_description),
            business_name=req.business_name or "",
            headline=f"{ans.get('headline', '')} {ans.get('turn', '')}".strip() or decision.get("central_problem", ""),
            sub=ans.get("sub") or "",
            kind=decision.get("intervention_kind") or "unspecified",
            central_problem=decision.get("central_problem") or "",
            summary=decision.get("consulting_summary") or req.consulting_analysis or "",
            move=(f"{move['display']} — {move['label']} ({move['working']})" if move else ""),
            unverified="; ".join(decision.get("unverified") or []) or "nothing listed",
            claims=_answer._claim_lines(claims),
            weeks=weeks,
            building=building,
        )
    except Exception as exc:
        logger.warning("plan could not be prepared: %s", str(exc)[:200])
        _save(db, request_id, {"status": FAILED})
        return None

    feedback, plan = "", None
    for attempt in (1, 2):
        try:
            prompt = render("action_plan.j2", **base)
            if feedback:
                prompt += ("\n\nYOUR LAST ATTEMPT WAS REJECTED FOR THESE REASONS — fix exactly these:\n"
                           + feedback)
            body = provider.chat(settings.REASONING_MODEL, [{"role": "user", "content": prompt}],
                                 max_tokens=PLAN_TOKENS)
            raw = extract_json_from_text(body["choices"][0]["message"]["content"])
            log_usage(db, request_id, provider="openrouter", model=settings.REASONING_MODEL,
                      purpose=f"action_plan:{attempt}", usage=body.get("usage"), success=True)
        except Exception as exc:
            log_usage(db, request_id, provider="openrouter", model=settings.REASONING_MODEL,
                      purpose=f"action_plan:{attempt}", success=False, error=str(exc)[:500])
            logger.warning("plan call failed: %s", str(exc)[:200])
            break
        candidate, problems = shape(raw, claims, allowed, weeks, figures.given_hours(texts))
        if candidate:
            plan = candidate
        if not problems:
            break
        logger.info("plan attempt %d rejected in part: %s", attempt, "; ".join(problems)[:400])
        feedback = "\n".join(f"- {p}" for p in problems)

    _save(db, request_id, plan or {"status": FAILED})
    return plan


def write_in_background(request_id: int, building: bool = False) -> None:
    """Thread entry: its own session, like every other pipeline thread."""
    db = SessionLocal()
    try:
        write(db, request_id, building=building)
    except Exception:
        logger.exception("plan thread failed")
        try:
            _save(db, request_id, {"status": FAILED})
        except Exception:
            pass
    finally:
        db.close()


def ensure(db: Session, request_id: int, building: bool = False) -> dict | None:
    """The plan, writing it if it is not already there. For the build half,
    whose package opens with it."""
    req = db.get(Request, request_id)
    current = load(req) if req is not None else None
    if current and current.get("status") == READY:
        return current
    return write(db, request_id, building=building)


def load(req) -> dict | None:
    try:
        return json.loads(req.action_plan_json) if getattr(req, "action_plan_json", None) else None
    except (TypeError, ValueError):
        return None


def load_log(req) -> list[dict]:
    try:
        log = json.loads(req.pilot_log_json) if getattr(req, "pilot_log_json", None) else []
        return [e for e in log if isinstance(e, dict)] if isinstance(log, list) else []
    except (TypeError, ValueError):
        return []


def record(plan: dict, log: list[dict], week: int, values: dict, note: str) -> list[dict]:
    """Upsert one week's readings. Pure. Only the plan's own measures, only
    numbers — the tracker is theirs, but it may not grow fields the plan does
    not define."""
    ids = {m["id"] for m in (plan or {}).get("measures") or []}
    clean = {}
    for k, v in (values or {}).items():
        if k not in ids or v in (None, ""):
            continue
        try:
            clean[k] = float(v)
        except (TypeError, ValueError):
            continue
    entry = {"week": week, "values": clean, "note": str(note or "").strip()[:400]}
    out = [e for e in log if e.get("week") != week] + [entry]
    return sorted(out, key=lambda e: e.get("week") or 0)
