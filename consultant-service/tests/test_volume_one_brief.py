"""The Volume I brief, pinned: PG-01 identical everywhere, treatment versus
control with the right denominator, no Phase-1 dependency on a later-phase
module, no AI actor in Phase 1, no invented KPI, no raw module ids, the
30-day monthly basis, half-up rounding, dollars-only payback, and no
'order_IDs', '>=' or 'N attempts' on any page."""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.models import Request
from app.pipeline import pilot_gate as pg
from app.pipeline import registry as rg
from app.pipeline import timebasis as tb


@pytest.fixture
def client():
    from main import app

    Base.metadata.create_all(bind=engine)
    return TestClient(app)


OPS = json.dumps([
    {"question": "Deliveries per day and average delivery fee?", "answer": "900 deliveries a day, average fee $2.50"},
    {"question": "Failed first attempts and re-attempt cost?", "answer": "12% of deliveries fail first attempt; each re-attempt costs about $1.80"},
    {"question": "'Where is my order' WhatsApp inquiries per day?", "answer": "About 350 a day, handled by 5 support staff"},
    {"question": "COD settlement inquiries per month?", "answer": "Around 300 inquiries"},
    {"question": "Days after month-end to fully settle COD with a client?", "answer": "10 days"},
])

GATE = {
    "duration": "6 weeks (proposed — client approval required)",
    "population": "All first-attempt deliveries to new customers", "geography": "Beirut",
    "control_method": "50% of the pilot population will be randomly assigned to a control group receiving standard delivery notifications, while the other 50% receives proactive WhatsApp confirmation",
    "primary_metric": "First-attempt delivery success rate",
    "numerator": "Deliveries completed on the first attempt", "denominator": "All delivery attempts",
    "baseline": "measure in week 1",
    "target": "A 10 percentage point rise in first-attempt delivery success rate (proposed — client approval required)",
    "target_value": 10, "change_kind": "percentage_point",
    "guardrails": ["complaint rate increase > 2% relative to control group", "delivery delay increase > 5% relative to control group"],
    "approvals_required": ["Pilot duration", "Pilot population", "Control method", "Primary metric target"],
}

MODULES = [
    {"id": "pre-dispatch-whatsapp-pilot", "name": "Pre-Dispatch WhatsApp Pilot", "purpose": "confirms address and window before dispatch, reviewed in the Unified Support Workbench",
     "depends_on": ["unified-support-workbench"], "pilot": True, "automation_level": "rules",
     "spec": {"ai": None, "kpis": [{"metric": "Orders confirmed before dispatch", "basis": "proposed", "value": 80, "unit": "%", "horizon": None}]},
     "tech": {"done_when": ["Support staff review each conversation in the Unified Support Workbench within 5 minutes.",
                            "Updates initiated through the pilot reach the Core Delivery Management System for all pilot orders."], "ai_agent": None}},
    {"id": "delivery-exception-ai-coordinator", "name": "Delivery Exception AI Coordinator", "purpose": "predicts and handles delivery exceptions",
     "depends_on": ["pre-dispatch-whatsapp-pilot"], "spec": {"ai": {"role": "predicts"}, "kpis": [
         {"metric": "Reduction in 'where is my order' inquiries", "basis": "measure_in_week_1", "value": None, "unit": "%", "horizon": None}]},
     "tech": {"done_when": ["Flagged orders appear in the exception queue with a reason.", "Operations can open any flagged order."], "ai_agent": {"evaluation": []}}},
    {"id": "cod-settlement-inquiry-ai-handler", "name": "COD Settlement Inquiry AI Handler", "purpose": "answers COD settlement inquiries",
     "depends_on": [], "spec": {"ai": {"role": "answers"}, "kpis": []},
     "tech": {"done_when": ["A client receives the correct settlement status for a valid order id within 10 seconds (proposed — client approval required).",
                            "Disputes are escalated to finance."], "ai_agent": None}},
    {"id": "unified-support-workbench", "name": "Unified Support Workbench", "purpose": "one screen for support and finance",
     "depends_on": ["delivery-exception-ai-coordinator", "cod-settlement-inquiry-ai-handler"], "spec": {"ai": {"role": "suggests replies"}, "kpis": []},
     "tech": {"done_when": ["Agents see the full history for any order.", "Agents can take over any conversation."], "ai_agent": None}},
]
FM = {"lines": [{"item": "Annual re-attempt costs", "arithmetic": "900 deliveries/day * 365 days/year * 12% failed * $1.80", "annual": "$70,956/year"},
                {"item": "Annual support inquiries for 'where is my order'", "arithmetic": "350 inquiries/day * 365 days/year", "annual": "127,750 inquiries/year"}],
      "scenarios": [{"name": "Conservative", "assumption": "prevents 25% of failed first attempts and automates 30% of 'where is my order' inquiries",
                     "impact": "Saved $17,739/year in re-attempt costs, automated 38,325 'where is my order' inquiries/year, by your own figures."},
                    {"name": "Expected", "assumption": "prevents 40% of failed first attempts and automates 50% of 'where is my order' inquiries",
                     "impact": "Saved $28,382.40/year in re-attempt costs, automated 63,875 'where is my order' inquiries/year, by your own figures."},
                    {"name": "Upside", "assumption": "prevents 60% of failed first attempts and automates 70% of 'where is my order' inquiries",
                     "impact": "Saved $42,573.60/year in re-attempt costs, automated 89,425 'where is my order' inquiries/year, by your own figures."}],
      "payback_note": "To estimate payback, divide the build quote by the Expected monthly impact (annual impact / 12).",
      "missing_inputs": ["Your fully-loaded hourly cost for support staff"]}


def _skeleton():
    from app.pipeline.decompose import _sanitize_financial_model

    bc = {"financial_model": copy.deepcopy(FM), "pilot_gate": copy.deepcopy(GATE),
          "build_order": ["pre-dispatch-whatsapp-pilot", "delivery-exception-ai-coordinator", "cod-settlement-inquiry-ai-handler", "unified-support-workbench"],
          "cost_of_inaction": "Staying as you are costs approximately $5,832 per month in re-attempt costs alone."}
    mods = copy.deepcopy(MODULES)
    _sanitize_financial_model(bc)
    reg = rg.build_registry(OPS, bc, mods)
    return bc, mods, reg


def test_pg01_is_one_object_compared_with_control_and_identical_everywhere():
    bc, mods, reg = _skeleton()
    g = reg["pilot_gate"]
    assert g["id"] == "PG-01" and g["control_ratio"] == 0.5 and g["target_vs_control"] is True
    assert g["treatment"].startswith("proactive WhatsApp confirmation")
    assert g["comparison_metric"] == "treatment First-attempt delivery success rate minus control First-attempt delivery success rate"
    assert g["denominator"] == "eligible deliveries assigned to each group"
    short = pg.canonical_sentence(g)
    assert short == ("PG-01: treatment first-attempt delivery success must exceed control by 10 percentage points after six weeks; "
                     "guardrails apply. Proposed — client approval required.")
    full = pg.full_definition(g)
    assert "50% treatment, 50% control" in full and "divided by eligible deliveries assigned to each group" in full
    assert "the control group, not a baseline, is the comparison" in full and "week-one baseline" not in short
    # every restatement site receives the SAME short reference
    text = "Decision: [[PILOT_GATE]]\nKPI: [[PILOT_GATE]]\nSOP: Refer to [[PILOT_GATE]]"
    out, _ = pg.enforce(text, g)
    assert out.count(short) == 3 and pg.restatement_findings(out + "\n" + full, g) == []
    # a paraphrase of the gate is rejected, the full definition is not
    assert pg.restatement_findings("First-attempt delivery success rate must rise by 10 percentage points within 6 weeks of the pilot.", g)
    assert pg.restatement_findings(full, g) == []


def test_phase_one_never_depends_on_a_later_phase_module_and_cod_is_parallel():
    bc, mods, reg = _skeleton()
    by_id = {m["id"]: m for m in reg["modules"]}
    assert by_id["pre-dispatch-whatsapp-pilot"]["phase_number"] == 1
    assert by_id["delivery-exception-ai-coordinator"]["phase_number"] == 2
    assert by_id["unified-support-workbench"]["phase_number"] == 3
    assert by_id["cod-settlement-inquiry-ai-handler"]["phase_number"] is None
    assert by_id["cod-settlement-inquiry-ai-handler"]["workstream"] == "parallel"
    pilot = next(m for m in mods if m["pilot"])
    assert pilot["depends_on"] == [] and pilot["pilot_tooling"] == "Pilot Review Queue"
    # the removal is recorded, not silent
    removed = reg["forward_dependencies_removed"]
    assert any(r["later_phase_module"] == "Unified Support Workbench" and r["field"] == "depends_on" for r in removed)
    assert any(r["field"].startswith("tech.done_when") for r in removed)
    assert rg.corrections(reg)["forward_dependencies_removed"] == removed
    assert "Unified Support Workbench" not in json.dumps(pilot) and "Pilot Review Queue" in pilot["tech"]["done_when"][0]
    assert pilot["display_name"] == "Pre-Dispatch WhatsApp Pilot" and pilot["ai_involvement"] is False
    assert reg["errors"] == []


def test_no_ai_actor_in_phase_one_people_plan_or_risks():
    from app.pipeline.extras import canonicalize_layers

    bc, mods, reg = _skeleton()
    by_name = {"organization": {"roles": [
        {"role": "Pre-Dispatch WhatsApp Pilot", "type": "ai", "responsibilities": ["The AI confirms addresses over WhatsApp"],
         "decides_alone": "Null", "hands_off": "Null"},
        {"role": "iCARRY Operations Lead", "type": "human", "responsibilities": ["Owns the pilot"], "decides_alone": "x", "hands_off": "y"}],
        "change_impact": [{"role": "Pre-Dispatch WhatsApp Pilot", "what_changes": "x", "must_learn": "y"}]},
        "governance": {"scoreboard": [], "risks": [{"risk": "Customers distrust AI-handled messages from the Pre-Dispatch WhatsApp Pilot",
                                                   "mitigation": "Humans review the AI output for the first 2 weeks", "who_feels_it": "support"}]}}
    canonicalize_layers([], by_name, mods, reg, reg["pilot_gate"])
    roles = by_name["organization"]["roles"]
    assert roles[0]["role"] == "Pilot Support Operator" and roles[0]["type"] == "human"
    assert "AI" not in json.dumps(roles[0]) and by_name["organization"]["change_impact"][0]["role"] == "Pilot Support Operator"
    risk = by_name["governance"]["risks"][0]
    assert "AI" not in risk["risk"] and "pilot-workflow" in risk["risk"]
    assert "2 weeks (proposed — client approval required)" in risk["mitigation"] or "2-week" in risk["mitigation"]


def test_no_invented_kpi_and_claim_ids_are_assigned():
    bc, mods, reg = _skeleton()
    pilot = next(m for m in mods if m["pilot"])
    assert pilot["spec"]["kpi_statement"] == reg["pilot_gate_sentence"] and pilot["kpi_claim_ids"] == ["MK-pre-dispatch-whatsapp-pilot-gate"]
    assert "80%" not in pilot["spec"]["kpi_statement"]
    deac = next(m for m in mods if m["id"] == "delivery-exception-ai-coordinator")
    assert rg.WEEK_ONE_SENTENCE[:-1] in deac["spec"]["kpi_statement"] and deac["kpi_claim_ids"] == []
    props = [c for c in rg.proposals(reg) if c["type"] == "module_kpi"]
    assert all(not c.get("accepted") for c in props)
    statements = " ".join(m["spec"]["kpi_statement"] for m in mods)
    assert rg.kpi_number_findings("**You'll know it's working when:** " + statements, reg, strict_kpi=True) == []


def test_no_raw_module_ids_reach_client_text():
    bc, mods, reg = _skeleton()
    text = "1. **pre-dispatch-whatsapp-pilot:** first. Then delivery-exception-ai-coordinator and cod-settlement-inquiry-ai-handler."
    out = rg.resolve_module_ids(text, mods)
    assert "-" not in out.replace("Pre-Dispatch", "").replace("first-", "") or "pilot:" not in out
    assert "Pre-Dispatch WhatsApp Pilot" in out and "COD Settlement Inquiry AI Handler" in out
    assert rg.identifier_artifacts(out, [m["id"] for m in mods]) == []
    assert rg.identifier_artifacts(text, [m["id"] for m in mods])


def test_thirty_day_monthly_basis_and_half_up_rounding():
    bc, mods, reg = _skeleton()
    fm = bc["financial_model"]
    assert "$42,574" in fm["scenarios"][2]["impact"] and "$42,573.60" not in fm["scenarios"][2]["impact"]
    assert "$28,382" in fm["scenarios"][1]["impact"]
    assert fm["time_basis"]["monthly_identity"] == "operating_30_day_month"
    assert abs(tb.candidates(70956.0, "per month")[0][0] - 5832.0) < 0.01 and len(tb.candidates(70956.0, "per month")) == 1
    assert rg.plain_language("Saved $42,573.60 and a fee of $1.80 and $2.50") == "Saved $42,574 and a fee of $1.80 and $2.50"
    assert rg.plain_language("$12,345.50") == "$12,346"  # half-up, not banker's
    assert tb.identity_findings({"b": "about $5,913 per month"}, [70956.0])


def test_payback_uses_hard_dollars_only_on_the_thirty_day_month():
    bc, mods, reg = _skeleton()
    note = bc["financial_model"]["payback_note"]
    assert "/ 12" not in note and "÷ 12" not in note
    assert "$2,333" in note and "$28,382/year ÷ 365 × 30" in note
    assert "inquiry volumes and released hours are not added" in note
    assert "cannot yet be calculated" in note
    assert bc["financial_model"]["payback_monthly_hard_dollar"] == round(28382.4 / 365 * 30, 2)


def test_client_facing_syntax_is_plain_language():
    assert rg.plain_language("using random order_IDs within 30 seconds") == "using random order IDs within 30 seconds"
    assert rg.plain_language("resolved with >=90% accuracy") == "resolved with at least 90% accuracy"
    assert rg.plain_language("after N attempts via WhatsApp") == "after approved maximum number of attempts via WhatsApp"
    assert rg.plain_language("a six-month staffing plan and two-week monitoring") == "a 6-month staffing plan and 2-week monitoring"
    claims = rg.client_fact_claims(json.loads(OPS), [])
    out, new = rg.threshold_pass("a six-month staffing plan and two-week monitoring", claims, source="x", module_id="m", counter={"n": 0})
    assert out.count(rg.PROPOSED_LABEL) == 2 and {c["type"] for c in new} == {"timing_sla"}
    from app.pipeline import export_pdf as ep

    assert ep._strip_artifacts("order_IDs >=90% N attempts $42,573.60") == "order IDs at least 90% approved maximum number of attempts $42,574"


def test_run50_classes_generic_tags_are_not_aliases_placeholders_are_slots_pilot_sop_uses_the_queue():
    from app.pipeline.extras import canonicalize_layers
    from app.pipeline.structural import preflight

    mods = [{"id": "cod-resolver", "name": "COD Settlement Inquiry Resolver (AI)", "purpose": "resolves COD inquiries", "depends_on": [],
             "spec": {"ai": {"role": "x"}, "kpis": []}, "tech": {"done_when": ["a", "b"]}},
            {"id": "comms", "name": "AI Delivery Communications Manager", "purpose": "manages comms", "depends_on": [],
             "spec": {"ai": {"role": "x"}, "kpis": []}, "tech": {"done_when": ["a", "b"]}},
            {"id": "lva", "name": "Location Verification Assistant (LVA)", "purpose": "verifies pins", "depends_on": [],
             "spec": {"ai": None, "kpis": []}, "tech": {"done_when": ["a", "b"]}}]
    reg = rg.build_registry(OPS, {"build_order": [m["id"] for m in mods]}, mods)
    by_id = {m["id"]: m for m in reg["modules"]}
    assert by_id["cod-resolver"]["client_facing_name"] == "COD Settlement Inquiry Resolver" and by_id["cod-resolver"]["alias"] is None
    assert by_id["lva"]["alias"] == "LVA"
    out = rg.resolve_module_ids("The AI Delivery Communications Manager hands off to the LVA.", mods)
    assert out == "The AI Delivery Communications Manager hands off to the Location Verification Assistant."
    # placeholders: a preflight defect in specs, an approved-threshold slot in rendered text
    bad = copy.deepcopy(MODULES)
    bad[1]["tech"]["done_when"][0] = "Flags >[CLIENT_INPUT_OR_ARITHMETIC]% of risky orders within [CLIENT_INPUT_OR_ARITHMETRIC] minutes."
    assert any("template placeholder" in f["issue"] for f in preflight({"build_order": [m["id"] for m in bad]}, bad))
    reg_bad = rg.build_registry(OPS, {"build_order": [m["id"] for m in bad]}, copy.deepcopy(bad))
    logged = reg_bad["placeholder_replacements"]
    assert len(logged) == 2 and all(l["module"] == "delivery-exception-ai-coordinator" for l in logged)
    assert rg.corrections(reg_bad)["placeholder_replacements"] == logged
    assert rg.plain_language("for >[CLIENT_INPUT_OR_ARITHMETIC]% of replies within [CLIENT_INPUT_OR_ARITHMETRIC] minutes") == \
        "for an approved threshold of replies within an approved threshold minutes"
    assert rg.plain_language("x (proposed — client approval required) (proposed — client approval required) y") == \
        "x (proposed — client approval required) y"
    # the pilot SOP never names an AI or later-phase module: it runs on the Pilot Review Queue
    bc, mods2, reg2 = _skeleton()
    procedures = [{"name": "Pre-Dispatch Delivery Detail Confirmation", "phase": "pilot", "module": "The pilot", "trigger": "order created",
                   "steps": [{"actor": "ai", "step": "Delivery Exception AI Coordinator drafts the WhatsApp message."},
                             {"actor": "dispatcher", "step": "Log the reply in the Unified Support Workbench."}]}]
    canonicalize_layers(procedures, {}, mods2, reg2, reg2["pilot_gate"])
    assert procedures[0]["steps"][0]["actor"] == "Pilot Support Operator"
    assert "Pilot Review Queue" in procedures[0]["steps"][0]["step"] and "Pilot Review Queue" in procedures[0]["steps"][1]["step"]
    assert "AI Coordinator" not in json.dumps(procedures) and "Workbench" not in json.dumps(procedures)


def test_people_plan_moves_pilot_work_to_the_human_operator(client, monkeypatch):
    from app.pipeline import playbook

    bc, mods, reg = _skeleton()
    db = SessionLocal()
    row = Request(business_name="iCARRY Lebanon", business_description="d", email="t@example.com", status="done",
                  is_generating=False, modules_json=json.dumps(mods), business_case_json=json.dumps(bc), registry_json=json.dumps(reg))
    db.add(row)
    db.commit()
    payload = {"steps": [{"title": "Approve the gate", "detail": "Sign off [[PILOT_GATE]]", "phase": "before", "who": "you"}],
               "quick_wins": [], "people_plan": {
                   "ai_covers": ["Pre-Dispatch WhatsApp Pilot confirms addresses with customers", "COD Settlement Inquiry AI Handler answers settlement questions"],
                   "humans_needed": [{"role": "Pre-Dispatch WhatsApp Pilot", "when": "now", "why": "x"}]}}
    monkeypatch.setattr(playbook.provider, "chat", lambda *a, **k: {"choices": [{"message": {"content": json.dumps(payload)}}], "usage": {}})
    out = playbook.write_playbook(db, row.id, {"concept_name": "C"}, {"modules": mods, "business_case": bc, "registry": reg})
    people = out["people_plan"]
    assert people["ai_covers"] == ["COD Settlement Inquiry AI Handler answers settlement questions"]
    assert all(h["role"] != "Pre-Dispatch WhatsApp Pilot" for h in people["humans_needed"])
    assert any(h["role"] == "Pilot Support Operator" for h in people["humans_needed"])
    assert out["steps"][0]["detail"].endswith(reg["pilot_gate_sentence"])
    db.close()
