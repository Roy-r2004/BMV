"""Their files, turned into figures a diagnosis may cite.

The rule this module exists to enforce: a number that came from a client's
file must be traceable to the cell it came from, and we must be able to CHECK
that. An extracted figure nobody verified is indistinguishable, downstream,
from one a model invented — and the whole diagnosis rests on the difference.

So the work is split. Parsing is deterministic: the file is read into rows and
cells by code, and a model never gets to say what is in the file. The model
only says which figures MATTER and what they mean, citing a cell; every
citation is then checked against the parsed grid, and a figure whose cited
cell does not hold it is dropped.

Claims come out in `registry._claim`'s shape, so a file-derived figure is the
same kind of object as a discovery answer and the integrity layer already
knows how to validate it.
"""

import csv
import io
import json
import logging
import os
import re

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import extract_json_from_text, log_usage
from app.templating import render

logger = logging.getLogger("consultant.evidence")

EXTRACT_TOKENS = 4000
#: Enough of a sheet for a model to see what the columns mean and how the
#: values move, without paying to read a year of rows. Files are usually an
#: export of everything; the shape is in the first screenful.
MAX_ROWS_SHOWN = 40
MAX_TABLES = 6
MAX_FILE_BYTES = 8 * 1024 * 1024

SUPPORTED = (".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".pdf")


class UnreadableFile(Exception):
    """The file could not be read as data. The client is told which and why."""


def _col_letter(i: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA. Spreadsheet addressing, because the client
    is going to open the file and look."""
    out = ""
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        out = chr(65 + rem) + out
    return out


def _grid_table(name: str, rows: list[list]) -> dict | None:
    """One table: a name, its rows, and every cell addressable as A1."""
    cleaned = [[("" if c is None else str(c)).strip() for c in row] for row in rows]
    cleaned = [r for r in cleaned if any(c for c in r)]
    if len(cleaned) < 2:
        return None
    return {"name": name, "rows": cleaned}


def read_tables(data: bytes, filename: str) -> list[dict]:
    """Deterministic parse. No model involved — this is what the file SAYS."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED:
        raise UnreadableFile(
            f"We can read spreadsheets (.xlsx), CSVs and PDFs. {ext or 'That file'} we cannot.")
    if len(data) > MAX_FILE_BYTES:
        raise UnreadableFile("That file is larger than 8MB. A summary export is usually enough.")

    if ext in (".csv", ".tsv", ".txt"):
        text = data.decode("utf-8-sig", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))
        table = _grid_table(os.path.basename(filename), rows)
        return [table] if table else []

    if ext in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        tables = []
        for sheet in wb.worksheets[:MAX_TABLES]:
            table = _grid_table(sheet.title, [list(r) for r in sheet.iter_rows(values_only=True)])
            if table:
                tables.append(table)
        wb.close()
        return tables

    import pymupdf

    doc = pymupdf.open(stream=data, filetype="pdf")
    tables = []
    try:
        for page in doc:
            for found in page.find_tables().tables[:MAX_TABLES]:
                table = _grid_table(f"page {page.number + 1}", found.extract())
                if table:
                    tables.append(table)
            if len(tables) >= MAX_TABLES:
                break
        if not tables:
            # No ruled table on any page. The text still carries figures — a
            # one-page P&L is often prose — so it goes through as a single
            # column, and cell verification still anchors every citation.
            lines = [[ln.strip()] for page in doc for ln in page.get_text().splitlines()
                     if ln.strip()]
            table = _grid_table(os.path.basename(filename), lines)
            if table:
                tables.append(table)
    finally:
        doc.close()
    return tables[:MAX_TABLES]


def _render_table(table: dict) -> str:
    """The grid as the model sees it, every cell carrying its own address.

    The name is quoted rather than following a bare `TABLE:` label. With the
    label, models returned "TABLE: Bookings by month" as the name — correctly,
    since the prompt asked for the name "exactly as printed" and that is what
    was printed. Every citation was right and every one was thrown away.
    """
    lines = [f'TABLE "{table["name"]}"']
    for r, row in enumerate(table["rows"][:MAX_ROWS_SHOWN], start=1):
        cells = " | ".join(f"{_col_letter(c)}{r}={v}" for c, v in enumerate(row) if v)
        if cells:
            lines.append(cells)
    if len(table["rows"]) > MAX_ROWS_SHOWN:
        lines.append(f"...and {len(table['rows']) - MAX_ROWS_SHOWN} more rows not shown")
    return "\n".join(lines)


_NUM = re.compile(r"-?[\d,]*\.?\d+")


def _cell_value(table: dict, ref: str) -> str | None:
    m = re.fullmatch(r"([A-Z]+)(\d+)", (ref or "").strip().upper())
    if not m:
        return None
    col, row = m.group(1), int(m.group(2)) - 1
    idx = 0
    for ch in col:
        idx = idx * 26 + (ord(ch) - 64)
    idx -= 1
    if row < 0 or row >= len(table["rows"]):
        return None
    cells = table["rows"][row]
    return cells[idx] if 0 <= idx < len(cells) else None


def _holds(cell: str | None, value) -> bool:
    """Does this cell actually carry that number?

    Compared as numbers, not as strings: a cell reading "$1,240.00" holds
    1240, and rejecting it for punctuation would throw away good evidence.
    """
    if cell is None:
        return False
    try:
        wanted = float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return False
    for found in _NUM.findall(cell.replace(",", "")):
        try:
            if abs(float(found) - wanted) < 0.01:
                return True
        except ValueError:
            continue
    return False


def _normalise(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^table\s*:?\s*", "", name.strip().strip('"\''),
                                      flags=re.I)).casefold()


def _resolve_table(tables: list[dict], name: str, ref: str, value) -> dict | None:
    """Which sheet a citation meant.

    Loose on the NAME and strict on the CELL, which is the right way round: a
    sheet title is a label a model can reasonably echo back with a prefix or
    different casing, while the cell is the thing being verified. When the
    name resolves to nothing, the cell is looked for across the sheets — and
    only an unambiguous single hit counts, because a value that sits at the
    same address in two sheets does not identify either.
    """
    exact = {t["name"]: t for t in tables}
    if name in exact:
        return exact[name]
    wanted = _normalise(name)
    loose = [t for t in tables if _normalise(t["name"]) == wanted]
    if len(loose) == 1:
        return loose[0]
    if len(tables) == 1:
        return tables[0]
    hits = [t for t in tables if _holds(_cell_value(t, ref), value)]
    return hits[0] if len(hits) == 1 else None


def extract(db: Session, request_id: int, tables: list[dict], filename: str,
            start_index: int = 0) -> tuple[list[dict], int]:
    """Figures worth citing, each verified against the cell it claims.

    Returns the claims and how many the model offered that did NOT survive
    verification — that count is logged, because a model that starts inventing
    cell references is a thing we need to see rather than silently absorb.
    """
    if not tables:
        return [], 0
    try:
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": render(
            "extract_evidence.j2", filename=filename,
            tables="\n\n".join(_render_table(t) for t in tables),
        )}], max_tokens=EXTRACT_TOKENS)
        raw = extract_json_from_text(body["choices"][0]["message"]["content"])
        log_usage(db, request_id, provider="openrouter", model=settings.ANALYSIS_MODEL,
                  purpose="extract_evidence", usage=body.get("usage"), success=True)
    except Exception as exc:
        log_usage(db, request_id, provider="openrouter", model=settings.ANALYSIS_MODEL,
                  purpose="extract_evidence", success=False, error=str(exc)[:500])
        logger.warning("could not read figures out of %s: %s", filename, str(exc)[:200])
        return [], 0

    claims, rejected = [], 0
    for item in (raw.get("figures") or []):
        if not isinstance(item, dict):
            continue
        ref = str(item.get("cell") or "")
        value = item.get("value")
        table = _resolve_table(tables, str(item.get("table") or ""), ref, value)
        if table is None or not _holds(_cell_value(table, ref), value):
            # The citation does not check out. Dropped rather than kept with a
            # caveat: a figure in the evidence list is one a hypothesis may
            # rest on, and "probably in their file somewhere" is not evidence.
            rejected += 1
            continue
        n = start_index + len(claims) + 1
        claims.append({
            "id": f"CE-{n:02d}",
            "type": "client_fact",
            "value": value,
            "unit": str(item.get("unit") or "")[:40],
            "time_basis": str(item.get("time_basis") or "n/a")[:20],
            "population": "n/a", "scope": "engagement", "phase": "all",
            # `client_input`, not a provenance of our own. The registry
            # validates every claim against a closed set of four provenance
            # values and reports anything else as an error, so a distinct
            # "client_file" would have failed validation the moment these
            # reached the build. A figure read from their file IS client
            # input; where it came from is carried by `origin` and `source`.
            "provenance": "client_input",
            "approval_status": "client_stated",
            "source": f"{filename} · {table['name']} · {ref.upper()}",
            "allowed_sections": ["*"],
            "text": str(item.get("means") or "")[:200],
            "origin": "file",
            "cell": ref.upper(),
            "file": filename,
        })
    if rejected:
        logger.warning("%s: dropped %d figure(s) whose cited cell did not hold them",
                       filename, rejected)
    return claims, rejected


def load(req: Request) -> list[dict]:
    try:
        return json.loads(req.evidence_json) if req.evidence_json else []
    except (TypeError, ValueError):
        return []


def pending_dir(request_id: int) -> str:
    # NOT under UPLOADS_DIR: that folder is served publicly at /uploads, and a
    # client's booking export must never be one guessed URL away. The wait is
    # seconds — the diagnosis reads these first — so a temp folder is enough.
    import tempfile

    return os.path.join(tempfile.gettempdir(), "bmv_pending_evidence", str(request_id))


def stash(request_id: int, name: str, data: bytes) -> None:
    """Keep a file sent WITH the engagement until the run reads it.

    The conversation offers "drop your booking export in" before any
    engagement exists, and reading a file is a model call — too slow to make
    the launch wait on. So the bytes wait on disk and the diagnosis half reads
    them first, before it forms a single explanation.
    """
    folder = pending_dir(request_id)
    os.makedirs(folder, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in os.path.basename(name))[:120] or "upload"
    with open(os.path.join(folder, safe), "wb") as fh:
        fh.write(data)


def ingest_pending(db: Session, request_id: int) -> list[tuple[str, int]]:
    """Read every stashed file into verified figures. Returns (name, figures
    added) per file. Each file is removed once read — whether or not it held
    anything — so a re-diagnosis never reads the same file twice."""
    folder = pending_dir(request_id)
    if not os.path.isdir(folder):
        return []
    done = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        try:
            with open(path, "rb") as fh:
                data = fh.read()
            tables = read_tables(data, name)
            req = db.get(Request, request_id)
            existing = load(req)
            found, _ = extract(db, request_id, tables, name, start_index=len(existing))
            if found:
                save(db, req, existing + found)
            done.append((name, len(found)))
        except Exception as exc:
            logger.warning("could not read stashed file %s: %s", name, str(exc)[:200])
            done.append((name, 0))
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
    try:
        os.rmdir(folder)
    except OSError:
        pass
    return done


def save(db: Session, req: Request, claims: list[dict]) -> None:
    req.evidence_json = json.dumps(claims) if claims else None
    db.commit()
