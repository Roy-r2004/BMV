"""The implementation roadmap: how it gets done, and who does it.

It replaces the Monday plan. That document handed the owner a list of tasks,
a schedule and a weekly tracking sheet — work, after an engagement whose
whole promise is that we do the work. Nobody kept the tracker. A serious firm
closes an engagement differently: here is the order it gets done in, here is
what we do in each phase, and here are the few calls only you can make.

So the roadmap is phases, each carried out by us ("together" only when it
genuinely needs the owner in the room), and decisions — go ahead, when to go
live, who we deal with, and any business choice the answer rests on — each
with answers they can tap. No tasks, no tracking.

Every number is checked the way the answer's are (`answer.allowed_numbers`):
money and percentages strictly, other figures above twelve strictly too —
twelve and under are left to the prose, where "weeks 1 to 2" lives.
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

logger = logging.getLogger("consultant.roadmap")

PLAN_TOKENS = 4000
LENIENT_BELOW = 13
WRITING, READY, FAILED = "writing", "ready", "failed"


def _text(v, limit: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:limit]


def shape(raw: dict, allowed: set[float], hours: set[int] | None = None) -> tuple[dict | None, list[str]]:
    """(roadmap, problems). Pure. `hours` are the clock times they named."""
    if not isinstance(raw, dict):
        return None, ["the response was not an object"]
    problems: list[str] = []

    def ok(text: str, what: str) -> bool:
        bad = figures.unsupported(text, allowed, lenient_below=LENIENT_BELOW, hours=hours)
        if bad:
            problems.append(f"{what} uses numbers they never gave: " + ", ".join(f"{b:g}" for b in bad))
            return False
        return True

    summary = _text(raw.get("summary"), 400)
    if summary and not ok(summary, "the summary"):
        summary = ""

    phases = []
    for i, p in enumerate(list(raw.get("phases") or [])[:6]):
        if not isinstance(p, dict):
            continue
        when, title, do = _text(p.get("when"), 40), _text(p.get("title"), 60), _text(p.get("do"), 320)
        you = _text(p.get("you"), 60)
        by = _text(p.get("by"), 10).lower()
        if when and title and do and ok(f"{title} {do} {you}", f"phase {i + 1}"):
            phases.append({"when": when, "title": title, "do": do,
                           "by": "together" if by == "together" else "us", "you": you})

    decisions = []
    for i, d in enumerate(list(raw.get("decisions") or [])[:4]):
        if not isinstance(d, dict):
            continue
        question = _text(d.get("question"), 90)
        detail = _text(d.get("detail"), 160)
        options = [o for o in (_text(x, 36) for x in (d.get("options") or [])[:4]) if o]
        if not question or len(options) < 2 or not ok(f"{question} {detail} {' '.join(options)}", f"decision {i + 1}"):
            continue
        decisions.append({"id": f"d{len(decisions) + 1}", "question": question,
                          "detail": detail, "options": options})

    assumptions = [a for a in (_text(x, 240) for x in (raw.get("assumptions") or [])[:5])
                   if a and ok(a, "an assumption")]

    if len(phases) < 2:
        problems.append("fewer than two usable phases")
        return None, problems
    if not decisions:
        problems.append("no usable decisions")
        return None, problems
    return {"status": READY, "title": "Implementation roadmap", "summary": summary,
            "phases": phases, "decisions": decisions, "assumptions": assumptions}, problems


def _modules(req) -> str:
    try:
        mods = json.loads(req.modules_json) if getattr(req, "modules_json", None) else []
    except (TypeError, ValueError):
        return ""
    mods = [m for m in mods if isinstance(m, dict)]
    mods.sort(key=lambda m: 0 if m.get("pilot") else 1)
    lines = []
    for m in mods[:10]:
        name = m.get("client_facing_name") or m.get("name")
        if name:
            lines.append(f"- {name}: {str(m.get('purpose') or '')[:160]}")
    return "\n".join(lines)


def _save(db: Session, request_id: int, plan: dict) -> None:
    req = db.get(Request, request_id)
    if req is not None:
        req.action_plan_json = json.dumps(plan)
        db.commit()


def write(db: Session, request_id: int) -> dict | None:
    """Write, verify and persist the roadmap. Never raises."""
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
            modules=_modules(req),
            timeline=req.timeline or "",
            claims=_answer._claim_lines(claims),
        )
    except Exception as exc:
        logger.warning("roadmap could not be prepared: %s", str(exc)[:200])
        _save(db, request_id, {"status": FAILED})
        return None

    feedback, plan = "", None
    for attempt in (1, 2):
        try:
            prompt = render("roadmap.j2", **base)
            if feedback:
                prompt += ("\n\nYOUR LAST ATTEMPT WAS REJECTED FOR THESE REASONS — fix exactly these:\n"
                           + feedback)
            body = provider.chat(settings.REASONING_MODEL, [{"role": "user", "content": prompt}],
                                 max_tokens=PLAN_TOKENS)
            raw = extract_json_from_text(body["choices"][0]["message"]["content"])
            log_usage(db, request_id, provider="openrouter", model=settings.REASONING_MODEL,
                      purpose=f"roadmap:{attempt}", usage=body.get("usage"), success=True)
        except Exception as exc:
            log_usage(db, request_id, provider="openrouter", model=settings.REASONING_MODEL,
                      purpose=f"roadmap:{attempt}", success=False, error=str(exc)[:500])
            logger.warning("roadmap call failed: %s", str(exc)[:200])
            break
        candidate, problems = shape(raw, allowed, figures.given_hours(texts))
        if candidate:
            plan = candidate
        if not problems:
            break
        logger.info("roadmap attempt %d rejected in part: %s", attempt, "; ".join(problems)[:400])
        feedback = "\n".join(f"- {p}" for p in problems)

    _save(db, request_id, plan or {"status": FAILED})
    return plan


def write_in_background(request_id: int) -> None:
    """Thread entry: its own session, like every other pipeline thread."""
    db = SessionLocal()
    try:
        write(db, request_id)
    except Exception:
        logger.exception("roadmap thread failed")
        try:
            _save(db, request_id, {"status": FAILED})
        except Exception:
            pass
    finally:
        db.close()


def load(req) -> dict | None:
    try:
        return json.loads(req.action_plan_json) if getattr(req, "action_plan_json", None) else None
    except (TypeError, ValueError):
        return None


def load_decisions(req) -> dict:
    """What the owner chose on the roadmap's decisions, by decision id."""
    try:
        raw = json.loads(req.decisions_json) if getattr(req, "decisions_json", None) else {}
    except (TypeError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def record_choices(plan: dict | None, current: dict, choices: dict) -> dict:
    """Merge their choices. Pure. Only the roadmap's own decisions, and only
    one of the options each offers — the page cannot grow answers the
    roadmap never asked for."""
    offered = {d["id"]: d.get("options") or [] for d in (plan or {}).get("decisions") or []}
    picked = dict(current.get("choices") or {}) if isinstance(current.get("choices"), dict) else {}
    for k, v in (choices or {}).items():
        if k in offered and v in offered[k]:
            picked[k] = v
    return {**current, "choices": picked}
