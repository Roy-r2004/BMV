"""Mutation-test the DoD 2 / DoD 5 census parsers.

    cd backend && python scripts/cli/mutate_content_census.py

A census tool is a measurement instrument, and this repo's recurring defect is an
instrument that quietly stops measuring: a `tail` that swallowed a red `tsc`,
mutation decoys whose anchors had drifted, a compose service mounting the wrong
tree. A prose detector that starts returning zero reads as "Phase 2 already
landed", which is the most expensive possible way to be wrong about DoD 2.

Restores from an **in-memory** backup, never `git checkout`. Exit code is 0 only
when every mutation was caught. Reads the SUMMARY LINE, never the exit code.

One mutation is deliberately absent. Removing the `className` span exclusion
entirely survives, because `_looks_like_a_class_list` already rejects the same
strings — over the archived corpus the exclusion is worth 1,497 chars out of
645,884, 0.2 %. That is a finding about the definition rather than a gap in the
tests, and it is what makes DoD 2's number robust to its one judgment call.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
CENSUS = BACKEND / "scripts/measure/content_census.py"

SUITES = "tests/preview_app/test_content_census.py"

MUTATIONS = [
    (
        "every string is prose (tailwind class lists counted as copy)",
        "    if _looks_like_a_class_list(text):\n        return False",
        "    if False:\n        return False",
    ),
    (
        "nothing is prose (the detector reads Phase 2 as already done)",
        "    if _looks_like_a_class_list(text):\n        return False",
        "    if True:\n        return False",
    ),
    (
        "one word is enough to be prose",
        "    return len(words) >= 2",
        "    return len(words) >= 1",
    ),
    (
        "any string of four characters is prose",
        "    return len(words) >= 2",
        "    return len(words) >= 0",
    ),
    (
        "the utility charset accepts capitals (the only thing keeping copy out)",
        r'    return all(re.fullmatch(r"[a-z0-9:\[\]/.\-%#()!*+_,]+", t) for t in tokens)',
        r'    return all(re.fullmatch(r"[A-Za-z0-9:\[\]/.\-%#()!*+_,]+", t) for t in tokens)',
    ),
    (
        "one hyphenated token is enough to read as tailwind (the original defect)",
        "    if utility * 2 < len(tokens):\n        return False",
        "    if utility < 1:\n        return False",
    ),
    (
        "the utility-token ratio stops mattering entirely",
        "    if utility * 2 < len(tokens):\n        return False",
        "    if False:\n        return False",
    ),
    (
        "JSX text nodes are not counted (only props are)",
        "    for m in _JSX_TEXT.finditer(body):",
        "    for m in []:",
    ),
    (
        "string literals are not counted (only JSX text is)",
        "    for m in _STRING.finditer(body):",
        "    for m in []:",
    ),
    (
        "seed key walk collects nested keys too",
        "        elif depth == 1 and c == \":\":",
        "        elif depth >= 1 and c == \":\":",
    ),
    (
        "seed key walk does not skip string contents",
        "        if c in \"\\\"'`\":\n            quote = c\n            i += 1\n            continue",
        "        if False:\n            quote = c\n            i += 1\n            continue",
    ),
    (
        "mock export keys match anywhere, not at line start",
        r'    return {m.group(1) for m in re.finditer(r"^export const (\w+)", source, re.M)}',
        r'    return {m.group(1) for m in re.finditer(r"export const (\w+)", source)}',
    ),
]

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
    original = CENSUS.read_text()

    green, summary, _ = run_suite()
    print(f"baseline: {summary}")
    if not green:
        print("BASELINE IS RED — fix before mutating")
        return 1

    survivors: list[str] = []
    try:
        for label, old, new in MUTATIONS:
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
            CENSUS.write_text(mutated)
            green, summary, failed = run_suite()
            print(f"\n[{'STILL GREEN <-- pins nothing' if green else 'RED'}] {label}")
            print(f"    {summary}")
            for name in failed:
                print(f"    caught by: {name}")
            if green:
                survivors.append(label)
            CENSUS.write_text(original)
    finally:
        CENSUS.write_text(original)
        restored = CENSUS.read_text() == original
        if not restored:
            print(f"RESTORE FAILED for {CENSUS}")
        else:
            print("\nsource restored and verified byte-identical")

    if not restored:
        return 2
    print(f"\nsurvivors: {survivors or 'none'}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
