"""Mutation-test the needs-based blueprint gap-fill — the trattoria's art gallery.

    cd backend && python scripts/cli/mutate_blueprint_gap_fill.py

Reverts each part of the fix in turn, runs the suites that pin it, reports which
tests caught it, and restores from an **in-memory** backup — never `git checkout`.

`product_kind.py:1008-1010` gap-filled `_storefront_pages()` into every
`PUBLIC_KINDS` app *even when `_routes_are_substantive(routes)` was already True*,
and `_storefront_pages()` declares `/gallery` and
`/gallery/:id -> ArtworkDetailPage.tsx` as literals. The gap-fill's only test for
"already served" was an exact path string, so an app with `/menu` or `/rooms` was
told it had no catalogue.

The blind spots this sweep is written against:

  - **two guards that overlap on the obvious fixture** (session 11's four
    survivors). The catalogue test and the detail-parent test both fire on the
    restaurant fixture, so each has a fixture that binds it *alone*: the booking
    contract has no detail page in its blueprint at all, which leaves the kind
    test standing by itself, and the two `/gallery` fixtures put a detail child
    under a parent that is served.
  - **guards that cannot fail.** The `/` exemption, the AI-hub exclusion, the
    plan merge and the page-id fallback are each removed on their own; anything
    that stays green is decoration and should be deleted rather than tested
    around.
  - **the boundary in the other direction.** A thin inventory must still receive
    the whole blueprint, and an app with no catalogue at all must still be given
    one — the rule stops *duplicating* a catalogue, not supplying one.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

PRODUCT_KIND = BACKEND / "app/application/preview_app/product_kind.py"

SUITES = (
    "tests/preview_app/test_blueprint_gap_fill.py "
    "tests/preview_app/test_product_kind.py"
)

MUTATIONS = [
    # --- the defect itself ----------------------------------------------------
    (
        PRODUCT_KIND,
        "the gap-fill goes back to adding every blueprint page to a substantive app",
        """            only_when_unserved=True,
            plan=plan,""",
        """            only_when_unserved=False,
            plan=plan,""",
    ),
    # --- the catalogue test, standing alone on the booking contract ------------
    (
        PRODUCT_KIND,
        "a page the app already serves is gap-filled anyway (the kind test)",
        '            elif path != "/" and bp.skeleton_id in served_kinds:',
        '            elif path != "/" and False:',
    ),
    # --- the two detail-page guards, each bound by its own fixture -------------
    (
        PRODUCT_KIND,
        "a detail page is added even when its listing is not served",
        "                if parent not in existing_paths or any(",
        "                if False or any(",
    ),
    (
        PRODUCT_KIND,
        "a listing that already has a detail child is given a second one",
        "                    _detail_parent_path(other) == parent for other in existing_paths",
        "                    False for other in existing_paths",
    ),
    (
        PRODUCT_KIND,
        "every blueprint path reads as a detail child, so none takes the kind test",
        '    if not sep or not tail.startswith(":"):',
        "    if not sep:",
    ),
    # --- the entry route is an address, not a kind -----------------------------
    (
        PRODUCT_KIND,
        "the root route loses its exemption and a `/home` page suppresses `/`",
        '            elif path != "/" and bp.skeleton_id in served_kinds:',
        "            elif bp.skeleton_id in served_kinds:",
    ),
    # --- what a route is measured against --------------------------------------
    (
        PRODUCT_KIND,
        "the AI hub counts as a page the app serves",
        "        if not isinstance(route, dict) or _is_ai_hub_route(route):\n"
        "            continue\n"
        "        skeleton = _route_page_kind(route, plan_pages)",
        "        if not isinstance(route, dict):\n"
        "            continue\n"
        "        skeleton = _route_page_kind(route, plan_pages)",
    ),
    (
        PRODUCT_KIND,
        "the plan page is dropped, so a route is judged on its own text",
        "    source = {**(page or {}), **route}",
        "    source = dict(route)",
    ),
    (
        PRODUCT_KIND,
        "the route wins nothing — the plan page overwrites its path and title",
        "    source = {**(page or {}), **route}",
        "    source = {**route, **(page or {})}",
    ),
    (
        PRODUCT_KIND,
        "a plan page is only matched when the role id matches too",
        '    page = plan_pages.get((role_id, page_id)) or plan_pages.get(("", page_id))',
        "    page = plan_pages.get((role_id, page_id))",
    ),
    (
        PRODUCT_KIND,
        "an ambiguous page id is matched to whichever role was read first",
        """    for page_id, count in counts.items():
        if count > 1:
            by_role_page.pop(("", page_id), None)""",
        "    pass",
    ),
    # --- the page added one iteration ago is served -----------------------------
    (
        PRODUCT_KIND,
        "a just-added listing is not served, so its detail page never follows it",
        "        existing_paths.add(path)\n        if component not in existing_files:",
        "        if component not in existing_files:",
    ),
    # --- the boundary in the other direction ------------------------------------
    (
        PRODUCT_KIND,
        "a thin inventory is gap-filled instead of being given the whole blueprint",
        "    if not substantive:\n        routes, files, _ = _inject_blueprint_routes(routes, files, contract, role_id)",
        "    if not substantive:\n        routes, files, _ = _inject_blueprint_routes(\n"
        "            routes, files, contract, role_id, only_when_unserved=True, plan=plan\n        )",
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
