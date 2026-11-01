"""The case file: what the client told us, stored as figures that say where each came from.

Pins: one theirs Figure per number in an interview answer, a free-text column or a
claim read out of an uploaded file, each with its turn, field, file and cell; ids
that do not move; a row made before the column existed still works and is not
written to by a read; the file figures follow the client's files (the whole case file
is rebuilt when they change); a failure of ours to build it never costs the client
their data; and nothing the model wrote (a brief fact, the scope question) becomes "theirs".
"""
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.figures import casefile
from app.figures.model import FigureSet, TheirsSource, display
from app.models import Request

DOT = "\u00b7"   # the middle dot in "<file> . <sheet> . <CELL>", written as an escape to keep this file ASCII


def _req(**fields) -> Request:
    base = dict(business_name="Halo Reformer Studio", business_description="A pilates studio.",
                email="owner@example.com")
    base.update(fields)
    return Request(**base)


def _pairs(*pairs: dict) -> str:
    return json.dumps(list(pairs))


def _claim(n: int, value=1240, file="bookings.csv", sheet="March", cell="B4", means="Bookings in March") -> dict:
    """A claim as evidence.extract writes it (app/pipeline/evidence.py)."""
    return {"id": f"CE-{n:02d}", "type": "client_fact", "value": value, "unit": "", "time_basis": "month",
            "population": "n/a", "scope": "engagement", "phase": "all", "provenance": "client_input",
            "approval_status": "client_stated", "source": f"{file} {DOT} {sheet} {DOT} {cell}",
            "allowed_sections": ["*"], "text": means, "origin": "file", "cell": cell, "file": file}


def _by_id(figures) -> dict:
    return {f.id: f for f in figures}


# -- build: where each figure comes from -------------------------------------------------

def test_each_number_they_gave_is_a_figure_that_says_where_it_came_from():
    req = _req(
        business_description="We run a studio with twelve reformers. Classes cost $22.50.",
        main_problem="Evenings are full but the daytime classes are at 40%.",
        ops_numbers_json=_pairs(
            {"id": "q1", "question": "How many reformers?", "answer": "12, and 6 classes a day"},
            {"question": "What do you charge?", "answer": "$22 a class"}),
        evidence_json=json.dumps([_claim(3)]))
    figs = _by_id(casefile.build(req))

    first = figs["T1-1"]
    assert (first.kind, first.value) == ("theirs", Decimal(12))
    assert first.source == TheirsSource(turn=1, field="q1", quote="12, and 6 classes a day", file=None, cell=None)
    assert figs["T1-2"].value == Decimal(6) and figs["T1-2"].source.turn == 1

    price = figs["T2-1"]   # no question id was sent for this pair
    assert (price.value, price.unit, price.source.turn, price.source.field) == (Decimal(22), "USD", 2, None)

    word = figs["F-business_description-1"]   # "twelve" counts
    assert word.value == Decimal(12) and word.unit == ""
    assert word.source == TheirsSource(turn=None, field="business_description",
                                       quote="We run a studio with twelve reformers.", file=None, cell=None)
    cost = figs["F-business_description-2"]
    assert (cost.value, cost.unit, display(cost)) == (Decimal("22.50"), "USD", "$22.50")   # cents stay
    pct = figs["F-main_problem-1"]
    assert (pct.value, pct.unit, pct.source.field) == (Decimal(40), "percent", "main_problem")

    cell = figs["E3-1"]   # CE-03
    assert (cell.value, cell.source.file, cell.source.cell, cell.source.field) == (
        Decimal(1240), "bookings.csv", "B4", "March")
    assert cell.source.turn is None and cell.kind == "theirs"
    assert len(figs) == 7


def test_an_answer_with_three_numbers_gives_three_figures_on_the_same_turn():
    req = _req(ops_numbers_json=_pairs(
        {"question": "Warm-up?", "answer": "skip"},
        {"id": "q2", "question": "How big are you?", "answer": "We have 12 reformers, 6 classes a day and 8 coaches."}))
    got = casefile.build(req)
    assert [(f.id, f.value, f.source.turn) for f in got] == [
        ("T2-1", Decimal(12), 2), ("T2-2", Decimal(6), 2), ("T2-3", Decimal(8), 2)]


def test_a_number_written_as_a_word_is_a_figure():
    req = _req(ops_numbers_json=_pairs({"question": "How many?", "answer": "twelve reformers"}))
    [fig] = casefile.build(req)
    assert (fig.value, fig.source.quote) == (Decimal(12), "twelve reformers")


def test_a_request_with_no_numbers_has_an_empty_case_file():
    req = _req(main_problem="Bookings are a mess.", ops_numbers_json=_pairs({"question": "Why?", "answer": "no idea"}))
    assert casefile.build(req) == []
    assert len(casefile.load(req)) == 0


def test_ids_are_unique_and_do_not_change_between_builds():
    req = _req(
        business_description="12 reformers and 12 classes. We charge $22 and $22.",
        main_problem="12 12 12",
        ops_numbers_json=_pairs({"question": "a", "answer": "12 or 12"}, {"question": "b", "answer": "12"}),
        evidence_json=json.dumps([_claim(1, 12), _claim(2, 12, file="other.csv")]))
    first, second = casefile.build(req), casefile.build(req)
    assert first == second
    ids = [f.id for f in first]
    assert len(ids) == len(set(ids)) and len(ids) >= 10
    assert len(FigureSet(first)) == len(ids)   # a FigureSet refuses two figures under one id


def test_evidence_ids_follow_the_claim_id_so_removing_one_claim_renumbers_nothing():
    both = casefile.build(_req(evidence_json=json.dumps([_claim(1, 100), _claim(2, 200, cell="B5")])))
    only_second = casefile.build(_req(evidence_json=json.dumps([_claim(2, 200, cell="B5")])))
    assert [f.id for f in both] == ["E1-1", "E2-1"]
    assert only_second == [both[1]]


def test_two_claims_that_share_an_id_still_get_two_ids():
    # evidence.extract numbers from len(existing), so a removal then an upload can repeat CE-02
    got = casefile.build(_req(evidence_json=json.dumps([_claim(2, 100), _claim(2, 200, file="again.csv")])))
    assert len({f.id for f in got}) == 2 and {f.value for f in got} == {Decimal(100), Decimal(200)}


def test_a_claim_value_is_read_the_way_the_cell_shows_it():
    claims = [_claim(1, "$1,240.00"), _claim(2, 0.07), _claim(3, 1240.0), _claim(4, "25%"), _claim(5, "n/a"),
              _claim(6, True), {"id": "CE-07", "file": "x.csv"}, "junk"]
    got = _by_id(casefile.build(_req(evidence_json=json.dumps(claims))))
    assert (got["E1-1"].value, got["E1-1"].unit) == (Decimal("1240.00"), "USD")
    assert got["E2-1"].value == Decimal("0.07") and got["E2-1"].precision == 2
    assert got["E3-1"].value == Decimal(1240) and got["E3-1"].precision == 0
    assert (got["E4-1"].value, got["E4-1"].unit) == (Decimal(25), "percent")
    assert sorted(got) == ["E1-1", "E2-1", "E3-1", "E4-1"]


def test_the_unit_comes_from_how_the_number_was_written_and_never_claims_a_currency_it_cannot_see():
    text = ("It costs $35, \u20ac40, \u00a345, A$50, US$55, 60 USD, 65 dollars and 70 percent; "
            "we have 75 staff.")
    req = _req(main_problem=text)
    units = {f.value: f.unit for f in casefile.build(req)}
    assert units == {Decimal(35): "USD", Decimal(40): "EUR", Decimal(45): "GBP", Decimal(50): "",
                     Decimal(55): "USD", Decimal(60): "USD", Decimal(65): "USD",
                     Decimal(70): "percent", Decimal(75): ""}


def test_a_currency_code_written_with_the_amount_beats_the_sign_beside_it():
    req = _req(main_problem="Fees are $80 AUD, $90 CAD, CAD 100, \u20ac110 USD, and $120.")
    units = {f.value: f.unit for f in casefile.build(req)}
    assert units == {Decimal(80): "AUD", Decimal(90): "CAD", Decimal(100): "CAD", Decimal(110): "USD",
                     Decimal(120): "USD"}


def test_a_fraction_is_stored_as_a_percent_so_it_prints_with_its_sign():
    req = _req(main_problem="A third of members come on Fridays.")
    [fig] = casefile.build(req)
    assert (fig.unit, fig.value) == ("percent", Decimal("33.3333"))
    assert display(fig).endswith("%")


def _units(text: str) -> list:
    return [(f.value, f.unit) for f in casefile.build(_req(main_problem=text))]


def test_a_number_directly_followed_by_a_time_word_carries_that_unit():
    assert _units("Onboarding takes twelve weeks.") == [(Decimal(12), "week")]
    assert _units("We lose 8 hrs a week.") == [(Decimal(8), "hour")]   # the rate phrase does not change it
    assert _units("The lease has 3 months left.") == [(Decimal(3), "month")]
    assert _units("A 6-month trial, 5hrs, 2 yrs, 4 mos, 9 min and 1 wk.") == [
        (Decimal(6), "month"), (Decimal(5), "hour"), (Decimal(2), "year"), (Decimal(4), "month"),
        (Decimal(9), "minute"), (Decimal(1), "week")]
    [fig] = casefile.build(_req(main_problem="Onboarding takes twelve weeks."))
    assert display(fig) == "12 weeks"


def test_other_nouns_and_positions_stay_without_a_unit():
    assert _units("We have 12 reformers and 6 classes a day.") == [(Decimal(12), ""), (Decimal(6), "")]
    assert _units("We have 12 weekend slots.") == [(Decimal(12), "")]   # weekend is not week
    assert _units("It was the 3rd week, and 4x weeks.") == [(Decimal(3), ""), (Decimal(4), "")]   # a place, a factor
    assert _units("Open 7\n\nweeks") == [(Decimal(7), "")]   # not directly followed


def test_money_and_percent_keep_their_units_beside_a_time_word():
    assert _units("It is $80 a month, 70% a year and $9 per week.") == [
        (Decimal(80), "USD"), (Decimal(70), "percent"), (Decimal(9), "USD")]


def test_a_files_value_with_a_time_word_carries_it_too():
    [fig] = casefile.build(_req(evidence_json=json.dumps([_claim(1, "12 weeks")])))
    assert (fig.value, fig.unit) == (Decimal(12), "week")


def test_a_figure_prints_the_value_they_gave_without_the_zeros_a_magnitude_adds():
    req = _req(main_problem="We make 1.5k a month; the best day was $1,240.00; fill is 12.50%; and twelve staff.")
    assert [display(f) for f in casefile.build(req)] == ["1,500", "$1,240", "12.5%", "12"]


def test_a_time_or_a_date_is_not_a_figure():
    # read.supported() passes these by their form, and an "18" made from 6pm would
    # vouch for 18 reformers
    req = _req(main_problem="We open at 6pm on 31 Oct 2025, and 12 people come.")
    assert [f.value for f in casefile.build(req)] == [Decimal(12)]


def test_the_quote_is_the_sentence_the_number_sits_in():
    req = _req(main_problem="We are at 40% in the day. Evenings are full, 12 of 12 on Fridays!\n"
                            "Mondays are slow: 3 or 4 people turn up")
    quotes = {f.value: f.source.quote for f in casefile.build(req)}
    assert quotes[Decimal(40)] == "We are at 40% in the day."
    assert quotes[Decimal(12)] == "Evenings are full, 12 of 12 on Fridays!"
    assert quotes[Decimal(3)] == quotes[Decimal(4)] == "Mondays are slow: 3 or 4 people turn up"


def test_a_decimal_point_or_an_abbreviation_does_not_end_the_sentence():
    req = _req(main_problem="Classes are $22.50 each and run until 6 p.m. on weekdays. Then 3 staff close.")
    quotes = [f.source.quote for f in casefile.build(req)]
    assert quotes[0] == "Classes are $22.50 each and run until 6 p.m. on weekdays."
    assert quotes[-1] == "Then 3 staff close."


def test_a_long_sentence_is_cut_around_the_number():
    long = "word " * 200
    req = _req(main_problem=f"{long}we have 12 reformers {long}")
    [fig] = casefile.build(req)
    quote = fig.source.quote
    assert "12" in quote and len(quote) <= casefile.QUOTE_MAX + 2   # + the two ellipses
    assert quote.startswith("\u2026") and quote.endswith("\u2026")


def test_a_text_is_read_only_up_to_its_bound():
    far = "x " * casefile.MAX_TEXT_CHARS
    req = _req(main_problem=f"We have 12 reformers. {far} and 99 more.")
    assert [f.value for f in casefile.build(req)] == [Decimal(12)]


def test_the_same_words_in_two_columns_are_read_once():
    words = "We have 12 reformers"
    req = _req(business_description=words, desired_outcome=f" {words} ", main_problem="Fill 9 slots")
    ids = [f.id for f in casefile.build(req)]
    assert ids == ["F-business_description-1", "F-main_problem-1"]


# -- build: only their own words ----------------------------------------------------------

def test_a_brief_fact_that_is_not_in_a_quote_of_their_words_is_never_theirs():
    brief = {"question": "Should Halo raise its evening prices?",
             "facts": [{"key": "price", "label": "What you charge", "status": "estimate", "value": "$4,700"},
                       {"key": "fill", "label": "Evening fill", "status": "got", "value": "11 of 12"}]}
    req = _req(brief_json=json.dumps(brief), main_problem="We charge $35 a class.",
               ops_numbers_json=_pairs({"question": "How full?", "answer": "10 of 12 on a good night"}))
    values = sorted(f.value for f in casefile.build(req))
    assert values == [Decimal(10), Decimal(12), Decimal(35)]   # not 4700, not 11
    assert not any(f.source.quote in ("$4,700", "11 of 12") for f in casefile.build(req))


def test_a_brief_value_the_client_also_wrote_comes_from_their_words_with_the_quote():
    brief = {"facts": [{"key": "price", "label": "What you charge", "status": "got", "value": "$35"}]}
    req = _req(brief_json=json.dumps(brief), main_problem="We charge $35 a class.")
    [fig] = casefile.build(req)
    assert (fig.value, fig.source.field, fig.source.quote) == (Decimal(35), "main_problem", "We charge $35 a class.")


def test_what_the_intake_adds_to_the_description_is_ours_not_theirs():
    # create_request appends the scope question and the facts they did not know to
    # the description; the question is written by the interview, not by them
    description = ("A studio with 6 coaches."
                   f"\n\n{casefile.UNKNOWNS_NOTE} - estimate these:\n- Rent for the 2nd floor"
                   f"\n\n{casefile.QUESTION_NOTE} Should we move 4 classes to evenings?")
    req = _req(business_description=description,
               brief_json=json.dumps({"question": "Should we move 4 classes to evenings?"}),
               desired_outcome="Should we move 4 classes to evenings?")
    assert [f.value for f in casefile.build(req)] == [Decimal(6)]


def test_an_outcome_they_wrote_themselves_is_theirs():
    req = _req(desired_outcome="Fill 3 more classes", brief_json=json.dumps({"question": "Should we raise prices?"}))
    assert [f.value for f in casefile.build(req)] == [Decimal(3)]


def test_a_correction_they_sent_later_is_in_their_words():
    req = _req(business_description="A studio.\n\nCorrections and additions from the briefing chat:\n- It is 11 of 12.")
    assert [f.value for f in casefile.build(req)] == [Decimal(11), Decimal(12)]


@pytest.mark.parametrize("bad", ["not json", "{}", "[1, 2]", json.dumps([{"question": "q"}]), json.dumps([None])])
def test_malformed_stored_answers_give_no_figures_and_no_error(bad):
    assert casefile.build(_req(ops_numbers_json=bad, evidence_json=bad)) == []


# -- load: stored, or built on read for an old row -----------------------------------------------

@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _persist(db, **fields) -> Request:
    row = _req(**{"owner_email": "test@example.com", "status": "done", "is_generating": False, **fields})
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _fresh(row_id: int) -> Request:
    other = SessionLocal()
    try:
        row = other.get(Request, row_id)
        other.expunge(row)
        return row
    finally:
        other.close()


def test_a_row_made_before_this_step_loads_without_error_and_is_not_written(db):
    row = _persist(db, main_problem="We lose 8 hours a week.",
                   ops_numbers_json=_pairs({"question": "How many?", "answer": "twelve"}))
    assert row.case_file_json is None
    loaded = casefile.load(row)
    assert sorted(f.value for f in loaded) == [Decimal(8), Decimal(12)]
    assert row.case_file_json is None
    assert not db.dirty and not db.new
    db.commit()
    assert _fresh(row.id).case_file_json is None


def test_load_reads_the_stored_case_file_not_the_columns(db):
    row = _persist(db, main_problem="We lose 8 hours a week.")
    casefile.save(db, row)
    db.commit()
    stored = _fresh(row.id)
    stored.main_problem = "We lose 9 hours a week and 11 minutes."   # the text moved on; the store has not
    assert [f.value for f in casefile.load(stored)] == [Decimal(8)]


def _stored_figure(value: str) -> dict:
    return {"id": "T1-1", "value": value, "unit": "", "period": None, "kind": "theirs", "precision": 0,
            "source": {"turn": 1, "field": None, "quote": value, "file": None, "cell": None}}


@pytest.mark.parametrize("bad", [
    "not json", "{}", '[{"id": "x"}]', "[1]",
    json.dumps([_stored_figure("1"), _stored_figure("2")]),   # two different figures under one id
])
def test_an_unreadable_stored_case_file_is_built_again_not_raised(bad):
    req = _req(main_problem="We lose 8 hours a week.", case_file_json=bad)
    assert [f.value for f in casefile.load(req)] == [Decimal(8)]


def test_an_empty_case_file_is_stored_as_empty_not_as_missing(db):
    row = _persist(db, main_problem="Bookings are a mess.")
    casefile.save(db, row)
    db.commit()
    assert _fresh(row.id).case_file_json == "[]"


def test_save_stages_the_case_file_and_leaves_the_commit_to_the_caller(db):
    row = _persist(db, main_problem="We lose 8 hours a week.")
    casefile.save(db, row)
    assert _fresh(row.id).case_file_json is None   # not committed yet
    db.commit()
    stored = json.loads(_fresh(row.id).case_file_json)
    assert [(f["id"], f["kind"], f["value"]) for f in stored] == [("F-main_problem-1", "theirs", "8")]


# -- the client's files ----------------------------------------------------------------------

def test_removing_a_file_removes_only_its_figures(db):
    from app.pipeline import evidence

    a1, b1, a2 = _claim(1, 100, file="a.csv"), _claim(2, 200, file="b.csv"), _claim(3, 300, file="a.csv", cell="C9")
    row = _persist(db, main_problem="We lose 8 hours a week.")
    evidence.save(db, row, [a1, b1, a2])
    assert len(casefile.load(_fresh(row.id))) == 4

    evidence.save(db, row, [b1])   # both claims from a.csv go
    left = casefile.load(_fresh(row.id))
    assert sorted((f.id, f.value) for f in left) == [("E2-1", Decimal(200)), ("F-main_problem-1", Decimal(8))]


def test_saving_evidence_keeps_the_case_file_in_the_same_commit(db):
    from app.pipeline import evidence

    row = _persist(db, main_problem="We lose 8 hours a week.")
    evidence.save(db, row, [_claim(1, 100), _claim(2, 200, file="b.csv")])
    stored = _fresh(row.id)
    assert sorted(f.id for f in casefile.load(stored)) == ["E1-1", "E2-1", "F-main_problem-1"]
    assert stored.case_file_json is not None   # written, not built on read

    evidence.save(db, row, [_claim(2, 200, file="b.csv")])   # CE-01 removed
    assert sorted(f.id for f in casefile.load(_fresh(row.id))) == ["E2-1", "F-main_problem-1"]
    evidence.save(db, row, [])
    assert [f.id for f in casefile.load(_fresh(row.id))] == ["F-main_problem-1"]


# -- the routes ------------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    from app.config import settings
    from app.routers import requests as requests_router
    from main import app

    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(requests_router.orchestrator, "run", lambda request_id: None)
    monkeypatch.setattr(settings, "MAX_CONCURRENT_GENERATIONS", 10_000)
    return TestClient(app)


def _intake(**overrides) -> dict:
    form = {"business_name": "Halo", "business_description": "A pilates studio with twelve reformers.",
            "email": "owner@example.com"}
    form.update(overrides)
    return form


def test_create_request_writes_the_case_file_in_the_same_commit_as_the_row(client):
    statements: list[tuple[str, object]] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append((statement, parameters))

    pairs = [{"id": "q1", "question": "How full is a class?", "answer": "About 10 of 12"}]
    event.listen(engine, "before_cursor_execute", capture)
    try:
        r = client.post("/api/requests", data=_intake(
            ops_numbers=json.dumps(pairs), main_problem="We lose about 8 hours a week."))
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert r.status_code == 200

    sql = [(s.lstrip().upper(), p) for s, p in statements]
    inserts = [(s, p) for s, p in sql if s.startswith("INSERT INTO REQUESTS")]
    assert len(inserts) == 1 and "CASE_FILE_JSON" in inserts[0][0]
    assert not [s for s, _ in sql if s.startswith("UPDATE REQUESTS") and "CASE_FILE_JSON" in s]

    row = _fresh(r.json()["id"])
    figures = {f.id: f for f in casefile.load(row)}
    assert row.case_file_json is not None   # stored with the row, not built on read
    assert figures["T1-1"].source == TheirsSource(turn=1, field="q1", quote="About 10 of 12", file=None, cell=None)
    assert sorted(figures) == ["F-business_description-1", "F-main_problem-1", "T1-1", "T1-2"]


def test_the_question_id_they_sent_is_kept_trimmed_and_bounded_and_nothing_else_is_added():
    from app.routers import requests as requests_router

    long_id = "q" * (requests_router.QUESTION_ID_MAX + 30)
    raw = json.dumps([
        {"id": "  q1  ", "question": "How full?", "answer": "10 of 12"},
        {"id": long_id, "question": "How many?", "answer": "12"},
        {"question": "No id sent", "answer": "5"},
        {"id": "   ", "question": "Blank id", "answer": "6"},
        {"id": ["q9"], "question": "Not text", "answer": "7"},
        {"id": True, "question": "A flag", "answer": "8"},
        {"id": 4, "question": "A number", "answer": "9"},
    ])
    kept = json.loads(requests_router._sanitize_ops_numbers(raw))
    assert kept[0] == {"id": "q1", "question": "How full?", "answer": "10 of 12"}
    assert kept[1]["id"] == "q" * requests_router.QUESTION_ID_MAX
    assert "id" not in kept[2] and "id" not in kept[3] and "id" not in kept[4] and "id" not in kept[5]
    assert kept[6]["id"] == "4"
    assert requests_router.QUESTION_ID_MAX >= 40   # the interview's ids are cut to 40 (discovery.casefile_sources)


def test_a_question_id_is_kept_only_if_it_is_made_of_letters_digits_and_a_few_marks():
    from app.routers import requests as requests_router

    ids = ["a b", "q;1", "<b>", "a/b", "q1\nq2", "q'1", "field:evil_x", "A.b-c_d:9"]
    raw = json.dumps([{"id": i, "question": "Q?", "answer": "1"} for i in ids])
    kept = json.loads(requests_router._sanitize_ops_numbers(raw))
    assert [p.get("id") for p in kept] == [None, None, None, None, None, None, "field:evil_x", "A.b-c_d:9"]
    assert all(p["question"] == "Q?" and p["answer"] == "1" for p in kept)   # the pair itself is kept


def test_a_failure_to_build_the_case_file_does_not_stop_an_engagement_starting(client, monkeypatch):
    def broken(db, req):
        raise RuntimeError("the reader fell over")

    monkeypatch.setattr(casefile, "save", broken)
    r = client.post("/api/requests", data=_intake())
    assert r.status_code == 200
    row = _fresh(r.json()["id"])
    assert row.case_file_json is None and len(casefile.load(row)) == 1   # built on read, as an old row is


def test_the_description_the_intake_assembles_is_read_without_the_parts_we_added(client):
    brief = {"question": "Should Halo move 4 classes to evenings?", "facts": []}
    r = client.post("/api/requests", data=_intake(
        brief=json.dumps(brief), unknowns=json.dumps(["Rent for the 2nd floor"]),
        business_description="A studio with 6 coaches."))
    assert r.status_code == 200
    row = _fresh(r.json()["id"])
    assert "Should Halo move 4 classes" in row.business_description
    assert row.desired_outcome == brief["question"]
    assert [f.value for f in casefile.load(row)] == [Decimal(6)]
    assert json.loads(row.case_file_json)[0]["value"] == "6"


def test_deleting_a_claim_through_the_route_takes_only_its_figure_out_of_the_case_file(client, db):
    row = _persist(db, public_id="casefile-del", main_problem="We lose 8 hours a week.",
                   evidence_json=json.dumps([_claim(1, 100), _claim(2, 200, cell="B5")]))
    from app.pipeline import evidence
    evidence.save(db, row, json.loads(row.evidence_json))

    r = client.delete(f"/api/requests/{row.public_id}/evidence/CE-01")
    assert r.status_code == 200
    assert sorted(f.id for f in casefile.load(_fresh(row.id))) == ["E2-1", "F-main_problem-1"]
    assert _fresh(row.id).case_file_json is not None


def test_uploading_a_file_through_the_route_adds_its_figures_to_the_case_file(client, db, monkeypatch):
    from app.routers import requests as requests_router

    row = _persist(db, public_id="casefile-add", main_problem="We lose 8 hours a week.")
    monkeypatch.setattr(requests_router.evidence, "extract",
                        lambda db_, rid, tables, name, start_index=0: ([_claim(start_index + 1, 310, file=name)], 0))
    r = client.post(f"/api/requests/{row.public_id}/evidence",
                    files={"file": ("march.csv", b"day,bookings\n1,310\n2,290\n", "text/csv")})
    assert r.status_code == 200 and r.json()["added"] == 1
    got = {f.id: f for f in casefile.load(_fresh(row.id))}
    assert got["E1-1"].source.file == "march.csv" and got["E1-1"].value == Decimal(310)
    assert "F-main_problem-1" in got


def _break_the_case_file(monkeypatch):
    def fell_over(req):
        raise RuntimeError("the reader fell over")

    monkeypatch.setattr(casefile, "build", fell_over)


def _file_gives(monkeypatch, value=310):
    from app.pipeline import evidence

    monkeypatch.setattr(evidence, "extract", lambda db_, rid, tables, name, start_index=0:
                        ([_claim(start_index + 1, value, file=name)], 0))


def test_an_upload_is_kept_when_the_case_file_cannot_be_built(client, db, monkeypatch):
    row = _persist(db, public_id="casefile-boom", main_problem="We lose 8 hours a week.")
    casefile.save(db, row)
    db.commit()
    assert _fresh(row.id).case_file_json is not None   # one is stored, and about to be out of date
    _file_gives(monkeypatch)
    _break_the_case_file(monkeypatch)

    r = client.post(f"/api/requests/{row.public_id}/evidence",
                    files={"file": ("march.csv", b"day,bookings\n1,310\n2,290\n", "text/csv")})
    assert r.status_code == 200 and r.json()["added"] == 1
    stored = _fresh(row.id)
    assert [c["id"] for c in json.loads(stored.evidence_json)] == ["CE-01"]   # the client's file is kept
    assert stored.case_file_json is None   # not left stale: the next read builds it again


def test_a_deleted_claim_is_gone_even_when_the_case_file_cannot_be_built(client, db, monkeypatch):
    row = _persist(db, public_id="casefile-boom-del", main_problem="We lose 8 hours a week.",
                   evidence_json=json.dumps([_claim(1, 100), _claim(2, 200, cell="B5")]))
    _break_the_case_file(monkeypatch)
    r = client.delete(f"/api/requests/{row.public_id}/evidence/CE-01")
    assert r.status_code == 200
    stored = _fresh(row.id)
    assert [c["id"] for c in json.loads(stored.evidence_json)] == ["CE-02"] and stored.case_file_json is None


def test_a_stashed_file_is_not_dropped_when_the_case_file_cannot_be_built(db, monkeypatch):
    from app.pipeline import evidence

    row = _persist(db, main_problem="We lose 8 hours a week.")
    evidence.stash(row.id, "march.csv", b"day,bookings\n1,310\n2,290\n")
    _file_gives(monkeypatch)
    _break_the_case_file(monkeypatch)

    assert evidence.ingest_pending(db, row.id) == [("march.csv", 1)]   # read, not counted as nothing found
    stored = _fresh(row.id)
    assert [c["id"] for c in json.loads(stored.evidence_json)] == ["CE-01"] and stored.case_file_json is None


def test_a_correction_that_cannot_reach_the_case_file_is_still_saved(client, db, monkeypatch):
    row = _persist(db, public_id="casefile-boom-rev", status="awaiting_approval", is_generating=False,
                   main_problem="We lose 8 hours a week.")
    casefile.save(db, row)
    db.commit()
    _break_the_case_file(monkeypatch)
    r = client.post(f"/api/requests/{row.public_id}/decision/revise",
                    data={"note": "You have the evening numbers wrong, it is 11 of 12."})
    assert r.status_code == 200 and r.json()["started"] is True
    stored = _fresh(row.id)
    assert "11 of 12" in stored.business_description and stored.case_file_json is None


def test_a_correction_they_send_through_the_route_reaches_the_case_file(client, db):
    row = _persist(db, public_id="casefile-rev", status="awaiting_approval", is_generating=False,
                   main_problem="We lose 8 hours a week.")
    r = client.post(f"/api/requests/{row.public_id}/decision/revise",
                    data={"note": "You have the evening numbers wrong, it is 11 of 12."})
    assert r.status_code == 200 and r.json()["started"] is True
    got = casefile.load(_fresh(row.id))
    assert sorted(f.value for f in got) == [Decimal(8), Decimal(11), Decimal(12)]
    assert _fresh(row.id).case_file_json is not None


def test_the_interview_case_file_says_the_figures_are_theirs_in_plain_words(client, monkeypatch):
    from app.pipeline import capacity
    from app.routers import discovery

    reply = {"figures": [
        {"source": "q2", "token": "About 10 of 12", "value": "10 of 12", "label": "a typical class"},
        {"source": "main_problem", "token": "about 8 hours a week", "value": "8 hrs", "label": "a week on bookings"},
        {"source": "field:business_description", "token": "6 therapists", "value": "6", "label": "therapists"},
    ]}
    monkeypatch.setattr(discovery.provider, "chat", lambda *a, **k: {
        "choices": [{"message": {"content": json.dumps(reply)}}], "usage": {}})
    monkeypatch.setattr(capacity, "read", lambda texts, stage="operating", earlier=None: (None, None, None))

    r = client.post("/api/discovery/casefile", data={
        "main_problem": "I spend about 8 hours a week juggling bookings on WhatsApp",
        "ops_numbers": json.dumps([{"id": "q2", "question": "How full is a typical class?",
                                    "answer": "About 10 of 12. The 6pm ones have a waiting list."}]),
        "known": json.dumps({"business_description": "A physio clinic with 6 therapists."}),
    })
    assert r.status_code == 200
    figures = {f["value"]: f for f in r.json()["figures"]}
    assert set(figures) == {"10 of 12", "8 hrs", "6"}
    assert all(f["kind"] == "theirs" for f in figures.values())
    assert figures["10 of 12"]["source"] == 'From your answer to "How full is a typical class?"'
    assert figures["8 hrs"]["source"] == "From what you told us about the problem"
    assert figures["6"]["source"] == "From what you wrote about your business description"
    assert figures["10 of 12"]["source_id"] == "q2"   # the id the page sent is still there
    assert figures["10 of 12"]["token"] == "About 10 of 12" and figures["10 of 12"]["label"] == "a typical class"


def test_a_long_question_is_shortened_in_the_plain_source():
    from app.routers import discovery

    question = "How " + "much " * 60 + "does it cost?"
    lines = discovery.casefile_lines(None, json.dumps([{"id": "q1", "question": question, "answer": "$5"}]), "{}")
    assert lines.origins["q1"].startswith('From your answer to "How much') and len(lines.origins["q1"]) < 200
    assert lines.sources["q1"].startswith(question[:200])
    assert lines.theirs["q1"] == "$5"   # the answer alone


def test_the_plain_source_follows_the_kind_of_line_not_the_id_the_page_sent():
    from app.routers import discovery

    ops = json.dumps([{"id": "field:evil_x", "question": "How many reformers?", "answer": "We have 12"},
                      {"id": "main_problem_2", "question": "How full?", "answer": "10 of 12"}])
    lines = discovery.casefile_lines("Bookings eat 8 hours.", ops, json.dumps({"business_description": "6 coaches"}))
    assert lines.origins["field:evil_x"] == 'From your answer to "How many reformers?"'
    assert lines.origins["main_problem_2"] == 'From your answer to "How full?"'
    assert lines.origins["main_problem"] == "From what you told us about the problem"
    assert lines.origins["field:business_description"] == "From what you wrote about your business description"
    raw = {"figures": [{"source": "field:evil_x", "token": "We have 12", "value": "12", "label": "reformers"}]}
    [fig] = discovery.shape_casefile(raw, lines.sources, False, None, lines.origins, lines.theirs)["figures"]
    assert fig["source"] == 'From your answer to "How many reformers?"' and fig["source_id"] == "field:evil_x"
    # with no origins given, the sentence does not guess from the id either
    [bare] = discovery.shape_casefile(raw, lines.sources, False)["figures"]
    assert bare["source"] == "From what you told us"


def test_a_number_only_in_our_question_is_not_theirs():
    from app.routers import discovery

    ops = json.dumps([{"id": "q1", "question": "Is it true you run 5 classes a day and charge $35?",
                       "answer": "Yes, roughly. About 12 reformers."}])
    lines = discovery.casefile_lines(None, ops, "{}")

    def shaped(token, value, label):
        raw = {"figures": [{"source": "q1", "token": token, "value": value, "label": label}]}
        return discovery.shape_casefile(raw, lines.sources, False, None, lines.origins, lines.theirs)["figures"]

    assert shaped("5 classes a day", "5", "classes a day") == []   # only our question says it
    assert shaped("$35", "$35", "the price") == []
    assert shaped("About 12 reformers", "12", "5 classes a day") == []   # a label may not bring our number in either
    [kept] = shaped("About 12 reformers", "12", "reformers")
    assert kept["kind"] == "theirs" and kept["source"].startswith("From your answer to")
    # given only the whole line (the old call), the question's number was accepted: that is what this fixes
    old = {"figures": [{"source": "q1", "token": "5 classes a day", "value": "5", "label": "classes a day"}]}
    assert len(discovery.shape_casefile(old, lines.sources, False)["figures"]) == 1


def test_the_playback_quotes_their_words_and_their_fix_from_their_answer_not_our_question():
    from app.routers import discovery

    question = "Would a 3-month booking app fix this?"

    def played_back(answer, **raw):
        lines = discovery.casefile_lines(None, json.dumps([{"id": "q1", "question": question, "answer": answer}]), "{}")
        return discovery.shape_casefile({"figures": [], **raw}, lines.sources, True, None, lines.origins, lines.theirs)

    # the model repeats our suggestion as if it were theirs: neither passes
    out = played_back("Yes, I think so.", their_fix="a 3-month booking app", their_words="a 3-month booking app")
    assert out["their_fix"] is None and out["their_words"] == ""
    # the same words in their own answer are theirs
    out = played_back("Yes, a 3-month booking app would fix it.",
                      their_fix="a 3-month booking app", their_words="a 3-month booking app would fix it")
    assert out["their_fix"] == "a 3-month booking app" and out["their_words"] == "a 3-month booking app would fix it"
    # a time only our question mentions is not a time they gave
    ops = [{"id": "q1", "question": "Is 6pm the best time?", "answer": "Yes, evenings."}]
    lines = discovery.casefile_lines(None, json.dumps(ops), "{}")
    out = discovery.shape_casefile({"their_fix": "booking from 6pm"}, lines.sources, True, None, lines.origins,
                                   lines.theirs)
    assert out["their_fix"] is None
    ops[0]["answer"] = "Yes, 6pm."
    lines = discovery.casefile_lines(None, json.dumps(ops), "{}")
    out = discovery.shape_casefile({"their_fix": "booking from 6pm"}, lines.sources, True, None, lines.origins,
                                   lines.theirs)
    assert out["their_fix"] == "booking from 6pm"


def test_the_interview_route_does_not_call_a_number_from_our_question_theirs(client, monkeypatch):
    from app.pipeline import capacity
    from app.routers import discovery

    reply = {"figures": [
        {"source": "q1", "token": "5 classes a day", "value": "5", "label": "classes a day"},
        {"source": "q1", "token": "About 12 reformers", "value": "12", "label": "reformers"}]}
    monkeypatch.setattr(discovery.provider, "chat", lambda *a, **k: {
        "choices": [{"message": {"content": json.dumps(reply)}}], "usage": {}})
    monkeypatch.setattr(capacity, "read", lambda texts, stage="operating", earlier=None: (None, None, None))
    r = client.post("/api/discovery/casefile", data={"ops_numbers": json.dumps([
        {"id": "q1", "question": "Is it true you run 5 classes a day and charge $35?",
         "answer": "Yes, roughly. About 12 reformers."}])})
    assert [f["value"] for f in r.json()["figures"]] == ["12"]


# -- the column ------------------------------------------------------------------------------

def test_a_table_made_before_this_column_gets_it_and_its_rows_still_work(tmp_path, monkeypatch):
    from app import database

    old = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    try:
        Base.metadata.create_all(old)
        with Session(old) as s:
            s.add(_req(business_name="Old Co", main_problem="We lose 8 hours a week.", status="done",
                       is_generating=False))
            s.commit()
        with old.begin() as conn:   # the table as it was before this step
            conn.exec_driver_sql("ALTER TABLE requests DROP COLUMN case_file_json")
        assert "case_file_json" not in {c["name"] for c in inspect(old).get_columns("requests")}

        monkeypatch.setattr(database, "engine", old)
        database._ensure_columns()
        database._ensure_columns()   # idempotent

        assert "case_file_json" in {c["name"] for c in inspect(old).get_columns("requests")}
        with Session(old) as s:
            row = s.query(Request).one()
            assert row.case_file_json is None
            assert [f.value for f in casefile.load(row)] == [Decimal(8)]
    finally:
        old.dispose()


def test_a_run_of_punctuation_does_not_make_the_sentence_split_take_quadratic_time():
    """Hostile or accidental text in a form field (50,000 dots) must split in milliseconds."""
    import time

    from app.figures import casefile

    text = "." * casefile.MAX_TEXT_CHARS + "x"
    started = time.perf_counter()
    casefile._sentence_spans(text)
    assert time.perf_counter() - started < 2.0


# -- bounds ------------------------------------------------------------------------------------

def test_a_pasted_wall_of_numbers_cannot_make_the_case_file_unbounded():
    from app.config import settings
    from app.figures.model import as_json

    req = _req(main_problem="1 " * (casefile.MAX_TEXT_CHARS // 2))   # 50,000 characters, 25,000 numbers
    figures = casefile.build(req)
    assert len(figures) == settings.CASE_FILE_FIGURES_PER_TEXT
    assert [f.id for f in figures][:2] == ["F-main_problem-1", "F-main_problem-2"]   # the first ones, in text order
    assert len(json.dumps([as_json(f) for f in figures])) < 1_000_000


def test_the_request_bound_stops_a_build_in_the_order_the_texts_are_read(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "CASE_FILE_FIGURES_PER_TEXT", 20)
    monkeypatch.setattr(settings, "CASE_FILE_FIGURES_PER_REQUEST", 30)
    req = _req(ops_numbers_json=_pairs({"question": "a", "answer": "1 " * 25}), main_problem="2 " * 100,
               revenue_today="3 " * 5, evidence_json=json.dumps([_claim(1)]))
    ids = [f.id for f in casefile.build(req)]
    # the one file figure is counted first, so the typed words get 29 of the 30; it is still listed last
    assert ids == ([f"T1-{i}" for i in range(1, 21)] + [f"F-main_problem-{i}" for i in range(1, 10)] + ["E1-1"])


def test_a_long_interview_cannot_starve_the_figures_from_their_files(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "CASE_FILE_FIGURES_PER_TEXT", 40)
    monkeypatch.setattr(settings, "CASE_FILE_FIGURES_PER_REQUEST", 100)
    pairs = [{"question": f"q{i}", "answer": "1 " * 40} for i in range(10)]   # 400 numbers
    claims = [_claim(n, 100 + n, cell=f"B{n}") for n in range(1, 31)]
    ids = [f.id for f in casefile.build(_req(ops_numbers_json=_pairs(*pairs), evidence_json=json.dumps(claims)))]
    assert len(ids) == 100
    assert [i for i in ids if i.startswith("E")] == [f"E{n}-1" for n in range(1, 31)]   # every file figure is in
    assert ids[-30:] == [f"E{n}-1" for n in range(1, 31)]   # listed after the typed ones
    assert len([i for i in ids if i.startswith("T")]) == 70


def test_the_files_take_no_more_than_half_of_the_bound_from_their_typed_words(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "CASE_FILE_FIGURES_PER_REQUEST", 100)
    claims = [_claim(n, 100 + n, cell=f"B{n}") for n in range(1, 81)]
    req = _req(main_problem="2 " * 100, evidence_json=json.dumps(claims))
    ids = [f.id for f in casefile.build(req)]
    assert len(ids) == 100
    assert len([i for i in ids if i.startswith("E")]) == 50 and len([i for i in ids if i.startswith("F")]) == 50


def test_a_claim_with_several_numbers_stops_at_the_bound_not_after_it(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "CASE_FILE_FIGURES_PER_REQUEST", 100)   # 50 for the files
    claims = [_claim(n, 100 + n, cell=f"B{n}") for n in range(1, 50)] + [_claim(50, "7 8 9 10 11", cell="B50")]
    figures = casefile.build(_req(evidence_json=json.dumps(claims)))
    assert len(figures) == 50   # 49 single numbers, then the first of the five in the last claim
    assert figures[-1].id == "E50-1"


def test_the_bounds_are_held_to_their_ranges():
    from app.config import settings

    assert 20 <= settings.CASE_FILE_FIGURES_PER_TEXT <= 1000
    assert 100 <= settings.CASE_FILE_FIGURES_PER_REQUEST <= 5000
