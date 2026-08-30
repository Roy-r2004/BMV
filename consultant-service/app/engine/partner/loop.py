"""app/engine/partner/loop.py - the Engagement Partner: one turn of the
conversation, and one run of the analysis (design 6.2, 6.7).

This module orchestrates and decides nothing. Ingestion, reconciliation,
hypothesis, gaps, the charter, the method library, the specialist runner and
the regulated screen each own their laws; the loop's only job is to run them in
the order the design states and to enforce the four laws that are its own:

  * A paid method never runs before the client's charter. During discovery only
    FREE_EXECUTION (DETERMINISTIC / CALCULATION) methods run, directly, as
    Actor.METHOD (S6). RESEARCH and MODEL_ASSISTED reach outside the registry
    or ask a model to word a conclusion, and both need a frozen scope the
    client has agreed to fund.
  * In analysis, every RESEARCH / MODEL_ASSISTED selection, and every tied
    selection however cheap, runs under an `Assignment` (MF1.2). This is the
    mechanical specialist trigger: no issue node has to be "marked" for
    independent analysis, the execution type and the tie decide. Removing the
    branch is the mutation under which no benchmark case shows an assignment
    at all.
  * A NEW material question opened during analysis pauses it and returns to the
    client (PAUSED_FOR_DISCOVERY). "New" is measured against the questions that
    were already open when the run began, because analysis that stalled on
    every question discovery had left open would never start; the spec's law is
    "continue discovery during analysis if a NEW material gap appears".
  * The live summary is recomputed from registry queries on every read and
    never stored. A cached summary is prose that drifts from the rows, which is
    exactly the class of defect this engine exists to make impossible.

`Partner` holds no engagement state: the state is the `EngagementState` handed
to each call, and the registry inside it. Two engagements can share one Partner
and one provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.engine.calc.arith import DecimalCalculator
from app.engine.llm import ModelProvider, StructuredFailure
from app.engine.methods.contract import METHODS, MethodContext, MethodRegistry, Selection, select_methods
from app.engine.partner import charter as charter_mod
from app.engine.partner.charter import CharterItem, CharterOutcome, CharterProposal
from app.engine.partner.hypothesis import (
    Reframe, charter_ready, hypothesis_weights, maybe_reframe, revise_hypothesis,
)
from app.engine.partner.ingest import IngestOutcome, ingest_document, ingest_turn
from app.engine.partner.questions import ASKABLE_STRATEGIES, ask, open_issues, top_gap_value
from app.engine.partner.state import (
    EngagementState, PhaseError, advance, analysis_blockers, approved_charter, attempted,
    synthesis_blockers,
)
from app.engine.registry import Calculator, EngagementRegistry
from app.engine.specialists.assignment import Assignment
from app.engine.specialists.runner import RunOutcome
from app.engine.specialists.runner import run as run_assignment
from app.engine.specialists.runner import run_free
from app.engine.synthesis.conflicts import detect_conflicts, reevaluate_materiality
from app.engine.synthesis.regulated import screen_candidates
from app.engine.types import (
    FREE_EXECUTION, Actor, Add, AnalysisPayload, AnalysisState, Confidence, Entity, EntityDelta,
    FillStrategy, Finding, Kind, Phase, Provenance, RegistryError, RelationToCentralDecision,
    Relevance, Status, make_entity,
)

__all__ = ["AnalysisRun", "Partner", "PartnerReply", "TurnStep"]


# The steps of one turn, in the order design 6.2 states them. Named so a
# refusal can say which step declined rather than "something went wrong".
class TurnStep:
    INGEST = "ingest"
    RECONCILE = "reconcile"
    FREE_METHODS = "free_methods"
    HYPOTHESIS = "hypothesis"
    CHARTER = "charter"
    REGULATED = "regulated"


@dataclass(frozen=True)
class PartnerReply:
    """What the client is shown after one turn (design 6.2 step 8).

    `registry` is carried, not a rendered summary, because `live_summary` is a
    property: the ids are grouped by query at the moment they are read.
    """
    phase: Phase
    turn_n: int
    registry: EngagementRegistry
    # The EVIDENCE_SOURCE row this turn became. A charter correction has to
    # cite the turn the client made it in (I2 refuses a client fact whose new
    # wording is in no turn the registry holds), so the reply hands it back.
    turn_id: str = ""
    understanding: tuple[CharterItem, ...] = ()
    reframe: Reframe | None = None
    questions: tuple[Entity, ...] = ()
    evidence_requests: tuple[Entity, ...] = ()
    charter: CharterProposal | None = None
    regulated: tuple[Entity, ...] = ()
    ran: tuple[tuple[str, str], ...] = ()
    refusals: tuple[str, ...] = ()

    @property
    def live_summary(self) -> dict:
        """Ids grouped by query, recomputed on every read and never stored
        (design 6.1). Storing the dict here would freeze a picture of the
        engagement that the next row makes false, and nothing would say so."""
        return self.registry.live_summary()


@dataclass(frozen=True)
class AnalysisRun:
    """What one `run_analysis` did. Every field is a list of ids, so the API,
    the integrity record and the tests all read the same account of the run."""
    phase: Phase
    rounds: int = 0
    ran: tuple[tuple[str, str], ...] = ()          # (method_id, issue_id) run directly as METHOD
    assignments: tuple[str, ...] = ()              # SPECIALIST_ASSIGNMENT ids
    conflicts: tuple[str, ...] = ()
    paused_on: tuple[str, ...] = ()                # the new material QUESTIONs that stopped it
    amendment: Entity | None = None                # the CHARTER proposed when the diagnosis moved
    findings: tuple[Finding, ...] = ()
    refusals: tuple[str, ...] = ()


def _material_ask_ids(view) -> set[str]:
    """Open material questions that are the CLIENT's to answer. A specialist
    gap is not a question and never pauses anything (design 6.5)."""
    return {q.id for q in view.open_material_questions()
            if q.payload.strategy in ASKABLE_STRATEGIES}


class Partner:
    """The one agent the client sees (spec section 2)."""

    def __init__(self, provider: ModelProvider, *, calc: Calculator | None = None,
                 methods: MethodRegistry = METHODS, model: str | None = None):
        self._provider = provider
        self._calc = calc
        self._methods = methods
        self._model = model

    def _calculator(self, state: EngagementState) -> Calculator:
        return self._calc if self._calc is not None else DecimalCalculator(state.registry)

    # -----------------------------------------------------------------------
    # 1. One turn
    # -----------------------------------------------------------------------

    def turn(self, state: EngagementState, message: str,
             attachments: Sequence[tuple[str, bytes]] = ()) -> PartnerReply:
        """Design 6.2, step by step. Every step that can decline records why in
        `refusals`; a step that declined never becomes a default."""
        registry = state.registry
        calc = self._calculator(state)
        state.turn_n += 1
        refusals: list[str] = []
        touched: list[Entity] = []

        # The client has spoken, so discovery has begun; a client who answers
        # instead of confirming a standing charter is still in discovery, and
        # the charter is re-proposed below over the evidence that just arrived.
        if state.phase in (Phase.OPENING, Phase.CHARTER_PROPOSED):
            advance(state, Phase.DISCOVERY, methods=self._methods)

        # 1. ingest: the turn, then every attachment
        outcome = ingest_turn(registry, self._provider, message, turn_number=state.turn_n)
        turn_id = outcome.source.id
        touched.extend(self._from_ingest(outcome, refusals))
        for name, data in attachments:
            doc = ingest_document(registry, self._provider, name=name, data=data,
                                  turn_number=state.turn_n)
            touched.extend(self._from_ingest(doc, refusals))

        # 2. reconcile: every pair of live facts on one measure, plus the other
        #    three detection queries. The calculator never sees a pair.
        try:
            detect_conflicts(registry, calc=calc)
        except Exception as exc:                          # pragma: no cover - defensive
            refusals.append(f"{TurnStep.RECONCILE}: {exc}")

        # 3. free methods may run during discovery (S6); paid ones may not
        ran = self._run_free_methods(state, touched, refusals)

        # 4. hypothesis
        try:
            touched.extend(revise_hypothesis(registry, self._provider, model=self._model))
        except StructuredFailure as exc:
            # The step is recorded as blocked rather than defaulted: no
            # candidate is invented because the model did not answer.
            refusals.append(f"{TurnStep.HYPOTHESIS}: {exc}")
        reframe = maybe_reframe(registry, state.bounds)

        # 5. gaps -> questions
        batch = ask(registry, self._provider, turn_number=state.turn_n, bounds=state.bounds,
                    methods=self._methods, model=self._model)
        touched.extend(batch.questions)

        # 6. charter, when the ranking (or the ASK_FLOOR) says it is time
        proposal = self._maybe_propose_charter(state, refusals)

        # 7. regulated screen on what this turn produced, so the client is told
        #    early rather than at synthesis
        matters: tuple[Entity, ...] = ()
        try:
            fresh = list({e.id: e for e in touched if e.id}.values())
            matters = screen_candidates(registry, self._provider, fresh).matters
        except Exception as exc:                          # pragma: no cover - defensive
            refusals.append(f"{TurnStep.REGULATED}: {exc}")

        # 8. the reply
        questions = tuple(batch.questions)
        return PartnerReply(
            phase=state.phase, turn_n=state.turn_n, registry=registry, turn_id=turn_id,
            understanding=charter_mod.understanding(registry), reframe=reframe,
            questions=tuple(q for q in questions if q.payload.strategy != FillStrategy.REQUEST_DOCUMENT),
            evidence_requests=tuple(q for q in questions
                                    if q.payload.strategy == FillStrategy.REQUEST_DOCUMENT),
            charter=proposal, regulated=matters, ran=ran, refusals=tuple(refusals))

    @staticmethod
    def _from_ingest(outcome: IngestOutcome, refusals: list[str]) -> list[Entity]:
        for r in outcome.refused:
            refusals.append(f"{TurnStep.INGEST}: {r}")
        if outcome.failure:
            refusals.append(f"{TurnStep.INGEST}: {outcome.failure}")
        return [outcome.source, *outcome.created, *outcome.questions]

    def _maybe_propose_charter(self, state: EngagementState,
                               refusals: list[str]) -> CharterProposal | None:
        """A charter is proposed from DISCOVERY only. In ANALYSIS an amendment
        is the charter's own path (design 6.7), and a charter already approved
        is not re-proposed behind the client's back."""
        if state.phase != Phase.DISCOVERY:
            return None
        top = top_gap_value(state.registry, bounds=state.bounds, methods=self._methods)
        if not charter_ready(state.registry, state.bounds, top_gap_value=top):
            return None
        proposal = charter_mod.propose(state.registry, turn_number=state.turn_n,
                                       bounds=state.settings_bounds(), methods=self._methods)
        refusals.extend(f"{TurnStep.CHARTER}: {r}" for r in proposal.refusals)
        advance(state, Phase.CHARTER_PROPOSED, methods=self._methods)
        return proposal

    # -----------------------------------------------------------------------
    # 2. The client's answer to the charter
    # -----------------------------------------------------------------------

    def confirm_charter(self, state: EngagementState, charter_id: str, *,
                        verdicts: Mapping[str, str] | None = None,
                        corrections: Mapping[str, Any] | None = None,
                        turn_id: str | None = None) -> CharterOutcome:
        """Apply the client's per-item verdicts and, if the charter was
        approved, move to CHARTER_CONFIRMED. A refused confirmation leaves the
        phase where it was: the mandate is the charter, not the request."""
        result = charter_mod.confirm(state.registry, charter_id, verdicts=verdicts,
                                     corrections=corrections, turn_number=state.turn_n,
                                     turn_id=turn_id)
        if result.approved and state.phase == Phase.CHARTER_PROPOSED:
            advance(state, Phase.CHARTER_CONFIRMED, methods=self._methods)
        return result

    # -----------------------------------------------------------------------
    # 3. Analysis
    # -----------------------------------------------------------------------

    def run_analysis(self, state: EngagementState) -> AnalysisRun:
        """Design 6.7. Bounded rounds; free methods run directly, paid and tied
        selections run as assignments; a new material question pauses; a moved
        diagnosis amends the charter."""
        registry = state.registry
        calc = self._calculator(state)

        # The mandate is checked before the phase moves, so "no approved
        # charter" is the reason the caller hears whatever phase it is in.
        blockers = analysis_blockers(registry)
        if blockers:
            raise PhaseError(state.phase, Phase.ANALYSIS, blockers)
        advance(state, Phase.ANALYSIS, methods=self._methods)

        max_rounds = int(state.bound("MAX_ANALYSIS_ROUNDS"))
        max_specialists = int(state.bound("MAX_SPECIALISTS_PER_ROUND"))
        standing_material = _material_ask_ids(registry)
        ran: list[tuple[str, str]] = []
        assignments: list[str] = []
        conflicts: list[str] = []
        findings: list[Finding] = []
        refusals: list[str] = []
        rounds = 0

        while rounds < max_rounds:
            rounds += 1
            spawned = 0
            worked = False
            for selection in select_methods(open_issues(registry), registry, self._methods):
                if attempted(registry, selection.method_id, selection.issue_id):
                    continue
                spec = self._methods.get(selection.method_id).spec
                if selection.inputs.missing:
                    # The hole is the question pass's business: it is already a
                    # typed Gap with a fill strategy, and a specialist gap
                    # becomes an assignment when its producer is selectable.
                    continue
                if spec.execution in FREE_EXECUTION and not selection.tied:
                    if self._run_free(state, selection, spec, refusals):
                        ran.append((selection.method_id, selection.issue_id))
                        worked = True
                else:
                    if spawned >= max_specialists:
                        continue                          # the round's ceiling, not a refusal
                    outcome = self._assign(state, selection, refusals)
                    if outcome is None:
                        continue
                    assignments.append(outcome.assignment_id)
                    findings.extend(outcome.findings)
                    spawned += 1
                    worked = True

            conflicts.extend(c.id for c in detect_conflicts(registry, calc=calc))
            reevaluate_materiality(registry, calc=calc)

            new_material = _material_ask_ids(registry) - standing_material
            if new_material:
                advance(state, Phase.PAUSED_FOR_DISCOVERY, methods=self._methods)
                return AnalysisRun(phase=state.phase, rounds=rounds, ran=tuple(ran),
                                   assignments=tuple(assignments), conflicts=tuple(conflicts),
                                   paused_on=tuple(sorted(new_material)), findings=tuple(findings),
                                   refusals=tuple(refusals))

            amendment = self._maybe_amend(state)
            if amendment is not None:
                return AnalysisRun(phase=state.phase, rounds=rounds, ran=tuple(ran),
                                   assignments=tuple(assignments), conflicts=tuple(conflicts),
                                   amendment=amendment, findings=tuple(findings),
                                   refusals=tuple(refusals))
            if not worked:
                break

        left = synthesis_blockers(registry, rounds_used=rounds, bounds=state.bounds,
                                  methods=self._methods)
        if left:
            refusals.extend(left)
        else:
            advance(state, Phase.SYNTHESIS, rounds_used=rounds, methods=self._methods)
        return AnalysisRun(phase=state.phase, rounds=rounds, ran=tuple(ran),
                           assignments=tuple(assignments), conflicts=tuple(conflicts),
                           findings=tuple(findings), refusals=tuple(refusals))

    # -----------------------------------------------------------------------
    # 4. Running one selection
    # -----------------------------------------------------------------------

    def _run_free_methods(self, state: EngagementState, touched: list[Entity],
                          refusals: list[str]) -> tuple[tuple[str, str], ...]:
        """S6: during discovery, a method that costs nothing and calls no model
        may run on what the registry already holds, so its outputs feed
        uncertainty and question value this turn. A RESEARCH or MODEL_ASSISTED
        selection is skipped here and waits for the approved charter - running
        one now would spend the client's money on an engagement they have not
        yet agreed to."""
        registry = state.registry
        ran: list[tuple[str, str]] = []
        for selection in select_methods(open_issues(registry), registry, self._methods):
            spec = self._methods.get(selection.method_id).spec
            if spec.execution not in FREE_EXECUTION or selection.tied:
                continue
            if selection.inputs.missing or attempted(registry, selection.method_id, selection.issue_id):
                continue
            before = len(registry.rows())
            if self._run_free(state, selection, spec, refusals):
                ran.append((selection.method_id, selection.issue_id))
                touched.extend(registry.rows()[before:])
        return tuple(ran)

    def _run_free(self, state: EngagementState, selection: Selection, spec,
                  refusals: list[str]) -> bool:
        """Direct execution through the one door that refuses a paid or tied
        selection (`run_free`). Whatever the method produced is written as one
        batch: a half-written analysis would leave conclusions with no inputs."""
        registry = state.registry
        actor_ref = f"method:{spec.id}@{spec.version}"
        ctx = MethodContext(registry=registry, provider=self._provider,
                            calc=self._calculator(state), actor=Actor.METHOD, actor_ref=actor_ref,
                            issue_ids=(selection.issue_id,), settings=state.settings_bounds())
        try:
            result = run_free(selection, ctx, methods=self._methods)
        except Exception as exc:
            self._record_analysis(state, spec, selection.issue_id, actor_ref=actor_ref,
                                  state_value=AnalysisState.BLOCKED, blocked_on=(type(exc).__name__,))
            refusals.append(f"{TurnStep.FREE_METHODS}: {spec.id}: {exc}")
            return False
        deltas: list[EntityDelta] = list(result.deltas)
        for q in result.questions:
            deltas.append(Add(make_entity(
                kind=Kind.QUESTION, engagement_id=registry.engagement_id, payload=q,
                provenance=Provenance(actor=Actor.METHOD, actor_ref=actor_ref,
                                      derived_from=(selection.issue_id,)),
                confidence=Confidence(None), relevance=Relevance(None, 0.0),
                relation=RelationToCentralDecision.INFORMS, status=Status.OPEN)))
        try:
            written = registry.apply_all(deltas)
        except RegistryError as exc:
            # The batch rolled back whole. The attempt is recorded as blocked
            # so the round loop does not offer the same refusal again.
            self._record_analysis(state, spec, selection.issue_id, actor_ref=actor_ref,
                                  state_value=AnalysisState.BLOCKED, blocked_on=(exc.invariant,))
            refusals.append(f"{TurnStep.FREE_METHODS}: {spec.id}: {exc}")
            return False
        self._record_analysis(state, spec, selection.issue_id, actor_ref=actor_ref,
                              state_value=AnalysisState.DONE, outputs=tuple(e.id for e in written))
        return True

    def _assign(self, state: EngagementState, selection: Selection,
                refusals: list[str]) -> RunOutcome | None:
        """The mechanical specialist trigger (MF1.2): a RESEARCH or
        MODEL_ASSISTED selection, or a tie at equal rank, becomes an Assignment
        with a frozen evidence window and a budget, and runs under S1-S6."""
        registry = state.registry
        issue = registry.get(selection.issue_id)
        if issue is None:                                 # pragma: no cover - defensive
            return None
        assignment = Assignment.from_selection(issue, selection, registry, methods=self._methods,
                                               settings_bounds=state.settings_bounds())
        outcome = run_assignment(assignment, registry, self._provider, self._calculator(state),
                                 methods=self._methods, settings_bounds=state.settings_bounds())
        if outcome.outcome != "done":
            refusals.append(f"{selection.method_id}: assignment {outcome.assignment_id} "
                            f"{outcome.outcome}{': ' + outcome.rejection_rule if outcome.rejection_rule else ''}")
        return outcome

    def _record_analysis(self, state: EngagementState, spec, issue_id: str, *, actor_ref: str,
                         state_value: AnalysisState, outputs: tuple[str, ...] = (),
                         blocked_on: tuple[str, ...] = ()) -> Entity:
        """One ANALYSIS row per direct run. The specialist runner writes its
        own; both are read by `attempted()`, which is what stops a method being
        offered the same node twice."""
        registry = state.registry
        return registry.apply(Add(make_entity(
            kind=Kind.ANALYSIS, engagement_id=registry.engagement_id,
            payload=AnalysisPayload(method_id=spec.id, method_version=spec.version,
                                    issue_ids=(issue_id,), state=state_value, outputs=outputs,
                                    blocked_on=blocked_on),
            provenance=Provenance(actor=Actor.METHOD, actor_ref=actor_ref, derived_from=(issue_id,)),
            confidence=Confidence(None), relevance=Relevance(None, 0.0),
            relation=RelationToCentralDecision.INFORMS, status=Status.PROPOSED)))

    # -----------------------------------------------------------------------
    # 5. The diagnosis moving under an approved charter
    # -----------------------------------------------------------------------

    def _maybe_amend(self, state: EngagementState) -> Entity | None:
        """Evidence that changes the diagnosis amends the charter (design 6.7).

        The margin is the law, as it is for symptom-vs-problem: a candidate
        that merely edges ahead reflects which evidence happened to arrive
        first, and re-opening the mandate on that would churn the engagement.
        The amendment PROPOSES the new central decision; it becomes central
        only if the client approves the amendment.
        """
        registry = state.registry
        charter = approved_charter(registry)
        if charter is None:                               # pragma: no cover - guarded by run_analysis
            return None
        central_id = charter.payload.central_decision
        weights = hypothesis_weights(registry)
        current = weights.get(central_id, 0.0) if central_id else 0.0
        margin = float(state.bound("CHARTER_MIN_MARGIN"))
        rivals = sorted(((w, did) for did, w in weights.items()
                         if did != central_id and (w - current) >= margin),
                        key=lambda t: (-t[0], t[1]))
        if not rivals:
            return None
        winner = rivals[0][1]
        proposal = charter_mod.amend(registry, charter.id, turn_number=state.turn_n,
                                     bounds=state.settings_bounds(), central_decision=winner,
                                     methods=self._methods)
        advance(state, Phase.CHARTER_PROPOSED, methods=self._methods)
        return proposal.charter
