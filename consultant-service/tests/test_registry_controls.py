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
    from tests._integrity_stub import stamp_clean

    stamp = overrides.pop("integrity_stamp", True)
    row = Request(business_name="iCARRY Lebanon", business_description="delivery platform",
                  email="t@example.com", status="done", is_generating=False)
    for k, v in overrides.items():
        setattr(row, k, v)
    if stamp:
        stamp_clean(row)  # fixture rows never ran the pipeline
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
          # run 52 law: the control is comparable eligible orders randomized 50/50,
          # never orders outside the zone (run 46's shape, kept in GATE46 as the defect)
          "control_method": "Eligible orders are randomized 50/50 between treatment and control",
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
         "The `/predict-delivery-incident` API successfully returns a risk score and predicted reasons for 100% of new e-commerce COD and express on-demand orders within 500ms (proposed — client approval required) for pilot regions.",
         "Operations staff can open any flagged order and see its predicted failure reason in the incident queue."],
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
         "The 'Pre-Dispatch Location Refinement Display' section appears in the driver app for 100% of orders having refined address details from the Pre-Dispatch WhatsApp Engine.",
         "A driver can open the refined address and landmark notes for an assigned order before leaving the hub."],
         "ai_agent": None}},
    {"id": "client-portal-notifier", "name": "Client Portal Notifier", "purpose": "notifies clients",
     "depends_on": [],
     "spec": {"ai": None, "kpis": [
         "The engagement rate with portal notifications (proposed — client approval required) increases by 25% within 3 months of launch.",
         "Notifications achieve a click-through rate of at least 20% (proposed — client approval required) for linked detailed reports.",
         "Finance team time spent on manual COD inquiries reduces by 50%."]},
     "tech": {"done_when": ["A business client receives a portal notification when an order is marked delivered.",
                            "A business client receives a portal notification when a COD settlement statement is issued."],
              "ai_agent": None}},
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
    assert s == ("PG-01: treatment first-attempt delivery success must exceed control by 5 percentage points after six weeks; "
                 "guardrails apply. Proposed — client approval required.")
    full = pg.full_definition(g)
    assert "PG-01 — the pilot decision gate" in full and "divided by" in full and "(your figure)" in full
    assert "Guardrails: the pilot pauses if" in full and "the control group, not this baseline, is the comparison" in full
    # the same object always renders the same sentence
    assert pg.canonical_sentence(pg.normalize_gate(GATE47, claims)) == s


def test_run46_gate_lacks_the_typed_components_and_is_rejected_before_prose():
    from app.pipeline.structural import preflight

    g = pg.normalize_gate(GATE46, [])
    errs = pg.gate_errors(g)
    assert "missing numerator" in errs  # the denominator defaults to the control-group form
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
    assert rg.WEEK_ONE_SENTENCE[:-1] in statements
    # the pilot module's KPI IS the canonical sentence
    pilot = next(m for m in mods if m["pilot"])
    assert pilot["spec"]["kpi_statement"].startswith(reg["pilot_gate_sentence"])
    # every coined candidate is registered as a proposal awaiting approval, not accepted
    props = [c for c in rg.proposals(reg) if c["type"] == "module_kpi"]
    assert len(props) >= 7  # the pilot module's candidates are not registered: its KPI is the gate alone
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
    # the payback note is no longer the model's: it is derived from the Expected
    # scenario's hard dollars on the 30-day month — the latent $1,977 is gone
    assert "$1,977" not in fm["payback_note"] and "$1,925" in fm["payback_note"]
    assert "$23,415/year ÷ 365 × 30" in fm["payback_note"] and "cannot yet be calculated" in fm["payback_note"]
    assert fm["payback_monthly_hard_dollar"] == round(23415 / 365 * 30, 2)


# ── §7 / §8 module names and build order ────────────────────────────────────


def test_pilot_module_is_named_honestly_in_every_structure():
    bc, mods, reg = _skeleton()
    pilot = next(m for m in mods if m["pilot"])
    assert pilot["client_facing_name"] == "Pre-Dispatch WhatsApp Pilot" == pilot["name"]
    assert pilot["original_name"] == "Pre-Dispatch WhatsApp Engine"
    assert pilot["automation_level"] in ("manual", "rules") and pilot["phase"] == "PILOT"
    assert reg["renames"] == [{"id": "pre-dispatch-whatsapp-engine", "from": "Pre-Dispatch WhatsApp Engine",
                               "to": "Pre-Dispatch WhatsApp Pilot", "reason": "pilot_name"}]
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
    # a released record also carries a current, clean integrity report AND a
    # truthful description of what THIS pass corrected: run 53-r22 reported its
    # own corrections as a bare count and filled "current pass" with entries
    # recovered from revision r3.
    applied = [{"where": "technical", "surface": "a", "canonical": "b", "entity": "gate:PG-01",
                "law": "the pilot gate owns the pilot population"}]
    integ = {"status": "current", "blocked": False, "findings": [], "content_hash": "abc",
             "mappings_applied": applied, "mappings_count": 1}
    record = {"status": "final", "reasons": [], "volumes": volumes, "totals": dict(totals), "integrity": integ,
              "revision": "53-r23",
              "corrections_current_pass": {"proven": True, "content_hash": "abc", "count": 1, "applied": applied}}
    assert ra.validate_record(record) == []
    assert any("current integrity report" in e for e in ra.validate_record({**record, "integrity": None}))
    # a count without the corrections themselves is not a description
    silent = copy.deepcopy(record)
    silent.pop("corrections_current_pass")
    assert any("does not describe this pass" in e for e in ra.validate_record(silent))
    # corrections bound to other content than the report describes
    stale = copy.deepcopy(record)
    stale["corrections_current_pass"]["content_hash"] = "other"
    assert any("different content" in e for e in ra.validate_record(stale))
    # a prior revision's work presented as this pass's
    foreign = copy.deepcopy(record)
    foreign["corrections_current_pass"]["applied"] = [
        {"where": "blueprint", "surface": "x", "canonical": "y", "entity": "e", "law": "l",
         "source": "53-r3 rendered text"}]
    assert any("another revision" in e for e in ra.validate_record(foreign))
    # a correction recorded without its authority
    mute = copy.deepcopy(record)
    mute["corrections_current_pass"]["applied"] = [{"surface": "x", "canonical": "y"}]
    assert any("without its location or its authority" in e for e in ra.validate_record(mute))
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
    # a re-audit can clear every finding and still never call DRAFT-stamped pages FINAL
    row.qa_report_json = json.dumps({"checks": [], "findings": []})
    db.commit()
    audit2 = ra.reaudit_revision(rev_dir, row)
    assert audit2["status"] == "draft" and any("DRAFT stamp" in r for r in audit2["reasons"])
    assert audit2["audit_revision"].endswith("-a3")
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


def test_finish_document_renders_registry_statements_and_reports_the_rest():
    """v2 architecture: a finished volume is never repaired by pattern. The
    two registry-owned renderings happen; every other run-46 defect becomes a
    finding for the integrity layer, not a silent rewrite."""
    from app.pipeline import integrity as it
    from app.pipeline.blueprint import finish_document

    bc, mods, reg = _skeleton()
    canon = reg["pilot_gate_sentence"]
    md = ("## The decision\n\n- **Phase 1 — Pilot Delivery Confirmation:** proves the mechanism. [[PILOT_GATE]]\n"
          "- **Phase 2 — Prediction:** built from Phase 1 data.\n\n## How this makes money\n\n" + COST46 + "\n\n"
          "## The product, module by module\n\n### Pre-Dispatch WhatsApp Pilot\n**You'll know it's working when:** "
          + VARIANT_MODULE + "\n\n" + BUILD_FIRST46)
    out, report = finish_document(md, modules=mods, business_case=bc, registry=reg, kind="blueprint")
    # 1. the token became the canonical gate sentence; 2. the KPI line is the registry's
    assert out.count(canon) >= 1 and report["gate"]["token_substitutions"] == 1
    assert VARIANT_MODULE not in out and any(r["statement"] == "module KPI lines" for r in report["rendered"])
    # nothing else was touched: the invented monthly figure and the raw id survive
    assert "$5,913" in out or "/ 12 months" in out or "pre-dispatch-whatsapp-engine" in out
    # and the integrity layer reports what it did not rewrite
    content = {"modules": mods, "business_case": bc, "registry": reg, "blueprint": out, "technical": "",
               "procedures": {"procedures": []}, "checklists": None, "scoreboard": None, "risks": None,
               "journey": None, "org": None, "playbook": None, "ops_numbers": OPS, "free_texts": [],
               "concept_name": "iCARRY Lebanon", "business_name": "iCARRY Lebanon"}
    findings, _ = it.verify(content)
    assert findings and all(f.severity == "high" for f in findings)


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


# ── run 47's classes ────────────────────────────────────────────────────────

GATE47_RAW = {
    "duration": "6 weeks (proposed — client approval required)", "population": "All cash-on-delivery orders",
    "geography": "Beirut",
    "control_method": "Random assignment of 50% of eligible orders to pilot group, 50% to control group.",
    "primary_metric": "First-attempt delivery success rate",
    "numerator": "Deliveries successfully completed on the first attempt within the pilot group",
    "denominator": "All delivery attempts within the pilot group",
    "baseline": "12% of deliveries fail first attempt, meaning 88% first-attempt success rate (by your own figures)",
    "target": "A 5 percentage-point rise in first-attempt delivery success rate (proposed — client approval required)",
    "target_value": 0.93, "change_kind": "percentage_point",
    "guardrails": ["Increase in average delivery time by more than 10% for pilot orders"],
    "approvals_required": ["Pilot duration"],
}


def test_gate_text_governs_a_contradicting_numeric_field_and_strings_are_clean():
    """Run 47: the model's target_value (0.93, the resulting rate) contradicted
    its own labeled text ('5 percentage-point rise'); the text governs and the
    conflict is a preflight error. Strings lose trailing periods and the
    model's own attribution parentheticals."""
    claims = rg.client_fact_claims(json.loads(OPS), [])
    g = pg.normalize_gate(GATE47_RAW, claims)
    assert g["target_value"] == 5 and g["target_value_conflict"] is True
    assert any("target_value (0.93) contradicts the target text" in e and "write target_value exactly" in e
               for e in pg.gate_errors(g))
    assert not g["control_method_stated"].endswith(".") and "by your own figures" not in g["baseline"]
    s = pg.canonical_sentence(g)
    full = pg.full_definition(g)
    assert "must exceed control by 5 percentage points" in s and "0.93" not in s and "0.93" not in full
    assert "group., " not in full and "(by your own figures) (your figure)" not in full
    assert "(your figure)" in full
    clean = {**GATE47_RAW, "target_value": 5}
    assert pg.gate_errors(pg.normalize_gate(clean, claims)) == []


def test_money_line_without_a_dollar_sign_still_anchors_monthly_restatements():
    """Run 47: annual '70,956' (no $) — every monthly restatement lost its
    anchor, '$4,730 per month' stayed 'unverifiable' and the blueprint
    borrowed the Upside scenario's $2,333 for 'what staying manual costs'."""
    from app.pipeline.blueprint import _align_cost_line, _monthly_identity_note
    from app.pipeline.decompose import _sanitize_financial_model

    bc = {"cost_of_inaction": "Continuing with 12% failed first attempts costs approximately $4,730 per month in re-attempt costs alone.",
          "financial_model": {"lines": [{"item": "Annual re-attempt costs from failed first deliveries",
                                         "arithmetic": "900 deliveries/day * 365 days/year * 12% failed first attempts * $1.80 re-attempt cost",
                                         "annual": "70,956"}],
                              "scenarios": [{"name": "Upside", "assumption": "prevents 40% of failed attempts",
                                             "impact": "$28,382/year saved in re-attempt costs"}]}}
    _sanitize_financial_model(bc)
    assert "$5,832 per month" in bc["cost_of_inaction"] and "$4,730" not in bc["cost_of_inaction"]
    note = _monthly_identity_note(bc)
    assert note.index("$70,956/year = $5,832") < note.index("$28,382")
    reg = rg.build_registry(OPS, bc, [])
    assert any(c["id"] == "TB-01-month" and c["value"] == 5832.0 for c in reg["claims"])
    md = "## How this makes money\n\n**What staying manual costs:** Continuing with 12% failed first attempts costs approximately $2,333 per month in re-attempt costs alone.\n"
    out = _align_cost_line(md, bc)
    assert "$5,832 per month" in out and "$2,333" not in out


def test_operations_layers_are_corrected_in_place_for_run47_shapes():
    from app.pipeline.extras import canonicalize_layers
    from app.pipeline.phases import phase_findings

    bc, mods, reg = _skeleton()
    procedures = [
        {"name": "Managing Pre-Dispatch Customer Confirmation", "phase": "pilot", "module": "Pre-Dispatch WhatsApp Pilot",
         "trigger": "order created", "steps": [{"actor": "ai", "step": "Delivery Incident Predictor scores the order."}]},
        {"name": "Assisting the driver", "phase": "future", "module": "Driver Clarification Assistant", "trigger": "dispatch",
         "steps": [{"actor": "driver-clarification-assistant", "step": "Displays confirmed location details."},
                   {"actor": "support agent", "step": "Escalate immediately to the dispatcher if the driver is lost."}]},
    ]
    by_name = {"organization": {"roles": [{"role": "COD Settlement Inquiry Bot", "type": "ai", "responsibilities": ["answers"],
                                           "decides_alone": "Null", "hands_off": "When a dispute is raised."}]}}
    canonicalize_layers(procedures, by_name, mods, reg, reg["pilot_gate"])
    # run 52 law: a pilot procedure stays in the pilot — its AI actor becomes the
    # human operator and the AI module it named becomes the pilot tooling
    assert procedures[0]["phase"] == "pilot" and procedures[0]["steps"][0]["actor"] == pg.PILOT_OPERATOR
    assert "Delivery Incident Predictor" not in procedures[0]["steps"][0]["step"]
    assert procedures[1]["steps"][0]["actor"] == "Driver Clarification Assistant"
    assert by_name["organization"]["roles"][0]["decides_alone"].startswith("Does not decide autonomously")
    # an adverb inside a step is not present-execution language; the phase model agrees
    assert not [f for f in phase_findings(procedures, mods) if "execute it now" in f["issue"]]
    from app.pipeline import export_pdf as ep

    assert ep.release_status(_seed_row(by_name, procedures, bc, mods, reg))["reasons"] == []


def _seed_row(by_name, procedures, bc, mods, reg):
    db = SessionLocal()
    row = _seed(db, mvp_blueprint="## The decision\nfine\n", technical_plan="## How your system works\nfine\n",
                org_json=json.dumps(by_name["organization"]), procedures_json=json.dumps({"procedures": procedures}),
                business_case_json=json.dumps(bc), modules_json=json.dumps(mods), registry_json=json.dumps(reg),
                journey_json=json.dumps({"stages": [{"stage": "Order", "backstage_modules": ["delivery-incident-predictor"]}]}),
                qa_report_json=json.dumps({"checks": [], "findings": []}))
    db.close()
    return row


def test_invented_settlement_policy_is_a_structural_finding():
    claims = rg.client_fact_claims(json.loads(OPS), [])
    texts = {"technical": "This AI understands that COD collections are settled with clients within 5 business days of month-end. "
                          "Settlement statements follow your 10 days after month-end cycle."}
    found = rg.policy_findings(texts, claims)
    assert len(found) == 1 and "5 business days" in found[0]["issue"] and "10 days" in found[0]["issue"]
    assert rg.policy_findings({"t": "Settlements are remitted weekly to every client."}, claims)
    assert rg.policy_findings({"t": "Settlement happens 10 days after month-end, on monthly cycles."}, claims) == []
    assert rg.policy_findings({"t": "a settlement reminder is sent within 48 hours (proposed — client approval required)"}, claims) == []


def test_bullets_are_their_own_sentences_for_paraphrase_detection():
    bc, mods, reg = _skeleton()
    g = reg["pilot_gate"]
    text = ("- **Pricing levers:**\n- Reduced failed delivery costs leading to higher profitability per delivery at existing rates\n"
            "- Enhanced first-attempt delivery success supports premium same-day pricing for 350 daily inquiries\n")
    assert pg.restatement_findings(text, g) == []
    assert len(pg.restatement_findings("- " + VARIANT_MODULE + "\n- another bullet\n", g)) == 1


def test_r13_qualitative_trigger_and_r8_verbatim_presence(client):
    from app.pipeline.adjudicate import adjudicate

    bc, mods, reg = _skeleton()
    canon = reg["pilot_gate_sentence"]
    db = SessionLocal()
    row = _seed(db, business_case_json=json.dumps(bc), modules_json=json.dumps(mods), registry_json=json.dumps(reg),
                qa_report_json=json.dumps({"checks": [], "findings": [
                    _finding("THE BLUEPRINT DOCUMENT: 'Where it stops and hands to you'",
                             "This threshold or trigger ('fraud or major service problems') is newly introduced, qualitative, and lacks the required '(proposed — client approval required)' attribution."),
                    _finding("The decision",
                             "The 'Pre-Dispatch Customer Confirmation Workflow' description within 'The decision' section includes a pilot decision gate that does not precisely match the canonical gate sentence.",
                             source="qa_completeness"),
                ]}))
    result = adjudicate(row, {"blueprint": "The decision gate: " + canon + " It hands off on fraud or major service problems."})
    kinds = [e["classification"] for e in result["ledger"]]
    assert kinds[0] == "semantic false positive resolved by structured threshold typing" and "R13" in result["ledger"][0]["evidence"]
    assert kinds[1] == "machine-proven false positive" and "verbatim" in result["ledger"][1]["evidence"]
    db.close()


def test_abbreviated_module_names_resolve_to_one_name():
    mods = [{"id": "location-verification-availability-assistant-ai",
             "name": "Location Verification & Availability Assistant (LVA)", "purpose": "p", "depends_on": [],
             "spec": {"ai": {"role": "x"}, "kpis": []}, "tech": {"done_when": ["LVA confirms the pin for all orders."]}},
            {"id": "cod-settlement-inquiry-bot", "name": "COD Settlement Inquiry Bot (CSI Bot)", "purpose": "p",
             "depends_on": [], "spec": {"ai": None, "kpis": []}, "tech": {}}]
    bc = {"build_order": [m["id"] for m in mods], "revenue_streams": [{"description": "handled by the LVA and the CSI Bot"}]}
    reg = rg.build_registry(OPS, bc, mods)
    names = [m["client_facing_name"] for m in reg["modules"]]
    assert names == ["Location Verification & Availability Assistant", "COD Settlement Inquiry Bot"]
    assert [m["alias"] for m in reg["modules"]] == ["LVA", "CSI Bot"]
    prose = "The LVA hands off to the COD Settlement Inquiry Bot (CSI Bot); non-LVA orders skip it. LVA-processed orders."
    out = rg.resolve_module_ids(prose, mods)
    assert "LVA" not in out.replace("Location Verification & Availability Assistant", "") and "(CSI Bot)" not in out
    assert out.count("Location Verification & Availability Assistant") == 3
    assert rg.identifier_artifacts("all internal APIs use service-to-service mTLS and an end-to-end check", []) == []
    assert rg.identifier_artifacts("For your build team: order-intake-service, pin-capture-handler", []) == []
    assert rg.identifier_artifacts("wire the pin-capture-handler to the queue", []) == ["pin-capture-handler"]


def test_gate_renderings_and_counts_are_not_paraphrases_but_stale_specs_are():
    bc, mods, reg = _skeleton()
    g = reg["pilot_gate"]
    table = ("Parameter Value Duration 6 weeks (proposed — client approval required) Population all new customer orders "
             "Geography Beirut Central District Baseline 12% failed first attempts (88% success rate) Target rise by 5 "
             "percentage points (proposed — client approval required) Approval status consultant_proposed — client approval required")
    assert pg.restatement_findings(table, g) == []
    board = ("Metric Baseline Target Owner Review First-attempt delivery success rate 12% " + reg["pilot_gate_sentence"] +
             " you weekly Daily inquiries 350 a day (your figure) Down, by 30% within 3 months ops weekly How each is measured: x")
    assert pg.restatement_findings(board, g) == []
    assert pg.restatement_findings("Your support team manually handles 350 first-attempt delivery success inquiries daily.", g) == []
    stale = "Target: more than 0.93 first-attempt delivery success rate for AI-processed orders after 2 weeks (proposed — client approval required)."
    assert len(pg.restatement_findings(stale, g)) == 1
    mods2 = copy.deepcopy(mods)
    mods2[1]["tech"]["ai_agent"]["evaluation"].append(stale)
    assert rg.enforce_gate_in_specs(mods2, g) == 1
    assert mods2[1]["tech"]["ai_agent"]["evaluation"][-1] == reg["pilot_gate_sentence"]


def test_policy_periods_must_be_about_settling_and_are_corrected_in_specs():
    claims = rg.client_fact_claims(json.loads(OPS), [])
    assert rg.policy_findings({"o": "COD Settlement Inquiry Review Checklist (Weekly) When: Every Monday morning"}, claims) == []
    assert rg.policy_findings({"b": "Monitor COD inquiry resolution weekly — track COD settlement inquiries automatically resolved"}, claims) == []
    assert rg.policy_findings({"b": "Head of Operations Weekly Daily inquiries 350 a day Down, by 30% COD settlement"}, claims) == []
    found = rg.policy_findings({"t": "What it knows: iCARRY's 2-day remittance policy for individual COD order deliveries."}, claims)
    assert len(found) == 1 and "'2-day'" in found[0]["issue"]
    fixed, notes = rg.policy_pass("iCARRY's 2-day remittance policy for individual COD order deliveries.", claims)
    assert "10-day (your stated cycle) remittance policy" in fixed and notes
    assert rg.policy_findings({"t": fixed}, claims) == []


def test_scoreboard_targets_obey_the_kpi_law():
    from app.pipeline.extras import canonicalize_layers

    bc, mods, reg = _skeleton()
    by_name = {"governance": {"scoreboard": [
        {"metric": "Daily 'where is my order' inquiries", "baseline": "350 a day (your figure)",
         "target": "Down, by 35% reduction in inquiries within 3 months", "owner": "you", "review": "weekly"},
        {"metric": "Failed first attempts prevented", "baseline": "measure in week 1",
         "target": "Up to 20% (scenario assumption — requires your approval)", "owner": "ops", "review": "weekly"}]}}
    canonicalize_layers([], by_name, mods, reg, reg["pilot_gate"])
    rows = by_name["governance"]["scoreboard"]
    assert rows[0]["target"] == "Down — target to be established during week-one measurement"
    assert "35%" in rows[0]["target_note"] and "3 months" in rows[0]["target_note"]
    # a scenario assumption's fraction is a registered claim and may stand
    assert rows[1]["target"].startswith("Up to 20%")


def test_page_chrome_is_stripped_from_rendered_text():
    from app.pipeline.export_pdf import strip_page_chrome

    bc, mods, reg = _skeleton()
    canon = reg["pilot_gate_sentence"]
    cut = canon.index("must exceed")
    page_text = (canon[:cut] + "THE TECHNICAL PLAN DRAFT — REQUIRES VALIDATION iCARRY Lebanon\r\n" + canon[cut:]
                 + "\r\nBuild My Version · buildmyversion.com · consulting@buildmyversion.com\r\nPage 7\r\n")
    clean = " ".join(strip_page_chrome(page_text, "iCARRY Lebanon").split())
    assert canon in clean and "Page 7" not in clean
    assert pg.restatement_findings(strip_page_chrome(page_text, "iCARRY Lebanon"), reg["pilot_gate"]) == []


def test_kpi_renderings_state_baselines_labels_and_never_claim_ids():
    mods = [{"id": "pilot-wf", "name": "Pre-Dispatch Confirmation Pilot", "purpose": "confirms pins", "depends_on": [],
             "pilot": True, "spec": {"ai": None, "kpis": []}, "tech": {}},
            {"id": "cod-handler", "name": "COD Settlement Inquiry Handler", "purpose": "p", "depends_on": [],
             "spec": {"ai": {"role": "x"}, "kpis": [
                 {"metric": "Manual support staff interventions for COD settlement inquiries", "basis": "client_fact",
                  "value": 300, "unit": "count", "horizon": None},
                 {"metric": "Reduction in manual COD settlement inquiry handling", "basis": "scenario_assumption",
                  "value": 30, "unit": "%", "horizon": "within 3 months of launch"},
                 {"metric": "Manual dispatcher interventions per day", "basis": "pilot_gate", "value": 5, "unit": "count", "horizon": None}]},
             "tech": {}}]
    bc = {"financial_model": copy.deepcopy(FM46), "pilot_gate": copy.deepcopy(GATE47),
          "build_order": ["pilot-wf", "cod-handler"]}
    from app.pipeline.decompose import _sanitize_financial_model

    _sanitize_financial_model(bc)
    reg = rg.build_registry(OPS, bc, mods)
    stmt = mods[1]["spec"]["kpi_statement"]
    assert "(your related figure: COD settlement inquiries per month: Around 300 inquiries)" in stmt and "300 count" not in stmt
    assert "30% (proposed — client approval required; our scenario assumption)" in stmt
    assert "claim " not in stmt and "count (" not in stmt
    assert rg.kpi_number_findings("**You'll know it's working when:** " + stmt, reg, strict_kpi=True) == []


def test_pilot_module_is_ai_free_by_construction_and_policy_pass_reaches_every_spec_string():
    bc, mods, reg = _skeleton()
    mods2 = copy.deepcopy(MODULES46)
    mods2[0]["spec"]["ai"] = {"role": "parses replies"}
    mods2[0]["tech"]["ai_agent"] = {"purpose": "parse", "tools": [{"name": "t", "does": "shows the expected remittance date under the 2-day remittance policy"}]}
    bc2 = {"financial_model": copy.deepcopy(FM46), "pilot_gate": copy.deepcopy(GATE47), "build_order": list(BUILD_ORDER46)}
    reg2 = rg.build_registry(OPS, bc2, mods2)
    pilot = next(m for m in mods2 if m["pilot"])
    assert pilot["spec"]["ai"] is None and pilot["tech"]["ai_agent"] is None and pilot["ai_involvement"] is False
    assert reg2["pilot_ai_removed"] and {r["module"] for r in reg2["pilot_ai_removed"]} == {pilot["id"]} and reg2["errors"] == []
    other = copy.deepcopy(MODULES46)
    other[1]["tech"]["ai_agent"]["tools"] = [{"name": "t", "does": "shows the expected remittance date under the 2-day remittance policy"}]
    reg3 = rg.build_registry(OPS, {"financial_model": copy.deepcopy(FM46), "pilot_gate": copy.deepcopy(GATE47),
                                   "build_order": list(BUILD_ORDER46)}, other)
    assert "10-day (your stated cycle)" in other[1]["tech"]["ai_agent"]["tools"][0]["does"]
    assert reg3["policy_corrections"]


def test_register_carries_the_clients_briefing_corrections():
    from app.pipeline._shared import briefing_corrections, build_engagement_register

    desc = ("Delivery platform.\n\nCorrections and additions from the briefing chat:\n"
            "- The capability must also handle COD settlement inquiries from business clients (around 300 a month). Cover both.")
    assert briefing_corrections(desc).startswith("The capability must also handle COD settlement inquiries")
    reg = build_engagement_register("capability", "yes", "Failed first-attempt deliveries", "fewer failures", desc)
    assert "EXTENDED the capability" in reg and "COD settlement inquiries" in reg
    assert "EXTENDED" not in build_engagement_register("capability", "yes", "x", "y", "no corrections here")


def test_r14_r15_r16_and_ai_consistency(client):
    from app.pipeline.adjudicate import adjudicate

    bc, mods, reg = _skeleton()
    desc = ("Delivery platform.\n\nCorrections and additions from the briefing chat:\n"
            "- The capability must also handle COD settlement inquiries from business clients (around 300 a month). Cover both.")
    db = SessionLocal()
    row = _seed(db, business_description=desc, business_case_json=json.dumps(bc), modules_json=json.dumps(mods),
                registry_json=json.dumps(reg), qa_report_json=json.dumps({"checks": [], "findings": [
                    _finding("The decision, Executive summary",
                             "The engagement blueprint claims to address TWO capabilities ('enhancing first-attempt delivery success and automating COD settlement inquiries') despite the engagement register specifying ONE CAPABILITY.",
                             source="qa_completeness"),
                    _finding("The decision",
                             "The description of Phase 1 refers to the pilot as 'Pre-Dispatch WhatsApp Pilot', which is a module name, instead of describing it as a rules-based process without using a module name.",
                             source="qa_completeness"),
                    _finding("THE BUSINESS CASE.financial_model.scenarios.Conservative",
                             "The discrepancy is just a missing comma in the arithmetic field but correct in the impact string. This is a minor formatting issue.",
                             fix="No fix needed for the figure, only for the arithmetic formatting to add a comma if desired."),
                ]}))
    result = adjudicate(row, {"blueprint": "fine"})
    kinds = [e["classification"] for e in result["ledger"]]
    assert kinds == ["semantic false positive resolved by structured phase data",
                     "semantic false positive resolved by structured phase data",
                     "machine-proven false positive"]
    assert "R14" in result["ledger"][0]["evidence"] and "R15" in result["ledger"][1]["evidence"] and "R16" in result["ledger"][2]["evidence"]
    md = "### Delivery Incident Predictor\n**What the AI does on its own:** No AI in this part — deliberately.\n"
    found = rg.ai_consistency_findings(md, mods)
    assert len(found) == 1 and "specified with an AI component" in found[0]["issue"]
    db.close()


def test_r17_complement_r18_labeled_typed_thresholds_and_convention_line(client):
    from app.pipeline.adjudicate import adjudicate
    from app.pipeline import timebasis as tb

    bc, mods, reg = _skeleton()
    db = SessionLocal()
    row = _seed(db, business_case_json=json.dumps(bc), modules_json=json.dumps(mods), registry_json=json.dumps(reg),
                qa_report_json=json.dumps({"checks": [], "findings": [
                    _finding("Pilot decision gate",
                             "The baseline is stated as '88%' when the client input implies 12% failed, so 100-12=88% success rate; the derived figure is not a client input."),
                    _finding("TECHNICAL PLAN DOCUMENT: Delivery Incident Predictor",
                             "The '90%' accuracy and '100,000' historical orders are arbitrary figures lacking any client input or proposed assumption, even with the approval tag."),
                    _finding("The decision",
                             "The pilot decision gate is stated multiple times and while mostly consistent there are minor discrepancies and formatting differences compared to the canonical gate sentence.",
                             source="qa_completeness"),
                ]}))
    rendered = {"technical": "aiming for over 90% accuracy (proposed — client approval required) on 100,000 historical orders (proposed — client approval required). " + reg["pilot_gate_sentence"]}
    result = adjudicate(row, rendered)
    kinds = [e["classification"] for e in result["ledger"]]
    assert kinds[0] == "machine-proven false positive" and "R17" in result["ledger"][0]["evidence"]
    assert kinds[1] == "semantic false positive resolved by structured threshold typing" and "R18" in result["ledger"][1]["evidence"]
    assert kinds[2] == "machine-proven false positive" and "verbatim" in result["ledger"][2]["evidence"]
    # the convention sentence the financial case prints is not a mixed-identity sentence
    line = ("Convention: a 365-day year; every monthly figure in this engagement is a 30-day operating month "
            "(the annual figure ÷ 365 × 30), never one twelfth of the year.")
    assert tb.identity_findings({"b": line}, [70956.0]) == []
    # run 52 law: the client's number AND the client's event origin ("after month-end")
    fixed, _ = rg.policy_pass("settled within 2 days of collection", rg.client_fact_claims(json.loads(OPS), []))
    assert "within 10 days after month-end (your stated cycle)" in fixed and "collection" not in fixed
    fixed2, _ = rg.policy_pass("Get your remittance within 10-day (your stated cycle) (proposed — client approval required) of collection",
                               rg.client_fact_claims(json.loads(OPS), []))
    assert "within 10 days after month-end (your stated cycle)" in fixed2 and "(proposed" not in fixed2 and "collection" not in fixed2
    g = pg.normalize_gate(GATE47_RAW, rg.client_fact_claims(json.loads(OPS), []))
    assert g["control"] == g["control_method"] and g["guardrail"]
    db.close()


def test_volume_i_kpi_lines_are_pinned_and_null_lines_rewritten():
    from app.pipeline.blueprint import _no_null_lines, _pin_kpi_lines, finish_document

    bc, mods, reg = _skeleton()
    canon = reg["pilot_gate_sentence"]
    dip = next(m for m in mods if m["id"] == "delivery-incident-predictor")
    md = ("## The product, module by module\n\n### Pre-Dispatch WhatsApp Pilot\nIntro.\n"
          "- **You'll know it's working when:** " + canon.replace("12% of deliveries fail first attempt, meaning 88% first-attempt success rate (your figure)",
                                                                    "88% first-attempt success rate (derived from your figure of 12% failed)") + "\n"
          "### Delivery Incident Predictor\nIntro.\n- **What it does:** scores risk\n"
          "- **You'll know it's working when:** A 15% reduction in failures (proposed — client approval required).\n"
          "  • Offline: A human expert will review 500 (proposed — client approval required) random entries, aiming for 90% accuracy.\n\n"
          "### Client Portal Notifier\nIntro only.\n\n## What we'd build first\n1. x\n")
    out, _ = finish_document(md, modules=mods, business_case=bc, registry=reg, kind="blueprint")
    assert out.count(canon) >= 1 and "derived from your figure" not in out
    assert "15% reduction" not in out and "500 (proposed" not in out
    assert dip["spec"]["kpi_statement"] in out
    assert "**You'll know it's working when:** " in out.split("### Client Portal Notifier")[1]
    assert pg.restatement_findings(out, reg["pilot_gate"]) == [] and rg.kpi_number_findings(out, reg, strict_kpi=True) == []
    tech = "- **What the AI does on its own:** Null\n- **Memory:** Null\n"
    fixed = _no_null_lines(tech)
    assert "No AI in this part — deliberately." in fixed and "Null" not in fixed


def test_polish_rewrite_goes_through_the_deterministic_passes(client, monkeypatch):
    from app.pipeline import qa_experts

    bc, mods, reg = _skeleton()
    canon = reg["pilot_gate_sentence"]
    md = ("## The decision\n- **Phase 1 — Pre-Dispatch WhatsApp Pilot:** proves it. The decision gate: " + canon + "\n\n"
          "## Executive summary\nfine\n\n## How this makes money\nfine\n\n## The product, module by module\n"
          "### Pre-Dispatch WhatsApp Pilot\n- **You'll know it's working when:** " + canon + "\n")
    db = SessionLocal()
    row = _seed(db, mvp_blueprint=md, technical_plan="## How your system works\nfine\n", modules_json=json.dumps(mods),
                business_case_json=json.dumps(bc), registry_json=json.dumps(reg), ops_numbers_json=OPS)
    edited = md.replace("12% of deliveries fail first attempt, meaning 88% first-attempt success rate (your figure)",
                        "88% success (derived from your 12% failed figure)")

    def chat(model, messages, **kwargs):
        prompt = messages[0]["content"]
        if "NUMBERS AUDITOR" in prompt:
            payload = {"checks": [], "findings": [{"severity": "high", "where": "x", "issue": "attribution missing on $70,956", "fix": "add it"}]}
            return {"choices": [{"message": {"content": json.dumps(payload)}}], "usage": {}}
        if "STRUCTURE AUDITOR" in prompt:
            return {"choices": [{"message": {"content": json.dumps({"checks": [], "findings": []})}}], "usage": {}}
        return {"choices": [{"message": {"content": edited}}], "usage": {}}  # the polish "tidies" the gate

    monkeypatch.setattr(qa_experts.provider, "chat", chat)
    qa_experts.review_quality(db, row.id)
    db.refresh(row)
    assert row.mvp_blueprint.count(canon) == 2 and "derived from your 12%" not in row.mvp_blueprint
    db.close()


def test_pass5_classes_merged_sentences_future_week_one_no_ai_repair_and_quote_only_findings(client):
    from app.pipeline.adjudicate import adjudicate
    from app.pipeline.blueprint import _repair_no_ai_lines

    bc, mods, reg = _skeleton()
    g = reg["pilot_gate"]
    merged = ("- Enhanced client satisfaction due to improved reliability and faster COD settlements **What staying manual "
              "costs:** Continuing with 12% failed first attempts costs approximately $5,832 per month in re-attempt costs alone.")
    assert pg.restatement_findings(merged, g) == []
    out, rep = pg.enforce(merged, g)
    assert out == merged and rep["paraphrases_replaced"] == 0
    # the FUTURE module's week-one statement names its own launch
    dip = next(m for m in mods if m["id"] == "delivery-incident-predictor")
    assert "once this module is live" in dip["spec"]["kpi_statement"]
    pilot = next(m for m in mods if m["pilot"])
    assert "once this module is live" not in pilot["spec"]["kpi_statement"]
    # the "No AI" line of an AI-specced module is rebuilt from its spec
    dip["spec"]["ai"] = {"role": "scores each order's failure risk", "decides_alone": "which orders to flag",
                         "hands_off": "to operations when a flagged order needs a call"}
    md = "### Delivery Incident Predictor\n- **What the AI does on its own:** No AI in this part — deliberately.\n"
    fixed = _repair_no_ai_lines(md, mods)
    assert "No AI in this part" not in fixed and "Scores each order's failure risk. On its own it which orders to flag" in fixed
    # quote-only findings: labeled everywhere => proposal; a bare one => defect with evidence
    db = SessionLocal()
    row = _seed(db, registry_json=json.dumps(reg), modules_json=json.dumps(mods), business_case_json=json.dumps(bc),
                qa_report_json=json.dumps({"checks": [], "findings": [
                    _finding("THE TECHNICAL PLAN DOCUMENT: X", "'within 5 minutes', '>90%'"),
                    _finding("THE TECHNICAL PLAN DOCUMENT: Y", "'3 re-prompts'"),
                    _finding("The product, module by module",
                             "The module 'Automated COD Settlement Inquiry Handler' is listed as 'Automated COD Settlement Inquiry Handler' in the document but is listed as 'Automated COD Settlement Inquiry Handler' in the structured layers, an inconsistency.",
                             source="qa_completeness"),
                ]}))
    rendered = {"technical": "sent within 5 minutes (proposed — client approval required); accuracy >90% (proposed — client approval required). "
                             "escalates after 3 re-prompts with no label here."}
    result = adjudicate(row, rendered)
    kinds = [e["classification"] for e in result["ledger"]]
    assert kinds[0] == "semantic false positive resolved by structured threshold typing" and "R23" in result["ledger"][0]["evidence"]
    assert kinds[1] == "real defect" and "carry no approval label" in result["ledger"][1]["evidence"]
    assert kinds[2] == "machine-proven false positive" and "R22" in result["ledger"][2]["evidence"]
    db.close()


def test_pass6_classes_unpromised_components_auditor_arithmetic_and_current_state_sentences(client):
    from app.pipeline.adjudicate import adjudicate
    from app.pipeline.decompose import _sanitize_financial_model
    from app.pipeline.structural import scenario_component_map, unpromised_components

    lines = [{"item": "Annual re-attempt costs from failed first deliveries",
              "arithmetic": "900 deliveries/day * 365 days/year * 12% failed first attempts * $1.80 re-attempt cost", "annual": "$70,956/year"},
             {"item": "Annual support inquiries for 'where is my order'", "arithmetic": "350 inquiries/day * 365 days/year", "annual": "127,750 inquiries/year"},
             {"item": "Annual COD settlement inquiries", "arithmetic": "300 inquiries/month * 12 months/year", "annual": "3,600 inquiries/year"}]
    sc = {"name": "Conservative",
          "assumption": "The LVA AI prevents 20% of current failed first attempts and CSI Bot resolves 40% of COD inquiries.",
          "impact": "$14,191/year saved in re-attempt costs + 51,100 fewer 'where is my order' inquiries/year + 1,440 fewer COD inquiries/year"}
    un = unpromised_components(sc, lines)
    assert len(un) == 1 and un[0]["subject"] == "where is my order" and abs(un[0]["fraction"] - 0.4) < 1e-9
    assert scenario_component_map(sc, lines)["complete"] is False
    bc = {"financial_model": {"lines": copy.deepcopy(lines), "scenarios": [copy.deepcopy(sc)]}}
    _sanitize_financial_model(bc)
    fixed = bc["financial_model"]["scenarios"][0]
    assert "resolves 40% of 'where is my order' inquiries" in fixed["assumption"]
    assert bc["financial_model"]["assumption_repairs"][0]["for"] == "51,100"
    assert scenario_component_map(fixed, bc["financial_model"]["lines"])["complete"] is True
    # the current-state sentence quoting the client's own figures is not a gate paraphrase
    bc2, mods, reg = _skeleton()
    g = reg["pilot_gate"]
    current = ("You report 12% of your deliveries fail on the first attempt, costing you $5,832 per 30-day operating month "
               "in re-attempt costs alone, alongside 350 'where is my order' messages a day your support staff answer by hand.")
    assert not pg.is_paraphrase(current, g)
    for variant in (VARIANT_DECISION, VARIANT_KPI, VARIANT_MODULE):
        assert pg.is_paraphrase(variant, g)
    # the auditor's own arithmetic drift, and arithmetic it invented
    db = SessionLocal()
    row = _seed(db, business_case_json=json.dumps(bc2), modules_json=json.dumps(mods), registry_json=json.dumps(reg),
                qa_report_json=json.dumps({"checks": [], "findings": [
                    _finding("restatements", "The formula '70,956/year / 365 x 30 = 5,832.00' contains a numerical error. 70,956 / 365 * 30 = 5828.60, not 5832.00.",
                             fix="70,956/year / 365 x 30 = 5,828.60"),
                    _finding("scenarios -> impact", "The Conservative impact arithmetic for 'where is my order' inquiries is given as '(127750 * 0.20)', leading to 25,550 fewer inquiries. However, the machine-verified claim states '51,100 fewer inquiries/year'.",
                             fix="The arithmetic should be '(127750 * X)' where X is 0.40"),
                ]}))
    result = adjudicate(row, {"blueprint": "51,100 fewer 'where is my order' inquiries a year, by your own figures."})
    kinds = [e["classification"] for e in result["ledger"]]
    assert kinds[0] == "machine-proven false positive" and "R24" in result["ledger"][0]["evidence"]
    assert kinds[1] == "machine-proven false positive" and "R25" in result["ledger"][1]["evidence"]
    db.close()


def test_failed_regeneration_never_erases_an_existing_volume(client, monkeypatch):
    from app.pipeline import blueprint as bp

    bc, mods, reg = _skeleton()
    db = SessionLocal()
    row = _seed(db, mvp_blueprint="## The decision\nkept\n", technical_plan="## How your system works\nkept\n",
                modules_json=json.dumps(mods), business_case_json=json.dumps(bc), registry_json=json.dumps(reg))

    def chat(model, messages, **kwargs):
        raise RuntimeError("OpenRouter 402: Insufficient credits")

    monkeypatch.setattr(bp.provider, "chat", chat)
    out = bp.write_blueprint(db, row.id, {}, {}, {"concept_name": "C", "roles": []},
                             {"modules": mods, "business_case": bc, "registry": reg})
    out2 = bp.write_technical_plan(db, row.id, {}, {"concept_name": "C", "roles": []},
                                   {"modules": mods, "business_case": bc, "registry": reg})
    db.refresh(row)
    assert row.mvp_blueprint == "## The decision\nkept\n" == out
    assert row.technical_plan == "## How your system works\nkept\n" == out2
    db.close()


def test_inline_arithmetic_in_business_case_prose_must_compute_on_scenario_fractions():
    from app.pipeline.structural import inline_product_findings, preflight

    bc = {"financial_model": {"lines": [{"item": "Annual support inquiries for 'where is my order'",
                                         "arithmetic": "350 * 365", "annual": "127,750 inquiries/year"}],
                              "scenarios": [{"name": "Conservative", "assumption": "resolves 40% of 'where is my order' inquiries",
                                             "impact": "51,100 fewer 'where is my order' inquiries/year"}]},
          "payback_logic": "Automating 'where is my order' inquiries (127750 * 0.20) = 25,550 fewer inquiries a year frees support capacity."}
    found = inline_product_findings(bc)
    assert len(found) == 1 and "scenarios assume 40%" in found[0]["issue"]
    bc["payback_logic"] = "Automating 'where is my order' inquiries (127,750 x 40%) = 51,100 fewer inquiries a year."
    assert inline_product_findings(bc) == []
    bc["payback_logic"] = "Automating inquiries (127,750 x 40% = 61,100) frees capacity."
    assert "does not compute" in inline_product_findings(bc)[0]["issue"]
    assert any("does not compute" in f["issue"] for f in preflight(bc, []))
    # run 47: the scenario's own arithmetic field contradicted its impact
    bc["payback_logic"] = "fine"
    bc["financial_model"]["scenarios"][0]["arithmetic"] = "(300 * 12 * 0.40) annually for COD inquiries. (127750 * 0.20) for 'where is my order' inquiries."
    bc["financial_model"]["scenarios"][0]["impact"] = "51,100 fewer 'where is my order' inquiries/year + 1,440 fewer COD inquiries/year"
    found = inline_product_findings(bc)
    assert len(found) == 1 and "(127750 * 0.20)' = 25,550 matches no figure" in found[0]["issue"]
    bc["financial_model"]["scenarios"][0]["arithmetic"] = "(300 * 12 * 0.40) for COD inquiries. (127750 * 0.40) for 'where is my order' inquiries."
    assert inline_product_findings(bc) == []


def test_scenario_arithmetic_is_derived_from_verified_components_never_the_models():
    from app.pipeline.decompose import _sanitize_financial_model
    from app.pipeline.structural import inline_product_findings

    bc = {"financial_model": {
        "lines": [{"item": "re-attempt costs", "arithmetic": "900 * 365 * 0.12 * $1.80", "annual": "$70,956/year"},
                  {"item": "'where is my order' inquiries", "arithmetic": "350 * 365", "annual": "127,750 inquiries/year"}],
        "scenarios": [{"name": "Conservative",
                       "assumption": "prevents 20% of failed first attempts and resolves 40% of 'where is my order' inquiries",
                       "arithmetic": "(127750 * 0.20) for 'where is my order' inquiries.",
                       "impact": "$14,191/year saved + 51,100 fewer 'where is my order' inquiries/year"}]}}
    _sanitize_financial_model(bc)
    sc = bc["financial_model"]["scenarios"][0]
    assert sc["impact_verified"] and "0.20" not in sc["arithmetic"]
    assert "70,956 x 20% = 14,191" in sc["arithmetic"] and "127,750 x 40% = 51,100" in sc["arithmetic"]
    assert inline_product_findings(bc) == []


def test_overlapping_modules_and_list_named_phases_are_rejected_and_label_probes_are_specific():
    from app.pipeline.adjudicate import _label_check
    from app.pipeline.structural import module_overlap_findings, preflight

    mods = [{"id": "automated-cod-settlement-inquiry-handler", "name": "Automated COD Settlement Inquiry Handler",
             "purpose": "Answers business clients' COD settlement inquiries from the settlement records and escalates disputes.",
             "pain_point_addressed": "manual COD settlement inquiry handling", "depends_on": []},
            {"id": "cod-settlement-inquiry-bot", "name": "COD Settlement Inquiry Bot",
             "purpose": "Resolves COD settlement inquiries for business clients using settlement records, escalating disputes to finance.",
             "pain_point_addressed": "manual COD settlement inquiry handling", "depends_on": []},
            {"id": "driver-directions", "name": "Driver Directions Module", "purpose": "guides couriers to the confirmed pin",
             "pain_point_addressed": "drivers lost", "depends_on": []}]
    found = module_overlap_findings(mods)
    assert len(found) == 1 and "one capability split into two modules" in found[0]["issue"]
    assert any("split into two" in f["issue"] for f in preflight({"build_order": [m["id"] for m in mods]}, mods))
    assert module_overlap_findings(mods[1:]) == []
    md = ("- **Phase 1 — Pre-Dispatch Customer Confirmation Workflow:** proves it.\n"
          "- **Phase 2 — Location Verification & Availability Assistant, Driver 'Assisted Directions' Module, COD Settlement Inquiry Bot:** later.\n"
          "- **Phase 3 — Automated support replies:** last.\n")
    reg_mods = [{"client_facing_name": n} for n in ("Pre-Dispatch Customer Confirmation Workflow", "Location Verification & Availability Assistant",
                                                     "Driver 'Assisted Directions' Module", "COD Settlement Inquiry Bot")]
    found = rg.phase_name_findings(md, reg_mods)
    assert len(found) == 1 and "Phase 2" in found[0]["where"]
    corpus = ("the pilot covers 50% of eligible orders; resolves 50% of the top 10 most common COD settlement inquiry types "
              "(proposed — client approval required); another 50% of eligible orders.")
    labeled, evidence = _label_check("50% of the top 10 most common COD settlement inquiry types", corpus)
    assert labeled is True and "all 1 occurrence" in evidence


def test_preflight_retries_with_targeted_feedback_and_metric_direction_is_checked(client, monkeypatch):
    from app.pipeline import orchestrator as orch
    from app.templating import render

    claims = rg.client_fact_claims(json.loads(OPS), [])
    wrong_way = {**GATE47, "target": "A 25% relative reduction in first-attempt delivery success rate (proposed — client approval required)",
                 "change_kind": "relative", "target_value": 25}
    errs = pg.gate_errors(pg.normalize_gate(wrong_way, claims))
    assert any("contradicts a success-type" in e for e in errs)
    seen = []
    bad = {"modules": [{"id": "a", "name": "A", "purpose": "p", "depends_on": []}],
           "business_case": {"financial_model": {"scenarios": [
               {"name": "S", "assumption": "prevents 10% and resolves 25%", "impact": "Saved $7,096/year."}]}}}
    good = {"modules": [{"id": "a", "name": "A", "purpose": "p", "depends_on": []}], "business_case": {"financial_model": {"scenarios": []}}}

    def fake_decompose(db, request_id, *a, feedback=None, **k):
        seen.append(feedback)
        return good if len(seen) == 3 else bad

    monkeypatch.setattr(orch.decompose, "decompose_business", fake_decompose)
    out = orch._decompose_with_preflight(None, 1)
    assert out is good and seen[0] is None and seen[1] and "promises 2 impact mechanism" in seen[1][0] and seen[2]
    prompt = render("decompose.j2", business_name="B", business_description="d", industry="i", revenue_today="r",
                    main_problem="m", desired_outcome="o", site_research="none", business_model="x",
                    target_customer_profile="", pain_points="[]", growth_opportunity="", consulting_summary="",
                    recommended_ai_employees="[]", recommended_features="[]", concept_name="C", min_modules=3,
                    max_modules=7, operating_stage="operating", owner_numbers="x", engagement_register="reg",
                    preflight_feedback="- pilot_gate: missing numerator")
    assert "PREVIOUS ATTEMPT WAS REJECTED" in prompt and "missing numerator" in prompt


def test_run49_classes_prose_formulas_compute_acceptance_checks_exist_future_ai_is_consistent(client):
    from app.pipeline import timebasis as tb
    from app.pipeline.adjudicate import adjudicate
    from app.pipeline.structural import preflight

    text = ("Even a conservative estimate — ($70,956/year / 365 days/year * 30 operating days/month) * 25% for saving "
            "~$490 per month in re-attempt costs — pays for itself.")
    out, recs = tb.repair_expressions(text)
    assert "$1,458" in out and "$490" not in out and recs[0]["status"] == "snapped"
    ok = "(350 inquiries/day * 365 days/year) = 127,750 inquiries a year"
    assert tb.repair_expressions(ok)[0] == ok
    assert tb.repair_expressions("(900 x 12%) = 108 failed deliveries a day")[0].startswith("(900 x 12%) = 108")
    mods = copy.deepcopy(MODULES46)
    mods[1]["tech"]["done_when"] = ["To be established after the pilot, depending on its data."]
    found = [f for f in preflight({"build_order": BUILD_ORDER46}, mods) if "acceptance check" in f["issue"]]
    assert len(found) == 1 and "Delivery Incident Predictor" in found[0]["issue"]
    bc, mods2, reg = _skeleton()
    db = SessionLocal()
    row = _seed(db, business_case_json=json.dumps(bc), modules_json=json.dumps(mods2), registry_json=json.dumps(reg),
                qa_report_json=json.dumps({"checks": [], "findings": [
                    _finding("The product, module by module",
                             "The 'Delivery Incident Predictor' and 'Driver Clarification Assistant' modules are mentioned as 'AI' in their names, despite the decision explicitly stating 'deliberately defer full AI automation'.",
                             source="qa_completeness"),
                    _finding("The product, module by module > Delivery Incident Predictor",
                             "The 'You'll know it's working when' section for 'Delivery Incident Predictor' includes 'Baseline and target to be established during week-one measurement once this module is live.' implying immediate availability.",
                             source="qa_completeness"),
                ]}))
    result = adjudicate(row, {"blueprint": "once this module is live"})
    assert [e["classification"] for e in result["ledger"]] == ["semantic false positive resolved by structured phase data"] * 2
    assert "R27" in result["ledger"][0]["evidence"] and "R21" in result["ledger"][1]["evidence"]
    db.close()


def test_run49_round_two_gate_reads_on_the_page_as_stored_and_business_case_prose_is_arithmetic():
    from app.pipeline import export_pdf as ep
    from app.pipeline.decompose import _sanitize_financial_model

    claims = rg.client_fact_claims(json.loads(OPS), [])
    raw = {**GATE47, "guardrails": ["complaint rate increase > 2% relative to control group",
                                   "delivery delay increase >= 5% relative to control group"],
           "control_method": "50% of the pilot population will be randomly assigned to a control_group receiving standard notifications"}
    g = pg.normalize_gate(raw, claims)
    s = pg.canonical_sentence(g)
    full = pg.full_definition(g)
    assert ">" not in full and "more than 2%" in full and "at least 5%" in full
    assert "control group receiving" in g["control_method_stated"] and "randomized 50/50" in full
    assert g["control_method"] == pg.assignment_sentence(g)
    # what the renderer prints is exactly what is stored
    assert ep._strip_artifacts(s) == s and ep._strip_artifacts(full) == full
    assert pg.restatement_findings("The decision gate: " + s, g) == []
    bc = {"payback_logic": "Reducing failed first attempts by even 25% (a conservative estimate) would save ~$490 per month in re-attempt costs, by your own figures.",
          "financial_model": {"lines": [{"item": "re-attempt costs", "arithmetic": "900 * 365 * 0.12 * $1.80", "annual": "$70,956/year"}],
                              "scenarios": [{"name": "Conservative", "assumption": "prevents 25% of failed first attempts",
                                             "impact": "$17,739/year saved in re-attempt costs"}]}}
    _sanitize_financial_model(bc)
    assert "$1,458 per month" in bc["payback_logic"] and "$490" not in bc["payback_logic"]
    fixed, notes = rg.policy_pass("status enum: remittance_due_in_2_days | remittance_confirmed", claims)
    assert "remittance_due_in_10_days" in fixed and notes


def test_r26_structural_corroboration_confirms_a_scenario_arithmetic_finding(client):
    from app.pipeline.adjudicate import adjudicate

    bc = {"financial_model": {"lines": [{"item": "Annual support inquiries for 'where is my order'", "arithmetic": "350 * 365",
                                         "annual": "127,750 inquiries/year"}],
                              "scenarios": [{"name": "Conservative", "assumption": "resolves 40% of 'where is my order' inquiries",
                                             "arithmetic": "(127750 * 0.20) for 'where is my order' inquiries.",
                                             "impact": "51,100 fewer 'where is my order' inquiries/year"}]}}
    db = SessionLocal()
    row = _seed(db, business_case_json=json.dumps(bc), qa_report_json=json.dumps({"checks": [], "findings": [
        _finding("scenarios -> impact", "The 'Conservative' scenario impact arithmetic is given as '(127750 * 0.20)', leading to 25,550, but the impact states '51,100'.")]}))
    result = adjudicate(row, {"blueprint": "x"})
    assert result["ledger"][0]["classification"] == "real defect" and "R26" in result["ledger"][0]["evidence"]
    db.close()


def test_prose_thresholds_in_hand_off_sentences_are_labeled():
    bc, mods, reg = _skeleton()
    line = ("**Where it stops and hands to you:** it hands off when a customer doesn't respond quickly enough "
            "(2 hours for express/same-day, 4 hours for standard deliveries), or asks for human help.")
    out, new = rg.label_prose_thresholds(line, reg["claims"], {"n": 0})
    assert out.count(rg.PROPOSED_LABEL) == 2 and all(c["type"] == "timing_sla" for c in new)


def test_partial_extras_rebuild_merges_the_pilot_sop_into_the_existing_library(client, monkeypatch):
    from app.pipeline import extras

    bc, mods, reg = _skeleton()
    db = SessionLocal()
    existing = [{"name": "Handling a settlement inquiry", "phase": "future", "module": "Settlement Inquiry Resolver",
                 "trigger": "client message", "steps": [{"actor": "finance", "step": "Check the statement."}]}]
    row = _seed(db, business_case_json=json.dumps(bc), modules_json=json.dumps(mods), registry_json=json.dumps(reg),
                procedures_json=json.dumps({"procedures": existing}),
                scoreboard_json=json.dumps([{"metric": "x", "baseline": "measure in week 1", "target": "down"}]),
                org_json=json.dumps({"roles": [{"role": "Owner", "type": "human", "responsibilities": ["runs it"]}]}))

    def chat(model, messages, **kwargs):
        payload = {"procedures": [{"name": "Running the gate review", "phase": "pilot", "trigger": "end of the pilot",
                                   "steps": [{"actor": "you", "step": "Judge the pilot against [[PILOT_GATE]]"}],
                                   "exceptions": []}]}
        return {"choices": [{"message": {"content": json.dumps(payload)}}], "usage": {}}

    monkeypatch.setattr(extras.provider, "chat", chat)
    extras.build_extras(db, row.id, {}, {"modules": mods, "business_case": bc, "registry": reg}, only={"procedures:pilot"})
    db.refresh(row)
    procs = json.loads(row.procedures_json)["procedures"]
    assert [p["module"] for p in procs] == ["The pilot", "Settlement Inquiry Resolver"]
    assert procs[0]["steps"][0]["step"].endswith(reg["pilot_gate_sentence"])
    assert json.loads(row.scoreboard_json)[0]["metric"] == "x" and json.loads(row.org_json)["roles"][0]["role"] == "Owner"
    db.close()
