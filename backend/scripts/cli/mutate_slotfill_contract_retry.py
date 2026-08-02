"""Mutation-test the slot-fill catalogue-contract retry (roadmap 2.9).

    cd backend && python scripts/cli/mutate_slotfill_contract_retry.py

The standing rule is *mutation-test every guard*. This one needs it more than
most: the defect it fixes was itself a guard that could not fail. The slot-fill
retry loop had four rejection reasons, a cap of two attempts, and a log line for
each — and across requests 74-79 it fired exactly zero times while 26 pages were
discarded past it. Everything about it looked healthy.

Reverts each half of the fix in turn, runs the two suites that pin it, reports
which tests caught it, and restores from an in-memory backup — never
`git checkout`, which has discarded uncommitted work in this repo before.

Exit code is 0 only when every mutation was caught. Requires the `api` service
to be up (`docker compose up -d api`); the repo is bind-mounted into it, so
edits here are visible there without a rebuild.

Note the shell: `sh -c`, never `sh -lc`. A login shell re-reads /etc/profile,
which drops /opt/node/bin from PATH, and `tsx_parse_error` fails open without
node — six unrelated tests go red and the mutation report becomes noise.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

#: `"failed" in summary` is wrong: "1 xfailed" contains it, so a green suite
#: with one xfail reads as red and the sweep refuses to start. Count instead.
_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

GENERATE = BACKEND / "app/application/preview_app/codegen/generate.py"

SUITES = (
    "tests/preview_app/test_slotfill_retry.py "
    "tests/preview_app/test_catalogue_contract.py"
)

MUTATIONS = [
    # --- the rejection itself ------------------------------------------------
    (
        "contract rejection disabled (revert to syntax-only — the 2.9 defect)",
        "    if not would_replace:\n        return None",
        "    if True:\n        return None",
    ),
    (
        "rejects every contract error, not only what enforce discards",
        "    if not would_replace:\n        return None",
        "    if False:\n        return None",
    ),
    (
        "retry prompt loses the validator errors (generic 'try again')",
        "            if reason == CONTRACT_REJECTION:",
        "            if False:",
    ),
    (
        "contract rejection not counted as an unusable call",
        "            call.adjudicate(not reason, reason=UNUSABLE_REJECTED)",
        "            call.adjudicate(True, reason=UNUSABLE_REJECTED)",
    ),
    # --- the cost bound ------------------------------------------------------
    (
        "runway gate always open (retry regardless of remaining time)",
        "    if left is None or left >= DEFAULT_ASK_CEILING_SECONDS + RESERVE_SECONDS:",
        "    if True:",
    ),
    (
        "runway gate always closed (contract retry can never fire)",
        "    if left is None or left >= DEFAULT_ASK_CEILING_SECONDS + RESERVE_SECONDS:",
        "    if False:",
    ),
    (
        "skipped retry is silent (no degradation recorded)",
        '    record_degradation("codegen", "slot_fill_contract_retry_skipped_low_runway")',
        "    pass",
    ),
]

PYTEST = (
    "docker compose exec -T api sh -c "
    f"'cd /app/backend && python -m pytest {SUITES} -q --no-header -p no:cacheprovider'"
)


def run_suite() -> tuple[bool, str, list[str]]:
    proc = subprocess.run(
        PYTEST, shell=True, capture_output=True, text=True, timeout=900, cwd=BACKEND.parent
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
    green = "passed" in summary and not _FAILED_RE.search(summary)
    return green, summary, failed


def main() -> int:
    original = GENERATE.read_text()

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
            GENERATE.write_text(original.replace(old, new, 1))
            green, summary, failed = run_suite()
            print(f"\n[{'STILL GREEN <-- pins nothing' if green else 'RED'}] {label}")
            print(f"    {summary}")
            for name in failed:
                print(f"    caught by: {name}")
            if green:
                survivors.append(label)
            GENERATE.write_text(original)
    finally:
        GENERATE.write_text(original)
        if GENERATE.read_text() != original:
            print(f"RESTORE FAILED for {GENERATE}")
            return 2
        print("\nsource restored and verified byte-identical")

    print(f"\nsurvivors: {survivors or 'none'}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
