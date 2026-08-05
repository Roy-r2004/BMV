"""How big is the PRODUCT_KIND clause pile-on, and does it reach anything?

    docker run --rm -v "$REPO:/repo" -w /repo/backend \
      -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \
      -c 'python3 scripts/measure/design_direction_census.py'

No database, no network. Drives the real functions in the order `plan_phase`
runs them, per reachable kind:

  plan side       apply_product_kind_to_plan at :119 and :190, then the
                  internal_desk / saas_accounting forcers at :204 / :208
                  (which read the polluted direction and can append a third
                  clause via their own apply_product_kind_to_plan)
  architect side  apply_product_kind_to_architect at :330 and :340

What it deliberately does NOT claim: that any of this reaches a prompt or a
stored artifact. `seal_design_brief` returns `sealed: True` unconditionally, so
`apply_sealed_brief_to_plan` (:265) and `apply_sealed_brief_to_architect`
(:349) REPLACE the direction before `call_architect` (:288), before codegen,
and before `finalize` persists it. The companion measurement — zero
`PRODUCT_KIND=` occurrences across all 47 stored `preview_app.design_direction`
values — is taken from the database and recorded in the roadmap; this script
measures the transient window those two replaces bound.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.application.preview_app.internal_desk import (  # noqa: E402
    ensure_internal_desk_experience_plan,
)
from app.application.preview_app.product_kind import (  # noqa: E402
    apply_product_kind_to_architect,
    apply_product_kind_to_plan,
    resolve_product_kind_contract,
)
from app.application.preview_app.saas_accounting import (  # noqa: E402
    ensure_saas_accounting_experience_plan,
)
from app.application.services.page_experience import _normalize_plan  # noqa: E402

#: Same per-kind contexts as deterministic_paths_census.py (with its session 14
#: internal_ops correction — the old context resolved storefront).
CONTEXTS = {
    "storefront": "boutique art gallery selling original paintings online",
    "booking_service": "dental clinic taking patient appointments and bookings",
    "saas_workspace": "saas workspace dashboard for managing team projects",
    "internal_ops": "internal desk for staff on the warehouse floor",
    "trading": "trading desk blotter for equities order flow and positions",
    "accounting": "accounting practice ledger, invoices and reconciliation software",
    "(empty context)": "",
}

PRIMARY = "#0f766e"
SECONDARY = "#134e4a"


def main() -> int:
    rows = {}
    for label, context in CONTEXTS.items():
        contract = resolve_product_kind_contract(context)

        plan0 = _normalize_plan({}, PRIMARY, SECONDARY)
        base_len = len(str(plan0.get("design_direction") or ""))
        p1 = apply_product_kind_to_plan(plan0, contract)  # plan_phase:119
        p2 = apply_product_kind_to_plan(p1, contract)  # plan_phase:190
        p3 = ensure_internal_desk_experience_plan(p2, context=context)  # :204
        p3 = ensure_saas_accounting_experience_plan(p3, context=context)  # :208
        d1 = str(p1["design_direction"])
        d2 = str(p2["design_direction"])
        d3 = str(p3["design_direction"])

        a1 = apply_product_kind_to_architect({}, contract, p3)  # plan_phase:330
        a2 = apply_product_kind_to_architect(a1, contract, p3)  # plan_phase:340
        ad2 = str(a2["design_direction"])

        rows[label] = {
            "resolved_kind": f"{contract.kind}/{contract.subtype}",
            "plan_clause_chars": len(d1) - base_len,
            "plan_clauses_after_190": d2.count("PRODUCT_KIND="),
            "plan_direction_after_190_chars": len(d2),
            "plan_clauses_after_forcers": d3.count("PRODUCT_KIND="),
            "plan_direction_after_forcers_chars": len(d3),
            "architect_clause_chars": len(str(a1["design_direction"])),
            "architect_clauses_after_340": ad2.count("PRODUCT_KIND="),
            "architect_direction_after_340_chars": len(ad2),
            "transient_duplicate_chars": (len(d3) - base_len - (len(d1) - base_len))
            + (len(ad2) - len(str(a1["design_direction"]))),
        }

    print(json.dumps(rows, indent=2))
    print()
    print(
        "transient duplicate chars = direction growth beyond one clause per dict, "
        "plan + architect, before the sealed-brief replaces at :265/:349 discard it"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
