#!/usr/bin/env python3
"""Mutation sweep for the session 29 hardening pass (terminal salvage,
attrition guard, exact-duplicate heal, binder state-id collision).

Run inside the test container:
  docker run --rm -v "$PWD:/repo" -w /repo/backend \
    -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
    --entrypoint sh bmv-local-api -c \
    'pip install -q pytest; python /repo/docs/evidence/session29/mutate_hardening.py'
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path("/repo")
HEAL = REPO / "backend/app/domain/appspec/sanitize/heal.py"
GEN = REPO / "backend/app/application/appspec/generation.py"
AI = REPO / "backend/app/application/services/ai_features.py"

T_HARD = ["tests/appspec/test_terminal_salvage_and_attrition.py"]
T_BINDER = ["tests/appspec/test_ai_hub_binder_reconcile.py"]

EXIT4_HOOK = (
    "                # 4) One deterministic pass before losing the run, then the\n"
    "                # safety-net fallback — which is only taken when explicitly\n"
    "                # enabled; with fallback disabled this is the death line.\n"
    "                if _terminal_salvage_pass():\n"
    "                    continue\n"
)

MUT: list[tuple[str, Path, list[str], int, str, str]] = [
    ("R1 restore ignores a missing requirement", HEAL, T_HARD, 1,
     "        if req_id not in requirements:",
     "        if False:"),
    ("R2 restore ignores dangling evidence refs", HEAL, T_HARD, 1,
     "        if not all(e in evidence for e in ev_ids):",
     "        if False:"),
    ("R3 restore duplicates an existing trace row", HEAL, T_HARD, 1,
     "        if not req_id or req_id.casefold() in traced:",
     "        if not req_id:"),
    ("R4 restore skips the capability-claims check", HEAL, T_HARD, 1,
     '            req_id in [str(r) for r in (capabilities[c].get("requirement_ids") or [])]',
     "            True"),
    ("D1 conflicting duplicates dropped as if identical", HEAL, T_HARD, 1,
     "                if seen[item_id] == item:",
     "                if True:"),
    ("D2 duplicate heal fires without the code", HEAL, T_HARD, 1,
     '    if issue_codes & {"duplicate_global_id", "duplicate_id"}:',
     "    if True:"),
    ("G1 terminal salvage disabled", GEN, T_HARD, 1,
     "            if terminal_salvages >= 1 or candidate is None or not candidate.payload:",
     "            if True:"),
    ("G3 attrition wiring removed", GEN, T_HARD, 1,
     "                    if repaired_candidate is not None:",
     "                    if False:"),
    ("G4 exit-4 hook removed", GEN, T_HARD, 1,
     EXIT4_HOOK,
     "                # 4) hook removed by mutation\n"),
    ("S1 foreign hub-ready state collides again", AI, T_BINDER, 1,
     '        and str(s.get("page_id") or "") != hub_id',
     "        and False"),
]


def run(tests: list[str]) -> bool:
    return (
        subprocess.run(
            [sys.executable, "-m", "pytest", *tests, "-q", "-x", "--no-header"],
            cwd=str(REPO / "backend"),
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def main() -> None:
    all_tests = sorted({t for _, _, tests, _, _, _ in MUT for t in tests})
    if not run(all_tests):
        print("baseline RED — fix the tests before sweeping")
        raise SystemExit(2)
    print(f"baseline green; {len(MUT)} mutations\n")

    originals = {p: p.read_text(encoding="utf-8") for p in {m[1] for m in MUT}}
    survivors: list[str] = []
    try:
        for label, target, tests, count, old, new in MUT:
            source = originals[target]
            found = source.count(old)
            if found != count:
                print(f"  MISCOUNT  {label} — anchor x{found}, expected x{count}")
                survivors.append(label)
                continue
            target.write_text(source.replace(old, new), encoding="utf-8")
            killed = not run(tests)
            print(f"  {'kill' if killed else 'SURVIVED'}  {label}")
            if not killed:
                survivors.append(label)
            target.write_text(source, encoding="utf-8")
    finally:
        for path, text in originals.items():
            path.write_text(text, encoding="utf-8")

    print(f"\n{len(MUT) - len(survivors)} killed / {len(survivors)} survived")
    for label in survivors:
        print("  survivor:", label)
    raise SystemExit(1 if survivors else 0)


if __name__ == "__main__":
    main()
