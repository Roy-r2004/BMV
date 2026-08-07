"""Mutation-test the planning writers' routing off haiku.

    cd backend && python scripts/cli/mutate_planning_writer_models.py

Session 18: `design_manifest` returned 0 chars at exactly its 1,500-token cap
on every run and `plan_validation` did the same at 14,000 on both baseline
runs — ARCHITECT_MODEL (haiku-4.5) burns the budget on reasoning before any
text. Both writers now ask TEXT_MODEL first; the architect slot is only
plan_validation's fallback. Three mutations: each writer reverted to the
architect model, and the fallback order flipped back. Restores from an
in-memory backup. Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

PAGE_EXPERIENCE = BACKEND / "app/application/services/page_experience.py"

SUITES = "tests/preview_app/test_planning_writers_route_off_haiku.py"

MUTATIONS = [
    (
        PAGE_EXPERIENCE,
        "design_manifest reverts to the architect model",
        'raw = ai_provider.ask_chat(settings.TEXT_MODEL, [{"role": "user", "content": prompt}], max_tokens=1500)',
        'raw = ai_provider.ask_chat(settings.ARCHITECT_MODEL, [{"role": "user", "content": prompt}], max_tokens=1500)',
    ),
    (
        PAGE_EXPERIENCE,
        "plan_validation's order flips back to architect-first",
        'for attempt, model in enumerate((settings.TEXT_MODEL, settings.ARCHITECT_MODEL), start=1):\n'
        "        try:\n"
        '            with ai_call("planning", writer="plan_validation", attempt=attempt) as call:',
        'for attempt, model in enumerate((settings.ARCHITECT_MODEL, settings.TEXT_MODEL), start=1):\n'
        "        try:\n"
        '            with ai_call("planning", writer="plan_validation", attempt=attempt) as call:',
    ),
    (
        PAGE_EXPERIENCE,
        "plan_validation loses its fallback entirely",
        'for attempt, model in enumerate((settings.TEXT_MODEL, settings.ARCHITECT_MODEL), start=1):\n'
        "        try:\n"
        '            with ai_call("planning", writer="plan_validation", attempt=attempt) as call:',
        'for attempt, model in enumerate((settings.TEXT_MODEL,), start=1):\n'
        "        try:\n"
        '            with ai_call("planning", writer="plan_validation", attempt=attempt) as call:',
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
