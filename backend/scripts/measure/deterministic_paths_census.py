"""What 1.12's deterministic paths actually ship, per product kind.

    docker run --rm -v "$REPO:/repo" -w /repo/backend \
      -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \
      -c 'python3 scripts/measure/deterministic_paths_census.py'

No database and no network — this reads nothing but the production functions.

Every claim session 13 published about the size and shape of a degraded preview
comes from here, so that none of them is a paraphrase of the code they describe.
The three questions it answers:

  1. **Does the architect fallback produce anything?** `plan_phase` rescues a
     failed `call_architect` with `architect = {}`. `{}` is not a substantive
     route table, so `apply_product_kind_to_architect` injects the whole
     blueprint — and `_normalize_architect` has to accept the result, or the
     rescue only moves the crash three lines down.
  2. **Does the planner fallback produce a plan the pipeline will accept?**
     Measured against `_plan_meets_minimums`, the pipeline's own gate, rather
     than against an opinion about what a plan needs.
  3. **Is either stable under a second application?** `plan_phase` applies
     `apply_product_kind_to_plan` twice on a healthy run (`:119` and `:190`) and
     `apply_product_kind_to_architect` twice (`:305` and `:315`), so a fallback
     that duplicated its inventory on the second pass would ship double.

`resolve_product_kind_contract` takes ONE string. `context_from_request(req)`
also returns one string — session 12 splatted it (`f(*context_from_request(req))`)
and passed one character per argument, which silently forced an entire corpus to
`storefront` and cost two published numbers. Pass the string.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.application.preview_app.pipeline.architect_normalize import (  # noqa: E402
    _normalize_architect,
)
from app.application.preview_app.product_kind import (  # noqa: E402
    apply_product_kind_to_architect,
    apply_product_kind_to_plan,
    resolve_product_kind_contract,
)
from app.application.services.page_experience import (  # noqa: E402
    _normalize_plan,
    _plan_meets_minimums,
)

#: One brief-shaped context per kind the resolver can reach, including the five
#: skeletons the archived corpus never exercised.
#:
#: Session 14 correction: the original internal_ops context ("internal ops back
#: office desk for warehouse staff") resolved storefront/storefront — "internal
#: desk" and "warehouse floor" are the measured hint pair and neither is a
#: substring of it — so the internal_ops/ops contract was never actually driven
#: and three of the seven rows measured storefront. EXPECTED below turns that
#: class of silent mislabel into a red summary line.
CONTEXTS = {
    "storefront": "boutique art gallery selling original paintings online",
    "booking_service": "dental clinic taking patient appointments and bookings",
    "saas_workspace": "saas workspace dashboard for managing team projects",
    "internal_ops": "internal desk for staff on the warehouse floor",
    "trading": "trading desk blotter for equities order flow and positions",
    "accounting": "accounting practice ledger, invoices and reconciliation software",
    "(empty context)": "",
}

#: What each labelled context must resolve to for its row to measure what the
#: label claims. "(empty context)" deliberately documents the default.
EXPECTED = {
    "storefront": "storefront/storefront",
    "booking_service": "booking_service/booking",
    "saas_workspace": "saas_workspace/generic",
    "internal_ops": "internal_ops/ops",
    "trading": "internal_ops/trading",
    "accounting": "saas_workspace/accounting",
    "(empty context)": "storefront/storefront",
}

PRIMARY = "#0f766e"
SECONDARY = "#134e4a"


def main() -> int:
    rows = {}
    for label, context in CONTEXTS.items():
        contract = resolve_product_kind_contract(context)

        # (a) the architect path — exactly what plan_phase does after a rescue.
        #
        # Order is load-bearing and the first version of this script got it
        # wrong: `_normalize_architect` mutates the dict it is handed, so a
        # stability comparison written *after* the normalize call measures the
        # census's own side effect and reports every kind as unstable. Take the
        # comparison first, and hand `_normalize_architect` a copy.
        arch = apply_product_kind_to_architect({}, contract, None)
        arch_twice = apply_product_kind_to_architect(arch, contract, None)
        arch_stable = arch.get("routes") == arch_twice.get("routes")
        arch_routes = [r.get("path") for r in arch.get("routes") or []]
        arch_files = len(arch.get("files_to_generate") or [])
        arch = json.loads(json.dumps(arch))
        try:
            normalized = _normalize_architect(arch, {})
            normalize = "ok"
            routes_out = len(normalized.get("routes") or [])
        except Exception as exc:  # noqa: BLE001
            normalize = f"RAISED {type(exc).__name__}: {exc}"
            routes_out = 0

        # (d) the planner path.
        plan = apply_product_kind_to_plan(_normalize_plan({}, PRIMARY, SECONDARY), contract)
        plan_twice = apply_product_kind_to_plan(plan, contract)
        pages = [p for r in (plan.get("roles") or []) for p in (r.get("pages") or [])]
        pages_twice = [p for r in (plan_twice.get("roles") or []) for p in (r.get("pages") or [])]
        meets, issues = _plan_meets_minimums(plan, [])

        rows[label] = {
            "resolved_kind": f"{contract.kind}/{contract.subtype}",
            "architect_routes": arch_routes,
            "architect_files": arch_files,
            "architect_normalize": normalize,
            "architect_routes_after_normalize": routes_out,
            "architect_stable_on_second_apply": arch_stable,
            "plan_pages": [p.get("id") for p in pages],
            "plan_meets_minimums": meets,
            "plan_minimum_issues": issues,
            "plan_stable_on_second_apply": [p.get("id") for p in pages]
            == [p.get("id") for p in pages_twice],
        }

    print(json.dumps(rows, indent=2))

    mislabelled = {
        label: row["resolved_kind"]
        for label, row in rows.items()
        if row["resolved_kind"] != EXPECTED[label]
    }
    ok = all(
        row["architect_normalize"] == "ok"
        and row["architect_routes"]
        and row["plan_meets_minimums"]
        and row["architect_stable_on_second_apply"]
        and row["plan_stable_on_second_apply"]
        for row in rows.values()
    )
    print()
    distinct = sorted({row["resolved_kind"] for row in rows.values()})
    print(f"distinct contracts measured: {len(distinct)} — {', '.join(distinct)}")
    for label, got in mislabelled.items():
        print(f"MISLABELLED ROW: {label!r} resolved {got}, expected {EXPECTED[label]}")
    print(f"every kind ships routes, normalizes, meets minimums and is stable: {ok}")
    return 0 if ok and not mislabelled else 1


if __name__ == "__main__":
    raise SystemExit(main())
