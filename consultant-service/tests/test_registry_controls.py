"""Run 46's defects, closed structurally: the typed claim registry, the
canonical pilot gate, module KPI rendering, threshold typing, the single
monthly identity, honest pilot-module naming, build order by name, phase
semantics, adjudication R2/R6/R7, and a release report that adds up.

Every fixture below is the exact run-46 text or shape.
"""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

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


def _seed(db, **overrides):
    row = Request(business_name="iCARRY Lebanon", business_description="delivery platform",
                  email="t@example.com", status="done", is_generating=False)
    for k, v in overrides.items():
        setattr(row, k, v)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


OPS = json.dumps([
    {"question": "Deliveries per day and average delivery fee?", "answer": "900 deliveries a day, average fee $2.50"},
    {"question": "Failed first attempts and re-attempt cost?",
     "answer": "12% of deliveries fail first attempt; each re-attempt costs about $1.80"},
    {"question": "'Where is my order' WhatsApp inquiries per day?", "answer": "About 350 a day, handled by 5 support staff"},
    {"question": "COD settlement inquiries per month?", "answer": "Around 300 inquiries"},
    {"question": "Staff hours per week reconciling COD and preparing statements?",
     "answer": "About 45 hours across our finance team"},
    {"question": "Days after month-end to fully settle COD with a client?", "answer": "10 days"},
])

GATE46 = {
    "duration": "6 weeks (proposed — client approval required)",
    "population": "All new customer orders within a specific geographic zone (e.g., Beirut Central District)",
    "control": "Orders outside the pilot zone or existing customer orders within the pilot zone",
    "primary_metric": "First-attempt delivery success rate",
    "baseline": "12% failed first attempts (88% success rate), measured in week 1",
    "target": "A 5 percentage point increase in first-attempt delivery success rate (proposed — client approval required)",
    "secondary_metrics": ["Driver average phone call time per delivery"],
    "guardrail": "Any increase in average delivery time by more than 10 minutes (proposed)",
    "approvals_required": ["Pilot duration", "Pilot population", "Primary metric target"],
}
GATE47 = {**GATE46, "numerator": "deliveries completed on the first attempt",
          "denominator": "all delivery attempts in the pilot population",
          "change_kind": "percentage_point", "target_value": 5}

# the three run-46 restatements of one gate
VARIANT_DECISION = ("The decision gate to unlock Phase 2 is a 5 percentage point increase in first-attempt "
                    "delivery success rate (proposed — client approval required), from a baseline of 88% "
                    "success, measured in week 1 (proposed — client approval required).")
VARIANT_KPI = ("First-attempt delivery success rate increases by 5 percentage points (primary pilot metric: "
               "A 5 percentage point increase in first-attempt delivery success rate within 6 weeks of pilot "
               "launch in the specified geographic zone).")
VARIANT_MODULE = "The first-attempt delivery success rate increases by 5 percentage points (within 6 weeks of pilot launch)."

FM46 = {
    "lines": [
        {"item": "Annual Failed First Attempt Re-attempt Costs",
         "arithmetic": "900 deliveries/day * 12% failed first attempts * $1.80 re-attempt cost * 365 days/year",
         "annual": "$70,956/year"},
        {"item": "Annual 'Where is my order' Inquiries (volume)", "arithmetic": "350 inquiries/day * 365 days/year",
         "annual": "127,750 inquiries/year"},
    ],
    "scenarios": [
        {"name": "Conservative", "assumption": "The system prevents 1 in 5 failed first attempts (20% reduction) and automates 30% of 'where is my order' and 20% of COD settlement inquiries.",
         "impact": "~$14,191/year hard savings + ~38,325 'where is my order' inquiries automated/year + ~720 COD inquiries automated/year + ~468 finance hours/year released, by your own figures."},
        {"name": "Expected", "assumption": "The system prevents 1 in 3 failed first attempts (33% reduction) and automates 60% of 'where is my order' and 40% of COD settlement inquiries.",
         "impact": "~$23,415/year hard savings + ~76,650 'where is my order' inquiries automated/year + ~1,440 COD inquiries automated/year + ~936 finance hours/year released, by your own figures."},
        {"name": "Upside", "assumption": "The system prevents 1 in 2 failed first attempts (50% reduction) and automates 80% of 'where is my order' and 60% of COD settlement inquiries.",
         "impact": "~$35,478/year hard savings + ~102,200 'where is my order' inquiries automated/year + ~2,160 COD inquiries automated/year + ~1,404 finance hours/year released, by your own figures."},
    ],
    "payback_note": "To compute payback, divide the build quote by the Expected monthly financial impact (approximately $1,977/month hard savings plus value of released staff capacity).",
    "missing_inputs": ["Your fully-loaded hourly cost for support staff", "Your fully-loaded hourly cost for finance staff"],
}

MODULES46 = [
    {"id": "pre-dispatch-whatsapp-engine", "name": "Pre-Dispatch WhatsApp Engine",
     "purpose": "confirms address and window before dispatch", "depends_on": [],
     "spec": {"ai": None, "kpis": [
         "The percentage of orders confirmed via WhatsApp before dispatch (proposed — client approval required) reaches 80% within 6 weeks of pilot launch.",
         "The average time from order creation to customer WhatsApp confirmation (proposed — client approval required) is under 15 minutes."]},
     "tech": {"done_when": [
         "A new order for the pilot zone is created in the iCARRY Order Management System and a personalized WhatsApp message is sent to the customer within 60 seconds (proposed — client approval required).",
         "An order requiring manual intervention is correctly flagged for iCARRY operations staff after two unanswered reminder messages or unresolved address ambiguity, and a notification is sent within 5 minutes.",
         "For 95% of confirmed orders in the pilot zone, both the delivery address and preferred window are explicitly confirmed by the customer via WhatsApp before driver dispatch."],
         "ai_agent": None}},
    {"id": "delivery-incident-predictor", "name": "Delivery Incident Predictor",
     "purpose": "predicts likely failures", "depends_on": ["pre-dispatch-whatsapp-engine"],
     "spec": {"ai": {"role": "scores risk"}, "kpis": [
         "A 15% reduction in preventable delivery failures flagged by the module (proposed — client approval required) is observed within 3 months of launch.",
         "The module achieves 80% accuracy for the top 3 predicted failure reasons (proposed — client approval required) identified.",
         "An A/B test (proposed — client approval required) demonstrates that orders flagged by the predictor for intervention have a 10% higher first-attempt success rate compared to a control group."]},
     "tech": {"done_when": [
         "The `/predict-delivery-incident` API successfully returns a risk score and predicted reasons for 100% of new e-commerce COD and express on-demand orders within 500ms (proposed — client approval required) for pilot regions."],
         "ai_agent": {"evaluation": [
             "Offline backtesting: Compare model predictions against actual outcomes for 100,000 historical orders, measuring precision, recall, and F1-score.",
             "Human-in-the-loop: For the first 1,000 flagged incidents, an operations supervisor manually reviews each flagged order.",
             "Weekly, 100 generated prompts will be checked for accuracy and helpfulness, aiming for over 90% accuracy."]}}},
    {"id": "driver-clarification-assistant", "name": "Driver Clarification Assistant",
     "purpose": "guides drivers", "depends_on": ["pre-dispatch-whatsapp-engine", "delivery-incident-predictor"],
     "spec": {"ai": {"role": "prompts drivers"}, "kpis": [
         "A 15% reduction in driver's average phone call time per delivery (proposed — client approval required) is observed within 3 months of launch.",
         "A 20% decrease in \"high re-attempt risk\" orders needing a second dispatch (proposed — client approval required) due to address confusion is achieved."]},
     "tech": {"done_when": [
         "The 'Pre-Dispatch Location Refinement Display' section appears in the driver app for 100% of orders having refined address details from the Pre-Dispatch WhatsApp Engine."],
         "ai_agent": None}},
    {"id": "client-portal-notifier", "name": "Client Portal Notifier", "purpose": "notifies clients",
     "depends_on": [],
     "spec": {"ai": None, "kpis": [
         "The engagement rate with portal notifications (proposed — client approval required) increases by 25% within 3 months of launch.",
         "Notifications achieve a click-through rate of at least 20% (proposed — client approval required) for linked detailed reports.",
         "Finance team time spent on manual COD inquiries reduces by 50%."]},
     "tech": {"done_when": [], "ai_agent": None}},
]
BUILD_ORDER46 = ["pre-dispatch-whatsapp-engine", "delivery-incident-predictor",
                 "driver-clarification-assistant", "client-portal-notifier"]
COINED46 = ["15%", "80%", "10% higher", "20% decrease", "25%", "20%", "50%", "70%", "15 minutes"]

BUILD_FIRST46 = ("## What we'd build first\n\n"
                 "1.  **pre-dispatch-whatsapp-engine:** This module directly addresses your biggest pain point.\n"
                 "2.  **delivery-incident-predictor:** It leverages the data from the Pre-Dispatch WhatsApp Engine.\n"
                 "3.  **driver-clarification-assistant:** It provides immediate intelligence to drivers.\n"
                 "4.  **client-portal-notifier:** It enhances client transparency.\n")

COST46 = ("**What staying manual costs:** Staying as they are costs iCARRY approximately $5,913/month in re-attempt "
          "costs alone (900 deliveries/day * 12% failed * $1.80/re-attempt * 30 days, or $70,956/year / 12 months) "
          "by your own figures.")


def _skeleton():
    bc = {"financial_model": copy.deepcopy(FM46), "pilot_gate": copy.deepcopy(GATE47),
          "build_order": list(BUILD_ORDER46),
          "cost_of_inaction": "Staying as they are costs iCARRY approximately $5,832/month in re-attempt costs alone."}
    mods = copy.deepcopy(MODULES46)
    from app.pipeline.decompose import _sanitize_financial_model

    _sanitize_financial_model(bc)
    reg = rg.build_registry(OPS, bc, mods, free_texts=["COD settlement inquiries (around 300 a month)"])
    return bc, mods, reg


# ── §3 canonical pilot gate ─────────────────────────────────────────────────


def test_gate_is_one_typed_object_and_one_sentence():
    claims = rg.client_fact_claims(json.loads(OPS), [])
    g = pg.normalize_gate(GATE47, claims)
    assert pg.gate_errors(g) == []
    assert g["duration_value"] == 6 and g["duration_unit"] == "week"
    assert g["geography"] == "Beirut Central District" and "e.g." not in g["population"]
    assert g["change_kind"] == "percentage_point" and g["target_value"] == 5 and g["direction"] == "rise"
    assert g["baseline_source"] == "client" and g["baseline_value"] == 12
    assert g["numerator"] and g["denominator"] and g["control_method"] and g["guardrails"]
    s = pg.canonical_sentence(g)
    assert s.startswith("Pilot decision gate: over a 6-week pilot (proposed — client approval required)")
    assert "divided by" in s and "must rise by 5 percentage points" in s and "(your figure)" in s
    assert "the pilot pauses if" in s and s.count("(proposed — client approval required)") == 2
    # the same object always renders the same sentence
    assert pg.canonical_sentence(pg.normalize_gate(GATE47, claims)) == s


def test_run46_gate_lacks_the_typed_components_and_is_rejected_before_prose():
    from app.pipeline.structural import preflight

    g = pg.normalize_gate(GATE46, [])
    errs = pg.gate_errors(g)
    assert "missing numerator" in errs and "missing denominator" in errs
    findings = preflight({"pilot_gate": GATE46, "build_order": BUILD_ORDER46}, copy.deepcopy(MODULES46))
    assert any("pilot gate is not a whole typed object" in f["issue"] for f in findings)


def test_all_three_run46_gate_variants_are_rejected_and_the_canonical_sentence_accepted():
    g = pg.normalize_gate(GATE47, rg.client_fact_claims(json.loads(OPS), []))
    for variant in (VARIANT_DECISION, VARIANT_KPI, VARIANT_MODULE):
        assert pg.is_paraphrase(variant, g), variant
        assert len(pg.restatement_findings(variant, g)) == 1
    canon = pg.canonical_sentence(g)
    assert not pg.is_paraphrase(canon, g)
    assert pg.restatement_findings("The decision gate: " + canon, g) == []
    # an innocent sentence naming the metric with a client figure is not a paraphrase
    assert not pg.is_paraphrase("Every failed first-attempt delivery costs you $1.80 to re-attempt.", g)
    assert not pg.is_paraphrase("12% of deliveries fail the first attempt, by your own figures.", g)


def test_enforce_substitutes_the_token_and_replaces_every_paraphrase():
    g = pg.normalize_gate(GATE47, rg.client_fact_claims(json.loads(OPS), []))
    canon = pg.canonical_sentence(g)
    md = ("## The decision\n\n- **Phase 1 — Pre-Dispatch WhatsApp Pilot:** proves the mechanism. "
          "The decision gate: [[PILOT_GATE]]\n- **Phase 2 — Prediction:** " + VARIANT_MODULE + "\n\n"
          "## The product, module by module\n\n**You'll know it's working when:** " + VARIANT_KPI + "\n")
    out, report = pg.enforce(md, g)
    assert report["token_substitutions"] == 1 and report["paraphrases_replaced"] == 2
    assert out.count(canon) == 3 and "[[PILOT_GATE]]" not in out
    assert pg.restatement_findings(out, g) == []
    # a decision section that forgot the token gets the sentence inserted after Phase 1
    bare = "## The decision\n\n- **Phase 1 — Pilot:** proves the mechanism.\n- **Phase 2 — AI:** later.\n\n## Executive summary\nx\n"
    fixed = pg.ensure_in_decision(bare, g)
    assert canon in fixed and fixed.index(canon) < fixed.index("Phase 2")


# ── §2 / §4 typed registry and module KPIs ──────────────────────────────────


def test_registry_validates_and_types_every_release_critical_claim():
    bc, mods, reg = _skeleton()
    assert reg["errors"] == []
    types = {c["type"] for c in reg["claims"]}
    for needed in ("client_fact", "derived_value", "time_basis_conversion", "scenario_assumption",
                   "scenario_impact", "pilot_gate", "module_kpi", "timing_sla", "performance_target",
                   "capacity_assumption", "sampling_requirement"):
        assert needed in types, needed
    for c in reg["claims"]:
        for k in ("id", "type", "value", "unit", "time_basis", "population", "scope", "phase",
                  "provenance", "approval_status", "source", "allowed_sections"):
            assert k in c, (c["id"], k)
    # a broken claim fails validation
    bad = copy.deepcopy(reg)
    bad["claims"][0].pop("unit")
    bad["claims"][1]["provenance"] = "consultant_proposed"
    bad["claims"][1]["approval_status"] = "client_stated"
    errs = rg.validate_registry(bad)
    assert any("missing unit" in e for e in errs) and any("approval-required" in e for e in errs)


def test_no_module_kpi_number_is_coined_and_proposals_stay_out_of_documents():
    bc, mods, reg = _skeleton()
    statements = " ".join((m["spec"] or {}).get("kpi_statement", "") for m in mods)
    for coined in COINED46:
        assert coined not in statements, coined
    assert rg.WEEK_ONE_SENTENCE in statements
    # the pilot module's KPI IS the canonical sentence
    pilot = next(m for m in mods if m["pilot"])
    assert pilot["spec"]["kpi_statement"].startswith(reg["pilot_gate_sentence"])
    # every coined candidate is registered as a proposal awaiting approval, not accepted
    props = [c for c in rg.proposals(reg) if c["type"] == "module_kpi"]
    assert len(props) >= 8
    assert all(c["approval_status"] == "consultant_proposed — client approval required" and not c.get("accepted")
               for c in props)
    # the prose model never sees the candidates
    from app.pipeline.blueprint import _prompt_modules

    shown = json.dumps(_prompt_modules(mods))
    assert "kpi_candidates" not in shown and "15% reduction" not in shown


def test_final_text_validator_maps_every_kpi_number_to_a_claim(client):
    bc, mods, reg = _skeleton()
    canon = reg["pilot_gate_sentence"]
    good = ("**You'll know it's working when:** " + canon + "\n"
            "**You'll know it's working when:** Orders confirmed before dispatch — " + rg.WEEK_ONE_SENTENCE + "\n"
            "**You'll know it's working when:** Failed first attempts prevented: 20% (scenario assumption — requires your approval, claim SA-01-1).\n")
    assert rg.kpi_number_findings(good, reg, strict_kpi=True) == []
    for coined in ("A 15% reduction in preventable delivery failures", "achieves 80% accuracy for the top 3 reasons",
                   "a click-through rate of at least 20%", "is under 15 minutes"):
        bad = "**You'll know it's working when:** " + coined + " within 3 months of launch.\n"
        found = rg.kpi_number_findings(bad, reg, strict_kpi=True)
        assert found and "maps to no registered claim" in found[0]["issue"], coined
    # Volume II: a typed, labeled evaluation threshold in "how you'll know it's working" is legitimate
    tech = ("**How you'll know it's working:** Weekly, 100 generated prompts (proposed — client approval required) "
            "will be checked, aiming for over 90% accuracy (proposed — client approval required).\n")
    assert rg.kpi_number_findings(tech, reg, strict_kpi=False) == []
    # the gate blocks release on it
    db = SessionLocal()
    row = _seed(db, mvp_blueprint="## The decision\nx\n**You'll know it's working when:** A 15% reduction is observed.\n",
                qa_report_json=json.dumps({"checks": [], "findings": []}),
                registry_json=json.dumps(reg), business_case_json=json.dumps(bc), modules_json=json.dumps(mods))
    from app.pipeline import export_pdf as ep

    status = ep.release_status(row)
    assert status["status"] == "draft" and any("map to no registered claim" in r for r in status["reasons"])
    db.close()


# ── §5 threshold types ───────────────────────────────────────────────────────


def test_threshold_categories_are_distinct_and_functional_requirements_become_words():
    claims = rg.client_fact_claims(json.loads(OPS), [])
    counter = {"n": 0}
    cases = {
        "returns a risk score for 100% of new e-commerce COD orders within 500ms": ("all new e-commerce", "performance_target"),
        "Offline testing will compare predictions for 100,000 historical orders.": (None, "capacity_assumption"),
        "For the first 1,000 flagged incidents, a supervisor reviews predictions.": (None, "sampling_requirement"),
        "aiming for over 90% accuracy in address validation.": (None, "performance_target"),
        "a notification is sent within 5 minutes.": (None, "timing_sla"),
    }
    for text, (words, category) in cases.items():
        out, new = rg.threshold_pass(text, claims, source="tech.done_when[0]", module_id="m", counter=counter)
        assert new and new[0]["type"] == category, (text, [c["type"] for c in new])
        assert rg.PROPOSED_LABEL in out, text
        if words:
            assert words in out and "100%" not in out
    # a client figure inside a check is a historical fact — no label
    out, new = rg.threshold_pass("handles the 350 inquiries a day you receive", claims,
                                 source="tech.done_when[0]", module_id="m", counter=counter)
    assert new[0]["type"] == "historical_fact" and rg.PROPOSED_LABEL not in out
    # an already-labeled value is registered, not double-labeled
    out, new = rg.threshold_pass("within 60 seconds (proposed — client approval required).", claims,
                                 source="tech.done_when[0]", module_id="m", counter=counter)
    assert out.count(rg.PROPOSED_LABEL) == 1 and new[0]["type"] == "timing_sla"
    # narrative numbers are not thresholds: the prose pass leaves them alone
    out, new = rg.label_prose_thresholds("The build has 3 phases and 4 records.\nIt's finished when the reply "
                                         "arrives within 30 seconds.", claims, counter)
    assert "3 phases" in out and "4 records" in out and "30 seconds (proposed" in out


def test_run46_technical_specs_come_out_typed_labeled_and_registered():
    bc, mods, reg = _skeleton()
    dip = next(m for m in mods if m["id"] == "delivery-incident-predictor")
    evaluation = " ".join(dip["tech"]["ai_agent"]["evaluation"])
    assert "100,000 historical orders (proposed — client approval required)" in evaluation
    assert "1,000 flagged incidents (proposed — client approval required)" in evaluation
    assert "90% accuracy (proposed — client approval required)" in evaluation
    assert "all new e-commerce COD" in dip["tech"]["done_when"][0]
    dca = next(m for m in mods if m["id"] == "driver-clarification-assistant")
    assert "for all orders having refined" in dca["tech"]["done_when"][0]
    pre = next(m for m in mods if m["pilot"])
    assert "within 5 minutes (proposed — client approval required)" in pre["tech"]["done_when"][1]
    by_type = {}
    for c in reg["claims"]:
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1
    assert by_type.get("capacity_assumption") and by_type.get("sampling_requirement") and by_type.get("timing_sla")


# ── §6 one monthly identity ─────────────────────────────────────────────────


def test_package_wide_monthly_identity_for_the_70956_claim():
    annual = 70956.0
    assert abs(tb.candidates(annual, "per day")[0][0] - 194.40) < 0.005
    assert abs(tb.candidates(annual, "per month")[0][0] - 5832.0) < 0.01
    assert len(tb.candidates(annual, "per month")) == 1
    out, recs = tb.check_restatements(COST46, [annual])
    assert "$5,832/month" in out and "$5,913" not in out
    assert "/ 12 months" not in out and "/ 365 x 30 days" in out
    assert {r["status"] for r in recs} >= {"identity_corrected", "snapped"}
    assert all(r["identity"] == tb.MONTHLY_IDENTITY for r in recs
               if "identity" in r and "month" in str(r.get("basis", "month")))
    # the calendar identity never verifies, anywhere in the package
    findings = tb.identity_findings({"blueprint": "about $5,913 per month", "business case": "$5,832/month"}, [annual])
    assert len(findings) == 1 and "calendar-month identity" in findings[0]["issue"]
    assert tb.identity_findings({"b": COST46}, [annual])  # mixed formula in one sentence
    from app.pipeline import export_pdf as ep

    assert "mixed monthly identity" in ep.find_artifacts(COST46)


def test_latent_1977_payback_value_is_corrected_in_the_structured_layer():
    from app.pipeline.decompose import _sanitize_financial_model

    bc = {"financial_model": copy.deepcopy(FM46)}
    _sanitize_financial_model(bc)
    fm = bc["financial_model"]
    assert all(sc.get("impact_verified") for sc in fm["scenarios"])
    assert "$1,977" not in fm["payback_note"] and "$1,925" in fm["payback_note"]
    rec = next(r for r in fm["restatements"] if r["original"] == "$1,977")
    assert rec["status"] == "snapped" and "23,415/year / 365 x 30" in rec["formula"]
    assert fm["time_basis"]["monthly_identity"] == "operating_30_day_month" if "time_basis" in fm else True


# ── §7 / §8 module names and build order ────────────────────────────────────


def test_pilot_module_is_named_honestly_in_every_structure():
    bc, mods, reg = _skeleton()
    pilot = next(m for m in mods if m["pilot"])
    assert pilot["client_facing_name"] == "Pre-Dispatch WhatsApp Pilot" == pilot["name"]
    assert pilot["original_name"] == "Pre-Dispatch WhatsApp Engine"
    assert pilot["automation_level"] in ("manual", "rules") and pilot["phase"] == "PILOT"
    assert reg["renames"] == [{"id": "pre-dispatch-whatsapp-engine", "from": "Pre-Dispatch WhatsApp Engine",
                               "to": "Pre-Dispatch WhatsApp Pilot"}]
    # every other mention followed the rename
    assert "Engine" not in json.dumps(bc)
    dca = next(m for m in mods if m["id"] == "driver-clarification-assistant")
    assert "Pre-Dispatch WhatsApp Pilot" in dca["tech"]["done_when"][0]
    assert rg.canonical_pilot_name("Smart Predictive Scoring Engine") == "Manual Pilot"
    assert rg.canonical_pilot_name("Order Intake Pilot") == "Order Intake Pilot"
    # an AI-automated pilot module is a preflight failure
    from app.pipeline.structural import preflight

    mods2 = copy.deepcopy(mods)
    mods2[0]["automation_level"] = "ai"
    assert any("cannot be AI" in f["issue"] or "AI-automated" in f["issue"] for f in preflight(bc, mods2))


def test_build_order_renders_by_name_and_raw_ids_are_release_artifacts(client):
    bc, mods, reg = _skeleton()
    assert reg["build_order_names"] == ["Pre-Dispatch WhatsApp Pilot", "Delivery Incident Predictor",
                                        "Driver Clarification Assistant", "Client Portal Notifier"]
    resolved = rg.resolve_module_ids(BUILD_FIRST46, mods)
    assert "**Pre-Dispatch WhatsApp Pilot:**" in resolved and "pre-dispatch-whatsapp-engine" not in resolved
    assert "**Client Portal Notifier:**" in resolved
    from app.pipeline import export_pdf as ep

    assert "internal identifier in client-facing text" in ep.find_artifacts(BUILD_FIRST46)
    assert ep.find_artifacts(resolved) == []
    assert rg.identifier_artifacts(BUILD_FIRST46, [m["id"] for m in mods]) != []
    assert rg.identifier_artifacts("a cash-on-delivery, state-of-the-art first-and-last-mile network", []) == []
    # the inspection tool fails the exact run-46 page text
    import inspect_pdf  # noqa: F401 — uses find_artifacts; exercised through release_status below

    db = SessionLocal()
    row = _seed(db, mvp_blueprint=BUILD_FIRST46, qa_report_json=json.dumps({"checks": [], "findings": []}))
    assert ep.release_status(row)["status"] == "draft"
    db.close()


# ── §9 phase semantics ───────────────────────────────────────────────────────


def test_phase_semantics_positive_and_negative():
    from app.pipeline.phases import future_is_consistent, phase_findings

    bc, mods, reg = _skeleton()
    future_ok = [{"name": "Reviewing the incident queue", "phase": "future", "module": "Delivery Incident Predictor",
                  "trigger": "each morning", "steps": [{"actor": "operations lead", "step": "Open the incident queue and review flagged orders."}]}]
    assert phase_findings(future_ok, mods) == []
    assert future_is_consistent(future_ok, mods)[0] is True
    future_now = [{"name": "Reviewing the incident queue", "phase": "future", "module": "Delivery Incident Predictor",
                   "trigger": "starting today", "steps": [{"actor": "operations lead", "step": "Do this immediately."}]}]
    assert any("instructs staff to execute" in f["issue"] for f in phase_findings(future_now, mods))
    current_unbuilt = [{"name": "Checking predictions", "phase": "current", "module": "Delivery Incident Predictor",
                        "trigger": "daily", "steps": [{"actor": "ai", "step": "Delivery Incident Predictor scores the orders."}]}]
    assert any("usable today" in f["issue"] for f in phase_findings(current_unbuilt, mods))
    pilot_with_ai = [{"name": "Confirming orders", "phase": "pilot", "module": "The pilot", "trigger": "order created",
                      "steps": [{"actor": "ai", "step": "Send the confirmation."}]}]
    assert any("pilot must be executable without" in f["issue"] for f in phase_findings(pilot_with_ai, mods))


# ── §1 adjudication rules on the exact run-46 findings ──────────────────────


def _finding(where, issue, fix="Change it.", source="qa_numbers_recheck"):
    return {"severity": "high", "source": source, "where": where, "issue": issue, "fix": fix}


def test_r2_label_evidence_outranks_the_auditors_wording(client):
    from app.pipeline.adjudicate import adjudicate

    rendered = {"technical": ("a personalized WhatsApp message is sent to the customer within 60 seconds "
                              "(proposed — client approval required). the module sends a relevant clarification "
                              "question within 30 seconds (proposed — client approval required). and a notification "
                              "is sent within 5 minutes. For 95% of confirmed orders")}
    db = SessionLocal()
    row = _seed(db, qa_report_json=json.dumps({"checks": [], "findings": [
        _finding("THE TECHNICAL PLAN DOCUMENT -> Pre-Dispatch WhatsApp Engine",
                 "The threshold '60 seconds' is an invented, unverified threshold. It lacks '(proposed — client approval required)'."),
        _finding("THE TECHNICAL PLAN DOCUMENT -> Pre-Dispatch WhatsApp Engine",
                 "The threshold '30 seconds' is an invented, unverified threshold. It lacks '(proposed — client approval required)'."),
        _finding("THE TECHNICAL PLAN DOCUMENT -> Pre-Dispatch WhatsApp Engine",
                 "The threshold '5 minutes' is an invented, unverified threshold. It lacks '(proposed — client approval required)'."),
    ]}))
    result = adjudicate(row, rendered)
    kinds = [e["classification"] for e in result["ledger"]]
    assert kinds == ["machine-proven false positive", "machine-proven false positive", "real defect"]
    assert "all 1 occurrence(s) labeled" in result["ledger"][0]["evidence"]
    assert "carry no approval label" in result["ledger"][2]["evidence"]
    db.close()


def test_r7_functional_requirement_and_r6_phase_semantics(client):
    from app.pipeline.adjudicate import adjudicate

    bc, mods, reg = _skeleton()
    procedures = [{"name": "Reviewing the incident queue", "phase": "future", "module": "Delivery Incident Predictor",
                   "trigger": "each morning", "steps": [{"actor": "operations lead", "step": "Review flagged orders."}]},
                  {"name": "Initiating Pre-Dispatch Delivery Confirmation", "phase": "pilot", "module": "Pre-Dispatch WhatsApp Pilot",
                   "trigger": "order created", "steps": [{"actor": "dispatcher", "step": "Send the WhatsApp message."}]}]
    db = SessionLocal()
    row = _seed(db, modules_json=json.dumps(mods), procedures_json=json.dumps({"procedures": procedures}),
                qa_report_json=json.dumps({"checks": [], "findings": [
                    _finding("THE TECHNICAL PLAN DOCUMENT -> Delivery Incident Predictor",
                             "The threshold '100%' for success is an invented, unverified threshold. While '500ms' is attributed, '100%' is not."),
                    _finding("Procedures list",
                             "The 'Procedures' structured layer lists multiple procedures with `\"phase\": \"future\"` for modules like "
                             "'Pre-Dispatch WhatsApp Engine', 'Delivery Incident Predictor'. However, the 'What we'd build first' section "
                             "lists all of these modules in a numbered sequence, implying immediate implementation.",
                             source="qa_completeness"),
                ]}))
    rendered = {"technical": "returns a risk score and predicted reasons for 100% of new e-commerce COD orders within 500ms (proposed — client approval required)."}
    result = adjudicate(row, rendered)
    assert result["ledger"][0]["classification"] == "semantic false positive resolved by structured threshold typing"
    assert "functional completeness requirement" in result["ledger"][0]["evidence"]
    assert result["ledger"][1]["classification"] == "semantic false positive resolved by structured phase data"
    # but a FUTURE procedure that says "today" keeps the finding open
    procedures[0]["trigger"] = "starting today"
    row.procedures_json = json.dumps({"procedures": procedures})
    row.qa_report_json = json.dumps({"checks": [], "findings": [
        _finding("Procedures list", "procedures with phase future contradict the build first sequence", source="qa_completeness")]})
    db.commit()
    assert adjudicate(row)["ledger"][0]["classification"] == "real defect"
    db.close()


# ── §10 release-report arithmetic ───────────────────────────────────────────


def test_release_report_totals_come_from_the_manifest_and_inconsistent_totals_fail():
    import release_audit as ra

    volumes = {"blueprint": {"pages": 21, "inspected_pages": 21, "every_page_inspected": True, "inspection_ok": True, "failures": []},
               "technical": {"pages": 31, "inspected_pages": 31, "every_page_inspected": True, "inspection_ok": True, "failures": []},
               "operations": {"pages": 17, "inspected_pages": 17, "every_page_inspected": True, "inspection_ok": True, "failures": []}}
    totals = ra.totals_from(volumes)
    assert totals == {"volumes": 3, "pages": 69, "inspected_pages": 69, "every_page_inspected": True}
    record = {"status": "final", "reasons": [], "volumes": volumes, "totals": dict(totals)}
    assert ra.validate_record(record) == []
    wrong = copy.deepcopy(record)
    wrong["totals"]["pages"] = 98
    assert any("69" in e for e in ra.validate_record(wrong))
    over = copy.deepcopy(record)
    over["totals"]["inspected_pages"] = 70
    assert any("exceed" in e or "!=" in e for e in ra.validate_record(over))
    partial = copy.deepcopy(record)
    partial["volumes"]["technical"]["inspected_pages"] = 30
    partial["volumes"]["technical"]["every_page_inspected"] = False
    partial["totals"] = ra.totals_from(partial["volumes"])
    assert partial["totals"]["every_page_inspected"] is False
    assert any("every page" in e for e in ra.validate_record(partial))  # final without every page
    lie = copy.deepcopy(partial)
    lie["totals"]["every_page_inspected"] = True
    assert any("every-page claim" in e for e in ra.validate_record(lie))


def test_audit_run_records_validated_totals_and_reaudit_never_touches_the_source(client, tmp_path, monkeypatch):
    import release_audit as ra
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    bc, mods, reg = _skeleton()
    db = SessionLocal()
    row = _seed(db, mvp_blueprint="## The decision\nA plan.\n\n## Executive summary\nfine\n",
                technical_plan="## How your system works\nfine\n",
                procedures_json=json.dumps({"procedures": [{"name": "Daily check", "phase": "pilot", "module": "The pilot",
                                                            "trigger": "morning", "steps": [{"actor": "you", "step": "Check the log."}]}]}),
                qa_report_json=json.dumps({"checks": [], "findings": [
                    _finding("x", "The threshold '60 seconds' is an invented, unverified threshold. It lacks the label.")]}),
                registry_json=json.dumps(reg), business_case_json=json.dumps(bc), modules_json=json.dumps(mods),
                ops_numbers_json=OPS)
    record = ra.audit_run(row)
    assert record["totals"]["pages"] == sum(v["pages"] for v in record["volumes"].values())
    assert record["totals"]["inspected_pages"] == record["totals"]["pages"]
    assert record["totals"]["every_page_inspected"] is True and record["validation_errors"] == []
    assert record["status"] == "draft"
    rev_dir = os.path.dirname(record["record_path"])
    hashes_before = {k: v["sha256"] for k, v in record["volumes"].items()}
    # the improved audit of the frozen revision: new dir, source untouched
    audit = ra.reaudit_revision(rev_dir, row)
    assert audit["audit_revision"].endswith("-a2") and os.path.isdir(os.path.dirname(audit["record_path"]))
    assert audit["source_integrity"] == "valid" == audit["source_integrity_after"]
    assert {k: v["sha256"] for k, v in audit["volumes"].items()} == hashes_before
    assert ra.verify(record["record_path"]) == "valid"
    assert audit["totals"]["pages"] == record["totals"]["pages"] and audit["validation_errors"] == []
    # the run's persisted findings were read, never written
    db.refresh(row)
    assert "adjudication" not in json.loads(row.qa_report_json)["findings"][0]
    db.close()


# ── the operations layers and the finished documents ────────────────────────


def test_canonicalize_layers_puts_the_gate_sentence_in_the_scoreboard_and_the_sop():
    from app.pipeline.extras import canonicalize_layers

    bc, mods, reg = _skeleton()
    gate = reg["pilot_gate"]
    canon = reg["pilot_gate_sentence"]
    procedures = [{"name": "The gate review", "phase": "pilot", "module": "The pilot", "trigger": "end of week 6",
                   "steps": [{"actor": "you", "step": "Compare pilot against control: [[PILOT_GATE]]"},
                             {"actor": "dispatcher", "step": "Escalate any customer unreachable after 30 minutes."}]}]
    by_name = {"governance": {"scoreboard": [
        {"metric": "First-attempt delivery success rate", "baseline": "12%", "target": "+5 pp (proposed)", "owner": "you", "review": "weekly"},
        {"metric": "COD settlement inquiries per month", "baseline": "300", "target": "down", "owner": "finance", "review": "monthly"}]},
        "checklists": {"checklists": [{"name": "Daily close", "items": ["All pins confirmed within 2 hours of order creation"]}]}}
    canonicalize_layers(procedures, by_name, mods, reg, gate)
    assert procedures[0]["steps"][0]["step"].endswith(canon)
    assert "30 minutes (proposed — client approval required)" in procedures[0]["steps"][1]["step"]
    assert by_name["governance"]["scoreboard"][0]["target"] == canon
    assert by_name["governance"]["scoreboard"][1]["target"] == "down"
    assert "(proposed — client approval required)" in by_name["checklists"]["checklists"][0]["items"][0]
    assert any(c["type"] == "operational_policy" for c in reg["claims"])


def test_finish_document_closes_every_run46_volume_i_defect_at_once():
    from app.pipeline.blueprint import finish_document

    bc, mods, reg = _skeleton()
    canon = reg["pilot_gate_sentence"]
    md = ("## The decision\n\n- **Phase 1 — Pilot Delivery Confirmation:** proves the mechanism. " + VARIANT_DECISION + "\n"
          "- **Phase 2 — Prediction:** built from Phase 1 data.\n\n## How this makes money\n\n" + COST46 + "\n\n"
          "## The product, module by module\n\n### Delivery Incident Predictor\n**You'll know it's working when:** " + VARIANT_MODULE + "\n\n"
          + BUILD_FIRST46)
    out, report = finish_document(md, modules=mods, business_case=bc, registry=reg, kind="blueprint")
    assert out.count(canon) == 2 and pg.restatement_findings(out, reg["pilot_gate"]) == []
    assert "$5,832/month" in out and "$5,913" not in out and "/ 12 months" not in out
    assert "**Pre-Dispatch WhatsApp Pilot:**" in out and "pre-dispatch-whatsapp-engine" not in out
    from app.pipeline import export_pdf as ep

    assert ep.find_artifacts(out) == []
    assert rg.kpi_number_findings(out, reg) == []


def test_preflight_fixture_for_run_47_has_zero_structural_findings(client):
    """The intended run-47 skeleton (run 46's structures after the registry's
    deterministic passes) carries no structural finding; the raw run-46
    skeleton carries the typed-gate finding."""
    import preflight_fixture
    from app.pipeline.structural import preflight

    db = SessionLocal()
    row = _seed(db, ops_numbers_json=OPS, business_case_json=json.dumps(
        {"financial_model": copy.deepcopy(FM46), "pilot_gate": copy.deepcopy(GATE46),
         "build_order": list(BUILD_ORDER46)}), modules_json=json.dumps(copy.deepcopy(MODULES46)))
    raw = preflight(json.loads(row.business_case_json), json.loads(row.modules_json))
    assert any("pilot gate" in f["issue"] for f in raw)
    bc, mods, reg = preflight_fixture.intended_skeleton(row)
    assert preflight(bc, mods, reg) == [] and reg["errors"] == []
    db.close()
