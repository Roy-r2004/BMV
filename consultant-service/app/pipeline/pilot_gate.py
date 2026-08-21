"""The one canonical pilot gate — one typed object, one rendered sentence.

Run 46 restated its gate three different ways: the decision prose ("from a
baseline of 88% success, measured in week 1"), the gate box ("5 pp increase
(proposed…)") and a module KPI ("within 6 weeks of pilot launch in the
specified geographic zone"). None was the others. Here the gate is a typed
object with every component named, and exactly ONE deterministic sentence
renders it. Prompts write the token [[PILOT_GATE]] where they restate the
gate; the renderer substitutes the sentence. A sentence that mentions the
primary metric with a number and is not the canonical sentence is a
paraphrase — it is replaced, and if any survive they block release.
"""

import re

TOKEN = "[[PILOT_GATE]]"
LABEL = "(proposed — client approval required)"
APPROVAL_REQUIRED = "consultant_proposed — client approval required"

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(weeks?|days?|months?)", re.IGNORECASE)
_PP = re.compile(r"(\d+(?:\.\d+)?)\s*(?:percentage[- ]points?|pp\b|p\.p\.)", re.IGNORECASE)
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_ONE_IN = re.compile(r"\b1 in (\d+)\b", re.IGNORECASE)
_EG = re.compile(r"\(\s*(?:e\.?g\.?,?|such as|for example,?)\s*([^)]+)\)", re.IGNORECASE)
_UP = re.compile(r"increas|rise|improv|higher|lift|grow|up\b", re.IGNORECASE)
_DOWN = re.compile(r"decreas|reduc|lower|fall|drop|fewer|down\b|cut", re.IGNORECASE)
_WEEK1 = re.compile(r"measure[d]? in week[- ]?(1|one)", re.IGNORECASE)
_STOP = {"rate", "the", "and", "for", "per", "of", "with", "from", "that", "this"}


def _strip_label(s: str) -> str:
    out = re.sub(r"\s*\(proposed[^)]*\)", "", s or "")
    out = re.sub(r"\s*\((?:by )?your own figures?\)|,?\s*by your own figures", "", out, flags=re.IGNORECASE)
    # the canonical sentence must read on the page exactly as it is stored:
    # comparison notation becomes the words the renderer would print anyway
    out = re.sub(r"(?<![\w<>])>=\s*(\d)", r"at least \1", out)
    out = re.sub(r"(?<![\w<>])<=\s*(\d)", r"at most \1", out)
    out = re.sub(r"(?<![\w<>])≥\s*(\d)", r"at least \1", out)
    out = re.sub(r"(?<![\w<>])≤\s*(\d)", r"at most \1", out)
    out = re.sub(r"(?<![\w<>])>\s*(\d)", r"more than \1", out)
    out = re.sub(r"(?<![\w<>])<\s*(\d)", r"fewer than \1", out)
    out = re.sub(r"\b([a-z0-9]+(?:_[a-z0-9]+)+)\b", lambda m: m.group(1).replace("_", " "), out)
    return out.strip().rstrip(".;,").strip()


def _num_in(s: str) -> float | None:
    m = _NUM.search(s or "")
    return float(m.group(0).replace(",", "")) if m else None


def normalize_gate(raw: dict, claims: list[dict] | None = None) -> dict:
    """Typed gate from the decomposition's object. Strings the model wrote
    are parsed into numbers and kinds; nothing is invented — a component the
    model did not provide stays None and gate_errors() names it."""
    raw = raw if isinstance(raw, dict) else {}
    g: dict = {k: raw.get(k) for k in (
        "duration", "population", "control", "primary_metric", "baseline", "target",
        "secondary_metrics", "guardrail", "approvals_required", "numerator", "denominator",
        "geography", "control_method", "guardrails", "change_kind")}
    # duration
    dur = _strip_label(str(raw.get("duration") or ""))
    m = _DURATION.search(dur)
    g["duration_value"] = float(m.group(1)) if m else (float(raw["duration_weeks"]) if isinstance(raw.get("duration_weeks"), (int, float)) else None)
    g["duration_unit"] = (m.group(2).lower().rstrip("s") if m else ("week" if g["duration_value"] else None))
    # population / geography
    pop = str(raw.get("population") or "").strip()
    geo = str(raw.get("geography") or "").strip()
    eg = _EG.search(pop)
    if not geo and eg:
        geo = eg.group(1).strip()
    if eg:
        pop = _EG.sub("", pop).strip()
        pop = re.sub(r"\s{2,}", " ", pop).rstrip(" ,")
    g["population"] = _strip_label(pop) or None
    g["geography"] = _strip_label(geo) or None
    g["control_method"] = _strip_label(str(raw.get("control_method") or raw.get("control") or "")) or None
    # target — the labeled TEXT governs; a numeric field that contradicts it
    # (run 47: text "5 percentage-point rise", target_value 0.93 = the
    # resulting rate) is recorded as a conflict, never silently preferred
    tgt = str(raw.get("target") or "")
    kind = str(raw.get("change_kind") or raw.get("target_kind") or "").lower() or None
    field = raw.get("target_value") if isinstance(raw.get("target_value"), (int, float)) else None
    tv = None
    if _PP.search(tgt):
        tv = float(_PP.search(tgt).group(1))
        kind = kind or "percentage_point"
    elif _PCT.search(tgt):
        tv = float(_PCT.search(tgt).group(1))
        if kind is None:
            kind = "relative" if re.search(r"relative", tgt, re.IGNORECASE) else None
    elif _ONE_IN.search(tgt):
        n = float(_ONE_IN.search(tgt).group(1))
        tv = round(100.0 / n, 1)
        kind = kind or "relative"
    if tv is None:
        tv = field
    g["target_value"] = tv
    g["target_value_conflict"] = (field is not None and tv is not None and abs(field - tv) > 0.01 * max(tv, 1))
    g["change_kind"] = kind
    g["target_unit"] = "percentage points" if kind == "percentage_point" else ("% relative" if kind == "relative" else (kind or ""))
    g["direction"] = "fall" if _DOWN.search(tgt) and not _UP.search(tgt) else ("rise" if _UP.search(tgt) else None)
    # baseline
    base = str(raw.get("baseline") or "")
    bv = _num_in(_strip_label(base))
    g["baseline_value"] = bv
    if bv is not None and any(
            isinstance(c.get("value"), (int, float)) and c.get("type") == "client_fact"
            and (abs(c["value"] - bv) < 1e-9 or abs(c["value"] * 100 - bv) < 1e-9 or abs(c["value"] - bv / 100) < 1e-9)
            for c in (claims or [])):
        g["baseline_source"] = "client"
    elif _WEEK1.search(base):
        g["baseline_source"] = "measure in week 1"
    elif bv is not None:
        g["baseline_source"] = "consultant"
    else:
        g["baseline_source"] = None
    g["baseline"] = _strip_label(base) or None
    # guardrails
    guards = raw.get("guardrails") if isinstance(raw.get("guardrails"), list) else (
        [raw.get("guardrail")] if raw.get("guardrail") else [])
    g["guardrails"] = [_strip_label(str(x)) for x in guards if x]
    g["guardrail_value"] = _num_in(g["guardrails"][0]) if g["guardrails"] else None
    g["numerator"] = _strip_label(str(raw.get("numerator") or "")) or None
    g["denominator"] = _strip_label(str(raw.get("denominator") or "")) or None
    g["primary_metric"] = _strip_label(str(raw.get("primary_metric") or "")) or None
    # legacy keys stay populated — an auditor reading the structured object
    # must never see a null beside a filled sibling
    g["control"] = g["control_method"]
    g["guardrail"] = "; ".join(g["guardrails"]) if g["guardrails"] else None
    g["approval_status"] = APPROVAL_REQUIRED
    g["secondary_metrics"] = [str(x) for x in (raw.get("secondary_metrics") or []) if x]
    g["approvals_required"] = [str(x) for x in (raw.get("approvals_required") or []) if x]
    g["canonical_sentence"] = canonical_sentence(g)
    return g


def gate_errors(g: dict) -> list[str]:
    errors = []
    for key, label in (("primary_metric", "primary metric"), ("numerator", "numerator"),
                       ("denominator", "denominator"), ("population", "population"),
                       ("geography", "geography"), ("control_method", "control-group method")):
        if not g.get(key):
            errors.append(f"missing {label}")
    if g.get("duration_value") is None:
        errors.append("missing pilot duration")
    if g.get("target_value") is None:
        errors.append("missing numeric target")
    if g.get("target_value_conflict"):
        errors.append("target_value contradicts the target text")
    if g.get("change_kind") not in ("percentage_point", "relative"):
        errors.append("target must be explicitly percentage-point or relative")
    if g.get("direction") is None:
        errors.append("target direction (rise/fall) not stated")
    # a success/completion rate rises; a failure/error/complaint rate falls —
    # a target pointing the other way measures something else than the metric
    metric = (g.get("primary_metric") or "").lower()
    if g.get("direction") == "fall" and re.search(r"success|completion|confirmed|resolved|accuracy|adoption", metric) \
            and not re.search(r"fail|error|complaint|miss|re-attempt|unreach", metric):
        errors.append("target direction 'fall' contradicts a success-type primary metric (state the target on the metric itself)")
    if g.get("direction") == "rise" and re.search(r"fail|error|complaint|miss|re-attempt|unreach", metric) \
            and not re.search(r"success|completion|confirmed|resolved|accuracy|adoption", metric):
        errors.append("target direction 'rise' contradicts a failure-type primary metric (state the target on the metric itself)")
    if g.get("baseline_value") is None and g.get("baseline_source") != "measure in week 1":
        errors.append("baseline must be a client figure or 'measure in week 1'")
    if not g.get("guardrails"):
        errors.append("missing guardrail")
    return errors


def _fmt(v: float | None) -> str:
    if v is None:
        return "?"
    return f"{v:g}"


def _lc(s: str | None) -> str:
    """Sentence-internal casing: 'All new orders' -> 'all new orders';
    acronyms and proper nouns (second letter upper-case) are left alone."""
    s = (s or "").strip()
    if len(s) > 1 and s[0].isupper() and s[1].islower():
        return s[0].lower() + s[1:]
    return s


def canonical_sentence(g: dict | None) -> str:
    """THE sentence. Every restatement of the gate in every volume is this
    string verbatim; sections may explain around it, never rewrite it."""
    if not g:
        return ""
    dur = f"{_fmt(g.get('duration_value'))}-{g.get('duration_unit') or 'week'}"
    unit = "percentage points" if g.get("change_kind") == "percentage_point" else (
        "percent (relative)" if g.get("change_kind") == "relative" else "points")
    direction = g.get("direction") or "move"
    if g.get("baseline_source") == "client":
        base = f"from a baseline of {g.get('baseline')} (your figure)"
    elif g.get("baseline_source") == "measure in week 1":
        base = "from the baseline measured in week 1"
    elif g.get("baseline"):
        base = f"from a baseline of {g.get('baseline')} {LABEL}"
    else:
        base = "from the baseline measured in week 1"
    metric = _lc(g.get("primary_metric")) or "the primary metric"
    definition = ""
    if g.get("numerator") and g.get("denominator"):
        definition = f" — {_lc(g['numerator'])} divided by {_lc(g['denominator'])} —"
    guard = ""
    if g.get("guardrails"):
        guard = f"; the pilot pauses if {'; or if '.join(_lc(x) for x in g['guardrails'])} {LABEL}"
    return (f"Pilot decision gate: over a {dur} pilot {LABEL} covering {_lc(g.get('population')) or 'the pilot population'}"
            f" in {g.get('geography') or 'the pilot zone'}, measured against {_lc(g.get('control_method')) or 'the control group'},"
            f" {metric}{definition} must {direction} by {_fmt(g.get('target_value'))} {unit} {base}{guard}.")


def gate_claims(g: dict) -> list[dict]:
    """The gate as registry claims — PG (target) plus its numeric components."""
    base_claim = {"population": g.get("population") or "n/a", "scope": g.get("geography") or "engagement",
                  "phase": "PILOT", "provenance": "canonical_gate", "approval_status": APPROVAL_REQUIRED,
                  "source": "pilot_gate", "allowed_sections": ["decision", "gate", "module_kpi", "scoreboard",
                                                                "technical", "operations", "pilot_sop"]}
    claims = [{"id": "PG", "type": "pilot_gate", "value": g.get("target_value"),
               "unit": g.get("target_unit") or "", "time_basis": f"{_fmt(g.get('duration_value'))} {g.get('duration_unit') or ''}".strip(),
               "text": canonical_sentence(g), **base_claim}]
    if g.get("duration_value") is not None:
        claims.append({"id": "PG-duration", "type": "pilot_gate", "value": g["duration_value"],
                       "unit": g.get("duration_unit") or "week", "time_basis": "pilot", "text": f"{_fmt(g['duration_value'])} {g.get('duration_unit')}s",
                       **base_claim})
    if g.get("baseline_value") is not None:
        c = dict(base_claim)
        if g.get("baseline_source") == "client":
            c.update(provenance="client_input", approval_status="client_stated")
        claims.append({"id": "PG-baseline", "type": "pilot_gate", "value": g["baseline_value"],
                       "unit": "%" if "%" in str(g.get("baseline")) else "", "time_basis": "baseline",
                       "text": str(g.get("baseline")), **c})
    if g.get("guardrail_value") is not None:
        claims.append({"id": "PG-guardrail", "type": "pilot_gate", "value": g["guardrail_value"],
                       "unit": "", "time_basis": "pilot", "text": g["guardrails"][0], **base_claim})
    return claims


# ── restatement enforcement ───────────────────────────────────────────────────


def _metric_terms(g: dict) -> set[str]:
    words = re.findall(r"[a-z]+", (g.get("primary_metric") or "").lower())
    return {w for w in words if len(w) > 3 and w not in _STOP}


def _mentions_metric(sentence: str, g: dict) -> bool:
    s = sentence.lower()
    metric = (g.get("primary_metric") or "").lower()
    if metric and metric in s:
        return True
    terms = _metric_terms(g)
    hit = sum(1 for t in terms if t in s)
    return bool(terms) and hit >= max(2, min(3, len(terms) - 1))


def _has_number(sentence: str) -> bool:
    """A GATE-shaped number: a percentage, percentage points, a '1 in N'
    fraction or a week/day horizon — a bare count ('350 inquiries') does not
    make a sentence a gate restatement."""
    return bool(re.search(r"\d[\d.]*\s*(?:%|percent|percentage[- ]points?|pp\b)|\b1 in \d+\b|"
                          r"\d+\s*(?:weeks?|days?)\b|percentage point", sentence, re.IGNORECASE))


# our own deterministic gate-components table, as it reads in extracted PDF
# text — it is the gate's rendering, never a paraphrase of it
_GATE_TABLE = re.compile(r"Parameter Value Duration .*?(?:Approval status consultant_proposed — client approval required|"
                         r"Before launch, you approve:)", re.DOTALL)
# the scoreboard table likewise: its gate row IS the canonical sentence and
# its other rows are registry-governed; flattened cells are not prose
_SCOREBOARD_TABLE = re.compile(r"Metric Baseline Target Owner Review .*?(?:How each is measured:|SECTION \d+)", re.DOTALL)


_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[*(\-•\d])|\n")


# a restatement of the GATE speaks of its target: percentage points, a
# decision gate, a target, the pilot's horizon — a current-state sentence
# quoting the client's 12% and $5,832 does not
_GATE_SIGNAL = re.compile(
    r"percentage.point|\bpp\b|decision gate|pilot gate|unlock phase|\btarget|"
    r"within \d+ weeks? of (the )?pilot|\b1 in \d+\b|must (?:rise|fall) by", re.IGNORECASE)
_BOLD_LABEL = re.compile(r"\s+(?=\*\*[A-Z][^*\n]{2,60}:\*\*)")


def is_paraphrase(sentence: str, g: dict) -> bool:
    """A sentence that names the primary metric, carries a number and speaks
    of a target/baseline/change — and is not the canonical sentence."""
    canon = canonical_sentence(g)
    s = sentence.strip()
    if not s or (canon and canon in s) or TOKEN in s:
        return False
    return _has_number(s) and _mentions_metric(s, g) and bool(_GATE_SIGNAL.search(s))


def restatement_findings(text: str, g: dict) -> list[dict]:
    """Sentences that restate the gate in their own words — each one a high
    finding, because a reader cannot tell which of two criteria governs."""
    out = []
    if not g or not text:
        return out
    # rendered PDF text wraps sentences across lines: judge on collapsed
    # whitespace — but a bullet or list item (also an inline " - Item") is
    # its own sentence, and our gate-components table is the gate itself
    text = re.sub(r"\n\s*(?:[-*•]|\d+\.)\s+", ". ", text)
    text = re.sub(r"\s*•\s*", ". ", text)
    text = re.sub(r"\s-\s+(?=[A-Z*])", ". ", text)
    text = _BOLD_LABEL.sub(". ", text)
    text = re.sub(r"[ \t\r]*\n[ \t\r]*", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = _GATE_TABLE.sub(" [gate components table] ", text)
    text = _SCOREBOARD_TABLE.sub(" [scoreboard table] ", text)
    for sentence in _SPLIT.split(text):
        if is_paraphrase(sentence, g):
            out.append({"severity": "high", "source": "structural", "where": "pilot gate restatement",
                        "issue": ("The pilot gate is restated in other words instead of the canonical "
                                  f"sentence: \"{sentence.strip()[:180]}\""),
                        "fix": "replace with the canonical gate sentence verbatim"})
    return out


def enforce(text: str, g: dict | None) -> tuple[str, dict]:
    """Substitute the token and replace paraphrases with the canonical
    sentence (one per paragraph; further paraphrases in the same paragraph
    are removed). Returns (text, report)."""
    report = {"token_substitutions": 0, "paraphrases_replaced": 0, "paraphrases_removed": 0}
    if not text:
        return text, report
    if not g:
        return text.replace(TOKEN, ""), report
    canon = canonical_sentence(g)
    report["token_substitutions"] = text.count(TOKEN)
    out = text.replace(TOKEN, canon)
    paragraphs = out.split("\n")
    fixed = []
    for para in paragraphs:
        if not _has_number(para) or not _mentions_metric(para, g):
            fixed.append(para)
            continue
        has_canon = canon in para
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\[*(\-•\d])|\s+(?=\*\*[A-Z][^*\n]{2,60}:\*\*)|\s-\s+(?=[A-Z*])", para)
        rebuilt = []
        for s in sentences:
            if is_paraphrase(s, g):
                if has_canon:
                    report["paraphrases_removed"] += 1
                    continue
                rebuilt.append(canon)
                has_canon = True
                report["paraphrases_replaced"] += 1
            else:
                rebuilt.append(s)
        fixed.append(" ".join(rebuilt))
    return "\n".join(fixed), report


def ensure_in_decision(md: str, g: dict | None) -> str:
    """The decision section must carry the canonical sentence at least once;
    when the model wrote neither the token nor the sentence, it is inserted
    after the Phase 1 bullet."""
    if not md or not g:
        return md
    canon = canonical_sentence(g)
    head = md.find("## The decision")
    if head < 0:
        return md
    nxt = md.find("\n## ", head + 5)
    section = md[head: nxt if nxt > 0 else len(md)]
    if canon in section:
        return md
    m = re.search(r"(?m)^(\s*[-*]\s*\*\*Phase 1[^\n]*)$", section)
    if m:
        insert_at = head + m.end()
        return md[:insert_at] + f"\n  The decision gate — {canon}" + md[insert_at:]
    end = head + len(section)
    return md[:end].rstrip("\n") + f"\n\n**The decision gate:** {canon}\n" + md[end:]
