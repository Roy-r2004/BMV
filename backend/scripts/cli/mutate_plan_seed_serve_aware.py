"""Mutation-test the serve-aware plan seed and the detail-assignment guard.

    cd backend && python scripts/cli/mutate_plan_seed_serve_aware.py

Session 20, item 5: the plan-stage thin-branch appended the storefront
blueprint (gallery + Artwork detail + nav links) into thin roles with no
serve-aware check, and the explicit-skeleton escape hatch kept planner-assigned
`public-detail` on About/Contact/Private-Dining pages that the detail contract
then rejected wholesale. Nine mutations: the plan-wide wiring dropped, the
serve test inverted, the detail pairing broken, the public-only scope widened,
the browse-token half deleted, the serve set made per-role, the guard deleted,
the guard's anchor loosened to mid-path params, and the id-only rule widened to
titles. Restores from an in-memory backup. Exit code is 0 only when every
mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

PRODUCT_KIND = BACKEND / "app/application/preview_app/product_kind.py"
UI_CATALOGUE = BACKEND / "app/application/ui_catalogue.py"

SUITES = (
    "tests/preview_app/test_plan_seed_serve_aware.py "
    "tests/preview_app/test_plan_detail_assignment.py"
)

MUTATIONS = [
    (
        PRODUCT_KIND,
        "the plan-wide wiring is dropped: every role seeds as before",
        "        _ensure_role_pages(role, contract, plan_served_kinds=plan_served)",
        "        _ensure_role_pages(role, contract)",
    ),
    (
        PRODUCT_KIND,
        "the serve test is inverted",
        "    return bp.skeleton_id in plan_served_kinds",
        "    return bp.skeleton_id not in plan_served_kinds",
    ),
    (
        PRODUCT_KIND,
        "the detail pairing is broken: the child rides alone again",
        "        return not (parent_ids & appended_ids)",
        "        return False",
    ),
    (
        PRODUCT_KIND,
        "the public-only scope is widened to ops seeding",
        '    if plan_served_kinds is None or bp.surface != "public":',
        "    if plan_served_kinds is None:",
    ),
    (
        PRODUCT_KIND,
        "the browse-token half is deleted: under-resolved menus stop serving",
        "            if (leaf and leaf in CATALOG_BROWSE_LEAVES) or (tokens & CATALOG_BROWSE_LEAVES):\n"
        '                served.add("public-catalog")\n',
        "",
    ),
    (
        PRODUCT_KIND,
        "the serve set collapses to per-role: 124's owner role seeds again",
        "    plan_served = _plan_served_kinds(roles)\n"
        "    for role in roles:\n"
        "        if not isinstance(role, dict):\n"
        "            continue\n"
        "        _ensure_role_pages(role, contract, plan_served_kinds=plan_served)",
        "    for role in roles:\n"
        "        if not isinstance(role, dict):\n"
        "            continue\n"
        "        _ensure_role_pages(role, contract, plan_served_kinds=_plan_served_kinds([role]))",
    ),
    (
        UI_CATALOGUE,
        "the detail-assignment guard is deleted: About keeps public-detail",
        '            if skeleton.get("surface") == surface and not (\n'
        '                explicit == "public-detail" and not _explicit_detail_is_anchored(page)\n'
        "            ):\n"
        "                return explicit",
        '            if skeleton.get("surface") == surface:\n'
        "                return explicit",
    ),
    (
        UI_CATALOGUE,
        "the anchor loosens to mid-path params: inquire forms count as items",
        '    if path and re.search(r"/(?::[^/]+|\\[[^\\]]+\\])$", path):\n'
        "        return True\n"
        '    page_id = str(page.get("id") or page.get("page_id") or "").casefold()',
        '    if path and re.search(r"/(?::[^/]+|\\[[^\\]]+\\])", path):\n'
        "        return True\n"
        '    page_id = str(page.get("id") or page.get("page_id") or "").casefold()',
    ),
    (
        UI_CATALOGUE,
        "the id-only rule widens to titles: 'contact details.' anchors again",
        '    page_id = str(page.get("id") or page.get("page_id") or "").casefold()\n'
        "    return bool(_DETAIL_ID_SEGMENT.search(page_id))",
        '    page_id = str(page.get("id") or page.get("page_id") or "").casefold()\n'
        '    blob = f"{page_id} {str(page.get(\'title\') or \'\').casefold()}"\n'
        "    return bool(_DETAIL_ID_SEGMENT.search(blob))",
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
