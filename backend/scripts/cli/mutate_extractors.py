"""Mutation-test `tests/test_json_extractor_parity.py` against the extractor fixes.

    cd backend && python scripts/cli/mutate_extractors.py

The standing rule is *mutation-test every guard*: a guard whose success looks
like its failure is this codebase's recurring defect, and a green suite is not
evidence until each test has been shown to go red when the fix it claims to pin
is reverted. The parity suite is especially exposed to this — three of its four
extractors would pass a naive "returns a dict" assertion while returning the
wrong document.

Reverts each fix in turn, runs the parity suite in the documented container,
reports which tests caught it, and restores from an in-memory backup — never
`git checkout`, which has discarded uncommitted work in this repo before.

Exit code is 0 only when every mutation was caught. Re-run after touching any
extractor. Requires Docker and the `bmv-local-api` image.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

#: `"failed" in summary` is wrong: "1 xfailed" contains it, so the day this
#: suite grows an xfail the sweep refuses to start on a green baseline. Count.
_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent

PAGE_EXP = BACKEND / "app/application/services/page_experience.py"
AUTHORING = BACKEND / "app/domain/appspec/authoring_parser.py"
PREPARSE = BACKEND / "app/domain/appspec/sanitize/preparse_normalize.py"

MUTATIONS = [
    (
        "page_experience: shared extractor removed (revert to truncation-first)",
        PAGE_EXP,
        "        value, meta = extract_json_with_meta(raw)",
        '        raise RuntimeError("mutation: shared extractor disabled")',
    ),
    (
        "authoring_parser: repair pass removed",
        AUTHORING,
        "        value, meta = extract_json_with_meta(text)",
        '        raise RuntimeError("mutation: repair disabled")',
    ),
    (
        "authoring_parser: strict direct parse skipped (repair pre-empts strict)",
        AUTHORING,
        "    direct, direct_err = _try_loads(text.strip())",
        '    direct, direct_err = None, "mutation: strict skipped"',
    ),
    (
        "preparse_normalize: shared fallback removed",
        PREPARSE,
        '        value, shared_meta = extract_json_with_meta(raw or "")',
        '        raise RuntimeError("mutation: fallback disabled")',
    ),
    (
        "preparse_normalize: strict path skipped (fallback pre-empts strict)",
        PREPARSE,
        '    if meta.get("ok"):\n        return text, meta',
        "    if False:\n        return text, meta",
    ),
]

PYTEST = (
    "docker run --rm -v {repo}:/repo -w /repo/backend "
    "-e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template "
    "--entrypoint sh bmv-local-api -c "
    "'pip install -q pytest; python -m pytest tests/test_json_extractor_parity.py "
    "-q --no-header -p no:cacheprovider'"
).format(repo=REPO)


def run_suite() -> tuple[bool, str]:
    proc = subprocess.run(PYTEST, shell=True, capture_output=True, text=True, timeout=900)
    out = proc.stdout + proc.stderr
    summary = ""
    for line in reversed(out.strip().splitlines()):
        if "passed" in line or "failed" in line or "error" in line.lower():
            summary = line.strip()
            break
    failed = [
        line.split("::")[-1].split()[0]
        for line in out.splitlines()
        if line.startswith("FAILED")
    ]
    # Read the SUMMARY LINE, never the exit code.
    green = "passed" in summary and not _FAILED_RE.search(summary)
    if failed:
        summary += f"  |  {len(set(failed))} distinct test(s)"
    return green, summary


def main() -> int:
    originals = {path: path.read_text() for path in {m[1] for m in MUTATIONS}}

    green, summary = run_suite()
    print(f"baseline: {summary}")
    if not green:
        print("BASELINE IS RED — fix before mutating")
        return 1

    survivors: list[str] = []
    try:
        for label, path, old, new in MUTATIONS:
            source = originals[path]
            if source.count(old) != 1:
                print(f"!! {label}: anchor matched {source.count(old)} times — NOT APPLIED")
                survivors.append(f"{label} (anchor drift)")
                continue
            path.write_text(source.replace(old, new, 1))
            green, summary = run_suite()
            print(f"\n[{'STILL GREEN <-- pins nothing' if green else 'RED'}] {label}")
            print(f"    {summary}")
            if green:
                survivors.append(label)
            path.write_text(source)
    finally:
        for path, text in originals.items():
            path.write_text(text)
            if path.read_text() != text:
                print(f"RESTORE FAILED for {path}")
                return 2
        print("\nall sources restored and verified byte-identical")

    print(f"\nsurvivors: {survivors or 'none'}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
