"""Deterministic preflight fixture for the next run.

    python tools/preflight_fixture.py <source_request_id>

Takes a finished run's persisted decomposition as the RAW skeleton, shows
what the current controls find in it (the run-46 defects, by construction),
then builds the INTENDED skeleton — the same structures after the registry's
deterministic passes plus the typed gate fields the new decompose prompt
demands — and proves it carries zero structural findings before any prose
would be generated. Nothing is persisted.
"""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def intended_skeleton(row) -> tuple[dict, list, dict]:
    """The run-47 skeleton: the source run's structures, typed and normalized
    the way the new decomposition stage produces them."""
    from app.pipeline import registry as _registry

    bc = copy.deepcopy(json.loads(row.business_case_json) if row.business_case_json else {})
    mods = copy.deepcopy(json.loads(row.modules_json) if row.modules_json else [])
    gate = bc.get("pilot_gate") or {}
    # the fields the new prompt requires and the old run never produced
    gate.setdefault("numerator", "deliveries completed on the first attempt")
    gate.setdefault("denominator", "all delivery attempts in the pilot population")
    if not gate.get("geography"):
        gate["geography"] = "the pilot zone (to be named by the client)"
    gate.setdefault("control_method", gate.get("control") or "orders outside the pilot zone")
    gate.setdefault("change_kind", "percentage_point")
    gate.setdefault("target_value", 5)
    gate.setdefault("guardrails", [gate.get("guardrail")] if gate.get("guardrail") else [])
    bc["pilot_gate"] = gate
    # the pilot module is the first built, rules-based
    order = bc.get("build_order") or [m.get("id") for m in mods]
    for m in mods:
        m["pilot"] = m.get("id") == order[0]
        if m["pilot"]:
            m["automation_level"] = "rules"
        for candidate in ((m.get("spec") or {}).get("kpi_candidates") or []):
            pass
    reg = _registry.build_registry(
        row.ops_numbers_json, bc, mods,
        free_texts=[row.business_description or "", row.main_problem or "", row.desired_outcome or ""])
    return bc, mods, reg


def main(argv: list[str]) -> int:
    from app.database import SessionLocal
    from app.models import Request
    from app.pipeline import registry as _registry
    from app.pipeline.structural import preflight

    db = SessionLocal()
    row = db.get(Request, int(argv[0]))
    raw_bc = json.loads(row.business_case_json or "{}")
    raw_mods = json.loads(row.modules_json or "[]")
    raw_findings = preflight(copy.deepcopy(raw_bc), copy.deepcopy(raw_mods))
    print(f"RAW skeleton of run {row.id}: {len(raw_findings)} structural finding(s)")
    for f in raw_findings:
        print("  -", f["where"], "|", f["issue"][:150])

    bc, mods, reg = intended_skeleton(row)
    findings = preflight(bc, mods, reg)
    print(f"\nINTENDED skeleton: {len(findings)} structural finding(s)")
    for f in findings:
        print("  -", f["where"], "|", f["issue"][:150])
    print("registry: claims", len(reg["claims"]), "| errors", reg["errors"], "| renames", reg["renames"])
    print("pilot gate:", reg["pilot_gate_sentence"])
    print("build order:", reg["build_order_names"])
    for m in mods:
        print(" ", m["client_facing_name"], "|", m["phase"], "|", m["automation_level"], "| KPI:",
              (m.get("spec") or {}).get("kpi_statement", "")[:140])
    print("proposals awaiting approval:", len(_registry.proposals(reg)))
    db.close()
    return 0 if not findings and not reg["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
