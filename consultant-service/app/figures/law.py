"""The release law: a rendered document holds no number nobody owns.

Long documents (the PDF volumes, the roadmap, the deck, the proposal) are not edited by the
law (plan ruling 7). While one is being built, every piece of content passes
through the renderer's choke points (`export_pdf._rich`, `export_pptx._add_text`,
the screens templates' Jinja `finalize`), and each choke point calls `check`:

    with law.scope(known, where="Volume I", request_id=req.id) as s:
        ... build the flowables; `_rich` calls `law.check(text)` ...
    findings = law.locate_pages(pdf_path, s.findings)
    law.save(req.id, "Volume I", findings, built_at=started, data_at=req.updated_at)

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

`save` and `record` keep each document's findings beside its file, stamped
with the time its check started and the release status its cover carries. A
record counts only while its check is newer than the request's last data
change, so findings from a superseded build never survive, and a rebuild
replaces them. `ensure_records` runs the law-only pass of every document of the
package that has no fresh record (content through the law, nothing printed), so
a cover is always stamped from the whole package's status; a cached file is
served only while the status it was stamped with is still the package's.
`page_reasons` turns the records into the release gate's reasons, one per page.
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
import tempfile
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Iterator, Sequence

from app.figures.model import FigureSet

logger = logging.getLogger("consultant.figures.law")

#: The documents the law records, in the order the release gate reports them,
#: and what a document's pages are called.
DOCUMENTS: tuple[tuple[str, str], ...] = (
    ("Volume I", "page"), ("Volume II", "page"), ("Volume III", "page"),
    ("The roadmap", "page"), ("Volume IV", "page"), ("The deck", "slide"),
)


def _law_version() -> str:
    """The rules a record was made under: LAW_RULES (bumped by hand when the
    law's own rules change) and a short hash of the modules that decide what a
    finding is (the law, the reader, the binder, the label words, the figure
    model). A record or a cached file made under other rules is stale."""
    import hashlib

    digest = hashlib.sha256()
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("law.py", "read.py", "bind.py", "labels.py", "model.py"):
        try:
            with open(os.path.join(here, name), "rb") as fh:
                digest.update(fh.read())
        except OSError:
            digest.update(name.encode())
    return f"{LAW_RULES}-{digest.hexdigest()[:12]}"


#: Bumped by hand when the law's rules change in a way the module hash would
#: not show (a document's furniture redrawn, a choke point added).
LAW_RULES = 2
LAW_VERSION = _law_version()

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
    #: exact phrases our own code prints for a registered figure in a form the
    #: binder has no figure for ("5 percentage points": a change between two
    #: percents is never a percent), each declared by the code that registers it
    phrases: tuple[str, ...] = ()
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
          pending: Sequence[Finding] | None = None, phrases: Iterable[str] = ()) -> Iterator[Scope]:
    """Hold `known` as the figures every `check` binds against while the block
    runs, and collect what it finds. `where` names the document ("Volume I").
    `hours` are the hours of the day the client gave; a clock time outside them
    is a finding (None: times are not checked). `request_id` ties the scope to
    one request, so the release gate can tell a build of that request is under
    way. `pending` is what an earlier pass of the same build found. `phrases`
    are exact phrases our code prints for a registered figure the binder cannot
    bind (see `Scope.phrases`): a number inside one of them is that figure."""
    s = Scope(known if isinstance(known, FigureSet) else FigureSet(), str(where or ""), hours, request_id,
              list(pending) if pending is not None else None,
              tuple(p for p in dict.fromkeys(phrases or ()) if isinstance(p, str) and p.strip()))
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


class UnstampedSample(Exception):
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


def _finding(s: Scope, number: str, text: str, start: int, end: int, region: str | None,
             page: int | None) -> Finding:
    return Finding(str(number), snippet(text, start, end), str(region or s.where),
                   page if isinstance(page, int) and not isinstance(page, bool) else None)


def _phrase_spans(text: str, phrases: Sequence[str]) -> list[tuple[int, int]]:
    """Where each declared phrase stands in `text`, matched exactly and as whole
    words (a phrase is never found inside a longer number)."""
    spans = []
    for p in phrases:
        for m in re.finditer(r"(?<![\w.,])" + re.escape(p) + r"(?![\w])", text):
            spans.append((m.start(), m.end()))
    return spans


#: The ids figures and claims carry. A model told to cite them sometimes prints
#: them in the sentence, and a client must never read "20% (T4-1)".
_ID = r"(?:T\d+-\d+|F-[a-z_]+-\d+|E\d+-\d+(?:\.\d+)?|CF-\d+|CE-\d+|CAP-\d+|SUM-\d+|REF-\d+|PROP-\d+|TH-[a-z0-9-]+?-\d+)"
_CITED_IDS = re.compile(rf"\s*[(\[]{_ID}(?:\s*,\s*{_ID})*[)\]]")
_THRESHOLD_ID = re.compile(r"\bTH-[a-z0-9-]+?-\d+\b(:\s*)?")
_PROPOSED_AFTER = re.compile(r"(?:\s+[a-z%-]+){0,3}\s*\(proposed\b", re.I)
_PROPOSED_BEFORE = re.compile(r"approval required\)\s*$", re.I)


def _without_ids(text: str, known: FigureSet) -> str:
    """The text as a client should read it: ids cited in brackets are gone, and a
    threshold written as its id reads as its value."""
    def threshold(m: re.Match) -> str:
        if m.group(1):
            return ""
        figure = known.get(m.group(0))
        return format(figure.value.normalize(), "f") if figure is not None else ""

    return _THRESHOLD_ID.sub(threshold, _CITED_IDS.sub("", text))


def _marked_as_proposed(text: str, start: int, end: int) -> bool:
    """The label is printed right beside this number, so the reader can see it is
    ours to propose and theirs to approve. Close by only: a label further along
    the sentence says nothing about this number."""
    return bool(_PROPOSED_AFTER.match(text, end)) or bool(_PROPOSED_BEFORE.search(text, 0, start))


def _exempt(m, known: FigureSet, constants: frozenset, fractions_as_percent: bool) -> bool:
    """Whether an unresolved number in a working is one of the working's own
    constants, or a share written as a fraction of a percent figure we hold
    (0.12 for the client's 12%, the registry's own convention)."""
    value = getattr(m, "value", None)
    # in a working "0.12 x" is an operand and its operator, which the reader
    # reads as a multiplier: the same number either way
    if value is None or getattr(m, "form", None) not in ("digit", "word", "range", "multiplier"):
        return False
    if value in constants:
        return True
    if fractions_as_percent and 0 < value < 1:
        return any(f.unit == "percent" for f in known.match(value * 100))
    return False


def check(text, *, region: str | None = None, page: int | None = None,
          constants: Iterable = (), fractions_as_percent: bool = False):
    """`text` with each number that names a figure of the active scope printed
    as that figure's value; every number that names none is recorded as a
    `Finding` and left as written. `region` overrides the scope's document name
    in the finding ("working", "evidence question"); `page` is the page or slide
    when the caller already knows it.

    A working (the arithmetic behind a derived figure) passes its own constants:
    `constants` are the values the code that verified it allows besides figures
    (the calendar constants, the line's period step), and with
    `fractions_as_percent` a share written as 0.12 matches the 12% we hold.

    Outside a scope, inside a sample region or declared furniture, and for
    anything that is not a string, the text comes back untouched. Never raises:
    if the binder fails, every number the reader finds (or, failing that, every
    digit run) is recorded as a finding, and the text comes back as it was. A
    stage that fails part-way records nothing, so no number is recorded twice."""
    s = _ACTIVE.get()
    if s is None or _UNREAD.get() > 0 or not isinstance(text, str) or not text:
        return text
    text = _without_ids(text, s.known)
    try:
        allowed = frozenset(Decimal(str(c)) for c in constants)
    except Exception:
        allowed = frozenset()
    try:
        from app.figures.bind import bind

        r = bind(text, s.known, hours=s.hours)
        declared = _phrase_spans(r.text, s.phrases)
        found = [_finding(s, u.text, r.text, u.start, u.end, region, page) for u in r.unresolved
                 if not _exempt(u, s.known, allowed, fractions_as_percent)
                 and not _marked_as_proposed(r.text, u.start, u.end)
                 and not any(a <= u.start and u.end <= b for a, b in declared)]
        s._found.extend(found)
        return r.text
    except Exception as exc:                                   # a law that raises stops a build
        logger.warning("the release law could not bind a text (%s); its numbers are findings",
                       type(exc).__name__)
    try:
        from app.figures.read import mentions

        found = [_finding(s, m.text, text, m.start, m.end, region, page) for m in mentions(text)
                 if not _exempt(m, s.known, allowed, fractions_as_percent)]
        s._found.extend(found)
        return text
    except Exception:
        pass
    try:
        found = [_finding(s, m.group(0), text, m.start(), m.end(), region, page)
                 for m in _DIGIT_RUN.finditer(text)]
        s._found.extend(found)
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
    return locate_in_texts(texts, findings)


def locate_in_texts(texts: Sequence[str], findings: Iterable[Finding]) -> list[Finding]:
    """`locate_pages` over page texts the caller already has (page 1 first), for
    a document whose pages are known without printing it."""
    findings = [f for f in findings if isinstance(f, Finding)]
    texts = [_SPACE.sub(" ", str(t or "")) for t in texts]
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
    folder, named after the request, so they go wherever the file goes. None
    for anything that is not a request's whole-number id."""
    if isinstance(request_id, bool):
        return None
    try:
        rid = int(request_id)
    except (TypeError, ValueError):
        return None
    if str(rid) != str(request_id).strip():
        return None
    from app.config import settings

    return os.path.join(settings.UPLOADS_DIR, "exports", f"{rid}-law-{_slug(where)}.json")


def save(request_id: object, where: str, findings: Iterable[Finding], *,
         built_at: datetime | None = None, data_at: datetime | None = None,
         stamped: str | None = None, absent: bool = False) -> bool:
    """Keep a document's findings, replacing what an earlier check kept.
    `built_at` is when the build started (naive UTC). `data_at` is the request's
    `updated_at` the build read: the version of the row it checked. A record
    without it is never trusted, because a clock cannot say whether a check
    that started in the same instant as a change came before or after it.
    `stamped` is the release
    status the built file carries on its cover (None when no file was made: a
    law-only pass). `absent` records that the package has no such document yet
    (its stage has not produced it). Never raises; False when nothing could be
    kept. Each save writes its own temporary file, so two builds of the same
    document cannot write into each other's."""
    path = findings_path(request_id, where)
    if path is None:
        return False
    record = {"where": where, "built_at": (built_at or datetime.utcnow()).isoformat(),
              "data_at": data_at.isoformat() if isinstance(data_at, datetime) else None,
              "law_version": LAW_VERSION, "stamped": stamped if isinstance(stamped, str) else None, "absent": bool(absent),
              "findings": [] if absent else [as_json(f) for f in sorted_findings(findings)]}
    body = json.dumps(record)
    folder = os.path.dirname(path)
    try:
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=folder)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
    except OSError as exc:
        logger.warning("could not keep the law's findings for %s (%s)", where, type(exc).__name__)
        return False
    # Windows refuses a replace while another process (a virus scanner reading
    # the file just written) holds either file open: wait for it briefly.
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(tmp, path)
            return True
        except OSError:
            time.sleep(_REPLACE_WAIT * (attempt + 1))
    try:
        os.remove(tmp)
    except OSError:
        pass
    logger.warning("could not keep the law's findings for %s (the file stayed locked)", where)
    return False


def record(request_id: object, where: str, updated_at: datetime | None) -> dict | None:
    """A document's kept record (`findings` as `Finding`s, `stamped`, `absent`),
    when its check read the row as it stands (`data_at` equals `updated_at`) and
    was made under these rules (`LAW_VERSION`); None when it was never checked
    since, was checked under other rules, or the record cannot be read. The
    row's version, not the clock, decides: a check that started in the same
    instant as the last change is current. An `absent` record is checked against
    the row by `_records`."""
    path = findings_path(request_id, where)
    if path is None or not isinstance(updated_at, datetime) or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        data_at = datetime.fromisoformat(str(raw.get("data_at")))
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    if data_at.tzinfo is not None or data_at != updated_at:
        return None
    if raw.get("law_version") != LAW_VERSION:
        return None
    items = raw.get("findings") if isinstance(raw.get("findings"), list) else []
    stamped = raw.get("stamped")
    return {"findings": [f for f in (from_json(d) for d in items) if f is not None],
            "stamped": stamped if isinstance(stamped, str) else None,
            "absent": raw.get("absent") is True}


def fresh(request_id: object, where: str, updated_at: datetime | None) -> bool:
    """Whether the document has a record from a check of the row as it stands
    (an empty list counts: it was checked)."""
    return record(request_id, where, updated_at) is not None


def can_record(req) -> bool:
    """Whether the request can hold a fresh record at all: a whole-number id and
    the time of its last data change. Anything else (a row made up in memory)
    can never be checked, so nothing about the law is said of it."""
    return (findings_path(getattr(req, "id", None), "x") is not None
            and isinstance(getattr(req, "updated_at", None), datetime))


def _trusted(rec: dict | None, req, buildable) -> dict | None:
    """A record, unless it says the package has no such document while the row
    shows one can be built: "absent" means the stage produced nothing, and the
    row, not the file, is what says so."""
    if rec is None or not rec["absent"] or buildable is None:
        return rec
    try:
        return None if buildable(req) else rec
    except Exception:
        return None


def _records(req) -> dict[str, dict | None]:
    request_id = getattr(req, "id", None)
    updated_at = getattr(req, "updated_at", None)
    try:
        buildable = {where: can for where, _, can in _checkers()}
    except Exception:
        buildable = {}
    out = {where: _trusted(record(request_id, where, updated_at), req, buildable.get(where))
           for where, _ in DOCUMENTS}
    s = _ACTIVE.get()
    if s is not None and request_id is not None and s.request_id == request_id:
        out[s.where] = {"findings": list(s.pending if s.pending is not None else s._found),
                        "stamped": None, "absent": False}
    return out


def recorded(req) -> dict[str, list[Finding] | None]:
    """Each document's findings as the release gate should read them: the kept
    findings of its latest check when that check is newer than the request's
    last data change ([] for a document the package does not have), None when it
    has not been checked since. While a document of this request is being
    built, what its earlier pass found stands in for it."""
    return {where: (None if r is None else r["findings"]) for where, r in _records(req).items()}


def states(req) -> dict[str, str]:
    """Each document's state in the team's words: "checked", "N number(s)
    nobody owns", "not produced" (the package has none yet) or "not yet
    checked" (nothing has read it since the last data change)."""
    out = {}
    for where, r in _records(req).items():
        if r is None:
            out[where] = "not yet checked"
        elif r["absent"]:
            out[where] = "not produced"
        elif not r["findings"]:
            out[where] = "checked"
        else:
            n = len(r["findings"])
            out[where] = f"{n} number{'s' if n != 1 else ''} nobody owns"
    return out


def _checkers():
    """The law-only pass of each document, by the module that draws it."""
    from app.pipeline import export_pdf, export_pptx
    from app.screens import export as screens_export
    from app.storyline import roadmap

    return (("Volume I", lambda r: export_pdf.check_volume(r, "blueprint"),
             lambda r: export_pdf.volume_ready(r, "blueprint")),
            ("Volume II", lambda r: export_pdf.check_volume(r, "technical"),
             lambda r: export_pdf.volume_ready(r, "technical")),
            ("Volume III", lambda r: export_pdf.check_volume(r, "operations"),
             lambda r: export_pdf.volume_ready(r, "operations")),
            ("The roadmap", roadmap.check_roadmap, roadmap.roadmap_ready),
            ("Volume IV", screens_export.check_proposal, screens_export.proposal_ready),
            ("The deck", export_pptx.check_deck, lambda r: export_pptx.deck_inputs(r) is not None))


def ensure_records(req) -> dict[str, list[Finding] | None]:
    """Make sure every document of the package has a record newer than the
    request's last data change, running each missing one's law-only pass (its
    content through the law, no file printed), so the package's release status
    is whole before any cover is stamped. Returns `recorded(req)`. A request
    with no id or no `updated_at` cannot hold a fresh record and is left as it
    is. Never raises: a pass that fails leaves its document unchecked."""
    request_id = getattr(req, "id", None)
    updated_at = getattr(req, "updated_at", None)
    if findings_path(request_id, "x") is None or not isinstance(updated_at, datetime):
        return recorded(req)
    try:
        checkers = _checkers()
    except Exception:
        logger.warning("the release law's checkers could not be loaded", exc_info=True)
        return recorded(req)
    for where, check_document, buildable in checkers:
        if _trusted(record(request_id, where, updated_at), req, buildable) is not None:
            continue
        try:
            check_document(req)
        except Exception:
            logger.warning("the release law could not check %s", where, exc_info=True)
    return recorded(req)


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
