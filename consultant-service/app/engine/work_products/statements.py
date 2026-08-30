"""Statements: the one canonical wording of every claim the deliverables
repeat, and the tokens that carry it (design 11.1).

The laws this module enforces:

  S-VERBATIM  a client-stated FACT is printed in the client's own words,
              quoted, and suffixed "as stated by the client" - the label
              CLIENT_STATED authority renders as (MF2.1, spec section 7)
  S-LABEL     an ASSUMPTION that no client has approved carries
              registry.PROPOSED_LABEL, reused verbatim from r30
              (app/pipeline/registry.py:52), so a proposal can never read as
              a finding (L3 checks the same label on the extracted page)
  S-UNKNOWN   a hole - no quantity, no scope, no as-of date, no source, a
              question the client answered "don't know" - renders as
              RenderingRules.unknown_text. Unknown stays unknown; it is
              never defaulted, blanked or averaged away
  S-ONE-TEXT  a claim consumed by REPEATED_IN_SECTIONS or more sections is
              written once as a STATEMENT entity and referenced by its token
              everywhere; substitution (corrections.py) inserts that one
              string, so two sections cannot drift apart

Nothing here is worded by a model and nothing branches on an engagement
type: statement_text is a function of the entity's kind (a closed enum) and
its typed fields, so the same code prints a headcount fact whatever the
engagement is about.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, TYPE_CHECKING

# The r30 label, imported rather than retyped: L3 looks for this exact string
# on the page, and two copies of a constant are two constants.
from app.pipeline.registry import PROPOSED_LABEL

from app.engine.calc.units import format_quantity
from app.engine.types import (
    ID_PREFIX,
    TERMINAL_STATUSES,
    Actor,
    Add,
    ApprovalState,
    Confidence,
    Entity,
    FactBasis,
    Kind,
    Provenance,
    RelationToCentralDecision,
    Relevance,
    StatementPayload,
    Status,
    make_entity,
)
from app.engine.work_products.decl import RenderingRules

if TYPE_CHECKING:  # the read side is a protocol; importing it at runtime would be circular
    from app.engine.registry import RegistryView


DEFAULT_RULES = RenderingRules()

# The visible mark of CLIENT_STATED authority (MF2.1). A recollection is
# evidence of what the client believes, and the page says so; a verified
# record outranks it visibly rather than silently.
CLIENT_STATED_SUFFIX = "as stated by the client"

TOKEN_OPEN = "[[STMT:"
TOKEN_CLOSE = "]]"

# "Repeated" means printed in more than one place. This is the definition of
# repetition, not a count of anything an engagement has: no engagement gets a
# fixed number of statements, and nothing here caps how many there may be.
REPEATED_IN_SECTIONS = 2

_EM = "\u2014"


def token_for(statement_id: str) -> str:
    return f"{TOKEN_OPEN}{statement_id}{TOKEN_CLOSE}"


# ---------------------------------------------------------------------------
# The parts every kind renders the same way
# ---------------------------------------------------------------------------

def _hole(value: Any, rules: RenderingRules) -> str:
    """A missing part of a claim prints as the declared unknown text. The test
    is `is None` / empty string, never falsy arithmetic: a zero is a value, and
    a dimension a newer normaliser pins to an empty-but-present value is not
    condemned as absent."""
    if value is None:
        return rules.unknown_text
    text = str(value).strip()
    return text if text else rules.unknown_text


def _get(view: "RegistryView | None", entity_id: str | None) -> Entity | None:
    if view is None or not entity_id:
        return None
    return view.get(entity_id)


def _measure_name(fact_payload: Any, view: "RegistryView | None", rules: RenderingRules) -> str:
    m = _get(view, getattr(fact_payload, "measure_id", None))
    if m is not None:
        return _hole(m.payload.name, rules)
    # A fact with no MEASURE has no reconciliation key either; its topic is
    # display text only, and when there is none the hole is printed.
    return _hole(getattr(fact_payload, "topic", None), rules)


def _source_names(e: Entity, view: "RegistryView | None", rules: RenderingRules) -> str:
    """The evidence a row cites, by name. Provenance is not decoration: a
    reader must be able to ask 'who said this' of every printed claim
    (rules.cite_provenance)."""
    names = []
    for sid in e.provenance.derived_from:
        src = _get(view, sid)
        if src is not None and src.kind is Kind.EVIDENCE_SOURCE:
            names.append(str(src.payload.name))
    if not names:
        return _hole(None, rules)
    return "; ".join(names)


def _quantity_basis(payload: Any, e: Entity, view: "RegistryView | None", rules: RenderingRules) -> str:
    q = getattr(payload, "quantity", None)
    dims = q.dimensions if q is not None else None
    scope = _hole(getattr(dims, "scope", None), rules)
    as_of = _hole(getattr(dims, "as_of", None), rules)
    return f"{scope}; as of {as_of}; source: {_source_names(e, view, rules)}"


def _text_of(payload: Any, rules: RenderingRules) -> str:
    for name in ("statement", "text", "name", "question"):
        value = getattr(payload, name, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return rules.unknown_text


# ---------------------------------------------------------------------------
# Per-kind renderings (design 11.1)
# ---------------------------------------------------------------------------

def _fact(e: Entity, view: "RegistryView | None", rules: RenderingRules) -> str:
    p = e.payload
    basis = _quantity_basis(p, e, view, rules)
    if p.basis is FactBasis.CLIENT_STATED and rules.client_facts_verbatim:
        # The client's words, exactly, inside quotes. corrections.py masks this
        # span before any canonical mapping runs (MF2.6) and L14 checks the
        # same string survives onto the page.
        core = '"' + p.statement + '" ' + _EM + " " + CLIENT_STATED_SUFFIX
        if p.quantity is not None:
            return f"{core} ({_measure_name(p, view, rules)}: {format_quantity(p.quantity)}; {basis})"
        return f"{core} ({basis})"
    if p.quantity is not None:
        return f"{_measure_name(p, view, rules)}: {format_quantity(p.quantity)} ({basis})"
    return f"{_text_of(p, rules)} (source: {_source_names(e, view, rules)})"


def _unapproved(e: Entity) -> bool:
    """Approval is a status the CLIENT grants (APPROVAL_OWNER); the payload
    field records what the client said. Either one saying approved is enough,
    and neither saying so leaves the row unapproved."""
    return e.payload.approval is not ApprovalState.APPROVED and e.status is not Status.APPROVED


def _assumption(e: Entity, view: "RegistryView | None", rules: RenderingRules) -> str:
    p = e.payload
    text = _text_of(p, rules)
    if p.quantity is not None:
        text = f"{text} ({format_quantity(p.quantity)})"
    if rules.label_unapproved_assumptions and _unapproved(e):
        # S-LABEL. Without this suffix a proposal reads as a finding, which is
        # exactly the failure L3 exists to catch.
        return f"{text} {PROPOSED_LABEL}"
    return text


def _recommendation(e: Entity, view: "RegistryView | None", rules: RenderingRules) -> str:
    p = e.payload
    text = _text_of(p, rules)
    if not rules.conditional_recommendations_marked:
        return text
    open_on = []
    for qid in p.conditional_on:
        q = _get(view, qid)
        # No view, or a question this registry does not hold: the condition
        # stands. Fail closed - a condition is dropped only when the register
        # shows the question answered.
        if q is None or q.status is Status.OPEN:
            open_on.append(q.payload.text if q is not None else qid)
    if open_on:
        return f"{text} {_EM} conditional on: " + "; ".join(open_on)
    return text


def _question(e: Entity, view: "RegistryView | None", rules: RenderingRules) -> str:
    p = e.payload
    # `is True` on purpose (owner contract): a row written before the field
    # existed is not read as "the client answered".
    if p.unknown is True:
        return f"{p.text} ({rules.unknown_text})"
    return _text_of(p, rules)


def _regulated_matter(e: Entity, view: "RegistryView | None", rules: RenderingRules) -> str:
    p = e.payload
    # The constant refusal sentence, never an interpretation of our own.
    return f"{p.text} ({p.domain.value}; {p.adviser_class}). {p.cannot_answer_statement}"


def _conflict(e: Entity, view: "RegistryView | None", rules: RenderingRules) -> str:
    p = e.payload
    sides = " vs ".join(f"{c.statement} [{c.entity_id}]" for c in p.conclusions)
    if p.resolution_chosen:
        return f"{p.kind.value}: {sides} {_EM} resolved in favour of {p.resolution_chosen}"
    return f"{p.kind.value}: {sides} {_EM} open"


def _quantified(e: Entity, view: "RegistryView | None", rules: RenderingRules) -> str:
    """Anything else that carries a Quantity - a cost, a benefit, an expected
    outcome, an objective's target. One rendering, so a number reads the same
    wherever it is printed."""
    p = e.payload
    text = _text_of(p, rules)
    q = getattr(p, "quantity", None)
    if q is None:
        q = getattr(p, "target", None)
    if q is None:
        return text
    return f"{text}: {format_quantity(q)}"


def _plain(e: Entity, view: "RegistryView | None", rules: RenderingRules) -> str:
    return _text_of(e.payload, rules)


# Kind -> renderer. A dict, not a chain of string comparisons: the branch is a
# lookup on a closed enum, which is what keeps the whitelist AST law (S5) true
# here and what keeps a new kind from needing a new branch.
TEXT_BY_KIND: Mapping[Kind, Callable[[Entity, "RegistryView | None", RenderingRules], str]] = {
    Kind.FACT: _fact,
    Kind.ASSUMPTION: _assumption,
    Kind.RECOMMENDATION: _recommendation,
    Kind.QUESTION: _question,
    Kind.REGULATED_MATTER: _regulated_matter,
    Kind.CONFLICT: _conflict,
    Kind.COST: _quantified,
    Kind.BENEFIT: _quantified,
    Kind.EXPECTED_OUTCOME: _quantified,
    Kind.OBJECTIVE: _quantified,
    Kind.SUCCESS_CRITERION: _quantified,
}


def statement_text(entity: Entity, view: "RegistryView | None" = None, *,
                   rules: RenderingRules = DEFAULT_RULES) -> str:
    """The one canonical wording of one entity. Deterministic in the entity and
    the registry it is read against: the same row renders the same string in
    every product, in every format and on every run."""
    return TEXT_BY_KIND.get(entity.kind, _plain)(entity, view, rules)


# ---------------------------------------------------------------------------
# STATEMENT entities and their tokens (S-ONE-TEXT)
# ---------------------------------------------------------------------------

def repeated_claims(consumed_by: Mapping[str, Iterable[str]], always: Iterable[str] = ()) -> tuple[str, ...]:
    """Entity ids that more than one section prints, in id order.

    `consumed_by` maps section id -> the entity ids that section renders.
    `always` are ids that need a statement whatever the count: a narrative may
    reference a claim only by token, so a claim a narrative speaks about is
    repeated by construction.

    The result is ordered by the ids themselves, never by the order the
    sections were built in, so two registries holding the same rows produce
    the same statements and therefore byte-identical documents."""
    sections_of: dict[str, set[str]] = {}
    for section_id, ids in consumed_by.items():
        for entity_id in ids:
            sections_of.setdefault(entity_id, set()).add(section_id)
    wanted = {eid for eid, secs in sections_of.items() if len(secs) >= REPEATED_IN_SECTIONS}
    wanted |= set(always)
    return tuple(sorted(wanted))


def existing_statements(view: "RegistryView") -> dict[str, Entity]:
    """of_entity_id -> the live STATEMENT that already carries its wording."""
    return {s.payload.of_entity_id: s for s in view.query(Kind.STATEMENT)
            if s.status not in TERMINAL_STATUSES}


def _next_statement_id(view: "RegistryView", taken: set[str]) -> str:
    prefix = ID_PREFIX[Kind.STATEMENT]
    used = {s.id for s in view.query(Kind.STATEMENT)} | taken
    n = 0
    for entity_id in used:
        _, _, num = entity_id.rpartition("-")
        if num.isdigit():
            n = max(n, int(num))
    return f"{prefix}-{n + 1}"


def statement_deltas(view: "RegistryView", consumed_by: Mapping[str, Iterable[str]], *,
                     rules: RenderingRules = DEFAULT_RULES,
                     always: Iterable[str] = ()) -> tuple[Add, ...]:
    """One STATEMENT row per repeated claim that does not have one yet.

    Rendering is a pure function of the registry: this returns deltas for the
    caller to apply, exactly as a method does, so a render never edits state
    behind the planner's back."""
    if not rules.statements_by_token:
        return ()
    have = existing_statements(view)
    central = view.central_decision()
    taken: set[str] = set()
    out: list[Add] = []
    for entity_id in repeated_claims(consumed_by, always):
        if entity_id in have:
            continue
        e = view.get(entity_id)
        if e is None or e.status in TERMINAL_STATUSES:
            continue
        statement_id = _next_statement_id(view, taken)
        taken.add(statement_id)
        sections = tuple(sorted(sid for sid, ids in consumed_by.items() if entity_id in set(ids)))
        payload = StatementPayload(text=statement_text(e, view, rules=rules), of_entity_id=entity_id,
                                   token=token_for(statement_id), rendered_in=sections)
        out.append(Add(make_entity(
            kind=Kind.STATEMENT, engagement_id=view.engagement_id, payload=payload,
            provenance=Provenance(actor=Actor.SYSTEM, actor_ref="renderer:statements",
                                  derived_from=(entity_id,)),
            confidence=Confidence(None), relevance=Relevance(central.id if central else None, 0.0),
            relation=RelationToCentralDecision.INFORMS, status=Status.PROPOSED, entity_id=statement_id)))
    return tuple(out)


def token_index(view: "RegistryView", extra: Iterable[Add] = ()) -> dict[str, str]:
    """entity id -> its statement token, over the live STATEMENTs plus the
    deltas this render pass just produced (they belong to the same pass; the
    caller applies them)."""
    out = {eid: s.payload.token for eid, s in existing_statements(view).items()}
    for delta in extra:
        out[delta.entity.payload.of_entity_id] = delta.entity.payload.token
    return out


def token_texts(view: "RegistryView", extra: Iterable[Add] = ()) -> dict[str, str]:
    """token -> the exact string it stands for. This mapping is the whole of
    what corrections.py may substitute."""
    out = {s.payload.token: s.payload.text for s in existing_statements(view).values()}
    for delta in extra:
        out[delta.entity.payload.token] = delta.entity.payload.text
    return out


def client_fact_texts(view: "RegistryView", *, rules: RenderingRules = DEFAULT_RULES) -> tuple[str, ...]:
    """The rendered statement of every CONFIRMED client-stated FACT: the spans
    corrections.py masks before it maps anything (MF2.6). Longest first, so a
    quote nested inside a longer quote is masked as part of the longer one."""
    texts = [statement_text(f, view, rules=rules) for f in view.query(Kind.FACT, status=Status.CONFIRMED)
             if f.payload.basis is FactBasis.CLIENT_STATED]
    return tuple(sorted(set(texts), key=lambda t: (-len(t), t)))
