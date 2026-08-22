"""The integrity layer — one registry-driven pass before rendering."""
import copy
import json

from app.database import SessionLocal
from app.models import Request
from app.pipeline import integrity as it
from app.pipeline import pilot_gate as pg
from app.pipeline import registry as rg
from tests.test_registry_controls import _seed, client  # noqa: F401 — the fixture
from tests.test_volume_one_brief import GATE, MODULES, OPS


def _content(mods=None, **extra):
    mods = copy.deepcopy(mods or MODULES)
    bc = {"build_order": [m["id"] for m in mods], "pilot_gate": copy.deepcopy(GATE)}
    reg = rg.build_registry(OPS, bc, mods)
    content = {"modules": mods, "business_case": bc, "registry": reg, "procedures": {"procedures": []}, "checklists": None,
               "scoreboard": None, "risks": None, "journey": None, "org": None, "playbook": None, "blueprint": "", "technical": "",
               "ops_numbers": OPS, "free_texts": ["We deliver e-commerce COD orders, same-day and express on-demand deliveries."],
               "concept_name": "Beacon", "business_name": "Beacon"}
    content.update(extra)
    return content


def test_automation_level_is_the_structured_ai_component():
    mods = copy.deepcopy(MODULES)
    mods[2]["automation_level"], mods[2]["ai_involvement"] = "rules", True
    mods[2]["spec"]["ai"] = {"role": "categorizes escalations"}
    content = _content(mods)
    facts = it.derive_facts(content)
    findings = [f for f in it.validate(content, facts) if f.get("kind") == "misclassification" and "classified" in f["issue"]]
    assert findings and mods[2]["name"] in findings[0]["issue"]
    ledger = {}
    it.correct_automation_class(content, facts, ledger)
    assert content["modules"][2]["automation_level"] == "ai" and ledger["automation_reclassified"][0]["to"] == "ai"
    assert not [f for f in it.validate(content, facts) if "classified" in f["issue"]]


def test_aliases_abbreviations_and_humanized_ids_resolve_to_the_registered_name():
    content = _content()
    facts = it.derive_facts(content)
    engine = content["modules"][1]["name"]                      # Delivery Exception AI Coordinator
    humanized = it._humanize(content["modules"][2]["id"])       # Unified Support Workbench
    short = " ".join(engine.split()[:1] + engine.split()[2:])   # drop an inner word
    text = f"The {short} feeds the {humanized}; the {pg.PILOT_TOOLING} module holds the rest."
    fixed, recs = it.resolve_names(text, facts)
    assert engine in fixed and content["modules"][2]["name"] in fixed and f"{pg.PILOT_TOOLING} module" not in fixed
    assert {r["alias"] for r in recs} >= {short, f"{pg.PILOT_TOOLING} module"}
    assert [f for f in it.validate_texts({"t": text}, content, facts) if f["kind"] == "drift"]
    assert not [f for f in it.validate_texts({"t": fixed}, content, facts) if f["kind"] == "drift"]


def test_unregistered_product_names_are_flagged_and_replaced():
    content = _content()
    facts = it.derive_facts(content)
    text = "This blueprint proposes a phased implementation of a smart Delivery & Settlement Resolution Hub, beginning with a pilot."
    assert it.unregistered_names(text, facts) == ["Delivery & Settlement Resolution Hub"]
    fixed, recs = it.replace_unregistered_names(text, facts)
    assert "Resolution Hub" not in fixed and "implementation of the system, beginning" in fixed and recs
    ok = f"The {content['modules'][1]['name']} and the {pg.PILOT_CUSTOMER_FORM} are registered."
    assert it.unregistered_names(ok, facts) == []


def test_phase_statements_follow_the_registry():
    mods = copy.deepcopy(MODULES)
    content = _content(mods)
    facts = it.derive_facts(content)
    by = {t["name"]: t for t in facts["modules"]}
    pilot = facts["pilot_names"][0]
    seq = [t for t in facts["modules"] if t["phase_number"] == 2]
    par = [t for t in facts["modules"] if t["workstream"] == "parallel"]
    assert seq and par
    text = (f"• Phase 1 — {pilot}: the pilot.\n• Phase 3 — {seq[0]['name']}: wrong number.\n"
            f"• Phase 4 — {par[0]['name']}: runs in parallel.\nFinally, in parallel, build the {seq[0]['name']}.")
    fixed, recs = it.correct_phase_statements(text, facts)
    assert f"Phase 2 — {seq[0]['name']}" in fixed and f"Parallel workstream — {par[0]['name']}" in fixed
    assert "Finally, build the" in fixed and len(recs) == 3
    assert it.phase_statement_findings(text, facts, "t") and it.phase_statement_findings(fixed, facts, "t") == []


def test_only_thresholds_wear_the_label_and_it_has_one_form():
    cases = {
        "transmitted over TLS 1.2 (proposed — client approval required)+": "transmitted over TLS 1.2+",
        "returns a 403 (proposed — client approval required) Forbidden": "returns a 403 Forbidden",
        "generate a random number between 0 (proposed — client approval required) and 1": "generate a random number between 0 and 1",
        "1. (proposed — client approval required) Pilot: first": "1. Pilot: first",
        "within 5 seconds (proposed - client approval required)": f"within 5 seconds {it.LABEL}",
    }
    for src, want in cases.items():
        assert it.normalize_labels(src)[0] == want, src
        assert rg.plain_language(src) == want, src
    kept = f"after 3 attempts {it.LABEL}"
    assert it.normalize_labels(kept)[0] == kept
    assert it.nonthreshold_label_findings("returns a 403 (proposed — client approval required) Forbidden", "t")
    assert it.nonthreshold_label_findings(kept, "t") == []
    # the number scanner never registers them either
    claims = []
    out, new = rg.threshold_pass("Transmitted over TLS 1.2; an expired link returns 403 Forbidden; draw a random number between 0 and 1.",
                                 claims, source="s", module_id="m", counter={"n": 0})
    assert "(proposed" not in out and new == []


def test_kpi_proposal_units_and_mutilated_names():
    content = _content()
    content["registry"]["claims"].append({"id": "MK-x-02", "type": "module_kpi", "value": 0.85, "unit": "%", "scope": "x",
                                          "provenance": "consultant_proposed",
                                          "text": "Percentage of escalated inquiries resolved by human support business day: 0.85 %"})
    assert it.kpi_unit_findings(content)
    ledger = {}
    it.correct_kpi_claims(content, ledger)
    c = content["registry"]["claims"][-1]
    assert c["text"] == "Percentage of escalated inquiries resolved by human support: 85%" and ledger["kpi_units_corrected"] and ledger["kpi_text_repaired"]
    assert it.kpi_unit_findings(content) == []


def test_standin_duplicates_collapse_to_one_entry():
    mods = copy.deepcopy(MODULES)
    q = pg.PILOT_TOOLING
    mods[0]["tech"] = {"build_sequence": ["Set up the records.", f"Set up the {q} to process responses.", f"Build the {q} to interact with records."],
                       "integrations": [{"system": q, "direction": "out"}, {"system": q, "direction": "both"}, {"system": "Dispatch System"}],
                       "done_when": ["a", "b"]}
    content = _content(mods)
    facts = it.derive_facts(content)
    assert it.standin_duplicate_findings(content, facts)
    ledger = {}
    it.dedupe_standin_entries(content, facts, ledger)
    tech = content["modules"][0]["tech"]
    assert len(tech["build_sequence"]) == 2 and len(tech["integrations"]) == 2 and len(ledger["standin_duplicates_removed"]) == 2
    assert it.standin_duplicate_findings(content, facts) == []


def test_checklists_horizons_and_misfiled_procedures_are_classified():
    mods = copy.deepcopy(MODULES)
    future = mods[1]["name"]
    content = _content(mods, checklists={"checklists": [{"name": "Daily review", "items": [f"Check the {future} queue."]},
                                                        {"name": "Pilot log", "items": ["Fill the pilot log."]}], "forms": []},
                       playbook={"steps": [{"title": "Integrate", "horizon": "weeks 3-5"}, {"title": "Approve", "horizon": "week 1"}]},
                       procedures={"procedures": [{"name": "Handling inquiries", "phase": "future", "module": mods[1]["name"],
                                                   "steps": [{"actor": mods[2]["name"], "step": "a"}, {"actor": mods[2]["name"], "step": "b"},
                                                             {"actor": mods[2]["name"], "step": "c"}, {"actor": mods[1]["name"], "step": "d"}]}]})
    facts = it.derive_facts(content)
    assert it.checklist_phase_findings(content, facts) and it.horizon_findings(content) and it.procedure_home_findings(content, facts)
    ledger = {}
    it.classify_checklists(content, facts, ledger)
    it.label_playbook_horizons(content, ledger)
    it.rehome_procedures(content, facts, ledger)
    cl = content["checklists"]["checklists"]
    assert cl[0]["phase"] == "future" and future in cl[0]["phase_note"] and cl[1]["phase"] == "pilot"
    assert content["playbook"]["steps"][0]["horizon"] == "weeks 3-5 " + it.LABEL and content["playbook"]["steps"][1]["horizon"] == "week 1"
    assert content["procedures"]["procedures"][0]["module"] == mods[2]["name"] and ledger["procedures_rehomed"]
    assert not (it.checklist_phase_findings(content, facts) or it.horizon_findings(content) or it.procedure_home_findings(content, facts))


def test_phase_line_subject_is_the_first_named_module_and_names_are_judged_on_one_line():
    mods = copy.deepcopy(MODULES)
    content = _content(mods)
    facts = it.derive_facts(content)
    by = {t["name"]: t for t in facts["modules"]}
    seq = [t for t in facts["modules"] if t["phase_number"] == 2][0]
    three = [t for t in facts["modules"] if t["phase_number"] == 3] or [seq]
    line = f"• Phase 5 — Human Handoffs: {three[0]['name']} handles issues from both the {facts['pilot_names'][0]} and the {seq['name']}."
    fixed, recs = it.correct_phase_statements(line, facts)
    assert fixed.startswith(f"• Phase {three[0]['phase_number']} — Human Handoffs: {three[0]['name']}") and recs
    wrapped = f"The {seq['name'].replace(' ', chr(10), 1)} is registered even when a page break splits it."
    assert it.unregistered_names(wrapped, facts) == []


def test_link_accessed_queue_is_the_customer_form_including_integration_entries():
    q, form = pg.PILOT_TOOLING, pg.PILOT_CUSTOMER_FORM
    assert rg.customer_queue_findings(f"Screens: {q} (accessed via WhatsApp link)", "t")
    assert rg.customer_facing_pass(f"{q} (accessed via WhatsApp link)")[0] == f"{form} (accessed via WhatsApp link)"
    assert rg.customer_queue_findings(f"Flags orders for human intervention via the {q}.", "t") == []
    module = {"id": "p", "pilot": True, "tech": {"integrations": [
        {"system": q, "direction": "out", "data": "Out: Unique URL with delivery id token for customer to access interface."},
        {"system": q, "direction": "out", "data": "Out: Escalation request with delivery id and reason."}]}}
    assert len(rg.integration_channel_findings(module)) == 1
    recs = rg.integration_channel_pass(module)
    assert module["tech"]["integrations"][0]["system"] == form and module["tech"]["integrations"][1]["system"] == q and recs
    assert rg.integration_channel_findings(module) == []


def test_the_guard_rejects_a_rewrite_beyond_its_floor_unless_canonical():
    content = _content()
    facts = it.derive_facts(content)
    ledger = {}
    original = "Customers confirm their address through a link before dispatch."
    assert it.guard(original, "Something entirely different happened here today.", "test", facts, ledger, "t") == original
    assert ledger["rejected_rewrites"][0]["rule"] == "test"
    close = original.replace("a link", "the " + pg.PILOT_CUSTOMER_FORM)
    assert it.guard(original, close, "test", facts, ledger, "t") == close
    canon = pg.assignment_sentence(facts["gate"])
    assert it.guard(original, canon, "test", facts, ledger, "t") == canon


def test_enforce_persists_a_current_report_and_the_gate_depends_on_it(client):
    from app.pipeline import export_pdf as ep

    mods = copy.deepcopy(MODULES)
    bc = {"build_order": [m["id"] for m in mods], "pilot_gate": copy.deepcopy(GATE)}
    reg = rg.build_registry(OPS, bc, mods)
    db = SessionLocal()
    row = _seed(db, mvp_blueprint="## The decision\nA plan.\n\n## Executive summary\nfine\n", technical_plan="## How your system works\nfine\n",
                business_case_json=json.dumps(bc), modules_json=json.dumps(mods), registry_json=json.dumps(reg), ops_numbers_json=OPS,
                procedures_json=json.dumps({"procedures": []}), qa_report_json=json.dumps({"checks": [], "findings": []}),
                integrity_stamp=False)
    assert "integrity layer has not run" in " ".join(ep.release_status(row)["reasons"])
    report = it.enforce(db, row.id)
    db.refresh(row)
    assert report["version"] == it.VERSION and report["content_hash"] == it.content_hash(it.load(row))
    assert it.current_report(row) is not None
    assert not any("integrity layer" in r for r in ep.release_status(row)["reasons"]) or not report["clean"]
    # any later change to the content invalidates the report
    row.mvp_blueprint += "\nA new sentence."
    assert it.current_report(row) is None and "integrity layer has not run" in " ".join(ep.release_status(row)["reasons"])
    db.close()
