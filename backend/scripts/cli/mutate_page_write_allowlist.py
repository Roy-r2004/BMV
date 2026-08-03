"""Mutation-test the DoD 8 page-write allowlist.

    cd backend && python scripts/cli/mutate_page_write_allowlist.py

DoD 8 is a hard guarantee rather than a measurement, which makes it exactly the
kind of guard this repo gets wrong: one whose success is indistinguishable from
its failure. A frame walk that returns the wrong module, a pattern that matches
nothing, an `if` that never fires — all of them look like "no unauthorized
writes" from the outside.

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

SUITES = (
    "tests/preview_app/test_page_write_allowlist.py "
    "tests/preview_app/test_phase5_ui_alias_imports.py "
    "tests/preview_app/test_task3_catalogue_guards.py"
)

MUTATIONS: list[tuple[str, str, str]] = [
    (
        "guard never fires (DoD 8 removed)",
        "    if not _GUARDED_WRITE_RE.match(rel_path):\n        return",
        "    if True:\n        return",
    ),
    (
        "guard records instead of raising, outside audit mode",
        "    raise UnauthorizedPageWrite(",
        "    ws_log.warning(",
    ),
    (
        "pattern misses nested pages",
        r'^src/(?:pages/.+\.(?:tsx|jsx)|render/.+)$',
        r'^src/(?:pages/[^/]+\.(?:tsx|jsx)|render/.+)$',
    ),
    (
        "pattern misses src/render entirely",
        r'^src/(?:pages/.+\.(?:tsx|jsx)|render/.+)$',
        r'^src/pages/.+\.(?:tsx|jsx)$',
    ),
    (
        "pattern swallows every source file",
        r'^src/(?:pages/.+\.(?:tsx|jsx)|render/.+)$',
        r'^src/.+$',
    ),
    (
        "origin walk stops inside workspace, so everything is allowed",
        '        if name and name != __name__:\n            return name',
        "        if name:\n            return name",
    ),
    (
        "allowlist is bypassed for every caller",
        "    if origin in _PAGE_WRITERS or origin.startswith(_TEST_MODULE_PREFIX):",
        "    if True:",
    ),
    (
        "any module whose name starts with app. is allowed",
        '    if origin in _PAGE_WRITERS or origin.startswith(_TEST_MODULE_PREFIX):',
        '    if origin.startswith("app.") or origin.startswith(_TEST_MODULE_PREFIX):',
    ),
    (
        "guard runs before canonicalization, so a rename slips past it",
        "    _check_page_write_allowed(normalized)",
        "    _check_page_write_allowed(original)",
    ),
    (
        "audit mode blocks as well as records (census unusable)",
        '        print(f"PAGE_WRITE_ORIGIN\\t{origin}\\t{rel_path}", flush=True)\n        return',
        '        print(f"PAGE_WRITE_ORIGIN\\t{origin}\\t{rel_path}", flush=True)',
    ),
    (
        "a real writer silently dropped from the allowlist",
        '        "app.application.preview_app.codegen.generate",  # observed',
        "",
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
    original = WORKSPACE.read_text()

    green, summary, _ = run_suite()
    print(f"baseline: {summary}")
    if not green:
        print("BASELINE IS RED — fix before mutating")
        return 1

    survivors: list[str] = []
    try:
        for label, old, new in MUTATIONS:
            if original.count(old) != 1:
                print(
                    f"!! {label}: anchor matched {original.count(old)} times "
                    "— NOT APPLIED, this mutation tests nothing"
                )
                survivors.append(f"{label} (anchor drift)")
                continue
            WORKSPACE.write_text(original.replace(old, new, 1))
            green, summary, failed = run_suite()
            print(f"\n[{'STILL GREEN <-- pins nothing' if green else 'RED'}] {label}")
            print(f"    {summary}")
            for name in failed:
                print(f"    caught by: {name}")
            if green:
                survivors.append(label)
            WORKSPACE.write_text(original)
    finally:
        WORKSPACE.write_text(original)
        if WORKSPACE.read_text() != original:
            print(f"RESTORE FAILED for {WORKSPACE}")
            return 2
        print("\nsource restored and verified byte-identical")

    print(f"\nsurvivors: {survivors or 'none'}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
