"""Deterministic adjudication of quality-bench findings.

Run 42 taught the lesson this module encodes: the LLM auditor recomputed
900 x 365 x 0.12 x 1.80 as 59,040 (the true product is 70,956) and cascaded
five false high findings off its own error — while genuinely wrong figures
sat one field away. An LLM's verdict alone may neither close nor sustain an
arithmetic finding: machine evidence decides.

Rules, applied to each OPEN high finding:

R1 ARITHMETIC — a finding is a proven false positive when it disputes a
   value the deterministic recompute verifies exactly (the finding's issue
   cites a verified value AND its fix proposes a replacement number that is
   NOT verified). A finding whose proposed fix agrees with the verified
   value (attribution/wording complaints) is untouched.

R2 LABEL — a finding claiming a threshold lacks its approval label is a
   false positive when every occurrence of that threshold in the rendered
   text carries "(proposed" within reach; confirmed when any occurrence is
   bare. Deterministic label evidence outranks the auditor's wording: the
   rule runs on ANY finding that quotes a numeric fragment and speaks of
   labels, approval, thresholds, invented or unverified values (run 46's
   bench wrote "invented, unverified threshold. It lacks …" and the old
   trigger, keyed to exact phrases, never ran).

R3 DOCUMENT DATE — a finding that flags a document/generation date as a
   threshold is a false positive: dates of record are not SLAs.

R4 CAPACITY — demanding dollars for hours/staff/volumes while the loaded
   labor costs are BY DESIGN in missing_inputs is a false positive.

R5 SCENARIO COMPLETENESS — an omission claim closes when the component map
   proves every promised mechanism delivered.

R6 PHASE SEMANTICS — a finding that reads FUTURE procedures as contradicting
   the build sequence closes when the structured phase data shows every
   FUTURE procedure belongs to a planned module and none instructs present
   execution (FUTURE = availability; "build first" = sequence).

R7 THRESHOLD TYPE — a finding that demands an approval label on a number
   the registry types as a functional completeness requirement ("100% of
   eligible orders" = every eligible order) is a false positive: functional
   requirements carry no threshold label; they render as words.

Everything else stays exactly as the bench left it — adjudication proves
false positives with evidence; it never waves through real defects.
"""

import json
import re

from app.models import Request

_NUM_RE = re.compile(r"\d[\d,]*\.?\d*\s*%?")
_LABEL_WINDOW = 130
_QUOTED = re.compile(r"'([^']{2,90})'")
_DOC_DATE = re.compile(
    r"(generated|prepared exclusively|reviewed and released on)[^.]{0,60}"
    r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}",
    re.IGNORECASE,
)
_LABEL_TALK = re.compile(
    r"\(proposed|approval label|client approval|unlabel|lacks|without (an? )?(approval|label|proposed)|"
    r"not (?:attributed|labeled|labelled)|(?:invented|unverified)[, ]+(?:unverified )?threshold", re.IGNORECASE)
_GATE_TALK = re.compile(r"decision gate|pilot gate|pilot decision|success criteri|primary metric|pilot.s (?:primary )?metric",
                        re.IGNORECASE)
_KPI_TALK = re.compile(r"success metric|\bKPI|know it.?s working|metric(?:s)? (?:should|must) be distinct|success criteria",
                       re.IGNORECASE)
_MONTH_TALK = re.compile(r"/month|per month|monthly|30-day|calendar month|/ ?12", re.IGNORECASE)
_PHASE_TALK = re.compile(
    r"\bfuture\b.{0,300}(build first|build plan|what we.d build|implying|contradict|sequence|numbered|"
    r"immediate implementation|phase 1)|"
    r"(build first|build plan|what we.d build|implying|contradict|sequence|numbered).{0,300}\bfuture\b",
    re.IGNORECASE | re.DOTALL)


def _numbers_in(text: str) -> list[float]:
    vals = []
    for m in _NUM_RE.finditer(text or ""):
        tok = m.group(0).strip()
        pct = tok.endswith("%")
        try:
            v = float(tok.rstrip("%").replace(",", "").strip())
        except ValueError:
            continue
        vals.append(v / 100.0 if pct else v)
    return vals


def _recomputed_value(arith: str, stated: str) -> float | None:
    """Recompute a plain product with an optional period step; return the
    stated value when the machine confirms it (never relies on stored
    verification marks — adjudication re-derives everything itself)."""
    if not arith or not stated or "+" in arith or " - " in arith:
        return None
    operands = _numbers_in(arith)
    stated_vals = _numbers_in(stated)
    if len(operands) < 2 or not stated_vals:
        return None
    product = 1.0
    for v in operands:
        product *= v
    target = stated_vals[0]
    if not target:
        return None
    for period in (1, 12, 26, 52, 365):
        if abs(product * period - target) / abs(target) <= 0.005:
            return target
    return None


def _verified_values(fm: dict) -> dict[float, str]:
    """value -> evidence, for every machine-verifiable financial claim plus
    its package-identity derivations (30-day monthly = /365*30, daily)."""
    out: dict[float, str] = {}

    def _add(v: float, why: str) -> None:
        if v:
            out[round(v, 2)] = why

    line_values: list[float] = []
    for line in (fm.get("lines") or []) if isinstance(fm, dict) else []:
        if not isinstance(line, dict):
            continue
        arith = str(line.get("arithmetic") or "")
        annual = _recomputed_value(arith, str(line.get("annual") or ""))
        if annual is None:
            continue
        line_values.append(annual)
        _add(annual, f"deterministic recompute of '{arith}' = {annual:,.0f}")
        _add(annual / 365, f"{annual:,.0f}/year / 365 = {annual / 365:,.2f}/day")
        _add(annual / 365 * 30, f"{annual:,.0f}/year / 365 x 30 = {annual / 365 * 30:,.2f}/30-day month")
    for sc in (fm.get("scenarios") or []) if isinstance(fm, dict) else []:
        if not isinstance(sc, dict):
            continue
        fracs = [v for v in _numbers_in(str(sc.get("assumption") or "")) if 0 < v < 1]
        impacts = [v for v in _numbers_in(str(sc.get("impact") or "")) if v > 1]
        if not fracs or not impacts:
            continue
        impact = impacts[0]
        hit = next(((frac, base) for frac in fracs for base in line_values
                    if abs(base * frac - impact) / max(impact, 1e-9) <= 0.005), None)
        if hit:
            frac, base = hit
            _add(impact, f"scenario '{sc.get('name')}': {frac:.0%} x verified {base:,.0f} = {impact:,.0f}")
            _add(impact / 365 * 30, f"verified scenario impact {impact:,.0f} / 365 x 30 = {impact / 365 * 30:,.2f}/30-day month")
    return out


def _matches(value: float, verified: dict[float, str]) -> str | None:
    for v, why in verified.items():
        if v and abs(v - value) / max(abs(v), 1e-9) <= 0.005:
            return why
    return None


def _label_check(fragment: str, corpus: str) -> tuple[bool | None, str]:
    """(all labeled?, evidence). None when the fragment isn't found."""
    nums = [m.group(0) for m in _NUM_RE.finditer(fragment) if any(c.isdigit() for c in m.group(0))]
    probe = fragment.strip() if len(fragment.strip()) <= 40 else (nums[0].strip() if nums else fragment[:40])
    hits = [m.start() for m in re.finditer(re.escape(probe), corpus)]
    if not hits and nums:
        probe = nums[0].strip()
        hits = [m.start() for m in re.finditer(re.escape(probe), corpus)]
    if not hits:
        return None, f"'{probe}' not found in rendered text"
    bare = sum(1 for h in hits if "(proposed" not in corpus[h:h + _LABEL_WINDOW])
    if bare:
        return False, f"'{probe}': {bare} of {len(hits)} occurrence(s) carry no approval label"
    return True, f"'{probe}': all {len(hits)} occurrence(s) labeled '(proposed …)' in the rendered text"


def _functional_fragment(fragment: str, corpus: str) -> bool:
    """'100% of <things>' / 'all' / 'every' is a completeness requirement."""
    f = fragment.lower()
    if re.search(r"\b100\s*%\s*(of|for)\b", f) or re.search(r"\b(all|every)\b", f):
        return True
    if re.fullmatch(r"\s*100\s*%?\s*", f):
        for m in re.finditer(r"100\s*%", corpus):
            if re.match(r"\s*(of|for)\b", corpus[m.end():m.end() + 8]):
                return True
    return False


def adjudicate(req: Request, texts: dict[str, str] | None = None, *, persist: bool = True) -> dict:
    """Adjudicate the run's open high findings (in place when persist=True;
    commit req's session afterwards). Returns the ledger."""
    qa = json.loads(req.qa_report_json) if req.qa_report_json else {}
    if not persist:
        qa = json.loads(json.dumps(qa))
    findings = qa.get("findings") or []
    bc = json.loads(req.business_case_json) if req.business_case_json else {}
    fm = (bc.get("financial_model") or {}) if isinstance(bc, dict) else {}
    verified = _verified_values(fm)
    corpus = "\n".join((texts or {}).values()) or "\n".join(
        str(x or "") for x in (req.mvp_blueprint, req.technical_plan))
    modules = json.loads(req.modules_json) if req.modules_json else []
    procedures = (json.loads(req.procedures_json) if req.procedures_json else {}).get("procedures") or []
    # the typed gate and registry, from the row when it has them, rebuilt in
    # memory otherwise (runs that predate the registry column)
    from app.pipeline import pilot_gate as _pg
    from app.pipeline import registry as _registry
    from app.pipeline import timebasis as _tb

    registry = _registry.registry_for(req)
    if registry is None:
        import copy

        try:
            registry = _registry.build_registry(
                getattr(req, "ops_numbers_json", None), copy.deepcopy(bc) if isinstance(bc, dict) else {},
                copy.deepcopy(modules))
        except Exception:
            registry = None
    gate = (registry or {}).get("pilot_gate") or (
        _pg.normalize_gate(bc.get("pilot_gate")) if isinstance(bc, dict) and isinstance(bc.get("pilot_gate"), dict)
        and bc.get("pilot_gate") else None)
    annuals = [c["value"] for c in (registry or {}).get("claims") or []
               if c.get("type") == "derived_value" and c.get("unit") == "USD" and isinstance(c.get("value"), (int, float))]

    ledger = []
    for i, f in enumerate(findings, 1):
        entry = {"id": f"F{i:02d}", "where": f.get("where"), "issue": f.get("issue"),
                 "severity": f.get("severity"), "source": f.get("source")}
        if f.get("severity") != "high" or f.get("repaired"):
            entry["classification"] = "closed (repaired)" if f.get("repaired") else "low"
            ledger.append(entry)
            continue

        issue, fix = str(f.get("issue") or ""), str(f.get("fix") or "")

        def _close(kind: str, evidence: str, classification: str) -> None:
            f["adjudication"] = kind
            f["machine_evidence"] = evidence
            entry.update(classification=classification, evidence=evidence)
            ledger.append(entry)

        # R1 — arithmetic: disputes a verified value, proposes an unverified one
        cited = [(v, _matches(v, verified)) for v in _numbers_in(issue) if v > 1]
        cited_verified = [(v, why) for v, why in cited if why]
        fix_nums = [v for v in _numbers_in(fix) if v > 1]
        fix_all_unverified = fix_nums and all(not _matches(v, verified) for v in fix_nums)
        if cited_verified and fix_all_unverified:
            _close("false_positive",
                   f"R1: the disputed value is machine-verified ({cited_verified[0][1]}); the auditor's replacement is not",
                   "machine-proven false positive")
            continue
        # R12 — monthly identity: a calendar-month figure or a mixed-formula sentence
        if annuals and _MONTH_TALK.search(issue):
            drift = _tb.identity_findings({"rendered": corpus}, annuals)
            if drift:
                _close("confirmed", f"R12: {drift[0]['issue'][:200]}", "real defect")
                continue
        # R1 (confirming direction) — the auditor disputes an UNverified value
        # and proposes the verified derivation: the recompute agrees with the auditor
        dollar_cited = [float(x.replace(",", "")) for x in re.findall(r"\$\s?([\d,]+(?:\.\d+)?)", issue)]
        cited_unverified = [v for v in dollar_cited if v > 1 and not _matches(v, verified)] or \
            [v for v, why in cited if not why]
        fix_verified = [(v, _matches(v, verified)) for v in fix_nums if _matches(v, verified)]
        if cited_unverified and fix_verified and re.search(r"discrepanc|incorrect|wrong|does not equal|evaluates to|invented",
                                                             issue, re.IGNORECASE):
            disputed = min(cited_unverified, key=lambda v: abs(v - fix_verified[0][0]))
            _close("confirmed",
                   f"R1: the recompute agrees with the auditor — {fix_verified[0][0]:,.2f} is the verified derivation "
                   f"({fix_verified[0][1]}); the stated {disputed:,.2f} is not",
                   "real defect")
            continue
        # R8 — gate restatement: the rendered text carries paraphrases of the canonical gate
        if gate and _GATE_TALK.search(issue):
            paraphrases = _pg.restatement_findings(corpus, gate)
            if paraphrases:
                _close("confirmed",
                       f"R8: {len(paraphrases)} sentence(s) in the rendered text restate the pilot gate in other words "
                       f"than the canonical sentence (e.g. \"{paraphrases[0]['issue'].split(chr(34))[1][:120]}\")",
                       "real defect")
                continue
        # R11 — module KPIs: coined numbers that map to no registered claim
        if registry and _KPI_TALK.search(issue):
            unmapped = _registry.kpi_number_findings((texts or {}).get("blueprint") or corpus, registry,
                                                     strict_kpi=True)
            if unmapped:
                _close("confirmed",
                       f"R11: {len(unmapped)} KPI/acceptance number(s) in the rendered text map to no registered claim "
                       f"(e.g. {unmapped[0]['issue'][:120]})",
                       "real defect")
                continue
        # R3 — a document date is not a threshold
        if ("threshold" in issue.lower() or "sla" in issue.lower()) and _DOC_DATE.search(issue):
            _close("false_positive", "R3: the flagged value is a document date of record, not an operational threshold",
                   "machine-proven false positive")
            continue
        # R4 — capacity-is-not-cash
        missing = " ".join(str(x) for x in (fm.get("missing_inputs") or [])).lower()
        wants_dollars = re.search(r"without[^.]{0,40}(currency|cost)|in terms of cost|not.{0,20}monetiz",
                                  issue, re.IGNORECASE)
        about_capacity = re.search(r"hours|staff|inquiries|capacity", issue, re.IGNORECASE)
        if wants_dollars and about_capacity and "hourly cost" in missing:
            _close("false_positive",
                   "R4: converting capacity to currency requires the loaded labor costs, which are "
                   "correctly listed as missing inputs — the capacity-is-not-cash law forbids inventing them",
                   "machine-proven false positive")
            continue
        # R5 — scenario-completeness evidence
        if "fails to include any impact" in issue or "omit" in issue.lower():
            from app.pipeline.structural import scenario_component_map

            where = str(f.get("where") or "")
            target = next((sc for sc in (fm.get("scenarios") or [])
                           if isinstance(sc, dict) and str(sc.get("name") or "") and
                           str(sc.get("name")) in where), None)
            if target is not None:
                cmap = scenario_component_map(target)
                if cmap["complete"]:
                    _close("false_positive",
                           f"R5: component map complete — {cmap['promised']} promised mechanism(s), "
                           f"{cmap['quantified']} quantified + {cmap['cannot_quantify_notes']} "
                           f"explicit cannot-quantify note(s) delivered", "machine-proven false positive")
                    continue
        # R6 — phase semantics from structured data
        if _PHASE_TALK.search(issue) and procedures:
            from app.pipeline.phases import future_is_consistent

            ok, evidence = future_is_consistent(procedures, modules)
            if ok and not re.search(r"\b(today|immediately|right away)\b", issue, re.IGNORECASE):
                _close("false_positive", "R6: " + evidence,
                       "semantic false positive resolved by structured phase data")
                continue
        # R7 + R2 — label evidence outranks the auditor's wording
        if _LABEL_TALK.search(issue):
            quoted = [q for q in _QUOTED.findall(issue)
                      if any(ch.isdigit() for ch in q) and not re.fullmatch(r"\s*\d{1,2}\s*", q)]
            if quoted:
                fragment = quoted[0]
                if _functional_fragment(fragment, corpus) and not re.search(r"\(proposed", fragment):
                    _close("false_positive",
                           f"R7: '{fragment}' is a functional completeness requirement (every eligible "
                           "item), not a threshold — no approval label applies; it renders as words",
                           "semantic false positive resolved by structured threshold typing")
                    continue
                labeled, evidence = _label_check(fragment, corpus)
                if labeled is True:
                    _close("false_positive", f"R2: {evidence}", "machine-proven false positive")
                    continue
                if labeled is False:
                    _close("confirmed", f"R2: {evidence}", "real defect")
                    continue
        # R10 — pilot-module honesty: a Phase 1 naming/AI finding against the registry
        if registry and re.search(r"phase 1|pilot", issue, re.IGNORECASE) and \
                re.search(r"engine|predictive|rules-based|manual|\bAI\b", issue, re.IGNORECASE):
            errs = [e for e in (registry.get("errors") or []) if "pilot" in e.lower()]
            renames = registry.get("renames") or []
            if errs or renames:
                _close("confirmed",
                       "R10: the registry rejects the pilot module as named/specified — "
                       + "; ".join(errs[:2] + [f"rename required: '{r['from']}' -> '{r['to']}'" for r in renames[:1]]),
                       "real defect")
                continue
        f["adjudication"] = "confirmed"
        f["machine_evidence"] = "no deterministic rule proves this false — stays open"
        entry.update(classification="real defect", evidence=f["machine_evidence"])
        ledger.append(entry)

    if persist:
        req.qa_report_json = json.dumps(qa)
    open_real = sum(1 for e in ledger if e.get("classification") == "real defect")
    fps = sum(1 for e in ledger if "false positive" in str(e.get("classification")))
    return {"ledger": ledger, "open_real": open_real, "false_positives": fps, "findings": findings}
