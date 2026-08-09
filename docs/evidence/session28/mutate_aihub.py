#!/usr/bin/env python3
"""Mutation sweep for the AI-hub initial-state fix (session 28)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

T = Path("/repo/backend/app/application/services/ai_features.py")
TESTS = ["tests/appspec/test_ai_hub_initial_state.py"]

GUARD = '            str(s.get("id") or "").casefold() in hub_existing and s.get("initial")'

MUT = [
    ("a1 the injected state is always initial again",
     '                "initial": not page_already_has_initial,',
     '                "initial": True,'),
    ("a2 the injected state is never initial",
     '                "initial": not page_already_has_initial,',
     '                "initial": False,'),
    ("a3 a non-initial state on the page also suppresses it",
     GUARD,
     '            str(s.get("id") or "").casefold() in hub_existing'),
    ("a4 an initial state on any other page suppresses it",
     GUARD,
     '            s.get("initial")'),
]


def run() -> bool:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *TESTS, "-q", "-x", "--no-header"],
        cwd="/repo/backend", capture_output=True, text=True,
    ).returncode == 0


def main() -> None:
    orig = T.read_text(encoding="utf-8")
    if not run():
        print("baseline RED")
        raise SystemExit(2)
    print(f"baseline green; {len(MUT)} mutations\n")
    surv: list[str] = []
    try:
        for label, old, new in MUT:
            if old not in orig:
                print(f"  SKIP  {label} — anchor not found")
                surv.append(label)
                continue
            T.write_text(orig.replace(old, new, 1), encoding="utf-8")
            killed = not run()
            print(f"  {'kill' if killed else 'SURVIVED'}  {label}")
            if not killed:
                surv.append(label)
            T.write_text(orig, encoding="utf-8")
    finally:
        T.write_text(orig, encoding="utf-8")
    print(f"\n{len(MUT) - len(surv)} killed / {len(surv)} survived")
    for s in surv:
        print("  survivor:", s)
    raise SystemExit(1 if surv else 0)


if __name__ == "__main__":
    main()
