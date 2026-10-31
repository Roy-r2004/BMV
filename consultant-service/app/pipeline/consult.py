"""The diagnosis, as text the recommendation prompt can use.

`consult()` — the old stage 2 — is gone: `decide` replaced it, and its fallback
answered every business with the same front desk and analyst. What remains is
the one helper `decide` still imports.
"""

import json

from app.models import Request

#: What a test that crashed on our side is called wherever the diagnosis is put
#: into words for a model. Never "untestable": that is a verdict, the finding
#: that their figures could not settle it.
NOT_TESTED = "not tested: the test could not be run on our side"


def _verdict_in_words(test: dict) -> str:
    if test.get("not_tested"):
        return NOT_TESTED
    return test.get("verdict", "untested")


def _format_diagnosis(req: Request) -> str:
    """The diagnosis as the lines the recommendation has to answer.

    Empty string when there is none, which the template reads as "no
    diagnosis" rather than "a diagnosis that found nothing" — the second
    would have the model write around a conclusion that was never reached.
    """
    if not req.diagnosis_json:
        return ""
    try:
        d = json.loads(req.diagnosis_json)
    except (TypeError, ValueError):
        return ""
    leading = next((h for h in d.get("hypotheses") or [] if h.get("id") == d.get("leading")), None)
    if not leading:
        return ""
    test = leading.get("test") or {}
    lines = [f"The cause: {leading['statement']}"]
    if test.get("not_tested"):
        # A crash on our side, not a finding about their figures: it must not
        # reach the recommendation as "untestable", which says the figures were
        # too thin to decide.
        lines.append(f"This was {NOT_TESTED}.")
    elif test.get("because"):
        verdict = test.get("verdict", "untestable")
        cites = ", ".join(test.get("cites") or [])
        lines.append(f"Tested against their numbers — {verdict}: {test['because']}"
                     + (f" (their figures: {cites})" if cites else ""))
    if test.get("would_need"):
        lines.append(f"Still unverified. To settle it we would need: {test['would_need']}")
    status = d.get("status")
    if status == "survived":
        lines.append("Two reviewers tried to kill this and could not.")
    elif status == "killed":
        lines.append("A reviewer landed a hit on this — treat it as the best available reading, not a settled fact.")
    else:
        lines.append("This went unchallenged — the review could not be run, so nothing has tested it but the evidence above.")
    for w in d.get("weaknesses") or []:
        lines.append(f"Weakness a reviewer left standing: {w}")
    rejected = [h for h in d.get("hypotheses") or [] if h.get("id") != d.get("leading")]
    if rejected:
        lines.append("Explanations considered and set aside: "
                     + "; ".join(f"{h['statement']} ({_verdict_in_words(h.get('test') or {})})"
                                 for h in rejected))
    return "\n".join(lines)
