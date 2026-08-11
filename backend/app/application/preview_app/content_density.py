"""Spec-level content density, stored beside `fallback_pages` (Phase 0's 0.8).

Why this exists: `fallback_pages` rides scaffold bookkeeping whose literal
marker the 0.2 census proved survives slot-fill wholesale — 275 of 631
archived pages carry the marker while finalize's own acceptability predicate
disagrees on 195 of them — and after the Phase 2 flip a marker-derived count
reads 0 forever or 12 forever, both silently. This measurement reads the
shipped page sources instead: characters of human-readable copy per routed
page.

The prose predicate is the archived DoD-2 baseline's
(`scripts/measure/content_census.py`), ported verbatim and pinned against the
script by test so the two cannot drift apart silently. The census stays a
script over the archive; this module is the same ruler held against live runs.

Measurement only. It is stored in the preview record and logged; nothing reads
it to make a decision, and `measure` never raises — a failed measurement is
recorded as `status: unmeasured` with the reason, because a metric that can
silently vanish is the defect class (`visual_review_status: None`) this repo
keeps re-finding.
"""
from __future__ import annotations

import re
import statistics
from typing import Any

from app.application.preview_app.workspace import read_file

#: A JSX text node: the run of text between a closing `>` and the next `<`.
_JSX_TEXT = re.compile(r">([^<>{}]+)<")
#: Single, double and template literals, non-greedy, escapes tolerated.
_STRING = re.compile(r"""(['"])((?:\\.|(?!\1)[^\\\n])*)\1|`((?:\\.|[^\\`])*)`""", re.S)
_CLASSNAME = re.compile(r"""class(?:Name)?\s*=\s*(['"`])""")
_IMPORT_LINE = re.compile(r"^\s*(?:import|export)\b.*\bfrom\b", re.M)

#: A page below this many prose characters is listed by name in the record.
#: The threshold is DoD 2's target, not a judgment made here.
THIN_PAGE_CHARS = 200


def _looks_like_a_class_list(text: str) -> bool:
    """Tailwind, not prose — at least half the tokens carry a `-` or `:` and
    every token is drawn from a charset with no capitals in it. The **half**
    is load-bearing (see the census's docstring for the sweep that found it)."""
    tokens = text.split()
    if not tokens:
        return False
    utility = sum(1 for t in tokens if "-" in t or ":" in t)
    if utility * 2 < len(tokens):
        return False
    return all(re.fullmatch(r"[a-z0-9:\[\]/.\-%#()!*+_,]+", t) for t in tokens)


def _is_prose(text: str) -> bool:
    text = text.strip()
    if len(text) < 4:
        return False
    if text.startswith(("/", "#", "http", "./", "../", "data:")):
        return False
    if _looks_like_a_class_list(text):
        return False
    words = [w for w in re.split(r"\s+", text) if len(re.sub(r"[^A-Za-z]", "", w)) >= 2]
    return len(words) >= 2


def prose_chars(source: str) -> int:
    """Characters of human-readable copy baked into a TSX file."""
    total = 0
    body = _IMPORT_LINE.sub("", source)
    classname_spans: list[tuple[int, int]] = []
    for m in _CLASSNAME.finditer(body):
        quote = m.group(1)
        end = body.find(quote, m.end())
        if end != -1:
            classname_spans.append((m.end(), end))

    def _inside_classname(pos: int) -> bool:
        return any(start <= pos < end for start, end in classname_spans)

    for m in _STRING.finditer(body):
        text = m.group(2) if m.group(2) is not None else (m.group(3) or "")
        if _inside_classname(m.start(2 if m.group(2) is not None else 3)):
            continue
        if _is_prose(text):
            total += len(text.strip())
    for m in _JSX_TEXT.finditer(body):
        text = m.group(1)
        if _is_prose(text):
            total += len(text.strip())
    return total


def measure_content_density(workspace, routes: list[dict] | None) -> dict[str, Any]:
    """Density over every routed page file, deduplicated on component_file.

    Routed files only, deliberately: the unrouted-page classes (request 33's
    orphans, template seeds) are DoD 7's numbers, and mixing them in here
    would move this metric when a route table changes rather than when
    content does.
    """
    per_page: dict[str, int] = {}
    for route in routes or []:
        component_file = (route.get("component_file") or "").replace("\\", "/")
        if not component_file or component_file in per_page:
            continue
        source = read_file(workspace, component_file)
        if not source:
            continue
        per_page[component_file] = prose_chars(source)
    counts = sorted(per_page.values())
    return {
        "status": "measured",
        "pages_measured": len(per_page),
        "prose_chars_total": sum(counts),
        "prose_chars_median": statistics.median(counts) if counts else 0,
        "pages_under_200_chars": sorted(
            f for f, c in per_page.items() if c < THIN_PAGE_CHARS
        ),
        "per_page": per_page,
    }


def density_record(workspace, routes: list[dict] | None) -> dict[str, Any]:
    """`measure_content_density`, but a failure is a recorded fact, not a raise."""
    try:
        return measure_content_density(workspace, routes)
    except Exception as exc:  # noqa: BLE001 — measurement must never fail a ship
        return {"status": "unmeasured", "reason": f"{type(exc).__name__}: {exc}"[:200]}
