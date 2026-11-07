"""The roadmap file is as long as the plan, and it says so.

A six-week plan does not say ninety days. A baseline the owner has not
measured yet stays the words "measure in week 1". Metrics that share a
review rhythm sit under that rhythm once. No plan means no file.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal

import pymupdf
import pytest

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.figures.bind import bind
from app.figures.known import known_for, plan_weeks_figure
from app.figures.model import Figure, TheirsSource, as_json, display
from app.models import Request
from app.pipeline import action_plan
from app.pipeline.export_pdf import strip_page_chrome, COVER_PANEL_SPANS
from app.storyline import roadmap
from app.storyline.pagelaw import pdf_findings

WEEKS = plan_weeks_figure(6)
THEIRS = Figure("CF-04", Decimal("22"), "USD", None, "theirs",
                TheirsSource(1, "price", "We charge twenty-two a class.", None, None), 0)
QUESTION = "Should the studio keep the evening class?"


def _pages(path: str) -> str:
    doc = pymupdf.open(path)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _seed(db, **columns) -> Request:
    phases = [
        {"when": "Week 1", "title": "Set the week", "do": "Tell them the evening class stays.",
         "you": "You send the note.", "by": "us"},
        {"when": "Weeks 3 to 6", "title": "Watch the room", "do": "Watch which evening fills.",
         "you": "You look at the room.", "by": "together"},
    ]
    decisions = [{"id": "d1", "question": "Who covers the desk?",
                  "detail": "The evening needs a person.", "options": ["You cover it.", "We hire cover."]}]
    plan = {"status": "ready", "phases": phases, "decisions": decisions, "figures": [as_json(WEEKS)]}
    rows = [
        {"phase": 1, "recommendation": "Keep the evening class.", "changes": "The evening class.",
         "owner": "the owner", "depends_on": [], "share_pct": 60, "cost_figure": "CF-04", "cost_needs": None},
        {"phase": 2, "recommendation": "Watch the week.", "changes": "The week.",
         "owner": "the front desk", "depends_on": [1], "share_pct": 40, "cost_figure": "CF-04", "cost_needs": None},
    ]
    row = Request(
        business_name="Halo", business_description="A studio.", email="a@b.c",
        status="done", is_generating=False, concept_name="Halo",
        brief_json=json.dumps({"question": QUESTION}),
        case_file_json=json.dumps([as_json(THEIRS)]),
        answer_json=json.dumps({"headline": "You are full.", "turn": "Keep the class.",
                                 "action": {"weeks": 6, "figure": as_json(WEEKS)}}),
        storyline_json=json.dumps({"register": rows, "sections": []}),
        action_plan_json=json.dumps(plan),
        scoreboard_json=json.dumps([
            {"metric": "no-shows", "baseline": "measure in week 1", "target": "down",
             "owner": "you", "review": "weekly"},
            {"metric": "fill", "baseline": "measure in week 1", "target": "up",
             "owner": "you", "review": "weekly"},
            {"metric": "revenue", "baseline": "the till", "target": "up",
             "owner": "the owner", "review": "monthly"},
        ]),
        risks_json=json.dumps([
            {"risk": "staff leave", "mitigation": "train the desk", "who_feels_it": "the front desk"},
        ]),
    )
    for key, value in columns.items():
        setattr(row, key, value)
    from tests._integrity_stub import stamp_clean
    stamp_clean(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _ready(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    return db, _seed(db)


def test_roadmap_names_the_plans_real_length(tmp_path, monkeypatch):
    db, row = _ready(tmp_path, monkeypatch)
    text = _pages(roadmap.build_roadmap_pdf(row))
    assert display(WEEKS) in text
    assert "ninety" not in text.lower()
    assert "Set the week" in text and "the owner" in text
    db.close()


def test_kpi_rows_keep_week_one_baselines_verbatim(tmp_path, monkeypatch):
    db, row = _ready(tmp_path, monkeypatch)
    text = _pages(roadmap.build_roadmap_pdf(row))
    assert text.count("measure in week 1") == 2
    db.close()


def test_cadence_table_groups_metrics_by_their_review_rhythm(tmp_path, monkeypatch):
    db, row = _ready(tmp_path, monkeypatch)
    text = _pages(roadmap.build_roadmap_pdf(row))
    cadence = text.split("The cadence", 1)[-1]
    assert cadence.count("weekly") == 1
    assert cadence.index("weekly") < cadence.index("no-shows") < cadence.index("fill")
    assert cadence.index("fill") < cadence.index("monthly") < cadence.index("revenue")
    db.close()


def test_no_action_plan_is_not_ready_and_not_a_blank_file(tmp_path, monkeypatch):
    db, row = _ready(tmp_path, monkeypatch)
    path = os.path.join(str(tmp_path), "exports", f"{row.id}-roadmap.pdf")
    for raw in (None, "", json.dumps({"status": action_plan.WRITING, "phases": [{"title": "x"}]}),
                json.dumps({"status": action_plan.FAILED, "phases": [{"title": "x"}]}),
                json.dumps({"status": "ready", "phases": []})):
        row.action_plan_json = raw
        db.commit()
        with pytest.raises(roadmap.NotReady) as caught:
            roadmap.build_roadmap_pdf(row)
        assert caught.value.key == "roadmap"
        assert not os.path.isfile(path)
    db.close()


def test_roadmap_passes_the_number_law_and_page_law(tmp_path, monkeypatch):
    db, row = _ready(tmp_path, monkeypatch)
    path = roadmap.build_roadmap_pdf(row)
    text = _pages(path)
    assert "staff leave" in text and "train the desk" in text and "Who covers the desk?" in text
    assert QUESTION in text.split("The plan", 1)[0]
    unresolved = bind(strip_page_chrome(text, "Halo"), known_for(row)).unresolved
    assert unresolved == []
    findings = [reason for reason in pdf_findings(path) if not reason.endswith(COVER_PANEL_SPANS)]
    assert findings == []
    db.close()


def test_the_roadmap_is_a_document_of_the_release_law(tmp_path, monkeypatch):
    # Review C1: the roadmap was built outside any law scope, so "From 12 to 20"
    # printed with no record and no effect on the stamp.
    from app.figures import law
    from app.pipeline import export_pdf

    db, row = _ready(tmp_path, monkeypatch)
    row.scoreboard_json = json.dumps([{"metric": "classes full", "baseline": "12", "target": "20",
                                       "owner": "you", "review": "weekly"}])
    db.commit()
    path = roadmap.build_roadmap_pdf(row)
    found = law.recorded(row)["The roadmap"]
    assert {f.number for f in found} == {"12", "20"}
    assert all(f.page is not None for f in found)
    reasons = export_pdf.release_status(row)["reasons"]
    assert any(reason.startswith("The roadmap, page") for reason in reasons)
    assert law.record(row.id, "The roadmap", row.updated_at)["stamped"] == "draft"
    assert "From 12 to 20" in _pages(path)
    db.close()


def test_a_clean_roadmap_has_a_clean_record(tmp_path, monkeypatch):
    from app.figures import law

    db, row = _ready(tmp_path, monkeypatch)
    roadmap.build_roadmap_pdf(row)
    assert law.recorded(row)["The roadmap"] == []
    db.close()


def test_a_roadmap_without_a_plan_is_recorded_as_not_produced(tmp_path, monkeypatch):
    from app.figures import law

    db, row = _ready(tmp_path, monkeypatch)
    row.action_plan_json = None
    db.commit()
    law.ensure_records(row)
    assert law.states(row)["The roadmap"] == "not produced"
    db.close()


def test_a_measure_with_no_baseline_says_no_empty_from(tmp_path, monkeypatch):
    # Review L7: "Metric. From  to ." was printed for a measure with no numbers.
    db, row = _ready(tmp_path, monkeypatch)
    row.scoreboard_json = json.dumps([{"metric": "repeat bookings", "target": "up", "owner": "you"},
                                      {"metric": "walk-ins", "owner": "you"}])
    db.commit()
    text = _pages(roadmap.build_roadmap_pdf(row))
    assert "From  to" not in text and "From to" not in text
    assert "repeat bookings. Aim: up." in text
    assert "walk-ins." in text
    db.close()
