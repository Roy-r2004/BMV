"""The analysis loop past its first tier, and the two producers it feeds.

Before this wave the engine executed exactly ONE tier of its own dependency
graph and stopped: a method whose inputs are another method's outputs was
unsatisfied on the first pass, "nothing runnable right now" was read as
"analysis is complete", the phase move to SYNTHESIS is one-way, and two kinds
the products read (RECOMMENDATION, EVALUATION_CRITERION) had no writer at all.
Every test here pins one of the laws that closed that, and each names the
mutation it dies under.

  attempted methods stop holding a node's slot   -> test_a_finished_method_stops_holding_its_slot
  the ceiling is a bound, never a literal        -> test_the_methods_per_issue_ceiling_is_an_operator_bound
  "not runnable now" is not "finished"           -> test_analysis_is_not_finished_while_a_producer_could_feed_it
  ...nor while the client still owes an answer   -> test_analysis_is_not_finished_while_the_client_still_owes_an_answer
  ...and the round ceiling still ends it         -> test_the_round_ceiling_ends_analysis_unconditionally
  ids come from the registry, not from the view  -> test_reserved_ids_clear_rows_the_window_hides
  a node another run placed is not superseded    -> test_issue_tree_does_not_supersede_another_runs_node
  a tie cannot force an S4 refusal               -> test_a_tied_decision_owned_method_runs_directly
  ...and the loop and the door read one rule     -> test_the_loop_routes_exactly_what_run_free_admits
  criteria restate the client's declarations     -> test_a_criterion_restates_a_declaration_and_cites_it
  criteria are never born weighted               -> test_a_criterion_is_never_born_weighted
  one criterion per declaration                  -> test_criteria_are_not_restated_twice
  advice traces to confirmed evidence            -> test_no_recommendation_without_admitted_support
  advice is never born approved                  -> test_a_recommendation_is_born_proposed
  advice names the route it selects              -> test_option_id_is_named_only_when_the_lineage_singles_one_out
  one recommendation per route                   -> test_a_route_is_not_advised_twice
  the client can settle their own words          -> test_the_client_confirms_what_the_playback_showed
  licensed advice stops being advice             -> test_licensed_advice_is_withdrawn_and_put_to_an_adviser
  ...and the bundle's own synthesis does it      -> test_the_bundle_synthesis_withdraws_licensed_advice
  the fake fills the fields it was told about    -> test_the_oracle_fills_the_fields_the_instructions_name
  the fake may propose a capability-classed node -> test_the_oracle_proposes_the_capability_classes_it_was_shown
  a bounded decomposition moves over the window  -> test_a_bounded_decomposition_moves_across_the_window
  ...and so do the shapes it may carry           -> test_the_shapes_a_decomposition_reaches_move_as_the_tree_grows
  production is bounded per engagement           -> test_an_engagement_holds_only_so_many_rows_of_one_conclusion
  ...and a full method stops being offered       -> test_a_method_whose_conclusions_are_all_full_stops_being_offered
  a free run over its budget is blocked whole    -> test_a_free_run_larger_than_its_budget_is_blocked_whole
  ...and ONE full conclusion stops the offer     -> test_a_method_is_not_offered_while_any_conclusion_it_writes_is_full
  a scarce round buys breadth before depth       -> test_a_scarce_round_spends_its_budget_on_work_not_yet_done
  advice names what it was judged against        -> test_advice_names_the_criteria_it_was_judged_against
  advice that chooses nothing is a finding       -> test_advice_that_selects_no_route_is_a_finding
  advice does not repeat its own evidence        -> test_advice_does_not_repeat_the_evidence_it_rests_on
  one hypothesis per causal claim                -> test_the_same_causal_claim_is_one_hypothesis
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.engine import types as T
from app.engine.benchmark import oracle as O
from app.engine.llm import ModelCall
from app.engine.methods.contract import (
    METHODS, InputState, MethodContext, QuestionShape, Selection, select_methods,
)
from app.engine.partner import charter as CH
from app.engine.partner import state as ST
from app.engine.registry import ScopedView
from app.engine.specialists.assignment import DECISION_OWNED_KINDS
from app.engine.specialists.runner import AssignmentRequired, run_free
from app.engine.synthesis import recommend as REC
from app.engine.templating import render

import app.engine.methods.builtin  # noqa: F401  - registration by import
from app.engine.methods.builtin import capability_gap as CG
from app.engine.methods.builtin import recommendation as RM


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def add(reg, kind, payload, *, derived_from=(), actor=T.Actor.PARTNER, status=T.Status.PROPOSED,
        actor_ref=None, decision_id="DEC-1", relation=T.RelationToCentralDecision.INFORMS):
    return reg.apply(T.Add(T.make_entity(
        kind=kind, engagement_id=reg.engagement_id, payload=payload,
        provenance=T.Provenance(actor=actor, actor_ref=actor_ref or f"{actor.value}:probe",
                                derived_from=tuple(derived_from)),
        confidence=T.Confidence(None), relevance=T.Relevance(decision_id, 0.5),
        relation=relation, status=status)))


def turn_with(reg, *statements):
    """The conversation turn a client fact must cite (I2), and the source text
    the registry hashes it against."""
    text = "\n".join(statements)
    source = add(reg, T.Kind.EVIDENCE_SOURCE,
                 T.EvidenceSourcePayload(name="turn", source_kind=T.SourceKind.CONVERSATION_TURN,
                                         text=text, received_at="2026-01-01T00:00:00+00:00"),
                 actor=T.Actor.CLIENT, decision_id=None)
    reg.register_source_text(source.id, text)
    return source


def engagement(registry, *, statements=("the line ran 40 hours",)):
    """A registry with a central decision, an objective the client declared and
    a client-stated fact that cites the turn it was said in."""
    reg = registry()
    decision = add(reg, T.Kind.DECISION,
                   T.DecisionPayload(statement="which way", role=T.DecisionRole.CENTRAL),
                   decision_id=None)
    source = turn_with(reg, *statements)
    objective = add(reg, T.Kind.OBJECTIVE, T.ObjectivePayload(text="cut the queue", priority=1),
                    derived_from=(source.id,), actor=T.Actor.CLIENT, decision_id=decision.id)
    fact = add(reg, T.Kind.FACT,
               T.FactPayload(statement=statements[0], basis=T.FactBasis.CLIENT_STATED),
               derived_from=(source.id,), actor=T.Actor.CLIENT, decision_id=decision.id)
    return reg, decision, objective, fact, source


def issue(reg, *, interrogative=T.Interrogative.WHICH, target=T.Kind.DECISION, comparative=True,
          decision_id="DEC-1", capability_class=None):
    return add(reg, T.Kind.ISSUE, T.IssuePayload(
        text="which way", interrogative=interrogative, target_kind=target, parent_id=None,
        comparative=comparative, capability_class=capability_class, weight_to_parent=1.0,
        decisive_for=(decision_id,)), derived_from=(decision_id,), decision_id=decision_id)


def ctx(reg, issue_id, *, method_id, provider=None):
    return MethodContext(registry=reg, provider=provider, calc=None, actor=T.Actor.METHOD,
                         actor_ref=f"method:{method_id}@1", issue_ids=(issue_id,))


def run_method(reg, method_id, issue_id, *, provider=None):
    return METHODS.get(method_id).run(ctx(reg, issue_id, method_id=method_id, provider=provider))


def written(result, kind):
    return [d.entity for d in result.deltas
            if getattr(d, "entity", None) is not None and d.entity.kind is kind]


def validate(method_id, view, result):
    out = []
    for v in METHODS.get(method_id).spec.validators:
        out.extend(v(view, result))
    return out


def confirm(reg, entity, actor=T.Actor.CLIENT):
    return reg.apply(T.SetStatus(entity.id, T.Status.CONFIRMED,
                                 T.Provenance(actor=actor, actor_ref=f"{actor.value}:probe")))


# ===========================================================================
# 1. Selection: a finished method stops holding a node's slot
# ===========================================================================

def test_a_finished_method_stops_holding_its_slot(registry):
    """`select_methods` truncates at MAX_METHODS_PER_ISSUE. Without the
    `exclude` predicate the ranking does not know what already ran, so the
    methods that ran first keep the node's slots for the life of the
    engagement - and a method whose inputs those very runs wrote can never be
    reached. Mutation: drop `exclude=` from `open_selections`."""
    reg, decision, objective, fact, _src = engagement(registry)
    node = issue(reg, decision_id=decision.id)

    matching = [m.spec.id for m in METHODS.all()
                if any(QuestionShape.of(node) == s or _takes(s, node) for s in m.spec.applicability)]
    assert len(matching) > int(T.BOUNDS["MAX_METHODS_PER_ISSUE"]), (
        "the node must be contested for the ceiling to bind; this check would be vacuous otherwise")

    first = {s.method_id for s in ST.open_selections(reg)}
    assert first and len(first) <= int(T.BOUNDS["MAX_METHODS_PER_ISSUE"])

    # Record every chosen method as attempted on this node, exactly as a run
    # would, and ask again: the next-ranked methods must now be reachable.
    for method_id in sorted(first):
        add(reg, T.Kind.ANALYSIS, T.AnalysisPayload(method_id=method_id, method_version=1,
                                                    issue_ids=(node.id,), state=T.AnalysisState.DONE),
            derived_from=(node.id,))
    second = {s.method_id for s in ST.open_selections(reg)}
    assert second and not (second & first), (
        "an attempted method is still being offered the node it already ran on")


def _takes(decl: QuestionShape, node) -> bool:
    from app.engine.methods.contract import shape_matches
    return shape_matches(decl, QuestionShape.of(node))


def test_the_methods_per_issue_ceiling_is_an_operator_bound(registry, monkeypatch):
    """No bound is a literal: the ceiling is MAX_METHODS_PER_ISSUE, it is in
    BOUNDS with a settings field beside it, and moving it moves how many
    methods a node offers. Mutation: put the number back in the signature."""
    from app.config import settings

    assert "MAX_METHODS_PER_ISSUE" in T.BOUNDS
    assert getattr(settings, "ENGINE_MAX_METHODS_PER_ISSUE") == T.BOUNDS["MAX_METHODS_PER_ISSUE"]

    reg, decision, _obj, _fact, _src = engagement(registry)
    node = issue(reg, decision_id=decision.id)
    available = len(select_methods([node], reg, max_per_issue=len(list(METHODS.all()))))
    narrow = select_methods([node], reg, max_per_issue=1)
    assert len(narrow) == 1 and available > 1

    # The caller's number is honoured, and - the half a literal survives - so
    # is the BOUND when the caller states none. Moving the bound has to move
    # the default, or the default is a number written twice and only one of
    # them is the operator's.
    assert available > int(T.BOUNDS["MAX_METHODS_PER_ISSUE"]), (
        "the node must offer more methods than the ceiling or this is vacuous")
    for ceiling in (1, int(T.BOUNDS["MAX_METHODS_PER_ISSUE"]) + 1):
        monkeypatch.setitem(T.BOUNDS, "MAX_METHODS_PER_ISSUE", ceiling)
        assert len(select_methods([node], reg)) == min(available, ceiling), (
            "the default ceiling is a literal, not MAX_METHODS_PER_ISSUE")


# ===========================================================================
# 2. The synthesis guard: "nothing runnable now" is not "analysis is finished"
# ===========================================================================

def test_analysis_is_not_finished_while_a_producer_could_feed_it(registry):
    """The primary defect this wave closed, half one. `runnable_selections`
    asks only what is satisfied AT THIS INSTANT; a method whose inputs another
    method is about to write is unsatisfied on every first pass. Mutation:
    delete the `outstanding_inputs` term from `synthesis_blockers`."""
    reg, decision, _obj, _fact, _src = engagement(registry)
    # Two nodes, one tier apart: capability_gap is fully fed on the first and
    # writes a CAPABILITY; make_buy_partner takes on the second and is missing
    # exactly that kind.
    # WHAT on a capability rather than HOW: both are capability_gap's declared
    # shapes, and on WHAT every method that takes the node on is fed by what
    # the registry already holds - so the feeder contributes nothing to
    # `waiting` and the assertion below is about the waiter alone.
    # (`operating_model` also answers HOW on a capability and requires two of
    # them, so a HOW node is legitimately BOTH a feeder and a waiter.)
    feeder = issue(reg, interrogative=T.Interrogative.WHAT, target=T.Kind.CAPABILITY,
                   comparative=False, decision_id=decision.id)
    waiter = issue(reg, interrogative=T.Interrogative.WHICH, target=T.Kind.CAPABILITY,
                   comparative=True, decision_id=decision.id)
    runnable = {s.method_id for s in ST.runnable_selections(reg)}
    assert "capability_gap" in runnable and "make_buy_partner" not in runnable

    waiting = ST.outstanding_inputs(reg)
    assert any(waiter.id in w and "make_buy_partner" in w for w in waiting)
    assert feeder.id not in " ".join(waiting)
    assert ST.synthesis_blockers(reg, rounds_used=0)

    # And the frontier closes: once the feeder has run and its kind is
    # registered, nothing is waiting on a promise any more.
    add(reg, T.Kind.CAPABILITY,
        T.CapabilityPayload(text="scheduling", capability_class=T.CapabilityClass.PROCESS,
                            gap=T.GapState.MISSING, evidence=()),
        derived_from=(decision.id,), decision_id=decision.id)
    for method_id in sorted(runnable):
        add(reg, T.Kind.ANALYSIS, T.AnalysisPayload(method_id=method_id, method_version=1,
                                                    issue_ids=(feeder.id,), state=T.AnalysisState.DONE),
            derived_from=(feeder.id,))
    assert "make_buy_partner" in {s.method_id for s in ST.runnable_selections(reg)}


def test_analysis_is_not_finished_while_the_client_still_owes_an_answer(registry):
    """The primary defect this wave closed, half two, and the one the first
    term cannot see: NOTHING is runnable, so `runnable_selections` is empty and
    SYNTHESIS looks reachable - while the very answer that would feed the
    blocked method is a question the client has been asked and has not given.
    Because the phase move is one-way, that answer could never be used.
    Mutation: delete the `outstanding_inputs` term from `synthesis_blockers`."""
    reg, decision, _obj, _fact, _src = engagement(registry)
    waiter = issue(reg, interrogative=T.Interrogative.WHICH, target=T.Kind.CAPABILITY,
                   comparative=True, decision_id=decision.id)
    assert ST.runnable_selections(reg) == [], "the first term must be silent or this is vacuous"
    assert ST.synthesis_blockers(reg, rounds_used=0) == ()

    asked = add(reg, T.Kind.QUESTION,
                T.QuestionPayload(text="which capabilities are in question?",
                                  asks_for=(T.AsksFor(T.Kind.CAPABILITY),), issue_ids=(waiter.id,),
                                  strategy=T.FillStrategy.ASK_CLIENT),
                derived_from=(waiter.id,), status=T.Status.OPEN)
    waiting = ST.outstanding_inputs(reg)
    assert any(waiter.id in w and "make_buy_partner" in w for w in waiting)
    assert ST.synthesis_blockers(reg, rounds_used=0), (
        "SYNTHESIS is reachable although the answer that would feed a blocked "
        "method is still outstanding with the client")

    # An answered question is no longer OPEN, and the wait ends with it.
    reg.apply(T.SetStatus(asked.id, T.Status.RESOLVED,
                          T.Provenance(actor=T.Actor.PARTNER, actor_ref="partner:probe")))
    assert ST.outstanding_inputs(reg) == []
    assert ST.synthesis_blockers(reg, rounds_used=0) == ()


def test_the_round_ceiling_ends_analysis_unconditionally(registry):
    """Termination: whatever is still waiting, MAX_ANALYSIS_ROUNDS ends it.
    An engagement that could not deliver would be a worse defect than one that
    delivered early. Mutation: move the ceiling check below the new term."""
    reg, decision, _obj, _fact, _src = engagement(registry)
    issue(reg, interrogative=T.Interrogative.HOW, target=T.Kind.DECISION, comparative=False,
          decision_id=decision.id)
    assert ST.synthesis_blockers(reg, rounds_used=0)
    ceiling = int(T.BOUNDS["MAX_ANALYSIS_ROUNDS"])
    assert ST.synthesis_blockers(reg, rounds_used=ceiling) == ()


def test_the_two_halves_of_left_to_run_read_one_list(registry):
    """The loop runs what the guard counts. `open_selections` is that one
    list, so a method the loop skips and a method the guard counts can never
    be different sets."""
    reg, decision, _obj, _fact, _src = engagement(registry)
    issue(reg, decision_id=decision.id)
    everything = ST.open_selections(reg)
    runnable = ST.runnable_selections(reg)
    assert set(s.method_id for s in runnable) <= set(s.method_id for s in everything)
    assert all(not s.inputs.missing for s in runnable)


# ===========================================================================
# 3. Ids are the registry's to give, not the window's to count
# ===========================================================================

def test_reserved_ids_clear_rows_the_window_hides(registry):
    """A specialist's ScopedView holds its declared inputs and nothing else, so
    an id counted off it collides with a row the assignment was never shown and
    I6 refuses the whole batch - which is what retired the issue tree after its
    first expansion. Mutation: count `reserve_ids` off `view.query(kind)`."""
    reg, decision, _obj, _fact, _src = engagement(registry)
    nodes = [issue(reg, decision_id=decision.id) for _ in range(4)]
    window = ScopedView(reg, [nodes[0].id])
    assert len(window.query(T.Kind.ISSUE)) == 1, "the window must hide rows or this is vacuous"

    reserved = window.reserve_ids(T.Kind.ISSUE, 2)
    live_ids = {e.id for e in reg.query(T.Kind.ISSUE)}
    assert len(reserved) == 2 and not (set(reserved) & live_ids)
    # And the counter moved: the same window never offers one id twice.
    assert not (set(window.reserve_ids(T.Kind.ISSUE, 2)) & set(reserved))
    # A row written on a reserved id is admitted; the collision is gone.
    written_row = add(reg, T.Kind.ISSUE, nodes[0].payload, derived_from=(decision.id,),
                      decision_id=decision.id)
    assert written_row.id not in live_ids


def test_issue_tree_reserves_its_ids_through_the_view(registry):
    """The issue tree's pre-assigned ids come from the same door, so a graft
    made inside an assignment cannot collide with the tree outside it."""
    from app.engine.methods.builtin.issue_tree import _issue_ids

    reg, decision, _obj, _fact, _src = engagement(registry)
    nodes = [issue(reg, decision_id=decision.id) for _ in range(3)]
    window = ScopedView(reg, [nodes[0].id])
    fresh = _issue_ids(window, 2)
    assert not (set(fresh) & {e.id for e in reg.query(T.Kind.ISSUE)})


# ===========================================================================
# 4. The issue tree stops colliding with the rows another run placed
# ===========================================================================

def test_issue_tree_does_not_supersede_another_runs_node(registry, fake_provider):
    """S1 refuses a Supersede against a row this assignment did not create, and
    S1 is right. The tree therefore attaches to a node another run already
    placed instead of restating it. Mutation: emit `Supersede(old.id, entity)`
    for a node whose actor_ref is not this run's."""
    reg, decision, _obj, _fact, source = engagement(registry)
    root = add(reg, T.Kind.ISSUE, T.IssuePayload(
        text="root", interrogative=T.Interrogative.WHAT, target_kind=T.Kind.DECISION,
        parent_id=None, weight_to_parent=1.0, decisive_for=(decision.id,)),
        derived_from=(decision.id,), decision_id=decision.id, actor_ref="specialist:SPE-1")
    child = add(reg, T.Kind.ISSUE, T.IssuePayload(
        text="a child another run placed", interrogative=T.Interrogative.WHY,
        target_kind=T.Kind.OBJECTIVE, parent_id=root.id, causal=True, weight_to_parent=0.5,
        decisive_for=(decision.id,)), derived_from=(decision.id,), decision_id=decision.id,
        actor_ref="specialist:SPE-1")

    node = {"text": "a child another run placed", "parent_id": root.id, "temp_id": "n0",
            "interrogative": "why", "target_kind": "objective", "capability_class": None,
            "quantified": False, "comparative": False, "causal": True, "temporal": False,
            "weight_to_parent": 0.5, "derived_from": [decision.id], "decisive_for": [decision.id],
            "evidence_needed": []}
    provider = fake_provider(script={"issue_tree": [json.dumps({"nodes": [node]})]})
    result = METHODS.get("issue_tree").run(
        MethodContext(registry=reg, provider=provider, calc=None, actor=T.Actor.SPECIALIST,
                      actor_ref="specialist:SPE-2", issue_ids=(root.id,)))
    superseded = [d for d in result.deltas if isinstance(d, T.Supersede)]
    assert superseded == [], "the run restated a node it does not own; S1 would reject the batch"
    assert any("duplicate" in f.law for f in result.findings), \
        "the restatement was not recorded at all"
    assert reg.get(child.id).status not in T.TERMINAL_STATUSES


# ===========================================================================
# 5. A rank tie may not force an S4 refusal on a free method
# ===========================================================================

def test_a_tied_decision_owned_method_runs_directly(registry):
    """S4 refuses a specialist a RECOMMENDATION, a TRADE_OFF or an OPTION on a
    decision its assignment does not target, and the central decision is
    forbidden on every assignment. A tie must therefore not push such a method
    under one, or its whole result is rejected for a reason about specialists.
    Mutation: drop the DECISION_OWNED_KINDS exception from `run_free`."""
    reg, decision, _obj, _fact, _src = engagement(registry)
    node = issue(reg, decision_id=decision.id)
    spec = METHODS.get("decision_criteria").spec
    assert not any(k in DECISION_OWNED_KINDS for k in spec.output_kinds)

    empty = InputState((), ())
    tied_criteria = Selection(node.id, "decision_criteria", empty, rank_key=(), tied=True)
    with pytest.raises(AssignmentRequired):
        run_free(tied_criteria, ctx(reg, node.id, method_id="decision_criteria"))

    tied_advice = Selection(node.id, "recommendation", empty, rank_key=(), tied=True)
    result = run_free(tied_advice, ctx(reg, node.id, method_id="recommendation"))
    assert result is not None, "a tied decision-owned method still cannot run anywhere"


def test_the_loop_routes_exactly_what_run_free_admits(registry):
    """The exception has to be written in BOTH doors or it is written in
    neither. `run_free` admits a tied decision-owned method; the loop is what
    decides whether that method is ever offered to `run_free` at all, and a
    loop that routes it to an assignment instead never reaches the door that
    would have let it through - its whole result is then rejected under S4 for
    a reason about specialists.

    So the law is an agreement, not a value: for every registered method and
    both tie states, the loop's routing and the door's admission are the same
    boolean. The routing side is read from `_runs_directly` itself rather than
    restated here: a test that recomputed the rule would agree with itself
    however the engine changed. Mutation: drop `_decision_owned(spec)` from
    `_runs_directly`.
    """
    from app.engine.partner.loop import _runs_directly

    reg, decision, _obj, _fact, _src = engagement(registry)
    node = issue(reg, decision_id=decision.id)
    exercised = 0
    for method in METHODS.all():
        spec = method.spec
        for tied in (False, True):
            selection = Selection(node.id, spec.id, InputState((), ()), rank_key=(), tied=tied)
            routed_free = _runs_directly(spec, selection)
            try:
                run_free(selection, ctx(reg, node.id, method_id=spec.id))
                admitted = True
            except AssignmentRequired:
                admitted = False
            except Exception:
                # Past the door and failed on its own work, which is the
                # method's business and not this law's.
                admitted = True
            assert routed_free == admitted, (
                f"the loop routes {spec.id} (tied={tied}) {'free' if routed_free else 'to an assignment'} "
                f"but run_free {'admits' if admitted else 'refuses'} it")
            if tied and admitted:
                exercised += 1
    assert exercised, "no tied method is admitted anywhere; the exception is untested"


def test_every_decision_owned_kind_is_one_s4_actually_refuses():
    """The table is not a second opinion: the kinds named are the kinds the
    admission rule checks."""
    assert set(DECISION_OWNED_KINDS) == {T.Kind.RECOMMENDATION, T.Kind.TRADE_OFF, T.Kind.OPTION}


# ===========================================================================
# 6. decision_criteria (DC1-DC3)
# ===========================================================================

def test_decision_criteria_is_registered_and_selected_by_shape(registry):
    """A method is a method: declared shapes, declared inputs, an execution
    type, validators - and registering it took no orchestrator change."""
    spec = METHODS.get("decision_criteria").spec
    assert spec.execution in T.FREE_EXECUTION and spec.max_model_calls == 0
    assert T.Kind.EVALUATION_CRITERION in spec.output_kinds
    assert spec.validators and spec.applicability
    reg, decision, _obj, _fact, _src = engagement(registry)
    node = issue(reg, decision_id=decision.id)
    assert "decision_criteria" in {s.method_id for s in select_methods([node], reg, max_per_issue=9)}


def test_a_criterion_restates_a_declaration_and_cites_it(registry):
    """DC1. A criterion the client never declared is the consultant's own
    priority entering the comparison under the client's name. Mutation: word
    the criterion from the issue node instead of from the declaration."""
    reg, decision, objective, _fact, _src = engagement(registry)
    node = issue(reg, decision_id=decision.id)
    result = run_method(reg, "decision_criteria", node.id)
    rows = written(result, T.Kind.EVALUATION_CRITERION)
    assert rows, "no criterion was written from a declared objective"
    assert all(objective.id in r.provenance.derived_from for r in rows if r.payload.text == objective.payload.text)
    assert {r.payload.text for r in rows} == {objective.payload.text}
    assert validate("decision_criteria", reg, result) == []

    doctored = replace(result, deltas=(T.Add(replace(
        rows[0], payload=replace(rows[0].payload, text="a priority nobody declared"))),))
    laws = {f.law for f in validate("decision_criteria", reg, doctored)}
    assert "M.decision_criteria.reworded_criterion" in laws


def test_a_criterion_is_never_born_weighted(registry):
    """DC2. Only the client's weights may rank options (O3); a criteria writer
    that set its own would rank them on the consultant's priorities under the
    client's name. Mutation: write `weight=1.0, weight_set_by=CONSULTANT`."""
    reg, decision, _obj, _fact, _src = engagement(registry)
    node = issue(reg, decision_id=decision.id)
    result = run_method(reg, "decision_criteria", node.id)
    rows = written(result, T.Kind.EVALUATION_CRITERION)
    assert rows and all(r.payload.weight is None and r.payload.weight_set_by is None for r in rows)

    doctored = replace(result, deltas=(T.Add(replace(
        rows[0], payload=replace(rows[0].payload, weight=1.0,
                                 weight_set_by=T.Authority.CONSULTANT))),))
    laws = {f.law for f in validate("decision_criteria", reg, doctored)}
    assert "M.decision_criteria.consultant_weight" in laws


def test_criteria_are_not_restated_twice(registry):
    """DC3. The same declaration restated on a second run would count twice in
    any coverage the comparison reads. Mutation: drop `already_restated`."""
    reg, decision, _obj, _fact, _src = engagement(registry)
    node = issue(reg, decision_id=decision.id)
    first = run_method(reg, "decision_criteria", node.id)
    reg.apply_all(list(first.deltas))
    again = run_method(reg, "decision_criteria", node.id)
    assert written(again, T.Kind.EVALUATION_CRITERION) == []


def test_criteria_are_asked_for_when_the_client_declared_nothing(registry):
    """Absence stays absent: with nothing declared the method asks, it does not
    name criteria of its own."""
    reg = registry()
    add(reg, T.Kind.DECISION, T.DecisionPayload(statement="which way", role=T.DecisionRole.CENTRAL),
        decision_id=None)
    node = issue(reg, decision_id="DEC-1")
    result = run_method(reg, "decision_criteria", node.id)
    assert written(result, T.Kind.EVALUATION_CRITERION) == []
    assert result.questions and T.Kind.OBJECTIVE in {a.kind for q in result.questions for a in q.asks_for}


# ===========================================================================
# 7. recommendation (R1-R4)
# ===========================================================================

def advised_registry(registry, *, supported=True):
    """An engagement with two registered ROUTES, the comparison that weighs
    them against each other, a lineage that reaches (or does not reach)
    evidence a support law admits, and a step that takes the first route.

    The route is the subject: a recommendation selects one of the routes the
    engagement registered and says to take it, the rival is what it was taken
    over, and the ACTION is how. The rival and the TRADE_OFF are part of the
    fixture because advice that names no comparison cannot say what it beat -
    the recommender will not write one, and the release gate (L15/L16) reads
    the same relation.
    """
    reg, decision, objective, fact, source = engagement(registry)
    if supported:
        confirm(reg, fact)
    capability = add(reg, T.Kind.CAPABILITY,
                     T.CapabilityPayload(text="scheduling", capability_class=T.CapabilityClass.PROCESS,
                                         gap=T.GapState.MISSING, evidence=(fact.id,)),
                     derived_from=(fact.id,), decision_id=decision.id)
    option = add(reg, T.Kind.OPTION,
                 T.OptionPayload(text="buy scheduling in", decision_id=decision.id,
                                 mechanism="buy", evidence=(capability.id,)),
                 derived_from=(capability.id,), decision_id=decision.id)
    rival = add(reg, T.Kind.OPTION,
                T.OptionPayload(text="stand scheduling up in house", decision_id=decision.id,
                                mechanism="make", evidence=(capability.id,)),
                derived_from=(capability.id,), decision_id=decision.id)
    # Something the engagement registered that tells the two routes apart, and
    # tells them apart the way a COST and a BENEFIT do (R8). Without it the
    # recommender declines and asks, which is the right answer to a comparison
    # nothing separates - so a fixture that wants advice has to hold the
    # evidence that licenses it, exactly as an engagement would.
    add(reg, T.Kind.BENEFIT,
        T.BenefitPayload(text="the supplier carries the peak weeks", basis="client_fact",
                         for_ids=(option.id,)),
        derived_from=(option.id, fact.id), decision_id=decision.id)
    add(reg, T.Kind.COST,
        T.CostPayload(text="a second scheduling team would have to be hired", basis="client_fact",
                      for_ids=(rival.id,)),
        derived_from=(rival.id, fact.id), decision_id=decision.id)
    add(reg, T.Kind.TRADE_OFF,
        T.TradeOffPayload(decision_id=decision.id, option_ids=(option.id, rival.id),
                          gives_up="these routes are alternatives"),
        derived_from=(capability.id, option.id, rival.id), decision_id=decision.id)
    add(reg, T.Kind.ACTION,
        T.ActionPayload(text="stand up scheduling", capability_class=T.CapabilityClass.PROCESS),
        derived_from=(option.id,), decision_id=decision.id)
    node = issue(reg, decision_id=decision.id)
    return reg, decision, option, fact, capability, node


def test_recommendation_is_registered_and_runs_free(registry):
    spec = METHODS.get("recommendation").spec
    assert spec.execution in T.FREE_EXECUTION and spec.max_model_calls == 0
    assert T.Kind.RECOMMENDATION in spec.output_kinds and spec.validators
    assert any(i.kind is T.Kind.FACT and i.min_status is T.Status.CONFIRMED
               for i in spec.required_inputs), "L2 must be a selection precondition, not a gate surprise"


def test_no_recommendation_without_admitted_support(registry):
    """R1. `_is_support` admits a CONFIRMED FACT or an APPROVED ASSUMPTION and
    nothing else, so advice whose lineage reaches neither is not written - it
    is asked about. Writing it anyway would manufacture the L2 finding the
    gate exists to catch. Mutation: drop the `if not supports` guard."""
    reg, _dec, option, _fact, _cap, node = advised_registry(registry, supported=False)
    result = run_method(reg, "recommendation", node.id)
    assert written(result, T.Kind.RECOMMENDATION) == []
    assert result.questions and option.id in result.questions[0].text

    reg2, _d2, _a2, fact2, _c2, node2 = advised_registry(registry, supported=True)
    result2 = run_method(reg2, "recommendation", node2.id)
    rows = written(result2, T.Kind.RECOMMENDATION)
    assert rows and rows[0].payload.supports == (fact2.id,)
    assert set(rows[0].payload.supports) <= set(rows[0].provenance.derived_from)
    assert validate("recommendation", reg2, result2) == []
    # And the registry agrees: nothing is listed as unsupported.
    reg2.apply_all(list(result2.deltas))
    assert REC.support_findings(reg2) == []


def test_the_recommendation_validator_catches_a_doctored_support(registry):
    """The negative control on R1: a recommendation whose support is a merely
    PROPOSED fact is a finding, so the law can fail."""
    reg, _dec, _action, fact, _cap, node = advised_registry(registry, supported=True)
    result = run_method(reg, "recommendation", node.id)
    row = written(result, T.Kind.RECOMMENDATION)[0]
    unconfirmed = add(reg, T.Kind.FACT,
                      T.FactPayload(statement="an unconfirmed reading", basis=T.FactBasis.INFERRED),
                      derived_from=(fact.id,))
    doctored = replace(result, deltas=(T.Add(replace(
        row, payload=replace(row.payload, supports=(unconfirmed.id,)),
        provenance=replace(row.provenance,
                           derived_from=row.provenance.derived_from + (unconfirmed.id,)))),))
    laws = {f.law for f in validate("recommendation", reg, doctored)}
    assert "M.recommendation.unsupported" in laws


def test_a_recommendation_is_born_proposed(registry):
    """R2. The consultant proposes; only the DECISION_OWNER or the CLIENT
    approves (APPROVAL_OWNER, I1). Mutation: write it CONFIRMED."""
    reg, _dec, _action, _fact, _cap, node = advised_registry(registry)
    result = run_method(reg, "recommendation", node.id)
    rows = written(result, T.Kind.RECOMMENDATION)
    assert rows and all(r.status is T.Status.PROPOSED for r in rows)

    doctored = replace(result, deltas=(T.Add(replace(rows[0], status=T.Status.APPROVED)),))
    laws = {f.law for f in validate("recommendation", reg, doctored)}
    assert "M.recommendation.self_approved" in laws


def test_option_id_is_named_only_when_the_lineage_singles_one_out(registry):
    """R3. Advice selects a route and says which: every recommendation written
    names the OPTION it advises, so nothing is published with the choice left
    blank. And where a lineage is asked which route it reaches, choosing
    between the client's routes IS the decision and it is the decision
    owner's: None for zero routes and None for two, because nothing here
    breaks a tie. Mutation: return `found[0]` whenever found."""
    reg, decision, option, _fact, capability, node = advised_registry(registry)
    result = run_method(reg, "recommendation", node.id)
    rows = written(result, T.Kind.RECOMMENDATION)
    assert rows and rows[0].payload.option_id == option.id
    assert validate("recommendation", reg, result) == []

    one = add(reg, T.Kind.OPTION,
              T.OptionPayload(text="buy it", decision_id=decision.id, evidence=(capability.id,)),
              derived_from=(capability.id,), decision_id=decision.id)
    action2 = add(reg, T.Kind.ACTION,
                  T.ActionPayload(text="take the route", capability_class=T.CapabilityClass.PROCESS),
                  derived_from=(one.id,), decision_id=decision.id)
    closure = RM.lineage_closure(reg, (action2.id,))
    assert RM.single_option(reg, closure, decision.id) == one.id

    two = add(reg, T.Kind.OPTION,
              T.OptionPayload(text="build it", decision_id=decision.id, evidence=(capability.id,)),
              derived_from=(capability.id,), decision_id=decision.id)
    action3 = add(reg, T.Kind.ACTION,
                  T.ActionPayload(text="take a route", capability_class=T.CapabilityClass.PROCESS),
                  derived_from=(one.id, two.id), decision_id=decision.id)
    assert RM.single_option(reg, RM.lineage_closure(reg, (action3.id,)), decision.id) is None


def test_a_route_is_not_advised_twice(registry):
    """R4. A brief cannot list the same advice twice because analysis ran
    twice. Mutation: drop `already_recommended`."""
    reg, _dec, _action, _fact, _cap, node = advised_registry(registry)
    first = run_method(reg, "recommendation", node.id)
    reg.apply_all(list(first.deltas))
    again = run_method(reg, "recommendation", node.id)
    assert written(again, T.Kind.RECOMMENDATION) == []


def test_the_engine_has_a_producer_for_every_kind_a_product_reads():
    """The census that used to have two holes in it. RECOMMENDATION and
    EVALUATION_CRITERION were read by the registry, the gates, synthesis and
    the products, and constructed by nothing at all."""
    for kind in (T.Kind.RECOMMENDATION, T.Kind.EVALUATION_CRITERION, T.Kind.OPTION):
        assert METHODS.producers_of(kind), f"{kind.value} has no producer in the library"


# ===========================================================================
# 8. The client settles their own words
# ===========================================================================

def test_the_client_confirms_what_the_playback_showed(registry):
    """MF2.1, the document-less path to a supported recommendation. Every turn
    plays the client back their own statements; nothing let them settle one, so
    a client-stated FACT could never leave PROPOSED and `_is_support` admitted
    nothing. Mutation: delete `charter.confirm_understanding`."""
    reg, _dec, _obj, fact, _src = engagement(registry)
    assert fact.status is T.Status.PROPOSED
    shown = {i.entity_id for i in CH.understanding(reg)}
    assert fact.id in shown

    outcome = CH.confirm_understanding(reg, [fact.id], turn_number=1)
    assert outcome.confirmed == (fact.id,) and outcome.refused == ()
    assert reg.get(fact.id).status is T.Status.CONFIRMED


def test_a_row_the_client_was_not_shown_is_refused(registry):
    """The law the mutation "confirm promotes anything" breaks: an act on the
    playback reaches exactly what the playback showed."""
    reg, decision, _obj, _fact, _src = engagement(registry)
    hidden = add(reg, T.Kind.HYPOTHESIS,
                 T.HypothesisPayload(text="a consultant judgement", issue_id="ISS-1"),
                 derived_from=(decision.id,))
    assert hidden.id not in {i.entity_id for i in CH.understanding(reg)}
    outcome = CH.confirm_understanding(reg, [hidden.id], turn_number=1)
    assert outcome.confirmed == () and outcome.refused
    assert reg.get(hidden.id).status is T.Status.PROPOSED


# ===========================================================================
# 9. Licensed advice stops being advice
# ===========================================================================

def test_licensed_advice_is_withdrawn_and_put_to_an_adviser(registry):
    """L4's own fix, made an act. A recommendation carrying
    `licensed_interpretation` that is still LIVE means the engine is still
    giving advice a licensed professional must give. Mutation: delete
    `withdraw_licensed_advice`."""
    from app.engine.gates import laws as laws_mod

    reg, decision, _obj, fact, _src = engagement(registry)
    confirm(reg, fact)
    rec = add(reg, T.Kind.RECOMMENDATION,
              T.RecommendationPayload(statement="restructure the contracts", decision_id=decision.id,
                                      supports=(fact.id,), licensed_interpretation=True),
              derived_from=(fact.id, decision.id), actor=T.Actor.SYSTEM, decision_id=decision.id,
              relation=T.RelationToCentralDecision.RESOLVES)
    matter = add(reg, T.Kind.REGULATED_MATTER,
                 T.RegulatedMatterPayload(text="restructure the contracts",
                                          domain=T.RegulatedDomain.LEGAL_CONTRACT,
                                          adviser_class="qualified lawyer", why_regulated="w",
                                          touches=(rec.id,), withheld_interpretation="x"),
                 derived_from=(rec.id,), actor=T.Actor.SYSTEM, decision_id=decision.id)
    reg.apply(T.SetStatus(matter.id, T.Status.ROUTED,
                          T.Provenance(actor=T.Actor.SYSTEM, actor_ref="regulated_screen")))
    assert [f.law for f in laws_mod.run_laws(reg, ()) if f.law.startswith("L4")], \
        "L4 does not report a live licensed recommendation; this check would be vacuous"

    asked = REC.withdraw_licensed_advice(reg)
    assert len(asked) == 1 and asked[0].kind is T.Kind.DECISION_REQUIRED
    assert asked[0].payload.from_authority is T.Authority.QUALIFIED_PROFESSIONAL
    assert matter.id in asked[0].payload.options
    assert reg.get(rec.id).status is T.Status.WITHDRAWN
    assert [f.law for f in laws_mod.run_laws(reg, ()) if f.law.startswith("L4")] == []


def test_the_bundle_synthesis_withdraws_licensed_advice(registry):
    """The wiring, not only the function. No fake case produces a
    recommendation the regulated screen flags - measured: zero across the
    fifteen runs - so a `run_case` that stopped withdrawing licensed advice
    would pass every benchmark assertion there is. The synthesis pass is a
    named step so a probe registry that DOES hold one can be put through the
    same order of operations a bundle runs.

    Mutation: delete the `withdraw_licensed_advice` line from
    `harness.synthesise`.
    """
    from app.engine.benchmark.harness import synthesise

    reg, decision, _obj, fact, _src = engagement(registry)
    confirm(reg, fact)
    rec = add(reg, T.Kind.RECOMMENDATION,
              T.RecommendationPayload(statement="restructure the contracts", decision_id=decision.id,
                                      supports=(fact.id,), licensed_interpretation=True),
              derived_from=(fact.id, decision.id), actor=T.Actor.SYSTEM, decision_id=decision.id,
              relation=T.RelationToCentralDecision.RESOLVES)
    add(reg, T.Kind.REGULATED_MATTER,
        T.RegulatedMatterPayload(text="restructure the contracts",
                                 domain=T.RegulatedDomain.LEGAL_CONTRACT,
                                 adviser_class="qualified lawyer", why_regulated="w",
                                 touches=(rec.id,), withheld_interpretation="x"),
        derived_from=(rec.id,), actor=T.Actor.SYSTEM, decision_id=decision.id)

    synthesise(reg, None)

    assert reg.get(rec.id).status is T.Status.WITHDRAWN, (
        "the synthesis a bundle runs left licensed advice standing")
    asked = [d for d in reg.live(T.Kind.DECISION_REQUIRED)
             if d.payload.from_authority is T.Authority.QUALIFIED_PROFESSIONAL]
    assert len(asked) == 1 and rec.id in asked[0].provenance.derived_from


def test_advice_with_no_matter_behind_the_flag_is_left_for_the_gate(registry):
    """Absent evidence is not evidence: a flag with no matter naming it says
    nothing about which licence is needed, so nothing is put to anybody and L4
    still reports it."""
    reg, decision, _obj, fact, _src = engagement(registry)
    confirm(reg, fact)
    rec = add(reg, T.Kind.RECOMMENDATION,
              T.RecommendationPayload(statement="advice", decision_id=decision.id,
                                      supports=(fact.id,), licensed_interpretation=True),
              derived_from=(fact.id, decision.id), actor=T.Actor.SYSTEM, decision_id=decision.id,
              relation=T.RelationToCentralDecision.RESOLVES)
    assert REC.withdraw_licensed_advice(reg) == []
    assert reg.get(rec.id).status is T.Status.PROPOSED


# ===========================================================================
# 10. The fake answers what the prompt actually asked for
# ===========================================================================

def _generic_prompt(method_id: str, instructions: str, rows) -> str:
    spec = METHODS.get(method_id).spec
    return render(
        "method_generic.j2", method_id=method_id, method_purpose="probe",
        issue={"id": "ISS-1", "text": "what is missing", "interrogative": "what",
               "target_kind": "capability"},
        inputs=[{"id": i, "kind": k, "text": t, "quantity": None} for i, k, t in rows],
        assumption_grants=[],
        output_kinds=[k for k in spec.output_kinds if k is not T.Kind.QUESTION],
        instructions=instructions)


def _answer(prompt: str):
    call = ModelCall(purpose="method_probe", messages=({"role": "user", "content": prompt},),
                     engagement_id="E-1")
    return json.loads(O.structural_oracle(call))


def test_the_oracle_fills_the_fields_the_instructions_name():
    """The fixture, not the engine, was what zeroed CAPABILITY: every output
    carried `fields: {}`, and a payload builder that refuses an unstated enum
    (GapState has no unknown member) therefore refused all of them. The rule
    reads the closed vocabularies the template itself rendered from the enums.
    Mutation: return `{}` from `_field_rules`."""
    prompt = _generic_prompt("capability_gap", CG._INSTRUCTIONS,
                             [("OBJ-1", "objective", "cut the queue"),
                              ("FCT-1", "fact", "the line ran 40 hours")])
    answer = _answer(prompt)
    assert answer["outputs"], "the oracle proposed nothing at all"
    for output in answer["outputs"]:
        assert CG.gap_of(output["fields"].get("gap")) is not None
        assert CG.capability_class_of(output["fields"].get("capability_class")) is not None


def test_the_filled_fields_reach_the_payload_builder(registry, fake_provider):
    """End to end on one method: the same answer, run through capability_gap,
    is admitted rather than dropped for a vocabulary it never stated."""
    reg, decision, objective, fact, _src = engagement(registry)
    node = issue(reg, interrogative=T.Interrogative.WHAT, target=T.Kind.CAPABILITY,
                 comparative=False, decision_id=decision.id)
    result = run_method(reg, "capability_gap", node.id,
                        provider=fake_provider(oracle=O.structural_oracle))
    rows = written(result, T.Kind.CAPABILITY)
    assert rows, [f.issue for f in result.findings]
    assert all(isinstance(r.payload.gap, T.GapState) for r in rows)


def test_the_oracle_proposes_the_capability_classes_it_was_shown():
    """`operating_model`, `org_design` and `systems_data_map` declare shapes
    qualified by a CapabilityClass; while the oracle dropped every such shape
    and wrote `capability_class: None` on every node, those methods matched no
    node the benchmark could ever produce. Mutation: put the skip back."""
    catalogue = O._shapes_by_interrogative()
    classed = [s for shapes in catalogue.values() for s in shapes if s.capability_class is not None]
    assert classed, "the oracle can propose no capability-classed node at all"
    node = O._node(classed[0], text="t", parent_id=None, temp_id="n0", derived_from=["DEC-1"],
                   decisive_for=["DEC-1"], weight=1.0)
    assert node["capability_class"] == classed[0].capability_class.value


def test_a_bounded_decomposition_moves_across_the_window():
    """The fanout the prompt states is smaller than a mature window; always
    taking the first `limit` rows decomposes the same handful forever, so the
    tree deepens and never widens. Mutation: `return list(rows)`."""
    rows = [("A", "a"), ("B", "b"), ("C", "c"), ("D", "d")]
    assert O._rotated(rows, 0) == rows
    assert O._rotated(rows, 1)[0] == ("B", "b")
    assert sorted(O._rotated(rows, 7)) == sorted(rows), "rotation must lose nothing"
    assert O._rotated([], 3) == []
    starts = {tuple(O._rotated(rows, n)[:2]) for n in range(4)}
    assert len(starts) == 4, "the offset does not move the window"


def test_the_oracle_still_reads_nothing_but_the_call():
    """The property the whole benchmark rests on: the new rules take their
    values from the prompt's own rendered text. An instruction block that
    names no field leaves the fields empty rather than inventing one."""
    prompt = _generic_prompt("capability_gap", "Say something useful.",
                             [("FCT-1", "fact", "the line ran 40 hours")])
    answer = _answer(prompt)
    assert answer["outputs"] and all(o["fields"] == {} for o in answer["outputs"])


# ===========================================================================
# 12. Production is bounded: an engagement holds only so many conclusions
# ===========================================================================

def test_an_engagement_holds_only_so_many_rows_of_one_conclusion(registry, monkeypatch):
    """I9. Every other bound caps how much WORK may run and none of them
    capped what the work leaves behind, so an engagement could hold six
    hundred routes to one decision and satisfy every published bound - and
    every distinctness count over those rows was cheap, because divergence is
    easy when production is unbounded.

    Refused at the registry door rather than dropped, so `apply_all` rolls the
    batch back whole and no conclusion is left citing a row that never landed.

    Mutation: drop the `_check_capacity` call from `_add`.
    """
    from app.config import settings
    from app.engine.types import ANALYSIS_KINDS, RegistryError

    monkeypatch.setattr(settings, "ENGINE_MAX_ENTITIES_PER_ANALYSIS_KIND", 2)
    reg, decision, _obj, _fact, _src = engagement(registry)
    assert T.Kind.CAPABILITY in ANALYSIS_KINDS and T.Kind.QUESTION not in ANALYSIS_KINDS

    def capability(text):
        return T.CapabilityPayload(text=text, capability_class=T.CapabilityClass.PROCESS,
                                   gap=T.GapState.MISSING)

    for n in range(2):
        add(reg, T.Kind.CAPABILITY, capability(f"cap {n}"), decision_id=decision.id)
    with pytest.raises(RegistryError) as caught:
        add(reg, T.Kind.CAPABILITY, capability("one too many"), decision_id=decision.id)
    assert caught.value.invariant == "I9"
    assert len(reg.live(T.Kind.CAPABILITY)) == 2

    # A batch that would cross the ceiling lands not at all, so nothing in it
    # is left half-written.
    before = len(reg.rows())
    batch = [T.Add(T.make_entity(
        kind=T.Kind.CAPABILITY, engagement_id=reg.engagement_id, payload=capability(f"batch {n}"),
        provenance=T.Provenance(actor=T.Actor.METHOD, actor_ref="method:probe@1"),
        confidence=T.Confidence(None), relevance=T.Relevance(decision.id, 0.5),
        relation=T.RelationToCentralDecision.INFORMS, status=T.Status.PROPOSED)) for n in range(2)]
    with pytest.raises(RegistryError):
        reg.apply_all(batch)
    assert len(reg.rows()) == before

    # Evidence and the records the engagement is audited by are not rationed.
    for n in range(4):
        add(reg, T.Kind.QUESTION, T.QuestionPayload(text=f"q{n}?", asks_for=(T.AsksFor(T.Kind.FACT),)),
            status=T.Status.OPEN)
    assert len(reg.live(T.Kind.QUESTION)) == 4


def test_a_method_whose_conclusions_are_all_full_stops_being_offered(registry, monkeypatch):
    """The selection half of the same law: once every conclusion a method
    writes is at its ceiling the method has nothing left to add, so the round
    is not spent starting work the registry door would only refuse. A method
    that also writes a QUESTION is NOT exempted by it - a kind that is never
    rationed would make the test true of nothing.

    Mutation: return an empty frozenset from `saturated_kinds`.
    """
    from app.config import settings

    reg, decision, _obj, _fact, _src = engagement(registry)
    node = issue(reg, decision_id=decision.id)
    offered = {s.method_id for s in ST.open_selections(reg)}
    assert offered, "nothing is offered; the check would be vacuous"

    monkeypatch.setattr(settings, "ENGINE_MAX_ENTITIES_PER_ANALYSIS_KIND", 0)
    assert ST.saturated_kinds(reg) >= {T.Kind.EVALUATION_CRITERION, T.Kind.RECOMMENDATION}
    still = {s.method_id for s in ST.open_selections(reg)}
    for method_id in offered:
        concludes = [k for k in METHODS.get(method_id).spec.output_kinds if k in T.ANALYSIS_KINDS]
        if concludes:
            assert method_id not in still, f"{method_id} is still offered with every conclusion full"


def _fake_option(reg, decision_id, n):
    return T.Add(T.make_entity(
        kind=T.Kind.OPTION, engagement_id=reg.engagement_id,
        payload=T.OptionPayload(text=f"route {n}", decision_id=decision_id, mechanism="make"),
        provenance=T.Provenance(actor=T.Actor.METHOD, actor_ref="method:probe@1",
                                derived_from=(decision_id,)),
        confidence=T.Confidence(None), relevance=T.Relevance(decision_id, 0.5),
        relation=T.RelationToCentralDecision.RESOLVES, status=T.Status.PROPOSED))


def test_a_free_run_larger_than_its_budget_is_blocked_whole(registry, monkeypatch):
    """The free path is metered exactly like an assignment.

    `runner.run` has always refused a result larger than the assignment funded,
    "blocked whole, never trimmed to fit: a truncated analysis reads as a
    complete one". `run_free` is where every DETERMINISTIC and CALCULATION
    method runs - most of the library's writers - and nothing counted what they
    wrote. So a method whose output grew with the size of the REGISTER rather
    than with the question it was asked could offer hundreds of rows in one
    batch and be stopped only by the ceiling at the registry door, which rolls
    the batch back and leaves the live count BELOW the ceiling that refused it:
    the overproduction is then invisible to every query anyone can run.

    Mutation: drop the `max_deltas` check from `run_free`.
    """
    from app.engine.methods.contract import MethodResult, input_state
    from app.engine.specialists.assignment import default_budget
    from app.engine.specialists.runner import BudgetExceeded

    reg, decision, _obj, _fact, _src = engagement(registry)
    node = issue(reg, interrogative=T.Interrogative.WHICH, target=T.Kind.CAPABILITY,
                 comparative=True, decision_id=decision.id)
    add(reg, T.Kind.CAPABILITY, T.CapabilityPayload(
        text="scheduling", capability_class=T.CapabilityClass.PROCESS, gap=T.GapState.MISSING),
        derived_from=(decision.id,), decision_id=decision.id)
    spec = METHODS.get("make_buy_partner").spec
    funded = default_budget(spec).max_deltas
    assert funded > 0, "the budget has to fund something or the test proves nothing"

    selection = Selection(node.id, "make_buy_partner", input_state(spec, reg),
                          (0.0, spec.cost_class, spec.max_model_calls, spec.id))
    context = ctx(reg, node.id, method_id="make_buy_partner")
    over = MethodResult(deltas=tuple(_fake_option(reg, decision.id, n) for n in range(funded + 1)))
    monkeypatch.setattr(type(METHODS.get("make_buy_partner")), "run", lambda self, c: over)
    with pytest.raises(BudgetExceeded) as caught:
        run_free(selection, context)
    assert str(funded) in str(caught.value)
    assert len(reg.live(T.Kind.OPTION)) == 0, "blocked whole: nothing of it was written"

    # NEGATIVE CONTROL: a result the run IS funded for passes through untouched.
    within = MethodResult(deltas=over.deltas[:funded])
    monkeypatch.setattr(type(METHODS.get("make_buy_partner")), "run", lambda self, c: within)
    assert run_free(selection, context) is within


def test_a_method_is_not_offered_while_any_conclusion_it_writes_is_full(registry, monkeypatch):
    """The other half of I9's selection guard, and the one the cap defeated.

    A method writes its kinds TOGETHER, in one batch the registry admits or
    rolls back whole. So a method that would write one row of a saturated kind
    alongside twenty of an unsaturated one cannot write the twenty either: I9
    refuses the one and the batch goes back. Requiring EVERY declared kind to
    be full therefore kept offering a method that could no longer land
    anything, round after round - and each refusal rolled the live count back
    BELOW the ceiling that caused it, so the guard looked again and saw room.
    The cap and the guard defeated each other, and only a count taken on the
    write path could see it.

    Mutation: `any` -> `all` in `open_selections`' exclude predicate.
    """
    from app.config import settings

    spec = METHODS.get("make_buy_partner").spec
    rationed = [k for k in spec.output_kinds if k in T.ANALYSIS_KINDS]
    assert len(rationed) > 1, "the law is about a method with more than one rationed conclusion"

    reg, decision, _obj, _fact, _src = engagement(registry)
    node = issue(reg, interrogative=T.Interrogative.WHICH, target=T.Kind.CAPABILITY,
                 comparative=True, decision_id=decision.id)
    add(reg, T.Kind.CAPABILITY, T.CapabilityPayload(
        text="scheduling", capability_class=T.CapabilityClass.PROCESS, gap=T.GapState.MISSING),
        derived_from=(decision.id,), decision_id=decision.id)
    assert "make_buy_partner" in {s.method_id for s in ST.open_selections(reg)}

    monkeypatch.setattr(settings, "ENGINE_MAX_ENTITIES_PER_ANALYSIS_KIND", 1)
    add(reg, T.Kind.OPTION, T.OptionPayload(text="a route already on the table",
                                            decision_id=decision.id, mechanism="make"),
        derived_from=(decision.id,), decision_id=decision.id)
    full = ST.saturated_kinds(reg)
    assert T.Kind.OPTION in full and T.Kind.TRADE_OFF not in full, (
        "exactly one of the method's conclusions is full, which is what this law is about")
    assert "make_buy_partner" not in {s.method_id for s in ST.open_selections(reg)}, (
        "a method one of whose conclusions is full is still being offered")

    # NEGATIVE CONTROL: with nothing full it is offered again, so the exclusion
    # is about saturation and not about the method.
    monkeypatch.setattr(settings, "ENGINE_MAX_ENTITIES_PER_ANALYSIS_KIND",
                        int(T.BOUNDS["MAX_ENTITIES_PER_ANALYSIS_KIND"]))
    assert ST.saturated_kinds(reg) == frozenset()
    assert "make_buy_partner" in {s.method_id for s in ST.open_selections(reg)}


def test_a_scarce_round_spends_its_budget_on_work_not_yet_done(registry):
    """MAX_SPECIALISTS_PER_ROUND is a real budget, so some ready work does not
    run this round. WHICH work was decided by nothing: the loop took selections
    in issue order and stopped counting, so the budget went to whichever nodes
    the tree listed first and a method that only matched later nodes was
    crowded out of every round of the engagement.

    Breadth before depth: a budget is a reason to do a different thing next,
    not the same thing again. Mutation: drop `s.method_id in already` from the
    sort key in `granted_slots`.
    """
    reg, decision, _obj, _fact, _src = engagement(registry)
    node = issue(reg, decision_id=decision.id)
    pending = [s for s in ST.open_selections(reg) if not s.inputs.missing]
    assert len(pending) >= 2, "two ready selections are needed for a budget to choose between"

    first, second = pending[0], pending[1]
    assert ST.granted_slots(reg, [first, second], ceiling=1) == frozenset({(first.issue_id, first.method_id)})

    # Once the better-ranked method has run somewhere, the slot goes to the
    # one the engagement has not done yet.
    add(reg, T.Kind.ANALYSIS, T.AnalysisPayload(method_id=first.method_id, method_version=1,
                                                issue_ids=("ISS-999",), state=T.AnalysisState.DONE),
        derived_from=(node.id,))
    assert ST.granted_slots(reg, [first, second], ceiling=1) == frozenset({(second.issue_id, second.method_id)})


# ===========================================================================
# 13. Advice says what chose it, and the fake can reach the whole library
# ===========================================================================

def advised_with_criteria(registry):
    reg, decision, option, fact, capability, node = advised_registry(registry)
    criterion = add(reg, T.Kind.EVALUATION_CRITERION,
                    T.EvaluationCriterionPayload(text="cut the queue", decision_id=decision.id),
                    derived_from=(decision.id,), decision_id=decision.id)
    return reg, decision, option, criterion, node


def test_advice_names_the_criteria_it_was_judged_against(registry):
    """R5. Nothing else on the row says WHY this route beat the others: with no
    criterion in its lineage a recommendation has been emitted rather than
    chosen. The criteria are the client's own declarations restated by
    `decision_criteria`, so citing them is the advice pointing at the standard
    it was held to, not the consultant importing a priority of his own.

    Mutation: drop `criteria` from the recommendation's `derived_from`.
    """
    reg, _dec, _option, criterion, node = advised_with_criteria(registry)
    result = run_method(reg, "recommendation", node.id)
    rows = written(result, T.Kind.RECOMMENDATION)
    assert rows and criterion.id in rows[0].provenance.derived_from
    assert validate("recommendation", reg, result) == []

    stripped = replace(result, deltas=(T.Add(replace(
        rows[0], provenance=replace(rows[0].provenance, derived_from=tuple(
            i for i in rows[0].provenance.derived_from if i != criterion.id)))),))
    assert "M.recommendation.uncited_criteria" in {f.law for f in validate("recommendation", reg, stripped)}


def test_advice_that_selects_no_route_is_a_finding(registry):
    """R3's negative control. A recommendation with no option_id cites the
    evidence it was built from, so every support law is satisfied by a row that
    settles no choice - the citation is real and the advice has still chosen
    nothing. Mutation: return `[]` from `_v_advice_selects_a_route`."""
    reg, _dec, _option, _criterion, node = advised_with_criteria(registry)
    rows = written(run_method(reg, "recommendation", node.id), T.Kind.RECOMMENDATION)
    blank = replace(run_method(reg, "recommendation", node.id), deltas=(T.Add(replace(
        rows[0], payload=replace(rows[0].payload, option_id=None))),))
    assert "M.recommendation.selects_nothing" in {f.law for f in validate("recommendation", reg, blank)}


def test_advice_does_not_repeat_the_evidence_it_rests_on(registry):
    """A recommendation whose statement IS its support's statement satisfies
    I3, L2 and `unsupported_recommendations()` completely and has still traced
    to nothing: the evidence and the claim are one row apart and identical.
    The statement names the route as a course of action instead, so the claim
    and the evidence can never be the same characters.

    Mutation: `return wording(option)` from `advice_statement`.
    """
    reg, _dec, option, _criterion, node = advised_with_criteria(registry)
    rows = written(run_method(reg, "recommendation", node.id), T.Kind.RECOMMENDATION)
    claim = rows[0].payload.statement
    assert claim != option.payload.text
    for support_id in rows[0].payload.supports:
        assert claim != reg.get(support_id).payload.statement
    assert option.payload.text in claim, "the advice must still name the route in the registry's words"


def test_the_same_causal_claim_is_one_hypothesis(registry):
    """A hypothesis is a claim that one thing causes another, so the SAME claim
    arriving on a later turn is the same hypothesis. The model is shown the
    whole live registry every pass and re-proposes what it proposed before, so
    without this the row count grows with the number of TURNS rather than with
    what was found - measured: hundreds of copies of a handful of claims, which
    makes every count over hypotheses meaningless.

    Mutation: drop the `registered` guard in `revise_hypothesis`.
    """
    from app.engine.partner import hypothesis as HY

    reg, decision, _obj, fact, _src = engagement(registry)
    node = issue(reg, decision_id=decision.id)
    payload = T.HypothesisPayload(text="the queue causes the delay", issue_id=node.id,
                                  causes=(fact.id,))
    add(reg, T.Kind.HYPOTHESIS, payload, derived_from=(node.id, fact.id), decision_id=decision.id)

    class _Provider:
        def complete(self, call):
            from app.engine.llm import ModelResponse
            body = json.dumps({"new_candidates": [], "causal_links": [
                {"issue_id": node.id, "cause_id": fact.id, "text": "the queue causes the delay",
                 "support_ids": [fact.id]}]})
            return ModelResponse(text=body, finish_reason="stop", usage={}, call_id="probe")

    before = len(reg.live(T.Kind.HYPOTHESIS))
    HY.revise_hypothesis(reg, _Provider())
    assert len(reg.live(T.Kind.HYPOTHESIS)) == before, "the same causal claim was registered twice"


def test_the_shapes_a_decomposition_reaches_move_as_the_tree_grows(registry):
    """`_rotated` moved which ROWS a bounded decomposition reaches; nothing
    moved which SHAPES it could carry, so a row's wording pinned that row to
    one run of consecutive shapes for the life of the engagement. An engagement
    holding few distinct wordings could then only ever reach a handful of the
    catalogue however long its tree grew - measured: ninety third-level nodes
    covering sixteen adjacent shapes out of forty, and never one of the
    nineteen the capability producers answer.

    Mutation: drop `start` from the shape index in `_issue_tree`.
    """
    def decomposition(placed):
        """One issue-tree answer over the SAME rows, differing only in how much
        of the tree is already on the page."""
        prompt = render(
            "issue_tree.j2",
            decisions=[{"id": "DEC-1", "role": "central", "text": "which way"}],
            objectives=[{"id": "OBJ-1", "text": "cut the queue"}],
            entities=[{"id": "FCT-1", "kind": "fact", "text": "the line ran 40 hours"},
                      {"id": "MEA-1", "kind": "measure", "text": "hours run"}],
            existing_nodes=[{"id": i, "parent_id": None, "text": "already placed"} for i in placed],
            max_fanout=int(T.BOUNDS["MAX_FANOUT"]))
        call = ModelCall(purpose="method_issue_tree",
                         messages=({"role": "user", "content": prompt},), engagement_id="E-1")
        nodes = json.loads(O._issue_tree(call))["nodes"]
        return frozenset((n["interrogative"], n["target_kind"], n["capability_class"]) for n in nodes)

    grown = [decomposition(placed) for placed in
             ([], ["ISS-1"], ["ISS-1", "ISS-2"], ["ISS-1", "ISS-2", "ISS-3"])]
    assert all(grown), "the oracle proposed no nodes at all; the check would be vacuous"
    assert len(set(grown)) > 1, (
        "the shapes a decomposition reaches never move as the tree grows: the same wording is "
        "pinned to one run of the catalogue for the life of the engagement")
    assert decomposition(["ISS-1"]) == grown[1], "the same tree must decompose the same way twice"


# ===========================================================================
# 14. The brief states the limits, and a restatement is not a finding
# ===========================================================================

def test_the_brief_states_what_the_answer_must_live_within(registry):
    """No work product read a CONSTRAINT at all. The limits a client states -
    what may not be spent, what may not be broken - are the first thing that
    makes a recommendation wrong, and the mandatory brief that carries the
    recommendation was not carrying them.

    The section is planned only where the engagement holds one, so a brief on
    an engagement that declared no limits does not carry an empty heading
    standing in for limits that were never stated (MF1.1).

    Mutation: delete the `constraints` section from `executive_decision_brief`.
    """
    from app.engine.work_products.decl import WORK_PRODUCTS, plan_sections

    brief = WORK_PRODUCTS.get("executive_decision_brief")
    section = [s for s in brief.sections if T.Kind.CONSTRAINT in {q.kind for q in s.query}]
    assert section, "the mandatory brief reads no CONSTRAINT"
    assert not section[0].required, "a limit nobody stated must not become an empty heading"

    reg, decision, _obj, _fact, _src = engagement(registry)
    assert section[0].id not in plan_sections(brief, reg)

    add(reg, T.Kind.CONSTRAINT, T.ConstraintPayload(text="no redundancies before April"),
        derived_from=(decision.id,), actor=T.Actor.CLIENT, decision_id=decision.id)
    assert section[0].id in plan_sections(brief, reg)


def test_a_conclusion_the_engagement_already_holds_is_not_registered_again(registry):
    """A method that runs on twenty issue nodes proposes the same capability
    from twenty angles. Registering each one makes the row count a measure of
    how many NODES ran rather than of what the analysis found - measured:
    thirty-five distinct capabilities inside a hundred and forty rows - so the
    counts every plan predicate reads stop meaning anything, and two
    engagements that found different things come out looking alike because
    both simply filled up. Restating is not finding.

    Mutation: drop the `held` check from `admitted`.
    """
    reg, decision, _obj, fact, _src = engagement(registry)
    node = issue(reg, interrogative=T.Interrogative.WHAT, target=T.Kind.CAPABILITY,
                 comparative=False, decision_id=decision.id)
    add(reg, T.Kind.CAPABILITY,
        T.CapabilityPayload(text="Scheduling", capability_class=T.CapabilityClass.PROCESS,
                            gap=T.GapState.MISSING, evidence=(fact.id,)),
        derived_from=(fact.id,), decision_id=decision.id)

    class _Sheet:
        outputs = [CG.ProposedOutput(kind="capability", text="  scheduling  ",
                                     fields={"gap": "missing"}, derived_from=[fact.id]),
                   CG.ProposedOutput(kind="capability", text="dispatch",
                                     fields={"gap": "missing"}, derived_from=[fact.id])]
        questions = []

    proposal = CG.Proposal(_Sheet(), None, (fact,), node, None, reg)
    findings = []
    kept = [o.text for _i, o, _k, _d, _q in CG.admitted(METHODS.get("capability_gap").spec,
                                                        proposal, findings)]
    assert kept == ["dispatch"], "a restatement of a live conclusion was admitted"
    assert any(f.law.endswith("restatement") for f in findings), "the drop was not recorded"
