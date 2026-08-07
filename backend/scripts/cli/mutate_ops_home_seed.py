"""Mutation-test run 135's ops-home seed fix.

    cd backend && python scripts/cli/mutate_ops_home_seed.py

The dispatch-desk run's accepted internal_ops spec seeded routes at /queue,
/records and /ai-features with nothing at `/`; `validate_product_kind_chrome`
honestly refused the ship (ops_kind_missing_home) after codegen had spent the
run. Seven mutations pin the fix's guards: the re-path fires only for ops
kinds, only when no home exists, only on real ops-surface routes, never
elects the AI hub, prefers the spec's primary (ops-dashboard) page, keeps
role defaultPaths in step, and is actually wired into
lock_chrome_on_architecture_seed. Restores from an in-memory backup. Exit
code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

PRODUCT_KIND = BACKEND / "app/application/preview_app/product_kind.py"

SUITES = "tests/preview_app/test_ops_home_seed.py tests/preview_app/test_product_kind.py"

MUTATIONS = [
    (
        PRODUCT_KIND,
        "the seed fix is unwired: run 135's gap returns",
        "    _ensure_ops_home_route(updated)\n"
        "    for route in updated.get(\"routes\") or []:\n"
        "        if not isinstance(route, dict) or _is_ai_hub_route(route):",
        "    for route in updated.get(\"routes\") or []:\n"
        "        if not isinstance(route, dict) or _is_ai_hub_route(route):",
    ),
    (
        PRODUCT_KIND,
        "the home-exists guard is deleted: existing homes get displaced",
        "    if any(str(rt.get(\"path\") or \"\") in {\"/\", \"/home\"} for rt in routes):\n"
        "        return\n"
        "    candidates = [",
        "    candidates = [",
    ),
    (
        PRODUCT_KIND,
        "the kind guard is bypassed: public kinds get ops re-pathing",
        "    if contract.kind not in OPS_KINDS:\n"
        "        return updated\n"
        "    _ensure_ops_home_route(updated)",
        "    _ensure_ops_home_route(updated)\n"
        "    if contract.kind not in OPS_KINDS:\n"
        "        return updated",
    ),
    (
        PRODUCT_KIND,
        "the ops-surface filter is dropped: mislabeled specs invent a home",
        "        rt\n"
        "        for rt in routes\n"
        "        if not _is_ai_hub_route(rt) and str(rt.get(\"surface\") or \"\") == \"ops\"\n"
        "    ]",
        "        rt\n"
        "        for rt in routes\n"
        "        if not _is_ai_hub_route(rt)\n"
        "    ]",
    ),
    (
        PRODUCT_KIND,
        "the AI-hub exclusion is dropped: the hub can become the home",
        "        rt\n"
        "        for rt in routes\n"
        "        if not _is_ai_hub_route(rt) and str(rt.get(\"surface\") or \"\") == \"ops\"\n"
        "    ]\n"
        "    if not candidates:",
        "        rt\n"
        "        for rt in routes\n"
        "        if str(rt.get(\"surface\") or \"\") == \"ops\"\n"
        "    ]\n"
        "    if not candidates:",
    ),
    (
        PRODUCT_KIND,
        "the dashboard preference is dropped: route order elects the home",
        "    home = next(\n"
        "        (\n"
        "            rt\n"
        "            for rt in candidates\n"
        "            if str(rt.get(\"skeleton_id\") or \"\") == \"ops-dashboard\"\n"
        "        ),\n"
        "        candidates[0],\n"
        "    )",
        "    home = candidates[0]",
    ),
    (
        PRODUCT_KIND,
        "the defaultPath sync is dropped: roles point at a dead path",
        "    old_path = str(home.get(\"path\") or \"\")\n"
        "    home[\"path\"] = \"/\"\n"
        "    for role in seed.get(\"roles\") or []:\n"
        "        if isinstance(role, dict) and str(role.get(\"defaultPath\") or \"\") == old_path:\n"
        "            role[\"defaultPath\"] = \"/\"",
        "    old_path = str(home.get(\"path\") or \"\")\n"
        "    home[\"path\"] = \"/\"",
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
