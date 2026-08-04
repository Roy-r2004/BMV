"""Mutation-test the per-request AppSpec budget and its runway reservation.

    cd backend && python scripts/cli/mutate_appspec_request_budget.py

Reverts each half of the fix in turn, runs the suites that pin it, reports which
tests caught it, and restores from an **in-memory** backup — never `git checkout`,
which has discarded uncommitted work in this repo before.

The blind spots this sweep is written against, all four of which have let
mutations survive a first pass in an earlier session:

  - **asserting against the case that does not bind.** A per-instance ceiling and
    a per-request one are identical until the stage is entered twice, so every
    budget mutation is driven through *two* providers on one armed deadline. A
    single-provider fixture proves nothing here and would have passed the defect.
  - **driving the consumer and never the producer.** `consume_stage_call` on
    `RequestDeadline` is the producer; `_acquire` is the consumer. Both are
    mutated, and the tests call `_acquire` — the seam the pipeline actually uses.
  - **guards that cannot fail.** The no-deadline path is mutated to share the
    tally, which must break the admin/test case; if nothing goes red there, that
    branch is dead code rather than a fallback.
  - **fixtures too small to reach the rule.** The runway tests arm deadlines
    either side of the reservation (200 s and 285 s), not a comfortable default.

Exit code is 0 only when every mutation was caught.

Note the shell: `sh -c`, never `sh -lc`. A login shell re-reads /etc/profile,
which drops /opt/node/bin from PATH, and `tsx_parse_error` fails open without
node — unrelated tests go red and the mutation report becomes noise.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

#: `"failed" in summary` is wrong: "1 xfailed" contains it, so a green suite with
#: one xfail reads as red and the sweep refuses to start. Count instead.
_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

GENERATION = BACKEND / "app/application/appspec/generation.py"
DEADLINE = BACKEND / "app/application/services/request_deadline.py"
CONFIG = BACKEND / "app/core/config.py"

SUITES = (
    "tests/appspec/test_appspec_request_budget.py "
    "tests/application/test_request_deadline.py "
    "tests/appspec/test_appspec_call_telemetry.py"
)

MUTATIONS = [
    # --- the runway reservation: the bound that decides if a run has a preview -
    (
        GENERATION,
        "the runway reservation is removed (appspec may spend the whole budget)",
        "        if left < reserve:",
        "        if False:",
    ),
    (
        GENERATION,
        "reservation only fires past the deadline (the pre-fix behaviour exactly)",
        "        if left < reserve:",
        "        if left < 0:",
    ),
    (
        GENERATION,
        "refusing on runway silently eats a call from the budget too",
        "            deadline.record_degradation(\"appspec\", \"stopped_low_downstream_runway\")",
        "            deadline.consume_stage_call(\"appspec\", self.max_calls)",
    ),
    (
        GENERATION,
        "the runway refusal is silent (a starved run looks like a short one)",
        "            deadline.record_degradation(\"appspec\", \"stopped_low_downstream_runway\")\n",
        "",
    ),
    # --- the per-request tally ------------------------------------------------
    (
        GENERATION,
        "budget held per provider instance again (the defect: 7, 6 and 10 calls)",
        "        if not deadline.consume_stage_call(\"appspec\", self.max_calls):",
        "        if self.calls_used >= self.max_calls:",
    ),
    (
        GENERATION,
        "the budget refusal is silent",
        "            deadline.record_degradation(\"appspec\", \"call_budget_exhausted\")\n",
        "",
    ),
    (
        GENERATION,
        "the no-deadline path shares the tally (admin re-runs get one budget ever)",
        "        deadline = current_deadline()\n        if deadline is None:",
        "        deadline = current_deadline()\n        if False:",
    ),
    # --- the producer, on RequestDeadline -------------------------------------
    (
        DEADLINE,
        "tally compares with > so the stage gets one call more than configured",
        "            if used >= max(1, int(limit)):",
        "            if used > max(1, int(limit)):",
    ),
    (
        DEADLINE,
        "the tally never increments (the ceiling stops binding entirely)",
        "            self._stage_calls[stage] = used + 1",
        "            self._stage_calls[stage] = used",
    ),
    (
        DEADLINE,
        "the tally is keyed per call rather than per stage",
        "            used = self._stage_calls.get(stage, 0)",
        "            used = 0",
    ),
    (
        DEADLINE,
        "stage_calls_used always reports zero (the measurement, not the bound)",
        "            return self._stage_calls.get(stage, 0)",
        "            return 0",
    ),
    # --- the two numbers ------------------------------------------------------
    (
        CONFIG,
        "call budget back to 6 per request (refuses the call that accepted 87)",
        'self.APPSPEC_MAX_CALLS = max(2, int(os.getenv("APPSPEC_MAX_CALLS", "8")))',
        'self.APPSPEC_MAX_CALLS = max(2, int(os.getenv("APPSPEC_MAX_CALLS", "6")))',
    ),
    (
        CONFIG,
        "reservation set above what shipped runs left (would refuse request 83)",
        '"APPSPEC_DOWNSTREAM_RESERVE_SECONDS", "280"',
        '"APPSPEC_DOWNSTREAM_RESERVE_SECONDS", "400"',
    ),
    (
        CONFIG,
        "reservation set to zero (the bound is configured away)",
        '"APPSPEC_DOWNSTREAM_RESERVE_SECONDS", "280"',
        '"APPSPEC_DOWNSTREAM_RESERVE_SECONDS", "0"',
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
    # Read the SUMMARY LINE, never the exit code.
    green = "passed" in summary and not _FAILED_RE.search(summary)
    return green, summary, failed


def main() -> int:
    paths = {GENERATION, DEADLINE, CONFIG}
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
            # Anchor drift is the most valuable refusal in this script: an
            # anchor that no longer matches applies nothing and reports a pass.
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
