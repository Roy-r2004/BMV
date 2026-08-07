"""Mutation-test the provider-error gate in the AppSpec authoring parser.

    cd backend && python scripts/cli/mutate_appspec_provider_error.py

Session 19: gemini-2.5-flash returned error-cut partial streams (HTTP 200,
finish_reason=error, 0 output tokens) and the parser's fragment strategies
extracted small complete objects out of them, adjudicated them as candidates,
and failed four funded runs as spec rejections. The gate refuses fragment
extraction on an error-cut stream and classifies it truncated (retryable), so
the authoring loop re-asks the provider.

Five mutations: the gate deleted, its condition inverted, its typed code
downgraded out of the honest class, its truncated flag dropped, and the
builder's retryable set losing the truncated code. Restores from an in-memory
backup. Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

PARSER = BACKEND / "app/domain/appspec/authoring_parser.py"
BUILDER = BACKEND / "app/application/appspec/builder.py"

SUITES = (
    "tests/appspec/test_authoring_provider_error.py "
    "tests/appspec/test_request43_authoring_parser.py"
)

MUTATIONS = [
    (
        PARSER,
        "the gate is deleted: error-cut fragments become candidates again",
        '    if str(finish_reason or "").lower() == "error":\n'
        "        return _fail(\n"
        "            code=AUTHORING_JSON_TRUNCATED,\n"
        '            strategy="provider_error",\n'
        "            raw=text,\n"
        '            parser_error="provider_error_cut_stream",\n'
        '            extra={"finish_reason": finish_reason, "truncated": True},\n'
        "        )\n",
        "",
    ),
    (
        PARSER,
        "the condition is inverted: healthy streams fail, error streams pass",
        'if str(finish_reason or "").lower() == "error":',
        'if str(finish_reason or "").lower() != "error":',
    ),
    (
        PARSER,
        "the typed code is downgraded to syntax-invalid",
        "            code=AUTHORING_JSON_TRUNCATED,\n"
        '            strategy="provider_error",',
        "            code=AUTHORING_JSON_SYNTAX_INVALID,\n"
        '            strategy="provider_error",',
    ),
    (
        PARSER,
        "the truncated flag is dropped from diagnostics",
        'extra={"finish_reason": finish_reason, "truncated": True},',
        'extra={"finish_reason": finish_reason},',
    ),
    (
        BUILDER,
        "the builder stops retrying truncated authoring output",
        "                AUTHORING_JSON_TRUNCATED,\n",
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
