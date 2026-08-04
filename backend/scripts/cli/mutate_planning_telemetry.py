"""Mutation-test the planning-phase call scopes and the mid-stream-error verdict.

    cd backend && python scripts/cli/mutate_planning_telemetry.py

Reverts each half of the fix in turn, runs the suites that pin it, reports which
tests caught it, and restores from an **in-memory** backup — never `git checkout`,
which has discarded uncommitted work in this repo before.

Written against the four blind spots that have let mutations survive a first
pass in earlier sessions:

  - **asserting against the case that does not bind.** Deleting one scope leaves
    the other three intact, so a sweep that only mutates `planner` proves
    nothing about `plan_validation` — the writer that had never been observed at
    all. Every scope is removed independently.
  - **driving the consumer and never the producer.** The scopes are the producer;
    `presumed_usable` is a different producer with its own consumer in
    `record_usage`. Both are mutated, and the tests call each directly.
  - **guards that cannot fail.** The billed-tokens condition on the mid-stream
    error is mutated *both* ways: removed (condemns 24 rows of real work) and
    inverted. If neither goes red the condition is decoration.
  - **fixtures too small to reach the rule.** The attempt numbering only binds
    on the second model in a chain, so the mutations that flatten `attempt` are
    driven through a first ask that fails.

Exit code is 0 only when every mutation was caught.

Note the shell: `sh -c`, never `sh -lc`, and `docker run`, not
`docker compose exec` — the compose `api` service mounts only `backend/` and
its login shell drops node, each of which reads as an application defect.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

#: `"failed" in summary` is wrong: "1 xfailed" contains it, so a green suite with
#: one xfail reads as red and the sweep refuses to start. Count instead.
_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

PLANNING = BACKEND / "app/application/services/page_experience.py"
ADMIN_OPS = BACKEND / "app/application/services/admin_ops.py"

SUITES = (
    "tests/application/test_planning_call_telemetry.py "
    "tests/application/test_ai_call_telemetry.py "
    "tests/measure/test_measure_tools.py"
)

MUTATIONS = [
    # --- the scopes: without these the plan phase is billed to codegen --------
    (
        PLANNING,
        "the planner loses its scope (55.98 s billed to codegen, as before)",
        '    with ai_call("planning", writer="planner", attempt=attempt) as call:',
        "    if True:  # noqa\n        call = _NoScope()",
    ),
    (
        PLANNING,
        "the plan validator loses its scope (the writer nobody knew existed)",
        '            with ai_call("planning", writer="plan_validation", attempt=attempt) as call:',
        "            if True:  # noqa\n                call = _NoScope()",
    ),
    (
        PLANNING,
        "plan expansion loses its scope",
        '            with ai_call("planning", writer="plan_expansion", attempt=attempt) as call:',
        "            if True:  # noqa\n                call = _NoScope()",
    ),
    (
        PLANNING,
        "the design manifest loses its scope",
        '        with ai_call("planning", writer="design_manifest", attempt=1) as call:',
        "        if True:  # noqa\n            call = _NoScope()",
    ),
    # --- the stage name: `codegen` is exactly the wrong answer ----------------
    (
        PLANNING,
        "the planner is scoped to codegen (the mis-attribution, made explicit)",
        '    with ai_call("planning", writer="planner", attempt=attempt) as call:',
        '    with ai_call("codegen", writer="planner", attempt=attempt) as call:',
    ),
    # --- attempt numbering: appspec's re-asks were invisible this way ---------
    (
        PLANNING,
        "every planner ask is attempt 1 again (a re-ask reads as a first try)",
        "    with ai_call(\"planning\", writer=\"planner\", attempt=attempt) as call:",
        "    with ai_call(\"planning\", writer=\"planner\", attempt=1) as call:",
    ),
    (
        PLANNING,
        "the validator's two asks are both attempt 1",
        '            with ai_call("planning", writer="plan_validation", attempt=attempt) as call:',
        '            with ai_call("planning", writer="plan_validation", attempt=1) as call:',
    ),
    (
        PLANNING,
        "the planner chain stops passing its position (attempt always defaults)",
        "                canonical_seed,\n                attempt=attempt,",
        "                canonical_seed,",
    ),
    # --- the usability verdicts ----------------------------------------------
    (
        PLANNING,
        "a roles-less planner answer is presumed usable (7-15 s reported as spent well)",
        '        call.adjudicate(bool(plan and plan.get("roles")), reason=UNUSABLE_REJECTED)\n',
        "",
    ),
    (
        PLANNING,
        "the validator never adjudicates its answer",
        # `plan_validation` and `plan_expansion` adjudicate with the same line,
        # so the writer above it is the only thing that makes this anchor unique.
        # The first version of this mutation matched twice and applied nothing.
        '            with ai_call("planning", writer="plan_validation", attempt=attempt) as call:\n'
        '                raw = ai_provider.ask_chat(model, [{"role": "user", "content": prompt}], max_tokens=14000)\n'
        "                result = _parse_json_from_response(raw)\n"
        '                call.adjudicate(bool(result and result.get("roles")), reason=UNUSABLE_REJECTED)\n',
        '            with ai_call("planning", writer="plan_validation", attempt=attempt) as call:\n'
        '                raw = ai_provider.ask_chat(model, [{"role": "user", "content": prompt}], max_tokens=14000)\n'
        "                result = _parse_json_from_response(raw)\n",
    ),
    (
        PLANNING,
        "the validator keeps asking after a usable answer (its 34-48 s second ask)",
        "            if result and result.get(\"roles\"):\n                return _normalize_plan(result, primary, \"\")",
        "            if result and result.get(\"roles\"):\n                plan = _normalize_plan(result, primary, \"\")",
    ),
    # --- presumed_usable: the mid-stream error -------------------------------
    (
        ADMIN_OPS,
        "mid-stream errors are presumed usable again (15 rows, 114.4 s)",
        '    if str(finish_reason or "").lower() == "error" and int(completion_tokens or 0) <= 0:\n        return False, UNUSABLE_TRANSPORT\n',
        "",
    ),
    (
        ADMIN_OPS,
        "the billed-tokens guard is dropped (condemns 24 rows of real work)",
        '    if str(finish_reason or "").lower() == "error" and int(completion_tokens or 0) <= 0:',
        '    if str(finish_reason or "").lower() == "error":',
    ),
    (
        ADMIN_OPS,
        "the billed-tokens guard is inverted",
        '    if str(finish_reason or "").lower() == "error" and int(completion_tokens or 0) <= 0:',
        '    if str(finish_reason or "").lower() == "error" and int(completion_tokens or 0) > 0:',
    ),
    (
        ADMIN_OPS,
        "record_usage stops forwarding the token count (the seam, not the rule)",
        "        completion_tokens=completion_tokens,\n    )",
        "    )",
    ),
    # --- the census's own arithmetic -----------------------------------------
    (
        BACKEND / "scripts/measure/codegen_cost.py",
        "unscoped rows are folded into a writer bucket instead of named",
        '    if architect_start is None:\n        return UNATTRIBUTED_UNKNOWN',
        '    if architect_start is None:\n        return "slot_fill"',
    ),
    (
        BACKEND / "scripts/measure/codegen_cost.py",
        "the architect boundary is the call's END, not its start",
        "        began = float(row[\"ts\"]) - _seconds(row)\n        current = starts[rid]",
        "        began = float(row[\"ts\"])\n        current = starts[rid]",
    ),
    (
        BACKEND / "scripts/measure/codegen_cost.py",
        "a run with no architect row defaults its boundary to zero",
        # Written first as `(architect_start or 0.0)` in the comparison, which
        # the early return above makes unreachable — a mutation that cannot
        # change an outcome reports SURVIVED and means nothing. It has to
        # remove the early return to reach the behaviour it claims to test.
        "    if architect_start is None:\n        return UNATTRIBUTED_UNKNOWN",
        "    if architect_start is None:\n        architect_start = 0.0",
    ),
]

REPO = BACKEND.parent
PYTEST = (
    f'docker run --rm -v "{REPO}:/repo" -w /repo/backend '
    "-e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api "
    f"-c 'pip install -q pytest 2>/dev/null; python -m pytest {SUITES} "
    "-q --no-header -p no:cacheprovider'"
)

#: Injected alongside the scope mutations so a de-scoped body still runs. Without
#: it every scope mutation dies on `NameError: call` and reports "caught" for a
#: reason that has nothing to do with telemetry.
NO_SCOPE_SHIM = '''

class _NoScope:
    """Stand-in for a missing `ai_call` scope, for mutation runs only."""

    stage = writer = None
    attempt = 1
    usable = None

    def adjudicate(self, *_args, **_kwargs) -> None:
        return None
'''


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
    # Read the SUMMARY LINE, never the exit code.
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
            # Anchor drift is the most valuable refusal in this script: an
            # anchor that no longer matches applies nothing and reports a pass.
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
            if "_NoScope()" in new:
                mutated += NO_SCOPE_SHIM

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
