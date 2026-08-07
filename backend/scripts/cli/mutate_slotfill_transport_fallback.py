"""Mutation-test R1+R2 at slot_fill: the cross-provider rung and the live translation.

    cd backend && python scripts/cli/mutate_slotfill_transport_fallback.py

1.12(b): an unroutable page writer shipped bare scaffolds to the gate —
slot_fill had NO fallback and its bare `except Exception: break` classified
nothing. Thirteen mutations pin the new contract: the predicate is exactly the
retryable transport class, the rung fires only from a recorded transport cut,
asks the cross-provider model once under a distinct telemetry attempt, its
answer faces the same judge and is adjudicated honestly, the unconfigured /
same-model / low-runway guards fail closed (and skipping is never silent),
the startup warning covers the new pair, and the contract retry's translation
reaches the LIVE attempt-2 prompt (request 107's lesson — the old pin drove a
path production never takes). Restores from an in-memory backup. Exit code 0
only when every mutation is caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

GENERATE = BACKEND / "app/application/preview_app/codegen/generate.py"
SHARED = BACKEND / "app/application/preview_app/codegen/shared.py"
CONFIG = BACKEND / "app/core/config.py"

SUITES = (
    "tests/preview_app/test_slotfill_transport_fallback.py "
    "tests/preview_app/test_slotfill_retry.py"
)

MUTATIONS = [
    (
        GENERATE,
        "the predicate widens: refusal-class raises reach the rung",
        "    return isinstance(exc, ProviderGenerationError) and bool(exc.retryable)",
        "    return isinstance(exc, ProviderGenerationError)",
    ),
    (
        GENERATE,
        "the loop forgets the transport cut: the rung never learns of it",
        "                    transport_exc = exc",
        "                    transport_exc = None",
    ),
    (
        GENERATE,
        "the rung is unwired",
        "    if transport_exc is not None:",
        "    if False:",
    ),
    (
        GENERATE,
        "the rung asks the PRIMARY model instead of the other provider",
        "                    raw = ai_provider.ask_chat(\n"
        "                        fallback_model,",
        "                    raw = ai_provider.ask_chat(\n"
        "                        primary_model,",
    ),
    (
        GENERATE,
        "the rung's attempt flattens to 1: telemetry rows collide",
        '            "codegen", writer="slot_fill", attempt=_MAX_SLOT_FILL_ATTEMPTS + 1',
        '            "codegen", writer="slot_fill", attempt=1',
    ),
    (
        GENERATE,
        "the unconfigured guard is deleted: an empty model gets asked",
        "        if (\n"
        "            fallback_model\n"
        "            and fallback_model != primary_model",
        "        if (\n"
        "            True\n"
        "            and fallback_model != primary_model",
    ),
    (
        GENERATE,
        "the same-model guard is deleted: the fallback rides the same storm",
        "            and fallback_model != primary_model\n"
        "            and _has_transport_fallback_runway()",
        "            and _has_transport_fallback_runway()",
    ),
    (
        GENERATE,
        "the runway gate is deleted: the rung spends time the tail needs",
        "            and _has_transport_fallback_runway()\n"
        "        ):",
        "        ):",
    ),
    (
        GENERATE,
        "the skipped rung is silent (no degradation recorded)",
        '    record_degradation("codegen", "slot_fill_transport_fallback_skipped_low_runway")',
        "    pass",
    ),
    (
        GENERATE,
        "the fallback's answer ships unjudged",
        "                    if not reason:\n"
        "                        content = filled\n"
        "                    else:",
        "                    if True:\n"
        "                        content = filled\n"
        "                    else:",
    ),
    (
        GENERATE,
        "a rejected fallback fill is adjudicated usable",
        "                    call.adjudicate(not reason, reason=UNUSABLE_REJECTED)",
        "                    call.adjudicate(True, reason=UNUSABLE_REJECTED)",
    ),
    (
        GENERATE,
        "the live contract retry drops the translation (request 107 regresses)",
        "                    guidance=_SLOT_FILL_RETRY_GUIDANCE[CONTRACT_REJECTION],\n",
        "",
    ),
    (
        SHARED,
        "the retry context never renders its guidance section",
        '    guidance_section = f"How to repair: {guidance}\\n" if guidance else ""',
        '    guidance_section = ""',
    ),
    (
        CONFIG,
        "the page-writer pair drops out of the startup warning",
        '        for slot in ("PREVIEW_APP_MODEL",)',
        "        for slot in ()",
    ),
    (
        CONFIG,
        "startup never checks the page-writer pair",
        "    warn_same_provider_transport_fallback(config)\n"
        "    warn_same_provider_preview_app_fallback(config)",
        "    warn_same_provider_transport_fallback(config)",
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
