"""The answer page, from columns the run already stored.

Nothing is asked of a model. A column that is missing, blank or unreadable
leaves that part off the page. The register and the proof titles are filled
in later; this module names the page and whether a system file belongs.
"""
from __future__ import annotations

import json

from app.figures import known as figures_known
from app.figures.model import display, tag_word
from app.pipeline.decide import builds as decision_builds
from app.storyline.model import AnswerPage, Number, RestsOn, Storyline

_ANSWER_LINES = ("headline", "turn")
_MAX_NUMBERS = 3
_MAX_FIGURES = 2
_MAX_WOULD_NOT = 3


def build(req) -> Storyline | None:
    """The storyline, or None when the run has no answer to open with."""
    if not isinstance(_loads(getattr(req, "answer_json", None)), dict):
        return None
    known = figures_known.known_for(req)
    return Storyline(answer_page(req, known), _register(req, known), _sections(req, known), _builds(req))


def answer_page(req, known=None) -> AnswerPage:
    """The opening page. Each part is taken from the column that holds it."""
    answer = _loads(getattr(req, "answer_json", None))
    answer = answer if isinstance(answer, dict) else {}
    known = figures_known.known_for(req) if known is None else known
    return AnswerPage(
        question=_question(req),
        answer_lines=_answer_lines(answer),
        numbers=_numbers(answer, known),
        believed=_text(getattr(req, "main_problem", None)),
        tested=_tested(req),
        monday=_monday(req),
        would_not=_would_not(req),
        rests_on=_rests_on(req, known),
    )


def _sections(req, known) -> tuple:
    """The proof sections the stage stored. A section with nothing to draw
    has no exhibit. A stored list that is not a list is no sections. A figure
    token stored before the stage bound its words prints as its figure."""
    raw = _loads(getattr(req, "storyline_json", None))
    items = raw.get("sections") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return ()
    from app.storyline.exhibits import for_section
    from app.storyline.model import Section

    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sid = item.get("id") if isinstance(item.get("id"), str) else ""
        title = item.get("title") if isinstance(item.get("title"), str) else ""
        if not sid or not title:
            continue
        takeaway = item.get("takeaway") if isinstance(item.get("takeaway"), str) else None
        try:
            exhibit = for_section(req, sid)
        except Exception:
            exhibit = None
        out.append(Section(sid, _bound(title, known), _bound(takeaway, known), exhibit, (), None, (), None))
    return tuple(out)


def _register(req, known):
    """The assembled register, or None when this run has none or it does not
    check out. Its words are printed bound, as the sections' are."""
    raw = _loads(getattr(req, "storyline_json", None))
    drafted = raw.get("register") if isinstance(raw, dict) else None
    if not isinstance(drafted, list) or not drafted:
        return None
    try:
        from app.storyline.register import assemble
        register = assemble(req, drafted)
    except Exception:
        return None
    from dataclasses import replace

    from app.storyline.model import Cost

    rows = tuple(replace(
        row, recommendation=_bound(row.recommendation, known), changes=_bound(row.changes, known),
        owner=_bound(row.owner, known), cost=Cost(row.cost.figure_id, _bound(row.cost.needs, known)),
    ) for row in register.rows)
    return replace(register, rows=rows, footnotes=tuple(_bound(note, known) for note in register.footnotes))


def _bound(text, known):
    """`text` with each figure token printed as its figure; anything else as it is."""
    if not isinstance(text, str) or not text:
        return text
    from app.figures.bind import bind

    return bind(text, known).text


def _question(req) -> str | None:
    brief = _loads(getattr(req, "brief_json", None))
    if not isinstance(brief, dict):
        return None
    return _text(brief.get("question"))


def _answer_lines(answer: dict) -> tuple[str, ...]:
    return tuple(line for key in _ANSWER_LINES if (line := _text(answer.get(key))))


def _numbers(answer: dict, known) -> tuple[Number, ...]:
    numbers: list[Number] = []
    for shown in list(answer.get("figures") or [])[:_MAX_FIGURES]:
        number = _shown(shown, known)
        if number is not None:
            numbers.append(number)
    move = answer.get("move")
    if len(numbers) < _MAX_NUMBERS and isinstance(move, dict):
        figure = known.get(figures_known.MOVE_ID)
        text = _text(move.get("display"))
        if figure is not None and text:
            numbers.append(Number(figures_known.MOVE_ID, text, tag_word(figure.kind)))
    return tuple(numbers)


def _shown(shown, known) -> Number | None:
    if not isinstance(shown, dict):
        return None
    ids = shown.get("ids") if isinstance(shown.get("ids"), list) else []
    figure_id = next((fid for fid in ids if isinstance(fid, str) and known.get(fid) is not None), None)
    if figure_id is None:
        return None
    figure = known.get(figure_id)
    text = _text(shown.get("value")) or display(figure)
    return Number(figure_id, text, tag_word(figure.kind))


def _tested(req) -> str | None:
    for hypothesis in _hypotheses(req):
        if not hypothesis.get("from_owner"):
            continue
        test = hypothesis.get("test") if isinstance(hypothesis.get("test"), dict) else {}
        return _text(test.get("because"))
    return None


def _monday(req) -> str | None:
    plan = _loads(getattr(req, "action_plan_json", None))
    phases = plan.get("phases") if isinstance(plan, dict) else None
    if isinstance(phases, list) and phases and isinstance(phases[0], dict):
        said = " ".join(part for key in ("do", "you") if (part := _text(phases[0].get(key))))
        if said:
            return said
    playbook = _loads(getattr(req, "playbook_json", None))
    wins = playbook.get("quick_wins") if isinstance(playbook, dict) else None
    for win in wins if isinstance(wins, list) else []:
        if isinstance(win, dict) and win.get("no_software"):
            title = _text(win.get("title"))
            if title:
                return title
    return None


def _would_not(req) -> tuple[str, ...] | None:
    said: list[str] = []
    for hypothesis in _hypotheses(req):
        test = hypothesis.get("test") if isinstance(hypothesis.get("test"), dict) else {}
        if test.get("verdict") != "refuted":
            continue
        statement = _text(hypothesis.get("statement"))
        if statement:
            said.append(statement)
        if len(said) >= _MAX_WOULD_NOT:
            break
    decision = _decision(req)
    why = _text(decision.get("why_not_the_others")) if isinstance(decision, dict) else None
    if why:
        said.append(why)
    return tuple(said) or None


def _rests_on(req, known) -> RestsOn:
    counts = known.counts()
    report = _loads(getattr(req, "qa_report_json", None))
    checks = report.get("checks") if isinstance(report, dict) else None
    rows = [c for c in checks if isinstance(c, dict)] if isinstance(checks, list) else []
    return RestsOn(
        counts["theirs"], counts["derived"], counts["ours"], counts["reference"],
        sum(1 for c in rows if c.get("passed") is True), len(rows),
    )


def _builds(req) -> bool:
    decision = _decision(req)
    return decision_builds(decision if isinstance(decision, dict) else None)


def _decision(req):
    return _loads(getattr(req, "consulting_recommendations_json", None))


def _hypotheses(req) -> list[dict]:
    diagnosis = _loads(getattr(req, "diagnosis_json", None))
    rows = diagnosis.get("hypotheses") if isinstance(diagnosis, dict) else None
    return [h for h in rows if isinstance(h, dict)] if isinstance(rows, list) else []


def for_web(req) -> dict:
    """The answer page and the register, as the screens read them.

    None when the run has no answer. A register that does not check out is
    absent, not filled.
    """
    story = build(req)
    if story is None:
        return {"answer_page": None, "register": None}
    from app.storyline.pdf import rests_line

    page = story.answer
    return {
        "answer_page": {
            "question": page.question,
            "answer_lines": list(page.answer_lines),
            "numbers": [
                {"figure_id": number.figure_id, "display": number.display, "tag": number.tag}
                for number in page.numbers
            ],
            "believed": page.believed,
            "tested": page.tested,
            "monday": page.monday,
            "would_not": list(page.would_not or ()),
            "rests_on": rests_line(page.rests_on),
        },
        "register": _register_web(req, story.register),
    }


def _register_web(req, register) -> dict | None:
    if register is None:
        return None
    known = figures_known.known_for(req)
    rows = []
    for row in register.rows:
        ends = {}
        for name in ("low", "mid", "high"):
            figure = known.get(f"REG-{row.id}-{name.upper()}")
            ends[name] = None if figure is None else {
                "figure_id": figure.id, "display": display(figure), "tag": tag_word(figure.kind),
            }
        rows.append({
            "recommendation": row.recommendation,
            "changes": row.changes,
            "when": row.when,
            "owner": row.owner,
            "depends_on": list(row.depends_on),
            **ends,
        })
    return {"rows": rows, "footnotes": list(register.footnotes)}


def _text(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value or None


def _loads(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None
