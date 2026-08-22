"""53-r4: the seven content defects the independent audit found on 53-r3,
each as a generic registry/renderer law with a pin.

1. an invented settlement period hiding behind a label or a parenthesis is caught and restored
2. one pilot procedure set; contradictory attempt counts are a finding
3. a customer never receives the internal queue — the customer-facing form stands in
4. a relative gate target carries the relative formula
5. a pilot string never narrows the gate's population
6. "3. Implement …" is a list item, not a threshold
7. clock times and review cadences are labeled proposals
"""
import copy
import json

from app.pipeline import pilot_gate as pg
from app.pipeline import registry as rg
from tests.test_volume_one_brief import GATE, MODULES, OPS

CLAIMS = rg.client_fact_claims([{"question": "Days after month-end to fully settle COD with a client?", "answer": "10 days"}], [])


def test_invented_period_behind_a_label_or_parenthesis_is_caught_and_restored():
    s1 = "Responses detail collection amounts, remittance dates (within 2 days (proposed — client approval required) of order delivery), and any outstanding items."
    s2 = "Sends notifications on the status of their COD remittances, aligning with the 'within 2 days (proposed — client approval required) of order delivery' policy."
    for s in (s1, s2):
        assert rg.policy_findings({"t": s}, CLAIMS), s
        fixed, notes = rg.policy_pass(s, CLAIMS)
        assert "2 days" not in fixed and "order delivery" not in fixed and "(proposed" not in fixed and notes
        assert "within 10 days after month-end (your stated cycle)" in fixed
        assert rg.policy_findings({"t": fixed}, CLAIMS) == []


def test_one_pilot_procedure_set_and_one_attempt_count():
    pilot_name = "Pre-Dispatch WhatsApp Pilot"
    procs = [
        {"name": "Conducting outreach", "phase": "pilot", "module": "The pilot", "trigger": "each treatment order",
         "steps": [{"actor": "support staff", "step": "Send the message, wait 30 minutes (proposed — client approval required), send a second, then a third and final message."},
                   {"actor": "support staff", "step": "Orders still empty after three attempts are marked unconfirmed."}]},
        {"name": "Managing confirmations", "phase": "pilot", "module": pilot_name, "trigger": "a new order",
         "steps": [{"actor": "Pilot Support Operator", "step": "Sends one reminder if no response within 30 minutes (proposed — client approval required)."}],
         "exceptions": [{"when": "cannot reach the customer after 3 attempts (proposed — client approval required) over 30 minutes", "then": "mark it"}]},
        {"name": "Future thing", "phase": "future", "module": "Unified Support Workbench", "trigger": "x", "steps": []},
    ]
    found = rg.pilot_procedure_findings(procs, {pilot_name})
    assert any("Two pilot procedure sets" in f["issue"] for f in found) and any("attempt counts" in f["issue"] for f in found)
    removed = rg.consolidate_pilot_procedures(procs, {pilot_name})
    assert [r["procedure"] for r in removed] == ["Managing confirmations"]
    assert [p["name"] for p in procs] == ["Conducting outreach", "Future thing"]
    assert rg.pilot_procedure_findings(procs, {pilot_name}) == []


def test_customer_receives_the_pilot_form_never_the_internal_queue():
    q, form = pg.PILOT_TOOLING, pg.PILOT_CUSTOMER_FORM
    s = (f"Sends a WhatsApp message to customers asking them to confirm their delivery location via a link to the {q} "
         f"before dispatch. Flags the order as high-risk for human intervention via the {q} if no confirmation is received.")
    assert rg.customer_queue_findings(s, "t") and len(rg.customer_queue_findings(s, "t")) == 1
    fixed, recs = rg.customer_facing_pass(s)
    assert f"via a link to the {form} before dispatch." in fixed and f"human intervention via the {q}" in fixed and recs
    assert rg.customer_queue_findings(fixed, "t") == []
    # registry: a later module a customer uses stands in as the form; a staff module as the queue
    mods = copy.deepcopy(MODULES)
    pm = mods[0]
    mods[1]["users"] = ["customer"]
    mods[2]["users"] = ["support staff"]
    pm["spec"]["features"] = [{"name": "Confirm", "description": f"Customers confirm their address through the {mods[1]['name']}; "
                                                                   f"flagged orders go to the {mods[2]['name']}."}]
    rg.build_registry(OPS, {"build_order": [m["id"] for m in mods], "pilot_gate": copy.deepcopy(GATE)}, mods)
    desc = mods[0]["spec"]["features"][0]["description"]
    assert form in desc and q in desc and mods[1]["name"] not in desc and mods[2]["name"] not in desc


def test_relative_target_carries_the_relative_formula():
    raw = copy.deepcopy(GATE)
    raw["target"] = "A 15% relative rise in first-attempt delivery success rate (proposed — client approval required)"
    raw["target_value"], raw["change_kind"] = 15, "relative"
    g = pg.normalize_gate(raw)
    assert g["comparison_metric"].startswith("(treatment First-attempt delivery success rate minus control")
    assert g["target_formula"] == "(treatment rate − control rate) ÷ control rate must be at least 15%"
    assert g["target_formula"] in pg.full_definition(g) and "15 percent (relative)" in pg.canonical_sentence(g)
    pp = pg.normalize_gate(copy.deepcopy(GATE))
    assert pp["comparison_metric"].startswith("treatment First-attempt") and "percentage points" in pp["target_formula"]


def test_pilot_strings_never_narrow_the_gate_population():
    g = pg.normalize_gate(copy.deepcopy(GATE))  # population: all first-attempt deliveries to new customers
    kinds = rg.service_types(["We deliver e-commerce COD orders, same-day and express on-demand deliveries across Lebanon."])
    assert {"e-commerce", "cod", "same-day", "express", "on-demand"} <= set(kinds)
    s = "The pilot sends a WhatsApp message before dispatch for their same-day and express on-demand deliveries."
    assert rg.population_findings(s, g, "t", kinds)
    # a later module's own scope is not the pilot population: document-text checks are pilot-scoped
    later = "The engine validates windows for same-day and express on-demand deliveries."
    assert rg.population_findings(later, g, "t", kinds) == [] and rg.population_findings(later, g, "t", kinds, pilot_scope=False)
    fixed, recs = rg.population_pass(s, g, kinds)
    assert fixed == "The pilot sends a WhatsApp message before dispatch for their eligible deliveries." and recs
    assert rg.population_findings(fixed, g, "t", kinds) == []
    # ordinary prepositional phrases are not service types
    for ok in ("Sends a WhatsApp message for new customer deliveries in the pilot.",
               "This cuts the cost of failed first-attempt deliveries.", "Asks them to confirm their exact delivery spot."):
        assert rg.population_findings(ok, g, "t", kinds) == [] and rg.population_pass(ok, g, kinds)[0] == ok
    # without the client's service types the rule stays silent
    assert rg.population_findings(s, g, "t", []) == []


def test_list_items_lose_their_own_numbers_before_typing():
    mods = copy.deepcopy(MODULES)
    mods[1]["tech"]["build_sequence"] = ["1. Define the data models.", "3. Implement the WhatsApp integration.", "(4) Build the dashboard."]
    reg = rg.build_registry(OPS, {"build_order": [m["id"] for m in mods], "pilot_gate": copy.deepcopy(GATE)}, mods)
    seq = mods[1]["tech"]["build_sequence"]
    assert seq == ["Define the data models.", "Implement the WhatsApp integration.", "Build the dashboard."]
    assert not [c for c in reg["claims"] if c.get("source", "").startswith("tech.build_sequence") and c.get("value") in (1, 3, 4)]


def test_operating_times_and_cadences_are_labeled_proposals():
    procs = [{"name": "Preparing orders", "phase": "pilot", "module": "The pilot",
              "trigger": "Daily, at the start of business day (e.g. 8:00 AM Beirut time), before dispatch",
              "steps": [{"actor": "staff", "step": "Daily: compile the summary at 5:00 PM."}]}]
    assert len(rg.operating_time_findings(procs)) == 1
    rg.type_procedures(procs, [], {"n": 0})
    t, s = procs[0]["trigger"], procs[0]["steps"][0]["step"]
    assert t.startswith("Daily (proposed — client approval required), at the start") and "8:00 AM (proposed — client approval required) Beirut" in t
    assert s.startswith("Daily (proposed — client approval required):") and "5:00 PM (proposed — client approval required)." in s
    assert rg.operating_time_findings(procs) == [] and rg.operating_time_pass(t)[0] == t
