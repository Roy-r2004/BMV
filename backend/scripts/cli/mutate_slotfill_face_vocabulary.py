"""Mutation-test the listing-face vocabulary in the slot_fill prompt.

    cd backend && python scripts/cli/mutate_slotfill_face_vocabulary.py

Session 18: the dominant contract rejection ("missing directory face
component:PageHeader, missing BRAND_MANIFEST services binding", 5 of 6) was a
vocabulary the prompt never taught, and request 107 repeated it byte-identical
on retry. The fix renders a face-contract block — derived from the validator's
own required tuples — into every face-scaffold slot_fill prompt, and gives the
contract retry a translation. Five mutations: the producer gated shut, the
directory requirements dropped, the render kwarg unwired, the template render
deleted, and the retry translation removed. Restores from an in-memory backup.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

FACE_PROMPT = BACKEND / "app/application/preview_app/catalogue_contract/face_prompt.py"
GENERATE = BACKEND / "app/application/preview_app/codegen/generate.py"
TEMPLATE = BACKEND / "app/templates/prompts/preview_app_slot_fill.j2"

SUITES = "tests/preview_app/test_slotfill_face_vocabulary.py tests/preview_app/test_slotfill_retry.py"

MUTATIONS = [
    (
        FACE_PROMPT,
        "the producer is gated shut: every scaffold reads as slot-composed",
        "    if _DIRECTORY_FACE_MARKER in text:",
        "    if False and _DIRECTORY_FACE_MARKER in text:",
    ),
    (
        FACE_PROMPT,
        "the directory requirements are dropped from the block",
        '        required = ", ".join(_DIRECTORY_FACE_REQUIRED)',
        '        required = ", ".join(_DIRECTORY_FACE_REQUIRED[:1])',
    ),
    (
        GENERATE,
        "the render kwarg is unwired: the block never reaches the prompt",
        "        face_contract_block=listing_face_contract_block(scaffold),",
        '        face_contract_block="",',
    ),
    (
        TEMPLATE,
        "the template render is deleted",
        "{% if face_contract_block %}\n{{ face_contract_block }}\n{% endif %}",
        "",
    ),
    (
        GENERATE,
        "the contract-retry translation is removed",
        '    "catalogue-contract": (',
        '    "catalogue-contract-disabled": (',
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
