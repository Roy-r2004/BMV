"""The one model call the package adds.

It writes the register's words, who owns each row, and each row's share, and
the title and takeaway of each proof section. It does not write an amount.
The shares are checked, the titles are measured, and every other number has
to be a figure this engagement already has. One rejection is sent back with
the reason. After that the stage stops, and nothing is cut to make it fit.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.ai import provider
from app.config import settings
from app.figures import known as figures_known
from app.figures.bind import bind
from app.models import Request
from app.pipeline import decide
from app.pipeline._shared import ask_until_usable, ledger, reply_json
from app.pipeline.failure import StageFailed
from app.storyline.pagelaw import title_lines
from app.storyline.register import RegisterInvalid, assemble
from app.templating import render

logger = logging.getLogger("consultant.storyline")

#: What the progress screen says while this stage runs. The stage's own name
#: is not a word the client is shown.
PROGRESS = "Writing the plan summary..."

_TOKENS = 3500


class _Rejected(Exception):
    def __init__(self, hint: str):
        self.hint = hint
        super().__init__(hint)


def write(db, request_id: int) -> None:
    """Store the storyline, or raise StageFailed("storyline") once the retries
    are spent. A missing request is a no-op."""
    req = db.get(Request, request_id)
    if req is None:
        return None
    known = figures_known.known_for(req)
    builds = decide.builds(_decision(req))
    from app.storyline.exhibits import available

    prompt_base = render(
        "storyline.j2",
        business_name=req.business_name or "",
        figures_block=figures_known.prompt_lines(known),
        phases=_phases(req),
        builds=builds,
        exhibits=available(req),
        sections_max=settings.STORYLINE_SECTIONS_MAX,
    )
    feedback = ""
    saved = None
    cause: str | BaseException = "the plan summary did not come back usable"
    for attempt in range(1, settings.STAGE_REPLY_ATTEMPTS + 1):
        prompt = prompt_base
        if feedback:
            prompt += "\n\nYOUR LAST ATTEMPT WAS REJECTED FOR THESE REASONS — fix exactly these:\n" + feedback
        try:
            raw = ask_until_usable(
                lambda prompt=prompt: provider.chat(
                    settings.REASONING_MODEL, [{"role": "user", "content": prompt}], max_tokens=_TOKENS),
                reply_json,
                ledger(db, request_id, model=settings.REASONING_MODEL, purpose=f"storyline:{attempt}"),
            )
        except Exception as exc:
            logger.warning("plan summary call failed: %s", str(exc)[:200])
            cause = exc
            break
        try:
            saved = _accept(req, raw, known, builds)
            break
        except _Rejected as exc:
            logger.info("plan summary attempt %s rejected: %s", attempt, exc.hint[:200])
            feedback = exc.hint
            cause = exc.hint
            saved = None
    req = db.get(Request, request_id)
    if saved is None:
        req.storyline_json = None
        db.commit()
        raise StageFailed("storyline", cause)
    req.storyline_json = json.dumps({
        "register": saved["register"],
        "sections": saved["sections"],
        "written_at": datetime.now(timezone.utc).isoformat(),
    })
    db.commit()
    return None


def _accept(req, raw: dict, known, builds: bool) -> dict:
    if not isinstance(raw, dict):
        raise _Rejected("The reply was not a JSON object.")
    drafted = raw.get("register")
    try:
        assemble(req, drafted)
    except RegisterInvalid as exc:
        raise _Rejected("\n".join(exc.reasons)) from exc
    return {"register": _register_words(drafted, known),
            "sections": _sections(raw.get("sections"), known, builds, req)}


#: The register's words a row prints. Each is checked for numbers like a title.
_ROW_WORDS = (("recommendation", "recommendation"), ("changes", "what it changes"),
              ("owner", "owner"), ("cost_needs", "cost"))


def _register_words(drafted: list, known) -> list[dict]:
    """The drafted rows with every printed word checked and bound: a number in
    them is a figure this engagement has, written as the figure prints, so no
    token is ever stored. A number nobody owns sends the reply back."""
    kept = []
    for index, row in enumerate(drafted, 1):
        row = dict(row)
        for key, said in _ROW_WORDS:
            text = row.get(key)
            if isinstance(text, str) and text.strip():
                _numbers(text, f"{said} of recommendation {index}", known)
                row[key] = bind(text, known).text
        kept.append(row)
    return kept


def _sections(raw, known, builds: bool, req=None) -> list[dict]:
    if not isinstance(raw, list):
        raise _Rejected("The sections did not come back as a list.")
    kept = []
    for section in raw:
        if not isinstance(section, dict):
            raise _Rejected("A section was not an object.")
        sid = section.get("id")
        if sid == "system" and not builds:
            continue
        title = section.get("title")
        takeaway = section.get("takeaway") if isinstance(section.get("takeaway"), str) else ""
        if not isinstance(sid, str) or not sid.strip() or not isinstance(title, str) or not title.strip():
            raise _Rejected("A section needs an id and a title.")
        _numbers(title, "title", known)
        if takeaway:
            _numbers(takeaway, "takeaway", known)
        title = bind(title, known).text
        if title_lines(title) > 2:
            raise _Rejected(
                "A title has to fit on two lines. This one does not. "
                "Write a shorter title that fits on two lines. Do not cut a word off."
            )
        takeaway = bind(takeaway, known).text if takeaway else ""
        _page_law(req, sid, title, takeaway, len(kept) + 1)
        kept.append({"id": sid, "title": title, "takeaway": takeaway})
    bound = settings.STORYLINE_SECTIONS_MAX
    if len(kept) > bound:
        # nothing is cut to fit: the reply is sent back with the bound
        raise _Rejected(f"The proof has {len(kept)} sections, and it can have at most {bound}. "
                        f"Write at most {bound} sections.")
    return kept


def _page_law(req, sid: str, title: str, takeaway: str, number: int) -> None:
    """The section as its lead page will draw it, through the page law. Its
    foot and stamp are composed in code; a reason the law gives sends the
    reply back."""
    if req is None:
        return
    from app.storyline.build import section
    from app.storyline.exhibits import for_section
    from app.storyline.pagelaw import check_section

    try:
        exhibit = for_section(req, sid)
    except Exception:
        exhibit = None
    reasons = check_section(section(sid, title, takeaway or None, exhibit, number))
    if reasons:
        raise _Rejected("\n".join(reasons))


def _numbers(text: str, where: str, known) -> None:
    unresolved = bind(text, known).unresolved
    if not unresolved:
        return
    shown = ", ".join(item.text for item in unresolved)
    raise _Rejected(
        f"The {where} holds {shown}, and that number is not one of this engagement's figures. "
        "Drop it, or cite a figure from the list as a token."
    )


def _decision(req) -> dict | None:
    raw = getattr(req, "consulting_recommendations_json", None)
    if not isinstance(raw, str) or not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _phases(req) -> list:
    from app.pipeline import action_plan

    plan = action_plan.load(req)
    phases = plan.get("phases") if isinstance(plan, dict) else None
    if not isinstance(phases, list):
        return []
    out = []
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        out.append({
            "when": phase.get("when") if isinstance(phase.get("when"), str) else "",
            "title": phase.get("title") if isinstance(phase.get("title"), str) else "",
        })
    return out
