"""Mutation-test the appspec prompt hardening.

    cd backend && python scripts/cli/mutate_appspec_prompt_hardening.py

Sessions 18-19's quality-reject shapes (transport artifacts excluded) are now
taught in `app_spec.j2` and translated in `app_spec_repair.j2`, with the prompt
revision bumped so reject rates stay queryable per revision. Seven mutations:
each of the five taught authoring rules deleted, the repair translation
deleted, and the revision bump reverted. Restores from an in-memory backup.
Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

AUTHORING = BACKEND / "app/templates/prompts/app_spec.j2"
REPAIR = BACKEND / "app/templates/prompts/app_spec_repair.j2"
CONFIG = BACKEND / "app/core/config.py"

SUITES = (
    "tests/appspec/test_prompt_teaches_reject_shapes.py "
    "tests/appspec/test_request47_trace_reference_reconcile.py"
)

MUTATIONS = [
    (
        AUTHORING,
        "exactly-one initial state reverts to the old at-least-one wording",
        "9. Every stateful page has EXACTLY ONE initial state: of the states a page's\n"
        "   `state_ids` lists, exactly one carries `\"initial\": true` and every sibling\n"
        "   carries `\"initial\": false` — two initial states on one page is a validation\n"
        "   failure, not emphasis. Each state's `page_id` must be the one page whose\n"
        "   `state_ids` lists it. Actions identify",
        "9. Every stateful page has an explicit initial state. Actions identify",
    ),
    (
        AUTHORING,
        "the per-kind assertion rule is deleted",
        "12a. Every assertion carries the reference its kind requires: a `route`\n"
        "    assertion requires `page_id`; a `visible` assertion requires `evidence_id`;\n"
        "    a `state` assertion requires `state_id` — never emit a state assertion\n"
        "    without one. The referenced state or evidence must belong to the page the\n"
        "    assertion names.\n",
        "",
    ),
    (
        AUTHORING,
        "declare-before-cite reverts to the bare resolve sentence",
        "17. Every reference must resolve, and DECLARE BEFORE YOU CITE: any ID written\n"
        "    into an `*_id` / `*_ids` field must exist as a declared object in its\n"
        "    top-level collection — never cite an EVIDENCE-* ID in a page, journey step,\n"
        "    assertion, or traceability row without adding the matching item to the\n"
        "    `evidence` array itself. Output must validate",
        "17. Every reference must resolve. Output must validate",
    ),
    (
        AUTHORING,
        "the minItems floor shrinks back to trace collections only",
        " The same\n"
        "   floor applies OUTSIDE traceability: every capability's `role_ids` and every\n"
        "   page's `capability_ids`, `evidence_ids`, and `state_ids` must each name at\n"
        "   least one declared ID.",
        "",
    ),
    (
        AUTHORING,
        "trace-or-defer is deleted from rule 16",
        " Every\n"
        "    requirement must end up EITHER traced in `traceability` OR listed in\n"
        "    `deferred_scope` — a requirement in neither place is a validation failure.",
        "",
    ),
    (
        REPAIR,
        "the repair translation of the recurring codes is deleted",
        "   The recurring codes have exact fixes:\n"
        "   - `state_assertion_state_required`: add the missing `state_id` to that\n"
        "     state-kind assertion (a state on the asserted page), or change its kind.\n"
        "   - `missing_reference`: the cited ID does not exist — either declare the\n"
        "     missing object in its top-level collection (for example add the cited\n"
        "     EVIDENCE-* item to `evidence`) or stop citing it.\n"
        "   - `page_initial_state_count`: keep EXACTLY ONE `\"initial\": true` state per\n"
        "     page's `state_ids`, set every sibling to `\"initial\": false`, and make each\n"
        "     state's `page_id` match the one page listing it.\n",
        "",
    ),
    (
        CONFIG,
        "the prompt revision reverts: reject rates stop being attributable",
        'os.getenv("APPSPEC_PROMPT_REVISION", "2026-08-07.1").strip()',
        'os.getenv("APPSPEC_PROMPT_REVISION", "2026-07-28.2").strip()',
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
