"""The release law: a rendered document holds no number nobody owns.

Long documents (the PDF volumes, the deck, the proposal) are not edited by the
law (plan ruling 7). While one is being built, every piece of content passes
through the renderer's choke points (`export_pdf._rich`, `export_pptx._add_text`,
the screens templates' Jinja `finalize`), and each choke point calls `check`:

    with law.scope(known, where="Volume I", request_id=req.id) as s:
        ... build the flowables; `_rich` calls `law.check(text)` ...
    findings = law.locate_pages(pdf_path, s.findings)
    law.save(req.id, "Volume I", findings, built_at=started)

`check(text)` binds every number that names a known figure to that figure's
literal value (`bind.bind`) and records a `Finding` for every number that names
none. It never raises: a build always completes, and a number the law could not
read is reported, not hidden. Outside a scope `check` returns its text untouched,
so a renderer that never opens a scope (the engine's work products) is unchanged.

What the law does not read (ruling 4). Furniture is declared by the code that
draws it, never guessed by pattern: page numbers, volume numerals, running
headers and footers, dates the chrome stamps, a renderer's own fixed copy and
its code-drawn labels are drawn outside the choke points (or inside
`furniture()`), so they never reach `check`. Inside content the reader's own
rules apply unchanged: a date, a clock time (against `hours` when given), a label
after a word from `labels.LABEL_WORDS` and a plan position are not quantities.
Nothing here hides a number with a pattern of its own.

Sample data (ruling 3) is not a fifth kind of figure. A drawn screen's sample
region is text inside `sample_region()`: the law does not read it, and the
template that opens one must carry the SAMPLE DATA stamp (`stamped`), or it
refuses to render.

`save` and `recorded` keep each document's findings beside its file, stamped
with the time its build started. `recorded` returns them only while that build
is newer than the request's last data change, so findings from a superseded
build never survive, and a rebuild replaces them. `page_reasons` turns them into
the release gate's reasons, one per page.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Iterable, Iterator, Sequence

from app.figures.model import FigureSet

logger = logging.getLogger("consultant.figures.law")

#: The documents the law records, in the order the release gate reports them,
#: and what a document's pages are called.
DOCUMENTS: tuple[tuple[str, str], ...] = (
    ("Volume I", "page"), ("Volume II", "page"), ("Volume III", "page"),
    ("Volume IV", "page"), ("The deck", "slide"),
)
_UNIT_OF = dict(DOCUMENTS)

#: What a sample region must show to be drawn at all.
SAMPLE_STAMP = "Sample data"

#: The words a finding's snippet keeps on each side of its number, to find the
#: number again on the rendered page.
_SNIPPET_WORDS = 4
#: The longest snippet kept, in characters, on each side of the number.
_SNIPPET_SIDE = 48
#: How often, and after how long a first wait in seconds, a refused file
#: replace is tried again before the record is written in place.
_REPLACE_ATTEMPTS = 4
_REPLACE_WAIT = 0.05


@dataclass(frozen=True)
class Finding:
    """One number in a rendered document that names no known figure: the number
    as written, a few words around it as printed, the document (or region) it
    sits in, and its page (or slide), None until located."""
    number: str
    snippet: str
    region: str
    page: int | None = None


def as_json(f: Finding) -> dict:
    return {"number": f.number, "snippet": f.snippet, "region": f.region, "page": f.page}


def from_json(d: object) -> Finding | None:
    """A stored finding, or None when it cannot be read."""
    if not isinstance(d, dict):
        return None
    page = d.get("page")
    if isinstance(page, bool) or not (page is None or isinstance(page, int)):
        return None
    number, snippet, region = d.get("number"), d.get("snippet"), d.get("region")
    if not all(isinstance(x, str) for x in (number, snippet, region)):
        return None
    return Finding(number, snippet, region, page)


@dataclass
class Scope:
    """The law while one document is built: the figures it knows, where it is,
    and what it has found so far (in the order `check` met them)."""
    known: FigureSet
    where: str
    hours: set[int] | None = None
    request_id: object = None
    #: what an earlier pass over the same document found, for a release gate
    #: consulted while this pass draws the cover (see `recorded`)
    pending: list[Finding] | None = None
    _found: list[Finding] = field(default_factory=list)

    @property
    def findings(self) -> list[Finding]:
        return list(self._found)


_ACTIVE: ContextVar[Scope | None] = ContextVar("figures_law_scope", default=None)
#: How deep inside unread regions (sample data, declared furniture) we are.
_UNREAD: ContextVar[int] = ContextVar("figures_law_unread", default=0)


def active() -> Scope | None:
    """The scope a document is being built in, or None."""
    return _ACTIVE.get()


@contextmanager
def scope(known: FigureSet, *, where: str, hours: set[int] | None = None, request_id: object = None,
          pending: Sequence[Finding] | None = None) -> Iterator[Scope]:
    """Hold `known` as the figures every `check` binds against while the block
    runs, and collect what it finds. `where` names the document ("Volume I").
    `hours` are the hours of the day the client gave; a clock time outside them
    is a finding (None: times are not checked). `request_id` ties the scope to
    one request, so the release gate can tell a build of that request is under
    way. `pending` is what an earlier pass of the same build found."""
    s = Scope(known if isinstance(known, FigureSet) else FigureSet(), str(where or ""), hours, request_id,
              list(pending) if pending is not None else None)
    token = _ACTIVE.set(s)
    unread = _UNREAD.set(0)
    try:
        yield s
    finally:
        _UNREAD.reset(unread)
        _ACTIVE.reset(token)


@contextmanager
def sample_region() -> Iterator[None]:
    """Text drawn inside this block is a screen's sample data: the law does not
    read it. Whoever opens one draws the SAMPLE DATA stamp inside it (`stamped`)."""
    token = _UNREAD.set(_UNREAD.get() + 1)
    try:
        yield
    finally:
        _UNREAD.reset(token)


@contextmanager
def furniture() -> Iterator[None]:
    """Text drawn inside this block is the renderer's own furniture (a
    stylesheet, chrome it composes), declared as such by the code that draws it."""
    with sample_region():
        yield


def stamped(html: object) -> bool:
    """Whether a rendered sample region carries the SAMPLE DATA stamp."""
    return SAMPLE_STAMP.lower() in str(html or "").lower()


class UnstampedSample(ValueError):
    """A sample region was drawn without the SAMPLE DATA stamp: its numbers would
    read as the client's, so it is not drawn at all."""


# -- checking ---------------------------------------------------------------------------------

_SPACE = re.compile(r"\s+")
_DIGIT_RUN = re.compile(r"\d[\d,.]*")


def _printed(text: str) -> str:
    """Text as the page prints it: bold markers gone, runs of space one space."""
    return _SPACE.sub(" ", text.replace("**", "")).strip()


def snippet(text: str, start: int, end: int) -> str:
    """The number at text[start:end] with up to a few words on each side, on its
    own line, as the page prints it."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line_end = len(text) if line_end < 0 else line_end
    left = text[max(line_start, start - _SNIPPET_SIDE):start]
    right = text[end:min(line_end, end + _SNIPPET_SIDE)]
    left_words = left.split(" ")
    if start - _SNIPPET_SIDE > line_start and len(left_words) > 1:
        left_words = left_words[1:]          # a cut word is no word
    right_words = right.split(" ")
    if end + _SNIPPET_SIDE < line_end and len(right_words) > 1:
        right_words = right_words[:-1]
    left = " ".join(left_words[-(_SNIPPET_WORDS + 1):])
    right = " ".join(right_words[:_SNIPPET_WORDS + 1])
    return _printed(left + text[start:end] + right)


def _record(s: Scope, number: str, text: str, start: int, end: int, region: str | None,
            page: int | None) -> None:
    s._found.append(Finding(str(number), snippet(text, start, end), str(region or s.where),
                            page if isinstance(page, int) and not isinstance(page, bool) else None))


def check(text, *, region: str | None = None, page: int | None = None):
    """`text` with each number that names a figure of the active scope printed
    as that figure's value; every number that names none is recorded as a
    `Finding` and left as written. `region` overrides the scope's document name
    in the finding; `page` is the page or slide when the caller already knows it.

    Outside a scope, inside a sample region or declared furniture, and for
    anything that is not a string, the text comes back untouched. Never raises:
    if the binder fails, every number the reader finds (or, failing that, every
    digit run) is recorded as a finding, and the text comes back as it was."""
    s = _ACTIVE.get()
    if s is None or _UNREAD.get() > 0 or not isinstance(text, str) or not text:
        return text
    try:
        from app.figures.bind import bind

        r = bind(text, s.known, hours=s.hours)
        for u in r.unresolved:
            _record(s, u.text, r.text, u.start, u.end, region, page)
        return r.text
    except Exception as exc:                                   # a law that raises stops a build
        logger.warning("the release law could not bind a text (%s); its numbers are findings",
                       type(exc).__name__)
    try:
        from app.figures.read import mentions

        for m in mentions(text):
            _record(s, m.text, text, m.start, m.end, region, page)
        return text
    except Exception:
        pass
    try:
        for m in _DIGIT_RUN.finditer(text):
            _record(s, m.group(0), text, m.start(), m.end(), region, page)
    except Exception:                                          # pragma: no cover - last resort
        pass
    return text


# -- pages ---------------------------------------------------------------------------------------

def sorted_findings(findings: Iterable[Finding]) -> list[Finding]:
    """Findings by document, then page (unlocated last), keeping the order they
    were found in among equals. The same findings always sort the same way."""
    order = {w: i for i, (w, _) in enumerate(DOCUMENTS)}
    indexed = list(enumerate(f for f in findings if isinstance(f, Finding)))
    indexed.sort(key=lambda p: (order.get(p[1].region, len(order)), p[1].region,
                                p[1].page is None, p[1].page or 0, p[0]))
    return [f for _, f in indexed]


def _variants(text: str) -> list[str]:
    """The snippet, then shorter forms of it that still hold its number: a
    sentence wrapped over a page break is found by one of its halves."""
    out = [text]
    words = text.split(" ")
    if len(words) > 2:
        half = len(words) // 2
        out += [" ".join(words[:half + 1]), " ".join(words[half:])]
    return [v for v in dict.fromkeys(out) if v]


def _page_texts(pdf_path: str, margins: tuple[float, float] | None) -> list[str]:
    import pymupdf

    texts = []
    doc = pymupdf.open(pdf_path)
    try:
        for page in doc:
            height = page.rect.height
            parts = []
            for b in page.get_text("blocks"):
                y0, y1, words = b[1], b[3], b[4]
                if margins and (y1 <= margins[0] or y0 >= height - margins[1]):
                    continue                                   # the chrome's bands, declared by its caller
                parts.append(words)
            texts.append(_SPACE.sub(" ", " ".join(parts)))
    finally:
        doc.close()
    return texts


def locate_pages(pdf_path: str, findings: Iterable[Finding], *,
                 margins: tuple[float, float] | None = None) -> list[Finding]:
    """The findings with their page set, from the rendered file (PyMuPDF text
    search of each snippet). `margins` are the heights, in points, of the bands at
    the top and the bottom of every page that the renderer fills with its own
    chrome: text there is not searched.

    Findings with the same snippet take its occurrences in page order, the last
    ones first used: a heading is repeated, earlier, by the table of contents. A
    snippet that cannot be found (nor either half of it) leaves the page None.
    Never raises; if the file cannot be read, the findings come back unlocated."""
    findings = [f for f in findings if isinstance(f, Finding)]
    try:
        texts = _page_texts(pdf_path, margins)
    except Exception as exc:
        logger.warning("could not read %s to locate the law's findings (%s)", pdf_path, type(exc).__name__)
        return sorted_findings(findings)
    by_snippet: dict[str, list[int]] = {}
    for i, f in enumerate(findings):
        by_snippet.setdefault(f.snippet, []).append(i)
    out = list(findings)
    for snip, idxs in by_snippet.items():
        pages: list[int] = []
        for variant in _variants(_printed(snip)):
            pages = [n + 1 for n, t in enumerate(texts) for _ in range(t.count(variant))]
            if pages:
                break
        taken = pages[-len(idxs):] if pages else []
        for k, i in enumerate(idxs):
            page = taken[k] if k < len(taken) else None
            out[i] = replace(findings[i], page=page)
    return sorted_findings(out)


# -- the record beside each document ------------------------------------------------------------

def _slug(where: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(where).lower()).strip("-") or "document"


def findings_path(request_id: object, where: str) -> str | None:
    """Where a document's findings are kept: beside its file in the exports
    folder, named after the request, so they go wherever the file goes."""
    if request_id is None or isinstance(request_id, bool):
        return None
    from app.config import settings

    return os.path.join(settings.UPLOADS_DIR, "exports", f"{request_id}-law-{_slug(where)}.json")


def save(request_id: object, where: str, findings: Iterable[Finding], *,
         built_at: datetime | None = None) -> bool:
    """Keep a document's findings, replacing what an earlier build kept.
    `built_at` is when the build started (naive UTC). Never raises; False when
    nothing could be kept."""
    path = findings_path(request_id, where)
    if path is None:
        return False
    record = {"where": where, "built_at": (built_at or datetime.utcnow()).isoformat(),
              "findings": [as_json(f) for f in sorted_findings(findings)]}
    body = json.dumps(record)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
    except OSError as exc:
        logger.warning("could not keep the law's findings for %s (%s)", where, type(exc).__name__)
        return False
    # Windows refuses a replace while another process (a virus scanner reading
    # the file just written) holds either file open: wait for it briefly, then
    # write in place rather than lose the record.
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(tmp, path)
            return True
        except OSError:
            time.sleep(_REPLACE_WAIT * (attempt + 1))
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        return True
    except OSError as exc:
        logger.warning("could not keep the law's findings for %s (%s)", where, type(exc).__name__)
        return False


def _load(request_id: object, where: str, updated_at: datetime | None) -> list[Finding] | None:
    """A document's kept findings, when its build started after the request's
    last data change; None when it was never built since (or cannot be read)."""
    path = findings_path(request_id, where)
    if path is None or not isinstance(updated_at, datetime) or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            record = json.load(fh)
        built_at = datetime.fromisoformat(str(record.get("built_at")))
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    if built_at.tzinfo is not None or not built_at > updated_at:
        return None
    items = record.get("findings") if isinstance(record.get("findings"), list) else []
    return [f for f in (from_json(d) for d in items) if f is not None]


def fresh(request_id: object, where: str, updated_at: datetime | None) -> bool:
    """Whether the document has kept findings from a build newer than the
    request's last data change (an empty list counts: it was checked)."""
    return _load(request_id, where, updated_at) is not None


def recorded(req) -> dict[str, list[Finding] | None]:
    """Each document's findings as the release gate should read them: the kept
    findings of its latest build when that build is newer than the request's
    last data change, None when it has not been rendered since. While a document
    of this request is being built, what its earlier pass found stands in for it."""
    request_id = getattr(req, "id", None)
    updated_at = getattr(req, "updated_at", None)
    out = {where: _load(request_id, where, updated_at) for where, _ in DOCUMENTS}
    s = _ACTIVE.get()
    if s is not None and request_id is not None and s.request_id == request_id:
        out[s.where] = list(s.pending if s.pending is not None else s._found)
    return out


def page_reasons(by_document: dict[str, list[Finding] | None]) -> list[tuple[str, str, str]]:
    """One (document, place, what) per page that holds findings, in document and
    page order: ("Volume I", "page 7", "the number 35 matches") or ("The deck",
    "slide 4", "the numbers 35 and 12 match"). A finding with no page is placed
    "page not located"."""
    out = []
    for where, unit in DOCUMENTS:
        found = by_document.get(where) or []
        pages: dict[int | None, list[str]] = {}
        for f in sorted_findings(replace(f, region=where) for f in found):
            numbers = pages.setdefault(f.page, [])
            if f.number not in numbers:
                numbers.append(f.number)
        for page, numbers in pages.items():
            place = f"{unit} {page}" if page is not None else f"{unit} not located"
            if len(numbers) == 1:
                what = f"the number {numbers[0]} matches"
            else:
                what = f"the numbers {', '.join(numbers[:-1])} and {numbers[-1]} match"
            out.append((where, place, what))
    return out
