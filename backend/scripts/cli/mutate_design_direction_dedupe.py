"""Mutation-test the design_direction kind-clause dedupe guard.

    cd backend && python scripts/cli/mutate_design_direction_dedupe.py

Reverts each part of the guard in turn, runs the suite that pins it, reports
which tests caught it, and restores from an **in-memory** backup — never
`git checkout`.

Session 14 demoted this from "prompt pollution" to a tidy-up: the append is
real (twice per dict, three times on ops/accounting kinds via the forcer
re-application in plan_phase), but `seal_design_brief` replaces the direction
before any prompt or artifact reads it, so nothing observable changes. The
guard exists so the transient pile-on stops feeding the forcer keyword checks
redundant copies. It is keyed on the FULL `PRODUCT_KIND={kind}/{subtype}`
marker, not the bare `PRODUCT_KIND=` prefix, so a kind flipped by a forcer
still appends its own note — the feedback loop (session 14 finding 1) keeps
today's information content.

The blind spots this sweep is written against:

  - **the case that does not bind.** Same-kind dedupe and flipped-kind append
    are separate fixtures; a bare-prefix guard passes the first and fails the
    second, at both append sites.
  - **guards that cannot fail.** The skip branch's normalising assignment is
    mutated away; the whitespace fixture is what makes it catchable.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

PRODUCT_KIND = BACKEND / "app/application/preview_app/product_kind.py"

SUITES = "tests/preview_app/test_product_kind.py tests/preview_app/test_design_brief.py"

MUTATIONS = [
    # --- the guard itself, at each append site --------------------------------
    (
        PRODUCT_KIND,
        "the plan-site guard is removed: every re-application stacks a clause again",
        """    kind_marker = f"PRODUCT_KIND={contract.kind}/{contract.subtype}"
    if kind_marker in direction:
        # Forcer re-application (plan_phase) lands here 2-3x per run; a kind
        # flip must still append its own note, so key on the full marker.
        updated["design_direction"] = direction
    else:
        updated["design_direction"] = (
            f"{direction} | {kind_marker} (chrome default; "
            f"LLM owns roles/pages from the brief): {contract.design_note}"
        ).strip(" |")""",
        """    updated["design_direction"] = (
        f"{direction} | PRODUCT_KIND={contract.kind}/{contract.subtype} (chrome default; "
        f"LLM owns roles/pages from the brief): {contract.design_note}"
    ).strip(" |")""",
    ),
    (
        PRODUCT_KIND,
        "the architect-site guard is removed: every re-application stacks a clause again",
        """    kind_marker = f"PRODUCT_KIND={contract.kind}/{contract.subtype}"
    if kind_marker in direction:
        # Same guard as apply_product_kind_to_plan: dedupe same-kind
        # re-application, never a flipped kind's note.
        updated["design_direction"] = direction
    else:
        updated["design_direction"] = (
            f"{direction} | {kind_marker}: "
            f"LLM-first inventory; {contract.design_note}"
        ).strip(" |")""",
        """    updated["design_direction"] = (
        f"{direction} | PRODUCT_KIND={contract.kind}/{contract.subtype}: "
        f"LLM-first inventory; {contract.design_note}"
    ).strip(" |")""",
    ),
    # --- the marker the guard keys on -----------------------------------------
    (
        PRODUCT_KIND,
        "the plan-site guard keys on the bare prefix: a flipped kind's note is swallowed",
        '    kind_marker = f"PRODUCT_KIND={contract.kind}/{contract.subtype}"\n'
        "    if kind_marker in direction:\n"
        "        # Forcer re-application (plan_phase) lands here 2-3x per run; a kind",
        '    kind_marker = f"PRODUCT_KIND={contract.kind}/{contract.subtype}"\n'
        '    if "PRODUCT_KIND=" in direction:\n'
        "        # Forcer re-application (plan_phase) lands here 2-3x per run; a kind",
    ),
    (
        PRODUCT_KIND,
        "the architect-site guard keys on the bare prefix: a flipped kind's note is swallowed",
        '    kind_marker = f"PRODUCT_KIND={contract.kind}/{contract.subtype}"\n'
        "    if kind_marker in direction:\n"
        "        # Same guard as apply_product_kind_to_plan: dedupe same-kind",
        '    kind_marker = f"PRODUCT_KIND={contract.kind}/{contract.subtype}"\n'
        '    if "PRODUCT_KIND=" in direction:\n'
        "        # Same guard as apply_product_kind_to_plan: dedupe same-kind",
    ),
    # --- the guard's direction ------------------------------------------------
    (
        PRODUCT_KIND,
        "the plan-site guard is inverted: the clause is never appended at all",
        "    if kind_marker in direction:\n"
        "        # Forcer re-application (plan_phase) lands here 2-3x per run; a kind",
        "    if kind_marker not in direction:\n"
        "        # Forcer re-application (plan_phase) lands here 2-3x per run; a kind",
    ),
    # --- the skip branch must still normalise ---------------------------------
    (
        PRODUCT_KIND,
        "the skip branch stops normalising: a re-application leaves raw whitespace",
        "        # Forcer re-application (plan_phase) lands here 2-3x per run; a kind\n"
        "        # flip must still append its own note, so key on the full marker.\n"
        '        updated["design_direction"] = direction',
        "        # Forcer re-application (plan_phase) lands here 2-3x per run; a kind\n"
        "        # flip must still append its own note, so key on the full marker.\n"
        "        pass",
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
