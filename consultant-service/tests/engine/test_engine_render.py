"""C18 - registry-owned rendering (design 11).

Each test names the law it pins. The four named mutations for this component
and the test that kills each:

  replace token substitution with a regex rewrite
      -> test_corrections_imports_no_regex_engine
         test_token_substitution_is_literal_not_a_pattern
  remove the assumption label
      -> test_unapproved_assumption_carries_the_proposed_label
  remove client-fact masking
      -> test_client_fact_survives_a_mapping_that_would_rewrite_it
         test_masking_is_what_protects_a_client_fact
  remove sorted section order
      -> test_identical_registry_renders_identical_pdf_bytes
         test_section_entities_are_ordered_by_entity_id

Two follow-up laws and the mutation each kills:

  draw the Contents heading in _S["h1toc"] again (D5)
      -> test_the_contents_page_does_not_list_itself
         test_the_contents_heading_is_invisible_as_a_change
  re-declare ArtifactRef locally instead of importing the laws' class
      -> test_artifact_ref_is_the_laws_class_and_not_a_local_copy
"""
from __future__ import annotations

import ast
import os
import sys
from decimal import Decimal

import pytest

from app.engine.methods.contract import InputSpec
from app.engine.registry import EngagementRegistry
from app.engine.types import (
    Actor,
    ApprovalState,
    AssumptionPayload,
    Confidence,
    DecisionPayload,
    DecisionRole,
    Dimensions,
    EffortClass,
    EvidenceSourcePayload,
    FactBasis,
    FactPayload,
    FillStrategy,
    Kind,
    MeasurePayload,
    Provenance,
    QuestionPayload,
    Quantity,
    RecommendationPayload,
    RelationToCentralDecision,
    Relevance,
    RiskPayload,
    SourceKind,
    Status,
    UnitFamily,
    WorkstreamPayload,
    make_entity,
)
from app.engine.work_products import corrections, statements
from app.engine.work_products.canon_bridge import build_canon, canon_entities
from app.engine.work_products.decl import (
    Always,
    RenderingRules,
    SectionDecl,
    WorkProductDecl,
)
from app.engine.work_products.integrity_record import ArtifactReport, build_integrity_record
from app.engine.work_products.render_csv import render_csv
from app.engine.work_products.render_deck import render_deck, section_bullets
from app.engine.work_products.render_md import (
    RENDERERS,
    narrative_findings,
    render_product,
    section_entities,
    untraceable_number_findings,
)
from app.engine.work_products.render_pdf import (
    DRAFT_STAMP,
    _TOC_HEAD,
    header_label,
    render_markdown_artifact,
    render_pdf,
    strip_engine_chrome,
)
from app.pipeline.registry import PROPOSED_LABEL

from tests.engine.conftest import FIXED_CLOCK


# ---------------------------------------------------------------------------
# One engagement, built once, used by every test. No client is named: the
# strings below are ordinary trade words, and nothing in app/engine reads them.
# ---------------------------------------------------------------------------

CLIENT_SENTENCE = "we move 4200 parcels a week out of the northern depots"
CLIENT_PROGRAMME_SENTENCE = "the Regional Consolidation Programme is already funded"
CANONICAL_PROGRAMME = "Regional Freight Consolidation Programme"
SURFACE_PROGRAMME = "Regional Consolidation Programme"
TURN_TEXT = (f"Good morning. {CLIENT_SENTENCE}, and {CLIENT_PROGRAMME_SENTENCE}. "
             "We need to decide what to do before the peak season.")


def _entity(kind, payload, *, eid, actor=Actor.PARTNER, status=Status.PROPOSED,
            derived=(), locator=None):
    return make_entity(
        kind=kind, engagement_id="E-1", payload=payload,
        provenance=Provenance(actor=actor, actor_ref=f"{actor.value}:1", derived_from=tuple(derived),
                              source_locator=locator, recorded_at=FIXED_CLOCK),
        confidence=Confidence(None), relevance=Relevance("DEC-1", 0.5),
        relation=RelationToCentralDecision.INFORMS, status=status, entity_id=eid)


def _qty(value: str, unit: str, family: UnitFamily, *, as_of: str | None = "2026-01-31",
         precision: int = 0) -> Quantity:
    return Quantity(Decimal(value), unit, family,
                    Dimensions(currency=None, period="2026-01", period_basis="week",
                               scope="the northern depots", as_of=as_of, definition=None),
                    precision)


def sample_rows() -> list:
    """The row history of one small engagement, with explicit ids so it can be
    replayed in any order (which is what the byte-identity law needs)."""
    return [
        _entity(Kind.EVIDENCE_SOURCE, EvidenceSourcePayload(
            name="opening conversation", source_kind=SourceKind.CONVERSATION_TURN,
            text=TURN_TEXT, received_at=FIXED_CLOCK), eid="EVI-1"),
        _entity(Kind.MEASURE, MeasurePayload(name="weekly parcel volume", unit_family=UnitFamily.COUNT,
                                             definition="parcels leaving the depots", confirmed_by_client=True),
                eid="MEA-1", actor=Actor.CLIENT),
        _entity(Kind.DECISION, DecisionPayload(statement="whether to consolidate the depots",
                                               role=DecisionRole.CENTRAL), eid="DEC-1"),
        _entity(Kind.FACT, FactPayload(statement=CLIENT_SENTENCE, basis=FactBasis.CLIENT_STATED,
                                       measure_id="MEA-1", quantity=_qty("4200", "parcels", UnitFamily.COUNT),
                                       topic="volume"),
                eid="FCT-1", actor=Actor.CLIENT, status=Status.CONFIRMED, derived=("EVI-1",)),
        _entity(Kind.FACT, FactPayload(statement=CLIENT_PROGRAMME_SENTENCE, basis=FactBasis.CLIENT_STATED,
                                       topic="programme"),
                eid="FCT-2", actor=Actor.CLIENT, status=Status.CONFIRMED, derived=("EVI-1",)),
        _entity(Kind.ASSUMPTION, AssumptionPayload(
            statement="the peak season starts in the last week of November",
            rationale="prior years", approval=ApprovalState.UNAPPROVED), eid="ASM-1"),
        _entity(Kind.ASSUMPTION, AssumptionPayload(
            statement="the lease on the northern site runs to the end of the year",
            rationale="stated by the client", approval=ApprovalState.APPROVED),
            eid="ASM-2", actor=Actor.CLIENT, status=Status.APPROVED),
        _entity(Kind.QUESTION, QuestionPayload(
            text="Which site holds the picking equipment?", material=True, why="it decides the target site",
            effort=EffortClass.LOOKUP, strategy=FillStrategy.ASK_CLIENT), eid="QST-1", status=Status.OPEN),
        _entity(Kind.QUESTION, QuestionPayload(
            text="What did the depots cost to run last year?", material=False, why="it would size the case",
            effort=EffortClass.DOCUMENT, strategy=FillStrategy.REQUEST_DOCUMENT, unknown=True),
            eid="QST-2", status=Status.OPEN),
        _entity(Kind.RISK, RiskPayload(text=f"The {SURFACE_PROGRAMME} slips past the peak season.",
                                       likelihood="medium", impact="high", who_feels_it="the depots"),
                eid="RSK-1"),
        _entity(Kind.WORKSTREAM, WorkstreamPayload(name=CANONICAL_PROGRAMME,
                                                   purpose="consolidate the depot network"), eid="WKS-1"),
        _entity(Kind.RECOMMENDATION, RecommendationPayload(
            statement="Consolidate onto the northern site", decision_id="DEC-1",
            supports=("FCT-1",), conditional_on=("QST-1",)), eid="REC-1"),
    ]


def build_registry(rows=None, *, order=None):
    rows = list(rows if rows is not None else sample_rows())
    if order is not None:
        rows = [rows[i] for i in order]
    return EngagementRegistry.from_rows("E-1", rows, clock=lambda: FIXED_CLOCK)


@pytest.fixture
def view():
    return build_registry()


def _spec(name: str, kind: Kind, flt=None, *, min_status: Status = Status.PROPOSED) -> InputSpec:
    return InputSpec(name=name, kind=kind, filter=dict(flt or {}), min_status=min_status)


def brief_decl() -> WorkProductDecl:
    """A product whose facts are printed by two sections - which is what makes
    them repeated claims, and therefore statements with tokens."""
    return WorkProductDecl(
        id="test_brief", title_template="Decision Brief: {central_decision}",
        applicability=Always(), mandatory=True,
        sections=(
            SectionDecl("the_decision", "The decision", (_spec("central", Kind.DECISION),),
                        "statement_list", required=True),
            SectionDecl("evidence", "What the evidence shows", (_spec("facts", Kind.FACT),),
                        "statement_list", required=True),
            SectionDecl("evidence_table", "Evidence, with its standing", (_spec("facts", Kind.FACT),),
                        "table", required=True),
            SectionDecl("assumptions", "Assumptions", (_spec("assumptions", Kind.ASSUMPTION),),
                        "statement_list", required=True),
            SectionDecl("risks", "Risks", (_spec("risks", Kind.RISK),), "label_list", required=True),
            SectionDecl("questions", "Open questions", (_spec("questions", Kind.QUESTION),),
                        "label_list", required=True),
            SectionDecl("recommendations", "Recommendations", (_spec("recs", Kind.RECOMMENDATION),),
                        "statement_list", required=True),
        ))


def narrative_decl() -> WorkProductDecl:
    return WorkProductDecl(
        id="test_narrative", title_template="Findings", applicability=Always(), mandatory=True,
        sections=(SectionDecl("story", "What the evidence shows", (_spec("facts", Kind.FACT),),
                              "narrative", required=True),))


def _norm(text: str) -> str:
    return " ".join((text or "").split())


# ===========================================================================
# statement_text: the wording laws
# ===========================================================================

def test_client_fact_is_quoted_verbatim_and_attributed(view):
    """S-VERBATIM: the client's own sentence, in quotes, with the label that
    CLIENT_STATED authority renders as (MF2.1)."""
    text = statements.statement_text(view.get("FCT-1"), view)
    assert f'"{CLIENT_SENTENCE}"' in text
    assert statements.CLIENT_STATED_SUFFIX in text
    assert "weekly parcel volume: 4,200 parcels per week" in text


def test_unapproved_assumption_carries_the_proposed_label(view):
    """S-LABEL, and the mutation 'remove the assumption label'."""
    unapproved = statements.statement_text(view.get("ASM-1"), view)
    approved = statements.statement_text(view.get("ASM-2"), view)
    assert unapproved.endswith(PROPOSED_LABEL)
    assert PROPOSED_LABEL not in approved


def test_unknown_renders_the_declared_unknown_text():
    """S-UNKNOWN: a hole prints as unknown_text - it is never defaulted."""
    rules = RenderingRules()
    rows = sample_rows()
    rows = [r for r in rows if r.id != "FCT-1"]
    rows.append(_entity(Kind.FACT, FactPayload(
        statement=CLIENT_SENTENCE, basis=FactBasis.CLIENT_STATED, measure_id="MEA-1",
        quantity=_qty("4200", "parcels", UnitFamily.COUNT, as_of=None)),
        eid="FCT-1", actor=Actor.CLIENT, status=Status.CONFIRMED, derived=("EVI-1",)))
    v = build_registry(rows)

    assert f"as of {rules.unknown_text}" in statements.statement_text(v.get("FCT-1"), v)
    # a question the client answered "don't know" says so rather than vanishing
    assert f"({rules.unknown_text})" in statements.statement_text(v.get("QST-2"), v)


def test_recommendation_stays_conditional_while_its_question_is_open(view):
    text = statements.statement_text(view.get("REC-1"), view)
    assert "conditional on:" in text
    assert "Which site holds the picking equipment?" in text


def test_statement_text_without_a_view_fails_closed(view):
    """No registry to read means the condition stands and the holes stay
    holes: rendering never invents what it cannot look up."""
    text = statements.statement_text(view.get("REC-1"))
    assert "conditional on: QST-1" in text


# ===========================================================================
# Section order and statements
# ===========================================================================

def test_section_entities_are_ordered_by_entity_id():
    """R1, and the mutation 'remove sorted section order'."""
    forward = build_registry()
    shuffled = build_registry(order=list(reversed(range(len(sample_rows())))))
    section = brief_decl().sections[1]
    assert [e.id for e in section_entities(section, forward)] == ["FCT-1", "FCT-2"]
    assert [e.id for e in section_entities(section, shuffled)] == ["FCT-1", "FCT-2"]


def test_a_claim_in_two_sections_becomes_one_statement_with_a_token(view):
    product = render_product(brief_decl(), view)
    of = {d.entity.payload.of_entity_id for d in product.statement_deltas}
    assert {"FCT-1", "FCT-2"} <= of
    # the decision is printed once, so it needs no statement of its own
    assert "DEC-1" not in of


def test_a_claim_consumed_by_two_sections_renders_byte_identically(tmp_path, view):
    """The statement law end to end: one wording, printed twice, identical on
    the extracted page."""
    product = render_product(brief_decl(), view)
    claim = statements.statement_text(view.get("FCT-1"), view)
    assert _norm(product.markdown).count(_norm(claim)) == 2

    ref = render_pdf(product, out_path=str(tmp_path / "brief.pdf"), draft=True)
    assert _norm(ref.extracted_text).count(_norm(claim)) == 2


# ===========================================================================
# Narrative sections (R2 / L6)
# ===========================================================================

def test_a_paraphrase_in_the_narrative_is_a_finding_and_falls_back(view, fake_provider):
    provider = fake_provider(script={"engine:narrative_section": [
        "The depots handle 4200 parcels every week, which makes the case straightforward.",
        "Again, 4200 parcels a week is the volume in question.",
    ]})
    product = render_product(narrative_decl(), view, provider=provider)
    section = product.sections[0]

    assert [f.law for f in section.findings] == ["L6.statement_drift"]
    assert section.model_calls == 2                      # one attempt, one regeneration, then closed
    assert section.body.startswith("- ")                 # the statement list, not the prose
    assert "4200 parcels every week" not in product.markdown


def test_a_narrative_that_only_uses_tokens_is_kept(view, fake_provider):
    tokens = None

    def answer(call):
        # The prompt carries tokens and labels, never a figure: what the model
        # can write is exactly what it was shown.
        assert "4200" not in call.messages[0]["content"]
        return "Taken together, " + " and ".join(tokens) + "."

    product_tokens = render_product(narrative_decl(), view)   # first pass: learn the tokens
    tokens = [d.entity.payload.token for d in product_tokens.statement_deltas]
    provider = fake_provider(script={"engine:narrative_section": [answer]})
    product = render_product(narrative_decl(), view, provider=provider)

    assert product.sections[0].findings == ()
    assert product.sections[0].model_calls == 1
    assert "Taken together," in product.markdown
    assert statements.statement_text(view.get("FCT-1"), view) in product.markdown


def test_narrative_findings_reject_an_unoffered_token():
    findings = narrative_findings("As [[STMT:STA-9]] shows, the case holds.", {"[[STMT:STA-1]]"},
                                  where="p:s")
    assert [f.law for f in findings] == ["L6.statement_drift"]


def test_a_narrative_without_a_provider_is_the_statement_list(view):
    product = render_product(narrative_decl(), view)
    assert product.sections[0].body.startswith("- ")
    assert product.sections[0].model_calls == 0


# ===========================================================================
# Numbers on the page (R3 / L11)
# ===========================================================================

def test_a_number_not_in_the_registry_is_an_untraceable_finding(view):
    findings = untraceable_number_findings("The depots will release 9,999 parcels a week.", view,
                                           where="test_brief")
    assert [f.law for f in findings] == ["L11.untraceable_number"]
    assert untraceable_number_findings("The depots move 4,200 parcels a week.", view,
                                       where="test_brief") == ()


def test_a_rendered_product_traces_every_number_it_prints(view):
    product = render_product(brief_decl(), view)
    assert [f for f in product.findings if f.law == "L11.untraceable_number"] == []


def test_a_number_within_the_tolerance_traces_and_one_outside_does_not(view):
    inside = untraceable_number_findings("about 4,260 parcels", view, where="p",
                                         bounds={"RENDERED_RESTATEMENT_TOLERANCE": 0.005})
    assert inside != ()
    widened = untraceable_number_findings("about 4,260 parcels", view, where="p",
                                          bounds={"RENDERED_RESTATEMENT_TOLERANCE": 0.05})
    assert widened == ()


# ===========================================================================
# corrections.py - the only module that rewrites text
# ===========================================================================

def _corrections_source() -> str:
    import app.engine.work_products.corrections as mod
    return open(mod.__file__, encoding="utf-8").read()


def test_corrections_imports_no_regex_engine():
    """The mutation 'replace token substitution with a regex rewrite'. Broad
    regex replacement is prohibited (spec section 7); the module that is
    allowed to rewrite text is the one module that must not be able to."""
    tree = ast.parse(_corrections_source())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "re" not in imported
    assert "difflib" not in imported and "rapidfuzz" not in imported

    calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert not {c for c in calls if c.startswith("re.")}


def test_token_substitution_is_literal_not_a_pattern():
    """A canonical sentence is data. A regex rewrite would read \\1 as a group
    reference and $ as an anchor; a literal replace prints them."""
    text = "The finding is [[STMT:STA-1]] and nothing else."
    canonical = r"cost fell by 30% (basis \1, ref $0 & co.)"
    out, applied = corrections.substitute_tokens(text, {"[[STMT:STA-1]]": canonical}, where="p:s")
    assert canonical in out
    assert [a.law for a in applied] == [corrections.LAW_TOKEN]


def test_every_substitution_is_a_lineage_record():
    out, applied = corrections.substitute_tokens("a [[STMT:STA-1]] and [[STMT:STA-1]]",
                                                 {"[[STMT:STA-1]]": "X"}, where="p:s")
    assert out == "a X and X"
    assert len(applied) == 2
    assert applied[0].as_dict() == {"where": "p:s", "entity": "[[STMT:STA-1]]",
                                    "law": corrections.LAW_TOKEN, "before": "[[STMT:STA-1]]", "after": "X"}


def test_an_unsubstituted_token_is_reported_never_deleted():
    result = corrections.correct("see [[STMT:STA-7]]", tokens={})
    assert result.text == "see [[STMT:STA-7]]"
    assert result.unresolved_tokens == ("[[STMT:STA-7]]",)


def test_masking_is_what_protects_a_client_fact(view):
    """The mutation 'remove client-fact masking', at the unit that owns it."""
    canon = build_canon(view)
    sentence = f'"{CLIENT_PROGRAMME_SENTENCE}"'
    text = f"{sentence} and separately the {SURFACE_PROGRAMME} needs an owner."

    guarded, applied = corrections.apply_mappings(text, canon, protected=[sentence], where="p:s")
    assert sentence in guarded                                   # the client's words, untouched
    assert f"the {CANONICAL_PROGRAMME} needs an owner" in guarded  # consultant prose, mapped
    assert [a.law for a in applied] == [corrections.LAW_CANON]

    unguarded, _ = corrections.apply_mappings(text, canon, protected=[], where="p:s")
    assert sentence not in unguarded                              # this is the failure masking prevents


def test_client_fact_survives_a_mapping_that_would_rewrite_it(view):
    """MF2.6 through the renderer: the mapping runs on the product and skips
    inside the masked span."""
    product = render_product(brief_decl(), view)
    assert f'"{CLIENT_PROGRAMME_SENTENCE}"' in product.markdown
    assert f"The {CANONICAL_PROGRAMME} slips past the peak season." in product.markdown
    assert corrections.LAW_CANON in {m.law for m in product.mappings}


# ===========================================================================
# canon_bridge
# ===========================================================================

def test_only_named_kinds_reach_the_canon(view):
    kinds = {e.id: e.kind for e in canon_entities(view)}
    # B1: a workstream is a module and a measure is a concept; a fact, a risk
    # and a question are statements, and a statement is never resolved from prose
    assert kinds == {"WKS-1": "module", "MEA-1": "concept"}


def test_a_sentence_is_never_registered_as_a_name(view):
    from app.engine.work_products import canon_bridge

    assert canon_bridge.is_name(CANONICAL_PROGRAMME)
    assert not canon_bridge.is_name("The programme consolidates the depots into one site by June.")
    assert not canon_bridge.is_name(None)


# ===========================================================================
# The PDF (design 11.4)
# ===========================================================================

def test_identical_registry_renders_identical_pdf_bytes(tmp_path):
    """D1, and the mutation 'remove sorted section order': the same rows loaded
    in a different order are the same registry and must be the same bytes."""
    forward = build_registry()
    reversed_rows = build_registry(order=list(reversed(range(len(sample_rows())))))
    assert forward.content_hash() == reversed_rows.content_hash()

    a = render_pdf(render_product(brief_decl(), forward), out_path=str(tmp_path / "a.pdf"), draft=True)
    b = render_pdf(render_product(brief_decl(), reversed_rows), out_path=str(tmp_path / "b.pdf"), draft=True)
    assert a.sha256 == b.sha256
    assert open(a.path, "rb").read() == open(b.path, "rb").read()


def test_presentation_and_inspection_are_clean_on_an_engine_pdf(tmp_path, view):
    """MF2.7: inspect() is called unchanged and passes, because an engine PDF
    is drawn with r30's faces, footer and stamp."""
    from app.pipeline.export_pdf import presentation_findings

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "tools"))
    import inspect_pdf

    product = render_product(brief_decl(), view)
    ref = render_pdf(product, out_path=str(tmp_path / "brief.pdf"), draft=True,
                     subtitle="prepared for the decision owner")

    assert presentation_findings(ref.path) == []
    result = inspect_pdf.inspect(ref.path, expect="draft")
    assert result["failures"] == []
    assert result["draft_stamped_pages"] == result["pages"]


def test_a_released_pdf_carries_no_draft_stamp(tmp_path, view):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "tools"))
    import inspect_pdf

    product = render_product(brief_decl(), view)
    ref = render_pdf(product, out_path=str(tmp_path / "final.pdf"), draft=False)
    assert inspect_pdf.inspect(ref.path, expect="final")["failures"] == []


def test_the_draft_stamp_is_the_string_r30_draws():
    """One spelling of the release state. Two would mean a page that says
    DRAFT and a gate that cannot see it."""
    import app.pipeline.export_pdf as ep

    assert DRAFT_STAMP in open(ep.__file__, encoding="utf-8").read()


def test_the_contents_page_does_not_list_itself(tmp_path, view):
    """D5. `_EngagementDoc` notifies a table-of-contents entry for every
    paragraph styled "h1toc", and r30's own `_toc` styles the word "Contents"
    that way - so the contents page opens by listing itself as entry 1. The
    release gate strips the whole block as front matter and never sees it; the
    client does. The word appears once on that page: as the heading."""
    import pymupdf

    product = render_product(brief_decl(), view)
    ref = render_pdf(product, out_path=str(tmp_path / "brief.pdf"), draft=True)
    doc = pymupdf.open(ref.path)
    try:
        front = doc[0].get_text()
    finally:
        doc.close()

    assert front.count("Contents") == 1
    # and it is a real table of contents, not an empty one: every section of
    # the product is listed under that heading
    for section in product.sections:
        assert section.title in front


def test_the_contents_heading_is_invisible_as_a_change(view):
    """The fix is a style NAME, not a restyle: the heading is drawn exactly as
    r30 draws it, so the page is unchanged and only the notification stops.
    A heading that merely looked different would be a design change smuggled
    in under an integrity fix."""
    from app.pipeline.export_pdf import _S

    assert _TOC_HEAD.name != _S["h1toc"].name          # what afterFlowable reads
    for attr in ("fontName", "fontSize", "textColor", "leading",
                 "spaceBefore", "spaceAfter", "alignment", "leftIndent"):
        assert getattr(_TOC_HEAD, attr) == getattr(_S["h1toc"], attr), attr


def test_artifact_ref_is_the_laws_class_and_not_a_local_copy():
    """One shape for "one rendered file". A renderer that declared its own
    ArtifactRef would hand the gate an object of a different class with the
    same name - the kind of duplicate the r30 lesson S15 exists to prevent."""
    import app.engine.work_products.render_md as md
    from app.engine.gates.laws import ArtifactRef as LawArtifactRef

    assert md.ArtifactRef is LawArtifactRef
    source = open(md.__file__, encoding="utf-8").read()
    assert "class ArtifactRef" not in source


def test_engine_chrome_is_stripped_before_the_semantic_laws_read(tmp_path, view):
    product = render_product(brief_decl(), view)
    ref = render_pdf(product, out_path=str(tmp_path / "brief.pdf"), draft=True)
    assert strip_engine_chrome(f"{header_label(product.title).upper()} {DRAFT_STAMP} body",
                               product.title).strip() == "body"
    assert header_label(product.title).upper() not in ref.extracted_text
    assert DRAFT_STAMP not in ref.extracted_text
    assert "Page 2" not in ref.extracted_text
    # the claims themselves survive the strip
    assert _norm(statements.statement_text(view.get("FCT-1"), view)) in _norm(ref.extracted_text)


def test_a_long_title_is_cut_to_the_header_width():
    long_title = "Decision Brief: " + "whether to consolidate the depots " * 6
    assert header_label(long_title).endswith("...")
    assert len(header_label(long_title)) < len(long_title)


def test_markdown_artifact_hashes_its_own_bytes(tmp_path, view):
    product = render_product(brief_decl(), view)
    ref = render_markdown_artifact(product, out_path=str(tmp_path / "brief.md"))
    assert ref.fmt == "md"
    assert ref.registry_hash == view.content_hash()
    assert open(ref.path, encoding="utf-8").read() == product.markdown


# ===========================================================================
# Deck and CSV
# ===========================================================================

def test_the_deck_builds_from_the_export_pptx_primitives(tmp_path, view):
    from pptx import Presentation

    product = render_product(brief_decl(), view)
    ref = render_deck(product, out_path=str(tmp_path / "deck.pptx"), draft=True,
                      subtitle="prepared for the decision owner")
    deck = Presentation(ref.path)
    text = "\n".join(s.text_frame.text for slide in deck.slides for s in slide.shapes if s.has_text_frame)

    assert len(deck.slides) >= 3                       # cover, at least one section, close
    assert product.title in text
    assert DRAFT_STAMP in text
    assert _norm(statements.statement_text(view.get("FCT-1"), view)[:60]) in _norm(text)
    assert ref.sha256 and ref.fmt == "pptx"


def test_the_deck_paginates_rather_than_dropping_claims():
    from app.engine.work_products.render_deck import BULLETS_PER_SLIDE
    from app.engine.work_products.render_md import RenderedSection

    section = RenderedSection(id="s", title="t", renderer="statement_list",
                              body="\n".join(f"- claim {i}" for i in range(BULLETS_PER_SLIDE * 2 + 1)))
    assert len(section_bullets(section)) == BULLETS_PER_SLIDE * 2 + 1


def test_tabular_sections_ship_as_csv(tmp_path, view):
    import csv as _csv

    product = render_product(brief_decl(), view)
    refs = render_csv(product, out_dir=str(tmp_path))
    assert [r.product_id for r in refs] == ["test_brief"]

    with open(refs[0].path, encoding="utf-8", newline="") as fh:
        rows = list(_csv.reader(fh))
    assert rows[0] == ["Statement", "Status", "Authority"]
    assert any(CLIENT_SENTENCE in r[0] for r in rows[1:])
    # V3: the same bytes twice
    assert refs[0].sha256 == render_csv(product, out_dir=str(tmp_path))[0].sha256


# ===========================================================================
# The Integrity Record (design 11.5)
# ===========================================================================

def test_the_integrity_record_lists_every_unplanned_product_and_the_legacy_block(tmp_path, view):
    from app.engine.work_products.decl import PlanVerdict

    product = render_product(brief_decl(), view)
    ref = render_pdf(product, out_path=str(tmp_path / "brief.pdf"), draft=True)
    unplanned = (PlanVerdict("financial_model", planned=False, because="0 calculated money facts"),
                 PlanVerdict("customer_journeys", planned=False, because="0 customer process steps"))
    legacy = {"r30_request_id": 57, "revision": "57-r30", "status": "final"}

    record = build_integrity_record(
        view, artifacts=(ArtifactReport(ref, pages=3, presentation_findings=()),),
        unplanned=unplanned, findings=product.findings, mappings=product.mappings, legacy=legacy)

    assert [u["product_id"] for u in record["work_products_unplanned"]] == \
        ["financial_model", "customer_journeys"]
    assert record["work_products_unplanned"][0]["because"] == "0 calculated money facts"
    assert record["legacy"] == legacy
    assert record["registry_hash"] == view.content_hash()
    assert record["mappings_applied"] == len(product.mappings)


def test_the_integrity_record_reports_what_is_unknown(view):
    record = build_integrity_record(view)
    assert [q["id"] for q in record["unknowns"]["questions_answered_unknown"]] == ["QST-2"]
    assert [q["id"] for q in record["unresolved_questions"]] == ["QST-1"]
    assert [a["id"] for a in record["assumptions"]["unapproved"]] == ["ASM-1"]
    assert [a["id"] for a in record["assumptions"]["approved"]] == ["ASM-2"]
    assert record["legacy"] is None                     # absent, and said to be absent


def test_an_artifact_from_another_registry_makes_the_record_stale(tmp_path, view):
    """L8's condition: a document that describes another registry does not
    describe this one, whatever it says."""
    product = render_product(brief_decl(), view)
    ref = render_pdf(product, out_path=str(tmp_path / "brief.pdf"), draft=True,
                     registry_hash="0" * 64)
    record = build_integrity_record(view, artifacts=(ArtifactReport(ref),))
    assert record["verification_status"] == "stale"


def test_a_blocking_finding_blocks_the_record(view):
    findings = untraceable_number_findings("we will save 9,999 parcels", view, where="p")
    record = build_integrity_record(view, findings=findings)
    assert record["status"] == "blocked"
    assert len(record["blocked"]) == 1


# ===========================================================================
# Structure
# ===========================================================================

def test_sections_render_in_declaration_order(view):
    """A product's shape is its declaration's, not the registry's write
    order: two loads of one registry produce the same document."""
    decl = brief_decl()
    product = render_product(decl, view)
    assert [s.id for s in product.sections] == [s.id for s in decl.sections]
    other = render_product(decl, build_registry(order=list(reversed(range(len(sample_rows()))))))
    assert [s.id for s in other.sections] == [s.id for s in decl.sections]
    assert other.markdown == product.markdown


def test_every_declared_renderer_has_an_implementation():
    assert set(RENDERERS) == set(SectionDecl.RENDERERS)


def test_engine_render_sources_are_pure_ascii():
    import app.engine.work_products.render_md as mod

    base = os.path.dirname(mod.__file__)
    for name in ("statements.py", "corrections.py", "canon_bridge.py", "render_md.py",
                 "render_pdf.py", "render_deck.py", "render_csv.py", "integrity_record.py"):
        source = open(os.path.join(base, name), encoding="utf-8").read()
        assert all(ord(c) < 128 for c in source), name
