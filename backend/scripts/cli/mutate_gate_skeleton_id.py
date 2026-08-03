"""Mutation-test the gate-issue `skeleton_id` instrument (pre-flight question 5).

    cd backend && python scripts/cli/mutate_gate_skeleton_id.py

The thing being guarded is a *measurement*, and a measurement that silently
records nothing is this repo's most expensive recurring defect —
`preview_app["gate_issues"]` was read by `analyse.py` for four trios and written
by nobody, so every evidence table it produced said zero and nothing was red.

Both halves get mutated on purpose: the producer (`GateReport` resolving a
skeleton) and the consumer (`finalize` publishing it). Session 7 shipped six
tests that could not fail and half of them drove only one side.

Restores from an in-memory backup, never `git checkout`. Exit 0 only when every
mutation was caught. Reads the SUMMARY LINE, never the exit code.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent

GATE = BACKEND / "app/application/preview_app/quality_gate.py"
FINALIZE = BACKEND / "app/application/preview_app/pipeline/finalize.py"

SUITES = (
    "tests/preview_app/test_gate_issue_skeleton_id.py "
    "tests/preview_app/test_quality_gate.py"
)

MUTATIONS = [
    # --- the producer ---------------------------------------------------------
    (
        GATE,
        "skeleton never resolved (the defect: one code, two indistinguishable fires)",
        '        return str(catalogue_route_for_file(path, self.architect).get("skeleton_id") or "")',
        '        return ""',
    ),
    (
        GATE,
        "the gate stops handing its architect to the report",
        "    report = GateReport(architect=architect)",
        "    report = GateReport()",
    ),
    (
        GATE,
        "failures carry a skeleton, warnings do not",
        "        self.warnings.append(\n            GateIssue(\n"
        "                code=code, message=message, path=path, "
        "skeleton_id=self._skeleton_for(path)\n            )\n        )",
        "        self.warnings.append(GateIssue(code=code, message=message, path=path))",
    ),
    (
        GATE,
        "the lookup keys on the code rather than the path",
        "        return str(catalogue_route_for_file(path, self.architect)"
        '.get("skeleton_id") or "")',
        '        return str(catalogue_route_for_file("", self.architect)'
        '.get("skeleton_id") or "")',
    ),
    # Two mutations are deliberately absent: `if not path` and
    # `if self.architect is None` short-circuits in front of that lookup. Both were
    # written, both survived, and both turned out to be provably dead —
    # `catalogue_route_for_file` handles a `None` architect and can never match an
    # empty path. They were deleted rather than tested around.
    # --- the consumer ---------------------------------------------------------
    (
        FINALIZE,
        "gate issues not published (back to analyse.py reading a key nobody writes)",
        '        "gate_issues": [\n            {\n                "code": i.code,',
        '        "gate_issues": [\n            {\n                "code": None,',
    ),
    (
        FINALIZE,
        "the published issue drops its skeleton",
        '                "skeleton_id": i.skeleton_id,\n                "message": i.message[:200],',
        '                "skeleton_id": "",\n                "message": i.message[:200],',
    ),
    (
        FINALIZE,
        "warnings are not published",
        '        "gate_warnings": [\n            {"code": i.code, "path": i.path, '
        '"skeleton_id": i.skeleton_id}\n            for i in gate.warnings\n        ],',
        '        "gate_warnings": [],',
    ),
    (
        FINALIZE,
        "the message bound is removed (a repair log lands in generated_pages)",
        '"message": i.message[:200],',
        '"message": i.message,',
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
    originals = {path: path.read_text() for path in {GATE, FINALIZE}}

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
            green, summary, failed = run_suite()
            print(f"\n[{'STILL GREEN <-- pins nothing' if green else 'RED'}] {label}")
            print(f"    {summary}")
            for name in failed:
                print(f"    caught by: {name}")
            if green:
                survivors.append(label)
            path.write_text(original)
    finally:
        restored = True
        for path, original in originals.items():
            path.write_text(original)
            if path.read_text() != original:
                print(f"RESTORE FAILED for {path}")
                restored = False
        if restored:
            print("\nsource restored and verified byte-identical")

    if not restored:
        return 2
    print(f"\nsurvivors: {survivors or 'none'}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
