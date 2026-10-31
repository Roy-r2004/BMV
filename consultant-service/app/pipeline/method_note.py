"""The method statement on the Evidence & method page: how the work was done,
which checks ran, and what was not verified.

It is a record, read from the run's own records with no model call. It claims
only what those records show: a check is listed because the quality bench
recorded it as passed, the integrity layer is listed because its report is
current for this content, and what was not verified is the release gate's own
list of open reasons. When nothing is outstanding that list is empty, and the
page says nothing about it.
"""

import json

from app.pipeline import integrity

HOW = ("Build My Version's analysis system produced this engagement from the facts you gave us "
       "and the files you sent.")
INTEGRITY_RAN = "The integrity layer ran on this content."


def _passed_checks(raw) -> list[str]:
    """The label of every check the quality bench recorded as passed, in the
    order it recorded them and once each. A report that cannot be read, or an
    entry that is not a labelled pass, claims nothing."""
    try:
        report = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return []
    checks = report.get("checks") if isinstance(report, dict) else None
    labels: list[str] = []
    for check in checks if isinstance(checks, list) else []:
        if not isinstance(check, dict) or check.get("passed") is not True:
            continue
        label = check.get("label")
        if isinstance(label, str) and label.strip() and label.strip() not in labels:
            labels.append(label.strip())
    return labels


def _integrity_ran(req) -> bool:
    try:
        return integrity.current_report(req) is not None
    except Exception:
        # a report that cannot be checked against the content is not a claim
        return False


def method_note(req, release: dict) -> dict:
    """{"how", "checks_ran", "not_verified"} for one engagement. `release` is
    `export_pdf.release_status(req)`; its reasons are copied, never reworded."""
    checks_ran = _passed_checks(getattr(req, "qa_report_json", None))
    if _integrity_ran(req):
        checks_ran.append(INTEGRITY_RAN)
    reasons = (release or {}).get("reasons")
    not_verified = [r for r in reasons if isinstance(r, str) and r.strip()] if isinstance(reasons, list) else []
    return {"how": HOW, "checks_ran": checks_ran, "not_verified": not_verified}
