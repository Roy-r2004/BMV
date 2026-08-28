"""The canonical registry — one typed source of truth for every fact an
engagement repeats.

Every statement that appears more than once in a package (a module's name, a
phase number, a dependency, an interface, an actor, a policy period, a metric
target, a scenario assumption, the pilot gate) is ONE typed entity here. The
renderer prints those statements from this registry. The verifier compares
what a document says against this registry and REPORTS what does not match.

The only automatic correction this module permits is an exact canonical
mapping: a surface form that denotes exactly one entity is replaced by that
entity's canonical form. Name for the same name, nothing else. When a surface
form denotes no entity, or more than one, the verifier fails closed — it
reports the conflict and blocks the release. No generic wording is ever
substituted for unknown content; no sentence is rewritten; no similarity
score decides anything.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

KINDS = ("fact", "concept", "module", "phase", "dependency", "interface", "actor",
         "policy", "metric", "assumption", "gate", "feature")
# kinds whose canonical form is a NAME (and so can be resolved from a surface
# form in prose); the rest are statements, addressed by id
NAMED_KINDS = ("module", "actor", "interface", "concept", "policy", "feature")

# audiences an interface can serve
CUSTOMER, STAFF, INTERNAL = "customer", "staff", "internal"


@dataclass(frozen=True)
class Entity:
    """One canonical thing. `canonical` is how it is written wherever it is
    stated; `surfaces` are the other exact strings that denote it."""
    id: str
    kind: str
    canonical: str
    surfaces: tuple[str, ...] = ()
    data: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"unknown entity kind: {self.kind}")


@dataclass(frozen=True)
class Resolution:
    status: str                      # "unique" | "ambiguous" | "unknown"
    entity: Entity | None = None
    candidates: tuple[str, ...] = ()

    @property
    def unique(self) -> bool:
        return self.status == "unique"


@dataclass(frozen=True)
class Mapping:
    """One applied exact canonical mapping — the audit trail of the only
    correction this architecture allows."""
    surface: str
    canonical: str
    entity_id: str
    where: str


# ── surface-form derivation ──────────────────────────────────────────────────

_WORD = re.compile(r"[A-Za-z0-9]+")
_WORD_TOKEN = re.compile(r"[A-Za-z][\w-]*")


def humanize(identifier: str) -> str:
    """'ai-settlement-inquiry-resolver' -> 'Ai Settlement Inquiry Resolver'.
    A machine id written out as words is a surface form of its entity."""
    return " ".join(w.capitalize() for w in re.split(r"[-_]+", str(identifier or "")) if w)


def _drop_inner_words(name: str) -> set[str]:
    """Forms a writer produces by dropping one or two inner words:
    'AI Delivery Pre-Confirmation Engine' -> 'AI Pre-Confirmation Engine'."""
    words = name.split()
    out: set[str] = set()
    if len(words) >= 4:
        for i in range(1, len(words) - 1):
            out.add(" ".join(words[:i] + words[i + 1:]))
        for i in range(1, len(words) - 2):
            out.add(" ".join(words[:i] + words[i + 2:]))
    return {f for f in out if len(f.split()) >= 3}


_ACRONYM = re.compile(r"^[A-Z]{2,4}$")


def _drop_leading_words(name: str) -> set[str]:
    """'AI COD Settlement Inquiry Resolver' -> 'COD Settlement Inquiry
    Resolver', 'Settlement Inquiry Resolver'.

    ONLY leading acronyms are droppable. Dropping an ordinary leading word
    would register generic English ('Support Staff', 'Confirmation Pilot') as
    a name for one entity, and a document that uses those words in their
    ordinary sense would be rewritten. Fail closed: fewer surface forms."""
    words = name.split()
    out = set()
    for k in (1, 2):
        if len(words) - k >= 2 and all(_ACRONYM.match(w) for w in words[:k]):
            out.add(" ".join(words[k:]))
    return out


# ── well-formedness ─────────────────────────────────────────────────────────
# A token repeated inside ONE contiguous name, with at most two words between.
# Separators are spaces and tabs only: a comma-separated list ("… Engine,
# Delivery & Settlement …") and a heading followed by a paragraph are not
# repetitions, and treating them as such would flag ordinary prose.
_REPEATED_RUN = re.compile(r"\b([A-Z][\w-]+)((?:[ \t]+[A-Za-z][\w-]*){0,2})[ \t]+\1\b")
# the same parenthetical twice in a row — "(your stated cycle) (your stated
# cycle)" — which is an attribution rendered onto a statement that already
# carried it.
_REPEATED_PARENTHETICAL = re.compile(r"(\(([^()]{2,80})\))(\s*\1)+")


# function words are not names. A heading followed by a paragraph that opens
# with the same word ("The opportunity" / "The …") is ordinary English, and on
# a rendered page the two sit one after the other.
_NOT_A_NAME_TOKEN = frozenset(
    "The This That These Those A An It We You Your Our Their Its In On At For To Of And Or But If "
    "When While With By From As Is Are Be All Each Every No Not One Two Three First Next Then Now "
    "Also How What Why Where Who Both Any Some Such Other Same More Most Less".split())


def repeated_run(name: str, name_tokens: Iterable[str] | None = None):
    """The first repeated token run in a NAME, or None.

    Two things keep this off ordinary prose. The repeated token is never an
    English function word ("The opportunity … The …" is a heading and its
    paragraph). And when the registry's vocabulary is supplied, the repeated
    token must be a token of some registered name — so a rendered heading like
    "DAY TO DAY" is English, while "Client Client Portal …" is a name built
    twice from the registry's own words."""
    tokens = set(name_tokens) if name_tokens is not None else None
    for m in _REPEATED_RUN.finditer(name or ""):
        token = m.group(1)
        if token in _NOT_A_NAME_TOKEN or (tokens is not None and token not in tokens):
            continue
        return m
    return None


def _statement_around(text: str, index: int) -> str:
    """The sentence the character at `index` sits in — the span an attribution
    is judged over."""
    start = max((text.rfind(p, 0, index) for p in (". ", "! ", "? ", "\n")), default=-1)
    end = min((e for e in (text.find(p, index) for p in (". ", "! ", "? ", "\n")) if e != -1), default=len(text))
    return text[start + 1:end + 1]


def collapse_attribution(text: str) -> str:
    """An attribution is stated once. Idempotent by construction: its own
    output contains no adjacent repeat for it to collapse."""
    return _REPEATED_PARENTHETICAL.sub(r"\1", text or "")


def collapse_statement_attributions(text: str, policies: Iterable[tuple[str, str]]) -> str:
    """Within one statement an attribution is stated once per policy the
    statement names.

    Run 53-r24 shipped "… remittance dates (within 10 days after month-end
    (your stated cycle) to fully settle COD with a client (your stated
    cycle))". The two markers are not adjacent, so collapsing adjacent repeats
    could not see them. A statement naming ONE registered policy carries ONE
    attribution: the first is kept and the rest are dropped. A statement that
    names two policies may carry two, so a package with several client-stated
    cycles is never flattened."""
    policies = [(c, a) for c, a in policies if c and a]
    if not text or not policies:
        return text
    out = []
    for chunk in re.split(r"(?<=[.!?])(\s+)", text):
        if not chunk or chunk.isspace():
            out.append(chunk)
            continue
        for attribution in {a for _, a in policies}:
            allowed = max(1, len({c for c, a in policies if a == attribution and c in chunk}))
            seen = 0
            pieces, last = [], 0
            for m in re.finditer(re.escape(attribution), chunk):
                seen += 1
                if seen <= allowed:
                    continue
                pieces.append(chunk[last:m.start()])
                last = m.end()
                while last < len(chunk) and chunk[last] == " ":
                    last += 1
            if pieces:
                pieces.append(chunk[last:])
                chunk = re.sub(r"\s+([)\].,;])", r"\1", "".join(pieces))
        out.append(chunk)
    return "".join(out)


def collapse_repeat(name: str, known: Iterable[str] = (), corpus: str = "",
                    name_tokens: Iterable[str] | None = None) -> tuple[str | None, str]:
    """The one well-formed name a repeated run collapses to, or (None, reason).

    Dropping either occurrence of the repeated token gives two candidates.
    Exactly one of three ordered tests must choose between them — they are
    identical; exactly one contains a registered canonical name; exactly one
    occurs verbatim elsewhere in the engagement. If none chooses, the registry
    states nothing: the verifier reports the malformed name and the release
    fails closed. Nothing is guessed and no similarity is scored."""
    m = repeated_run(name, name_tokens)
    if not m:
        return name, ""
    token, middle = m.group(1), m.group(2)
    drop_first = name[:m.start()] + (middle.strip() + " " if middle.strip() else "") + token + name[m.end():]
    drop_second = name[:m.start()] + token + middle + name[m.end():]
    a, b = (re.sub(r"[ \t]{2,}", " ", s).strip() for s in (drop_first, drop_second))
    if a == b:
        return a, "both collapses agree"
    registered = [n for n in known if n and len(str(n).split()) >= 2]
    in_a = [n for n in registered if n in a]
    in_b = [n for n in registered if n in b]
    if bool(in_a) != bool(in_b):
        chosen, names = (a, in_a) if in_a else (b, in_b)
        return chosen, f"it states the registered name '{sorted(names, key=len)[-1]}'"
    if corpus:
        seen_a, seen_b = corpus.count(a), corpus.count(b)
        if bool(seen_a) != bool(seen_b):
            return (a if seen_a else b), "it is the form the engagement states elsewhere"
    return None, "neither collapse states a registered name or appears elsewhere"


def name_surfaces(name: str, *extra: str) -> tuple[str, ...]:
    """Every exact string that denotes this name and is not the name itself."""
    out: set[str] = set()
    for e in extra:
        if e and str(e) != name:
            out.add(str(e))
    out |= _drop_inner_words(name)
    out |= _drop_leading_words(name)
    out.discard(name)
    return tuple(sorted({s for s in out if len(s) > 5}, key=len, reverse=True))


# ── the registry ─────────────────────────────────────────────────────────────


class Canon:
    """A typed, immutable view over one engagement's canonical entities."""

    def __init__(self, entities: Iterable[Entity]):
        self._entities: dict[str, Entity] = {}
        for e in entities:
            if e.id in self._entities:
                raise ValueError(f"duplicate entity id: {e.id}")
            self._entities[e.id] = e
        # surface -> entity ids (a list: ambiguity is data, not an error).
        # Only NAMED kinds are indexed by surface form: a fact or an
        # assumption is a statement, not a name, and two facts quoting the
        # same client sentence must never make that sentence "ambiguous".
        self._index: dict[str, list[str]] = {}
        for e in self._entities.values():
            if e.kind not in NAMED_KINDS:
                continue
            for s in (e.canonical,) + tuple(e.surfaces):
                if not s:
                    continue
                self._index.setdefault(s, [])
                if e.id not in self._index[s]:
                    self._index[s].append(e.id)

    # -- access ------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._entities)

    def __getitem__(self, entity_id: str) -> Entity:
        return self._entities[entity_id]

    def get(self, entity_id: str) -> Entity | None:
        return self._entities.get(entity_id)

    def of_kind(self, kind: str) -> list[Entity]:
        return [e for e in self._entities.values() if e.kind == kind]

    def names(self, *kinds: str) -> list[str]:
        want = set(kinds) or set(KINDS)
        return sorted({e.canonical for e in self._entities.values() if e.kind in want}, key=len, reverse=True)

    def name_tokens(self) -> set[str]:
        """Every word of every registered name — the vocabulary a malformed
        name is necessarily built from."""
        if getattr(self, "_tokens", None) is None:
            self._tokens = {w for e in self._entities.values() if e.kind in NAMED_KINDS
                            for w in _WORD_TOKEN.findall(e.canonical)}
        return self._tokens

    def all_surfaces(self, *kinds: str) -> list[tuple[str, str]]:
        """(surface, entity_id) for every non-canonical surface form."""
        want = set(kinds) or set(KINDS)
        out = []
        for e in self._entities.values():
            if e.kind in want:
                out += [(s, e.id) for s in e.surfaces]
        return sorted(out, key=lambda p: -len(p[0]))

    # -- resolution --------------------------------------------------------
    def resolve(self, surface: str) -> Resolution:
        """Exactly one entity, several, or none. No fuzziness: a surface form
        is either an exact string this registry knows or it is unknown."""
        ids = self._index.get((surface or "").strip(), [])
        if len(ids) == 1:
            return Resolution("unique", self._entities[ids[0]], (ids[0],))
        if len(ids) > 1:
            return Resolution("ambiguous", None, tuple(ids))
        return Resolution("unknown", None, ())

    def is_known(self, surface: str) -> bool:
        return bool(self._index.get((surface or "").strip()))

    # -- the one permitted correction --------------------------------------
    def _scanner(self) -> "re.Pattern[str] | None":
        """One alternation over every canonical form AND every surface form,
        longest first. Scanning once, left to right, is what makes the
        mapping safe: a surface form that is part of its own canonical form
        ('COD Settlement Inquiry Resolver' inside 'AI COD Settlement Inquiry
        Resolver') is consumed by the canonical match and never rewritten."""
        if getattr(self, "_scan", None) is None:
            forms = sorted(self._index, key=len, reverse=True)
            self._scan = (re.compile(r"(?<!\w)(?:" + "|".join(re.escape(f) for f in forms) + r")(?!\w)")
                          if forms else None)
        return self._scan

    def mask_entities(self, text: str) -> str:
        """Every registered name span replaced by same-length filler, in ONE
        longest-first left-to-right scan — the same scanner the mapping uses.

        A law that reads prose must not read a NAME: 'Business Client COD
        Settlement Escalation Form' is an interface, not a mention of the
        business-client population, and typing an actor from words inside a
        registered name lets a name decide its own audience."""
        scanner = self._scanner()
        if not text or scanner is None:
            return text or ""
        return scanner.sub(lambda m: "\0" * len(m.group(0)), text)

    def apply_exact_mappings(self, text: str, where: str = "") -> tuple[str, list[Mapping]]:
        """Replace every non-canonical surface form that denotes exactly one
        entity with that entity's canonical form. One left-to-right scan,
        word-bounded, literal, recorded. Nothing else in this codebase may
        rewrite a document."""
        scanner = self._scanner()
        if not text or scanner is None:
            return text, []
        applied: list[Mapping] = []
        out: list[str] = []
        last = 0
        for m in scanner.finditer(text):
            form = m.group(0)
            ids = self._index.get(form, [])
            if len(ids) != 1:
                continue                       # ambiguous: reported, never guessed
            entity = self._entities[ids[0]]
            if form == entity.canonical:
                continue                       # already canonical
            # a mapping never CREATES a repeated token run. Expanding a surface
            # form that overlaps a longer name already in the text inserts a
            # token that is present already: run 53 turned 'Client Portal …'
            # into 'Client Client Portal …' this way, and once THAT was
            # canonical its own derived surface was the clean name, so every
            # clean mention expanded into the corrupt one. The guard is local
            # and exact — it compares the join before and after.
            head = "".join(out) + text[last:m.start()]
            tail = text[m.end():m.end() + 80]
            # an ATTRIBUTED statement is attributed once. The surface form of a
            # policy is its core without the attribution, so mapping it onto a
            # statement that already carries the attribution appends a second
            # one — run 53 shipped "(your stated cycle) (your stated cycle)".
            attribution = entity.data.get("attribution")
            if attribution and attribution in _statement_around(text, m.start()):
                continue
            toks = self.name_tokens()
            if (repeated_run(head[-80:] + entity.canonical + tail, toks)
                    and not repeated_run(head[-80:] + form + tail, toks)):
                continue
            out.append(text[last:m.start()])
            out.append(entity.canonical)
            last = m.end()
            applied.append(Mapping(form, entity.canonical, entity.id, where))
        out.append(text[last:])
        return "".join(out), applied

    # -- canonical statements ----------------------------------------------
    def statement(self, kind: str, key: str) -> str | None:
        e = self._entities.get(f"{kind}:{key}")
        return e.canonical if e else None

    # -- audience ------------------------------------------------------------
    def interfaces_of(self, owner: str, audience: str) -> list[Entity]:
        return [e for e in self.of_kind("interface")
                if e.data.get("owner") == owner and e.data.get("audience") == audience]

    def channel_mapping(self, owner: str) -> tuple[Entity, Entity] | None:
        """The typed correction the registry can make on its own: when an
        owner holds EXACTLY ONE internal interface and EXACTLY ONE
        customer-facing interface, the name that belongs in a customer-facing
        position is determined — one exact canonical mapping, name for name.
        Zero or several of either and there is no mapping: the layer reports
        the conflict and the release stays closed."""
        internal = self.interfaces_of(owner, INTERNAL)
        customer = self.interfaces_of(owner, CUSTOMER)
        if len(internal) == 1 and len(customer) == 1:
            return internal[0], customer[0]
        return None

    # -- phases --------------------------------------------------------------
    def phases(self) -> list[Entity]:
        """Numbered phases in number order, then the parallel workstream."""
        numbered = sorted((e for e in self.of_kind("phase") if isinstance(e.data.get("number"), int)),
                          key=lambda e: e.data["number"])
        return numbered + [e for e in self.of_kind("phase") if e.data.get("number") is None]

    def phase_of_module(self, name: str) -> Entity | None:
        for e in self.of_kind("phase"):
            if name in (e.data.get("modules") or []):
                return e
        return None

    def build_order(self) -> list[str]:
        """The registry's build order: the modules of each numbered phase in
        phase order, then the parallel workstream's. A parallel module is
        never given a number by appearing in this list."""
        return [n for e in self.phases() for n in (e.data.get("modules") or [])]

    def heading_for(self, module_names: Iterable[str]) -> tuple[str | None, str]:
        """The canonical heading of a section that delivers `module_names`.

        Returns (heading, "") when the registry can state it, and (None,
        reason) when it cannot. A section that claims two numbered phases is a
        conflict: the registry reports it and the renderer writes nothing."""
        numbered: list[Entity] = []
        parallel: Entity | None = None
        for name in module_names:
            phase = self.phase_of_module(str(name))
            if phase is None:
                continue
            if phase.data.get("number") is None:
                parallel = phase
            elif phase not in numbered:
                numbered.append(phase)
        if not numbered and parallel is None:
            return None, "no delivered module belongs to a registry phase"
        if len(numbered) > 1:
            claimed = ", ".join(str(p.data.get("label")) for p in sorted(numbered, key=lambda e: e.data["number"]))
            return None, f"one section delivers modules from {claimed}"
        if not numbered:
            return parallel.canonical, ""
        # A numbered phase and the parallel workstream in ONE section is the
        # same conflict as two numbered phases. Run 53-r22 minted "Phase 4 —
        # …, with the parallel workstream …", which is exactly the grouping a
        # parallel workstream exists to deny: it has no number because it does
        # not run in sequence with the phases.
        if parallel is not None:
            return None, (f"one section delivers {numbered[0].data.get('label')} and the "
                          f"{PARALLEL_LABEL.lower()}")
        return numbered[0].canonical, ""


# ── building the registry from an engagement's structured content ────────────


class _NamedThings:
    """One namespace for everything with a NAME (modules, interfaces, actors).
    A module that a procedure step also acts as, and that an integration list
    also names as a system, is ONE entity playing three roles — never three
    entities that make every mention ambiguous. The first, most authoritative
    spelling is canonical; every other spelling becomes a surface form."""

    #  higher wins the canonical spelling and the entity's primary kind
    RANK = {"module": 4, "actor": 3, "interface": 2, "feature": 1}

    def __init__(self) -> None:
        self._by_slug: dict[str, dict] = {}

    def add(self, name: str, kind: str, *, id_hint: str = "", surfaces: Iterable[str] = (),
            data: dict | None = None) -> None:
        name = str(name or "").strip()
        if not name or len(name) < 4:
            return
        slug = _slug(name)
        rec = self._by_slug.get(slug)
        if rec is None:
            rec = {"slug": slug, "canonical": name, "kind": kind, "rank": self.RANK.get(kind, 0),
                   "surfaces": set(), "roles": set(), "data": {}, "id_hint": id_hint or slug}
            self._by_slug[slug] = rec
        if self.RANK.get(kind, 0) > rec["rank"]:
            # a more authoritative source names it: its spelling becomes canonical
            if rec["canonical"] != name:
                rec["surfaces"].add(rec["canonical"])
            rec.update(canonical=name, kind=kind, rank=self.RANK.get(kind, 0), id_hint=id_hint or rec["id_hint"])
        elif name != rec["canonical"]:
            rec["surfaces"].add(name)
        rec["roles"].add(kind)
        for s in surfaces:
            if s and str(s) != rec["canonical"]:
                rec["surfaces"].add(str(s))
        for k, v in (data or {}).items():
            # a set-valued key accumulates across every declarer. `setdefault`
            # alone means the FIRST module to name a shared system owns it,
            # and every later declarer is silently dropped — which makes
            # `owner` useless as proof of exclusive ownership.
            if isinstance(v, (set, frozenset)):
                rec["data"].setdefault(k, set()).update(v)
            else:
                rec["data"].setdefault(k, v)

    def entities(self) -> list[Entity]:
        out = []
        for rec in self._by_slug.values():
            derived = set(name_surfaces(rec["canonical"]))
            if rec["kind"] in ("module", "interface"):
                derived.add(f"{rec['canonical']} module")
            surfaces = {s for s in (rec["surfaces"] | derived) if s and s != rec["canonical"]}
            out.append(Entity(id=f"{rec['kind']}:{rec['id_hint']}", kind=rec["kind"], canonical=rec["canonical"],
                              surfaces=tuple(sorted(surfaces, key=len, reverse=True)),
                              data={**{k: (sorted(v) if isinstance(v, set) else v) for k, v in rec["data"].items()},
                                    "roles": sorted(rec["roles"])}))
        return out


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:60]


def _add_modules(things: _NamedThings, content: dict) -> None:
    from app.pipeline import pilot_gate as _pg

    reg = content.get("registry") or {}
    reg_by_id = {m.get("id"): m for m in reg.get("modules") or []}
    for m in content.get("modules") or []:
        if not isinstance(m, dict) or not m.get("id"):
            continue
        rm = reg_by_id.get(m["id"], {})
        canonical = str(m.get("client_facing_name") or rm.get("client_facing_name") or m.get("name") or "").strip()
        if not canonical:
            continue
        spec = m.get("spec") if isinstance(m.get("spec"), dict) else {}
        tech = m.get("tech") if isinstance(m.get("tech"), dict) else {}
        things.add(canonical, "module", id_hint=m["id"],
                   surfaces=[s for s in (m.get("name"), m.get("original_name"), rm.get("alias"), humanize(m["id"])) if s],
                   data={
                       "module_id": m["id"],
                       "pilot": bool(m.get("pilot")),
                       "phase": rm.get("phase") or m.get("phase"),
                       "phase_number": rm.get("phase_number", m.get("phase_number")),
                       "workstream": rm.get("workstream", m.get("workstream")),
                       "automation_level": m.get("automation_level"),
                       "has_ai_component": bool(spec.get("ai") or tech.get("ai_agent")),
                       "ai_involvement": bool(m.get("ai_involvement")),
                       "users": [str(u) for u in (m.get("users") or [])],
                       "depends_on": list(m.get("depends_on") or []),
                       "kpi_claim_ids": list(m.get("kpi_claim_ids") or []),
                       "audience": audience_of([str(u) for u in (m.get("users") or [])]),
                   })
    # the pilot's stand-ins are engagement-agnostic interfaces of their own
    things.add(_pg.PILOT_TOOLING, "interface", id_hint="pilot-tooling",
               data={"interface_kind": "queue", "audience": INTERNAL, "owner": "the pilot",
                     "declarers": {"the pilot"}})
    things.add(_pg.PILOT_CUSTOMER_FORM, "interface", id_hint="pilot-customer-form",
               data={"interface_kind": "form", "audience": CUSTOMER, "owner": "the pilot",
                     "declarers": {"the pilot"}})


PARALLEL_LABEL = "Parallel workstream"


def phase_title(module_names: Iterable[str]) -> str:
    """A phase is titled by what it delivers. The title is the canonical names
    of its modules, in registry order — never a coined phrase. One module, one
    name; several modules, all of them. Nothing about the count is fixed."""
    names = [str(n) for n in module_names if n]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def _phase_entities(modules: list[Entity]) -> list[Entity]:
    by_number: dict[int, list[str]] = {}
    parallel: list[str] = []
    for m in modules:
        n = m.data.get("phase_number")
        if isinstance(n, int):
            by_number.setdefault(n, []).append(m.canonical)
        elif m.data.get("workstream") == "parallel":
            parallel.append(m.canonical)
    out = [Entity(id=f"phase:{n}", kind="phase", canonical=f"Phase {n} — {phase_title(names)}",
                  data={"number": n, "modules": names, "title": phase_title(names),
                        "label": f"Phase {n}"})
           for n, names in sorted(by_number.items())]
    if parallel:
        out.append(Entity(id="phase:parallel", kind="phase",
                          canonical=f"{PARALLEL_LABEL} — {phase_title(parallel)}",
                          data={"number": None, "modules": parallel, "title": phase_title(parallel),
                                "label": PARALLEL_LABEL}))
    return out


def _dependency_entities(modules: list[Entity]) -> list[Entity]:
    by_module_id = {m.data.get("module_id"): m for m in modules if m.kind == "module"}
    out = []
    for m in modules:
        if m.kind != "module":
            continue
        for dep in m.data.get("depends_on") or []:
            target = by_module_id.get(dep)
            if target is None:
                continue
            out.append(Entity(id=f"dependency:{m.data['module_id']}->{dep}", kind="dependency",
                              canonical=f"{m.canonical} depends on {target.canonical}",
                              data={"from": m.canonical, "to": target.canonical,
                                    "from_phase": m.data.get("phase_number"), "to_phase": target.data.get("phase_number")}))
    return out


_STAFF_WORDS = re.compile(r"staff|team|agent|dispatch|operator|manager|finance|support|admin|analyst|lead", re.IGNORECASE)
_CUSTOMER_WORDS = re.compile(r"customer|client|shopper|patient|guest|member|tenant|passenger|end[- ]user", re.IGNORECASE)


def audience_of(users: Iterable[str], text: str = "") -> str:
    blob = " ".join(list(users) + [text or ""])
    customer = bool(_CUSTOMER_WORDS.search(blob))
    staff = bool(_STAFF_WORDS.search(blob))
    if customer and not staff:
        return CUSTOMER
    if staff and not customer:
        return STAFF
    return INTERNAL if not customer else CUSTOMER


def _add_interfaces(things: _NamedThings, content: dict) -> None:
    """Screens, APIs, forms and named systems each module declares. A screen
    a customer opens and an internal queue are both interfaces — they differ
    by audience, and the difference is registry data, not a judgment call."""
    for m in content.get("modules") or []:
        if not isinstance(m, dict):
            continue
        owner = str(m.get("client_facing_name") or m.get("name") or "")
        users = [str(u) for u in (m.get("users") or [])]
        spec = m.get("spec") if isinstance(m.get("spec"), dict) else {}
        tech = m.get("tech") if isinstance(m.get("tech"), dict) else {}
        for screen in list(spec.get("screens") or []) + list(tech.get("screens") or []):
            name = screen.get("name") if isinstance(screen, dict) else screen
            if isinstance(name, str):
                things.add(re.sub(r"\s*\([^)]*\)\s*$", "", name), "interface",
                           data={"interface_kind": "screen", "owner": owner, "declarers": {owner},
                                 "audience": audience_of(users, str(screen))})
        for api in tech.get("apis") or []:
            if isinstance(api, dict) and api.get("name"):
                things.add(str(api["name"]), "interface",
                           data={"interface_kind": "api", "owner": owner, "declarers": {owner},
                                 "audience": INTERNAL, "does": api.get("does")})
        # a named system is not internal by assumption: a client portal is a
        # system a client opens. Its audience comes from what the entry itself
        # says, never from the module's users (the pilot's users include
        # customers, which would make every system it touches customer-facing)
        for key in ("integrations", "integration_details"):
            for it in tech.get(key) or []:
                system = it.get("system") if isinstance(it, dict) else it
                if isinstance(system, str):
                    things.add(re.sub(r"\s*\([^)]*\)\s*$", "", system), "interface",
                               data={"interface_kind": "system", "owner": owner, "declarers": {owner},
                                     "audience": audience_of([], re.sub(r"\s*\([^)]*\)\s*$", "", str(system)))})
        for it in spec.get("integrations") or []:
            if isinstance(it, str):
                things.add(re.sub(r"\s*\([^)]*\)\s*$", "", it), "interface",
                           data={"interface_kind": "system", "owner": owner, "declarers": {owner},
                                 "audience": audience_of([], re.sub(r"\s*\([^)]*\)\s*$", "", str(it)))})
    checklists = content.get("checklists") if isinstance(content.get("checklists"), dict) else {}
    for form in checklists.get("forms") or []:
        if isinstance(form, dict) and form.get("name"):
            things.add(str(form["name"]), "interface",
                       data={"interface_kind": "form", "owner": "operations", "declarers": {"operations"},
                             "audience": audience_of([], str(form.get("purpose") or ""))})


def _add_features(things: _NamedThings, content: dict) -> None:
    """A module's named capabilities ('Response Tracking & Reminder System')
    are canonical names too — a document may state them, so the registry owns
    them and their owning module."""
    for m in content.get("modules") or []:
        if not isinstance(m, dict):
            continue
        owner = str(m.get("client_facing_name") or m.get("name") or "")
        spec = m.get("spec") if isinstance(m.get("spec"), dict) else {}
        for f in spec.get("features") or []:
            name = f.get("name") if isinstance(f, dict) else f
            if isinstance(name, str) and len(name.split()) >= 2:
                things.add(name.strip(), "feature",
                           data={"owner": owner, "module_id": m.get("id"), "pilot": bool(m.get("pilot"))})


def _add_actors(things: _NamedThings, content: dict) -> None:
    """Who acts. The org chart names the canonical form; a procedure's
    spelling of the same actor ('ICARRY support staff') is a surface form of
    it, never a second actor."""
    org = content.get("org") if isinstance(content.get("org"), dict) else {}
    for role in org.get("roles") or []:
        if isinstance(role, dict) and role.get("role"):
            things.add(str(role["role"]), "actor",
                       data={"actor_kind": "ai" if str(role.get("type")) == "ai" else "human",
                             "decides_alone": role.get("decides_alone"), "hands_off": role.get("hands_off"),
                             "from": "org"})
    procedures = (content.get("procedures") or {}).get("procedures") if isinstance(content.get("procedures"), dict) else []
    for p in procedures or []:
        for step in (p or {}).get("steps") or []:
            things.add(str((step or {}).get("actor") or ""), "actor", data={"from": "procedures"})


def _fact_and_policy_entities(content: dict) -> list[Entity]:
    from app.pipeline import registry as _reg

    reg = content.get("registry") or {}
    claims = reg.get("claims") or []
    out: list[Entity] = []
    for c in claims:
        if c.get("type") != "client_fact":
            continue
        out.append(Entity(id=f"fact:{c['id']}", kind="fact",
                          canonical=str(c.get("text") or "").strip() or f"{c.get('value')} {c.get('unit')}".strip(),
                          data={"value": c.get("value"), "unit": c.get("unit"), "basis": c.get("time_basis"),
                                "question": c.get("question"), "event": c.get("event")}))
    # a client-stated period with an event origin is a policy: one canonical
    # sentence fragment, wherever the package states it
    for n, origin in _reg.deadline_days(claims).items():
        subject = _reg._policy_subject(claims, n)
        core, attribution = f"{n} days {origin}", "(your stated cycle)"
        out.append(Entity(id=f"policy:{subject}-period", kind="policy",
                          canonical=f"{core} {attribution}",
                          surfaces=(core,),
                          data={"subject": subject, "value": n, "unit": "days", "event": origin,
                                "provenance": "client_stated", "core": core, "attribution": attribution,
                                "cadence_allowed": n in _reg.cadence_days(claims)}))
    # the pilot's outreach policy: one attempt total, from the pilot SOP
    procedures = (content.get("procedures") or {}).get("procedures") if isinstance(content.get("procedures"), dict) else []
    total = _reg.sop_attempt_total(procedures or [])
    if total:
        out.append(Entity(id="policy:pilot-outreach-attempts", kind="policy",
                          canonical=f"{total} outreach attempts (the first message and {total - 1} reminders)",
                          data={"value": total, "unit": "attempts", "provenance": "pilot_sop"}))
    return out


def _metric_and_assumption_entities(content: dict) -> list[Entity]:
    reg = content.get("registry") or {}
    out: list[Entity] = []
    for c in reg.get("claims") or []:
        if c.get("type") == "module_kpi":
            out.append(Entity(id=f"metric:{c['id']}", kind="metric",
                              canonical=str(c.get("text") or "").strip(),
                              data={"module": c.get("scope"), "value": c.get("value"), "unit": c.get("unit"),
                                    "provenance": c.get("provenance"), "metric": c.get("metric"),
                                    "basis": c.get("time_basis")}))
        elif c.get("type") == "scenario_assumption":
            out.append(Entity(id=f"assumption:{c['id']}", kind="assumption",
                              canonical=str(c.get("text") or "").strip(),
                              data={"scenario": c.get("scenario"), "value": c.get("value")}))
    return out


_EXCLUSION = re.compile(
    r"(?:,|\band\b|\bbut\b|^|\.)\s*(?:excluding|excludes|excluded|except(?:\s+for)?|"
    r"other than|not including|apart from)\s+(?P<np>[^.;,]+)", re.IGNORECASE)


def gate_exclusions(content: dict, population: str) -> tuple[list[str], list[str]]:
    """The populations a gate's own population clause excludes, resolved to
    the values modules declare as users.

    This is a SPLIT, never an inference: the clause is taken verbatim, and it
    resolves only when it matches a declared user value exactly (optionally
    without the unit noun the included half already uses). A clause that
    matches nothing is returned unresolved, so the gate blocks on its own
    under-specified wording rather than the law falling silent."""
    declared: dict[str, str] = {}
    for m in content.get("modules") or []:
        if isinstance(m, dict):
            for u in m.get("users") or []:
                if str(u).strip():
                    declared.setdefault(str(u).strip().lower(), str(u).strip())
    resolved, unresolved = [], []
    for m in _EXCLUSION.finditer(population or ""):
        clause = m.group("np").strip().rstrip(".")
        words = clause.split()
        candidates = [clause] + ([" ".join(words[:-1])] if len(words) > 1 else [])
        hit = next((declared[c.lower()] for c in candidates if c.lower() in declared), None)
        (resolved.append(hit) if hit else unresolved.append(clause))
    return resolved, unresolved


def _gate_entity(content: dict) -> list[Entity]:
    from app.pipeline import pilot_gate as _pg

    gate = (content.get("registry") or {}).get("pilot_gate")
    if not gate:
        return []
    excluded, unresolved = gate_exclusions(content, str(gate.get("population") or ""))
    return [Entity(id="gate:PG-01", kind="gate", canonical=_pg.canonical_sentence(gate),
                   data={"full_definition": _pg.full_definition(gate),
                         "assignment": _pg.assignment_sentence(gate),
                         "population": gate.get("population"), "geography": gate.get("geography"),
                         "population_excludes": excluded, "population_excludes_unresolved": unresolved,
                         "primary_metric": gate.get("primary_metric"), "target_value": gate.get("target_value"),
                         "change_kind": gate.get("change_kind"), "target_formula": gate.get("target_formula"),
                         "duration": gate.get("duration_value"), "guardrails": gate.get("guardrails")})]


def _concept_entities(content: dict) -> list[Entity]:
    out = []
    for key, label in (("concept_name", "concept:solution"), ("business_name", "concept:business")):
        name = str(content.get(key) or "").strip()
        if name and not any(e.canonical == name for e in out):
            out.append(Entity(id=label, kind="concept", canonical=name, data={"source": key}))
    return out


def build(content: dict) -> Canon:
    """The canonical registry for one engagement, from its structured content."""
    things = _NamedThings()
    _add_modules(things, content)
    _add_actors(things, content)
    _add_interfaces(things, content)
    _add_features(things, content)
    named = things.entities()
    modules = [e for e in named if e.kind == "module"]
    entities: list[Entity] = list(named)
    entities += _phase_entities(modules)
    entities += _dependency_entities(modules)
    entities += _fact_and_policy_entities(content)
    entities += _metric_and_assumption_entities(content)
    entities += _gate_entity(content)
    entities += _concept_entities(content)
    # a surface form claimed by two entities is dropped from BOTH indexes as a
    # mapping candidate — ambiguity is reported by resolve(), never guessed;
    # a duplicate id (two builders naming the same thing) keeps the first.
    seen_ids: set[str] = set()
    unique: list[Entity] = []
    for e in entities:
        if e.id in seen_ids:
            continue
        seen_ids.add(e.id)
        unique.append(e)
    return Canon(unique)
