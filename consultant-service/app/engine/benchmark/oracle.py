"""app/engine/benchmark/oracle.py - the structural oracle (design 17.5).

`FakeProvider(oracle=structural_oracle)` answers every model call in a fake-mode
benchmark run. The rules below derive their answers from ONE place: the text of
the call they were handed. They read the prompt's own rendered data - the turn
between its triple quotes, the entity rows the template printed as
`- <id> [<kind>]: <wording>`, the closed vocabularies the template rendered from
the enums, the bounds it printed in its rules - and nothing else. There is no
case id, no dossier, no per-case script and no import of `cases` here.

That is the whole point. If the oracle knew which case it was answering, the
divergence assertions would be measuring the oracle, and a benchmark that
measures its own fixture proves nothing. Because it cannot know, every
difference between two fake bundles is a difference the deterministic core
produced from different inputs.

What the oracle is NOT: a judge of prose. It cannot tell a good question from a
bad one, a real regulated matter from an imagined one, or an insight from a
restatement. Under the fake it claims no regulated domain at all and it clears
none - the safe direction in both cases (design 9.6: under-routing is the
dangerous one, so the harness scripts that purpose from the case's typed
annotations, and real runs are the only evidence about classification).

Two properties everything here maintains:

  * every quote is a verbatim, contiguous span of the text the prompt showed.
    The registry refuses a client fact whose statement is not a substring of the
    turn (I2) and promotes a document fact only when its locator is verbatim in
    the hashed text, so an oracle that paraphrased would be silently writing
    document_extracted rows forever and the benchmark would never exercise
    verification at all.
  * output size is bounded by the call's own token budget, never by a constant.
    A real model cannot answer beyond `max_tokens`; neither does this one, so a
    caller that widens a budget gets a longer answer and nothing here fixes a
    count per engagement.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Mapping, Sequence

from app.engine.llm import ModelCall
from app.engine.methods.contract import METHODS, QuestionShape
from app.engine.partner.hypothesis import REVISE_PURPOSE
from app.engine.partner.questions import PHRASE_PURPOSE
from app.engine.synthesis.regulated import CLASSIFIER_PURPOSE, VERIFIER_PURPOSE
from app.engine.templating import KEEP_VERDICT
from app.engine.types import ID_PREFIX, Interrogative, Kind
from app.engine.work_products.render_md import NARRATIVE_PURPOSE

__all__ = [
    "ANSWER_PREFIX_RE",
    "PURPOSE_EXTRACT_DOCUMENT",
    "PURPOSE_EXTRACT_TURN",
    "PURPOSE_ISSUE_TREE",
    "UNKNOWN_MARKER",
    "answer_line",
    "structural_oracle",
]

# The purposes ingestion issues. They are string literals in ingest.py rather
# than named constants, so they are named here once instead of at each rule.
PURPOSE_EXTRACT_TURN = "extract_turn"
PURPOSE_EXTRACT_DOCUMENT = "extract_document"
PURPOSE_ISSUE_TREE = "issue_tree"

# What the deterministic client writes when it has nothing for a question. The
# oracle turns it into `unknown: true` on that question, which is how the
# RECORD_UNKNOWN path is reached: "I don't know" is an answer, and a question
# answered that way is never asked again (ingest.open_questions).
UNKNOWN_MARKER = "no record of that here"

# How the deterministic client addresses an answer: the question id it is
# answering and the kind of thing it is handing over, then the fact in the
# dossier's exact words. The envelope is a machine talking to a machine - the
# reveal is typed by design (MF1.4), and typing it in the message keeps the
# oracle case-blind while still letting a DECISION_OWNER answer land as a
# DECISION_OWNER rather than as one more sentence.
ANSWER_PREFIX_RE = re.compile(r"^(?P<qid>[A-Z]{3}-\d+) \[(?P<kind>[a-z_]+)\] (?P<body>.+)$")

_EMPTY_OBJECT = "{}"
# Roughly what one JSON item of any of these shapes costs. Only the ratio to
# the call's budget matters: it is what stops a 40-sentence document from
# becoming 40 facts when the caller asked for a small answer.
_TOKENS_PER_ITEM = 160

_ID_RE = re.compile(r"\b[A-Z]{3}-\d+\b")
# `- <id> [<vocabulary value>]: <wording>` - the row shape every template that
# shows entities uses (extract_turn, issue_tree, revise_hypothesis,
# phrase_questions, regulated_classifier).
_TAGGED_ROW = re.compile(r"^- (?P<id>[A-Z]{3}-\d+) \[(?P<tag>[a-z_]+)\]: (?P<text>.*)$", re.M)
# `- <id>: <wording>` - open questions, objectives, registered measures.
_PLAIN_ROW = re.compile(r"^- (?P<id>[A-Z]{3}-\d+): (?P<text>.*)$", re.M)
# The source text every ingestion prompt puts between triple quotes.
_QUOTED_BLOCK = re.compile(r'"""\s*\n(?P<body>.*?)\n"""', re.S)
_TURN_NUMBER = re.compile(r"^turn number: (?P<n>\d+)$", re.M)
_FANOUT = re.compile(r"at most (?P<n>\d+) children")
_SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]+|\n|$)")
_HAS_DIGIT = re.compile(r"\d")
# The token that follows a figure, when there is one: a unit, a currency code
# or a percent sign. Only its presence is used; calc.units re-parses the span.
_NUMBER = re.compile(r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>%|[A-Za-z][A-Za-z/%]*)?")

# The gap block phrase_questions renders, one per gap.
_GAP_ID = re.compile(r"^- gap (?P<gap_id>\S+)$", re.M)
_ASKS_FOR = re.compile(r"^\s*asks for: (?P<kind>[a-z_]+)", re.M)
_SETTLES = re.compile(r"^\s*settles issue: (?P<id>\S*) - (?P<text>.*)$", re.M)
_FOR_DECISION = re.compile(r"^\s*for decision: (?P<id>\S*) - (?P<text>.*)$", re.M)
_WHY_NEEDED = re.compile(r"^\s*why needed: (?P<text>.*)$", re.M)
_EXISTING_NODE = re.compile(r"^- (?P<id>[A-Z]{3}-\d+) \(parent ", re.M)
# How a node asks about the row it decomposes. Wording only: the shape is the
# whole instruction the engine reads.
_ASK_PREFIX: Mapping[str, str] = {
    "m": "What does the engagement need to settle about",
    "o": "What is in the way of",
    "e": "What follows for the decision from",
}
# The generic method prompt's own rendered rows.
_OUTPUT_KINDS = re.compile(r"^OUTPUT KINDS you may propose[^:]*: (?P<kinds>.+)$", re.M)
_INPUT_ROW = re.compile(r"^- (?P<id>[A-Z]{3}-\d+) \[(?P<kind>[a-z_]+)\]: (?P<text>.*?)(?: = (?P<qty>.+))?$", re.M)
_ISSUE_ROW = re.compile(r"^- (?P<id>[A-Z]{3}-\d+): (?P<text>.*)$", re.M)
# The sentence a narrative prompt requires when it offers no claims.
_EMPTY_NARRATIVE = re.compile(r'return the single sentence: "(?P<text>[^"]+)"')
_TOKEN_ROW = re.compile(r"^- (?P<id>[A-Z]{3}-\d+) -> (?P<token>\S+) : ", re.M)


# =============================================================================
# 1. Reading the prompt
# =============================================================================

def _prompt(call: ModelCall) -> str:
    return "\n".join(str(m.get("content") or "") for m in call.messages)


def _budget(call: ModelCall) -> int:
    """How many items this answer may carry. A model cannot exceed its token
    budget and neither does the oracle; the number is derived, never fixed."""
    return max(1, int(call.max_tokens) // _TOKENS_PER_ITEM)


def _source_text(prompt: str) -> str:
    match = _QUOTED_BLOCK.search(prompt)
    return match.group("body") if match else ""


def _sentences(text: str) -> list[str]:
    """Contiguous spans of `text`, trimmed. Trimming keeps a span a substring,
    which is what verify_quote and I2 both require."""
    out: list[str] = []
    for m in _SENTENCE.finditer(text):
        span = m.group().strip()
        if span:
            out.append(span)
    return out


def _tagged_rows(prompt: str) -> list[tuple[str, str, str]]:
    return [(m.group("id"), m.group("tag"), m.group("text").strip()) for m in _TAGGED_ROW.finditer(prompt)]


def _rows_of_kind(prompt: str, kind: Kind) -> list[tuple[str, str]]:
    """The rendered entity rows whose tag is this kind. The tag is validated
    against the enum, so a role tag (`[stated_request]`) is not mistaken for a
    kind tag and nothing is matched by wording."""
    out: list[tuple[str, str]] = []
    for entity_id, tag, text in _tagged_rows(prompt):
        try:
            tagged = Kind(tag)
        except ValueError:
            continue
        if tagged is kind:
            out.append((entity_id, text))
    return out


def _ids_with_prefix(prompt: str, kind: Kind) -> list[str]:
    prefix = ID_PREFIX[kind] + "-"
    seen: list[str] = []
    for found in _ID_RE.findall(prompt):
        if found.startswith(prefix) and found not in seen:
            seen.append(found)
    return seen


def _plain_rows(prompt: str, kind: Kind) -> list[tuple[str, str]]:
    prefix = ID_PREFIX[kind] + "-"
    return [(m.group("id"), m.group("text").strip())
            for m in _PLAIN_ROW.finditer(prompt) if m.group("id").startswith(prefix)]


def _kind_cues(prompt: str) -> list[tuple[str, Kind]]:
    """The kinds this prompt says may be proposed, as cue phrases.

    The catalogue is rendered into the prompt from the enum, so the rule reads
    prompt data rather than case text: a sentence that uses the word the
    catalogue prints for a kind proposes that kind. Longest phrase first, so
    `decision owner` is not read as `decision`.
    """
    cues: list[tuple[str, Kind]] = []
    for kind in Kind:
        phrase = kind.value.replace("_", " ")
        if phrase in prompt:
            cues.append((phrase, kind))
    cues.sort(key=lambda c: (-len(c[0]), c[0]))
    return cues


def _offset(seed: str) -> int:
    """A stable non-negative number from a piece of wording - where a choice
    over a catalogue starts."""
    return int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:8], "big")


def _pick(options: Sequence[Any], seed: str) -> Any:
    """One option, chosen by the hash of the wording the prompt showed. A model
    reads its prompt; this is the only sense in which the oracle does - and it
    is what makes two registries with different contents produce different
    structures rather than the same one twice."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return options[int.from_bytes(digest[:8], "big") % len(options)]


# =============================================================================
# 2. Quantities and measures
# =============================================================================

def _quantity_hint(span: str) -> tuple[dict[str, Any] | None, str | None]:
    """(quantity hint, measure name) for a span that states a figure.

    The value is handed back as written and re-parsed from the span by
    calc.units; the unit token is the word that follows the number. The measure
    is the noun phrase before the number, lowercased and not otherwise touched -
    normalising further would merge two measures the source kept apart.
    """
    match = _NUMBER.search(span)
    if match is None:
        return None, None
    unit = match.group("unit")
    hint = {"value": match.group("value"), "unit": unit, "currency": None, "period": None}
    before = span[: match.start()].strip()
    words = [w for w in re.split(r"[\s,;:()]+", before) if w]
    name = " ".join(words[-4:]).lower().strip()
    return hint, (name or None)


def _candidate(kind: Kind, quote: str, *, answers: Sequence[str] = ()) -> dict[str, Any]:
    hint, measure = _quantity_hint(quote)
    return {
        "kind": kind.value,
        "quote": quote,
        "text": quote,
        "quantity": hint,
        "measure_id": None,
        "measure_name": measure,
        "role": None,
        "answers": list(answers),
        "unknown": False,
    }


def answer_line(question_id: str, kind: Kind, body: str) -> str:
    """One line of a deterministic client's reply, in the shape the oracle
    reads. Built here so the two sides of the envelope cannot drift apart."""
    return f"{question_id} [{kind.value}] {body}"


# =============================================================================
# 3. Ingestion rules
# =============================================================================

def _answered_candidates(message: str, askable: Sequence[str],
                         budget: int) -> tuple[list[dict[str, Any]], set[str]]:
    """The lines that address an open question by id. Everything else is left
    to the generic sentence rules."""
    out: list[dict[str, Any]] = []
    consumed: set[str] = set()
    for line in message.splitlines():
        match = ANSWER_PREFIX_RE.match(line.strip())
        if match is None:
            continue
        qid = match.group("qid")
        if qid not in askable:
            continue
        consumed.add(line.strip())
        body = match.group("body").strip()
        if body == UNKNOWN_MARKER:
            # A refusal is an answer and carries no candidate: `unknown` is
            # read before the kind is, so the kind on the envelope does not
            # have to be one a turn may propose.
            out.append({"kind": Kind.FACT.value, "quote": "", "text": "", "quantity": None,
                        "measure_id": None, "measure_name": None, "role": None,
                        "answers": [qid], "unknown": True})
            continue
        try:
            kind = Kind(match.group("kind"))
        except ValueError:
            continue
        out.append(_candidate(kind, body, answers=[qid]))
        if len(out) >= budget:
            break
    return out, consumed


def _extract_turn(call: ModelCall) -> str:
    """One conversation turn -> candidates.

    Three rules, in order: a line addressed to an open question proposes what
    its envelope says it is; a sentence that uses a word from the rendered kind
    catalogue proposes that kind; a sentence that states a figure proposes a
    FACT with the figure as written. Turn one additionally states the request:
    the whole message, which is the only decision anybody has named yet.
    """
    prompt = _prompt(call)
    message = _source_text(prompt)
    if not message:
        return _EMPTY_OBJECT
    budget = _budget(call)
    askable = [m.group("id") for m in _PLAIN_ROW.finditer(prompt)
               if m.group("id").startswith(ID_PREFIX[Kind.QUESTION] + "-")]
    candidates, consumed = _answered_candidates(message, askable, budget)

    turn_match = _TURN_NUMBER.search(prompt)
    turn_number = int(turn_match.group("n")) if turn_match else 0
    if turn_number == 1:
        candidates.append(_candidate(Kind.DECISION, message.strip()))

    cues = _kind_cues(prompt)
    for span in _sentences(message):
        if len(candidates) >= budget:
            break
        if span in consumed or ANSWER_PREFIX_RE.match(span):
            continue
        lowered = span.lower()
        kind = None
        for phrase, cued in cues:
            if phrase in lowered:
                kind = cued
                break
        if kind is None and _HAS_DIGIT.search(span):
            kind = Kind.FACT
        if kind is None or kind is Kind.DECISION:
            # A decision candidate is proposed once, from the whole opening
            # statement: proposing one per sentence would flood the ranking
            # with restatements of the same request.
            continue
        candidates.append(_candidate(kind, span))
    return json.dumps({"candidates": candidates})


def _extract_document(call: ModelCall) -> str:
    """One document's text -> one FACT per sentence that states a figure.

    The record class stays unknown: a structural rule cannot tell a system of
    record from an opinion, and the class decides precedence in a conflict
    (design 5.4). Unknown leaves the provenance question open for the client,
    which is the honest outcome; guessing would resolve real conflicts on a
    fake's guess.
    """
    prompt = _prompt(call)
    text = _source_text(prompt)
    if not text:
        return _EMPTY_OBJECT
    budget = _budget(call)
    facts: list[dict[str, Any]] = []
    for span in _sentences(text):
        if len(facts) >= budget:
            break
        if not _HAS_DIGIT.search(span):
            continue
        hint, measure = _quantity_hint(span)
        facts.append({"quote": span, "statement": span, "quantity": hint,
                      "measure_id": None, "measure_name": measure,
                      "definition": None, "as_of": None})
    return json.dumps({"record_class": "unknown", "record_class_reason": "", "facts": facts})


# =============================================================================
# 4. Structure rules
# =============================================================================

def _shapes_by_interrogative() -> Mapping[Interrogative, tuple[QuestionShape, ...]]:
    """The shapes the method library declares it can take on, grouped by
    interrogative. The oracle proposes issues from this set on purpose: a model
    that proposed nodes no method answers would leave the tree full of dead
    questions, and the benchmark would measure the oracle's imagination instead
    of the engine's selection. Which shape a node gets is decided by the
    wording the prompt showed, so two registries diverge."""
    out: dict[Interrogative, list[QuestionShape]] = {}
    for method in METHODS.all():
        for shape in method.spec.applicability:
            if shape.capability_class is not None:
                continue
            out.setdefault(shape.interrogative, []).append(shape)
    return {k: tuple(sorted(set(v), key=lambda s: (s.target_kind.value, s.interrogative.value)))
            for k, v in out.items()}


def _node(shape: QuestionShape, *, text: str, parent_id: str | None, temp_id: str,
          derived_from: Sequence[str], decisive_for: Sequence[str], weight: float) -> dict[str, Any]:
    return {
        "text": text,
        "parent_id": parent_id,
        "temp_id": temp_id,
        "interrogative": shape.interrogative.value,
        "target_kind": shape.target_kind.value,
        "capability_class": None,
        "quantified": bool(shape.quantified),
        "comparative": bool(shape.comparative),
        "causal": bool(shape.causal),
        "temporal": bool(shape.temporal),
        "weight_to_parent": weight,
        "derived_from": list(derived_from),
        "decisive_for": list(decisive_for),
        "evidence_needed": [{"kind": shape.target_kind.value, "filter": {}}],
    }


def _issue_tree(call: ModelCall) -> str:
    """Decompose the decision: one quantified node per registered MEASURE, one
    causal node per OBJECTIVE (design 17.5). Both are things the registry
    holds, so a registry that gathered different measures decomposes into a
    differently shaped tree without the oracle knowing why."""
    prompt = _prompt(call)
    fanout_match = _FANOUT.search(prompt)
    fanout = int(fanout_match.group("n")) if fanout_match else _budget(call)
    limit = min(fanout, _budget(call))
    by_interrogative = _shapes_by_interrogative()
    quantified = by_interrogative.get(Interrogative.HOW_MUCH, ())
    causal = by_interrogative.get(Interrogative.WHY, ())
    if not quantified or not causal:
        return json.dumps({"nodes": []})

    every = tuple(s for shapes in by_interrogative.values() for s in shapes)
    decisions = [i for i in _ids_with_prefix(prompt, Kind.DECISION)]
    existing = [m.group("id") for m in _EXISTING_NODE.finditer(prompt)]
    parent = existing[0] if existing else None
    measures = _rows_of_kind(prompt, Kind.MEASURE)
    objectives = _plain_rows(prompt, Kind.OBJECTIVE)
    # Everything else the window showed. A specialist's ScopedView is narrow -
    # it holds the method's declared inputs and what they were derived from -
    # so a tree built only from measures and objectives can come out with one
    # node. The rest of the window is decomposed too, each node shaped by the
    # wording of the row it decomposes.
    others = [(eid, text) for eid, tag, text in _tagged_rows(prompt)
              if not eid.startswith(ID_PREFIX[Kind.DECISION] + "-")
              and not eid.startswith(ID_PREFIX[Kind.ISSUE] + "-")
              and not eid.startswith(ID_PREFIX[Kind.MEASURE] + "-")
              and not eid.startswith(ID_PREFIX[Kind.OBJECTIVE] + "-")]

    # Three levels, each within the fanout ceiling the prompt states: a wide
    # flat batch would break that rule, and depth is what gives the tree parent
    # edges - which is most of what its structural hash is made of. A level's
    # rows are the kind the design names for it (measures asked how much,
    # objectives asked why) and everything the window held otherwise, because a
    # specialist's window is narrow and a level with no rows is a level with no
    # nodes.
    everything = measures + objectives + others
    groups = ((measures or everything, quantified, "m"),
              (objectives or everything, causal, "o"),
              (others or everything, every, "e"))
    nodes: list[dict[str, Any]] = []
    level: list[str | None] = [parent]
    for rows, shapes, tag in groups:
        below: list[str | None] = []
        for i, (entity_id, wording) in enumerate(rows[:limit]):
            # The wording decides where in the catalogue this node starts, the
            # position decides how far along it steps. One decomposition
            # therefore spreads across the shapes rather than landing them all
            # on the same one, and two registries still diverge because the
            # wording that seeded them differs.
            shape = shapes[(_offset(wording or entity_id) + i) % len(shapes)]
            temp_id = f"{tag}{len(nodes)}"
            nodes.append(_node(shape, text=f"{_ASK_PREFIX[tag]} {wording}?",
                               parent_id=level[i % len(level)], temp_id=temp_id,
                               derived_from=[entity_id], decisive_for=decisions[:1],
                               weight=round(1.0 / max(1, limit), 4)))
            below.append(temp_id)
        if below:
            level = below
    return json.dumps({"nodes": nodes})


def _revise_hypothesis(call: ModelCall) -> str:
    """Candidate decisions and causal links, both citing the ids the prompt
    listed. The oracle proposes no new candidate wording of its own: the
    entities it can see are the client's words, and a candidate invented from a
    hash would be a decision nobody in the engagement ever mentioned. Causal
    links it can honestly offer - an issue and a cause the prompt listed
    together, cited by id."""
    prompt = _prompt(call)
    rows = _tagged_rows(prompt)
    issues = [r for r in rows if r[0].startswith(ID_PREFIX[Kind.ISSUE] + "-")]
    facts = [r for r in rows if r[0].startswith(ID_PREFIX[Kind.FACT] + "-")]
    links = []
    for (issue_id, _, issue_text), (fact_id, _, fact_text) in zip(issues, facts):
        if len(links) >= _budget(call):
            break
        links.append({"issue_id": issue_id, "cause_id": fact_id, "support_ids": [fact_id],
                      "text": f"{issue_text} may follow from {fact_text}"})
    return json.dumps({"new_candidates": [], "causal_links": links})


def _phrase_questions(call: ModelCall) -> str:
    """One question per gap, echoing the gap: the issue it settles and why it
    is needed, both rendered into the prompt by the engine. The agenda lock
    drops anything else, so echoing is the only honest thing to do - and it is
    what makes question text diverge between cases without the oracle knowing
    one case from another."""
    prompt = _prompt(call)
    blocks = list(_GAP_ID.finditer(prompt))
    questions: list[dict[str, str]] = []
    for i, match in enumerate(blocks):
        start = match.end()
        end = blocks[i + 1].start() if i + 1 < len(blocks) else len(prompt)
        block = prompt[start:end]
        asks = _ASKS_FOR.search(block)
        settles = _SETTLES.search(block)
        decision = _FOR_DECISION.search(block)
        why = _WHY_NEEDED.search(block)
        subject = (settles.group("text").strip() if settles else "")
        reason = (why.group("text").strip() if why else "")
        kind_phrase = (asks.group("kind").replace("_", " ") if asks else "")
        text = " ".join(p for p in (
            f"On {subject}" if subject else "",
            f"what {kind_phrase} can you give us?" if kind_phrase else "",
            f"({reason})" if reason else "",
        ) if p)
        questions.append({
            "gap_id": match.group("gap_id"),
            "text": text or kind_phrase,
            "issue_id": settles.group("id") if settles else "",
            "decision_id": decision.group("id") if decision else "",
        })
    return json.dumps({"questions": questions})


# =============================================================================
# 5. Screening and prose
# =============================================================================

def _regulated_classifier(call: ModelCall) -> str:
    """No claim. A structural rule cannot tell a licensed matter from an
    ordinary one, and a hashed guess would route arbitrary wording to an
    arbitrary profession - noise the coverage assertion would then be measuring.
    An empty list is a real answer (the prompt says so); the harness scripts
    this purpose from the case's typed annotations when a case needs the
    routing path exercised, and real runs are the only evidence about the
    classifier itself."""
    return json.dumps({"claims": []})


def _regulated_verifier(call: ModelCall) -> str:
    """Never clears. Stage two clears a claim only on one literal word, and
    clearing on a structural rule would be the under-routing the whole screen
    exists to prevent."""
    prompt = _prompt(call)
    ids = _ID_RE.findall(prompt)
    return json.dumps({"entity_id": ids[0] if ids else "", "verdict": KEEP_VERDICT,
                       "reason": "a structural rule cannot refute a licensed claim"})


def _narrative(call: ModelCall) -> str:
    """The claim tokens the prompt offered, one per line, and nothing else. The
    rules forbid a number, a name or a date outside a token, so a fake that
    wrote connecting prose would be inventing exactly what L6 and L11 exist to
    catch."""
    prompt = _prompt(call)
    tokens = [m.group("token") for m in _TOKEN_ROW.finditer(prompt)]
    if tokens:
        return "\n".join(tokens[: _budget(call)])
    empty = _EMPTY_NARRATIVE.search(prompt)
    return empty.group("text") if empty else ""


def _generic_method(call: ModelCall) -> str:
    """Model-assisted methods other than the issue tree.

    One output per declared output kind per input the window showed, each
    citing that input by id and restating its wording. Nothing is concluded and
    no number is coined: a figure travels only by `quantity_from`, copied from
    the input the prompt printed it on, which is the one channel the admission
    law allows. What this exercises is the machinery around the model - the
    admission rules, the payload builders, the validators, the plan predicates
    that count what analysis produced - and that machinery is what a benchmark
    can test. Whether a real model's conclusions are any good is a question
    only a real run answers.
    """
    prompt = _prompt(call)
    kinds_match = _OUTPUT_KINDS.search(prompt)
    if kinds_match is None:
        return json.dumps({"outputs": [], "questions": []})
    kinds: list[Kind] = []
    for token in kinds_match.group("kinds").split("|"):
        try:
            kinds.append(Kind(token.strip()))
        except ValueError:
            continue
    inputs = [(m.group("id"), m.group("text").strip(), m.group("qty"))
              for m in _INPUT_ROW.finditer(prompt)]
    budget = _budget(call)
    outputs: list[dict[str, Any]] = []
    for kind in kinds:
        for entity_id, text, quantity in inputs:
            if len(outputs) >= budget:
                break
            outputs.append({"kind": kind.value, "text": text,
                            "fields": {}, "quantity_from": entity_id if quantity else None,
                            "derived_from": [entity_id]})
    # What the window did not hold is a question, never an assumption. The
    # specialist asks for the kind it was told to produce and hands the issue
    # back; that question is what pauses analysis and returns to the client,
    # so the discovery-inside-analysis path of design 6.7 is on every run
    # rather than only on the runs that happened to strand a method.
    issue = _ISSUE_ROW.search(prompt)
    questions: list[dict[str, Any]] = []
    if kinds:
        wanted = kinds[-1]
        # The ask is worded from the node the specialist was assigned, never
        # from a template. A fake that asked for the same kind in the same
        # words on every engagement would put one constant question in every
        # bundle, which is a script by any other name - and the divergence
        # checks (assertions D1 and D2) exist to fail on exactly that. The
        # issue row is the per-engagement text this call carries; its wording
        # came out of the registry, so a question built from it is as
        # case-blind as the rest of the oracle and still differs per case.
        # The window's first input is the fallback subject: a method the tree
        # assigned without printing the node still asked about something
        # particular, and "this" would name nothing.
        subject = (issue.group("text").strip() if issue else "") or (inputs[0][1] if inputs else "")
        wording = wanted.value.replace("_", " ")
        questions.append({"text": (f"What {wording} would settle {subject}?" if subject
                                   else f"What {wording} would settle this?"),
                          "asks_for_kind": wanted.value,
                          "issue_id": issue.group("id") if issue else ""})
    return json.dumps({"outputs": outputs, "questions": questions})


_RULES: Mapping[str, Callable[[ModelCall], str]] = {
    PURPOSE_EXTRACT_TURN: _extract_turn,
    PURPOSE_EXTRACT_DOCUMENT: _extract_document,
    PURPOSE_ISSUE_TREE: _issue_tree,
    REVISE_PURPOSE: _revise_hypothesis,
    PHRASE_PURPOSE: _phrase_questions,
    CLASSIFIER_PURPOSE: _regulated_classifier,
    VERIFIER_PURPOSE: _regulated_verifier,
    NARRATIVE_PURPOSE: _narrative,
}

# What a generic method prompt prints. Matched as a marker, not parsed: the
# purposes are `method_<id>` and `method:<id>` in different modules, so the
# shape the prompt asks for is the reliable signal.
_GENERIC_MARKERS: tuple[str, ...] = ('"outputs"', '"questions"')


def structural_oracle(call: ModelCall) -> str:
    """Answer one model call from the call's own context.

    An unknown purpose whose prompt asks for the generic method shape gets the
    generic answer; anything else gets an empty JSON object, which every
    consumer in the engine reads as a real "nothing found" rather than as a
    default (llm.FakeProvider's contract).
    """
    rule = _RULES.get(call.purpose)
    if rule is not None:
        return rule(call)
    prompt = _prompt(call)
    if all(marker in prompt for marker in _GENERIC_MARKERS):
        return _generic_method(call)
    return _EMPTY_OBJECT
