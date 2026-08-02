"""Mutation-test the vitest suite against preview-template source.

    python3 tools/mutate.py

The repo's standing rule is *mutation-test every guard*: a guard whose success
looks like its failure is this codebase's recurring defect, and a green suite is
not evidence until each test has been shown to go red when the behaviour it
claims to pin is removed.

For each mutation below: apply an exact-string edit to the template source, run
vitest, record which test names failed, then restore from an in-memory backup —
never from `git checkout`, which has discarded uncommitted work here before.
A mutation that leaves the suite green names a test that pins nothing.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent.parent
TEMPLATE = TESTS.parent / "preview-template"
SRC = TEMPLATE / "src/ui/compose/SkeletonComposer.tsx"

#: (label, exact source to replace, replacement)
MUTATIONS: list[tuple[str, str, str]] = [
    (
        "throw removed from assertRequiredSections",
        """  if (missingRequired.length > 0) {
    throw new Error(`Skeleton "${skeletonId}" missing required sections: ${missingRequired.join(', ')}`);
  }""",
        "",
    ),
    (
        "shell no longer exempt from required check",
        "    if (section === 'shell') return false;\n",
        "",
    ),
    (
        "null slot treated as present",
        "    return slots[section] == null;",
        "    return !(section in slots);",
    ),
    (
        "explicit order no longer owns the page face (leftovers appended)",
        """  if (order && order.length > 0) {
    const requiredMissing = skeleton.requiredSections.filter(
      (section) =>
        section !== 'shell' &&
        slots[section] != null &&
        !sequence.includes(section),
    );
    return [...sequence, ...requiredMissing];
  }""",
        "",
    ),
    (
        "required-but-unordered sections no longer restored",
        "    return [...sequence, ...requiredMissing];",
        "    return sequence;",
    ),
    (
        "unrecognised slots no longer appended",
        """  for (const section of Object.keys(slots)) {
    if (section !== 'shell' && slots[section] != null && !sequence.includes(section)) {
      sequence.push(section);
    }
  }""",
        "",
    ),
    (
        "public-utility frame removed",
        "  if (skeletonId === 'public-utility') {",
        "  if (false) {",
    ),
    (
        "ops rail split removed",
        "  if (railSkeletons.includes(skeletonId) && slots.activity != null) {",
        "  if (false) {",
    ),
    (
        "non-rail fallback drops the recipe order",
        "    main: <SkeletonComposer skeletonId={skeletonId} slots={slots} order={order} />,",
        "    main: <SkeletonComposer skeletonId={skeletonId} slots={slots} />,",
    ),
]


def run_suite(report: Path) -> tuple[int, list[str]]:
    """Run vitest; return (exit code, names of failed tests)."""
    proc = subprocess.run(
        ["npm", "test", "--", "--reporter=json", f"--outputFile={report}"],
        cwd=TESTS,
        capture_output=True,
        text=True,
        timeout=600,
    )
    try:
        data = json.loads(report.read_text())
    except Exception:
        return proc.returncode, ["<no json report>"]
    failed = [
        test["fullName"]
        for result in data.get("testResults", [])
        for test in result.get("assertionResults", [])
        if test.get("status") == "failed"
    ]
    return proc.returncode, failed


def main() -> int:
    original = SRC.read_text()
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "vitest.json"

        code, failed = run_suite(report)
        print(f"baseline: exit={code} failed={failed}")
        if code != 0:
            print("BASELINE IS RED — fix that before mutating anything")
            return 1

        survivors: list[str] = []
        try:
            for label, old, new in MUTATIONS:
                found = original.count(old)
                if found != 1:
                    # The source moved out from under the mutation. Silence here
                    # would report a passing sweep that tested nothing.
                    print(f"!! {label}: anchor matched {found} times — NOT APPLIED")
                    survivors.append(f"{label} (anchor drift)")
                    continue
                SRC.write_text(original.replace(old, new, 1))
                code, failed = run_suite(report)
                caught = code != 0
                print(f"\n[{'RED' if caught else 'STILL GREEN <-- pins nothing'}] {label}")
                for name in failed:
                    print(f"    caught by: {name}")
                if not caught:
                    survivors.append(label)
                SRC.write_text(original)
        finally:
            SRC.write_text(original)
            if SRC.read_text() != original:
                print("RESTORE FAILED — check git diff before doing anything else")
                return 2
            print("\nsource restored and verified byte-identical")

    print(f"\nsurvivors (mutations no test caught): {survivors or 'none'}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
