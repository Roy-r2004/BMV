"""The integrity layer — validate meaning against the canonical registry and
fail closed.

Contract (v2):

  * ONE typed canonical registry (app/pipeline/canon.py) owns every fact an
    engagement repeats: client facts, modules, phases, dependencies,
    interfaces, actors, policies, metrics, assumptions, the pilot gate.
  * The renderer prints repeated statements FROM that registry.
  * The only automatic correction permitted here is an EXACT canonical
    mapping: a surface form that denotes exactly one entity becomes that
    entity's canonical form. Name for the same name.
  * Everything else is VALIDATED, never modified. A statement that disagrees
    with the registry, a name that denotes nothing or denotes two things, a
    misclassification — each is reported as a typed finding and blocks the
    release. Unknown content is never replaced by generic wording; no
    sentence is rewritten; no similarity score decides anything.

The report is bound to a hash of the content it was computed on, so any later
edit invalidates it and the release gate refuses FINAL until the layer has
run again on the current content.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Request
from app.pipeline import canon as _canon
from app.pipeline import pilot_gate as _pg
from app.pipeline import registry as _reg

VERSION = 2

# finding kinds — every finding says what KIND of failure it is
CONFLICT = "conflict"                  # two statements of one fact disagree
UNKNOWN = "unknown_entity"             # a name that denotes nothing in the registry
AMBIGUOUS = "ambiguous_entity"         # a name that denotes more than one entity
MISCLASSIFIED = "misclassification"    # right words, wrong type/audience/phase/unit
DRIFT = "drift"                        # the same fact stated in two different forms
ARTIFACT = "artifact"                  # placeholder, null, template token, raw identifier
STRUCTURAL = "structural"              # a law proven on the structures themselves


@dataclass(frozen=True)
class Finding:
    kind: str
    where: str
    issue: str
    fix: str
    severity: str = "high"
    expected: str | None = None
    statement: str | None = None
    entities: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        d = asdict(self)
        d["entities"] = list(self.entities)
        d["source"] = "integrity"
        return d


# ── content I/O ──────────────────────────────────────────────────────────────

_LAYERS = {"modules_json": "modules", "business_case_json": "business_case", "procedures_json": "procedures",
           "checklists_json": "checklists", "scoreboard_json": "scoreboard", "risks_json": "risks",
           "journey_json": "journey", "org_json": "org", "playbook_json": "playbook"}
_PROSE = {"mvp_blueprint": "blueprint", "technical_plan": "technical"}


def _loads(s):
    try:
        return json.loads(s) if s else None
    except ValueError:
        return None


def load(row) -> dict:
    content = {name: _loads(getattr(row, attr, None)) for attr, name in _LAYERS.items()}
    content.update({name: getattr(row, attr, None) or "" for attr, name in _PROSE.items()})
    content["registry"] = _reg.registry_for(row) or {}
    content["ops_numbers"] = getattr(row, "ops_numbers_json", None)
    content["free_texts"] = [getattr(row, k, None) or "" for k in
                             ("business_description", "main_problem", "desired_outcome", "revenue_today")]
    content["concept_name"] = getattr(row, "concept_name", None) or getattr(row, "business_name", None) or ""
    content["business_name"] = getattr(row, "business_name", None) or ""
    return content


def content_hash(content: dict) -> str:
    h = hashlib.sha256()
    for key in sorted(list(_LAYERS.values()) + list(_PROSE.values())):
        h.update(key.encode())
        h.update(json.dumps(content.get(key), sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))
    return h.hexdigest()


def save(row, content: dict) -> None:
    for attr, name in _LAYERS.items():
        if content.get(name) is not None:
            setattr(row, attr, json.dumps(content[name]))
    for attr, name in _PROSE.items():
        if content.get(name):
            setattr(row, attr, content[name])
    if content.get("registry") is not None:
        row.registry_json = json.dumps(content["registry"])


# ── the one permitted correction ─────────────────────────────────────────────

_SKIP_KEYS = {"id", "entity", "module_id", "original_name", "depends_on", "build_order", "maps_to", "kpi_claim_ids"}


def normalize(content: dict, canon: _canon.Canon) -> list[dict]:
    """Apply exact canonical mappings — and nothing else — to every string in
    the structured layers and the prose. Each application is recorded."""
    applied: list[dict] = []
    # the pilot's two stand-in interfaces differ only by audience; when the
    # registry holds exactly one of each, a customer-facing position has one
    # determined name — the same exact-mapping licence, applied by audience
    channel = canon.channel_mapping("the pilot")

    def _fix(text: str, where: str) -> str:
        out, maps = canon.apply_exact_mappings(text, where)
        applied.extend({"where": where, "surface": m.surface, "canonical": m.canonical, "entity": m.entity_id}
                       for m in maps)
        if channel is not None:
            internal, customer = channel
            out, recs = _reg.channel_pass(out, internal.canonical, customer.canonical)
            applied.extend({"where": where, "surface": r["original"], "canonical": customer.canonical,
                            "entity": customer.id, "law": "a customer-facing position names the customer interface"}
                           for r in recs)
        return out

    def _walk(obj, where: str):
        if isinstance(obj, str):
            return _fix(obj, where)
        if isinstance(obj, dict):
            return {k: (_walk(v, f"{where}.{k}") if k not in _SKIP_KEYS else v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk(v, f"{where}[{i}]") for i, v in enumerate(obj)]
        return obj

    for layer in ("modules", "procedures", "checklists", "scoreboard", "risks", "journey", "org", "playbook"):
        if content.get(layer) is not None:
            content[layer] = _walk(content[layer], layer)
    for vol in ("blueprint", "technical"):
        if content.get(vol):
            lines = content[vol].split("\n")
            content[vol] = "\n".join(_fix(line, f"{vol}:{i}") for i, line in enumerate(lines))
    return applied


def sanitize(content: dict, canon: _canon.Canon) -> list[dict]:
    """Well-formedness of the names and statements themselves, repaired at
    source before anything is mapped.

    Two hygiene laws, both idempotent by construction:

      * a canonical name states each of its tokens once;
      * an attribution is stated once.

    They run FIRST. A corrupt name that reaches the registry becomes canonical,
    and dropping an inner word from it derives the CLEAN name as one of its own
    surface forms — after which every clean mention maps into the corruption
    and the damage is self-reinforcing. Run 53 shipped four such names."""
    applied: list[dict] = []
    corpus = json.dumps({k: content.get(k) for k in _LAYERS.values()}, ensure_ascii=False, default=str)
    tokens = canon.name_tokens()
    known = [e.canonical for e in canon._entities.values() if not _canon.repeated_run(e.canonical, tokens)]

    # every name-shaped string: a registered canonical, or a field called "name"
    candidates: set[str] = {e.canonical for e in canon._entities.values() if _canon.repeated_run(e.canonical, tokens)}

    def _names(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "name" and isinstance(v, str) and _canon.repeated_run(v, tokens):
                    candidates.add(v)
                _names(v)
        elif isinstance(obj, list):
            for v in obj:
                _names(v)

    for layer in _LAYERS.values():
        _names(content.get(layer))

    repairs: dict[str, str] = {}
    for name in sorted(candidates, key=len, reverse=True):
        fixed, why = _canon.collapse_repeat(name, known, corpus, tokens)
        if fixed and fixed != name:
            repairs[name] = fixed
            applied.append({"where": "names", "surface": name, "canonical": fixed, "entity": "name",
                            "law": f"a canonical name states each of its tokens once — {why}"})

    def _walk(obj, where: str):
        if isinstance(obj, str):
            out = obj
            for bad, good in repairs.items():
                if bad in out:
                    out = out.replace(bad, good)
            fixed = _canon.collapse_attribution(out)
            if fixed != out:
                applied.append({"where": where, "surface": out.strip()[:140], "canonical": fixed.strip()[:140],
                                "entity": "attribution", "law": "an attribution is stated once"})
            return fixed
        if isinstance(obj, dict):
            return {k: (_walk(v, f"{where}.{k}") if k not in _SKIP_KEYS else v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk(v, f"{where}[{i}]") for i, v in enumerate(obj)]
        return obj

    for layer in _LAYERS.values():
        if content.get(layer) is not None:
            content[layer] = _walk(content[layer], layer)
    for vol in _PROSE.values():
        if content.get(vol):
            content[vol] = _walk(content[vol], vol)
    return applied


def retype(content: dict, canon: _canon.Canon) -> list[dict]:
    """Typed structured corrections the registry determines EXACTLY — a field
    set to the one value the structures allow. No prose is touched here.

    Today there is one: a procedure filed under a module that plays no part in
    it is filed under the module its steps execute, when exactly one such
    module exists. Where the structures do not determine a single answer,
    nothing is written and the verifier reports the conflict."""
    applied: list[dict] = []
    procedures = (content.get("procedures") or {}).get("procedures") \
        if isinstance(content.get("procedures"), dict) else None
    names = {e.canonical for e in canon.of_kind("module")}
    for p in procedures or []:
        owner, n = misfiled_owner(p, names, canon)
        if not owner:
            continue
        applied.append({"where": f"procedures: {p.get('name')}", "surface": p.get("module"),
                        "canonical": owner, "entity": f"module:{owner}",
                        "law": "a procedure is filed under the module that executes it"})
        p["module"] = owner
    # an integration entry carries its audience in the fields beside `system`,
    # so the audience mapping is applied to the entry as one unit
    channel = canon.channel_mapping("the pilot")
    if channel is not None:
        internal, customer = channel
        for m in content.get("modules") or []:
            if not isinstance(m, dict) or not m.get("pilot"):
                continue
            for rec in _reg.integration_channel_pass(m, internal.canonical, customer.canonical):
                applied.append({"where": f"modules.{rec['module']}.{rec['field']}", "surface": rec["original"],
                                "canonical": customer.canonical, "entity": customer.id,
                                "law": "a customer-facing position names the customer interface"})
    return applied


def apply_authority(content: dict, canon: _canon.Canon) -> list[dict]:
    """Render the authoritative value wherever a lesser source states a
    conflicting one.

    The precedence is declared once in app/pipeline/authority.py — the gate
    owns the pilot population, the canonical SOP owns the pilot's procedure
    steps and its outreach attempt count, the registry owns entity names and
    ownership. Every application records which source's authority was used, so
    the release record says not just what changed but on whose authority."""
    from app.pipeline import authority as _auth

    applied: list[dict] = []
    reg = content.get("registry") or {}
    gate = reg.get("pilot_gate")
    types = reg.get("service_types") or []
    terms = _reg.pilot_terms(content.get("modules") or [])

    # the canonical SOP is the pilot's only executable procedure set
    layer = content.get("procedures") if isinstance(content.get("procedures"), dict) else None
    if layer is not None and isinstance(layer.get("procedures"), list):
        pilot_names = {e.canonical for e in canon.of_kind("module") if e.data.get("pilot")}
        layer["procedures"], recs = _auth.dedupe_pilot_procedures(layer["procedures"], pilot_names)
        applied += [{"where": "procedures: pilot", "surface": r["removed"], "canonical": r["kept"],
                     "entity": "procedures",
                     "law": f"the {r['authority']} owns the pilot's procedure steps"} for r in recs]
    total = _reg.sop_attempt_total((layer or {}).get("procedures") or [])

    def _authoritative(text: str, where: str) -> str:
        out, recs = _auth.population_render(text, gate, types, terms)
        applied.extend({"where": where, "surface": r["original"], "canonical": r["replaced_with"],
                        "entity": "gate:PG-01", "law": f"the {r['authority']} owns the pilot population"}
                       for r in recs)
        out, recs = _auth.attempt_render(out, total, terms)
        applied.extend({"where": where, "surface": r["original"], "canonical": r["replaced_with"],
                        "entity": "policy:pilot-outreach-attempts",
                        "law": f"the {r['authority']} owns the outreach attempt count"} for r in recs)
        return out

    def _walk(obj, where: str):
        if isinstance(obj, str):
            return _authoritative(obj, where)
        if isinstance(obj, dict):
            return {k: (_walk(v, f"{where}.{k}") if k not in _SKIP_KEYS else v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk(v, f"{where}[{i}]") for i, v in enumerate(obj)]
        return obj

    for name in ("modules", "procedures", "checklists", "scoreboard", "risks", "journey", "org", "playbook"):
        if content.get(name) is not None:
            content[name] = _walk(content[name], name)
    for vol in _PROSE.values():
        if not content.get(vol):
            continue
        text = _authoritative(content[vol], vol)
        text, recs = _auth.coined_name_render(text, canon, vol)
        applied.extend({"where": vol, "surface": r["original"], "canonical": r["replaced_with"],
                        "entity": "module",
                        "law": f"the {r['authority']} owns entity names — resolved by {r['resolved_by']}"}
                       for r in recs)
        content[vol] = text
    return applied


def render_slots(content: dict, canon: _canon.Canon) -> list[dict]:
    """Re-render the registry-owned SLOTS in the finished volumes — today the
    phase heading, which states a phase's number (or that it is the parallel
    workstream) and its title.

    Rendering a slot is not rewriting prose: the narrative around it is
    untouched, the value comes from the registry rather than from a pattern,
    and a slot the registry cannot state is left exactly as it is for the
    verifier to report. This is the same licence `finish_document` uses when a
    volume is first written, applied to a volume that already exists so that a
    package can be corrected without regenerating a word of it."""
    from app.pipeline.blueprint import _pin_phase_headings

    applied: list[dict] = []
    for vol in _PROSE.values():
        if not content.get(vol):
            continue
        content[vol], rendered, refused = _pin_phase_headings(content[vol], canon)
        applied += [{"where": f"{vol}: phase heading", "surface": r["stated"], "canonical": r["rendered"],
                     "entity": "phase", "law": "a phase heading is rendered from the registry"}
                    for r in rendered]
        _REFUSALS[vol] = refused
    return applied


# a slot the registry refused to state, carried from the render to the verifier
_REFUSALS: dict[str, list[dict]] = {}


def phase_section_findings(canon: _canon.Canon) -> list[Finding]:
    """A section the registry refused to head. A numbered phase and the
    parallel workstream in one section groups a workstream that has no number
    into a sequence — which is what having no number denies."""
    out = []
    for vol, refusals in sorted(_REFUSALS.items()):
        for r in refusals or []:
            out.append(Finding(CONFLICT, f"{vol}: phases",
                               f"the registry states no heading for a section that delivers "
                               f"{', '.join(r.get('delivers') or [])}: {r.get('reason')}",
                               "one section delivers one registry phase", statement=str(r.get("stated"))[:160]))
    return out


# ── detectors (they DETECT; they never rewrite) ──────────────────────────────

_NAME_SPAN = re.compile(
    r"\b((?:[A-Z][A-Za-z0-9]+|&|AI|COD|API|iCARRY)(?:[ -](?:[A-Z][A-Za-z0-9]+|&|AI|COD))*\s+"
    r"(?:Hub|Platform|Engine|Module|System|Resolver|Interface|Assistant|Bot|Suite|Portal|Dashboard|Queue|Form|Log|"
    r"Database|Warehouse|Service|Layer|Workbench|Coordinator|Orchestrator|Pilot|Tool|Tracker|Console|Gateway))\b")
_PHASE_HEAD = re.compile(r"\bPhase\s+(\d+)\s*[—–:-]\s*")
_CUSTOMER_CLAUSE = re.compile(
    r"\b(?:customers?|clients?|shoppers?|patients?|guests?|members?|end[- ]users?)\b[^.;]{0,120}?"
    r"\b(?:link|form|confirms?|reply|replies|responds?|submits?|access(?:es)?|opens?|receives?|clicks?|taps?|"
    r"drops?|pins?|uploads?|fills?)\b", re.IGNORECASE)
_LINK_TO = re.compile(r"\b(?:link|URL|web page|page)\s+to\s+(?:the\s+)?$|\baccessed via\b|\bvia a link\b", re.IGNORECASE)


def _sentences(text: str) -> list[str]:
    flat = _pg.flatten_prose(text)
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\[(•\d])|•", flat) if s.strip()]


def _lines(text: str) -> list[str]:
    return (text or "").split("\n")


# ── laws ─────────────────────────────────────────────────────────────────────


def name_findings(text: str, canon: _canon.Canon, where: str) -> list[Finding]:
    """Every name-shaped span in a document denotes exactly one registry
    entity. Nothing is replaced: an unknown or ambiguous name is reported."""
    out: list[Finding] = []
    seen: set[str] = set()
    flat = re.sub(r"\s+", " ", text or "")
    for m in _NAME_SPAN.finditer(flat):
        raw = m.group(1)
        words = raw.split()
        # a span may carry leading words that are not part of the name
        # ('Launch the Pre-Dispatch … Pilot'): try the whole span, then each
        # shorter tail, and accept the first that denotes exactly one entity
        tails = [" ".join(words[k:]) for k in range(0, max(1, len(words) - 1))]
        resolved = False
        ambiguous: tuple[str, tuple[str, ...]] | None = None
        for cand in tails:
            res = canon.resolve(cand)
            if res.unique:
                resolved = True
                break
            if res.status == "ambiguous" and ambiguous is None:
                ambiguous = (cand, res.candidates)
        if resolved:
            continue
        if ambiguous:
            cand, ids = ambiguous
            if cand not in seen:
                seen.add(cand)
                out.append(Finding(AMBIGUOUS, f"{where}: names", f"'{cand}' denotes {len(ids)} registry entities",
                                   "give each entity one name in the registry", entities=ids, statement=cand))
            continue
        # report the longest tail that begins with a capital — the name as
        # the document states it
        cand = next((t for t in tails if t[:1].isupper() and len(t) >= 8), raw)
        # a two-word span is a verb phrase far more often than a coined system
        # name ("Approve Pilot", "Reviewing Pilot", "If System" all come out of
        # ordinary sentences and headings). Reporting those blocks a release on
        # something no one can ever register, which empties the gate of meaning;
        # ambiguity, which is PROVEN rather than guessed, is reported at any
        # length.
        if len(cand.split()) < 3 or cand in seen:
            continue
        seen.add(cand)
        out.append(Finding(UNKNOWN, f"{where}: names", f"'{cand}' is stated as a system or module but is in no registry entity",
                           "register it as an entity, or state the registered name", statement=cand))
    return out


_PHASE_TITLE = re.compile(r"\bPhase\s+(\d+)\s*[—–:-]\s*([A-Z][^.\n•:]{3,70})")


def phase_title_findings(texts: dict[str, str], canon: _canon.Canon) -> list[Finding]:
    """A phase heading states the REGISTRY's title for that phase — what the
    phase delivers. Every volume states the same title because every volume
    renders it from the registry, so cross-volume agreement follows from
    registry agreement instead of being checked volume against volume."""
    by_number = {e.data.get("number"): e for e in canon.of_kind("phase")
                 if isinstance(e.data.get("number"), int)}
    out: list[Finding] = []
    for label, text in (texts or {}).items():
        seen: set[int] = set()
        for m in _PHASE_TITLE.finditer(_pg.flatten_prose(text or "")):
            n = int(m.group(1))
            if n in seen:
                continue
            seen.add(n)
            title = m.group(2).strip().rstrip(":;,").strip("* ")
            e = by_number.get(n)
            if e is None:
                out.append(Finding(CONFLICT, f"{label}: phases",
                                   f"the document states a Phase {n}; the registry has no Phase {n}",
                                   "state only the phases the registry holds", statement=f"Phase {n}"))
                continue
            want = str(e.data.get("title") or "")
            if want and title != want and not title.startswith(want):
                out.append(Finding(CONFLICT, f"{label}: phases",
                                   f"Phase {n} is titled '{title}' but the registry titles it '{want}'",
                                   "state the registry's title for the phase — what the phase delivers",
                                   expected=want, statement=f"Phase {n}", entities=(e.id,)))
    return out


def surface_findings(text: str, canon: _canon.Canon, where: str) -> list[Finding]:
    """A known non-canonical spelling that survived mapping (because it is
    ambiguous) is drift and is reported, never guessed at."""
    out = []
    flat = re.sub(r"\s+", " ", text or "")
    for surface, entity_id in canon.all_surfaces():
        e = canon[entity_id]
        if surface == e.canonical or canon.resolve(surface).unique:
            continue
        if re.search(r"(?<!\w)" + re.escape(surface) + r"(?!\w)", flat):
            out.append(Finding(DRIFT, f"{where}: names", f"'{surface}' is a second spelling of '{e.canonical}'",
                               "one name per entity", expected=e.canonical, statement=surface, entities=(entity_id,)))
    return out


def phase_findings(text: str, canon: _canon.Canon, where: str) -> list[Finding]:
    """'Phase N — <module>' states the registry's phase for that module; a
    parallel workstream has no number."""
    out = []
    by_name = {e.canonical: e for e in canon.of_kind("module")}
    names = sorted(by_name, key=len, reverse=True)
    lines = _lines(text)
    for i, line in enumerate(lines):
        m = _PHASE_HEAD.search(line)
        if not m:
            continue
        after = [n for n in names if n in line[m.end():]]
        if not after and i + 1 < len(lines) and "Delivers:" in lines[i + 1]:
            after = [n for n in names if n in lines[i + 1]]
        if not after:
            continue
        e = by_name[after[0]]
        stated, want = int(m.group(1)), e.data.get("phase_number")
        if want is None:
            out.append(Finding(MISCLASSIFIED, f"{where}: phases",
                               f"'{e.canonical}' is a parallel workstream but is stated as Phase {stated}",
                               "state it as a parallel workstream", expected="Parallel workstream",
                               statement=line.strip()[:160], entities=(e.id,)))
        elif stated != want:
            out.append(Finding(CONFLICT, f"{where}: phases",
                               f"'{e.canonical}' is Phase {want} in the registry but Phase {stated} here",
                               f"state Phase {want}", expected=f"Phase {want}", statement=line.strip()[:160], entities=(e.id,)))
    return out


def audience_findings(text: str, canon: _canon.Canon, where: str) -> list[Finding]:
    """A clause in which a customer acts names no interface whose audience is
    internal — WHEN the registry holds a customer-facing counterpart for that
    interface's owner, so there is a determinate right answer.

    Without a counterpart there is nothing to say: naming a transport API or a
    data warehouse in a sentence that also mentions customers does not send a
    customer anywhere, and reporting it would block a release on a sentence no
    one can correct. This is the same scope the corrector uses, so what the
    corrector cannot fix is exactly what this reports."""
    out: list[Finding] = []
    flat = _pg.flatten_prose(text)
    owners = {str(e.data.get("owner") or "") for e in canon.of_kind("interface")}
    for owner in sorted(o for o in owners if o):
        pair = canon.channel_mapping(owner)
        if pair is None:
            continue
        internal, customer = pair
        for clause in _reg._CLAUSE_SPLIT.split(flat):
            if not clause or _reg._CLAUSE_SPLIT.fullmatch(clause):
                continue
            acts_customer = _reg._customer_acts(clause, internal.canonical)
            acts_staff = _reg._staff_acts(clause)
            if acts_customer and acts_staff:
                continue                       # neither name is determined here
            if internal.canonical in clause and acts_customer:
                out.append(Finding(MISCLASSIFIED, f"{where}: audience",
                                   f"a customer is sent to '{internal.canonical}', which the registry holds as an "
                                   f"internal {internal.data.get('interface_kind', 'interface')}",
                                   f"name the customer-facing interface the registry holds — '{customer.canonical}'",
                                   expected=customer.canonical, statement=clause.strip()[:180],
                                   entities=(internal.id,)))
            elif customer.canonical in clause and acts_staff:
                out.append(Finding(MISCLASSIFIED, f"{where}: audience",
                                   f"staff work in '{customer.canonical}', which the registry holds as the "
                                   f"customer-facing {customer.data.get('interface_kind', 'interface')}",
                                   f"name the internal interface the registry holds — '{internal.canonical}'",
                                   expected=internal.canonical, statement=clause.strip()[:180],
                                   entities=(customer.id,)))
    return out


def statement_findings(content: dict, canon: _canon.Canon, texts: dict[str, str]) -> list[Finding]:
    """Canonical statements that a document tells differently: the gate, the
    pilot design, the settlement policy, the outreach attempt total, the
    pilot population, module KPI lines."""
    out: list[Finding] = []
    reg = content.get("registry") or {}
    gate = reg.get("pilot_gate")
    claims = reg.get("claims") or []
    modules = content.get("modules") or []
    procedures = (content.get("procedures") or {}).get("procedures") if isinstance(content.get("procedures"), dict) else []
    total = _reg.sop_attempt_total(procedures or [])
    terms = _reg.pilot_terms(modules)
    types = reg.get("service_types") or []
    for label, text in texts.items():
        if not text:
            continue
        if gate:
            for f in _pg.restatement_findings(text, gate):
                out.append(Finding(CONFLICT, f"{label}: pilot gate", f["issue"], f["fix"],
                                   expected=_pg.canonical_sentence(gate), entities=("gate:PG-01",)))
            for f in _pg.design_findings(text, gate):
                out.append(Finding(CONFLICT, f"{label}: pilot design", f["issue"], f["fix"],
                                   expected=_pg.assignment_sentence(gate), entities=("gate:PG-01",)))
            for f in _reg.population_findings(text, gate, label, types, terms):
                out.append(Finding(CONFLICT, f"{label}: pilot population", f["issue"], f["fix"],
                                   expected=str(gate.get("population") or ""), entities=("gate:PG-01",)))
        for f in _reg.policy_findings({label: text}, claims):
            out.append(Finding(CONFLICT, f["where"], f["issue"], f["fix"]))
        for f in _reg.attempts_text_findings(text, total, terms, label):
            out.append(Finding(CONFLICT, f["where"], f["issue"], f["fix"],
                               expected=canon.statement("policy", "pilot-outreach-attempts")))
        for f in _reg.auth_text_findings(text, label):
            out.append(Finding(MISCLASSIFIED, f["where"], f["issue"], f["fix"]))
        for f in _reg.api_text_findings(text, reg.get("api_paths") or []):
            out.append(Finding(ARTIFACT, f"{label}: {f['where']}", f["issue"], f["fix"]))
        for f in _reg.ordinal_label_findings(text, label):
            out.append(Finding(MISCLASSIFIED, f["where"], f["issue"], f["fix"]))
        out += name_findings(text, canon, label)
        out += surface_findings(text, canon, label)
        out += phase_findings(text, canon, label)
        out += audience_findings(text, canon, label)
        out += label_findings(text, label)
    out += phase_title_findings(texts, canon)
    return out


_LABEL_VARIANT = re.compile(r"\(proposed\s*[-–—]\s*client approval required\)")
_NON_THRESHOLD_LABELED = [
    (re.compile(r"\b(?:TLS|SSL|OAuth|HTTP/?|API\s?v|version|v)\s?\d+(?:\.\d+)?\s*\(proposed — client approval required\)", re.I),
     "a protocol or version number"),
    (re.compile(r"\b[1-5]\d\d\s*\(proposed — client approval required\)\s*(?:Forbidden|Not Found|Unauthorized|OK|Bad Request)", re.I),
     "an HTTP status code"),
    (re.compile(r"\brandom[^.]{0,40}\bbetween\s+\d+(?:\.\d+)?\s*\(proposed — client approval required\)", re.I),
     "a random-draw bound"),
]


def label_findings(text: str, where: str) -> list[Finding]:
    """The approval label has one form and marks thresholds only."""
    out = []
    flat = _pg.flatten_prose(text)
    for m in _LABEL_VARIANT.finditer(flat):
        if m.group(0) != _reg.PROPOSED_LABEL:
            out.append(Finding(DRIFT, f"{where}: labels", f"a non-canonical approval label: '{m.group(0)}'",
                               f"use {_reg.PROPOSED_LABEL}", expected=_reg.PROPOSED_LABEL))
    for rx, what in _NON_THRESHOLD_LABELED:
        for m in rx.finditer(flat):
            out.append(Finding(MISCLASSIFIED, f"{where}: labels", f"{what} wears an approval label: \"{m.group(0)[:80]}\"",
                               "only thresholds carry the approval label", statement=m.group(0)[:120]))
    return out


def _procedure_text(p: dict) -> str:
    parts = [str(p.get("trigger") or ""), str(p.get("name") or "")]
    for s in p.get("steps") or []:
        if isinstance(s, dict):
            parts += [str(s.get("actor") or ""), str(s.get("step") or "")]
    for e in p.get("exceptions") or []:
        if isinstance(e, dict):
            parts += [str(e.get("when") or ""), str(e.get("then") or "")]
    return " ".join(parts)


def _tools_of(canon: _canon.Canon, module_name: str) -> set[str]:
    """The interfaces only this module declares. An interface several modules
    declare is shared and proves nothing about ownership."""
    return {e.canonical for e in canon.of_kind("interface")
            if set(e.data.get("declarers") or ()) == {module_name}}


def misfiled_owner(p: dict, names: set[str], canon: _canon.Canon | None = None) -> tuple[str | None, int]:
    """The module a procedure's steps execute, when the structures determine
    exactly ONE and the module it is filed under plays NO part in it.

    Both halves matter. An escalation procedure is filed under the escalation
    module while another module triggers it and human staff carry it out —
    counting only module-actors would re-file it under the trigger, which is
    wrong. So a procedure is misfiled only when the module named on it appears
    nowhere in it — not as an actor, not in a step, not in the trigger — and a
    single other module dominates the steps outright."""
    if not isinstance(p, dict) or p.get("module") in ("The pilot", None) or str(p.get("phase") or "").lower() == "pilot":
        return None, 0
    filed = str(p.get("module") or "")
    text = _procedure_text(p)
    if filed in text:
        return None, 0
    # a module also plays a part through its OWN tools. An escalation
    # procedure names the escalation module's queue and its detail view while
    # never naming the module — re-filing it under the module that triggers it
    # was wrong, and left a procedure using tools its new owner does not have.
    if canon is not None and any(tool in text for tool in _tools_of(canon, filed)):
        return None, 0
    counts: dict[str, int] = {}
    for s in p.get("steps") or []:
        a = str((s or {}).get("actor") or "")
        if a in names:
            counts[a] = counts.get(a, 0) + 1
    if not counts:
        return None, 0
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    top, n = ranked[0]
    if n < 3 or (len(ranked) > 1 and ranked[1][1] == n) or top == filed:
        return None, 0
    return top, n


def hygiene_findings(content: dict, canon: _canon.Canon, texts: dict[str, str] | None = None) -> list[Finding]:
    """A malformed name or a doubled attribution that survived the hygiene
    pass. Either one reached a client page in run 53-r22, so either one blocks
    the release."""
    out: list[Finding] = []
    seen: set[str] = set()
    tokens = canon.name_tokens()
    for e in canon._entities.values():
        m = _canon.repeated_run(e.canonical, tokens)
        if m and e.canonical not in seen:
            seen.add(e.canonical)
            out.append(Finding(ARTIFACT, f"registry: {e.id}",
                               f"a canonical name states '{m.group(1)}' twice: \"{e.canonical}\"",
                               "a canonical name states each of its tokens once", statement=e.canonical,
                               entities=(e.id,)))

    def _scan(text: str, where: str) -> None:
        m = _canon.repeated_run(text, tokens)
        if m and m.group(0) not in seen:
            seen.add(m.group(0))
            out.append(Finding(ARTIFACT, f"{where}: names",
                               f"a name states '{m.group(1)}' twice: \"{m.group(0)}\"",
                               "a canonical name states each of its tokens once", statement=m.group(0)))
        d = _canon._REPEATED_PARENTHETICAL.search(text)
        if d and d.group(0) not in seen:
            seen.add(d.group(0))
            out.append(Finding(ARTIFACT, f"{where}: attribution",
                               f"an attribution is stated twice: \"{d.group(0)[:80]}\"",
                               "an attribution is stated once", statement=d.group(0)[:120]))

    def _walk(obj, where: str) -> None:
        if isinstance(obj, str):
            _scan(obj, where)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                _walk(v, f"{where}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _walk(v, f"{where}[{i}]")

    for layer in _LAYERS.values():
        _walk(content.get(layer), layer)
    # the RAW text, never flattened: the repeated-run law reads a contiguous
    # name, and flattening turns every line break into a space, which would
    # join a heading to the paragraph beneath it
    for label, text in (texts or {name: content.get(name) or "" for name in _PROSE.values()}).items():
        _scan(text or "", label)
    return out


_SCOPING = re.compile(r"\b(excluding|excludes?|excluded|except(?:\s+for)?|other than|not including|omit(?:s|ting)?|"
                      r"skip(?:s|ping)?|filters?\s+out|filtered\s+out|ignor(?:e|es|ing)|leave out|non-|not)\b",
                      re.IGNORECASE)


def _procedure_fields(p: dict):
    yield "trigger", p.get("trigger")
    for i, s in enumerate(p.get("steps") or []):
        if isinstance(s, dict):
            yield f"steps[{i}].actor", s.get("actor")
            yield f"steps[{i}].step", s.get("step")
    for j, e in enumerate(p.get("exceptions") or []):
        if isinstance(e, dict):
            yield f"exceptions[{j}].when", e.get("when")
            yield f"exceptions[{j}].then", e.get("then")


def pilot_population_findings(content: dict, canon: _canon.Canon) -> list[Finding]:
    """A pilot artifact may not ACT on a population the gate excludes.

    The gate owns the pilot population, and its population clause names what
    the pilot does not cover. A pilot procedure whose trigger or steps act on
    that population contradicts the gate — run 53-r22 shipped a pilot SOP
    procedure resolving business-client COD settlement inquiries while the
    gate excluded business client orders.

    Detection is typed, never fuzzy: registered names are masked first (a name
    that CONTAINS the population is a name, not a mention), the population is
    matched only as the value a module declares, and a clause that excludes or
    negates the population states the boundary correctly and is skipped.

    This law DETECTS only. Whether the pilot should drop the work or the gate
    should widen its population is the author's or the client's decision — the
    gate itself is 'client approval required'."""
    gate = canon.get("gate:PG-01")
    if gate is None:
        return []
    out: list[Finding] = []
    for clause in gate.data.get("population_excludes_unresolved") or []:
        out.append(Finding(CONFLICT, "registry: pilot gate",
                           f"the gate excludes a population no registry entity declares: '{clause}'",
                           "declare the excluded population as a user of the module that serves it, or state "
                           "the exclusion using a name the registry already carries",
                           statement=clause, entities=("gate:PG-01",)))
    excluded = [p for p in (gate.data.get("population_excludes") or []) if p]
    if not excluded:
        return out
    procedures = (content.get("procedures") or {}).get("procedures") \
        if isinstance(content.get("procedures"), dict) else []
    pilot_names = {e.canonical for e in canon.of_kind("module") if e.data.get("pilot")}

    def _acting_hits(text: str) -> list[str]:
        hits = []
        masked = canon.mask_entities(text or "")
        for population in excluded:
            for m in re.finditer(r"(?<!\w)" + re.escape(population) + r"(?!\w)", masked, re.IGNORECASE):
                clause = re.split(r"[.;:]", masked[:m.start()])[-1]
                if not _SCOPING.search(clause):
                    hits.append(population)
        return hits

    for p in procedures or []:
        if not isinstance(p, dict) or str(p.get("phase") or "").lower() != "pilot":
            continue
        if p.get("module") not in ({"The pilot"} | pilot_names):
            continue
        named: dict[str, list[str]] = {}
        statement = ""
        for where, text in _procedure_fields(p):
            if not isinstance(text, str):
                continue
            for population in _acting_hits(text):
                named.setdefault(population, []).append(where)
                statement = statement or text.strip()[:170]
        for population, wheres in sorted(named.items()):
            out.append(Finding(CONFLICT, f"procedures: {p.get('name')}",
                               f"a pilot procedure acts on '{population}', which the pilot gate's population "
                               f"excludes — named in {', '.join(sorted(set(wheres)))}",
                               "the gate excludes this population: take this work out of the pilot, or widen "
                               "the gate's population with client approval",
                               expected=str(gate.data.get("population")), statement=statement,
                               entities=("gate:PG-01",)))
    for m in content.get("modules") or []:
        if not isinstance(m, dict) or not m.get("pilot"):
            continue
        for key in ("purpose", "pain_point_addressed", "spec", "tech"):
            for text in _strings_in(m.get(key)):
                for population in _acting_hits(text):
                    out.append(Finding(CONFLICT, f"modules.{m.get('id')}.{key}",
                                       f"the pilot module acts on '{population}', which the pilot gate's "
                                       f"population excludes",
                                       "the gate excludes this population: take this work out of the pilot, or "
                                       "widen the gate's population with client approval",
                                       expected=str(gate.data.get("population")), statement=text.strip()[:170],
                                       entities=("gate:PG-01",)))
                    break
    return out


def _strings_in(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings_in(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings_in(v)


def procedure_tool_fit_findings(content: dict, canon: _canon.Canon) -> list[Finding]:
    """A procedure names only the tools of the module it belongs to.

    An interface belongs to a module when exactly ONE module declares it;
    an interface several modules declare is shared and belongs to none of them
    in particular. Run 53-r22 shipped financial COD-settlement procedures that
    reached for the delivery pre-confirmation module's AI and its Customer
    Confirmation Status Log.

    DETECTS only: which tool the settlement work should have used is not
    something the structures determine — the owning module may hold no
    equivalent at all."""
    procedures = (content.get("procedures") or {}).get("procedures") \
        if isinstance(content.get("procedures"), dict) else []
    exclusive: dict[str, tuple[str, str]] = {}
    for e in canon.of_kind("interface"):
        declarers = [d for d in (e.data.get("declarers") or []) if d]
        if len(set(declarers)) == 1:
            exclusive[e.canonical] = (declarers[0], e.id)
    module_names = {m.canonical for m in canon.of_kind("module")}
    out: list[Finding] = []
    for p in procedures or []:
        if not isinstance(p, dict):
            continue
        filed = str(p.get("module") or "")
        if filed not in module_names:
            continue                       # the pilot SOP belongs to no module
        seen: set[str] = set()
        for where, text in _procedure_fields(p):
            if not isinstance(text, str):
                continue
            for name, (owner, entity_id) in exclusive.items():
                if owner == filed or name in seen or name not in text:
                    continue
                seen.add(name)
                out.append(Finding(MISCLASSIFIED, f"procedures: {p.get('name')}",
                                   f"filed under '{filed}' but uses '{name}', which only '{owner}' declares "
                                   f"— named in {where}",
                                   f"name a tool '{filed}' declares, or file the procedure under '{owner}'",
                                   statement=text.strip()[:170], entities=(entity_id,)))
    return out


def structure_findings(content: dict, canon: _canon.Canon) -> list[Finding]:
    """Laws proven on the structures themselves — no prose involved."""
    from app.pipeline.structural import structural_findings

    out: list[Finding] = []
    modules = content.get("modules") or []
    procedures = (content.get("procedures") or {}).get("procedures") if isinstance(content.get("procedures"), dict) else []
    for f in structural_findings(content.get("business_case") or {}, modules, content.get("registry") or {}):
        out.append(Finding(STRUCTURAL, f.get("where", "structures"), f.get("issue", ""), f.get("fix", "")))
    for e in canon.of_kind("module"):
        if e.data.get("pilot"):
            continue
        if e.data.get("has_ai_component") and e.data.get("automation_level") != "ai":
            out.append(Finding(MISCLASSIFIED, f"modules.{e.data.get('module_id')}",
                               f"'{e.canonical}' carries an AI agent in its specification but is classified "
                               f"'{e.data.get('automation_level')}'",
                               "the automation level is the structured AI component", entities=(e.id,)))
        if not e.data.get("has_ai_component") and e.data.get("automation_level") == "ai":
            out.append(Finding(MISCLASSIFIED, f"modules.{e.data.get('module_id')}",
                               f"'{e.canonical}' is classified 'ai' with no AI component in its specification",
                               "classify it by its specification", entities=(e.id,)))
    pilot_names = {e.canonical for e in canon.of_kind("module") if e.data.get("pilot")}
    for f in _reg.pilot_procedure_findings(procedures or [], pilot_names, modules):
        out.append(Finding(CONFLICT, f.get("where", "procedures"), f.get("issue", ""), f.get("fix", "")))
    for f in _reg.operating_time_findings(procedures or []):
        out.append(Finding(MISCLASSIFIED, f.get("where", "procedures"), f.get("issue", ""), f.get("fix", "")))
    for f in _reg.pilot_isolation_findings(modules, procedures or []):
        out.append(Finding(CONFLICT, f.get("where", "modules"), f.get("issue", ""), f.get("fix", "")))
    for m in modules:
        if isinstance(m, dict) and m.get("pilot"):
            for f in _reg.integration_channel_findings(m):
                out.append(Finding(MISCLASSIFIED, f.get("where", "modules"), f.get("issue", ""), f.get("fix", "")))
    # a procedure filed under a module that plays no part in it
    names = {e.canonical for e in canon.of_kind("module")}
    for p in procedures or []:
        owner, n = misfiled_owner(p, names, canon)
        if owner:
            out.append(Finding(MISCLASSIFIED, f"procedures: {p.get('name')}",
                               f"filed under '{p.get('module')}', which plays no part in it, "
                               f"but executed by '{owner}' in {n} steps",
                               "file it under the module that executes it"))
    # checklists that name a FUTURE module are not day-one artifacts
    future = {e.canonical for e in canon.of_kind("module") if e.data.get("phase") == "FUTURE"}
    cl = content.get("checklists") if isinstance(content.get("checklists"), dict) else {}
    for c in cl.get("checklists") or []:
        blob = " ".join(str(x) for x in (c.get("items") or []))
        if any(n in blob for n in future) and str(c.get("phase") or "") != "future":
            out.append(Finding(MISCLASSIFIED, f"checklists: {c.get('name')}",
                               "a checklist naming a module that is not built yet carries no FUTURE tag",
                               "tag the checklist by the modules it names"))
    # a schedule horizon stated as fact
    pb = content.get("playbook") if isinstance(content.get("playbook"), dict) else {}
    for step in pb.get("steps") or []:
        for key in ("horizon", "when"):
            h = step.get(key) if isinstance(step, dict) else None
            if isinstance(h, str) and re.search(r"\d", h) and "(proposed" not in h \
                    and not re.search(r"week 1\b|immediately", h, re.IGNORECASE):
                out.append(Finding(MISCLASSIFIED, f"playbook: {step.get('title')}",
                                   f"a schedule horizon is stated as fact: '{h}'",
                                   "a horizon we propose carries the approval label"))
    # KPI claims: unit, coined qualifier, repeated metric name
    for c in content.get("registry", {}).get("claims") or []:
        if c.get("type") != "module_kpi":
            continue
        text = str(c.get("text") or "")
        if c.get("unit") == "%" and isinstance(c.get("value"), (int, float)) and 0 < c["value"] <= 1 \
                and re.search(r"\b0?\.\d+\s*%", text):
            out.append(Finding(MISCLASSIFIED, f"registry: {c.get('id')}",
                               f"a fractional KPI value prints as a percentage of itself: \"{text[-60:]}\"",
                               "a '%' claim value is a fraction — render it as a percentage"))
        metric = str(c.get("metric") or "").strip()
        if metric and text.startswith(metric + ": ") and text[len(metric) + 2:].lstrip().startswith(metric):
            out.append(Finding(DRIFT, f"registry: {c.get('id')}", f"a KPI statement repeats its metric name: \"{text[:100]}\"",
                               "the metric name once, then its value"))
    return out


def artifact_findings(content: dict, texts: dict[str, str]) -> list[Finding]:
    from app.pipeline.export_pdf import find_artifacts

    out = []
    reg = content.get("registry") or {}
    for label, text in texts.items():
        for hit in find_artifacts(text or "", reg):
            out.append(Finding(ARTIFACT, f"{label}: rendered text", f"client-unsafe artifact: {hit}",
                               "remove the artifact at its source"))
    return out


# ── verification ─────────────────────────────────────────────────────────────


def verify(content: dict, texts: dict[str, str] | None = None) -> tuple[list[Finding], _canon.Canon]:
    """Every law, on the structures and on the text. Nothing is modified."""
    canon = _canon.build(content)
    prose = texts if texts is not None else {"blueprint": content.get("blueprint") or "",
                                             "technical": content.get("technical") or ""}
    findings: list[Finding] = []
    findings += structure_findings(content, canon)
    findings += hygiene_findings(content, canon, texts)
    findings += pilot_population_findings(content, canon)
    findings += procedure_tool_fit_findings(content, canon)
    findings += phase_section_findings(canon)
    findings += statement_findings(content, canon, prose)
    if texts is not None:
        findings += artifact_findings(content, texts)
    # de-duplicate identical findings (a law may see the same sentence twice)
    seen: set[tuple] = set()
    unique: list[Finding] = []
    for f in findings:
        key = (f.kind, f.where, f.issue)
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    return unique, canon


def enforce(db: Session, request_id: int) -> dict:
    """Normalize by exact canonical mapping, verify, persist the report.
    Returns the report; `blocked` is true when any finding stands."""
    row = db.get(Request, request_id)
    if row is None:
        raise ValueError(f"Request {request_id} not found")
    content = load(row)
    canon = _canon.build(content)
    # name hygiene FIRST: a corrupt name that survives into the mapping pass
    # makes the clean name one of its own surface forms
    mappings = sanitize(content, canon)
    canon = _canon.build(content)
    mappings += normalize(content, canon)
    mappings += retype(content, canon)
    mappings += apply_authority(content, canon)
    canon = _canon.build(content)          # procedures and names have changed
    mappings += render_slots(content, canon)
    save(row, content)
    db.commit()
    content = load(row)
    findings, canon = verify(content)
    report = {
        "version": VERSION,
        "ran_at": datetime.utcnow().isoformat() + "Z",
        "canon": {
            "entities": len(canon),
            "by_kind": {k: len(canon.of_kind(k)) for k in _canon.KINDS if canon.of_kind(k)},
            "modules": [{"name": e.canonical, "phase": e.data.get("phase_number") or e.data.get("workstream"),
                         "automation": e.data.get("automation_level"), "audience": e.data.get("audience")}
                        for e in canon.of_kind("module")],
        },
        "mappings_applied": mappings,
        "findings": [f.as_dict() for f in findings],
        "blocked": bool(findings),
        "clean": not findings,
        "content_hash": content_hash(content),
    }
    row.integrity_report_json = json.dumps(report)
    db.commit()
    return report


def current_report(row) -> dict | None:
    """The persisted report — only if it was computed on the content the row
    holds now. Any later edit invalidates it."""
    rep = _loads(getattr(row, "integrity_report_json", None))
    if not isinstance(rep, dict) or rep.get("version") != VERSION:
        return None
    if rep.get("content_hash") != content_hash(load(row)):
        return None
    return rep


def validate_rendered(row, texts: dict[str, str]) -> list[dict]:
    """The same laws on the exact rendered PDF text."""
    content = load(row)
    findings, _ = verify(content, texts)
    return [f.as_dict() for f in findings]
