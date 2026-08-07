"""Mutation-test the repair-path transport re-ask.

    cd backend && python scripts/cli/mutate_repair_transport_reask.py

Session 19, run 123: an error-cut schema_repair stream bypassed the
provider-error gate (no finish_reason threaded) and its fragment consumed the
only schema-repair attempt. Session 20 routes every candidate-shaped ask
through one bounded helper and makes the coverage review refuse an error-cut
stream. Seven mutations: the re-ask loop removed, the retry widened past the
transport class, non-retryable raises swallowed into re-asks, the
finish_reason threading dropped (run 123's exact bug re-created), the coverage
transport check deleted, the diagnostics flag stubbed, and the attempt bump
flattened. Restores from an in-memory backup. Exit code is 0 only when every
mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

BUILDER = BACKEND / "app/application/appspec/builder.py"
COVERAGE = BACKEND / "app/application/appspec/coverage.py"

SUITES = "tests/appspec/test_repair_transport_reask.py"

MUTATIONS = [
    (
        BUILDER,
        "the re-ask loop is removed: one cut ends the repair again",
        "    for attempt_index in range(1 + _TRANSPORT_REASK_MAX):\n"
        "        raw: str | None = None",
        "    for attempt_index in range(1):\n"
        "        raw: str | None = None",
    ),
    (
        BUILDER,
        "the retry widens past the transport class to any parse failure",
        '            transport_cut = dict(exc.json_extraction or {}).get("method") == "provider_error"',
        "            transport_cut = True",
    ),
    (
        BUILDER,
        "non-retryable provider raises are swallowed into re-asks",
        "            except ProviderGenerationError as exc:\n"
        "                if not exc.retryable:\n"
        "                    raise\n"
        "                last_error = exc",
        "            except ProviderGenerationError as exc:\n"
        "                last_error = exc",
    ),
    (
        BUILDER,
        "the finish_reason threading is dropped: run 123's bug returns",
        "        if raw is None:\n"
        "            continue\n"
        "        try:\n"
        "            candidate = _parse_candidate(\n"
        "                raw,\n"
        '                finish_reason=provider_diag.get("finish_reason"),\n'
        "                provider_diagnostics=provider_diag,\n"
        "            )",
        "        if raw is None:\n"
        "            continue\n"
        "        try:\n"
        "            candidate = _parse_candidate(raw)",
    ),
    (
        COVERAGE,
        "the coverage transport check is deleted: cut reviews get adjudicated",
        '    if str(provider_diag.get("finish_reason") or "").lower() == "error":\n'
        "        raise AppSpecCoverageError(\n"
        '            "AppSpec coverage review stream was cut by a provider error "\n'
        '            "(finish_reason=error)"\n'
        "        )\n",
        "",
    ),
    (
        BUILDER,
        "the transport_reask_used flag is stubbed to False",
        '        merged["transport_reask_used"] = attempt_index > 0',
        '        merged["transport_reask_used"] = False',
    ),
    (
        BUILDER,
        "the attempt bump flattens: re-ask rows become indistinguishable",
        '        with ai_call("appspec", writer=writer, attempt=attempt_index + 1):',
        '        with ai_call("appspec", writer=writer, attempt=1):',
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
