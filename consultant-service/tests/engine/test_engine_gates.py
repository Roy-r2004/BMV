"""C19 - the gate (design 12.1-12.3).

Every law gets a pair: a fixture that fails it and a fixture that passes it,
and both go through `run_laws`, never through the law function alone. That is
what makes "remove the law from LAWS" a mutation the suite catches - a law
nobody registered raises no finding, and the failing half of its pair goes
red.

The named mutations for this component and the test that kills each:

  remove L1..L14 from LAWS
      -> the fourteen test_lN_* failing-fixture tests (each runs run_laws)
         test_every_law_is_registered
  read the stored material flag (L1)
      -> test_l1_recomputes_materiality_and_ignores_the_stored_flag
  widen L7 to 0.5%
      -> test_l7_demands_an_exact_recompute
         test_l7_tolerance_is_zero
  drop the clipping check (L9)
      -> test_l9_reports_a_clipped_span
         test_presentation_gate_is_all_three_checks
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal

import pytest

from app.engine.gates import presentation
from app.engine.gates.laws import (
    LAWS,
    ArtifactRef,
    Law,
    LawId,
    RECOMPUTE_TOLERANCE,
    run_laws,
)
from app.engine.registry import EngagementRegistry
from app.engine.types import (
    Actor,
    ApprovalState,
    AssumptionPayload,
    Authority,
    ConflictConclusion,
    ConflictKind,
    ConflictPayload,
    Confidence,
    DecisionPayload,
    DecisionRequiredPayload,
    DecisionRole,
    Dimensions,
    EffortClass,
    EvidenceSourcePayload,
    FactBasis,
    FactPayload,
    Feasibility,
    FillStrategy,
    Kind,
    MeasurePayload,
    ObjectivePayload,
    Provenance,
    QuestionPayload,
    Quantity,
    RecommendationPayload,
    RegulatedDomain,
    RegulatedMatterPayload,
    RelationToCentralDecision,
    Relevance,
    SourceKind,
    Status,
    UnitFamily,
    WorkProductPayload,
    WorkstreamPayload,
    make_entity,
)
from app.engine.work_products import statements
from app.pipeline.registry import PROPOSED_LABEL

from tests.engine.conftest import FIXED_CLOCK


# ---------------------------------------------------------------------------
# One small engagement. No client is named and nothing below is read by
# app/engine: these are ordinary trade words.
# ---------------------------------------------------------------------------

CLIENT_SENTENCE = "we move 4200 parcels a week out of the northern depots"
TURN_TEXT = (f"Good morning. {CLIENT_SENTENCE}. We need to decide what to do "
             "before the peak season.")
ASSUMPTION_TEXT = "the peak season starts in the last week of November"


def _entity(kind, payload, *, eid, actor=Actor.PARTNER, status=Status.PROPOSED,
            derived=(), locator=None, relation=RelationToCentralDecision.INFORMS,
            confirmed_by=None):
    e = make_entity(
        kind=kind, engagement_id="E-1", payload=payload,
        provenance=Provenance(actor=actor, actor_ref=f"{actor.value}:1", derived_from=tuple(derived),
                              source_locator=locator, recorded_at=FIXED_CLOCK),
        confidence=Confidence(None), relevance=Relevance("DEC-1", 0.5),
        relation=relation, status=status, entity_id=eid)
    if confirmed_by is not None:
        from dataclasses import replace

        e = replace(e, confirmed_by=confirmed_by)
    return e


def _qty(value: str, unit: str = "parcels", family: UnitFamily = UnitFamily.COUNT, *,
         precision: int = 0) -> Quantity:
    return Quantity(Decimal(value), unit, family,
                    Dimensions(currency=None, period="2026-01", period_basis="week",
                               scope="the northern depots", as_of="2026-01-31", definition=None),
                    precision)


def base_rows() -> list:
    """A registry every law passes: a confirmed client fact, a recommendation
    that rests on it, one unapproved assumption and one immaterial question."""
    return [
        _entity(Kind.EVIDENCE_SOURCE, EvidenceSourcePayload(
            name="opening conversation", source_kind=SourceKind.CONVERSATION_TURN,
            text=TURN_TEXT, received_at=FIXED_CLOCK), eid="EVI-1"),
        _entity(Kind.MEASURE, MeasurePayload(name="weekly parcel volume", unit_family=UnitFamily.COUNT,
                                             definition="parcels leaving the depots",
                                             confirmed_by_client=True), eid="MEA-1", actor=Actor.CLIENT),
        _entity(Kind.DECISION, DecisionPayload(statement="whether to consolidate the depots",
                                               role=DecisionRole.CENTRAL), eid="DEC-1"),
        _entity(Kind.FACT, FactPayload(statement=CLIENT_SENTENCE, basis=FactBasis.CLIENT_STATED,
                                       measure_id="MEA-1", quantity=_qty("4200"), topic="volume"),
                eid="FCT-1", actor=Actor.CLIENT, status=Status.CONFIRMED, derived=("EVI-1",)),
        _entity(Kind.ASSUMPTION, AssumptionPayload(statement=ASSUMPTION_TEXT, rationale="prior years",
                                                   approval=ApprovalState.UNAPPROVED), eid="ASM-1"),
        _entity(Kind.QUESTION, QuestionPayload(text="Which site holds the picking equipment?",
                                               material=False, why="it would refine the plan",
                                               effort=EffortClass.LOOKUP,
                                               strategy=FillStrategy.ASK_CLIENT),
                eid="QST-1", status=Status.OPEN),
        _entity(Kind.RECOMMENDATION, RecommendationPayload(
            statement="Consolidate onto the northern site", decision_id="DEC-1",
            supports=("FCT-1",)), eid="REC-1"),
    ]


def build(rows=None) -> EngagementRegistry:
    return EngagementRegistry.from_rows("E-1", list(rows if rows is not None else base_rows()),
                                        clock=lambda: FIXED_CLOCK)


@pytest.fixture
def clean():
    return build()


def claim(view, entity_id: str) -> str:
    return presentation.normalise(statements.statement_text(view.get(entity_id), view))


def artifact(tmp_path, text: str, *, view=None, product_id="brief", fmt="md",
             registry_hash=None, name=None) -> ArtifactRef:
    """An artifact whose extracted text is exactly `text`, written to disk so
    L8 can hash it: a law that reads a page must be able to read the file."""
    path = tmp_path / (name or f"{product_id}.{fmt}")
    path.write_text(text, encoding="utf-8")
    digest = presentation.sha256_of_file(str(path))
    if registry_hash is None:
        registry_hash = view.content_hash() if view is not None else ""
    return ArtifactRef(product_id=product_id, fmt=fmt, path=str(path), sha256=digest,
                       registry_hash=registry_hash, extracted_text=text)


def fired(law: LawId, view, artifacts=()) -> list:
    """The findings THIS law raised, through the registry that holds it."""
    return [f for f in run_laws(view, artifacts) if f.law == law.value]


# ===========================================================================
# The registry of laws
# ===========================================================================

def test_every_law_is_registered():
    """The list IS the gate: sixteen ids, sixteen entries, in order."""
    assert [law.id for law in LAWS.all()] == list(LawId)
    assert len(list(LawId)) == 16
    assert all(law.blocks_final for law in LAWS.all())


def test_a_law_cannot_be_registered_twice():
    with pytest.raises(ValueError):
        LAWS.register(Law(LawId.L1, lambda view, artifacts: []))


def test_the_clean_registry_passes_every_law(clean):
    assert run_laws(clean) == []


def test_law_ids_are_spelled_once(clean):
    """A finding raised at synthesis and one raised at the gate must carry the
    same law name, or a reader sees two laws where there is one."""
    from app.engine.synthesis.recommend import UNSUPPORTED_RECOMMENDATION_LAW

    assert UNSUPPORTED_RECOMMENDATION_LAW == LawId.L2.value
    assert presentation.LAW_PRESENTATION == LawId.L9.value


# ===========================================================================
# L1 - a material conflict still open
# ===========================================================================

def _conflict_rows(*, material: bool, status=Status.OPEN, on="FCT-1"):
    rows = base_rows()
    rows.append(_entity(Kind.CONFLICT, ConflictPayload(
        kind=ConflictKind.VALUE, subject_id="MEA-1",
        conclusions=(ConflictConclusion(on, "4200 parcels", evidence=("EVI-1",)),
                     ConflictConclusion("FCT-9", "3900 parcels")),
        relation_to_central_decision=RelationToCentralDecision.INFORMS,
        authority_required=Authority.CLIENT, material=material), eid="CFL-1", status=status))
    return rows


def test_l1_blocks_an_open_conflict_a_recommendation_rests_on():
    view = build(_conflict_rows(material=True))
    assert [f.where for f in fired(LawId.L1, view)] == ["CFL-1"]


def test_l1_recomputes_materiality_and_ignores_the_stored_flag():
    """MF2.4, and the mutation 'read the stored material flag'. The conflict
    was written non-material - before the recommendation existed - and its
    conclusion is now a support of a live recommendation."""
    view = build(_conflict_rows(material=False))
    assert view.get("CFL-1").payload.material is False
    assert view.is_material(view.get("CFL-1")) is True
    assert [f.where for f in fired(LawId.L1, view)] == ["CFL-1"]


def test_l1_passes_a_resolved_conflict():
    view = build(_conflict_rows(material=True, status=Status.RESOLVED))
    assert fired(LawId.L1, view) == []


def test_l1_passes_an_immaterial_conflict():
    """The negative control for the recomputation: a conflict on a conclusion
    nothing rests on is not waved through by a flag, it is simply not
    material."""
    view = build(_conflict_rows(material=True, on="QST-1"))
    assert view.is_material(view.get("CFL-1")) is False
    assert fired(LawId.L1, view) == []


# ===========================================================================
# L2 - a recommendation that traces to nothing
# ===========================================================================

def _rec_rows(**payload_kw):
    rows = [r for r in base_rows() if r.id != "REC-1"]
    kw = dict(statement="Consolidate onto the northern site", decision_id="DEC-1", supports=("FCT-1",))
    kw.update(payload_kw)
    rows.append(_entity(Kind.RECOMMENDATION, RecommendationPayload(**kw), eid="REC-1"))
    return rows


def test_l2_blocks_a_recommendation_with_no_supports():
    view = build(_rec_rows(supports=()))
    assert [f.where for f in fired(LawId.L2, view)] == ["REC-1"]


def test_l2_blocks_a_support_that_is_only_proposed():
    """A PROPOSED fact is a candidate, not evidence."""
    rows = _rec_rows(supports=("FCT-2",))
    rows.append(_entity(Kind.FACT, FactPayload(statement="the depots run six days a week",
                                               basis=FactBasis.CLIENT_STATED, topic="hours"),
                        eid="FCT-2", actor=Actor.CLIENT, status=Status.PROPOSED, derived=("EVI-1",)))
    assert fired(LawId.L2, build(rows)) != []


def test_l2_accepts_a_confirmed_client_fact(clean):
    """MF2.1: the document-less path to a supported recommendation."""
    assert fired(LawId.L2, clean) == []


# ===========================================================================
# L3 - an unapproved assumption printed without its label
# ===========================================================================

def test_l3_blocks_an_assumption_printed_without_the_label(tmp_path, clean):
    page = f"What we assume\n{ASSUMPTION_TEXT}\nThat is what the plan rests on."
    findings = fired(LawId.L3, clean, [artifact(tmp_path, page, view=clean)])
    assert len(findings) == 1
    assert "ASM-1" in findings[0].where


def test_l3_passes_a_labelled_assumption(tmp_path, clean):
    page = f"What we assume\n{claim(clean, 'ASM-1')}\nThat is what the plan rests on."
    assert PROPOSED_LABEL in page
    assert fired(LawId.L3, clean, [artifact(tmp_path, page, view=clean)]) == []


def test_l3_says_nothing_about_a_page_that_does_not_print_it(tmp_path, clean):
    """Absence of the claim is not absence of the label: a product that never
    printed the assumption is not condemned by it."""
    page = "What we decided\nConsolidate onto the northern site."
    assert fired(LawId.L3, clean, [artifact(tmp_path, page, view=clean)]) == []


# ===========================================================================
# L4 - regulated matter unrouted, licensed interpretation printed
# ===========================================================================

def _regulated_rows(status=Status.PROPOSED, licensed=False):
    rows = _rec_rows(licensed_interpretation=licensed)
    rows.append(_entity(Kind.REGULATED_MATTER, RegulatedMatterPayload(
        text="whether the depot lease may be assigned", domain=RegulatedDomain.LEGAL_CONTRACT,
        adviser_class="qualified lawyer", why_regulated="lease assignment is legal advice",
        touches=("REC-1",), withheld_interpretation="the lease appears assignable"),
        eid="REG-1", status=status))
    return rows


def test_l4_blocks_an_unrouted_matter():
    findings = fired(LawId.L4, build(_regulated_rows()))
    assert any(f.where == "REG-1" for f in findings)


def test_l4_blocks_a_licensed_recommendation():
    findings = fired(LawId.L4, build(_regulated_rows(status=Status.ROUTED, licensed=True)))
    assert any(f.where == "REC-1" for f in findings)


def test_l4_blocks_a_claim_printed_while_its_matter_is_unrouted(tmp_path):
    view = build(_regulated_rows())
    page = claim(view, "REC-1")
    findings = fired(LawId.L4, view, [artifact(tmp_path, page, view=view)])
    assert any("REC-1" in f.where and "brief" in f.where for f in findings)


def test_l4_passes_a_routed_matter(tmp_path):
    view = build(_regulated_rows(status=Status.ROUTED))
    page = claim(view, "REC-1")
    assert fired(LawId.L4, view, [artifact(tmp_path, page, view=view)]) == []


# ===========================================================================
# L5 - a material question still open
# ===========================================================================

def _question_rows(*, material, status=Status.OPEN):
    rows = [r for r in base_rows() if r.id != "QST-1"]
    rows.append(_entity(Kind.QUESTION, QuestionPayload(
        text="Which site holds the picking equipment?", material=material,
        why="it decides the target site", effort=EffortClass.LOOKUP,
        strategy=FillStrategy.ASK_CLIENT), eid="QST-1", status=status))
    return rows


def test_l5_blocks_an_open_material_question():
    assert [f.where for f in fired(LawId.L5, build(_question_rows(material=True)))] == ["QST-1"]


def test_l5_passes_an_answered_question():
    assert fired(LawId.L5, build(_question_rows(material=True, status=Status.RESOLVED))) == []


def test_l5_reads_the_material_flag_with_is_true():
    """Owner contract: a row written before the flag existed carries None and
    is not condemned by it."""
    assert fired(LawId.L5, build(_question_rows(material=None))) == []


# ===========================================================================
# L6 - a claim restated in other words
# ===========================================================================

PARAPHRASE = "The northern depots move about 4,200 parcels each week."


def test_l6_blocks_a_figure_restated_outside_its_claim(tmp_path, clean):
    page = f"What the evidence shows\n{claim(clean, 'FCT-1')}\n\n{PARAPHRASE}"
    findings = fired(LawId.L6, clean, [artifact(tmp_path, page, view=clean)])
    assert len(findings) == 1
    assert "FCT-1" in findings[0].where


def test_l6_passes_a_page_that_only_prints_the_claim(tmp_path, clean):
    """The figure inside the canonical claim is the claim; blanking the claims
    out first is what makes that true, and removing the blanking turns every
    claim on every page into a finding."""
    page = f"What the evidence shows\n{claim(clean, 'FCT-1')}\n\nThe decision follows from it."
    assert fired(LawId.L6, clean, [artifact(tmp_path, page, view=clean)]) == []


def test_l6_and_l11_divide_every_figure_on_the_page(tmp_path, clean):
    """A figure that traces is L6's when it stands outside its claim; a figure
    that traces to nothing is L11's. No figure is judged by both and none by
    neither."""
    page = f"{claim(clean, 'FCT-1')}\n\n{PARAPHRASE} We also handle 8,400 returns."
    refs = [artifact(tmp_path, page, view=clean)]
    assert len(fired(LawId.L6, clean, refs)) == 1
    assert len(fired(LawId.L11, clean, refs)) == 1


# ===========================================================================
# L7 - a calculation that does not recompute
# ===========================================================================

def _calc_rows(stored: str):
    rows = base_rows()
    rows.append(_entity(Kind.FACT, FactPayload(
        statement="fortnightly parcel volume", basis=FactBasis.CALCULATED, measure_id="MEA-1",
        quantity=_qty(stored), formula="2 * FCT-1", inputs=("FCT-1",), topic="volume"),
        eid="FCT-3", actor=Actor.CALCULATOR, status=Status.PROPOSED, derived=("FCT-1",)))
    return rows


def test_l7_demands_an_exact_recompute():
    """2 x 4200 is 8400. A stored 8440 is off by 0.474% - inside the 0.5% a
    rendered restatement is allowed and outside anything a stored calculation
    may be."""
    view = build(_calc_rows("8440"))
    findings = fired(LawId.L7, view)
    assert [f.where for f in findings] == ["FCT-3"]
    assert "0.4" in findings[0].issue


def test_l7_passes_an_exact_recompute():
    assert fired(LawId.L7, build(_calc_rows("8400"))) == []


def test_l7_tolerance_is_zero():
    """The mutation 'widen L7 to 0.5%' is exactly this constant moving."""
    assert RECOMPUTE_TOLERANCE == Decimal("0")


def test_l7_blocks_a_calculation_whose_input_is_gone():
    rows = _calc_rows("8400")
    rows = [r for r in rows if r.id != "FCT-1"]
    assert fired(LawId.L7, build(rows)) != []


# ===========================================================================
# L8 - an artifact that describes another registry, or another file
# ===========================================================================

def test_l8_blocks_an_artifact_rendered_from_an_earlier_registry(tmp_path, clean):
    ref = artifact(tmp_path, "a page", view=clean, registry_hash="0" * 64)
    assert [f.issue for f in fired(LawId.L8, clean, [ref])] != []


def test_l8_blocks_a_file_edited_after_it_was_hashed(tmp_path, clean):
    ref = artifact(tmp_path, "a page", view=clean)
    with open(ref.path, "a", encoding="utf-8") as fh:
        fh.write("\nand one more line nobody audited")
    findings = fired(LawId.L8, clean, [ref])
    assert any("no longer hashes" in f.issue for f in findings)


def test_l8_blocks_an_artifact_that_is_not_on_disk(clean):
    ref = ArtifactRef(product_id="brief", fmt="pdf", path="", sha256="x" * 64,
                      registry_hash=clean.content_hash(), extracted_text="")
    assert any("not on disk" in f.issue for f in fired(LawId.L8, clean, [ref]))


def test_l8_passes_a_fresh_artifact(tmp_path, clean):
    assert fired(LawId.L8, clean, [artifact(tmp_path, "a page", view=clean)]) == []


# ===========================================================================
# L9 - the page itself
# ===========================================================================

def _plain_pdf(path: str, text: str, *, split_long_words: int = 1, font: str | None = None,
               chrome: bool = False):
    """A PDF laid out in the engine's own body frame. `split_long_words=0`
    makes a long token unbreakable, which is the one way a paragraph overflows
    a frame it fits nothing else past."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph

    from app.pipeline.export_pdf import F_BODY, _page_chrome

    style = ParagraphStyle("probe", fontName=font or F_BODY, fontSize=9.3, leading=13.5,
                           splitLongWords=split_long_words)
    doc = BaseDocTemplate(path, pagesize=A4)
    W, H = A4
    frame = Frame(18 * mm, 20 * mm, W - 36 * mm, H - 36 * mm, id="content")
    doc.addPageTemplates([PageTemplate(id="body", frames=[frame],
                                       onPage=_page_chrome("PROBE", "", draft=True) if chrome
                                       else (lambda canvas, d: None))])
    doc.build([Paragraph(text, style)])
    return path


LONG_TOKEN = "consolidation" * 12
CLIPPED = "The programme is recorded as " + LONG_TOKEN + " in the register."
WRAPPED = "The programme is recorded as " + " ".join(["consolidation"] * 12) + " in the register."


@pytest.fixture
def engine_pdf(tmp_path, clean):
    """A real engine volume: r30's faces, footer, stamp and body frame."""
    from app.engine.work_products.render_md import RenderedProduct, RenderedSection
    from app.engine.work_products.render_pdf import render_pdf

    body = "\n".join(f"- {claim(clean, eid)}" for eid in ("FCT-1", "ASM-1", "REC-1"))
    section = RenderedSection(id="s1", title="What the record shows", renderer="statement_list", body=body)
    product = RenderedProduct(product_id="brief", title="Decision Brief", sections=(section,),
                              markdown=f"# Decision Brief\n\n## What the record shows\n\n{body}\n",
                              registry_hash=clean.content_hash())
    return render_pdf(product, out_path=str(tmp_path / "brief.pdf"), draft=True,
                      subtitle="prepared for the decision owner", registry_hash=clean.content_hash())


def test_l9_reports_a_clipped_span(tmp_path, clean):
    """MF2.5, and the mutation 'drop the clipping check'. r30 listed clipped
    text as not automatically detectable and asked a human to look."""
    path = _plain_pdf(str(tmp_path / "clip.pdf"), CLIPPED, split_long_words=0)
    ref = ArtifactRef(product_id="brief", fmt="pdf", path=path,
                      sha256=presentation.sha256_of_file(path),
                      registry_hash=clean.content_hash(), extracted_text="")
    assert any("right edge of the body frame" in f.issue for f in fired(LawId.L9, clean, [ref]))


def test_the_same_text_wrapped_passes_the_clipping_check(tmp_path):
    path = _plain_pdf(str(tmp_path / "wrap.pdf"), WRAPPED)
    assert presentation.clipping_findings(path) == []


def test_clipping_reports_lines_printed_over_each_other(tmp_path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    from app.pipeline.export_pdf import F_BODY

    path = str(tmp_path / "overlap.pdf")
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont(F_BODY, 10)
    c.drawString(80, 500, "the northern depot consolidation plan")
    c.drawString(84, 502, "the northern depot consolidation plan")
    c.showPage()
    c.save()
    assert any("overlap" in f for f in presentation.clipping_findings(path))


def test_clipping_ignores_the_page_furniture(tmp_path):
    """The header, the stamp and the footer are drawn outside the frame on
    purpose; a check that called them clipped would fail every page."""
    path = _plain_pdf(str(tmp_path / "chrome.pdf"), WRAPPED, chrome=True)
    assert presentation.clipping_findings(path, title="Probe") == []


def test_presentation_gate_is_all_three_checks(tmp_path):
    """Each of the three contributes a class of finding nothing else raises:
    remove any one and one of these assertions goes red."""
    unembedded = _plain_pdf(str(tmp_path / "helv.pdf"), WRAPPED, font="Helvetica")
    issues = presentation.presentation_issues(unembedded)
    assert any("fonts not embedded" in i for i in issues)          # export_pdf.presentation_findings
    assert any("footer page numbers" in i for i in issues)         # tools/inspect_pdf.inspect

    clipped = _plain_pdf(str(tmp_path / "clip2.pdf"), CLIPPED, split_long_words=0)
    assert any("body frame" in i for i in presentation.presentation_issues(clipped))


def test_l9_passes_a_rendered_engine_volume(clean, engine_pdf):
    """MF2.7: inspect() is called unchanged and passes, because an engine PDF
    is drawn with r30's own faces, footer and stamp - and the clipping check
    agrees with the frame the renderer laid out."""
    assert fired(LawId.L9, clean, [engine_pdf]) == []


def test_the_stamp_is_on_every_page_or_on_none(engine_pdf):
    result = presentation.inspect_pdf_result(engine_pdf.path, expect="draft")
    assert result["draft_stamped_pages"] == result["pages"]
    assert presentation.stamp_findings(result) == []
    assert presentation.stamp_findings({"pages": 4, "draft_stamped_pages": 1}) != []


def test_the_semantic_laws_are_clean_on_a_rendered_engine_volume(clean, engine_pdf):
    """The whole gate over a real page: page furniture, section numbering and
    entity ids must not read as claims, or every document would be a draft."""
    assert run_laws(clean, [engine_pdf]) == []


# ===========================================================================
# L10 - two comparable facts on one measure, both printed
# ===========================================================================

def _second_fact(status=Status.CONFIRMED):
    return _entity(Kind.FACT, FactPayload(
        statement="the register says 3900 parcels a week", basis=FactBasis.DOCUMENT_EXTRACTED,
        measure_id="MEA-1", quantity=_qty("3900"), topic="volume"),
        eid="FCT-4", actor=Actor.PARTNER, status=status, derived=("EVI-1",))


def test_l10_blocks_two_unreconciled_values_on_one_measure(tmp_path):
    view = build(base_rows() + [_second_fact()])
    page = f"{claim(view, 'FCT-1')}\n{claim(view, 'FCT-4')}"
    findings = fired(LawId.L10, view, [artifact(tmp_path, page, view=view)])
    assert len(findings) == 1
    assert "MEA-1" in findings[0].where


def test_l10_passes_once_the_loser_is_superseded(tmp_path):
    view = build(base_rows() + [_second_fact(status=Status.SUPERSEDED)])
    page = f"{claim(view, 'FCT-1')}\n{claim(view, 'FCT-4')}"
    assert fired(LawId.L10, view, [artifact(tmp_path, page, view=view)]) == []


def test_l10_says_nothing_when_only_one_of_them_is_printed(tmp_path):
    view = build(base_rows() + [_second_fact()])
    page = claim(view, "FCT-1")
    assert fired(LawId.L10, view, [artifact(tmp_path, page, view=view)]) == []


# ===========================================================================
# L11 - a figure that traces to nothing
# ===========================================================================

def test_l11_blocks_a_coined_figure(tmp_path, clean):
    page = "The northern depots will save 12,600 parcels of handling."
    findings = fired(LawId.L11, clean, [artifact(tmp_path, page, view=clean)])
    assert findings != []


def test_l11_passes_a_traced_figure(tmp_path, clean):
    assert fired(LawId.L11, clean, [artifact(tmp_path, claim(clean, "FCT-1"), view=clean)]) == []


# ===========================================================================
# L12 - an objective the arithmetic refutes, never put to the client
# ===========================================================================

def _objective_rows(*, decided: bool):
    rows = base_rows()
    rows.append(_entity(Kind.OBJECTIVE, ObjectivePayload(
        text="halve the handling cost this quarter", priority=1, measure_id="MEA-1",
        target=_qty("2100"), feasibility=Feasibility.INFEASIBLE_ON_FACTS),
        eid="OBJ-1", actor=Actor.CLIENT))
    if decided:
        rows.append(_entity(Kind.DECISION_REQUIRED, DecisionRequiredPayload(
            text="the target cannot be met on the registered facts; change it or change the scope",
            from_authority=Authority.CLIENT, decision_id="DEC-1"),
            eid="DRQ-1", status=Status.OPEN, derived=("OBJ-1",)))
    return rows


def test_l12_blocks_an_infeasible_objective_nobody_asked_about():
    assert [f.where for f in fired(LawId.L12, build(_objective_rows(decided=False)))] == ["OBJ-1"]


def test_l12_passes_once_the_decision_is_put_to_the_client():
    assert fired(LawId.L12, build(_objective_rows(decided=True))) == []


# ===========================================================================
# L13 - a delivered r30 package that is not itself FINAL
# ===========================================================================

def _legacy_rows():
    rows = base_rows()
    rows.append(_entity(Kind.WORKSTREAM, WorkstreamPayload(
        name="Depot systems", purpose="replace the routing system", legacy_request_id=57),
        eid="WKS-1"))
    return rows


@pytest.fixture
def legacy_status(monkeypatch):
    """The r30 gate, faked. The real reader opens the Request row and calls
    export_pdf.release_status on it; the law's decision is what is pinned
    here, not r30's own gate, which has its own suite."""
    from app.engine.gates import laws as laws_module

    def install(**status):
        monkeypatch.setattr(laws_module, "LEGACY_STATUS", lambda rid: dict(status, request_id=rid))

    return install


def test_l13_blocks_while_the_r30_package_is_a_draft(legacy_status):
    legacy_status(found=True, status="draft", reasons=["2 open high finding(s) on the quality bench"],
                  integrity_current=True, integrity_findings=[])
    findings = fired(LawId.L13, build(_legacy_rows()))
    assert any("not final" in f.issue for f in findings)


def test_l13_blocks_an_open_r30_integrity_finding(legacy_status):
    legacy_status(found=True, status="final", reasons=[], integrity_current=True,
                  integrity_findings=[{"issue": "a KPI number maps to no claim"}])
    assert any("integrity finding" in f.issue for f in fired(LawId.L13, build(_legacy_rows())))


def test_l13_blocks_a_package_with_no_current_integrity_report(legacy_status):
    legacy_status(found=True, status="final", reasons=[], integrity_current=False, integrity_findings=[])
    assert any("no current integrity report" in f.issue for f in fired(LawId.L13, build(_legacy_rows())))


def test_l13_passes_a_final_r30_package(legacy_status):
    legacy_status(found=True, status="final", reasons=[], integrity_current=True, integrity_findings=[])
    assert fired(LawId.L13, build(_legacy_rows())) == []


def test_l13_says_nothing_about_an_engagement_with_no_legacy_work(clean):
    """No engagement-type switch: a registry that commissioned no r30 run has
    no legacy ids to read, and the law never opens a database."""
    from app.engine.gates.laws import legacy_request_ids

    assert legacy_request_ids(clean) == []
    assert fired(LawId.L13, clean) == []


# ===========================================================================
# L14 - the client's own words, rewritten
# ===========================================================================

REWRITTEN = CLIENT_SENTENCE.replace("northern depots", "Northern Depot Network")


def test_l14_blocks_a_client_quote_a_mapping_rewrote(tmp_path, clean):
    """MF2.6 on the page. A canonical mapping that reached inside the quote
    leaves an attribution standing behind words the client never said."""
    page = f'"{REWRITTEN}" {chr(8212)} {statements.CLIENT_STATED_SUFFIX} (as of 2026-01-31).'
    findings = fired(LawId.L14, clean, [artifact(tmp_path, page, view=clean)])
    assert len(findings) == 1
    assert "not what any confirmed client fact records" in findings[0].issue


def test_l14_passes_the_verbatim_quote(tmp_path, clean):
    assert fired(LawId.L14, clean, [artifact(tmp_path, claim(clean, "FCT-1"), view=clean)]) == []


def test_l14_blocks_an_attribution_with_no_quotation(tmp_path, clean):
    page = f"The depots move a lot of parcels, {statements.CLIENT_STATED_SUFFIX}."
    assert any("without quoting" in f.issue
               for f in fired(LawId.L14, clean, [artifact(tmp_path, page, view=clean)]))


def test_l14_blocks_a_consumed_client_fact_that_never_reached_the_page(tmp_path):
    rows = base_rows()
    rows.append(_entity(Kind.WORK_PRODUCT, WorkProductPayload(
        product_id="brief", title="Decision Brief", planned_because="mandatory",
        section_ids=("s1",), consumes=("FCT-1",)), eid="WPR-1"))
    view = build(rows)
    page = "What the evidence shows\nThe depots are busy."
    findings = fired(LawId.L14, view, [artifact(tmp_path, page, view=view)])
    assert any("its words are not on the page" in f.issue for f in findings)


def test_l14_line_breaks_do_not_break_a_quote(tmp_path, clean):
    """A PDF breaks a sentence wherever the line ends; the law reads the page
    with whitespace normalised, so a quote split across two lines is still the
    client's sentence."""
    rendered = claim(clean, "FCT-1")
    broken = rendered.replace(" a week ", " a week\n")
    assert fired(LawId.L14, clean, [artifact(tmp_path, broken, view=clean)]) == []


# ===========================================================================
# How the laws are read
# ===========================================================================

def test_a_finding_carries_the_law_that_raised_it(tmp_path, clean):
    view = build(_conflict_rows(material=False))
    f = fired(LawId.L1, view)[0]
    assert f.as_dict()["law"] == LawId.L1.value
    assert f.as_dict()["source"] == "engine.integrity"
    assert f.blocks_final is True


def test_run_all_stamps_the_law_s_own_blocking_state(clean):
    """`Law.blocks_final` decides, not the finding: a law cannot be softened
    by the wording of one of its findings."""
    from app.engine.types import Finding, Severity

    soft = Law(LawId.L1, lambda view, artifacts: [
        Finding(law=LawId.L1.value, where="x", issue="i", fix="f", severity=Severity.LOW,
                blocks_final=False)])
    registry = type(LAWS)()
    registry.register(soft)
    assert registry.run_all(clean, ())[0].blocks_final is True


def test_the_gate_never_reads_an_engagement_type():
    """Universality, mechanically: no law branches on a business, a sector or
    a deliverable name. The only strings a law compares against are law ids
    and the closed enums types.py declares."""
    import ast

    source = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "app", "engine", "gates", "laws.py")
    tree = ast.parse(open(source, encoding="utf-8").read())
    banned = {"blueprint", "technical", "operations", "engagement_type", "industry", "sector"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert not (set(node.value.lower().split()) & banned), node.value
