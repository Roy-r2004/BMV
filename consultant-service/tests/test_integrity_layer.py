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


def test_cross_volume_phase_titles_must_agree():
    out = it.phase_title_findings({"blueprint": "- **Phase 2 — Enhanced Customer Interaction:** x\n",
                                   "technical": "- **Phase 2: Customer Self-Service:** y\n"})
    assert len(out) == 1 and out[0].kind == it.CONFLICT and "Phase 2" in out[0].statement
    assert it.phase_title_findings({"blueprint": "Phase 2 — Same Title: x", "technical": "Phase 2 — Same Title: y"}) == []


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
