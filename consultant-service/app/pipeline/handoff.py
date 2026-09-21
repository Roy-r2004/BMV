"""The diagnosis, handed to the build.

The build half of the pipeline was written to blueprint software from a
recommendation: a paragraph of summary, a list of AI employees, a list of
features. It never saw WHY. So a client whose diagnosis said "you are at your
ceiling, the constraint is price" and who then chose to build anyway got
documents written from their original request and a summary that argued
against it — nothing made the documents agree with the finding, and nothing
stopped them promising a return that depended on a cause the diagnosis had
already ruled out.

This module words the diagnosis as constraints and appends it to the
engagement register — the one paragraph every content prompt already carries —
so the blueprint, the technical plan, the playbook and the expert review all
read it, without a dozen prompts each learning a new variable.

It is a FINDING handed forward, not a preference: the cause, what actually
fixes it, the figures it rests on, what was ruled out, and what is still
unverified. When the client builds software the diagnosis did not recommend,
it also says how to write about that honestly.
"""
import json

# What each kind of intervention means, in words the documents can reuse.
_PLAIN = {
    "software": "software",
    "process": "a change to how the work flows",
    "pricing": "a change to what they charge",
    "staffing": "people and hours, not software",
    "none": "nothing that can be built",
}

_VERDICT_PLAIN = {
    "supported": "supported by their own figures",
    "refuted": "ruled out by their own figures",
    "untestable": "not verifiable from what they gave us",
}

MAX_EVIDENCE = 8
MAX_LIST = 5


def _load(text):
    try:
        value = json.loads(text) if text else None
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _short(text, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _evidence_lines(diag: dict | None, decision: dict, leading: dict | None) -> list[str]:
    """The client's own figures the diagnosis rests on, cited by id.

    Only ids that exist are kept: a model that cites CF-99 must not be able to
    hand the build a figure nobody gave.
    """
    if not diag:
        return []
    claims = {c.get("id"): c for c in diag.get("evidence") or [] if isinstance(c, dict)}
    wanted = list(decision.get("rests_on") or [])
    wanted += list(((leading or {}).get("test") or {}).get("cites") or [])
    for h in diag.get("hypotheses") or []:
        wanted += list((h.get("test") or {}).get("cites") or [])
    lines, seen, same_figure = [], set(), set()
    for cid in wanted:
        c = claims.get(cid)
        if not c or cid in seen:
            continue
        seen.add(cid)
        # One line per FIGURE, not per mention. The client's "8 hours a week"
        # is registered once for every place they wrote it — the opening
        # paragraph, the outcome they described — and listing all three would
        # hand the build what reads as three separate facts.
        figure = (c.get("value"), c.get("unit"), c.get("time_basis"))
        if figure in same_figure:
            continue
        same_figure.add(figure)
        basis = f" per {c['time_basis']}" if c.get("time_basis") not in (None, "", "n/a") else ""
        lines.append(f"  {cid}: {c.get('value')} {c.get('unit') or ''}{basis} — {_short(c.get('text'), 90)}".rstrip())
        if len(lines) >= MAX_EVIDENCE:
            break
    return lines


def for_build(req) -> str:
    """The block appended to the register for every build stage. Empty when
    there is no diagnosis to hand over — the register is then exactly what it
    was before this module existed."""
    decision = _load(getattr(req, "consulting_recommendations_json", None)) or {}
    diag = _load(getattr(req, "diagnosis_json", None))
    hyps = (diag or {}).get("hypotheses") or []
    leading = next((h for h in hyps if h.get("id") == (diag or {}).get("leading")), None)

    cause = decision.get("central_problem") or (leading or {}).get("statement")
    kind = decision.get("intervention_kind")
    if not cause and not kind:
        return ""

    out = [
        "THE DIAGNOSIS — a finding established before this engagement was scoped, from the "
        "client's own figures. Every document you write must be consistent with it.",
    ]
    if cause:
        out.append(f"The cause of the problem: {_short(cause, 320)}")
    if kind:
        out.append(f"What actually fixes it: {_PLAIN.get(kind, kind)}.")
    if decision.get("why_not_the_others"):
        out.append(f"Why the other kinds of fix do not: {_short(decision['why_not_the_others'], 360)}")

    evidence = _evidence_lines(diag, decision, leading)
    if evidence:
        out.append("It rests on these figures the client gave (cite them by id, never restate a different number):")
        out += evidence

    # The client's own explanation, and whatever else was set aside. A build
    # must not justify a module by a cause the diagnosis already rejected.
    ruled_out = [h for h in hyps if (h.get("test") or {}).get("verdict") == "refuted"]
    if ruled_out:
        out.append("Explanations tested and RULED OUT — never build for these and never cite them as a benefit:")
        out += [f"  - {_short(h.get('statement'), 180)}" for h in ruled_out[:MAX_LIST]]
    theirs = next((h for h in hyps if h.get("from_owner")), None)
    if theirs and theirs not in ruled_out:
        verdict = (theirs.get("test") or {}).get("verdict")
        out.append(f"The client's own explanation ({_short(theirs.get('statement'), 160)}) was "
                   f"{_VERDICT_PLAIN.get(verdict, 'not tested')}.")

    unverified = list(dict.fromkeys(
        [str(u) for u in decision.get("unverified") or []] + [str(w) for w in (diag or {}).get("weaknesses") or []]))
    if unverified:
        out.append("Still unverified — say so where it matters and never assume it away:")
        out += [f"  - {_short(u, 200)}" for u in unverified[:MAX_LIST]]
        # The rule that turns "unverified" from a caveat into a constraint. A
        # first real build listed price sensitivity as unverified and then put
        # "$8,000 a year" on the effect of a 25% price rise — a guess wearing a
        # number, which the number auditor flagged as unsupported.
        out.append("A figure that depends on any of these is NOT YET CALCULABLE. Say so, name what would settle it "
                   "(a pilot, a record, a number only the client can give), and do not give it a dollar figure.")
    if decision.get("confidence"):
        out.append(f"Confidence in the diagnosis: {decision['confidence']}.")

    if kind and kind != "software":
        out.append(
            "IMPORTANT: the client read this diagnosis and chose to build software ANYWAY. Software does not "
            "remove the diagnosed cause, so:\n"
            "  1. Where the document states the decision or recommendation, its FIRST sentence must say what the "
            "diagnosis found and what actually fixes it, before any mention of software — in the shape \"The "
            "constraint is <the cause>; what fixes it is <the fix>, and that does not need software to begin.\" "
            "Never open with \"you need an application\". Only then say what the software adds to that fix: it "
            "carries it out, keeps it in place, or removes the admin it creates.\n"
            "  2. Justify every module by what it does for the diagnosed cause or for the change it requires — "
            "carrying out a price change, using capacity that has been freed, removing hours of owner admin. "
            "Never justify one by \"more customers\", \"more demand\" or extra revenue that the diagnosis showed "
            "the business cannot serve.\n"
            "  3. Any benefit or payback figure must come from the client's own figures above, with its "
            "arithmetic shown, and must not depend on an explanation that was ruled out or on anything listed "
            "as unverified. If the honest benefit is small, say it is small.\n"
            "  4. Do not invent a justification for the build that the diagnosis does not support.")
    else:
        out.append(
            "This engagement builds software for the diagnosed cause. Justify every module by its effect on THAT "
            "cause, and never by an explanation the diagnosis ruled out.")
    return "\n".join(out)
