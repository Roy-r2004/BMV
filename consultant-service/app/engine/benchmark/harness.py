"""app/engine/benchmark/harness.py - the simulated client and one run of one
case (design 17.3, 17.4).

The harness plays the client and drives the Partner; it never decides anything
the engine decides. Two rules hold it to that:

  * the client reveals a dossier item only when a question asks for it, matched
    on TYPES (MF1.4). The item's annotation and the question's `asks_for` must
    name the same `Kind`, and no filter the question states may contradict what
    the annotation says. Absence is not a contradiction: a key the annotation
    does not mention is not a constraint, because a benchmark that treated
    silence as a mismatch would grade the engine on the annotator's
    thoroughness (owner contract: absent evidence is not evidence of a defect).
  * the client answers in the dossier's exact wording. The registry refuses a
    client fact whose statement is not a verbatim span of the turn (I2), so a
    paraphrasing client would quietly stop the engine from ever holding a
    client fact - and every conflict, restatement and verbatim law downstream
    would go untested.

The tree's first node is the ENGINE's: an approved charter opens it
(`partner.charter.seed_root_issue`). The harness keeps a fallback for the build
where that does not happen, because a run with no root reaches analysis with an
empty tree and every method sits unselected - fifteen empty bundles that would
still pass most of the shape checks. If the fallback ever fires the bundle says
so (`seeded_root`, read back off the registry's own provenance rather than off
a flag the caller set), and the fake-mode test asserts it never does: an engine
that stopped seeding its root must fail loudly, not be quietly compensated for.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from app.engine.benchmark import oracle as oracle_mod
from app.engine.benchmark.cases import LoadedCase
from app.engine.gates import laws as laws_mod
from app.engine.gates.release import client_approval, release_status
from app.engine.llm import ModelCall, ModelProvider, ModelResponse
import app.engine.methods.builtin  # noqa: F401  - method registration is by import
from app.engine.methods.contract import METHODS, MethodRegistry, QuestionShape
from app.engine.partner.charter import ROOT_ISSUE_ACTOR_REF, root_issue_id
from app.engine.partner.ingest import TURN_CANDIDATE_KINDS
from app.engine.partner.questions import ASKABLE_STRATEGIES as _ASKABLE
from app.engine.partner.loop import Partner
from app.engine.partner.state import EngagementState, PhaseError, advance, synthesis_blockers
from app.engine.registry import EngagementRegistry
from app.engine.synthesis.conflicts import detect_conflicts, reevaluate_materiality
from app.engine.synthesis.recommend import refresh_conditional_on
from app.engine.synthesis.regulated import CLASSIFIER_PURPOSE, screen_synthesis
from app.engine.synthesis.resolve import auto_resolve, emit_decisions_required
from app.engine.templating import render
from app.engine.types import (
    BOUNDS, Actor, Add, AsksFor, Confidence, Entity, FillStrategy, Interrogative,
    IssuePayload, Kind, Phase, Provenance, Relevance, RelationToCentralDecision, Status, make_entity,
)
from app.engine.work_products.integrity_record import build_integrity_record
from app.engine.work_products.plan import plan_work_products

__all__ = [
    "AnnotatedClassifier",
    "BENCH_CLIENT_PURPOSE",
    "Bundle",
    "BudgetExceeded",
    "CountingProvider",
    "FIXED_CLOCK",
    "SimulatedClient",
    "asks_for_matches",
    "issue_tree_hash",
    "outstanding",
    "run_case",
    "shape_signature",
]

# The simulated client's own model purpose, ledgered apart from the engine's
# calls: the client's spend is the benchmark's, not the engagement's.
BENCH_CLIENT_PURPOSE = "bench:client"

# One instant for every row in a fake run. `Entity.content_hash` already
# excludes `recorded_at` (MF3.7), but the bundle carries ids and the registry
# hash, and a moving clock would make "the same case twice" a different string.
FIXED_CLOCK = "2026-01-01T00:00:00+00:00"

# What the persona itself answers, as opposed to the dossier. The persona IS
# the decision owner and the business they run, and both are stated in the case
# file; without this a run can never name a decision owner, and no engagement
# would ever reach analysis (state.analysis_blockers). Every other kind comes
# from the annotated dossier or is answered "no record of that here".
_PERSONA_ANSWERS: Mapping[Kind, str] = {
    Kind.DECISION_OWNER: "{name}, {role}",
    Kind.BUSINESS_CONTEXT: "{company} works in {sector} in {country}, at {size}",
}

_MISSING = object()

# The one Bundle field that is not part of its serialised account: the registry
# rides along for the adversarial checks and is excluded by name here, once.
_RIDE_ALONG = "registry"


def _joined(call: ModelCall) -> str:
    """One call's messages as one text - what every prompt-reading rule sees."""
    return "\n".join(str(m.get("content") or "") for m in call.messages)


# The candidate rows the regulated classifier prompt renders.
_CANDIDATE_ROW = re.compile(r"^- (?P<id>[A-Z]{3}-\d+) \[[a-z_]+\]: ", re.M)


def _turn_kind(kind: Kind) -> Kind:
    """The kind an answer is ingested AS. A turn may propose only nine of the
    41 kinds (ingest.TURN_CANDIDATE_KINDS), so a client answering a question
    about a capability or a cost is stating a FACT about one - which is what a
    client does. The MATCH is still made on the annotation's own kind, so the
    reveal stays as typed as the annotation is; only the envelope narrows."""
    return kind if kind in TURN_CANDIDATE_KINDS else Kind.FACT


class AnnotatedClassifier:
    """The regulated screen's stage-one judgement, in fake mode.

    The structural oracle refuses to claim a domain (it cannot read a licence
    out of prose, and a hashed guess would route arbitrary wording to an
    arbitrary profession). But every case file states the matters a good engine
    should hand to a qualified adviser, and `<case>.keys.json` types each one
    with its `RegulatedDomain`. Those annotations ARE the model's judgement,
    supplied by the harness so that the ROUTING can be measured: the matter
    rows, the adviser class, the withheld interpretation, the licensed flag on
    a recommendation and L4.

    What this does NOT measure is the classification. That is a model
    capability, and only a real run is evidence about it (design 17.5, risk 5).
    Claims are spread over the candidates the prompt showed, ordered by id, so
    the same registry produces the same claims twice.
    """

    def __init__(self, inner: ModelProvider, loaded: LoadedCase):
        self._inner = inner
        self._domains = [a.domain.value for a in loaded.keys.regulated_domains]

    def complete(self, call: ModelCall) -> ModelResponse:
        if call.purpose != CLASSIFIER_PURPOSE or not self._domains:
            return self._inner.complete(call)
        prompt = _joined(call)
        candidates = sorted({m.group("id") for m in _CANDIDATE_ROW.finditer(prompt)})
        claims = [{"entity_id": cid, "domain": self._domains[i % len(self._domains)],
                   "trigger": "", "reason": "annotated regulated matter for this case"}
                  for i, cid in enumerate(candidates)]
        return ModelResponse(json.dumps({"claims": claims}), "stop",
                             {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0},
                             f"annotated-classifier-{len(candidates)}")


class BudgetExceeded(RuntimeError):
    """A costed run reached --max-usd. Raised before the next call, never after
    it: the ceiling is a ceiling, not a report."""


# =============================================================================
# 1. Typed reveal
# =============================================================================

def _admitted(value: Any) -> tuple[Any, ...]:
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(_norm(v) for v in value)
    return (_norm(value),)


def _norm(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def asks_for_matches(annotated: AsksFor, asked: AsksFor) -> bool:
    """Whether a dossier item annotated `annotated` answers a question asking
    `asked`. Same kind, and every filter key the question states that the
    annotation also states must agree. A key the annotation is silent about is
    not a mismatch - see the module docstring."""
    if annotated.kind is not asked.kind:
        return False
    for key, wanted in dict(asked.filter).items():
        have = dict(annotated.filter).get(key, _MISSING)
        if have is _MISSING:
            continue
        if _norm(have) not in _admitted(wanted):
            return False
    return True


@dataclass
class SimulatedClient:
    """The client for one run. Deterministic by default; `provider` switches
    the wording to a model under purpose `bench:client` while the reveal itself
    stays typed, so a model-mode run cannot leak a fact no question asked for.
    """
    loaded: LoadedCase
    provider: ModelProvider | None = None
    model: str | None = None
    revealed: list[int] = field(default_factory=list)
    offered: list[int] = field(default_factory=list)
    said: list[str] = field(default_factory=list)
    answered: list[str] = field(default_factory=list)

    # -- what the client knows -------------------------------------------
    def _unrevealed(self) -> list[int]:
        return [i for i in range(len(self.loaded.case.dossier)) if i not in self.revealed]

    def _matching(self, asked: Sequence[AsksFor]) -> list[int]:
        out: list[int] = []
        for i in self._unrevealed():
            annotations = self.loaded.asks_for(i)
            if any(asks_for_matches(a, q) for a in annotations for q in asked):
                out.append(i)
        return out

    def _persona_answer(self, asked: Sequence[AsksFor]) -> tuple[Kind, str] | None:
        persona = self.loaded.case.client_persona
        for question_ask in asked:
            template = _PERSONA_ANSWERS.get(question_ask.kind)
            if template is not None:
                return question_ask.kind, template.format(**persona.model_dump())
        return None

    def _document_for(self, question: Entity) -> tuple[str, bytes] | None:
        """A document is handed over when the question asked for one and there
        is one left. Which document is not chosen by wording: the client hands
        over the next one they have not sent."""
        if question.payload.strategy is not FillStrategy.REQUEST_DOCUMENT:
            return None
        for i, doc in enumerate(self.loaded.case.documents):
            if i in self.offered:
                continue
            self.offered.append(i)
            return f"{doc.name}.txt", doc.content.encode("utf-8")
        return None

    # -- what the client says --------------------------------------------
    def opening(self) -> str:
        self.said.append(self.loaded.case.opening_statement)
        return self.loaded.case.opening_statement

    def reply(self, questions: Sequence[Entity]) -> tuple[str, list[tuple[str, bytes]]]:
        """One answer to this turn's questions, plus any documents handed over.

        Every question is answered: with the dossier items whose annotation
        matches it, with what the persona is, or with "no record of that here",
        which the ingester records as unknown and never asks again."""
        lines: list[str] = []
        attachments: list[tuple[str, bytes]] = []
        for question in questions:
            self.answered.append(question.id)
            asked = list(question.payload.asks_for)
            attachment = self._document_for(question)
            if attachment is not None:
                attachments.append(attachment)
            matches = self._matching(asked)
            if matches:
                for i in matches:
                    self.revealed.append(i)
                    item = self.loaded.case.dossier[i]
                    lines.append(oracle_mod.answer_line(
                        question.id, _turn_kind(self.loaded.asks_for(i)[0].kind), item.fact))
                continue
            persona = self._persona_answer(asked)
            if persona is not None and attachment is None:
                lines.append(oracle_mod.answer_line(question.id, _turn_kind(persona[0]), persona[1]))
                continue
            if attachment is None:
                kind = asked[0].kind if asked else Kind.FACT
                lines.append(oracle_mod.answer_line(question.id, _turn_kind(kind),
                                                    oracle_mod.UNKNOWN_MARKER))
        message = "\n".join(lines) if lines else oracle_mod.UNKNOWN_MARKER
        if self.provider is not None:
            message = self._worded(message, questions)
        self.said.append(message)
        return message, attachments

    def _worded(self, deterministic: str, questions: Sequence[Entity]) -> str:
        """Model mode: the persona words the same typed reveal. On any failure
        the deterministic wording stands - a benchmark that skipped a turn
        because the client's model was down would score the engine for an
        outage it did not cause."""
        prompt = render(
            "simulated_client.j2",
            persona=self.loaded.case.client_persona.model_dump(),
            unrevealed=[{"topic": self.loaded.case.dossier[i].topic,
                         "fact": self.loaded.case.dossier[i].fact}
                        for i in self.revealed[-len(questions) or None:]],
            revealed=list(self.said),
            documents=[{"name": d.name, "kind": d.kind} for d in self.loaded.case.documents],
            consultant_message="\n".join(q.payload.text for q in questions),
        )
        call = ModelCall(purpose=BENCH_CLIENT_PURPOSE,
                         messages=({"role": "user", "content": prompt},), model=self.model)
        response = self.provider.complete(call)
        if response.error is not None or not response.text:
            return deterministic
        return response.text

    def revealed_changers(self) -> int:
        """How many of the items that CHANGE the recommendation were surfaced.
        The guard against vacuous divergence: two runs can differ in every
        listed way and still both have missed everything that mattered."""
        changers = set(self.loaded.changing_indexes())
        return len(changers & set(self.revealed))


# =============================================================================
# 2. The provider wrapper that counts and stops
# =============================================================================

class CountingProvider:
    """Counts calls and money, and refuses to place the call that would cross
    the ceiling. Wrapping is how the harness stays out of llm.py: the ledger
    there is the engagement's, this one is the run's."""

    def __init__(self, inner: ModelProvider, *, max_usd: float | None = None):
        self._inner = inner
        self._max_usd = max_usd
        self.calls: list[tuple[str, float]] = []

    @property
    def cost_usd(self) -> float:
        return round(sum(c for _, c in self.calls), 6)

    def complete(self, call: ModelCall) -> ModelResponse:
        if self._max_usd is not None and self.cost_usd >= self._max_usd:
            raise BudgetExceeded(f"{self.cost_usd} USD spent, ceiling {self._max_usd}")
        response = self._inner.complete(call)
        cost = float((response.usage or {}).get("cost") or 0.0)
        self.calls.append((call.purpose, cost))
        return response


# =============================================================================
# 3. The bundle
# =============================================================================

def shape_signature(shape: QuestionShape) -> str:
    """A shape as one text-free string: what makes two issue trees comparable
    without comparing prose."""
    flags = "".join(c for c, on in (
        ("q", shape.quantified), ("c", shape.comparative),
        ("s", shape.causal), ("t", shape.temporal)) if on)
    cap = shape.capability_class.value if shape.capability_class is not None else ""
    return f"{shape.interrogative.value}/{shape.target_kind.value}/{flags}/{cap}"


def issue_tree_hash(view) -> str:
    """The tree's structure and nothing else: every node's shape and the shape
    of its parent, sorted. No text enters, so two trees hash alike only when
    they are the same STRUCTURE - which is the claim the divergence assertion
    makes (design 17.4)."""
    nodes = [e for e in view.live(Kind.ISSUE)]
    by_id = {e.id: e for e in nodes}
    edges = []
    for node in nodes:
        parent = by_id.get(node.payload.parent_id) if node.payload.parent_id else None
        parent_sig = shape_signature(QuestionShape.of(parent)) if parent is not None else ""
        edges.append(f"{shape_signature(QuestionShape.of(node))}<-{parent_sig}")
    return hashlib.sha256("|".join(sorted(edges)).encode("utf-8")).hexdigest()


def _asks_signature(asks: Iterable[AsksFor]) -> str:
    parts = []
    for a in asks:
        items = ",".join(f"{k}={_norm(v)}" for k, v in sorted(dict(a.filter).items()))
        parts.append(f"{a.kind.value}[{items}]")
    return "+".join(sorted(parts))


@dataclass(frozen=True)
class Bundle:
    """What one run produced, in the terms the assertions compare (design 17.4).

    Everything here is derived from registry queries, so a bundle is an account
    of rows rather than of prose. `registry` rides along for the adversarial
    checks, which read the graph itself; it is excluded from `as_dict` and from
    the digest, both of which must be stable and JSON-shaped.
    """
    case_id: str
    # (text, asks-for signature, tied to an issue node). The flag is the
    # structural exemption of design 17.4: a gap that belongs to no issue node
    # is one of the seven structural inputs EVERY engagement has, so its
    # wording is the same everywhere by construction and only the questions the
    # tree produced can be asked to diverge.
    questions: tuple[tuple[str, str, bool], ...] = ()
    evidence_requests: tuple[str, ...] = ()
    central_decision: str = ""
    stated_request: str = ""
    issue_hash: str = ""
    issue_shapes: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
    assignments: tuple[tuple[str, str], ...] = ()        # (method id, node shape)
    recommendations: tuple[str, ...] = ()
    workstreams: tuple[str, ...] = ()
    work_products: tuple[tuple[str, tuple[str, ...]], ...] = ()
    conflicts: tuple[str, ...] = ()                      # ConflictKind values
    regulated_domains: tuple[str, ...] = ()
    counts: Mapping[str, int] = field(default_factory=dict)
    revealed: tuple[int, ...] = ()
    revealed_changers: int = 0
    documents_offered: int = 0
    turns: int = 0
    analysis_rounds: int = 0
    model_calls: int = 0
    cost_usd: float = 0.0
    findings: tuple[str, ...] = ()
    blocking_findings: tuple[str, ...] = ()
    release_status: str = ""
    phase: str = ""
    registry_hash: str = ""
    integrity_status: str = ""
    seeded_root: bool = False
    refusals: tuple[str, ...] = ()
    registry: Any = field(default=None, compare=False, repr=False)

    def deliverable_set(self) -> frozenset[str]:
        return frozenset(pid for pid, _ in self.work_products)

    def section_signature(self) -> str:
        parts = [f"{pid}:{','.join(sections)}" for pid, sections in sorted(self.work_products)]
        return "|".join(parts)

    def question_texts(self, *, tied_only: bool = True) -> frozenset[str]:
        """The wording this engagement asked. Structural gaps are left out by
        default: they are the same seven holes in every engagement and the
        design exempts their phrasing."""
        return frozenset(text for text, _, tied in self.questions if tied or not tied_only)

    def as_dict(self) -> dict:
        out = {}
        for name, value in self.__dict__.items():
            if name == _RIDE_ALONG:
                continue
            out[name] = _jsonable(value)
        return out

    def digest(self) -> str:
        """The determinism check's subject: same case, same provider, same
        clock -> the same string twice."""
        return hashlib.sha256(
            json.dumps(self.as_dict(), sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    return str(value)


# =============================================================================
# 4. Running one case
# =============================================================================

def _clock() -> str:
    return FIXED_CLOCK


# The actor_ref every issue this harness writes carries. It is the marker the
# bundle reads to answer one question honestly: did the tree's root come out of
# the engine, or did the benchmark put it there? Nothing else in the engine may
# use it, so a row carrying it is the harness's by construction.
HARNESS_ROOT_ACTOR_REF = "benchmark:root_issue"


def _harness_seeded_root(registry: EngagementRegistry) -> bool:
    """True only if THIS harness supplied an issue node.

    Read off provenance rather than returned from the seeding call, because the
    question the assertions need answered is what is in the registry, not what
    the harness meant to do. A seed that was refused (an id collision, a failed
    admission rule) would leave a caller-set flag saying the root is the
    harness's when the tree has none at all.
    """
    return any(e.provenance.actor_ref == HARNESS_ROOT_ACTOR_REF
               for e in registry.query(Kind.ISSUE))


def _seed_root_issue(registry: EngagementRegistry, fanout: int) -> bool:
    """The fallback root, for a build whose charter did not open one.

    `select_methods` reads open ISSUE rows and the only writer of an ISSUE row
    is the `issue_tree` method, which is itself selected by an ISSUE row's
    shape. `partner.charter.seed_root_issue` is what breaks that circle on an
    approved charter; this stands behind it so a regression there shows up as
    one declared flag plus a failing assertion rather than as fifteen empty
    trees that still produce a bundle. It never fires on a healthy engine, and
    the fake-mode test pins that it does not.

    The id comes from `charter.root_issue_id`, imported rather than recomputed:
    the collision it dodges (a specialist's ScopedView cannot see the root, so
    its first child claims `ISS-1`) is the engine's reasoning, and two copies of
    it would drift apart the moment MAX_FANOUT moved.
    """
    if registry.live(Kind.ISSUE):
        return False
    decision = registry.central_decision()
    if decision is None:
        return False
    payload = IssuePayload(
        text=getattr(decision.payload, "statement", ""),
        interrogative=Interrogative.WHICH, target_kind=Kind.DECISION,
        parent_id=None, comparative=True, weight_to_parent=1.0,
        decisive_for=(decision.id,))
    registry.apply(Add(make_entity(
        kind=Kind.ISSUE, engagement_id=registry.engagement_id, payload=payload,
        provenance=Provenance(actor=Actor.PARTNER, actor_ref=HARNESS_ROOT_ACTOR_REF,
                              derived_from=(decision.id,)),
        confidence=Confidence(None), relevance=Relevance(decision.id, 1.0),
        relation=RelationToCentralDecision.DEFINES, status=Status.PROPOSED,
        entity_id=root_issue_id({"MAX_FANOUT": max(1, int(fanout))}))))
    return True


def outstanding(registry: EngagementRegistry, client: "SimulatedClient") -> list[Entity]:
    """Every open question the client is the one to answer and has not already
    been put. A turn's reply carries only the batch `ask()` wrote, but the
    engagement's live summary shows the client every open question - including
    the provenance questions ingestion opens directly - and a client who could
    answer one of those and was never asked would make the benchmark measure
    the reply's shape rather than the engagement's."""
    already = set(client.answered)
    return [q for q in registry.live(Kind.QUESTION)
            if q.status is Status.OPEN and q.payload.strategy in _ASKABLE
            and q.payload.unknown is not True and q.id not in already]


def _confirm_charter(partner: Partner, state: EngagementState, proposal, turn_id: str) -> bool:
    """The client signs what they were shown. Every listed item is confirmed by
    default (charter.confirm's own rule), which is the honest reading of a
    client who agreed: they were played back each item with its locator."""
    charter = proposal.charter if proposal is not None else None
    if charter is None:
        return False
    outcome = partner.confirm_charter(state, charter.id, turn_id=turn_id)
    return outcome.approved


def _bound(state: EngagementState, name: str) -> int:
    return int(state.bound(name))


def _live_texts(view, kind: Kind, attr: str) -> tuple[str, ...]:
    return tuple(str(getattr(e.payload, attr, "") or "") for e in view.live(kind))


def _counts(view) -> dict[str, int]:
    out: dict[str, int] = {}
    for kind in Kind:
        n = len(view.live(kind))
        if n:
            out[kind.value] = n
    return out


def run_case(loaded: LoadedCase, provider: ModelProvider, *,
             client_provider: ModelProvider | None = None,
             methods: MethodRegistry = METHODS,
             max_usd: float | None = None,
             model: str | None = None,
             bounds: Mapping[str, Any] | None = None) -> Bundle:
    """One case, end to end: discovery until the charter is confirmed, analysis
    with every pause answered by the client, synthesis, planning, the integrity
    record and the release verdict.

    Bounds, never counts: the discovery cap is MAX_DISCOVERY_TURNS and the
    analysis cap is MAX_ANALYSIS_ROUNDS, both read from this state's settings.
    """
    counted = CountingProvider(AnnotatedClassifier(provider, loaded), max_usd=max_usd)
    registry = EngagementRegistry(loaded.id, clock=_clock)
    state = EngagementState(registry=registry) if bounds is None else EngagementState(
        registry=registry, bounds=dict(BOUNDS, **bounds))
    partner = Partner(counted, methods=methods, model=model)
    client = SimulatedClient(loaded, provider=client_provider, model=model)

    refusals: list[str] = []
    max_turns = _bound(state, "MAX_DISCOVERY_TURNS")
    message: str = client.opening()
    attachments: list[tuple[str, bytes]] = []
    approved = False
    reply = None

    while state.turn_n < max_turns and not approved:
        reply = partner.turn(state, message, attachments)
        refusals.extend(reply.refusals)
        if reply.charter is not None:
            approved = _confirm_charter(partner, state, reply.charter, reply.turn_id)
            if approved:
                break
        asked = outstanding(registry, client)
        if not asked:
            break
        message, attachments = client.reply(asked)

    rounds = 0
    if approved:
        # A no-op on a healthy engine: the charter already opened the root. The
        # call stands so a build that stopped doing so still measures what is
        # downstream of a tree, with `Bundle.seeded_root` saying who supplied it.
        _seed_root_issue(registry, _bound(state, "MAX_FANOUT"))
        # Analysis and discovery interleave (design 6.7): a method input the
        # client can supply is a typed gap, gaps are asked in a turn, and the
        # answers are what makes the next round runnable. One iteration is one
        # client turn and one analysis pass, bounded by MAX_ANALYSIS_ROUNDS.
        pending: list[Entity] = outstanding(registry, client)
        for _ in range(_bound(state, "MAX_ANALYSIS_ROUNDS")):
            if state.phase is Phase.SYNTHESIS:
                break
            message, attachments = client.reply(pending)
            reply = partner.turn(state, message, attachments)
            refusals.extend(reply.refusals)
            pending = outstanding(registry, client)
            try:
                run = partner.run_analysis(state)
            except PhaseError as exc:
                refusals.append(f"analysis: {exc}")
                break
            rounds += run.rounds
            refusals.extend(run.refusals)
            pending = outstanding(registry, client)

        # The client answers the last batch. A question asked on the turn a run
        # ends is still a question the client was asked, and leaving it hanging
        # would credit the engine for asking while never testing whether the
        # answer was one the dossier could give - which is exactly what
        # MIN_REVEALED_CHANGERS measures. Bounded by the same discovery ceiling
        # as the opening, and stops as soon as a turn asks nothing new.
        while pending and state.turn_n < max_turns:
            message, attachments = client.reply(pending)
            reply = partner.turn(state, message, attachments)
            refusals.extend(reply.refusals)
            pending = outstanding(registry, client)

    # Synthesis: the four detection queries, then resolution, the decisions the
    # client owes, the conditions every recommendation carries, and the screen
    # over every live piece of advice.
    detect_conflicts(registry)
    reevaluate_materiality(registry)
    auto_resolve(registry)
    emit_decisions_required(registry)
    refresh_conditional_on(registry)
    try:
        screen = screen_synthesis(registry, counted)
        refusals.extend(f"regulated: {cid} cleared for {domain}" for cid, domain in screen.cleared)
    except Exception as exc:                                  # pragma: no cover - defensive
        refusals.append(f"regulated: {exc}")
    if state.phase is Phase.ANALYSIS:
        left = synthesis_blockers(registry, rounds_used=rounds, bounds=state.bounds, methods=methods)
        if not left:
            advance(state, Phase.SYNTHESIS, rounds_used=rounds, methods=methods)

    plan = plan_work_products(registry, bounds=state.settings_bounds())
    registry.apply_all(list(plan.deltas))

    findings = laws_mod.run_laws(registry, ())
    record = build_integrity_record(registry, unplanned=plan.unplanned, findings=findings)
    status = release_status(findings, approval=client_approval(registry))

    return Bundle(
        case_id=loaded.id,
        questions=tuple((q.payload.text, _asks_signature(q.payload.asks_for),
                         bool(q.payload.issue_ids))
                        for q in registry.live(Kind.QUESTION)),
        # What the engagement asked to be GIVEN, typed: every open question's
        # asks_for, of which a document request is one strategy. Kinds and
        # filters, never wording - two engagements that asked for the same
        # kinds of evidence asked the same thing however differently they
        # worded it.
        evidence_requests=tuple(sorted({
            _asks_signature(q.payload.asks_for) for q in registry.live(Kind.QUESTION)
            if q.payload.strategy in _ASKABLE})),
        central_decision=(registry.central_decision().payload.statement
                          if registry.central_decision() is not None else ""),
        stated_request=next((d.payload.statement for d in registry.live(Kind.DECISION)
                             if d.payload.role.value == "stated_request"), ""),
        issue_hash=issue_tree_hash(registry),
        issue_shapes=tuple(sorted(shape_signature(QuestionShape.of(i))
                                  for i in registry.live(Kind.ISSUE))),
        methods=tuple(sorted(a.payload.method_id for a in registry.live(Kind.ANALYSIS))),
        assignments=tuple(sorted(
            (a.payload.method_id,
             shape_signature(QuestionShape.of(registry.get(a.payload.issue_id)))
             if registry.get(a.payload.issue_id) is not None else "")
            for a in registry.live(Kind.SPECIALIST_ASSIGNMENT))),
        recommendations=tuple(sorted(_live_texts(registry, Kind.RECOMMENDATION, "statement"))),
        workstreams=tuple(sorted(_live_texts(registry, Kind.WORKSTREAM, "name"))),
        work_products=tuple(sorted((v.product_id, tuple(v.section_ids)) for v in plan.planned)),
        conflicts=tuple(sorted(c.payload.kind.value for c in registry.live(Kind.CONFLICT))),
        regulated_domains=tuple(sorted({m.payload.domain.value
                                        for m in registry.query(Kind.REGULATED_MATTER)
                                        if m.status is Status.ROUTED})),
        counts=_counts(registry),
        revealed=tuple(sorted(client.revealed)),
        revealed_changers=client.revealed_changers(),
        documents_offered=len(client.offered),
        turns=state.turn_n,
        analysis_rounds=rounds,
        model_calls=len(counted.calls),
        cost_usd=counted.cost_usd,
        findings=tuple(sorted(f"{f.law}:{f.where}" for f in findings)),
        blocking_findings=tuple(sorted(f"{f.law}:{f.where}" for f in laws_mod.blocking(findings))),
        release_status=str(status.get("status", "")),
        phase=state.phase.value,
        registry_hash=registry.content_hash(),
        integrity_status=str(record.get("status", "")),
        seeded_root=_harness_seeded_root(registry),
        refusals=tuple(refusals),
        registry=registry,
    )
