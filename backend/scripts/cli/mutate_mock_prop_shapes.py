"""Mutation-test the mock-synthesis prop-shape wiring.

    cd backend && python scripts/cli/mutate_mock_prop_shapes.py

Reverts the session-16 wiring in turn, runs the suite that pins it, and
restores from an **in-memory** backup — never `git checkout`.

The defect class this guards: the CATALOGUE ITEM SHAPES section of
`preview_app_mock_synthesize.j2`, its producer `catalogue_prop_shape_block()`
and its render-level tests all landed while the ONE kwarg at the production
call site (`codegen/mock.py`) did not — the `is defined` guard hid the gap, so
the guidance never reached a model. Found by a template/call-site variable
audit (StrictUndefined renderer; every guarded variable that no call site
passes is a silently-dead prompt section). The catching test drives
`synthesize_mock_data` itself and captures the prompt off a fake provider, so
it cannot drift from the wiring the way the render-level test did.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

MOCK = BACKEND / "app/application/preview_app/codegen/mock.py"

SUITES = "tests/preview_app/test_propshape_contract.py"

KWARG_BLOCK = """        # The template's CATALOGUE ITEM SHAPES section was authored for this
        # call and guarded with `is defined` — without this kwarg it never
        # renders and the model invents member names the components don't read.
        catalogue_prop_shapes=catalogue_prop_shape_block(),
"""

MUTATIONS = [
    (
        MOCK,
        "the kwarg is dropped again: the shapes section silently stops rendering",
        KWARG_BLOCK,
        "",
    ),
    (
        MOCK,
        "an empty block is passed: the guard swallows it and the section is gone",
        "        catalogue_prop_shapes=catalogue_prop_shape_block(),",
        '        catalogue_prop_shapes="",',
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
