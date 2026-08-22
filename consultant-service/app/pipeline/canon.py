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
                              data={**rec["data"], "roles": sorted(rec["roles"])}))
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
               data={"interface_kind": "queue", "audience": INTERNAL, "owner": "the pilot"})
    things.add(_pg.PILOT_CUSTOMER_FORM, "interface", id_hint="pilot-customer-form",
               data={"interface_kind": "form", "audience": CUSTOMER, "owner": "the pilot"})


def _phase_entities(modules: list[Entity]) -> list[Entity]:
    by_number: dict[int, list[str]] = {}
    parallel: list[str] = []
    for m in modules:
        n = m.data.get("phase_number")
        if isinstance(n, int):
            by_number.setdefault(n, []).append(m.canonical)
        elif m.data.get("workstream") == "parallel":
            parallel.append(m.canonical)
    out = [Entity(id=f"phase:{n}", kind="phase", canonical=f"Phase {n}",
                  data={"number": n, "modules": names})
           for n, names in sorted(by_number.items())]
    if parallel:
        out.append(Entity(id="phase:parallel", kind="phase", canonical="Parallel workstream",
                          data={"number": None, "modules": parallel}))
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
                           data={"interface_kind": "screen", "owner": owner,
                                 "audience": audience_of(users, str(screen))})
        for api in tech.get("apis") or []:
            if isinstance(api, dict) and api.get("name"):
                things.add(str(api["name"]), "interface",
                           data={"interface_kind": "api", "owner": owner, "audience": INTERNAL, "does": api.get("does")})
        for key in ("integrations", "integration_details"):
            for it in tech.get(key) or []:
                system = it.get("system") if isinstance(it, dict) else it
                if isinstance(system, str):
                    things.add(re.sub(r"\s*\([^)]*\)\s*$", "", system), "interface",
                               data={"interface_kind": "system", "owner": owner, "audience": INTERNAL})
        for it in spec.get("integrations") or []:
            if isinstance(it, str):
                things.add(re.sub(r"\s*\([^)]*\)\s*$", "", it), "interface",
                           data={"interface_kind": "system", "owner": owner, "audience": INTERNAL})
    checklists = content.get("checklists") if isinstance(content.get("checklists"), dict) else {}
    for form in checklists.get("forms") or []:
        if isinstance(form, dict) and form.get("name"):
            things.add(str(form["name"]), "interface",
                       data={"interface_kind": "form", "owner": "operations",
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
        out.append(Entity(id=f"policy:{subject}-period", kind="policy",
                          canonical=f"{n} days {origin} (your stated cycle)",
                          surfaces=(f"{n} days {origin}",),
                          data={"subject": subject, "value": n, "unit": "days", "event": origin,
                                "provenance": "client_stated",
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
                                    "provenance": c.get("provenance"), "metric": c.get("metric")}))
        elif c.get("type") == "scenario_assumption":
            out.append(Entity(id=f"assumption:{c['id']}", kind="assumption",
                              canonical=str(c.get("text") or "").strip(),
                              data={"scenario": c.get("scenario"), "value": c.get("value")}))
    return out


def _gate_entity(content: dict) -> list[Entity]:
    from app.pipeline import pilot_gate as _pg

    gate = (content.get("registry") or {}).get("pilot_gate")
    if not gate:
        return []
    return [Entity(id="gate:PG-01", kind="gate", canonical=_pg.canonical_sentence(gate),
                   data={"full_definition": _pg.full_definition(gate),
                         "assignment": _pg.assignment_sentence(gate),
                         "population": gate.get("population"), "geography": gate.get("geography"),
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
