"""W3 — the text-truth gate.

The spec already contains the ground truth: the client's business name, the
product name, the navigation labels. A screenshot with the client's name
misspelled is unusable at any aesthetic score, so this gate is a hard
reject, not a deduction: brand-critical strings must be spelled exactly, or
the screen regenerates.

The comparison lives here, in code, rather than in a judge's prompt —
because judges are demonstrably unreliable about text in BOTH directions.
During W1 the aesthetic judge scored screens in the 8s while reporting
their text as correct, and the pairwise judge went further: it reported
"Hartwell Chamers" and "Northgate Roast Inteligence" as misspellings on
two specific screenshots. Both claims were false — the wordmarks are
spelled correctly in both images; they are simply wrapped across two
sidebar lines. A judge asked about text confabulates plausible errors and
misses real ones. Transcribing first (see
prompts/image_text_transcription.j2) and diffing second makes a difference
of one character arithmetic instead of opinion.

What is deliberately NOT enforced, each rule paid for by a false rejection
observed on real bake-off screenshots (2026-08-11):
- Case. A sidebar that renders "DASHBOARD" for the label "Dashboard" is a
  styling choice, not a misspelling; failing it would burn a regeneration
  on a correct screen.
- Whitespace and surrounding punctuation, for the same reason.
- Line breaks inside a string. Every model tested wrapped the wordmark
  across two sidebar lines ("SmileBright" / "Operations"), which a
  transcriber returns as two entries. Matching only per-entry called four
  correct screens misspelled.
- The business name's ABSENCE. Real product UIs show the product wordmark,
  not the client's company name — none of the models rendered "Hartwell &
  Grey LLP" anywhere, and they were right not to. The rule that matters is
  the roadmap's actual one: if the client's name appears, it must be
  spelled correctly. Absence is not a defect; a near-miss is.
- Any string the prompt never asked for. The gate checks exactly the
  slices prompt_builder sends (navigation[:8]) — holding a screen to text
  it was never given would be a permanent, unfixable failure.
"""

import difflib
import re

from app.ui_spec import UIDemoSpec

TEXT_TRUTH_VERSION = "text-truth-v1"

# How close a rendered string has to be to a required one before it counts
# as "this string, misspelled" rather than "this string is simply absent".
# Only used to describe the failure — both outcomes fail the gate.
_MISSPELLING_RATIO = 0.75

# Fields where the string simply not being on screen is a defect. The
# business name is absent from this set on purpose — see the module
# docstring; for it, only a near-miss counts as a failure.
_MUST_BE_PRESENT = ("product_name", "navigation")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def _closest_misspelling(target: str, rendered: list[str], explained: set[str]) -> str | None:
    """The rendered string that looks like a misspelling of `target`, or None.

    Two things are deliberately NOT misspellings:

    A substring relationship. "SmileBright Dental" and a wordmark rendered
    "SmileBright" score 0.76 similar, over the cutoff — but nothing is
    spelled wrong, the name is simply shorter on screen, and business names
    share a prefix with their product names most of the time.

    A string that is already accounted for by a DIFFERENT expected value.
    Measured on the golden set 2026-08-11: the salon screen renders the
    product wordmark "Lumière Studio OS", which scores similar enough to
    the business name "Lumière Hair Studio" to be reported as a misspelling
    of it. Nothing was wrong with that screen; the gate spent a
    regeneration on it and the request cost 60% more than its siblings.
    Text that correctly renders one required string cannot simultaneously
    be a corruption of another.
    """
    for match in difflib.get_close_matches(target, rendered, n=3, cutoff=_MISSPELLING_RATIO):
        if match in target or target in match or match in explained:
            continue
        return match
    return None


def required_strings(spec: UIDemoSpec) -> dict[str, list[str]]:
    """The brand-critical set, grouped by field, exactly as the prompt asked
    for it. `navigation` is sliced to 8 because that is what
    prompt_builder._content_sections emits."""
    return {
        "business_name": [spec.business.name] if spec.business.name else [],
        "product_name": [spec.product.name] if spec.product.name else [],
        "navigation": [label for label in spec.navigation[:8] if label],
    }


def check(spec: UIDemoSpec, transcript: list[str]) -> dict:
    """Diffs a transcription against the spec's brand-critical strings.

    Returns {"passed": bool, "checked": int, "failures": [...],
    "absent": [...]} where a failure's kind is "misspelled" (something close
    was rendered) or "missing" (nothing close was rendered at all).
    `absent` collects strings that are simply not on screen and are not
    required to be — reported for visibility, never a failure.
    """
    rendered = [_normalize(t) for t in transcript if str(t).strip()]
    # Two views of the same transcription. Per-entry drives the
    # closest-match diagnosis; the flat join is what a wrapped label
    # ("SmileBright" / "Operations") has to be matched against, since the
    # transcriber returns each rendered LINE, not each logical string.
    flat = " ".join(rendered)

    required = required_strings(spec)

    # Rendered entries that already account for some required string. Built
    # before any diagnosis, because whether a line is "explained" does not
    # depend on which field is being checked at the time.
    explained: set[str] = set()
    for values in required.values():
        for expected in values:
            target = _normalize(expected)
            if not target:
                continue
            for entry in rendered:
                if re.search(rf"(?<!\w){re.escape(target)}(?!\w)", entry):
                    explained.add(entry)

    failures: list[dict] = []
    absent: list[dict] = []
    checked = 0
    for field, expected_values in required.items():
        for expected in expected_values:
            target = _normalize(expected)
            if not target:
                continue
            checked += 1
            # Contained-but-whole: a nav label is often rendered inside a
            # longer line ("Dashboard 12"), so equality is too strict — but
            # a bare substring test is too loose in the other direction,
            # since "Recal" sits happily inside "Recall" and a spec label
            # like "Bill" would be satisfied by "Billing". Word boundaries
            # give the containment without the free pass.
            if re.search(rf"(?<!\w){re.escape(target)}(?!\w)", flat):
                continue
            closest = _closest_misspelling(target, rendered, explained)
            entry = {
                "field": field,
                "expected": expected,
                "kind": "misspelled" if closest else "missing",
                "closest": closest,
            }
            if entry["kind"] == "missing" and field not in _MUST_BE_PRESENT:
                absent.append(entry)
            else:
                failures.append(entry)

    return {"passed": not failures, "checked": checked, "failures": failures, "absent": absent}


def describe(result: dict) -> list[str]:
    """Short issue strings for the QA verdict / logs."""
    out = []
    for failure in result["failures"]:
        if failure["kind"] == "misspelled":
            out.append(f'text-truth: "{failure["expected"]}" rendered as "{failure["closest"]}"')
        else:
            out.append(f'text-truth: "{failure["expected"]}" ({failure["field"]}) not rendered')
    return out
