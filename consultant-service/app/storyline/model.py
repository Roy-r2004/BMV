"""The storyline: one object the answer, the register and every file are drawn from.

A part that has nothing behind it is None or empty. Nothing here is filled in
to make a page look finished.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


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

    @property
    def foot(self) -> tuple[str, ...]:
        """The foot as it prints: the numbered notes, then the Note line, then the Source line."""
        return (*self.footnotes, *((self.note,) if self.note else ()), *self.sources)


@dataclass(frozen=True)
class Range:
    """A value flexed either way. The three ends add up across the register."""
    low: Decimal
    mid: Decimal
    high: Decimal
    unit: str
    period: str | None


@dataclass(frozen=True)
class Cost:
    """A cost we can point at, or the input still needed before it can be priced."""
    figure_id: str | None
    needs: str | None


@dataclass(frozen=True)
class RegisterRow:
    """One recommendation. `depends_on` names earlier rows, counting from 1."""
    id: str
    recommendation: str
    changes: str
    value: Range | None
    cost: Cost
    owner: str
    when: str
    depends_on: tuple[int, ...]


@dataclass(frozen=True)
class Register:
    """The one table. `total` is the headline the rows add up to."""
    rows: tuple[RegisterRow, ...]
    total: Range | None
    footnotes: tuple[str, ...]


@dataclass(frozen=True)
class Storyline:
    """Everything the files and the screens share."""
    answer: AnswerPage
    register: Register | None
    sections: tuple[Section, ...]
    builds: bool


def to_json(story: Storyline) -> dict:
    """A plain dict, safe to store. Tuples become lists."""
    return _plain(story)


def from_json(data: dict) -> Storyline:
    """The storyline `to_json` wrote."""
    return Storyline(
        answer=_answer(data["answer"]),
        register=_register(data.get("register")),
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


def _register(data) -> Register | None:
    if not isinstance(data, dict):
        return None
    total = data.get("total")
    return Register(
        rows=tuple(_register_row(row) for row in data.get("rows") or []),
        total=None if total is None else _range(total),
        footnotes=tuple(data.get("footnotes") or ()),
    )


def _register_row(data: dict) -> RegisterRow:
    value = data.get("value")
    cost = data.get("cost") or {}
    return RegisterRow(
        id=data["id"], recommendation=data["recommendation"], changes=data["changes"],
        value=None if value is None else _range(value),
        cost=Cost(cost.get("figure_id"), cost.get("needs")),
        owner=data["owner"], when=data["when"],
        depends_on=tuple(int(n) for n in data.get("depends_on") or ()),
    )


def _range(data: dict) -> Range:
    return Range(_decimal(data["low"]), _decimal(data["mid"]), _decimal(data["high"]),
                 data.get("unit") or "", data.get("period"))


def _decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


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
    if isinstance(value, Decimal):
        return format(value, "f")
    return value
