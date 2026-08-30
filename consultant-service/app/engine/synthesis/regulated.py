"""app/engine/synthesis/regulated.py - the regulated screen (design 9.6).

Regulated or licensed advice is identified and routed for qualified review
rather than invented (spec section 7). The screen is a two-stage classifier
over every RECOMMENDATION, OPTION, ACTION and QUESTION candidate:

  stage 1 (regulated_classifier.j2) claims a RegulatedDomain for a candidate,
          or none. It is deliberately generous: a claim costs one verifier
          call, a miss costs the client licensed advice invented by a model.
  stage 2 (regulated_verifier.j2) tries to refute each claim, and may clear
          it ONLY with the literal CLEAR_VERDICT ("not_licensed"). Anything
          else - a synonym, a hedge, a paragraph, a schema failure, a
          provider outage - keeps the matter regulated. This inverts
          app/pipeline/defect_check.py:166-175, where the literal word
          REFUTED clears a defect claim: there over-flagging was the cheap
          direction; here under-routing is the dangerous direction and is
          closed. Over-routing is measured only on real runs (design 21).

A claim that stands becomes a REGULATED_MATTER row: domain, adviser_class
(a licensed profession derived from the domain, never chosen by the model),
why_regulated, the exact interpretation the engine refused to state
(withheld_interpretation, S11) and the constant CANNOT_ANSWER_STATEMENT.
The matter is born PROPOSED and then ROUTED by Actor.SYSTEM in a second,
visible transition (I4: routing happens inside the engine; the lineage shows
the matter existed before it was handed on). A touched RECOMMENDATION is
superseded with licensed_interpretation=True, which moves its information
type to LICENSED_INTERPRETATION (owner QUALIFIED_PROFESSIONAL): the registry
then refuses APPROVED/CONFIRMED on it (I4) and renderers list it under
"decisions required from advisers", never as a recommendation.

The screen runs unconditionally - at ingestion over the new candidates, at
synthesis over every live candidate of the four kinds. It is NOT bound to
the issue tree: a regulated matter can arrive in a wording no issue node
predicted, and a screen that only ran when some issue looked regulated
would be the under-routing hole the two stages exist to close.

The screen reads candidate wording to SHOW it to the model, never to select
on it: which entities are screened is decided by Kind alone, so no prose
filter (the way an engagement type would creep in) can be constructed here.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Mapping, Sequence

from pydantic import BaseModel

from app.engine.llm import ModelCall, ModelProvider, StructuredFailure, structured_call
from app.engine.registry import EngagementRegistry
from app.engine.templating import CLEAR_VERDICT, render
from app.engine.types import (
    Actor, Add, Confidence, Entity, Kind, Provenance, RegulatedDomain,
    RegulatedMatterPayload, SetStatus, Status, Supersede, TERMINAL_STATUSES, make_entity,
)

# The kinds the screen looks at: everything that words advice or asks the
# client to act or answer. A closed Kind list, never a text filter.
SCREEN_KINDS: tuple[Kind, ...] = (Kind.RECOMMENDATION, Kind.OPTION, Kind.ACTION, Kind.QUESTION)

CLASSIFIER_PURPOSE = "regulated_classifier"
VERIFIER_PURPOSE = "regulated_verifier"

# Who the screen writes as: routing is the engine's own recorded act (I4),
# not the partner's judgement and not a model's claim.
_ACTOR_REF = "regulated_screen"

# The licensed profession per domain. Derived from the enum, asserted total,
# so the model can never invent an adviser and a new domain cannot ship
# without naming who answers it. Professions, not engagement vocabulary.
ADVISER_CLASS: Mapping[RegulatedDomain, str] = {
    RegulatedDomain.LEGAL_CONTRACT: "contracts solicitor",
    RegulatedDomain.EMPLOYMENT_LAW: "employment lawyer",
    RegulatedDomain.TAX: "tax adviser",
    RegulatedDomain.FINANCIAL_REGULATION: "authorised financial adviser",
    RegulatedDomain.MEDICAL: "licensed medical practitioner",
    RegulatedDomain.DATA_PROTECTION: "data protection counsel",
    RegulatedDomain.ENVIRONMENTAL_PERMITTING: "environmental permitting adviser",
    RegulatedDomain.LICENSING_AND_CERTIFICATION: "licensing and certification adviser",
    RegulatedDomain.COMPANY_LAW_AND_GOVERNANCE: "corporate counsel",
    RegulatedDomain.COMPETITION_AND_TRADE: "competition and trade counsel",
}
assert set(ADVISER_CLASS) == set(RegulatedDomain), "every regulated domain names its adviser"


# -- model output shapes ------------------------------------------------------
# Validation raises, never constructs (llm._validate): a claim the model did
# not make cannot appear, and a malformed reply goes through the one retry
# and then StructuredFailure - which, at stage 2, keeps the matter regulated.

class _Claim(BaseModel):
    entity_id: str
    domain: str
    trigger: str = ""
    reason: str = ""


class _Claims(BaseModel):
    claims: list[_Claim] = []


class _Verdict(BaseModel):
    entity_id: str
    verdict: str
    reason: str = ""
    cited_ids: list[str] = []


@dataclass(frozen=True)
class ScreenResult:
    """What one run of the screen did, for the caller's reply and lineage."""
    matters: tuple[Entity, ...]                 # REGULATED_MATTER rows, already ROUTED
    flagged: tuple[str, ...]                    # RECOMMENDATION ids now licensed_interpretation=True
    cleared: tuple[tuple[str, str], ...]        # (candidate id, domain) claims the literal refuted


def _wording(e: Entity) -> str:
    """The candidate's words, for display in the prompts only. Selection
    never reads this - candidates are chosen by Kind above."""
    for name in ("statement", "text"):
        v = getattr(e.payload, name, None)
        if isinstance(v, str) and v:
            return v
    return ""


def _as_row(e: Entity) -> dict:
    return {"id": e.id, "kind": e.kind.value, "text": _wording(e)}


def _context_rows(registry: EngagementRegistry, cand: Entity) -> list[dict]:
    """The entities the verifier may cite: the candidate itself plus what it
    was derived from and what it rests on - the evidence trail, not the whole
    registry, so a verdict cannot lean on material the candidate never used."""
    ids = list(cand.provenance.derived_from)
    ids += list(getattr(cand.payload, "supports", ()) or ())
    ids += list(getattr(cand.payload, "evidence", ()) or ())
    rows = [_as_row(cand)]
    seen = {cand.id}
    for i in ids:
        if i in seen:
            continue
        seen.add(i)
        e = registry.get(i)
        if e is not None and e.status not in TERMINAL_STATUSES:
            rows.append(_as_row(e))
    return rows


def _classify(provider: ModelProvider, engagement_id: str, cands: Sequence[Entity]) -> list[_Claim]:
    """Stage 1. A StructuredFailure here propagates: with no claims there is
    nothing to keep regulated, and returning an empty result would be the
    silent under-routing this module exists to prevent. The caller sees the
    screen did not run; it never sees 'nothing found'."""
    prompt = render("regulated_classifier.j2", candidates=[_as_row(c) for c in cands])
    call = ModelCall(purpose=CLASSIFIER_PURPOSE, messages=({"role": "user", "content": prompt},),
                     engagement_id=engagement_id)
    claims, _ = structured_call(provider, call, _Claims)
    return list(claims.claims)


def _verify(provider: ModelProvider, engagement_id: str, claim: Mapping[str, str],
            entities: Sequence[Mapping[str, str]]) -> tuple[bool, str | None, str]:
    """Stage 2. Returns (cleared, model_call_id, note). Cleared is True only
    for the literal CLEAR_VERDICT on the claimed candidate."""
    prompt = render("regulated_verifier.j2", claim=claim, entities=entities)
    call = ModelCall(purpose=VERIFIER_PURPOSE, messages=({"role": "user", "content": prompt},),
                     engagement_id=engagement_id)
    try:
        verdict, resp = structured_call(provider, call, _Verdict)
    except StructuredFailure:
        # The outage branch: a provider error or unparseable reply is not a
        # refutation. The claim stands and the matter is routed, because an
        # outage that silently un-regulated a matter would let the engine
        # state licensed advice exactly when its checker was down.
        return False, None, "verifier unavailable; kept regulated"
    # One literal word decides. Equality, not membership: "probably
    # not licensed", "not_licensed in most cases" and every other hedge is
    # uncertainty, and uncertainty routes. A verdict about a different
    # candidate clears nothing either.
    cleared = verdict.entity_id == claim["entity_id"] and verdict.verdict == CLEAR_VERDICT
    return cleared, resp.call_id, verdict.reason


def _admitted_claims(claims: Iterable[_Claim], by_id: Mapping[str, Entity],
                     registry: EngagementRegistry) -> list[tuple[Entity, _Claim, RegulatedDomain]]:
    """Drop what the closed vocabulary refuses: a claim on an id that was not
    a candidate, a domain outside the enum (the prompt says so: anything else
    is dropped), a duplicate (candidate, domain) pair, and a pair an existing
    live matter already covers - the screen re-runs every round and must not
    stack duplicate matters on one wording."""
    covered: set[tuple[str, str]] = set()
    for m in registry.query(Kind.REGULATED_MATTER):
        if m.status in TERMINAL_STATUSES:
            continue
        for t in m.payload.touches:
            covered.add((t, m.payload.domain.value))
    out: list[tuple[Entity, _Claim, RegulatedDomain]] = []
    for c in claims:
        cand = by_id.get(c.entity_id)
        if cand is None:
            continue
        try:
            domain = RegulatedDomain(c.domain)
        except ValueError:
            continue
        key = (cand.id, domain.value)
        if key in covered:
            continue
        covered.add(key)
        out.append((cand, c, domain))
    return out


def _route_matter(registry: EngagementRegistry, cand: Entity, claim: _Claim,
                  domain: RegulatedDomain, model_call_id: str | None, note: str) -> Entity:
    """Write the matter and route it, two visible rows: born PROPOSED (I4: a
    matter is born unresolved), then ROUTED by SYSTEM - the lineage records
    that the engine identified it and handed it on, and who did the handing."""
    why = " - ".join(p for p in (claim.trigger, claim.reason) if p) or note
    payload = RegulatedMatterPayload(
        text=_wording(cand),
        domain=domain,
        adviser_class=ADVISER_CLASS[domain],
        why_regulated=why,
        touches=(cand.id,),
        # The exact interpretation the engine refused to state (S11): the
        # candidate's own wording, recorded so the adviser sees precisely
        # what was withheld, not a paraphrase of it.
        withheld_interpretation=_wording(cand),
    )
    row = registry.apply(Add(make_entity(
        kind=Kind.REGULATED_MATTER, engagement_id=registry.engagement_id, payload=payload,
        provenance=Provenance(actor=Actor.SYSTEM, actor_ref=_ACTOR_REF,
                              derived_from=(cand.id,), model_call_id=model_call_id),
        confidence=Confidence(None), relevance=cand.relevance, relation=cand.relation,
        status=Status.PROPOSED)))
    return registry.apply(SetStatus(row.id, Status.ROUTED,
                                    by=Provenance(actor=Actor.SYSTEM, actor_ref=_ACTOR_REF)))


def _flag_recommendation(registry: EngagementRegistry, rec_id: str, matter_ids: tuple[str, ...]) -> Entity:
    """Supersede the touched recommendation with licensed_interpretation=True.
    make_entity re-derives its information type (LICENSED_INTERPRETATION,
    owner QUALIFIED_PROFESSIONAL), so from this row on the registry itself
    refuses APPROVED and CONFIRMED (I4) - the block lives at the door, not in
    a renderer's goodwill. The new row is PROPOSED whatever the old status
    was: an approval granted before the flag was known does not survive the
    discovery that the advice needs a licence."""
    old = registry.get(rec_id)
    assert old is not None and old.kind == Kind.RECOMMENDATION
    new = make_entity(
        kind=Kind.RECOMMENDATION, engagement_id=registry.engagement_id,
        payload=replace(old.payload, licensed_interpretation=True),
        provenance=Provenance(actor=Actor.SYSTEM, actor_ref=_ACTOR_REF,
                              derived_from=tuple(dict.fromkeys(old.provenance.derived_from + matter_ids)),
                              source_locator=old.provenance.source_locator,
                              model_call_id=old.provenance.model_call_id),
        confidence=old.confidence, relevance=old.relevance, relation=old.relation,
        status=Status.PROPOSED, entity_id=old.id, labels=old.labels)
    return registry.apply(Supersede(old.id, new))


def _screen(registry: EngagementRegistry, provider: ModelProvider,
            candidates: Sequence[Entity]) -> ScreenResult:
    cands = [e for e in candidates if e.kind in SCREEN_KINDS and e.status not in TERMINAL_STATUSES]
    if not cands:
        return ScreenResult((), (), ())
    by_id = {e.id: e for e in cands}
    claims = _classify(provider, registry.engagement_id, cands)
    matters: list[Entity] = []
    cleared: list[tuple[str, str]] = []
    touched_recs: dict[str, list[str]] = {}
    for cand, claim, domain in _admitted_claims(claims, by_id, registry):
        claim_ctx = {"entity_id": cand.id, "kind": cand.kind.value, "text": _wording(cand),
                     "domain": domain.value, "trigger": claim.trigger, "reason": claim.reason}
        ok, call_id, note = _verify(provider, registry.engagement_id, claim_ctx,
                                    _context_rows(registry, cand))
        if ok:
            cleared.append((cand.id, domain.value))
            continue
        matter = _route_matter(registry, cand, claim, domain, call_id, note)
        matters.append(matter)
        if cand.kind == Kind.RECOMMENDATION:
            touched_recs.setdefault(cand.id, []).append(matter.id)
    flagged: list[str] = []
    for rec_id, matter_ids in touched_recs.items():
        rec = registry.get(rec_id)
        # "is False", never falsily (owner contract): a row an older writer
        # left with the flag unset is flagged now; a row some future shape
        # leaves as None is left for a human, not silently rewritten.
        if rec is not None and rec.payload.licensed_interpretation is False:
            _flag_recommendation(registry, rec_id, tuple(matter_ids))
            flagged.append(rec_id)
    return ScreenResult(tuple(matters), tuple(flagged), tuple(cleared))


def screen_candidates(registry: EngagementRegistry, provider: ModelProvider,
                      candidates: Iterable[Entity]) -> ScreenResult:
    """Ingestion-time screen: run over the candidates just written, before
    they are worded back to the client. Non-screen kinds pass through
    untouched; the screen decides by Kind, never by wording."""
    return _screen(registry, provider, list(candidates))


def screen_synthesis(registry: EngagementRegistry, provider: ModelProvider) -> ScreenResult:
    """Synthesis-time screen: every live RECOMMENDATION, OPTION, ACTION and
    QUESTION, unconditionally. Deliberately NOT bound to the issue tree: no
    issue node has to look regulated for the screen to run, because the
    dangerous wording is exactly the one nothing predicted."""
    cands: list[Entity] = []
    for kind in SCREEN_KINDS:
        cands.extend(registry.live(kind))
    return _screen(registry, provider, cands)


__all__ = ["ScreenResult", "SCREEN_KINDS", "ADVISER_CLASS", "CLASSIFIER_PURPOSE",
           "VERIFIER_PURPOSE", "screen_candidates", "screen_synthesis"]
