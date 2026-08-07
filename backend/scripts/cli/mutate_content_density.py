"""Mutation-test the content-density record (Phase 0's 0.8).

    cd backend && python scripts/cli/mutate_content_density.py

The metric exists because `fallback_pages` reads scaffold bookkeeping whose
literal marker the 0.2 census proved survives slot-fill (275 of 631 archived
pages), and because after the Phase 2 flip a marker count is silently dead.
The mutations that matter are therefore the silent-death shapes: a detector
that returns zero, an exclusion that stops excluding, a failure that becomes
an absent key instead of a recorded `unmeasured`, and finalize dropping the
record entirely.

`docker run`, not `docker compose exec` — see HANDOFF.md for the two ways the
convenient alternative lies about the verdict.

Exit 0 only when every mutation was caught. Restores from an in-memory backup,
never `git checkout`.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

#: "2 xfailed" contains "failed"; count instead of substring-testing.
_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent

DENSITY = BACKEND / "app/application/preview_app/content_density.py"
FINALIZE = BACKEND / "app/application/preview_app/pipeline/finalize.py"

SUITES = "tests/preview_app/test_content_density.py"

MUTATIONS: list[tuple[str, Path, str, str]] = [
    (
        "the detector silently returns zero (the census's core fear)",
        DENSITY,
        "    words = [w for w in re.split(r\"\\s+\", text) if len(re.sub(r\"[^A-Za-z]\", \"\", w)) >= 2]\n    return len(words) >= 2",
        "    words = [w for w in re.split(r\"\\s+\", text) if len(re.sub(r\"[^A-Za-z]\", \"\", w)) >= 2]\n    return False",
    ),
    (
        "one hyphenated token condemns real prose as Tailwind (the sweep-found decoy)",
        DENSITY,
        "    if utility * 2 < len(tokens):",
        "    if utility < 1:",
    ),
    (
        "className spans stop being excluded",
        DENSITY,
        "        if _inside_classname(m.start(2 if m.group(2) is not None else 3)):\n            continue",
        "        if False:\n            continue",
    ),
    # No import-sub mutation: `_IMPORT_LINE` strips only the clause up to
    # `from`, which contains no strings and no JSX text, so removing the sub
    # cannot change a count — an unkillable mutation tests the driver, not
    # the code.
    (
        "an unreadable page crashes the measurement instead of being skipped",
        DENSITY,
        "        if not source:\n            continue",
        "        if False:\n            continue",
    ),
    (
        "the thin-page threshold inverts",
        DENSITY,
        "            f for f, c in per_page.items() if c < THIN_PAGE_CHARS",
        "            f for f, c in per_page.items() if c > THIN_PAGE_CHARS",
    ),
    (
        "the total lies",
        DENSITY,
        "        \"prose_chars_total\": sum(counts),",
        "        \"prose_chars_total\": 0,",
    ),
    (
        "a failed measurement reports itself as measured",
        DENSITY,
        "        return {\"status\": \"unmeasured\", \"reason\": f\"{type(exc).__name__}: {exc}\"[:200]}",
        "        return {\"status\": \"measured\", \"reason\": f\"{type(exc).__name__}: {exc}\"[:200]}",
    ),
    (
        "finalize stops storing the record",
        FINALIZE,
        "        \"content_density\": content_density,",
        "",
    ),
    (
        "finalize stores a permanent unmeasured stub",
        FINALIZE,
        "    content_density = density_record(workspace, route_list)",
        "    content_density = {\"status\": \"unmeasured\", \"reason\": \"skipped\"}",
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
    # Read the SUMMARY LINE, never the exit code.
    return "passed" in summary and not _FAILED_RE.search(summary), summary, failed


def main() -> int:
    originals = {path: path.read_text() for path in {m[1] for m in MUTATIONS}}

    green, summary, _ = run_suite()
    print(f"baseline: {summary}")
    if not green:
        print("BASELINE IS RED — fix before mutating")
        return 1

    survivors: list[str] = []
    try:
        for label, path, old, new in MUTATIONS:
            source = originals[path]
            if source.count(old) != 1:
                print(
                    f"!! {label}: anchor matched {source.count(old)} times in "
                    f"{path.name} — NOT APPLIED, this mutation tests nothing"
                )
                survivors.append(f"[anchor] {label}")
                continue
            path.write_text(source.replace(old, new))
            green, summary, failed = run_suite()
            verdict = "SURVIVED" if green else "caught"
            print(f"{verdict}: {label} — {summary}")
            if green:
                survivors.append(label)
            path.write_text(source)
    finally:
        for path, source in originals.items():
            path.write_text(source)

    print(f"\n{len(MUTATIONS) - len(survivors)}/{len(MUTATIONS)} caught")
    if survivors:
        print("SURVIVORS:")
        for s in survivors:
            print(f"  - {s}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
