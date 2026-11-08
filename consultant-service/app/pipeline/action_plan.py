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

Every number in the prose is bound the way the answer's is: against what the
request knows (`app.figures.known`), with no leniency, so "twelve" and "3" need
a figure as much as "$35" does. What goes is the sentence, not the phase: each
sentence of the prose (what we do, the summary, a detail, an assumption, each
option) holding a number that names no figure is removed and named for the retry.
A phase goes only when its title or its "when" names nothing or nothing of what we
do is left; a decision only when its question names nothing or fewer than two
options are left. A number the roadmap labels "(proposed)" or "(our proposal)" is
ours (PLAN-PROP-n, bounded by `settings.PLAN_PROPOSED_FIGURES_MAX`) and stays.

The lengths the roadmap proposes are ours, and it says so: each phase whose
"when" is a span of weeks ("Weeks 3 to 6") has its length as a figure
(PLAN-PHASE-n-WEEKS), the plan has its length (PLAN-WEEKS, the one the answer
proposed, or else the end of the last phase) and its number of phases
(PLAN-PHASES). They are stored in the roadmap's `figures` (`model.as_json`), and
prose that says "four weeks" or "three phases" binds to them. A "when" that is a
span of weeks and nothing else is the roadmap's structure: it is held to the plan
(a phase may not run past the plan's last week) and not bound. Any other "when"
("Month 3 on", "When revenue hits $10k") is bound like the prose, so a quantity in
it must name a figure.
"""

import json
import logging
import re
from decimal import Decimal

from sqlalchemy.orm import Session

from app import mailer
from app.ai import provider
from app.config import settings
from app.database import SessionLocal
from app.figures import known as _known
from app.figures.bind import bind, clean_sentences
from app.figures.model import Figure, FigureSet, Proposal, as_json
from app.models import Request
from app.pipeline import answer as _answer
from app.pipeline import decide as _decide
from app.pipeline._shared import ask_until_usable, build_engagement_register, ledger, reply_json
from app.pipeline.failure import StageFailed
from app.templating import render

logger = logging.getLogger("consultant.roadmap")

PLAN_TOKENS = 4000
WRITING, READY, FAILED = "writing", "ready", "failed"


def _text(v, limit: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:limit]


# "Weeks 3 to 6", "Week 2", "weeks 1-2", "Week 1 and 2": a span of weeks, first to last,
# and nothing else in the field
_WEEK_SPAN = re.compile(
    r"^\s*weeks?\s+(\d{1,3})(?:\s*(?:-|\u2013|\u2014|to|through|and)\s*(\d{1,3}))?\s*$", re.I)


def week_span(when: str) -> tuple[int, int] | None:
    """The first and last week a phase's "when" names, or None when it is not a
    span of weeks ("Month 3 on")."""
    m = _WEEK_SPAN.match(str(when or ""))
    if not m:
        return None
    first, last = int(m.group(1)), int(m.group(2) or m.group(1))
    return (first, last) if 1 <= first <= last else None


def _ours(fid: str, value: int, unit: str, note: str) -> Figure:
    return Figure(fid, Decimal(value), unit, None, "ours", Proposal(note=note), 0)


# "$26 (proposed)", "4 weeks (our proposal)": a number the roadmap labels as ours
_PROPOSED_LABEL = re.compile(r"(?:[ \t]+[A-Za-z]+){0,2}?[ \t]*\((?:proposed|our proposal)\)", re.I)
_NOT_PROPOSED_FORMS = frozenset({"time", "date"})


def _plan_texts(raw: dict) -> list[str]:
    """Every piece of text the roadmap wrote, in order."""
    texts = [raw.get("summary")]
    for p in raw.get("phases") or []:
        if isinstance(p, dict):
            texts += [p.get("when"), p.get("title"), p.get("do"), p.get("you")]
    for d in raw.get("decisions") or []:
        if isinstance(d, dict):
            texts += [d.get("question"), d.get("detail"), *(d.get("options") or [])]
    texts += list(raw.get("assumptions") or [])
    return [t for t in (_text(x, 400) for x in texts) if t]


def proposed_figures(raw: dict) -> list[Figure]:
    """The numbers the roadmap labels as our proposal, as ours figures (PLAN-PROP-n),
    each in the unit it was written in (a currency, a percent, a time word, the noun
    it counts). The label stays in the printed text; a number without it is held to
    the known set like any other. At most `settings.PLAN_PROPOSED_FIGURES_MAX`; the
    same number in the same unit is one figure."""
    from app.figures.casefile import unit_of
    from app.figures.read import mentions

    out: list[Figure] = []
    seen: set = set()
    for text in _plan_texts(raw):
        for m in mentions(text):
            if m.form in _NOT_PROPOSED_FORMS or not _PROPOSED_LABEL.match(text, m.end):
                continue
            unit = unit_of(m, text)
            if (m.value, unit) in seen:
                continue
            if len(out) >= settings.PLAN_PROPOSED_FIGURES_MAX:
                return out
            try:
                out.append(Figure(f"PLAN-PROP-{len(out) + 1}", m.value, unit, None, "ours",
                                  Proposal(note="proposed in the roadmap"),
                                  max(0, -m.value.normalize().as_tuple().exponent)))
            except (TypeError, ValueError):
                continue
            seen.add((m.value, unit))
    return out


def shape(raw: dict, known: FigureSet, hours: set[int] | None = None,
          plan_weeks: Figure | None = None) -> tuple[dict | None, list[str]]:
    """(roadmap, problems). Pure. `known` is what the request knows
    (`known.known_for`), `hours` the clock times they named, `plan_weeks` the
    length of the plan the answer proposed (PLAN-WEEKS), when there is one."""
    if not isinstance(raw, dict):
        return None, ["the response was not an object"]
    problems: list[str] = []

    def checked(text: str, what: str, against: FigureSet) -> str | None:
        """A short field (a title, a question) bound to the figures, or None when a
        number in it names none: it has no sentence to spare."""
        r = bind(text, against, hours=hours)
        if r.unresolved:
            problems.append(f"{what} uses numbers they never gave: " + ", ".join(u.text for u in r.unresolved))
            return None
        return r.text

    def cleaned(text: str, what: str, against: FigureSet) -> str:
        """Prose bound to the figures, with each sentence that holds a number naming
        none removed (and named in the problems, for the retry); "" when none is left."""
        if not text:
            return ""
        kept, removed = clean_sentences(text, against, hours=hours)
        problems.extend(f"{what}: removed \"{s}\", whose numbers they never gave" for s in removed)
        return kept.strip()

    # A number the roadmap itself labels as ours ("$26 (proposed)") is a figure of ours.
    proposed = proposed_figures(raw)
    known = _known.with_extra(known, proposed)
    base = [plan_weeks] if plan_weeks is not None else []
    # No phase runs past the plan: its length when the answer proposed one, else the longest plan we make.
    last_week = int(plan_weeks.value) if plan_weeks is not None else settings.PLAN_WEEKS_MAX
    phases, spans, figures = [], [], []
    for i, p in enumerate(list(raw.get("phases") or [])[:6]):
        if not isinstance(p, dict):
            continue
        when, title, do = _text(p.get("when"), 40), _text(p.get("title"), 60), _text(p.get("do"), 320)
        you = _text(p.get("you"), 60)
        by = _text(p.get("by"), 10).lower()
        if not (when and title and do):
            continue
        span = week_span(when)
        if span and span[1] > last_week:
            # a span past the plan would register a length nobody proposed, and vouch for prose with it
            problems.append(f"phase {i + 1} runs to week {span[1]}, past the {last_week}-week plan")
            continue
        own = ([_ours(_known.phase_weeks_id(len(phases) + 1), span[1] - span[0] + 1, "week",
                      f"how long phase {len(phases) + 1} takes")] if span else [])
        against = _known.with_extra(known, base + own)
        # A span of weeks is the field's whole text and was held to the plan above; any
        # other "when" is bound, so a quantity in it ("When revenue hits $10k") must name a figure.
        # The title and the when have no sentence to spare: a number naming nothing drops the phase.
        what = f"phase {i + 1}"
        head = [when if span else checked(when, what, against), checked(title, what, against)]
        if any(h is None for h in head):
            continue
        # What we do is prose: a sentence holding an operational number nobody owns ("within
        # 15 minutes") goes, and the phase stays while any of it is left.
        done = cleaned(do, what, against)
        if not done:
            problems.append(f"{what} had nothing left to say once its unowned numbers were removed")
            continue
        phases.append({"when": head[0], "title": head[1], "do": done,
                       "by": "together" if by == "together" else "us", "you": cleaned(you, what, against)})
        spans.append(span)
        figures += own

    if plan_weeks is None and phases and all(spans):
        plan_weeks = _ours(_known.PLAN_WEEKS_ID, max(s[1] for s in spans), "week",
                           "the length of the plan we propose")
    figures = ([plan_weeks] if plan_weeks is not None else []) + figures + proposed
    if phases:
        figures.append(_ours(_known.PLAN_PHASES_ID, len(phases), "phases", "the phases we propose"))
    against = _known.with_extra(known, figures)

    summary = cleaned(_text(raw.get("summary"), 400), "the summary", against)

    decisions = []
    for i, d in enumerate(list(raw.get("decisions") or [])[:4]):
        if not isinstance(d, dict):
            continue
        what = f"decision {i + 1}"
        question = _text(d.get("question"), 90)
        options = [o for o in (_text(x, 36) for x in (d.get("options") or [])[:4]) if o]
        if not question or len(options) < 2:
            continue
        question = checked(question, what, against)
        # each option is a sentence of its own: one naming a price nobody owns goes,
        # the others keep their words; a decision needs its question and two options
        options = [o for o in (cleaned(x, what, against) for x in options) if o]
        if question is None or len(options) < 2:
            continue
        decisions.append({"id": f"d{len(decisions) + 1}", "question": question,
                          "detail": cleaned(_text(d.get("detail"), 160), what, against), "options": options})

    assumptions = [b for b in (cleaned(a, "an assumption", against)
                               for a in (_text(x, 240) for x in (raw.get("assumptions") or [])[:5]) if a) if b]

    if len(phases) < 2:
        problems.append("fewer than two usable phases")
        return None, problems
    if not decisions:
        problems.append("no usable decisions")
        return None, problems
    return {"status": READY, "title": "Implementation roadmap", "summary": summary,
            "phases": phases, "decisions": decisions, "assumptions": assumptions,
            "figures": [as_json(f) for f in figures]}, problems


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
    """Write, verify and persist the roadmap.

    When it cannot be written (the inputs cannot be read, the model call fails,
    or no attempt gives a roadmap that checks out) the failed state is saved
    first, so the page shows a roadmap that failed and offers the retry, and
    then `StageFailed("roadmap")` is raised. Inside a run that stops the run;
    a caller outside one (`write_in_background`) has to tell the team itself.
    Returns None only when the request does not exist."""
    from app.pipeline import diagnose

    req = db.get(Request, request_id)
    if req is None:
        return None
    _save(db, request_id, {"status": WRITING})
    try:
        decision = json.loads(req.consulting_recommendations_json) if req.consulting_recommendations_json else {}
        ans = _answer.load(req) or {}
        _, claims = diagnose._evidence_lines(req)
        move = ans.get("move")
        known = _known.known_for(req, leave_out={"roadmap"})
        hours = _known.hours_for(req)
        plan_weeks = next((f for f in _known.answer_figures(ans) if f.id == _known.PLAN_WEEKS_ID), None)
        base = dict(
            engagement_register=build_engagement_register(
                req.engagement_type, req.needs_ai, req.main_problem, req.desired_outcome,
                req.business_description),
            business_name=req.business_name or "",
            headline=f"{ans.get('headline', '')} {ans.get('turn', '')}".strip() or decision.get("central_problem", ""),
            sub=ans.get("sub") or "",
            kind=decision.get("intervention_kind") or "unspecified",
            not_to_build=not _decide.builds(decision),
            central_problem=decision.get("central_problem") or "",
            summary=decision.get("consulting_summary") or req.consulting_analysis or "",
            move=(f"{move['display']} — {move['label']} ({move['working']})" if move else ""),
            unverified="; ".join(decision.get("unverified") or []) or "nothing listed",
            modules=_modules(req),
            timeline=req.timeline or "",
            claims=_answer._claim_lines(claims),
            figures_block=_known.prompt_lines(known),
            # no phase runs past the plan: its length when the answer proposed one, else the longest plan we make
            plan_proposed=plan_weeks is not None,
            plan_ceiling=int(plan_weeks.value) if plan_weeks is not None else settings.PLAN_WEEKS_MAX,
        )
    except Exception as exc:
        logger.warning("roadmap could not be prepared: %s", str(exc)[:200])
        _save(db, request_id, {"status": FAILED})
        raise StageFailed("roadmap", exc) from exc

    feedback, plan = "", None
    cause: str | BaseException = "no roadmap came back usable"
    for attempt in (1, 2):
        try:
            prompt = render("roadmap.j2", **base)
            if feedback:
                prompt += ("\n\nYOUR LAST ATTEMPT WAS REJECTED FOR THESE REASONS — fix exactly these:\n"
                           + feedback)
            # A reply that is not JSON is asked for again here; this loop's
            # second attempt is for a reply that read but was wrong.
            raw = ask_until_usable(
                lambda: provider.chat(settings.REASONING_MODEL, [{"role": "user", "content": prompt}],
                                      max_tokens=PLAN_TOKENS),
                reply_json,
                ledger(db, request_id, model=settings.REASONING_MODEL, purpose=f"roadmap:{attempt}"),
            )
        except Exception as exc:
            logger.warning("roadmap call failed: %s", str(exc)[:200])
            cause = exc
            break
        candidate, problems = shape(raw, known, hours, plan_weeks)
        if candidate:
            plan = candidate
        if not problems:
            break
        logger.info("roadmap attempt %d rejected in part: %s", attempt, "; ".join(problems)[:400])
        feedback = "\n".join(f"- {p}" for p in problems)
        cause = "no usable roadmap: " + "; ".join(problems)

    _save(db, request_id, plan or {"status": FAILED})
    if plan is None:
        raise StageFailed("roadmap", cause)
    return plan


def _tell_the_team_it_failed(db: Session, request_id: int, cause: str) -> None:
    """For a roadmap written outside a run, where nothing else would: the
    orchestrator tells the team about the ones inside. Never raises."""
    try:
        db.rollback()  # whatever raised may have left the session unusable
        req = db.get(Request, request_id)
        ref = (req.public_id if req is not None else None) or request_id
        mailer.notify_team_failure(ref, (req.business_name if req is not None else "") or "", "roadmap", cause)
    except Exception:
        logger.exception("could not tell the team the roadmap failed")


def write_in_background(request_id: int) -> None:
    """Thread entry: its own session, like every other pipeline thread. Not the
    orchestrator, so a roadmap that fails here is reported here: the saved
    failed state is what the owner sees (and can retry from), and the team is
    told. Nothing in it may raise out of the thread."""
    db = SessionLocal()
    try:
        write(db, request_id)
    except StageFailed as exc:
        _tell_the_team_it_failed(db, request_id, exc.cause)  # write() has saved the failed state
    except Exception as exc:
        logger.exception("roadmap thread failed")
        try:
            _save(db, request_id, {"status": FAILED})
        except Exception:
            pass
        _tell_the_team_it_failed(db, request_id, str(exc) or type(exc).__name__)
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
