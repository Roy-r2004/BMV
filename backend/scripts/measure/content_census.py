#!/usr/bin/env python3
"""Phase 2 DoD 2 and DoD 5, measured: the "before" numbers.

Two rows in the Phase 2 DoD carry a parenthesised baseline and neither had a
recorded derivation:

  DoD 2  "Inline prose in page TSX <= 200 chars (wrappers only; today 13,540)."
  DoD 5  "`SiteSpec` key-set identical across 5 runs of 5 industries
          (today: 1 key common to 27 workspaces)."

Both were written from a six-part audit whose method was not archived, so
neither figure can be reproduced — only re-taken. This is the re-take, with the
method stated, over the 58 workspaces in
`docs/evidence/preview-workspaces.tar.gz`.

    python3 backend/scripts/measure/content_census.py --workspaces DIR

**DoD 2's judgment call, stated rather than buried.** "Inline prose" has no
mechanical definition, and the number moves a lot depending on where the line is
drawn. Counted here: JSX text nodes, and string literals that read as prose.
Excluded: `className` values, import specifiers, URLs and paths, and anything
with no interior space. The script prints the count both with and without the
`className` exclusion so a reader can see how much of the total rests on that one
decision.

**DoD 5 has no `SiteSpec` to measure** — it is the artifact Phase 2 creates. The
closest thing that exists is `src/data/mock.ts`, the data module every workspace
emits, so the census is over its exported key set. That substitution is the
reason to read this number as a baseline for a *shape*, not as the DoD row.

Read-only.
"""
from __future__ import annotations

import argparse
import re
import statistics
from collections import Counter
from pathlib import Path

#: A JSX text node: the run of text between a closing `>` and the next `<`.
_JSX_TEXT = re.compile(r">([^<>{}]+)<")
#: Single, double and template literals, non-greedy, escapes tolerated.
_STRING = re.compile(r"""(['"])((?:\\.|(?!\1)[^\\\n])*)\1|`((?:\\.|[^\\`])*)`""", re.S)
_CLASSNAME = re.compile(r"""class(?:Name)?\s*=\s*(['"`])""")
_IMPORT_LINE = re.compile(r"^\s*(?:import|export)\b.*\bfrom\b", re.M)


def _looks_like_a_class_list(text: str) -> bool:
    """Tailwind, not prose.

    `flex items-center gap-4 md:grid-cols-2` and "a calm, premium feel." are both
    space-separated lowercase words. What separates them is density: at least half
    the tokens in a utility list carry a `-` or a `:`, and every token is drawn
    from a charset with no capitals in it.

    The **half** in the ratio is load-bearing and the mutation sweep is what found
    it. Requiring only *one* hyphenated token classified `self-catering apartments
    available` as Tailwind and dropped it from the count — real lowercase
    hyphenated prose, silently uncounted.

    There is deliberately no separate capitalization test. One was written, and the
    sweep showed it could not change an outcome: the charset check below already
    rejects every token with a capital in it. A guard that cannot fail is the thing
    this file exists to avoid becoming.
    """
    tokens = text.split()
    if not tokens:
        return False
    utility = sum(1 for t in tokens if "-" in t or ":" in t)
    if utility * 2 < len(tokens):
        return False
    return all(re.fullmatch(r"[a-z0-9:\[\]/.\-%#()!*+_,]+", t) for t in tokens)


def _is_prose(text: str) -> bool:
    text = text.strip()
    # No `" " not in text` guard: the two-word rule below already implies it, and a
    # condition that cannot change an outcome is the shape of guard this repo keeps
    # discovering was never doing anything.
    if len(text) < 4:
        return False
    if text.startswith(("/", "#", "http", "./", "../", "data:")):
        return False
    if _looks_like_a_class_list(text):
        return False
    words = [w for w in re.split(r"\s+", text) if len(re.sub(r"[^A-Za-z]", "", w)) >= 2]
    return len(words) >= 2


def prose_chars(source: str, drop_classnames: bool = True) -> int:
    """Characters of human-readable copy baked into a TSX file."""
    total = 0
    body = _IMPORT_LINE.sub("", source)
    classname_spans: list[tuple[int, int]] = []
    if drop_classnames:
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


def mock_export_keys(source: str) -> set[str]:
    return {m.group(1) for m in re.finditer(r"^export const (\w+)", source, re.M)}


def seed_keys(source: str) -> set[str]:
    """Depth-1 keys of `export const seed = { … }`, brace-walked, strings skipped."""
    m = re.search(r"^export const seed = \{", source, re.M)
    if not m:
        return set()
    start = m.end() - 1
    depth = 0
    keys: set[str] = set()
    quote: str | None = None
    i = start
    while i < len(source):
        c = source[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "\"'`":
            quote = c
            i += 1
            continue
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
            if depth == 0:
                break
        elif depth == 1 and c == ":":
            k = re.search(r'([A-Za-z_$][\w$]*|"[^"]+")\s*$', source[start:i])
            if k:
                keys.add(k.group(1).strip('"'))
        i += 1
    return keys


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspaces", default="/app/data/preview-apps")
    args = ap.parse_args()
    root = Path(args.workspaces)
    runs = sorted(
        (d for d in root.iterdir() if d.is_dir() and d.name.isdigit()),
        key=lambda d: int(d.name),
    )

    # ---- DoD 2 -----------------------------------------------------------
    per_file: list[tuple[int, str]] = []
    per_run: list[tuple[str, int, int]] = []
    kept_classnames = 0
    for ws in runs:
        pages = sorted((ws / "src" / "pages").rglob("*.tsx"))
        if not pages:
            continue
        run_total = 0
        for page in pages:
            src = page.read_text(errors="replace")
            n = prose_chars(src)
            kept_classnames += prose_chars(src, drop_classnames=False) - n
            per_file.append((n, f"{ws.name}/{page.relative_to(ws).as_posix()}"))
            run_total += n
        per_run.append((ws.name, len(pages), run_total))

    counts = sorted(n for n, _p in per_file)
    print("DoD 2 — inline prose in page TSX (target: <= 200 chars per page)")
    print(f"  page files                : {len(counts)} across {len(per_run)} workspaces")
    print(f"  chars per page  mean      : {statistics.mean(counts):,.0f}")
    print(f"                  median    : {statistics.median(counts):,.0f}")
    print(f"                  p90 / max : {counts[int(len(counts) * 0.9)]:,} / {counts[-1]:,}")
    print(f"  pages already <= 200      : {sum(1 for n in counts if n <= 200)} "
          f"({sum(1 for n in counts if n <= 200) / len(counts):.0%})")
    print(f"  chars per workspace  mean : {statistics.mean(t for _r, _n, t in per_run):,.0f}")
    print(f"  corpus total              : {sum(counts):,}")
    print(f"  [sensitivity] counting className values too would add {kept_classnames:,}")
    print("  biggest single pages:")
    for n, path in sorted(per_file, reverse=True)[:5]:
        print(f"    {n:>7,}  {path}")

    # ---- DoD 5 -----------------------------------------------------------
    exports: dict[str, set[str]] = {}
    seeds: dict[str, set[str]] = {}
    for ws in runs:
        mock = ws / "src" / "data" / "mock.ts"
        if not mock.is_file():
            continue
        src = mock.read_text(errors="replace")
        exports[ws.name] = mock_export_keys(src)
        seeds[ws.name] = seed_keys(src)

    def _report(label: str, sets: dict[str, set[str]]) -> None:
        present = {k: v for k, v in sets.items() if v}
        if not present:
            print(f"  {label}: nothing to measure")
            return
        common = set.intersection(*present.values())
        union: Counter = Counter()
        for v in present.values():
            union.update(v)
        sizes = sorted(len(v) for v in present.values())
        print(f"  {label}")
        print(f"    workspaces                 : {len(present)}")
        print(f"    keys common to all         : {len(common)} {sorted(common)}")
        print(f"    distinct keys in the corpus: {len(union)}")
        print(f"    keys per workspace min/med/max: {sizes[0]} / "
              f"{statistics.median(sizes):.0f} / {sizes[-1]}")
        print(f"    keys in >= 90% of workspaces : "
              f"{sum(1 for _k, c in union.items() if c >= 0.9 * len(present))}")

    print()
    print("DoD 5 — data-module key set (target: identical across runs)")
    print("  no `SiteSpec` exists yet; `src/data/mock.ts` is the closest artifact")
    _report("top-level exports", exports)
    _report("`seed` keys", seeds)


if __name__ == "__main__":
    main()
