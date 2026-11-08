"""The sums that decide the question, worked out before anything is diagnosed.

The model reads the figures and says which sums matter: what the client takes
home at their goal, how long the money lasts, what has to be true to break even.
It proposes them as operations over figure ids and writes no result. Code does
the arithmetic through `calc.derive`, so each result is a `derived` figure with
its working (or `ours`, when it rests on a number of ours). They join the known
set, so the diagnosis, the answer and the documents can use them and the number
law accepts them.

The stage adds to a run and never stops one: a reply that cannot be used means
no sums, and a sum that cannot be trusted is left out.
"""
from __future__ import annotations

import json
import logging
from dataclasses import replace
from decimal import Decimal, InvalidOperation

from app.ai import provider
from app.config import settings
from app.figures import calc
from app.figures.known import known_for, prompt_lines
from app.figures.model import Figure, FigureSet, Proposal, Working, as_json, from_json
from app.models import Request
from app.pipeline._shared import ask_until_usable, ledger, reply_json
from app.templating import render

logger = logging.getLogger("consultant.sums")

PROGRESS = "Doing the sums..."
_TOKENS = 1800
_STALE = frozenset({"sums", "answer", "registry", "roadmap", "register", "exhibits"})
_PERIODS = (None, "day", "week", "month", "year")
#: The only numbers a sum may bring in that are not figures: the calendar.
_CALENDAR = {Decimal(7), Decimal(12), Decimal(30), Decimal(52), Decimal(365)}
_AS_A_SHARE = "as a share"
_PERCENT_UNITS = {"percent", "%"}


def _is_percent(f: Figure) -> bool:
    return calc.unit_key(f.unit) in _PERCENT_UNITS


def _constants(raw: object) -> list[tuple[Decimal, str]]:
    out = []
    for c in raw if isinstance(raw, list) else []:
        value = Decimal(str(c["value"]))
        if value not in _CALENDAR:
            raise ValueError(f"{value} is not a calendar constant")
        out.append((value, str(c.get("label") or "").strip()[:30]))
    return out


def _one(raw: dict, new_id: str, held: dict[str, Figure]) -> Figure:
    op = raw["op"]
    names = raw["inputs"]
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ValueError("inputs must be figure ids")
    inputs = [held[n] for n in names]
    period = raw.get("period") or None
    if period not in _PERIODS:
        raise ValueError(f"unknown period {period!r}")
    unit = str(raw.get("unit") or "").strip()[:20]
    factors = _constants(raw.get("constants"))
    shares = [(Decimal("0.01"), _AS_A_SHARE) for f in inputs if _is_percent(f)] if op == "product" else []
    made = calc.derive(op, inputs, id=new_id, unit=unit, period=period, factors=[*factors, *shares],
                       precision=1 if op == "ratio" else None)
    label = " ".join(str(raw.get("label") or "").split())[:80]
    tail = f" × 0.01 {_AS_A_SHARE}"

    def tell(text: str) -> str:
        text = text.replace(tail, "")
        return f"{label}: {text}" if label else text

    if isinstance(made.source, Working):
        return replace(made, source=replace(made.source, text=tell(made.source.text)))
    return replace(made, source=Proposal(note=tell(made.source.note)))


def compute(proposed: object, known: FigureSet) -> list[Figure]:
    """Each usable sum as a figure, numbered in order. A sum that names a figure
    nobody has, brings in a number of its own or does not add up is left out, and
    so is anything that leaned on it."""
    held = {f.id: f for f in known}
    out: list[Figure] = []
    for index, raw in enumerate(proposed if isinstance(proposed, list) else [], 1):
        if len(out) >= settings.SUMS_MAX:
            break
        new_id = f"SUM-{index}"
        try:
            figure = _one(raw, new_id, held)
        except (KeyError, TypeError, ValueError, InvalidOperation, AttributeError) as exc:
            logger.info("sum %s left out: %s", new_id, exc)
            continue
        held[new_id] = figure
        out.append(figure)
    return out


def as_claims(req) -> list[dict]:
    """The worked-out sums as claims a hypothesis can cite, like the capacity totals.
    A sum resting on a number of ours is an estimate, so it is not evidence."""
    try:
        stored = json.loads(req.sums_json) if getattr(req, "sums_json", None) else []
    except (TypeError, ValueError):
        return []
    out = []
    for item in stored:
        figure = from_json(item)
        if figure.kind == "derived":
            out.append({"id": figure.id, "value": float(figure.value), "unit": figure.unit,
                        "time_basis": figure.period or "as stated", "text": figure.source.text,
                        "source": "computed from their figures", "provenance": "machine_computed"})
    return out


def write(db, request_id: int) -> None:
    """Store the sums for this run, or none. Never raises for a reply it cannot use."""
    req = db.get(Request, request_id)
    if req is None:
        return
    req.sums_json = None
    known = known_for(req, leave_out=_STALE)
    if len(list(known)) >= 2:
        prompt = render("sums.j2", question=req.desired_outcome or "", main_problem=req.main_problem or "",
                        stage="not launched yet, this is a plan" if req.operating_stage == "opening" else "already operating",
                        figures_block=prompt_lines(known), most=settings.SUMS_MAX)
        figures: list[Figure] = []
        # code does the arithmetic and the model only proposes it, so a second
        # model is as good as the first, and no sums would weaken the whole answer
        for model in (settings.REASONING_MODEL, settings.ANALYSIS_MODEL):
            try:
                reply = ask_until_usable(
                    lambda: provider.chat(model, [{"role": "user", "content": prompt}], max_tokens=_TOKENS),
                    reply_json, ledger(db, request_id, model=model, purpose="sums"))
                figures = compute(reply.get("sums"), known)
                break
            except Exception as exc:
                logger.warning("the sums could not be worked out with %s: %s", model, str(exc)[:200])
        req.sums_json = json.dumps([as_json(f) for f in figures]) if figures else None
    db.commit()
