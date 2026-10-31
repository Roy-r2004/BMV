"""The method statement on the Evidence & method page: how the work was done,
which checks ran, and what was not verified.

It is a record, read from the run's own records with no model call. It claims
only what those records show: a check is listed because the quality bench
recorded it as passed, a consistency check is listed because its report is
current for this content, and what was not verified comes from the release
gate's own list of open reasons.

The gate writes those reasons for the team: they carry counts, internal names
and the names of our own checks. The client reads none of that. Each reason is
restated by its KIND in one plain sentence (`plain_reason`), and a reason of a
kind not listed here becomes the generic sentence, never the raw string. When
nothing is outstanding the list is empty, and the page says nothing about it.
"""

import json
import re

from app.pipeline import integrity

HOW = ("Build My Version's analysis system produced this engagement from the facts you gave us "
       "and the files you sent.")
INTEGRITY_RAN = "A consistency check ran across the whole document."
GENERIC_REASON = "One check did not pass."

#: (what a reason from `export_pdf.release_status` / `registry_reasons` starts
#: with, the client's sentence for it), one row per kind of reason the gate can
#: give. Never a count, a name of ours or an id.
_KINDS: tuple[tuple[re.Pattern, str], ...] = tuple((re.compile(pattern), sentence) for pattern, sentence in (
    (r"the run did not complete$",
     "This engagement had not finished being written."),
    (r"no documents were produced$",
     "No documents had been written for this engagement."),
    (r"the quality bench never audited this run$",
     "The quality review did not run on this engagement."),
    (r"\d+ open high finding\(s\) on the quality bench$",
     "The quality review found problems that are still open."),
    (r"client-unsafe artifacts: ",
     "Some text still contains placeholders or unfinished wording."),
    (r"\d+ paraphrased pilot-gate restatement",
     "The pilot's go or no-go rule is worded differently in different places."),
    (r"\d+ KPI/acceptance number",
     "Some figures in the plans could not be tied back to a figure you gave us."),
    (r"internal identifiers in client-facing text",
     "Some wording still uses working labels instead of the plain names of your system's parts."),
    (r"\d+ pilot-design restatement",
     "The pilot is described with a design other than the one it is meant to use."),
    (r"\d+ sentence\(s\) gate financial detail",
     "Some wording lets a phone number alone unlock financial detail."),
    (r"\d+ API path",
     "Some technical addresses are written with spaces in them."),
    (r"\d+ pilot specification\(s\)/procedure\(s\) depend",
     "The pilot is specified to depend on other parts of the system that it should stand apart from."),
    (r"\d+ contradiction\(s\) inside the pilot specification",
     "The pilot's procedures and its part of the system do not fully agree."),
    (r"\d+ sentence\(s\) state a pilot attempt count",
     "The number of attempts stated for the pilot differs between places."),
    (r"\d+ list ordinal",
     "Some numbers that only put a list in order are written as if they were limits."),
    (r"\d+ unlabeled operating time",
     "Some operating times in the procedures are not marked as proposals."),
    (r"\d+ sentence\(s\) send a customer into the internal pilot queue",
     "Some wording points a customer to a work queue meant for your staff."),
    (r"\d+ sentence\(s\) narrow the pilot population",
     "Some wording narrows the pilot to fewer customers than the pilot rule covers."),
    (r"\d+ monthly-identity violation",
     "Some monthly figures do not agree with the yearly figures they come from."),
    (r"\d+ invented operational policy statement",
     "Some wording states an operating policy that you did not give us."),
    (r"integrity layer has not run on the current content$",
     "The consistency check has not run on the current version of this engagement."),
    (r"integrity layer: \d+ finding",
     "The consistency check found inconsistencies that are still open."),
))


def plain_reason(reason: str) -> str:
    """One release-gate reason as the sentence the client reads. Matched by the
    kind of reason; anything that matches no kind is `GENERIC_REASON`, so a new
    or reworded reason can never put its raw text, a count or an id on a page."""
    text = reason.strip() if isinstance(reason, str) else ""
    for pattern, sentence in _KINDS:
        if pattern.match(text):
            return sentence
    return GENERIC_REASON


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
    `export_pdf.release_status(req)`; each of its reasons is restated in plain
    words (`plain_reason`), once each, in the order the gate gave them."""
    checks_ran = _passed_checks(getattr(req, "qa_report_json", None))
    if _integrity_ran(req):
        checks_ran.append(INTEGRITY_RAN)
    reasons = (release or {}).get("reasons")
    not_verified: list[str] = []
    for reason in reasons if isinstance(reasons, list) else []:
        if isinstance(reason, str) and reason.strip():
            sentence = plain_reason(reason)
            if sentence not in not_verified:
                not_verified.append(sentence)
    return {"how": HOW, "checks_ran": checks_ran, "not_verified": not_verified}
