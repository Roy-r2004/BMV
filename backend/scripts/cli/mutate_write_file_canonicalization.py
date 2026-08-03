"""Mutation-test the `write_file` canonicalization contract.

    cd backend && python scripts/cli/mutate_write_file_canonicalization.py

The last of the eight xfails. `write_file` canonicalizes page names
(`Dashboard.tsx` -> `DashboardPage.tsx`) and **deletes the pre-canonical file**,
which is deliberate — leaving both means the import guards go on to "fix" a
duplicate copy of the page and Vite bundles two of them on a case-sensitive
filesystem. What was wrong was the reporting: callers recorded the path they
passed in, which by then named a file that no longer existed.

Two of these mutations exist because the *tests* were pinning the defect. Three
separate assertions across two files asserted the pre-canonicalize path, so the
bug had test coverage confirming it.

`docker run`, not `docker compose exec` — see HANDOFF.md.

Exit 0 only when every mutation was caught. Restores from an in-memory backup,
never `git checkout`.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

#: "1 xfailed" contains "failed"; count instead of substring-testing.
_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent

WORKSPACE = BACKEND / "app/application/preview_app/workspace.py"
IMPORTS = BACKEND / "app/application/preview_app/safety/imports.py"

SUITES = (
    "tests/preview_app/test_phase5_ui_alias_imports.py "
    "tests/preview_app/test_task3_catalogue_guards.py "
    "tests/preview_app/test_catalogue_contract.py"
)

MUTATIONS: list[tuple[str, Path, str, str]] = [
    # --- the seam ------------------------------------------------------------
    (
        "write_file goes back to returning nothing",
        WORKSPACE,
        "    return normalized\n",
        "    return None\n",
    ),
    (
        "write_file returns the path it was given, not the one it wrote",
        WORKSPACE,
        "    return normalized\n",
        "    return original\n",
    ),
    (
        "write_file returns the caller's raw, un-normalized string",
        WORKSPACE,
        "    return normalized\n",
        "    return rel_path\n",
    ),
    # --- the rename this fix deliberately KEEPS ------------------------------
    (
        "page canonicalization removed (the tempting other way out of the xfail)",
        WORKSPACE,
        "        normalized = canonicalize_page_component_path(normalized)",
        "        normalized = normalized",
    ),
    (
        "pre-canonical file left behind, so the page exists twice",
        WORKSPACE,
        "            if old_path.is_file() and old_path.resolve() != target.resolve():\n"
        "                old_path.unlink()",
        "            if False:\n                old_path.unlink()",
    ),
    # --- the callers ---------------------------------------------------------
    (
        "normalize_ui_kit_imports reports the pre-canonicalize path (the defect)",
        IMPORTS,
        "        touched.append(write_file(workspace, norm, updated))",
        "        write_file(workspace, norm, updated)\n        touched.append(norm)",
    ),
    (
        "strip_forbidden_npm_imports reports the pre-canonicalize path",
        IMPORTS,
        "            touched.append(written)",
        "            touched.append(norm)",
    ),
]

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
    return "passed" in summary and not _FAILED_RE.search(summary), summary, failed


def main() -> int:
    originals = {path: path.read_text() for path in {m[1] for m in MUTATIONS}}

    green, summary, _ = run_suite()
    print(f"baseline: {summary}")
    if not green:
        print("BASELINE IS RED — fix before mutating")
        return 1

    survivors: list[str] = []
    try:
        for label, path, old, new in MUTATIONS:
            source = originals[path]
            if source.count(old) != 1:
                print(
                    f"!! {label}: anchor matched {source.count(old)} times in "
                    f"{path.name} — NOT APPLIED, this mutation tests nothing"
                )
                survivors.append(f"{label} (anchor drift)")
                continue
            path.write_text(source.replace(old, new, 1))
            green, summary, failed = run_suite()
            print(f"\n[{'STILL GREEN <-- pins nothing' if green else 'RED'}] {label}")
            print(f"    {summary}")
            for name in failed:
                print(f"    caught by: {name}")
            if green:
                survivors.append(label)
            path.write_text(source)
    finally:
        for path, source in originals.items():
            path.write_text(source)
            if path.read_text() != source:
                print(f"RESTORE FAILED for {path}")
                return 2
        print("\nsources restored and verified byte-identical")

    print(f"\nsurvivors: {survivors or 'none'}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
