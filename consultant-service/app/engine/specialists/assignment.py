"""Specialist assignments (contracts.py section 12, design section 8).

A specialist is a temporary analytical role, never a standing agent: the
Assignment built here freezes, before anything runs, the question, the exact
evidence the specialist may read, the method it must use, the assumptions it
may make, the decisions it may not take and the budget it may spend. The
runner (runner.py) executes it behind a ScopedView and admits the result
all-or-nothing under S1-S6.

Why the freeze is the whole mechanism: an analyst who can widen their own
evidence, redefine the question or approve their own assumptions produces work
nobody can audit afterwards. Every one of those moves is a typed refusal here
or in the runner, so "the specialist stayed in scope" is a property of the
code rather than a claim in a report.

  permitted_evidence   the entities the method's own InputSpecs match, plus
                       the derived_from closure of those entities, plus the
                       assigned issue node and the nodes it hangs from. The
                       closure is what makes the scope honest: an analysis may
                       always look at what its inputs rest on, and never at
                       anything else. The node chain is there because a
                       specialist that cannot read its own question cannot
                       answer it. ScopedView adds every CONFIRMED client
                       preference on top, because objectives, constraints and
                       deadlines are the frame every analysis works inside.
  forbidden_decisions  every live DECISION except the SUBORDINATE ones this
                       issue node is decisive_for. A specialist answers its
                       node; it does not get to settle the engagement.
  allowed_assumptions  a grant exists only for a kind the method declared it
                       writes, so a specialist cannot invent an assumption its
                       method never claimed it would need (S5).
  validation           the method's own declared validators. The runner runs
                       the union of these and MethodSpec.validators, so a law
                       a method declared bites on every run of it however the
                       Assignment was built.
  budget               a ceiling per method, derived from what the method
                       declared and from the operator-movable ENGINE_* bounds,
                       never a fixed count per engagement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping

from app.engine.methods.contract import METHODS, MethodRegistry, MethodSpec, Selection, Validator
from app.engine.types import (
    TERMINAL_STATUSES,
    AssumptionGrant,
    Budget,
    DecisionRole,
    Entity,
    Kind,
    SpecialistAssignmentPayload,
)

if TYPE_CHECKING:  # the read side is a protocol; importing it at runtime would
    from app.engine.registry import RegistryView  # tie this module to one implementation


# The six admission rules, as the runner states them in the Finding it raises.
# The table IS the law list: a rule the runner no longer checks is a key here
# with no enforcement, which is what the mutation tests hunt for.
ADMISSION_RULES: Mapping[str, str] = {
    "S1": "no Supersede or SetStatus on an entity this assignment did not create",
    "S2": "every Add has status PROPOSED",
    "S3": ("no FACT with basis client_stated / document_verified / document_extracted; "
           "a calculated FACT carries the formula and inputs that reproduce it"),
    "S4": "no RECOMMENDATION or TRADE_OFF on a forbidden decision; no OPTION for the central decision unless the issue targets it",
    "S5": "every derived_from id is permitted evidence or created here; every ASSUMPTION matches a grant and is unapproved",
    "S6": "every Quantity is calculated (formula + inputs) or copied from permitted evidence by id",
}

# One full-size model call, as app/engine/llm.py ModelCall.max_tokens defines
# it. The token ceiling is a whole number of the provider's own default call
# size, so a method that declares two calls is funded for two calls and not a
# third -- the budget follows the declaration instead of a number typed here.
TOKENS_PER_MODEL_CALL = 4000


def resolve_bounds(settings_bounds: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """The live ENGINE_* values. Read through app.config so an operator can
    move a ceiling without a code change; the frozen BOUNDS defaults answer if
    the settings object is not importable (a bounds lookup must never be the
    reason an assignment cannot be built)."""
    if settings_bounds is not None:
        return settings_bounds
    try:
        from app.config import settings

        return settings.engine_bounds()
    except Exception:                                    # pragma: no cover - defensive
        from app.engine.types import BOUNDS

        return BOUNDS


def default_budget(spec: MethodSpec, settings_bounds: Mapping[str, Any] | None = None) -> Budget:
    """What one run of this method may spend. Every term is derived:

      model calls  exactly what the method declared (M1 makes that 0 for a
                   DETERMINISTIC or CALCULATION method, so a free method run
                   under an assignment is funded for no calls at all);
      tokens       that many full-size calls;
      deltas       one full fan-out per analysis round for each kind the
                   method declared it writes -- a ceiling against a runaway
                   result, not a target, and moved by ENGINE_MAX_FANOUT /
                   ENGINE_MAX_ANALYSIS_ROUNDS rather than by editing this line.
    """
    b = resolve_bounds(settings_bounds)
    calls = int(spec.max_model_calls)
    kinds = max(1, len(spec.output_kinds))
    deltas = int(b["MAX_FANOUT"]) * int(b["MAX_ANALYSIS_ROUNDS"]) * kinds
    return Budget(max_model_calls=calls, max_tokens=calls * TOKENS_PER_MODEL_CALL, max_deltas=deltas)


@dataclass(frozen=True)
class Assignment:
    """A temporary analytical role (spec section 4), persisted as a
    SPECIALIST_ASSIGNMENT entity. The runner builds a ScopedView from
    permitted_evidence plus every CONFIRMED client-preference entity, executes
    the method as Actor.SPECIALIST and admits the result all-or-nothing under
    S1-S6: one bad delta rejects the whole result."""
    id: str
    question: str
    issue_id: str
    method_id: str
    permitted_evidence: tuple[str, ...]
    output_schema: type | None
    allowed_assumptions: tuple[AssumptionGrant, ...]
    forbidden_decisions: tuple[str, ...]
    validation: tuple[Validator, ...]
    budget: Budget

    @classmethod
    def from_selection(cls, issue: Entity, selection: Selection, registry: "RegistryView", *,
                       methods: MethodRegistry = METHODS, budget: Budget | None = None,
                       assignment_id: str = "", settings_bounds: Mapping[str, Any] | None = None) -> "Assignment":
        spec = methods.get(selection.method_id).spec
        permitted: set[str] = set()
        for inp in spec.required_inputs + spec.optional_inputs:
            for e in registry.query(inp.kind):
                if inp.matches(e):
                    permitted.add(e.id)
        frontier = list(permitted)
        while frontier:                                  # derived_from closure
            e = registry.get(frontier.pop())
            if e is None:
                continue
            for d in e.provenance.derived_from:
                if d not in permitted:
                    permitted.add(d)
                    frontier.append(d)
        # The node itself, and the nodes it hangs from, are always in the
        # window. The question is not evidence, so the InputSpec pass above
        # never matches it -- and with the assigned node hidden a method's
        # own `ctx.registry.get(ctx.issue_ids[0])` came back None, so every
        # model-assisted method answered its no-issue finding instead of the
        # question, and a method that grafts children numbered them from an
        # empty view and had the ids refused by I6. Ancestors come with it
        # because a sub-question means nothing apart from the question it
        # decomposes. Only the chain itself is added, never its derived_from
        # closure: reading the question is not a licence to read the evidence
        # some other node rests on, which is the scope the method's InputSpecs
        # were meant to draw.
        node: Entity | None = issue
        walked: set[str] = set()
        while node is not None and node.id not in walked:  # a malformed parent
            walked.add(node.id)                            # cycle must not hang
            permitted.add(node.id)                         # assignment building
            parent = getattr(node.payload, "parent_id", None)
            node = registry.get(parent) if parent else None
        decisive = set(issue.payload.decisive_for)
        # Every live decision is out of bounds except a subordinate one this
        # node was built to settle: answering the node is the job, and taking
        # the engagement's central decision is never a specialist's to take.
        forbidden = tuple(sorted(
            d.id for d in registry.query(Kind.DECISION)
            if d.status not in TERMINAL_STATUSES
            and not (d.id in decisive and d.payload.role == DecisionRole.SUBORDINATE)))
        # A grant exists only for a kind the method declared it writes. An
        # unconditional grant would make S5's "matches a grant" vacuous: the
        # point is that a specialist cannot reach for an assumption its own
        # method never said it needed.
        grants = tuple(AssumptionGrant(kind=k, unit_family=None, must_cite=True)
                       for k in spec.output_kinds if k == Kind.ASSUMPTION)
        return cls(id=assignment_id, question=issue.payload.text, issue_id=issue.id, method_id=spec.id,
                   permitted_evidence=tuple(sorted(permitted)), output_schema=spec.output_schema,
                   allowed_assumptions=grants, forbidden_decisions=forbidden, validation=spec.validators,
                   budget=budget if budget is not None else default_budget(spec, settings_bounds))

    def as_payload(self, methods: MethodRegistry = METHODS, *, outcome: str | None = None,
                   rejection_rule: str | None = None) -> SpecialistAssignmentPayload:
        """The assignment as the registry stores it. Validators are recorded by
        name: what checked the result is part of the record, and a function
        object is not something a row can hold."""
        spec = methods.get(self.method_id).spec
        return SpecialistAssignmentPayload(
            question=self.question, issue_id=self.issue_id, method_id=self.method_id,
            permitted_evidence=self.permitted_evidence, output_kinds=spec.output_kinds,
            allowed_assumptions=self.allowed_assumptions, forbidden_decisions=self.forbidden_decisions,
            validation=tuple(getattr(v, "__name__", "validator") for v in self.validation), budget=self.budget,
            outcome=outcome, rejection_rule=rejection_rule)

    def grant_for(self, entity: Entity) -> AssumptionGrant | None:
        """The grant that admits this entity, or None. Kept beside the grants
        so S5 reads one predicate rather than re-deriving the match."""
        for g in self.allowed_assumptions:
            if g.kind != entity.kind:
                continue
            if g.unit_family is not None:
                q = getattr(entity.payload, "quantity", None)
                if q is None or q.unit_family != g.unit_family:
                    continue
            if g.must_cite and not entity.provenance.derived_from:
                continue
            return g
        return None


__all__ = ["ADMISSION_RULES", "Assignment", "TOKENS_PER_MODEL_CALL", "default_budget", "resolve_bounds"]
