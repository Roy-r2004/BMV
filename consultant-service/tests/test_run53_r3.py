"""53-r3: a deadline is not a cadence; three release states; record lineage."""
import copy
import json
import os

from app.database import SessionLocal
from app.models import Request
from app.pipeline import registry as rg
from tests.test_registry_controls import OPS, _finding, _seed, _skeleton, client  # noqa: F401 — the fixture

DEADLINE_Q = [{"question": "Days after month-end to fully settle COD with a client?", "answer": "10 days"},
              {"question": "Staff hours per week reconciling COD and preparing statements?",
               "answer": "About 45 hours across our finance team"}]
INVENTED = ("Monitor the Financial Settlement Database every 10 days (your stated cycle) for COD collections eligible "
            "for proactive remittance reminders.")
CANON = ("Monitor settlement status according to the client-approved finance routine. "
         "Settlement must be completed within 10 days after month-end.")


def test_a_client_deadline_is_never_reused_as_a_monitoring_cadence():
    claims = rg.client_fact_claims(DEADLINE_Q, [])
    assert rg.deadline_days(claims) == {10: "after month-end"} and rg.cadence_days(claims) == set()
    found = rg.cadence_findings({"ops": INVENTED}, claims)
    assert found and "monitoring frequency the client never supplied" in found[0]["issue"]
    assert any("monitoring frequency" in f["issue"] for f in rg.policy_findings({"ops": INVENTED}, claims))
    fixed, notes = rg.policy_pass(INVENTED, claims)
    assert fixed == CANON and any("deadline reused as a cadence" in n for n in notes)
    assert rg.policy_findings({"ops": fixed}, claims) == [] and rg.policy_pass(fixed, claims)[0] == fixed
    # a step that keeps its other sentences loses only the invented one
    two = "Open the log. " + INVENTED + " Note exceptions."
    assert rg.policy_pass(two, claims)[0] == "Open the log. " + CANON + " Note exceptions."
    # the client separately supplied that cadence -> legitimate
    with_cadence = rg.client_fact_claims(DEADLINE_Q + [{"question": "How often does finance review settlement status?",
                                                         "answer": "every 10 days"}], [])
    assert rg.cadence_findings({"ops": INVENTED}, with_cadence) == [] and rg.policy_pass(INVENTED, with_cadence)[0] == INVENTED
    # a cadence on a number that is not the deadline is not this rule's business
    other = "Review the dashboard every 7 days."
    assert rg.cadence_findings({"ops": other}, claims) == [] and rg.policy_pass(other, claims)[0] == other


def test_release_states_and_the_bmv_statement():
    from app.pipeline import export_pdf as ep

    from tests._integrity_stub import stamp_clean

    row = Request(id=9401, business_name="x", status="done", is_failed=False, mvp_blueprint="doc", technical_plan="doc",
                  qa_report_json=json.dumps({"checks": [], "findings": []}))
    stamp_clean(row)
    assert ep.release_status(row)["status"] == "final"
    cover = " ".join(getattr(f, "text", "") for f in ep._cover("blueprint", "The Blueprint", "Volume I", row))
    assert "FINAL — CONSULTANCY DELIVERABLE" in cover and ep.BMV_STATEMENT in cover and "DRAFT" not in cover
    control = " ".join(getattr(f, "text", "") for f in ep._doc_control_flowables(row))
    assert "FINAL — CONSULTANCY DELIVERABLE" in control and ep.BMV_STATEMENT in control
    assert "Not yet assigned — set by the client at approval" in control and "required before FINAL" not in control
    row.document_owner, row.document_approver = "Operations Manager (client)", "Head of Operations (client)"
    control2 = " ".join(getattr(f, "text", "") for f in ep._doc_control_flowables(row))
    assert "CLIENT APPROVED" in control2 and ep.BMV_STATEMENT not in control2 and "Operations Manager (client)" in control2
    cover2 = " ".join(getattr(f, "text", "") for f in ep._cover("blueprint", "The Blueprint", "Volume I", row))
    assert "CLIENT APPROVED" in cover2
    row.qa_report_json = json.dumps({"checks": [], "findings": [_finding("x", "open finding")]})
    cover3 = " ".join(getattr(f, "text", "") for f in ep._cover("blueprint", "The Blueprint", "Volume I", row))
    assert "DRAFT — REQUIRES VALIDATION" in cover3 and ep.BMV_STATEMENT not in cover3


def test_release_record_carries_parent_revision_and_cumulative_corrections(client, tmp_path, monkeypatch):
    import release_audit as ra
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    bc, mods, reg = _skeleton()
    reg["pilot_ai_removed"] = [{"module": "pre-dispatch-whatsapp-pilot", "field": "tech.build_sequence[2]", "removed": "AI step"}]
    db = SessionLocal()
    row = _seed(db, mvp_blueprint="## The decision\nA plan.\n\n## Executive summary\nfine\n",
                technical_plan="## How your system works\nfine\n",
                procedures_json=json.dumps({"procedures": [{"name": "Daily check", "phase": "pilot", "module": "The pilot",
                                                            "trigger": "morning", "steps": [{"actor": "you", "step": "Check the log."}]}]}),
                qa_report_json=json.dumps({"checks": [], "findings": []}),
                registry_json=json.dumps(reg), business_case_json=json.dumps(bc), modules_json=json.dumps(mods),
                ops_numbers_json=OPS)
    first = ra.audit_run(row)
    assert first["parent_revision"] is None and first["corrections_current_pass"]["pilot_ai_removed"] == reg["pilot_ai_removed"]
    assert first["corrections_cumulative"] == first["corrections_current_pass"] and first["validation_errors"] == []
    from app.pipeline.export_pdf import STATUS_LABELS

    assert first["status"] in ("final", "draft") and first["status_label"] == STATUS_LABELS[first["status"]]
    # second pass: nothing new corrected, a different correction class logged
    reg2 = json.loads(row.registry_json)
    reg2["pilot_ai_removed"] = []
    reg2["derivations_shown"] = [{"source": "blueprint", "original": "$194.40 per day", "derivation": "$70,956 a year ÷ 365"}]
    row.registry_json = json.dumps(reg2)
    db.commit()
    second = ra.audit_run(row)
    assert second["parent_revision"] == first["revision"]
    assert second["corrections_current_pass"]["pilot_ai_removed"] == [] and second["corrections_current_pass"]["derivations_shown"]
    assert second["corrections_cumulative"]["pilot_ai_removed"] == reg["pilot_ai_removed"]
    assert second["corrections_cumulative"]["derivations_shown"] == reg2["derivations_shown"]
    assert second["corrections"] == second["corrections_cumulative"] and second["validation_errors"] == []
    with open(second["record_path"], encoding="utf-8") as f:
        on_disk = json.load(f)
    assert on_disk["parent_revision"] == first["revision"] and on_disk["corrections_cumulative"]["pilot_ai_removed"]
    # a record claiming fewer cumulative entries than its own pass does not validate
    lie = copy.deepcopy(second)
    lie["corrections_cumulative"]["derivations_shown"] = []
    assert any("corrections_cumulative" in e for e in ra.validate_record(lie))
    db.close()
