"""Run 52 controls — the seven generic laws behind the 51-r3 reclassification.

1. a client policy keeps its event origin ("10 days after month-end")
2. one canonical pilot design: comparable eligible orders randomized 50/50
3. the pilot is rules-based, human-supervised, and depends on no module
4. financial units and provenance: hours are hours; hours released need the client's share
5. financial detail needs authentication stronger than a number match
6. API paths are URL-safe slugs
7. a FINAL operations manual has an assigned owner and approver
All registry/schema validations and cross-volume checks; no client literals in code.
"""
import copy
import json

from app.models import Request
from app.pipeline import pilot_gate as pg
from app.pipeline import registry as rg
from tests.test_volume_one_brief import GATE, MODULES, OPS


def test_policy_period_keeps_its_event_origin():
    claims = rg.client_fact_claims([{"question": "Days after month-end to fully settle COD with a client?",
                                     "answer": "10 days"}], [])
    c = claims[0]
    assert c["value"] == 10 and c["unit"].startswith("day") and c["event"] == "after month-end"
    bad = "Explain the 'settlement within 10 days (your stated cycle) of order delivery' policy for business clients."
    found = rg.policy_findings({"t": bad}, claims)
    assert found and "event origin" in found[0]["issue"]
    fixed, notes = rg.policy_pass(bad, claims)
    assert "10 days after month-end (your stated cycle)" in fixed and "order delivery" not in fixed and notes
    assert rg.policy_findings({"t": fixed}, claims) == []
    good = "COD is settled 10 days after month-end (your stated cycle)."
    assert rg.policy_findings({"t": good}, claims) == [] and rg.policy_pass(good, claims)[0] == good


def test_pilot_design_is_canonical_and_other_zones_are_rejected():
    raw = copy.deepcopy(GATE)
    raw["control_method"] = ("All other orders (not from the 5 selected business clients, or from other zones) "
                             "will serve as the control group, maintaining current processes")
    g = pg.normalize_gate(raw)
    assert g["design_errors"] and any("randomized" in e for e in pg.gate_errors(g)) and g["assignment"] is None
    raw["control_method"] = "Eligible orders are randomly assigned 50/50 to treatment and control"
    g2 = pg.normalize_gate(raw)
    assert not g2["design_errors"] and g2["control_method"] == pg.assignment_sentence(g2)
    assert "randomized 50/50" in pg.full_definition(g2)
    sop = ("Assign orders to 'Treatment' or 'Control Group' based on a predetermined alternating assignment "
           "(e.g. odd/even order numbers).")
    assert pg.design_findings(sop, g2)
    fixed, recs = pg.enforce_design(sop, g2)
    assert fixed == pg.assignment_sentence(g2) and recs
    assert pg.design_findings(fixed, g2) == []


def test_pilot_specification_and_procedures_are_rules_based_and_isolated():
    from app.pipeline.extras import canonicalize_layers

    mods = copy.deepcopy(MODULES)
    pm = mods[0]
    assert pm["pilot"]
    other = mods[1]["name"]
    pm["tech"] = {
        "build_sequence": ["Build the pilot log", "Implement the core AI agent logic: message parsing, classification"],
        "data_model": [{"entity": "PilotOrder", "fields": ["order_id", "last_ai_classification"]}],
        "apis": [{"name": "/webhook/inbound", "does": "Routes replies to the AI agent or the supervisor queue"}],
        "done_when": ["Supervisor sees every flagged conversation", f"Details reach the {other}"],
        "security": [],
    }
    pm["spec"]["integrations"] = [other]
    assert rg.pilot_isolation_findings(mods)
    bc = {"build_order": [m["id"] for m in mods], "pilot_gate": copy.deepcopy(GATE)}
    reg = rg.build_registry(OPS, bc, mods)
    pm = mods[0]
    blob = json.dumps({k: pm.get(k) for k in ("spec", "tech")})
    assert "AI" not in blob and other not in blob and "classification" not in blob.lower()
    assert rg.pilot_isolation_findings(mods) == []
    assert any(str(r.get("removed", "")).startswith("Implement the core AI") for r in reg["pilot_ai_removed"])
    assert any(r.get("field") == "tech.data_model[0].fields" for r in reg["pilot_ai_removed"])
    assert reg["forward_dependencies_removed"]
    gate = reg["pilot_gate"]
    procs = [{"name": "Assigning orders", "phase": "pilot", "module": pm["client_facing_name"], "trigger": "Each morning",
              "steps": [{"actor": "AI", "step": f"Pull the order list from the {other} and let the AI agent classify replies; "
                                                "assign by alternating order numbers to Treatment or Control Group."}],
              "exceptions": []}]
    canonicalize_layers(procs, {}, mods, reg, gate)
    st = procs[0]["steps"][0]
    assert st["actor"] == pg.PILOT_OPERATOR and other not in st["step"] and "AI" not in st["step"]
    assert pg.assignment_sentence(gate) in st["step"]
    assert rg.pilot_isolation_findings(mods, procs) == []
    assert reg["pilot_design_corrections"] and any(r.get("where", "").startswith("procedures") for r in reg["pilot_ai_removed"])


def test_hours_line_keeps_its_unit_and_hours_released_needs_the_client_share():
    from app.pipeline import export_pdf as ep
    from app.pipeline.decompose import _sanitize_financial_model, line_unit
    from app.pipeline.structural import structural_findings

    bc = {"financial_model": {
        "lines": [
            {"item": "Annual 'where is my order' inquiries", "arithmetic": "350 inquiries/day * 365 days/year", "annual": 127750},
            {"item": "Annual finance staff hours on COD settlement inquiries", "arithmetic": "45 hours/week * 52 weeks/year",
             "annual": 2340},
        ],
        "scenarios": [{"name": "Expected",
                       "assumption": "automates 40% of 'where is my order' inquiries and 30% of COD settlement inquiries.",
                       "impact": "~51,100 'where is my order' inquiries/year automated + ~1,080 COD inquiries/year automated "
                                 "(~702 finance staff hours/year released), by your own figures."}],
        "missing_inputs": []}}
    before = copy.deepcopy(bc)
    assert line_unit(before["financial_model"]["lines"][1]) == "hours"
    assert any("hours released" in f["issue"] for f in structural_findings(before, [], {"claims": []}))
    _sanitize_financial_model(bc)
    fm = bc["financial_model"]
    assert fm["lines"][1]["unit"] == "hours" and fm["lines"][0]["unit"] == "inquiries"
    impact = fm["scenarios"][0]["impact"]
    assert "702" not in impact and "not yet calculable" in impact and "2,340 hours" in impact
    assert any("share" in x for x in fm["missing_inputs"]) and fm["unit_corrections"][0]["base_unit"] == "hours"
    assert not any("hours released" in f["issue"] for f in structural_findings(bc, [], {"claims": []}))
    assert ep._quantity(2340, "45 hours/week * 52 weeks/year Annual finance staff hours on COD settlement inquiries",
                        unit="hours") == "2,340 hours"
    # the client's own share makes the component legitimate
    share = [{"id": "CF-99", "type": "client_fact", "value": 0.6, "unit": "%",
              "question": "Share of finance hours spent on settlement inquiries?"}]
    assert not any("hours released" in f["issue"] for f in structural_findings(before, [], {"claims": share}))


def test_financial_detail_requires_more_than_a_number_match():
    mods = copy.deepcopy(MODULES)
    m = mods[1]
    m["tech"] = {"security": ["Authentication for `lookup cod settlement status` will verify the WhatsApp phone number "
                              "corresponds to a known business client before querying financial data."],
                 "apis": [{"name": "/api/v1/settlements/{client_id}", "does": "Returns settlement status over WhatsApp"}],
                 "done_when": ["a check", "another check"]}
    assert rg.auth_findings(mods)
    recs = rg.harden_auth(mods)
    assert recs and rg.AUTH_CLAUSE in m["tech"]["security"][0]
    assert rg.auth_findings(mods) == []
    prose = ("The module will verify the WhatsApp phone number matches a known business client and then share "
             "the settlement status.")
    assert rg.auth_text_findings(prose, "technical")
    fixed, r = rg.harden_auth_text(prose)
    assert rg.AUTH_CLAUSE in fixed and r and rg.auth_text_findings(fixed) == []


def test_api_paths_stay_url_safe_slugs():
    assert rg.plain_language("call `/api/v1/pilot/opt_out/{customer_phone_number}` with the order_id") == \
        "call `/api/v1/pilot/opt_out/{customer_phone_number}` with the order id"
    kept = "POST /api/v1/pilot/orders/{order_id}/start_whatsapp_confirmation then"
    assert rg.plain_language(kept) == kept
    mods = [{"id": "m", "name": "M", "tech": {"apis": [{"name": "/api/v1/pilot/opt out/{customer phone number}", "does": "x"}]}}]
    assert rg.api_path_findings(mods)
    recs = rg.api_path_repair(mods)
    assert mods[0]["tech"]["apis"][0]["name"] == "/api/v1/pilot/opt-out/{customer_phone_number}" and recs
    assert rg.api_path_findings(mods) == []
    text = "The dashboard exposes /api/v1/flagged delivery inquiries and /api/v1/conversation/{conversation id}/details."
    found = rg.api_text_findings(text, ["/api/v1/flagged_delivery_inquiries", "/api/v1/conversation/{conversation_id}/details"])
    assert len(found) == 2


def test_target_value_fraction_form_is_reconciled_and_a_resulting_rate_is_named():
    """Run 52 failed closed three times on 'target_value contradicts the
    target text' with no hint of the expected number. The same number as a
    fraction is reconciled; a different number is an error that names the
    value to write."""
    raw = copy.deepcopy(GATE)
    raw["target_value"] = 0.10            # the text says 10 percentage points
    g = pg.normalize_gate(raw)
    assert g["target_value"] == 10 and g["target_value_reconciled"] and not g["target_value_conflict"]
    assert not [e for e in pg.gate_errors(g) if "target_value" in e]
    raw["target_value"] = 0.93            # the resulting rate — a different number
    g2 = pg.normalize_gate(raw)
    assert g2["target_value"] == 10 and g2["target_value_conflict"]
    err = next(e for e in pg.gate_errors(g2) if "target_value" in e)
    assert "(0.93)" in err and "write target_value exactly as the number in the target text: 10" in err


def test_final_operations_manual_requires_owner_and_approver():
    from app.pipeline import export_pdf as ep

    # three states: DRAFT (open findings) / FINAL — CONSULTANCY DELIVERABLE (all
    # quality checks pass; no client approval needed) / CLIENT APPROVED (the
    # client supplied the document owner and approver — never invented)
    from tests._integrity_stub import stamp_clean

    row = Request(id=9201, business_name="x", status="done", is_failed=False, mvp_blueprint="doc", technical_plan="doc",
                  qa_report_json=json.dumps({"checks": [], "findings": []}))
    stamp_clean(row)
    gate = ep.release_status(row)
    assert gate["status"] == "final" and gate["status_label"] == "FINAL — CONSULTANCY DELIVERABLE" and gate["reasons"] == []
    assert not rg.document_control(row)["complete"]
    row.document_owner, row.document_approver = "Operations Manager (client)", "Head of Operations (client)"
    gate = ep.release_status(row)
    assert gate["status"] == "client_approved" and gate["status_label"] == "CLIENT APPROVED" and rg.document_control(row)["complete"]
    row.qa_report_json = json.dumps({"checks": [], "findings": [{"severity": "high", "source": "qa_numbers", "where": "x",
                                                                 "issue": "an open finding", "fix": "fix it"}]})
    assert ep.release_status(row)["status"] == "draft"
