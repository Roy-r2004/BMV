"""The integrity layer, v2 — one typed canonical registry, validation only.

The contract these tests pin:
  * canon.build gives ONE entity per real thing, with its other spellings as
    surface forms and no ambiguity;
  * the ONLY automatic correction is an exact canonical mapping, applied in a
    single left-to-right scan (so a surface form inside its own canonical form
    is never rewritten, and applying it twice changes nothing);
  * nothing else is modified: verify() leaves the content byte-identical;
  * every disagreement is a typed finding that blocks release;
  * the report is bound to a hash of the content it was computed on.
"""
import copy
import json

from app.database import SessionLocal
from app.models import Request
from app.pipeline import canon as C
from app.pipeline import integrity as it
from app.pipeline import pilot_gate as pg
from app.pipeline import registry as rg
from tests.test_registry_controls import _seed, client  # noqa: F401 — the fixture
from tests.test_volume_one_brief import GATE, MODULES, OPS


def _content(mods=None, **extra):
    mods = copy.deepcopy(mods or MODULES)
    bc = {"build_order": [m["id"] for m in mods], "pilot_gate": copy.deepcopy(GATE)}
    reg = rg.build_registry(OPS, bc, mods)
    content = {"modules": mods, "business_case": bc, "registry": reg, "procedures": {"procedures": []},
               "checklists": None, "scoreboard": None, "risks": None, "journey": None, "org": None,
               "playbook": None, "blueprint": "", "technical": "", "ops_numbers": OPS,
               "free_texts": ["We deliver e-commerce COD orders, same-day and express on-demand deliveries."],
               "concept_name": "Beacon", "business_name": "Beacon"}
    content.update(extra)
    return content


# ── the canonical registry ───────────────────────────────────────────────────


def test_one_entity_per_thing_with_its_other_spellings_and_no_ambiguity():
    content = _content(org={"roles": [{"role": "iCARRY Support Staff", "type": "human"}]},
                       procedures={"procedures": [{"name": "p", "phase": "pilot", "module": "The pilot",
                                                   "steps": [{"actor": "iCARRY support staff", "step": "x"}]}]})
    canon = C.build(content)
    # a module that is also an actor and a named system is ONE entity
    pilot = next(e for e in canon.of_kind("module") if e.data.get("pilot"))
    assert "module" in pilot.data["roles"]
    # the org spelling is canonical; the procedure spelling is a surface form
    staff = canon.resolve("iCARRY support staff")
    assert staff.unique and staff.entity.canonical == "iCARRY Support Staff"
    # no surface form denotes two entities
    assert [(s, ids) for s, ids in canon._index.items() if len(ids) > 1] == []
    # every kind the engagement has is typed
    assert {"module", "interface", "actor", "phase", "gate", "fact"} <= {e.kind for e in canon._entities.values()}


def test_resolution_is_exact_unique_ambiguous_or_unknown():
    canon = C.build(_content())
    engine = next(e for e in canon.of_kind("module") if e.data.get("has_ai_component") or "AI" in e.canonical)
    assert canon.resolve(engine.canonical).unique
    assert canon.resolve("Delivery & Settlement Resolution Hub").status == "unknown"
    amb = C.Canon([C.Entity("module:a", "module", "Alpha Engine", ("Shared Name",), {}),
                   C.Entity("module:b", "module", "Beta Engine", ("Shared Name",), {})])
    assert amb.resolve("Shared Name").status == "ambiguous" and len(amb.resolve("Shared Name").candidates) == 2


def test_only_acronym_prefixes_make_a_suffix_surface_form():
    """'AI COD X Y' may be written 'COD X Y'; 'iCARRY Support Staff' must NOT
    register 'Support Staff' — ordinary English would be rewritten."""
    assert C._drop_leading_words("AI COD Settlement Inquiry Resolver") == {
        "COD Settlement Inquiry Resolver", "Settlement Inquiry Resolver"}
    assert C._drop_leading_words("iCARRY Support Staff") == set()
    assert C._drop_leading_words("Pre-Dispatch Customer Confirmation Pilot") == set()


# ── the one permitted correction ─────────────────────────────────────────────


def test_exact_mapping_is_a_single_scan_and_never_rewrites_a_canonical_form():
    canon = C.Canon([
        C.Entity("module:r", "module", "AI COD Settlement Inquiry Resolver", ("COD Settlement Inquiry Resolver",), {}),
        C.Entity("actor:s", "actor", "iCARRY Support Staff", ("iCARRY support staff",), {}),
    ])
    text = ("The AI COD Settlement Inquiry Resolver answers; the COD Settlement Inquiry Resolver escalates to "
            "iCARRY support staff.")
    once, applied = canon.apply_exact_mappings(text, "t")
    assert once == ("The AI COD Settlement Inquiry Resolver answers; the AI COD Settlement Inquiry Resolver escalates to "
                    "iCARRY Support Staff.")
    assert {m.surface for m in applied} == {"COD Settlement Inquiry Resolver", "iCARRY support staff"}
    # idempotent, and no name is ever doubled
    twice, again = canon.apply_exact_mappings(once, "t")
    assert twice == once and again == []
    import re

    assert not re.search(r"(?<!\w)((?:[A-Z][\w&'-]*\s+){1,4})\1", twice)


def test_an_ambiguous_surface_is_never_mapped():
    canon = C.Canon([C.Entity("module:a", "module", "Alpha Engine", ("Shared Name",), {}),
                     C.Entity("module:b", "module", "Beta Engine", ("Shared Name",), {})])
    out, applied = canon.apply_exact_mappings("The Shared Name runs nightly.", "t")
    assert out == "The Shared Name runs nightly." and applied == []


def test_unknown_content_is_never_replaced_by_generic_wording():
    content = _content(blueprint="This blueprint proposes a smart Delivery & Settlement Resolution Hub for you.\n")
    canon = C.build(content)
    before = content["blueprint"]
    it.normalize(content, canon)
    assert content["blueprint"] == before                      # nothing rewritten
    findings, _ = it.verify(content)
    unknown = [f for f in findings if f.kind == it.UNKNOWN]
    assert unknown and "Delivery & Settlement Resolution Hub" in unknown[0].issue
    assert "the system" not in content["blueprint"]


# ── validation only ──────────────────────────────────────────────────────────


def test_verify_never_modifies_the_content():
    content = _content(blueprint="Phase 9 — Something: the Unregistered Widget Engine does work.\n",
                       technical="A customer opens the Pilot Review Queue via a link.\n")
    snapshot = json.dumps(content, sort_keys=True, default=str)
    findings, _ = it.verify(content)
    assert findings                                            # it has plenty to say
    assert json.dumps(content, sort_keys=True, default=str) == snapshot


def test_every_disagreement_is_a_typed_finding():
    mods = copy.deepcopy(MODULES)
    mods[2]["automation_level"], mods[2]["spec"]["ai"] = "rules", {"role": "classifies"}
    content = _content(mods, blueprint="Phase 9 — Late: the Delivery Exception AI Coordinator ships.\n",
                       technical="Customers confirm their address in the Pilot Review Queue.\n")
    findings, canon = it.verify(content)
    kinds = {f.kind for f in findings}
    assert it.MISCLASSIFIED in kinds and it.CONFLICT in kinds
    assert any("classified 'rules'" in f.issue for f in findings)
    assert any(f.kind == it.MISCLASSIFIED and "audience" in f.where for f in findings)
    assert all(f.severity == "high" for f in findings)


def test_a_phase_statement_is_checked_against_the_registry_not_rewritten():
    content = _content()
    canon = C.build(content)
    seq = next(e for e in canon.of_kind("module") if e.data.get("phase_number") == 2)
    line = f"- **Phase 7 — Later:** the {seq.canonical} ships.\n"
    content["blueprint"] = line
    findings, _ = it.verify(content)
    assert content["blueprint"] == line
    conflict = [f for f in findings if f.kind == it.CONFLICT and "phases" in f.where]
    assert conflict and conflict[0].expected == "Phase 2"


def test_a_phase_title_is_the_registrys_title_not_the_volumes_invention():
    """Run 53: the two volumes coined their own phase titles and disagreed.
    The law is not 'the volumes agree' — it is 'each volume states the
    registry's title', which is what the phase delivers."""
    canon = C.build(_content())
    phase2 = next(e for e in canon.of_kind("phase") if e.data.get("number") == 2)
    want = phase2.data["title"]
    coined = {"blueprint": f"- **Phase 2 — Enhanced Customer Interaction:** x\n",
              "technical": "- **Phase 2: Customer Self-Service:** y\n"}
    out = it.phase_title_findings(coined, canon)
    assert len(out) == 2 and {f.kind for f in out} == {it.CONFLICT}
    assert all(f.expected == want for f in out)
    # both volumes stating the registry's title is clean, and the mixed
    # heading (a numbered phase carrying the parallel workstream) still reads
    # as that phase's title
    assert it.phase_title_findings({"blueprint": f"Phase 2 — {want}: x",
                                    "technical": f"Phase 2 — {want}, with the parallel workstream Z: y"}, canon) == []
    # a phase the registry does not hold is a conflict, not a silent pass
    assert [f.kind for f in it.phase_title_findings({"blueprint": "Phase 9 — Human Handoffs: x"}, canon)] == [it.CONFLICT]


# ── root cause C: phases are the registry's, in the registry's order ─────────


def test_a_phase_is_titled_by_what_it_delivers_and_a_parallel_workstream_has_no_number():
    canon = C.build(_content())
    numbered = [e for e in canon.phases() if e.data.get("number") is not None]
    parallel = [e for e in canon.phases() if e.data.get("number") is None]
    assert [e.data["number"] for e in numbered] == sorted(e.data["number"] for e in numbered)
    assert canon.phases()[-1] in parallel or not parallel      # parallel comes last
    for e in numbered + parallel:
        # the title is the canonical names of the modules it delivers — never
        # a coined phrase, and never a fixed number of them
        assert e.data["title"] == C.phase_title(e.data["modules"])
        assert all(n in e.canonical for n in e.data["modules"])
    assert parallel and parallel[0].data["label"] == C.PARALLEL_LABEL


def test_the_build_order_never_gives_a_parallel_module_a_phase_number():
    """Run 53's origin: build_order listed the parallel module fourth, the
    blueprint read 'fourth' as 'Phase 4', and the real Phase 4 became a
    Phase 5 that does not exist."""
    content = _content()
    canon = C.build(content)
    parallel = next(e for e in canon.of_kind("module") if e.data.get("workstream") == "parallel")
    names = content["registry"]["build_order_names"]
    numbered = [e.canonical for e in canon.of_kind("module") if isinstance(e.data.get("phase_number"), int)]
    assert names[-1] == parallel.canonical                     # after every numbered module
    assert names[:len(numbered)] == canon.build_order()[:len(numbered)]
    assert sorted(names) == sorted(e.canonical for e in canon.of_kind("module"))


def test_a_phase_heading_is_rendered_from_the_registry_and_refuses_a_two_phase_section():
    from app.pipeline import blueprint as bp

    content = _content()
    canon = C.build(content)
    p2 = next(e for e in canon.of_kind("phase") if e.data.get("number") == 2)
    p3 = next(e for e in canon.of_kind("phase") if e.data.get("number") == 3)
    mod2, mod3 = p2.data["modules"][0], p3.data["modules"][0]
    par = next(e for e in canon.phases() if e.data.get("number") is None)

    # the heading's title is replaced by the registry's; the narrative is not
    doc = f"- **Phase 2 — Enhanced Customer Interaction:** The {mod2} will do things.\n"
    out, rendered, _refused = bp._pin_phase_headings(doc, canon)
    assert out == f"- **Phase 2 — {p2.data['title']}:** The {mod2} will do things.\n"
    assert len(rendered) == 1

    # a parallel module stated as a numbered phase is re-labelled, not renumbered
    par_mod = par.data["modules"][0]
    out, _, _ = bp._pin_phase_headings(f"- **Phase 4 — Automated Inquiry Resolution:** The {par_mod} runs alone.\n", canon)
    assert out.startswith(f"- **{C.PARALLEL_LABEL} — {par.data['title']}:**")

    # a numbered phase AND the parallel workstream in one section: run 53-r22
    # minted "Phase 4 — …, with the parallel workstream …", grouping a
    # workstream that has no number into the sequence. The registry now states
    # no heading, the renderer writes nothing, and the refusal is carried out.
    doc = f"*   **Phase 3: Coined**\n    *   **Delivers:** {mod3}, {par_mod}\n"
    out, rendered, refused = bp._pin_phase_headings(doc, canon)
    assert out == doc and rendered == []
    assert len(refused) == 1 and C.PARALLEL_LABEL.lower() in refused[0]["reason"]
    assert "with the parallel workstream" not in out
    assert canon.heading_for([mod3, par_mod])[0] is None

    # two NUMBERED phases in one section: refused the same way
    doc = f"*   **Phase 2: Coined**\n    *   **Delivers:** {mod2}, {mod3}\n"
    out, rendered, refused = bp._pin_phase_headings(doc, canon)
    assert out == doc and rendered == [] and len(refused) == 1
    assert canon.heading_for([mod2, mod3])[0] is None

    # rendering twice changes nothing
    once, _, _ = bp._pin_phase_headings(f"- **Phase 2 — Coined:** The {mod2} acts.\n", canon)
    twice, again, _ = bp._pin_phase_headings(once, canon)
    assert twice == once and again == []


def test_enforce_renders_the_phase_heading_into_a_volume_that_already_exists(client):
    """A package is corrected without regenerating a word of it: the heading
    slot is re-rendered from the registry, the narrative is left alone."""
    mods = copy.deepcopy(MODULES)
    bc = {"build_order": [m["id"] for m in mods], "pilot_gate": copy.deepcopy(GATE)}
    reg = rg.build_registry(OPS, bc, mods)
    canon = C.build({"modules": mods, "registry": reg})
    p2 = next(e for e in canon.of_kind("phase") if e.data.get("number") == 2)
    mod2 = p2.data["modules"][0]
    narrative = f"The {mod2} will interpret responses and route them."
    db = SessionLocal()
    row = _seed(db, mvp_blueprint=f"## The decision\n- **Phase 2 — Coined Title:** {narrative}\n",
                technical_plan="## How your system works\nfine\n",
                business_case_json=json.dumps(bc), modules_json=json.dumps(mods), registry_json=json.dumps(reg),
                ops_numbers_json=OPS, procedures_json=json.dumps({"procedures": []}),
                qa_report_json=json.dumps({"checks": [], "findings": []}), integrity_stamp=False)
    report = it.enforce(db, row.id)
    db.refresh(row)
    assert f"- **Phase 2 — {p2.data['title']}:** {narrative}" in row.mvp_blueprint
    assert "Coined Title" not in row.mvp_blueprint
    assert any(m.get("entity") == "phase" for m in report["mappings_applied"])
    # the report is bound to the content it was computed on, after rendering
    assert report["content_hash"] == it.content_hash(it.load(row))
    # and running it again renders nothing new
    again = it.enforce(db, row.id)
    assert not [m for m in again["mappings_applied"] if m.get("entity") == "phase"]
    db.close()


# ── root cause A: audience — who is sent where ──────────────────────────────


def test_a_customer_facing_position_names_the_customer_interface_and_staff_keep_the_queue():
    content = _content()
    canon = C.build(content)
    internal, customer = canon.channel_mapping("the pilot")
    assert internal.data["audience"] == C.INTERNAL and customer.data["audience"] == C.CUSTOMER

    text = (f"Sends a WhatsApp message asking customers to confirm their location via a link to the {internal.canonical}. "
            f"Flags high-risk orders for human intervention via the {internal.canonical}.")
    fixed, recs = rg.channel_pass(text, internal.canonical, customer.canonical)
    assert fixed.count(customer.canonical) == 1 and fixed.count(internal.canonical) == 1
    assert fixed.endswith(f"human intervention via the {internal.canonical}.")
    assert len(recs) == 1
    # applying it again changes nothing
    assert rg.channel_pass(fixed, internal.canonical, customer.canonical) == (fixed, [])


def test_an_integration_entry_is_corrected_as_one_unit_because_its_name_field_is_bare():
    content = _content()
    canon = C.build(content)
    internal, customer = canon.channel_mapping("the pilot")
    pilot = next(m for m in content["modules"] if m.get("pilot"))
    pilot.setdefault("tech", {})["integration_details"] = [
        {"system": internal.canonical, "direction": "out",
         "detail": "Unique URL with delivery id token for the customer to access the interface."},
        {"system": internal.canonical, "direction": "in", "detail": "Staff review the queued responses."}]
    applied = it.retype(content, canon)
    systems = [e["system"] for e in pilot["tech"]["integration_details"]]
    assert systems == [customer.canonical, internal.canonical]
    assert any(a.get("entity") == customer.id for a in applied)


def test_a_named_system_is_not_internal_by_assumption():
    """Run 53 held 'iCARRY Client Portal' as internal and then reported every
    sentence in which a client opened it."""
    content = _content()
    pilot = next(m for m in content["modules"] if m.get("pilot"))
    pilot.setdefault("tech", {})["integrations"] = [{"system": "iCARRY Client Portal"},
                                                   {"system": "Dispatch Router Service"}]
    canon = C.build(content)
    assert canon.resolve("iCARRY Client Portal").entity.data["audience"] == C.CUSTOMER
    assert canon.resolve("Dispatch Router Service").entity.data["audience"] != C.CUSTOMER


def test_the_audience_mapping_fails_closed_when_the_registry_holds_more_than_one():
    content = _content()
    canon = C.build(content)
    internal, customer = canon.channel_mapping("the pilot")
    crowded = C.Canon(list(canon._entities.values()) + [
        C.Entity(id="interface:second-form", kind="interface", canonical="Second Pilot Form",
                 data={"interface_kind": "form", "owner": "the pilot", "audience": C.CUSTOMER})])
    assert crowded.channel_mapping("the pilot") is None


def test_a_customer_is_not_sent_to_a_transport_api_or_a_warehouse():
    """The law fires only where the registry holds a customer-facing
    counterpart — the same scope the corrector has. A WhatsApp API or a data
    warehouse named beside the word 'customer' sends nobody anywhere."""
    content = _content()
    pilot = next(m for m in content["modules"] if m.get("pilot"))
    pilot.setdefault("tech", {})["integrations"] = [{"system": "WhatsApp Business API"},
                                                   {"system": "Historical Delivery Data Warehouse"}]
    canon = C.build(content)
    internal, customer = canon.channel_mapping("the pilot")
    assert canon.resolve("WhatsApp Business API").entity.data["audience"] == C.INTERNAL
    assert it.audience_findings("The customer receives a message via WhatsApp Business API.", canon, "technical") == []
    assert it.audience_findings("Customer records are held in the Historical Delivery Data Warehouse.",
                                canon, "technical") == []
    # the pilot's queue DOES have a counterpart, so a customer sent there is reported
    out = it.audience_findings(f"The customer opens a link to the {internal.canonical}.", canon, "technical")
    assert len(out) == 1 and out[0].kind == it.MISCLASSIFIED and out[0].entities == (internal.id,)


def test_the_build_team_block_is_exempt_even_when_the_page_hard_wraps_it():
    """On the rendered page the sanctioned block runs over several physical
    lines. The line-anchored exemption cleared only the first, so the tool
    names on the continuation lines read as internal identifiers loose in
    client-facing prose — an artifact that blocked a release and was not real."""
    from app.pipeline.export_pdf import find_artifacts

    reg = rg.build_registry(OPS, {"build_order": [m["id"] for m in copy.deepcopy(MODULES)],
                                  "pilot_gate": copy.deepcopy(GATE)}, copy.deepcopy(MODULES))
    mid = MODULES[0]["id"]                      # a hyphenated internal module id
    wrapped = ("• For your build team: `DeliveryPreConfirmation` (delivery id, confirmation status),\n"
               f"`CustomerHistoricalDeliveryPattern` (customer id); Modules: {mid},\n"
               "`validate_location_pin`; APIs: `/api/v1/pre_dispatch_confirmations`.\n"
               "• What this part does: it confirms delivery details before dispatch.\n")
    assert "internal identifier in client-facing text" not in find_artifacts(wrapped, reg)
    # the same identifier OUTSIDE the block is still caught
    loose = wrapped + f"\nYour team opens {mid} from the client dashboard.\n"
    assert "internal identifier in client-facing text" in find_artifacts(loose, reg)


def test_a_two_word_verb_phrase_is_not_reported_as_a_coined_system_name():
    """'Approve Pilot', 'Reviewing Pilot', 'If System' come out of headings and
    ordinary sentences. Blocking a release on a name nobody can register
    empties the gate; a real coined name is longer and still reported."""
    canon = C.build(_content())
    for noise in ("Approve Pilot and record the decision.", "If System availability drops, escalate.",
                  "Reviewing Pilot performance weekly.", "Update the Pilot Log."):
        assert [f for f in it.name_findings(noise, canon, "operations") if f.kind == it.UNKNOWN] == []
    real = it.name_findings("We propose a smart Delivery & Settlement Resolution Hub.", canon, "blueprint")
    assert [f.kind for f in real] == [it.UNKNOWN]
    assert real[0].statement == "Delivery & Settlement Resolution Hub"


# ── the owner's audit of the exact 53-r22 PDFs ──────────────────────────────
# Eight defects reached client pages with a clean integrity report. Each test
# below uses the failing string from those pages, with the negative control
# that must NOT trip.


def test_a_pilot_procedure_may_not_act_on_a_population_the_gate_excludes():
    content = _content()
    gate = content["registry"]["pilot_gate"]
    gate["population"] = "All delivery orders placed for individuals via the app, excluding business client orders"
    content["modules"][3]["users"] = ["business client", "finance team"]
    content["procedures"] = {"procedures": [{
        "name": "Resolving COD Settlement Inquiries", "module": "The pilot", "phase": "pilot",
        "trigger": "Upon receiving a COD settlement inquiry from a business client via WhatsApp or email",
        "steps": [{"actor": "iCARRY Support Staff", "step": "Identify the business client and extract identifiers."}]}]}
    canon = C.build(content)
    assert canon.get("gate:PG-01").data["population_excludes"] == ["business client"]
    out = it.pilot_population_findings(content, canon)
    assert len(out) == 1 and out[0].kind == it.CONFLICT
    assert "business client" in out[0].issue and "trigger" in out[0].issue

    # a clause that EXCLUDES the population states the boundary correctly
    content["procedures"]["procedures"][0]["trigger"] = "Any pilot order, excluding business client orders"
    content["procedures"]["procedures"][0]["steps"] = [
        {"actor": "iCARRY Support Staff", "step": "Skip business client orders."}]
    assert it.pilot_population_findings(content, C.build(content)) == []

    # a gate whose exclusion names nothing the registry declares blocks on itself
    gate["population"] = "All orders, excluding wholesale partner accounts"
    unresolved = it.pilot_population_findings(content, C.build(content))
    assert any("no registry entity declares" in f.issue for f in unresolved)


def test_a_procedure_names_only_the_tools_of_the_module_it_belongs_to():
    content = _content()
    mods = content["modules"]
    mods[1].setdefault("tech", {})["integrations"] = [{"system": "Customer Confirmation Status Log"}]
    mods[2].setdefault("tech", {})["integrations"] = [{"system": "iCARRY Financial Settlement Database"}]
    canon = C.build(content)
    owner1 = mods[1]["client_facing_name"]
    owner2 = mods[2]["client_facing_name"]
    content["procedures"] = {"procedures": [{
        "name": "Handling Business Client COD Settlement Inquiries", "module": owner2, "phase": "future",
        "steps": [{"actor": "iCARRY Support Staff",
                   "step": "Monitors the Customer Confirmation Status Log for 'unresolvable' COD inquiries."}]}]}
    out = it.procedure_tool_fit_findings(content, canon)
    assert len(out) == 1 and owner1 in out[0].issue and "Customer Confirmation Status Log" in out[0].issue

    # its own module's tool is fine
    content["procedures"]["procedures"][0]["steps"][0]["step"] = "Reads the iCARRY Financial Settlement Database."
    assert it.procedure_tool_fit_findings(content, canon) == []

    # a tool SEVERAL modules declare belongs to none of them in particular —
    # whichever module the procedure is filed under
    mods[1]["tech"]["integrations"].append({"system": "Shared Ledger Service"})
    mods[2]["tech"]["integrations"].append({"system": "Shared Ledger Service"})
    shared = C.build(content)
    content["procedures"]["procedures"][0]["steps"][0]["step"] = "Reads the Shared Ledger Service."
    for filed in (owner1, owner2):
        content["procedures"]["procedures"][0]["module"] = filed
        assert it.procedure_tool_fit_findings(content, shared) == [], filed


def test_staff_are_not_sent_to_the_customer_facing_interface():
    """The exact 53-r22 sentence. A customer clause joined by ', and' to a
    staff clause was ONE clause, so the staff half was handed the customer
    form."""
    content = _content()
    canon = C.build(content)
    internal, customer = canon.channel_mapping("the pilot")
    shipped = ("You'll be able to send WhatsApp messages to customers asking them to confirm details via a "
               f"secure link, and your team will use the {customer.canonical} to monitor responses and "
               "intervene for risky orders.")
    fixed, recs = rg.channel_pass(shipped, internal.canonical, customer.canonical)
    assert f"your team will use the {internal.canonical} to monitor responses" in fixed
    assert "to customers asking them to confirm details via a secure link" in fixed
    assert [r["actor"] for r in recs] == ["staff"]
    assert rg.channel_pass(fixed, internal.canonical, customer.canonical) == (fixed, [])
    # and every detector reports the same sentence the corrector would fix,
    # and is satisfied by what the corrector writes. A detector its own
    # corrector cannot satisfy blocks a release forever — 53-r23 was held on
    # exactly this sentence AFTER it had been fixed.
    assert [f.kind for f in it.audience_findings(shipped, canon, "technical")] == [it.MISCLASSIFIED]
    assert it.audience_findings(fixed, canon, "technical") == []
    assert rg.customer_queue_findings(shipped, "technical", internal.canonical, customer.canonical) == []
    assert rg.customer_queue_findings(fixed, "technical", internal.canonical, customer.canonical) == []
    sent_in = f"The customer opens a link to the {internal.canonical} to confirm."
    assert rg.customer_queue_findings(sent_in, "technical", internal.canonical, customer.canonical)


def test_the_pilot_description_may_not_narrow_participation_after_any_governor():
    """53-r22: '… on WhatsApp before their same-day and express deliveries go
    out.' No law saw it, because the governor list held only the slots the
    RENDERER can safely write into."""
    content = _content()
    kinds = rg.service_types(content["free_texts"])
    gate = content["registry"]["pilot_gate"]
    shipped = ("This is a test program to reach out to individual customers on WhatsApp before their "
               "same-day and express deliveries go out.")
    assert rg.population_findings(shipped, gate, "technical", kinds, ["the pilot"], pilot_scope=False)
    # the renderer refuses this slot: a 20-word population would strand "go out"
    from app.pipeline import authority as au

    out, recs = au.population_render(shipped, gate, kinds, ["the pilot"], pilot_scope=False)
    assert out == shipped and recs == []
    # the renderer's governors are a strict subset of the detector's: what it
    # can DETECT is wider than what it may WRITE, and "before" is on the wrong
    # side of that line in both guards
    assert au._PREPOSITION.match("before their deliveries go out") is None
    assert rg._POP_QUALIFIER_RENDER.search(shipped) is None
    assert rg._POP_QUALIFIER.search(shipped) is not None
    # the slot it CAN write ends its clause
    safe = "The pilot sends a message for their same-day and express on-demand deliveries."
    assert au.population_render(safe, gate, kinds, ["the pilot"])[1]


def test_a_canonical_name_states_each_of_its_tokens_once():
    """The four names 53-r22 shipped, and the ordinary English that must not
    be mistaken for them."""
    content = _content()
    canon = C.build(content)
    tokens = canon.name_tokens() | {"Client", "Support", "Proactive", "iCARRY"}
    for bad in ("Client Client Portal Settlement Inquiry Form",
                "Client iCARRY Client Portal Settlement Status Display",
                "Support iCARRY Support Staff Resolution Feedback Loop",
                "Sending Proactive COD Proactive Payment Timeline Reminders"):
        assert C.repeated_run(bad, tokens), bad
    for ok in ("DAY TO DAY", "The opportunity\n\nThe plan is simple",
               "AI Delivery Pre-Confirmation Engine, Delivery & Settlement Support Escalation",
               "POST /api/v1/escalations/delivery, POST /api/v1/escalations/queue"):
        assert C.repeated_run(ok, tokens) is None, ok
    # the collapse is determinate, and says which test chose it
    fixed, why = C.collapse_repeat("Client iCARRY Client Portal Settlement Status Display",
                                   ["iCARRY Client Portal"], "", tokens)
    assert fixed == "iCARRY Client Portal Settlement Status Display" and "registered name" in why
    fixed, why = C.collapse_repeat("Client Client Portal Settlement Inquiry Form", [], "", tokens)
    assert fixed == "Client Portal Settlement Inquiry Form" and "agree" in why
    # neither collapse determined: the registry states nothing and it blocks
    assert C.collapse_repeat("Alpha Beta Alpha Gamma", [], "", {"Alpha", "Beta", "Gamma"})[0] is None


def test_a_mapping_never_creates_a_repeated_token_run():
    """Once the corrupt name was canonical, dropping an inner word derived the
    CLEAN name as one of its own surfaces — so every clean mention mapped into
    the corruption."""
    content = _content()
    content["modules"][2].setdefault("spec", {})["features"] = [
        {"name": "Client Client Portal Settlement Inquiry Form"}]
    canon = C.build(content)
    clean = "Client Portal Settlement Inquiry Form"
    assert canon.resolve(clean).unique                      # the corrupt name claims the clean one
    out, _ = canon.apply_exact_mappings(clean)
    assert out == clean, "the mapping must not expand a clean name into a corrupt one"


def test_an_attribution_is_stated_once():
    """53-r22: 'remitting within 10 days after month-end (your stated cycle)
    (your stated cycle)'. The policy's surface form is its core without the
    attribution, so mapping it onto an already-attributed statement appends a
    second one."""
    assert C.collapse_attribution("within 10 days after month-end (your stated cycle) (your stated cycle).") \
        == "within 10 days after month-end (your stated cycle)."
    once = "within 10 days after month-end (your stated cycle)."
    assert C.collapse_attribution(once) == once
    assert C.collapse_attribution("(a) then (b)") == "(a) then (b)"
    # prevention: the mapping does not append to a statement that already says it
    policy = C.Entity(id="policy:settlement-period", kind="policy",
                      canonical="10 days after month-end (your stated cycle)",
                      surfaces=("10 days after month-end",),
                      data={"core": "10 days after month-end", "attribution": "(your stated cycle)"})
    canon = C.Canon([policy])
    already = "Remitting within 10 days after month-end (your stated cycle) is the rule."
    assert canon.apply_exact_mappings(already)[0] == already
    # and where the attribution sits elsewhere in the statement, so the
    # canonical form does not match at the offset and only the guard stops it
    apart = "Your stated cycle (your stated cycle) means remitting within 10 days after month-end."
    assert canon.apply_exact_mappings(apart)[0] == apart
    assert apart.count("(your stated cycle)") == 1
    bare = "Remitting within 10 days after month-end is the rule."
    assert canon.apply_exact_mappings(bare)[0] == \
        "Remitting within 10 days after month-end (your stated cycle) is the rule."


# ── authority precedence: which source wins a disagreement ──────────────────


def test_the_precedence_names_one_owning_source_for_each_contested_fact():
    from app.pipeline import authority as au

    assert au.PRECEDENCE == {"pilot population": "pilot gate",
                             "procedure steps": "canonical SOP",
                             "outreach attempt count": "canonical SOP",
                             "entity name": "canonical registry",
                             "module ownership": "canonical registry"}


def test_the_gate_owns_the_pilot_population():
    from app.pipeline import authority as au

    content = _content()
    content["registry"]["service_types"] = rg.service_types(content["free_texts"])
    gate, kinds = content["registry"]["pilot_gate"], content["registry"]["service_types"]
    pop = gate["population"]

    s = "The pilot sends a WhatsApp message before dispatch for their same-day and express on-demand deliveries."
    out, recs = au.population_render(s, gate, kinds, ["the pilot"])
    assert out == f"The pilot sends a WhatsApp message before dispatch for {pop[0].lower() + pop[1:]}."
    assert recs and recs[0]["authority"] == "pilot gate"
    assert rg.population_findings(out, gate, "t", kinds) == []
    # the geography the gate's own population carries is not stated twice
    s2 = "Pilot messages are sent for all same-day and express on-demand deliveries in the pilot region."
    out2, _ = au.population_render(s2, gate, kinds, ["the pilot"])
    assert out2.count("region") == 0 and out2.endswith(".") and out2.count(pop[0].lower() + pop[1:]) == 1
    # a sentence that is not about the pilot is left alone, and the pass is idempotent
    later = "The engine validates windows for same-day and express on-demand deliveries."
    assert au.population_render(later, gate, kinds, ["the pilot"]) == (later, [])
    assert au.population_render(out, gate, kinds, ["the pilot"]) == (out, [])


def test_legacy_vague_wording_is_rendered_from_the_gate_where_it_scopes_the_pilot():
    """'eligible deliveries' is what the deleted population_pass left behind:
    not narrower than the gate, so the population law never reported it, and
    saying nothing at all."""
    from app.pipeline import authority as au

    content = _content()
    gate = content["registry"]["pilot_gate"]
    s = "The pilot confirms details before dispatch for their eligible deliveries."
    out, recs = au.population_render(s, gate, [], ["the pilot"])
    assert "eligible" not in out and gate["population"][1:] in out and recs
    assert "eligible" in au.LEGACY_VAGUE


def test_the_canonical_sop_is_the_only_executable_pilot_procedure_set():
    from app.pipeline import authority as au

    sop = [{"name": "Preparing orders", "module": "The pilot", "phase": "pilot", "steps": []},
           {"name": "Outreach", "module": "The pilot", "phase": "pilot", "steps": []}]
    dup = [{"name": "Managing confirmations", "module": "Pilot Module", "phase": "pilot", "steps": []}]
    future = [{"name": "Later", "module": "Pilot Module", "phase": "future", "steps": []}]
    kept, recs = au.dedupe_pilot_procedures(sop + dup + future, {"Pilot Module"})
    assert [p["name"] for p in kept] == ["Preparing orders", "Outreach", "Later"]
    assert len(recs) == 1 and recs[0]["authority"] == "canonical SOP"
    # with no SOP set there is nothing authoritative to keep, so nothing is dropped
    assert au.dedupe_pilot_procedures(dup + future, {"Pilot Module"}) == (dup + future, [])


def test_the_sop_owns_the_outreach_attempt_count():
    from app.pipeline import authority as au

    s = "The pilot sends one reminder if no response is received."
    out, recs = au.attempt_render(s, 3, ["the pilot"])
    assert out == "The pilot sends two reminders if no response is received." and recs
    assert rg._attempt_totals(out) == {3}
    # the sentence's own form is kept: digits stay digits
    assert au.attempt_render("The pilot sends 1 reminder.", 3, ["the pilot"])[0] == "The pilot sends 2 reminders."
    # already canonical, and sentences that are not the pilot's, are untouched
    assert au.attempt_render(out, 3, ["the pilot"]) == (out, [])
    assert au.attempt_render("Finance sends one reminder about invoices.", 3, ["the pilot"])[0] \
        == "Finance sends one reminder about invoices."


def test_a_coined_name_resolves_to_its_module_or_to_the_registrys_own_names():
    from app.pipeline import authority as au

    content = _content()
    canon = C.build(content)
    roster = C.phase_title(canon.build_order())
    names = [e.canonical for e in canon.of_kind("module")]
    one = canon.build_order()[-1]                    # deliberately NOT first in the roster
    others = [n for n in names if n != one]

    # its own sentence names exactly one module: that module is responsible,
    # and no other module's name is dragged in with it
    s = f"The {one} feeds a smart Delivery & Settlement Resolution Hub for the client."
    out, recs = au.coined_name_render(s, canon)
    assert "Delivery & Settlement Resolution Hub" not in out and f"the {one}" in out
    assert all(n not in out for n in others)
    assert recs[0]["authority"] == "canonical registry"
    assert recs[0]["resolved_by"] == "the one module its sentence names"

    # no single module: the registry's own names, and the determiner and its
    # adjectives go with the coined name so the sentence stays grammatical
    s = "This proposes a phased implementation of a smart Delivery & Settlement Resolution Hub, beginning now."
    out, recs = au.coined_name_render(s, canon)
    assert out == f"This proposes a phased implementation of the {roster}, beginning now."
    assert "invent" not in out and recs

    # a REGISTERED name that is just as name-shaped is never touched, and no
    # entity is invented for the coined one
    registered = next(n for n in names if len(n.split()) >= 3 and n.split()[-1] in
                      ("Pilot", "Engine", "Coordinator", "Workbench", "Hub", "Platform", "System", "Interface"))
    known = f"The {registered} handles it."
    assert au.coined_name_render(known, canon) == (known, [])
    assert C.build(content).resolve("Delivery & Settlement Resolution Hub").status == "unknown"


def test_enforce_applies_the_authority_precedence_end_to_end(client):
    """The precedence is not advisory: enforce renders the owning source's
    value into the structures and the volumes, and records whose authority
    it used."""
    mods = copy.deepcopy(MODULES)
    bc = {"build_order": [m["id"] for m in mods], "pilot_gate": copy.deepcopy(GATE)}
    reg = rg.build_registry(OPS, bc, mods, ["We deliver same-day and express on-demand deliveries."])
    canon = C.build({"modules": mods, "registry": reg})
    pilot = next(e for e in canon.of_kind("module") if e.data.get("pilot")).canonical
    pop = reg["pilot_gate"]["population"]
    procedures = {"procedures": [
        {"name": "Outreach", "module": "The pilot", "phase": "pilot",
         "steps": [{"actor": "Pilot Support Operator", "step": "The pilot sends two reminders if no response."}]},
        {"name": "Managing confirmations", "module": pilot, "phase": "pilot",
         "steps": [{"actor": "Pilot Support Operator", "step": "The pilot sends one reminder if no response."}]}]}
    db = SessionLocal()
    row = _seed(db, mvp_blueprint=("## The decision\nThe pilot confirms details before dispatch for their "
                                   "same-day and express on-demand deliveries.\n"),
                technical_plan="## How your system works\nfine\n",
                business_case_json=json.dumps(bc), modules_json=json.dumps(mods), registry_json=json.dumps(reg),
                ops_numbers_json=OPS, procedures_json=json.dumps(procedures),
                qa_report_json=json.dumps({"checks": [], "findings": []}), integrity_stamp=False)
    report = it.enforce(db, row.id)
    db.refresh(row)
    # the SOP is the only pilot set left, and the gate's population is on the page
    assert [p["name"] for p in json.loads(row.procedures_json)["procedures"]] == ["Outreach"]
    assert pop[1:] in row.mvp_blueprint and "same-day and express" not in row.mvp_blueprint
    laws = " | ".join(m.get("law", "") for m in report["mappings_applied"])
    assert "pilot gate owns the pilot population" in laws
    assert "canonical SOP owns the pilot's procedure steps" in laws
    # and it settles: a second pass finds nothing left to render
    assert it.enforce(db, row.id)["mappings_applied"] == []
    db.close()


# ── root cause D: a procedure is filed under the module that executes it ────


def test_a_procedure_is_refiled_only_when_the_module_it_names_plays_no_part_in_it():
    content = _content()
    canon = C.build(content)
    mods = {e.canonical for e in canon.of_kind("module")}
    coordinator = next(e.canonical for e in canon.of_kind("module")
                       if e.data.get("phase_number") == 2)
    workbench = next(e.canonical for e in canon.of_kind("module") if e.data.get("phase_number") == 3)

    # filed under a module that appears nowhere in it: re-filed
    misfiled = {"name": "Settling inquiries", "module": workbench, "phase": "future",
                "steps": [{"actor": coordinator, "step": "a"}, {"actor": coordinator, "step": "b"},
                          {"actor": coordinator, "step": "c"}]}
    assert it.misfiled_owner(misfiled, mods) == (coordinator, 3)

    # an ESCALATION procedure: another module triggers it, humans carry it out,
    # and the module it is filed under is named in it — never re-filed
    escalation = {"name": "Handling escalations", "module": workbench, "phase": "future",
                  "trigger": f"The {workbench} receives an unresolved case",
                  "steps": [{"actor": coordinator, "step": "a"}, {"actor": coordinator, "step": "b"},
                            {"actor": coordinator, "step": "c"},
                            {"actor": "iCARRY Support Staff", "step": "d"},
                            {"actor": "iCARRY Support Staff", "step": "e"}]}
    assert it.misfiled_owner(escalation, mods) == (None, 0)

    # a tie determines nothing
    tied = dict(misfiled, steps=[{"actor": coordinator, "step": "a"}] * 3 + [{"actor": "Third Module", "step": "b"}] * 3)
    assert it.misfiled_owner(dict(tied, module=workbench), mods | {"Third Module"}) == (None, 0)

    content["procedures"] = {"procedures": [copy.deepcopy(misfiled), copy.deepcopy(escalation)]}
    applied = it.retype(content, canon)
    filed = [p["module"] for p in content["procedures"]["procedures"]]
    assert filed == [coordinator, workbench]
    assert any(a["canonical"] == coordinator for a in applied)


# ── root cause B and the leftovers: conflicting content fails closed ────────


def test_a_narrowed_pilot_population_is_reported_and_never_reworded():
    """r19 replaced the narrowing words with 'eligible' and produced
    '[eligible] deliveries'. The layer reports and leaves the text alone."""
    content = _content()
    content["registry"]["service_types"] = rg.service_types(content["free_texts"])
    gate = content["registry"]["pilot_gate"]
    text = "Messages are sent for all same-day and express on-demand deliveries in the pilot region."
    content["blueprint"] = text
    before = content["blueprint"]
    findings, _ = it.verify(content)
    pop = [f for f in findings if "population" in f.where]
    assert pop and pop[0].kind == it.CONFLICT
    assert pop[0].expected == gate["population"]
    assert content["blueprint"] == before           # nothing was modified
    assert "eligible" not in content["blueprint"]


def test_an_unknown_system_name_is_reported_never_registered_and_never_replaced():
    content = _content()
    content["blueprint"] = "This blueprint proposes a smart Delivery & Settlement Resolution Hub for the client."
    canon = C.build(content)
    assert canon.resolve("Delivery & Settlement Resolution Hub").status == "unknown"
    findings, _ = it.verify(content)
    unknown = [f for f in findings if f.kind == it.UNKNOWN]
    assert unknown and "Delivery & Settlement Resolution Hub" in unknown[0].statement
    # the name is neither invented into the registry nor swapped for another
    assert C.build(content).resolve("Delivery & Settlement Resolution Hub").status == "unknown"
    mapped, _ = canon.apply_exact_mappings(content["blueprint"])
    assert mapped == content["blueprint"]


# ── the gate ─────────────────────────────────────────────────────────────────


def test_the_report_is_bound_to_the_content_and_the_gate_refuses_final_without_it(client):
    from app.pipeline import export_pdf as ep

    mods = copy.deepcopy(MODULES)
    bc = {"build_order": [m["id"] for m in mods], "pilot_gate": copy.deepcopy(GATE)}
    reg = rg.build_registry(OPS, bc, mods)
    db = SessionLocal()
    row = _seed(db, mvp_blueprint="## The decision\nA plan.\n", technical_plan="## How your system works\nfine\n",
                business_case_json=json.dumps(bc), modules_json=json.dumps(mods), registry_json=json.dumps(reg),
                ops_numbers_json=OPS, procedures_json=json.dumps({"procedures": []}),
                qa_report_json=json.dumps({"checks": [], "findings": []}), integrity_stamp=False)
    assert "integrity layer has not run" in " ".join(ep.release_status(row)["reasons"])
    report = it.enforce(db, row.id)
    db.refresh(row)
    assert report["version"] == it.VERSION and report["content_hash"] == it.content_hash(it.load(row))
    assert it.current_report(row) is not None
    if report["blocked"]:
        assert any("integrity layer:" in r for r in ep.release_status(row)["reasons"])
    else:
        assert not any("integrity layer" in r for r in ep.release_status(row)["reasons"])
    # any later edit invalidates the report
    row.mvp_blueprint += "\nA new sentence."
    assert it.current_report(row) is None
    assert "integrity layer has not run" in " ".join(ep.release_status(row)["reasons"])
    db.close()


def test_the_release_record_carries_the_hash_bound_report(client, tmp_path, monkeypatch):
    import release_audit as ra
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    mods = copy.deepcopy(MODULES)
    bc = {"build_order": [m["id"] for m in mods], "pilot_gate": copy.deepcopy(GATE)}
    reg = rg.build_registry(OPS, bc, mods)
    db = SessionLocal()
    row = _seed(db, mvp_blueprint="## The decision\nA plan.\n\n## Executive summary\nfine\n",
                technical_plan="## How your system works\nfine\n", business_case_json=json.dumps(bc),
                modules_json=json.dumps(mods), registry_json=json.dumps(reg), ops_numbers_json=OPS,
                procedures_json=json.dumps({"procedures": []}),
                qa_report_json=json.dumps({"checks": [], "findings": []}), integrity_stamp=False)
    it.enforce(db, row.id)
    db.refresh(row)
    record = ra.audit_run(row)
    assert record["integrity"]["status"] == "current"
    assert record["integrity"]["content_hash"] == it.content_hash(it.load(row))
    assert record["integrity"]["canon"]["entities"] > 0
    # a record that claims FINAL while the report is stale does not validate
    lie = copy.deepcopy(record)
    lie["status"], lie["reasons"] = "final", []
    lie["integrity"] = {"status": "stale"}
    assert any("current integrity report" in e for e in ra.validate_record(lie))
    lie["integrity"] = {"status": "current", "blocked": True, "findings": [{"kind": "conflict"}]}
    assert any("open integrity finding" in e for e in ra.validate_record(lie))
    db.close()
