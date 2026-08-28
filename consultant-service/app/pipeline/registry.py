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
NO_AUTONOMY = "Nothing on its own — it proposes, a human decides"
_NULLISH = {"", "null", "none", "n/a", "na", "nil", "-", "—"}
_SLUG_TOKEN = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)+$")
_ID_FIELDS = {"id", "name", "tools", "apis", "data_models", "components", "services", "tables", "events",
              "endpoints", "enabled_by", "backstage_modules", "integrations", "queues", "topics"}


def technical_identifiers(modules: list) -> list[str]:
    """Every slug-shaped identifier the structured technical anatomy declares
    (module ids, data models, services, queues …) — the registry's list of
    what counts as an internal identifier when it appears in client prose."""
    found: set[str] = set()

    def _walk(obj, under_id_field: bool):
        if isinstance(obj, str):
            tok = obj.strip()
            if under_id_field and _SLUG_TOKEN.match(tok):
                found.add(tok)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                _walk(v, under_id_field or k in _ID_FIELDS)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v, under_id_field)

    for m in modules or []:
        if isinstance(m, dict):
            if _SLUG_TOKEN.match(str(m.get("id") or "")):
                found.add(str(m["id"]))
            _walk(m.get("tech"), False)
            _walk(m.get("spec"), False)
    return sorted(found)

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
    r"option|v|q|run|no\.|#|tls|ssl|oauth|https?/?|api\s?v|http status|status code|error code)\s*|[A-Za-z0-9]-|claim\s+[A-Z]{2}-[\w-]*)$",
    re.IGNORECASE)
_SKIP_AFTER = re.compile(
    r"^\s*(/7|x\b|×|am\b|pm\b|:\d|-\w|\.\s+[A-Z]|\(proposed[^)]*\)\.\s+[A-Z]|"  # "3. Then, we …" is an inline ordinal
    r"(?:Forbidden|Not Found|Unauthorized|Bad Request|Internal Server Error|Conflict|Gone|Created|Accepted)\b|"  # HTTP codes
    r"(?:phases?|steps?|parts?|modules?|volumes?|sections?|pages?|records?|"
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
# the same sanctioned block as it survives PDF extraction, where it is HARD
# WRAPPED across several physical lines. The line-anchored form above exempts
# only the first of them, so the identifiers on the continuation lines used to
# read as internal identifiers loose in client-facing prose. A continuation is
# a line that does not itself start a new bullet, heading or paragraph.
_BUILD_TEAM_BLOCK = re.compile(r"For your build team:(?:[^\n•]|\n(?!\s*(?:\n|[-*•#]|\d+\.\s)))*", re.IGNORECASE)
_APPENDIX_START = re.compile(r"Module appendix\s*[—–-]\s*the engineering detail", re.IGNORECASE)
_APPENDIX_END = re.compile(r"Three ways forward", re.IGNORECASE)


def client_facing_region(text: str) -> str:
    """The text a client reads as prose: Volume II's module appendix is
    declared engineering detail (data models, APIs, tools) and is excluded."""
    t = text or ""
    starts = list(_APPENDIX_START.finditer(t))
    if not starts:
        return t
    m = starts[-1]  # the section itself, not its table-of-contents entry
    ends = [e for e in _APPENDIX_END.finditer(t) if e.start() > m.end()]
    e = ends[-1] if ends else None
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


# the EVENT a policy period counts from ("10 days after month-end") is part
# of the fact — a document that keeps the number and moves the origin
# ("10 days after order delivery") states a policy the client never gave
_EVENT = re.compile(r"\b(?:after|from|following|since|post)\s+(?:the\s+)?([a-z][a-z\-]{2,}(?:\s+[a-z][a-z\-]{2,}){0,3}?)"
                    r"(?=\s+(?:to|for|before|until)\b|\s*[?,.;:]|\s*$)", re.IGNORECASE)
_POLICY_Q = re.compile(r"settle|remit|payout|pay out|disburse|invoice|billing|cycle", re.IGNORECASE)


def event_origin(question: str, answer: str = "") -> str | None:
    """'Days after month-end to fully settle COD?' -> 'after month-end'."""
    for s in (answer or "", question or ""):
        m = _EVENT.search(s)
        if m:
            return re.sub(r"\s+", " ", m.group(0).strip().lower())
    return None


def client_fact_claims(ops_numbers: list, free_texts: list[str]) -> list[dict]:
    claims = []
    n = 0
    for pair in ops_numbers or []:
        if not isinstance(pair, dict):
            continue
        q, a = str(pair.get("question") or ""), str(pair.get("answer") or "")
        origin = event_origin(q, a) if _POLICY_Q.search(q) else None
        for tok, v, unit, s, e in _numbers(a):
            n += 1
            u, basis = _infer_unit(tok, unit, a[max(0, s - 30):e + 30] + " " + q)
            claims.append(_claim(
                f"CF-{n:02d}", "client_fact", v, u, time_basis=basis,
                provenance="client_input", approval="client_stated",
                source=f"discovery: {q}", sections=["*"], text=a.strip(),
                question=q, **({"event": origin} if origin else {})))
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
        if line.get("unit"):
            u = str(line["unit"])  # the unit the arithmetic itself declares (hours x weeks = hours)
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
    or rules-based pilot. '<Workflow> Engine' -> '<Workflow> Pilot'.
    Deterministic, so the same name lands in all volumes."""
    stripped = _AI_NAME.sub("", name or "").strip()
    stripped = re.sub(r"\s{2,}", " ", stripped).strip(" -—:")
    if not stripped:
        stripped = "Manual"
    if not re.search(r"\bpilot\b", stripped, re.IGNORECASE):
        stripped += " Pilot"
    return stripped


_CUSTOMER_USER = re.compile(r"customer|client|shopper|patient|guest|member|tenant|passenger|end[- ]user", re.IGNORECASE)
_STAFF_ONLY = re.compile(r"^(?:[^a-z]*(?:staff|team|agent|dispatch|operator|manager|finance|support|admin)[^a-z]*)+$", re.IGNORECASE)
_CUSTOMER_ACT = re.compile(r"\b(?:customers?|clients?|shoppers?|patients?|guests?|members?|end[- ]users?)\b[^.;]{0,120}?"
                           r"\b(?:link|form|confirms?|reply|replies|responds?|submits?|access(?:es)?|opens?|receives?|clicks?|taps?|"
                           r"drops?|pins?|uploads?|fills?)\b", re.IGNORECASE)
_LINK_TO_QUEUE = re.compile(r"\b(?:link|form|page|url)\s+to\s+(?:the\s+)?", re.IGNORECASE)


def customer_facing_pass(text: str) -> tuple[str, list[dict]]:
    return channel_pass(text, _pg.PILOT_TOOLING, _pg.PILOT_CUSTOMER_FORM)


def channel_pass(text: str, internal_name: str, customer_name: str) -> tuple[str, list[dict]]:
    """Name for the same thing's other name: a clause in which a customer
    receives, opens or fills something names the CUSTOMER-facing interface,
    never the internal one. Both names come from the registry, so this is an
    exact canonical mapping between two registered entities — no wording is
    invented and no similarity decides anything. The caller applies it only
    when the registry holds exactly one interface of each audience."""
    records: list[dict] = []
    if not text or internal_name not in text:
        return text, records
    # clause by clause: the customer's action must precede the mention inside
    # the same clause ("customers confirm … via a link to the queue"), never a
    # later clause about staff ("; flagged orders go to the queue")
    parts = re.split(r"((?<=[.!?;])\s+)", text)
    out = []
    for s in parts:
        if _customer_meets(s, internal_name):
            fixed = s.replace(internal_name + " module", customer_name).replace(internal_name, customer_name)
            records.append({"original": s.strip()[:140], "replaced_with": customer_name})
            out.append(fixed)
        else:
            out.append(s)
    return "".join(out), records


def _customer_meets_queue(clause: str) -> bool:
    return _customer_meets(clause, _pg.PILOT_TOOLING)


def _customer_meets(clause: str, internal_name: str) -> bool:
    """The clause sends a customer into the internal interface: a customer
    acts on it (before or after the mention), it is a link/URL a customer
    uses, or the clause is about a customer's access to it."""
    if internal_name not in clause:
        return False
    before = clause.split(internal_name)[0]
    if _CUSTOMER_ACT.search(clause) or _LINK_TO_QUEUE.search(before[-20:]):
        return True
    if re.search(r"\b(?:link|URL|web page|page)\b", clause, re.IGNORECASE) and re.search(r"\bcustomers?\b", clause, re.IGNORECASE):
        return True
    # something reached through a link is what the customer receives
    return bool(re.search(r"\baccessed via\b|\b(?:via|through)\s+(?:a|an|the)?\s*(?:\w+\s+)?link\b|\blink contains\b|"
                          r"\bunique URL\b", clause, re.IGNORECASE))


def _integration_entries(module: dict):
    tech = module.get("tech") if isinstance(module.get("tech"), dict) else {}
    for key in ("integrations", "integration_details"):
        for it in tech.get(key) or []:
            if isinstance(it, dict):
                yield key, it


def _entry_is_customer_facing(entry: dict) -> bool:
    text = " ".join(str(v) for k, v in entry.items() if k != "system" and isinstance(v, str))
    return bool(_CUSTOMER_ACT.search(text) or (re.search(r"\b(?:link|URL|web page|page)\b", text, re.IGNORECASE)
                                               and re.search(r"\bcustomers?\b", text, re.IGNORECASE)))


def integration_channel_pass(module: dict, internal_name: str = "", customer_name: str = "") -> list[dict]:
    """An integration entry whose own description says a customer opens,
    receives or fills it is the customer-facing interface, not the internal
    one — the entry's `system` field is corrected as one unit.

    The entry is the unit because the `system` field holds a bare name: the
    audience lives in the sibling fields, so no clause-level rule can see it."""
    internal_name = internal_name or _pg.PILOT_TOOLING
    customer_name = customer_name or _pg.PILOT_CUSTOMER_FORM
    records = []
    for key, entry in _integration_entries(module):
        if str(entry.get("system") or "") == internal_name and _entry_is_customer_facing(entry):
            entry["system"] = customer_name
            records.append({"module": module.get("id"), "field": f"tech.{key}", "replaced_with": customer_name,
                            "original": " ".join(str(v) for v in entry.values())[:120]})
    return records


def integration_channel_findings(module: dict) -> list[dict]:
    return [{"severity": "high", "source": "structural", "where": f"modules.{module.get('id')}.tech.{key}",
             "issue": f"An integration the customer uses is named as the internal {_pg.PILOT_TOOLING}: "
                      f"\"{' '.join(str(v) for v in entry.values())[:140]}\"",
             "fix": f"the customer-facing integration is the {_pg.PILOT_CUSTOMER_FORM}"}
            for key, entry in _integration_entries(module)
            if str(entry.get("system") or "") == _pg.PILOT_TOOLING and _entry_is_customer_facing(entry)]


def customer_queue_findings(text: str, label: str = "") -> list[dict]:
    out = []
    flat = _pg.flatten_prose(text)
    if _pg.PILOT_TOOLING not in flat:
        return out
    for s in re.split(r"(?<=[.!?;])\s+|•", flat):
        if _customer_meets_queue(s):
            out.append({"severity": "high", "source": "structural", "where": f"{label}: pilot customer channel".strip(": "),
                        "issue": f"A customer is sent into the internal {_pg.PILOT_TOOLING}: \"{s.strip()[:160]}\"",
                        "fix": f"the customer receives the {_pg.PILOT_CUSTOMER_FORM}; the queue stays internal"})
    return out


# ── the pilot population is the gate's population ────────────────────────────
_POP_QUALIFIER = re.compile(r"\b(?:for|to|of|covering|limited to|only for|restricted to|scheduled for)\s+(?:their\s+|all\s+|the\s+|new\s+)?"
                            r"((?:[a-z]+(?:-[a-z]+)*\s+){1,4}?)(?:orders?|deliveries|shipments|delivery)\b", re.IGNORECASE)
_POP_GENERIC = {"new", "eligible", "individual", "customer", "customers", "delivery", "deliveries", "pilot", "mobile", "app",
                "order", "orders", "their", "all", "the", "and", "or", "standard", "each", "every", "treatment", "control",
                "group", "selected", "business", "client", "clients", "scheduled", "same", "these", "those", "such", "pending",
                "confirmed", "unconfirmed", "flagged", "high-risk", "incoming", "daily", "todays", "today's"}
_POP_ALIASES = {"cod": ("cash-on-delivery", "cash on delivery", "cod")}


def _population_words(gate: dict | None) -> set[str]:
    blob = " ".join(str((gate or {}).get(k) or "") for k in ("population", "numerator", "denominator", "geography")).lower()
    words = set(re.findall(r"[a-z][a-z-]*", blob))
    for w in list(words):
        words.update(w.split("-"))
    return words


def service_types(free_texts: list[str]) -> list[str]:
    """The client's own service types: the qualifiers the client puts in front
    of 'orders' / 'deliveries' in the brief ('e-commerce COD orders, same-day
    and express on-demand deliveries' -> e-commerce, cod, same-day, express,
    on-demand). Only these can narrow a pilot population."""
    found: set[str] = set()
    for t in free_texts or []:
        for m in _SERVICE_QUALIFIER.finditer(str(t or "")):
            for w in m.group(1).lower().split()[-4:]:
                # a service type names an offering (same-day, on-demand, COD,
                # e-commerce) — never a state ("failed"), a verb ("flags") or
                # a question word ("where")
                if w in _POP_GENERIC or w in _NOT_A_TYPE or len(w) < 3 or w in _STATE_WORDS:
                    continue
                if re.search(r"(?:ed|ing)$", w) and "-" not in w:
                    continue
                found.add(w)
    return sorted(found)


_STATE_WORDS = {"failed", "failing", "successful", "completed", "unconfirmed", "confirmed", "pending", "flagged", "flags",
                "late", "delayed", "missed", "cancelled", "canceled", "returned", "first", "first-attempt", "re-attempt",
                "attempted", "where", "current", "known", "historical", "previous", "existing", "eligible", "new", "open",
                "closed", "active", "inactive", "high-risk", "low-risk", "risky", "problem", "problematic", "unresolved",
                "resolved", "escalated", "treatment", "control"}


# the run of words right before the unit noun, wherever it sits in the brief
_SERVICE_QUALIFIER = re.compile(r"((?:[A-Za-z][A-Za-z-]*\s+){1,4}?)(?:orders?|deliveries|shipments)\b", re.IGNORECASE)
_NOT_A_TYPE = {"we", "our", "your", "their", "they", "you", "deliver", "delivers", "delivering", "handle", "handles",
               "handling", "process", "processes", "manage", "manages", "ship", "ships", "collect", "collects", "receive",
               "receives", "include", "includes", "including", "offer", "offers", "provide", "provides", "support",
               "supports", "serve", "serves", "accept", "accepts", "with", "from", "through", "via", "for", "into",
               "individual", "individuals", "business", "businesses", "more", "most", "many", "some", "few"}


def _narrowing_qualifiers(text: str, gate: dict | None, types: list[str] | None) -> list[str]:
    """Qualifier phrases that restrict the unit noun to a client service type
    the gate's population does not name."""
    pop = _population_words(gate)
    kinds = {t.lower() for t in (types or [])}
    if not pop or not kinds:
        return []
    hits = []
    for m in _POP_QUALIFIER.finditer(text or ""):
        words = [w.lower() for w in m.group(1).split()]
        typed = [w for w in words if w in kinds and w not in _POP_GENERIC]
        if not typed:
            continue

        def _known(w: str) -> bool:
            if w in pop or any(p in pop for p in w.split("-") if len(p) > 2):
                return True
            return any(a in " ".join(sorted(pop)) for a in _POP_ALIASES.get(w, ()))
        if not all(_known(w) for w in typed):
            hits.append(m.group(0))
    return hits


def population_findings(text: str, gate: dict | None, label: str = "", types: list[str] | None = None,
                        pilot_names: list[str] | None = None, pilot_scope: bool = True) -> list[dict]:
    """A pilot string may not narrow the pilot population to a client service
    type the gate never named ('same-day and express deliveries' against a
    population of 'all individual mobile-app orders'). On document text the
    check applies to sentences about the pilot (the word or the pilot
    module's name); a later module's own scope is not the pilot population."""
    out = []
    flat = _pg.flatten_prose(text)
    names = [n for n in (pilot_names or []) if n]
    for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\[(•\d])|•", flat):
        if pilot_scope and not (re.search(r"\bpilot\b", s, re.IGNORECASE) or any(n in s for n in names)):
            continue
        for q in _narrowing_qualifiers(s, gate, types):
            out.append({"severity": "high", "source": "structural", "where": f"{label}: pilot population".strip(": "),
                        "issue": (f"The pilot population is narrowed to '{q.strip()}' — the gate's population is "
                                  f"'{(gate or {}).get('population')}': \"{s.strip()[:160]}\""),
                        "fix": "describe the eligible orders of the pilot population, never a narrower service type"})
            break
    return out


# There is deliberately no population_pass. Narrowing the pilot population is
# a CONFLICT between a sentence and the gate, and the words the sentence should
# have used are not recoverable from the registry: only the author knows
# whether the narrowing or the gate is wrong. The pass that used to substitute
# the literal word "eligible" for whatever it did not recognise is what put
# "[eligible] deliveries" and "eligible delivery success" on run 53's pages.
# population_findings reports it; the release fails closed until it is fixed at
# the source.


# ── one pilot procedure set, labeled operating times ─────────────────────────
# "3. Implement …", "(4) Build …", and a label an earlier pass put between the
# ordinal and its period ("3 (proposed — client approval required). Implement")
_ORDINAL_PREFIX = re.compile(r"^\s*(?:\d{1,2}\s*(?:\(proposed[^)]*\)\s*)?[.):]|\(\d{1,2}\)|[a-z]\s*[.)])\s+(?=\S)")
# an inline ordinal in prose ("… messages. 3. Then, we …") wearing a label
_LABELED_ORDINAL = re.compile(r"(?<![\w$.,])(\d{1,2}) \(proposed — client approval required\)(\.)(?=\s+[A-Z])")


def unlabel_ordinals(text: str) -> str:
    """A number that is a list ordinal is not a threshold: the label an
    earlier pass attached is removed ('3 (proposed …). Then' -> '3. Then')."""
    return _LABELED_ORDINAL.sub(r"\1\2", text) if isinstance(text, str) else text


def ordinal_label_findings(text: str, label: str = "") -> list[dict]:
    out = []
    flat = _pg.flatten_prose(text)
    for m in _LABELED_ORDINAL.finditer(flat):
        out.append({"severity": "high", "source": "structural", "where": f"{label}: list ordinals".strip(": "),
                    "issue": f"A list ordinal is labeled as a proposed threshold: \"{flat[max(0, m.start()-60):m.end()+40]}\"",
                    "fix": "ordinals are never thresholds — strip the label"})
    return out


def strip_ordinal(item: str) -> str:
    """'3. Implement …' in a sequence field is a list item, not a threshold."""
    return _ORDINAL_PREFIX.sub("", item) if isinstance(item, str) else item


_CLOCK = re.compile(r"\b(\d{1,2}(?::\d{2})?\s*(?:AM|PM|a\.m\.|p\.m\.))(?![^()]{0,40}\(proposed)", re.IGNORECASE)
_CADENCE_WORD = re.compile(r"^(\s*)(Daily|Weekly|Twice (?:a |per )day|Every (?:morning|evening|day|week)|Each (?:morning|evening|day))"
                           r"\b(?!\s*\(proposed)", re.IGNORECASE)


def operating_time_pass(text: str) -> tuple[str, list[dict]]:
    """A clock time or a review cadence the client never stated is a
    proposal and carries the label."""
    records: list[dict] = []
    if not isinstance(text, str) or not text:
        return text, records

    def _clock(m: re.Match) -> str:
        records.append({"value": m.group(1), "kind": "clock_time"})
        return m.group(1) + " " + PROPOSED_LABEL

    out = _CLOCK.sub(_clock, text)
    cm = _CADENCE_WORD.match(out)
    if cm:
        records.append({"value": cm.group(2), "kind": "cadence"})
        out = out[:cm.end()] + " " + PROPOSED_LABEL + out[cm.end():]
    return out, records


def operating_time_findings(procedures: list) -> list[dict]:
    out = []
    for p in procedures or []:
        if not isinstance(p, dict):
            continue
        strings = [("trigger", str(p.get("trigger") or ""))] + \
                  [(f"steps[{i}]", str(s.get("step") or "")) for i, s in enumerate(p.get("steps") or []) if isinstance(s, dict)]
        for field, s in strings:
            if _CLOCK.search(s) or _CADENCE_WORD.match(s):
                out.append({"severity": "high", "source": "structural", "where": f"procedures: {p.get('name')} ({field})",
                            "issue": f"An operating time or review cadence is stated without attribution or a proposal label: \"{s[:140]}\"",
                            "fix": "label it '(proposed — client approval required)' or source it from the client"})
                break
    return out


def consolidate_pilot_procedures(procedures: list, pilot_names: set[str]) -> list[dict]:
    """The pilot SOP ('The pilot') is the ONE executable pilot procedure set;
    a pilot-phase procedure filed under the pilot module restates it with
    other mechanics (53-r3: one reminder vs three attempts) and is removed."""
    removed: list[dict] = []
    sop = [p for p in (procedures or []) if isinstance(p, dict) and p.get("module") == "The pilot"
           and str(p.get("phase") or "").lower() == "pilot"]
    if not sop:
        return removed
    for p in list(procedures or []):
        if isinstance(p, dict) and str(p.get("phase") or "").lower() == "pilot" and p.get("module") in pilot_names:
            removed.append({"procedure": p.get("name"), "module": p.get("module"),
                            "reason": "the pilot SOP is the single executable pilot procedure set"})
            procedures.remove(p)
    return removed


_ATTEMPTS = re.compile(r"\b(\d+|one|two|three|four|five)\s+(?:\(proposed[^)]*\)\s*)?(attempts?|reminders?)\b", re.IGNORECASE)
_WORD_N = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _attempt_totals(text: str) -> set[int]:
    """Outreach attempt totals a text states: 'three attempts' -> 3, 'one
    reminder' -> 2 (the first message plus one reminder)."""
    totals = set()
    for m in _ATTEMPTS.finditer(text or ""):
        n = int(m.group(1)) if m.group(1).isdigit() else _WORD_N[m.group(1).lower()]
        totals.add(n + 1 if m.group(2).lower().startswith("reminder") else n)
    return totals


def _procedure_text(p: dict) -> str:
    return " ".join([str(p.get("trigger") or "")] + [str(s.get("step") or "") for s in p.get("steps") or [] if isinstance(s, dict)]
                    + [str(e.get("when") or "") + " " + str(e.get("then") or "") for e in p.get("exceptions") or [] if isinstance(e, dict)])


def pilot_procedure_findings(procedures: list, pilot_names: set[str], modules: list | None = None) -> list[dict]:
    """Two pilot procedure sets, or two different attempt counts anywhere in
    the pilot's specification (its SOP procedures AND the pilot module's
    own strings), are a contradiction the reader cannot resolve."""
    out = []
    pilot = [p for p in (procedures or []) if isinstance(p, dict) and str(p.get("phase") or "").lower() == "pilot"]
    sets = {str(p.get("module")) for p in pilot}
    if "The pilot" in sets and (sets & pilot_names):
        out.append({"severity": "high", "source": "structural", "where": "procedures: pilot",
                    "issue": "Two pilot procedure sets exist (the pilot SOP and module-level pilot procedures) — one workflow "
                             "described twice with different mechanics.",
                    "fix": "keep the pilot SOP as the single executable set"})
    totals = set()
    for p in pilot:
        totals |= _attempt_totals(_procedure_text(p))
    for m in modules or []:
        if isinstance(m, dict) and m.get("pilot"):
            totals |= _attempt_totals(" ".join(s for k in ("purpose", "spec", "tech") for s in _strings_in(m.get(k))))
    if len(totals) > 1:
        out.append({"severity": "high", "source": "structural", "where": "pilot specification",
                    "issue": f"The pilot's specification states different outreach attempt counts: {sorted(totals)} "
                             "(SOP procedures and pilot module strings together).",
                    "fix": "one canonical attempt count across the pilot SOP and the pilot module"})
    return out


def pilot_terms(modules: list) -> list[str]:
    """What marks a sentence as being about the pilot: the pilot module's
    client-facing name and the names of its own features ('Response Tracking
    & Reminder System') — registry data, never a hardcoded phrase."""
    terms: list[str] = []
    for m in modules or []:
        if not (isinstance(m, dict) and m.get("pilot")):
            continue
        for nm in (m.get("client_facing_name"), m.get("name"), m.get("original_name")):
            if nm:
                terms.append(str(nm))
        spec = m.get("spec") if isinstance(m.get("spec"), dict) else {}
        for f in spec.get("features") or []:
            if isinstance(f, dict) and f.get("name") and len(str(f["name"])) > 6:
                terms.append(str(f["name"]))
    return sorted(set(terms), key=len, reverse=True)


def sop_attempt_total(procedures: list) -> int | None:
    """The one outreach attempt total the pilot SOP states (None if it
    states none or several)."""
    sop = [p for p in (procedures or []) if isinstance(p, dict) and p.get("module") == "The pilot"
           and str(p.get("phase") or "").lower() == "pilot"]
    totals = set()
    for p in sop:
        totals |= _attempt_totals(_procedure_text(p))
    return next(iter(totals)) if len(totals) == 1 else None


def _align_attempts(s: str, total: int) -> str:
    words = {v: k for k, v in _WORD_N.items()}

    def _sub(m: re.Match) -> str:
        n = int(m.group(1)) if m.group(1).isdigit() else _WORD_N[m.group(1).lower()]
        kind = m.group(2).lower()
        want = total - 1 if kind.startswith("reminder") else total
        if (n + 1 if kind.startswith("reminder") else n) == total or want < 1:
            return m.group(0)
        number = words.get(want, str(want)) if not m.group(1).isdigit() else str(want)
        noun = ("reminder" if kind.startswith("reminder") else "attempt") + ("s" if want != 1 else "")
        return m.group(0).replace(m.group(1), number, 1).replace(m.group(2), noun, 1)

    fixed = _ATTEMPTS.sub(_sub, s)
    return re.sub(r"\breminders message\b", "reminder messages", fixed)


def attempts_text_pass(text: str, total: int | None, pilot_names: list[str] | None) -> tuple[str, list[dict]]:
    """Prose about the pilot states the SOP's attempt total — line by line,
    only lines about the pilot (the word or the pilot module's name)."""
    records: list[dict] = []
    if not text or not total:
        return text, records
    names = [n for n in (pilot_names or []) if n]
    out = []
    for line in text.split("\n"):
        if _ATTEMPTS.search(line) and (re.search(r"\bpilot\b", line, re.IGNORECASE) or any(n in line for n in names)):
            fixed = _align_attempts(line, total)
            if fixed != line:
                records.append({"original": line.strip()[:140], "replaced_with": fixed.strip()[:140], "sop_attempts": total})
            out.append(fixed)
        else:
            out.append(line)
    return "\n".join(out), records


def attempts_text_findings(text: str, total: int | None, pilot_names: list[str] | None, label: str = "") -> list[dict]:
    """Rendered-text check: a pilot sentence whose attempt or reminder count
    differs from the SOP's total is a contradiction."""
    out = []
    if not text or not total:
        return out
    names = [n for n in (pilot_names or []) if n]
    flat = _pg.flatten_prose(text)
    for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\[(•\d])|•", flat):
        if not (re.search(r"\bpilot\b", s, re.IGNORECASE) or any(n in s for n in names)):
            continue
        stated = _attempt_totals(s)
        if stated and stated != {total}:
            out.append({"severity": "high", "source": "structural", "where": f"{label}: pilot attempts".strip(": "),
                        "issue": (f"The pilot's outreach attempt count reads {sorted(stated)} here but the pilot SOP makes "
                                  f"{total}: \"{s.strip()[:160]}\""),
                        "fix": f"state the SOP's total ({total} attempts)"})
    return out


def pilot_attempts_pass(modules: list, procedures: list) -> list[dict]:
    """The pilot SOP is executable and canonical: its attempt total governs
    the pilot module's strings ('sends one reminder' becomes 'sends two
    reminders' when the SOP makes three attempts). Recorded."""
    records: list[dict] = []
    sop = [p for p in (procedures or []) if isinstance(p, dict) and p.get("module") == "The pilot"
           and str(p.get("phase") or "").lower() == "pilot"]
    sop_totals = set()
    for p in sop:
        sop_totals |= _attempt_totals(_procedure_text(p))
    if len(sop_totals) != 1:
        return records
    total = next(iter(sop_totals))

    def _rewrite(s: str, path: str) -> str:
        if not isinstance(s, str) or not _ATTEMPTS.search(s):
            return s
        fixed = _align_attempts(s, total)
        if fixed != s:
            records.append({"field": path, "original": s[:140], "replaced_with": fixed[:140], "sop_attempts": total})
        return fixed

    def _walk(obj, path):
        if isinstance(obj, str):
            return _rewrite(obj, path)
        if isinstance(obj, dict):
            return {k: (_walk(v, f"{path}.{k}") if k not in ("id", "name", "entity") else v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk(v, f"{path}[{i}]") for i, v in enumerate(obj)]
        return obj

    for m in modules or []:
        if isinstance(m, dict) and m.get("pilot"):
            for key in ("purpose", "pain_point_addressed", "spec", "tech"):
                if key in m:
                    m[key] = _walk(m[key], f"{m.get('id')}.{key}")
    return records


def build_order_names(reg_modules: list, build_order: list) -> list[str]:
    """The build order the registry states: the modules of each numbered phase
    in phase order, then the parallel workstream's.

    A parallel module never acquires a phase number by its position in this
    list. Run 53 listed a parallel module fourth and the blueprint read the
    fourth entry as 'Phase 4', numbering a workstream that has no number and
    pushing the real Phase 4 to a Phase 5 that does not exist."""
    by_id = {m["id"]: m for m in reg_modules if isinstance(m, dict) and m.get("id")}
    ids = [mid for mid in build_order if isinstance(mid, str) and mid in by_id]
    ids += [mid for mid in by_id if mid not in ids]

    def key(item: tuple[int, str]) -> tuple[int, int]:
        i, mid = item
        n = by_id[mid].get("phase_number")
        return (n if isinstance(n, int) else 10 ** 6, i)

    return [by_id[mid].get("client_facing_name") or mid for _, mid in sorted(enumerate(ids), key=key)]


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
        # a parenthetical abbreviation ("... Assistant (XYZ)") invites the
        # prose to use two names for one thing — the full name is THE name,
        # the abbreviation an alias that resolves back to it
        alias = None
        am = re.search(r"\s*\(([A-Z][A-Za-z0-9 .&'-]{1,16})\)\s*$", name)
        if am and len(am.group(1).split()) <= 3 and am.group(1).upper() != am.group(1).lower():
            candidate = am.group(1).strip()
            name = name[:am.start()].strip()
            # an alias is an ABBREVIATION of the name (its initials, or words
            # of the name) — never a generic tag such as "(AI)": run 50 took
            # "AI" as an alias and rewrote every "AI" in every volume
            initials = "".join(w[0] for w in re.findall(r"[A-Za-z]+", name)).upper()
            words = {w.lower() for w in re.findall(r"[A-Za-z]+", name)}
            letters = re.sub(r"[^A-Za-z]", "", candidate).upper()
            cand_words = [w.lower() for w in re.findall(r"[A-Za-z]+", candidate)]
            generic = {"AI", "ML", "UI", "API", "COD", "OMS", "CRM", "ERP", "SMS", "KPI", "V1", "V2", "MVP", "BOT"}
            def _abbrev(w: str) -> bool:  # initials of the name's words, or a word of the name
                return w in words or w in ("bot", "agent", "tool") or (len(w) >= 2 and w.upper() in initials)

            if candidate.upper() not in generic and (
                    (len(letters) >= 2 and letters in initials) or
                    (len(cand_words) >= 2 and all(_abbrev(w) for w in cand_words))):
                alias = candidate
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
    # Module.phase / workstream from the dependency graph: the pilot is
    # phase 1; a module is phase 1 + the deepest phase it depends on; a
    # module with no dependency path to the pilot is a PARALLEL workstream
    by_id = {m["id"]: m for m in mods}
    phase_no: dict[str, int | None] = {}

    def _phase(mid: str, seen: frozenset = frozenset()) -> int | None:
        if mid in phase_no:
            return phase_no[mid]
        m = by_id.get(mid)
        if m is None or mid in seen:
            return None
        if m.get("pilot"):
            phase_no[mid] = 1
            return 1
        deps = [d for d in (m.get("depends_on") or []) if d in by_id]
        dep_phases = [p for p in (_phase(d, seen | {mid}) for d in deps) if p is not None]
        phase_no[mid] = (max(dep_phases) + 1) if dep_phases else None
        return phase_no[mid]

    for m in mods:
        _phase(m["id"])
    for m, rm in zip(mods, out):
        p = phase_no.get(m["id"])
        m["phase_number"] = rm["phase_number"] = p
        m["workstream"] = rm["workstream"] = "delivery" if p else "parallel"
        m["display_name"] = rm["display_name"] = m["client_facing_name"]
        m.setdefault("human_owner", None)
        rm["human_owner"] = m.get("human_owner")
        rm["dependencies"] = list(m.get("depends_on") or [])
    # the Phase-1 pilot may not lean on ANY other module — later-phase or
    # parallel workstream alike, none exists when the pilot runs: its strings
    # name the lightweight pilot tooling instead
    # a later module a CUSTOMER uses (its users name the customer) stands in
    # the pilot as the customer-facing pilot form; a staff module as the
    # internal pilot queue — the queue is never what a customer receives
    replacement: dict[str, str] = {}
    for m in mods:
        if m.get("pilot"):
            continue
        users = " ".join(str(u) for u in (m.get("users") or []))
        stand_in = _pg.PILOT_CUSTOMER_FORM if _CUSTOMER_USER.search(users) and not _STAFF_ONLY.search(users) else _pg.PILOT_TOOLING
        for nm in (m.get("client_facing_name"), m.get("original_name"), m.get("name")):
            if nm:
                replacement[str(nm)] = stand_in
    later = sorted({x for x in replacement if x}, key=len, reverse=True)
    pilot_mods = [m for m in mods if m.get("pilot")]
    if pilot_mods and later:
        removed: list[dict] = []

        def _detach(obj, path=""):
            if isinstance(obj, str):
                for name in later:
                    if name in obj:
                        removed.append({"field": path, "later_phase_module": name, "replaced_with": replacement[name]})
                        obj = obj.replace(name, replacement[name])
                return obj
            if isinstance(obj, dict):
                return {k: (_detach(v, f"{path}.{k}") if k not in ("id", "depends_on") else v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_detach(v, f"{path}[{i}]") for i, v in enumerate(obj)]
            return obj
        for pm in pilot_mods:
            for key in ("purpose", "pain_point_addressed", "spec", "tech"):
                if key in pm:
                    pm[key] = _detach(pm[key], key)
            pruned = [d for d in (pm.get("depends_on") or []) if d in by_id and not by_id[d].get("pilot")]
            for d in pruned:
                removed.append({"field": "depends_on", "later_phase_module": by_id[d]["client_facing_name"],
                                "replaced_with": "(dependency removed)"})
            pm["depends_on"] = [d for d in (pm.get("depends_on") or []) if d not in pruned]
            pm["pilot_tooling"] = _pg.PILOT_TOOLING
        # the log lives on the registry, never on the module object that the
        # prompts read — the later-phase name must not re-enter the pilot
        renames.append({"kind": "forward_dependencies_removed", "module": pilot_mods[0]["id"], "entries": removed})
    # the rename must reach every string that carried the old name — in the
    # business case and in every OTHER module's spec and tech anatomy
    if any("from" in r for r in renames):
        def _walk(obj):
            if isinstance(obj, str):
                for r in renames:
                    if "from" in r:
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


# only the hyphenated adjective form ("six-month staffing") — "after six
# weeks" is prose and the canonical gate reference is written that way
_WORD_DURATION = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)-(week|month|day|hour|year)(s?)\b", re.IGNORECASE)
_WORD_TO_N = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
              "ten": 10, "eleven": 11, "twelve": 12}
_CENTS = re.compile(r"\$(\d{1,3}(?:,\d{3})+)\.(\d{1,2})\b")


def plain_language(text: str) -> str:
    """Client-facing normalizations applied to data AND at render time:
    'order_IDs' -> 'order IDs', '>=90%' -> 'at least 90%', 'N attempts' ->
    'approved maximum number of attempts', '$42,573.60' -> '$42,574'
    (half-up; amounts under $1,000 keep their cents — '$1.80' is a client
    figure), word durations become digits so the label pass can see them."""
    out = text or ""
    # code spans and URL paths are identifiers BY DESIGN: they are masked so
    # no normalization below (de-snaking above all) can put a space in them
    masks: dict[str, str] = {}

    def _mask(m: re.Match) -> str:
        key = f"\x00ID{len(masks)}\x00"
        masks[key] = m.group(0)
        return key

    out = _CODE_SPAN.sub(_mask, out)
    out = _URL_PATH.sub(_mask, out)
    # template placeholders first — before de-snaking can split them apart
    out = re.sub(r">?\[(?:CLIENT_INPUT|OWNER_INPUT|ARITHMETIC)[A-Z_]*\]%?", "an approved threshold", out)
    out = re.sub(r"\[[A-Z][A-Z_]{4,}\]", "an approved value", out)
    out = re.sub(r"(?<![\w<>])>=\s*(\d)", r"at least \1", out)
    out = re.sub(r"(?<![\w<>])<=\s*(\d)", r"at most \1", out)
    out = re.sub(r"(?<![\w<>])≥\s*(\d)", r"at least \1", out)
    out = re.sub(r"(?<![\w<>])≤\s*(\d)", r"at most \1", out)
    out = re.sub(r"\b([A-Za-z0-9]+(?:_[A-Za-z0-9]+)+)\b", lambda m: m.group(1).replace("_", " "), out)
    out = re.sub(r"\bN\s+attempts\b", "approved maximum number of attempts", out)
    out = re.sub(r"\b(?:after|up to|maximum of|max\.?)\s+N\b", lambda m: m.group(0).replace("N", "the approved maximum number"), out)
    out = _CENTS.sub(lambda m: "$" + f"{int(float(m.group(1).replace(',', '') + '.' + m.group(2)) + 0.5):,}", out)
    out = _WORD_DURATION.sub(lambda m: f"{_WORD_TO_N[m.group(1).lower()]}-{m.group(2).lower()}{m.group(3)}", out)
    # never two approval labels back to back; never a label on a list ordinal
    out = re.sub(r"(\(proposed — client approval required\))(?:[\s,;]*\(proposed — client approval required\))+", r"\1", out)
    out = _LABELED_ORDINAL.sub(r"\1\2", out)
    # the label has one form; protocol/version numbers, HTTP codes and the
    # bounds of a random draw are never thresholds
    out = re.sub(r"\(proposed\s*[-–—]\s*client approval required\)", PROPOSED_LABEL, out)
    out = re.sub(r"\b((?:TLS|SSL|OAuth|HTTP/?|API\s?v|version|v)\s?\d+(?:\.\d+)?)\s*\(proposed — client approval required\)", r"\1", out,
                 flags=re.IGNORECASE)
    out = re.sub(r"\b(\d{3})\s*\(proposed — client approval required\)(\s*(?:Forbidden|Not Found|Unauthorized|OK|Bad Request|"
                 r"Internal Server Error|Conflict|Gone|Created|Accepted))", r"\1\2", out, flags=re.IGNORECASE)
    out = re.sub(r"\b((?:returns?|return code|status(?: code)?|HTTP(?: status)?|error code)\s+(?:an?\s+)?[1-5]\d\d)\s*"
                 r"\(proposed — client approval required\)", r"\1", out, flags=re.IGNORECASE)
    if re.search(r"\brandom", out, re.IGNORECASE):
        out = re.sub(r"(\bbetween\s+\d+(?:\.\d+)?)\s*\(proposed — client approval required\)(\s+and\s+\d+(?:\.\d+)?)", r"\1\2", out,
                     flags=re.IGNORECASE)
    out = re.sub(r"(?m)^(\s*\d{1,2}\.)\s*\(proposed — client approval required\)\s*", r"\1 ", out)
    for key, original in masks.items():
        out = out.replace(key, original)
    return out


_CODE_SPAN = re.compile(r"`[^`\n]+`")
_URL_PATH = re.compile(r"(?<![\w/.])/(?:api|webhooks?|v\d+|internal|public)/[A-Za-z0-9_{}\-./:]*|"
                       r"(?<![\w/.])/(?:[A-Za-z0-9_{}\-.]+/){2,}[A-Za-z0-9_{}\-.]*")
_API_PATH_OK = re.compile(r"^/[A-Za-z0-9/_\-{}.:]*$")


# numbers that are identifiers, never thresholds — the classes the number
# scanner skips and the label pass strips
NON_THRESHOLD_FRAGMENT = re.compile(
    r"\b(?:TLS|SSL|OAuth|HTTP/?|API\s?v|version|v)\s?\d+(?:\.\d+)?\b|"
    r"\b[1-5]\d\d\b[^.]{0,40}\b(?:Forbidden|Not Found|Unauthorized|OK|Bad Request|Internal Server Error|Conflict|Gone)\b|"
    r"\b(?:returns?|status(?: code)?|error code|HTTP(?: status)?)\s+(?:an?\s+)?[1-5]\d\d\b|"
    r"\brandom[^.]{0,40}\bbetween\s+\d+(?:\.\d+)?\s+and\s+\d+(?:\.\d+)?\b", re.IGNORECASE)


def api_path_repair(modules: list) -> list[dict]:
    """Every declared API path is a URL-safe slug: whitespace inside a path
    or a {parameter} becomes a hyphen (recorded), so the identifier the
    build team reads is the identifier the system serves."""
    records = []
    for m in modules or []:
        tech = m.get("tech") if isinstance(m, dict) and isinstance(m.get("tech"), dict) else None
        if not tech:
            continue
        for i, a in enumerate(tech.get("apis") or []):
            if not isinstance(a, dict):
                continue
            name = str(a.get("name") or "").strip()
            if not name.startswith("/") or _API_PATH_OK.match(name):
                continue
            fixed = re.sub(r"\s+", "-", name)
            fixed = re.sub(r"\{([^}]*)\}", lambda mm: "{" + re.sub(r"[^A-Za-z0-9_]+", "_", mm.group(1).strip()) + "}", fixed)
            fixed = re.sub(r"[^A-Za-z0-9/_\-{}.:]", "-", fixed)
            if fixed != name:
                records.append({"module": m.get("id"), "field": f"tech.apis[{i}].name", "original": name, "replaced_with": fixed})
                a["name"] = fixed
    return records


def api_path_findings(modules: list) -> list[dict]:
    out = []
    for m in modules or []:
        tech = m.get("tech") if isinstance(m, dict) and isinstance(m.get("tech"), dict) else None
        for i, a in enumerate((tech or {}).get("apis") or []):
            name = str(a.get("name") or "") if isinstance(a, dict) else ""
            if name.startswith("/") and not _API_PATH_OK.match(name):
                out.append({"severity": "high", "source": "structural", "where": f"modules.{m.get('id')}.tech.apis[{i}]",
                            "issue": f"API path '{name}' is not a URL-safe slug (spaces or illegal characters).",
                            "fix": "use lowercase words joined by hyphens or underscores, parameters in {braces}, never spaces"})
    return out


def api_paths(modules: list) -> list[str]:
    return sorted({str(a.get("name")) for m in (modules or []) if isinstance(m, dict)
                   for a in ((m.get("tech") or {}).get("apis") or []) if isinstance(a, dict)
                   and str(a.get("name") or "").startswith("/")})


def api_text_findings(text: str, paths: list[str]) -> list[dict]:
    """Rendered-text check: a registered path printed with its underscores
    turned into spaces, or any {parameter} carrying a space, is a defect."""
    out = []
    flat = re.sub(r"\s+", " ", text or "")
    seen = set()
    for p in paths or []:
        spaced = p.replace("_", " ")
        if spaced != p and spaced in flat and spaced not in seen:
            seen.add(spaced)
            out.append({"severity": "high", "source": "structural", "where": "technical identifiers",
                        "issue": f"API path '{p}' is printed as '{spaced}' — an identifier with spaces is not a valid path.",
                        "fix": "render API paths verbatim (code span), never through prose normalization"})
    for m in re.finditer(r"/[A-Za-z0-9/_\-.]*\{[a-z]+(?: [a-z]+)+\}", flat):
        if not any(m.group(0) in s for s in seen):
            seen.add(m.group(0))
            out.append({"severity": "high", "source": "structural", "where": "technical identifiers",
                        "issue": f"API path parameter with a space: '{m.group(0)}'.",
                        "fix": "parameters are single tokens in {braces}"})
    return out


# ── authentication floor for sensitive data over a messaging channel ─────────
_SENSITIVE = re.compile(r"settlement|payout|remittance|balance|invoice|amount (?:owed|due)|financial (?:data|record|detail|information|status)|"
                        r"payment (?:status|detail|schedule)|bank", re.IGNORECASE)
_WEAK_AUTH = re.compile(r"(?:verif\w+|match\w*|check\w*|confirm\w*|validat\w+|authenticat\w+)[^.;]{0,40}?(?:whatsapp|phone|sender'?s?|caller)\s*(?:phone\s*)?number|"
                        r"(?:whatsapp|phone)\s*number\s+(?:corresponds|matches|belongs|is (?:a )?known|is registered|is associated)|"
                        r"known (?:whatsapp|phone) number|registered (?:whatsapp |phone )?number (?:match|check)|"
                        r"based (?:solely |only )?on (?:the |their )?(?:whatsapp |phone )?number", re.IGNORECASE)
_STRONG_AUTH = re.compile(r"one[- ]time (?:code|password|passcode|pin)|\bOTP\b|\bPIN\b|passcode|two[- ]factor|\b2FA\b|\bMFA\b|"
                          r"signed[- ]in|sign[- ]in|log(?:ged)?[- ]in|login|authenticated (?:session|account|user)|magic link|"
                          r"verified (?:account|identity) link|identity verification step", re.IGNORECASE)
_CHANNEL = re.compile(r"whatsapp|sms|chat|messag|text message|telegram|messenger", re.IGNORECASE)
AUTH_CLAUSE = ("Before any settlement or financial detail is shared, the requester completes a verification step "
               "stronger than the sender's number — a one-time code to the registered contact or sign-in through "
               "the client's existing account (proposed — client approval required).")


def weak_auth_sentences(text: str) -> list[str]:
    flat = _pg.flatten_prose(text)
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\[(•])|•", flat)
    out = []
    for i, s in enumerate(sentences):
        # the stronger step may be stated in the sentence that follows
        context = s + " " + (sentences[i + 1] if i + 1 < len(sentences) else "")
        if _SENSITIVE.search(s) and _WEAK_AUTH.search(s) and not _STRONG_AUTH.search(context):
            out.append(s.strip())
    return out


def harden_auth_text(text: str) -> tuple[str, list[dict]]:
    """A sentence that gates financial detail on a phone-number match alone
    gets the canonical stronger step appended, in place."""
    records = []
    if not text:
        return text, records
    out = text
    for s in weak_auth_sentences(text):
        if s in out and AUTH_CLAUSE not in out[out.find(s): out.find(s) + len(s) + len(AUTH_CLAUSE) + 5]:
            out = out.replace(s, s.rstrip() + " " + AUTH_CLAUSE, 1)
            records.append({"original": s[:160], "appended": AUTH_CLAUSE})
    return out, records


def harden_auth(modules: list) -> list[dict]:
    """Module level: every weak-auth string is hardened; a module that
    exposes sensitive data over a messaging channel without any strong
    method in its security bullets gets the canonical bullet."""
    records = []
    for m in modules or []:
        if not isinstance(m, dict):
            continue

        def _walk(obj, path):
            if isinstance(obj, str):
                fixed, recs = harden_auth_text(obj)
                for r in recs:
                    records.append({"module": m.get("id"), "field": path, **r})
                return fixed
            if isinstance(obj, dict):
                return {k: _walk(v, f"{path}.{k}") for k, v in obj.items()}
            if isinstance(obj, list):
                return [_walk(v, f"{path}[{i}]") for i, v in enumerate(obj)]
            return obj

        for key in ("spec", "tech"):
            if key in m:
                m[key] = _walk(m[key], key)
        tech = m.get("tech") if isinstance(m.get("tech"), dict) else None
        blob = json.dumps({k: m.get(k) for k in ("spec", "tech", "purpose")})
        if tech is not None and _SENSITIVE.search(blob) and _CHANNEL.search(blob):
            sec = tech.get("security") if isinstance(tech.get("security"), list) else []
            if not any(isinstance(s, str) and _STRONG_AUTH.search(s) for s in sec):
                sec.append(AUTH_CLAUSE)
                tech["security"] = sec
                records.append({"module": m.get("id"), "field": "tech.security", "appended": AUTH_CLAUSE})
    return records


def auth_findings(modules: list) -> list[dict]:
    out = []
    for m in modules or []:
        if not isinstance(m, dict):
            continue
        blob = json.dumps({k: m.get(k) for k in ("spec", "tech", "purpose")})
        for s in weak_auth_sentences(" ".join(s for k in ("spec", "tech", "purpose") for s in _strings_in(m.get(k)))):
            out.append({"severity": "high", "source": "structural", "where": f"modules.{m.get('id')}: authentication",
                        "issue": f"Financial detail is gated on a phone-number match alone: \"{s[:160]}\"",
                        "fix": "require a one-time code, PIN or sign-in before any settlement information is shared"})
        tech = m.get("tech") if isinstance(m.get("tech"), dict) else None
        if tech is not None and _SENSITIVE.search(blob) and _CHANNEL.search(blob):
            sec = tech.get("security") if isinstance(tech.get("security"), list) else []
            if not any(isinstance(s, str) and _STRONG_AUTH.search(s) for s in sec):
                out.append({"severity": "high", "source": "structural", "where": f"modules.{m.get('id')}.tech.security",
                            "issue": f"'{m.get('name')}' exposes settlement or financial information over a messaging channel "
                                     "with no authentication stronger than the sender's number in its security bullets.",
                            "fix": "add a one-time code / PIN / sign-in requirement before any financial detail is shared"})
    return out


def auth_text_findings(text: str, label: str = "") -> list[dict]:
    return [{"severity": "high", "source": "structural", "where": f"{label}: authentication".strip(": "),
             "issue": f"Financial detail is gated on a phone-number match alone: \"{s[:160]}\"",
             "fix": "require a one-time code, PIN or sign-in before any settlement information is shared"}
            for s in weak_auth_sentences(text)]


def _strings_in(obj) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _strings_in(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _strings_in(v)]
    return []


# ── the Phase-1 pilot is rules-based and human-supervised ────────────────────
_AI_LOGIC = re.compile(r"\b(?:the |an |our )?AI(?:[- ]agent| model| logic| classifier| assistant| module| rationale| confidence)?\b|"
                       r"\bLLM\b|machine learning|\bNLP\b|\bML\b|classif(?:ier|ication)|intent (?:detection|extraction|classification)|"
                       r"confidence score|model (?:training|inference)|natural language (?:understanding|processing)", re.IGNORECASE)
_AI_FIELD = re.compile(r"(?:^|_)ai(?:_|$)|classification|confidence|llm|model_", re.IGNORECASE)


def scrub_ai_logic(s: str, operator: str) -> str:
    """An AI actor or AI logic in a pilot string becomes the pilot's human
    operator or its rules — the string keeps its meaning as a manual step."""
    if not isinstance(s, str) or not _AI_LOGIC.search(s):
        return s
    fixed = re.sub(r"\b(?:the |an |our )?AI[- ]agent\b", f"the {operator}", s, flags=re.IGNORECASE)
    fixed = re.sub(r"\bby the AI\b", "by the pilot rules", fixed, flags=re.IGNORECASE)
    fixed = re.sub(r"\b(?:the |an |our )?AI(?: model| logic| classifier| assistant| module| rationale| confidence)?\b",
                   "the pilot rules", fixed, flags=re.IGNORECASE)
    fixed = re.sub(r"\bLLM\b|machine learning|\bNLP\b|\bML\b|natural language (?:understanding|processing)",
                   "rules-based handling", fixed, flags=re.IGNORECASE)
    fixed = re.sub(r"intent (?:detection|extraction|classification)|confidence score|model (?:training|inference)",
                   "review by the " + operator, fixed, flags=re.IGNORECASE)
    fixed = re.sub(r"classif(?:ier|ication)", "sorting by the pilot rules", fixed, flags=re.IGNORECASE)
    fixed = re.sub(r"\bthe the\b", "the", fixed)
    return fixed


def pilot_rules_only(modules: list, operator: str, tooling: str) -> list[dict]:
    """Remove AI-agent logic from the pilot module's own specification:
    build steps that implement AI logic are dropped, AI-labeled data fields
    are dropped, and an AI actor in any remaining string becomes the pilot's
    human operator or its rules. Every change is recorded."""
    records = []
    for m in modules or []:
        if not (isinstance(m, dict) and m.get("pilot")):
            continue
        mid = m.get("id")
        tech = m.get("tech") if isinstance(m.get("tech"), dict) else None
        if tech:
            kept = []
            for i, step in enumerate(tech.get("build_sequence") or []):
                if isinstance(step, str) and _AI_LOGIC.search(step):
                    records.append({"module": mid, "field": f"tech.build_sequence[{i}]", "removed": step[:160]})
                else:
                    kept.append(step)
            if "build_sequence" in tech:
                tech["build_sequence"] = kept
            for j, ent in enumerate(tech.get("data_model") or []):
                if isinstance(ent, dict) and isinstance(ent.get("fields"), list):
                    keep_f = [f for f in ent["fields"] if not (isinstance(f, str) and _AI_FIELD.search(f))]
                    for f in ent["fields"]:
                        if f not in keep_f:
                            records.append({"module": mid, "field": f"tech.data_model[{j}].fields", "removed": str(f)})
                    ent["fields"] = keep_f

        def _rewrite(s: str, path: str) -> str:
            fixed = scrub_ai_logic(s, operator)
            if fixed != s:
                records.append({"module": mid, "field": path, "original": s[:160], "replaced_with": fixed[:160]})
            return fixed

        def _walk(obj, path):
            if isinstance(obj, str):
                return _rewrite(obj, path)
            if isinstance(obj, dict):
                return {k: (_walk(v, f"{path}.{k}") if k not in ("id", "name", "entity") else v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_walk(v, f"{path}[{i}]") for i, v in enumerate(obj)]
            return obj

        for key in ("purpose", "pain_point_addressed", "spec", "tech"):
            if key in m:
                m[key] = _walk(m[key], key)
    return records


def pilot_isolation_findings(modules: list, procedures: list | None = None) -> list[dict]:
    """The pilot module and every pilot-phase procedure name no AI logic and
    no other module — proven on the structures, not the prompt."""
    out = []
    mods = [m for m in (modules or []) if isinstance(m, dict)]
    pilot = [m for m in mods if m.get("pilot")]
    others = [str(m.get("client_facing_name") or m.get("name") or "") for m in mods if not m.get("pilot")]
    others += [str(m.get("name") or "") for m in mods if not m.get("pilot")]
    others = sorted({o for o in others if o}, key=len, reverse=True)
    for pm in pilot:
        for key in ("purpose", "pain_point_addressed", "spec", "tech"):
            for s in _strings_in(pm.get(key)):
                hit = _AI_LOGIC.search(s)
                named = next((o for o in others if o in s), None)
                if hit or named:
                    out.append({"severity": "high", "source": "structural", "where": f"modules.{pm.get('id')}.{key}",
                                "issue": (f"The pilot specification {'names AI logic (' + hit.group(0) + ')' if hit else ''}"
                                          f"{' and ' if hit and named else ''}{'depends on ' + repr(named) if named else ''}: "
                                          f"\"{s[:140]}\" — a Phase 1 pilot is rules-based, human-supervised and depends on no module."),
                                "fix": "describe the rules and the human operator; move AI logic to the later module"})
                    break
    pilot_names = {str(m.get("client_facing_name") or m.get("name") or "") for m in pilot} | {"The pilot"}
    for p in procedures or []:
        if not isinstance(p, dict) or str(p.get("phase") or "").lower() != "pilot":
            continue
        if p.get("module") not in pilot_names:
            continue
        texts = [str(p.get("trigger") or "")] + [str(s.get("step") or "") + " " + str(s.get("actor") or "")
                                                  for s in (p.get("steps") or []) if isinstance(s, dict)]
        texts += [str(e.get("when") or "") + " " + str(e.get("then") or "") for e in (p.get("exceptions") or []) if isinstance(e, dict)]
        for s in texts:
            hit = _AI_LOGIC.search(s)
            named = next((o for o in others if o in s), None)
            if hit or named:
                out.append({"severity": "high", "source": "structural", "where": f"procedures: {p.get('name')}",
                            "issue": (f"A pilot procedure {'relies on AI logic (' + hit.group(0) + ')' if hit else ''}"
                                      f"{' and ' if hit and named else ''}{'depends on ' + repr(named) if named else ''}: \"{s[:140]}\""),
                            "fix": "run the step with today's tools and the pilot's human operator"})
                break
    return out


def document_control(req) -> dict:
    """The operations manual's owner and approver — client-provided intake
    facts, never invented. Both are required for a FINAL manual."""
    owner = str(getattr(req, "document_owner", None) or "").strip()
    approver = str(getattr(req, "document_approver", None) or "").strip()
    return {"owner": owner or None, "approver": approver or None, "complete": bool(owner and approver),
            "source": "client intake (document_owner, document_approver)"}


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
            # "the XYZ" / "(XYZ)" -> the one name; the parenthetical form disappears
            out = re.sub(r"\s*\(" + re.escape(alias) + r"\)", "", out)
            out = re.sub(r"(?<![\w'])" + re.escape(alias) + r"(?![\w'])", name, out)
            out = out.replace(name + " " + name, name)
    return out


def identifier_artifacts(text: str, module_ids: list[str] | None = None,
                         known_ids: list[str] | None = None) -> list[str]:
    """Internal identifiers found in client-facing text: known module ids,
    slug-shaped list labels ('1. some-module-engine:'), registered technical
    identifiers, and compound technical slugs ('pin-capture-handler'). A
    single-hyphen word ending in a technical noun ('re-queue', 'sub-store')
    is ordinary English unless the registry declares it as an identifier."""
    hits = []
    known = {k for k in (known_ids or []) if k}
    # "For your build team" lines and the module appendix ("the engineering
    # detail") are the sanctioned homes of technical identifiers; ordinary
    # hyphenated English is not a slug
    raw = client_facing_region(text or "")
    hits += [m.group(1) for m in _SLUG_ITEM.finditer(_BUILD_TEAM_LINE.sub(" ", raw))]
    # rendered pages wrap a build-team line across lines: judge on collapsed whitespace
    t = re.sub(r"\s+", " ", raw)
    t = re.sub(r"For your build team:.*?(?=\s(?:•|-|\*\*|##|Applying it)|$)", " ", t, flags=re.IGNORECASE)
    t = _BUILD_TEAM_LINE.sub(" ", t)
    t = _SLUG_ALLOW.sub(" ", t)
    for mid in list(module_ids or []) + sorted(known):
        if mid and ("-" in mid or "_" in mid) and re.search(r"(?<![\w-])" + re.escape(mid) + r"(?![\w-])", t):
            hits.append(mid)
    hits += [m.group(0) for m in _TECH_SLUG.finditer(t)
             if m.group(0).count("-") >= 2 or m.group(0) in known]
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
    # the canonical gate sentence (and its full definition) is opaque to
    # every other pass: its numbers are the gate's, already typed and labeled
    protected = [s for c in claims if c.get("type") == "pilot_gate"
                 for s in (str(c.get("text") or ""), str(c.get("full_definition") or ""), str(c.get("assignment") or ""))
                 if len(s) > 40]
    masks: dict[str, str] = {}
    out = plain_language(text)
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
    # '6-month staffing', '2-week monitoring': hyphenated durations are
    # thresholds too — the number scanner skips hyphen-joined tokens, so
    # they are handled here first
    spans = list(_numbers(out))
    for dm in re.finditer(r"(?<![\w.])(\d+)-(weeks?|months?|days?|hours?)\b", out):
        spans.append((dm.group(1), float(dm.group(1)), dm.group(2).lower(), dm.start(), dm.end()))
    spans.sort(key=lambda x: x[3])
    random_draw = bool(re.search(r"\brandom", out, re.IGNORECASE))
    for tok, v, unit, s, e in spans:
        if s < last:
            continue
        before, after = out[max(0, s - 80):s], out[e:e + 80]
        # the bounds of a random draw ("a random number between 0 and 1") are
        # an assignment mechanic, never thresholds
        if random_draw and (re.search(r"\bbetween\s*$", before) or re.match(r"\s*and\s+\d", after) or re.search(r"\band\s*$", before)):
            continue
        # an HTTP status code ("returns a 403") is an identifier
        if re.fullmatch(r"[1-5]\d\d", tok) and re.search(r"\b(?:returns?|return code|status(?: code)?|http(?: status)?|error code)\s+(?:an?\s+)?$",
                                                          before, re.IGNORECASE):
            continue
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


# "<n> days (your stated cycle) of order delivery" — the period with the event
# it is counted from
_PERIOD_ORIGIN = re.compile(
    r"(\d+)\s*(?:-|\s)?days?\s*(?:\((?:your stated cycle|proposed[^)]*)\)\s*)*(?:of|after|from|following|post|since)\s+(?:the\s+)?"
    r"([a-z][a-z\-]*(?:\s+[a-z][a-z\-]*){0,3}?)(?=[,.;:'\")]|\s+(?:policy|for|to|and|or|is|must|will|has|have)\b|\s*$)",
    re.IGNORECASE)
_LABEL_TXT = "(proposed — client approval required)"


def _policy_day_claims(claims: list[dict]) -> list[dict]:
    return [c for c in claims
            if c.get("type") == "client_fact" and str(c.get("unit") or "").startswith("day")
            and isinstance(c.get("value"), (int, float))
            and re.search(r"settle|remit|payout|month-end", str(c.get("question") or c.get("source") or ""), re.IGNORECASE)]


def _origin_words(origin: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (origin or "").lower()) if len(w) > 2 and w not in ("the", "after", "from", "following", "since", "post")}


def _origin_mismatch(stated: str, claim_origin: str) -> bool:
    """'order delivery' against 'after month-end': no content word shared."""
    want = _origin_words(claim_origin)
    have = _origin_words(stated)
    return bool(want) and not (want & have)


def policy_findings(texts: dict[str, str], claims: list[dict]) -> list[dict]:
    """NO INVENTED POLICIES, deterministically: a sentence that states a
    settlement / remittance / payout period must state the client's own
    period (a client fact in days) — any other period is a fabrication —
    AND the client's own event origin ('after month-end'): the same number
    counted from another event is a different policy."""
    out = []
    day_claims = _policy_day_claims(claims)
    client_days = {int(c["value"]) for c in day_claims}
    origins = {int(c["value"]): c["event"] for c in day_claims if c.get("event")}
    if not client_days:
        return out
    out += cadence_findings(texts, claims)
    for label, text in (texts or {}).items():
        flat = _pg.flatten_prose(re.sub(r"\s-\s+(?=[A-Z*])", ". ", text or ""))
        for sentence in re.split(r"(?<=[.!?])\s+|•", flat):
            if not _POLICY_WORDS.search(sentence):
                continue
            for om in _PERIOD_ORIGIN.finditer(sentence):
                n = int(om.group(1))
                if n in origins and _origin_mismatch(om.group(2), origins[n]):
                    out.append({"severity": "high", "source": "structural", "where": f"{label}: operational policy",
                                "issue": (f"The client's {n}-day settlement period is counted from '{om.group(2).strip()}', "
                                          f"but the client stated it as '{n} days {origins[n]}' — the event origin is part of "
                                          f"the policy: \"{sentence.strip()[:160]}\""),
                                "fix": f"state '{n} days {origins[n]} (your stated cycle)'"})
            # the client's own cycle is a stated fact: an approval label on it
            # misattributes the provenance
            for n, origin in origins.items():
                if re.search(rf"\b{n} days {re.escape(origin)}[^().;]{{0,60}}?\s*\(proposed — client approval required\)",
                             sentence, re.IGNORECASE):
                    out.append({"severity": "high", "source": "structural", "where": f"{label}: operational policy",
                                "issue": (f"The client's own settlement cycle ('{n} days {origin}') carries an approval label — "
                                          f"a client-stated fact is never a proposal: \"{sentence.strip()[:160]}\""),
                                "fix": f"state '{n} days {origin} (your stated cycle)' without the approval label"})
            for m in _POLICY_PERIOD.finditer(sentence):
                if m.group(1) and int(m.group(1)) in client_days:
                    continue
                if m.group(1) is None and not (m.group(4) or m.group(5)):
                    continue
                # the period must be ABOUT settling — adjacent to the policy
                # verb/noun ("remitted weekly", "settled within 5 days",
                # "2-day remittance policy", "remittance dates (within 2 days …
                # of order delivery)", "the 'within 2 days … of delivery' policy")
                # — a review cadence in the same sentence is not
                before = sentence[max(0, m.start() - 60): m.start()]
                after = sentence[m.end(): m.end() + 60]
                near = before + " " + after
                tied = (re.search(r"(?:" + _POLICY_WORDS.pattern + r")\w*\s+(?:\w+\s+){0,2}[('\"]?\s*(?:within|in|after|every|of|on|per|at)?\s*$",
                                  before, re.IGNORECASE)
                        or re.match(r"\s*(?:\w+\s+){0,1}(?:settlement|remittance|payout|disbursement)\s+(?:cycle|policy|period|terms|window)",
                                    after, re.IGNORECASE)
                        or re.match(r"\s*(?:\((?:proposed[^)]*|your stated cycle)\)\s*)*(?:of|after|from|following)\s+(?:the\s+)?"
                                    r"(?:order|delivery|collection|invoice|pickup|month|the sale)", after, re.IGNORECASE)
                        or re.match(r"\s*(?:\((?:proposed[^)]*|your stated cycle)\)\s*)*(?:of|after)[^.']{0,40}?['\"]?\s*policy\b", after, re.IGNORECASE))
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


# ── a deadline is not a cadence ──────────────────────────────────────────────
# "settle within 10 days after month-end" is a deadline counted from an
# event; "monitor every 10 days" is a frequency. The client's deadline number
# may not be reused as a monitoring frequency unless the client separately
# supplied that cadence.
_CADENCE = re.compile(r"\b(?:every|each)\s+(\d+)\s*(?:-|\s)?days?\b|\b(\d+)[- ]day\s+(?:cadence|frequency|interval|rhythm|"
                      r"monitoring|review|check)\b", re.IGNORECASE)
_CADENCE_Q = re.compile(r"how often|frequency|cadence|every|routine|rhythm|interval", re.IGNORECASE)


def deadline_days(claims: list[dict]) -> dict[int, str]:
    """Client-stated deadlines: a day count that counts from an event."""
    return {int(c["value"]): c["event"] for c in _policy_day_claims(claims) if c.get("event")}


def cadence_days(claims: list[dict]) -> set[int]:
    """Day counts the client supplied AS a cadence ('how often…: every 10 days')."""
    return {int(c["value"]) for c in claims
            if c.get("type") == "client_fact" and str(c.get("unit") or "").startswith("day")
            and isinstance(c.get("value"), (int, float)) and _CADENCE_Q.search(str(c.get("question") or ""))}


def _policy_subject(claims: list[dict], n: int) -> str:
    q = " ".join(str(c.get("question") or "") for c in _policy_day_claims(claims) if int(c["value"]) == n)
    for verb, noun in (("settle", "settlement"), ("remit", "remittance"), ("payout", "payout"),
                       ("pay out", "payout"), ("disburse", "disbursement"), ("invoice", "invoicing")):
        if verb in q.lower():
            return noun
    return "the policy"


def _routine_owner(claims: list[dict]) -> str:
    """The team the client named around its routines ('across our finance team')."""
    blob = " ".join(str(c.get("text") or "") + " " + str(c.get("question") or "") for c in claims if c.get("type") == "client_fact")
    m = re.search(r"\b([a-z]+) team\b", blob, re.IGNORECASE)
    return (m.group(1).lower() + " ") if m else ""


def cadence_sentence(claims: list[dict], n: int) -> str:
    subject = _policy_subject(claims, n)
    origin = deadline_days(claims).get(n, "")
    return (f"Monitor {subject} status according to the client-approved {_routine_owner(claims)}routine. "
            f"{subject[0].upper() + subject[1:]} must be completed within {n} days {origin}.").replace("  ", " ")


def _cadence_hits(sentence: str, claims: list[dict]) -> list[int]:
    deadlines, cadences = deadline_days(claims), cadence_days(claims)
    out = []
    for m in _CADENCE.finditer(sentence):
        n = int(m.group(1) or m.group(2))
        if n in deadlines and n not in cadences:
            out.append(n)
    return out


def cadence_findings(texts: dict[str, str], claims: list[dict]) -> list[dict]:
    out = []
    if not deadline_days(claims):
        return out
    for label, text in (texts or {}).items():
        flat = _pg.flatten_prose(text)
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z\[(•\d])|•", flat):
            for n in _cadence_hits(sentence, claims):
                out.append({"severity": "high", "source": "structural", "where": f"{label}: operational policy",
                            "issue": (f"The client's {n}-day deadline ({n} days {deadline_days(claims)[n]}) is reused as a "
                                      f"monitoring frequency the client never supplied: \"{sentence.strip()[:160]}\""),
                            "fix": f"replace with: {cadence_sentence(claims, n)}"})
                break
    return out


def cadence_pass(text: str, claims: list[dict]) -> tuple[str, list[str]]:
    """Deterministic repair: a sentence that turns the client's deadline into
    a frequency is replaced by the canonical routine sentence."""
    notes: list[str] = []
    if not text or not deadline_days(claims):
        return text, notes
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\[(•\d])", text)
    out = []
    for s in parts:
        hits = _cadence_hits(s, claims)
        if hits:
            canon = cadence_sentence(claims, hits[0])
            notes.append(f"'{s.strip()[:100]}' -> '{canon}' (deadline reused as a cadence)")
            out.append(canon)
        else:
            out.append(s)
    return " ".join(out) if len(parts) > 1 else out[0], notes


def policy_pass(text: str, claims: list[dict]) -> tuple[str, list[str]]:
    """Rewrite an invented settlement period in a structured string to the
    client's stated one, marked as theirs — the least-invention deterministic
    correction ('2-day remittance policy' -> '10-day (your stated cycle)
    remittance policy'). Returns (text, notes)."""
    notes = []
    if not text:
        return text, notes
    day_claims = _policy_day_claims(claims)
    client_days = sorted({int(c["value"]) for c in day_claims})
    origins = {int(c["value"]): c["event"] for c in day_claims if c.get("event")}
    if not client_days:
        return text, notes
    out = text
    # labels are normalized BEFORE the origin pass so a "(proposed …)" sitting
    # between the period and its origin cannot hide the moved origin
    out = re.sub(r"\(your stated cycle\)\s*\(proposed — client approval required\)", "(your stated cycle)", out)

    # the client's number counted from the wrong event: the origin is restored
    def _origin(m: re.Match) -> str:
        n = int(m.group(1))
        if n not in origins or not _origin_mismatch(m.group(2), origins[n]):
            return m.group(0)
        fixed = f"{n} days {origins[n]} (your stated cycle)"
        notes.append(f"'{m.group(0)}' -> '{fixed}' (event origin restored)")
        return fixed

    def _restore_origin(s: str) -> str:
        s = _PERIOD_ORIGIN.sub(_origin, s)
        # the client's own cycle never carries an approval label
        for n, origin in origins.items():
            def _unlabel(m: re.Match, n=n, origin=origin) -> str:
                notes.append(f"'{m.group(0)[:80]}' -> approval label removed from the client's own {n}-day cycle ({origin})")
                return m.group(1) + " (your stated cycle)"
            s = re.sub(rf"(\b{n} days {re.escape(origin)}[^().;]{{0,60}}?)\s*\(proposed — client approval required\)",
                       _unlabel, s, flags=re.IGNORECASE)
            s = re.sub(r"\(your stated cycle\)(?:\s*\(your stated cycle\))+", "(your stated cycle)", s)
        return s

    out = _restore_origin(out)
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
    # an invented period corrected to the client's number still has to count
    # from the client's event ("2 days of collection" -> "10 days after month-end")
    out = _restore_origin(out)
    # and a deadline never becomes a monitoring frequency
    out, cadence_notes = cadence_pass(out, claims)
    notes += cadence_notes
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


CORRECTION_KEYS = ("renames", "policy_corrections", "pilot_ai_removed", "placeholder_replacements",
                   "forward_dependencies_removed", "derivations_shown", "null_values_replaced",
                   "identifier_corrections", "auth_hardening", "pilot_design_corrections", "unit_corrections",
                   "pilot_procedures_consolidated", "population_corrections", "operating_time_labels",
                   "customer_channel_corrections", "pilot_attempt_corrections", "content_recovery")


def corrections(reg: dict | None) -> dict:
    """Every deterministic correction the registry applied — recorded in the
    QA report and the release record so nothing is silently rewritten."""
    reg = reg or {}
    return {k: reg.get(k) or [] for k in CORRECTION_KEYS}


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
                # a null decision right is a statement, not a literal: the AI
                # decides nothing alone (recorded as a correction)
                for key in ("decides_alone", "hands_off"):
                    if ai.get(key) is None or str(ai.get(key)).strip().lower() in _NULLISH:
                        ai[key] = (NO_AUTONOMY if key == "decides_alone" else
                                   "Everything it cannot resolve with confidence — a human picks it up")
                        counter.setdefault("null_values_replaced", []).append(
                            {"module": mid, "field": f"spec.ai.{key}", "replaced_with": ai[key]})
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
        # clock times and review cadences are proposals unless the client stated them
        if isinstance(p.get("trigger"), str):
            p["trigger"], recs = operating_time_pass(p["trigger"])
            for r in recs:
                counter.setdefault("operating_time_labels", []).append({"procedure": p.get("name"), "field": "trigger", **r})
        for i, st in enumerate(p.get("steps") or []):
            if isinstance(st, dict) and isinstance(st.get("step"), str):
                st["step"], recs = operating_time_pass(st["step"])
                for r in recs:
                    counter.setdefault("operating_time_labels", []).append({"procedure": p.get("name"), "field": f"steps[{i}]", **r})
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
        kpi_ids: list[str] = []
        if m.get("pilot") and sentence:
            rendered.append(sentence)
            out.append(_claim(f"MK-{mid}-gate", "module_kpi", gate.get("target_value"), gate.get("target_unit") or "",
                              phase="PILOT", scope=mid, provenance="canonical_gate",
                              approval=gate.get("approval_status") or "consultant_proposed — client approval required",
                              source="pilot_gate", sections=["module_kpi", "decision", "scoreboard"],
                              text=sentence, maps_to="PG"))
            kpi_ids.append(f"MK-{mid}-gate")
            # the pilot module's success IS the gate — nothing sits beside it
            candidates = []
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
                kpi_ids.append(f"MK-{mid}-{n:02d}")
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
        m["kpi_claim_ids"] = kpi_ids
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
    forward_removed = [{"module": r["module"], **e} for r in renames
                       if r.get("kind") == "forward_dependencies_removed" for e in r["entries"]]
    renames = [r for r in renames if "from" in r]
    gate = None
    if isinstance(bc.get("pilot_gate"), dict) and bc["pilot_gate"]:
        gate = _pg.normalize_gate(bc["pilot_gate"], claims)
        bc["pilot_gate"] = gate
        claims += _pg.gate_claims(gate)
    enforce_gate_in_specs(modules, gate)
    # placeholders the model left in the structures are recorded BEFORE the
    # typing pass renders them as approved-threshold slots
    placeholder_log: list[dict] = []
    _PH = re.compile(r"\[[A-Z][A-Z_]{4,}\]|>?\[?CLIENT_INPUT[A-Z_]*\]?%?")

    def _ph_walk(obj, mid, path):
        if isinstance(obj, str):
            for hit in _PH.findall(obj):
                placeholder_log.append({"module": mid, "field": path, "placeholder": hit,
                                        "replaced_with": "an approved threshold / an approved value"})
        elif isinstance(obj, dict):
            for k, v in obj.items():
                _ph_walk(v, mid, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _ph_walk(v, mid, f"{path}[{i}]")

    for m in modules or []:
        if isinstance(m, dict):
            for key in ("spec", "tech", "purpose", "pain_point_addressed"):
                _ph_walk(m.get(key), m.get("id"), key)
    # the Phase 1 pilot is manual or rules-based BY LAW: an AI component the
    # model specced into the pilot module is removed from it (the AI belongs
    # to the later modules the pilot's data will train)
    pilot_ai_removed = []
    for m in modules or []:
        if isinstance(m, dict) and m.get("pilot"):
            spec = m.get("spec") if isinstance(m.get("spec"), dict) else None
            tech = m.get("tech") if isinstance(m.get("tech"), dict) else None
            if (spec and spec.get("ai")) or (tech and tech.get("ai_agent")):
                pilot_ai_removed.append({"module": m["id"], "field": "spec.ai / tech.ai_agent", "removed": "AI component"})
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
    # AI logic written INTO the pilot's build steps, fields and strings is
    # removed too — the pilot is rules-based and human-supervised
    pilot_ai_removed += pilot_rules_only(modules, _pg.PILOT_OPERATOR, _pg.PILOT_TOOLING)
    # list items never start with their own number (a threshold pass would
    # label "3." as a proposal); a customer never receives the internal
    # queue; the pilot population is the gate's population
    customer_channel, population_corrections = [], []
    kinds = service_types(free_texts or [])
    for m in modules or []:
        if not isinstance(m, dict):
            continue
        tech = m.get("tech") if isinstance(m.get("tech"), dict) else None
        if tech:
            for key in ("build_sequence", "done_when", "evaluation"):
                if isinstance(tech.get(key), list):
                    tech[key] = [strip_ordinal(x) for x in tech[key]]
            ai = tech.get("ai_agent") if isinstance(tech.get("ai_agent"), dict) else None
            if ai and isinstance(ai.get("evaluation"), list):
                ai["evaluation"] = [strip_ordinal(x) for x in ai["evaluation"]]
        if m.get("pilot"):
            def _pilot_walk(obj, path):
                if isinstance(obj, str):
                    fixed, recs = customer_facing_pass(obj)
                    customer_channel.extend({"module": m.get("id"), "field": path, **r} for r in recs)
                    return fixed
                if isinstance(obj, dict):
                    return {k: (_pilot_walk(v, f"{path}.{k}") if k not in ("id", "name", "entity") else v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [_pilot_walk(v, f"{path}[{i}]") for i, v in enumerate(obj)]
                return obj
            for key in ("purpose", "pain_point_addressed", "spec", "tech"):
                if key in m:
                    m[key] = _pilot_walk(m[key], key)
    # identifiers are URL-safe; financial detail needs more than a number match
    identifier_corrections = api_path_repair(modules)
    auth_hardening = harden_auth(modules)
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
    for rm in reg_modules:
        src = next((m for m in modules if isinstance(m, dict) and m.get("id") == rm["id"]), {})
        rm["kpi_claim_ids"] = list(src.get("kpi_claim_ids") or [])
    reg = {
        "version": 2,
        "monthly_identity": MONTHLY_IDENTITY,
        "claims": claims,
        "modules": reg_modules,
        "renames": renames,
        "policy_corrections": policy_notes,
        "pilot_ai_removed": pilot_ai_removed,
        "placeholder_replacements": placeholder_log,
        "forward_dependencies_removed": forward_removed,
        "null_values_replaced": counter.get("null_values_replaced") or [],
        "technical_identifiers": technical_identifiers(modules),
        "api_paths": api_paths(modules),
        "identifier_corrections": identifier_corrections,
        "auth_hardening": auth_hardening,
        "customer_channel_corrections": customer_channel,
        "population_corrections": population_corrections,
        "service_types": kinds,
        "pilot_design": _pg.assignment_sentence(gate) if gate and not gate.get("design_errors") else None,
        "pilot_gate": gate,
        "pilot_gate_sentence": _pg.canonical_sentence(gate) if gate else "",
        "pilot_gate_definition": _pg.full_definition(gate) if gate else "",
        "build_order_names": build_order_names(reg_modules, bc.get("build_order") or []),
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
