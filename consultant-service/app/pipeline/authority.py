"""Authority precedence — which source wins when two statements of one fact
disagree.

The canonical registry alone cannot settle every conflict. When a document
narrows the pilot population, nothing in the document says whether the
sentence or the gate is the wrong one; when two procedure sets describe one
workflow with different mechanics, nothing in the procedures says which set
staff should run. Without a precedence those conflicts have no determinate
answer, and the integrity layer can only fail closed on them forever.

This module states the precedence once, generically:

    population                     -> the pilot gate
    procedure steps                -> the canonical SOP
    outreach attempt counts        -> the canonical SOP
    entity names, ownership        -> the canonical registry

Everything here RENDERS an authoritative value into a place a lesser source
stated a conflicting one. The value always comes from the owning source, so
nothing is guessed, no wording is invented, and no similarity score decides
anything. A conflict between two sources that NEITHER owns is not settled
here: it still fails closed and the verifier reports it.
"""
from __future__ import annotations

import re

# the fact -> the source that owns it. Read by the renderers below and by the
# release record, so the precedence a package was corrected under is legible.
PRECEDENCE = {
    "pilot population": "pilot gate",
    "procedure steps": "canonical SOP",
    "outreach attempt count": "canonical SOP",
    "entity name": "canonical registry",
    "module ownership": "canonical registry",
}

# stand-in words an earlier architecture substituted for words it could not
# recognise. They are not narrower than the gate, so the population law never
# reports them, but they say nothing — where they scope the pilot they are
# rendered from the gate like any other conflicting population.
LEGACY_VAGUE = {"eligible", "applicable", "relevant", "qualifying"}

# a locative the gate's own population already carries ("… in the pilot
# geography"). Consumed with the qualifier so the rendered sentence does not
# state the geography twice — which would read as a second, narrower filter.
_LOCATIVE_TAIL = re.compile(
    r"^\s+(?:in|within|across|throughout)\s+(?:the\s+)?[\w\s-]{0,40}?"
    r"(?:region|geography|area|district|city|zone|market)\b\.?", re.IGNORECASE)
_PREPOSITION = re.compile(r"^(for|to|of|covering|limited to|only for|restricted to|scheduled for)\s+", re.IGNORECASE)


def _lower_first(s: str) -> str:
    return (s[0].lower() + s[1:]) if s else s


# ── the gate owns the pilot population ───────────────────────────────────────


def population_render(text: str, gate: dict | None, types: list[str] | None,
                      terms: list[str] | None = None, pilot_scope: bool = True) -> tuple[str, list[dict]]:
    """A pilot sentence states the gate's population, exactly.

    A qualifier that narrows the population to a service type the gate never
    named, or that stands in for it with a legacy vague word, is replaced by
    the gate's own population text. The preposition the sentence used is kept,
    so the sentence stays the sentence its author wrote."""
    from app.pipeline import pilot_gate as _pg
    from app.pipeline import registry as _reg

    records: list[dict] = []
    population = str((gate or {}).get("population") or "").strip().rstrip(".")
    if not text or not population:
        return text, records
    names = [n for n in (terms or []) if n]
    out_parts = []
    for chunk in re.split(r"(?<=[.!?])(\s+)", text):
        if not chunk or chunk.isspace():
            out_parts.append(chunk)
            continue
        if pilot_scope and not (re.search(r"\bpilot\b", chunk, re.IGNORECASE) or any(n in chunk for n in names)):
            out_parts.append(chunk)
            continue
        narrowing = set(_reg._narrowing_qualifiers(chunk, gate, types))
        fixed = chunk
        # right to left, so earlier offsets stay valid
        for m in list(_reg._POP_QUALIFIER.finditer(chunk))[::-1]:
            modifier = re.sub(r"\s+", " ", (m.group(1) or "")).strip().lower()
            if m.group(0) not in narrowing and modifier not in LEGACY_VAGUE:
                continue
            prep = _PREPOSITION.match(m.group(0))
            if not prep:
                continue
            start, end = m.start(), m.end()
            tail = _LOCATIVE_TAIL.match(chunk[end:])
            stop = end + (tail.end() if tail else 0)
            consumed = chunk[start:stop]
            rendered = f"{prep.group(1)} {_lower_first(population)}"
            fixed = (fixed[:start] + rendered + ("." if consumed.rstrip().endswith(".") else "") + fixed[stop:])
            records.append({"original": consumed.strip()[:140], "replaced_with": population,
                            "authority": PRECEDENCE["pilot population"]})
        out_parts.append(fixed)
    return "".join(out_parts), records


# ── the canonical SOP owns the pilot's procedures and its attempt count ──────


def dedupe_pilot_procedures(procedures: list, pilot_module_names: set[str]) -> tuple[list, list[dict]]:
    """The SOP is the pilot's only executable procedure set.

    A pilot-phase procedure filed under the pilot MODULE describes the same
    workflow the SOP already describes, with different mechanics; the reader
    cannot know which to run. The SOP set (filed under 'The pilot') is
    authoritative and the module-level duplicates are dropped. With no SOP set
    present nothing is dropped — there would be nothing left to run."""
    procs = [p for p in (procedures or []) if isinstance(p, dict)]
    pilot = [p for p in procs if str(p.get("phase") or "").lower() == "pilot"]
    sets = {str(p.get("module")) for p in pilot}
    duplicates = sets & set(pilot_module_names or ())
    if "The pilot" not in sets or not duplicates:
        return procedures, []
    drop = {id(p) for p in pilot if str(p.get("module")) in duplicates}
    records = [{"removed": str(p.get("name")), "filed_under": str(p.get("module")),
                "kept": "the pilot SOP", "authority": PRECEDENCE["procedure steps"]}
               for p in pilot if id(p) in drop]
    return [p for p in (procedures or []) if id(p) not in drop], records


def attempt_render(text: str, total: int | None, terms: list[str] | None = None) -> tuple[str, list[dict]]:
    """A pilot sentence that counts outreach attempts states the SOP's total.

    Only the reminder COUNT is rewritten, and only in a sentence that is about
    the pilot's outreach: the SOP's total counts the first message plus its
    reminders, so a sentence offering N reminders states total - 1."""
    from app.pipeline import registry as _reg

    records: list[dict] = []
    if not text or not total or total < 1:
        return text, records
    names = [n for n in (terms or []) if n]
    reminders = total - 1
    out_parts = []
    for chunk in re.split(r"(?<=[.!?])(\s+)", text):
        if not chunk or chunk.isspace():
            out_parts.append(chunk)
            continue
        stated = _reg._attempt_totals(chunk)
        if not stated or stated == {total} or not (
                re.search(r"\bpilot\b", chunk, re.IGNORECASE) or any(n in chunk for n in names)):
            out_parts.append(chunk)
            continue
        fixed = _REMINDER_COUNT.sub(
            lambda m: f"{m.group(1)} {_count_word(reminders, m.group(2))} {_plural(m.group(3), reminders)}", chunk)
        if fixed != chunk:
            records.append({"original": chunk.strip()[:140], "replaced_with": f"{total} attempts",
                            "authority": PRECEDENCE["outreach attempt count"]})
        out_parts.append(fixed)
    return "".join(out_parts), records


_NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
_REMINDER_COUNT = re.compile(r"\b(sends?|send|issues?|deliver(?:s)?)\s+(one|two|three|four|five|six|\d+)\s+"
                             r"(reminder|reminders|follow[- ]up|follow[- ]ups)\b", re.IGNORECASE)


def _count_word(n: int, like: str) -> str:
    """Match the form the sentence already used: a word stays a word."""
    if like.isdigit():
        return str(n)
    return _NUMBER_WORDS.get(n, str(n))


def _plural(noun: str, n: int) -> str:
    base = noun[:-1] if noun.lower().endswith("s") else noun
    return base if n == 1 else base + "s"


# ── the registry owns entity names ──────────────────────────────────────────


def coined_name_render(text: str, canon, where: str = "") -> tuple[str, list[dict]]:
    """A name-shaped span that denotes NO registry entity is never registered
    and never invented around.

    It resolves to the module structurally responsible for it — the one
    registry module its own sentence names. When its sentence names no single
    module, the coined name is removed and the function is described with the
    registry's own module names, in the registry's build order. A determiner
    and its adjectives are consumed with the name so the sentence stays
    grammatical ('a smart <coined>' -> 'the <modules>')."""
    from app.pipeline import canon as _canon
    from app.pipeline.integrity import _NAME_SPAN

    records: list[dict] = []
    if not text:
        return text, records
    module_names = sorted((e.canonical for e in canon.of_kind("module")), key=len, reverse=True)
    if not module_names:
        return text, records
    roster = _canon.phase_title(canon.build_order())
    out = text
    for chunk in sorted({m.group(1) for m in _NAME_SPAN.finditer(re.sub(r"\s+", " ", text))}, key=len, reverse=True):
        words = chunk.split()
        if len(words) < 3 or any(canon.resolve(" ".join(words[k:])).unique for k in range(len(words))):
            continue                                  # known, or too short to be a coined name
        for sentence in re.split(r"(?<=[.!?])\s+", out):
            if chunk not in sentence:
                continue
            named = [n for n in module_names if n in sentence]
            replacement = named[0] if len(named) == 1 else roster
            pattern = re.compile(r"(?:\b(?:a|an|the)\s+(?:[a-z]+\s+){0,2})?" + re.escape(chunk))
            fixed = pattern.sub("the " + replacement, sentence, count=1)
            if fixed != sentence:
                out = out.replace(sentence, fixed, 1)
                records.append({"original": chunk, "replaced_with": replacement,
                                "resolved_by": "the one module its sentence names" if len(named) == 1
                                               else "the registry's module names, in build order",
                                "authority": PRECEDENCE["entity name"], "where": where})
            break
    return out, records
