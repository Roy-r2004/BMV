"""C17 charter / state / loop: app/engine/partner/state.py, charter.py and
loop.py -- the phase machine and its registry guards, the fourteen-list charter
with per-item confirm / correct / reject, and Partner.turn / Partner.run_analysis.

Pinned mutations (work breakdown C17):
- remove the APPROVED-charter guard  -> test_analysis_is_unreachable_without_an_approved_charter
- remove the pause                   -> test_a_material_question_from_a_method_pauses_analysis
- run RESEARCH methods directly      -> test_research_waits_for_the_charter_while_deterministic_runs
- remove the SPAWN branch            -> test_paid_and_tied_selections_become_assignments
- cache the live summary             -> test_live_summary_is_recomputed_not_stored
- drop the merge of the caller's bindings -> test_a_binding_reaches_a_free_method
- let a binding shadow a bound       -> test_a_binding_cannot_move_an_operators_ceiling

Every provider here is the FakeProvider driven by a case-agnostic structural
oracle: one answer per model purpose, reused for every call of that purpose, so
nothing in this file knows what the engagement is about.
"""
from __future__ import annotations

import pytest

from app.engine import types as T
from app.engine.methods.contract import (
    EvidenceRequirement, MethodRegistry, MethodResult, MethodSpec, QuestionShape, new_entity,
)
from app.engine.partner import charter as C
from app.engine.partner import loop as L
from app.engine.partner import questions as Q
from app.engine.partner import state as S
from app.engine.types import Actor, Add, Kind, Phase, RelationToCentralDecision, Status

K = Kind
EID = "E-1"
DEFINES = RelationToCentralDecision.DEFINES
INFORMS = RelationToCentralDecision.INFORMS

# Two structurally distinct nodes: one every free method takes on, one only the
# research method declares. Shapes are enums, so nothing here is about a topic.
SHAPE_FREE = QuestionShape(T.Interrogative.WHAT, K.FACT)
SHAPE_PAID = QuestionShape(T.Interrogative.WHY, K.FACT, causal=True)
SHAPE_TIE = QuestionShape(T.Interrogative.WHICH, K.DECISION, comparative=True)


# ---------------------------------------------------------------------------
# the structural oracle: one answer per purpose, no case knowledge
# ---------------------------------------------------------------------------

def oracle(**answers):
    """A case-agnostic responder for FakeProvider. An unscripted purpose gets
    an empty JSON object, which every consumer reads as a real 'nothing found'
    rather than as a default."""
    def respond(call):
        return answers.get(call.purpose, "{}")

    return respond


# ---------------------------------------------------------------------------
# builders: every entity through make_entity, every write through apply()
# ---------------------------------------------------------------------------

def add(reg, kind, payload, *, actor=Actor.PARTNER, status=Status.PROPOSED, relation=INFORMS,
        relevance=None, confidence=None, derived=(), labels=(), locator=None):
    return reg.apply(Add(T.make_entity(
        kind=kind, engagement_id=EID, payload=payload,
        provenance=T.Provenance(actor=actor, actor_ref=f"{actor.value}:1", derived_from=tuple(derived),
                                source_locator=locator),
        confidence=confidence or T.Confidence(None), relevance=relevance or T.Relevance(None),
        relation=relation, status=status, labels=tuple(labels))))


def decision(reg, text="which fulfilment path", role=T.DecisionRole.STATED_REQUEST, origin="client_request"):
    return add(reg, K.DECISION, T.DecisionPayload(statement=text, role=role, origin=origin))


def owner(reg, name="md"):
    return add(reg, K.DECISION_OWNER, T.DecisionOwnerPayload(name=name, role="managing director"))


def objective(reg, text="cut the order cycle time"):
    return add(reg, K.OBJECTIVE, T.ObjectivePayload(text=text), locator=text)


def fact(reg, *, statement="the line runs 40 orders a day", decision_id=None, weight=0.4,
         relation=INFORMS, conf=None):
    return add(reg, K.FACT, T.FactPayload(statement=statement, basis=T.FactBasis.INFERRED),
               relation=relation, relevance=T.Relevance(decision_id, weight),
               confidence=T.Confidence(conf, "verified" if conf is not None else "unknown"))


def issue(reg, decision_id, shape, *, text="what drives the delay", parent=None, weight=1.0):
    return add(reg, K.ISSUE,
               T.IssuePayload(text=text, interrogative=shape.interrogative, target_kind=shape.target_kind,
                              parent_id=parent, quantified=shape.quantified,
                              comparative=shape.comparative, causal=shape.causal,
                              temporal=shape.temporal, weight_to_parent=weight,
                              decisive_for=(decision_id,)),
               relation=DEFINES, relevance=T.Relevance(decision_id, 0.5))


# ---------------------------------------------------------------------------
# test methods: registered in a LOCAL registry, so the builtin library is never
# touched and selection is entirely a function of the shapes above
# ---------------------------------------------------------------------------

def spec(mid, execution, shape, *, calls=0, cost=1, writes=(K.CAPABILITY,)):
    return MethodSpec(
        id=mid, version=1, applicability=(shape,), answers=(shape.interrogative,),
        required_inputs=(_fact_input(),), optional_inputs=(),
        execution=execution, output_kinds=writes, output_schema=None,
        evidence=EvidenceRequirement(), limitations=(), validators=(), cost_class=cost,
        max_model_calls=calls)


def _fact_input():
    from app.engine.methods.contract import InputSpec

    return InputSpec(name="facts", kind=K.FACT, min_count=1, why_needed="a fact to work from")


class _Writer:
    """Writes one CAPABILITY citing the first fact it is shown, plus whatever
    questions the test handed it. Deterministic, cites its input, coins no
    quantity: admissible under S1-S6 whether it runs free or under scope."""

    def __init__(self, method_spec, questions=()):
        self.spec = method_spec
        self._questions = tuple(questions)

    def run(self, ctx):
        facts = [f for f in ctx.registry.query(K.FACT) if f.status not in T.TERMINAL_STATUSES]
        deltas = []
        if facts:
            deltas.append(Add(new_entity(
                ctx, K.CAPABILITY,
                T.CapabilityPayload(text=f"capability from {self.spec.id}",
                                    capability_class=T.CapabilityClass.PROCESS,
                                    gap=T.GapState.PARTIAL, evidence=(facts[0].id,)),
                derived_from=(facts[0].id,), relation=INFORMS, confidence=T.Confidence(None),
                decision_id=None, weight=0.0)))
        return MethodResult(deltas=tuple(deltas), questions=self._questions)


def registry_of(*methods) -> MethodRegistry:
    reg = MethodRegistry()
    for m in methods:
        reg.register(m)
    return reg


def det_method(mid="det", questions=(), cost=1):
    return _Writer(spec(mid, T.ExecutionType.DETERMINISTIC, SHAPE_FREE, cost=cost), questions)


def research_method(mid="research"):
    return _Writer(spec(mid, T.ExecutionType.RESEARCH, SHAPE_PAID, calls=3, cost=3))


def tied_pair():
    return (_Writer(spec("tie_a", T.ExecutionType.DETERMINISTIC, SHAPE_TIE)),
            _Writer(spec("tie_b", T.ExecutionType.DETERMINISTIC, SHAPE_TIE)))


# ---------------------------------------------------------------------------
# scaffolds
# ---------------------------------------------------------------------------

def partner_for(methods, provider):
    return L.Partner(provider, methods=methods)


def state_for(reg, phase=Phase.OPENING):
    return S.EngagementState(registry=reg, phase=phase)


def approved_engagement(reg, methods, provider, *, phase_after=Phase.CHARTER_CONFIRMED):
    """A registry carried to an APPROVED charter through the real path: propose,
    then the client's per-item confirmation."""
    partner = partner_for(methods, provider)
    state = state_for(reg, Phase.DISCOVERY)
    state.turn_n = 1
    proposal = C.propose(reg, turn_number=1, methods=methods)
    state.phase = Phase.CHARTER_PROPOSED
    outcome = partner.confirm_charter(state, proposal.charter.id)
    assert outcome.approved, outcome.refused
    assert state.phase == phase_after
    return partner, state, proposal, outcome


# ===========================================================================
# 1. Turn 1: the structural gaps of an empty registry, and nothing else
# ===========================================================================

def test_opening_statement_asks_only_the_structural_gaps(registry, fake_provider):
    reg = registry(EID)
    methods = registry_of(det_method())
    partner = partner_for(methods, fake_provider(oracle=oracle()))
    state = state_for(reg)

    reply = partner.turn(state, "we are losing customers and I do not know why")

    assert state.phase == Phase.DISCOVERY
    assert reply.turn_n == 1
    asked = reply.questions + reply.evidence_requests
    structural_kinds = {i.kind for i in Q.STRUCTURAL_INPUTS}
    assert asked, "turn 1 asks something"
    for q in asked:
        assert q.payload.asks_for[0].kind in structural_kinds, q.payload.text
    # Bounds, never a fixed count: the batch sits inside the operator's window.
    assert state.bound("MIN_QUESTIONS_PER_TURN") <= len(asked) <= state.bound("MAX_QUESTIONS_PER_TURN")
    # No charter can be ready when nothing has been said yet.
    assert reply.charter is None
    assert reg.query(K.CHARTER) == []


# ===========================================================================
# 2. The charter needs a central decision and a decision owner
# ===========================================================================

def test_charter_requires_a_decision_owner_and_a_central_decision(registry, fake_provider):
    reg = registry(EID)
    methods = registry_of(det_method())
    dec = decision(reg)
    objective(reg)

    # No DECISION_OWNER yet: the ranking may be confident, the charter is not.
    assert C.assemble(reg).decision_owner is None
    assert S.analysis_blockers(reg) == ("no CHARTER approved by the client",)

    payload = C.assemble(reg)
    charter = add(reg, K.CHARTER, payload, relation=DEFINES)
    reg.apply(T.SetStatus(charter.id, Status.APPROVED,
                          T.Provenance(actor=Actor.CLIENT, actor_ref="client:1")))
    blockers = S.analysis_blockers(reg)
    assert any("DECISION_OWNER" in b for b in blockers), blockers
    assert any("central DECISION" in b for b in blockers), blockers

    # With an owner named and the decision made central, both reasons go away.
    own = owner(reg)
    reg.apply(T.Supersede(dec.id, T.make_entity(
        kind=K.DECISION, engagement_id=EID,
        payload=T.DecisionPayload(statement=dec.payload.statement, role=T.DecisionRole.CENTRAL),
        provenance=T.Provenance(actor=Actor.CLIENT, actor_ref="client:1"),
        confidence=T.Confidence(None), relevance=T.Relevance(None), relation=INFORMS,
        status=Status.PROPOSED, entity_id=dec.id)))
    charter2 = add(reg, K.CHARTER,
                   T.CharterPayload(central_decision=dec.id, decision_owner=own.id), relation=DEFINES)
    reg.apply(T.SetStatus(charter2.id, Status.APPROVED,
                          T.Provenance(actor=Actor.CLIENT, actor_ref="client:1")))
    assert S.analysis_blockers(reg) == ()


# ===========================================================================
# 3. Confirmation promotes exactly the listed items
# ===========================================================================

def test_confirm_promotes_exactly_the_listed_items(registry, fake_provider):
    reg = registry(EID)
    methods = registry_of(det_method())
    decision(reg)
    own = owner(reg)
    listed_objective = objective(reg, "cut the order cycle time")
    listed_constraint = add(reg, K.CONSTRAINT, T.ConstraintPayload(text="no new headcount"))

    proposal = C.propose(reg, turn_number=1, methods=methods)
    # Written after the charter was assembled: it is not on the page the client
    # signed, so the signature must not reach it.
    unlisted = objective(reg, "open a second site")

    outcome = C.confirm(reg, proposal.charter.id, turn_number=2)

    assert outcome.approved
    assert set(outcome.confirmed) >= {listed_objective.id, listed_constraint.id, own.id}
    assert unlisted.id not in outcome.confirmed
    assert reg.get(unlisted.id).status == Status.PROPOSED
    assert reg.get(listed_objective.id).status == Status.CONFIRMED
    assert reg.get(proposal.charter.id).status == Status.APPROVED
    # A consultant judgement the charter lists is not the client's to confirm.
    assert all(reg.get(i).authority in (T.Authority.CLIENT, T.Authority.CLIENT_STATED)
               for i in outcome.confirmed)


def test_a_verdict_on_an_unlisted_entity_refuses_the_whole_confirmation(registry):
    reg = registry(EID)
    decision(reg)
    owner(reg)
    listed = objective(reg)
    proposal = C.propose(reg, turn_number=1, methods=MethodRegistry())
    unlisted = objective(reg, "open a second site")

    outcome = C.confirm(reg, proposal.charter.id, verdicts={unlisted.id: C.REJECT})

    assert not outcome.approved
    assert any(unlisted.id in r for r in outcome.refused)
    assert reg.get(proposal.charter.id).status == Status.PROPOSED
    assert reg.get(listed.id).status == Status.PROPOSED, "nothing of a refused batch is written"


# ===========================================================================
# 4. A correction supersedes and re-proposes
# ===========================================================================

def test_a_correction_supersedes_and_reproposes(registry):
    reg = registry(EID)
    decision(reg)
    owner(reg)
    wrong = objective(reg, "cut the order cycle time")
    proposal = C.propose(reg, turn_number=1, methods=MethodRegistry())

    outcome = C.confirm(reg, proposal.charter.id, turn_number=2,
                        verdicts={wrong.id: C.CORRECT},
                        corrections={wrong.id: T.ObjectivePayload(text="cut the delivery cost")})

    assert outcome.approved
    assert outcome.corrected == (wrong.id,)
    assert wrong.id not in outcome.confirmed, "a correction is not a confirmation of itself"
    current = reg.get(wrong.id)
    assert current.payload.text == "cut the delivery cost"
    assert current.status == Status.PROPOSED, "corrected items are re-proposed, not confirmed"
    assert current.provenance.actor == Actor.CLIENT
    lineage = reg.lineage(wrong.id)
    assert any(r.status == Status.SUPERSEDED for r in lineage), "the wrong wording stays queryable"


def test_a_correction_the_registry_refuses_takes_the_approval_with_it(registry):
    reg = registry(EID)
    decision(reg)
    owner(reg)
    turn = add(reg, K.EVIDENCE_SOURCE,
               T.EvidenceSourcePayload(name="turn 1", source_kind=T.SourceKind.CONVERSATION_TURN,
                                       text="we ship 40 orders a day"))
    reg.register_source_text(turn.id, "we ship 40 orders a day")
    client_fact = add(reg, K.FACT,
                      T.FactPayload(statement="we ship 40 orders a day", basis=T.FactBasis.CLIENT_STATED),
                      relation=DEFINES, derived=(turn.id,), locator="we ship 40 orders a day")
    proposal = C.propose(reg, turn_number=1, methods=MethodRegistry())

    outcome = C.confirm(
        reg, proposal.charter.id, turn_number=2, turn_id=turn.id,
        verdicts={client_fact.id: C.CORRECT},
        corrections={client_fact.id: T.FactPayload(statement="we ship four hundred orders a day",
                                                   basis=T.FactBasis.CLIENT_STATED)})

    assert not outcome.approved
    assert any("I2" in r for r in outcome.refused), outcome.refused
    assert reg.get(proposal.charter.id).status == Status.PROPOSED
    assert reg.get(client_fact.id).payload.statement == "we ship 40 orders a day"


def test_approving_the_charter_is_what_makes_a_decision_central(registry):
    reg = registry(EID)
    dec = decision(reg)
    owner(reg)
    objective(reg)
    assert reg.central_decision() is None

    proposal = C.propose(reg, turn_number=1, methods=MethodRegistry())
    outcome = C.confirm(reg, proposal.charter.id, turn_number=2)

    assert outcome.approved and outcome.central_decision == dec.id
    central = reg.central_decision()
    assert central is not None and central.id == dec.id
    assert len([d for d in reg.live(K.DECISION) if d.payload.role == T.DecisionRole.CENTRAL]) == 1


# ===========================================================================
# 5. ANALYSIS is unreachable without an APPROVED charter  [MUTATION]
# ===========================================================================

def test_analysis_is_unreachable_without_an_approved_charter(registry, fake_provider):
    reg = registry(EID)
    methods = registry_of(det_method())
    dec = decision(reg)
    owner(reg)
    objective(reg)
    fact(reg, decision_id=dec.id)
    issue(reg, dec.id, SHAPE_FREE)
    partner = partner_for(methods, fake_provider(oracle=oracle()))

    # A charter that is proposed but not approved, naming a live CENTRAL
    # decision and a live owner: the client's approval is the ONLY thing
    # missing, so nothing but that guard can be what refuses the run. The phase
    # pointer is set by hand because the guard, not the table, is under test.
    C.propose(reg, turn_number=1, methods=methods)
    reg.apply(T.Supersede(dec.id, T.make_entity(
        kind=K.DECISION, engagement_id=EID,
        payload=T.DecisionPayload(statement=dec.payload.statement, role=T.DecisionRole.CENTRAL),
        provenance=T.Provenance(actor=Actor.PARTNER, actor_ref="partner:1"),
        confidence=T.Confidence(None), relevance=T.Relevance(None), relation=INFORMS,
        status=Status.PROPOSED, entity_id=dec.id)))
    state = state_for(reg, Phase.CHARTER_CONFIRMED)
    assert S.approved_charter(reg) is None
    assert reg.central_decision() is not None and reg.live(K.DECISION_OWNER)

    with pytest.raises(S.PhaseError) as caught:
        partner.run_analysis(state)
    assert "no CHARTER approved by the client" in str(caught.value)
    assert state.phase == Phase.CHARTER_CONFIRMED
    assert not [a for a in reg.live(K.ANALYSIS) if a.payload.state is T.AnalysisState.DONE]

    # Approved by the client, the same call runs.
    standing = C.live_proposal(reg)
    assert C.confirm(reg, standing.id, turn_number=1).approved
    run = partner.run_analysis(state)
    assert run.phase in (Phase.SYNTHESIS, Phase.ANALYSIS, Phase.PAUSED_FOR_DISCOVERY)
    assert run.ran, "with the mandate in place the free method runs"


# ===========================================================================
# 6. Free methods run during discovery, paid ones wait  [MUTATION]
# ===========================================================================

def test_research_waits_for_the_charter_while_deterministic_runs(registry, fake_provider):
    reg = registry(EID)
    methods = registry_of(det_method("det"), research_method("research"))
    dec = decision(reg)
    objective(reg)
    fact(reg, decision_id=dec.id)
    free_node = issue(reg, dec.id, SHAPE_FREE, text="what the current state is")
    paid_node = issue(reg, dec.id, SHAPE_PAID, text="why the delay happens")
    partner = partner_for(methods, fake_provider(oracle=oracle()))
    state = state_for(reg, Phase.DISCOVERY)

    reply = partner.turn(state, "orders are late and I need to know what to do")

    ran = {mid for mid, _ in reply.ran}
    assert "det" in ran, "a deterministic method may run during discovery (S6)"
    assert "research" not in ran
    analyses = {a.payload.method_id for a in reg.live(K.ANALYSIS)}
    assert "research" not in analyses, "a paid method leaves no analysis row before the charter"
    assert reg.live(K.SPECIALIST_ASSIGNMENT) == []
    assert reply.refusals == (), reply.refusals
    # The free method's output is on the record, citing what it read.
    caps = reg.live(K.CAPABILITY)
    assert caps and caps[0].provenance.actor == Actor.METHOD
    assert caps[0].provenance.derived_from


# ===========================================================================
# 7. A method's material question pauses analysis  [MUTATION]
# ===========================================================================

def _material_question():
    return T.QuestionPayload(text="which sites are in scope for the change?",
                             asks_for=(T.AsksFor(K.CONSTRAINT),),
                             why="the answer changes which options are feasible",
                             effort=T.EffortClass.OFFHAND, strategy=T.FillStrategy.ASK_CLIENT,
                             material=True)


def test_a_material_question_from_a_method_pauses_analysis(registry, fake_provider):
    reg = registry(EID)
    methods = registry_of(det_method("det", questions=(_material_question(),)))
    dec = decision(reg)
    owner(reg)
    objective(reg)
    fact(reg, decision_id=dec.id)
    issue(reg, dec.id, SHAPE_FREE)
    provider = fake_provider(oracle=oracle())
    partner, state, _, _ = approved_engagement(reg, methods, provider)

    run = partner.run_analysis(state)

    assert run.paused_on, "a new material question stops the analysis"
    assert state.phase == Phase.PAUSED_FOR_DISCOVERY
    assert run.phase == Phase.PAUSED_FOR_DISCOVERY
    paused = reg.get(run.paused_on[0])
    assert paused.kind == K.QUESTION and paused.status == Status.OPEN
    assert paused.payload.material is True


# ===========================================================================
# 8. Evidence that moves the diagnosis amends the charter
# ===========================================================================

def test_evidence_that_changes_the_diagnosis_amends_the_charter(registry, fake_provider):
    reg = registry(EID)
    methods = registry_of(det_method())
    stated = decision(reg, "which warehouse to lease")
    owner(reg)
    objective(reg)
    fact(reg, statement="the current lease ends in June", decision_id=stated.id, weight=0.2,
         relation=INFORMS, conf=0.5)
    provider = fake_provider(oracle=oracle())
    partner, state, proposal, _ = approved_engagement(reg, methods, provider)
    approved = S.approved_charter(reg)
    assert approved.payload.central_decision == stated.id

    # A second candidate the partner inferred, with the evidence now defining it.
    rival = decision(reg, "whether to keep fulfilment in house",
                     role=T.DecisionRole.SUBORDINATE, origin="partner_inferred")
    for n in range(3):
        fact(reg, statement=f"outsourced picking costs more than in house ({n})",
             decision_id=rival.id, weight=1.0, relation=DEFINES, conf=1.0)

    run = partner.run_analysis(state)

    assert run.amendment is not None, "the mandate is re-opened, not silently switched"
    assert run.amendment.payload.amends == approved.id
    assert run.amendment.payload.central_decision == rival.id
    assert run.amendment.status == Status.PROPOSED
    assert state.phase == Phase.CHARTER_PROPOSED
    # The approved charter is untouched: it is what the client agreed to.
    assert reg.get(approved.id).status == Status.APPROVED
    assert reg.central_decision().id == stated.id


# ===========================================================================
# 9. Paid and tied selections become assignments  [MUTATION]
# ===========================================================================

def test_paid_and_tied_selections_become_assignments(registry, fake_provider):
    reg = registry(EID)
    a, b = tied_pair()
    methods = registry_of(research_method("research"), a, b)
    dec = decision(reg)
    owner(reg)
    objective(reg)
    fact(reg, decision_id=dec.id)
    issue(reg, dec.id, SHAPE_PAID, text="why the delay happens")
    issue(reg, dec.id, SHAPE_TIE, text="which option to take")
    provider = fake_provider(oracle=oracle())
    partner, state, _, _ = approved_engagement(reg, methods, provider)

    run = partner.run_analysis(state)

    rows = reg.live(K.SPECIALIST_ASSIGNMENT)
    by_method = sorted(r.payload.method_id for r in rows)
    assert "research" in by_method, "a RESEARCH selection runs only under an Assignment"
    assert by_method.count("tie_a") == 1 and by_method.count("tie_b") == 1, \
        "a tie runs both, so the disagreement is visible"
    assert len(run.assignments) == len(rows) == 3
    assert run.ran == (), "nothing paid or tied ran directly"
    assert len(rows) <= state.bound("MAX_SPECIALISTS_PER_ROUND") * run.rounds


# ===========================================================================
# 10. The live summary is recomputed, never stored  [MUTATION]
# ===========================================================================

def test_live_summary_is_recomputed_not_stored(registry, fake_provider):
    reg = registry(EID)
    methods = registry_of(det_method())
    partner = partner_for(methods, fake_provider(oracle=oracle()))
    state = state_for(reg)

    reply = partner.turn(state, "we are losing customers and I do not know why")
    before = reply.live_summary
    assert before["missing"], "turn 1 has open questions"

    fresh = add(reg, K.QUESTION,
                T.QuestionPayload(text="who signs this off?", asks_for=(T.AsksFor(K.DECISION_OWNER),)),
                status=Status.OPEN)

    after = reply.live_summary
    assert fresh.id in after["missing"], "the summary is a query, not a snapshot"
    assert fresh.id not in before["missing"], "each read is its own answer"
    assert reply.live_summary is not after, "nothing is kept between reads"


# ===========================================================================
# the phase machine itself
# ===========================================================================

def test_the_reply_names_the_turn_a_correction_can_cite(registry, fake_provider):
    reg = registry(EID)
    partner = partner_for(registry_of(det_method()), fake_provider(oracle=oracle()))
    state = state_for(reg)

    reply = partner.turn(state, "we ship 40 orders a day and they are late")

    source = reg.get(reply.turn_id)
    assert source is not None and source.kind == K.EVIDENCE_SOURCE
    assert source.payload.source_kind == T.SourceKind.CONVERSATION_TURN
    # I2 checks a client fact against the turn's own text, so the turn the
    # client corrects in has to be nameable by the caller.
    assert reg.source_text(reply.turn_id) == "we ship 40 orders a day and they are late"


def test_an_undeclared_edge_is_refused(registry):
    reg = registry(EID)
    state = state_for(reg, Phase.DISCOVERY)
    with pytest.raises(S.PhaseError):
        S.advance(state, Phase.ANALYSIS)
    assert state.phase == Phase.DISCOVERY
    assert S.advance(state, Phase.DISCOVERY) == Phase.DISCOVERY, "re-entering a phase is a no-op"


def test_synthesis_waits_until_nothing_is_runnable(registry):
    reg = registry(EID)
    methods = registry_of(det_method())
    dec = decision(reg)
    fact(reg, decision_id=dec.id)
    node = issue(reg, dec.id, SHAPE_FREE)

    assert S.runnable_selections(reg, methods=methods), "the method has its input"
    assert S.synthesis_blockers(reg, rounds_used=0, methods=methods)

    add(reg, K.ANALYSIS,
        T.AnalysisPayload(method_id="det", method_version=1, issue_ids=(node.id,),
                          state=T.AnalysisState.DONE),
        derived=(node.id,))
    assert S.runnable_selections(reg, methods=methods) == []
    assert S.synthesis_blockers(reg, rounds_used=0, methods=methods) == ()


def test_the_charter_is_fourteen_lists_walked_from_the_contract(registry):
    reg = registry(EID)
    dec = decision(reg)
    owner(reg)
    objective(reg)
    payload = C.assemble(reg)
    assert len(C.CHARTER_SECTIONS) == 14
    sections = {section for section, _ in C.listed_ids(payload)}
    assert sections <= set(C.CHARTER_SECTIONS)
    assert "proposed_work_products" not in sections, "declaration ids are not entity ids"
    assert payload.central_decision == dec.id


def test_a_reproposed_charter_with_the_same_content_is_not_rewritten(registry):
    reg = registry(EID)
    decision(reg)
    owner(reg)
    objective(reg)
    first = C.propose(reg, turn_number=1, methods=MethodRegistry())
    again = C.propose(reg, turn_number=2, methods=MethodRegistry())
    assert again.reproposed and again.charter.id == first.charter.id
    assert len(reg.query(K.CHARTER)) == 1


# ===========================================================================
# 11. The bindings a round hands its methods (design 13.2)  [MUTATION x2]
# ===========================================================================

# The three keys the r30 adapter reads out of ctx.settings. They are named here
# as the strings the method reads, not imported, so this file stays a test of
# the seam rather than of one method that happens to use it.
COMMISSION_KEY = "legacy_r30_commission"
BUSINESS_NAME_KEY = "legacy_r30_business_name"
OWNER_EMAIL_KEY = "legacy_r30_owner_email"


class _SettingsSpy(_Writer):
    """A method that records the mapping its context was given. Everything else
    about it is _Writer, so it is admissible under S1-S6 and the seam is the
    only thing under test."""

    def __init__(self, method_spec, questions=()):
        super().__init__(method_spec, questions)
        self.seen = []

    def run(self, ctx):
        self.seen.append(dict(ctx.settings))
        return super().run(ctx)


def spy_free(mid="det"):
    return _SettingsSpy(spec(mid, T.ExecutionType.DETERMINISTIC, SHAPE_FREE))


def spy_paid(mid="research"):
    return _SettingsSpy(spec(mid, T.ExecutionType.RESEARCH, SHAPE_PAID, calls=3, cost=3))


def bindings():
    """One binding of each kind the seam carries: a callable the caller closed
    over its own session, and the two plain strings that are facts about the
    account rather than about the business."""
    def commission(_inputs):                             # pragma: no cover - never called here
        raise AssertionError("nothing in this test commissions anything")

    return commission, {COMMISSION_KEY: commission,
                        BUSINESS_NAME_KEY: "the engagement's filing name",
                        OWNER_EMAIL_KEY: "owner@example.com"}


def test_a_binding_reaches_a_free_method(registry, fake_provider):
    """A method is a pure function of its context and opens no session of its
    own, so what it cannot compute from the registry has to arrive in
    ctx.settings. Removing the merge leaves the bounds only, and a costed
    adapter would report a missing seam on a round that supplied one."""
    reg = registry(EID)
    method = spy_free()
    methods = registry_of(method)
    dec = decision(reg)
    objective(reg)
    fact(reg, decision_id=dec.id)
    issue(reg, dec.id, SHAPE_FREE)
    partner = partner_for(methods, fake_provider(oracle=oracle()))
    state = state_for(reg, Phase.DISCOVERY)
    commission, given = bindings()

    reply = partner.turn(state, "orders are late", context_settings=given)

    assert reply.ran, "the deterministic method ran during discovery"
    assert method.seen, "the method was given a context"
    settings = method.seen[0]
    assert settings[COMMISSION_KEY] is commission, "the callable arrives itself, not a copy"
    assert settings[BUSINESS_NAME_KEY] == given[BUSINESS_NAME_KEY]
    assert settings[OWNER_EMAIL_KEY] == given[OWNER_EMAIL_KEY]
    # The bounds are still all there: the bindings are merged over them, not
    # instead of them, so a method reads one mapping and finds both.
    assert set(settings) >= set(T.BOUNDS)
    assert settings["MAX_ANALYSIS_ROUNDS"] == state.bound("MAX_ANALYSIS_ROUNDS")


def test_a_binding_reaches_a_method_that_runs_under_an_assignment(registry, fake_provider):
    """The r30 adapter is MODEL_ASSISTED, so the only path it ever takes is the
    assignment one. A seam that reached free runs alone would be a seam the
    method that needs it never sees."""
    reg = registry(EID)
    method = spy_paid()
    methods = registry_of(method)
    dec = decision(reg)
    owner(reg)
    objective(reg)
    fact(reg, decision_id=dec.id)
    issue(reg, dec.id, SHAPE_PAID, text="why the delay happens")
    provider = fake_provider(oracle=oracle())
    partner, state, _, _ = approved_engagement(reg, methods, provider)
    commission, given = bindings()

    run = partner.run_analysis(state, context_settings=given)

    assert run.assignments, "a RESEARCH selection runs under an Assignment"
    assert method.seen, "the specialist ran the method"
    settings = method.seen[0]
    assert settings[COMMISSION_KEY] is commission
    assert settings[OWNER_EMAIL_KEY] == given[OWNER_EMAIL_KEY]
    assert set(settings) >= set(T.BOUNDS), "the assignment's context still carries every bound"


def test_a_binding_cannot_move_an_operators_ceiling(registry, fake_provider):
    """A bound comes from Settings so an operator can move it and see it. A
    per-call binding that could overwrite one would make the ceiling whatever
    the last caller said, which is why a colliding key is dropped."""
    reg = registry(EID)
    method = spy_free()
    methods = registry_of(method)
    dec = decision(reg)
    objective(reg)
    fact(reg, decision_id=dec.id)
    issue(reg, dec.id, SHAPE_FREE)
    partner = partner_for(methods, fake_provider(oracle=oracle()))
    state = state_for(reg, Phase.DISCOVERY)
    operator_value = state.bound("MAX_SPECIALISTS_PER_ROUND")

    partner.turn(state, "orders are late",
                 context_settings={"MAX_SPECIALISTS_PER_ROUND": operator_value + 99,
                                   COMMISSION_KEY: "kept"})

    assert method.seen
    settings = method.seen[0]
    assert settings["MAX_SPECIALISTS_PER_ROUND"] == operator_value
    assert settings[COMMISSION_KEY] == "kept", "only the colliding key is dropped"


def test_settings_bounds_carries_bounds_and_nothing_else(registry):
    """state.settings_bounds() is the operator's side of the mapping: derived
    from the frozen name table, so a binding can never be mistaken for a
    ceiling. The merge that adds bindings lives in the loop, per call."""
    reg = registry(EID)
    state = state_for(reg)

    assert set(state.settings_bounds()) == set(T.BOUNDS)
    assert COMMISSION_KEY not in state.settings_bounds()
    # No caller and no bindings: the mapping a method reads is exactly the
    # bounds, so nothing about the seam changes an engagement that has none.
    assert L._method_settings(state) == dict(state.settings_bounds())
    assert L._method_settings(state, None) == dict(state.settings_bounds())


def test_methods_read_the_same_mapping_whichever_path_they_take(registry, fake_provider):
    """Free run and assignment run are two doors into one library. If they
    handed different mappings, a method's behaviour would depend on how it
    happened to be selected rather than on what it was told."""
    reg = registry(EID)
    free, paid = spy_free("det"), spy_paid("research")
    methods = registry_of(free, paid)
    dec = decision(reg)
    owner(reg)
    objective(reg)
    fact(reg, decision_id=dec.id)
    issue(reg, dec.id, SHAPE_FREE, text="what the current state is")
    issue(reg, dec.id, SHAPE_PAID, text="why the delay happens")
    provider = fake_provider(oracle=oracle())
    partner, state, _, _ = approved_engagement(reg, methods, provider)
    _, given = bindings()

    partner.run_analysis(state, context_settings=given)

    assert free.seen and paid.seen, "both doors were used"
    for key in (COMMISSION_KEY, BUSINESS_NAME_KEY, OWNER_EMAIL_KEY):
        assert free.seen[0][key] == paid.seen[0][key]
