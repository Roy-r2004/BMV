"""The answer page is assembled from columns the run already stored.

A part with nothing behind it is absent. A number carries the tag of the
figure it is. Nothing on the page says the system is unsure.
"""
from __future__ import annotations

import json
from decimal import Decimal

from app.figures import known as K
from app.figures.model import (
    Figure, Proposal, Reference, TheirsSource, Working, as_json,
)
from app.models import Request
from app.storyline.build import answer_page, build
from app.storyline.model import (
    AnswerPage, Exhibit, Number, RestsOn, Section, Storyline, from_json, to_json,
)

_TAGS = {"yours", "worked out", "our estimate", "reference"}


def _fig(kind: str, fid: str, value: str, source) -> Figure:
    return Figure(fid, Decimal(value), "USD", None, kind, source, 0)


THEIRS = _fig("theirs", "CF-04", "22", TheirsSource(1, "price", "We charge $22 a class.", None, None))
DERIVED = _fig("derived", "CAP-05", "144", Working(("CF-04",), "product", "12 x 12 = 144"))
OURS = _fig("ours", "PROP-9", "28", Proposal("the evening price we propose"))
REFERENCE = _fig("reference", "REF-1", "30", Reference("The studio survey", 2024, "city studios",
                                                       "https://example.com/survey"))


def _req(**columns) -> Request:
    base = dict(business_name="Halo", business_description="A pilates studio.", email="a@b.c")
    base.update(columns)
    return Request(**base)


def _answer(**over) -> dict:
    answer = {
        "headline": "You are full at the price you charge.",
        "turn": "The evenings are the hours to change.",
        "sub": "",
        "figures": [
            {"value": "$22", "label": "a class", "cites": ["CF-04"], "ids": ["CF-04"]},
            {"value": "144", "label": "evening spots", "cites": ["CAP-05"], "ids": ["CAP-05"]},
        ],
        "move": {"label": "the prize", "value": 3120, "display": "≈ $3,120 a year", "unit": "USD",
                 "period": "year", "proposed": [{"value": 28, "label": "evening price", "unit": "USD"}],
                 "cites": ["CF-04"]},
    }
    answer.update(over)
    return answer


def _full(**over) -> Request:
    diagnosis = {
        "hypotheses": [
            {"statement": "The price is what keeps the mornings empty.", "from_owner": True,
             "test": {"verdict": "supported", "because": "The mornings are the empty hours, and the price is theirs."}},
            {"statement": "A new booking app fills Tuesday.", "from_owner": False,
             "test": {"verdict": "refuted", "because": "Tuesday is empty because of the price, not the tool."}},
            {"statement": "Hiring another teacher fills the week.", "from_owner": False,
             "test": {"verdict": "refuted", "because": "The week is already staffed."}},
            {"statement": "Opening Sunday fills the week.", "from_owner": False,
             "test": {"verdict": "refuted", "because": "Sunday was not asked for."}},
            {"statement": "A loyalty card fills the week.", "from_owner": False,
             "test": {"verdict": "refuted", "because": "The regulars already come."}},
        ]
    }
    plan = {"phases": [{"when": "Week 1", "do": "Tell the regulars the new price.",
                        "you": "You send the message."}]}
    columns = dict(
        main_problem="I think the mornings are empty because the price is too low.",
        brief_json=json.dumps({"question": "Why are the mornings empty?"}),
        answer_json=json.dumps(_answer()),
        storyline_json=json.dumps({"register": [], "sections": []}),
        case_file_json=json.dumps([as_json(f) for f in (THEIRS, DERIVED, OURS, REFERENCE)]),
        diagnosis_json=json.dumps(diagnosis),
        action_plan_json=json.dumps(plan),
        consulting_recommendations_json=json.dumps({
            "intervention_kind": "software",
            "why_not_the_others": "A new app would not fill Tuesday.",
        }),
        qa_report_json=json.dumps({"checks": [
            {"label": "numbers", "passed": True},
            {"label": "structure", "passed": True},
            {"label": "scope", "passed": False},
        ]}),
    )
    columns.update(over)
    return _req(**columns)


def test_answer_page_takes_each_part_from_its_column():
    page = answer_page(_full())
    assert page.question == "Why are the mornings empty?"
    assert page.answer_lines == ("You are full at the price you charge.",
                                 "The evenings are the hours to change.")
    assert page.believed == "I think the mornings are empty because the price is too low."
    assert page.tested == "The mornings are the empty hours, and the price is theirs."
    assert page.monday == "Tell the regulars the new price. You send the message."
    assert page.would_not == (
        "A new booking app fills Tuesday.",
        "Hiring another teacher fills the week.",
        "Opening Sunday fills the week.",
        "A new app would not fill Tuesday.",
    )
    assert page.rests_on.checks_passed == 2 and page.rests_on.checks_run == 3
    story = build(_full())
    assert story is not None and story.builds is True and story.answer == page


def test_numbers_are_at_most_three_and_each_carries_its_tag_word():
    page = answer_page(_full())
    assert len(page.numbers) == 3
    assert [(n.figure_id, n.tag) for n in page.numbers] == [
        ("CF-04", "yours"), ("CAP-05", "worked out"), ("MOVE", "our estimate")]
    assert page.numbers[0].display == "$22"
    assert page.numbers[2].display == "≈ $3,120 a year"
    reference = answer_page(_full(answer_json=json.dumps(_answer(
        figures=[{"value": "$30", "label": "a published rate", "cites": ["REF-1"], "ids": ["REF-1"]}],
        move=None))))
    assert [n.tag for n in reference.numbers] == ["reference"]
    assert all(n.tag in _TAGS for n in page.numbers + reference.numbers)


def test_rests_on_counts_equal_known_for_counts():
    req = _full()
    counts = K.known_for(req).counts()
    rests = answer_page(req).rests_on
    assert (rests.theirs, rests.derived, rests.ours, rests.reference) == (
        counts["theirs"], counts["derived"], counts["ours"], counts["reference"])
    assert counts["theirs"] and counts["reference"]


def test_a_part_with_no_data_is_none_not_invented():
    assert build(_req()) is None
    page = answer_page(_req(answer_json=json.dumps(_answer(
        figures=[], move=None, turn=""))))
    assert page.question is None and page.believed is None and page.tested is None
    assert page.monday is None and page.would_not is None and page.numbers == ()
    assert page.answer_lines == ("You are full at the price you charge.",)
    win = answer_page(_req(
        answer_json=json.dumps(_answer(figures=[], move=None)),
        playbook_json=json.dumps({"quick_wins": [
            {"title": "Needs a tool", "no_software": False},
            {"title": "Write the evening price on the board.", "no_software": True},
        ]})))
    assert win.monday == "Write the evening price on the board."


def test_do_not_build_run_sets_builds_false():
    story = build(_full(consulting_recommendations_json=json.dumps({"intervention_kind": "pricing"})))
    assert story is not None and story.builds is False


def test_json_round_trip_is_lossless():
    story = build(_full())
    assert from_json(to_json(story)) == story
    exhibit = Exhibit("1.1", "waterfall", "Where the prize comes from", "The price carries it.",
                      {"steps": ["CF-04"]}, "her prices")
    section = Section("plan", "The evenings move first, and the mornings wait.",
                      "Start with the hours that already sell out.", exhibit,
                      ("The year is 52 weeks.",), "Price means a class.", ("Her answers",), "ESTIMATE")
    full = Storyline(
        AnswerPage("Why?", ("One.", "Two."),
                   (Number("CF-04", "$22", "yours"),),
                   "She said the price.", "The mornings are empty.", "Send the note.",
                   ("Do not open Sunday.",),
                   RestsOn(1, 2, 3, 4, 5, 6)),
        None, (section,), False)
    assert from_json(to_json(full)) == full


def test_the_answer_page_text_contains_no_hedging_words():
    banned = ("confident", "ai is", "not sure", "validation", "review by a human")
    page = answer_page(_full())
    text = json.dumps(to_json(Storyline(page, None, (), True)), ensure_ascii=False).lower()
    assert not any(word in text for word in banned)


def test_a_run_with_an_answer_and_no_storyline_has_no_storyline():
    # Review H2: every Step-2 run (answer stored, no storyline) opened its files
    # on an answer page it never had, and the web served one too.
    from app.storyline.build import for_web

    legacy = _full(storyline_json=None)
    assert build(legacy) is None
    assert for_web(legacy) == {"answer_page": None, "register": None}
