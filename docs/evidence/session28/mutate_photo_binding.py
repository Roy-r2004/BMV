#!/usr/bin/env python3
"""Mutation sweep for the catalogue photo binding (session 28)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TARGETS = {
    "bind": Path("/repo/backend/app/application/preview_app/catalogue_contract/photo_binding.py"),
    "imgs": Path("/repo/backend/app/application/services/industry_images.py"),
}
TESTS = [
    "tests/preview_app/test_catalogue_photo_binding.py",
    "tests/preview_app/test_request_40_defects.py",
]

MUTATIONS: list[tuple[str, str, str, str]] = [
    ("bind", "p1 titles read in reverse order",
     "        if len(deduped) > len(best):", "        if len(deduped) >= len(best):"),
    ("bind", "p2 consecutive title/name duplicates counted as two items",
     "            if not deduped or deduped[-1] != title:", "            if True:"),
    ("bind", "p3 lazy array scan instead of bracket counting",
     "            if depth == 0:\n                return source[open_index : i + 1]",
     "            if depth >= 0:\n                return source[open_index : i + 1]"),
    ("bind", "p4 word overlap ignored — every photo scores the same",
     "    score = 2 * len(title_tokens & alt_tokens)", "    score = 2"),
    ("bind", "p5 stopwords not removed, so 'the' counts as a match",
     "    return {w.lower() for w in _WORD_RE.findall(text or \"\")} - _STOPWORDS",
     "    return {w.lower() for w in _WORD_RE.findall(text or \"\")}"),
    ("bind", "p6 greedy left-to-right instead of best-pair-first",
     "    pairs.sort()", "    pairs.sort(key=lambda p: (p[2], p[0]))"),
    ("bind", "p7 a photo may be reused by two items",
     "        if t_index in taken_titles or c_index in taken_photos:",
     "        if t_index in taken_titles:"),
    ("bind", "p8 an unmatched item is left with no picture",
     "    spare = (url for i, (url, _alt) in enumerate(usable) if i not in taken_photos)",
     "    spare = iter(())"),
    ("bind", "p9 a repeating binding is accepted",
     "        if len(set(bound.values())) != len(bound):\n            return {}",
     "        if False:\n            return {}"),
    ("bind", "p10 more titles than slots overruns the slot tuple",
     "    for t_index, title in enumerate(titles[: len(slots)]):",
     "    for t_index, title in enumerate(titles):"),
    ("imgs", "p11 the item pool is back to a search page's worth",
     "_ITEM_SLOT_COUNT = 24", "_ITEM_SLOT_COUNT = 8"),
    ("imgs", "p12 the search asks for exactly the pool size",
     "_ITEM_POOL_PER_PAGE = 40", "_ITEM_POOL_PER_PAGE = 8"),
]


def run_tests() -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *TESTS, "-q", "-x", "--no-header"],
        cwd="/repo/backend", capture_output=True, text=True,
    )
    return proc.returncode == 0


def main() -> None:
    originals = {k: p.read_text(encoding="utf-8") for k, p in TARGETS.items()}
    if not run_tests():
        print("baseline is RED")
        raise SystemExit(2)
    print(f"baseline green; {len(MUTATIONS)} mutations\n")

    survivors = []
    try:
        for key, label, old, new in MUTATIONS:
            path, original = TARGETS[key], originals[key]
            if old not in original:
                print(f"  SKIP  {label} — anchor not found")
                survivors.append(f"{label} (anchor missing)")
                continue
            path.write_text(original.replace(old, new, 1), encoding="utf-8")
            killed = not run_tests()
            print(f"  {'kill' if killed else 'SURVIVED'}  {label}")
            if not killed:
                survivors.append(label)
            path.write_text(original, encoding="utf-8")
    finally:
        for k, p in TARGETS.items():
            p.write_text(originals[k], encoding="utf-8")

    print(f"\n{len(MUTATIONS) - len(survivors)} killed / {len(survivors)} survived")
    for s in survivors:
        print(f"  survivor: {s}")
    raise SystemExit(1 if survivors else 0)


if __name__ == "__main__":
    main()
