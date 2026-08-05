"""Mutation-test 1.12 — the deterministic paths for MANDATORY stages.

    cd backend && python scripts/cli/mutate_mandatory_deterministic_paths.py

Reverts each part of the fix in turn, runs the suites that pin it, reports which
tests caught it, and restores from an **in-memory** backup — never `git checkout`.

Five runs shipped NULL because three MANDATORY stages had no deterministic path
(74, 92, 94, 101, 102). Every piece of the fix is a *widened `except`*, and the
characteristic failure of a widened `except` is that it starts catching the
healthy case — so roughly half the mutations here push the fallback **onto the
normal path** rather than removing it, and the fixtures that catch those are the
healthy-run ones.

The blind spots this sweep is written against:

  - **the case that does not bind.** The shadow fallback and the enforced rescue
    reach the same statement from different branches, so each is mutated alone:
    the shadow one by reverting it to `raise`, the enforced one by letting the
    shadow logic reach it.
  - **guards that cannot fail.** `store_crash_record`'s three refusals — no
    workspace, an already-`ready` record, and its own bookkeeping failure — are
    removed one at a time.
  - **a fix that changes no outcome.** The blueprint must come from the
    *resolved* contract, so one mutation hands the fallback a route table that
    is already substantive: the dentist then keeps an art gallery and only the
    kind-specific fixture notices.
  - **anchors that match twice.** Every anchor is counted before it is applied;
    a multiple match is reported as a survivor rather than silently skipped.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

PLAN_PHASE = BACKEND / "app/application/preview_app/pipeline/plan_phase.py"
MOCK = BACKEND / "app/application/preview_app/codegen/mock.py"
FINALIZE = BACKEND / "app/application/preview_app/pipeline/finalize.py"
ORCHESTRATOR = BACKEND / "app/application/preview_app/pipeline/orchestrator.py"
PAGE_EXPERIENCE = BACKEND / "app/application/services/page_experience.py"

SUITES = (
    "tests/preview_app/test_mandatory_stage_deterministic_paths.py "
    "tests/preview_app/test_architect_deadline.py "
    "tests/preview_app/test_withheld_reason_is_published.py "
    "tests/application/test_planning_call_telemetry.py"
)

MUTATIONS = [
    # --- (a) the shadow architect fallback -----------------------------------
    (
        PLAN_PHASE,
        "(a) the shadow architect fallback is reverted to a raise",
        """            record_degradation("architect", "call_failed_deterministic_blueprint")""",
        """            raise""",
    ),
    (
        PLAN_PHASE,
        "(a) the fallback ships the blueprint but records nothing",
        """            record_degradation("architect", "call_failed_deterministic_blueprint")\n""",
        "",
    ),
    (
        PLAN_PHASE,
        "(a) the degradation is recorded under a reason nothing reads",
        '''record_degradation("architect", "call_failed_deterministic_blueprint")''',
        '''record_degradation("architect", "architect_failed")''',
    ),
    (
        PLAN_PHASE,
        "(a) the shadow branch reaches the enforced rescue too",
        "        if ctx.enforce_app_spec and ctx.app_spec_result and ctx.app_spec_scope:\n"
        "            # Enforced mode rescues from the AppSpec projection below. Unchanged.\n"
        "            architect = {}",
        "        if False:\n"
        "            architect = {}",
    ),
    (
        PLAN_PHASE,
        "(a) the fallback seeds a substantive table, so the contract never fires",
        # Anchored on the *last* statement of the branch. Anchoring on
        # `record_degradation` instead put the seed above the `architect = {}`
        # that then overwrote it — applied, and semantically a no-op. The bare
        # `architect = {}` cannot be the anchor either: it appears in both
        # branches, and an anchor that matches twice tests nothing.
        "                kind_contract.kind,\n            )\n            architect = {}",
        "                kind_contract.kind,\n            )\n"
        '            architect = {"routes": [{"path": "/"}, {"path": "/gallery"}]}',
    ),
    # --- (b) synthesize_mock_data --------------------------------------------
    (
        MOCK,
        "(b) a dead provider raises out of the mock synthesis again",
        """    except Exception as exc:
        from app.application.services.request_deadline import record_degradation

        record_degradation("codegen", "mock_synthesis_failed_plumbing_mock_kept")""",
        """    except Exception as exc:
        raise exc from None
        from app.application.services.request_deadline import record_degradation

        record_degradation("codegen", "mock_synthesis_failed_plumbing_mock_kept")""",
    ),
    (
        MOCK,
        "(b) the outage is survived but nothing records it",
        """        record_degradation("codegen", "mock_synthesis_failed_plumbing_mock_kept")\n""",
        "",
    ),
    (
        MOCK,
        "(b) the failed synthesis reports success to the codegen phase",
        """            type(exc).__name__,
            exc,
        )
        return False""",
        """            type(exc).__name__,
            exc,
        )
        return True""",
    ),
    (
        MOCK,
        "(b) a merely unusable answer is recorded as a provider outage",
        """            call.adjudicate(valid, reason=UNUSABLE_REJECTED)
            if not valid:
                return False""",
        """            call.adjudicate(valid, reason=UNUSABLE_REJECTED)
            if not valid:
                from app.application.services.request_deadline import record_degradation

                record_degradation(
                    "codegen", "mock_synthesis_failed_plumbing_mock_kept"
                )
                return False""",
    ),
    # --- (c) the crash record -------------------------------------------------
    (
        ORCHESTRATOR,
        "(c) a crashed run stores nothing again",
        "        store_crash_record(ctx, exc)\n        raise",
        "        raise",
    ),
    (
        ORCHESTRATOR,
        "(c) the crash is recorded and the exception is swallowed",
        "        store_crash_record(ctx, exc)\n        raise",
        "        store_crash_record(ctx, exc)\n        return {}",
    ),
    (
        FINALIZE,
        "(c) the crash record claims the preview is ready",
        '''        "status": "failed",
        "withheld_reason": "pipeline_crashed",''',
        '''        "status": "ready",
        "withheld_reason": "pipeline_crashed",''',
    ),
    (
        FINALIZE,
        "(c) the crash record does not say why it is not being served",
        '''        "withheld_reason": "pipeline_crashed",''',
        '''        "withheld_reason": None,''',
    ),
    (
        FINALIZE,
        "(c) the record names no cause, only a failure",
        '''        "crash_error": f"{type(exc).__name__}: {exc}"[:500],''',
        '''        "crash_error": "failed",''',
    ),
    (
        FINALIZE,
        "(c) a crashed rebuild overwrites the preview the user is being served",
        """        if isinstance(previous, dict) and previous.get("status") == "ready":""",
        """        if False:""",
    ),
    (
        FINALIZE,
        "(c) a run with no workspace invents a record for a run that never was",
        "        if ctx.workspace is None:\n            return False",
        "        if False:\n            return False",
    ),
    (
        FINALIZE,
        "(c) the bookkeeping is free to replace the real exception",
        "    except Exception as bookkeeping:  # noqa: BLE001 — must never mask `exc`\n"
        '        log.warning("    could not store the crash record: %s", bookkeeping)\n'
        "        return False",
        "    except ZeroDivisionError as bookkeeping:\n"
        '        log.warning("    could not store the crash record: %s", bookkeeping)\n'
        "        return False",
    ),
    # --- (d) build_experience_plan --------------------------------------------
    (
        PAGE_EXPERIENCE,
        "(d) a dead planner raises again instead of taking the blueprint",
        "    if not plan and fallback_contract is not None:",
        "    if False:",
    ),
    (
        PAGE_EXPERIENCE,
        "(d) the blueprint plan is taken but nothing records it",
        """        record_degradation("planning", "planner_failed_deterministic_blueprint")\n""",
        "",
    ),
    (
        PAGE_EXPERIENCE,
        "(d) the blueprint replaces a plan the planner did produce",
        "    if not plan and fallback_contract is not None:",
        "    if fallback_contract is not None:",
    ),
    (
        PAGE_EXPERIENCE,
        "(d) the fallback fires for callers that resolved no contract",
        "    if not plan and fallback_contract is not None:",
        "    if not plan:",
    ),
    (
        PAGE_EXPERIENCE,
        "(d) the deterministic plan is returned without its inventory",
        "        return apply_product_kind_to_plan(\n"
        "            _normalize_plan({}, primary, secondary), fallback_contract\n"
        "        )",
        "        return _normalize_plan({}, primary, secondary)",
    ),
    (
        PAGE_EXPERIENCE,
        "(d) the blueprint outranks an accepted AppSpec's own inventory",
        "    if not plan and canonical_seed:",
        "    if False and canonical_seed:",
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
        PYTEST, shell=True, capture_output=True, text=True, timeout=1800, cwd=REPO
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
