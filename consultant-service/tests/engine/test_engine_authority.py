"""C0 contracts: app/engine/authority.py -- who owns what and who may advance
a status (I1, MF2.1, MF2.2). Pins the tables as data and may_advance as the
one function the registry consults.
"""
from __future__ import annotations

import pytest

from app.engine.authority import (
    APPROVAL_OWNER, AUTHORITY_OF, MAY_CONFIRM, MAY_RESOLVE, may_advance, owner_of, precedence_rank,
    resolution_authority,
)
from app.engine.types import (
    CURRENT_STATE_PRECEDENCE, Actor, Authority, FactBasis, InfoType, Kind, RecordClass, Status,
)

from conftest import sample_entity, sample_payload


# ---------------------------------------------------------------------------
# the authority table (spec section 5) as data
# ---------------------------------------------------------------------------

EXPECTED_AUTHORITY = {
    InfoType.CLIENT_PREFERENCE: Authority.CLIENT,
    InfoType.CLIENT_RECOLLECTION: Authority.CLIENT_STATED,
    InfoType.CURRENT_STATE_FACT: Authority.VERIFIED_RECORD,
    InfoType.EXTERNAL_FACT: Authority.CITED_SOURCE,
    InfoType.ARITHMETIC: Authority.DETERMINISTIC_ENGINE,
    InfoType.CONSULTANT_JUDGEMENT: Authority.CONSULTANT,
    InfoType.LICENSED_INTERPRETATION: Authority.QUALIFIED_PROFESSIONAL,
    InfoType.MATERIAL_TRADE_OFF: Authority.DECISION_OWNER,
    InfoType.PROCESS_RECORD: Authority.PARTNER,
}


def test_authority_of_is_complete_and_exactly_the_spec_table():
    # Mutation "AUTHORITY_OF[ARITHMETIC] = CONSULTANT" is caught here: a
    # consultant would then own arithmetic, which the spec gives to
    # deterministic engines alone.
    assert set(AUTHORITY_OF) == set(InfoType)
    assert dict(AUTHORITY_OF) == EXPECTED_AUTHORITY
    for it in InfoType:
        assert owner_of(it) is EXPECTED_AUTHORITY[it]


def test_every_authority_has_confirmers_and_none_is_confirmed_by_a_model_actor():
    assert set(MAY_CONFIRM) == set(Authority)
    assert all(MAY_CONFIRM[a] for a in Authority)
    # SPECIALIST never confirms anything: its outputs are PROPOSED (S2).
    assert all(Actor.SPECIALIST not in MAY_CONFIRM[a] for a in Authority)
    # A licensed interpretation is confirmed by nobody inside the engine (I4).
    assert MAY_CONFIRM[Authority.QUALIFIED_PROFESSIONAL] == {Actor.QUALIFIED_PROFESSIONAL}
    assert MAY_CONFIRM[Authority.DETERMINISTIC_ENGINE] == {Actor.CALCULATOR}
    assert MAY_CONFIRM[Authority.CLIENT_STATED] == {Actor.CLIENT}


def test_approval_owner_table_is_exactly_mf2_2():
    # Mutation "APPROVAL_OWNER[RECOMMENDATION] gains PARTNER" is caught here
    # and in test_partner_cannot_approve_a_recommendation.
    assert dict(APPROVAL_OWNER) == {
        Kind.RECOMMENDATION: {Actor.DECISION_OWNER, Actor.CLIENT},
        Kind.ASSUMPTION: {Actor.CLIENT},
        Kind.CHARTER: {Actor.CLIENT},
    }
    assert dict(MAY_RESOLVE) == {
        Kind.QUESTION: {Actor.CLIENT, Actor.PARTNER, Actor.SYSTEM},
        Kind.DECISION_REQUIRED: {Actor.CLIENT, Actor.DECISION_OWNER, Actor.QUALIFIED_PROFESSIONAL},
        Kind.REGULATED_MATTER: {Actor.QUALIFIED_PROFESSIONAL},
    }


# ---------------------------------------------------------------------------
# may_advance: CONFIRMED
# ---------------------------------------------------------------------------

def test_client_confirms_a_client_stated_fact_and_nobody_else_does():
    fact = sample_entity(Kind.FACT, sample_payload(Kind.FACT, basis=FactBasis.CLIENT_STATED))
    assert fact.authority == Authority.CLIENT_STATED
    assert may_advance(fact, Status.CONFIRMED, Actor.CLIENT) is True
    for actor in Actor:
        if actor != Actor.CLIENT:
            assert may_advance(fact, Status.CONFIRMED, actor) is False, actor


def test_document_or_calculator_confirms_a_current_state_fact_not_the_client():
    fact = sample_entity(Kind.FACT, sample_payload(Kind.FACT, basis=FactBasis.DOCUMENT_VERIFIED,
                                                   record_class=RecordClass.SYSTEM_OF_RECORD))
    assert may_advance(fact, Status.CONFIRMED, Actor.DOCUMENT)
    assert may_advance(fact, Status.CONFIRMED, Actor.CALCULATOR)
    assert not may_advance(fact, Status.CONFIRMED, Actor.CLIENT)
    assert not may_advance(fact, Status.CONFIRMED, Actor.PARTNER)


def test_only_the_calculator_confirms_arithmetic():
    calc = sample_entity(Kind.FACT, sample_payload(Kind.FACT, basis=FactBasis.CALCULATED, formula="FCT-1 * 12",
                                                   inputs=("FCT-1",)), actor=Actor.CALCULATOR)
    assert calc.authority == Authority.DETERMINISTIC_ENGINE
    assert may_advance(calc, Status.CONFIRMED, Actor.CALCULATOR)
    for actor in (Actor.PARTNER, Actor.METHOD, Actor.SPECIALIST, Actor.CLIENT, Actor.DOCUMENT):
        assert not may_advance(calc, Status.CONFIRMED, actor), actor


def test_client_confirms_preferences_partner_confirms_judgement():
    obj = sample_entity(Kind.OBJECTIVE)
    assert may_advance(obj, Status.CONFIRMED, Actor.CLIENT) and not may_advance(obj, Status.CONFIRMED, Actor.PARTNER)
    hyp = sample_entity(Kind.HYPOTHESIS, actor=Actor.SPECIALIST)
    assert may_advance(hyp, Status.CONFIRMED, Actor.PARTNER) and may_advance(hyp, Status.CONFIRMED, Actor.METHOD)
    assert not may_advance(hyp, Status.CONFIRMED, Actor.SPECIALIST)
    assert not may_advance(hyp, Status.CONFIRMED, Actor.CLIENT)


def test_a_regulated_matter_is_never_confirmed_or_approved_by_an_engine_actor():
    m = sample_entity(Kind.REGULATED_MATTER)
    for actor in Actor:
        assert not may_advance(m, Status.APPROVED, actor), actor
        if actor != Actor.QUALIFIED_PROFESSIONAL:
            assert not may_advance(m, Status.CONFIRMED, actor), actor


# ---------------------------------------------------------------------------
# may_advance: APPROVED (MF2.2 -- confirming is not approving)
# ---------------------------------------------------------------------------

def test_partner_cannot_approve_a_recommendation():
    rec = sample_entity(Kind.RECOMMENDATION)
    assert may_advance(rec, Status.CONFIRMED, Actor.PARTNER)       # the partner may confirm its judgement
    assert not may_advance(rec, Status.APPROVED, Actor.PARTNER)    # and still never approve it
    assert not may_advance(rec, Status.APPROVED, Actor.METHOD)
    assert not may_advance(rec, Status.APPROVED, Actor.SPECIALIST)
    assert may_advance(rec, Status.APPROVED, Actor.DECISION_OWNER)
    assert may_advance(rec, Status.APPROVED, Actor.CLIENT)


def test_only_the_client_approves_assumptions_and_charters():
    for kind in (Kind.ASSUMPTION, Kind.CHARTER):
        e = sample_entity(kind)
        assert may_advance(e, Status.APPROVED, Actor.CLIENT)
        for actor in Actor:
            if actor != Actor.CLIENT:
                assert not may_advance(e, Status.APPROVED, actor), (kind, actor)


@pytest.mark.parametrize("kind", [k for k in Kind if k not in APPROVAL_OWNER], ids=lambda k: k.value)
def test_kinds_outside_the_approval_table_are_never_approved(kind):
    e = sample_entity(kind)
    assert all(not may_advance(e, Status.APPROVED, actor) for actor in Actor)


# ---------------------------------------------------------------------------
# may_advance: RESOLVED, ROUTED, OPEN, REJECTED / WITHDRAWN
# ---------------------------------------------------------------------------

def test_conflict_is_resolved_by_the_authority_it_names():
    c = sample_entity(Kind.CONFLICT, sample_payload(Kind.CONFLICT, authority_required=Authority.DECISION_OWNER))
    assert resolution_authority(c) == Authority.DECISION_OWNER
    assert may_advance(c, Status.RESOLVED, Actor.DECISION_OWNER)
    assert not may_advance(c, Status.RESOLVED, Actor.CLIENT)
    assert not may_advance(c, Status.RESOLVED, Actor.PARTNER)
    c2 = sample_entity(Kind.CONFLICT, sample_payload(Kind.CONFLICT, authority_required=Authority.CLIENT))
    assert may_advance(c2, Status.RESOLVED, Actor.CLIENT) and not may_advance(c2, Status.RESOLVED, Actor.PARTNER)
    with pytest.raises(TypeError):
        resolution_authority(sample_entity(Kind.FACT))


def test_question_resolvers_and_decision_required_resolvers():
    q = sample_entity(Kind.QUESTION)
    assert {a for a in Actor if may_advance(q, Status.RESOLVED, a)} == {Actor.CLIENT, Actor.PARTNER, Actor.SYSTEM}
    d = sample_entity(Kind.DECISION_REQUIRED, sample_payload(Kind.DECISION_REQUIRED, from_authority=Authority.DECISION_OWNER))
    assert may_advance(d, Status.RESOLVED, Actor.DECISION_OWNER)
    assert may_advance(d, Status.RESOLVED, Actor.CLIENT)
    assert not may_advance(d, Status.RESOLVED, Actor.PARTNER)
    assert not may_advance(sample_entity(Kind.FACT), Status.RESOLVED, Actor.PARTNER)


def test_regulated_matter_is_resolved_by_a_qualified_professional_only():
    m = sample_entity(Kind.REGULATED_MATTER)
    assert {a for a in Actor if may_advance(m, Status.RESOLVED, a)} == {Actor.QUALIFIED_PROFESSIONAL}


def test_only_system_or_partner_route_and_only_a_regulated_matter_is_routed():
    # I4: routing happens inside the engine, before anyone outside sees it.
    m = sample_entity(Kind.REGULATED_MATTER)
    assert {a for a in Actor if may_advance(m, Status.ROUTED, a)} == {Actor.SYSTEM, Actor.PARTNER}
    for kind in (Kind.RECOMMENDATION, Kind.QUESTION, Kind.FACT):
        assert not any(may_advance(sample_entity(kind), Status.ROUTED, a) for a in Actor), kind


def test_open_is_set_by_engine_actors_only():
    q = sample_entity(Kind.QUESTION)
    assert {a for a in Actor if may_advance(q, Status.OPEN, a)} == {Actor.PARTNER, Actor.SYSTEM, Actor.METHOD, Actor.SPECIALIST}


def test_reject_and_withdraw_by_creator_owner_or_approver():
    rec = sample_entity(Kind.RECOMMENDATION, actor=Actor.SPECIALIST)
    for status in (Status.REJECTED, Status.WITHDRAWN):
        assert may_advance(rec, status, Actor.SPECIALIST)          # the creator
        assert may_advance(rec, status, Actor.PARTNER)             # the owner's confirmer
        assert may_advance(rec, status, Actor.DECISION_OWNER)      # the approver
        assert not may_advance(rec, status, Actor.DOCUMENT)
        assert not may_advance(rec, status, Actor.EXTERNAL_SOURCE)


def test_terminal_and_unknown_targets_are_never_advanced_to():
    e = sample_entity(Kind.FACT)
    assert not any(may_advance(e, Status.SUPERSEDED, a) for a in Actor)
    assert not any(may_advance(e, Status.PROPOSED, a) for a in Actor)


# ---------------------------------------------------------------------------
# precedence among sources of one current-state fact
# ---------------------------------------------------------------------------

def test_precedence_rank_orders_records_above_the_client_above_inference():
    sor = sample_entity(Kind.FACT, sample_payload(Kind.FACT, basis=FactBasis.DOCUMENT_VERIFIED, record_class=RecordClass.SYSTEM_OF_RECORD))
    corr = sample_entity(Kind.FACT, sample_payload(Kind.FACT, basis=FactBasis.DOCUMENT_VERIFIED, record_class=RecordClass.CORRESPONDENCE))
    said = sample_entity(Kind.FACT, sample_payload(Kind.FACT, basis=FactBasis.CLIENT_STATED))
    opinion = sample_entity(Kind.FACT, sample_payload(Kind.FACT, basis=FactBasis.DOCUMENT_VERIFIED, record_class=RecordClass.OPINION))
    inferred = sample_entity(Kind.FACT, sample_payload(Kind.FACT, basis=FactBasis.INFERRED))
    ranks = [precedence_rank(e, None) for e in (sor, corr, said, opinion, inferred)]
    assert ranks == sorted(ranks) and len(set(ranks)) == 5
    assert ranks[0] == 0 and ranks[-1] == len(CURRENT_STATE_PRECEDENCE) - 1


def test_precedence_rank_is_none_when_it_cannot_be_known():
    # An unknown record class is not a low rank: absence stays absence.
    unknown = sample_entity(Kind.FACT, sample_payload(Kind.FACT, basis=FactBasis.DOCUMENT_VERIFIED, record_class=RecordClass.UNKNOWN))
    assert precedence_rank(unknown, None) is None
    assert precedence_rank(sample_entity(Kind.FACT, sample_payload(Kind.FACT, basis=FactBasis.DOCUMENT_VERIFIED)), None) is None
    extracted = sample_entity(Kind.FACT, sample_payload(Kind.FACT, basis=FactBasis.DOCUMENT_EXTRACTED, record_class=RecordClass.SYSTEM_OF_RECORD))
    assert precedence_rank(extracted, None) is None       # unverified: it has no rank yet
    assert precedence_rank(sample_entity(Kind.FACT, sample_payload(Kind.FACT, basis=FactBasis.CALCULATED, formula="a", inputs=("FCT-1",)), actor=Actor.CALCULATOR), None) is None
    assert precedence_rank(sample_entity(Kind.OBJECTIVE), None) is None
