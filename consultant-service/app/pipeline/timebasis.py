"""Deterministic time-basis conversion for financial restatements.

Run 43 shipped "$1,944 per day" where the verified annual implies $194.40;
run 46 shipped "$5,913/month" in Volume I and "$5,832/month" in the business
case for the SAME claim and the SAME "x 30 days" formula — one package, two
monthly identities. This layer makes every restatement of a canonical
annual claim a computation on ONE package identity:

    per day                        = annual / 365
    per week                       = annual / 52
    per month (operating_30_day)   = annual / 365 x 30      <- the package identity
    per year                       = annual

The calendar-month identity (annual / 12) is NOT a valid restatement in this
package: a stated figure matching it is snapped, and a formula fragment
declaring it ("/ 12 months") is rewritten to the package formula. A sentence
that declares its own formula ("x 30 days") must print the value of THAT
formula. Verification accepts only round-trip rounding (0.5%, or the
candidate rounded to two significant figures) — "$1,977" against a
$1,924.52 truth is not rounding, it is a different number.
"""

import math
import re

MONTHLY_IDENTITY = "operating_30_day_month"
YEAR_DAYS = 365
MONTH_DAYS = 30

_MONEY_BASIS = re.compile(
    r"(\$\s?\d[\d,]*(?:\.\d+)?)\s*(per day|/\s*day|a day|daily|per week|/\s*week|a week|weekly|"
    r"per month|/\s*month|a month|monthly|per year|/\s*year|a year|annually|per annum|yearly)",
    re.IGNORECASE,
)
_NUM = re.compile(r"\d[\d,]*\.?\d*")
_DECL_30 = re.compile(r"(?:[x×*]\s*30\s*days?|30-day)", re.IGNORECASE)
_DECL_12 = re.compile(r"(?:/|÷|divided by)\s*12(?:\s*months?)?\b|calendar month", re.IGNORECASE)
_DIV12_FRAGMENT = re.compile(r"(\$\s?\d[\d,]*(?:\.\d+)?\s*(?:/\s*year|per year|a year|annually)?)\s*(?:/|÷)\s*12(\s*months?)?\b",
                             re.IGNORECASE)


def _value(token: str) -> float | None:
    m = _NUM.search(token)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def candidates(annual: float, basis: str) -> list[tuple[float, str]]:
    """(value, formula) for a stated figure on `basis` — exactly one per
    basis; the month is ALWAYS the package identity."""
    b = basis.lower()
    if "annu" in b or "year" in b:
        return [(annual, f"{annual:,.0f}/year (as stated)")]
    if "day" in b or "daily" in b:
        return [(annual / YEAR_DAYS, f"{annual:,.0f}/year / {YEAR_DAYS} = {annual / YEAR_DAYS:,.2f}/day")]
    if "week" in b:
        return [(annual / 52, f"{annual:,.0f}/year / 52 = {annual / 52:,.2f}/week")]
    if "month" in b:
        v = annual / YEAR_DAYS * MONTH_DAYS
        return [(v, f"{annual:,.0f}/year / {YEAR_DAYS} x {MONTH_DAYS} = {v:,.2f}/{MONTHLY_IDENTITY}")]
    return [(annual, f"{annual:,.0f}/year (as stated)")]


def _rounds_to(stated: float, cand: float) -> bool:
    """Round-trip tolerance: 0.5% relative, or the candidate rounded to two
    significant figures — prose rounding, never a different number."""
    if cand <= 0:
        return False
    if abs(cand - stated) / cand <= 0.005:
        return True
    mag = 10 ** (math.floor(math.log10(cand)) - 1)
    return abs(round(cand / mag) * mag - stated) < 1e-9


def _format(v: float) -> str:
    return f"${v:,.2f}" if v < 1000 else f"${v:,.0f}"


def check_restatements(text: str, annual_claims: list[float]) -> tuple[str, list[dict]]:
    """Verify every '$X per <basis>' against the canonical annual claims on
    the package identity; snap what fails; rewrite calendar-month formula
    fragments. Returns (corrected_text, records)."""
    records: list[dict] = []
    if not text:
        return text, records
    claims = [c for c in annual_claims if isinstance(c, (int, float)) and c > 0]

    # 1. a declared calendar-month formula on a known annual claim is rewritten
    def _div12(m: re.Match) -> str:
        v = _value(m.group(1))
        if v is None or not any(_rounds_to(v, c) for c in claims):
            return m.group(0)
        records.append({"original": m.group(0), "status": "identity_corrected",
                        "identity": MONTHLY_IDENTITY,
                        "formula": f"{v:,.0f}/year / {YEAR_DAYS} x {MONTH_DAYS}"})
        return f"{m.group(1).strip()} / {YEAR_DAYS} x {MONTH_DAYS} days"

    text = _DIV12_FRAGMENT.sub(_div12, text)

    def _repl(m: re.Match) -> str:
        stated_tok, basis = m.group(1), m.group(2)
        stated = _value(stated_tok)
        if stated is None:
            return m.group(0)
        window = text[max(0, m.start() - 160): m.end() + 160]
        declared = "calendar" if (_DECL_12.search(window) and not _DECL_30.search(window)) else (
            MONTHLY_IDENTITY if _DECL_30.search(window) else None)
        for annual in claims:
            for cand, formula in candidates(annual, basis):
                if cand and _rounds_to(stated, cand):
                    records.append({"original": stated_tok, "basis": basis, "status": "verified",
                                    "identity": MONTHLY_IDENTITY if "month" in basis.lower() else basis.lower(),
                                    "formula": formula})
                    return m.group(0)
        pool = [(cand, formula) for annual in claims for cand, formula in candidates(annual, basis)]
        pool = [(c, f) for c, f in pool if c > 0]
        if not pool:
            records.append({"original": stated_tok, "basis": basis, "status": "unverifiable"})
            return m.group(0)
        cand, formula = min(pool, key=lambda cf: abs(math.log(stated / cf[0])) if stated > 0 else 99)
        if stated <= 0 or not (1 / 20 <= stated / cand <= 20):
            records.append({"original": stated_tok, "basis": basis,
                            "status": "unverifiable (no candidate within factor 20)"})
            return m.group(0)
        snapped = _format(cand)
        rec = {"original": stated_tok, "basis": basis, "status": "snapped", "converted": snapped,
               "formula": formula, "identity": MONTHLY_IDENTITY if "month" in basis.lower() else basis.lower(),
               "rounding": "2dp under $1,000, whole dollars above"}
        if declared == "calendar":
            rec["note"] = "the sentence declared the calendar-month identity; the package identity governs"
        records.append(rec)
        return m.group(0).replace(stated_tok, snapped)

    return _MONEY_BASIS.sub(_repl, text), records


def identity_findings(texts: dict[str, str], annual_claims: list[float]) -> list[dict]:
    """Package-wide check: for each annual claim, every monthly restatement
    across all texts must be the SAME figure on the package identity; a
    calendar-month figure or a mixed-formula sentence is a high finding."""
    out = []
    claims = [c for c in annual_claims if isinstance(c, (int, float)) and c > 0]
    for label, text in (texts or {}).items():
        text = re.sub(r"\s+", " ", text or "")  # rendered PDF text wraps lines mid-sentence
        for m in _MONEY_BASIS.finditer(text or ""):
            basis = m.group(2).lower()
            if "month" not in basis:
                continue
            stated = _value(m.group(1))
            if stated is None:
                continue
            for annual in claims:
                cal = annual / 12
                op = annual / YEAR_DAYS * MONTH_DAYS
                if _rounds_to(stated, cal) and not _rounds_to(stated, op):
                    out.append({"severity": "high", "source": "structural", "where": f"{label}: monthly restatement",
                                "issue": (f"'{m.group(1)}{m.group(2)}' is the calendar-month identity of "
                                          f"{annual:,.0f}/year ({cal:,.2f}); this package's monthly identity "
                                          f"is the 30-day operating month ({op:,.2f})."),
                                "fix": f"restate as {_format(op)}/month ({annual:,.0f}/year / {YEAR_DAYS} x {MONTH_DAYS})"})
        for sentence in re.split(r"(?<=[.!?])\s+|\n", text or ""):
            if _DECL_30.search(sentence) and _DECL_12.search(sentence):
                out.append({"severity": "high", "source": "structural", "where": f"{label}: mixed monthly identity",
                            "issue": f"One sentence declares both 'x 30 days' and '/ 12': \"{sentence.strip()[:160]}\"",
                            "fix": "use the 30-day operating month only"})
    return out


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
