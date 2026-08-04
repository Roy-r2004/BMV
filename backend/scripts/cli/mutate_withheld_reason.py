"""Mutation-test the published `withheld_reason` and the derived `viewable`.

    cd backend && python scripts/cli/mutate_withheld_reason.py

Reverts each half of the fix in turn, runs the suites that pin it, reports which
tests caught it, and restores from an **in-memory** backup — never `git checkout`.

The blind spots this sweep is written against:

  - **driving the consumer, never the producer.** The seam mutations hit
    `withheld_reason`; the publication mutations hit the dict `run_finalize`
    returns. A test that only called the helper would be green with the key
    deleted, which is exactly the defect being fixed.
  - **asserting against the case that does not bind.** Every ordering mutation
    is driven through a fixture where *two* refusals are live at once; a
    single-cause fixture cannot tell `build_failed` from `quality_gate_failed`.
  - **guards that cannot fail.** `viewable = withheld is None` is mutated back
    to its own boolean expression. If nothing goes red, the two are the same
    thing said twice and one of them should go.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

FINALIZE = BACKEND / "app/application/preview_app/pipeline/finalize.py"
ANALYSE = BACKEND / "scripts/measure/analyse.py"

SUITES = (
    "tests/preview_app/test_withheld_reason_is_published.py "
    "tests/preview_app/test_visual_report_is_re_derived.py "
    "tests/preview_app/test_fallback_accounting.py "
    "tests/preview_app/test_gate_issue_skeleton_id.py "
    "tests/measure/test_measure_tools.py"
)

MUTATIONS = [
    # --- the publication: the whole point ------------------------------------
    (
        FINALIZE,
        "the reason is never published (the state duo 1 was read in)",
        '        "withheld_reason": withheld,\n',
        "",
    ),
    (
        FINALIZE,
        "the reason is omitted when the preview is served",
        '        "withheld_reason": withheld,',
        '        **({"withheld_reason": withheld} if withheld else {}),',
    ),
    (
        FINALIZE,
        "`viewable` is stored beside `status`, free to disagree with it",
        '        "withheld_reason": withheld,',
        '        "withheld_reason": withheld,\n        "viewable": True,',
    ),
    # --- the ordering, which decides which tool the operator opens -----------
    (
        FINALIZE,
        "a failed build is reported as a gate failure",
        '    if not dist_ok:\n        return "build_failed"\n    if not gate_ok:\n        return "quality_gate_failed"',
        '    if not gate_ok:\n        return "quality_gate_failed"\n    if not dist_ok:\n        return "build_failed"',
    ),
    (
        FINALIZE,
        "an unresolved render crash outranks the gate that also blocked",
        '    if not gate_ok:\n        return "quality_gate_failed"\n    if crash_unresolved:',
        '    if crash_unresolved:\n        return "render_crash_unresolved"\n    if False:',
    ),
    (
        FINALIZE,
        "the unresolved-crash refusal is dropped (a stack trace ships as ready)",
        '    if crash_unresolved:\n        return "render_crash_unresolved"\n',
        "",
    ),
    (
        FINALIZE,
        "every refusal collapses to one undifferentiated string",
        '    if not gate_ok:\n        return "quality_gate_failed"',
        '    if not gate_ok:\n        return "build_failed"',
    ),
    # --- viewable must stay the negation of the reason -----------------------
    (
        FINALIZE,
        "viewable stops following the reason (the two can now disagree)",
        "    viewable = withheld is None",
        "    viewable = bool(dist_ok and gate.ok)",
    ),
    (
        FINALIZE,
        "viewable is inverted",
        "    viewable = withheld is None",
        "    viewable = withheld is not None",
    ),
    # --- the reader ----------------------------------------------------------
    (
        ANALYSE,
        "analyse goes back to reading the key nothing writes",
        '        "viewable": None if not pa else pa.get("status") == "ready",',
        '        "viewable": pa.get("viewable"),',
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
