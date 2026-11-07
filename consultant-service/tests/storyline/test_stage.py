"""The one new model call writes the register's words and the proof titles.

It does not write an amount. A share that does not add up, a title that does
not fit, and a number nobody owns are sent back once and then the stage stops.
The client hears "the plan summary", never the stage's own name.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.ai import provider
from app.database import Base, SessionLocal, engine
from app.figures.model import Figure, TheirsSource, as_json
from app.models import Request
from app.storyline.stage import PROGRESS, write

TERMS = [
    {"kind": "claim", "id": "CF-04", "value": "22", "sign": 1, "label": "her price"},
    {"kind": "constant", "value": "5", "sign": 1, "label": "days"},
    {"kind": "proposed", "value": "0.75", "sign": 1, "label": "who stay"},
]
THEIRS = Figure("CF-04", Decimal("22"), "USD", None, "theirs",
                TheirsSource(1, "price", "We charge twenty-two a class.", None, None), 0)
PROMPT = Path(__file__).resolve().parents[2] / "app" / "prompts" / "storyline.j2"


def _reply(shares=(60, 40), title="Keep the evening class", sections=None) -> dict:
    rows = []
    for n, share in enumerate(shares, 1):
        rows.append({
            "phase": 1 if n == 1 else 2, "recommendation": f"Do the thing.",
            "changes": "The evening class.", "owner": "the owner",
            "depends_on": [1] if n > 1 else [], "share_pct": share,
            "cost_figure": "CF-04", "cost_needs": None,
        })
    if sections is None:
        sections = [{"id": "week", "title": title, "takeaway": "The class stays on the board."}]
    return {"register": rows, "sections": sections}


def _chat(replies: list[dict]):
    sent = []

    def chat(model, messages, max_tokens=None, **kwargs):
        sent.append(messages[-1]["content"])
        body = replies.pop(0)
        return {"choices": [{"message": {"content": json.dumps(body)}}], "usage": {}}

    return chat, sent


@pytest.fixture(autouse=True)
def _tables():
    Base.metadata.create_all(bind=engine)


def _row(db, **columns) -> Request:
    phases = [{"when": "Week 1", "title": "Set the week", "do": "Tell them.", "you": "You send it."},
              {"when": "Weeks 2 to 6", "title": "Watch it", "do": "Watch.", "you": "You look."}]
    row = Request(
        business_name="Halo", business_description="A studio.", email="a@b.c",
        status="generating", is_generating=True, stage="roadmap",
        case_file_json=json.dumps([as_json(THEIRS)]),
        action_plan_json=json.dumps({"status": "ready", "phases": phases}),
        answer_json=json.dumps({"headline": "You are full.",
                                 "move": {"value": 82.5, "unit": "USD", "period": "year", "terms": TERMS}}),
    )
    for key, value in columns.items():
        setattr(row, key, value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_a_good_reply_is_stored_and_the_register_assembles(monkeypatch):
    from app.storyline.register import assemble

    chat, sent = _chat([_reply()])
    monkeypatch.setattr(provider, "chat", chat)
    db = SessionLocal()
    row = _row(db)
    write(db, row.id)
    db.refresh(row)
    stored = json.loads(row.storyline_json)
    register = assemble(row, stored["register"])
    assert register.rows and stored["sections"][0]["title"] == "Keep the evening class"
    assert stored["written_at"]
    assert len(sent) == 1
    db.close()


def test_unowned_number_in_a_title_is_sent_back_with_the_drop_hint(monkeypatch):
    bad = _reply(title="Open 15 more")
    good = _reply()
    chat, sent = _chat([bad, good])
    monkeypatch.setattr(provider, "chat", chat)
    db = SessionLocal()
    row = _row(db)
    write(db, row.id)
    db.refresh(row)
    assert len(sent) == 2
    assert "15" in sent[1] and "drop" in sent[1].lower()
    assert "15" not in json.loads(row.storyline_json)["sections"][0]["title"]
    db.close()


def test_shares_not_summing_to_100_get_one_retry_with_the_sum_named_then_stop(monkeypatch):
    from app.pipeline.failure import StageFailed

    chat, sent = _chat([_reply((50, 49)), _reply((50, 49))])
    monkeypatch.setattr(provider, "chat", chat)
    db = SessionLocal()
    row = _row(db)
    with pytest.raises(StageFailed):
        write(db, row.id)
    db.refresh(row)
    assert len(sent) == 2 and "99" in sent[1]
    assert row.storyline_json is None
    db.close()


def test_a_title_over_two_lines_gets_one_retry_naming_the_limit_then_stops_honestly(monkeypatch):
    from app.pipeline.failure import StageFailed
    from app.storyline.pagelaw import title_lines

    long = " ".join(["evening"] * 80)
    assert title_lines(long) > 2
    chat, sent = _chat([_reply(title=long), _reply(title=long)])
    monkeypatch.setattr(provider, "chat", chat)
    db = SessionLocal()
    row = _row(db)
    with pytest.raises(StageFailed):
        write(db, row.id)
    db.refresh(row)
    assert len(sent) == 2 and "two lines" in sent[1]
    assert row.storyline_json is None
    db.close()


def test_sections_for_a_do_not_build_run_exclude_the_system_section(monkeypatch):
    sections = [
        {"id": "system", "title": "The screens", "takeaway": "There are none."},
        {"id": "week", "title": "Keep the evening class", "takeaway": "The class stays on the board."},
    ]
    chat, _sent = _chat([_reply(sections=sections)])
    monkeypatch.setattr(provider, "chat", chat)
    db = SessionLocal()
    row = _row(db, consulting_recommendations_json=json.dumps({"intervention_kind": "process"}))
    write(db, row.id)
    db.refresh(row)
    stored = json.loads(row.storyline_json)
    assert [section["id"] for section in stored["sections"]] == ["week"]
    db.close()


def test_the_stage_failure_reaches_the_client_in_plain_words(monkeypatch):
    from app import mailer
    from app.pipeline.failure import client_reason, fail_run

    reason = client_reason("storyline", False)
    assert "plan summary" in reason and "storyline" not in reason
    assert "storyline" not in PROGRESS and "plan summary" in PROGRESS
    monkeypatch.setattr(mailer, "send_now", lambda *args, **kwargs: False)
    db = SessionLocal()
    row = _row(db)
    fail_run(db, row.id, "storyline", "the title was three lines")
    db.refresh(row)
    assert row.progress_detail == reason
    assert "three lines" not in row.progress_detail
    db.close()


def test_prompt_asks_for_no_amounts_and_no_hedging():
    text = PROMPT.read_text(encoding="utf-8").lower()
    assert "do not write an amount" in text
    assert "hedge" in text
    for word in ("confident", "not sure", "validation", "ai-native"):
        assert word not in text


def test_a_number_nobody_owns_in_the_register_words_is_sent_back(monkeypatch):
    # Review C1: the register's words were checked for shape only, so "$999" and
    # "$5,000" were stored and printed with no law check.
    bad = _reply()
    bad["register"][0]["recommendation"] = "Raise the price to $999 a class."
    bad["register"][0]["cost_figure"] = None
    bad["register"][0]["cost_needs"] = "a quote of $5,000 from the builder"
    chat, sent = _chat([bad, _reply()])
    monkeypatch.setattr(provider, "chat", chat)
    db = SessionLocal()
    row = _row(db)
    write(db, row.id)
    db.refresh(row)
    assert len(sent) == 2
    assert "$999" in sent[1] and "recommendation 1" in sent[1]
    assert "$999" not in row.storyline_json and "$5,000" not in row.storyline_json
    db.close()


def test_a_number_nobody_owns_in_the_cost_gap_is_sent_back(monkeypatch):
    bad = _reply()
    bad["register"][1]["cost_figure"] = None
    bad["register"][1]["cost_needs"] = "a quote of $5,000 from the builder"
    chat, sent = _chat([bad, _reply()])
    monkeypatch.setattr(provider, "chat", chat)
    db = SessionLocal()
    row = _row(db)
    write(db, row.id)
    db.refresh(row)
    assert len(sent) == 2 and "$5,000" in sent[1]
    db.close()


def test_figure_tokens_are_bound_before_the_storyline_is_stored(monkeypatch):
    # Review C2: the raw "{{F:CF-04}}" was stored and printed in the PDF and on the web.
    reply = _reply(sections=[{"id": "week", "title": "The class stays full at {{F:CF-04}}",
                              "takeaway": "Keep the price at {{F:CF-04}}."}])
    reply["register"][0]["recommendation"] = "Keep the price at {{F:CF-04}}."
    chat, _sent = _chat([reply])
    monkeypatch.setattr(provider, "chat", chat)
    db = SessionLocal()
    row = _row(db)
    write(db, row.id)
    db.refresh(row)
    stored = json.loads(row.storyline_json)
    assert "{{" not in row.storyline_json
    assert stored["sections"][0]["title"] == "The class stays full at $22"
    assert stored["sections"][0]["takeaway"] == "Keep the price at $22."
    assert stored["register"][0]["recommendation"] == "Keep the price at $22."
    db.close()


def test_the_prompt_names_the_section_ids_that_draw_an_exhibit(monkeypatch):
    # Review M1: the exhibit is chosen by section id, and the prompt never named the ids.
    grid = {"unit_plural": "spots", "grid": [{"day": "Mon", "slots": [{"time": "Evening", "taken": 11}]}]}
    chat, sent = _chat([_reply()])
    monkeypatch.setattr(provider, "chat", chat)
    db = SessionLocal()
    row = _row(db, capacity_json=json.dumps(grid))
    write(db, row.id)
    assert "- week: How full each class is" in sent[0]
    assert "- prize: Where the prize comes from" in sent[0]
    assert "- scoreboard:" not in sent[0]
    db.close()


def test_more_sections_than_the_bound_are_sent_back_not_cut(monkeypatch):
    # Review M3: STORYLINE_SECTIONS_MAX was defined and never enforced.
    from app.config import settings

    monkeypatch.setattr(settings, "STORYLINE_SECTIONS_MAX", 4)
    many = [{"id": f"s{n}", "title": f"Finding {chr(65 + n)} holds", "takeaway": ""} for n in range(5)]
    chat, sent = _chat([_reply(sections=many), _reply()])
    monkeypatch.setattr(provider, "chat", chat)
    db = SessionLocal()
    row = _row(db)
    write(db, row.id)
    db.refresh(row)
    assert "at most 4 sections" in sent[0]
    assert len(sent) == 2 and "at most 4" in sent[1]
    assert len(json.loads(row.storyline_json)["sections"]) == 1
    db.close()
