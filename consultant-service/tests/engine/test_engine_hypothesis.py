"""C7 hypothesis: app/engine/partner/hypothesis.py -- deterministic candidate
weights, the model's add-only revision pass, symptom-vs-problem with the
SYMPTOM_MARGIN and causal-chain laws, the confirm-revised-scope gate on the
charter, and charter_ready including the ASK_FLOOR trigger.

Pinned mutations (work breakdown C7):
- remove the margin check          -> test_reframe_needs_margin
- remove the DECISION_REQUIRED gate -> test_charter_cannot_name_inferred_until_resolved
- coerce unknown confidence to 0 in storage -> test_unknown_confidence_stays_none_in_storage

Also here: the bearing law that fills the relevance links the score is made
of (design 6.4). Its mutations are
- give BEARING_BY_KIND a default    -> test_a_kind_with_no_derived_bearing_bears_on_nothing
- let a candidate bear on a rival    -> test_a_candidate_decision_never_bears_on_a_decision
- attach before a decision is stated -> test_nothing_is_attached_before_a_decision_is_stated
- read the stated request past a central one -> test_a_statement_bears_on_the_central_decision
"""
from __future__ import annotations

import json

import pytest

from app.engine import types as T
from app.engine.partner import hypothesis as H
from app.engine.types import (
    Actor, Add, Authority, DecisionRole, Kind, RelationToCentralDecision, SetStatus, Status,
)

K = Kind
S = Status
EID = "E-1"
DEFINES = RelationToCentralDecision.DEFINES
INFORMS = RelationToCentralDecision.INFORMS
PRIOR = T.UNKNOWN_CONFIDENCE_PRIOR


# ---------------------------------------------------------------------------
# builders: every entity through make_entity, every write through apply()
# ---------------------------------------------------------------------------

def prov(actor: Actor, ref: str | None = None, derived=()) -> T.Provenance:
    return T.Provenance(actor=actor, actor_ref=ref or f"{actor.value}:1", derived_from=tuple(derived))


def add(reg, kind: Kind, payload, *, actor: Actor = Actor.PARTNER, status: Status = S.PROPOSED,
        relation: RelationToCentralDecision = INFORMS, relevance: T.Relevance | None = None,
        confidence: T.Confidence | None = None, derived=(), labels=()) -> T.Entity:
    return reg.apply(Add(T.make_entity(
        kind=kind, engagement_id=EID, payload=payload, provenance=prov(actor, derived=derived),
        confidence=confidence or T.Confidence(None), relevance=relevance or T.Relevance(None),
        relation=relation, status=status, labels=tuple(labels))))


def decision(reg, text: str, *, role: DecisionRole = DecisionRole.STATED_REQUEST,
             origin: str = "client_request") -> T.Entity:
    return add(reg, K.DECISION, T.DecisionPayload(statement=text, role=role, origin=origin))


def inferred_decision(reg, text: str = "decide whether to redesign fulfilment") -> T.Entity:
    return decision(reg, text, role=DecisionRole.SUBORDINATE, origin=H.PARTNER_INFERRED)


def fact(reg, decision_id: str | None, *, weight: float = 0.5, relation=DEFINES,
         conf: float | None = 0.8, statement: str = "an observed fact") -> T.Entity:
    return add(reg, K.FACT, T.FactPayload(statement=statement, basis=T.FactBasis.INFERRED),
               relevance=T.Relevance(decision_id, weight), relation=relation,
               confidence=T.Confidence(conf, "verified" if conf is not None else "unknown"))


def owner(reg) -> T.Entity:
    return add(reg, K.DECISION_OWNER, T.DecisionOwnerPayload(name="md", role="managing director"))


def issue_under(reg, decision_id: str, text: str = "why are orders late") -> T.Entity:
    return add(reg, K.ISSUE,
               T.IssuePayload(text=text, interrogative=T.Interrogative.HOW_MUCH, target_kind=K.FACT,
                              decisive_for=(decision_id,)),
               relevance=T.Relevance(decision_id, 0.3), relation=INFORMS)


def link(reg, issue_id: str, cause_id: str) -> T.Entity:
    return add(reg, K.HYPOTHESIS,
               T.HypothesisPayload(text="the delays trace to fulfilment", issue_id=issue_id,
                                   causes=(cause_id,)),
               derived=(issue_id, cause_id))


def bounds(**overrides) -> dict:
    b = dict(T.BOUNDS)
    b.update(overrides)
    return b


def reframe_scene(registry):
    """Stated request A lightly supported; inferred candidate B dominant, with
    an issue under A and a causal HYPOTHESIS to a cause under B."""
    reg = registry()
    a = decision(reg, "fix the delays")
    b = inferred_decision(reg)
    fact(reg, a.id, weight=0.2, conf=0.5)                    # A: 0.2*0.5*1.0 = 0.10
    iss = issue_under(reg, a.id)                             # A: 0.3*PRIOR*0.3
    cause = fact(reg, b.id, weight=0.9, conf=0.9)            # B: 0.81
    fact(reg, b.id, weight=0.9, conf=0.9)                    # B: 0.81
    hyp = link(reg, iss.id, cause.id)
    return reg, a, b, iss, cause, hyp


# ---------------------------------------------------------------------------
# deterministic weights
# ---------------------------------------------------------------------------

def test_weights_recompute_from_registry_only(registry):
    """Adding DEFINES facts for candidate B flips the ranking; no provider is
    anywhere in scope, so the ranking is a pure function of the rows."""
    reg = registry()
    a = decision(reg, "fix the delays")
    b = inferred_decision(reg)
    fact(reg, a.id, weight=0.5, relation=INFORMS)
    fact(reg, a.id, weight=0.5, relation=INFORMS)
    fact(reg, b.id, weight=0.5, relation=INFORMS)
    assert H.ranked_candidates(reg)[0][0].id == a.id
    # the flip: two defining facts land for B
    fact(reg, b.id, weight=0.5, relation=DEFINES)
    fact(reg, b.id, weight=0.5, relation=DEFINES)
    ranked = H.ranked_candidates(reg)
    assert ranked[0][0].id == b.id
    weights = H.hypothesis_weights(reg)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_relation_multipliers_and_exact_score(registry):
    reg = registry()
    a = decision(reg, "fix the delays")
    b = inferred_decision(reg)
    fact(reg, a.id, weight=0.5, relation=DEFINES, conf=0.8)      # 0.40
    fact(reg, a.id, weight=0.5, relation=T.RelationToCentralDecision.CONSTRAINS, conf=0.8)  # 0.28
    fact(reg, b.id, weight=0.5, relation=T.RelationToCentralDecision.UNRELATED, conf=0.8)   # 0.0
    scores = H.hypothesis_scores(reg)
    assert scores[a.id] == pytest.approx(0.68)
    assert scores[b.id] == 0.0


def test_no_evidence_means_no_ranking_not_a_default(registry):
    reg = registry()
    a = decision(reg, "fix the delays")
    assert H.hypothesis_weights(reg) == {a.id: 0.0}


def test_unknown_confidence_uses_prior_and_stays_none(registry):
    """Confidence(None) contributes the declared prior to the score; the
    stored value stays None (absent evidence is not evidence of a defect)."""
    reg = registry()
    a = decision(reg, "fix the delays")
    f = fact(reg, a.id, weight=0.5, relation=DEFINES, conf=None)
    assert H.hypothesis_scores(reg)[a.id] == pytest.approx(0.5 * PRIOR)
    assert reg.get(f.id).confidence.value is None


# ---------------------------------------------------------------------------
# revise_hypothesis: the model may ADD, never remove
# ---------------------------------------------------------------------------

REVISION = {
    "new_candidates": [
        {"text": "decide whether to redesign fulfilment",
         "rationale": "delays cluster in fulfilment", "rationale_ids": ["__CITE__"]},
        {"text": "a candidate citing nothing registered",
         "rationale": "invented", "rationale_ids": ["FCT-999"]},
        {"text": "a candidate citing nothing at all", "rationale": "", "rationale_ids": []},
    ],
    "causal_links": [
        {"issue_id": "__ISSUE__", "cause_id": "__CITE__", "support_ids": ["__CITE__"],
         "text": "the late orders trace to fulfilment"},
        {"issue_id": "ISS-999", "cause_id": "__CITE__", "support_ids": ["__CITE__"], "text": "bogus issue"},
        {"issue_id": "__ISSUE__", "cause_id": "__CITE__", "support_ids": [], "text": "unsupported"},
    ],
}


def test_revision_adds_with_rationale_and_never_removes(registry, fake_provider):
    reg = registry()
    a = decision(reg, "fix the delays")
    f = fact(reg, a.id, weight=0.5, statement="a third of orders ship late")
    iss = issue_under(reg, a.id)
    script = json.dumps(REVISION).replace("__CITE__", f.id).replace("__ISSUE__", iss.id)
    provider = fake_provider(script={H.REVISE_PURPOSE: [script]})
    before = {e.id: e.version for e in reg.live(K.DECISION)}

    added = H.revise_hypothesis(reg, provider)

    new_decisions = [e for e in added if e.kind == K.DECISION]
    new_hyps = [e for e in added if e.kind == K.HYPOTHESIS]
    # exactly the candidate whose rationale cites a registered entity survives
    assert len(new_decisions) == 1 and len(new_hyps) == 1 and len(added) == 2
    d = new_decisions[0]
    assert d.payload.role == DecisionRole.SUBORDINATE
    assert d.payload.origin == H.PARTNER_INFERRED
    assert d.provenance.derived_from == (f.id,)
    assert d.provenance.model_call_id is not None
    assert d.status == S.PROPOSED
    h = new_hyps[0]
    assert h.payload.issue_id == iss.id and h.payload.causes == (f.id,)
    # never removes: every pre-existing candidate is still live, untouched
    for eid, version in before.items():
        live = reg.get(eid)
        assert live is not None and live.status not in T.TERMINAL_STATUSES
        assert live.version == version


def test_unknown_confidence_stays_none_in_storage(registry, fake_provider):
    """MUTATION coerce-unknown-confidence: a stored Confidence(0.0) would let
    the prior-at-read-time law be bypassed and condemn the model's candidate
    forever; the row must carry None."""
    reg = registry()
    a = decision(reg, "fix the delays")
    f = fact(reg, a.id, weight=0.5, statement="a third of orders ship late")
    iss = issue_under(reg, a.id)
    script = json.dumps(REVISION).replace("__CITE__", f.id).replace("__ISSUE__", iss.id)
    added = H.revise_hypothesis(reg, fake_provider(script={H.REVISE_PURPOSE: [script]}))
    for row in added:
        assert reg.get(row.id).confidence.value is None
    # and the candidate still scores through the prior once evidence attaches
    d = next(e for e in added if e.kind == K.DECISION)
    fact(reg, d.id, weight=0.4, relation=DEFINES, conf=None)
    assert H.hypothesis_scores(reg)[d.id] == pytest.approx(0.4 * PRIOR)


def test_empty_revision_is_a_real_answer(registry, fake_provider):
    reg = registry()
    decision(reg, "fix the delays")
    assert H.revise_hypothesis(reg, fake_provider(script={H.REVISE_PURPOSE: ["{}"]})) == []


# ---------------------------------------------------------------------------
# symptom vs problem
# ---------------------------------------------------------------------------

def test_reframe_with_chain_sets_symptom_of_and_opens_decision_required(registry):
    reg, a, b, iss, cause, hyp = reframe_scene(registry)
    reframe = H.maybe_reframe(reg, bounds())
    assert reframe is not None
    assert reframe.stated_id == a.id and reframe.inferred_id == b.id
    assert hyp.id in reframe.hypothesis_ids
    # the stated DECISION is superseded with symptom_of, visibly
    stated = reg.get(a.id)
    assert stated.payload.symptom_of == b.id
    assert any(r.status == S.SUPERSEDED for r in reg.lineage(a.id))
    # the scope confirmation is OPEN, from the CLIENT's authority
    dr = reg.get(reframe.decision_required_id)
    assert dr.kind == K.DECISION_REQUIRED and dr.status == S.OPEN
    assert dr.payload.from_authority == Authority.CLIENT
    assert dr.payload.text == H.CONFIRM_SCOPE_TEXT
    assert dr.payload.decision_id == b.id
    # idempotent: the client is never asked twice
    assert H.maybe_reframe(reg, bounds()) is None


def test_no_causal_chain_no_reframe(registry):
    """Dominant weight alone never reframes: without the HYPOTHESIS linking an
    issue under the stated request to a cause under the candidate, the
    'symptom' claim would rest on arithmetic alone."""
    reg = registry()
    a = decision(reg, "fix the delays")
    b = inferred_decision(reg)
    fact(reg, a.id, weight=0.2, conf=0.5)
    fact(reg, b.id, weight=0.9, conf=0.9)
    fact(reg, b.id, weight=0.9, conf=0.9)
    assert H.maybe_reframe(reg, bounds()) is None
    assert reg.get(a.id).payload.symptom_of is None
    assert reg.live(K.DECISION_REQUIRED) == []


def test_reframe_needs_margin(registry):
    """MUTATION remove-the-margin-check: an inferred candidate merely AHEAD
    (chain and all) must not reframe; only dominance by SYMPTOM_MARGIN may."""
    reg = registry()
    a = decision(reg, "fix the delays")
    b = inferred_decision(reg)
    fact(reg, a.id, weight=0.5, conf=0.8)                    # 0.40
    iss = issue_under(reg, a.id)                             # + 0.3*PRIOR*0.3
    cause = fact(reg, b.id, weight=0.6, conf=0.8)            # 0.48: ahead, inside the margin
    link(reg, iss.id, cause.id)
    w = H.hypothesis_weights(reg)
    assert 0.0 < w[b.id] - w[a.id] < T.BOUNDS["SYMPTOM_MARGIN"]
    assert H.maybe_reframe(reg, bounds()) is None
    assert reg.get(a.id).payload.symptom_of is None
    # negative control: the same scene with the margin bound lowered reframes,
    # so the refusal above is the margin's and nothing else's
    assert H.maybe_reframe(reg, bounds(SYMPTOM_MARGIN=0.01)) is not None


def test_charter_cannot_name_inferred_until_resolved(registry):
    """MUTATION remove-the-DECISION_REQUIRED-gate: while the scope
    confirmation is OPEN the charter names the stated request; naming the
    inferred decision would be a silent substitution of scope."""
    reg, a, b, *_ = reframe_scene(registry)
    reframe = H.maybe_reframe(reg, bounds())
    assert reframe is not None
    named = H.central_decision_for_charter(reg)
    assert named is not None and named.id == a.id
    # the client resolves the scope decision; only then may the charter switch
    reg.apply(SetStatus(reframe.decision_required_id, S.RESOLVED, by=prov(Actor.CLIENT, "client:turn:3")))
    assert H.central_decision_for_charter(reg).id == b.id


# ---------------------------------------------------------------------------
# charter_ready
# ---------------------------------------------------------------------------

def test_charter_ready_confident_path(registry):
    reg = registry()
    a = decision(reg, "fix the delays")
    fact(reg, a.id, weight=0.5, relation=DEFINES)
    assert not H.charter_ready(reg, bounds())          # no owner yet
    owner(reg)
    assert H.charter_ready(reg, bounds())              # single candidate, weight 1.0


def test_charter_ready_requires_candidate(registry):
    reg = registry()
    owner(reg)
    # no candidate: not ready, not even under ASK_FLOOR
    assert not H.charter_ready(reg, bounds(), top_gap_value=0.0)


def _near_tie(registry):
    """Two candidates split ~50/50: top weight passes CHARTER_MIN_WEIGHT but
    the margin fails, so only ASK_FLOOR or a client's choice can open it."""
    reg = registry()
    a = decision(reg, "fix the delays")
    b = inferred_decision(reg)
    fact(reg, a.id, weight=0.5, relation=DEFINES)
    fact(reg, b.id, weight=0.5, relation=DEFINES)
    owner(reg)
    return reg, a, b


def test_charter_ready_ask_floor_trigger(registry):
    reg, a, b = _near_tie(registry)
    assert not H.charter_ready(reg, bounds())
    # the top remaining gap is worth less than ASK_FLOOR: asking more is
    # stalling, not diligence -- the charter opens
    assert H.charter_ready(reg, bounds(), top_gap_value=T.BOUNDS["ASK_FLOOR"] - 0.01)
    # at or above the floor there is still a question worth asking
    assert not H.charter_ready(reg, bounds(), top_gap_value=T.BOUNDS["ASK_FLOOR"])


def test_charter_ready_when_client_chose(registry):
    reg, a, b = _near_tie(registry)
    dr = add(reg, K.DECISION_REQUIRED,
             T.DecisionRequiredPayload(text=H.CONFIRM_SCOPE_TEXT, from_authority=Authority.CLIENT,
                                       decision_id=b.id, options=(a.id, b.id)),
             status=S.OPEN, labels=(H.SCOPE_CONFIRMATION_LABEL,))
    assert not H.charter_ready(reg, bounds())          # open: still the client's move
    reg.apply(SetStatus(dr.id, S.RESOLVED, by=prov(Actor.CLIENT, "client:turn:4")))
    assert H.charter_ready(reg, bounds())


def test_open_pin_question_on_defining_fact_blocks(registry):
    reg = registry()
    a = decision(reg, "fix the delays")
    f = fact(reg, a.id, weight=0.5, relation=DEFINES)
    owner(reg)
    q = add(reg, K.QUESTION, T.QuestionPayload(text="pin the currency"),
            status=S.OPEN, derived=(f.id,), labels=(H.PIN_DIMENSION_LABEL,))
    assert not H.charter_ready(reg, bounds())
    reg.apply(SetStatus(q.id, S.RESOLVED, by=prov(Actor.CLIENT, "client:turn:2")))
    assert H.charter_ready(reg, bounds())


# ---------------------------------------------------------------------------
# the bearing: what a statement bears on, and how (design 6.4)
# ---------------------------------------------------------------------------

def _fact_payload(basis: T.FactBasis) -> T.FactPayload:
    return T.FactPayload(statement="an observed figure", basis=basis)


def test_bearing_is_derived_from_the_kind_and_the_basis(registry):
    """The relation is a function of what the row IS - never of prose, never
    of a field the model returned. That is what keeps the ranking a property
    of the registry: with the table in place, ingesting more of a kind changes
    the score with no model call anywhere in scope."""
    reg = registry()
    a = decision(reg, "fix the delays")
    expected = [
        (K.OBJECTIVE, None, DEFINES),
        (K.DECISION_OWNER, None, DEFINES),
        (K.CONSTRAINT, None, T.RelationToCentralDecision.CONSTRAINS),
        (K.DEADLINE, None, T.RelationToCentralDecision.CONSTRAINS),
        (K.MEASURE, None, T.RelationToCentralDecision.EVIDENCES),
        (K.BUSINESS_CONTEXT, None, INFORMS),
        (K.STAKEHOLDER, None, INFORMS),
        (K.FACT, _fact_payload(T.FactBasis.CLIENT_STATED), T.RelationToCentralDecision.EVIDENCES),
        (K.FACT, _fact_payload(T.FactBasis.DOCUMENT_VERIFIED), T.RelationToCentralDecision.EVIDENCES),
        (K.FACT, _fact_payload(T.FactBasis.DOCUMENT_EXTRACTED), INFORMS),
    ]
    for kind, payload, relation in expected:
        relevance, got = H.bearing(reg, kind, payload)
        assert got is relation, kind
        assert relevance.decision_id == a.id, kind
        assert relevance.weight == H.STATEMENT_WEIGHT, kind
        assert relevance.rationale == f"{H.BEARING_RATIONALE}:{kind.value}", kind
    # every relation the table hands out is one the score actually prices
    for relation in set(H.BEARING_BY_KIND.values()) | set(H.BEARING_BY_FACT_BASIS.values()):
        assert H.REL_MULTIPLIER[relation] > 0.0


def test_a_kind_with_no_derived_bearing_bears_on_nothing(registry):
    """MUTATION give-BEARING_BY_KIND-a-default: an entity whose relevance is
    genuinely unknown keeps relation UNKNOWN and contributes zero. A default
    would let a process record - the turn row that merely carried the words,
    the question that asked for them - vote in the ranking."""
    reg = registry()
    a = decision(reg, "fix the delays")
    for kind in (K.EVIDENCE_SOURCE, K.QUESTION, K.ANALYSIS, K.CHARTER, K.WORK_PRODUCT):
        relevance, relation = H.bearing(reg, kind)
        assert relevance.decision_id is None, kind
        assert relevance.weight == 0.0, kind
        assert relation is T.RelationToCentralDecision.UNKNOWN, kind
        assert H.REL_MULTIPLIER.get(relation, 0.0) == 0.0
    assert H.hypothesis_scores(reg) == {a.id: 0.0}


def test_a_candidate_decision_never_bears_on_a_decision(registry):
    """MUTATION let-a-candidate-bear-on-a-rival: hypothesis_scores stops a
    candidate voting for ITSELF, but nothing there stops one voting for a
    rival. The bearing table is where that is refused: a DECISION is a
    candidate, not evidence for one."""
    reg = registry()
    decision(reg, "fix the delays")
    inferred_decision(reg)
    relevance, relation = H.bearing(reg, K.DECISION,
                                    T.DecisionPayload(statement="another", role=DecisionRole.SUBORDINATE))
    assert relevance.decision_id is None
    assert relation is T.RelationToCentralDecision.UNKNOWN
    assert K.DECISION not in H.BEARING_BY_KIND


def test_nothing_is_attached_before_a_decision_is_stated(registry):
    """MUTATION attach-before-a-decision-is-stated: with no candidate on the
    record there is nothing to bear on, and both halves of the envelope stay
    empty. Half a link - a relation with no decision - would arm the gates
    that read relation structurally on a decision nobody has named."""
    reg = registry()
    assert H.bearing_decision(reg) is None
    relevance, relation = H.bearing(reg, K.OBJECTIVE)
    assert relevance.decision_id is None
    assert relation is T.RelationToCentralDecision.UNKNOWN
    assert H.bearing(reg, K.OBJECTIVE) == H.UNATTACHED


def test_a_statement_bears_on_the_central_decision(registry):
    """MUTATION read-the-stated-request-past-a-central-one: once the client
    has approved a charter the engagement has a CENTRAL decision, and what is
    said afterwards is said about THAT. Reading the stated request first would
    keep piling weight onto a request the charter already replaced."""
    reg = registry()
    stated = decision(reg, "fix the delays")
    central = decision(reg, "choose a fulfilment model", role=DecisionRole.CENTRAL)
    assert H.bearing_decision(reg).id == central.id
    relevance, _ = H.bearing(reg, K.OBJECTIVE)
    assert relevance.decision_id == central.id
    assert relevance.decision_id != stated.id


def test_bearing_relation_reads_a_fact_basis_it_does_not_know_as_unknown():
    """Absence is not a verdict. A basis the table does not name returns
    UNKNOWN - zero in the score - rather than the nearest neighbour, so a new
    FactBasis cannot quietly inherit somebody else's weight."""
    assert H.bearing_relation(K.FACT, None) is T.RelationToCentralDecision.UNKNOWN
    assert set(H.BEARING_BY_FACT_BASIS) == set(T.FactBasis), (
        "a FactBasis with no declared bearing would silently score zero")
