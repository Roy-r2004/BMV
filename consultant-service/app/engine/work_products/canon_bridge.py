"""Engine named entities -> canon.Entity kinds (S14, design 11.3).

The engine has 41 kinds; r30's canon has 12, and only six of those
(canon.NAMED_KINDS, canon.py:28) are NAMES that may be resolved from prose.
This module is the whole of the translation, and it is a closed table:

  B1  a kind not in CANON_KIND_OF contributes nothing. There is no default
      kind and no fallback: canon.Entity refuses an unknown kind
      (canon.py:44-46) and this table refuses to invent one
  B2  a CAPABILITY is a canon `interface` only when its capability_class is
      SOFTWARE_SYSTEM - a process capability is not a named system, and
      registering it as one would let ordinary process wording be rewritten
  B3  only a NAME is registered, never a statement. A sentence resolved from
      prose is how a mapping stops being exact: r30 draws the same line by
      indexing only NAMED_KINDS, and MAX_NAME_WORDS draws it on this side

Surface forms come from canon.name_surfaces (canon.py:237), which derives
only the forms a writer produces by dropping an inner or a leading acronym
word - never a similarity match. Two entities that share a name make that
name ambiguous, and an ambiguous surface is reported, never rewritten
(Canon.apply_exact_mappings). Fail closed: fewer mappings, never a guess.
"""
from __future__ import annotations

from typing import Callable, Mapping, TYPE_CHECKING

from app.pipeline.canon import Canon, Entity as CanonEntity, name_surfaces

from app.engine.types import TERMINAL_STATUSES, CapabilityClass, Entity, Kind

if TYPE_CHECKING:
    from app.engine.registry import RegistryView


# Engine kind -> canon kind (canon.KINDS, canon.py:24). Keys are enum members,
# never strings, so this table cannot smuggle in a branch on prose.
CANON_KIND_OF: Mapping[Kind, str] = {
    Kind.OWNER: "actor",
    Kind.STAKEHOLDER: "actor",
    Kind.DECISION_OWNER: "actor",
    Kind.WORKSTREAM: "module",
    Kind.INITIATIVE: "module",
    Kind.CAPABILITY: "interface",
    Kind.MEASURE: "concept",
}

# B2: the admission a kind must also pass. Absent means "always admitted".
ADMITS: Mapping[Kind, Callable[[Entity], bool]] = {
    Kind.CAPABILITY: lambda e: e.payload.capability_class is CapabilityClass.SOFTWARE_SYSTEM,
}

# B3: a name is a name. Beyond this a string is a statement, and a statement is
# addressed by its entity id, never resolved out of prose. The bound is a
# property of names, not a count of anything an engagement has.
MAX_NAME_WORDS = 8

# Named, not written into the branch: the whitelist AST law (design 18) admits
# no string constant inside a branch test anywhere under app/engine.
_LINE_BREAK = "\n"
_SENTENCE_END = "."


def is_name(text: str | None) -> bool:
    if text is None:
        return False
    name = text.strip()
    if not name or _LINE_BREAK in name or name.endswith(_SENTENCE_END):
        return False
    return len(name.split()) <= MAX_NAME_WORDS


def _name_of(e: Entity) -> str | None:
    """The entity's own name. `name` when the payload has one, else `text`
    (a CAPABILITY names itself there); nothing is derived or humanised."""
    for field_name in ("name", "text"):
        value = getattr(e.payload, field_name, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def canon_entities(view: "RegistryView") -> list[CanonEntity]:
    """Every live engine entity this table admits, as a canon.Entity, in
    entity-id order so the built Canon is identical for identical registries."""
    out: list[CanonEntity] = []
    for e in sorted(view.query(), key=lambda x: x.id):
        if e.status in TERMINAL_STATUSES:
            continue
        kind = CANON_KIND_OF.get(e.kind)
        if kind is None:
            continue
        if not ADMITS.get(e.kind, lambda _e: True)(e):
            continue
        name = _name_of(e)
        if not is_name(name):
            continue
        out.append(CanonEntity(id=e.id, kind=kind, canonical=name, surfaces=name_surfaces(name)))
    return out


def build_canon(view: "RegistryView") -> Canon:
    """The registry's named entities as r30's canonical registry. This is the
    only Canon the engine's corrections module is allowed to apply."""
    return Canon(canon_entities(view))
