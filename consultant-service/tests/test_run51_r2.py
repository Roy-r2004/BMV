"""Run 51-r2: deterministic fixes and registry-evidenced detectors.

- a null decision right renders as a statement, never the literal Null
- a verified per-day / per-month restatement shows its derivation
- the duplicate-label detector accepts two separately REGISTERED proposals
- the identifier detector judges on registered identifiers, not hyphenated English
- R29 closes "the pilot is listed as a module" only on registry proof
- R30 judges a quoted sentence's thresholds inside that sentence, against the registry
"""
import copy
import json

from app.models import Request
from app.pipeline import registry as rg
from tests.test_volume_one_brief import GATE, MODULES, OPS


def test_null_decision_rights_render_as_a_statement_not_a_literal():
    from app.pipeline import blueprint as bp, export_pdf as ep

    md = "**Where the AI works:**\n- Role: Assists the team.\n- Decides alone: Null\n- Hands off: Ambiguity.\n"
    out = bp._no_null_lines(md)
    assert "Null" not in out and "- Decides alone: Nothing on its own — it proposes, a human decides." in out
    assert ep.find_artifacts(out) == []
    # and at the source: the structured spec never carries a null decision right
    mods = copy.deepcopy(MODULES)
    mods[1]["spec"]["ai"] = {"role": "Reads replies.", "decides_alone": "Null", "hands_off": None}
    reg = rg.build_registry(OPS, {"build_order": [m["id"] for m in mods]}, mods)
    ai = mods[1]["spec"]["ai"]
    assert ai["decides_alone"].startswith("Nothing on its own") and ai["hands_off"]
    assert {r["field"] for r in reg["null_values_replaced"]} == {"spec.ai.decides_alone", "spec.ai.hands_off"}
    assert rg.corrections(reg)["null_values_replaced"] == reg["null_values_replaced"]


def test_verified_daily_restatement_shows_its_derivation_once():
    from app.pipeline import timebasis as tb

    text = ("**What staying manual costs:** Staying as is means continuing to incur approximately $194.40 per day, "
            "by your own figures, in re-attempt costs.\n| row | $5,832 per month |\n")
    out, recs = tb.attribute_restatements(text, [70956.0])
    assert "$194.40 per day ($70,956 a year ÷ 365)," in out and "| row | $5,832 per month |" in out
    assert recs == [{"original": "$194.40 per day", "derivation": "$70,956 a year ÷ 365", "status": "derivation_shown"}]
    again, recs2 = tb.attribute_restatements(out, [70956.0])
    assert again == out and recs2 == []
    monthly, _ = tb.attribute_restatements("costing $5,832 per month today", [70956.0])
    assert "$5,832 per month ($70,956 a year ÷ 365 × 30)" in monthly
    assert tb.attribute_restatements("about $999 per day", [70956.0])[0] == "about $999 per day"


def test_duplicate_label_detector_accepts_two_registered_proposals_and_rejects_a_true_duplicate():
    from app.pipeline import export_pdf as ep

    two = ("If either falls below 70% (proposed — client approval required) and 60% "
           "(proposed — client approval required) respectively, review the responses.")
    reg = {"claims": [
        {"id": "TH-a-01", "type": "performance_target", "value": 0.7, "unit": "%", "provenance": "consultant_proposed"},
        {"id": "TH-a-02", "type": "performance_target", "value": 0.6, "unit": "%", "provenance": "consultant_proposed"},
    ], "modules": []}
    assert "duplicate approval label" not in ep.find_artifacts(two, reg)
    assert "duplicate approval label" in ep.find_artifacts(two)            # no registry: strict
    unregistered = two.replace("60%", "65%")
    assert "duplicate approval label" in ep.find_artifacts(unregistered, reg)
    true_dup = "within 15 minutes (proposed — client approval required) always (proposed — client approval required) now"
    assert "duplicate approval label" in ep.find_artifacts(true_dup, reg)


def test_identifier_detector_uses_registered_identifiers_not_hyphen_english():
    from app.pipeline import export_pdf as ep

    assert rg.identifier_artifacts("mark it pending and re-queue for review in 2 hours", []) == []
    assert rg.identifier_artifacts("wire the pin-capture-handler to the queue", []) == ["pin-capture-handler"]
    assert rg.identifier_artifacts("events land on the order-queue first", [], ["order-queue"]) == ["order-queue"]
    mods = copy.deepcopy(MODULES)
    mods[1]["tech"]["data_models"] = [{"name": "delivery-verification-record", "fields": ["id"]}]
    mods[1]["tech"]["queues"] = ["reply-queue"]
    reg = rg.build_registry(OPS, {"build_order": [m["id"] for m in mods]}, mods)
    assert {"delivery-verification-record", "reply-queue", "delivery-exception-ai-coordinator"} <= set(reg["technical_identifiers"])
    prose = "The team watches the reply-queue while customers re-queue their requests."
    assert "internal identifier in client-facing text" in ep.find_artifacts(prose, reg)
    assert ep.find_artifacts("customers re-queue their requests", reg) == []


def _finding(where, issue):
    return {"severity": "high", "source": "qa_completeness", "where": where, "issue": issue, "fix": "reword"}


def test_r29_closes_pilot_listed_as_module_only_with_registry_proof():
    from app.pipeline.adjudicate import adjudicate

    mods = copy.deepcopy(MODULES)
    bc = {"build_order": [m["id"] for m in mods], "pilot_gate": copy.deepcopy(GATE)}
    reg = rg.build_registry(OPS, bc, mods)
    pilot = next(m for m in reg["modules"] if m.get("pilot"))
    name = pilot["client_facing_name"]
    procs = {"procedures": [{"name": "Logging pilot orders", "module": name, "phase": "pilot", "steps": []}]}
    findings = [
        _finding("The product, module by module",
                 f"The '{name}' is listed as a module but its description suggests it is a pilot workflow, "
                 "not a distinct software module."),
        _finding("Procedures",
                 f"Procedures are listed under the module '{name}' with 'pilot' phase, implying procedures for a "
                 "module, not the pilot itself."),
        _finding("cost_of_inaction", "The derivation of $194.40 per day is not shown in the cost_of_inaction text."),
    ]
    row = Request(id=9151, business_name="x", status="done", modules_json=json.dumps(mods),
                  business_case_json=json.dumps(bc), registry_json=json.dumps(reg), procedures_json=json.dumps(procs),
                  qa_report_json=json.dumps({"checks": [], "findings": findings}))
    result = adjudicate(row, {"blueprint": "doc"}, persist=False)
    classes = [e["classification"] for e in result["ledger"]]
    assert classes[0].startswith("semantic false positive") and "R29" in result["ledger"][0]["evidence"]
    assert classes[1].startswith("semantic false positive") and "procedure(s)" in result["ledger"][1]["evidence"]
    assert classes[2] == "real defect"
    # without the gate as its only KPI claim the registry proves nothing — stays open
    reg2 = copy.deepcopy(reg)
    next(m for m in reg2["modules"] if m.get("pilot"))["kpi_claim_ids"] = ["MK-other-01"]
    row.registry_json = json.dumps(reg2)
    result2 = adjudicate(row, {"blueprint": "doc"}, persist=False)
    assert result2["ledger"][0]["classification"] == "real defect"


def test_r30_judges_sample_sizes_inside_their_own_sentence_with_registry_claims():
    from app.pipeline.adjudicate import adjudicate

    mods = copy.deepcopy(MODULES)
    mods[1]["tech"]["ai_agent"] = {"evaluation": [
        "Daily review of 100 random 'UNRESOLVED REPLY' logs by annotators (target 90% accuracy)."]}
    bc = {"build_order": [m["id"] for m in mods], "pilot_gate": copy.deepcopy(GATE)}
    reg = rg.build_registry(OPS, bc, mods)
    mod = next(m for m in reg["modules"] if m["id"] == "delivery-exception-ai-coordinator")
    name = mod["client_facing_name"]
    rendered = ("• Daily review of 100 random (proposed — client approval required) 'UNRESOLVED REPLY' logs by "
                "annotators (target 90% accuracy). (proposed — client approval required) • Next bullet with 100 orders a day.")
    where = f"{name}: 'Daily review of 100 random 'UNRESOLVED REPLY' logs by an"
    issue = "The numbers '100', '90%' are thresholds that are not client inputs and lack '(proposed — client approval required)'."
    row = Request(id=9152, business_name="x", status="done", modules_json=json.dumps(mods),
                  business_case_json=json.dumps(bc), registry_json=json.dumps(reg),
                  qa_report_json=json.dumps({"checks": [], "findings": [_finding(where, issue)]}))
    result = adjudicate(row, {"technical": rendered}, persist=False)
    e = result["ledger"][0]
    assert e["classification"].startswith("semantic false positive") and "R30" in e["evidence"] and "'90%' = TH-" in e["evidence"]
    # bare in its own sentence => real, even though the same number is labeled elsewhere on the page
    bare = ("• Daily review of 100 random 'UNRESOLVED REPLY' logs by annotators (target 90% accuracy). "
            "• Next bullet with 100 orders (proposed — client approval required) a day.")
    row.qa_report_json = json.dumps({"checks": [], "findings": [_finding(where, issue)]})
    result2 = adjudicate(row, {"technical": bare}, persist=False)
    assert result2["ledger"][0]["classification"] == "real defect" and "not labeled inside" in result2["ledger"][0]["evidence"]


def test_r31_a_derivation_printed_on_the_page_answers_the_attribution_objection():
    from app.pipeline.adjudicate import adjudicate

    bc = {"financial_model": {"lines": [{"label": "re-attempts", "annual": "70,956",
                                         "arithmetic": "900 deliveries/day * 0.12 * $1.80 * 365 days/year"}]}}
    finding = _finding("cost_of_inaction: 'Staying as is means continuing to incur approximate",
                       "The derivation of $194.40 per day, while arithmetically sound (70,956 / 365), is not explicitly "
                       "shown in the cost_of_inaction text itself, violating the 'attribution kept' rule.")
    row = Request(id=9153, business_name="x", status="done", business_case_json=json.dumps(bc),
                  qa_report_json=json.dumps({"checks": [], "findings": [finding]}))
    shown = {"blueprint": "Staying as is means continuing to incur approximately $194.40 per day ($70,956 a year ÷ 365), "
                          "by your own figures, in re-attempt costs."}
    result = adjudicate(row, shown, persist=False)
    e = result["ledger"][0]
    assert e["classification"] == "machine-proven false positive" and "R31" in e["evidence"] and "÷ 365" in e["evidence"]
    row.qa_report_json = json.dumps({"checks": [], "findings": [finding]})
    bare = {"blueprint": "Staying as is means continuing to incur approximately $194.40 per day, by your own figures."}
    assert adjudicate(row, bare, persist=False)["ledger"][0]["classification"] == "real defect"
