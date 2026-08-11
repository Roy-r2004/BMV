"""Mutation-test the second family of `placeholder_content_shipped`.

    cd backend && python scripts/cli/mutate_placeholder_gate.py

The check exists because item 1.8 specified this gate on
`early_brand_placeholder_strings()` / `early_brand_placeholder_item_titles()`
and what shipped used only a bracket regex — so for as long as the DoD row has
been scored it measured one of the two families it was meant to catch. Session
26's census found the missing family live on 7 of 87 stored workspaces, two of
them (135, 140) inside the stretch the row was calling clean.

The mutations that matter are this check's two directions of failure, because
both are silent:

* **It stops catching.** The set empties, the guard rejects everything, the
  named titles drop out, the loop stops reporting. A gate that fires on nothing
  looks exactly like a corpus with no defects — which is precisely the reading
  that let this family ship unnoticed for the life of the row.
* **It starts over-catching.** Drop the `"Brand"` co-occurrence guard and it
  fires on 87 of 87 workspaces, because the Brand-default seed's leaves include
  `/gallery`, `60 min` and `Get started`. Match on substrings instead of exact
  leaves and any testimonial containing the phrase blocks a preview. An
  over-firing gate blocks every ship and is *worse* than the narrow one it
  replaced, so the negative tests are pinned as hard as the positive ones.

`docker run`, not `docker compose exec` — see HANDOFF.md for the two ways the
convenient alternative lies about the verdict.

Exit 0 only when every mutation was caught. Restores from an in-memory backup,
never `git checkout`.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

#: "2 xfailed" contains "failed"; count instead of substring-testing.
_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent

GATE = BACKEND / "app/application/preview_app/quality_gate.py"

SUITES = (
    "tests/preview_app/test_placeholder_gate_seed_defaults.py "
    "tests/preview_app/test_quality_gate_fail_codes.py"
)

MUTATIONS: list[tuple[str, Path, str, str]] = [
    (
        "the early-default set empties — the gate catches nothing and looks clean",
        GATE,
        "    early_defaults = {\n        s for s in early_brand_placeholder_strings() if s and \"Brand\" in s\n    } | {",
        "    early_defaults = set() | {",
    ),
    (
        "the named early titles drop out (Everyday essential / Guest favorite)",
        GATE,
        "        if t and (\"Brand\" in t or t in _NAMED_EARLY_TITLES)",
        "        if t and \"Brand\" in t",
    ),
    (
        "the `Brand` co-occurrence guard is dropped — fires on 87 of 87 workspaces",
        GATE,
        "        s for s in early_brand_placeholder_strings() if s and \"Brand\" in s",
        "        s for s in early_brand_placeholder_strings() if s",
    ),
    (
        "exact-leaf comparison becomes a substring scan — real copy blocks the ship",
        GATE,
        "    leaves = {m.group(2).strip() for m in _STRING_LEAF_RE.finditer(mock)}\n    for leaked in sorted(leaves & early_defaults):",
        "    for leaked in sorted(d for d in early_defaults if d in mock):",
    ),
    (
        "the loop finds hits and reports none",
        GATE,
        "    for leaked in sorted(leaves & early_defaults):\n        report.fail(",
        "    for leaked in sorted(leaves & early_defaults)[:0]:\n        report.fail(",
    ),
    (
        "the string-leaf regex stops honouring quotes and swallows the file",
        GATE,
        "_STRING_LEAF_RE = re.compile(r\"\"\"(['\"])((?:\\\\.|(?!\\1)[^\\\\\\n])*)\\1\"\"\")",
        "_STRING_LEAF_RE = re.compile(r\"\"\"(['\"])(.*)\\1\"\"\")",
    ),
    (
        "the second family reports under a different code, so the row never counts it",
        GATE,
        "            \"placeholder_content_shipped\",\n            f\"mock.ts ships the unfilled seed default {leaked!r} as content\",",
        "            \"seed_default_shipped\",\n            f\"mock.ts ships the unfilled seed default {leaked!r} as content\",",
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
                survivors.append(f"[anchor] {label}")
                continue
            path.write_text(source.replace(old, new))
            green, summary, failed = run_suite()
            verdict = "SURVIVED" if green else "caught"
            print(f"{verdict}: {label} — {summary}")
            if green:
                survivors.append(label)
            path.write_text(source)
    finally:
        for path, source in originals.items():
            path.write_text(source)

    print(f"\n{len(MUTATIONS) - len(survivors)}/{len(MUTATIONS)} caught")
    if survivors:
        print("SURVIVORS:")
        for s in survivors:
            print(f"  - {s}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
