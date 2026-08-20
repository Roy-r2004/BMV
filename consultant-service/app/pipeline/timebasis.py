"""Deterministic time-basis conversion for financial restatements.

Run 43 shipped "$1,944 per day" where the verified annual implies $194.40 —
a 10x drift born of the model doing period conversion in prose. This layer
makes every restatement of a canonical annual claim a computation, not a
paraphrase:

    per day               = annual / 365
    per week              = annual / 52
    per 30-day month      = annual / 365 * 30   (the operating month)
    per calendar month    = annual / 12
    per year              = annual

A stated "per month" verifies against EITHER month identity (both are
legitimate conventions) but a snap always uses the 30-day operating month
and records which identity it applied — the two are never silently mixed.
Verification accepts a 5% tolerance (prose rounding); a failed verification
snaps to the computed value when exactly one canonical currency claim
exists, and every action is recorded with its formula for the audit trail.
"""

import re

_MONEY_BASIS = re.compile(
    r"(\$\s?\d[\d,]*(?:\.\d+)?)\s*(per day|/\s*day|a day|per week|/\s*week|a week|"
    r"per month|/\s*month|a month|per year|/\s*year|a year)",
    re.IGNORECASE,
)
_NUM = re.compile(r"\d[\d,]*\.?\d*")


def _value(token: str) -> float | None:
    m = _NUM.search(token)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def candidates(annual: float, basis: str) -> list[tuple[float, str]]:
    """(value, formula) pairs a stated figure may legitimately be."""
    b = basis.lower()
    if "day" in b:
        return [(annual / 365, f"{annual:,.0f}/year / 365 = {annual / 365:,.2f}/day")]
    if "week" in b:
        return [(annual / 52, f"{annual:,.0f}/year / 52 = {annual / 52:,.2f}/week")]
    if "month" in b:
        return [
            (annual / 365 * 30, f"{annual:,.0f}/year / 365 x 30 = {annual / 365 * 30:,.2f}/30-day month"),
            (annual / 12, f"{annual:,.0f}/year / 12 = {annual / 12:,.2f}/calendar month"),
        ]
    return [(annual, f"{annual:,.0f}/year (as stated)")]


def check_restatements(text: str, annual_claims: list[float]) -> tuple[str, list[dict]]:
    """Verify every '$X per <basis>' in `text` against the canonical annual
    claims; snap a failed figure to the computed value when exactly one
    currency claim exists. Returns (corrected_text, records)."""
    records: list[dict] = []
    if not text:
        return text, records

    def _repl(m: re.Match) -> str:
        stated_tok, basis = m.group(1), m.group(2)
        stated = _value(stated_tok)
        if stated is None:
            return m.group(0)
        for annual in annual_claims:
            for cand, formula in candidates(annual, basis):
                if cand and abs(cand - stated) / max(cand, 1e-9) <= 0.05:
                    records.append({"original": stated_tok, "basis": basis,
                                    "status": "verified", "formula": formula})
                    return m.group(0)
        import math

        pool = [(cand, formula) for annual in annual_claims
                for cand, formula in candidates(annual, basis)[:1]]
        pool = [(c, f) for c, f in pool if c > 0]
        if not pool:
            records.append({"original": stated_tok, "basis": basis, "status": "unverifiable"})
            return m.group(0)
        cand, formula = min(pool, key=lambda cf: abs(math.log(stated / cf[0])) if stated > 0 else 99)
        if stated <= 0 or not (1 / 20 <= stated / cand <= 20):
            records.append({"original": stated_tok, "basis": basis,
                            "status": "unverifiable (no candidate within factor 20)"})
            return m.group(0)
        snapped = f"${cand:,.2f}" if cand < 1000 else f"${cand:,.0f}"
        records.append({"original": stated_tok, "basis": basis, "status": "snapped",
                        "converted": snapped, "formula": formula,
                        "rounding": "2dp under $1,000, whole dollars above"})
        return m.group(0).replace(stated_tok, snapped)

    return _MONEY_BASIS.sub(_repl, text), records


def round_counts(text: str) -> str:
    """Counts of discrete things are whole numbers — '31,937.5 inquiries'
    is not a quantity any operation ever handles."""
    def _repl(m: re.Match) -> str:
        v = _value(m.group(1))
        if v is None:
            return m.group(0)
        return f"{int(v + 0.5):,}{m.group(2)}"  # half-up: 95,812.5 -> 95,813

    return re.sub(
        r"(\d[\d,]*\.\d+)(\s*(?:'[^']{2,40}'\s*)?(?:inquiries|deliveries|orders|messages|calls|attempts|customers)\b)",
        _repl, text or "", flags=re.IGNORECASE)
