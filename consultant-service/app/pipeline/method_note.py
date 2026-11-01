"""The method statement on the Evidence & method page: how the work was done,
which checks ran, and what was not verified.

It is a record, read from the run's own records with no model call. It claims
only what those records show: a check is listed because the quality bench
recorded it as passed, a consistency check is listed because its report is
current for this content, and what was not verified comes from the release
gate's own list of open reasons.

The quality bench's checks are labelled by the model that ran them, so a label
is never printed. A label the bench's two auditors are asked to write is told
as a fixed sentence of what was checked (`_CHECK_SENTENCES`); any other label
is left out.

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

#: The classes of unfinished or unsupported content the release gate names in
#: "client-unsafe artifacts: <classes>" (`export_pdf._GATE_ARTIFACTS`). They are
#: placeholders and leftover template marks, but also a figure invented or
#: mis-stated and a label repeated or left in our working form, so the sentence
#: for them says "wording or figures", which is true of every one. A class the
#: gate adds is not listed here and reads as the generic sentence until it is.
_ARTIFACT_CLASSES = (
    "template token", "literal Null", "unresolved placeholder", "duplicate approval label",
    "invented ROI figure", "currency sign on a count", "internal identifier in client-facing text",
    "unsubstituted gate token", "mixed monthly identity",
)
_ANY_ARTIFACT_CLASS = "(?:" + "|".join(re.escape(name) for name in _ARTIFACT_CLASSES) + ")"

#: (the whole of a reason from `export_pdf.release_status` / `registry_reasons`,
#: with its counts as `\d+` and its list of names as the one open part, the
#: client's sentence for it), one row per kind of reason the gate can give.
#: Matched in full, so a reason reworded anywhere is no longer the kind it was
#: and reads as the generic sentence. Never a count, a name of ours or an id.
_KINDS: tuple[tuple[re.Pattern, str], ...] = tuple((re.compile(pattern), sentence) for pattern, sentence in (
    (r"the run did not complete",
     "This engagement had not finished being written."),
    (r"no documents were produced",
     "No documents had been written for this engagement."),
    (r"the quality bench never audited this run",
     "The quality review did not run on this engagement."),
    (r"\d+ open high finding\(s\) on the quality bench",
     "The quality review found problems that are still open."),
    (rf"client-unsafe artifacts: {_ANY_ARTIFACT_CLASS}(?:, {_ANY_ARTIFACT_CLASS})*",
     "Some wording or figures in the documents are unfinished or need correcting."),
    (r"\d+ paraphrased pilot-gate restatement\(s\)",
     "The pilot's go or no-go rule is worded differently in different places."),
    (r"\d+ KPI/acceptance number\(s\) map to no registered claim",
     "Some figures in the plans could not be tied back to a figure you gave us."),
    (r"internal identifiers in client-facing text: .+",
     "Some wording still uses working labels instead of the plain names of your system's parts."),
    (r"\d+ pilot-design restatement\(s\) that are not the canonical randomized design",
     "The pilot is described with a design other than the one it is meant to use."),
    (r"\d+ sentence\(s\) gate financial detail on a phone-number match alone",
     "Some wording lets a phone number alone unlock financial detail."),
    (r"\d+ API path\(s\) rendered with spaces",
     "Some technical addresses are written with spaces in them."),
    (r"\d+ pilot specification\(s\)/procedure\(s\) depend on AI logic or another module",
     "The pilot is specified to depend on other parts of the system that it should stand apart from."),
    (r"\d+ contradiction\(s\) inside the pilot specification \(procedures and pilot module\)",
     "The pilot's procedures and its part of the system do not fully agree."),
    (r"\d+ sentence\(s\) state a pilot attempt count different from the SOP's",
     "The number of attempts stated for the pilot differs between places."),
    (r"\d+ list ordinal\(s\) labeled as thresholds",
     "Some numbers that only put a list in order are written as if they were limits."),
    (r"\d+ unlabeled operating time\(s\)/cadence\(s\) in the procedures",
     "Some operating times in the procedures are not marked as proposals."),
    (r"\d+ sentence\(s\) send a customer into the internal pilot queue",
     "Some wording points a customer to a work queue meant for your staff."),
    (r"\d+ sentence\(s\) narrow the pilot population below the gate's population",
     "Some wording narrows the pilot to fewer customers than the pilot rule covers."),
    (r"\d+ monthly-identity violation\(s\)",
     "Some monthly figures do not agree with the yearly figures they come from."),
    (r"\d+ invented operational policy statement\(s\)",
     "Some wording states an operating policy that you did not give us."),
    (r"integrity layer has not run on the current content",
     "The consistency check has not run on the current version of this engagement."),
    (r"integrity layer: \d+ finding\(s\)",
     "The consistency check found inconsistencies that are still open."),
    # the release law (`app.figures.law.page_reasons`): "<document>, <page or
    # slide>: the number(s) <numbers> match(es) none of ..."; the numbers are the open part
    (r"(?:Volume I|Volume II|Volume III|Volume IV|The deck), (?:page|slide) (?:\d+|not located): "
     r"the (?:number .+? matches|numbers .+? match) none of the client's figures, our workings, our estimates "
     r"or a cited reference",
     "Some figures in the documents are not yet tied to your figures, our workings, our estimates or a "
     "cited source."),
    (r"\d+ document\(s\) not yet checked against the figures since the last data change",
     "Some of the documents have not yet been checked against your figures."),
))


def plain_reason(reason: str) -> str:
    """One release-gate reason as the sentence the client reads. Matched in full
    against the kinds above; anything that matches none (a reason reworded or
    added, or one that is blank or not text) is `GENERIC_REASON`, so a reason can
    never put its raw text, a count or an id on a page."""
    text = reason.strip() if isinstance(reason, str) else ""
    for pattern, sentence in _KINDS:
        if pattern.fullmatch(text):
            return sentence
    return GENERIC_REASON


#: The checks the quality bench's two auditors are asked to record, by the label
#: each is told to write (prompts/qa_numbers.j2 and qa_completeness.j2; the
#: bench keeps the label as written, cut to 120 characters), and what the client
#: reads for each that passed. Keys are the label with its whitespace collapsed,
#: in lower case. A label not listed here is the model's own and is dropped.
_CHECK_SENTENCES: dict[str, str] = {
    "every figure traces to a client input":
        "Every figure was compared with the figures you gave us.",
    "attributions present on computed figures":
        "Every figure we calculated says where it came from.",
    "assumptions explicit and conservative":
        "Every assumption is stated as an assumption, and kept cautious.",
    "no internal contradictions between figures":
        "The figures were checked against each other, and none contradicts another.",
    "all canonical sections present":
        "Every section the documents should contain was present.",
    "documents consistent with the structured layers":
        "The documents agree with the plans they were written from.",
    "scope obeys the engagement register":
        "The documents keep to the scope agreed with you.",
}


def _check_key(label: str) -> str:
    return " ".join(label.split()).lower()


def _passed_checks(raw) -> list[str]:
    """The sentence for every known check the quality bench recorded as passed,
    in the order it recorded them and once each. A report that cannot be read,
    an entry that is not a pass, and a label we do not know claim nothing."""
    try:
        report = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return []
    checks = report.get("checks") if isinstance(report, dict) else None
    sentences: list[str] = []
    for check in checks if isinstance(checks, list) else []:
        if not isinstance(check, dict) or check.get("passed") is not True:
            continue
        label = check.get("label")
        sentence = _CHECK_SENTENCES.get(_check_key(label)) if isinstance(label, str) else None
        if sentence and sentence not in sentences:
            sentences.append(sentence)
    return sentences


def _integrity_ran(req) -> bool:
    try:
        return integrity.current_report(req) is not None
    except Exception:
        # a report that cannot be checked against the content is not a claim
        return False


def method_note(req, release: dict) -> dict:
    """{"how", "checks_ran", "not_verified"} for one engagement. `release` is
    `export_pdf.release_status(req)`; each of its reasons is restated in plain
    words (`plain_reason`), once each, in the order the gate gave them. A draft
    never lists nothing: if its reasons are missing or unusable the list is the
    generic sentence."""
    checks_ran = _passed_checks(getattr(req, "qa_report_json", None))
    if _integrity_ran(req):
        checks_ran.append(INTEGRITY_RAN)
    release = release if isinstance(release, dict) else {}
    reasons = release.get("reasons")
    not_verified: list[str] = []
    for reason in reasons if isinstance(reasons, list) else []:
        # a reason that is blank or not text still stands for something that did
        # not pass: it is told as the generic sentence, never left out
        sentence = plain_reason(reason)
        if sentence not in not_verified:
            not_verified.append(sentence)
    if not not_verified and release.get("status") == "draft":
        # a draft is a draft because something did not pass; the cover says so,
        # so this page may not list nothing
        not_verified.append(GENERIC_REASON)
    return {"how": HOW, "checks_ran": checks_ran, "not_verified": not_verified}
