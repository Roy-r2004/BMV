"""Mutation-test the dead-nav-data deletion in sync_mock_roles_navigation.

    cd backend && python scripts/cli/mutate_dead_nav_data.py

Each mutation RE-ADDS a dead writer the session-15 fix deleted, runs the suite
that pins the deletion, and restores from an **in-memory** backup — never
`git checkout`.

Measured over the 67 archived workspaces (docs/evidence/preview-workspaces.tar.gz)
before deleting: 65 navigation objects, every one carrying public+admin, the
extra keys all per-role ids (customer x48, owner x18, staff x8, ...), none ever
`member` — the only other key `app-nav.ts` reads — and zero imports of the
`navItemsAdmin`/`adminNavItems` mock aliases; every generated page takes
`adminNavItems` from the `useAdminNavItems()` hook. The deletion is
behaviour-identical on every archived app; these mutations prove the tests
would catch the writers coming back.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

ASSEMBLE = BACKEND / "app/application/preview_app/assemble.py"

SUITES = (
    "tests/preview_app/test_catalogue_contract.py "
    "tests/preview_app/test_routes_and_nav_dedup.py"
)

MUTATIONS = [
    (
        ASSEMBLE,
        "the per-role navigation keys come back (customer/owner/staff, read by nothing)",
        '''    navigation_data = {"public": public_nav, "admin": admin_nav}

    roles_json = json.dumps(roles_data, indent=2, ensure_ascii=False)''',
        '''    navigation_data = {"public": public_nav, "admin": admin_nav}
    for role in roles_src:
        role_id = role.get("id")
        if not role_id:
            continue
        role_nav = _pin_ai_features_nav(
            _nav_items_for(
                routes,
                lambda rt, rid=role_id: rt.get("role_id") == rid,
            ),
            routes,
        )
        if len(role_nav) < 2 and admin_nav:
            role_nav = list(admin_nav)
        navigation_data[role_id] = role_nav

    roles_json = json.dumps(roles_data, indent=2, ensure_ascii=False)''',
    ),
    (
        ASSEMBLE,
        "the navItemsAdmin/adminNavItems mock aliases come back (imported by nothing)",
        '''            f"export const navigation = {nav_json};",
            updated,
            count=1,
        )
    if updated != mock:''',
        '''            f"export const navigation = {nav_json};",
            updated,
            count=1,
        )
    if "export const navItemsAdmin" not in updated:
        updated = updated.rstrip() + (
            "\\nexport const navItemsAdmin = navigation.admin;\\n"
            "export const adminNavItems = navigation.admin;\\n"
        )
    if updated != mock:''',
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
