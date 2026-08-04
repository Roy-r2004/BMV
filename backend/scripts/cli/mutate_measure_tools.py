"""Mutation-test the measurement tools' arithmetic.

    cd backend && python scripts/cli/mutate_measure_tools.py

These two files are why this sweep exists rather than being optional. Neither
had a test, both shipped a silent defect, and both defects were published as
findings before anyone noticed the instrument was wrong:

  - `analyse.py` read `preview_app["gate_issues"]`, a key nothing ever wrote, so
    four trios of evidence tables reported `gate_issues: 0`;
  - `tail.py` hardcoded `RUNS = [74..82]`, so asked about trio 7 it printed
    nothing and did not say it was printing nothing.

Both were unimportable — they parsed `sys.argv` at module scope, and under
pytest that argv is a list of test paths — which is the mechanical reason they
went untested for four trios. That is fixed, so the arithmetic is drivable, so
it is mutated here.

The blind spot aimed at specifically: **asserting against the case that does not
bind.** `distinct_candidates` equals `revisions` on any run whose candidates are
all different, and `fresh_authoring_chains` equals 1 on a healthy run — so the
fixtures are the real shape of request 92 (8 revisions, 6 distinct, 3 chains),
where each of those numbers differs from the others. A well-behaved fixture
would pass every mutation below.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

ANALYSE = BACKEND / "scripts/measure/analyse.py"
TAIL = BACKEND / "scripts/measure/tail.py"

SUITES = "tests/measure/test_measure_tools.py"

MUTATIONS = [
    # --- revision inflation: the number that misled me first ------------------
    (
        ANALYSE,
        "distinct_candidates just counts revisions (inflation invisible again)",
        '"distinct_candidates": len({r.get("app_spec_sha256") for r in ordered}),',
        '"distinct_candidates": len(ordered),',
    ),
    # --- the number 1.13 exists to move --------------------------------------
    (
        ANALYSE,
        "fresh_authoring_chains counts every revision",
        '            1 for r in ordered if r.get("parent_revision_id") is None\n        ),',
        "            1 for r in ordered\n        ),",
    ),
    (
        ANALYSE,
        "fresh chains counted by the wrong side of the parent link",
        "            1 for r in ordered if r.get(\"parent_revision_id\") is None",
        "            1 for r in ordered if r.get(\"parent_revision_id\") is not None",
    ),
    (
        ANALYSE,
        "fresh chains hardcoded to one (a re-authoring run reads as bounded)",
        "        \"fresh_authoring_chains\": sum(\n            1 for r in ordered if r.get(\"parent_revision_id\") is None\n        ),",
        "        \"fresh_authoring_chains\": 1,",
    ),
    # --- the verdict is the FINAL revision ------------------------------------
    (
        ANALYSE,
        "the verdict is read off the first revision instead of the last",
        "    final = ordered[-1]",
        "    final = ordered[0]",
    ),
    # --- acceptance -----------------------------------------------------------
    (
        ANALYSE,
        "accepted counts every revision (0-of-18 would have read as 18)",
        '        "accepted": sum(1 for r in ordered if r.get("status") == "accepted"),',
        '        "accepted": len(ordered),',
    ),
    (
        ANALYSE,
        "no revisions reports a clean zero rather than saying nothing was stored",
        '        return {"revisions": 0, "accepted": 0, "note": "no AppSpec revision stored"}',
        '        return {"revisions": 0, "accepted": 0}',
    ),
    # --- robustness: one bad row must not cost the run its numbers ------------
    (
        ANALYSE,
        "corrupt metadata JSON takes the whole report down",
        "        try:\n            return json.loads(row.get(\"generation_metadata_json\") or \"{}\")\n        except Exception:\n            return {}",
        "        return json.loads(row.get(\"generation_metadata_json\") or \"{}\")",
    ),
    # --- the void trio, in both tools ----------------------------------------
    (
        TAIL,
        "void trio 6 falls through and decomposes request 6",
        '    "6": None,',
        "",
    ),
    (
        TAIL,
        "the void guard is removed from tail",
        "        if runs is None:",
        "        if False:",
    ),
    (
        ANALYSE,
        "the void guard is removed from analyse",
        "    if selected is None:",
        "    if False:",
    ),
    (
        ANALYSE,
        "an unknown trio key is accepted silently",
        "    if key not in _TRIOS:",
        "    if False:",
    ),
    # --- the default nobody should change by accident -------------------------
    (
        ANALYSE,
        "a bare invocation no longer means trio 1",
        '    key = argv[0] if argv else "1"',
        '    key = argv[0] if argv else "2"',
    ),
    (
        TAIL,
        "a bare invocation no longer means the nine-run baseline",
        '        runs = _TRIOS["baseline"]',
        '        runs = _TRIOS["7"]',
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
    paths = {ANALYSE, TAIL}
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
            # The most valuable refusal in this script: an anchor that no longer
            # matches applies nothing and would be reported as a pass.
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
