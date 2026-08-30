"""The only module in the engine that rewrites rendered text (S15, design 11.3).

It does exactly two things, and both are exact:

  C1  token substitution - a `[[STMT:STA-n]]` token is replaced by the one
      string its STATEMENT entity holds. The substitution is a literal
      `str.replace`; there is no pattern, no group reference and no escaping,
      so a canonical sentence containing a backslash, a dollar sign or an
      ampersand lands on the page exactly as the registry holds it. A regex
      rewrite here would be a second, silent way for text to change - which
      is why this module imports no regex engine at all and a test asserts it
  C2  Canon.apply_exact_mappings (app/pipeline/canon.py:350) - a surface form
      that denotes EXACTLY ONE registered named entity becomes that entity's
      canonical form. Ambiguous or unknown surfaces are left alone and
      reported; nothing is guessed

and one thing it refuses to do:

  C3  MF2.6 - before any mapping runs, every client-fact span is masked (the
      canon.mask_entities pattern, canon.py:337) and restored afterwards, so
      a canonical mapping can never rewrite a word inside the client's own
      quoted sentence. L14 checks the same property on the extracted page;
      this is the mechanism that makes L14 pass rather than a second check

Every application - token or mapping - is recorded as a lineage record
{where, entity, law, before, after}. The release record's
`corrections_current_pass.applied` is exactly this list, so a client can ask
what was changed in their document and get a complete answer.

Prose is never patched: a narrative that fails its checks is regenerated once
and then replaced by a statement list (render_md), never edited into shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

# canon is imported, never modified: this engine borrows r30's exact-mapping
# machinery rather than growing a second one.
from app.pipeline.canon import Canon, Mapping as CanonMapping


LAW_TOKEN = "corrections.token_substitution"
LAW_CANON = "corrections.exact_canonical_mapping"

# A masked client-fact span. NUL cannot occur in rendered text (it is what a
# missing glyph extracts as, and the presentation gate fails on it), so a
# placeholder built from NUL can never collide with content, and it carries no
# word character for the canon scanner's word boundaries to catch on.
_MASK_OPEN = "\x00CF"
_MASK_CLOSE = "\x00"


@dataclass(frozen=True)
class MappingRecord:
    """One applied correction. `law` names which of the two permitted
    corrections it was, so an auditor never has to infer it."""
    where: str
    entity: str
    law: str
    before: str
    after: str

    def as_dict(self) -> dict:
        return {"where": self.where, "entity": self.entity, "law": self.law,
                "before": self.before, "after": self.after}


@dataclass(frozen=True)
class Correction:
    text: str
    applied: tuple[MappingRecord, ...]
    unresolved_tokens: tuple[str, ...] = ()


def _placeholder(index: int) -> str:
    return f"{_MASK_OPEN}{index}{_MASK_CLOSE}"


def substitute_tokens(text: str, tokens: Mapping[str, str], *, where: str = "") -> tuple[str, list[MappingRecord]]:
    """C1. Replace every statement token with the exact text it stands for.

    Longest token first so no token is a prefix of another; literal replace,
    never a pattern - the replacement is data from the registry and must not
    be read as a template."""
    out = text or ""
    applied: list[MappingRecord] = []
    for token in sorted(tokens, key=lambda t: (-len(t), t)):
        canonical = tokens[token]
        count = out.count(token)
        if count == 0:
            continue
        out = out.replace(token, canonical)
        for _ in range(count):
            applied.append(MappingRecord(where=where, entity=token, law=LAW_TOKEN,
                                         before=token, after=canonical))
    return out, applied


def unresolved_tokens(text: str) -> tuple[str, ...]:
    """Tokens still on the page after substitution. A token that reached the
    reader is a claim that lost its wording, which is a blocking defect, not a
    cosmetic one - so it is reported rather than deleted."""
    from app.engine.work_products.statements import TOKEN_CLOSE, TOKEN_OPEN

    out: list[str] = []
    rest = text or ""
    while True:
        start = rest.find(TOKEN_OPEN)
        if start < 0:
            break
        end = rest.find(TOKEN_CLOSE, start)
        if end < 0:
            break
        out.append(rest[start:end + len(TOKEN_CLOSE)])
        rest = rest[end + len(TOKEN_CLOSE):]
    return tuple(out)


def mask_client_facts(text: str, spans: Sequence[str]) -> tuple[str, list[tuple[str, str]]]:
    """C3. Replace every client-fact span with a placeholder, longest first so
    a quote nested inside a longer quote is masked once, as part of the longer
    one. Returns the masked text and the restorations, in application order."""
    out = text or ""
    slots: list[tuple[str, str]] = []
    for i, span in enumerate(sorted({s for s in spans if s}, key=lambda s: (-len(s), s))):
        if span not in out:
            continue
        placeholder = _placeholder(i)
        out = out.replace(span, placeholder)
        slots.append((placeholder, span))
    return out, slots


def _restore(text: str, slots: Iterable[tuple[str, str]]) -> str:
    out = text
    for placeholder, span in slots:
        out = out.replace(placeholder, span)
    return out


def apply_mappings(text: str, canon: Canon | None, *, protected: Sequence[str] = (),
                   where: str = "") -> tuple[str, list[MappingRecord]]:
    """C2 with C3. Exact canonical mappings over everything the client did not
    say, and nothing at all inside what they did."""
    if canon is None or not text:
        return text or "", []
    masked, slots = mask_client_facts(text, protected)
    mapped, applied = canon.apply_exact_mappings(masked, where)
    return _restore(mapped, slots), [_record(m, where) for m in applied]


def _record(m: CanonMapping, where: str) -> MappingRecord:
    return MappingRecord(where=where or m.where, entity=m.entity_id, law=LAW_CANON,
                         before=m.surface, after=m.canonical)


def correct(text: str, *, tokens: Mapping[str, str] | None = None, canon: Canon | None = None,
            protected: Sequence[str] = (), where: str = "") -> Correction:
    """The whole of what may happen to rendered text: tokens in, exact
    canonical names in, everything else untouched."""
    out, applied = substitute_tokens(text, tokens or {}, where=where)
    out, mapped = apply_mappings(out, canon, protected=protected, where=where)
    return Correction(text=out, applied=tuple(applied + mapped), unresolved_tokens=unresolved_tokens(out))
