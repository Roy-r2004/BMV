"""Mutation-test `visual_review_status` when the critic never ran.

    cd backend && python scripts/cli/mutate_visual_not_run_reason.py

The field used to be *absent* when there was no report, so every reader that
reached for it with `.get()` stored `None` — trios 4 and 5 are recorded that
way. `None` conflated three states a measurement has to tell apart (skipped past
the deadline, skipped by configuration, the stage raising) and was also
indistinguishable from "the field did not exist yet".

The mutation that matters most is the tempting one-word version of this fix:
reusing `unmeasured` for "never ran". `unmeasured` means the critic ran, had
pages and judged none of them, and it drives finalize's WARN plus
`PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED`. Overloading it would make every
deadline skip read as a vision outage.

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

CRITIC = BACKEND / "app/application/preview_app/pipeline/visual_critic.py"
FINALIZE = BACKEND / "app/application/preview_app/pipeline/finalize.py"
BUILD = BACKEND / "app/application/preview_app/pipeline/build_phase.py"

SUITES = (
    "tests/preview_app/test_visual_report_is_re_derived.py "
    "tests/application/test_request_deadline.py"
)

MUTATIONS: list[tuple[str, Path, str, str]] = [
    (
        "no-report case contributes no fields again (the defect)",
        CRITIC,
        "        if not path.is_file():\n            return not_run",
        "        if not path.is_file():\n            return {}",
    ),
    (
        "no-report case reports `unmeasured` (the tempting wrong fix)",
        CRITIC,
        '        "visual_review_status": not_run_reason or "not_run",',
        '        "visual_review_status": "unmeasured",',
    ),
    (
        "the reason is accepted and then discarded",
        CRITIC,
        '        "visual_review_status": not_run_reason or "not_run",',
        '        "visual_review_status": "not_run",',
    ),
    (
        "an unreadable report is indistinguishable from a configured skip",
        CRITIC,
        '        return {**not_run, "visual_review_status": "report_unreadable"}',
        "        return not_run",
    ),
    (
        "finalize drops the reason on the floor",
        FINALIZE,
        '        _visual_review_summary(workspace, getattr(ctx, "visual_not_run_reason", None))',
        "        _visual_review_summary(workspace)",
    ),
    (
        "an unreadable summary goes back to reporting nothing",
        FINALIZE,
        '        return {\n            "visual_review_status": "report_unreadable",',
        '        return {}\n        return {\n            "visual_review_status": "report_unreadable",',
    ),
    (
        "build_phase stops recording the reason at all",
        BUILD,
        "    ctx.visual_not_run_reason = _visual_critic_not_run_reason(ok)",
        "    ctx.visual_not_run_reason = None",
    ),
    (
        "a configured skip and a deadline skip record the same reason",
        BUILD,
        '        return "skipped_by_config"',
        '        return "skipped_past_deadline"',
    ),
    (
        "a failed build consults the elective deadline (phantom degradation)",
        BUILD,
        '    if not ok:\n        return "build_failed"',
        "    if False:\n        return \"build_failed\"",
    ),
    (
        "a stage that raised is indistinguishable from one that ran",
        BUILD,
        '            ctx.visual_not_run_reason = "stage_failed"',
        "            pass",
    ),
    (
        "the deadline skip is no longer reported as one",
        BUILD,
        '        return "skipped_past_deadline"',
        '        return "skipped_by_config"',
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
                survivors.append(f"{label} (anchor drift)")
                continue
            path.write_text(source.replace(old, new, 1))
            green, summary, failed = run_suite()
            print(f"\n[{'STILL GREEN <-- pins nothing' if green else 'RED'}] {label}")
            print(f"    {summary}")
            for name in failed:
                print(f"    caught by: {name}")
            if green:
                survivors.append(label)
            path.write_text(source)
    finally:
        for path, source in originals.items():
            path.write_text(source)
            if path.read_text() != source:
                print(f"RESTORE FAILED for {path}")
                return 2
        print("\nsources restored and verified byte-identical")

    print(f"\nsurvivors: {survivors or 'none'}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
