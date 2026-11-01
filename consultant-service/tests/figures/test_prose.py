"""The prose a client reads on the web, from the three stages that had no number check.

`analyze` (the understanding), `decide` (the recommendation) and `diagnose` (the
explanations, their tests and the reviewers' objections) write text a client reads.
Each now passes it through `bind.clean_sentences` against the figures the request
knows: a sentence that holds a number nobody owns is dropped and its neighbours are
kept; a number the client gave, or that we worked out from theirs, is kept.

What an emptied field does is each stage's existing rule. `decide` and `analyze`
require nothing in a reply beyond a JSON object, so a field whose every sentence is
dropped is stored empty, as one the model did not write. `diagnose` requires an
explanation to have a statement and a diagnosis to have two, so a reply whose
statements are all dropped is asked for again and then stops the run.

The model is always a stub (`app.ai.provider.chat`); nothing reaches the provider.
"""
import json
import os
import threading

import pytest

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import AiUsageEvent, Request
from app.pipeline import analyze, capacity, decide, diagnose, orchestrator
from app.pipeline.failure import StageFailed

QUESTION = "How many classes do you run, out of the 8 slots we could offer?"
ANSWER = "12 reformers, 6 classes a day, 6 days a week."
DESCRIPTION = "A pilates studio. We charge $22 a class."


# -- the row and the model ----------------------------------------------------------------

def _picture() -> dict:
    """Their week as `capacity.shape` works it out from their answer: 432 reformer
    spots a week, 36 slots a week."""
    picture = capacity.shape({"shape": "weekly_grid", "unit": "reformer spot", "unit_plural": "reformer spots",
                              "per_slot": 12, "slots_per_day": 6, "days_per_week": 6}, [ANSWER])
    assert picture and picture["capacity"] == 432
    return picture


def _row(**fields) -> int:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        req = Request(
            business_name="Halo Reformer Studio", business_description=DESCRIPTION,
            main_problem="The evenings are full.", email="test@example.com", owner_email="test@example.com",
            public_id=f"prose{os.urandom(4).hex()}", status="new", is_generating=True, stage="analyzing",
            stage_label="Analyzing...", progress_pct=10,
            ops_numbers_json=json.dumps([{"id": "q1", "question": QUESTION, "answer": ANSWER}]),
            **fields,
        )
        db.add(req)
        db.commit()
        return req.id
    finally:
        db.close()


def _read(request_id: int) -> Request:
    db = SessionLocal()
    try:
        row = db.get(Request, request_id)
        db.expunge(row)
        return row
    finally:
        db.close()


def _ledger(request_id: int) -> list[tuple[str, bool]]:
    db = SessionLocal()
    try:
        rows = db.query(AiUsageEvent).filter(AiUsageEvent.request_id == request_id).order_by(AiUsageEvent.id)
        return [(e.purpose, e.success) for e in rows]
    finally:
        db.close()


def _reply(content) -> dict:
    return {"choices": [{"message": {"content": content if isinstance(content, str) else json.dumps(content)}}],
            "usage": {}}


def _model_says(monkeypatch, *replies) -> list[str]:
    """The model answers each call with the next reply (the last one repeats). Returns
    the prompts it was sent."""
    prompts: list[str] = []
    left = list(replies)

    def chat(model, messages, **kwargs):
        prompts.append(messages[0]["content"])
        return _reply(left.pop(0) if len(left) > 1 else left[0])

    monkeypatch.setattr("app.ai.provider.chat", chat)
    return prompts


def _model_says_by_template(monkeypatch, replies: dict) -> None:
    """For `diagnose`, which renders three templates: the model answers each prompt from
    the template it was rendered from. A reply is a dict (sent as JSON) or a list of
    them, used in turn with the last one repeating."""
    rendered: dict[str, str] = {}
    real_render = diagnose.render
    lock = threading.Lock()
    turns: dict[str, int] = {}

    def render_and_remember(name, **context):
        text = real_render(name, **context)
        rendered[text] = name
        return text

    def chat(model, messages, **kwargs):
        name = rendered[messages[0]["content"]]
        reply = replies[name]
        if isinstance(reply, list):
            with lock:
                n = turns.get(name, 0)
                turns[name] = n + 1
            reply = reply[min(n, len(reply) - 1)]
        return _reply(reply)

    monkeypatch.setattr(diagnose, "render", render_and_remember)
    monkeypatch.setattr("app.ai.provider.chat", chat)


def _analyze(request_id: int) -> dict:
    db = SessionLocal()
    try:
        return analyze.analyze_business(db, request_id)
    finally:
        db.close()


def _decide(request_id: int) -> dict:
    db = SessionLocal()
    try:
        return decide.decide(db, request_id, {"business_model": "classes"})
    finally:
        db.close()


def _diagnose(request_id: int) -> dict:
    db = SessionLocal()
    try:
        return diagnose.diagnose(db, request_id, {"business_model": "classes"})
    finally:
        db.close()


# -- analyze --------------------------------------------------------------------------------

def test_the_analysis_loses_a_sentence_with_a_number_nobody_gave_and_keeps_its_neighbours(monkeypatch):
    _model_says(monkeypatch, {
        "business_model": "Appointments",
        "target_customer_profile": "Busy people who book a class after work. Most of them earn $85,000 a year. "
                                   "They expect to book from a phone.",
        "pain_points": ["Booking is done by hand."],
        "growth_opportunity": "Fill the quiet mornings. Competitors take 40% of the market. Rent is steady."})
    request_id = _row()

    result = _analyze(request_id)

    assert result["target_customer_profile"] == ("Busy people who book a class after work. "
                                                 "They expect to book from a phone.")
    assert result["growth_opportunity"] == "Fill the quiet mornings. Rent is steady."
    assert json.loads(_read(request_id).business_analysis_json) == result
    assert result["business_model"] == "Appointments"


def test_a_number_the_client_gave_stays_in_the_analysis(monkeypatch):
    """$22 is in their description and 12 in their answer; 'twelve' is bound to the digits."""
    _model_says(monkeypatch, {
        "business_model": "Appointments",
        "target_customer_profile": "Members who pay $22 a class.",
        "pain_points": ["Twelve reformers sit idle in the mornings."],
        "growth_opportunity": "Fill the mornings."})

    result = _analyze(_row())

    assert result["target_customer_profile"] == "Members who pay $22 a class."
    assert result["pain_points"] == ["12 reformers sit idle in the mornings."]


def test_a_pain_point_that_empties_is_dropped_and_the_others_stay(monkeypatch):
    _model_says(monkeypatch, {
        "business_model": "Appointments", "target_customer_profile": "Members.",
        "pain_points": ["Rent rose 40% last year.", "Booking is done by hand.",
                        "Cancellations cost them $3,000 a month. Nobody chases the gaps."],
        "growth_opportunity": "Fill the mornings."})

    result = _analyze(_row())

    assert result["pain_points"] == ["Booking is done by hand.", "Nobody chases the gaps."]


def test_an_analysis_whose_prose_all_empties_is_stored_empty_like_one_never_written(monkeypatch):
    """Nothing in an analysis is required beyond a JSON object, so no field is a reason to
    stop the run: an emptied field is stored empty and the stage does not ask again."""
    prompts = _model_says(monkeypatch, {
        "business_model": "Appointments", "target_customer_profile": "They earn $85,000 a year.",
        "pain_points": ["Rent rose 40% last year."], "growth_opportunity": "Take 15% of the market."})
    request_id = _row()

    result = _analyze(request_id)

    assert result["target_customer_profile"] == "" and result["growth_opportunity"] == ""
    assert result["pain_points"] == []
    assert len(prompts) == 1 and _ledger(request_id) == [("analyze", True)]
    assert json.loads(_read(request_id).business_analysis_json) == result


# -- decide ---------------------------------------------------------------------------------

DECISION = {
    "intervention_kind": "software",
    "central_problem": "The evenings are full. They turn away 30 people a week.",
    "why_not_the_others": "Pricing is not the constraint. A rise of 15% would not fill the mornings.",
    "consulting_summary": "Fill the quiet mornings first. That would add $9,000 a month. Keep the evening price.",
    "rests_on": ["CF-01"],
    "recommended_ai_employees": [{"title": "Booking agent", "why": "It answers at night."}],
    "recommended_features": ["Waiting list", "A 25% discount engine"],
    "confidence": "low",
    "unverified": ["Whether the mornings would fill.", "The 18 people on the waiting list."],
}


def test_the_decision_loses_each_sentence_with_a_number_nobody_gave_and_keeps_its_neighbours(monkeypatch):
    _model_says(monkeypatch, DECISION)
    request_id = _row()

    result = _decide(request_id)

    assert result["central_problem"] == "The evenings are full."
    assert result["why_not_the_others"] == "Pricing is not the constraint."
    assert result["consulting_summary"] == "Fill the quiet mornings first. Keep the evening price."
    row = _read(request_id)
    assert json.loads(row.consulting_recommendations_json) == result
    assert row.consulting_analysis == result["consulting_summary"]


def test_a_list_item_that_empties_is_dropped_from_every_list_of_the_decision(monkeypatch):
    _model_says(monkeypatch, {**DECISION, "recommended_ai_employees": [
        {"title": "Booking agent", "why": "It answers at night. It saves 20 hours a week."},
        {"title": "A 3-person night desk", "why": "It is staffed."},
        {"title": "Reminder agent", "why": "Members are told 2 days ahead."}]})

    result = _decide(_row())

    assert result["unverified"] == ["Whether the mornings would fill."]
    assert result["recommended_features"] == ["Waiting list"]
    # a title that empties drops the employee; a reason that loses a sentence keeps the rest of it;
    # a reason that empties leaves the employee, whose title is the recommendation
    assert result["recommended_ai_employees"] == [
        {"title": "Booking agent", "why": "It answers at night."},
        {"title": "Reminder agent", "why": ""}]


def test_a_number_the_client_gave_stays_in_the_decision(monkeypatch):
    _model_says(monkeypatch, {**DECISION,
                              "consulting_summary": "You charge $22 a class and have twelve reformers."})

    result = _decide(_row())

    assert result["consulting_summary"] == "You charge $22 a class and have 12 reformers."


def test_a_figure_we_worked_out_from_their_week_stays_in_the_decision(monkeypatch):
    """CAP-01 and CAP-02 are derived figures on the row: the week as it was just worked out."""
    _model_says(monkeypatch, {**DECISION,
                              "consulting_summary": "That is 432 reformer spots a week across 36 slots a week. "
                                                    "Of those, 400 reformer spots are sold."})

    result = _decide(_row(capacity_json=json.dumps(_picture())))

    assert result["consulting_summary"] == "That is 432 reformer spots a week across 36 slots a week."


def test_the_claim_ids_and_the_two_enumerations_are_not_prose(monkeypatch):
    _model_says(monkeypatch, {**DECISION, "consulting_summary": "The evenings are full (CF-01)."})

    result = _decide(_row())

    assert result["consulting_summary"] == "The evenings are full (CF-01)."
    assert result["rests_on"] == ["CF-01"]
    assert result["intervention_kind"] == "software" and result["confidence"] == "low"


def test_a_decision_whose_summary_all_empties_is_stored_with_an_empty_summary(monkeypatch):
    """The decision requires nothing in a reply beyond a JSON object (a reply with no
    summary is accepted today), so an emptied summary is stored empty and the stage
    does not ask again. Whoever shows the summary shows nothing, as for one never written."""
    prompts = _model_says(monkeypatch, {**DECISION, "consulting_summary": "That adds $9,000 a month."})
    request_id = _row()

    result = _decide(request_id)

    assert result["consulting_summary"] == ""
    assert len(prompts) == 1 and _ledger(request_id) == [("decide", True)]
    row = _read(request_id)
    assert row.consulting_analysis == "" and json.loads(row.consulting_recommendations_json) == result


# -- diagnose -------------------------------------------------------------------------------

def _hypothesis(n: int, statement: str, **fields) -> dict:
    return {"id": f"H{n}", "statement": statement, "area": "capacity", "software_can_fix": True,
            "would_support": "a full week", "would_refute": "an empty week", "cites": [],
            "from_owner": False, **fields}


STATEMENTS = ("Evenings are full.", "Mornings are empty.", "Prices are too low.")
TESTED = {"verdict": "supported", "because": "The evenings are full.", "cites": [], "would_need": "A booking export."}
NOT_KILLED = {"kills": False, "because": "", "weakness": "", "better_explanation": ""}


def _diagnosis_says(monkeypatch, hypotheses, tested=TESTED, challenge=NOT_KILLED) -> None:
    _model_says_by_template(monkeypatch, {
        "diagnose.j2": {"hypotheses": hypotheses}, "test_hypothesis.j2": tested, "challenge.j2": challenge})


def test_a_statement_loses_a_sentence_with_a_number_nobody_gave_and_keeps_its_neighbours(monkeypatch):
    _diagnosis_says(monkeypatch, [
        _hypothesis(1, "Evenings are full. They lose $50,000 a year because of it. Mornings are not."),
        _hypothesis(2, STATEMENTS[1]), _hypothesis(3, STATEMENTS[2])])
    request_id = _row()

    result = _diagnose(request_id)

    assert result["hypotheses"][0]["statement"] == "Evenings are full. Mornings are not."
    assert [h["statement"] for h in result["hypotheses"][1:]] == list(STATEMENTS[1:])


def test_a_number_the_client_gave_stays_in_a_statement(monkeypatch):
    _diagnosis_says(monkeypatch, [
        _hypothesis(1, "At $22 a class twelve reformers cannot earn enough."),
        _hypothesis(2, STATEMENTS[1]), _hypothesis(3, STATEMENTS[2])])

    result = _diagnose(_row())

    assert result["hypotheses"][0]["statement"] == "At $22 a class 12 reformers cannot earn enough."


def test_a_figure_we_worked_out_from_their_week_stays_in_a_statement(monkeypatch):
    _diagnosis_says(monkeypatch, [
        _hypothesis(1, "At 432 reformer spots a week the studio is at its ceiling. 400 reformer spots are sold."),
        _hypothesis(2, STATEMENTS[1]), _hypothesis(3, STATEMENTS[2])])

    result = _diagnose(_row(capacity_json=json.dumps(_picture())))

    assert result["hypotheses"][0]["statement"] == "At 432 reformer spots a week the studio is at its ceiling."


def test_an_explanation_that_empties_is_dropped_and_the_diagnosis_goes_on_with_the_rest(monkeypatch):
    _diagnosis_says(monkeypatch, [
        _hypothesis(1, "They lose $50,000 a year."), _hypothesis(2, STATEMENTS[1]),
        _hypothesis(3, STATEMENTS[2])])

    result = _diagnose(_row())

    assert [h["id"] for h in result["hypotheses"]] == ["H2", "H3"]


def test_the_other_prose_of_an_explanation_is_checked_and_its_citations_are_not(monkeypatch):
    request_id = _row()
    _diagnosis_says(monkeypatch, [
        _hypothesis(1, STATEMENTS[0], would_support="A full week. Fewer than 40 empty seats.",
                    would_refute="Empty evenings.", cites=["CF-01", "CF-99"]),
        _hypothesis(2, STATEMENTS[1]), _hypothesis(3, STATEMENTS[2])])

    result = _diagnose(request_id)

    first = result["hypotheses"][0]
    assert first["would_support"] == "A full week." and first["would_refute"] == "Empty evenings."
    # a claim id is kept when the claim exists and dropped when it does not, as before
    assert first["cites"] == [c for c in ["CF-01"] if c in {e["id"] for e in result["evidence"]}]
    assert first["cites"]


def test_an_explanation_reply_with_too_few_statements_left_is_asked_for_again_then_stops_the_run(monkeypatch):
    """A diagnosis needs two explanations. When the numbers nobody gave leave fewer, the
    reply is unusable: asked for again, and after the last the stage stops, with the
    last diagnosis cleared, exactly as for a reply that held too few to begin with."""
    _diagnosis_says(monkeypatch, [
        _hypothesis(1, "They lose $50,000 a year."), _hypothesis(2, "They lose 14 members a month."),
        _hypothesis(3, STATEMENTS[2])])
    request_id = _row(diagnosis_json=json.dumps({"leading": "H1", "hypotheses": [{"id": "H1", "statement": "Old"}]}))

    with pytest.raises(StageFailed) as stopped:
        _diagnose(request_id)

    assert stopped.value.stage == "diagnosing"
    assert "1 usable explanation" in stopped.value.cause and "needs 2" in stopped.value.cause
    assert _ledger(request_id) == [("diagnose:1", False)] * settings.STAGE_REPLY_ATTEMPTS
    assert _read(request_id).diagnosis_json is None


def test_a_second_reply_with_clean_statements_is_used(monkeypatch):
    bad = [_hypothesis(1, "They lose $50,000 a year."), _hypothesis(2, "They lose 14 members a month.")]
    good = [_hypothesis(1, STATEMENTS[0]), _hypothesis(2, STATEMENTS[1]), _hypothesis(3, STATEMENTS[2])]
    _model_says_by_template(monkeypatch, {
        "diagnose.j2": [{"hypotheses": bad}, {"hypotheses": good}],
        "test_hypothesis.j2": TESTED, "challenge.j2": NOT_KILLED})
    request_id = _row()

    result = _diagnose(request_id)

    assert [h["statement"] for h in result["hypotheses"]] == list(STATEMENTS)
    assert _ledger(request_id) == [
        ("diagnose:1", False), ("diagnose:1", True), *[("test_hypothesis", True)] * 3,
        ("challenge:alternative", True), ("challenge:confirmation", True)]


def test_what_the_tests_and_the_reviewers_write_is_checked_too(monkeypatch):
    request_id = _row()
    _diagnosis_says(
        monkeypatch, [_hypothesis(n, s) for n, s in enumerate(STATEMENTS, 1)],
        tested={"verdict": "supported", "cites": [],
                "because": "The evenings are full. Rent rose 40% last year. Twelve reformers share them.",
                "would_need": "A booking export for the last 90 days."},
        challenge={"kills": False, "because": "Nothing found. A rival opened 3 miles away.",
                   "weakness": "It rests on one week.", "better_explanation": "Prices are low at 15% below rivals."})

    result = _diagnose(request_id)

    test = result["hypotheses"][0]["test"]
    assert test["because"] == "The evenings are full. 12 reformers share them."
    assert test["would_need"] == ""
    for challenge in result["challenges"]:
        assert challenge["because"] == "Nothing found." and challenge["weakness"] == "It rests on one week."
        assert challenge["better_explanation"] == ""
    assert result["weaknesses"] == ["It rests on one week."]
    # the verdict, the flags and the reviewers' own verdict are not prose
    assert test["verdict"] == "supported" and result["status"] == "survived"


def test_the_thinking_trail_shows_the_cleaned_statements_and_keeps_our_own_counts(monkeypatch):
    request_id = _row()
    _diagnosis_says(monkeypatch, [
        _hypothesis(1, "Evenings are full. They lose $50,000 a year."), _hypothesis(2, STATEMENTS[1]),
        _hypothesis(3, STATEMENTS[2])])

    _diagnose(request_id)

    trail = json.loads(_read(request_id).thinking_json)
    texts = [line["text"] for line in trail]
    assert "3 possible explanations" in texts and "Testing all 3 against their own figures" in texts
    assert "Evenings are full." in texts
    assert not any("50,000" in t for t in texts)


# -- the parts of the row that are not about this run ----------------------------------------

STALE_ANSWER = json.dumps({"move": {"value": 44928, "unit": "USD", "label": "a move", "working": "w",
                                    "proposed": [], "cites": []}})


def test_a_figure_an_earlier_answer_left_on_the_row_vouches_for_nothing(monkeypatch):
    """The answer is written after all three stages, so on the row it is from an earlier
    run. Its move ($44,928) is not a figure of this run's prose."""
    _model_says(monkeypatch, {
        "business_model": "Appointments", "target_customer_profile": "Members.",
        "pain_points": ["Booking is done by hand."], "growth_opportunity": "Fill the mornings. Win $44,928 a year."})
    assert _analyze(_row(answer_json=STALE_ANSWER))["growth_opportunity"] == "Fill the mornings."

    _model_says(monkeypatch, {**DECISION, "consulting_summary": "Fill the mornings. That is worth $44,928 a year."})
    assert _decide(_row(answer_json=STALE_ANSWER))["consulting_summary"] == "Fill the mornings."

    _diagnosis_says(monkeypatch, [
        _hypothesis(1, "Evenings are full. They lose $44,928 a year."), _hypothesis(2, STATEMENTS[1]),
        _hypothesis(3, STATEMENTS[2])])
    assert _diagnose(_row(answer_json=STALE_ANSWER))["hypotheses"][0]["statement"] == "Evenings are full."


def test_the_analysis_runs_before_the_week_is_read_so_the_week_on_the_row_vouches_for_nothing(monkeypatch):
    """`analyze` is the first stage; the capacity picture on the row is the last run's, and
    the model was shown nothing of it. The decision, which runs after the week is read, may use it."""
    reply = {"business_model": "Appointments", "target_customer_profile": "Members.", "pain_points": [],
             "growth_opportunity": "Fill the mornings. The studio sells 432 reformer spots a week."}
    _model_says(monkeypatch, reply)

    result = _analyze(_row(capacity_json=json.dumps(_picture())))

    assert result["growth_opportunity"] == "Fill the mornings."


# -- the orchestrator's capacity read -------------------------------------------------------------

def test_the_capacity_prompt_shows_the_question_and_the_check_does_not(monkeypatch):
    """Their numbers are checked in their answers alone; the prompt shows each answer
    beside the question it answers, as the interview's does. The model says 8 slots, a
    number only our question holds: it is not theirs, so the picture has no 'typical' week."""
    reading = {"shape": "weekly_grid", "unit": "reformer spot", "unit_plural": "reformer spots",
               "per_slot": 12, "slots_per_day": 6, "days_per_week": 6, "typical_taken": 8,
               "day_names": [], "slot_times": [], "full_slots": [], "waitlist": False}
    prompts = _model_says(monkeypatch, reading)
    seen = {}
    real_read = capacity.read

    def spy(texts, stage="operating", earlier=None, *, context=None):
        seen.update(texts=list(texts), context=list(context or []))
        return real_read(texts, stage, earlier, context=context)

    monkeypatch.setattr(capacity, "read", spy)
    request_id = _row()

    db = SessionLocal()
    try:
        orchestrator._read_capacity(db, request_id)
    finally:
        db.close()

    assert len(prompts) == 1 and f"{QUESTION}: {ANSWER}" in prompts[0]
    assert ANSWER in seen["texts"] and not any(QUESTION in t for t in seen["texts"])
    assert f"{QUESTION}: {ANSWER}" in seen["context"] and DESCRIPTION in seen["context"]
    picture = json.loads(_read(request_id).capacity_json)
    assert picture["capacity"] == 432 and picture["typical_taken"] is None
    assert _ledger(request_id) == [("capacity", True)]


class _Row:
    def __init__(self, ops):
        self.ops_numbers_json = ops


@pytest.mark.parametrize("ops, texts, lines", [
    pytest.param(None, ["A."], ["A."], id="no answers"),
    pytest.param("not json", ["A."], ["A."], id="unreadable"),
    pytest.param(json.dumps({"q": "a"}), ["A."], ["A."], id="not a list"),
    pytest.param(json.dumps([{"question": "Q1?", "answer": " a1 "}, {"question": "Q2?", "answer": "  "},
                             "junk", {"question": "", "answer": "a3"}, {"answer": 7}]),
                 ["a1", "a3", "free"], ["Q1?: a1", "a3", "free"], id="only answered pairs, then the free words"),
])
def test_the_capacity_context_pairs_each_answer_with_its_question(ops, texts, lines):
    assert orchestrator._capacity_context(_Row(ops), texts) == lines
