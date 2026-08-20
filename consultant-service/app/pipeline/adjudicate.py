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
   bare.

R3 DOCUMENT DATE — a finding that flags a document/generation date as a
   threshold is a false positive: dates of record are not SLAs.

Everything else stays exactly as the bench left it — adjudication proves
false positives with evidence; it never waves through real defects.
"""

import json
import re

from app.models import Request

_NUM_RE = re.compile(r"\d[\d,]*\.?\d*\s*%?")
_LABEL_WINDOW = 130
_QUOTED = re.compile(r"'([^']{4,90})'")
_DOC_DATE = re.compile(
    r"(generated|prepared exclusively|reviewed and released on)[^.]{0,60}"
    r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}",
    re.IGNORECASE,
)


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


def _verified_values(fm: dict) -> dict[float, str]:
    """value -> evidence, for every machine-verified financial claim plus
    its standard derivations (monthly = /12, 30-day monthly = /365*30)."""
    out: dict[float, str] = {}

    def _add(v: float, why: str) -> None:
        if v:
            out[round(v, 2)] = why

    for line in (fm.get("lines") or []) if isinstance(fm, dict) else []:
        if not (isinstance(line, dict) and line.get("arithmetic_verified")):
            continue
        vals = _numbers_in(str(line.get("annual") or ""))
        if not vals:
            continue
        annual = vals[0]
        arith = str(line.get("arithmetic") or "")
        _add(annual, f"deterministic recompute of '{arith}' = {annual:,.0f}")
        _add(annual / 12, f"{annual:,.0f}/year / 12 = {annual / 12:,.2f}/month")
        _add(annual / 365 * 30, f"{annual:,.0f}/year / 365 x 30 = {annual / 365 * 30:,.2f}/30-day month")
    for sc in (fm.get("scenarios") or []) if isinstance(fm, dict) else []:
        if not (isinstance(sc, dict) and sc.get("impact_verified")):
            continue
        vals = [v for v in _numbers_in(str(sc.get("impact") or "")) if v > 1]
        if not vals:
            continue
        impact = vals[0]
        _add(impact, f"scenario '{sc.get('name')}' impact verified: {impact:,.0f}")
        _add(impact / 12, f"verified scenario impact {impact:,.0f} / 12 = {impact / 12:,.2f}/month")
    return out


def _matches(value: float, verified: dict[float, str]) -> str | None:
    for v, why in verified.items():
        if v and abs(v - value) / max(abs(v), 1e-9) <= 0.005:
            return why
    return None


def _label_check(fragment: str, corpus: str) -> tuple[bool | None, str]:
    """(all labeled?, evidence). None when the fragment isn't found."""
    nums = [m.group(0) for m in _NUM_RE.finditer(fragment) if any(c.isdigit() for c in m.group(0))]
    probe = nums[0].strip() if nums else fragment[:40]
    hits = [m.start() for m in re.finditer(re.escape(probe), corpus)]
    if not hits:
        return None, f"'{probe}' not found in rendered text"
    bare = sum(1 for h in hits if "(proposed" not in corpus[h:h + _LABEL_WINDOW])
    if bare:
        return False, f"'{probe}': {bare} of {len(hits)} occurrence(s) carry no approval label"
    return True, f"'{probe}': all {len(hits)} occurrence(s) labeled '(proposed …)' in the rendered text"


def adjudicate(req: Request, texts: dict[str, str] | None = None) -> dict:
    """Adjudicate the run's open high findings in place (persist by
    committing req's session afterwards). Returns the ledger."""
    qa = json.loads(req.qa_report_json) if req.qa_report_json else {}
    findings = qa.get("findings") or []
    bc = json.loads(req.business_case_json) if req.business_case_json else {}
    fm = (bc.get("financial_model") or {}) if isinstance(bc, dict) else {}
    verified = _verified_values(fm)
    corpus = "\n".join((texts or {}).values()) or "\n".join(
        str(x or "") for x in (req.mvp_blueprint, req.technical_plan))

    ledger = []
    for i, f in enumerate(findings, 1):
        entry = {"id": f"F{i:02d}", "where": f.get("where"), "issue": f.get("issue"),
                 "severity": f.get("severity"), "source": f.get("source")}
        if f.get("severity") != "high" or f.get("repaired"):
            entry["classification"] = "closed (repaired)" if f.get("repaired") else "low"
            ledger.append(entry)
            continue

        issue, fix = str(f.get("issue") or ""), str(f.get("fix") or "")
        # R1 — arithmetic: disputes a verified value, proposes an unverified one
        cited = [(v, _matches(v, verified)) for v in _numbers_in(issue) if v > 1]
        cited_verified = [(v, why) for v, why in cited if why]
        fix_nums = [v for v in _numbers_in(fix) if v > 1]
        fix_all_unverified = fix_nums and all(not _matches(v, verified) for v in fix_nums)
        if cited_verified and fix_all_unverified:
            why = cited_verified[0][1]
            f["adjudication"] = "false_positive"
            f["machine_evidence"] = f"R1: the disputed value is machine-verified ({why}); the auditor's replacement is not"
            entry.update(classification="false positive", evidence=f["machine_evidence"])
            ledger.append(entry)
            continue
        # R3 — a document date is not a threshold
        if ("threshold" in issue.lower() or "sla" in issue.lower()) and _DOC_DATE.search(issue):
            f["adjudication"] = "false_positive"
            f["machine_evidence"] = "R3: the flagged value is a document date of record, not an operational threshold"
            entry.update(classification="false positive", evidence=f["machine_evidence"])
            ledger.append(entry)
            continue
        # R2 — label presence in the rendered text
        if "(proposed" in issue or "invented percentage" in issue.lower() or "invented threshold" in issue.lower():
            quoted = _QUOTED.findall(issue)
            if quoted:
                labeled, evidence = _label_check(quoted[0], corpus)
                if labeled is True:
                    f["adjudication"] = "false_positive"
                    f["machine_evidence"] = f"R2: {evidence}"
                    entry.update(classification="false positive", evidence=f["machine_evidence"])
                    ledger.append(entry)
                    continue
                if labeled is False:
                    f["adjudication"] = "confirmed"
                    f["machine_evidence"] = f"R2: {evidence}"
                    entry.update(classification="real defect", evidence=f["machine_evidence"])
                    ledger.append(entry)
                    continue
        f["adjudication"] = "confirmed"
        f.setdefault("machine_evidence", "no deterministic rule proves this false — stays open")
        entry.update(classification="real defect", evidence=f["machine_evidence"])
        ledger.append(entry)

    req.qa_report_json = json.dumps(qa)
    open_real = sum(1 for e in ledger if e.get("classification") == "real defect")
    fps = sum(1 for e in ledger if e.get("classification") == "false positive")
    return {"ledger": ledger, "open_real": open_real, "false_positives": fps}
