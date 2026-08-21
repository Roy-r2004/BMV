"""The typed claim registry — release-critical facts as data, not prose.

Runs 42-46 proved that prompt law does not hold: the model coined module
KPIs (15%, 80%, 25%, 50%, 70%), restated the pilot gate three different
ways, printed raw module ids into a client document, and dropped approval
labels from acceptance criteria. Every one of those is a FACT that should
have existed as a typed record before any sentence was written. This module
is that record.

    Claim = {id, type, value, unit, time_basis, population, scope, phase,
             provenance, approval_status, source, allowed_sections, text}

Claim types
    client_fact            a number the client stated (discovery Q&A, brief)
    derived_value          machine-verified arithmetic on client facts
    time_basis_conversion  a derived value restated on another basis
    scenario_assumption    a labeled fraction of ours (requires approval)
    scenario_impact        fraction x verified base, machine-verified
    pilot_gate             the one canonical gate (and its components)
    module_kpi             a module success statement (registry-rendered)
    functional_requirement "process every eligible order" — words, no number
    performance_target     accuracy / latency / rate targets
    capacity_assumption    data volumes and load assumptions
    timing_sla             "within 5 minutes" style windows
    sampling_requirement   "the first 1,000", "a sample of 100"
    operational_policy     waits, retries, cut-offs in procedures
    historical_fact        a technical number that IS a client fact
    proposed_threshold     any other consultant-proposed operational number

Provenance: client_input | machine_computed | canonical_gate | consultant_proposed
Approval:   client_stated | machine_verified |
            consultant_proposed — client approval required | rejected

The prose model never creates a KPI number. A module's KPI statement is
rendered HERE from registered claims; a candidate the model proposes is
registered as consultant_proposed and stays out of every document until a
human accepts it. Thresholds in the structured technical specs are typed,
registered and labeled BEFORE the technical plan is written from them; the
same pass re-runs over the finished prose, and the final-text validator
maps every KPI/acceptance number back to a claim id — an unmapped number
blocks release.
"""

import json
import re

from app.pipeline import pilot_gate as _pg

MONTHLY_IDENTITY = "operating_30_day_month"
YEAR_DAYS = 365
MONTH_DAYS = 30
PROPOSED_LABEL = "(proposed — client approval required)"
WEEK_ONE_SENTENCE = "Baseline and target to be established during week-one measurement."

CLAIM_TYPES = {
    "client_fact", "derived_value", "time_basis_conversion", "scenario_assumption",
    "scenario_impact", "pilot_gate", "module_kpi", "functional_requirement",
    "performance_target", "capacity_assumption", "timing_sla", "sampling_requirement",
    "operational_policy", "historical_fact", "proposed_threshold",
}
PROVENANCE = {"client_input", "machine_computed", "canonical_gate", "consultant_proposed"}
APPROVAL = {"client_stated", "machine_verified",
            "consultant_proposed — client approval required", "rejected"}
# categories whose numbers need provenance or proposed status in prose
_LABELED_TYPES = {"performance_target", "capacity_assumption", "timing_sla",
                  "sampling_requirement", "operational_policy", "proposed_threshold"}

# names that imply predictive intelligence — forbidden on a pilot module
_AI_NAME = re.compile(
    r"\b(AI|A\.I\.|Engine|Predict\w*|Intelligen\w*|Smart|Scor\w*|Automat\w*|Brain|Neural|"
    r"ML|Machine[- ]Learning|Cognitive|Autonomous|Optimi[sz]er)\b", re.IGNORECASE)

_NUM = re.compile(
    r"(?<![\w.])(~?\$?\d[\d,]*(?:\.\d+)?)"
    r"(\s*(?:%|percent|percentage[- ]points?|pp\b|ms\b|milliseconds?|seconds?|minutes?|hours?|"
    r"days?|weeks?|months?|years?))?", re.IGNORECASE)
_SKIP_BEFORE = re.compile(
    r"((phase|section|page|volume|step|week|tier|level|version|part|top|chapter|figure|table|"
    r"option|v|q|run|no\.|#)\s*|[A-Za-z0-9]-|claim\s+[A-Z]{2}-[\w-]*)$", re.IGNORECASE)
_SKIP_AFTER = re.compile(
    r"^\s*(/7|x\b|×|am\b|pm\b|:\d|-\w|(?:phases?|steps?|parts?|modules?|volumes?|sections?|pages?|records?|"
    r"screens?|tables?|fields?|roles?|types?|categories|options?|lists?|entities|tools?|integrations?|"
    r"scenarios?|stages?|layers?|columns?|rows?|reasons?|sentences?|questions?|items?)\b)", re.IGNORECASE)
_THRESHOLD_SENTENCE = re.compile(
    r"within\s+\d|under\s+\d|\d\s*%\s*(accuracy|precision|recall|f1|of|success|resolution|helpful|"
    r"correct|confirm)|\d+\s*(ms|milliseconds)\b|first\s+\d|sample of\s+\d|historical|"
    r"know it.?s working|finished when|evaluation|trusted when|acceptance|"
    r"(?=.*\d)(?:.*\b(sample|review|reviews|reviewed|checked|audit\w*|backtest\w*|precision|recall|f1|latency|"
    r"accuracy|at least|more than|fewer than|less than|no more than|per day|per hour|per week|threshold|target|"
    r"window|hours? for|minutes? for|seconds? for)\b)", re.IGNORECASE)
_YEAR = re.compile(r"^(19|20)\d{2}$")
_LABEL_WINDOW = 130
_SLUG_ITEM = re.compile(r"(?m)^\s*(?:\d+\.|[-*•])\s*\**([a-z0-9]+(?:-[a-z0-9]+)+)\**\s*:")
_TECH_SLUG = re.compile(
    r"\b[a-z0-9]+(?:-[a-z0-9]+)*-(?:engine|predictor|assistant|concierge|resolver|notifier|"
    r"service|api|module|handler|worker|queue|store|ledger|agent|bot|portal|tracker|planner|"
    r"router|sync|feed|manager|dashboard|console|gateway|scheduler|optimizer)\b")
# ordinary hyphenated English that happens to end in a technical noun
_SLUG_ALLOW = re.compile(r"\b\w+-to-\w+\b|\bself-service\b|\bfull-service\b|\bmulti-agent\b|\bsingle-agent\b|"
                         r"\bfirst-party\b|\bthird-party\b|\bin-app\b|\bback-office\b|\bon-demand\b", re.IGNORECASE)
_BUILD_TEAM_LINE = re.compile(r"For your build team:[^\n•]*", re.IGNORECASE)
_APPENDIX_START = re.compile(r"Module appendix\s*[—–-]\s*the engineering detail", re.IGNORECASE)
_APPENDIX_END = re.compile(r"Three ways forward", re.IGNORECASE)


def client_facing_region(text: str) -> str:
    """The text a client reads as prose: Volume II's module appendix is
    declared engineering detail (data models, APIs, tools) and is excluded."""
    t = text or ""
    m = _APPENDIX_START.search(t)
    if not m:
        return t
    e = _APPENDIX_END.search(t, m.end())
    return t[:m.start()] + " " + (t[e.start():] if e else "")


# ── helpers ─────────────────────────────────────────────────────────────────


def _value(tok: str) -> float | None:
    try:
        return float(tok.replace("$", "").replace("~", "").replace(",", "").strip())
    except ValueError:
        return None


def _pct(tok: str | None) -> bool:
    return bool(tok) and ("%" in tok or "percent" in tok.lower())


def _close(a: float, b: float, rel: float = 0.005) -> bool:
    return a == b or abs(a - b) <= rel * max(abs(a), abs(b), 1e-9)


def _numbers(text: str) -> list[tuple[str, float, str, int, int]]:
    """(token, value, unit, start, end) for every real number in text —
    section/step/phase ordinals, years and times are not numbers."""
    out = []
    for m in _NUM.finditer(text or ""):
        before = text[max(0, m.start() - 14):m.start()]
        after = text[m.end():m.end() + 16]
        tok, unit = m.group(1), (m.group(2) or "").strip()
        if _SKIP_BEFORE.search(before) or _SKIP_AFTER.match(after):
            continue
        raw = tok.replace("$", "").replace("~", "").replace(",", "")
        if _YEAR.match(raw) and not unit and "$" not in tok:
            continue
        v = _value(tok)
        if v is None:
            continue
        if unit and ("%" in unit or "percent" in unit.lower()):
            v = v / 100.0
            unit = "%"
        out.append((tok, v, unit.lower(), m.start(), m.end()))
    return out


def _claim(cid: str, ctype: str, value, unit: str, *, time_basis: str = "n/a",
           population: str = "n/a", scope: str = "engagement", phase: str = "all",
           provenance: str, approval: str, source: str, sections: list[str],
           text: str = "", **extra) -> dict:
    c = {"id": cid, "type": ctype, "value": value, "unit": unit, "time_basis": time_basis,
         "population": population, "scope": scope, "phase": phase, "provenance": provenance,
         "approval_status": approval, "source": source, "allowed_sections": sections,
         "text": text}
    c.update(extra)
    return c


# ── client facts ─────────────────────────────────────────────────────────────

_UNIT_WORDS = (("deliver", "deliveries"), ("inquir", "inquiries"), ("hour", "hours"),
               ("order", "orders"), ("staff", "staff"), ("day", "days"), ("message", "messages"),
               ("call", "calls"), ("attempt", "attempts"), ("customer", "customers"),
               ("client", "clients"), ("visit", "visits"), ("week", "weeks"), ("month", "months"))
_BASIS_WORDS = (("a day", "day"), ("per day", "day"), ("/day", "day"), ("daily", "day"),
                ("a week", "week"), ("per week", "week"), ("/week", "week"), ("weekly", "week"),
                ("a month", "month"), ("per month", "month"), ("/month", "month"), ("monthly", "month"),
                ("a year", "year"), ("per year", "year"), ("annual", "year"))


def _infer_unit(tok: str, unit: str, context: str) -> tuple[str, str]:
    ctx = context.lower()
    if tok.startswith("$") or "usd" in ctx:
        u = "USD"
    elif unit == "%":
        u = "%"
    elif unit:
        u = unit
    else:
        u = next((w for h, w in _UNIT_WORDS if h in ctx), "count")
    basis = next((b for h, b in _BASIS_WORDS if h in ctx), "as stated")
    return u, basis


def client_fact_claims(ops_numbers: list, free_texts: list[str]) -> list[dict]:
    claims = []
    n = 0
    for pair in ops_numbers or []:
        if not isinstance(pair, dict):
            continue
        q, a = str(pair.get("question") or ""), str(pair.get("answer") or "")
        for tok, v, unit, s, e in _numbers(a):
            n += 1
            u, basis = _infer_unit(tok, unit, a[max(0, s - 30):e + 30] + " " + q)
            claims.append(_claim(
                f"CF-{n:02d}", "client_fact", v, u, time_basis=basis,
                provenance="client_input", approval="client_stated",
                source=f"discovery: {q}", sections=["*"], text=a.strip(),
                question=q))
    for t in free_texts:
        for tok, v, unit, s, e in _numbers(t or ""):
            n += 1
            u, basis = _infer_unit(tok, unit, t[max(0, s - 30):e + 30])
            claims.append(_claim(
                f"CF-{n:02d}", "client_fact", v, u, time_basis=basis,
                provenance="client_input", approval="client_stated",
                source="client brief", sections=["*"], text=t[max(0, s - 40):e + 40].strip()))
    return claims


# ── derived values, conversions, scenarios ───────────────────────────────────


def derived_claims(fm: dict) -> list[dict]:
    claims = []
    if not isinstance(fm, dict):
        return claims
    for i, line in enumerate(fm.get("lines") or [], 1):
        if not (isinstance(line, dict) and line.get("arithmetic_verified")):
            continue
        annual = str(line.get("annual") or "")
        nums = _numbers(annual)
        if not nums:
            continue
        tok, v, unit, _, _ = nums[0]
        u, _ = _infer_unit(tok, unit, annual + " " + str(line.get("item") or ""))
        if u != "USD" and re.search(r"\$|\busd\b", str(line.get("arithmetic") or ""), re.IGNORECASE) \
                and re.search(r"cost|saving|revenue|fee|spend|loss", str(line.get("item") or ""), re.IGNORECASE):
            u = "USD"  # the figure lost its sign; its arithmetic and item say money
        cid = f"DV-{i:02d}"
        claims.append(_claim(
            cid, "derived_value", v, u, time_basis="year", provenance="machine_computed",
            approval="machine_verified", source=f"financial_model.lines[{i - 1}]: {line.get('arithmetic')}",
            sections=["*"], text=annual, item=line.get("item")))
        if u == "USD":
            claims.append(_claim(
                f"TB-{i:02d}-day", "time_basis_conversion", round(v / YEAR_DAYS, 2), "USD",
                time_basis="day", provenance="machine_computed", approval="machine_verified",
                source=f"{cid} / {YEAR_DAYS}", sections=["*"],
                text=f"${v / YEAR_DAYS:,.2f}/day", formula=f"{v:,.0f}/year / {YEAR_DAYS}"))
            claims.append(_claim(
                f"TB-{i:02d}-month", "time_basis_conversion", round(v / YEAR_DAYS * MONTH_DAYS, 2), "USD",
                time_basis=MONTHLY_IDENTITY, provenance="machine_computed", approval="machine_verified",
                source=f"{cid} / {YEAR_DAYS} x {MONTH_DAYS}", sections=["*"],
                text=f"${v / YEAR_DAYS * MONTH_DAYS:,.0f}/month",
                formula=f"{v:,.0f}/year / {YEAR_DAYS} x {MONTH_DAYS}"))
    for i, sc in enumerate(fm.get("scenarios") or [], 1):
        if not isinstance(sc, dict):
            continue
        name = str(sc.get("name") or f"scenario {i}")
        for j, (tok, v, unit, _, _) in enumerate(_numbers(str(sc.get("assumption") or "")), 1):
            if unit == "%" or 0 < v < 1:
                claims.append(_claim(
                    f"SA-{i:02d}-{j}", "scenario_assumption", v, "ratio",
                    provenance="consultant_proposed",
                    approval="consultant_proposed — client approval required",
                    source=f"financial_model.scenarios[{name}].assumption", sections=["*"],
                    text=f"{v:.0%} ({name} scenario assumption)", scenario=name))
        if sc.get("impact_verified"):
            for j, (tok, v, unit, s, e) in enumerate(_numbers(str(sc.get("impact") or "")), 1):
                impact = str(sc.get("impact") or "")
                u, basis = _infer_unit(tok, unit, impact[max(0, s - 20):e + 40])
                claims.append(_claim(
                    f"SI-{i:02d}-{j}", "scenario_impact", v, u, time_basis=basis if basis != "as stated" else "year",
                    provenance="machine_computed", approval="machine_verified",
                    source=f"financial_model.scenarios[{name}].impact", sections=["*"],
                    text=tok + (" " + unit if unit else ""), scenario=name))
                if u == "USD" and j == 1:
                    claims.append(_claim(
                        f"SI-{i:02d}-month", "time_basis_conversion", round(v / YEAR_DAYS * MONTH_DAYS, 2),
                        "USD", time_basis=MONTHLY_IDENTITY, provenance="machine_computed",
                        approval="machine_verified", source=f"SI-{i:02d}-1 / {YEAR_DAYS} x {MONTH_DAYS}",
                        sections=["*"], text=f"${v / YEAR_DAYS * MONTH_DAYS:,.0f}/month", scenario=name))
    return claims


# ── module registry ───────────────────────────────────────────────────────────


def canonical_pilot_name(name: str) -> str:
    """A Phase-1 module's client-facing name must say what it is: a manual
    or rules-based pilot. 'Pre-Dispatch WhatsApp Engine' -> 'Pre-Dispatch
    WhatsApp Pilot'. Deterministic, so the same name lands in all volumes."""
    stripped = _AI_NAME.sub("", name or "").strip()
    stripped = re.sub(r"\s{2,}", " ", stripped).strip(" -—:")
    if not stripped:
        stripped = "Manual"
    if not re.search(r"\bpilot\b", stripped, re.IGNORECASE):
        stripped += " Pilot"
    return stripped


def module_registry(modules: list, business_case: dict) -> tuple[list[dict], list[dict]]:
    """Typed module metadata, and the renames applied to make pilot-phase
    names honest. Mutates the modules in place (the single source every
    downstream prompt reads) and returns (registry_modules, renames)."""
    bc = business_case if isinstance(business_case, dict) else {}
    order = [x for x in (bc.get("build_order") or []) if isinstance(x, str)]
    gate_present = bool(isinstance(bc.get("pilot_gate"), dict) and bc["pilot_gate"])
    mods = [m for m in (modules or []) if isinstance(m, dict) and m.get("id")]
    pilot_ids = {m["id"] for m in mods if m.get("pilot") is True}
    if not pilot_ids and gate_present and order:
        # the pilot's subject is the first module built, unless the model said otherwise
        pilot_ids = {order[0]}
    out, renames = [], []
    for m in mods:
        level = str(m.get("automation_level") or "").lower()
        has_ai = bool(m.get("ai_involvement")) or bool((m.get("spec") or {}).get("ai")) \
            or bool((m.get("tech") or {}).get("ai_agent"))
        if level not in ("manual", "rules", "ai"):
            level = "ai" if has_ai else "rules"
        is_pilot = m["id"] in pilot_ids
        original = str(m.get("name") or m["id"])
        name = original
        # a parenthetical abbreviation ("... Assistant (LVA)") invites the
        # prose to use two names for one thing — the full name is THE name,
        # the abbreviation an alias that resolves back to it
        alias = None
        am = re.search(r"\s*\(([A-Z][A-Za-z0-9 .&'-]{1,16})\)\s*$", name)
        if am and len(am.group(1).split()) <= 3 and am.group(1).upper() != am.group(1).lower():
            alias = am.group(1).strip()
            name = name[:am.start()].strip()
        if is_pilot and _AI_NAME.search(name):
            name = canonical_pilot_name(name)
        if name != original:
            renames.append({"id": m["id"], "from": original, "to": name,
                            "reason": "pilot_name" if (is_pilot and _AI_NAME.search(original)) else "alias"})
            m["original_name"] = original
            m["name"] = name
        if alias:
            m["alias"] = alias
        m["client_facing_name"] = name
        m["automation_level"] = level
        m["ai_involvement"] = has_ai
        m["pilot"] = is_pilot
        m["phase"] = "PILOT" if is_pilot else "FUTURE"
        out.append({"id": m["id"], "client_facing_name": name, "original_name": original, "alias": alias,
                    "phase": m["phase"], "automation_level": level, "ai_involvement": has_ai,
                    "pilot": is_pilot, "depends_on": list(m.get("depends_on") or [])})
    # the rename must reach every string that carried the old name — in the
    # business case and in every OTHER module's spec and tech anatomy
    if renames:
        def _walk(obj):
            if isinstance(obj, str):
                for r in renames:
                    obj = obj.replace(r["from"], r["to"])
                return obj
            if isinstance(obj, dict):
                return {k: _walk(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_walk(v) for v in obj]
            return obj
        for k in list(bc.keys()):
            bc[k] = _walk(bc[k])
        for m in mods:
            for key in list(m.keys()):
                if key in ("id", "original_name"):
                    continue
                m[key] = _walk(m[key])
    return out, renames


def resolve_module_ids(text: str, modules: list) -> str:
    """Client-facing text never shows an internal id: every raw module id
    becomes its approved client-facing name."""
    out = text or ""
    for m in sorted((modules or []), key=lambda x: -len(str(x.get("id") or ""))):
        mid, name = str(m.get("id") or ""), str(m.get("client_facing_name") or m.get("name") or "")
        if mid and name and ("-" in mid or "_" in mid):
            out = re.sub(r"(?<![\w-])" + re.escape(mid) + r"(?![\w-])", name, out)
        alias = str(m.get("alias") or "")
        if alias and name:
            # "the LVA" / "(LVA)" -> the one name; the parenthetical form disappears
            out = re.sub(r"\s*\(" + re.escape(alias) + r"\)", "", out)
            out = re.sub(r"(?<![\w'])" + re.escape(alias) + r"(?![\w'])", name, out)
            out = out.replace(name + " " + name, name)
    return out


def identifier_artifacts(text: str, module_ids: list[str] | None = None) -> list[str]:
    """Internal identifiers found in client-facing text: known module ids,
    slug-shaped list labels ('1. pre-dispatch-whatsapp-engine:') and
    technical slugs ('...-engine', '...-resolver')."""
    hits = []
    # "For your build team" lines and the module appendix ("the engineering
    # detail") are the sanctioned homes of technical identifiers; ordinary
    # hyphenated English is not a slug
    t = client_facing_region(text or "")
    t = _BUILD_TEAM_LINE.sub(" ", t)
    t = _SLUG_ALLOW.sub(" ", t)
    for mid in module_ids or []:
        if mid and ("-" in mid or "_" in mid) and re.search(r"(?<![\w-])" + re.escape(mid) + r"(?![\w-])", t):
            hits.append(mid)
    hits += [m.group(1) for m in _SLUG_ITEM.finditer(t)]
    hits += [m.group(0) for m in _TECH_SLUG.finditer(t)]
    return sorted(set(hits))


# ── threshold typing ──────────────────────────────────────────────────────────


def classify_threshold(tok: str, value: float, unit: str, before: str, after: str) -> str:
    """One deterministic category per numeric fragment — never a single
    generic percentage rule."""
    b, a = before.lower()[-70:], after.lower()[:70]
    if unit == "%" and _close(value, 1.0) and re.match(r"\s*(of|for)\b", a):
        return "functional_requirement"
    if unit in ("ms", "millisecond", "milliseconds"):
        return "performance_target"
    if unit == "%":
        return "performance_target"
    if unit in ("second", "seconds", "minute", "minutes", "hour", "hours", "day", "days",
                "week", "weeks", "month", "months"):
        if re.search(r"(within|under|in under|no later than|before|after|every|each|at least|"
                     r"more than|less than|fewer than|exceed|beyond|up to|of inactivity|"
                     r"of receiving|unanswered for)\s*$", b) or re.match(r"\s*(of|after|before|window|of receiving)\b", a):
            return "timing_sla"
        return "timing_sla"
    if re.search(r"\b(first|initial|sample of|random sample of|at least)\s*$", b) or \
            re.match(r"\s*(flagged|random|sampled|reviewed|checked|prompts|conversations|interactions|cases)\b", a):
        return "sampling_requirement"
    if re.search(r"\b(historical|past|backtest\w*|archive\w*|existing)\b", a[:30]) or \
            re.search(r"\b(historical|past|backtest\w*)\s*$", b) or \
            re.match(r"\s*\w+\s*(per|/|a)\s*(day|hour|minute|month|week)\b", a):
        return "capacity_assumption"
    return "proposed_threshold"


_TIME_UNITS = {"ms": "ms", "millisecond": "ms", "milliseconds": "ms", "second": "seconds", "seconds": "seconds",
               "minute": "minutes", "minutes": "minutes", "hour": "hours", "hours": "hours", "day": "days",
               "days": "days", "week": "weeks", "weeks": "weeks", "month": "months", "months": "months",
               "year": "years", "years": "years"}


def _unit_compatible(unit: str, claim: dict) -> bool:
    """A number matches a claim only in the same kind of unit: '5 minutes'
    is not the client's '5 support staff', '$2.50' is not '2.5 hours'."""
    u = (unit or "").lower()
    cu = str(claim.get("unit") or "").lower()
    ct = str(claim.get("time_basis") or "").lower()
    if u in _TIME_UNITS:
        return _TIME_UNITS[u] in (cu, ct, cu + "s", ct + "s") or cu in _TIME_UNITS and _TIME_UNITS[cu] == _TIME_UNITS[u]
    if u == "%":
        return cu in ("%", "ratio")
    if u.startswith("$") or u == "usd":
        return cu == "usd"
    # a bare number: never a time or a currency claim, anything else goes
    return cu not in ("usd",) and cu not in _TIME_UNITS


def _matches_claim(value: float, unit: str, claims: list[dict], types: tuple | None = None) -> dict | None:
    allowed = types or ("client_fact", "derived_value", "time_basis_conversion",
                        "scenario_impact", "scenario_assumption", "pilot_gate")
    for c in claims:
        if c["type"] in allowed:
            cv = c.get("value")
            if isinstance(cv, (int, float)) and _close(float(cv), value) and _unit_compatible(unit, c):
                return c
    return None


_ADJ = (r"historical|flagged|confirmed|new|generated|random|sampled|eligible|past|consecutive|unanswered|"
        r"reminder|support|finance|delivery|pilot|active|open|pending|failed|successful|escalated|relevant")
_NOUN = (r"orders|incidents|prompts|accuracy|precision|recall|records|messages|customers|deliveries|inquiries|"
         r"attempts|cases|samples|conversations|interactions|requests|items|reminders|pins|staff|clients|"
         r"drivers|responses|notifications|statements|transactions|settlements|disputes|tickets|calls|"
         r"resolution|helpfulness|coverage|uptime|availability|zones|queries")
_TAIL = re.compile(rf"^(?:(?:\s+of)?(?:\s+(?:{_ADJ}))*\s+(?:{_NOUN})|(?:\s+(?:{_ADJ}))+)\b", re.IGNORECASE)


def threshold_pass(text: str, claims: list[dict], *, source: str, module_id: str,
                   counter: dict, phase: str = "FUTURE") -> tuple[str, list[dict]]:
    """Type every number in an acceptance / evaluation / procedure string:
    functional requirements render as words, client facts and derived values
    stay bare, everything else is registered as a consultant-proposed claim
    and carries the approval label. Returns (text, new_claims)."""
    new: list[dict] = []
    if not text:
        return text, new
    # the canonical gate sentence is opaque to every other pass: its numbers
    # are the gate's, already typed and labeled
    protected = [str(c.get("text") or "") for c in claims
                 if c.get("type") == "pilot_gate" and len(str(c.get("text") or "")) > 40]
    masks: dict[str, str] = {}
    out = text
    for i, sentence in enumerate(protected):
        if sentence in out:
            key = f"\x00GATE{i}\x00"
            masks[key] = sentence
            out = out.replace(sentence, key)
    # functional completeness: "100% of X" -> "all X"
    out = re.sub(r"\b100\s*%\s*of\s+(the\s+)?", r"all \1", out)
    out = re.sub(r"\bfor all (the )?(?=\w)", r"for all \1", out)
    pieces = []
    last = 0
    for tok, v, unit, s, e in _numbers(out):
        before, after = out[max(0, s - 80):s], out[e:e + 80]
        # inside an existing label, or a number the label already follows
        if "(proposed" in out[e:e + _LABEL_WINDOW]:
            labeled = True
        else:
            labeled = False
        category = classify_threshold(tok, v, unit, before, after)
        known = _matches_claim(v, unit, claims)
        if known is not None:
            category = "historical_fact" if known["type"] == "client_fact" else "derived_value"
        if category == "functional_requirement":
            continue
        counter["n"] = counter.get("n", 0) + 1
        cid = f"TH-{module_id}-{counter['n']:02d}"
        needs_label = category in _LABELED_TYPES
        claim = _claim(
            cid, category, v, unit or "count",
            time_basis=unit if unit in ("day", "days", "week", "weeks", "month", "months") else "n/a",
            phase=phase, scope=module_id,
            provenance=("client_input" if category == "historical_fact" else
                        "machine_computed" if category == "derived_value" else "consultant_proposed"),
            approval=("client_stated" if category == "historical_fact" else
                      "machine_verified" if category == "derived_value" else
                      "consultant_proposed — client approval required"),
            source=source, sections=[source.split(".")[0]], text=tok + (" " + unit if unit else ""),
            maps_to=known["id"] if known else None)
        new.append(claim)
        if needs_label and not labeled:
            tail = _TAIL.match(out[e:e + 60])
            cut = e + (tail.end() if tail else 0)
            pieces.append(out[last:cut])
            pieces.append(" " + PROPOSED_LABEL)
            last = cut
    pieces.append(out[last:])
    result = "".join(pieces)
    for key, sentence in masks.items():
        result = result.replace(key, sentence)
    return result, new


def label_prose_thresholds(text: str, claims: list[dict], counter: dict, *,
                           source: str = "prose", module_id: str = "doc") -> tuple[str, list[dict]]:
    """The prose safety net: the same typing pass, restricted to sentences
    that state acceptance criteria, evaluation checks, KPIs or thresholds —
    a narrative "3 phases" is not a threshold and is left alone."""
    if not text:
        return text, []
    new: list[dict] = []
    out_lines = []
    for line in text.split("\n"):
        # every body line of the plan is in scope — except the sanctioned
        # technical line, headings, and lines with no digit at all
        if "For your build team" in line or line.lstrip().startswith("#") or not re.search(r"\d", line):
            out_lines.append(line)
            continue
        fixed, c = threshold_pass(line, claims, source=source, module_id=module_id, counter=counter)
        new += c
        out_lines.append(fixed)
    return "\n".join(out_lines), new


_POLICY_WORDS = re.compile(r"settle|settlement|remit|remittance|payout|pay out|disburse|invoice cycle|billing cycle",
                           re.IGNORECASE)
_POLICY_PERIOD = re.compile(r"(\d+)\s*(?:-|\s)?(business |working |calendar )?(days?)\b|(\d+)\s*-?\s*hours?\b|"
                            r"\b(weekly|bi-weekly|fortnightly|daily|twice a month|every two weeks)\b",
                            re.IGNORECASE)


def policy_findings(texts: dict[str, str], claims: list[dict]) -> list[dict]:
    """NO INVENTED POLICIES, deterministically: a sentence that states a
    settlement / remittance / payout period must state the client's own
    period (a client fact in days) — any other period is a fabrication."""
    out = []
    client_days = {int(c["value"]) for c in claims
                   if c.get("type") == "client_fact" and str(c.get("unit") or "").startswith("day")
                   and isinstance(c.get("value"), (int, float))
                   and re.search(r"settle|remit|payout|month-end", str(c.get("question") or c.get("source") or ""), re.IGNORECASE)}
    if not client_days:
        return out
    for label, text in (texts or {}).items():
        flat = re.sub(r"\s-\s+(?=[A-Z*])", ". ", text or "")
        flat = re.sub(r"\s+", " ", flat)
        for sentence in re.split(r"(?<=[.!?])\s+|•", flat):
            if not _POLICY_WORDS.search(sentence):
                continue
            for m in _POLICY_PERIOD.finditer(sentence):
                if m.group(1) and int(m.group(1)) in client_days:
                    continue
                if m.group(1) is None and not (m.group(4) or m.group(5)):
                    continue
                # the period must be ABOUT settling — adjacent to the policy
                # verb/noun ("remitted weekly", "settled within 5 days",
                # "2-day remittance policy") — a review cadence in the same
                # sentence ("Settlement Inquiry Review Checklist (Weekly)") is not
                before = sentence[max(0, m.start() - 60): m.start()]
                after = sentence[m.end(): m.end() + 40]
                near = before + " " + after
                tied = (re.search(r"(?:" + _POLICY_WORDS.pattern + r")\w*\s+(?:\w+\s+){0,2}(?:within|in|after|every|of|on|per|at)?\s*$",
                                  before, re.IGNORECASE)
                        or re.match(r"\s*(?:\w+\s+){0,1}(?:settlement|remittance|payout|disbursement)\s+(?:cycle|policy|period|terms|window)",
                                    after, re.IGNORECASE))
                if not tied:
                    continue
                # the 30-day operating month and "x 30 days" are identity formulas, not policies
                if re.search(r"\b30[- ]day\s*(?:operating\s*)?month|[x×*]\s*30\s*days", near, re.IGNORECASE):
                    continue
                stated = m.group(0)
                # a label does not rescue an invented policy: the client stated
                # their cycle, and a different one is a contradiction, labeled or not
                out.append({"severity": "high", "source": "structural", "where": f"{label}: operational policy",
                            "issue": (f"A settlement/remittance period of '{stated}' is stated, but the client's "
                                      f"stated period is {sorted(client_days)[0]} days — a policy the client never gave: "
                                      f"\"{sentence.strip()[:160]}\""),
                            "fix": f"state the client's own period ({sorted(client_days)[0]} days) or remove the policy claim"})
    return out


def policy_pass(text: str, claims: list[dict]) -> tuple[str, list[str]]:
    """Rewrite an invented settlement period in a structured string to the
    client's stated one, marked as theirs — the least-invention deterministic
    correction ('2-day remittance policy' -> '10-day (your stated cycle)
    remittance policy'). Returns (text, notes)."""
    notes = []
    if not text:
        return text, notes
    client_days = sorted({int(c["value"]) for c in claims
                          if c.get("type") == "client_fact" and str(c.get("unit") or "").startswith("day")
                          and isinstance(c.get("value"), (int, float))
                          and re.search(r"settle|remit|payout|month-end", str(c.get("question") or c.get("source") or ""), re.IGNORECASE)})
    if not client_days:
        return text, notes
    out = text
    # an invented period hiding in an identifier ('remittance_due_in_2_days'
    # — the renderer prints it as words) is corrected in place
    def _snake(m: re.Match) -> str:
        n = int(m.group(2))
        if n in client_days:
            return m.group(0)
        notes.append(f"'{m.group(0)}' -> '{m.group(1)}{client_days[0]}{m.group(3)}'")
        return f"{m.group(1)}{client_days[0]}{m.group(3)}"

    out = re.sub(r"\b((?:settle|settlement|remit|remittance|payout|disburse)\w*_(?:[a-z]+_){0,3})(\d+)(_days?\b)", _snake, out)
    # an earlier correction's phrasing is normalized, and the client's own
    # cycle never carries an approval label
    out = re.sub(r"\b(within|in|after|every)\s+(\d+)-day \(your stated cycle\)", r"\1 \2 days (your stated cycle)", out)
    out = re.sub(r"\(your stated cycle\)\s*\(proposed — client approval required\)", "(your stated cycle)", out)
    for f in policy_findings({"s": text}, claims):
        stated = re.search(r"period of '([^']+)'", f["issue"])
        if not stated:
            continue
        token = stated.group(1)
        # keep the grammar of the phrase it replaces: "within 2 days" -> "within 10 days (…)",
        # "2-day policy" -> "10-day (…) policy", "weekly" -> "every 10 days (…)"
        if re.fullmatch(r"\d+\s*-\s*day", token, re.IGNORECASE):
            replacement = f"{client_days[0]}-day (your stated cycle)"
        elif re.search(r"\d", token):
            replacement = f"{client_days[0]} days (your stated cycle)"
        else:
            replacement = f"every {client_days[0]} days (your stated cycle)"
        if re.search(re.escape(token), out):
            out = re.sub(re.escape(token), replacement, out, count=1)
            notes.append(f"'{token}' -> '{replacement}'")
    return out, notes


def enforce_gate_in_specs(modules: list, gate: dict | None) -> int:
    """The canonical sentence replaces any gate paraphrase living in the
    structured specs the volumes are written from (run 47: an evaluation
    item restated the gate with the model's stale 0.93 endpoint)."""
    if not gate:
        return 0
    n = 0
    for m in modules or []:
        if not isinstance(m, dict):
            continue
        tech = m.get("tech") if isinstance(m.get("tech"), dict) else {}
        spec = m.get("spec") if isinstance(m.get("spec"), dict) else {}
        targets = []
        for key in ("done_when", "build_sequence"):
            if isinstance(tech.get(key), list):
                targets.append(tech[key])
        agent = tech.get("ai_agent") if isinstance(tech.get("ai_agent"), dict) else {}
        for key in ("evaluation", "guardrails", "brain"):
            if isinstance(agent.get(key), list):
                targets.append(agent[key])
        for f in spec.get("features") or []:
            if isinstance(f, dict) and isinstance(f.get("description"), str):
                fixed, rep = _pg.enforce(f["description"], gate)
                if rep["paraphrases_replaced"] or rep["paraphrases_removed"]:
                    f["description"] = fixed
                    n += 1
        for items in targets:
            for i, it in enumerate(items):
                if isinstance(it, str):
                    fixed, rep = _pg.enforce(it, gate)
                    if rep["paraphrases_replaced"] or rep["paraphrases_removed"] or rep["token_substitutions"]:
                        items[i] = fixed
                        n += 1
    return n


def ai_consistency_findings(technical_md: str, modules: list) -> list[dict]:
    """A module specified with an AI component may not be described as
    'No AI in this part' — and vice versa (run 47: the Smart Reply module)."""
    out = []
    md = technical_md or ""
    for m in modules or []:
        if not isinstance(m, dict):
            continue
        name = str(m.get("client_facing_name") or m.get("name") or "")
        if not name:
            continue
        start = md.find("### " + name)
        if start < 0:
            continue
        nxt = md.find("\n### ", start + 4)
        section = md[start: nxt if nxt > 0 else len(md)]
        says_no_ai = "No AI in this part" in section
        has_ai = bool(m.get("ai_involvement"))
        if says_no_ai and has_ai:
            out.append({"severity": "high", "source": "structural", "where": f"technical: {name}",
                        "issue": f"'{name}' is specified with an AI component but its section says 'No AI in this part — deliberately'.",
                        "fix": "describe the module's AI role from its spec, or remove the AI from the spec"})
        if not says_no_ai and not has_ai and re.search(r"\*\*What the AI does on its own:\*\*\s*(?!No AI)", section):
            out.append({"severity": "high", "source": "structural", "where": f"technical: {name}",
                        "issue": f"'{name}' has no AI component in its spec but its section describes AI behavior.",
                        "fix": "write 'No AI in this part — deliberately.' for this module"})
    return out


_PHASE_LINE = re.compile(r"(?im)^\s*[-*]\s*\*\*Phase\s+(\d+)\s*[—–-]\s*([^*:]+?):?\*\*")


def phase_name_findings(blueprint_md: str, modules: list) -> list[dict]:
    """A phase is named for a capability, never as a list of modules
    (run 47: 'Phase 2 — A, B, C, D' with four module names)."""
    out = []
    names = [str(m.get("client_facing_name") or m.get("name") or "") for m in (modules or []) if isinstance(m, dict)]
    for m in _PHASE_LINE.finditer(blueprint_md or ""):
        label = m.group(2).strip()
        hits = [n for n in names if n and n in label]
        if len(hits) >= 2 or (len(hits) == 1 and "," in label and m.group(1) != "1"):
            out.append({"severity": "high", "source": "structural", "where": f"The decision, Phase {m.group(1)}",
                        "issue": f"Phase {m.group(1)} is named as a list of modules ('{label[:90]}') instead of one capability.",
                        "fix": "name the phase for what it delivers; list its modules in the sentence, not the name"})
    return out


def proposals(reg: dict) -> list[dict]:
    """Every consultant-proposed numeric claim still awaiting acceptance —
    the list the client signs off, and nothing a document may state as fact."""
    return [c for c in (reg or {}).get("claims") or []
            if c.get("provenance") == "consultant_proposed" and not c.get("accepted")]


def type_technical_specs(modules: list, claims: list[dict], counter: dict) -> list[dict]:
    """Run the threshold pass over every structured technical field the
    technical plan is written FROM — done_when, evaluation, build_sequence,
    security, spec features — so the prose inherits typed, labeled values."""
    new: list[dict] = []
    for m in modules or []:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "module")
        phase = m.get("phase") or "FUTURE"
        tech = m.get("tech") or {}
        if isinstance(tech, dict):
            for key in ("done_when", "build_sequence", "security"):
                items = tech.get(key)
                if isinstance(items, list):
                    for i, it in enumerate(items):
                        if isinstance(it, str):
                            items[i], c = threshold_pass(it, claims, source=f"tech.{key}[{i}]",
                                                         module_id=mid, counter=counter, phase=phase)
                            new += c
            agent = tech.get("ai_agent")
            if isinstance(agent, dict):
                for key in ("evaluation", "guardrails"):
                    items = agent.get(key)
                    if isinstance(items, list):
                        for i, it in enumerate(items):
                            if isinstance(it, str):
                                items[i], c = threshold_pass(it, claims, source=f"tech.ai_agent.{key}[{i}]",
                                                             module_id=mid, counter=counter, phase=phase)
                                new += c
                if isinstance(agent.get("escalation"), str):
                    agent["escalation"], c = threshold_pass(agent["escalation"], claims,
                                                            source="tech.ai_agent.escalation",
                                                            module_id=mid, counter=counter, phase=phase)
                    new += c
        # client-facing strings outside the spec proper carry thresholds too
        for key in ("purpose", "pain_point_addressed"):
            if isinstance(m.get(key), str):
                m[key], c = threshold_pass(m[key], claims, source=f"module.{key}", module_id=mid,
                                           counter=counter, phase=phase)
                new += c
        if isinstance(tech, dict):
            for key in ("apis",):
                for i, it in enumerate(tech.get(key) or []):
                    if isinstance(it, dict) and isinstance(it.get("does"), str):
                        it["does"], c = threshold_pass(it["does"], claims, source=f"tech.{key}[{i}].does",
                                                       module_id=mid, counter=counter, phase=phase)
                        new += c
            for i, it in enumerate(tech.get("integration_details") or []):
                if isinstance(it, dict) and isinstance(it.get("data"), str):
                    it["data"], c = threshold_pass(it["data"], claims, source=f"tech.integration_details[{i}].data",
                                                   module_id=mid, counter=counter, phase=phase)
                    new += c
            agent = tech.get("ai_agent")
            if isinstance(agent, dict):
                for i, t in enumerate(agent.get("tools") or []):
                    if isinstance(t, dict) and isinstance(t.get("does"), str):
                        t["does"], c = threshold_pass(t["does"], claims, source=f"tech.ai_agent.tools[{i}].does",
                                                      module_id=mid, counter=counter, phase=phase)
                        new += c
                for key in ("brain", "memory"):
                    if isinstance(agent.get(key), list):
                        for i, it in enumerate(agent[key]):
                            if isinstance(it, str):
                                agent[key][i], c = threshold_pass(it, claims, source=f"tech.ai_agent.{key}[{i}]",
                                                                  module_id=mid, counter=counter, phase=phase)
                                new += c
                    elif isinstance(agent.get(key), str):
                        agent[key], c = threshold_pass(agent[key], claims, source=f"tech.ai_agent.{key}",
                                                       module_id=mid, counter=counter, phase=phase)
                        new += c
        spec = m.get("spec") or {}
        if isinstance(spec, dict):
            for key in ("data", "screens", "integrations"):
                if isinstance(spec.get(key), list):
                    for i, it in enumerate(spec[key]):
                        if isinstance(it, str):
                            spec[key][i], c = threshold_pass(it, claims, source=f"spec.{key}[{i}]",
                                                             module_id=mid, counter=counter, phase=phase)
                            new += c
            for i, f in enumerate(spec.get("features") or []):
                if isinstance(f, dict) and isinstance(f.get("description"), str):
                    f["description"], c = threshold_pass(f["description"], claims,
                                                         source=f"spec.features[{i}]",
                                                         module_id=mid, counter=counter, phase=phase)
                    new += c
            ai = spec.get("ai")
            if isinstance(ai, dict):
                for key in ("decides_alone", "hands_off", "role"):
                    if isinstance(ai.get(key), str):
                        ai[key], c = threshold_pass(ai[key], claims, source=f"spec.ai.{key}",
                                                    module_id=mid, counter=counter, phase=phase)
                        new += c
    return new


def type_procedures(procedures: list, claims: list[dict], counter: dict) -> list[dict]:
    """Operational policies live in procedures, checklists and the pilot SOP:
    every wait, retry, cut-off is typed and labeled the same way."""
    new: list[dict] = []
    for p in procedures or []:
        if not isinstance(p, dict):
            continue
        pid = re.sub(r"[^a-z0-9]+", "-", str(p.get("name") or "procedure").lower()).strip("-")[:30]
        phase = str(p.get("phase") or "future").upper()
        for key in ("trigger",):
            if isinstance(p.get(key), str):
                p[key], c = threshold_pass(p[key], claims, source=f"procedures.{key}",
                                           module_id=pid, counter=counter, phase=phase)
                for cc in c:
                    cc["type"] = "operational_policy" if cc["type"] in ("proposed_threshold", "timing_sla") else cc["type"]
                new += c
        for i, st in enumerate(p.get("steps") or []):
            if isinstance(st, dict) and isinstance(st.get("step"), str):
                st["step"], c = threshold_pass(st["step"], claims, source=f"procedures.steps[{i}]",
                                               module_id=pid, counter=counter, phase=phase)
                for cc in c:
                    cc["type"] = "operational_policy" if cc["type"] in ("proposed_threshold", "timing_sla") else cc["type"]
                new += c
        for i, ex in enumerate(p.get("exceptions") or []):
            if isinstance(ex, dict):
                for key in ("when", "then"):
                    if isinstance(ex.get(key), str):
                        ex[key], c = threshold_pass(ex[key], claims, source=f"procedures.exceptions[{i}].{key}",
                                                    module_id=pid, counter=counter, phase=phase)
                        for cc in c:
                            cc["type"] = "operational_policy" if cc["type"] in ("proposed_threshold", "timing_sla") else cc["type"]
                        new += c
    return new


# ── module KPI statements ─────────────────────────────────────────────────────

_KPI_NUMERIC_CLAUSE = re.compile(
    r"(\b(?:a|an|by|of|at least|over|under|to|reach(?:es)?|increases? by|decreases? by|"
    r"reduction (?:in|of)|reduces? by|improves? by|higher|lower|from|within|for the first|for)\s+)?"
    r"~?\$?\d[\d,]*(?:\.\d+)?\s*(?:percentage[- ]points?|percent|%|pp\b|minutes?|hours?|days?|weeks?|"
    r"months?|seconds?)?(?:\s*(?:higher|lower|increase|decrease|reduction|improvement))?"
    r"(?:\s*\(proposed — client approval required\))?", re.IGNORECASE)


_HORIZON = re.compile(r"\s*\(?\s*within\s+\d+\s*(?:weeks?|months?|days?)\s+of\s+(?:pilot\s+)?launch\s*\)?", re.IGNORECASE)
_STUBS = re.compile(r"\b(?:is|are)\s+(?:observed|achieved|reached|maintained|seen|met)\b|\bof launch\b|"
                    r"\b(?:compared to|versus|vs\.?) a control group\b", re.IGNORECASE)
_BASIS_TYPES = {"client_fact": ("client_fact",), "pilot_gate": ("pilot_gate",),
                "scenario_assumption": ("scenario_assumption",)}


def _strip_numbers(s: str) -> str:
    out = (s or "").replace(PROPOSED_LABEL, "")
    out = _HORIZON.sub("", out)
    out = _KPI_NUMERIC_CLAUSE.sub("", out)
    out = _STUBS.sub("", out)
    out = re.sub(r"\(\s*\)", "", out)
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" ,;:-—.")
    return out


def kpi_statements(modules: list, claims: list[dict], gate: dict | None) -> list[dict]:
    """Render every module's KPI statement from registered claims. The model's
    candidates (structured {metric, basis, value, unit, horizon} or legacy
    strings) are mapped: a value that IS a client fact, a scenario assumption
    or the gate renders with its claim id; anything else is registered as a
    consultant proposal and does NOT render. The pilot module's KPI is the
    canonical gate sentence. Returns the KPI claims (+ proposals)."""
    out: list[dict] = []
    sentence = _pg.canonical_sentence(gate) if gate else ""
    for m in modules or []:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "module")
        spec = m.get("spec") if isinstance(m.get("spec"), dict) else {}
        if m.get("spec") is None:
            m["spec"] = spec = {}
        # idempotent: a rebuild reads the model's candidates, never its own renderings
        candidates = spec.get("kpi_candidates") if "kpi_candidates" in spec else (spec.get("kpis") or [])
        rendered: list[str] = []
        n = 0
        if m.get("pilot") and sentence:
            rendered.append(sentence)
            out.append(_claim(f"MK-{mid}-gate", "module_kpi", gate.get("target_value"), gate.get("target_unit") or "",
                              phase="PILOT", scope=mid, provenance="canonical_gate",
                              approval=gate.get("approval_status") or "consultant_proposed — client approval required",
                              source="pilot_gate", sections=["module_kpi", "decision", "scoreboard"],
                              text=sentence, maps_to="PG"))
        for cand in candidates:
            n += 1
            if isinstance(cand, dict):
                metric = _strip_numbers(str(cand.get("metric") or ""))
                value = cand.get("value")
                unit = str(cand.get("unit") or "")
                basis = str(cand.get("basis") or "").lower()
                raw = f"{metric} {value if value is not None else ''} {unit}".strip()
                if unit == "%" and isinstance(value, (int, float)) and value > 1:
                    value = value / 100.0
            else:
                # a legacy free-text KPI: a number in it is a coinage by
                # definition — value coincidence with a claim is not provenance
                raw = str(cand)
                metric = _strip_numbers(raw)
                nums = _numbers(raw)
                value = nums[0][1] if nums else None
                unit = nums[0][2] if nums else ""
                basis = "measure_in_week_1" if value is None else "proposed"
            if not metric:
                continue
            if gate and _pg._mentions_metric(metric, gate):
                # the gate's metric belongs to the pilot gate alone: the pilot
                # module already carries the canonical sentence, and a later-
                # phase module may not claim the pilot's success as its own
                continue
            known = None
            if isinstance(value, (int, float)) and basis in _BASIS_TYPES:
                known = _matches_claim(float(value), "%" if unit == "%" else unit, claims, _BASIS_TYPES[basis])
            if isinstance(value, (int, float)) and known is not None:
                shown_unit = "" if unit in ("count", "number", "") else (" " + unit if unit != "%" else "")
                shown = f"{value:.0%}" if unit == "%" and value <= 1 else f"{value:g}{shown_unit}"
                if known["type"] == "client_fact":
                    # a client figure is context a KPI starts from — named with
                    # its question so it is never read as the metric's own baseline
                    fact = str(known.get("text") or shown).strip()
                    q = str(known.get("question") or "").strip().rstrip("?")
                    related = f"{q}: {fact}" if q else fact
                    stmt = f"{metric} — {WEEK_ONE_SENTENCE[:-1]} (your related figure: {related})."
                elif known["type"] == "scenario_assumption":
                    stmt = f"{metric}: {shown} {PROPOSED_LABEL[:-1]}; our scenario assumption)."
                else:
                    stmt = f"{metric}: {shown} {PROPOSED_LABEL[:-1]}; from the pilot decision gate)."
                rendered.append(stmt)
                out.append(_claim(f"MK-{mid}-{n:02d}", "module_kpi", value, unit or "count", scope=mid,
                                  phase=m.get("phase") or "FUTURE", provenance=known["provenance"],
                                  approval=known["approval_status"], source=f"spec.kpis[{n - 1}]",
                                  sections=["module_kpi"], text=stmt, maps_to=known["id"]))
            elif isinstance(value, (int, float)):
                # a coined number: registered as a proposal, never rendered
                out.append(_claim(f"MK-{mid}-{n:02d}", "module_kpi", value, unit or "count", scope=mid,
                                  phase=m.get("phase") or "FUTURE", provenance="consultant_proposed",
                                  approval="consultant_proposed — client approval required",
                                  source=f"spec.kpis[{n - 1}]", sections=[], text=f"{metric}: {raw}",
                                  accepted=False, metric=metric))
                rendered.append(f"{metric} — {WEEK_ONE_SENTENCE}")
            else:
                rendered.append(f"{metric} — {WEEK_ONE_SENTENCE}")
        if not rendered:
            pain = str(m.get("pain_point_addressed") or m.get("purpose") or "the outcome this part exists for")
            pain = pain.rstrip(".")
            rendered.append(f"{pain[0].upper() + pain[1:]} — {WEEK_ONE_SENTENCE}")
        # a FUTURE module's week one is its first week live, not the pilot's
        if not m.get("pilot"):
            rendered = [r.replace(WEEK_ONE_SENTENCE, WEEK_ONE_SENTENCE[:-1] + " once this module is live.")
                        .replace(WEEK_ONE_SENTENCE[:-1] + " (your related figure",
                                 WEEK_ONE_SENTENCE[:-1] + " once this module is live (your related figure")
                        for r in rendered]
        # de-duplicate while preserving order
        seen = set()
        rendered = [r for r in rendered if not (r in seen or seen.add(r))]
        spec["kpi_candidates"] = candidates
        spec["kpis"] = rendered
        spec["kpi_statement"] = " ".join(rendered)
    return out


# ── the registry ──────────────────────────────────────────────────────────────


def build_registry(ops_numbers_json: str | None, business_case: dict, modules: list,
                   free_texts: list[str] | None = None, procedures: list | None = None) -> dict:
    """Build (and apply) the registry for one engagement. MUTATES modules and
    business_case: pilot-module renames, typed/labeled technical fields,
    registry-rendered KPI statements, the normalized pilot gate."""
    try:
        ops = json.loads(ops_numbers_json) if ops_numbers_json else []
    except ValueError:
        ops = []
    bc = business_case if isinstance(business_case, dict) else {}
    fm = bc.get("financial_model") if isinstance(bc.get("financial_model"), dict) else {}
    claims = client_fact_claims(ops, free_texts or [])
    claims += derived_claims(fm)
    reg_modules, renames = module_registry(modules, bc)
    gate = None
    if isinstance(bc.get("pilot_gate"), dict) and bc["pilot_gate"]:
        gate = _pg.normalize_gate(bc["pilot_gate"], claims)
        bc["pilot_gate"] = gate
        claims += _pg.gate_claims(gate)
    enforce_gate_in_specs(modules, gate)
    # the Phase 1 pilot is manual or rules-based BY LAW: an AI component the
    # model specced into the pilot module is removed from it (the AI belongs
    # to the later modules the pilot's data will train)
    pilot_ai_removed = []
    for m in modules or []:
        if isinstance(m, dict) and m.get("pilot"):
            spec = m.get("spec") if isinstance(m.get("spec"), dict) else None
            tech = m.get("tech") if isinstance(m.get("tech"), dict) else None
            if (spec and spec.get("ai")) or (tech and tech.get("ai_agent")):
                pilot_ai_removed.append(m["id"])
                if spec is not None:
                    spec["ai"] = None
                if tech is not None:
                    tech["ai_agent"] = None
                m["ai_involvement"] = False
                m["automation_level"] = "rules" if m.get("automation_level") not in ("manual", "rules") else m["automation_level"]
                for rm in reg_modules:
                    if rm["id"] == m["id"]:
                        rm["ai_involvement"] = False
                        rm["automation_level"] = m["automation_level"]
    policy_notes = []

    def _policy_walk(obj, key=None):
        if isinstance(obj, str):
            if key in ("id", "name", "entity", "fields", "original_name", "client_facing_name", "alias"):
                return obj
            fixed, notes = policy_pass(obj, claims)
            policy_notes.extend(notes)
            return fixed
        if isinstance(obj, dict):
            return {k: _policy_walk(v, k) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_policy_walk(v, key) for v in obj]
        return obj

    for m in modules or []:
        if isinstance(m, dict):
            for key in ("spec", "tech", "purpose", "pain_point_addressed"):
                if key in m:
                    m[key] = _policy_walk(m[key], key)
    counter = {"n": 0}
    claims += type_technical_specs(modules, claims, counter)
    if procedures:
        claims += type_procedures(procedures, claims, counter)
    claims += kpi_statements(modules, claims, gate)
    if isinstance(fm, dict) and fm:
        fm["time_basis"] = {"monthly_identity": MONTHLY_IDENTITY, "year_days": YEAR_DAYS,
                            "month_days": MONTH_DAYS}
    reg = {
        "version": 1,
        "monthly_identity": MONTHLY_IDENTITY,
        "claims": claims,
        "modules": reg_modules,
        "renames": renames,
        "policy_corrections": policy_notes,
        "pilot_ai_removed": pilot_ai_removed,
        "pilot_gate": gate,
        "pilot_gate_sentence": _pg.canonical_sentence(gate) if gate else "",
        "build_order_names": [
            next((m["client_facing_name"] for m in reg_modules if m["id"] == mid), mid)
            for mid in (bc.get("build_order") or []) if isinstance(mid, str)],
    }
    reg["errors"] = validate_registry(reg)
    return reg


_REQUIRED = ("id", "type", "value", "unit", "time_basis", "population", "scope", "phase",
             "provenance", "approval_status", "source", "allowed_sections")


def validate_registry(reg: dict) -> list[str]:
    errors = []
    seen = set()
    for c in reg.get("claims") or []:
        for k in _REQUIRED:
            if k not in c:
                errors.append(f"{c.get('id')}: missing {k}")
        if c.get("id") in seen:
            errors.append(f"{c.get('id')}: duplicate id")
        seen.add(c.get("id"))
        if c.get("type") not in CLAIM_TYPES:
            errors.append(f"{c.get('id')}: unknown type {c.get('type')}")
        if c.get("provenance") not in PROVENANCE:
            errors.append(f"{c.get('id')}: unknown provenance {c.get('provenance')}")
        if c.get("approval_status") not in APPROVAL:
            errors.append(f"{c.get('id')}: unknown approval {c.get('approval_status')}")
        if c.get("provenance") == "consultant_proposed" and \
                c.get("approval_status") != "consultant_proposed — client approval required":
            errors.append(f"{c.get('id')}: a consultant proposal must carry the approval-required status")
        if c.get("type") == "time_basis_conversion" and c.get("time_basis") not in ("day", "week", MONTHLY_IDENTITY, "year"):
            errors.append(f"{c.get('id')}: conversion on a non-canonical basis {c.get('time_basis')}")
    if reg.get("monthly_identity") != MONTHLY_IDENTITY:
        errors.append("monthly identity is not the package identity")
    for m in reg.get("modules") or []:
        if m.get("pilot") and _AI_NAME.search(m.get("client_facing_name") or ""):
            errors.append(f"module {m['id']}: pilot-phase name implies predictive intelligence")
        if m.get("pilot") and m.get("automation_level") == "ai":
            errors.append(f"module {m['id']}: a pilot module cannot be AI-automated")
    ids = {m["id"] for m in reg.get("modules") or []}
    names = reg.get("build_order_names") or []
    if ids and len(names) != len(ids):
        errors.append("build order does not cover every module exactly once")
    gate = reg.get("pilot_gate")
    if gate:
        errors += [f"pilot_gate: {e}" for e in _pg.gate_errors(gate)]
    return errors


# ── final-text validation ─────────────────────────────────────────────────────

_KPI_SENTENCE = re.compile(
    r"[^.\n]*(know it.?s working|it.?s finished when|decision gate|pilot decision gate|"
    r"success criteri|acceptance)[^\n]*?(?:\.(?=\s|$)|\n|$)", re.IGNORECASE)


def claim_values(reg: dict) -> list[tuple[float, dict, str]]:
    """(value, unit-bearing claim, id) for every number a document may state."""
    vals = []
    for c in reg.get("claims") or []:
        v = c.get("value")
        if isinstance(v, (int, float)) and not (c.get("provenance") == "consultant_proposed"
                                                and c.get("type") == "module_kpi" and not c.get("accepted")):
            vals.append((float(v), c, c["id"]))
    gate = reg.get("pilot_gate") or {}
    unit_of = {"target_value": "percentage points" if gate.get("change_kind") == "percentage_point" else "%",
               "baseline_value": "%" if "%" in str(gate.get("baseline") or "") else "count",
               "duration_value": (gate.get("duration_unit") or "week") + "s",
               "guardrail_value": "count"}
    for key, unit in unit_of.items():
        if isinstance(gate.get(key), (int, float)):
            v = float(gate[key])
            if unit == "%" and v > 1:
                v = v / 100.0
            vals.append((v, {"unit": unit, "time_basis": "n/a"}, "PG"))
            if key == "target_value":  # stated as "5 percentage points" or "5 pp" or "5%"
                vals.append((v, {"unit": "%", "time_basis": "n/a"}, "PG"))
                vals.append((v / 100.0, {"unit": "%", "time_basis": "n/a"}, "PG"))
    # every number the typed gate's own component strings carry is the gate's
    for s in [gate.get("baseline") or ""] + list(gate.get("guardrails") or []) + [gate.get("population") or ""]:
        for tok, v, unit, _, _ in _numbers(str(s)):
            vals.append((v, {"unit": unit or "count", "time_basis": "n/a"}, "PG"))
    return vals


def _value_registered(v: float, unit: str, vals: list) -> bool:
    for cv, claim, _ in vals:
        if not _close(v, cv):
            continue
        if unit in ("percentage points", "percentage point", "pp"):
            if str(claim.get("unit") or "").startswith("percentage") or claim.get("unit") in ("%", "ratio"):
                return True
            continue
        if _unit_compatible(unit, claim):
            return True
    return False


def kpi_number_findings(text: str, reg: dict, strict_kpi: bool = False) -> list[dict]:
    """Every number inside a KPI / acceptance / gate sentence of the
    finished text must map to a registered claim — an unmapped number is a
    coined target and blocks release. With strict_kpi (Volume I), a KPI
    sentence may draw only on KPI-grade claims; Volume II's 'how you'll know
    it's working' carries typed, labeled evaluation thresholds as well."""
    findings = []
    vals = claim_values(reg)
    # rendered PDF text wraps sentences across lines: judge on collapsed whitespace
    text = re.sub(r"\s+", " ", text or "")
    canon = re.sub(r"\s+", " ", reg.get("pilot_gate_sentence") or "")
    if canon:
        text = text.replace(canon, " [canonical gate sentence] ")
    # a KPI sentence may draw only on KPI-grade claims (client facts, verified
    # derivations, scenario assumptions, the gate, registry KPI statements);
    # an acceptance / evaluation sentence may also draw on typed thresholds
    kpi_vals = [(v, c, cid) for v, c, cid in vals
                if cid == "PG" or "*" in (c.get("allowed_sections") or [])
                or "module_kpi" in (c.get("allowed_sections") or [])
                or str(c.get("type")) in ("pilot_gate", "module_kpi")]
    for m in _KPI_SENTENCE.finditer(text or ""):
        sentence = m.group(0)
        is_kpi = strict_kpi and bool(re.search(r"know it.?s working|success criteri", sentence, re.IGNORECASE)) and \
            not re.search(r"finished when|acceptance|evaluation", sentence, re.IGNORECASE)
        pool = kpi_vals if is_kpi else vals
        for tok, v, unit, s, e in _numbers(sentence):
            ok = _value_registered(v, unit, pool)
            if not ok:
                findings.append({
                    "severity": "high", "source": "structural", "where": "KPI / acceptance statement",
                    "issue": (f"The number '{tok}{(' ' + unit) if unit else ''}' in a KPI or acceptance "
                              f"statement maps to no registered claim: \"{sentence.strip()[:160]}\""),
                    "fix": "state the metric without a coined number, or register the value as a claim",
                })
    return findings


def registry_for(req) -> dict | None:
    try:
        return json.loads(req.registry_json) if getattr(req, "registry_json", None) else None
    except ValueError:
        return None
