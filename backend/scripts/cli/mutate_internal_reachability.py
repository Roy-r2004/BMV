"""Mutation-test the session-15 reachability rulings (fix A and fix B).

    cd backend && python scripts/cli/mutate_internal_reachability.py

Reverts each part of the two fixes in turn, runs the suite that pins them, and
restores from an **in-memory** backup — never `git checkout`.

Fix A: a brief that ASSERTS it is internal-facing (staff-only, not a public
website, no customer ever) and carries ops/transactional language resolves
`internal_ops` — but only when it names no software product (`saas == 0`),
because "an internal tool our studio uses" is still a workspace. Fix B:
`lesson`/`instructor` are booking hints, so a driving school stops taking the
storefront default. Wrap-measured: exactly the four intended synthetic briefs
change (20/20 exact after), 0 of the 47 stored kind_contexts move
(docs/evidence/reachability-session15.json).

The mutation surface is the rule's three guards — each one removed must be
caught by a different fixture, or the guard is decoration:

  - the whole rule gone            -> the staff desks fall back to workspace
  - `saas == 0` gone               -> SB-11 (internal software tool) flips
  - the ops-language conjunct gone -> a bare "staff tool" note-taker flips
  - the new hints gone             -> back office / lessons stop counting

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

PRODUCT_KIND = BACKEND / "app/application/preview_app/product_kind.py"

SUITES = "tests/preview_app/test_product_kind.py"

RULE = """    if (
        saas == 0
        and _hits(text, _INTERNAL_FACING_HINTS) >= 1
        and (internal >= 1 or any(w in text for w in _TRANSACTIONAL_WORDS))
    ):
        return "internal_ops"
"""

MUTATIONS = [
    (
        PRODUCT_KIND,
        "the internal-facing rule is removed: staff desks are workspaces again",
        RULE,
        "",
    ),
    (
        PRODUCT_KIND,
        "the saas==0 guard is dropped: an internal software tool flips to a desk",
        "    if (\n        saas == 0\n        and _hits(text, _INTERNAL_FACING_HINTS) >= 1",
        "    if (\n        _hits(text, _INTERNAL_FACING_HINTS) >= 1",
    ),
    (
        PRODUCT_KIND,
        "the ops-language conjunct is dropped: the assertion alone flips the kind",
        "        and (internal >= 1 or any(w in text for w in _TRANSACTIONAL_WORDS))\n    ):",
        "    ):",
    ),
    (
        PRODUCT_KIND,
        "back office stops being an ops hint",
        '    "back office",\n    "back-office",\n',
        "",
    ),
    (
        PRODUCT_KIND,
        "lessons and instructors stop being booking hints",
        '    "lesson",\n    "instructor",\n',
        "",
    ),
]

REPO = BACKEND.parent
PYTEST = (
    f'docker run --rm -v "{REPO}:/repo" -w /repo/backend '
    "-e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api "
    f"-c 'pip install -q pytest 2>/dev/null; python -m pytest {SUITES} "
    "-q --no-header -p no:cacheprovider'"
)


def run_suite() -> tuple[bool, str, list[str]]:
    proc = subprocess.run(
        PYTEST, shell=True, capture_output=True, text=True, timeout=900, cwd=REPO
    )
    out = proc.stdout + proc.stderr
    summary = ""
    for line in reversed(out.strip().splitlines()):
        if "passed" in line or "failed" in line or "error" in line.lower():
            summary = line.strip()
            break
    failed = sorted(
        {
            line.split("::")[-1].split()[0]
            for line in out.splitlines()
            if line.startswith("FAILED")
        }
    )
    green = "passed" in summary and not _FAILED_RE.search(summary)
    return green, summary, failed


def main() -> int:
    paths = {path for path, *_ in MUTATIONS}
    originals = {path: path.read_text() for path in paths}

    green, summary, _ = run_suite()
    print(f"baseline: {summary}")
    if not green:
        print("BASELINE IS RED — fix before mutating")
        return 1

    survivors: list[str] = []
    try:
        for path, label, old, new in MUTATIONS:
            original = originals[path]
            if original.count(old) != 1:
                print(
                    f"!! {label}: anchor matched {original.count(old)} times "
                    "— NOT APPLIED, this mutation tests nothing"
                )
                survivors.append(f"{label} (anchor drift)")
                continue
            mutated = original.replace(old, new, 1)
            if mutated == original:
                print(f"!! {label}: replacement is a no-op — NOT APPLIED")
                survivors.append(f"{label} (no-op)")
                continue

            path.write_text(mutated)
            try:
                caught_green, caught_summary, failed = run_suite()
            finally:
                path.write_text(original)

            if caught_green:
                print(f"SURVIVED  {label}  [{caught_summary}]")
                survivors.append(label)
            else:
                names = ", ".join(failed[:3]) or caught_summary
                print(f"caught    {label}  <- {names}")
    finally:
        for path, text in originals.items():
            path.write_text(text)

    print()
    if survivors:
        print(f"{len(survivors)} SURVIVED of {len(MUTATIONS)}:")
        for entry in survivors:
            print(f"  - {entry}")
        return 1
    print(f"all {len(MUTATIONS)} mutations caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
