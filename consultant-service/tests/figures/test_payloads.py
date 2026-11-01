"""What the web payloads say about their figures.

The decision, preview, plan and shared-link payloads carry a `figures` map, one
entry per figure the payload names: how it prints, whose it is, the tag word the
client sees, and a plain sentence on where it came from. The answer's headline,
turn and sub (and each headline figure's value and label) also arrive in pieces,
so a page can put the tag beside each bound number. Everything else in the
payload keeps its shape.

Pins: every digit in served prose is a bound display; the map holds each kind the
payload names and nothing else; every source is a sentence a client can read (no
internal id, no raw exception text, no path); a row from before any of this
(no case file, no answer, no plan, or stored JSON that cannot be read) still
serves; the case file route says every figure is theirs.
"""
import json
import os
import re
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.figures import known as K
from app.figures import payload
from app.figures.bind import bind
from app.figures.model import (Figure, FigureSet, Proposal, Reference, TheirsSource, Working, display, tag_word)
from app.models import Request
from app.pipeline import action_plan, answer, capacity
from decimal import Decimal

# -- one realistic request -----------------------------------------------------------------

QUESTIONS = [
    ("How many reformers do you have, and how are classes scheduled?", "12 reformers. Six 50-minute classes a day, six days a week."),
    ("How full is a typical class?", "About 10 of 12. The 6pm and 7pm ones have a waiting list most weeks."),
    ("What do you charge a class?", "$22 a class, $200 for 10"),
    ("What do the studios nearby charge?", "Two others nearby, both $32 a class."),
]
DESCRIPTION = ("I run a pilates studio and I think I need a proper booking app. The 6pm and 7pm classes have a "
               "waiting list every week, and I spend about 8 hours a week juggling bookings on WhatsApp")
GRID = {"shape": "weekly_grid", "unit": "reformer spot", "unit_plural": "reformer spots",
        "per_slot": 12, "slots_per_day": 6, "days_per_week": 6,
        "slot_times": [None, None, None, None, "18:00", "19:00"],
        "typical_taken": 10, "full_slots": ["18:00", "19:00"], "waitlist": True}
MOVE = {"label": "moving 6pm and 7pm to $28, if regulars stay", "unit": "USD", "period": "year",
        "terms": [{"label": "evening spots a week", "value": 144, "from": "CAP-05"},
                  {"label": "price rise per spot", "value": 6,
                   "parts": [{"value": 28, "from": "proposed", "label": "proposed evening price"},
                             {"value": 22, "from": "CF-04", "sign": -1}]},
                  {"label": "weeks a year", "value": 52, "from": "constant"}]}
RAW_ANSWER = {
    "headline": "Your evenings sell out at $22 a class while others charge $32.",
    "turn": "Moving them to $28 is worth about $45,000 a year.",
    "sub": "Your 12 reformers hold 432 reformer spots a week, and 144 reformer spots are in the evenings that sell out.",
    "figures": [{"value": "$22 vs $32", "label": "you and two studios nearby", "cites": ["CF-04", "CF-06"]},
                {"value": "144 reformer spots", "label": "a week in the evenings that sell out", "cites": ["CAP-05"]}],
    "move": MOVE, "action": {"weeks": 6, "name": "six-week pilot"}}
RAW_ROADMAP = {
    "summary": "We move the evenings to $28 and watch the waiting list over six weeks.",
    "phases": [{"when": "Weeks 1 to 2", "title": "Set the evening price",
                "do": "We move the 6pm and 7pm classes to $28 and tell your regulars.", "by": "us"},
               {"when": "Weeks 3 to 6", "title": "Watch the evenings",
                "do": "We track evening fill against 10 of 12 each week.", "by": "together", "you": ""}],
    "decisions": [{"question": "Go ahead with $28 evenings?", "detail": "Daytime stays at $22.",
                   "options": ["Yes", "Not yet"]}],
    "assumptions": ["Regulars accept $28"]}
DECISION = {"consulting_summary": "Your evenings are full and your price is the lowest nearby.",
            "central_problem": "The evening price leaves money on the table.",
            "recommended_ai_employees": [], "recommended_features": [], "unverified": ["How regulars react"]}


def _fields(**over):
    base = dict(
        business_name="Halo Reformer Studio", business_description=DESCRIPTION, email="owner@example.com",
        status="done", is_generating=False,
        ops_numbers_json=json.dumps([{"id": f"q{i}", "question": q, "answer": a} for i, (q, a) in enumerate(QUESTIONS, 1)]),
        consulting_recommendations_json=json.dumps(DECISION))
    base.update(over)
    return base


def _written(**over) -> dict:
    """The columns of a finished run, written by the stages' own `shape` functions
    from a model reply, so the stored JSON is what a run stores."""
    row = Request(**_fields())
    picture = capacity.shape(GRID, [a for _, a in QUESTIONS] + [DESCRIPTION])
    row.capacity_json = json.dumps(picture)
    known = K.known_for(row)
    claims = [{"id": "CF-04", "value": 22, "unit": "USD", "text": "$22 a class", "provenance": "client_input"},
              {"id": "CF-06", "value": 32, "unit": "USD", "text": "$32", "provenance": "client_input"},
              ] + capacity.as_claims(picture)
    hours = K.hours_for(row)
    stored, problems = answer.shape(RAW_ANSWER, claims, known, hours)
    assert stored and not problems, problems
    plan_weeks = next(f for f in K.answer_figures(stored) if f.id == K.PLAN_WEEKS_ID)
    plan, problems = action_plan.shape(RAW_ROADMAP, K.with_extra(known, K.answer_figures(stored)), hours, plan_weeks)
    assert plan and not problems, problems
    return _fields(capacity_json=json.dumps(picture), answer_json=json.dumps(stored),
                   action_plan_json=json.dumps(plan), **over)


@pytest.fixture
def client(tmp_path, monkeypatch):
    from main import app
    from app.config import settings

    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    return TestClient(app)


def _seed(fields: dict) -> int:
    db = SessionLocal()
    req = Request(**fields)
    db.add(req)
    db.commit()
    rid = req.id
    db.close()
    return rid


def _decision(client, rid):
    r = client.get(f"/api/requests/{rid}/decision")
    assert r.status_code == 200, r.text
    return r.json()


def _prose(answer_json: dict | None, plan: dict | None) -> list[str]:
    """Every piece of model-written prose a client reads in the answer and the roadmap."""
    out: list[str] = []
    a = answer_json or {}
    out += [a.get("headline"), a.get("turn"), a.get("sub"), (a.get("action") or {}).get("name")]
    for f in a.get("figures") or []:
        out += [f.get("value"), f.get("label")]
    p = plan or {}
    out += [p.get("summary")] + list(p.get("assumptions") or [])
    for ph in p.get("phases") or []:
        out += [ph.get("title"), ph.get("do"), ph.get("you")]
    for d in p.get("decisions") or []:
        out += [d.get("question"), d.get("detail")] + list(d.get("options") or [])
    return [t for t in out if isinstance(t, str) and t]


# An internal name: a claim or figure id, a stage's path into its own JSON.
INTERNAL = re.compile(r"\b(?:[A-Z]{1,5}-\d+[a-z]?|[A-Z]\d+-\d+|PLAN-[A-Z0-9-]+|MOVE|PROP-\d+|F-[a-z_]+-\d+)\b"
                      r"|[a-z]+_[a-z_]+|\[\d+\]|Traceback|Error|Exception")


def _plain_source(s: str):
    assert isinstance(s, str) and s.strip(), "a source is a sentence"
    assert not INTERNAL.search(s), f"internal wording in a source: {s!r}"
    assert s.startswith(("Worked out", "Our estimate", "Reference", "From ")), s


# -- the sentences ---------------------------------------------------------------------------

def _f(kind, source, value="22", unit="USD", precision=0, id="X-1"):
    return Figure(id, Decimal(value), unit, None, kind, source, precision)


def test_a_figure_of_theirs_says_which_answer_it_came_from_in_the_words_of_the_question():
    f = _f("theirs", TheirsSource(turn=3, field="q3", quote="$22 a class, $200 for 10", file=None, cell=None))
    s = payload.source_sentence(f, {3: "What do you charge a class?"})
    assert s == 'From your answer to "What do you charge a class?": "$22 a class, $200 for 10"'
    assert "q3" not in s
    # no question on file for that turn: still a sentence, and still not the question's id
    assert payload.source_sentence(f, {}) == 'From one of your answers: "$22 a class, $200 for 10"'
    assert payload.source_sentence(f) == payload.source_sentence(f, {})


def test_a_figure_of_theirs_from_a_free_field_or_a_file_says_so():
    free = _f("theirs", TheirsSource(turn=None, field="main_problem", quote="we lose about 8 hours a week", file=None, cell=None))
    assert payload.source_sentence(free) == 'From what you wrote about your main problem: "we lose about 8 hours a week"'
    sheet = _f("theirs", TheirsSource(turn=None, field="March", quote="Monthly revenue", file="march.xlsx", cell="B5"))
    assert payload.source_sentence(sheet) == "From your file march.xlsx, sheet March, cell B5"
    bare = _f("theirs", TheirsSource(turn=None, field=None, quote="", file=None, cell=None))
    assert payload.source_sentence(bare) == "From what you told us"


def test_a_long_question_or_quote_is_cut_and_a_quote_keeps_its_own_quotes_out_of_the_way():
    long_q, long_quote = "q" * 400, "w" * 400
    f = _f("theirs", TheirsSource(turn=1, field="q1", quote=long_quote, file=None, cell=None))
    s = payload.source_sentence(f, {1: long_q})
    assert len(s) < payload.SENTENCE_MAX + 10 and s.endswith('"')
    assert long_q not in s and long_quote not in s


def test_a_derived_figure_shows_its_working_and_an_ours_figure_its_note():
    d = _f("derived", Working(inputs=("a",), op="product", text="12 × 6 a day × 6 days"), "432")
    assert payload.source_sentence(d) == "Worked out: 12 × 6 a day × 6 days"
    o = _f("ours", Proposal(note="the length of the plan we propose"), "6", "week")
    assert payload.source_sentence(o) == "Our estimate: the length of the plan we propose"
    r = _f("reference", Reference(publication="Pilates Industry Report", year=2024, population="US studios", url="https://x.example"), "70", "percent")
    assert payload.source_sentence(r) == "Reference: Pilates Industry Report, 2024"


def test_a_source_that_is_only_an_internal_name_becomes_a_plain_sentence():
    internal = ["DV-01 / 365", "financial_model.scenarios[Base].impact", "CAP-03", "", "   "]
    for text in internal:
        s = payload.source_sentence(_f("derived", Working(inputs=(), op="derived_value", text=text), "5"))
        _plain_source(s)
        assert text.strip() not in s or not text.strip()
        n = payload.source_sentence(_f("ours", Proposal(note=text), "5"))
        _plain_source(n)
    # the path in front of the arithmetic goes; the arithmetic stays
    s = payload.source_sentence(_f("derived", Working(inputs=(), op="derived_value", text="financial_model.lines[0]: 3 x 95 x 52"), "14820"))
    assert s == "Worked out: 3 x 95 x 52"


def test_the_entry_has_the_four_keys_and_the_tag_word_of_its_kind():
    f = _f("ours", Proposal(note="a price we propose"), "28")
    assert payload.entry(f) == {"display": "$28", "kind": "ours", "tag": "our estimate", "source": "Our estimate: a price we propose"}
    for kind, source in (("theirs", TheirsSource(None, None, "", None, None)), ("derived", Working((), "sum", "1 + 1")),
                         ("ours", Proposal("n")), ("reference", Reference("P", 2020, "p", "u"))):
        e = payload.entry(_f(kind, source, "2", "week"))
        assert set(e) == {"display", "kind", "tag", "source"} and e["tag"] == tag_word(kind) and e["display"] == "2 weeks"


def test_the_map_holds_only_the_ids_asked_for_and_skips_one_that_is_not_known():
    known = FigureSet([_f("ours", Proposal("a"), "1", id="A"), _f("ours", Proposal("b"), "2", id="B")])
    got = payload.figure_map(known, ["B", "nope", "B"])
    assert list(got) == ["B"]


# -- the payloads ----------------------------------------------------------------------------

def test_the_decision_names_every_figure_in_its_answer_the_week_and_the_roadmap_and_only_those(client):
    body = _decision(client, _seed(_written()))
    figures = body["figures"]
    kinds = {e["kind"] for e in figures.values()}
    assert kinds == {"theirs", "derived", "ours"}      # the three kinds this request names (reference: none exist yet)
    assert {e["tag"] for e in figures.values()} == {"yours", "worked out", "our estimate"}
    for key in ("MOVE", "PROP-1", "PLAN-WEEKS", "PLAN-PHASE-1-WEEKS", "PLAN-PHASE-2-WEEKS", "PLAN-PHASES", "CAP-01", "CAP-05"):
        assert key in figures, key
    assert figures["MOVE"]["kind"] == "ours" and figures["PROP-1"]["display"] == "$28"
    assert figures["CAP-01"]["kind"] == "derived" and figures["CAP-01"]["display"] == "432 reformer spots"
    for e in figures.values():
        assert set(e) == {"display", "kind", "tag", "source"}
        _plain_source(e["source"])
    # small: the 14-odd numbers in the case file that nothing on the page names are not sent
    named = set(payload.referenced_ids(body["answer"], body["action_plan"], body["capacity"]))
    assert set(figures) <= named and len(figures) < len(K.known_for(Request(**_written())))


def test_the_answer_arrives_in_pieces_that_join_to_the_prose_and_name_figures_in_the_map(client):
    body = _decision(client, _seed(_written()))
    a = body["answer"]
    for field in ("headline", "turn", "sub"):
        pieces = a[f"{field}_segments"]
        assert "".join(p["text"] for p in pieces) == a[field]
        for p in pieces:
            assert set(p) <= {"text", "figure"} and p["text"]
            if "figure" in p:
                assert p["figure"] in body["figures"]
                # the piece is the figure's number: its digits are in the figure as it prints
                shown = re.sub(r"\D", "", body["figures"][p["figure"]]["display"])
                assert re.sub(r"\D", "", p["text"]) in shown or not re.sub(r"\D", "", p["text"])
            else:
                assert not re.search(r"\d", p["text"]), "a number in plain text is a number no figure owns"
    assert {p["figure"] for p in a["turn_segments"] if "figure" in p} == {"PROP-1", "MOVE"}
    for f in a["figures"]:
        assert "".join(p["text"] for p in f["value_segments"]) == f["value"]
        assert "".join(p["text"] for p in f["label_segments"]) == f["label"]
        assert f["ids"] and all(i in body["figures"] for i in f["ids"])


def test_every_digit_in_served_prose_is_a_bound_display(client):
    """The prose is served as the stages stored it, so a number the model made up
    cannot arrive: binding it again against what the request knows changes nothing
    and leaves nothing unresolved."""
    for fetch in ("decision", "preview"):
        rid = _seed(_written())
        body = client.get(f"/api/requests/{rid}/{fetch}").json()
        known = K.known_for(Request(**_written()))
        hours = K.hours_for(Request(**_written()))
        texts = _prose(body["answer"], body["action_plan"])
        assert any(re.search(r"\d", t) for t in texts)
        for t in texts:
            r = bind(t, known, hours=hours)
            assert not r.unresolved, (fetch, t, [u.text for u in r.unresolved])
            assert r.text == t, (fetch, t, r.text)


def test_the_preview_the_plan_and_the_shared_link_carry_the_same_map(client):
    token = secrets.token_urlsafe(18)
    rid = _seed(_written(share_token=token))
    decision = _decision(client, rid)
    preview = client.get(f"/api/requests/{rid}/preview").json()
    plan = client.get(f"/api/requests/{rid}/plan").json()
    shared = client.get(f"/api/shared/{token}").json()
    assert preview["figures"] == decision["figures"] and shared["figures"] == decision["figures"]
    assert preview["answer"] == decision["answer"] and shared["answer"] == decision["answer"]
    # the roadmap alone needs only what it names
    assert set(plan["figures"]) == {"PLAN-WEEKS", "PLAN-PHASE-1-WEEKS", "PLAN-PHASE-2-WEEKS", "PLAN-PHASES"}
    assert plan["plan"]["phases"][0]["when"] == "Weeks 1 to 2"


def test_other_prose_keeps_its_shape(client):
    body = _decision(client, _seed(_written()))
    assert body["decision"]["summary"] == DECISION["consulting_summary"]
    assert body["decision"]["central_problem"] == DECISION["central_problem"]
    assert body["decision"]["unverified"] == DECISION["unverified"]
    stored = json.loads(_written()["answer_json"])
    for key in ("headline", "turn", "sub", "emphasis", "move", "action"):
        assert body["answer"][key] == stored[key]


# -- rows from before ------------------------------------------------------------------------

BARE = dict(business_name="Old Row", business_description="d", email="t@example.com", status="done", is_generating=False,
            consulting_recommendations_json=json.dumps({"recommended_ai_employees": [], "recommended_features": []}))


def test_a_row_from_before_any_of_this_serves_with_an_empty_map(client):
    rid = _seed(dict(BARE))
    d = _decision(client, rid)
    assert d["figures"] == {} and d["answer"] is None and d["action_plan"] is None
    p = client.get(f"/api/requests/{rid}/preview").json()
    assert p["figures"] == {} and p["answer"] is None
    plan = client.get(f"/api/requests/{rid}/plan").json()
    assert plan["figures"] == {} and plan["plan"] is None
    token = secrets.token_urlsafe(18)
    rid = _seed(dict(BARE, share_token=token))
    s = client.get(f"/api/shared/{token}")
    assert s.status_code == 200 and s.json()["figures"] == {}


def test_an_old_answer_with_no_ids_and_no_figure_serves_and_still_comes_in_pieces(client):
    old = {"headline": "You are full.", "turn": "", "sub": "Every evening sells out at $22.",
           "figures": [{"value": "$22", "label": "your price", "cites": ["CF-04"]}],
           "move": None, "action": {"weeks": 6, "name": "six-week pilot"}}
    d = _decision(client, _seed(dict(BARE, ops_numbers_json=json.dumps([{"question": "Price?", "answer": "$22 a class"}]),
                                     answer_json=json.dumps(old))))
    a = d["answer"]
    assert a["headline_segments"] == [{"text": "You are full."}] and a["turn_segments"] == []
    assert [p for p in a["sub_segments"] if "figure" in p]            # her $22 is still found in her answers
    assert a["figures"][0]["value_segments"] and d["figures"]
    assert a["action"] == old["action"]


@pytest.mark.parametrize("column,value", [
    ("answer_json", "[]"), ("answer_json", "{not json"), ("answer_json", '{"headline": ["x"], "figures": "bad"}'),
    ("answer_json", '{"headline": 5, "sub": null, "figures": [1, {"value": 3}], "move": "x", "action": []}'),
    ("capacity_json", "{not json"), ("capacity_json", '{"derived": "x"}'), ("capacity_json", '{"derived": [1, {"key": 5}]}'),
    ("action_plan_json", '"text"'), ("action_plan_json", '{"figures": "x", "phases": 3}'),
    ("ops_numbers_json", '[1, {"question": 5, "answer": ["x"]}]'),
    ("case_file_json", "{not json"), ("registry_json", '{"claims": [1]}'),
])
def test_stored_json_that_cannot_be_read_never_stops_a_page(client, column, value):
    fields = dict(BARE, **{column: value})
    token = secrets.token_urlsafe(18)
    rid = _seed(dict(fields, share_token=token))
    assert client.get(f"/api/requests/{rid}/decision").status_code == 200
    assert client.get(f"/api/requests/{rid}/preview").status_code == 200
    assert client.get(f"/api/requests/{rid}/plan").status_code == 200
    assert client.get(f"/api/shared/{token}").status_code == 200


def test_the_questions_are_read_from_an_interview_that_may_be_broken():
    assert payload.questions_for(Request(**dict(BARE, ops_numbers_json="{not json"))) == {}
    assert payload.questions_for(Request(**dict(BARE, ops_numbers_json=json.dumps(
        [{"question": "  What do   you charge? ", "answer": "$22"}, 3, {"question": 5}, {"question": "How many?"}])))
    ) == {1: "What do you charge?", 4: "How many?"}
    assert payload.questions_for(Request(**dict(BARE))) == {}


def test_a_failure_while_building_the_map_serves_the_page_without_it(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret internal detail")
    monkeypatch.setattr(payload, "figure_map", boom)
    rid = _seed(_written())
    d = _decision(client, rid)
    assert d["figures"] == {} and d["answer"]["headline"] and "secret" not in json.dumps(d)


# -- the case file ----------------------------------------------------------------------------

def test_every_case_file_figure_says_it_is_theirs_and_where_from():
    from app.routers import discovery

    sources = {"main_problem": "We lose about 8 hours a week", "q1": "What do you charge? — $22 a class"}
    theirs = {"main_problem": sources["main_problem"], "q1": "$22 a class"}
    origins = {"main_problem": "From what you told us about the problem",
               "q1": 'From your answer to "What do you charge?"'}
    raw = {"figures": [{"source": "main_problem", "token": "8 hours a week", "value": "8 hours", "label": "lost to bookings"},
                       {"source": "q1", "token": "$22", "value": "$22", "label": "a class"}]}
    out = discovery.shape_casefile(raw, sources, False, None, origins, theirs)
    assert len(out["figures"]) == 2
    for f in out["figures"]:
        assert f["kind"] == "theirs" and f["tag"] == "yours" and f["display"] == f["value"]
        _plain_source(f["source"])
