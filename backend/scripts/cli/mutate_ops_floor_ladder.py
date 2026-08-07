"""Mutation-test R4's ladder for `ops_kind_too_few_pages` (owner-ruled).

    cd backend && python scripts/cli/mutate_ops_floor_ladder.py

Run 135's accepted 3-page spec seeded its home and then — offline-proven —
refused at the ship gate: the ops gap-fill fired only on non-substantive
tables and the skeleton-keyed unserved test collides on `ops-list`. Ten
mutations pin the ladder: the floor VALUE (never lower the gate — ruled), the
gate deriving from the shared constant, the ops branch firing and being
path-keyed, the fill stopping at the floor, the refusal honoring its opt-in
and its kind guard and the shared floor, the prompt line deriving from the
constant and rendering for ops kinds only, and the builder actually passing
it. Restores from an in-memory backup. Exit code 0 only when every mutation
is caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

PRODUCT_KIND = BACKEND / "app/application/preview_app/product_kind.py"
BUILDER = BACKEND / "app/application/appspec/builder.py"
APP_SPEC_J2 = BACKEND / "app/templates/prompts/app_spec.j2"

SUITES = (
    "tests/preview_app/test_ops_floor_ladder.py "
    "tests/preview_app/test_ops_home_seed.py "
    "tests/preview_app/test_blueprint_gap_fill.py"
)

MUTATIONS = [
    (
        PRODUCT_KIND,
        "the floor is lowered (the ruled never-lower boundary)",
        "OPS_MIN_NON_HUB_PAGES = 4",
        "OPS_MIN_NON_HUB_PAGES = 3",
    ),
    (
        PRODUCT_KIND,
        "the gate stops deriving and duplicates a lower literal",
        "    if len(_non_hub_ops_routes(routes)) < OPS_MIN_NON_HUB_PAGES:\n"
        '        issues.append("ops_kind_too_few_pages")',
        "    if len(_non_hub_ops_routes(routes)) < 3:\n"
        '        issues.append("ops_kind_too_few_pages")',
    ),
    (
        PRODUCT_KIND,
        "the ops gap-fill branch is unwired",
        "    elif (\n"
        "        contract.kind in OPS_KINDS\n"
        "        and len(_non_hub_ops_routes(routes)) < OPS_MIN_NON_HUB_PAGES\n"
        "    ):",
        "    elif False:",
    ),
    (
        PRODUCT_KIND,
        "the ops gap-fill reverts to the skeleton key (the ops-list collision)",
        "            unserved_by_path=True,\n"
        "            stop_at_non_hub_floor=OPS_MIN_NON_HUB_PAGES,",
        "            unserved_by_path=False,\n"
        "            stop_at_non_hub_floor=OPS_MIN_NON_HUB_PAGES,",
    ),
    (
        PRODUCT_KIND,
        "the fill ignores the floor and dumps the whole blueprint",
        "        if (\n"
        "            stop_at_non_hub_floor is not None\n"
        "            and path not in existing_paths\n"
        "            and len(_non_hub_ops_routes(routes)) >= stop_at_non_hub_floor\n"
        "        ):\n"
        "            break",
        "        if False:\n"
        "            break",
    ),
    (
        PRODUCT_KIND,
        "the refusal ignores its opt-in and never fires",
        "    if (\n"
        "        refuse_ops_under_floor\n"
        "        and contract.kind in OPS_KINDS\n"
        "        and len(_non_hub_ops_routes(routes)) < OPS_MIN_NON_HUB_PAGES\n"
        "    ):",
        "    if False:",
    ),
    (
        PRODUCT_KIND,
        "the refusal fires for public kinds too",
        "        refuse_ops_under_floor\n"
        "        and contract.kind in OPS_KINDS\n"
        "        and len(_non_hub_ops_routes(routes)) < OPS_MIN_NON_HUB_PAGES",
        "        refuse_ops_under_floor\n"
        "        and len(_non_hub_ops_routes(routes)) < OPS_MIN_NON_HUB_PAGES",
    ),
    (
        PRODUCT_KIND,
        "the prompt line renders for every kind",
        '    face = (derived_context or {}).get("product_face") or {}\n'
        '    if str(face.get("product_kind") or "") not in OPS_KINDS:\n'
        '        return ""',
        '    face = (derived_context or {}).get("product_face") or {}\n'
        '    if False:\n'
        '        return ""',
    ),
    (
        BUILDER,
        "the builder stops passing the floor block",
        "        ops_floor_block=_ops_floor_block(derived_context or {}),",
        '        ops_floor_block="",',
    ),
    (
        APP_SPEC_J2,
        "the template drops the floor line",
        "{% if ops_floor_block %}\n{{ ops_floor_block }}\n{% endif %}",
        "",
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
