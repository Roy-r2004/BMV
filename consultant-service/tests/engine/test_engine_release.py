"""C19 - the release record, its revisions and what they prove (design 12.4).

The record is validated by `tools/release_audit.validate_record` UNCHANGED,
so most of what is pinned here is pinned against r30's own validator rather
than against a second opinion written for the engine.

The named mutations for this component and the test that kills each:

  bind corrections_current_pass to the parent's hash
      -> test_two_releases_after_an_edit_are_r1_and_r2
         test_this_passs_corrections_are_bound_to_this_content
  put an r30 revision id into corrections_current_pass.applied
      -> test_a_correction_from_another_revision_is_refused
         test_legacy_references_live_only_in_the_integrity_block
"""
from __future__ import annotations

import json
import os
from decimal import Decimal

import pytest

from app.engine.gates import presentation, release
from app.engine.gates.laws import LawId, run_laws
from app.engine.registry import EngagementRegistry
from app.engine.types import (
    Actor,
    Confidence,
    DecisionOwnerPayload,
    DecisionPayload,
    DecisionRole,
    Dimensions,
    EffortClass,
    EvidenceSourcePayload,
    FactBasis,
    FactPayload,
    FillStrategy,
    Finding,
    Kind,
    MeasurePayload,
    Provenance,
    QuestionPayload,
    Quantity,
    RecommendationPayload,
    RelationToCentralDecision,
    Relevance,
    Severity,
    SourceKind,
    Status,
    UnitFamily,
    WorkstreamPayload,
    make_entity,
)
from app.engine.work_products.integrity_record import ArtifactReport, build_integrity_record
from app.engine.work_products.render_md import RenderedProduct, RenderedSection
from app.engine.work_products.render_pdf import render_markdown_artifact, render_pdf
from app.engine.work_products import statements

from tests.engine.conftest import FIXED_CLOCK


ENGAGEMENT = "E-7"

# A conversation, and nothing else. No attachment, no document: the whole
# evidence base is what the client said and then confirmed (MF2.1).
CLIENT_SENTENCE = "we move 4200 parcels a week out of the northern depots"
TURN_TEXT = f"Good morning. {CLIENT_SENTENCE}. We must decide before the peak season."


def _entity(kind, payload, *, eid, actor=Actor.PARTNER, status=Status.PROPOSED, derived=()):
    return make_entity(
        kind=kind, engagement_id=ENGAGEMENT, payload=payload,
        provenance=Provenance(actor=actor, actor_ref=f"{actor.value}:1", derived_from=tuple(derived),
                              recorded_at=FIXED_CLOCK),
        confidence=Confidence(None), relevance=Relevance("DEC-1", 0.5),
        relation=RelationToCentralDecision.INFORMS, status=status, entity_id=eid)


def _qty(value: str) -> Quantity:
    return Quantity(Decimal(value), "parcels", UnitFamily.COUNT,
                    Dimensions(currency=None, period="2026-01", period_basis="week",
                               scope="the northern depots", as_of="2026-01-31", definition=None), 0)


def rows(extra=()) -> list:
    base = [
        _entity(Kind.EVIDENCE_SOURCE, EvidenceSourcePayload(
            name="opening conversation", source_kind=SourceKind.CONVERSATION_TURN,
            text=TURN_TEXT, received_at=FIXED_CLOCK), eid="EVI-1"),
        _entity(Kind.MEASURE, MeasurePayload(name="weekly parcel volume", unit_family=UnitFamily.COUNT,
                                             definition="parcels leaving the depots",
                                             confirmed_by_client=True), eid="MEA-1", actor=Actor.CLIENT),
        _entity(Kind.DECISION, DecisionPayload(statement="whether to consolidate the depots",
                                               role=DecisionRole.CENTRAL), eid="DEC-1"),
        _entity(Kind.DECISION_OWNER, DecisionOwnerPayload(name="the operations director",
                                                          role="operations director", resolves=("DEC-1",)),
                eid="DOW-1", actor=Actor.CLIENT),
        _entity(Kind.FACT, FactPayload(statement=CLIENT_SENTENCE, basis=FactBasis.CLIENT_STATED,
                                       measure_id="MEA-1", quantity=_qty("4200"), topic="volume"),
                eid="FCT-1", actor=Actor.CLIENT, status=Status.CONFIRMED, derived=("EVI-1",)),
        _entity(Kind.RECOMMENDATION, RecommendationPayload(
            statement="Consolidate onto the northern site", decision_id="DEC-1",
            supports=("FCT-1",)), eid="REC-1"),
    ]
    return base + list(extra)


def build(extra=()) -> EngagementRegistry:
    return EngagementRegistry.from_rows(ENGAGEMENT, rows(extra), clock=lambda: FIXED_CLOCK)


def claim(view, entity_id: str) -> str:
    return statements.statement_text(view.get(entity_id), view)


def render(view, out_dir, *, draft: bool, title="Decision Brief", product_id="brief"):
    """One product in two formats, the way a real pass renders it."""
    body = "\n".join(f"- {claim(view, eid)}" for eid in ("FCT-1", "REC-1"))
    section = RenderedSection(id="s1", title="What the record shows", renderer="statement_list", body=body)
    product = RenderedProduct(product_id=product_id, title=title, sections=(section,),
                              markdown=f"# {title}\n\n## What the record shows\n\n{body}\n",
                              registry_hash=view.content_hash())
    pdf = render_pdf(product, out_path=os.path.join(out_dir, f"{product_id}.pdf"), draft=draft,
                     subtitle="prepared for the decision owner", registry_hash=view.content_hash())
    md = render_markdown_artifact(product, out_path=os.path.join(out_dir, f"{product_id}.md"),
                                  registry_hash=view.content_hash())
    return [pdf, md]


def integrity_for(view, artifacts, findings=(), mappings=()) -> dict:
    reports = [ArtifactReport(ref=r) for r in artifacts]
    return build_integrity_record(view, artifacts=reports, findings=findings, mappings=mappings)


def do_release(view, artifacts, base_dir, *, mappings=(), legacy=None, extra_findings=()):
    findings = tuple(run_laws(view, artifacts)) + tuple(extra_findings)
    return release.release(view, artifacts, engagement_id=ENGAGEMENT,
                           integrity=integrity_for(view, artifacts, findings, mappings),
                           extra_findings=extra_findings, mappings=mappings, legacy=legacy,
                           base_dir=str(base_dir), clock=lambda: "2026-01-01T00:00:00Z")


@pytest.fixture
def base_dir(tmp_path):
    d = tmp_path / "releases"
    d.mkdir()
    return d


# ===========================================================================
# The status
# ===========================================================================

def test_release_status_is_draft_while_any_blocking_finding_is_open():
    open_finding = Finding(law=LawId.L5.value, where="QST-1", issue="a material question is open",
                           fix="answer it", severity=Severity.HIGH, blocks_final=True)
    gate = release.release_status([open_finding])
    assert gate["status"] == "draft"
    assert gate["reasons"] == [f"{LawId.L5.value}: QST-1: a material question is open"]


def test_a_non_blocking_finding_does_not_hold_the_door():
    advisory = Finding(law="R.style", where="brief", issue="a section reads stiffly", fix="rewrite",
                       severity=Severity.LOW, blocks_final=False)
    assert release.release_status([advisory])["status"] == "final"


def test_client_approved_needs_the_client_s_own_owner_and_approver():
    """A consultancy deliverable is FINAL on its quality checks; CLIENT
    APPROVED is the optional later state and needs two client facts."""
    assert release.release_status([])["status"] == "final"
    approved = release.release_status([], approval={"owner": "the operations director",
                                                    "approver": "the board", "complete": True})
    assert approved["status"] == "client_approved"


def test_client_approval_is_read_from_the_registry_never_invented():
    view = build()
    approval = release.client_approval(view)
    assert approval["owner"] == "the operations director"
    assert approval["approver"] is None                   # no charter has been approved
    assert approval["complete"] is False


# ===========================================================================
# The record
# ===========================================================================

def test_release_without_documents(base_dir, tmp_path):
    """MF2.1 end to end: an engagement whose entire evidence base is what the
    client said and confirmed reaches FINAL. Without CLIENT_STATED authority
    this document could never be released at all."""
    view = build()
    assert [e.payload.source_kind for e in view.query(Kind.EVIDENCE_SOURCE)] == [SourceKind.CONVERSATION_TURN]

    artifacts = render(view, str(tmp_path), draft=False)
    result = do_release(view, artifacts, base_dir)

    assert result.record["status"] == "final"
    assert result.record["validation_errors"] == []
    assert result.record["reasons"] == []
    assert result.verification == "valid"
    assert os.path.isfile(os.path.join(result.directory, "record.json"))


def test_the_record_validates_with_r30s_own_validator(base_dir, tmp_path):
    view = build()
    result = do_release(view, render(view, str(tmp_path), draft=False), base_dir)
    audit = presentation.import_tool("release_audit")
    assert audit.validate_record(result.record) == []


def test_totals_are_derived_from_the_manifest(base_dir, tmp_path):
    """R5: a total is arithmetic over the volumes, never a number someone
    typed. Editing a volume's page count and re-validating says so."""
    view = build()
    result = do_release(view, render(view, str(tmp_path), draft=False), base_dir)
    audit = presentation.import_tool("release_audit")
    assert result.record["totals"] == audit.totals_from(result.record["volumes"])

    tampered = json.loads(json.dumps(result.record))
    tampered["totals"]["pages"] += 1
    assert audit.validate_record(tampered) != []


def test_one_volume_per_artifact_and_no_fixed_number_of_them(base_dir, tmp_path):
    """Dynamic, not hardcoded: the manifest has as many volumes as the pass
    rendered, and adding a product adds a volume without touching the gate."""
    view = build()
    one = render(view, str(tmp_path), draft=False)
    two = render(view, str(tmp_path), draft=False, product_id="plan", title="Delivery Plan")
    result = do_release(view, one + two, base_dir)
    assert set(result.record["volumes"]) == {"brief.pdf", "brief.md", "plan.pdf", "plan.md"}
    assert result.record["totals"]["volumes"] == 4


def test_the_integrity_block_carries_the_corrections_themselves(base_dir, tmp_path):
    """A record that says "7 mappings" describes nothing and cannot be
    checked: every entry carries where it was applied and under which law."""
    from app.engine.work_products.corrections import MappingRecord

    view = build()
    mapping = MappingRecord(where="brief:s1", entity="WKS-1", law="corrections.exact_canonical_mapping",
                            before="the depot programme", after="Depot Consolidation Programme")
    result = do_release(view, render(view, str(tmp_path), draft=False), base_dir, mappings=[mapping])
    applied = result.record["corrections_current_pass"]["applied"]
    assert applied == [mapping.as_dict()]
    assert result.record["corrections_current_pass"]["count"] == 1
    assert result.record["integrity"]["mappings_applied"] == applied
    assert result.record["validation_errors"] == []


def test_this_passs_corrections_are_bound_to_this_content(base_dir, tmp_path):
    """R2, and the mutation 'bind corrections_current_pass to the parent's
    hash'. The corrections a record lists are the ones applied to the content
    that record hashes - binding them to any other hash is refused."""
    view = build()
    result = do_release(view, render(view, str(tmp_path), draft=False), base_dir)
    cur = result.record["corrections_current_pass"]
    assert cur["content_hash"] == result.record["integrity"]["content_hash"] == view.content_hash()
    assert cur["proven"] is True

    audit = presentation.import_tool("release_audit")
    tampered = json.loads(json.dumps(result.record))
    tampered["corrections_current_pass"]["content_hash"] = "0" * 64
    assert any("different content" in e for e in audit.validate_record(tampered))


def test_a_correction_count_that_does_not_match_its_list_is_refused(base_dir, tmp_path):
    view = build()
    result = do_release(view, render(view, str(tmp_path), draft=False), base_dir)
    audit = presentation.import_tool("release_audit")
    tampered = json.loads(json.dumps(result.record))
    tampered["corrections_current_pass"]["count"] = 99
    assert any("count does not match" in e for e in audit.validate_record(tampered))


# ===========================================================================
# R3 - legacy references
# ===========================================================================

def test_a_correction_from_another_revision_is_refused():
    """MF2.8, and the mutation 'put an r30 revision id into
    corrections_current_pass.applied'. Run 53-r22 presented seventeen
    corrections recovered from an earlier revision as the current pass's."""
    record = {"revision": "E-7-r2",
              "corrections_current_pass": {"applied": [
                  {"where": "53-r30/blueprint.pdf", "entity": "MK-1", "law": "canon",
                   "before": "a", "after": "b"}]}}
    errors = release.foreign_revision_errors(record)
    assert errors and "53-r30" in errors[0]


def test_this_revisions_own_id_is_not_foreign():
    record = {"revision": "E-7-r2",
              "corrections_current_pass": {"applied": [
                  {"where": "E-7-r2:brief:s1", "entity": "WKS-1", "law": "canon",
                   "before": "a", "after": "b"}]}}
    assert release.foreign_revision_errors(record) == []


def test_revision_tokens_are_read_literally():
    assert release.revision_tokens('{"where": "53-r30"}') == {"53-r30"}
    assert release.revision_tokens("nothing here") == set()
    assert release.revision_tokens("r30 alone, and -r5 alone") == set()


def test_legacy_references_live_only_in_the_integrity_block(base_dir, tmp_path, monkeypatch):
    """The r30 package is named in integrity.legacy and nowhere else in the
    record - and a record carrying a legacy VOLUME still validates."""
    from app.engine.gates import laws as laws_module

    monkeypatch.setattr(laws_module, "LEGACY_STATUS",
                        lambda rid: {"found": True, "status": "final", "reasons": [],
                                     "integrity_current": True, "integrity_findings": []})
    view = build([_entity(Kind.WORKSTREAM, WorkstreamPayload(
        name="Depot systems", purpose="replace the routing system", legacy_request_id=57), eid="WKS-1")])

    artifacts = render(view, str(tmp_path), draft=False)
    artifacts += render(view, str(tmp_path), draft=False, product_id="legacy_r30_technology_blueprint",
                        title="Technology Blueprint")
    legacy = {"r30_request_id": 57, "revision": "57-r3", "record_sha256": "a" * 64,
              "integrity_content_hash": "b" * 64, "status": "final"}
    result = do_release(view, artifacts, base_dir, legacy=legacy)

    assert result.record["validation_errors"] == []
    assert result.record["status"] == "final"
    assert result.record["integrity"]["legacy"]["revision"] == "57-r3"
    assert "legacy_r30_technology_blueprint.pdf" in result.record["volumes"]
    assert release.foreign_revision_errors(result.record) == []
    # the legacy revision is nowhere near this pass's corrections
    assert json.dumps(result.record["corrections_current_pass"]).find("57-r3") < 0


# ===========================================================================
# R4 - revisions
# ===========================================================================

def test_two_releases_after_an_edit_are_r1_and_r2(base_dir, tmp_path):
    """The design's own acceptance test: an edit earns the next revision, the
    artifacts hash differently, and both frozen revisions still verify."""
    from dataclasses import replace

    (tmp_path / "one").mkdir()
    first_view = build()
    first = do_release(first_view, render(first_view, str(tmp_path / "one"), draft=False), base_dir)

    # The edit: the recommendation is revised, which supersedes the row rather
    # than changing it. The next render therefore says something different and
    # hashes differently, which is what makes a revision worth having.
    revised = _entity(Kind.RECOMMENDATION, RecommendationPayload(
        statement="Consolidate onto the northern site before the peak season", decision_id="DEC-1",
        supports=("FCT-1",)), eid="REC-1")
    second_view = build([replace(revised, version=2, supersedes=1)])
    (tmp_path / "two").mkdir()
    second = do_release(second_view, render(second_view, str(tmp_path / "two"), draft=False), base_dir)

    assert first.revision == f"{ENGAGEMENT}-r1"
    assert second.revision == f"{ENGAGEMENT}-r2"
    assert second.record["parent_revision"] == first.revision
    assert first.record["volumes"]["brief.pdf"]["sha256"] != second.record["volumes"]["brief.pdf"]["sha256"]
    assert first.verification == "valid"
    assert second.verification == "valid"
    assert second.record["validation_errors"] == []


def test_the_cumulative_corrections_carry_the_parent_s(base_dir, tmp_path):
    """Lineage: a revision's cumulative log is its parent's plus its own."""
    from app.engine.work_products.corrections import MappingRecord

    view = build()
    (tmp_path / "one").mkdir()
    m1 = MappingRecord(where="brief:s1", entity="WKS-1", law="canon", before="a", after="b")
    do_release(view, render(view, str(tmp_path / "one"), draft=False), base_dir, mappings=[m1])

    (tmp_path / "two").mkdir()
    m2 = MappingRecord(where="brief:s1", entity="WKS-2", law="canon", before="c", after="d")
    second = do_release(view, render(view, str(tmp_path / "two"), draft=False), base_dir, mappings=[m2])

    cumulative = second.record["corrections_cumulative"]["mappings"]
    assert m1.as_dict() in cumulative and m2.as_dict() in cumulative
    assert second.record["corrections_current_pass"]["applied"] == [m2.as_dict()]


def test_a_revision_is_never_overwritten(base_dir, tmp_path):
    view = build()
    artifacts = render(view, str(tmp_path), draft=False)
    result = do_release(view, artifacts, base_dir)
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        release.freeze(result.record, artifacts, engagement_id=ENGAGEMENT, revision=1,
                       base_dir=str(base_dir))


def test_a_record_that_does_not_validate_is_never_frozen(base_dir, tmp_path):
    """R1: the errors are raised, not filed."""
    view = build()
    artifacts = render(view, str(tmp_path), draft=False)
    record = release.build_release_record(
        engagement_id=ENGAGEMENT, view=view, artifacts=artifacts,
        integrity=integrity_for(view, artifacts), findings=(), revision=1)
    record["validation_errors"] = ["a total that does not add up"]
    with pytest.raises(RuntimeError, match="does not validate"):
        release.freeze(record, artifacts, engagement_id=ENGAGEMENT, revision=1, base_dir=str(base_dir))
    assert not os.path.exists(release.revision_dir(ENGAGEMENT, 1, str(base_dir)))


def test_verify_reports_stale_when_a_frozen_file_changes(base_dir, tmp_path):
    """FINAL is valid ONLY for the exact hashes the record names."""
    view = build()
    result = do_release(view, render(view, str(tmp_path), draft=False), base_dir)
    assert release.verify(result.directory) == "valid"

    frozen = os.path.join(result.directory, result.record["volumes"]["brief.md"]["file"])
    with open(frozen, "a", encoding="utf-8") as fh:
        fh.write("\na line nobody audited\n")
    assert release.verify(result.directory).startswith("stale")


def test_the_revision_id_is_the_engagement_s_own(base_dir):
    assert release.revision_id(ENGAGEMENT, 3) == "E-7-r3"
    assert release.next_revision(ENGAGEMENT, str(base_dir)) == 1


# ===========================================================================
# The stamp
# ===========================================================================

def test_a_draft_release_demands_the_stamp_on_every_page(base_dir, tmp_path):
    """A document that is not releasable says so on every page a reader can
    open it at. The gate says draft, so the record inspects the pages
    expecting the stamp - and an unstamped file fails that inspection."""
    view = build([_entity(Kind.QUESTION, QuestionPayload(
        text="Which site holds the picking equipment?", material=True, why="it decides the site",
        effort=EffortClass.LOOKUP, strategy=FillStrategy.ASK_CLIENT), eid="QST-1", status=Status.OPEN)])
    artifacts = render(view, str(tmp_path), draft=False)          # rendered as if it were releasable
    findings = run_laws(view, artifacts)
    assert release.release_status(findings)["status"] == "draft"

    record = release.build_release_record(
        engagement_id=ENGAGEMENT, view=view, artifacts=artifacts,
        integrity=integrity_for(view, artifacts, findings), findings=findings, revision=1)
    assert record["status"] == "draft"
    assert any("expected DRAFT watermark" in f for f in record["volumes"]["brief.pdf"]["failures"])


def test_a_draft_stamped_page_cannot_be_released_as_final(base_dir, tmp_path):
    """The other direction: nothing else in the record contradicts the pages,
    so a stamped file forces the record back to draft."""
    view = build()
    artifacts = render(view, str(tmp_path), draft=True)
    record = release.build_release_record(
        engagement_id=ENGAGEMENT, view=view, artifacts=artifacts,
        integrity=integrity_for(view, artifacts), findings=(), revision=1)
    assert record["status"] == "draft"
    assert any("still carries the DRAFT watermark" in f
               for f in record["volumes"]["brief.pdf"]["failures"])


def test_the_stamped_draft_carries_it_on_every_page(tmp_path):
    view = build()
    pdf = render(view, str(tmp_path), draft=True)[0]
    result = presentation.inspect_pdf_result(pdf.path, expect="draft")
    assert result["failures"] == []
    assert result["draft_stamped_pages"] == result["pages"] > 0


# ===========================================================================
# What the record is for
# ===========================================================================

def test_a_blocking_finding_reaches_the_record_as_a_reason(base_dir, tmp_path):
    view = build([_entity(Kind.QUESTION, QuestionPayload(
        text="What did the depots cost to run last year?", material=True, why="it sizes the case",
        effort=EffortClass.DOCUMENT, strategy=FillStrategy.REQUEST_DOCUMENT), eid="QST-1",
        status=Status.OPEN)])
    artifacts = render(view, str(tmp_path), draft=True)
    findings = run_laws(view, artifacts)
    record = release.build_release_record(
        engagement_id=ENGAGEMENT, view=view, artifacts=artifacts,
        integrity=integrity_for(view, artifacts, findings), findings=findings, revision=1)

    assert any(LawId.L5.value in r for r in record["reasons"])
    assert record["integrity"]["status"] == "blocked"
    assert record["integrity"]["blocked"] and record["integrity"]["findings"]
    assert record["validation_errors"] == []                      # a draft record is still a valid record


def test_an_advisory_finding_is_recorded_without_blocking(base_dir, tmp_path):
    """Non-blocking findings go into the Integrity Record only (design 12.1);
    r30's validator reads `integrity.findings` as the open blockers, so an
    advisory must not be filed there."""
    view = build()
    artifacts = render(view, str(tmp_path), draft=False)
    advisory = Finding(law="R.style", where="brief:s1", issue="a section reads stiffly",
                       fix="regenerate the narrative", severity=Severity.LOW, blocks_final=False)
    result = do_release(view, artifacts, base_dir, extra_findings=[advisory])
    assert result.record["status"] == "final"
    assert result.record["integrity"]["findings"] == []
    assert result.record["integrity"]["advisory_findings"] == [advisory.as_dict()]
    assert result.record["validation_errors"] == []


def test_every_law_is_listed_in_the_record(base_dir, tmp_path):
    """A release names the fourteen laws it ran, so a reader can tell a law
    that passed from a law nobody ran."""
    view = build()
    result = do_release(view, render(view, str(tmp_path), draft=False), base_dir)
    assert [entry["id"] for entry in result.record["integrity"]["laws"]] == [law.value for law in LawId]


def test_the_frozen_directory_holds_the_exact_audited_files(base_dir, tmp_path):
    view = build()
    artifacts = render(view, str(tmp_path), draft=False)
    result = do_release(view, artifacts, base_dir)
    for key, vol in result.record["volumes"].items():
        frozen = os.path.join(result.directory, vol["file"])
        assert os.path.isfile(frozen)
        assert presentation.sha256_of_file(frozen) == vol["sha256"]
    assert result.directory.endswith(os.path.join("releases", f"{ENGAGEMENT}-r1"))


def test_the_record_never_names_an_engagement_type():
    """No engagement-type branching: release.py compares only against the
    three release states and the law ids."""
    import ast

    source = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "app", "engine", "gates", "release.py")
    tree = ast.parse(open(source, encoding="utf-8").read())
    banned = {"blueprint", "technical", "operations", "engagement_type", "industry", "sector"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert not (set(node.value.lower().split()) & banned), node.value
