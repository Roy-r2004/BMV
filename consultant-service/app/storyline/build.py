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
    return Storyline(answer_page(req), _register(req), (), _builds(req))


def answer_page(req) -> AnswerPage:
    """The opening page. Each part is taken from the column that holds it."""
    answer = _loads(getattr(req, "answer_json", None))
    answer = answer if isinstance(answer, dict) else {}
    known = figures_known.known_for(req)
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


def _register(req):
    """The assembled register, or None when this run has none or it does not check out."""
    raw = _loads(getattr(req, "storyline_json", None))
    drafted = raw.get("register") if isinstance(raw, dict) else None
    if not isinstance(drafted, list) or not drafted:
        return None
    try:
        from app.storyline.register import assemble
        return assemble(req, drafted)
    except Exception:
        return None


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
