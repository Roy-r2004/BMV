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
# "90 percent" is the same quantity as "90%". Only the symbol was accepted,
# so the word form fell through to the model's own numeric field -- which
# holds the RATIO (0.9) -- and was then rendered with a percent sign.
# "percent" needs no negative lookahead: \b already fails inside
# "percentage", which _PP owns and which is tested first.
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent\b|per\s+cent\b|pct\b)", re.IGNORECASE)
_ONE_IN = re.compile(r"\b1 in (\d+)\b", re.IGNORECASE)
_EG = re.compile(r"\(\s*(?:e\.?g\.?,?|such as|for example,?)\s*([^)]+)\)", re.IGNORECASE)
_UP = re.compile(r"increas|rise|improv|higher|lift|grow|up\b", re.IGNORECASE)
_DOWN = re.compile(r"decreas|reduc|lower|fall|drop|fewer|down\b|cut", re.IGNORECASE)
_WEEK1 = re.compile(r"measure[d]? in week[- ]?(1|one)", re.IGNORECASE)
_STOP = {"rate", "the", "and", "for", "per", "of", "with", "from", "that", "this"}


# ── the canonical pilot DESIGN ────────────────────────────────────────────────
# One assignment rule for every engagement: comparable eligible units are
# randomized between treatment and control. A control drawn from other
# clients, zones, periods or an alternating rule is not a control.
_BAD_CONTROL = re.compile(
    r"\b(?:other (?:zones?|regions?|areas?|cities|districts?|branches?|clients?|business clients|customers|merchants|"
    r"accounts?|teams?|drivers?|couriers?)|all other (?:orders|deliveries|customers)|not (?:from|in) the (?:selected|pilot|chosen)|"
    r"different (?:zone|region|client|branch|city|period)|alternat\w+|every other (?:order|day|week)|predetermined|"
    r"odd[- /]even|by day of (?:the )?week|historical (?:baseline|period|data)|the (?:previous|prior|last) (?:month|year|period|quarter)|"
    r"before the pilot|pre-pilot period|outside (?:of )?(?:the )?(?:pilot |selected |chosen )?(?:zone|area|region|district|city|branch)|"
    r"existing customer orders)\b", re.IGNORECASE)
_RANDOM = re.compile(r"random|lottery|coin[- ]flip|50/50|50-50", re.IGNORECASE)
_DESIGN_TALK = re.compile(r"control group|control arm|treatment group|treatment and control|treatment vs\.? control|"
                          r"serve as (?:the )?control|assigned to (?:treatment|control)", re.IGNORECASE)


# The head noun of the pilot population: "All delivery orders placed for
# individuals via the app" -> orders; "Every council question the team asks"
# -> questions. Words are taken until a participle, determiner or preposition
# ends the noun phrase.
_UNIT_LEAD = re.compile(r"^\s*(?:every|each|all|any|the)\s+", re.IGNORECASE)
# Anything that ends a noun phrase. Possessives belong here: production run 21
# said "Every council question MY team asks", "my" was not a boundary, and the
# head noun became "my" -> "mies".
_FUNCTION_WORD = (r"that|which|who|whom|whose|the|a|an|my|our|your|their|his|her|its|this|these|those|"
                  r"from|in|into|on|at|to|for|during|with|within|via|by|of|about|across|per|under|over|"
                  r"after|before|and|or|but|excluding|including|where|when|while|are|is|was|were|be|been")
_UNIT_STOP = re.compile(rf"(?:[a-z-]+(?:ed|ing)|{_FUNCTION_WORD})$", re.IGNORECASE)


def _plural(word: str) -> str:
    w = word.lower()
    if w.endswith("s") and not w.endswith("ss"):
        return w
    if re.search(r"[^aeiou]y$", w):
        return w[:-1] + "ies"
    if re.search(r"(?:s|ss|sh|ch|x|z)$", w):
        return w + "es"
    return w + "s"


def assignment_unit(g: dict | None) -> str:
    """The thing being randomised, in the engagement's OWN words.

    This was hardcoded to "orders", which put a delivery client's vocabulary
    into every engagement that followed. The AI-datacentre gate randomised
    "comparable eligible orders" and counted "eligible deliveries" -- neither
    exists in that estate. A default that names another client's business is
    worse than a neutral one, so the fallback here is deliberately generic."""
    pop = _strip_label(str((g or {}).get("population") or ""))
    words: list[str] = []
    for w in re.findall(r"[A-Za-z][A-Za-z-]*", _UNIT_LEAD.sub("", pop)):
        if _UNIT_STOP.match(w) or len(words) >= 3:
            break
        words.append(w)
    # nothing but function words before the boundary: print the neutral word
    # rather than a plural of "my"
    return _plural(words[-1]) if words else "units"


def assignment_sentence(g: dict | None) -> str:
    """THE pilot design, rendered identically everywhere."""
    ratio = (g or {}).get("control_ratio") or 0.5
    t, c = int(round((1 - ratio) * 100)), int(round(ratio * 100))
    return (f"Comparable eligible {assignment_unit(g)} are randomized {t}/{c} between treatment and control — "
            "the control group keeps today's process and is never drawn from another client, zone or period.")


def design_errors(g: dict | None) -> list[str]:
    """Why a stated control method is not the canonical design."""
    cm = str((g or {}).get("control_method_stated") or (g or {}).get("control_method") or "")
    errs = []
    if _BAD_CONTROL.search(cm):
        errs.append("the control group must be comparable eligible orders randomized between treatment and control — "
                    "never other clients, zones, time periods or an alternating rule")
    elif cm and not _RANDOM.search(cm) and (g or {}).get("control_ratio") is None:
        errs.append("assignment must be randomized (state the random 50/50 split between treatment and control)")
    return errs


def flatten_prose(text: str) -> str:
    """Markdown or rendered text as one line of sentences: a bullet, a
    numbered item, a heading or a table row is its own sentence boundary
    ('• '), so two list items are never read as one sentence."""
    t = text or ""
    t = re.sub(r"(?m)^\s*(?:[-*•]|\d+\.)\s+", " • ", t)
    t = re.sub(r"(?m)^\s*#{1,6}\s+", " • ", t)
    t = re.sub(r"(?m)^\s*\|", " • ", t)
    t = re.sub(r"\s*\n\s*", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def design_findings(text: str, g: dict | None) -> list[dict]:
    """Rendered-text check: any sentence that describes the control or the
    assignment differently from the canonical design is a high finding."""
    out = []
    if not text or not g:
        return out
    flat = flatten_prose(text)
    canon = assignment_sentence(g).lower()
    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z\[(•])|•", flat):
        if canon in sentence.lower():  # the gate box prints it sentence-internal, lower-cased
            continue
        if _DESIGN_TALK.search(sentence) and _BAD_CONTROL.search(sentence):
            out.append({"severity": "high", "source": "structural", "where": "pilot design",
                        "issue": ("The pilot design is restated with a control that is not the canonical design "
                                  f"(randomized comparable orders): \"{sentence.strip()[:180]}\""),
                        "fix": "state the canonical assignment: " + assignment_sentence(g)})
    return out


def enforce_design(text: str, g: dict | None) -> tuple[str, list[dict]]:
    """In a structured string (an SOP step, a checklist item) a sentence that
    assigns treatment/control by anything other than randomization is
    replaced by the canonical assignment sentence."""
    records: list[dict] = []
    if not text or not g:
        return text, records
    # a sentence ends at . ! ? followed by a capital — "e.g. odd/even" is not a boundary
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\[(•])", text)
    out = []
    for s in parts:
        if _DESIGN_TALK.search(s) and _BAD_CONTROL.search(s):
            records.append({"original": s.strip()[:160], "replaced_with": assignment_sentence(g)})
            out.append(assignment_sentence(g))
        else:
            out.append(s)
    return " ".join(out), records


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
    stated = _strip_label(str(raw.get("control_method_stated") or raw.get("control_method") or raw.get("control") or "")) or None
    g["control_method_stated"] = stated
    g["control_method"] = stated
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
    # Whether the number came from the labelled TEXT or was borrowed from the
    # model's numeric field. When a parse fails silently the two can disagree
    # by a factor of a hundred and nothing below notices, because the
    # conflict check compares the value against the field -- and after a
    # failed parse they are the same object.
    g["target_value_from_text"] = tv is not None
    if tv is None:
        tv = field
    g["target_value"] = tv
    g["target_value_field"] = field
    # the same number written as a fraction (0.05 for "5 percentage points")
    # is not a contradiction — it is reconciled and recorded; a different
    # number (0.93, the resulting rate) is
    same = field is not None and tv is not None and (
        abs(field - tv) <= 0.01 * max(tv, 1) or abs(field * 100 - tv) <= 0.01 * max(tv, 1))
    g["target_value_reconciled"] = (field is not None and tv is not None and abs(field - tv) > 0.01 * max(tv, 1) and same)
    g["target_value_conflict"] = (field is not None and tv is not None and not same)
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
    # PilotGate: the comparison is treatment versus CONTROL — never the
    # treatment versus its own week-one baseline
    g["id"] = str(raw.get("id") or "PG-01")
    cm = g.get("control_method") or ""
    ratio = re.search(r"(\d{1,2})\s*%", cm)
    g["control_ratio"] = (float(ratio.group(1)) / 100) if ratio else (0.5 if re.search(r"half|50/50|50-50|random", cm, re.IGNORECASE) else None)
    tm = re.search(r"(?:while )?(?:the )?other \d{1,2}\s*%\s*(?:receives?|gets?|is given)\s*([^.;]+)", cm, re.IGNORECASE)
    g["treatment"] = (tm.group(1).strip() if tm else
                      (str(raw.get("treatment") or "").strip() or "the pilot workflow"))
    # the canonical DESIGN: a valid stated method renders as the one
    # assignment sentence; an invalid one stays as stated so gate_errors()
    # names it and the decomposition is retried
    g["design_errors"] = design_errors(g)
    if stated and not g["design_errors"]:
        g["control_method"] = assignment_sentence(g)
    g["assignment"] = assignment_sentence(g) if not g["design_errors"] else None
    g["control"] = g["control_method"]  # the legacy key mirrors the rendered method
    g["target_vs_control"] = bool(g.get("control_method"))
    if g["target_vs_control"] and g.get("primary_metric"):
        m = g["primary_metric"]
        # the comparison follows the change kind: a percentage-point target is
        # the absolute difference; a relative target is that difference
        # divided by the control rate
        if g.get("change_kind") == "relative":
            g["comparison_metric"] = f"(treatment {m} minus control {m}) divided by control {m}"
            g["target_formula"] = (f"(treatment rate − control rate) ÷ control rate must be at least "
                                   f"{_fmt(g.get('target_value'))}%" if g.get("direction") != "fall" else
                                   f"(control rate − treatment rate) ÷ control rate must be at least {_fmt(g.get('target_value'))}%")
        else:
            g["comparison_metric"] = f"treatment {m} minus control {m}"
            g["target_formula"] = (f"treatment rate − control rate must be at least {_fmt(g.get('target_value'))} percentage points"
                                   if g.get("direction") != "fall" else
                                   f"control rate − treatment rate must be at least {_fmt(g.get('target_value'))} percentage points")
        if not (g.get("denominator") and re.search(r"group|assigned|arm", g["denominator"], re.IGNORECASE)):
            # the denominator counts the same unit the assignment randomises;
            # these were two different hardcoded nouns ("orders" and
            # "deliveries") describing one population
            g["denominator"] = f"eligible {assignment_unit(g)} assigned to each group"
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
    # `is False`, not falsy: the flag is written by normalize_gate, so a gate
    # stored before this check existed simply has no opinion. Reading its
    # absence as a failed parse condemns every engagement already on disk --
    # request 53, a delivered package, went from clean to two findings on
    # exactly that mistake. No evidence is not evidence of a defect.
    if (g.get("target_value") is not None and g.get("target_value_from_text") is False
            and _NUM.search(str(g.get("target") or ""))):
        errors.append(
            f"the target text states a number this gate could not parse "
            f"({_strip_label(str(g.get('target') or ''))[:80]!r}), so target_value "
            f"({_fmt(g.get('target_value'))}) came from the model's field instead of the "
            f"text — state the target as a percentage, a percentage-point change or '1 in N'")
    if g.get("target_value_conflict"):
        errors.append(f"target_value ({g.get('target_value_field')}) contradicts the target text "
                      f"({_fmt(g.get('target_value'))} {_unit_words(g)}) — write target_value exactly as the number in "
                      f"the target text: {_fmt(g.get('target_value'))}")
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
    errors += design_errors(g)
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


_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
          10: "ten", 11: "eleven", 12: "twelve"}


def _duration_words(g: dict) -> str:
    v = g.get("duration_value")
    unit = g.get("duration_unit") or "week"
    if v is None:
        return "the pilot"
    n = int(v) if float(v).is_integer() else v
    word = _WORDS.get(n, str(n)) if isinstance(n, int) else str(n)
    return f"{word} {unit}{'s' if n != 1 else ''}"


def _unit_words(g: dict) -> str:
    return ("percentage points" if g.get("change_kind") == "percentage_point" else
            "percent (relative)" if g.get("change_kind") == "relative" else "points")


def _metric_short(g: dict) -> str:
    m = _lc(g.get("primary_metric")) or "the primary metric"
    return re.sub(r"\s+rate$", "", m)


def canonical_sentence(g: dict | None) -> str:
    """THE short reference. Every restatement of the gate outside the gate
    box is this string verbatim; sections may explain around it, never
    rewrite it. The comparison is treatment versus control."""
    if not g:
        return ""
    verb = "fall below" if g.get("direction") == "fall" else "exceed"
    return (f"{g.get('id') or 'PG-01'}: treatment {_metric_short(g)} must {verb} control by "
            f"{_fmt(g.get('target_value'))} {_unit_words(g)} after {_duration_words(g)}; guardrails apply. "
            "Proposed — client approval required.")


def full_definition(g: dict | None) -> str:
    """The complete gate, printed ONCE (the gate box). Everywhere else the
    short reference stands in for it."""
    if not g:
        return ""
    dur = f"{_fmt(g.get('duration_value'))}-{g.get('duration_unit') or 'week'}"
    metric = _lc(g.get("primary_metric")) or "the primary metric"
    ratio = g.get("control_ratio")
    split = (_lc(assignment_sentence(g)).rstrip(".") if (ratio or not g.get("design_errors")) and g.get("control_method")
             else (_lc(g.get("control_method")) or "a control group"))
    definition = ""
    if g.get("numerator") and g.get("denominator"):
        definition = f" ({_lc(g['numerator'])}, divided by {_lc(g['denominator'])})"
    verb = "fall below" if g.get("direction") == "fall" else "exceed"
    guard = ""
    if g.get("guardrails"):
        guard = f" Guardrails: the pilot pauses if {'; or if '.join(_lc(x) for x in g['guardrails'])} {LABEL}."
    base = ""
    if g.get("baseline_source") == "client":
        base = f" Context only: today's {metric} is {g.get('baseline')} (your figure); the control group, not this baseline, is the comparison."
    elif g.get("baseline_source") == "measure in week 1":
        base = " Context only: the week-one measurement of both groups; the control group, not a baseline, is the comparison."
    return (f"{g.get('id') or 'PG-01'} — the pilot decision gate. Duration: {dur} pilot {LABEL}. "
            f"Population: {_lc(g.get('population')) or 'the pilot population'}. Geography: {g.get('geography') or 'the pilot zone'}. "
            f"Assignment: {split}; the treatment group receives {_lc(g.get('treatment')) or 'the pilot workflow'}. "
            f"Primary metric: {g.get('comparison_metric') or metric}{definition}. "
            f"Target: treatment {metric} must {verb} the control group's by {_fmt(g.get('target_value'))} {_unit_words(g)}"
            f"{' — ' + g['target_formula'] if g.get('target_formula') else ''} {LABEL}."
            f"{guard}{base} Approval status: {(g.get('approval_status') or APPROVAL_REQUIRED).replace('_', ' ')}.")


def gate_claims(g: dict) -> list[dict]:
    """The gate as registry claims — PG (target) plus its numeric components."""
    base_claim = {"population": g.get("population") or "n/a", "scope": g.get("geography") or "engagement",
                  "phase": "PILOT", "provenance": "canonical_gate", "approval_status": APPROVAL_REQUIRED,
                  "source": "pilot_gate", "allowed_sections": ["decision", "gate", "module_kpi", "scoreboard",
                                                                "technical", "operations", "pilot_sop"]}
    claims = [{"id": "PG", "type": "pilot_gate", "value": g.get("target_value"),
               "unit": g.get("target_unit") or "", "time_basis": f"{_fmt(g.get('duration_value'))} {g.get('duration_unit') or ''}".strip(),
               "text": canonical_sentence(g), "full_definition": full_definition(g),
               "assignment": assignment_sentence(g), **base_claim}]
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
    of a target/baseline/change — and is neither the short reference nor
    the once-printed full definition."""
    canon = canonical_sentence(g)
    full = full_definition(g)
    s = sentence.strip()
    if not s or (canon and canon in s) or (full and (full in s or s in full)) or TOKEN in s:
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
    full = re.sub(r"\s+", " ", full_definition(g))
    if full:
        text = text.replace(full, " [full gate definition] ")
    canon = re.sub(r"\s+", " ", canonical_sentence(g))
    if canon:
        text = text.replace(canon, " [canonical gate reference] ")
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
    full = full_definition(g)
    report["token_substitutions"] = text.count(TOKEN)
    out = text.replace(TOKEN, canon)
    # the canonical sentence carries an internal full stop ("apply. Proposed
    # —"): it is masked as one token so no splitter cuts it in two
    mask = "\x00CANON\x00"
    out = out.replace(canon, mask)
    paragraphs = out.split("\n")
    fixed = []
    for para in paragraphs:
        if not _has_number(para) or not _mentions_metric(para, g) or (full and full in para):
            fixed.append(para)
            continue
        has_canon = mask in para
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\[*(\-•\d])|\s+(?=\*\*[A-Z][^*\n]{2,60}:\*\*)|\s-\s+(?=[A-Z*])", para)
        rebuilt = []
        for s in sentences:
            if mask in s:
                rebuilt.append(s)
            elif is_paraphrase(s, g):
                if has_canon:
                    report["paraphrases_removed"] += 1
                    continue
                rebuilt.append(canon)
                has_canon = True
                report["paraphrases_replaced"] += 1
            else:
                rebuilt.append(s)
        fixed.append(" ".join(rebuilt))
    return "\n".join(fixed).replace(mask, canon), report


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


# Engagement-agnostic names for the Phase-1 pilot's tooling and its human
# operator — settings, so an engagement may rename them; never a client's
# module name
from app.config import settings as _settings

PILOT_TOOLING = getattr(_settings, "PILOT_TOOLING_NAME", None) or "Pilot Review Queue"
PILOT_OPERATOR = getattr(_settings, "PILOT_OPERATOR_ROLE", None) or "Pilot Support Operator"
PILOT_CUSTOMER_FORM = getattr(_settings, "PILOT_CUSTOMER_FORM_NAME", None) or "Pilot Confirmation Form"
