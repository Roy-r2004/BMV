"""The storyline: one object the answer, the register and every file are drawn from.

A part that has nothing behind it is None or empty. Nothing here is filled in
to make a page look finished.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Number:
    """One number on the answer page, tied to the figure it is."""
    figure_id: str
    display: str
    tag: str


@dataclass(frozen=True)
class RestsOn:
    """What the answer was checked against, as counts."""
    theirs: int
    derived: int
    ours: int
    reference: int
    checks_passed: int
    checks_run: int


@dataclass(frozen=True)
class AnswerPage:
    """The one page a package opens with."""
    question: str | None
    answer_lines: tuple[str, ...]
    numbers: tuple[Number, ...]
    believed: str | None
    tested: str | None
    monday: str | None
    would_not: tuple[str, ...] | None
    rests_on: RestsOn


@dataclass(frozen=True)
class Exhibit:
    """One exhibit. `data` holds figure ids and the strings drawn from them."""
    id: str
    kind: str
    caption: str
    takeaway: str
    data: dict
    source: str | None


@dataclass(frozen=True)
class Section:
    """One proof section. The foot is footnotes, then a note, then sources."""
    id: str
    title: str
    takeaway: str | None
    exhibit: Exhibit | None
    footnotes: tuple[str, ...]
    note: str | None
    sources: tuple[str, ...]
    stamp: str | None


@dataclass(frozen=True)
class Storyline:
    """Everything the files and the screens share. `register` is filled in by
    the register (Task 3); until then it is None."""
    answer: AnswerPage
    register: object | None
    sections: tuple[Section, ...]
    builds: bool


def to_json(story: Storyline) -> dict:
    """A plain dict, safe to store. Tuples become lists."""
    return _plain(story)


def from_json(data: dict) -> Storyline:
    """The storyline `to_json` wrote."""
    return Storyline(
        answer=_answer(data["answer"]),
        register=data.get("register"),
        sections=tuple(_section(s) for s in data.get("sections") or []),
        builds=bool(data["builds"]),
    )


def _answer(data: dict) -> AnswerPage:
    would = data.get("would_not")
    return AnswerPage(
        question=data.get("question"),
        answer_lines=_texts(data.get("answer_lines")),
        numbers=tuple(Number(n["figure_id"], n["display"], n["tag"]) for n in data.get("numbers") or []),
        believed=data.get("believed"),
        tested=data.get("tested"),
        monday=data.get("monday"),
        would_not=None if would is None else _texts(would),
        rests_on=RestsOn(**data["rests_on"]),
    )


def _section(data: dict) -> Section:
    exhibit = data.get("exhibit")
    return Section(
        id=data["id"], title=data["title"], takeaway=data.get("takeaway"),
        exhibit=None if exhibit is None else Exhibit(
            exhibit["id"], exhibit["kind"], exhibit["caption"], exhibit["takeaway"],
            dict(exhibit.get("data") or {}), exhibit.get("source")),
        footnotes=_texts(data.get("footnotes")),
        note=data.get("note"),
        sources=_texts(data.get("sources")),
        stamp=data.get("stamp"),
    )


def _texts(value) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(value)


def _plain(value):
    if hasattr(value, "__dataclass_fields__"):
        return {name: _plain(getattr(value, name)) for name in value.__dataclass_fields__}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value
