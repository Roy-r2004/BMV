"""Mutation-test request 143's empty-tuple reject-class defenses.

    cd backend && python scripts/cli/mutate_empty_tuple_reject_class.py

Run 143 (Osteria, session 22): the repair chain collapsed a 6-page spec into a
fragment, the schema repair answered an all-empty candidate with a placeholder
`Page1` page carrying `state_ids: []`, and the terminal revision reproduced its
parent's validator errors byte-identically — the session-19 class, 2-for-2
sessions in rejects. Eleven mutations pin the trio: the authoring prompt's
stateless-page floor and its mined Invalid exemplar, the repair prompt's
anti-collapse line, the schema-repair prompt's constructive stateless-page fix,
the identical-error-set early stop (disabled, unwired at either AI dispatch,
over-fired on progress, weakened identity, renamed reason), and the prompt
revision recording the change. Restores from an in-memory backup. Exit code 0
only when every mutation is caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

GENERATION = BACKEND / "app/application/appspec/generation.py"
CONFIG = BACKEND / "app/core/config.py"
APP_SPEC_J2 = BACKEND / "app/templates/prompts/app_spec.j2"
APP_SPEC_REPAIR_J2 = BACKEND / "app/templates/prompts/app_spec_repair.j2"
APP_SPEC_SCHEMA_REPAIR_J2 = (
    BACKEND / "app/templates/prompts/app_spec_schema_repair.j2"
)

SUITES = (
    "tests/appspec/test_repair_identical_error_stop.py "
    "tests/appspec/test_prompt_teaches_reject_shapes.py "
    "tests/appspec/test_request47_trace_reference_reconcile.py"
)

MUTATIONS = [
    (
        APP_SPEC_J2,
        "the stateless-page floor is untaught (9a reverted)",
        "9a. There is no stateless page: every page's `state_ids` names at least one\n"
        "   declared state — an empty `state_ids` tuple is a validation failure, not a\n"
        "   simplification.",
        "9a. Pages may describe their states.",
    ),
    (
        APP_SPEC_J2,
        "the mined Page1 exemplar is dropped from the authoring prompt",
        '   Valid: `{"id": "PAGE-MENU", "state_ids": ["STATE-MENU-READY"]}`.\n'
        '   Invalid: `{"id": "Page1", "state_ids": []}`.',
        "",
    ),
    (
        APP_SPEC_REPAIR_J2,
        "the anti-collapse line is dropped (rev 1's fragment ships unteached)",
        " Returning one sub-object (a single\n"
        "   acceptance test, page, or state) in place of the spec, or emptying `pages` /\n"
        "   `states` that the rejected candidate populated, is a collapse, not a repair —\n"
        "   every object the report does not fault must survive verbatim in your output.",
        "",
    ),
    (
        APP_SPEC_SCHEMA_REPAIR_J2,
        "the stateless-page translation is dropped (7a unteached)",
        "7a. When a page's `state_ids` is empty (\"Tuple should have at least 1 item\"),\n"
        "   that page is stateless: author its default state",
        "7a. Fix empty state_ids as you see fit — author a state",
    ),
    (
        GENERATION,
        "the identical-error-set early stop is disabled",
        "                if (\n"
        "                    awaited_repair_signature is not None\n"
        "                    and _issue_identity_signature(validation_payload)\n"
        "                    == awaited_repair_signature\n"
        "                ):",
        "                if False:",
    ),
    (
        GENERATION,
        "the general AI repair dispatch stops arming the signature",
        "                    repairs += 1\n"
        "                    last_ai_repair_error_signature = _issue_identity_signature(\n"
        "                        validation_payload\n"
        "                    )\n"
        "                    pre_ai_errors",
        "                    repairs += 1\n"
        "                    pre_ai_errors",
    ),
    (
        GENERATION,
        "the schema repair dispatch stops arming the signature",
        "                    schema_ai_repairs += 1\n"
        "                    last_ai_repair_error_signature = _issue_identity_signature(\n"
        "                        validation_payload\n"
        "                    )\n"
        "                    parent_sha",
        "                    schema_ai_repairs += 1\n"
        "                    parent_sha",
    ),
    (
        GENERATION,
        "the stop over-fires on ANY post-repair failure (progress punished)",
        "                    awaited_repair_signature is not None\n"
        "                    and _issue_identity_signature(validation_payload)\n"
        "                    == awaited_repair_signature",
        "                    awaited_repair_signature is not None",
    ),
    (
        GENERATION,
        "the error identity forgets the message (different rejects look identical)",
        '            str(issue.get("path") or ""),\n'
        '            str(issue.get("message") or ""),',
        '            str(issue.get("path") or ""),\n'
        '            "",',
    ),
    (
        GENERATION,
        "the stop hides behind the generic terminal reason",
        '                    return _fallback("repair_reproduced_parent_errors")',
        '                    return _fallback("deterministic_validation_failed")',
    ),
    (
        CONFIG,
        "the prompt revision stops recording the change",
        'os.getenv("APPSPEC_PROMPT_REVISION", "2026-08-07.3").strip()',
        'os.getenv("APPSPEC_PROMPT_REVISION", "2026-08-07.2").strip()',
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
