#!/usr/bin/env python3
"""Mutation sweep for the seed model failover (session 28).

Each mutation is a behavioural change to `_synthesize_mock_source`. A survivor
means the tests do not pin that behaviour.

    python3 mutate_seed_failover.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TARGET = Path("/repo/backend/app/application/preview_app/codegen/mock.py")
TESTS = [
    "tests/preview_app/test_seed_model_failover.py",
    "tests/preview_app/test_mandatory_stage_deterministic_paths.py",
]

MUTATIONS: list[tuple[str, str, str]] = [
    (
        "m1 no failover at all — the pre-fix behaviour",
        "    chain = _seed_model_chain()\n",
        "    chain = _seed_model_chain()[:1]\n",
    ),
    (
        "m2 chain not deduped — one model asked three times",
        "    return list(\n        dict.fromkeys(",
        "    return list(\n        (",
    ),
    (
        "m3 budget never checked",
        "        if attempt > 1 and ask_budget_seconds()",
        "        if attempt > 99 and ask_budget_seconds()",
    ),
    (
        "m4 floor is zero — a link with no time still starts",
        "_SEED_FAILOVER_FLOOR_SECONDS = 70.0",
        "_SEED_FAILOVER_FLOOR_SECONDS = 0.0",
    ),
    (
        "m5 out of time keeps looping instead of stopping",
        '            record_degradation("codegen", "mock_synthesis_failover_out_of_time")\n            return None',
        '            record_degradation("codegen", "mock_synthesis_failover_out_of_time")\n            continue',
    ),
    (
        "m6 a rejection is recorded as a provider failure",
        "    if provider_failed:\n        record_degradation",
        "    if True:\n        record_degradation",
    ),
    (
        "m7 every link numbered attempt 1 — the chain collapses to one row",
        'with ai_call("seed", writer="mock_synthesize", attempt=attempt) as call:',
        'with ai_call("seed", writer="mock_synthesize", attempt=1) as call:',
    ),
    (
        "m8 a rejected answer ends the chain instead of failing over",
        "                call.unusable(UNUSABLE_REJECTED)",
        "                call.unusable(UNUSABLE_REJECTED)\n                return None",
    ),
    (
        "m9 a transport failure is not remembered",
        "            provider_failed = True",
        "            provider_failed = False",
    ),
    # m10 (`return content or None`) is an EQUIVALENT mutant and is recorded as
    # one rather than chased: `_valid_synthesized_mock_source` opens with
    # `if not content.strip(): return False`, so the success path is
    # unreachable with falsy content and the two forms cannot differ. Verified
    # directly — v("", ...), v("   ", ...) and v("\n", ...) are all False.
    # m10b is its meaningful form, and it is killed.
    (
        "m10b valid output is dropped on the floor",
        "                    call.mark_usable()\n                    return content",
        "                    call.mark_usable()\n                    return None",
    ),
]


def run_tests() -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *TESTS, "-q", "-x", "--no-header"],
        cwd="/repo/backend",
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def main() -> None:
    original = TARGET.read_text(encoding="utf-8")
    if not run_tests():
        print("baseline is RED — fix that first")
        raise SystemExit(2)
    print(f"baseline green; {len(MUTATIONS)} mutations\n")

    survivors = []
    try:
        for label, old, new in MUTATIONS:
            if old not in original:
                print(f"  SKIP  {label} — anchor not found")
                survivors.append(f"{label} (anchor missing)")
                continue
            TARGET.write_text(original.replace(old, new, 1), encoding="utf-8")
            killed = not run_tests()
            print(f"  {'kill' if killed else 'SURVIVED'}  {label}")
            if not killed:
                survivors.append(label)
    finally:
        TARGET.write_text(original, encoding="utf-8")

    print(f"\n{len(MUTATIONS) - len(survivors)} killed / {len(survivors)} survived")
    for s in survivors:
        print(f"  survivor: {s}")
    raise SystemExit(1 if survivors else 0)


if __name__ == "__main__":
    main()
