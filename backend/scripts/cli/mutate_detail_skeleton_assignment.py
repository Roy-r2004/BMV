"""Mutation-test the detail-page assignment rule — the upstream half of the
`public-detail` contract rejections.

    cd backend && python scripts/cli/mutate_detail_skeleton_assignment.py

Reverts each part of the fix in turn, runs the suites that pin it, reports which
tests caught it, and restores from an **in-memory** backup — never `git checkout`.

Session 11 captured four `slot_fill` rejections live and two of them are the same
defect in two unrelated industries: an About page assigned `public-detail`, whose
contract requires a painting-first hero, an `itemSpecs` binding and an `#inquire`
CTA. This sweep covers the *assignment*, not the contract — fixing the contract
without fixing the assignment would only move the failure.

The blind spots this sweep is written against:

  - **the case that does not bind.** The prose rule and the path rule reach the
    same verdict on a page that is both, so each has a fixture that binds it
    alone: a parameterized path with no prose at all, and prose with no item in
    the path.
  - **guards that cannot fail.** The bracket form and the legacy
    `/services/<x>` path rule are each removed on their own.
  - **the boundary in the other direction.** The booking and utility tests run
    *before* this branch and must keep winning on a parameterized path, and the
    ops branch must not move at all.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

UI_CATALOGUE = BACKEND / "app/application/ui_catalogue.py"

SUITES = (
    "tests/preview_app/test_detail_skeleton_assignment.py "
    "tests/preview_app/test_blueprint_gap_fill.py "
    "tests/preview_app/test_catalogue_contract.py"
)

MUTATIONS = [
    # --- the defect itself ----------------------------------------------------
    (
        UI_CATALOGUE,
        "the bare word 'detail' names a page kind again",
        '            "single product",\n            "single service",',
        '            "detail",\n            "single product",\n            "single service",',
    ),
    # --- the path rule, bound with no prose at all ----------------------------
    (
        UI_CATALOGUE,
        "a parameterized path stops naming an item page",
        '    if path and re.search(r"/(?::[^/]+|\\[[^\\]]+\\])$", path):\n        return "public-detail"',
        "",
    ),
    (
        UI_CATALOGUE,
        "only the `:name` form counts, so `[slug]` stops naming an item page",
        r'    if path and re.search(r"/(?::[^/]+|\[[^\]]+\])$", path):',
        r'    if path and re.search(r"/(?::[^/]+)$", path):',
    ),
    (
        UI_CATALOGUE,
        "the parameter may appear anywhere, so `/book/:step/confirm` becomes an item",
        r'    if path and re.search(r"/(?::[^/]+|\[[^\]]+\])$", path):',
        r'    if path and re.search(r"/(?::[^/]+|\[[^\]]+\])", path):',
    ),
    # --- the phrases that are unambiguous -------------------------------------
    (
        UI_CATALOGUE,
        "the unambiguous multi-word phrases are dropped too",
        '            "single product",\n            "single service",\n            "treatment detail",',
        '            "__never__",',
    ),
    # --- the legacy path rule --------------------------------------------------
    (
        UI_CATALOGUE,
        "the named-service child path stops naming an item page",
        '    if path and re.search(r"/(?:services?|products?|treatments?)/[^/]+$", path):\n        return "public-detail"',
        "",
    ),
    # --- the boundary: this branch must not outrank the ones above it ----------
    (
        UI_CATALOGUE,
        "the item test is hoisted above the booking and utility tests",
        """    # Transactional flows first: judged as marketing pages they would be
    # rejected for missing hero/testimonials and fall back to scaffolds.
    if any(""",
        """    if path and re.search(r"/(?::[^/]+|\\[[^\\]]+\\])$", path):
        return "public-detail"
    # Transactional flows first: judged as marketing pages they would be
    # rejected for missing hero/testimonials and fall back to scaffolds.
    if any(""",
    ),
    # --- the boundary in the other direction ------------------------------------
    (
        UI_CATALOGUE,
        "a listing stops being a catalogue, so the rooms page falls through",
        '        for word in ("catalog", "catalogue", "shop", "store", "browse", "collection", "compare")',
        '        for word in ("__never__",)',
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
