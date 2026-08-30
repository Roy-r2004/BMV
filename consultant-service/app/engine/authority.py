"""app/engine/authority.py - who owns what, and who may advance a status.

Adopted verbatim from contracts.py section 5. Authority is a function of the
information type (spec section 5), never of who happened to produce a row:
AUTHORITY_OF maps InfoType -> Authority; MAY_CONFIRM, APPROVAL_OWNER and
MAY_RESOLVE say which Actor may move an entity to CONFIRMED / APPROVED /
RESOLVED; may_advance() is invariant I1 as one function the registry calls;
precedence_rank() orders sources of one current-state fact.

APPROVED has its own table (MF2.2) because confirming a consultant judgement
is not approving a recommendation: a PARTNER may confirm what a method wrote
and still never approve it.
"""
from __future__ import annotations

from typing import Mapping

from app.engine.types import (
    CURRENT_STATE_PRECEDENCE, Actor, Authority, Entity, FactBasis, InfoType, Kind, RecordClass, Status,
)


# The authority table of spec section 5, as data. Derived from information type only.
AUTHORITY_OF: Mapping[InfoType, Authority] = {
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
assert set(AUTHORITY_OF) == set(InfoType)


def owner_of(info_type: InfoType) -> Authority:
    return AUTHORITY_OF[info_type]


# who may CONFIRM (or RESOLVE) something owned by each authority
MAY_CONFIRM: Mapping[Authority, frozenset[Actor]] = {
    Authority.CLIENT: frozenset({Actor.CLIENT}),
    Authority.CLIENT_STATED: frozenset({Actor.CLIENT}),
    Authority.VERIFIED_RECORD: frozenset({Actor.DOCUMENT, Actor.CALCULATOR}),
    Authority.CITED_SOURCE: frozenset({Actor.EXTERNAL_SOURCE}),
    Authority.DETERMINISTIC_ENGINE: frozenset({Actor.CALCULATOR}),
    Authority.CONSULTANT: frozenset({Actor.PARTNER, Actor.METHOD}),
    Authority.QUALIFIED_PROFESSIONAL: frozenset({Actor.QUALIFIED_PROFESSIONAL}),
    Authority.DECISION_OWNER: frozenset({Actor.DECISION_OWNER}),
    Authority.PARTNER: frozenset({Actor.PARTNER, Actor.SYSTEM}),
}
assert set(MAY_CONFIRM) == set(Authority)

# APPROVED has its own table (MF2.2): confirming a consultant judgement is not
# approving a recommendation. Keyed by kind; kinds absent here cannot be APPROVED.
APPROVAL_OWNER: Mapping[Kind, frozenset[Actor]] = {
    Kind.RECOMMENDATION: frozenset({Actor.DECISION_OWNER, Actor.CLIENT}),
    Kind.ASSUMPTION: frozenset({Actor.CLIENT}),
    Kind.CHARTER: frozenset({Actor.CLIENT}),
}

# who may open/close process statuses
MAY_RESOLVE: Mapping[Kind, frozenset[Actor]] = {
    Kind.QUESTION: frozenset({Actor.CLIENT, Actor.PARTNER, Actor.SYSTEM}),
    Kind.DECISION_REQUIRED: frozenset({Actor.CLIENT, Actor.DECISION_OWNER, Actor.QUALIFIED_PROFESSIONAL}),
    Kind.REGULATED_MATTER: frozenset({Actor.QUALIFIED_PROFESSIONAL}),
}


def may_advance(entity: Entity, status: Status, actor: Actor) -> bool:
    """I1. Whether `actor` may move `entity` to `status`.

    CONFIRMED  -> MAY_CONFIRM[entity.authority]
    APPROVED   -> APPROVAL_OWNER[entity.kind] (absent kind: never)
    RESOLVED   -> CONFLICT: MAY_CONFIRM[conflict.authority_required]; QUESTION / DECISION_REQUIRED /
                  REGULATED_MATTER: MAY_RESOLVE[kind]
    ROUTED     -> REGULATED_MATTER only, by SYSTEM or PARTNER (I4: routing happens inside the engine)
    REJECTED / WITHDRAWN -> the creator's actor or the owning authority's confirmers
    """
    if status == Status.CONFIRMED:
        return actor in MAY_CONFIRM[entity.authority]
    if status == Status.APPROVED:
        return actor in APPROVAL_OWNER.get(entity.kind, frozenset())
    if status == Status.RESOLVED:
        if entity.kind == Kind.CONFLICT:
            return actor in MAY_CONFIRM[entity.payload.authority_required]
        if entity.kind == Kind.DECISION_REQUIRED:
            return actor in MAY_CONFIRM[entity.payload.from_authority] or actor in MAY_RESOLVE[Kind.DECISION_REQUIRED]
        return actor in MAY_RESOLVE.get(entity.kind, frozenset())
    if status == Status.ROUTED:
        return entity.kind == Kind.REGULATED_MATTER and actor in (Actor.SYSTEM, Actor.PARTNER)
    if status in (Status.REJECTED, Status.WITHDRAWN):
        return actor == entity.provenance.actor or actor in MAY_CONFIRM[entity.authority] \
            or actor in APPROVAL_OWNER.get(entity.kind, frozenset())
    if status == Status.OPEN:
        return actor in (Actor.PARTNER, Actor.SYSTEM, Actor.METHOD, Actor.SPECIALIST)
    return False


def precedence_rank(fact: Entity, registry: "RegistryView") -> int | None:
    """Position in CURRENT_STATE_PRECEDENCE (0 = strongest). None when the fact
    is not a current-state fact or its record class is unknown."""
    p = fact.payload
    if fact.kind != Kind.FACT:
        return None
    if p.basis == FactBasis.CLIENT_STATED:
        return CURRENT_STATE_PRECEDENCE.index("client_stated")
    if p.basis == FactBasis.INFERRED:
        return CURRENT_STATE_PRECEDENCE.index("inferred")
    if p.basis == FactBasis.DOCUMENT_VERIFIED and p.record_class not in (None, RecordClass.UNKNOWN):
        key = f"document_verified:{p.record_class.value}"
        return CURRENT_STATE_PRECEDENCE.index(key) if key in CURRENT_STATE_PRECEDENCE else None
    return None


def resolution_authority(conflict: Entity) -> Authority:
    """The authority a CONFLICT names as required to resolve it. Read from the
    typed payload, never inferred from the conclusions' producers."""
    if conflict.kind != Kind.CONFLICT:
        raise TypeError(f"resolution_authority expects a CONFLICT, got {conflict.kind.value}")
    return conflict.payload.authority_required


__all__ = [n for n in dir() if not n.startswith("_")]
