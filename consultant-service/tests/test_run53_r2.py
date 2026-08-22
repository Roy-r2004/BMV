"""53-r2: the five detector/renderer defects found on 53-r1, each pinned.

1. the renderer keeps URL paths and code spans intact
2. procedure actors render as role names, never bracketed tags
3. keyword / ALL-CAPS placeholders are caught; merge fields and lowercase tags are not
4. the design detector does not match "another client" and never flags the canonical sentence
5. the policy origin is restored even with labels in the way; a client cycle is never labeled
6. long quoted labeled fragments reach R2; a restored policy statement closes under R32
"""
import copy
import json

from app.models import Request
from app.pipeline import pilot_gate as pg
from app.pipeline import registry as rg
from tests.test_volume_one_brief import GATE, MODULES, OPS

CLAIMS = rg.client_fact_claims([{"question": "Days after month-end to fully settle COD with a client?", "answer": "10 days"}], [])


def test_renderer_keeps_paths_and_code_spans_while_de_snaking_prose():
    from app.pipeline import export_pdf as ep

    text = ("APIs: `/api/v1/pre_dispatch_confirmations/{delivery_id}/remind`, GET /api/v1/pre_dispatch_confirmations "
            "and the failed_first_attempt_rate field")
    out = ep._strip_artifacts(text)
    assert "`/api/v1/pre_dispatch_confirmations/{delivery_id}/remind`" in out
    assert "GET /api/v1/pre_dispatch_confirmations " in out and "failed first attempt rate" in out
    assert rg.api_text_findings(out, ["/api/v1/pre_dispatch_confirmations/{delivery_id}/remind",
                                      "/api/v1/pre_dispatch_confirmations"]) == []
    assert "pre_dispatch_confirmations" in ep._rich(text)


def test_procedure_actors_render_as_role_names():
    from app.pipeline import export_pdf as ep

    procs = [{"name": "Confirming a delivery", "phase": "future", "module": "Customer Location & Availability Interface",
              "trigger": "link sent", "steps": [{"actor": "[customer]", "step": "Accesses the secure link."},
                                                {"actor": "customer", "step": "Adjusts the map pin."},
                                                {"actor": "AI Delivery Pre-Confirmation Engine", "step": "Scores the reply."}]}]
    texts = " ".join(getattr(f, "text", "") for f in ep._procedures_flowables(procs))
    assert "[customer]" not in texts and "[Customer]" not in texts
    assert "Customer:</b>" in texts and "AI Delivery Pre-Confirmation Engine:</b>" in texts


def test_placeholder_detection_is_case_correct_and_keeps_merge_fields():
    from app.pipeline import export_pdf as ep
    from app.pipeline.structural import preflight

    assert ep.find_artifacts("Hello [CustomerName], this is the courier about your delivery") == []
    assert ep.find_artifacts("3. [customer] Accesses the secure link") == []
    # (an ALL-CAPS token never reaches the page: the renderer resolves it to an
    # approved-value slot and the registry records the replacement — the
    # structural check below catches it at the source)
    assert "unresolved placeholder" in ep.find_artifacts("owner: [TODO fill in]")
    assert "unresolved placeholder" in ep.find_artifacts("signed by [Insert name]")
    assert ep.find_artifacts("owner: [TODO fill in] and [Insert name]").count("unresolved placeholder") == 1
    mods = copy.deepcopy(MODULES)
    mods[1]["tech"]["done_when"][0] = "Sends 'Hello [CustomerName], your parcel is on its way' to every confirmed order."
    assert not [f for f in preflight({"build_order": [m["id"] for m in mods]}, mods) if "placeholder" in f["issue"]]
    mods[1]["tech"]["done_when"][0] = "Sends the message to [OWNER_NAME] for approval."
    assert [f for f in preflight({"build_order": [m["id"] for m in mods]}, mods) if "placeholder" in f["issue"]]


def test_design_detector_ignores_another_client_and_never_flags_the_canonical_sentence():
    g = pg.normalize_gate(copy.deepcopy(GATE))
    assert pg._BAD_CONTROL.search("never drawn from another client, zone or period") is None
    assert pg._BAD_CONTROL.search("orders from other zones serve as the control group")
    assert pg.design_findings(pg.full_definition(g), g) == []
    assert pg.design_findings(pg.assignment_sentence(g), g) == []
    assert pg.design_findings("Orders from other zones will serve as the control group.", g)


def test_policy_origin_is_restored_through_labels_and_a_client_cycle_is_never_labeled():
    s1 = "aligning with the policy of remitting within 10 days (your stated cycle) (proposed — client approval required) of collection."
    out1, notes1 = rg.policy_pass(s1, CLAIMS)
    assert "within 10 days after month-end (your stated cycle)." in out1 and "collection" not in out1 and notes1
    s2 = "remittance dates (within 10 days after month-end to fully settle COD with a client (proposed — client approval required))"
    assert rg.policy_findings({"t": s2}, CLAIMS) and "approval label" in rg.policy_findings({"t": s2}, CLAIMS)[0]["issue"]
    out2, notes2 = rg.policy_pass(s2, CLAIMS)
    assert "(proposed" not in out2 and "within 10 days after month-end to fully settle COD with a client (your stated cycle)" in out2
    assert rg.policy_findings({"t": out2}, CLAIMS) == [] and rg.policy_findings({"t": out1}, CLAIMS) == []
    assert rg.policy_pass(out2, CLAIMS)[0] == out2


def _finding(where, issue):
    return {"severity": "high", "source": "qa_numbers_recheck", "where": where, "issue": issue, "fix": "reword"}


def test_long_labeled_fragment_reaches_r2_and_a_restored_policy_closes_under_r32():
    from app.pipeline.adjudicate import adjudicate

    mods = copy.deepcopy(MODULES)
    bc = {"build_order": [m["id"] for m in mods], "pilot_gate": copy.deepcopy(GATE)}
    reg = rg.build_registry(OPS, bc, mods)
    reg["claims"] += CLAIMS
    long_q = ("This assumes a minimum 1-hour window and a maximum 4-hour window (proposed — client approval required) "
              "for delivery times.")
    f1 = _finding("THE BLUEPRINT DOCUMENT -> Engine -> Delivery Window",
                  f"The assumption '{long_q}' introduces specific time windows without deriving them from client inputs "
                  "or labeling them as proposed for client approval.")
    f2 = _finding("THE BLUEPRINT DOCUMENT -> Resolver -> Proactive Payment",
                  "The statement 'aligning with the policy of remitting within 10 days (your stated cycle) of collection.' is "
                  "inconsistent with the client input 'Days after month-end to fully settle COD with a client?: 10 days'.")
    row = Request(id=9301, business_name="x", status="done", modules_json=json.dumps(mods), business_case_json=json.dumps(bc),
                  registry_json=json.dumps(reg), qa_report_json=json.dumps({"checks": [], "findings": [f1, f2]}))
    page = {"blueprint": f"Delivery window. {long_q} Remittances follow the policy of remitting within 10 days after "
                         "month-end (your stated cycle) of collection."}
    # the second sentence still counts from 'collection'? no — the origin reads 'after month-end'; the page is clean
    result = adjudicate(row, page, persist=False)
    kinds = {e["id"]: e["classification"] for e in result["ledger"]}
    assert kinds["F01"] == "machine-proven false positive" and "R2" in result["ledger"][0]["evidence"]
    assert kinds["F02"] == "machine-proven false positive" and "R32" in result["ledger"][1]["evidence"]
    # the bad wording still on the page => stays real
    row.qa_report_json = json.dumps({"checks": [], "findings": [f2]})
    bad = {"blueprint": "aligning with the policy of remitting within 10 days (your stated cycle) of collection."}
    assert adjudicate(row, bad, persist=False)["ledger"][0]["classification"] == "real defect"
