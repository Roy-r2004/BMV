"""Mutation-test the classifier's prefix-anchored hint matching.

    cd backend && python scripts/cli/mutate_classifier_boundary.py

Reverts each part of the session-15 ruling in turn, runs the suite that pins
it, reports which tests caught it, and restores from an **in-memory** backup —
never `git checkout`.

The ruling adopted the PREFIX variant measured by
`scripts/measure/boundary_variant_census.py`: a hint matches only where it
starts at a word edge, and the right side stays free because the hint tables
hold deliberate stems ("reconcil", "bookkeep"). The mutation surface is
therefore two-sided:

  - falling back to bare substrings (the filed defect: "oms"@Rooms picked
    internal_ops off a business NAME), and
  - overshooting to a both-sides word boundary (the variant the ruling
    rejected: stems die, and a one-signal brief falls to the default).

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

PRODUCT_KIND = BACKEND / "app/application/preview_app/product_kind.py"

SUITES = "tests/preview_app/test_product_kind.py"

MUTATIONS = [
    (
        PRODUCT_KIND,
        "_blob stops wrapping: every hint check is a bare substring again",
        '''def _blob(*parts: str) -> _HintBlob:
    return _HintBlob(
        scrub_negated_product_clauses(" ".join(str(p or "") for p in parts).lower())
    )''',
        '''def _blob(*parts: str) -> str:
    return scrub_negated_product_clauses(
        " ".join(str(p or "") for p in parts).lower()
    )''',
    ),
    (
        PRODUCT_KIND,
        "the left lookbehind is dropped: 'oms' matches inside 'Rooms' again",
        '        lead = r"(?<!\\w)" if needle[0].isalnum() else ""',
        '        lead = ""',
    ),
    (
        PRODUCT_KIND,
        "a right boundary is added: the rejected word variant, stems die",
        '        return re.search(f"{lead}{re.escape(needle)}", self) is not None',
        '        return re.search(f"{lead}{re.escape(needle)}(?!\\\\w)", self) is not None',
    ),
    (
        PRODUCT_KIND,
        "the alnum condition is inverted: alnum-led hints lose their boundary",
        '        lead = r"(?<!\\w)" if needle[0].isalnum() else ""',
        '        lead = r"(?<!\\w)" if not needle[0].isalnum() else ""',
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
