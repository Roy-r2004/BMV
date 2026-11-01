"""The Figure: one number, and whose it is.

Every number a client can see is a Figure of one of four kinds:

    theirs     the client gave it (an answer, a field, a cell in their file)
    derived    we worked it out from other figures, and can show the working
    ours       we propose it; the client has not agreed to it yet
    reference  a published figure, cited

The value is a Decimal, always. A float is refused at construction, because a
float is how 0.07 times 100 becomes 7.000000000000001 on a client's page.

This module is the pure data model: the Figure, the set of figures a request
knows, how a figure prints, and the mapping to and from the pipeline's claim
dicts (`app/pipeline/registry.py`). It uses the standard library only. In
particular it does not import `app.pipeline.registry` or `app.engine`: the
pipeline will import this package, and the engine imports the pipeline, so an
import in either direction would close a cycle. The few words it needs from the
registry are copied below with the registry line that defines each, and
`tests/figures/test_model.py` fails if they drift.
"""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation
from typing import Iterable, Iterator, Literal

Kind = Literal["theirs", "derived", "ours", "reference"]
KINDS: tuple[str, ...] = ("theirs", "derived", "ours", "reference")


# -- sources: where a figure comes from, one shape per kind --------------------

@dataclass(frozen=True)
class TheirsSource:
    """The client's own words. `turn` is the 1-based position of the interview
    answer, `field` the question or form field (or, for a file, the sheet),
    `quote` the sentence it sits in, `file` and `cell` where in an upload."""
    turn: int | None
    field: str | None
    quote: str
    file: str | None
    cell: str | None


@dataclass(frozen=True)
class Working:
    """How a derived figure was worked out. `inputs` are the ids of the figures
    it came from, `op` names the operation, `text` shows the working."""
    inputs: tuple[str, ...]
    op: str
    text: str


@dataclass(frozen=True)
class Proposal:
    """What we propose, in plain words."""
    note: str


@dataclass(frozen=True)
class Reference:
    """A published figure: who published it, when, about whom, and where."""
    publication: str
    year: int
    population: str
    url: str


Source = TheirsSource | Working | Proposal | Reference

# The one source class each kind carries. A figure whose source belongs to
# another kind is a figure that cannot say whose it is, so it is refused.
_KIND_SOURCE: dict[str, type] = {
    "theirs": TheirsSource, "derived": Working, "ours": Proposal, "reference": Reference,
}

# Wide enough for the repr of any float (up to about 330 digits). Rounding is
# half away from zero, which is how a person rounds 2.5.
_CTX = Context(prec=500, rounding=ROUND_HALF_UP)


def _rounded(value: Decimal, precision: int) -> Decimal:
    """`value` at `precision` digits after the point; negative rounds to tens,
    hundreds. 44928 at -3 is 4.5E+4."""
    return value.quantize(Decimal(1).scaleb(-precision), context=_CTX)


# -- the figure ------------------------------------------------------------------

@dataclass(frozen=True)
class Figure:
    """One number. `precision` is the digits shown after the point; negative
    rounds to tens, hundreds. `period` is the time basis ("year", "week") or
    None when the number has none."""
    id: str
    value: Decimal
    unit: str
    period: str | None
    kind: Kind
    source: Source
    precision: int

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("a figure's id must be a string")
        if not self.id:
            raise ValueError("a figure needs a non-empty id")
        if not isinstance(self.value, Decimal):
            raise TypeError(f"figure {self.id}: value must be a Decimal, not {type(self.value).__name__}; "
                            "build it from the digits written (Decimal('0.07')), never from a float")
        if not self.value.is_finite():
            raise ValueError(f"figure {self.id}: value must be a finite number")
        if not isinstance(self.unit, str):
            raise TypeError(f"figure {self.id}: unit must be a string")
        if self.period is not None and not isinstance(self.period, str):
            raise TypeError(f"figure {self.id}: period must be a string or None")
        if self.kind not in KINDS:
            raise ValueError(f"figure {self.id}: kind must be one of {', '.join(KINDS)}, not {self.kind!r}")
        if not isinstance(self.source, _KIND_SOURCE[self.kind]):
            raise ValueError(f"figure {self.id}: a {self.kind} figure carries a "
                             f"{_KIND_SOURCE[self.kind].__name__}, not a {type(self.source).__name__}")
        if isinstance(self.precision, bool) or not isinstance(self.precision, int):
            raise TypeError(f"figure {self.id}: precision must be an int")
        try:
            rounded = _rounded(self.value, self.precision)
        except InvalidOperation:
            raise ValueError(f"figure {self.id}: precision {self.precision} is out of range") from None
        if self.kind in ("theirs", "reference") and rounded != self.value:
            # these print with no "~", so they may not hold digits they would not print
            raise ValueError(f"figure {self.id}: a {self.kind} figure's precision is the digits it was "
                             f"given with; {self.value} does not fit {self.precision}")


# -- display -----------------------------------------------------------------------

# How a figure prints, by unit: (prefix, suffix for one, suffix for many, fewest
# digits after the point once any are shown). This table is the only place that
# knows. Money shows cents or nothing: $22, $22.50, never $22.5. The suffix for
# "one" is used whenever the number shown equals 1, at any precision ("1 week",
# "1.0 week"); every other number, 0.5 and 1.5 included, takes the plural. A unit
# not in the table prints the number,
# a space, and the unit word as given ("12 reformers", "24 GB", "30 tokens/sec"),
# which is right for every hardware unit the registry emits
# (registry._CAPACITY_CANON) and for any word a client used.
#   "USD" and "count" are what registry._infer_unit returns; "percent" is the
#   Figure form of the registry's "%" (a fraction there, a percent number here).
#   The time words are the ones registry._NUM can capture.
#   "EUR" and "GBP" print their own sign (the binder meets euro and pound amounts a
#   client typed); any other currency code prints as an unknown unit, "1,000 AUD".
_TIME_UNITS = (("ms", "ms"), ("millisecond", "milliseconds"), ("second", "seconds"),
               ("minute", "minutes"), ("hour", "hours"), ("day", "days"), ("week", "weeks"),
               ("month", "months"), ("year", "years"))


def _unit_styles() -> dict[str, tuple[str, str, str, int]]:
    table = {
        "USD": ("$", "", "", 2),
        "EUR": ("\u20ac", "", "", 2),
        "GBP": ("\u00a3", "", "", 2),
        "percent": ("", "%", "%", 0),
        "count": ("", "", "", 0),
        "": ("", "", "", 0),
    }
    for one, many in _TIME_UNITS:
        table[one] = table[many] = ("", f" {one}", f" {many}", 0)
    return table


_UNIT_STYLE = _unit_styles()

# Derived and ours are estimates of a kind: when rounding to their precision
# changed the value, the page says so with "~". Theirs and reference are exact.
_APPROXIMATE_KINDS = ("derived", "ours")


def _shown(f: Figure, *, unit_word: bool, symbols: bool, tilde: bool = True) -> str:
    rounded = _rounded(f.value, f.precision)
    prefix, one, many, fewest = _UNIT_STYLE.get(f.unit, ("", f" {f.unit}", f" {f.unit}", 0))
    magnitude = rounded.copy_abs()
    digits = max(f.precision, fewest) if f.precision > 0 else 0
    number = format(magnitude, f",.{digits}f")
    sign = "-" if rounded < 0 else ""
    approx = "~" if tilde and f.kind in _APPROXIMATE_KINDS and rounded != f.value else ""
    suffix = one if magnitude == 1 else many
    is_word = suffix.startswith(" ")   # " weeks", " GB" are words; "%" is a symbol
    if is_word and not unit_word:
        suffix = ""
    if not symbols:
        prefix = ""
        if not is_word:
            suffix = ""
    return f"{approx}{sign}{prefix}{number}{suffix}"


def display(f: Figure) -> str:
    """The figure as a client reads it: "$22", "25%", "~45,000", "6 weeks"."""
    return _shown(f, unit_word=True, symbols=True)


def display_number(f: Figure, *, symbols: bool = True, tilde: bool = True) -> str:
    """The number alone, for putting a figure's value where the model wrote a
    number inside a sentence that already has the unit word: "6" for 6 weeks,
    "12" for 12 reformers. It keeps the "~", the sign, the thousands commas and
    the precision, and with `symbols` (the default) the currency sign before
    money and the "%" after a percent: "~$45,000", "25%". With `symbols=False` it
    is only the "~", the sign and the digits, for a caller that keeps the symbols
    the sentence already has. With `tilde=False` the "~" is left off, for a
    caller whose sentence already hedges ("about" before the number)."""
    return _shown(f, unit_word=False, symbols=symbols, tilde=tilde)


def displayed_value(f: Figure) -> Decimal:
    """The number the figure shows: its value rounded to its precision, which is
    what a reader of `display(f)` has in front of them (44928 at -3 shows 45,000)."""
    return _rounded(f.value, f.precision)


_TAG_WORDS = {"theirs": "yours", "derived": "worked out", "ours": "our estimate", "reference": "reference"}


def tag_word(kind: Kind) -> str:
    """The word a client sees beside a figure, the same on every surface."""
    try:
        return _TAG_WORDS[kind]
    except KeyError:
        raise ValueError(f"no tag word for kind {kind!r}") from None


# -- JSON --------------------------------------------------------------------------

def _source_json(s: Source) -> dict:
    if isinstance(s, TheirsSource):
        return {"turn": s.turn, "field": s.field, "quote": s.quote, "file": s.file, "cell": s.cell}
    if isinstance(s, Working):
        return {"inputs": list(s.inputs), "op": s.op, "text": s.text}
    if isinstance(s, Proposal):
        return {"note": s.note}
    return {"publication": s.publication, "year": s.year, "population": s.population, "url": s.url}


def as_json(f: Figure) -> dict:
    """The figure as plain JSON. The value is a string so no reader turns it
    into a float; the source has the shape of its kind."""
    return {"id": f.id, "value": format(f.value, "f"), "unit": f.unit, "period": f.period,
            "kind": f.kind, "source": _source_json(f.source), "precision": f.precision}


def _field(d: dict, key: str, want: type, what: str, *, null: bool = False) -> object:
    """d[key], which must be present and a `want` (an int is never a bool here);
    None is allowed only when `null`. Anything else is a ValueError in plain words."""
    if key not in d:
        raise ValueError(f"{what} is missing '{key}'")
    v = d[key]
    if v is None and null:
        return None
    if not isinstance(v, want) or (want is int and isinstance(v, bool)):
        article = "a whole number" if want is int else "text"
        raise ValueError(f"{what}: '{key}' must be {article}{' or null' if null else ''}")
    return v


def _source_from_json(kind: str, s: object) -> Source:
    if not isinstance(s, dict):
        raise ValueError("a figure's source is a JSON object")
    what = f"a {kind} figure's source"
    if kind == "theirs":
        return TheirsSource(
            turn=_field(s, "turn", int, what, null=True), field=_field(s, "field", str, what, null=True),
            quote=_field(s, "quote", str, what), file=_field(s, "file", str, what, null=True),
            cell=_field(s, "cell", str, what, null=True))
    if kind == "derived":
        inputs = s.get("inputs")
        if not isinstance(inputs, (list, tuple)) or not all(isinstance(i, str) for i in inputs):
            raise ValueError(f"{what}: 'inputs' must be a list of figure ids")
        return Working(inputs=tuple(inputs), op=_field(s, "op", str, what), text=_field(s, "text", str, what))
    if kind == "ours":
        return Proposal(note=_field(s, "note", str, what))
    if kind == "reference":
        return Reference(publication=_field(s, "publication", str, what), year=_field(s, "year", int, what),
                         population=_field(s, "population", str, what), url=_field(s, "url", str, what))
    raise ValueError(f"unknown figure kind {kind!r}")


def from_json(d: dict) -> Figure:
    """Inverse of `as_json`. Anything that is not a figure, at any depth, raises
    ValueError with a plain message."""
    if not isinstance(d, dict):
        raise ValueError("a figure is a JSON object")
    what = "a figure"
    kind = _field(d, "kind", str, what)
    try:
        value = Decimal(_field(d, "value", str, what))
    except InvalidOperation:
        raise ValueError("a figure's 'value' must be a number written as text") from None
    return Figure(id=_field(d, "id", str, what), value=value, unit=_field(d, "unit", str, what),
                  period=_field(d, "period", str, what, null=True), kind=kind,
                  source=_source_from_json(kind, d.get("source")), precision=_field(d, "precision", int, what))


# -- the pipeline's claims ---------------------------------------------------------
#
# A claim is the dict built by registry._claim (registry.py:266). Copied from the
# registry, checked against it by tests/figures/test_model.py:

# registry.py:94-95 (APPROVAL); the em dash is written as an escape to keep this file ASCII
_APPROVAL_PROPOSED = "consultant_proposed \u2014 client approval required"
_APPROVAL_REJECTED = "rejected"

# registry.py:93 (PROVENANCE): client_input is theirs, machine_computed is derived,
# consultant_proposed is ours. canonical_gate takes its kind from its approval
# status (plan ruling 1): stated by the client is theirs, verified by a machine is
# derived, anything proposed (or not said) is ours, rejected is not a figure.
_PROVENANCE_KIND = {"client_input": "theirs", "machine_computed": "derived", "consultant_proposed": "ours"}
_GATE_KIND_BY_APPROVAL = {"client_stated": "theirs", "machine_verified": "derived"}

# registry.py:1709, 2782: units whose value is stored as a fraction (0.25 for 25%).
# A Figure holds the percent number (25) with unit "percent". "ratio" (the scenario
# assumptions, registry.py:397) is the same thing.
_FRACTION_UNITS = frozenset({"%", "ratio"})

# registry.py:87-92 (CLAIM_TYPES). A derived figure remembers its claim type in
# Working.op; any other type reads as a plain derived_value.
_DERIVED_CLAIM_TYPES = ("derived_value", "time_basis_conversion", "scenario_impact")

# the source strings the producers write (registry.py:339/348, evidence.py:279)
_DISCOVERY_PREFIX = "discovery: "
_FILE_SEP = " \u00b7 "   # "<file> . <sheet> . <CELL>", a middle dot


def _kind_of(c: dict) -> Kind:
    cid = c.get("id")
    provenance, approval = c.get("provenance"), c.get("approval_status")
    if approval == _APPROVAL_REJECTED:
        raise ValueError(f"claim {cid} was rejected, so it is not a figure")
    if provenance == "canonical_gate":
        return _GATE_KIND_BY_APPROVAL.get(approval, "ours")
    try:
        return _PROVENANCE_KIND[provenance]
    except (KeyError, TypeError):
        raise ValueError(f"claim {cid} has provenance {provenance!r}, which is not one a figure can have") from None


def decimal_from_float(value: float) -> Decimal:
    """The digits a float stands for. It is first taken to 15 significant digits
    (DBL_DIG, what a float reliably holds), then built from its repr: 0.07 is
    Decimal('0.07'), and division noise goes (0.33299999999999996 is 0.333). Any
    number typed with 15 digits or fewer survives exactly. A whole number carries
    no trailing '.0'. The one place in the package a float becomes a Decimal;
    `calc.decimal_of` and the claim mapping below both come here. A float that is
    not finite raises ValueError."""
    if not math.isfinite(value):
        raise ValueError("a number must be finite")
    d = Decimal(repr(float(format(value, ".15g"))))
    return Decimal(int(d)) if d == d.to_integral_value() else d


def _decimal_of(value: object, cid: str) -> Decimal:
    """The digits of the claim's number (see `decimal_from_float`); a whole number
    carries no trailing '.0'."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"claim {cid} has no numeric value")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"claim {cid} has no finite value")
        return decimal_from_float(value)
    return Decimal(value)


def _file_field(source: str, file: str, cell: str | None) -> str | None:
    """The sheet in '<file> . <sheet> . <CELL>', or None when the source is not that shape."""
    prefix, suffix = f"{file}{_FILE_SEP}", f"{_FILE_SEP}{cell}" if cell else ""
    if source.startswith(prefix) and source.endswith(suffix) and len(source) > len(prefix) + len(suffix):
        return source[len(prefix):len(source) - len(suffix)]
    return None


def from_claim(c: dict) -> Figure:
    """A Figure from a registry claim dict.

    The kind follows the claim's provenance (and, for canonical_gate, its
    approval). A rejected claim is not a figure and raises ValueError, as does a
    claim with no numeric value. A percentage held as a fraction (unit "%" or
    "ratio", 0.25) becomes the percent number (25) with unit "percent". The
    source is read from the strings the producers write: a theirs figure keeps its
    question (or file, sheet and cell) and its text; a derived figure keeps the
    claim's source as its working text; an ours figure keeps the claim's text as
    its note."""
    cid = c.get("id")
    if not isinstance(cid, str) or not cid:
        raise ValueError("a claim needs an id")
    kind = _kind_of(c)
    value = _decimal_of(c.get("value"), cid)
    unit = str(c.get("unit") or "")
    if unit in _FRACTION_UNITS:
        value, unit = value.scaleb(2), "percent"
    precision = max(0, -value.as_tuple().exponent)
    basis = c.get("time_basis")
    period = None if basis in (None, "", "n/a") else str(basis)
    source, text = str(c.get("source") or ""), str(c.get("text") or "")
    if kind == "theirs":
        file = str(c["file"]) if c.get("file") else None
        cell = str(c["cell"]) if c.get("cell") else None
        if file:
            field = _file_field(source, file, cell)
        elif source.startswith(_DISCOVERY_PREFIX):
            field = source[len(_DISCOVERY_PREFIX):] or None
        else:
            field = None
        src: Source = TheirsSource(turn=None, field=field, quote=text, file=file, cell=cell)
    elif kind == "derived":
        ctype = c.get("type")
        src = Working(inputs=(), op=ctype if ctype in _DERIVED_CLAIM_TYPES else "derived_value", text=source)
    else:
        src = Proposal(note=text or source)
    return Figure(id=cid, value=value, unit=unit, period=period, kind=kind, source=src, precision=precision)


# -- the set of figures a request knows ----------------------------------------------

# Two numbers are the same figure when they differ by no more than this fraction of
# the larger (registry._close, registry.py:227).
_TOLERANCE = Decimal("0.005")


def _within(a: Decimal, b: Decimal) -> bool:
    if a == b:
        return True
    gap = _CTX.subtract(a, b).copy_abs()
    return gap <= _CTX.multiply(_TOLERANCE, max(a.copy_abs(), b.copy_abs()))


class FigureSet:
    """The figures a request knows, by id, in the order they were added."""

    def __init__(self, figures: Iterable[Figure] = ()) -> None:
        self._by_id: dict[str, Figure] = {}
        self._index: tuple[list[Decimal], list[Figure], dict[Decimal, list[Figure]], dict[str, int]] | None = None
        for f in figures:
            self.add(f)

    def add(self, f: Figure) -> None:
        """Add a figure. The same figure again changes nothing; a different
        figure under a known id raises ValueError, since an id must mean one number."""
        if not isinstance(f, Figure):
            raise TypeError("a FigureSet holds Figures")
        known = self._by_id.get(f.id)
        if known is None:
            self._by_id[f.id] = f
            self._index = None
        elif known != f:
            raise ValueError(f"two different figures share the id {f.id}")

    def get(self, id: str) -> Figure | None:
        return self._by_id.get(id)

    def __contains__(self, id: object) -> bool:
        return id in self._by_id

    def __iter__(self) -> Iterator[Figure]:
        return iter(self._by_id.values())

    def __len__(self) -> int:
        return len(self._by_id)

    def by_kind(self, kind: Kind) -> list[Figure]:
        if kind not in KINDS:
            raise ValueError(f"unknown figure kind {kind!r}")
        return [f for f in self if f.kind == kind]

    def counts(self) -> dict[Kind, int]:
        out: dict[str, int] = {k: 0 for k in KINDS}
        for f in self:
            out[f.kind] += 1
        return out  # type: ignore[return-value]

    def _built(self):
        """The figures sorted by value, and by the value each one displays, built
        when first needed and dropped when a figure is added."""
        if self._index is None:
            ordered = sorted(self._by_id.values(), key=lambda f: f.value)
            shown: dict[Decimal, list[Figure]] = {}
            for f in self._by_id.values():
                shown.setdefault(_rounded(f.value, f.precision), []).append(f)
            self._index = ([f.value for f in ordered], ordered, shown,
                           {fid: n for n, fid in enumerate(self._by_id)})
        return self._index

    def match(self, value: Decimal, unit: str | None = None) -> list[Figure]:
        """Every figure `value` could be a mention of: equal to it within half a
        percent, or equal to it as the figure displays it (44928 shown as 45,000
        matches 45000). In the order added. With `unit`, only figures in that unit."""
        if not isinstance(value, Decimal):
            raise TypeError("match takes a Decimal")
        if not value.is_finite():
            return []
        values, ordered, shown, position = self._built()
        # a figure within half a percent of `value` lies within one percent of it
        a, b = _CTX.multiply(value, Decimal("0.99")), _CTX.divide(value, Decimal("0.99"))
        lo, hi = (a, b) if a <= b else (b, a)
        near = ordered[bisect_left(values, lo):bisect_right(values, hi)]
        found = {f.id: f for f in near}
        for f in shown.get(value, ()):
            found[f.id] = f
        return [f for f in sorted(found.values(), key=lambda f: position[f.id])
                if (unit is None or f.unit == unit)
                and (_within(f.value, value) or _rounded(f.value, f.precision) == value)]
