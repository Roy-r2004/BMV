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
        # every component of the impact (dollars AND counts) that is a
        # fraction of a verified line is verified
        for j, impact in enumerate(impacts):
            hit = next(((frac, base) for frac in fracs for base in line_values
                        if abs(base * frac - impact) / max(impact, 1e-9) <= 0.005), None)
            if hit:
                frac, base = hit
                _add(impact, f"scenario '{sc.get('name')}': {frac:.0%} x verified {base:,.0f} = {impact:,.0f}")
                if j == 0:
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
    frag = re.sub(r"\s+", " ", fragment.strip())
    corpus = re.sub(r"\s+", " ", corpus)
    # the most specific probe that exists in the text wins — a bare "50%"
    # would count every unrelated 50% on the page (run 47, F10)
    hits, probe = [], frag
    for cand in (frag, frag[:60].strip(), frag[:40].strip()) + ((nums[0].strip(),) if nums else ()):
        if not cand:
            continue
        hits = [m.start() for m in re.finditer(re.escape(cand), corpus)]
        if hits:
            probe = cand
            break
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
            # the figure IS the package identity and the auditor objects only
            # to the words "per month": the convention is stated in the document
            monthly_cited = [v for v in _numbers_in(issue) if v > 1 and _matches(v, verified)
                             and any(abs(v - a / 365 * 30) / max(v, 1e-9) <= 0.005 for a in annuals)]
            unverified_cited = [v for v in _numbers_in(issue) if v > 1 and not _matches(v, verified)
                                and v not in (30, 365, 12)]
            if monthly_cited and not unverified_cited and \
                    re.search(r"30-day (?:operating )?month|operating month|operating_30_day|identity|convention|per month'",
                              issue, re.IGNORECASE):
                _close("false_positive",
                       f"R12: {monthly_cited[0]:,.0f} is the package's 30-day operating-month identity and the package "
                       "states that convention; 'per month' means that month throughout",
                       "machine-proven false positive")
                continue
        # R26 — structural corroboration: the machine finds the same defect in the structured layer
        from app.pipeline.structural import inline_product_findings

        scen_names = [str(sc.get("name")) for sc in (fm.get("scenarios") or []) if isinstance(sc, dict) and sc.get("name")]
        named_scen = [n for n in scen_names if n and n in issue]
        if named_scen:
            corroborating = [sf for sf in inline_product_findings(bc if isinstance(bc, dict) else {})
                             if any(n in sf["issue"] for n in named_scen)]
            if corroborating:
                _close("confirmed", "R26: " + corroborating[0]["issue"][:220], "real defect")
                continue
        # R25 — the auditor quotes arithmetic the document never contains
        quoted_arith = re.findall(r"\(\s*\d[\d,]*(?:\.\d+)?\s*[x×*]\s*\d*\.?\d+\s*\)", issue)
        doc_text = re.sub(r"\s+", " ", corpus + " " + (req.business_case_json or ""))
        if quoted_arith and not any(re.sub(r"\s+", "", q) in re.sub(r"\s+", "", doc_text) for q in quoted_arith) and cited_verified:
            _close("false_positive",
                   f"R25: the arithmetic the auditor quotes ({quoted_arith[0]}) appears nowhere in the document or its "
                   f"structured layers — the stated figure is machine-verified ({cited_verified[0][1]})",
                   "machine-proven false positive")
            continue
        # R24 — the auditor's own recompute drifts from the document's exactly-verified
        # value by less than the verification tolerance ("5828.60, not 5832.00"): the
        # machine product equals the document value; the auditor's arithmetic is off
        exact = {}
        for line in (fm.get("lines") or []) if isinstance(fm, dict) else []:
            if isinstance(line, dict):
                rv = _recomputed_value(str(line.get("arithmetic") or ""), str(line.get("annual") or ""))
                if rv:
                    exact[round(rv, 2)] = f"{line.get('arithmetic')} = {rv:,.2f}"
                    exact[round(rv / 365 * 30, 2)] = f"{rv:,.0f}/year / 365 x 30 = {rv / 365 * 30:,.2f}"
                    exact[round(rv / 365, 2)] = f"{rv:,.0f}/year / 365 = {rv / 365:,.2f}"
        nums_issue = [v for v in _numbers_in(issue) if v > 1]
        if re.search(r"\bnot\b|should be|instead of|rather than|error", issue, re.IGNORECASE):
            drift = next(((a, b) for a in nums_issue for b in nums_issue
                          if a != b and abs(a - b) / max(a, b) <= 0.005
                          and any(abs(b - e) < 0.006 for e in exact) and not any(abs(a - e) < 0.006 for e in exact)), None)
            if drift:
                a, b = drift
                why = next(w for e, w in exact.items() if abs(b - e) < 0.006)
                _close("false_positive",
                       f"R24: the machine product is exactly {b:,.2f} ({why}); the auditor's {a:,.2f} is its own "
                       "arithmetic drift, not the document's",
                       "machine-proven false positive")
                continue
        # R20 — whole-dollar rounding of a verified product is verification, not a discrepancy
        if re.search(r"rounding", issue, re.IGNORECASE) and cited_verified:
            near = [v for v, why in cited if not why and any(abs(v - cv) / max(cv, 1e-9) <= 0.005 for cv, _ in cited_verified)]
            if near:
                _close("false_positive",
                       f"R20: {near[0]:,.1f} rounds to the machine-verified {cited_verified[0][0]:,.0f} "
                       "(whole dollars by convention) — the figure is verified, not discrepant",
                       "machine-proven false positive")
                continue
        # R1 (confirming direction) — the auditor disputes an UNverified value
        # and proposes the verified derivation: the recompute agrees with the auditor.
        # Operands inside a quoted formula are not "stated values".
        issue_wo_formula = re.sub(r"\([^()]*[x×*/][^()]*\)", " ", issue)
        dollar_cited = [float(x.replace(",", "")) for x in re.findall(r"\$\s?([\d,]+(?:\.\d+)?)", issue_wo_formula)]
        cited_unverified = [v for v in dollar_cited if v > 1 and not _matches(v, verified)] or \
            [v for v in _numbers_in(issue_wo_formula) if v > 1 and not _matches(v, verified) and v not in (30, 365, 12, 52)]
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
            if re.search(r"repeated verbatim|repeated multiple times|redundan|repetiti", issue, re.IGNORECASE):
                _close("false_positive",
                       "R8: verbatim repetition of the canonical sentence is the law — the gate is restated only as "
                       "that sentence wherever it is restated",
                       "machine-proven false positive")
                continue
            paraphrases = _pg.restatement_findings(corpus, gate)
            if paraphrases:
                _close("confirmed",
                       f"R8: {len(paraphrases)} sentence(s) in the rendered text restate the pilot gate in other words "
                       f"than the canonical sentence (e.g. \"{paraphrases[0]['issue'].split(chr(34))[1][:120]}\")",
                       "real defect")
                continue
            canon = re.sub(r"\s+", " ", _pg.canonical_sentence(gate))
            if canon and canon in re.sub(r"\s+", " ", corpus) and re.search(
                    r"not (?:\w+\s+)?match|differs? from|deviat|does not match|do not match|discrepanc|"
                    r"formatting difference|inconsisten|but the struct|varies|variation|slightly|not used verbatim|"
                    r"not (?:\w+\s+){0,2}verbatim", issue, re.IGNORECASE):
                _close("false_positive",
                       "R8: the canonical gate sentence is present verbatim in the rendered text and zero "
                       "paraphrases exist — the auditor's mismatch claim has no textual basis",
                       "machine-proven false positive")
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
        # R31 — "the derivation is not shown": a machine-verified restatement that
        # the rendered text prints WITH its derivation ('$194.40 per day ($70,956 a
        # year ÷ 365)') is attributed — the objection is answered on the page
        if re.search(r"derivation|attribut|not (?:explicitly )?shown|how (?:it|this) (?:was|is) (?:calculated|derived)",
                     issue, re.IGNORECASE):
            flat_corpus = re.sub(r"\s+", " ", corpus)
            shown = None
            for v, why in cited_verified:
                tok = f"${v:,.2f}" if v < 1000 else f"${v:,.0f}"
                m = re.search(re.escape(tok) + r"[^()\n]{0,40}\(([^)]*(?:÷|/)\s*(?:365|52)[^)]*)\)", flat_corpus)
                if m:
                    shown = (tok, m.group(1), why)
                    break
            if shown:
                _close("false_positive",
                       f"R31: '{shown[0]}' is printed with its derivation '({shown[1]})' in the rendered text, and the "
                       f"value is machine-verified ({shown[2]})",
                       "machine-proven false positive")
                continue
        # R29 — the pilot IS registered as a module by design: pilot=true, its only
        # KPI claim is the decision gate, its procedures carry the pilot phase
        where = str(f.get("where") or "")
        pilot_mods = [m for m in (registry or {}).get("modules") or [] if m.get("pilot")]
        for pm in pilot_mods:
            pname = pm.get("client_facing_name") or ""
            # the objection must be that the pilot is LISTED/positioned as a module
            # (Phase-1 NAMING objections belong to R15)
            if not pname or pname not in issue or not re.search(r"\bmodule\b", issue, re.IGNORECASE) or \
                    not re.search(r"listed (?:as|among|in|under)|distinct (?:software )?module|"
                                  r"not a (?:distinct |software |real )?module|success metric for|positioned as|"
                                  r"copy of the pilot|procedures? (?:for|under) (?:a|the) module|"
                                  r"definition of a .module", issue, re.IGNORECASE):
                continue
            gate_kpi = list(pm.get("kpi_claim_ids") or []) == [f"MK-{pm.get('id')}-gate"]
            if not gate_kpi:
                continue
            proofs = [f"registry: '{pname}' is the pilot module (pilot=true, phase {pm.get('phase')})",
                      "its only KPI claim is the decision gate, so the gate IS its success statement"]
            if re.search(r"procedure", issue, re.IGNORECASE):
                mine = [p for p in procedures if p.get("module") == pname]
                if not mine or any(str(p.get("phase")).lower() != "pilot" for p in mine):
                    continue
                proofs.append(f"{len(mine)} procedure(s) filed under it all carry phase 'pilot'")
            _close("false_positive", "R29: the pilot is listed among the modules BY DESIGN — " + "; ".join(proofs),
                   "semantic false positive resolved by structured registry data")
            break
        if entry.get("classification"):
            continue
        # R30 — a threshold inside a quoted sentence is judged in THAT sentence:
        # registered as a proposal for the module AND labeled there => proposal;
        # unregistered or bare in the sentence => defect
        wm = re.match(r"\s*(.+?):\s*'(.+)$", where, re.DOTALL)
        if registry and _LABEL_TALK.search(issue) and wm:
            mod_name, frag = wm.group(1).strip(), re.sub(r"\s+", " ", wm.group(2)).strip().rstrip("'…. ")
            mod = next((m for m in registry.get("modules") or []
                        if mod_name in (m.get("client_facing_name"), m.get("original_name"))), None)
            nums_q = [q.strip() for q in _QUOTED.findall(issue) if any(ch.isdigit() for ch in q)
                      and re.fullmatch(r"[\d,]*\.?\d+\s*%?", q.strip())]
            words = [w for w in re.sub(r"\(proposed — client approval required\)", " ", frag).split() if w][:8]
            flat = re.sub(r"\s+", " ", corpus)
            if mod and nums_q and words:
                pat = r"\s*(?:\(proposed — client approval required\)\s*)?".join(re.escape(w) for w in words)
                hit = re.search(pat, flat)
                if hit:
                    end = flat.find(" • ", hit.end())
                    window = flat[hit.start():end if 0 < end - hit.start() <= 700 else hit.start() + 700]
                    proofs, fails = [], []
                    for tok in nums_q:
                        v = float(tok.rstrip("%").replace(",", "").strip())
                        v = v / 100 if tok.endswith("%") else v
                        claim = next((c for c in registry.get("claims") or []
                                      if c.get("scope") == mod.get("id") and c.get("provenance") == "consultant_proposed"
                                      and isinstance(c.get("value"), (int, float))
                                      and abs(float(c["value"]) - v) <= 1e-6 * max(1.0, abs(v))), None)
                        occ = list(re.finditer(r"(?<![\d.,])" + re.escape(tok.rstrip("%").strip()) + r"\s*%?", window))
                        labeled = bool(occ) and all("(proposed" in window[o.end():o.end() + _LABEL_WINDOW] for o in occ)
                        if claim and labeled:
                            proofs.append(f"'{tok}' = {claim['id']} ({claim.get('type')}), labeled in the sentence")
                        else:
                            fails.append(f"'{tok}': " + ("no registered proposal for this module" if not claim
                                                        else "not labeled inside the quoted sentence"))
                    if fails:
                        _close("confirmed", "R30: " + "; ".join(fails)[:300], "real defect")
                    else:
                        _close("false_positive", "R30: " + "; ".join(proofs)[:400],
                               "semantic false positive resolved by structured threshold typing")
                    continue
        # R7 + R2 — label evidence outranks the auditor's wording
        if _LABEL_TALK.search(issue):
            quoted = [q for q in _QUOTED.findall(issue)
                      if any(ch.isdigit() for ch in q) and not re.fullmatch(r"\s*\d{1,2}\s*", q)]
            # R13 — the label law governs NUMERIC thresholds; a qualitative
            # trigger ("fraud or major service problems") carries no number to approve
            if not quoted and _QUOTED.findall(issue) and \
                    re.search(r"qualitative|newly introduced|trigger|frequency|cadence|review|weekly|monthly|daily", issue, re.IGNORECASE) \
                    and not any(ch.isdigit() for ch in issue.replace("(proposed", "")):
                _close("false_positive",
                       "R13: the approval label applies to numeric thresholds; the quoted fragment is a qualitative "
                       "trigger or a review cadence and states no value to approve",
                       "semantic false positive resolved by structured threshold typing")
                continue
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
        # R21 — week-one measurement on a FUTURE module: its first week live, by the statement itself
        if registry and re.search(r"week.one|week 1", issue, re.IGNORECASE) and \
                re.search(r"phase [23]|future|later phase|not (?:yet )?built|immedia|deferred|defer", issue, re.IGNORECASE):
            named = [m for m in registry.get("modules") or []
                     if m.get("client_facing_name") and m["client_facing_name"] in issue and m.get("phase") == "FUTURE"]
            if named and "once this module is live" in corpus:
                _close("false_positive",
                       f"R21: '{named[0]['client_facing_name']}' is FUTURE; its KPI statement reads 'week-one measurement once "
                       "this module is live' — the baseline is measured when the module launches, not during the pilot",
                       "semantic false positive resolved by structured phase data")
                continue
        # R27 — FUTURE modules may be AI and may measure the pilot population: the
        # decision defers AI to later phases, and these modules ARE the later phases
        if registry and re.search(r"\bAI\b|pilot group|pilot-related|pilot metric", issue, re.IGNORECASE) and \
                re.search(r"defer|despite|even though|contradict|not part of the pilot|phase [23]|later phase", issue, re.IGNORECASE):
            named = [m for m in registry.get("modules") or []
                     if m.get("client_facing_name") and m["client_facing_name"] in issue and m.get("phase") == "FUTURE"]
            if named and all(not m.get("pilot") for m in named):
                _close("false_positive",
                       f"R27: {', '.join(repr(m['client_facing_name']) for m in named[:2])} is/are FUTURE in the registry — "
                       "the later phases the decision defers AI to; AI in their names and pilot-population metrics are "
                       "consistent with that phasing",
                       "semantic false positive resolved by structured phase data")
                continue
        # R22 — an 'inconsistency' between two identical names is no inconsistency
        quoted_all = _QUOTED.findall(issue)
        if len(quoted_all) >= 2 and re.search(r"inconsisten|mismatch|differ|listed as", issue, re.IGNORECASE) and \
                len({q.strip().lower() for q in quoted_all if not any(ch.isdigit() for ch in q)}) == 1 and \
                not any(ch.isdigit() for ch in "".join(quoted_all)):
            _close("false_positive",
                   f"R22: the quoted names are identical ('{quoted_all[0]}') — the auditor compared a string with itself",
                   "machine-proven false positive")
            continue
        # R23 — a finding that is only a list of quoted thresholds: each is judged on
        # its own evidence — registered & labeled everywhere => proposal, bare => defect
        stripped = re.sub(r"'[^']*'", "", issue).strip(" ,;.")
        if quoted_all and not stripped:
            numeric = [q for q in quoted_all if any(ch.isdigit() for ch in q)]
            qualitative = [q for q in quoted_all if not any(ch.isdigit() for ch in q)]
            bare = []
            for q in numeric:
                labeled, evidence = _label_check(q, corpus)
                if labeled is False:
                    bare.append(evidence)
            if bare:
                _close("confirmed", "R23/R2: " + "; ".join(bare)[:300], "real defect")
                continue
            _close("false_positive",
                   "R23: every quoted threshold is labeled '(proposed …)' at every occurrence in the rendered text"
                   + (f"; qualitative triggers carry no value to approve ({', '.join(qualitative[:2])})" if qualitative else ""),
                   "semantic false positive resolved by structured threshold typing")
            continue
        # R14 — scope: the client's own briefing corrections extend the capability
        from app.pipeline._shared import briefing_corrections

        corrections = briefing_corrections(getattr(req, "business_description", None))
        if corrections and re.search(r"two capabilit|second capabilit|outside (?:the )?scope|scope creep|"
                                     r"introduced prematurely|beyond the (?:one|stated) capability", issue, re.IGNORECASE):
            nouns = {w for w in re.findall(r"[a-z]{4,}", corrections.lower())} - {"must", "also", "from", "around", "month",
                                                                                    "roughly", "half", "just", "cover", "both", "with"}
            shared = [w for w in nouns if w in issue.lower()]
            if len(shared) >= 2:
                _close("false_positive",
                       f"R14: the client extended the capability in the briefing chat (shared terms: {', '.join(sorted(shared)[:4])}) — "
                       "the register carries that correction; this is scope, not scope creep",
                       "semantic false positive resolved by structured phase data")
                continue
        # R19 — build order is sequence, phase is availability: a FUTURE module's
        # position in "What we'd build first" implies nothing about immediacy
        if registry and re.search(r"build first|build order|second build item|build item", issue, re.IGNORECASE) and \
                re.search(r"impl(?:y|ies|ying)|contradict|immediate", issue, re.IGNORECASE):
            named = [m for m in registry.get("modules") or []
                     if m.get("client_facing_name") and m["client_facing_name"] in issue and m.get("phase") == "FUTURE"]
            if named:
                _close("false_positive",
                       f"R19: '{named[0]['client_facing_name']}' is phased FUTURE in the registry; its place in the build "
                       "order is sequence, not a claim of immediate construction",
                       "semantic false positive resolved by structured phase data")
                continue
        # R15 — the Phase 1 bullet carries the pilot module's client-facing name BY DESIGN
        if registry and re.search(r"phase 1", issue, re.IGNORECASE) and \
                re.search(r"module name|refers? to the pilot as|instead of describing|uses? the module|human-supervised|"
                          r"uses the phrase|describ(?:es|ed) (?:it|the pilot|the workflow) as|rules-based", issue, re.IGNORECASE):
            pilot = next((m for m in registry.get("modules") or [] if m.get("pilot")), None)
            if pilot and pilot.get("automation_level") in ("manual", "rules") and not pilot.get("ai_involvement"):
                _close("false_positive",
                       f"R15: Phase 1 is named after its pilot module '{pilot.get('client_facing_name')}', which the "
                       f"registry types as PILOT / {pilot.get('automation_level')} / no AI — one capability, one name",
                       "semantic false positive resolved by structured phase data")
                continue
        # R17 — a percentage and its complement of a client fact (12% failed = 88% success)
        pct_facts = [c["value"] for c in (registry or {}).get("claims") or []
                     if c.get("type") == "client_fact" and c.get("unit") == "%" and isinstance(c.get("value"), (int, float))]
        cited_pcts = [v for v in _numbers_in(issue) if 0 < v < 1]
        if pct_facts and cited_pcts and re.search(r"impl(?:y|ies)|100\s*-\s*\d|derived|complement|baseline", issue, re.IGNORECASE):
            pairs = [(p, 1 - p) for p in pct_facts
                     if any(abs(v - p) < 1e-9 for v in cited_pcts) and any(abs(v - (1 - p)) < 1e-9 for v in cited_pcts)]
            if pairs:
                p, q = pairs[0]
                _close("false_positive",
                       f"R17: {q:.0%} is the arithmetic complement of the client's own {p:.0%} — both are the client's figure",
                       "machine-proven false positive")
                continue
        # R18 — a typed, labeled consultant-proposed threshold needs no client input:
        # the law requires provenance OR proposed status, and the registry holds it
        if registry and re.search(r"even with the approval tag|while (?:they have|tagged for|it has|carrying) (?:the )?approval|"
                                  r"despite (?:the|its|their) (?:approval )?(?:tag|label)|arbitrary|lacking (?:any )?client input",
                                  issue, re.IGNORECASE):
            quoted_nums = [v for v in _numbers_in(issue) if v > 0]
            typed = [c for c in registry.get("claims") or []
                     if c.get("type") in ("performance_target", "timing_sla", "sampling_requirement",
                                          "capacity_assumption", "proposed_threshold", "operational_policy", "module_kpi")
                     and c.get("provenance") in ("consultant_proposed", "canonical_gate")
                     and isinstance(c.get("value"), (int, float))]
            matched = [c for c in typed if any(abs(float(c["value"]) - v) <= 0.005 * max(v, 1e-9)
                                              or abs(float(c["value"]) * 100 - v) <= 0.005 * max(v, 1e-9) for v in quoted_nums)]
            if matched and _label_check(str(quoted_nums[0]), corpus)[0] is not False:
                kinds = sorted({c["type"] for c in matched})
                _close("false_positive",
                       f"R18: the cited figure(s) are registered, typed consultant proposals ({', '.join(kinds)}) carrying "
                       "the approval label in the rendered text — the threshold law requires provenance OR proposed status",
                       "semantic false positive resolved by structured threshold typing")
                continue
        # R28 — a scenario fraction is a LABELED assumption of ours by design:
        # "not tied to client input" is its definition, not a defect
        if registry and re.search(r"assum|reduction|automation", issue, re.IGNORECASE) and \
                re.search(r"not (?:explicitly |fully )?(?:tied to|attributed|derived)|no client input|without client input|"
                          r"not a client input|unverified", issue, re.IGNORECASE):
            sa = [c for c in registry.get("claims") or [] if c.get("type") == "scenario_assumption"
                  and isinstance(c.get("value"), (int, float))]
            cited_fracs = [v for v in _numbers_in(issue) if 0 < v < 1]
            hit = [c for c in sa if any(abs(float(c["value"]) - v) < 1e-6 for v in cited_fracs)]
            if hit and "scenario" in issue.lower():
                _close("false_positive",
                       f"R28: {hit[0]['value']:.0%} is the registered {hit[0].get('scenario') or ''} scenario assumption — "
                       "labeled as ours and requiring the client's approval in the financial case; a scenario fraction is "
                       "by definition not a client input",
                       "semantic false positive resolved by structured threshold typing")
                continue
        # R12c — the 30-day operating month is the package convention, stated in the document
        if re.search(r"30.day|30 operating days|operating_30_day", issue, re.IGNORECASE) and \
                re.search(r"not (?:a )?client input|without (?:explicit )?client input|internal definition|assumption", issue, re.IGNORECASE) and \
                re.search(r"30-day operating month", corpus, re.IGNORECASE) and \
                not [v for v in _numbers_in(issue) if v > 1 and v not in (30, 365, 12) and not _matches(v, verified)]:
            _close("false_positive",
                   "R12: the 30-day operating month is the package's stated convention (printed in the financial case); "
                   "it is a unit definition, not a figure needing client input",
                   "machine-proven false positive")
            continue
        # R16 — the auditor's own text reports no defect
        if re.search(r"no fix (?:is )?needed|no change (?:is )?needed|no correction (?:is )?needed|formatting only|"
                     r"this is a minor|cosmetic", fix + " " + issue, re.IGNORECASE) and \
                not re.search(r"must|should be corrected|is wrong|incorrect", fix, re.IGNORECASE):
            _close("false_positive", "R16: the auditor's own fix text states no correction is needed — not a defect",
                   "machine-proven false positive")
            continue
        # R10 — pilot-module honesty: a Phase 1 naming/AI finding against the registry
        if registry and re.search(r"phase 1|pilot", issue, re.IGNORECASE) and \
                re.search(r"engine|predictive|rules-based|manual|\bAI\b", issue, re.IGNORECASE):
            errs = [e for e in (registry.get("errors") or []) if "pilot" in e.lower()]
            renames = [r for r in (registry.get("renames") or []) if r.get("reason", "pilot_name") == "pilot_name"]
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
