"""The prose a client reads on the web, from the three stages that had no number check.

`analyze` (the understanding), `decide` (the recommendation) and `diagnose` (the
explanations, their tests and the reviewers' objections) write text a client reads.
Each now passes it through `bind.clean_sentences` against the figures the request
knows: a sentence that holds a number nobody owns is dropped and its neighbours are
kept; a number the client gave, or that we worked out from theirs, is kept.

What an emptied core field does is the stage's existing "nothing usable" path: the
reply is asked for again (`ask_until_usable`) and then the stage raises `StageFailed`
with its own stage id. The core field is the summary for `decide`, the pain points and
the growth opportunity together for `analyze`, and the statements (two needed) for
`diagnose`. A reply that never had the field is accepted as before, and any other
field that loses every sentence is stored empty.

The model is always a stub (`app.ai.provider.chat`); nothing reaches the provider.
"""
import json
import os
import threading

import pytest

from app import mailer
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import AiUsageEvent, Request
from app.pipeline import analyze, capacity, decide, diagnose, orchestrator
from app.pipeline.failure import StageFailed, client_reason, fail_run

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


def _model_says_by_template(monkeypatch, replies: dict) -> dict[str, list[str]]:
    """For `diagnose`, which renders three templates: the model answers each prompt from
    the template it was rendered from. A reply is a dict (sent as JSON) or a list of
    them, used in turn with the last one repeating. Returns the prompts sent, by template."""
    rendered: dict[str, str] = {}
    real_render = diagnose.render
    lock = threading.Lock()
    turns: dict[str, int] = {}
    sent: dict[str, list[str]] = {}

    def render_and_remember(name, **context):
        text = real_render(name, **context)
        rendered[text] = name
        return text

    def chat(model, messages, **kwargs):
        # a prompt asked again carries the hint after the text that was rendered
        name = next(n for text, n in rendered.items() if messages[0]["content"].startswith(text))
        reply = replies[name]
        with lock:
            sent.setdefault(name, []).append(messages[0]["content"])
            if isinstance(reply, list):
                n = turns.get(name, 0)
                turns[name] = n + 1
                reply = reply[min(n, len(reply) - 1)]
        return _reply(reply)

    monkeypatch.setattr(diagnose, "render", render_and_remember)
    monkeypatch.setattr("app.ai.provider.chat", chat)
    return sent


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
    """$22 is in their description and 12 in their answer. A number word the client's figure
    supports ('Twelve') is kept as written: words stay words."""
    _model_says(monkeypatch, {
        "business_model": "Appointments",
        "target_customer_profile": "Members who pay $22 a class.",
        "pain_points": ["Twelve reformers sit idle in the mornings."],
        "growth_opportunity": "Fill the mornings."})

    result = _analyze(_row())

    assert result["target_customer_profile"] == "Members who pay $22 a class."
    assert result["pain_points"] == ["Twelve reformers sit idle in the mornings."]


def test_a_pain_point_that_empties_is_dropped_and_the_others_stay(monkeypatch):
    _model_says(monkeypatch, {
        "business_model": "Appointments", "target_customer_profile": "Members.",
        "pain_points": ["Rent rose 40% last year.", "Booking is done by hand.",
                        "Cancellations cost them $3,000 a month. Nobody chases the gaps."],
        "growth_opportunity": "Fill the mornings."})

    result = _analyze(_row())

    assert result["pain_points"] == ["Booking is done by hand.", "Nobody chases the gaps."]


NO_FINDINGS = {"business_model": "Appointments", "target_customer_profile": "They earn $85,000 a year.",
               "pain_points": ["Rent rose 40% last year."], "growth_opportunity": "Take 15% of the market."}
FINDINGS = {"business_model": "Appointments", "target_customer_profile": "Members.",
            "pain_points": ["Booking is done by hand."], "growth_opportunity": "Fill the mornings."}


def test_an_analysis_whose_findings_all_empty_is_asked_for_again_and_the_second_reply_is_used(monkeypatch):
    """The pain points and the growth opportunity are the analysis. When the model wrote
    some and the check leaves none, the reply is unusable: the existing second ask."""
    prompts = _model_says(monkeypatch, NO_FINDINGS, FINDINGS)
    request_id = _row()

    result = _analyze(request_id)

    assert result == FINDINGS and len(prompts) == 2
    assert _ledger(request_id) == [("analyze", False), ("analyze", True)]
    assert json.loads(_read(request_id).business_analysis_json) == FINDINGS


def test_an_analysis_whose_findings_empty_twice_stops_the_run_and_stores_nothing(monkeypatch):
    prompts = _model_says(monkeypatch, NO_FINDINGS)
    request_id = _row()

    with pytest.raises(StageFailed) as stopped:
        _analyze(request_id)

    assert stopped.value.stage == "analyzing" and len(prompts) == settings.STAGE_REPLY_ATTEMPTS
    assert "number nobody gave" in stopped.value.cause
    assert _ledger(request_id) == [("analyze", False)] * settings.STAGE_REPLY_ATTEMPTS
    assert _read(request_id).business_analysis_json is None


def test_an_analysis_that_keeps_one_finding_is_kept(monkeypatch):
    """Either finding is enough; the profile alone emptying is no reason to ask again."""
    prompts = _model_says(monkeypatch, {**NO_FINDINGS, "growth_opportunity": "Fill the mornings."})

    result = _analyze(_row())

    assert result["growth_opportunity"] == "Fill the mornings." and result["pain_points"] == []
    assert result["target_customer_profile"] == "" and len(prompts) == 1


def test_an_analysis_that_never_had_findings_is_accepted_as_before(monkeypatch):
    prompts = _model_says(monkeypatch, {"business_model": "Appointments"})

    result = _analyze(_row())

    assert result == {"business_model": "Appointments", "pain_points": []} and len(prompts) == 1


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

    assert result["consulting_summary"] == "You charge $22 a class and have twelve reformers."


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


EMPTIED_SUMMARY = {**DECISION, "consulting_summary": "That adds $9,000 a month. It saves 20 hours a week."}


def test_a_summary_that_empties_is_asked_for_again_and_the_second_reply_is_used(monkeypatch):
    """The summary is the recommendation to the owner. When the model wrote one and the
    check leaves nothing of it, the reply is unusable: the existing second ask."""
    good = {**DECISION, "consulting_summary": "Fill the quiet mornings first."}
    prompts = _model_says(monkeypatch, EMPTIED_SUMMARY, good)
    request_id = _row()

    result = _decide(request_id)

    assert result["consulting_summary"] == "Fill the quiet mornings first." and len(prompts) == 2
    assert _ledger(request_id) == [("decide", False), ("decide", True)]
    row = _read(request_id)
    assert row.consulting_analysis == "Fill the quiet mornings first."
    assert json.loads(row.consulting_recommendations_json)["consulting_summary"] == result["consulting_summary"]


def test_a_summary_that_empties_twice_stops_the_run_and_stores_nothing(monkeypatch):
    prompts = _model_says(monkeypatch, EMPTIED_SUMMARY)
    request_id = _row()

    with pytest.raises(StageFailed) as stopped:
        _decide(request_id)

    assert stopped.value.stage == "consulting" and len(prompts) == settings.STAGE_REPLY_ATTEMPTS
    assert "number nobody gave" in stopped.value.cause
    assert _ledger(request_id) == [("decide", False)] * settings.STAGE_REPLY_ATTEMPTS
    row = _read(request_id)
    assert row.consulting_recommendations_json is None and row.consulting_analysis is None


def test_a_summary_that_only_lost_a_sentence_is_kept_without_asking_again(monkeypatch):
    prompts = _model_says(monkeypatch, {**DECISION, "consulting_summary": "That adds $9,000 a month. Keep the price."})
    request_id = _row()

    result = _decide(request_id)

    assert result["consulting_summary"] == "Keep the price." and len(prompts) == 1
    assert _ledger(request_id) == [("decide", True)]


def test_a_decision_that_never_had_a_summary_is_accepted_as_before(monkeypatch):
    """A reply with no summary is usable today (test_honest_failure sends them), so the
    check adds no demand for one; only a summary the check emptied is unusable."""
    prompts = _model_says(monkeypatch, {"intervention_kind": "software", "confidence": "low"})

    result = _decide(_row())

    assert result.get("consulting_summary") is None and len(prompts) == 1


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

    assert result["hypotheses"][0]["statement"] == "At $22 a class twelve reformers cannot earn enough."


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
    # the cause (failure_json, the team's email) says it was the number check that emptied them
    assert "2 had no statement left once the sentences holding a number nobody gave" in stopped.value.cause
    assert _ledger(request_id) == [("diagnose:1", False)] * settings.STAGE_REPLY_ATTEMPTS
    assert _read(request_id).diagnosis_json is None


def test_a_reply_with_too_few_explanations_to_begin_with_does_not_blame_the_number_check(monkeypatch):
    _diagnosis_says(monkeypatch, [_hypothesis(1, STATEMENTS[0])])

    with pytest.raises(StageFailed) as stopped:
        _diagnose(_row())

    assert stopped.value.cause == "the model gave 1 usable explanation, and a diagnosis needs 2"


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
    assert test["because"] == "The evenings are full. Twelve reformers share them."
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


# -- the objections the diagnostician is handed again -----------------------------------------

KILLS = {"kills": True, "because": "Rent rose 40% last year, so the evenings are not the cause.",
         "weakness": "", "better_explanation": "Prices are 15% below rivals."}


def test_the_objections_a_second_pass_is_handed_are_the_reviewers_own_words(monkeypatch):
    """The text stored for the client is checked, so a reason that is one sentence holding a
    number nobody gave is stored empty. The diagnostician that must think again still hears
    it as written (it goes to the model, and anything it echoes is checked again), and no
    empty '- ' line is sent."""
    sent = _model_says_by_template(monkeypatch, {
        "diagnose.j2": {"hypotheses": [_hypothesis(n, s) for n, s in enumerate(STATEMENTS, 1)]},
        "test_hypothesis.j2": TESTED, "challenge.j2": KILLS})

    result = _diagnose(_row())

    first, second = sent["diagnose.j2"]
    assert "ONCE ALREADY" not in first and "ONCE ALREADY" in second
    heard = ("- Rent rose 40% last year, so the evenings are not the cause. "
             "A better explanation may be: Prices are 15% below rivals.")
    assert second.count(heard) == 2        # both reviewers
    assert not any(line.strip() == "-" for line in second.splitlines())
    assert result["attempts"] == 2
    assert all(c["because"] == "" and c["better_explanation"] == "" for c in result["challenges"])


# -- a cut never lands inside a figure -----------------------------------------------------------

def _straddling(limit: int, figure: str = "$2200") -> tuple[str, str]:
    """(a text, what is left of it once the sentence holding `figure` is taken out), built
    so that `figure` starts three characters before character `limit`: cut there, it would
    leave only the first three characters of it ("$22" of "$2200")."""
    start = limit - 3
    kept = "Evenings are full. "
    while len(kept) + 16 + len("Rent is ") <= start:
        kept += "Quiet mornings. "
    gap = start - len(kept) - len("Rent is ")
    # the sentence with the figure opens with a capital, or the splitter would not end the one before
    fill = "" if gap == 0 else " " if gap == 1 else "W" + "w" * (gap - 2) + " "
    text = kept + fill + f"Rent is {figure} a month."
    assert text[:limit].endswith("$22") and len(text) > limit
    return text, kept.strip()


def test_a_statement_is_checked_before_it_is_cut_so_the_cut_cannot_leave_a_known_number(monkeypatch):
    """Cut first, the 400th character would leave '$22', the price the client gave, in place
    of '$2200'. Checked first, the sentence holding '$2200' is taken out whole."""
    text, kept = _straddling(400)
    _diagnosis_says(monkeypatch, [_hypothesis(1, text), _hypothesis(2, STATEMENTS[1]), _hypothesis(3, STATEMENTS[2])])

    result = _diagnose(_row())

    assert result["hypotheses"][0]["statement"] == kept
    assert "$" not in result["hypotheses"][0]["statement"]


def test_a_test_and_a_reviewer_are_checked_before_they_are_cut_too(monkeypatch):
    because, kept_because = _straddling(400)
    note, kept_note = _straddling(300)
    _diagnosis_says(
        monkeypatch, [_hypothesis(n, s) for n, s in enumerate(STATEMENTS, 1)],
        tested={"verdict": "supported", "cites": [], "because": because, "would_need": note},
        challenge={"kills": False, "because": because, "weakness": note, "better_explanation": note})

    result = _diagnose(_row())

    test = result["hypotheses"][0]["test"]
    assert (test["because"], test["would_need"]) == (kept_because, kept_note)
    for c in result["challenges"]:
        assert (c["because"], c["weakness"], c["better_explanation"]) == (kept_because, kept_note, kept_note)


def test_an_unverified_item_is_checked_before_it_is_cut(monkeypatch):
    text, kept = _straddling(decide.UNVERIFIED_CHARS)
    _model_says(monkeypatch, {**DECISION, "unverified": [text]})

    assert _decide(_row())["unverified"] == [kept]


def test_a_long_statement_that_passes_is_cut_at_the_end_of_a_sentence(monkeypatch):
    long = "Quiet mornings. " * 40
    _diagnosis_says(monkeypatch, [_hypothesis(1, long), _hypothesis(2, STATEMENTS[1]), _hypothesis(3, STATEMENTS[2])])

    statement = _diagnose(_row())["hypotheses"][0]["statement"]

    assert len(statement) <= 400 and statement.endswith("mornings.") and statement.startswith("Quiet mornings. ")


def test_cut_prose_stops_at_a_sentence_end_in_the_second_half_else_at_a_word_end():
    cut = analyze.cut_prose
    text = "Aaa bbb. Ccc ddd eee. Fff ggg hhh iii."
    assert cut(text, 100) == text and cut(text, len(text)) == text
    assert cut(text, 23) == "Aaa bbb. Ccc ddd eee."      # the sentence ends at 21, after half of 23
    assert cut(text, 20) == "Aaa bbb. Ccc ddd"           # it ends at 8, in the first half: cut at a word
    assert cut(text, 25) == "Aaa bbb. Ccc ddd eee."      # the limit falls at the end of "Fff": the sentence end is kept
    assert cut("Rent is $2200 a month.", 11) == "Rent is"   # never inside the figure
    assert cut("w" * 50, 10) == ""                          # one word longer than the limit is not prose


# -- the figures a diagnosis is checked against ---------------------------------------------------

def test_figures_that_cannot_be_read_stop_the_diagnosis_as_diagnosing_and_clear_the_old_one(monkeypatch):
    def unreadable(*args, **kwargs):
        raise RuntimeError("the case file could not be read")

    prompts = _model_says(monkeypatch, {"hypotheses": []})
    monkeypatch.setattr(diagnose, "known_for", unreadable)
    request_id = _row(diagnosis_json=json.dumps({"leading": "H1", "hypotheses": [{"id": "H1", "statement": "Old"}]}))

    with pytest.raises(StageFailed) as stopped:
        _diagnose(request_id)

    assert stopped.value.stage == "diagnosing" and "the case file could not be read" in stopped.value.cause
    assert _read(request_id).diagnosis_json is None
    assert prompts == [] and _ledger(request_id) == []


def test_the_clock_times_that_cannot_be_read_stop_the_diagnosis_the_same_way(monkeypatch):
    def unreadable(*args, **kwargs):
        raise RuntimeError("no hours")

    monkeypatch.setattr(diagnose, "hours_for", unreadable)
    request_id = _row(diagnosis_json=json.dumps({"leading": "H1", "hypotheses": [{"id": "H1", "statement": "Old"}]}))

    with pytest.raises(StageFailed) as stopped:
        _diagnose(request_id)

    assert stopped.value.stage == "diagnosing" and _read(request_id).diagnosis_json is None


@pytest.mark.parametrize("module, stage, run", [
    pytest.param(analyze, "analyzing", _analyze, id="analyze"),
    pytest.param(decide, "consulting", _decide, id="decide"),
])
def test_figures_that_cannot_be_read_stop_the_other_two_stages_before_any_call(monkeypatch, module, stage, run):
    def unreadable(*args, **kwargs):
        raise RuntimeError("the case file could not be read")

    prompts = _model_says(monkeypatch, {"business_model": "x"})
    monkeypatch.setattr(module, "known_for", unreadable)
    request_id = _row()

    with pytest.raises(StageFailed) as stopped:
        run(request_id)

    assert stopped.value.stage == stage and prompts == [] and _ledger(request_id) == []


# -- what the check took out is logged --------------------------------------------------------------

def _logged(caplog, name: str) -> str:
    return " | ".join(r.getMessage() for r in caplog.records if r.name == name)


def test_the_log_names_how_many_sentences_and_which_numbers_but_never_the_sentences(monkeypatch, caplog):
    _model_says(monkeypatch, DECISION)

    with caplog.at_level("INFO", logger="consultant.decide"):
        _decide(_row())

    line = _logged(caplog, "consultant.decide")
    assert "took 5 sentence(s) out of the decision" in line
    for number in ("30", "15%", "$9,000", "25%", "18"):
        assert number in line
    for words in ("turn away", "discount engine", "waiting list", "fill the mornings"):
        assert words not in line


def test_the_log_is_written_on_the_retry_path_of_the_decision_and_the_analysis(monkeypatch, caplog):
    good = {**DECISION, "consulting_summary": "Fill the quiet mornings first."}
    _model_says(monkeypatch, EMPTIED_SUMMARY, good)
    with caplog.at_level("INFO", logger="consultant.decide"):
        assert _decide(_row())["consulting_summary"] == "Fill the quiet mornings first."
    first = _logged(caplog, "consultant.decide")
    assert "$9,000" in first and "20" in first          # the unusable first reply is what was logged

    _model_says(monkeypatch, NO_FINDINGS, FINDINGS)
    with caplog.at_level("INFO", logger="consultant.analyze"):
        assert _analyze(_row()) == FINDINGS
    second = _logged(caplog, "consultant.analyze")
    assert "took 3 sentence(s) out of the analysis" in second
    for number in ("$85,000", "40%", "15%"):
        assert number in second
    assert "Rent rose" not in second


def test_the_log_is_written_when_the_diagnosis_fails_for_want_of_statements(monkeypatch, caplog):
    _diagnosis_says(monkeypatch, [
        _hypothesis(1, "They lose $50,000 a year."), _hypothesis(2, "They lose 14 members a month."),
        _hypothesis(3, STATEMENTS[2])])

    with caplog.at_level("INFO", logger="consultant.diagnose"):
        with pytest.raises(StageFailed):
            _diagnose(_row())

    line = _logged(caplog, "consultant.diagnose")
    assert "took 4 sentence(s) out of the diagnosis" in line     # two sentences in each of the two replies
    assert "$50,000" in line and "14" in line and "They lose" not in line


# -- the next ask says what was taken out ---------------------------------------------------------

def _hint_after(prompts: list[str]) -> str:
    """What the second prompt adds to the first: the same prompt, then the hint."""
    first, second = prompts[0], prompts[1]
    assert "COULD NOT BE USED" not in first and second.startswith(first)
    return second[len(first):]


def _fails_for_the_client_in_its_own_words(request_id: int, stopped, monkeypatch) -> None:
    """The stage's stop, run through `fail_run`: the client reads the stage's own sentence,
    and nothing of the hint, the figures list or the numbers. The recorded cause is ours."""
    monkeypatch.setattr(mailer, "send_now", lambda to, subject, body: True)
    db = SessionLocal()
    try:
        told = fail_run(db, request_id, stopped.value.stage, stopped.value.cause)
    finally:
        db.close()
    row = _read(request_id)
    assert row.progress_detail == client_reason(stopped.value.stage, told)
    for text in (row.progress_detail, row.stage_label):
        assert "figures list" not in text and "{{F:" not in text and not any(ch.isdigit() for ch in text)
    assert "COULD NOT BE USED" not in (row.failure_json or "")


def test_the_second_analysis_ask_names_the_fields_and_the_numbers_but_not_the_sentences(monkeypatch):
    prompts = _model_says(monkeypatch, NO_FINDINGS, FINDINGS)
    request_id = _row()

    result = _analyze(request_id)

    hint = _hint_after(prompts)
    assert result == FINDINGS and len(prompts) == 2
    for name in ("target_customer_profile", "pain_points", "growth_opportunity"):
        assert f"- {name}: the number" in hint
    for number in ("$85,000", "40%", "15%"):
        assert number in hint
    assert "not in the figures list" in hint and "{{F:id}}" in hint and "in words" in hint
    assert "FIGURES YOU MAY USE" in hint and "$22" in hint       # the exact list, with the client's own figure
    for sentence_text in ("They earn", "Rent rose", "of the market"):
        assert sentence_text not in hint


def test_two_analysis_replies_the_check_empties_still_end_in_the_stage_failing(monkeypatch):
    prompts = _model_says(monkeypatch, NO_FINDINGS)
    request_id = _row()

    with pytest.raises(StageFailed) as stopped:
        _analyze(request_id)

    assert stopped.value.stage == "analyzing" and len(prompts) == settings.STAGE_REPLY_ATTEMPTS
    assert "$85,000" in stopped.value.cause and "COULD NOT BE USED" not in stopped.value.cause
    _fails_for_the_client_in_its_own_words(request_id, stopped, monkeypatch)


def test_the_second_decision_ask_names_the_fields_and_the_numbers_but_not_the_sentences(monkeypatch):
    good = {**DECISION, "consulting_summary": "Fill the quiet mornings first."}
    prompts = _model_says(monkeypatch, EMPTIED_SUMMARY, good)
    request_id = _row()

    result = _decide(request_id)

    hint = _hint_after(prompts)
    assert result["consulting_summary"] == "Fill the quiet mornings first." and len(prompts) == 2
    assert "- consulting_summary: the numbers $9,000 and 20" in hint
    for name in ("central_problem", "why_not_the_others", "unverified", "recommended_features"):
        assert f"- {name}: the number" in hint
    for number in ("30", "15%", "25%", "18"):
        assert number in hint
    assert "not in the figures list" in hint and "{{F:id}}" in hint and "FIGURES YOU MAY USE" in hint
    for sentence_text in ("That adds", "It saves", "turn away", "discount engine"):
        assert sentence_text not in hint


def test_two_decision_replies_the_check_empties_still_end_in_the_stage_failing(monkeypatch):
    prompts = _model_says(monkeypatch, EMPTIED_SUMMARY)
    request_id = _row()

    with pytest.raises(StageFailed) as stopped:
        _decide(request_id)

    assert stopped.value.stage == "consulting" and len(prompts) == settings.STAGE_REPLY_ATTEMPTS
    assert "$9,000" in stopped.value.cause and "COULD NOT BE USED" not in stopped.value.cause
    _fails_for_the_client_in_its_own_words(request_id, stopped, monkeypatch)


THIN_AFTER_THE_CHECK = [
    _hypothesis(1, "They lose $50,000 a year."), _hypothesis(2, "They lose 14 members a month."),
    _hypothesis(3, STATEMENTS[2])]
GOOD_EXPLANATIONS = [_hypothesis(1, STATEMENTS[0]), _hypothesis(2, STATEMENTS[1]), _hypothesis(3, STATEMENTS[2])]


def test_the_second_diagnosis_ask_names_the_emptied_explanations_and_their_numbers(monkeypatch):
    """H1 and H2 each had one sentence, and it held a number nobody gave, so one explanation
    is left and a diagnosis needs two. The retry says which, by id, and with which numbers."""
    sent = _model_says_by_template(monkeypatch, {
        "diagnose.j2": [{"hypotheses": THIN_AFTER_THE_CHECK}, {"hypotheses": GOOD_EXPLANATIONS}],
        "test_hypothesis.j2": TESTED, "challenge.j2": NOT_KILLED})
    request_id = _row()

    result = _diagnose(request_id)

    hint = _hint_after(sent["diagnose.j2"])
    assert [h["statement"] for h in result["hypotheses"]] == list(STATEMENTS)
    assert "- H1: the number $50,000" in hint and "- H2: the number 14" in hint and "H3" not in hint
    assert "at least 2 explanations" in hint and "{{F:id}}" in hint and "FIGURES YOU MAY USE" in hint
    assert "They lose" not in hint
    # only the diagnostician is told; the tests and the reviewers are asked as before
    assert not any("COULD NOT BE USED" in p for p in sent["test_hypothesis.j2"] + sent["challenge.j2"])
    assert _ledger(request_id)[:2] == [("diagnose:1", False), ("diagnose:1", True)]


def test_two_diagnosis_replies_the_check_empties_still_end_in_the_stage_failing(monkeypatch):
    sent = _model_says_by_template(monkeypatch, {
        "diagnose.j2": {"hypotheses": THIN_AFTER_THE_CHECK},
        "test_hypothesis.j2": TESTED, "challenge.j2": NOT_KILLED})
    request_id = _row()

    with pytest.raises(StageFailed) as stopped:
        _diagnose(request_id)

    assert stopped.value.stage == "diagnosing" and len(sent["diagnose.j2"]) == settings.STAGE_REPLY_ATTEMPTS
    assert "2 had no statement left" in stopped.value.cause and "COULD NOT BE USED" not in stopped.value.cause
    assert _read(request_id).diagnosis_json is None
    _fails_for_the_client_in_its_own_words(request_id, stopped, monkeypatch)


def test_a_diagnosis_with_enough_explanations_left_is_not_asked_again(monkeypatch):
    """Two of three keep a statement: the list shrinks to two and the diagnosis goes on, with no retry."""
    sent = _model_says_by_template(monkeypatch, {
        "diagnose.j2": {"hypotheses": [_hypothesis(1, "They lose $50,000 a year."),
                                       _hypothesis(2, STATEMENTS[1]), _hypothesis(3, STATEMENTS[2])]},
        "test_hypothesis.j2": TESTED, "challenge.j2": NOT_KILLED})

    result = _diagnose(_row())

    assert len(sent["diagnose.j2"]) == 1 and [h["id"] for h in result["hypotheses"]] == ["H2", "H3"]


def test_a_reply_that_was_thin_to_begin_with_is_asked_again_without_a_hint(monkeypatch):
    """The number check did not empty anything, so there is nothing to tell the model."""
    sent = _model_says_by_template(monkeypatch, {
        "diagnose.j2": [{"hypotheses": [_hypothesis(1, STATEMENTS[0])]}, {"hypotheses": GOOD_EXPLANATIONS}],
        "test_hypothesis.j2": TESTED, "challenge.j2": NOT_KILLED})

    _diagnose(_row())

    first, second = sent["diagnose.j2"]
    assert first == second


def test_retry_hint_says_one_two_or_many_numbers_and_never_a_sentence():
    hint = analyze.retry_hint("Problem.", {"a": ["48"], "b": ["48", "15"], "c": ["48", "15", "200"], "d": []}, "FIG")
    assert "- a: the number 48\n" in hint and "- b: the numbers 48 and 15\n" in hint
    assert "- c: the numbers 48, 15 and 200\n" in hint and "- d: a number that is not listed\n" in hint
    assert hint.endswith("FIG") and hint.startswith("YOUR LAST REPLY COULD NOT BE USED. Problem.")


# -- the log names the numbers that caused a drop ----------------------------------------------------

def test_the_log_names_the_unresolved_number_or_token_not_the_innocent_ones_in_the_same_sentence(monkeypatch, caplog):
    """'12 reformers' is the client's own and binds; '$9,000' and the unknown figure token are
    what made each sentence go. Only those are logged."""
    summary = ("You have 12 reformers and charge $9,000 a class. "
               "You have 12 reformers and pay {{F:CAP-99}} a week. Keep the price.")
    _model_says(monkeypatch, {**DECISION, "consulting_summary": summary})

    with caplog.at_level("INFO", logger="consultant.decide"):
        result = _decide(_row())

    line = _logged(caplog, "consultant.decide")
    assert result["consulting_summary"] == "Keep the price."
    assert "$9,000" in line and "{{F:CAP-99}}" in line and "consulting_summary" in line
    assert "12" not in line.split("numbers nobody gave:")[1].replace("$9,000", "")
    assert "reformers" not in line and "a class" not in line


# -- number words are checked like digits ---------------------------------------------------------

def test_a_number_word_nobody_gave_is_dropped_in_every_stage_and_one_they_gave_is_kept_as_written(monkeypatch):
    """Words stay words: a supported 'twelve' is not rewritten to '12'. That must not let
    a number written as a word through: 'twenty' is in nobody's figures and its sentence goes."""
    _model_says(monkeypatch, {
        "business_model": "Appointments", "target_customer_profile": "Members.",
        "pain_points": ["Twenty reformers sit idle in the mornings.", "Twelve reformers sit idle."],
        "growth_opportunity": "Fill the mornings. Twenty reformers sit idle."})
    result = _analyze(_row())
    assert result["pain_points"] == ["Twelve reformers sit idle."]
    assert result["growth_opportunity"] == "Fill the mornings."

    _model_says(monkeypatch, {**DECISION, "consulting_summary": "Fill the mornings. Twenty reformers sit idle. "
                                                                 "Twelve reformers stay."})
    assert _decide(_row())["consulting_summary"] == "Fill the mornings. Twelve reformers stay."

    _diagnosis_says(monkeypatch, [
        _hypothesis(1, "Evenings are full. Twenty reformers sit idle. Twelve reformers stay."),
        _hypothesis(2, STATEMENTS[1]), _hypothesis(3, STATEMENTS[2])])
    assert _diagnose(_row())["hypotheses"][0]["statement"] == "Evenings are full. Twelve reformers stay."


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
    """The columns `casefile.client_words` reads; a missing one reads as empty."""

    def __init__(self, ops, **columns):
        self.ops_numbers_json = ops
        for name, value in columns.items():
            setattr(self, name, value)


@pytest.mark.parametrize("ops, lines", [
    pytest.param(None, ["free"], id="no answers"),
    pytest.param("not json", ["free"], id="unreadable"),
    pytest.param(json.dumps({"q": "a"}), ["free"], id="not a list"),
    pytest.param(json.dumps([{"question": "Q1?", "answer": " a1 "}, {"question": "Q2?", "answer": "  "},
                             "junk", {"question": "", "answer": "a3"}, {"answer": 7}]),
                 ["Q1?: a1", "a3", "free"], id="only answered pairs, then the free words"),
])
def test_the_capacity_context_pairs_each_answer_with_its_question(ops, lines):
    assert orchestrator._capacity_context(_Row(ops, main_problem="free")) == lines


def test_the_capacity_context_lines_up_with_the_texts_the_numbers_are_checked_in():
    """The prompt's lines and the check's texts come from the same iterator, one for one."""
    row = _Row(json.dumps([{"question": "How many?", "answer": "12 reformers"}, {"answer": "6 a day"}]),
               main_problem="Evenings are full.", business_description="A studio.")

    context, texts = orchestrator._capacity_context(row), capacity.owner_texts(row)

    assert len(context) == len(texts) == 4
    assert [c.rsplit(": ", 1)[-1] for c in context] == texts
