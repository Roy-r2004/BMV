"""C15 regulated: app/engine/synthesis/regulated.py -- the two-stage regulated
screen (design 9.6; spec section 7: regulated or licensed advice is
identified and routed for qualified review rather than invented).

Laws pinned here, each with the mutation that kills it:

  * only the literal not_licensed clears a claim; a hedge keeps the matter
    regulated               (mutation: accept 'probably not licensed')
  * a verifier outage keeps the matter regulated and routed - never silently
    unregulated             (mutation: remove the outage branch)
  * the screen runs over the candidate kinds unconditionally, with zero
    issue nodes in the registry (mutation: run the screen only via
    issue-tree binding)

plus: a classifier outage raises rather than returning 'nothing found'; a
licensed recommendation cannot be APPROVED (I4 at the registry door) and is
listed by licensed_recommendations(), not as a recommendation; the constant
CANNOT_ANSWER_STATEMENT renders unchanged; the withheld interpretation is
recorded verbatim; routing is a visible SYSTEM transition in lineage; a
re-run does not stack duplicate matters on one wording.
"""
from __future__ import annotations

import json

import pytest

from app.engine import types as T
from app.engine.llm import StructuredFailure
from app.engine.registry import RegistryError
from app.engine.synthesis.regulated import (
    ADVISER_CLASS, CLASSIFIER_PURPOSE, SCREEN_KINDS, VERIFIER_PURPOSE,
    screen_candidates, screen_synthesis,
)
from app.engine.templating import CLEAR_VERDICT

K = T.Kind
S = T.Status
WORDING = "Move the workshop staff onto annualised-hours contracts"
DOMAIN = T.RegulatedDomain.EMPLOYMENT_LAW


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------

def _prov(actor: T.Actor = T.Actor.PARTNER) -> T.Provenance:
    return T.Provenance(actor=actor, actor_ref=f"{actor.value}:1")


def _ent(kind: K, payload, status: S = S.PROPOSED) -> T.Entity:
    return T.make_entity(kind=kind, engagement_id="E-1", payload=payload, provenance=_prov(),
                         confidence=T.Confidence(None), relevance=T.Relevance("DEC-1", 0.5, ""),
                         relation=T.RelationToCentralDecision.INFORMS, status=status)


def add_rec(reg, statement: str = WORDING) -> T.Entity:
    p = T.RecommendationPayload(statement=statement, decision_id="DEC-1")
    return reg.apply(T.Add(_ent(K.RECOMMENDATION, p)))


def add_question(reg, text: str = WORDING) -> T.Entity:
    p = T.QuestionPayload(text=text)
    return reg.apply(T.Add(_ent(K.QUESTION, p, status=S.OPEN)))


def claims_json(entity_id: str, domain: str = DOMAIN.value) -> str:
    return json.dumps({"claims": [{"entity_id": entity_id, "domain": domain,
                                   "trigger": "annualised-hours contracts",
                                   "reason": "changes employment terms"}]})


def verdict_json(entity_id: str, verdict: str) -> str:
    return json.dumps({"entity_id": entity_id, "verdict": verdict, "reason": "r", "cited_ids": []})


def run(reg, fake_provider, classifier, verifier):
    provider = fake_provider(script={CLASSIFIER_PURPOSE: classifier, VERIFIER_PURPOSE: verifier})
    return screen_synthesis(reg, provider), provider


# ---------------------------------------------------------------------------
# the literal, and only the literal, clears a claim
# ---------------------------------------------------------------------------

def test_literal_not_licensed_clears(registry, fake_provider):
    """Negative control: the exact literal refutes the claim - no matter, no
    flag, the clearance recorded."""
    reg = registry()
    rec = add_rec(reg)
    result, _ = run(reg, fake_provider, [claims_json(rec.id)], [verdict_json(rec.id, CLEAR_VERDICT)])
    assert result.matters == ()
    assert result.flagged == ()
    assert result.cleared == ((rec.id, DOMAIN.value),)
    assert reg.query(K.REGULATED_MATTER) == []
    assert reg.get(rec.id).payload.licensed_interpretation is False


@pytest.mark.parametrize("hedge", [
    "probably not licensed",            # the named mutation's target
    "not licensed",                     # the words without the literal form
    "not_licensed in most cases",       # the literal buried in a hedge
    "NOT_LICENSED",                     # case is part of the literal
    "licensed",
])
def test_anything_but_the_literal_keeps_regulated(registry, fake_provider, hedge):
    reg = registry()
    rec = add_rec(reg)
    result, _ = run(reg, fake_provider, [claims_json(rec.id)], [verdict_json(rec.id, hedge)])
    assert len(result.matters) == 1
    m = result.matters[0]
    assert m.kind == K.REGULATED_MATTER and m.status == S.ROUTED
    assert m.payload.domain == DOMAIN
    assert result.cleared == ()


def test_literal_about_a_different_candidate_clears_nothing(registry, fake_provider):
    """A verdict is a verdict on the claimed candidate; the literal on some
    other id refutes nothing."""
    reg = registry()
    rec = add_rec(reg)
    result, _ = run(reg, fake_provider, [claims_json(rec.id)], [verdict_json("REC-99", CLEAR_VERDICT)])
    assert len(result.matters) == 1 and result.cleared == ()


# ---------------------------------------------------------------------------
# outages: the screen fails closed, never silently unregulated
# ---------------------------------------------------------------------------

def test_verifier_outage_routes_the_matter(registry, fake_provider):
    """A provider error at stage 2 is not a refutation: the matter is created
    and ROUTED, with no model call to cite for the verdict that never came."""
    reg = registry()
    rec = add_rec(reg)
    result, _ = run(reg, fake_provider, [claims_json(rec.id)], [RuntimeError("provider outage")])
    assert len(result.matters) == 1
    m = result.matters[0]
    assert m.status == S.ROUTED
    assert m.provenance.model_call_id is None
    assert rec.id in m.payload.touches
    assert result.flagged == (rec.id,)


def test_verifier_schema_failure_routes_the_matter(registry, fake_provider):
    """Unparseable prose is the same non-answer as an outage: structured_call
    exhausts its one retry and the claim stands."""
    reg = registry()
    rec = add_rec(reg)
    result, _ = run(reg, fake_provider, [claims_json(rec.id)], ["no json here", "still no json"])
    assert len(result.matters) == 1 and result.matters[0].status == S.ROUTED


def test_classifier_outage_raises_never_silently_unregulated(registry, fake_provider):
    """With no stage-1 claims there is nothing to keep regulated, so an empty
    result would be exactly the silent under-routing the screen closes: the
    failure propagates and the caller knows the screen did not run."""
    reg = registry()
    add_rec(reg)
    provider = fake_provider(script={CLASSIFIER_PURPOSE: [RuntimeError("provider outage")]})
    with pytest.raises(StructuredFailure):
        screen_synthesis(reg, provider)
    assert reg.query(K.REGULATED_MATTER) == []


# ---------------------------------------------------------------------------
# the touched recommendation: flagged, blocked, listed as licensed
# ---------------------------------------------------------------------------

def test_touched_recommendation_is_flagged_licensed(registry, fake_provider):
    reg = registry()
    rec = add_rec(reg)
    result, _ = run(reg, fake_provider, [claims_json(rec.id)], [verdict_json(rec.id, "licensed")])
    assert result.flagged == (rec.id,)
    now = reg.get(rec.id)
    assert now.payload.licensed_interpretation is True
    # The flag moves ownership: the info type is re-derived at write, so the
    # registry, not a renderer, holds the block.
    assert now.info_type == T.InfoType.LICENSED_INTERPRETATION
    assert now.authority == T.Authority.QUALIFIED_PROFESSIONAL
    assert result.matters[0].id in now.provenance.derived_from
    assert [r.id for r in reg.licensed_recommendations()] == [rec.id]


def test_licensed_recommendation_cannot_be_approved(registry, fake_provider):
    """I4 at the registry door: even the decision owner cannot APPROVE advice
    that needs a licence; the refusal is the licensed law, not a supports
    technicality."""
    reg = registry()
    rec = add_rec(reg)
    run(reg, fake_provider, [claims_json(rec.id)], [verdict_json(rec.id, "licensed")])
    with pytest.raises(RegistryError) as exc:
        reg.apply(T.SetStatus(rec.id, S.APPROVED,
                              by=T.Provenance(actor=T.Actor.DECISION_OWNER, actor_ref="decision_owner:1")))
    assert exc.value.invariant == "I4"


def test_question_gets_a_matter_but_no_flag(registry, fake_provider):
    """Only recommendations carry the licensed flag; a touched question is
    routed via its matter and stays a question."""
    reg = registry()
    q = add_question(reg)
    result, _ = run(reg, fake_provider, [claims_json(q.id)], [verdict_json(q.id, "licensed")])
    assert len(result.matters) == 1
    assert q.id in result.matters[0].payload.touches
    assert result.flagged == ()
    assert reg.get(q.id).status == S.OPEN


# ---------------------------------------------------------------------------
# the matter itself: constant sentence, withheld interpretation, lineage
# ---------------------------------------------------------------------------

def test_constant_sentence_and_withheld_interpretation(registry, fake_provider):
    reg = registry()
    rec = add_rec(reg)
    result, _ = run(reg, fake_provider, [claims_json(rec.id)], [verdict_json(rec.id, "licensed")])
    p = result.matters[0].payload
    # The sentence is the constant, byte for byte: it is the one thing the
    # engine says about a matter, and no producer may reword it.
    assert p.cannot_answer_statement == T.CANNOT_ANSWER_STATEMENT
    # The exact interpretation refused, not a paraphrase (S11).
    assert p.withheld_interpretation == WORDING
    assert p.adviser_class == ADVISER_CLASS[DOMAIN]
    assert p.why_regulated != ""


def test_routing_is_a_visible_system_transition(registry, fake_provider):
    """Born PROPOSED, then ROUTED by SYSTEM: two rows in lineage, so the
    handover is a recorded act, not a birthmark."""
    reg = registry()
    rec = add_rec(reg)
    result, _ = run(reg, fake_provider, [claims_json(rec.id)], [verdict_json(rec.id, "licensed")])
    m = result.matters[0]
    history = reg.lineage(m.id)
    assert [r.status for r in history] == [S.PROPOSED, S.ROUTED]
    assert history[-1].confirmed_by == "regulated_screen"
    assert m.provenance.actor == T.Actor.SYSTEM
    assert reg.unrouted_regulated_matters() == []
    assert m.id in reg.live_summary()["regulated_matters"]


# ---------------------------------------------------------------------------
# the screen is unconditional and idempotent
# ---------------------------------------------------------------------------

def test_screen_runs_with_zero_issue_nodes(registry, fake_provider):
    """The screen is not bound to the issue tree: a registry with no ISSUE at
    all still gets both stages and the matter."""
    reg = registry()
    rec = add_rec(reg)
    assert reg.live(K.ISSUE) == []
    result, provider = run(reg, fake_provider, [claims_json(rec.id)], [verdict_json(rec.id, "licensed")])
    assert [c.purpose for c in provider.calls] == [CLASSIFIER_PURPOSE, VERIFIER_PURPOSE]
    assert len(result.matters) == 1


def test_ingestion_screen_covers_new_candidates(registry, fake_provider):
    """screen_candidates: the ingestion entry point screens what was just
    written, by kind, ignoring non-screen kinds in the batch."""
    reg = registry()
    rec = add_rec(reg)
    other = reg.apply(T.Add(_ent(K.BUSINESS_CONTEXT, T.BusinessContextPayload(text="a machine shop"))))
    provider = fake_provider(script={CLASSIFIER_PURPOSE: [claims_json(rec.id)],
                                     VERIFIER_PURPOSE: [verdict_json(rec.id, "licensed")]})
    result = screen_candidates(reg, provider, [rec, other])
    assert len(result.matters) == 1
    # The non-screen kind never reached the prompt.
    assert other.id not in provider.calls[0].messages[0]["content"]


def test_rerun_does_not_stack_duplicate_matters(registry, fake_provider):
    """Synthesis re-runs every round; a (candidate, domain) an existing live
    matter already covers is not re-claimed, so one wording yields one matter."""
    reg = registry()
    rec = add_rec(reg)
    provider = fake_provider(script={
        CLASSIFIER_PURPOSE: [claims_json(rec.id), claims_json(rec.id)],
        VERIFIER_PURPOSE: [verdict_json(rec.id, "licensed")],
    })
    first = screen_synthesis(reg, provider)
    second = screen_synthesis(reg, provider)
    assert len(first.matters) == 1 and second.matters == ()
    assert len(reg.query(K.REGULATED_MATTER)) == 1
    # The verifier ran once: the covered claim was dropped before stage 2.
    assert [c.purpose for c in provider.calls].count(VERIFIER_PURPOSE) == 1


def test_unknown_domain_and_unknown_candidate_are_dropped(registry, fake_provider):
    """The closed vocabulary holds at the boundary: a domain outside the enum
    or a claim on an id that was never a candidate creates nothing."""
    reg = registry()
    rec = add_rec(reg)
    bad = json.dumps({"claims": [
        {"entity_id": rec.id, "domain": "astrology", "trigger": "t", "reason": "r"},
        {"entity_id": "REC-404", "domain": DOMAIN.value, "trigger": "t", "reason": "r"},
    ]})
    result, provider = run(reg, fake_provider, [bad], [])
    assert result.matters == () and result.cleared == ()
    assert [c.purpose for c in provider.calls] == [CLASSIFIER_PURPOSE]


def test_screen_kinds_are_the_four_candidate_kinds():
    """The selection surface is a closed Kind list - RECOMMENDATION, OPTION,
    ACTION, QUESTION - never a text filter."""
    assert set(SCREEN_KINDS) == {K.RECOMMENDATION, K.OPTION, K.ACTION, K.QUESTION}
    assert set(ADVISER_CLASS) == set(T.RegulatedDomain)
