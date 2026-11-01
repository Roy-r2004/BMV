"""The number audit: every number in a request's package that nobody owns.

    python -m app.figures.audit <request public id> [--json]

For the owner's LOCAL testing. It reads one request through the app's own
database session and says, for each document of the package (Volume I, II and
III, the proposal as Volume IV, and the deck), every number the release law
found that matches none of the client's figures, our workings, our estimates or
a cited reference: the document, the page (or "page not located"), the number,
the words around it as the page prints them, and the plain reason. Then one line
per document ("Volume I: 2 numbers nobody owns"), the package's status ("final",
"draft", or "draft because of the number law"), and how many figures the request
knows, by kind (yours, worked out, our estimate, reference).

It is read-only. It never commits and never writes the request row (the session
is rolled back and closed, and a test pins that no column changes). The one thing
it can write is what the app's own mechanism writes: `law.ensure_records` runs
the law-only pass of every document that has no record newer than the request's
last data change, and saves that document's findings file under
`<uploads>/exports/<id>-law-<document>.json`. Those findings files are the only
files it can create, and only through `law.ensure_records`. Nothing is printed
to a PDF or a deck. A volume whose findings come from that pass has no page yet
(page not located); the volume a person has downloaded since the last change has
its findings placed on the pages that were printed, and the audit reads those.

Exit code: 0 when no document has a finding, 1 when any has (or when a document
could not be checked: a package that was not checked is not a clean one), 2 when
the audit could not run (no id given, no such request, the database cannot be
read). A request that does not exist prints a plain message and exits 2. A build
that fails never prints its error: the audit says "could not check <document>"
and goes on with the others.

`--json` prints the same report as one JSON document.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from contextlib import contextmanager
from typing import Sequence

#: Why a number is a finding. The same words the release gate uses for a page
#: (`export_pdf.release_status`).
REASON = "matches none of the client's figures, our workings, our estimates or a cited reference"

#: The longest snippet shown in the table, in characters.
SNIPPET_MAX = 72

#: The most other reasons for a draft the report lists.
OTHER_REASONS_MAX = 10

#: The exit codes.
CLEAN, FOUND, NOT_RUN = 0, 1, 2


# -- finding the request ---------------------------------------------------------------------

def _find(db, ref: str):
    """The request by public id, or by its whole-number id (as the app's
    `_load_request` reads a reference); None when there is none."""
    from app.models import Request

    ref = ref.strip()
    if ref.isdigit():
        return db.get(Request, int(ref))
    return db.query(Request).filter(Request.public_id == ref).first()


@contextmanager
def _quiet():
    """No log line (and so no exception text) reaches the terminal while the
    package is checked: a failed check is reported in the audit's own words."""
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous)


# -- the report -------------------------------------------------------------------------------

def _short(snippet: str, number: str, limit: int = SNIPPET_MAX) -> str:
    """The snippet cut to `limit` characters around its number, with "..." where
    it was cut."""
    snippet = " ".join(str(snippet or "").split())
    if len(snippet) <= limit:
        return snippet
    at = max(0, snippet.find(number))
    start = max(0, min(at - (limit - len(number)) // 2, len(snippet) - limit))
    end = start + limit
    return ("..." if start else "") + snippet[start:end].strip() + ("..." if end < len(snippet) else "")


def _plural(n: int) -> str:
    return f"{n} number{'s' if n != 1 else ''} nobody owns"


def _status_line(status: str | None, has_findings: bool) -> str:
    if status is None:
        return "could not be worked out"
    if status == "client_approved":
        return "final (approved by the client)"
    if status == "draft":
        return "draft because of the number law" if has_findings else "draft"
    return "final"


def build_report(req) -> dict:
    """The audit of one request as plain data: what `main` prints, or dumps as
    JSON. Runs the app's own law-only pass for any document with no fresh
    record (see the module docstring), nothing else that writes."""
    from app.figures import law
    from app.figures.model import tag_word
    from app.pipeline import export_pdf

    with _quiet():
        recorded = law.ensure_records(req)
        states = law.states(req)
        try:
            release = export_pdf.release_status(req)
        except Exception:
            release = None
        try:
            known, _ = export_pdf.document_known(req)
            counts = known.counts()
        except Exception:
            counts = None

    documents, total, unchecked = [], 0, 0
    for where, unit in law.DOCUMENTS:
        found = recorded.get(where)
        state = states.get(where, "not yet checked")
        checked = found is not None and state != "not yet checked"
        rows = []
        if checked:
            # by page, the pages that were located first; ties keep the order the law met them in
            ordered = sorted(enumerate(found), key=lambda p: (p[1].page is None, p[1].page or 0, p[0]))
            for _, f in ordered:
                part = f.region if f.region and f.region != where else None
                rows.append({
                    "page": f.page,
                    "place": f"{unit} {f.page}" if f.page is not None else f"{unit} not located",
                    "number": f.number,
                    "snippet": _short(f.snippet, f.number),
                    "reason": REASON + (f" (in the {part})" if part else ""),
                    "part": part,
                })
        else:
            unchecked += 1
        total += len(rows)
        documents.append({
            "document": where, "unit": unit, "checked": checked, "state": state if checked else "could not check",
            "summary": f"{where}: {state}" if checked else f"could not check {where}",
            "findings": rows,
        })

    reasons = list(release["reasons"]) if release else []
    pages = {f"{where}, {place}:" for where, place, _ in law.page_reasons(recorded)}
    others = [r for r in reasons if not any(r.startswith(p) for p in pages)]
    status = release["status"] if release else None
    return {
        "request": getattr(req, "public_id", None), "id": getattr(req, "id", None),
        "business": getattr(req, "business_name", None),
        "status": status, "status_line": _status_line(status, total > 0),
        "other_reasons": others,
        "documents": documents,
        "numbers_nobody_owns": total, "documents_not_checked": unchecked,
        "figures": ({tag_word(k): n for k, n in counts.items()} if counts is not None else None),
        "clean": total == 0 and unchecked == 0,
    }


def exit_code(report: dict) -> int:
    return CLEAN if report["clean"] else FOUND


# -- the words ---------------------------------------------------------------------------------

def _table(rows: list[tuple[str, ...]], head: tuple[str, ...]) -> list[str]:
    widths = [max(len(head[i]), *(len(r[i]) for r in rows)) for i in range(len(head))]
    line = lambda r: "  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip()   # noqa: E731
    return [line(head), "  ".join("-" * w for w in widths), *(line(r) for r in rows)]


def render_text(report: dict) -> str:
    out = [f"Number audit for {report['request'] or report['id']}"
           + (f" ({report['business']})" if report.get("business") else ""), ""]
    rows = [(d["document"], f["place"], f["number"], f["snippet"], f["reason"])
            for d in report["documents"] for f in d["findings"]]
    if rows:
        out += _table(rows, ("Document", "Page", "Number", "Snippet", "Reason")) + [""]
        if any("not located" in r[1] for r in rows):
            out += ["A page is not located until the document has been built (downloaded) since the last change.", ""]
    else:
        out += ["No number nobody owns was found.", ""]
    out += [d["summary"] for d in report["documents"]]
    out += ["", f"Package status: {report['status_line']}"]
    if report["other_reasons"]:
        shown = report["other_reasons"][:OTHER_REASONS_MAX]
        out += ["Other reasons it is a draft:"] + [f"  - {' '.join(r.split())[:240]}" for r in shown]
        if len(report["other_reasons"]) > len(shown):
            out.append(f"  - and {len(report['other_reasons']) - len(shown)} more")
    out.append("")
    if report["figures"] is None:
        out.append("Figures known for this request: could not be read")
    else:
        out.append("Figures known for this request")
        out += [f"  {tag}: {n}" for tag, n in report["figures"].items()]
    return "\n".join(out)


def _say(text: str, stream=None) -> None:
    """Print without ever failing on a terminal that cannot show a character."""
    stream = stream or sys.stdout
    try:
        stream.write(text + "\n")
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        stream.write(text.encode(encoding, "replace").decode(encoding) + "\n")
    try:
        stream.flush()
    except Exception:                                # pragma: no cover - a closed pipe
        pass


# -- the command --------------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m app.figures.audit",
        description="List every number in a request's package that nobody owns, by document and page.",
        epilog="Exit code 0: nothing found. 1: numbers found, or a document could not be checked. "
               "2: the audit could not run (no such request, bad usage).")
    p.add_argument("request", help="the request's public id (its whole-number id also works)")
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:                        # argparse: usage said, exit code 2 (0 for --help)
        return exc.code if isinstance(exc.code, int) else NOT_RUN
    ref = (args.request or "").strip()
    if not ref:
        _say("Give the request's public id.", sys.stderr)
        return NOT_RUN

    db = None
    try:
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            req = _find(db, ref)
        except Exception:
            _say("Could not read the database.", sys.stderr)
            return NOT_RUN
        if req is None:
            _say(f"No request with the id {ref!r} was found.", sys.stderr)
            return NOT_RUN
        try:
            report = build_report(req)
        except Exception:
            _say("The audit could not be completed.", sys.stderr)
            return NOT_RUN
    finally:
        if db is not None:
            try:
                db.rollback()                        # nothing the checks touched is kept
            finally:
                db.close()

    _say(json.dumps(report, indent=2) if args.json else render_text(report))
    return exit_code(report)


if __name__ == "__main__":                           # pragma: no cover
    sys.exit(main())
