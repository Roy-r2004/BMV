"""C1 registry: app/engine/registry.py -- the append-only, hash-addressed
engagement registry and its invariants I1-I8, the read side, the gate
queries, materiality and the scoped view.

Every refusal test uses a delta that ONLY the named branch can refuse (an
actor the authority tables would otherwise allow, a status no other law
gates), so deleting that branch lets the delta land and the test fails; every
refusal has a legal twin that must land (negative control). The mutations the
work breakdown names are noted where they are caught.
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import replace

import pytest

from app.engine import types as T
from app.engine.registry import SUPERSEDED_BY_RECORD, EngagementRegistry, RegistryView, ScopedView
from app.engine.types import (
    FILTERABLE_FIELDS, ID_PREFIX, TERMINAL_STATUSES, Actor, Add, Authority, ConflictKind, DecisionRole, FactBasis,
    InfoType, Kind, RegistryError, RelationToCentralDecision, SetStatus, Status, Supersede,
)

from conftest import FIXED_CLOCK, sample_payload

K = Kind
S = Status
EID = "E-1"
TURN = "We have 214 employees and revenue of EUR 48.2M in FY25."
DOC = "Payroll register, December: 219 employees on permanent contracts."
INFORMS = RelationToCentralDecision.INFORMS
DEFINES = RelationToCentralDecision.DEFINES


# ---------------------------------------------------------------------------
# builders: every entity through make_entity, every write through apply()
# ---------------------------------------------------------------------------

def prov(actor: Actor, ref: str | None = None, derived=(), locator: str | None = None) -> T.Provenance:
    return T.Provenance(actor=actor, actor_ref=ref or f"{actor.value}:1", derived_from=tuple(derived),
                        source_locator=locator)


def ent(kind: Kind, payload, actor: Actor = Actor.PARTNER, ref: str | None = None, *, derived=(),
        status: Status = S.PROPOSED, relation: RelationToCentralDecision = INFORMS, entity_id: str = "",
        labels=(), engagement_id: str = EID, locator: str | None = None) -> T.Entity:
    return T.make_entity(kind=kind, engagement_id=engagement_id, payload=payload,
                         provenance=prov(actor, ref, derived, locator), confidence=T.Confidence(None),
                         relevance=T.Relevance(None), relation=relation, status=status, entity_id=entity_id,
                         labels=tuple(labels))


def heads(value: str) -> T.Quantity:
    return T.Quantity(value, "heads", T.UnitFamily.COUNT)


def add_turn(reg, text: str = TURN, n: int = 1):
    p = T.EvidenceSourcePayload(name=f"turn {n}", source_kind=T.SourceKind.CONVERSATION_TURN, text=text)
    return reg.apply(Add(ent(K.EVIDENCE_SOURCE, p, Actor.CLIENT, f"client:turn:{n}")))


def add_document(reg, text: str = DOC):
    p = T.EvidenceSourcePayload(name="payroll register", source_kind=T.SourceKind.DOCUMENT,
                                record_class=T.RecordClass.SYSTEM_OF_RECORD, record_class_confirmed_by_client=True,
                                sha256="ab" * 32, byte_size=len(text), text_ref="doc-1")
    doc = reg.apply(Add(ent(K.EVIDENCE_SOURCE, p, Actor.CLIENT, "client:upload:1")))
    reg.register_source_text(doc.id, text)
    return doc


def client_fact(reg, turn, statement: str = "We have 214 employees", *, status: Status = S.PROPOSED,
                actor: Actor = Actor.PARTNER, measure_id: str | None = None, relation=INFORMS, entity_id: str = ""):
    p = T.FactPayload(statement, FactBasis.CLIENT_STATED, measure_id=measure_id, quantity=heads("214"))
    return reg.apply(Add(ent(K.FACT, p, actor, derived=(turn.id,), locator=statement, status=status,
                             relation=relation, entity_id=entity_id)))


def confirm(reg, e, actor: Actor = Actor.CLIENT, ref: str | None = None):
    return reg.apply(SetStatus(e.id, S.CONFIRMED, prov(actor, ref)))


def add_decision(reg, role: DecisionRole = DecisionRole.CENTRAL, statement: str = "Which cost base to cut?"):
    return reg.apply(Add(ent(K.DECISION, T.DecisionPayload(statement, role), relation=DEFINES)))


def add_rec(reg, dec, supports=(), *, status: Status = S.PROPOSED, actor: Actor = Actor.PARTNER,
            licensed: bool = False):
    p = T.RecommendationPayload("Renegotiate the supply contract", dec.id, supports=tuple(supports),
                                licensed_interpretation=licensed)
    return reg.apply(Add(ent(K.RECOMMENDATION, p, actor, derived=tuple(supports), status=status)))


def add_calc(reg, inputs, formula: str | None, *, actor: Actor = Actor.CALCULATOR, status: Status = S.PROPOSED):
    ids = tuple(i.id for i in inputs)
    p = T.FactPayload("428 heads", FactBasis.CALCULATED, quantity=heads("428"), formula=formula, inputs=ids)
    return reg.apply(Add(ent(K.FACT, p, actor, "calculator", derived=ids, status=status)))


def add_conflict(reg, conclusions, *, kind: ConflictKind = ConflictKind.VALUE, relation=INFORMS,
                 material: bool = False, authority: Authority = Authority.CLIENT):
    concl = tuple(T.ConflictConclusion(c.id, f"conclusion {i}") for i, c in enumerate(conclusions))
    p = T.ConflictPayload(kind, "MEA-1", concl, relation, authority, material=material)
    return reg.apply(Add(ent(K.CONFLICT, p, Actor.SYSTEM, "synthesis", derived=tuple(c.id for c in conclusions),
                             status=S.OPEN)))


def add_assumption(reg, approval: T.ApprovalState = T.ApprovalState.UNAPPROVED, text: str = "attrition stays flat"):
    return reg.apply(Add(ent(K.ASSUMPTION, T.AssumptionPayload(text, approval=approval))))


def add_question(reg, *, material: bool, value: float | None, unknown: bool = False):
    p = T.QuestionPayload("q", material=material, value=value, unknown=unknown)
    return reg.apply(Add(ent(K.QUESTION, p, status=S.OPEN)))


def refused(reg, delta, invariant: str) -> RegistryError:
    """apply() raises the named invariant and leaves no row behind."""
    n = len(reg.rows())
    with pytest.raises(RegistryError) as ei:
        reg.apply(delta)
    assert ei.value.invariant == invariant, str(ei.value)
    assert len(reg.rows()) == n, "a refused delta must leave no trace"
    return ei.value


def _forged(e: T.Entity, **overrides) -> T.Entity:
    """An Entity assembled without __post_init__: the shape of a row that did
    not come through make_entity (a hand-built object, a mis-migrated JSON
    row), which is the only way a producer could choose its own authority."""
    f = object.__new__(T.Entity)
    for fld in dataclasses.fields(T.Entity):
        object.__setattr__(f, fld.name, overrides.get(fld.name, getattr(e, fld.name)))
    return f


# ---------------------------------------------------------------------------
# I1: a status advances only by an actor the tables allow
# ---------------------------------------------------------------------------

def test_I1_set_status_is_refused_for_an_actor_the_tables_do_not_name(registry):
    # Mutation "delete the I1 branch of _set_status": the partner's confirmation lands.
    reg = registry()
    turn = add_turn(reg)
    fact = client_fact(reg, turn)
    for actor in (Actor.PARTNER, Actor.METHOD, Actor.DOCUMENT, Actor.SYSTEM, Actor.DECISION_OWNER):
        refused(reg, SetStatus(fact.id, S.CONFIRMED, prov(actor, f"{actor.value}:1")), "I1")
    refused(reg, SetStatus(fact.id, S.CONFIRMED, prov(Actor.SPECIALIST, "specialist:SPE-1")), "I5")   # I5 speaks first for a specialist
    assert reg.get(fact.id).status is S.PROPOSED and len(reg.lineage(fact.id)) == 1
    # negative control: the client confirms their own recollection, as a new row
    row = confirm(reg, fact, ref="client:turn:2")
    assert row.status is S.CONFIRMED and row.confirmed_by == "client:turn:2"
    assert (row.version, row.supersedes) == (2, 1) and len(reg.lineage(fact.id)) == 2


def test_I1_a_row_written_at_an_accepted_status_is_an_advance_and_is_checked(registry):
    # Mutation "delete the I1 branch of _check_row": a partner-confirmed fact is born confirmed.
    reg = registry()
    turn = add_turn(reg)
    with pytest.raises(RegistryError) as ei:
        client_fact(reg, turn, status=S.CONFIRMED, actor=Actor.PARTNER)
    assert ei.value.invariant == "I1"
    born = client_fact(reg, turn, status=S.CONFIRMED, actor=Actor.CLIENT)       # negative control
    assert born.status is S.CONFIRMED and born.confirmed_by == "client:1" and born.version == 1
    # ROUTED at birth is an advance too: a specialist may not route, the system may
    matter = sample_payload(K.REGULATED_MATTER)
    refused(reg, Add(ent(K.REGULATED_MATTER, matter, Actor.SPECIALIST, "specialist:SPE-1", status=S.ROUTED)), "I1")
    routed = reg.apply(Add(ent(K.REGULATED_MATTER, matter, Actor.SYSTEM, "system", status=S.ROUTED)))
    assert routed.status is S.ROUTED and routed.confirmed_by == "system"
    # a row at a creation status carries no confirmer, whatever the producer wrote
    assert client_fact(reg, turn).confirmed_by is None


def test_I1_supersede_is_not_a_back_door_around_the_approval_table(registry):
    # MF2.2 at the supersede path: the partner may confirm its judgement and still never approve it.
    reg = registry()
    turn = add_turn(reg)
    fact = confirm(reg, client_fact(reg, turn))
    dec = add_decision(reg)
    rec = add_rec(reg, dec, supports=(fact.id,))

    def approved_copy(actor: Actor) -> T.Entity:
        return ent(K.RECOMMENDATION, rec.payload, actor, derived=(fact.id,), status=S.APPROVED, entity_id=rec.id)

    for actor in (Actor.PARTNER, Actor.METHOD, Actor.SPECIALIST):
        with pytest.raises(RegistryError) as ei:
            reg.apply(Supersede(rec.id, approved_copy(actor)))
        assert ei.value.invariant in ("I1", "I5"), actor          # the specialist trips I5 first, by design
    assert reg.get(rec.id).status is S.PROPOSED and reg.get(rec.id).version == 1
    row = reg.apply(Supersede(rec.id, approved_copy(Actor.DECISION_OWNER)))   # negative control
    assert row.status is S.APPROVED and row.version == 3 and row.confirmed_by == "decision_owner:1"


# ---------------------------------------------------------------------------
# I2: client facts remain exact
# ---------------------------------------------------------------------------

def test_I2_a_client_fact_is_a_verbatim_substring_of_the_turn_it_cites(registry):
    # Mutation "delete the I2 substring branch": the restated number lands as the client's words.
    reg = registry()
    turn = add_turn(reg)
    for restated in ("We have 300 employees", "214 staff", "we have 214 employees", ""):
        with pytest.raises(RegistryError) as ei:
            client_fact(reg, turn, restated)
        assert ei.value.invariant == "I2", restated
    assert reg.query(K.FACT) == []
    exact = client_fact(reg, turn, "We have 214 employees")                # negative control
    assert exact.payload.statement in reg.source_text(turn.id)
    assert exact.authority is Authority.CLIENT_STATED and exact.info_type is InfoType.CLIENT_RECOLLECTION


def test_I2_a_client_fact_cites_a_conversation_turn_not_a_document_that_contains_the_words(registry):
    # Mutation "delete the I2 no-turn branch": a recollection is admitted on the strength of a record.
    reg = registry()
    doc = add_document(reg, text="We have 214 employees on the payroll.")
    words = T.FactPayload("We have 214 employees", FactBasis.CLIENT_STATED, quantity=heads("214"))
    refused(reg, Add(ent(K.FACT, words)), "I2")                                     # cites nothing
    refused(reg, Add(ent(K.FACT, words, derived=(doc.id,), locator="We have 214 employees")), "I2")   # cites a document
    turn = add_turn(reg, "We have 214 employees, said the owner.")
    ok = reg.apply(Add(ent(K.FACT, words, derived=(doc.id, turn.id))))         # negative control: a turn is among the citations
    assert ok.status is S.PROPOSED


def test_I2_a_document_verified_fact_quotes_a_verbatim_locator_from_the_document(registry):
    # Mutation "delete the I2 locator branch": a quote the document does not contain is "verified".
    reg = registry()
    doc = add_document(reg)
    verified = T.FactPayload("219 employees on permanent contracts", FactBasis.DOCUMENT_VERIFIED,
                             quantity=heads("219"), record_class=T.RecordClass.SYSTEM_OF_RECORD)
    refused(reg, Add(ent(K.FACT, verified, derived=(doc.id,), locator="219 staff")), "I2")       # not in the text
    refused(reg, Add(ent(K.FACT, verified, derived=(doc.id,), locator=None)), "I2")              # no locator
    refused(reg, Add(ent(K.FACT, verified, derived=(), locator="219 employees")), "I2")           # cites nothing
    turn = add_turn(reg, "219 employees on permanent contracts, I think.")
    refused(reg, Add(ent(K.FACT, verified, derived=(turn.id,), locator="219 employees")), "I2")   # a turn is not a record
    ok = reg.apply(Add(ent(K.FACT, verified, derived=(doc.id,), locator="219 employees on permanent contracts")))
    assert ok.authority is Authority.VERIFIED_RECORD
    # An extracted candidate is not refused for lacking a verified quote: absence
    # is a state the verifier promotes out of, never a defect at the door.
    extracted = T.FactPayload("219 employees", FactBasis.DOCUMENT_EXTRACTED, quantity=heads("219"))
    assert reg.apply(Add(ent(K.FACT, extracted, derived=(doc.id,), locator="219 staff"))).status is S.PROPOSED


def test_I2_only_the_client_or_a_labelled_record_resolution_supersedes_a_client_fact(registry):
    # Mutation "delete the I2 supersede branch": the partner rewrites what the client said.
    reg = registry()
    turn = add_turn(reg)
    doc = add_document(reg)
    fact = confirm(reg, client_fact(reg, turn))

    def same_words(actor: Actor, labels=()) -> T.Entity:
        return ent(K.FACT, fact.payload, actor, derived=(turn.id,), entity_id=fact.id, labels=labels)

    def record(labels=()) -> T.Entity:
        p = T.FactPayload("219 employees on permanent contracts", FactBasis.DOCUMENT_VERIFIED, quantity=heads("219"),
                          record_class=T.RecordClass.SYSTEM_OF_RECORD)
        return ent(K.FACT, p, Actor.DOCUMENT, f"document:{doc.id}", derived=(doc.id,),
                   locator="219 employees on permanent contracts", entity_id=fact.id, labels=labels)

    for actor in (Actor.PARTNER, Actor.METHOD, Actor.SYSTEM, Actor.CALCULATOR):
        refused(reg, Supersede(fact.id, same_words(actor)), "I2")
    refused(reg, Supersede(fact.id, same_words(Actor.PARTNER, labels=(SUPERSEDED_BY_RECORD,))), "I2")   # the label alone is not a record
    refused(reg, Supersede(fact.id, record()), "I2")                                                    # a record without the visible label
    assert reg.get(fact.id).version == 2
    # the visible path: the loser stays in lineage, retired, carrying the label that says why
    row = reg.apply(Supersede(fact.id, record(labels=(SUPERSEDED_BY_RECORD,))))
    assert row.payload.basis is FactBasis.DOCUMENT_VERIFIED and row.authority is Authority.VERIFIED_RECORD
    hist = reg.lineage(fact.id)
    assert [h.status for h in hist] == [S.PROPOSED, S.CONFIRMED, S.SUPERSEDED, S.PROPOSED]
    assert SUPERSEDED_BY_RECORD in hist[2].labels and hist[2].payload.statement == "We have 214 employees"
    assert SUPERSEDED_BY_RECORD in row.labels
    # and the client corrects their own words, on a new turn
    turn2 = add_turn(reg, "Sorry, we have 216 employees.", n=2)
    fact2 = client_fact(reg, turn)
    corrected = reg.apply(Supersede(fact2.id, ent(
        K.FACT, T.FactPayload("we have 216 employees", FactBasis.CLIENT_STATED, quantity=heads("216")),
        Actor.CLIENT, "client:turn:2", derived=(turn2.id,), entity_id=fact2.id)))
    assert corrected.payload.statement == "we have 216 employees" and corrected.version == 3


# ---------------------------------------------------------------------------
# I3: a recommendation is approved only on evidence
# ---------------------------------------------------------------------------

def test_I3_approval_needs_supports_that_are_confirmed_facts_or_approved_assumptions(registry):
    # Mutations "delete an I3 branch": a bare, a proposed-support or a ghost-support recommendation is approved.
    reg = registry()
    turn = add_turn(reg)
    dec = add_decision(reg)
    proposed = client_fact(reg, turn, "We have 214 employees")
    confirmed = confirm(reg, client_fact(reg, turn, "revenue of EUR 48.2M"))
    assumption = add_assumption(reg)

    def approve(rec, actor: Actor = Actor.CLIENT):
        return SetStatus(rec.id, S.APPROVED, prov(actor))

    e = refused(reg, approve(add_rec(reg, dec)), "I3")
    assert "supports" in str(e)
    refused(reg, approve(add_rec(reg, dec, supports=(proposed.id,))), "I3")               # PROPOSED support
    refused(reg, approve(add_rec(reg, dec, supports=("FCT-99",))), "I3")                  # missing support
    refused(reg, approve(add_rec(reg, dec, supports=(confirmed.id, assumption.id))), "I3")   # unapproved assumption
    rejected = confirm(reg, client_fact(reg, turn, "in FY25"))
    reg.apply(SetStatus(rejected.id, S.REJECTED, prov(Actor.CLIENT)))
    refused(reg, approve(add_rec(reg, dec, supports=(rejected.id,))), "I3")               # retired support
    # born approved by the client with a proposed support: I1 lets the client through, I3 does not
    p = T.RecommendationPayload("cut", dec.id, supports=(proposed.id,))
    refused(reg, Add(ent(K.RECOMMENDATION, p, Actor.CLIENT, status=S.APPROVED)), "I3")
    # negative control: a confirmed client fact (the document-less path, MF2.1) and an approved assumption
    reg.apply(SetStatus(assumption.id, S.APPROVED, prov(Actor.CLIENT)))
    good = add_rec(reg, dec, supports=(confirmed.id, assumption.id))
    assert reg.apply(approve(good)).status is S.APPROVED
    assert reg.apply(Add(ent(K.RECOMMENDATION, replace(p, supports=(confirmed.id,)), Actor.CLIENT,
                             status=S.APPROVED))).status is S.APPROVED


# ---------------------------------------------------------------------------
# I4: a licensed interpretation is identified and routed, never answered
# ---------------------------------------------------------------------------

def test_I4_a_regulated_matter_is_never_confirmed_or_approved_even_by_its_own_confirmer(registry):
    # Mutation "delete the I4 branch of _set_status": the adviser's confirmation lands
    # (MAY_CONFIRM[QUALIFIED_PROFESSIONAL] would allow it, so only I4 refuses).
    reg = registry()
    matter = reg.apply(Add(ent(K.REGULATED_MATTER, sample_payload(K.REGULATED_MATTER))))
    refused(reg, SetStatus(matter.id, S.CONFIRMED, prov(Actor.QUALIFIED_PROFESSIONAL, "adviser:1")), "I4")
    for actor in Actor:
        refused(reg, SetStatus(matter.id, S.APPROVED, prov(actor, f"{actor.value}:1")), "I4")
    assert reg.unrouted_regulated_matters() == [matter]
    refused(reg, SetStatus(matter.id, S.ROUTED, prov(Actor.CLIENT)), "I1")               # routing is the engine's act
    routed = reg.apply(SetStatus(matter.id, S.ROUTED, prov(Actor.SYSTEM, "system")))     # negative control
    assert routed.status is S.ROUTED and reg.unrouted_regulated_matters() == []
    assert reg.live_summary()["regulated_matters"] == [matter.id]
    resolved = reg.apply(SetStatus(matter.id, S.RESOLVED, prov(Actor.QUALIFIED_PROFESSIONAL, "adviser:1")))
    assert resolved.status is S.RESOLVED and resolved.confirmed_by == "adviser:1"


def test_I4_a_regulated_matter_is_born_unresolved(registry):
    # Mutation "delete the I4 branch of _check_row": an adviser writes a matter already confirmed.
    reg = registry()
    for status in (S.CONFIRMED, S.RESOLVED):
        refused(reg, Add(ent(K.REGULATED_MATTER, sample_payload(K.REGULATED_MATTER), Actor.QUALIFIED_PROFESSIONAL,
                             "adviser:1", status=status)), "I4")
    born = reg.apply(Add(ent(K.REGULATED_MATTER, sample_payload(K.REGULATED_MATTER))))   # negative control
    assert born.status is S.PROPOSED and born.authority is Authority.QUALIFIED_PROFESSIONAL


def test_I4_a_recommendation_flagged_licensed_cannot_be_approved(registry):
    # Design 9.6: the flag moves the info type, and APPROVAL_OWNER (by kind) would still let the
    # decision owner approve it -- I4 is what refuses.
    reg = registry()
    turn = add_turn(reg)
    fact = confirm(reg, client_fact(reg, turn))
    dec = add_decision(reg)
    licensed = add_rec(reg, dec, supports=(fact.id,), licensed=True)
    assert licensed.authority is Authority.QUALIFIED_PROFESSIONAL and reg.licensed_recommendations() == [licensed]
    refused(reg, SetStatus(licensed.id, S.APPROVED, prov(Actor.DECISION_OWNER)), "I4")
    refused(reg, SetStatus(licensed.id, S.CONFIRMED, prov(Actor.QUALIFIED_PROFESSIONAL, "adviser:1")), "I4")
    plain = add_rec(reg, dec, supports=(fact.id,))                                        # negative control
    assert reg.apply(SetStatus(plain.id, S.APPROVED, prov(Actor.DECISION_OWNER))).status is S.APPROVED
    assert reg.licensed_recommendations() == [licensed]
    reg.apply(SetStatus(licensed.id, S.WITHDRAWN, prov(Actor.PARTNER)))
    assert reg.licensed_recommendations() == []


# ---------------------------------------------------------------------------
# I5: a specialist touches only what it created
# ---------------------------------------------------------------------------

def test_I5_a_specialist_may_not_supersede_or_set_status_on_another_actors_row(registry):
    # Mutations "delete an I5 branch": one specialist rejects or rewrites another's conclusion
    # (the creator's actor class passes may_advance, so only I5 refuses).
    reg = registry()
    dec = add_decision(reg)
    mine = reg.apply(Add(ent(K.HYPOTHESIS, T.HypothesisPayload("margin fell with mix", "ISS-1"),
                             Actor.SPECIALIST, "specialist:SPE-1")))
    theirs = reg.apply(Add(ent(K.HYPOTHESIS, T.HypothesisPayload("margin fell with price", "ISS-1"),
                               Actor.SPECIALIST, "specialist:SPE-2")))
    refused(reg, SetStatus(theirs.id, S.REJECTED, prov(Actor.SPECIALIST, "specialist:SPE-1")), "I5")
    refused(reg, Supersede(theirs.id, ent(K.HYPOTHESIS, replace(theirs.payload, text="mine now"),
                                          Actor.SPECIALIST, "specialist:SPE-1", entity_id=theirs.id)), "I5")
    refused(reg, Supersede(dec.id, ent(K.DECISION, dec.payload, Actor.SPECIALIST, "specialist:SPE-1",
                                       entity_id=dec.id, relation=DEFINES)), "I5")
    refused(reg, SetStatus(dec.id, S.WITHDRAWN, prov(Actor.SPECIALIST, "specialist:SPE-1")), "I5")
    assert reg.get(theirs.id) == theirs and reg.get(dec.id) == dec
    # negative control: its own rows, under its own actor_ref
    own = reg.apply(Supersede(mine.id, ent(K.HYPOTHESIS, replace(mine.payload, verdict="supported"),
                                           Actor.SPECIALIST, "specialist:SPE-1", entity_id=mine.id)))
    assert own.version == 3 and own.payload.verdict == "supported"
    assert reg.apply(SetStatus(mine.id, S.WITHDRAWN, prov(Actor.SPECIALIST, "specialist:SPE-1"))).status is S.WITHDRAWN
    # and the partner, who owns consultant judgement, may retire either
    assert reg.apply(SetStatus(theirs.id, S.REJECTED, prov(Actor.PARTNER))).status is S.REJECTED


# ---------------------------------------------------------------------------
# I6: ids, versions, append-only
# ---------------------------------------------------------------------------

def test_I6_ids_are_assigned_from_ID_PREFIX_name_their_kind_and_never_collide(registry):
    # Mutations "delete an I6 branch": a duplicate id clobbers, a foreign id or engagement is stored.
    reg = registry()
    turn = add_turn(reg)
    assert turn.id == "EVI-1"
    assert (client_fact(reg, turn).id, client_fact(reg, turn).id) == ("FCT-1", "FCT-2")
    assert client_fact(reg, turn, entity_id="FCT-7").id == "FCT-7"
    assert client_fact(reg, turn).id == "FCT-8"           # the counter moved past the explicit id: no clobber
    e = refused(reg, Add(ent(K.FACT, T.FactPayload("We have 214 employees", FactBasis.CLIENT_STATED),
                             derived=(turn.id,), entity_id="FCT-7")), "I6")
    assert "exists" in str(e)
    for bad in ("DEC-9", "FCT-0", "FCT-x", "FCT-", "FCT-08", "fct-9", "9", "FCT9"):
        refused(reg, Add(ent(K.FACT, T.FactPayload("We have 214 employees", FactBasis.CLIENT_STATED),
                             derived=(turn.id,), entity_id=bad)), "I6")
    refused(reg, Add(ent(K.DECISION, T.DecisionPayload("x", DecisionRole.CENTRAL), engagement_id="E-2")), "I6")
    assert client_fact(reg, turn).id == "FCT-9"           # refusals burn no ids
    assert {r.id for r in reg.rows()} == {"EVI-1", "FCT-1", "FCT-2", "FCT-7", "FCT-8", "FCT-9"}
    assert all(ID_PREFIX[r.kind] == r.id.rpartition("-")[0] for r in reg.rows())


def test_I6_every_version_is_a_new_row_and_nothing_is_updated_in_place(registry):
    reg = registry()
    turn = add_turn(reg)
    fact = client_fact(reg, turn)
    snapshot = reg.rows()
    confirm(reg, fact)
    corrected = reg.apply(Supersede(fact.id, ent(
        K.FACT, T.FactPayload("revenue of EUR 48.2M", FactBasis.CLIENT_STATED), Actor.CLIENT, "client:turn:1",
        derived=(turn.id,), entity_id=fact.id)))
    hist = reg.lineage(fact.id)
    assert [(h.version, h.status, h.supersedes) for h in hist] == [
        (1, S.PROPOSED, None), (2, S.CONFIRMED, 1), (3, S.SUPERSEDED, 2), (4, S.PROPOSED, 2)]
    assert hist[2].payload.statement == "We have 214 employees" and hist[3] == corrected
    assert reg.rows()[:2] == snapshot                     # earlier rows are untouched
    assert reg.get(fact.id) == corrected and reg.query(K.FACT) == [corrected]
    copy = reg.rows()
    copy.clear()
    assert len(reg.rows()) == 5                          # rows() hands out a copy
    assert reg.lineage("FCT-9") == []


def test_I6_a_terminal_status_is_a_recorded_transition_never_a_birth(registry):
    # Mutation "delete the I6 born-terminal branch": a row is buried at creation, with no transition to see.
    reg = registry()
    turn = add_turn(reg)
    for status in TERMINAL_STATUSES:
        with pytest.raises(RegistryError) as ei:
            client_fact(reg, turn, status=status)
        assert ei.value.invariant == "I6", status
    fact = client_fact(reg, turn)
    reg.apply(SetStatus(fact.id, S.REJECTED, prov(Actor.CLIENT)))
    e = refused(reg, SetStatus(fact.id, S.CONFIRMED, prov(Actor.CLIENT)), "I6")    # a retired row is not advanced
    assert "supersede" in str(e)
    refused(reg, Supersede(fact.id, ent(K.FACT, fact.payload, Actor.CLIENT, derived=(turn.id,), entity_id=fact.id,
                                        status=S.WITHDRAWN)), "I6")
    revived = reg.apply(Supersede(fact.id, ent(K.FACT, fact.payload, Actor.CLIENT, derived=(turn.id,),
                                               entity_id=fact.id)))                 # negative control
    assert revived.status is S.PROPOSED and revived.version == 4
    assert [h.status for h in reg.lineage(fact.id)] == [S.PROPOSED, S.REJECTED, S.SUPERSEDED, S.PROPOSED]


def test_I6_a_supersession_keeps_the_id_and_the_kind_and_needs_an_existing_row(registry):
    reg = registry()
    turn = add_turn(reg)
    fact = client_fact(reg, turn)
    dec = add_decision(reg)
    copy = lambda entity_id, **kw: ent(K.FACT, fact.payload, Actor.CLIENT, derived=(turn.id,), entity_id=entity_id, **kw)
    refused(reg, Supersede("FCT-42", copy("FCT-42")), "I6")                          # nothing to supersede
    refused(reg, Supersede(fact.id, copy("FCT-2")), "I6")                             # a different id
    refused(reg, Supersede(dec.id, ent(K.OBJECTIVE, T.ObjectivePayload("o"), Actor.CLIENT, entity_id=dec.id)), "I6")
    refused(reg, Supersede(fact.id, copy(fact.id, engagement_id="E-2")), "I6")        # another engagement
    refused(reg, SetStatus("DEC-9", S.CONFIRMED, prov(Actor.PARTNER)), "I6")           # nothing to advance
    assert reg.get(fact.id) == fact and reg.get(dec.id) == dec
    assert reg.apply(Supersede(fact.id, copy(fact.id))).version == 3                  # negative control


# ---------------------------------------------------------------------------
# I7: authority is derived, re-derived at the door and on reload
# ---------------------------------------------------------------------------

def test_I7_the_registry_rederives_authority_and_refuses_a_row_that_chose_its_own(registry):
    # Mutation "delete the I7 branch": a forged owner is stored on write and on reload.
    reg = registry()
    turn = add_turn(reg)
    honest = ent(K.FACT, T.FactPayload("We have 214 employees", FactBasis.CLIENT_STATED), derived=(turn.id,))
    stored = reg.apply(Add(_forged(honest)))                     # control: the forge itself is not what is refused
    assert stored.authority is Authority.CLIENT_STATED
    forgeries = ({"authority": Authority.VERIFIED_RECORD}, {"info_type": InfoType.CURRENT_STATE_FACT},
                 {"authority": Authority.VERIFIED_RECORD, "info_type": InfoType.CURRENT_STATE_FACT},
                 {"authority": Authority.CONSULTANT})
    # the replacement is client-actored so that I2 (only the client supersedes a client fact) is not what refuses
    correction = replace(honest, id=stored.id, provenance=prov(Actor.CLIENT, "client:turn:2", derived=(turn.id,)))
    for over in forgeries:
        refused(reg, Add(_forged(honest, **over)), "I7")
        refused(reg, Supersede(stored.id, _forged(correction, **over)), "I7")
    assert reg.get(stored.id).version == 1
    assert reg.apply(Supersede(stored.id, _forged(correction))).version == 3     # control for the supersede path
    rows = reg.rows()
    for over in forgeries:
        with pytest.raises(RegistryError) as ei:
            EngagementRegistry.from_rows(EID, rows[:-1] + [_forged(rows[-1], **over)])
        assert ei.value.invariant == "I7"
    assert EngagementRegistry.from_rows(EID, rows).content_hash() == reg.content_hash()


# ---------------------------------------------------------------------------
# I8: a calculation carries its arithmetic and its inputs exist
# ---------------------------------------------------------------------------

def test_I8_a_calculated_fact_carries_formula_and_registered_inputs(registry):
    # Mutations "delete an I8 branch": a number with no arithmetic, or arithmetic over a ghost, is stored.
    reg = registry()
    turn = add_turn(reg)
    fact = confirm(reg, client_fact(reg, turn))
    with pytest.raises(RegistryError) as ei:
        add_calc(reg, [fact], formula=None)
    assert ei.value.invariant == "I8"
    with pytest.raises(RegistryError) as ei:
        add_calc(reg, [], formula="2 * 214")
    assert ei.value.invariant == "I8"
    ghost = T.FactPayload("428 heads", FactBasis.CALCULATED, quantity=heads("428"), formula="FCT-99 * 2", inputs=("FCT-99",))
    e = refused(reg, Add(ent(K.FACT, ghost, Actor.CALCULATOR, "calculator")), "I8")
    assert "FCT-99" in str(e)
    assert reg.calculated_facts() == []
    calc = add_calc(reg, [fact], formula=f"{fact.id} * 2")                          # negative control
    assert calc.authority is Authority.DETERMINISTIC_ENGINE and reg.calculated_facts() == [calc]
    assert reg.apply(SetStatus(calc.id, S.CONFIRMED, prov(Actor.CALCULATOR, "calculator"))).status is S.CONFIRMED


# ---------------------------------------------------------------------------
# read side
# ---------------------------------------------------------------------------

def test_query_reads_filterable_fields_only_and_a_text_key_raises(registry):
    reg = registry()
    turn = add_turn(reg)
    fact = client_fact(reg, turn)
    for key in ("text", "statement", "name", "topic", "definition"):
        with pytest.raises(ValueError) as ei:
            reg.query(K.FACT, where={key: "We have 214 employees"})
        assert "non-structural" in str(ei.value) and not isinstance(ei.value, RegistryError)
    with pytest.raises(ValueError):
        reg.query(where={"basis": FactBasis.CLIENT_STATED, "text": "x"})     # one text key poisons the filter
    for key in FILTERABLE_FIELDS:
        reg.query(where={key: None})                                            # every structural key is admitted
    assert reg.query(K.FACT, where={"basis": FactBasis.CLIENT_STATED}) == [fact]
    assert reg.query(K.FACT, where={"basis": "client_stated"}) == [fact]        # member or value: one normaliser
    assert reg.query(K.FACT, where={"basis": [FactBasis.CALCULATED, FactBasis.INFERRED]}) == []
    assert reg.query(K.FACT, where={"basis": (FactBasis.CALCULATED, FactBasis.CLIENT_STATED)}) == [fact]
    assert reg.query(K.FACT, where={"has_quantity": True, "unit_family": T.UnitFamily.COUNT}) == [fact]
    assert reg.query(K.FACT, where={"has_measure": True}) == []
    assert reg.query(where={"source_kind": T.SourceKind.CONVERSATION_TURN}) == [turn]
    assert reg.query(K.FACT, status=S.CONFIRMED) == [] and reg.query(status=S.PROPOSED) == [turn, fact]
    assert reg.query() == [turn, fact] and reg.get("FCT-9") is None


def test_query_returns_latest_versions_and_live_excludes_the_retired(registry):
    reg = registry()
    turn = add_turn(reg)
    kept = client_fact(reg, turn, "We have 214 employees")
    gone = client_fact(reg, turn, "revenue of EUR 48.2M")
    reg.apply(SetStatus(gone.id, S.WITHDRAWN, prov(Actor.PARTNER)))
    confirmed = confirm(reg, kept)
    assert reg.query(K.FACT) == [confirmed, reg.get(gone.id)]
    assert reg.live(K.FACT) == [confirmed] and reg.live() == [turn, confirmed]
    assert reg.query(K.FACT, status=S.WITHDRAWN) == [reg.get(gone.id)]
    with pytest.raises(ValueError):
        reg.live(K.FACT, where={"statement": "x"})


def test_source_text_reads_the_turn_row_or_the_registered_document_text(registry):
    reg = registry()
    turn = add_turn(reg)
    doc = add_document(reg)
    assert reg.source_text(turn.id) == TURN and reg.source_text(doc.id) == DOC
    assert reg.source_text("EVI-9") is None and reg.source_text(turn.id) is not None
    reg.register_source_text("EVI-9", "text registered before its row exists")
    assert reg.source_text("EVI-9").startswith("text registered")
    assert reg.source_texts() == {doc.id: DOC, "EVI-9": "text registered before its row exists"}
    reg.source_texts().clear()
    assert doc.id in reg.source_texts()                                        # a copy
    with pytest.raises(TypeError):
        reg.register_source_text(doc.id, None)


def test_central_decision_is_the_live_central_role(registry):
    reg = registry()
    assert reg.central_decision() is None
    stated = add_decision(reg, DecisionRole.STATED_REQUEST, "build us an app")
    assert reg.central_decision() is None
    central = add_decision(reg)
    assert reg.central_decision() == central and reg.central_decision() != stated
    reg.apply(SetStatus(central.id, S.WITHDRAWN, prov(Actor.PARTNER)))
    assert reg.central_decision() is None


def test_supports_of_and_support_closure_follow_derived_from_and_inputs(registry):
    reg = registry()
    turn = add_turn(reg)
    dec = add_decision(reg)
    base = confirm(reg, client_fact(reg, turn, "We have 214 employees"))
    calc = add_calc(reg, [base], formula=f"{base.id} * 2")
    calc = reg.apply(SetStatus(calc.id, S.CONFIRMED, prov(Actor.CALCULATOR, "calculator")))
    other = client_fact(reg, turn, "revenue of EUR 48.2M")
    assert reg.support_closure() == set()
    rec = add_rec(reg, dec, supports=(calc.id, "FCT-77"))
    assert reg.supports_of(rec.id) == [calc] and reg.supports_of(base.id) == [] and reg.supports_of("REC-9") == []
    assert reg.support_closure() == {calc.id, base.id, turn.id, "FCT-77"}      # inputs, derived_from, and the ghost id
    assert other.id not in reg.support_closure()
    reg.apply(SetStatus(rec.id, S.REJECTED, prov(Actor.PARTNER)))
    assert reg.support_closure() == set()                                       # only live recommendations count


# ---------------------------------------------------------------------------
# content hash: clock-blind, order-blind, reload-stable, moved by every delta
# ---------------------------------------------------------------------------

def script(reg) -> list[str]:
    hashes = [reg.content_hash()]
    turn = add_turn(reg)
    hashes.append(reg.content_hash())
    fact = client_fact(reg, turn)
    hashes.append(reg.content_hash())
    confirm(reg, fact)
    hashes.append(reg.content_hash())
    reg.apply(Supersede(fact.id, ent(K.FACT, T.FactPayload("revenue of EUR 48.2M", FactBasis.CLIENT_STATED),
                                     Actor.CLIENT, "client:turn:1", derived=(turn.id,), entity_id=fact.id)))
    hashes.append(reg.content_hash())
    reg.apply(SetStatus(fact.id, S.WITHDRAWN, prov(Actor.CLIENT)))
    hashes.append(reg.content_hash())
    return hashes


def test_content_hash_ignores_the_clock_and_moves_with_every_delta(registry):
    # Mutation "include recorded_at" is caught by the equality; a delta that leaves the hash
    # unchanged would be caught by the distinctness.
    ticks = iter(f"2026-02-{d:02d}T00:00:00+00:00" for d in range(1, 28))
    fixed, moving = registry(), registry(clock=lambda: next(ticks))
    a, b = script(fixed), script(moving)
    assert a == b
    assert len(set(a)) == len(a) == 6                     # Add, Add, SetStatus, Supersede, SetStatus each moved it
    assert fixed.rows()[0].provenance.recorded_at == FIXED_CLOCK
    assert moving.rows()[0].provenance.recorded_at != moving.rows()[1].provenance.recorded_at
    assert [r.content_hash() for r in fixed.rows()] == [r.content_hash() for r in moving.rows()]
    assert registry().content_hash() == a[0]


def test_content_hash_is_order_blind_and_survives_reload(registry):
    # Mutation "replace sorted() in content_hash with insertion order" is caught here: the same
    # rows written in another order, or reloaded in id order, would hash differently.
    def build(order):
        reg = registry()
        turn = add_turn(reg)
        pieces = {
            "fact": lambda: client_fact(reg, turn, entity_id="FCT-3"),
            "dec": lambda: add_decision(reg),
            "obj": lambda: reg.apply(Add(ent(K.OBJECTIVE, T.ObjectivePayload("halve the cost base"), Actor.CLIENT))),
        }
        for name in order:
            pieces[name]()
        return reg

    a, b = build(("fact", "dec", "obj")), build(("obj", "dec", "fact"))
    assert [r.id for r in a.rows()] != [r.id for r in b.rows()]
    assert a.content_hash() == b.content_hash()
    by_id = sorted(a.rows(), key=lambda r: (r.id, r.version))
    assert [r.id for r in by_id] != [r.id for r in a.rows()]
    assert EngagementRegistry.from_rows(EID, by_id).content_hash() == a.content_hash()
    assert EngagementRegistry.from_rows(EID, a.rows()).content_hash() == a.content_hash()
    assert ScopedView(a, [r.id for r in a.rows()]).content_hash() == a.content_hash()


def test_reload_from_rows_restores_state_history_and_counters(registry):
    reg = registry()
    hashes = script(reg)
    doc = add_document(reg)
    assert reg.content_hash() != hashes[-1]                                     # the document moved it
    wire = [json.loads(json.dumps(r.to_json())) for r in reg.rows()]           # what the store persists
    back = EngagementRegistry.from_rows(EID, [T.Entity.from_json(d) for d in wire], source_texts=reg.source_texts())
    assert back.content_hash() == reg.content_hash()
    assert back.rows() == reg.rows() and back.lineage("FCT-1") == reg.lineage("FCT-1")
    assert back.get("FCT-1") == reg.get("FCT-1") and back.live_summary() == reg.live_summary()
    assert back.source_text(doc.id) == DOC and back.source_text("EVI-1") == TURN
    assert back.rows()[0].provenance.recorded_at == FIXED_CLOCK                # kept as stored, not restamped
    turn = back.get("EVI-1")
    assert client_fact(back, turn).id == "FCT-2"                               # the counter continues
    assert add_document(back).id == "EVI-3"
    # and the same rows given in id order rebuild the same latest state
    again = EngagementRegistry.from_rows(EID, sorted(reg.rows(), key=lambda r: (r.id, r.version)))
    assert again.get("FCT-1") == reg.get("FCT-1") and again.content_hash() == reg.content_hash()


def test_reload_refuses_foreign_or_duplicate_rows(registry):
    reg = registry()
    script(reg)
    rows = reg.rows()
    with pytest.raises(RegistryError) as ei:
        EngagementRegistry.from_rows("E-2", rows)
    assert ei.value.invariant == "I6"
    with pytest.raises(RegistryError) as ei:
        EngagementRegistry.from_rows(EID, rows + [rows[0]])
    assert ei.value.invariant == "I6"
    with pytest.raises(RegistryError) as ei:
        EngagementRegistry.from_rows(EID, rows + [replace(rows[0], id="")])
    assert ei.value.invariant == "I6"
    with pytest.raises(ValueError):
        EngagementRegistry("")


# ---------------------------------------------------------------------------
# materiality and the gate queries
# ---------------------------------------------------------------------------

def test_is_material_recomputes_from_the_support_closure_never_from_the_flag(registry):
    # Mutation "make is_material read payload.material" is caught in both directions.
    reg = registry()
    turn = add_turn(reg)
    dec = add_decision(reg)
    base = confirm(reg, client_fact(reg, turn, "We have 214 employees"))
    calc = reg.apply(SetStatus(add_calc(reg, [base], formula=f"{base.id} * 2").id, S.CONFIRMED,
                               prov(Actor.CALCULATOR, "calculator")))
    other = client_fact(reg, turn, "revenue of EUR 48.2M")                    # nothing rests on it
    rec = add_rec(reg, dec, supports=(calc.id,))                               # rests on the calculation, so on the client fact
    on_base = add_conflict(reg, [base, other], material=False)                # the stored flag says no
    assert on_base.payload.material is False
    assert reg.is_material(on_base) is True
    on_other = add_conflict(reg, [other], material=True)                      # the stored flag says yes
    assert reg.is_material(on_other) is False
    assert reg.open_material_conflicts() == [on_base]
    assert reg.live_summary()["conflicts"] == [on_base.id, on_other.id]       # the summary lists every open one
    defining = client_fact(reg, turn, "in FY25", relation=DEFINES)            # a conclusion that defines the decision
    assert reg.is_material(add_conflict(reg, [defining], material=False)) is True
    assert reg.is_material(add_conflict(reg, [other], kind=ConflictKind.OBJECTIVE_VS_FEASIBILITY)) is True
    assert reg.is_material(add_conflict(reg, [], material=True)) is False
    reg.apply(SetStatus(rec.id, S.WITHDRAWN, prov(Actor.PARTNER)))            # the closure follows the recommendation's life
    assert reg.is_material(on_base) is False
    with pytest.raises(TypeError):
        reg.is_material(base)


def test_a_material_conflict_is_resolved_by_the_authority_it_names_and_the_loser_stays(registry):
    reg = registry()
    turn = add_turn(reg)
    a = confirm(reg, client_fact(reg, turn, "We have 214 employees", relation=DEFINES))
    b = client_fact(reg, turn, "revenue of EUR 48.2M", relation=DEFINES)
    conflict = add_conflict(reg, [a, b], authority=Authority.DECISION_OWNER)
    assert reg.open_material_conflicts() == [conflict]
    for actor in (Actor.PARTNER, Actor.CLIENT, Actor.SYSTEM):
        refused(reg, SetStatus(conflict.id, S.RESOLVED, prov(actor)), "I1")
    resolved = reg.apply(SetStatus(conflict.id, S.RESOLVED, prov(Actor.DECISION_OWNER, "client:turn:4 as DOW-1"),
                                   labels=("resolution:kept", "resolution:kept")))
    assert resolved.confirmed_by == "client:turn:4 as DOW-1" and resolved.labels == ("resolution:kept",)
    assert reg.open_material_conflicts() == [] and reg.live_summary()["conflicts"] == []
    reg.apply(SetStatus(b.id, S.REJECTED, prov(Actor.CLIENT)))
    assert reg.get(b.id).status is S.REJECTED and reg.lineage(b.id)[0] == b   # rejected, still addressable


def test_unsupported_recommendations_names_every_reason_and_accepts_a_confirmed_client_fact(registry):
    reg = registry()
    turn = add_turn(reg)
    dec = add_decision(reg)
    proposed = client_fact(reg, turn, "We have 214 employees")
    confirmed = confirm(reg, client_fact(reg, turn, "revenue of EUR 48.2M"))
    bare = add_rec(reg, dec)
    weak = add_rec(reg, dec, supports=(proposed.id,))
    ghost = add_rec(reg, dec, supports=("FCT-9",))
    good = add_rec(reg, dec, supports=(confirmed.id,))
    found = {r.id: why for r, why in reg.unsupported_recommendations()}
    assert found == {bare.id: "no supports", weak.id: f"support {proposed.id} is fact:proposed",
                     ghost.id: "support FCT-9 missing or superseded"}
    reg.apply(SetStatus(confirmed.id, S.REJECTED, prov(Actor.CLIENT)))
    assert dict(reg.unsupported_recommendations())[good] == f"support {confirmed.id} missing or superseded"
    reg.apply(SetStatus(good.id, S.WITHDRAWN, prov(Actor.PARTNER)))
    assert good.id not in {r.id for r, _ in reg.unsupported_recommendations()}


def test_assumption_approval_is_the_checked_status_not_the_payload_field(registry):
    # A producer can write approval=APPROVED into a payload; only the client's APPROVED transition counts.
    reg = registry()
    plain = add_assumption(reg)
    claimed = add_assumption(reg, approval=T.ApprovalState.APPROVED, text="the model said so")
    assert {a.id for a in reg.unapproved_assumptions()} == {plain.id, claimed.id}
    for actor in (Actor.PARTNER, Actor.DECISION_OWNER, Actor.METHOD, Actor.SYSTEM):
        refused(reg, SetStatus(plain.id, S.APPROVED, prov(actor)), "I1")
    reg.apply(SetStatus(plain.id, S.APPROVED, prov(Actor.CLIENT)))
    assert reg.unapproved_assumptions() == [reg.get(claimed.id)]
    summary = reg.live_summary()
    assert summary["assumptions_approved"] == [plain.id] and summary["assumptions_unapproved"] == [claimed.id]
    reg.apply(SetStatus(claimed.id, S.REJECTED, prov(Actor.CLIENT)))
    assert reg.unapproved_assumptions() == [] and reg.live_summary()["assumptions_unapproved"] == []


def test_open_material_questions_reads_the_flag_with_is_true_and_the_summary_ranks_by_value(registry):
    reg = registry()
    low = add_question(reg, material=True, value=0.2)
    high = add_question(reg, material=True, value=0.9)
    soft = add_question(reg, material=False, value=0.95)
    unknown = add_question(reg, material=True, value=None)
    done = add_question(reg, material=True, value=0.5)
    reg.apply(SetStatus(done.id, S.RESOLVED, prov(Actor.PARTNER)))
    assert reg.open_material_questions() == [low, high, unknown]
    assert reg.live_summary()["missing"] == [soft.id, high.id, low.id, unknown.id]   # by value; unknown last, still None
    assert reg.get(unknown.id).payload.value is None


def test_calculated_facts_facts_by_measure_and_client_facts_confirmed(registry):
    reg = registry()
    turn = add_turn(reg)
    a = confirm(reg, client_fact(reg, turn, "We have 214 employees", measure_id="MEA-1"))
    b = client_fact(reg, turn, "revenue of EUR 48.2M", measure_id="MEA-2")
    c = client_fact(reg, turn, "in FY25", measure_id="MEA-1")
    loose = client_fact(reg, turn, "EUR 48.2M")
    calc = add_calc(reg, [a], formula=f"{a.id} * 2")
    reg.apply(SetStatus(c.id, S.WITHDRAWN, prov(Actor.PARTNER)))
    assert reg.facts_by_measure() == {"MEA-1": [a], "MEA-2": [b]}
    assert reg.calculated_facts() == [calc] and reg.client_facts_confirmed() == [a]
    assert loose.id not in {f.id for fs in reg.facts_by_measure().values() for f in fs}
    reg.apply(SetStatus(calc.id, S.WITHDRAWN, prov(Actor.CALCULATOR, "calculator")))
    assert reg.calculated_facts() == []


def test_infeasible_objectives_without_decision_counts_only_live_decisions_required(registry):
    reg = registry()
    fine = reg.apply(Add(ent(K.OBJECTIVE, T.ObjectivePayload("grow"), Actor.CLIENT)))
    stuck = reg.apply(Add(ent(K.OBJECTIVE, T.ObjectivePayload("double output by June",
                                                              feasibility=T.Feasibility.INFEASIBLE_ON_FACTS))))
    assert reg.infeasible_objectives_without_decision() == [stuck]
    asked = reg.apply(Add(ent(K.DECISION_REQUIRED, T.DecisionRequiredPayload("revise or drop the target", Authority.CLIENT),
                              derived=(stuck.id,), status=S.OPEN)))
    assert reg.infeasible_objectives_without_decision() == []
    reg.apply(SetStatus(asked.id, S.WITHDRAWN, prov(Actor.PARTNER)))
    assert reg.infeasible_objectives_without_decision() == [stuck]
    reg.apply(Add(ent(K.DECISION_REQUIRED, T.DecisionRequiredPayload("choose", Authority.CLIENT, options=(stuck.id,)),
                      status=S.OPEN)))
    assert reg.infeasible_objectives_without_decision() == [] and fine.id not in reg.live_summary()["decisions_required"]


def test_live_summary_is_ids_only_and_recomputed_on_every_read(registry):
    reg = registry()
    turn = add_turn(reg)
    fact = client_fact(reg, turn)
    before = reg.live_summary()
    assert set(before) == {"confirmed_facts", "assumptions_approved", "assumptions_unapproved", "missing", "risks",
                           "conflicts", "decisions_required", "regulated_matters"}
    assert before["confirmed_facts"] == [] and before["risks"] == []
    confirm(reg, fact)
    risk = reg.apply(Add(ent(K.RISK, T.RiskPayload("key person leaves"))))
    after = reg.live_summary()
    assert after["confirmed_facts"] == [fact.id] and after["risks"] == [risk.id] and after != before
    assert reg.live_summary() == after and reg.live_summary() is not after
    for ids in after.values():
        assert all(isinstance(i, str) and i.rpartition("-")[2].isdigit() for i in ids)


# ---------------------------------------------------------------------------
# batches, the scoped view, the protocol
# ---------------------------------------------------------------------------

def test_apply_all_is_all_or_nothing(registry):
    reg = registry()
    turn = add_turn(reg)
    before = (reg.content_hash(), len(reg.rows()))
    good = ent(K.FACT, T.FactPayload("We have 214 employees", FactBasis.CLIENT_STATED), derived=(turn.id,))
    bad = ent(K.FACT, T.FactPayload("We have 300 employees", FactBasis.CLIENT_STATED), derived=(turn.id,))
    with pytest.raises(RegistryError) as ei:
        reg.apply_all([Add(good), Add(ent(K.DECISION, T.DecisionPayload("x", DecisionRole.CENTRAL))), Add(bad)])
    assert ei.value.invariant == "I2"
    assert (reg.content_hash(), len(reg.rows())) == before
    assert reg.query(K.FACT) == [] and reg.get("DEC-1") is None and reg.central_decision() is None
    landed = reg.apply_all([Add(good), Add(ent(K.DECISION, T.DecisionPayload("x", DecisionRole.CENTRAL)))])
    assert [e.id for e in landed] == ["FCT-1", "DEC-1"]                       # the refused batch burnt no ids
    with pytest.raises(TypeError):
        reg.apply(object())


def test_scoped_view_hides_what_was_not_permitted_and_shows_confirmed_preferences(registry):
    reg = registry()
    turn = add_turn(reg)
    doc = add_document(reg)
    fact = confirm(reg, client_fact(reg, turn))
    dec = add_decision(reg)
    rec = add_rec(reg, dec, supports=(fact.id,))
    objective = confirm(reg, reg.apply(Add(ent(K.OBJECTIVE, T.ObjectivePayload("halve the cost base"), Actor.CLIENT))))
    draft = reg.apply(Add(ent(K.OBJECTIVE, T.ObjectivePayload("maybe also grow"), Actor.CLIENT)))
    view = ScopedView(reg, [fact.id, turn.id])
    assert view.engagement_id == EID and view.permitted == {fact.id, turn.id, objective.id}
    assert view.get(fact.id) == fact and view.get(objective.id) == objective
    assert view.get(rec.id) is None and view.get(dec.id) is None and view.get(draft.id) is None
    assert view.query(K.RECOMMENDATION) == [] and view.query() == [turn, fact, objective]
    assert view.live(K.OBJECTIVE) == [objective] and view.query(K.FACT, where={"basis": FactBasis.CLIENT_STATED}) == [fact]
    assert view.lineage(fact.id) == reg.lineage(fact.id) and view.lineage(rec.id) == []
    assert view.supports_of(rec.id) == [] and view.central_decision() is None
    assert view.source_text(turn.id) == TURN and view.source_text(doc.id) is None
    assert view.content_hash() != reg.content_hash()
    assert view.content_hash() == ScopedView(reg, [turn.id, fact.id]).content_hash()
    with pytest.raises(ValueError):
        view.query(K.FACT, where={"statement": "x"})
    wide = ScopedView(reg, [fact.id, rec.id, dec.id])
    assert wide.supports_of(rec.id) == [fact] and wide.central_decision() == dec
    # the window is fixed when the assignment is issued: later rows are not in it
    later = client_fact(reg, turn, "in FY25")
    assert view.get(later.id) is None and reg.get(later.id) == later


def test_registry_and_scoped_view_satisfy_the_read_protocol():
    reg = EngagementRegistry(EID)
    assert isinstance(reg, RegistryView) and isinstance(ScopedView(reg, []), RegistryView)
    assert not isinstance(object(), RegistryView)
    assert reg.rows() == [] and reg.content_hash() == EngagementRegistry("E-2").content_hash()
    turn = add_turn(reg)
    assert turn.provenance.recorded_at.endswith("+00:00") and turn.provenance.recorded_at != FIXED_CLOCK


def test_the_calculator_boundary_types_live_with_the_read_side():
    # contracts.py section 8 has one home: an except clause written against
    # IncomparableInputs must catch what the calculator raises.
    from app.engine.registry import CalcResult, Calculator, IncomparableInputs, Reconciliation

    assert issubclass(IncomparableInputs, Exception)
    assert Reconciliation("question", unpinned=("currency",)).conflict_kind is None
    assert CalcResult(heads("428"), "FCT-1 * 2", ("FCT-1",)).inputs == ("FCT-1",)
    assert all(hasattr(Calculator, m) for m in ("product", "total", "ratio", "convert_period", "recompute", "comparable"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        Reconciliation("same").outcome = "conflict"


def test_read_side_and_calculator_protocols_are_exported_under_the_contract_names():
    # contract.py TYPE_CHECKING-imports Calculator and RegistryView from here
    # and calc/ resolves the same objects; a rename or a second definition
    # would split the boundary into two classes that no longer catch or
    # satisfy each other.
    import app.engine.registry as registry_module

    assert {"Calculator", "RegistryView", "IncomparableInputs", "CalcResult"} <= set(registry_module.__all__)
    calc_pkg = pytest.importorskip("app.engine.calc")
    assert calc_pkg.Calculator is registry_module.Calculator
    assert calc_pkg.RegistryView is registry_module.RegistryView
    assert calc_pkg.IncomparableInputs is registry_module.IncomparableInputs
    # both protocols are runtime-checkable so a context can be verified, not trusted
    assert not isinstance(object(), registry_module.Calculator)
    arith = pytest.importorskip("app.engine.calc.arith")
    assert isinstance(arith.DecimalCalculator(), registry_module.Calculator)
