"""The integrity layer — ONE registry-driven pass that validates and corrects
AI-generated structured content before anything is rendered or released.

What it guards against, generically (no client vocabulary, no sentence patches):

  semantic contradictions — the same fact told two ways (phase numbers, attempt
      counts, policy periods, the pilot design, automation class, tooling);
  cross-volume drift  — a registry fact restated differently in another volume
      (module names, aliases, abbreviations, unregistered product names);
  incorrect rewrites  — every correction is scoped and guarded: a change that
      touches text outside its scope, or rewrites a sentence beyond the guard's
      similarity floor without substituting a registered canonical sentence,
      is REJECTED and logged, never applied;
  misclassified content — automation level vs the structured AI component,
      customer-facing vs internal tooling, deadline vs cadence, ordinal /
      protocol / status code vs threshold, day-one vs FUTURE checklists, a
      procedure filed under the wrong module, a KPI unit.

Contract:
  enforce(db, request_id) -> report    corrects the row's content in place and
                                        persists integrity_report_json
  validate_rendered(row, texts) -> findings   the same laws on exact PDF text
  release_status() refuses FINAL without a CURRENT, CLEAN report (content hash).

Every correction is recorded (what, where, original, replacement, rule); every
rejected rewrite is recorded with the reason. Facts come from the registry.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Request
from app.pipeline import pilot_gate as _pg
from app.pipeline import registry as _reg

VERSION = 1
LABEL = _reg.PROPOSED_LABEL

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
    content["free_texts"] = [getattr(row, k, None) or "" for k in ("business_description", "main_problem", "desired_outcome", "revenue_today")]
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
    row.registry_json = json.dumps(content["registry"])


# ── facts from the registry ──────────────────────────────────────────────────

def _humanize(mid: str) -> str:
    return " ".join(w.capitalize() for w in re.split(r"[-_]+", str(mid or "")) if w)


def _abbreviations(name: str) -> set[str]:
    """Shorter forms a writer drops inner words into: 'AI Delivery
    Pre-Confirmation Engine' -> 'AI Pre-Confirmation Engine'."""
    words = name.split()
    out = set()
    if len(words) >= 4:
        for i in range(1, len(words) - 1):
            out.add(" ".join(words[:i] + words[i + 1:]))
        for i in range(1, len(words) - 2):
            out.add(" ".join(words[:i] + words[i + 2:]))
    return {a for a in out if len(a.split()) >= 2}


def _suffix_forms(name: str) -> list[tuple[str, str]]:
    """Forms that drop the first one or two words ('AI COD Settlement
    Inquiry Resolver' -> 'Settlement Inquiry Resolver'), each with the word
    that must NOT precede it (else it is the full name itself)."""
    words = name.split()
    out = []
    for k in (1, 2):
        if len(words) - k >= 3:
            out.append((" ".join(words[k:]), words[k - 1]))
    return out


def _alias_pattern(alias: str, not_after: str | None = None) -> "re.Pattern[str]":
    # a name inside quotes is still the name ('Support Escalation Handover');
    # a possessive after it is fine; a suffix form is not the full name
    guard = f"(?<!{re.escape(not_after)} )" if not_after else ""
    return re.compile(guard + r"(?<!\w)" + re.escape(alias) + r"(?!\w)")


def derive_facts(content: dict) -> dict:
    reg = content.get("registry") or {}
    modules = content.get("modules") or []
    reg_mods = {m.get("id"): m for m in reg.get("modules") or []}
    table = []
    for m in modules:
        if not isinstance(m, dict):
            continue
        rm = reg_mods.get(m.get("id"), {})
        cf = str(m.get("client_facing_name") or rm.get("client_facing_name") or m.get("name") or "")
        aliases = {str(x) for x in (m.get("name"), m.get("original_name"), rm.get("alias"), _humanize(m.get("id"))) if x and str(x) != cf}
        aliases |= _abbreviations(cf)
        users = " ".join(str(u) for u in (m.get("users") or []))
        table.append({
            "id": m.get("id"), "name": cf, "aliases": sorted(aliases, key=len, reverse=True),
            "pilot": bool(m.get("pilot")), "phase": rm.get("phase") or m.get("phase"),
            "phase_number": rm.get("phase_number", m.get("phase_number")), "workstream": rm.get("workstream", m.get("workstream")),
            "has_ai": bool(((m.get("spec") or {}).get("ai")) or ((m.get("tech") or {}).get("ai_agent"))),
            "automation_level": m.get("automation_level"),
            "customer_facing": bool(_reg._CUSTOMER_USER.search(users)) and not _reg._STAFF_ONLY.search(users),
        })
    procedures = (content.get("procedures") or {}).get("procedures") if isinstance(content.get("procedures"), dict) else []
    known_systems: set[str] = set()

    _NAME_KEY = re.compile(r"screen|system|name|entity|integration|tool|form|queue|dashboard|title", re.IGNORECASE)
    _NAME_VALUE = re.compile(r"^[A-Za-z][\w&'()/ .-]{3,80}$")

    def _collect(obj, key=None):
        # a declared name: any string under a name-like key ("screens",
        # "system", "name", …) that reads as a title — brand prefixes such as
        # "iCARRY …" included
        if isinstance(obj, str):
            s = obj.strip()
            if key and _NAME_KEY.search(str(key)) and _NAME_VALUE.match(s) and re.search(r"[A-Z]", s):
                known_systems.add(s)
                known_systems.add(re.sub(r"\s*\([^)]*\)\s*$", "", s))  # "Client Authentication Service (Internal …)"
        elif isinstance(obj, dict):
            for k, v in obj.items():
                _collect(v, k)
        elif isinstance(obj, list):
            for v in obj:
                _collect(v, key)

    for m in modules:
        _collect((m or {}).get("tech"))
        _collect((m or {}).get("spec"))
    # names the other layers declare (forms, checklists, procedures, screens,
    # journey stages, roles) are registered names too
    for layer in ("checklists", "procedures", "journey", "org", "playbook", "scoreboard"):
        _collect(content.get(layer))
    allowed = {t["name"] for t in table} | {a for t in table for a in t["aliases"]} | known_systems
    allowed |= {_pg.PILOT_TOOLING, _pg.PILOT_CUSTOMER_FORM, _pg.PILOT_OPERATOR, content.get("concept_name") or "",
                content.get("business_name") or ""}
    return {
        "modules": table,
        "pilot_names": [t["name"] for t in table if t["pilot"]],
        "pilot_terms": _reg.pilot_terms(modules),
        "gate": reg.get("pilot_gate"),
        "service_types": reg.get("service_types") or _reg.service_types(content.get("free_texts") or []),
        "sop_attempt_total": _reg.sop_attempt_total(procedures or []),
        "claims": reg.get("claims") or [],
        "allowed_names": {a for a in allowed if a},
        "standins": [_pg.PILOT_TOOLING, _pg.PILOT_CUSTOMER_FORM],
    }


# ── the rewrite guard ────────────────────────────────────────────────────────

CANONICAL = ("canonical_sentence", "assignment", "cadence", "auth_clause")


def _canonical_sentences(facts: dict) -> set[str]:
    out = {_reg.AUTH_CLAUSE}
    g = facts.get("gate")
    if g:
        out |= {_pg.canonical_sentence(g), _pg.assignment_sentence(g)}
    for n in _reg.deadline_days(facts.get("claims") or []):
        out.add(_reg.cadence_sentence(facts.get("claims") or [], n))
    return {s for s in out if s}


def guard(original: str, proposed: str, rule: str, facts: dict, ledger: dict, where: str,
          floor: float = 0.55) -> str:
    """Accept `proposed` only if it stays close to `original` (a bounded,
    local correction) or substitutes a registered canonical sentence; a
    rewrite beyond that is rejected and logged — the content keeps its text."""
    if proposed == original or not isinstance(original, str) or not isinstance(proposed, str):
        return original
    canon = _canonical_sentences(facts)
    if any(c in proposed for c in canon):
        return proposed
    ratio = difflib.SequenceMatcher(None, original, proposed).ratio()
    if ratio < floor:
        ledger.setdefault("rejected_rewrites", []).append(
            {"rule": rule, "where": where, "similarity": round(ratio, 3), "original": original[:160], "proposed": proposed[:160],
             "reason": "rewrite beyond the guard's similarity floor and not a registered canonical sentence"})
        return original
    return proposed


def _walk_strings(obj, fn, path="", skip=("id", "entity")):
    if isinstance(obj, str):
        return fn(obj, path)
    if isinstance(obj, dict):
        return {k: (_walk_strings(v, fn, f"{path}.{k}", skip) if k not in skip else v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_strings(v, fn, f"{path}[{i}]", skip) for i, v in enumerate(obj)]
    return obj


# ── correctors ───────────────────────────────────────────────────────────────

def correct_automation_class(content: dict, facts: dict, ledger: dict) -> None:
    """A module's automation level IS its structured AI component: a spec
    with an AI agent is 'ai'; a pilot stays manual/rules by law."""
    reg_mods = {m.get("id"): m for m in (content["registry"].get("modules") or [])}
    for m in content.get("modules") or []:
        if not isinstance(m, dict) or m.get("pilot"):
            continue
        has_ai = bool(((m.get("spec") or {}).get("ai")) or ((m.get("tech") or {}).get("ai_agent")))
        level = "ai" if has_ai else (m.get("automation_level") if m.get("automation_level") in ("manual", "rules") else "rules")
        if m.get("automation_level") != level or bool(m.get("ai_involvement")) != has_ai:
            ledger.setdefault("automation_reclassified", []).append(
                {"module": m.get("id"), "from": m.get("automation_level"), "to": level, "has_ai_component": has_ai})
            m["automation_level"], m["ai_involvement"] = level, has_ai
            if m.get("id") in reg_mods:
                reg_mods[m["id"]]["automation_level"], reg_mods[m["id"]]["ai_involvement"] = level, has_ai
    for t in facts["modules"]:
        src = next((m for m in content.get("modules") or [] if m.get("id") == t["id"]), {})
        t["automation_level"], t["has_ai"] = src.get("automation_level"), bool(src.get("ai_involvement"))


def _name_map(facts: dict) -> list[tuple[str, str, str | None]]:
    """(alias, registered name, word that must not precede the alias)."""
    pairs = []
    for t in facts["modules"]:
        for a in t["aliases"]:
            if a and a != t["name"] and len(a) > 5:
                pairs.append((a, t["name"], None))
        for suffix, prev in _suffix_forms(t["name"]):
            pairs.append((suffix, t["name"], prev))
    # "X module" on a stand-in names tooling as a module
    for s in facts["standins"]:
        pairs.append((f"{s} module", s, None))
    return sorted(pairs, key=lambda p: -len(p[0]))


def resolve_names(text: str, facts: dict) -> tuple[str, list[dict]]:
    """Every alias, abbreviation, suffix form or humanized id of a module
    reads as its client-facing name; tooling is never called a module."""
    records = []
    out = text
    for alias, name, prev in _name_map(facts):
        pat = _alias_pattern(alias, prev)
        if pat.search(out):
            out = pat.sub(name, out)
            records.append({"alias": alias, "resolved_to": name})
    return out, records


_LIST_ITEM = re.compile(r"^(\s*)(\d{1,2})\.\s+(.*)$")


def dedupe_standin_list_items(text: str, facts: dict) -> tuple[str, list[dict]]:
    """In a numbered list about the pilot, two items that each build the
    same stand-in are one item: the later one is dropped and the list is
    renumbered (the narrative twin of the build-sequence dedupe)."""
    records = []
    lines = text.split("\n")
    out = []
    i = 0
    terms = set(facts["pilot_terms"])
    while i < len(lines):
        m = _LIST_ITEM.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        block = []
        while i < len(lines) and _LIST_ITEM.match(lines[i]):
            block.append(lines[i])
            i += 1
        # scope: the list sits in a pilot section — its governing heading (the
        # last heading line above) or the lines just above name the pilot
        heading = next((ln for ln in reversed(out) if re.match(r"^\s*(?:#{1,6}\s|\*\*[^*]{3,80}\*\*\s*$)", ln)), "")
        context = heading + " " + " ".join(out[-12:])
        pilot_scoped = any(t in context for t in terms) or re.search(r"\bpilot\b", context, re.IGNORECASE)
        seen: set[str] = set()
        kept = []
        for line in block:
            mm = _LIST_ITEM.match(line)
            body = mm.group(3)
            s = next((x for x in facts["standins"] if x in body
                      and re.search(r"\b(?:build|develop|set up|configure|create|implement)\b", body, re.IGNORECASE)), None)
            if pilot_scoped and s and s in seen:
                records.append({"removed": body[:120], "standin": s})
                continue
            if s:
                seen.add(s)
            kept.append((mm.group(1), body))
        if len(kept) != len(block):
            out.extend(f"{indent}{n}. {body}" for n, (indent, body) in enumerate(kept, 1))
        else:
            out.extend(block)
    return "\n".join(out), records


_PRODUCT = re.compile(r"\b((?:[A-Z][A-Za-z]+|&|AI|COD)(?:\s+(?:[A-Z][A-Za-z]+|&|AI|COD)){1,5}\s+"
                      r"(?:Hub|Platform|Engine|Module|System|Resolver|Interface|Assistant|Bot|Suite|Portal|Dashboard|Queue|Form|Log|"
                      r"Database|Warehouse|Service|Layer|Workbench|Coordinator|Orchestrator))\b")


def unregistered_names(text: str, facts: dict) -> list[str]:
    allowed = facts["allowed_names"]
    out = []
    # rendered text wraps names across lines: judge on one-line text
    for m in _PRODUCT.finditer(re.sub(r"\s+", " ", text or "")):
        cand = m.group(1)
        if cand in allowed or any(cand in a or a in cand for a in allowed if len(a) > 8):
            continue
        if re.match(r"^(?:The|This|Your|Our|A|An)\s", cand):
            cand2 = re.sub(r"^(?:The|This|Your|Our|A|An)\s+", "", cand)
            if cand2 in allowed or any(cand2 in a or a in cand2 for a in allowed if len(a) > 8):
                continue
        out.append(cand)
    return out


def replace_unregistered_names(text: str, facts: dict) -> tuple[str, list[dict]]:
    records = []
    out = text
    for cand in sorted(set(unregistered_names(text, facts)), key=len, reverse=True):
        pat = re.compile(r"(?:\b(?:a|an|the)\s+(?:\w+\s+)?)?" + re.escape(cand) + r"\b")
        out2 = pat.sub("the system", out, count=0)
        if out2 != out:
            records.append({"name": cand, "replaced_with": "the system"})
            out = out2
    return out, records


_PHASE_HEAD = re.compile(r"\bPhase\s+(\d+)\s*([—–:-])\s*")
_PARALLEL = re.compile(r"\b[Ii]n parallel,?\s*")


def correct_phase_statements(text: str, facts: dict) -> tuple[str, list[dict]]:
    """'Phase N — <module>' states the registry's number; a parallel
    workstream is never a numbered phase; 'in parallel' is said only of
    registered parallel workstreams. Line by line."""
    records = []
    by_name = {t["name"]: t for t in facts["modules"]}
    names = sorted(by_name, key=len, reverse=True)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        named = sorted([n for n in names if n in line], key=lambda n: line.find(n))
        m = _PHASE_HEAD.search(line)
        if m and named:
            # the module this phase line is about: the FIRST module named
            # after the phase head (a line may go on to mention others), or
            # the ones a following "Delivers:" line names
            after_head = [n for n in named if line.find(n) >= m.end()]
            delivered = after_head[:1] or named[:1]
            if i + 1 < len(lines) and re.search(r"\bDelivers:", lines[i + 1]):
                delivered = [n for n in names if n in lines[i + 1]] or delivered
            numbers = [by_name[n]["phase_number"] for n in delivered]
            stated = int(m.group(1))
            if all(x is None for x in numbers):
                fixed = line[:m.start()] + "Parallel workstream " + m.group(2) + " " + line[m.end():]
                records.append({"line": line.strip()[:120], "rule": "parallel workstream is not a numbered phase"})
                lines[i] = fixed
            else:
                want = min(x for x in numbers if x is not None)
                if stated != want and stated not in [x for x in numbers if x is not None]:
                    lines[i] = line[:m.start()] + f"Phase {want} {m.group(2)} " + line[m.end():]
                    records.append({"line": line.strip()[:120], "rule": f"phase {stated} -> registry phase {want}"})
        if _PARALLEL.search(line) and named:
            if all(by_name[n]["workstream"] != "parallel" for n in named):
                lines[i] = _PARALLEL.sub("", line)
                records.append({"line": line.strip()[:120], "rule": "'in parallel' said of non-parallel modules"})
    return "\n".join(lines), records


def phase_statement_findings(text: str, facts: dict, label: str = "") -> list[dict]:
    fixed, recs = correct_phase_statements(text, facts)
    return [{"severity": "high", "source": "integrity", "kind": "contradiction", "where": f"{label}: phases".strip(": "),
             "issue": f"A phase statement contradicts the registry ({r['rule']}): \"{r['line'][:140]}\"",
             "fix": "phase numbers and parallel workstreams come from the module registry"} for r in recs]


_NONTHRESHOLD = [
    (re.compile(r"\b((?:TLS|SSL|OAuth|HTTP/?|API\s?v|version|v)\s?\d+(?:\.\d+)?)\s*\(proposed — client approval required\)", re.IGNORECASE),
     r"\1", "protocol or version number"),
    (re.compile(r"\b(\d{3})\s*\(proposed — client approval required\)(\s*(?:Forbidden|Not Found|Unauthorized|OK|Bad Request|"
                r"Internal Server Error|Conflict|Gone|Created|Accepted))", re.IGNORECASE), r"\1\2", "HTTP status code"),
    (re.compile(r"\b((?:returns?|return code|status(?: code)?|HTTP(?: status)?|error code)\s+(?:a\s+|an\s+)?[1-5]\d\d)\s*"
                r"\(proposed — client approval required\)", re.IGNORECASE), r"\1", "HTTP status code"),
    (re.compile(r"(?m)^(\s*\d{1,2}\.)\s*\(proposed — client approval required\)\s*"), r"\1 ", "list ordinal"),
    (re.compile(r"\b(\d{1,2}) \(proposed — client approval required\)(\.\s+(?=[A-Z]))"), r"\1\2", "inline ordinal"),
]
_RANDOM_BOUND = re.compile(r"(\bbetween\s+\d+(?:\.\d+)?)\s*\(proposed — client approval required\)(\s+and\s+\d+(?:\.\d+)?)", re.IGNORECASE)
_LABEL_VARIANT = re.compile(r"\(proposed\s*[-–—]\s*client approval required\)")
_SCOREBOARD_VARIANT = re.compile(r"Proposed decision threshold\s*[—–-]\s*requires your approval:\s*([^.]+?)\.?\s*$", re.IGNORECASE)


def normalize_labels(text: str) -> tuple[str, list[dict]]:
    """Only thresholds wear the approval label; the label has one form."""
    records = []
    out = text
    if _LABEL_VARIANT.search(out):
        fixed = _LABEL_VARIANT.sub(LABEL, out)
        if fixed != out:
            records.append({"rule": "label form", "text": out[:100]})
            out = fixed
    for rx, repl, why in _NONTHRESHOLD:
        fixed = rx.sub(repl, out)
        if fixed != out:
            records.append({"rule": f"label removed from a {why}", "text": out[:120]})
            out = fixed
    if re.search(r"random", out, re.IGNORECASE) and _RANDOM_BOUND.search(out):
        out2 = _RANDOM_BOUND.sub(r"\1\2", out)
        if out2 != out:
            records.append({"rule": "label removed from a random-draw bound", "text": out[:120]})
            out = out2
    m = _SCOREBOARD_VARIANT.search(out)
    if m:
        out = out[:m.start()] + m.group(1).strip() + " " + LABEL + "." + out[m.end():]
        records.append({"rule": "scoreboard label form", "text": out[:120]})
    return out, records


def nonthreshold_label_findings(text: str, label: str = "") -> list[dict]:
    out = []
    flat = _pg.flatten_prose(text)
    for rx, _repl, why in _NONTHRESHOLD[:2]:
        for m in rx.finditer(flat):
            out.append({"severity": "high", "source": "integrity", "kind": "misclassification", "where": f"{label}: labels".strip(": "),
                        "issue": f"A {why} wears a proposal label: \"{flat[max(0, m.start()-40):m.end()+30]}\"",
                        "fix": "only thresholds carry the label"})
    if re.search(r"random", flat, re.IGNORECASE):
        for m in _RANDOM_BOUND.finditer(flat):
            out.append({"severity": "high", "source": "integrity", "kind": "misclassification", "where": f"{label}: labels".strip(": "),
                        "issue": f"A random-draw bound wears a proposal label: \"{flat[max(0, m.start()-40):m.end()+30]}\"",
                        "fix": "only thresholds carry the label"})
    for m in _LABEL_VARIANT.finditer(flat):
        if m.group(0) != LABEL:
            out.append({"severity": "high", "source": "integrity", "kind": "drift", "where": f"{label}: labels".strip(": "),
                        "issue": f"A non-canonical approval label: \"{m.group(0)}\"", "fix": f"use {LABEL}"})
    for m in re.finditer(r"(?m)^\s*\d{1,2}\.\s*\(proposed — client approval required\)", text or ""):
        out.append({"severity": "high", "source": "integrity", "kind": "misclassification", "where": f"{label}: labels".strip(": "),
                    "issue": f"A list ordinal wears a proposal label: \"{m.group(0).strip()}\"", "fix": "ordinals are never thresholds"})
    return out


_UNIT_WORD = r"(?:business\s+)?(?:day|days|hour|hours|minute|minutes|week|weeks|month|months)"
_QUALIFIER = re.compile(r"\s+(?:within|after|under|in|over|inside)\s+\d+(?:\.\d+)?\s*" + _UNIT_WORD + r"\b", re.IGNORECASE)
_DANGLING_NUMBER = re.compile(r"\s+(?:within|after|under|in|over|inside)\s+\d+(?:\.\d+)?(?=\s*(?:—|:|\.|$))", re.IGNORECASE)
_DANGLING_UNIT = re.compile(r"\s+" + _UNIT_WORD + r"(?=\s*(?:—|:|\.|$))", re.IGNORECASE)


def repair_kpi_text(text: str) -> tuple[str, list[dict]]:
    """A KPI NAME carries no coined qualifier: 'resolved by human support
    within 1 business day' is the metric 'resolved by human support' (the
    number is the registered proposal); a unit or number left dangling by an
    earlier strip goes too."""
    out = _QUALIFIER.sub("", text)
    out = _DANGLING_NUMBER.sub("", out)
    out = _DANGLING_UNIT.sub("", out)
    return out, ([{"rule": "coined qualifier / dangling unit removed from a KPI name", "text": text[:120]}] if out != text else [])


def _shown_value(c: dict) -> str:
    v, unit = c.get("value"), str(c.get("unit") or "")
    if unit == "%" and isinstance(v, (int, float)) and 0 < v <= 1:
        return f"{v:.0%}"
    if unit == "%":
        return f"{v:g}%"
    return f"{v:g}" + (f" {unit}" if unit and unit not in ("count", "number") else "")


def correct_kpi_claims(content: dict, ledger: dict) -> None:
    """Module KPI proposals: the claim text is the cleaned metric name plus
    the value in its unit ('…: 85%'); a '%' value is a fraction and prints as
    a percentage; a repeated metric name or a dangling unit never survives."""
    for c in content["registry"].get("claims") or []:
        if c.get("type") != "module_kpi":
            continue
        text = str(c.get("text") or "")
        metric = str(c.get("metric") or text.split(":")[0]).strip()
        metric_clean, recs = repair_kpi_text(metric)
        if c.get("provenance") == "consultant_proposed" and isinstance(c.get("value"), (int, float)):
            rebuilt = f"{metric_clean}: {_shown_value(c)}"
            if rebuilt != text:
                ledger.setdefault("kpi_text_repaired", []).append({"claim": c.get("id"), "from": text[:120], "to": rebuilt[:120]})
                if c.get("unit") == "%" and re.search(r"\b0?\.\d+\s*%", text):
                    ledger.setdefault("kpi_units_corrected", []).append({"claim": c.get("id"), "from": text[-40:], "to": rebuilt[-40:]})
                c["text"] = rebuilt
            c["metric"] = metric_clean
        else:
            fixed, recs2 = repair_kpi_text(text)
            if recs2:
                ledger.setdefault("kpi_text_repaired", []).append({"claim": c.get("id"), **recs2[0]})
                c["text"] = fixed
            if recs and c.get("metric"):
                c["metric"] = metric_clean
    for m in content.get("modules") or []:
        spec = (m or {}).get("spec") if isinstance(m, dict) else None
        if isinstance(spec, dict):
            for key in ("kpis",):
                if isinstance(spec.get(key), list):
                    spec[key] = [repair_kpi_text(x)[0] if isinstance(x, str) else x for x in spec[key]]
            if isinstance(spec.get("kpi_statement"), str):
                spec["kpi_statement"] = repair_kpi_text(spec["kpi_statement"])[0]


def kpi_unit_findings(content: dict) -> list[dict]:
    out = []
    for c in content["registry"].get("claims") or []:
        if c.get("type") != "module_kpi":
            continue
        text = str(c.get("text") or "")
        if c.get("unit") == "%" and isinstance(c.get("value"), (int, float)) and 0 < c["value"] <= 1 and re.search(r"\b0?\.\d+\s*%", text):
            out.append({"severity": "high", "source": "integrity", "kind": "misclassification", "where": f"registry: {c.get('id')}",
                        "issue": f"A fractional KPI value prints as a percentage of itself: \"{text[-60:]}\"",
                        "fix": "a '%' claim value is a fraction — render it ×100"})
        name = text.split(":")[0]
        if _DANGLING_UNIT.search(name) or _DANGLING_NUMBER.search(name) or _QUALIFIER.search(name):
            out.append({"severity": "high", "source": "integrity", "kind": "misclassification", "where": f"registry: {c.get('id')}",
                        "issue": f"A KPI name carries a coined qualifier or a dangling unit: \"{text[:120]}\"",
                        "fix": "the metric name carries no number; the number is the registered proposal"})
        metric = str(c.get("metric") or "").strip()
        if metric and text.startswith(metric + ": ") and text[len(metric) + 2:].lstrip().startswith(metric):
            out.append({"severity": "high", "source": "integrity", "kind": "drift", "where": f"registry: {c.get('id')}",
                        "issue": f"A KPI text repeats its metric name: \"{text[:120]}\"", "fix": "metric name once, then the value"})
    return out


def dedupe_standin_entries(content: dict, facts: dict, ledger: dict) -> None:
    """Stand-in replacement can turn two original modules into the same
    name: a pilot build sequence then builds the queue twice and the
    integration list names it three times. One entry survives."""
    standins = facts["standins"]
    for m in content.get("modules") or []:
        if not (isinstance(m, dict) and m.get("pilot")):
            continue
        tech = m.get("tech") if isinstance(m.get("tech"), dict) else None
        if not tech:
            continue
        seen: set[str] = set()
        kept = []
        for step in tech.get("build_sequence") or []:
            s = next((x for x in standins if isinstance(step, str) and x in step
                      and re.search(r"\b(?:build|develop|set up|configure|create|implement)\b", step, re.IGNORECASE)), None)
            if s and s in seen:
                ledger.setdefault("standin_duplicates_removed", []).append({"module": m.get("id"), "field": "tech.build_sequence", "removed": step[:120]})
                continue
            if s:
                seen.add(s)
            kept.append(step)
        if "build_sequence" in tech:
            tech["build_sequence"] = kept
        for key in ("integrations", "integration_details"):
            items = tech.get(key)
            if not isinstance(items, list):
                continue
            seen_sys: set[str] = set()
            kept_i = []
            for it in items:
                sysname = it.get("system") if isinstance(it, dict) else (it if isinstance(it, str) else None)
                s = next((x for x in standins if sysname and x in str(sysname)), None)
                if s and s in seen_sys:
                    ledger.setdefault("standin_duplicates_removed", []).append({"module": m.get("id"), "field": f"tech.{key}", "removed": str(sysname)[:80]})
                    continue
                if s:
                    seen_sys.add(s)
                kept_i.append(it)
            tech[key] = kept_i


def standin_duplicate_findings(content: dict, facts: dict) -> list[dict]:
    out = []
    for m in content.get("modules") or []:
        if not (isinstance(m, dict) and m.get("pilot")):
            continue
        tech = m.get("tech") if isinstance(m.get("tech"), dict) else {}
        for key in ("build_sequence", "integrations", "integration_details"):
            items = tech.get(key) or []
            for s in facts["standins"]:
                n = sum(1 for it in items if s in (it.get("system") if isinstance(it, dict) else str(it))
                        and (key != "build_sequence" or re.search(r"\b(?:build|develop|set up|configure|create|implement)\b", str(it), re.IGNORECASE)))
                if n > 1:
                    out.append({"severity": "high", "source": "integrity", "kind": "contradiction", "where": f"modules.{m.get('id')}.tech.{key}",
                                "issue": f"'{s}' appears {n} times as the thing built/integrated — a stand-in collapsed several modules into one",
                                "fix": "one entry per stand-in"})
    return out


def classify_checklists(content: dict, facts: dict, ledger: dict) -> None:
    """A checklist that names a FUTURE module is usable once that module is
    built — tagged so, never presented as a day-one artifact."""
    cl = content.get("checklists") if isinstance(content.get("checklists"), dict) else None
    if not cl:
        return
    by_name = {t["name"]: t for t in facts["modules"]}
    for c in cl.get("checklists") or []:
        if not isinstance(c, dict):
            continue
        blob = " ".join(str(x) for x in (c.get("items") or [])) + " " + str(c.get("name") or "")
        named = [t for n, t in by_name.items() if n in blob]
        future = [t["name"] for t in named if t["phase"] == "FUTURE"]
        phase = "future" if future else ("pilot" if named else (c.get("phase") or "pilot"))
        if c.get("phase") != phase:
            ledger.setdefault("checklists_phased", []).append({"checklist": c.get("name"), "phase": phase, "future_modules": future})
        c["phase"] = phase
        c["phase_note"] = ("usable once " + ", ".join(future) + (" is" if len(future) == 1 else " are") + " built") if future else "runs during the pilot, with today's tools"


def checklist_phase_findings(content: dict, facts: dict) -> list[dict]:
    out = []
    cl = content.get("checklists") if isinstance(content.get("checklists"), dict) else {}
    future_names = [t["name"] for t in facts["modules"] if t["phase"] == "FUTURE"]
    for c in cl.get("checklists") or []:
        blob = " ".join(str(x) for x in (c.get("items") or []))
        if any(n in blob for n in future_names) and c.get("phase") != "future":
            out.append({"severity": "high", "source": "integrity", "kind": "misclassification", "where": f"checklists: {c.get('name')}",
                        "issue": "A checklist naming a FUTURE module is presented without a FUTURE phase tag", "fix": "tag it by the modules it names"})
    return out


def label_playbook_horizons(content: dict, ledger: dict) -> None:
    pb = content.get("playbook") if isinstance(content.get("playbook"), dict) else None
    if not pb:
        return
    for step in pb.get("steps") or []:
        if isinstance(step, dict):
            for key in ("horizon", "when"):
                h = step.get(key)
                if isinstance(h, str) and re.search(r"\d", h) and "(proposed" not in h and not re.search(r"week 1\b|immediately", h, re.IGNORECASE):
                    step[key] = h + " " + LABEL
                    ledger.setdefault("horizons_labeled", []).append({"step": step.get("title"), key: h})


def horizon_findings(content: dict) -> list[dict]:
    out = []
    pb = content.get("playbook") if isinstance(content.get("playbook"), dict) else {}
    for step in pb.get("steps") or []:
        for key in ("horizon", "when"):
            h = step.get(key) if isinstance(step, dict) else None
            if isinstance(h, str) and re.search(r"\d", h) and "(proposed" not in h and not re.search(r"week 1\b|immediately", h, re.IGNORECASE):
                out.append({"severity": "high", "source": "integrity", "kind": "misclassification", "where": f"playbook: {step.get('title')}",
                            "issue": f"A schedule horizon is stated as fact: '{h}'", "fix": "horizons are proposals — label them"})
    return out


def rehome_procedures(content: dict, facts: dict, ledger: dict) -> None:
    """A procedure belongs to the module that executes it: when another
    module is the dominant actor of its steps, it is refiled."""
    procs = (content.get("procedures") or {}).get("procedures") if isinstance(content.get("procedures"), dict) else None
    if not procs:
        return
    names = {t["name"] for t in facts["modules"]}
    for p in procs:
        if not isinstance(p, dict) or p.get("module") in ("The pilot", None) or str(p.get("phase") or "").lower() == "pilot":
            continue
        counts: dict[str, int] = {}
        for s in p.get("steps") or []:
            a = str((s or {}).get("actor") or "")
            if a in names:
                counts[a] = counts.get(a, 0) + 1
        if not counts:
            continue
        top, n = max(counts.items(), key=lambda kv: kv[1])
        mine = counts.get(str(p.get("module")), 0)
        if top != p.get("module") and n >= 3 and n >= 2 * max(mine, 1):
            ledger.setdefault("procedures_rehomed", []).append({"procedure": p.get("name"), "from": p.get("module"), "to": top, "steps": n})
            p["module"] = top


def procedure_home_findings(content: dict, facts: dict) -> list[dict]:
    out = []
    procs = (content.get("procedures") or {}).get("procedures") if isinstance(content.get("procedures"), dict) else []
    names = {t["name"] for t in facts["modules"]}
    for p in procs or []:
        if not isinstance(p, dict) or p.get("module") in ("The pilot", None) or str(p.get("phase") or "").lower() == "pilot":
            continue
        counts: dict[str, int] = {}
        for s in p.get("steps") or []:
            a = str((s or {}).get("actor") or "")
            if a in names:
                counts[a] = counts.get(a, 0) + 1
        if counts:
            top, n = max(counts.items(), key=lambda kv: kv[1])
            if top != p.get("module") and n >= 3 and n >= 2 * max(counts.get(str(p.get("module")), 0), 1):
                out.append({"severity": "high", "source": "integrity", "kind": "misclassification", "where": f"procedures: {p.get('name')}",
                            "issue": f"Filed under '{p.get('module')}' but executed by '{top}' in {n} steps", "fix": "file it under the module that executes it"})
    return out


def scoreboard_pilot_rows(content: dict, facts: dict, ledger: dict) -> None:
    """A pilot-orders row cites no FUTURE module — the pilot's own name
    stands in; its target carries the canonical label form."""
    rows = content.get("scoreboard") if isinstance(content.get("scoreboard"), list) else None
    if not rows or not facts["pilot_names"]:
        return
    pilot = facts["pilot_names"][0]
    future = [t for t in facts["modules"] if t["phase"] == "FUTURE"]
    for r in rows:
        if not isinstance(r, dict):
            continue
        metric = str(r.get("metric") or "")
        if re.search(r"\bpilot\b", metric, re.IGNORECASE):
            for key in ("target", "formula", "baseline"):
                v = r.get(key)
                if not isinstance(v, str):
                    continue
                for t in future:
                    for nm in [t["name"]] + t["aliases"]:
                        if nm and nm in v:
                            v = v.replace(nm, pilot)
                            ledger.setdefault("scoreboard_pilot_rows", []).append({"metric": metric[:60], "field": key, "replaced": nm, "with": pilot})
                r[key] = v
        for key in ("target", "baseline", "formula"):
            v = r.get(key)
            if isinstance(v, str):
                fixed, recs = normalize_labels(v)
                if recs:
                    ledger.setdefault("label_forms", []).extend({"where": f"scoreboard.{key}", **x} for x in recs)
                r[key] = fixed


def attempts_in_words(text: str, total: int | None) -> tuple[str, list[dict]]:
    """'after the reminder' when the SOP sends more than one reminder."""
    if not total or total <= 2 or not text:
        return text, []
    out = re.sub(r"\bafter the reminder\b", "after the final reminder", text)
    return out, ([{"rule": "'the reminder' with several reminders", "text": text[:100]}] if out != text else [])


# ── the pass ─────────────────────────────────────────────────────────────────

def _registry_rebuild(content: dict) -> dict:
    from app.pipeline.decompose import _sanitize_financial_model

    bc = content.get("business_case") if isinstance(content.get("business_case"), dict) else {}
    _sanitize_financial_model(bc)
    previous = content.get("registry") or {}
    procedures = (content.get("procedures") or {}).get("procedures") if isinstance(content.get("procedures"), dict) else None
    reg = _reg.build_registry(content.get("ops_numbers"), bc, content.get("modules") or [], free_texts=content.get("free_texts") or [],
                              procedures=procedures)
    for key in ("content_recovery",):
        if previous.get(key):
            reg[key] = previous[key]
    content["business_case"] = bc
    content["registry"] = reg
    return reg


def correct(content: dict, facts: dict) -> dict:
    """Every deterministic correction, in order, with its ledger."""
    ledger: dict = {}
    correct_automation_class(content, facts, ledger)
    for m in content.get("modules") or []:
        if isinstance(m, dict) and m.get("pilot"):
            recs = _reg.integration_channel_pass(m)
            if recs:
                ledger.setdefault("customer_channel", []).extend(recs)
    dedupe_standin_entries(content, facts, ledger)
    correct_kpi_claims(content, ledger)
    classify_checklists(content, facts, ledger)
    label_playbook_horizons(content, ledger)
    rehome_procedures(content, facts, ledger)
    scoreboard_pilot_rows(content, facts, ledger)
    total = facts.get("sop_attempt_total")

    def _string_fix(s: str, path: str) -> str:
        out, recs = resolve_names(s, facts)
        for r in recs:
            ledger.setdefault("names_resolved", []).append({"where": path, **r})
        out2, recs = normalize_labels(out)
        for r in recs:
            ledger.setdefault("label_forms", []).append({"where": path, **r})
        out2, recs = attempts_in_words(out2, total)
        for r in recs:
            ledger.setdefault("attempt_words", []).append({"where": path, **r})
        out2, recs = _reg.customer_facing_pass(out2)
        for r in recs:
            ledger.setdefault("customer_channel", []).append({"where": path, **r})
        return guard(s, out2, "string corrections", facts, ledger, path)

    for layer in ("modules", "procedures", "checklists", "scoreboard", "risks", "journey", "org", "playbook"):
        if content.get(layer) is not None:
            content[layer] = _walk_strings(content[layer], _string_fix, layer)
    for vol in ("blueprint", "technical"):
        text = content.get(vol) or ""
        if not text:
            continue
        lines = text.split("\n")
        fixed_lines = []
        for i, line in enumerate(lines):
            out, recs = resolve_names(line, facts)
            for r in recs:
                ledger.setdefault("names_resolved", []).append({"where": f"{vol}:{i}", **r})
            out, recs = normalize_labels(out)
            for r in recs:
                ledger.setdefault("label_forms", []).append({"where": f"{vol}:{i}", **r})
            out, recs = attempts_in_words(out, total)
            for r in recs:
                ledger.setdefault("attempt_words", []).append({"where": f"{vol}:{i}", **r})
            out, recs = _reg.customer_facing_pass(out)
            for r in recs:
                ledger.setdefault("customer_channel", []).append({"where": f"{vol}:{i}", **r})
            out, recs = replace_unregistered_names(out, facts)
            for r in recs:
                ledger.setdefault("unregistered_names", []).append({"where": f"{vol}:{i}", **r})
            fixed_lines.append(guard(line, out, "prose corrections", facts, ledger, f"{vol}:{i}"))
        text = "\n".join(fixed_lines)
        text, recs = correct_phase_statements(text, facts)
        for r in recs:
            ledger.setdefault("phase_statements", []).append({"where": vol, **r})
        text, recs = dedupe_standin_list_items(text, facts)
        for r in recs:
            ledger.setdefault("standin_duplicates_removed", []).append({"where": vol, **r})
        content[vol] = text
    return ledger


def validate(content: dict, facts: dict) -> list[dict]:
    """Typed findings on the structures and the markdown — the laws the
    correctors enforce, proven rather than assumed."""
    from app.pipeline.structural import structural_findings

    findings: list[dict] = []
    modules = content.get("modules") or []
    procedures = (content.get("procedures") or {}).get("procedures") if isinstance(content.get("procedures"), dict) else []
    reg = content["registry"]
    findings += [{**f, "kind": f.get("kind", "structural")} for f in structural_findings(content.get("business_case") or {}, modules, reg)]
    for t in facts["modules"]:
        if not t["pilot"] and t["has_ai"] and t["automation_level"] != "ai":
            findings.append({"severity": "high", "source": "integrity", "kind": "misclassification", "where": f"modules.{t['id']}",
                             "issue": f"'{t['name']}' carries an AI agent in its specification but is classified '{t['automation_level']}'",
                             "fix": "the automation level is the structured AI component"})
    findings += standin_duplicate_findings(content, facts)
    findings += kpi_unit_findings(content)
    findings += checklist_phase_findings(content, facts)
    findings += horizon_findings(content)
    findings += procedure_home_findings(content, facts)
    pilot_names = set(facts["pilot_names"])
    findings += _reg.pilot_procedure_findings(procedures or [], pilot_names, modules)
    findings += _reg.operating_time_findings(procedures or [])
    findings += _reg.pilot_isolation_findings(modules, procedures or [])
    texts = {"blueprint": content.get("blueprint") or "", "technical": content.get("technical") or ""}
    findings += validate_texts(texts, content, facts)
    return findings


def validate_texts(texts: dict[str, str], content: dict, facts: dict) -> list[dict]:
    """The text-level laws — on markdown here, on exact PDF text in the audit."""
    out: list[dict] = []
    reg = content["registry"]
    gate = facts.get("gate")
    total = facts.get("sop_attempt_total")
    terms = facts["pilot_terms"]
    for label, text in (texts or {}).items():
        if not text:
            continue
        out += phase_statement_findings(text, facts, label)
        out += nonthreshold_label_findings(text, label)
        for n in unregistered_names(text, facts):
            out.append({"severity": "high", "source": "integrity", "kind": "drift", "where": f"{label}: names",
                        "issue": f"An unregistered product or module name: '{n}'", "fix": "only registered module, tooling and system names"})
        flat_text = re.sub(r"\s+", " ", text)
        for alias, name, prev in _name_map(facts):
            if _alias_pattern(alias, prev).search(flat_text):
                out.append({"severity": "high", "source": "integrity", "kind": "drift", "where": f"{label}: names",
                            "issue": f"'{alias}' is an alias or abbreviation of the registered name '{name}'", "fix": "one name per module"})
        # ONE list building the same stand-in twice (the narrative and the
        # appendix each build it once — those are two lists, far apart)
        lst = _pg.flatten_prose(text)
        for s in facts["standins"]:
            positions = [m.start() for m in re.finditer(r"\b(?:build|set up|configure|develop|create|implement)\b[^•.]{0,60}" + re.escape(s), lst, re.IGNORECASE)]
            if any(b - a < 700 for a, b in zip(positions, positions[1:])):
                out.append({"severity": "high", "source": "integrity", "kind": "contradiction", "where": f"{label}: build narrative",
                            "issue": f"'{s}' is built twice within one list — a stand-in collapsed several modules into one",
                            "fix": "one build step per stand-in"})
        out += [{**f, "kind": "misclassification"} for f in _reg.customer_queue_findings(text, label)]
        out += _reg.attempts_text_findings(text, total, terms, label)
        if total and total > 2 and re.search(r"\bafter the reminder\b", text):
            out.append({"severity": "high", "source": "integrity", "kind": "contradiction", "where": f"{label}: pilot attempts",
                        "issue": "'after the reminder' while the pilot SOP sends more than one reminder", "fix": "'after the final reminder'"})
        if gate:
            out += [{**f, "where": f"{label}: {f['where']}"} for f in _pg.design_findings(text, gate)]
            out += _reg.population_findings(text, gate, label, facts.get("service_types"), terms)
        out += _reg.auth_text_findings(text, label)
        out += [{**f, "where": f"{label}: {f['where']}"} for f in _reg.api_text_findings(text, reg.get("api_paths") or [])]
        out += _reg.ordinal_label_findings(text, label)
        out += _reg.policy_findings({label: text}, reg.get("claims") or [])
    return out


def enforce(db: Session, request_id: int) -> dict:
    """Correct the row's content in place, validate, persist the report."""
    from app.pipeline import blueprint as _bp, extras as _extras

    row = db.get(Request, request_id)
    if row is None:
        raise ValueError(f"Request {request_id} not found")
    content = load(row)
    reg = _registry_rebuild(content)
    facts = derive_facts(content)
    # the registry-level deterministic passes on prose and layers, then the
    # layer's own correctors
    analysis = _loads(getattr(row, "business_analysis_json", None)) or {}
    for vol, kind in (("blueprint", "blueprint"), ("technical", "technical")):
        fixed, report = _bp.finish_document(content.get(vol), modules=content["modules"], business_case=content["business_case"],
                                            registry=reg, kind=kind)
        if fixed:
            content[vol] = fixed
        for key in ("policy_corrections", "placeholders", "derivations_shown", "design_corrections", "auth_hardening",
                    "customer_channel_corrections", "population_corrections", "pilot_attempt_corrections"):
            if report.get(key):
                reg.setdefault(key if key != "placeholders" else "placeholder_replacements", []).extend(report[key])
    save(row, content)
    db.commit()
    _extras.build_extras(db, request_id, analysis, {"modules": content["modules"], "business_case": content["business_case"], "registry": reg},
                         only={"__canonicalize__"})
    db.expire_all()
    row = db.get(Request, request_id)
    content = load(row)
    facts = derive_facts(content)
    # the prose once more with the SOP attempt total now in the registry
    for vol, kind in (("blueprint", "blueprint"), ("technical", "technical")):
        fixed, report = _bp.finish_document(content.get(vol), modules=content["modules"], business_case=content["business_case"],
                                            registry=content["registry"], kind=kind)
        if fixed:
            content[vol] = fixed
    ledger = correct(content, facts)
    findings = validate(content, facts)
    report = {
        "version": VERSION, "ran_at": datetime.utcnow().isoformat() + "Z",
        "facts": {"pilot": facts["pilot_names"], "sop_attempt_total": facts["sop_attempt_total"], "service_types": facts["service_types"],
                  "modules": [{k: t[k] for k in ("id", "name", "phase", "phase_number", "workstream", "automation_level", "has_ai", "customer_facing")}
                              for t in facts["modules"]]},
        "corrections": ledger, "rejected_rewrites": ledger.pop("rejected_rewrites", []),
        "findings": findings, "clean": not findings,
    }
    for key, entries in ledger.items():
        content["registry"].setdefault(f"integrity_{key}", []).extend(entries)
    save(row, content)
    report["content_hash"] = content_hash(load(row))
    row.integrity_report_json = json.dumps(report)
    db.commit()
    return report


def current_report(row) -> dict | None:
    """The persisted report, only if it was produced on the content the row
    holds now (any later rewrite invalidates it)."""
    rep = _loads(getattr(row, "integrity_report_json", None))
    if not isinstance(rep, dict) or rep.get("version") != VERSION:
        return None
    if rep.get("content_hash") != content_hash(load(row)):
        return None
    return rep


def validate_rendered(row, texts: dict[str, str]) -> list[dict]:
    content = load(row)
    facts = derive_facts(content)
    return validate_texts(texts, content, facts)
