"""Mutation-test the appspec transport model-fallback.

    cd backend && python scripts/cli/mutate_transport_model_fallback.py

Session 20, runs 136/137: a provider-side storm double error-cut both repair
chains — the bounded same-model re-ask fired live and the weather beat it.
Session 21 adds the last rung: when the bounded re-ask is also transport-cut,
one ask on the cross-provider APPSPEC_TRANSPORT_FALLBACK_MODEL before failing
closed. Eleven mutations pin the contract: the fallback fires ONLY on the
transport class (never model malformation, never refusal), asks the fallback
model exactly once with a distinct telemetry attempt, honors the same-model
and unconfigured guards, and its result is actually used. Restores from an
in-memory backup. Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

BUILDER = BACKEND / "app/application/appspec/builder.py"

SUITES = (
    "tests/appspec/test_transport_model_fallback.py "
    "tests/appspec/test_repair_transport_reask.py"
)

MUTATIONS = [
    (
        BUILDER,
        "the authoring tail guard widens: malformation reaches the fallback",
        "    if _is_transport_cut(last_error):\n"
        "        # Every authoring attempt died on weather, not on the model's answer.",
        "    if True:\n"
        "        # Every authoring attempt died on weather, not on the model's answer.",
    ),
    (
        BUILDER,
        "the predicate calls any parse failure transport",
        "    if isinstance(error, AppSpecBuildError):\n"
        '        return dict(error.json_extraction or {}).get("method") == "provider_error"',
        "    if isinstance(error, AppSpecBuildError):\n"
        "        return True",
    ),
    (
        BUILDER,
        "the predicate calls refusal-class raises transport",
        "    if isinstance(error, ProviderGenerationError):\n"
        "        return bool(error.retryable)",
        "    if isinstance(error, ProviderGenerationError):\n"
        "        return True",
    ),
    (
        BUILDER,
        "the same-model guard is deleted: the fallback rides the same storm",
        "    if not fallback_model or fallback_model == primary_model:\n"
        "        return None",
        "    if not fallback_model:\n"
        "        return None",
    ),
    (
        BUILDER,
        "the fallback asks the PRIMARY model instead of the other provider",
        "        try:\n"
        "            raw, provider_diag = _ask_appspec_chat(\n"
        "                ai_provider,\n"
        "                model=fallback_model,",
        "        try:\n"
        "            raw, provider_diag = _ask_appspec_chat(\n"
        "                ai_provider,\n"
        "                model=primary_model,",
    ),
    (
        BUILDER,
        "the helper's fallback attempt flattens to 1: telemetry rows collide",
        "        attempt=_TRANSPORT_REASK_MAX + 2,\n"
        "        transport_error=last_error,",
        "        attempt=1,\n"
        "        transport_error=last_error,",
    ),
    (
        BUILDER,
        "the authoring fallback attempt flattens to 1: telemetry rows collide",
        "                attempt=len(attempt_diagnostics) + 1,\n"
        "                transport_error=last_error,",
        "                attempt=1,\n"
        "                transport_error=last_error,",
    ),
    (
        BUILDER,
        "the helper discards the fallback candidate and fails closed anyway",
        "    if fallback is not None:\n"
        "        return fallback\n"
        "    if isinstance(last_error, AppSpecBuildError):",
        "    if False:\n"
        "        return fallback\n"
        "    if isinstance(last_error, AppSpecBuildError):",
    ),
    (
        BUILDER,
        "authoring discards the fallback candidate and fails closed anyway",
        "        if fallback is not None:\n"
        "            merged = dict(fallback.authoring_diagnostics or {})",
        "        if False:\n"
        "            merged = dict(fallback.authoring_diagnostics or {})",
    ),
    (
        BUILDER,
        "the authoring empty-cut catch is removed: the raise kills the run again",
        "                if not _is_transport_cut(exc):\n"
        "                    raise\n"
        "                transport_raise = exc",
        "                raise\n"
        "                transport_raise = exc",
    ),
    (
        BUILDER,
        "the transport_fallback_used flag is stubbed to False",
        '    merged["transport_fallback_used"] = True',
        '    merged["transport_fallback_used"] = False',
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
