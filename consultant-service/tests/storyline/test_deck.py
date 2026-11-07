"""The deck tells the same story as the files, from the same object.

The first slide is the answer and the second is the register. A proof
slide's title is the section's title. A run with no storyline is the
deck it was before.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal
from types import SimpleNamespace

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.figures.known import plan_weeks_figure
from app.figures.model import Figure, TheirsSource, as_json
from app.models import Request
from app.pipeline import export_pptx
from app.storyline.build import build

WEEKS = plan_weeks_figure(6)
THEIRS = Figure("CF-04", Decimal("22"), "USD", None, "theirs",
                TheirsSource(1, "price", "We charge twenty-two a class.", None, None), 0)
QUESTION = "Should the studio keep the evening class?"
HEDGING = ("confident", "not sure", "validation", "AI-native", "review by a human", "very-sure-marker")


def _texts(prs) -> list[str]:
    out = []
    for slide in prs.slides:
        parts = [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame]
        out.append(" ".join(parts))
    return out


def _seed(db, **columns) -> Request:
    phases = [
        {"when": "Week 1", "title": "Set the week", "do": "Tell them the evening class stays.",
         "you": "You send the note.", "by": "us"},
        {"when": "Weeks 3 to 6", "title": "Watch the room", "do": "Watch which evening fills.",
         "you": "You look at the room.", "by": "together"},
    ]
    plan = {"status": "ready", "phases": phases, "decisions": [
        {"id": "d1", "question": "Who covers the desk?", "options": ["You cover it.", "We hire cover."]},
    ], "figures": [as_json(WEEKS)]}
    rows = [
        {"phase": 1, "recommendation": "Keep the evening class.", "changes": "The evening class.",
         "owner": "the owner", "depends_on": [], "share_pct": 60,
         "cost_figure": "CF-04", "cost_needs": None},
        {"phase": 2, "recommendation": "Watch the week.", "changes": "The week.",
         "owner": "the front desk", "depends_on": [1], "share_pct": 40,
         "cost_figure": "CF-04", "cost_needs": None},
    ]
    row = Request(
        business_name="Halo", business_description="A studio.", email="a@b.c",
        status="done", is_generating=False, concept_name="Halo",
        brief_json=json.dumps({"question": QUESTION}),
        case_file_json=json.dumps([as_json(THEIRS)]),
        answer_json=json.dumps({"headline": "You are full.", "turn": "Keep the class.",
                                 "action": {"weeks": 6, "figure": as_json(WEEKS)}}),
        storyline_json=json.dumps({"register": rows, "sections": [
            {"id": "plan", "title": "The evening class stays open", "takeaway": "Keep the class."},
            {"id": "scoreboard", "title": "The room fills up", "takeaway": "The desk misses 37 calls."},
        ]}),
        action_plan_json=json.dumps(plan),
        scoreboard_json=json.dumps([
            {"metric": "no-shows", "baseline": "measure in week 1", "target": "down",
             "owner": "you", "review": "weekly"},
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


def _ready(tmp_path, monkeypatch, **columns):
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    return db, _seed(db, **columns)


def _deck(row, images=()):
    return export_pptx.build_presentation(row, {}, {}, {"concept_name": "Halo"}, list(images))


def _shot(tmp_path) -> SimpleNamespace:
    from PIL import Image

    folder = os.path.join(str(tmp_path), "images", "1")
    os.makedirs(folder, exist_ok=True)
    Image.new("RGB", (8, 8), (2, 6, 23)).save(os.path.join(folder, "shot.png"))
    spec = {"ai": {"title": "The desk", "headline": "It books the class.",
                   "rationale": "the desk books it", "confidence": "very-sure-marker"}}
    return SimpleNamespace(file_path="/uploads/images/1/shot.png", role_label="The desk",
                           spec_json=json.dumps(spec))


def test_deck_titles_equal_the_pdf_section_titles(tmp_path, monkeypatch):
    db, row = _ready(tmp_path, monkeypatch)
    titles = [section.title for section in build(row).sections]
    slides = _texts(_deck(row))
    for title in titles:
        assert any(title in slide for slide in slides), title
    db.close()


def test_first_two_slides_are_the_answer_and_the_register(tmp_path, monkeypatch):
    db, row = _ready(tmp_path, monkeypatch)
    slides = _texts(_deck(row))
    assert QUESTION in slides[0]
    assert "The register" in slides[1] and "Keep the evening class." in slides[1]
    db.close()


def test_one_exhibit_per_exhibit_slide(tmp_path, monkeypatch):
    db, row = _ready(tmp_path, monkeypatch)
    slides = _texts(_deck(row))
    plan = [slide for slide in slides if "The phases, in order." in slide]
    board = [slide for slide in slides if "Each measure, from today to the aim." in slide]
    assert len(plan) == 1 and len(board) == 1
    assert "Each measure, from today to the aim." not in plan[0]
    assert "The phases, in order." not in board[0]
    db.close()


def test_deck_text_has_no_hedging_words_and_no_ai_confidence_line(tmp_path, monkeypatch):
    db, row = _ready(tmp_path, monkeypatch)
    slides = _texts(_deck(row, [_shot(tmp_path)]))
    text = "\n".join(slides)
    for word in HEDGING:
        assert word not in text, word
    assert "the desk books it" in text
    assert "how the plan runs" in text.lower()
    db.close()


def test_deck_slides_are_named_slides_in_law_findings(tmp_path, monkeypatch):
    from app.figures import law

    db, row = _ready(tmp_path, monkeypatch)
    slides = _texts(_deck(row))
    slide_no = next(n for n, text in enumerate(slides, 1) if "37 calls" in text)
    found = law.recorded(row)["The deck"]
    assert [(item.number, item.page) for item in found] == [("37", slide_no)]
    db.close()


def test_a_legacy_run_deck_is_unchanged(tmp_path, monkeypatch):
    db, row = _ready(tmp_path, monkeypatch, storyline_json=None, answer_json=None, brief_json=None)
    first = _texts(_deck(row))
    second = _texts(_deck(row))
    assert first == second
    assert first and QUESTION not in first[0]
    db.close()


def _overlaps(prs, below: float = 0.0) -> list[str]:
    """Text boxes that sit on each other, or run past the foot of the slide.
    `below` (inches) leaves out the chrome band above it."""
    bad = []
    for number, slide in enumerate(prs.slides, 1):
        boxes = [(s.left, s.top, s.left + s.width, s.top + s.height, s.text_frame.text[:30])
                 for s in slide.shapes if s.has_text_frame and s.text_frame.text.strip()
                 and s.top >= below * 914400]
        for i, a in enumerate(boxes):
            if a[3] > prs.slide_height:
                bad.append(f"slide {number}: {a[4]!r} runs past the foot")
            for b in boxes[i + 1:]:
                if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                    bad.append(f"slide {number}: {a[4]!r} sits on {b[4]!r}")
    return bad


def test_deck_rows_are_measured_and_continue_rather_than_overlap(tmp_path, monkeypatch):
    # Review M2: at the default bounds the exhibit's rows ran under the section
    # takeaway and the register's rows ran past the 7.5 in slide.
    monkeypatch.setattr(settings, "REGISTER_ROWS_MAX", 12)
    grid = {"unit_plural": "spots", "grid": [{"day": "Mon", "slots": [
        {"time": f"Class {chr(65 + i)}", "taken": 3} for i in range(14)]}]}
    words = "Keep the evening class open and tell every regular on the list by the end of the week"
    rows = [{"phase": 1, "recommendation": f"{words}, part {chr(65 + n)}.", "changes": "The evening class.",
             "owner": "the owner", "depends_on": [1] if n else [], "share_pct": 10 if n < 4 else 5 if n < 10 else 15,
             "cost_figure": "CF-04", "cost_needs": None} for n in range(12)]
    assert sum(row["share_pct"] for row in rows) == 100
    db, row = _ready(tmp_path, monkeypatch, capacity_json=json.dumps(grid), storyline_json=json.dumps({
        "register": rows,
        "sections": [{"id": "week", "title": "The week is full", "takeaway": "The evening class stays."}]}))
    prs = _deck(row)
    assert _overlaps(prs) == []
    text = "\n".join(_texts(prs))
    assert all(f"part {chr(65 + n)}." in text for n in range(12))
    assert "Other classes, 3 classes" in text and "Other classes (3)" not in text
    db.close()


def test_the_first_slide_is_the_whole_answer_page(tmp_path, monkeypatch):
    # Review M6: the deck's first slide had no numbers, belief, test, Monday or would-not.
    db, row = _ready(tmp_path, monkeypatch, main_problem="The evening class is too quiet.",
                     consulting_recommendations_json=json.dumps({"why_not_the_others": "A new hire costs more."}))
    first = _texts(_deck(row))[0]
    for part in (QUESTION, "You are full.", "What you believed: The evening class is too quiet.",
                 "Monday: Tell them the evening class stays. You send the note.",
                 "What we would not do: A new hire costs more.", "What this rests on"):
        assert part in first, part
    db.close()


def test_the_register_slide_shows_every_column_and_the_headline(tmp_path, monkeypatch):
    # Review H5: the deck printed only "{recommendation} {owner}" per row.
    terms = [{"kind": "claim", "id": "CF-04", "value": "22", "sign": 1, "label": "her price"},
             {"kind": "proposed", "value": "0.75", "sign": 1, "label": "who stay"}]
    db, row = _ready(tmp_path, monkeypatch, answer_json=json.dumps({
        "headline": "You are full.", "turn": "Keep the class.", "action": {"weeks": 6, "figure": as_json(WEEKS)},
        "move": {"value": 16.5, "unit": "USD", "period": "week", "terms": terms}}))
    slides = _texts(_deck(row))
    register = next(slide for slide in slides if "The register" in slide)
    assert ".." not in register
    for part in ("What it changes: The evening class.", "Value: $7.92 to $11.88 a week", "Cost: $22",
                 "Owner: the owner", "When: Week 1", "After 1", "All together: $13.20 to $19.80 a week"):
        assert part in register, part
    from app.figures import law

    assert law.recorded(row)["The deck"] == [] or all(
        f.number == "37" for f in law.recorded(row)["The deck"])
    db.close()


def test_screen_captions_are_printed_whole_and_measured(tmp_path, monkeypatch):
    # Review M4: the new screens slides cut the description, the rationale and
    # the tracks to an estimated character count.
    from PIL import Image

    folder = os.path.join(str(tmp_path), "images", "1")
    os.makedirs(folder, exist_ok=True)
    Image.new("RGB", (8, 8), (2, 6, 23)).save(os.path.join(folder, "shot.png"))
    rationale = ("the desk books the class the moment a regular asks and keeps the waiting list "
                 "in the order people asked, so nobody is skipped and nobody is asked twice")
    spec = {"subheading": "Where the week is booked",
            "kpis": [{"label": "Bookings taken at the desk"}, {"label": "Waiting list kept in order"},
                     {"label": "Regulars who come back"}],
            "primary_panel": {"title": "Today's classes"}, "secondary_panel": {"title": "The waiting list"},
            "ai": {"title": "The desk", "headline": "It books the class.", "rationale": rationale}}
    shot = SimpleNamespace(file_path="/uploads/images/1/shot.png", role_label="The desk",
                           spec_json=json.dumps(spec))
    db, row = _ready(tmp_path, monkeypatch)
    prs = _deck(row, [shot])
    text = "\n".join(_texts(prs))
    assert rationale in text and "…" not in text
    assert "Bookings taken at the desk  ·  Waiting list kept in order  ·  Regulars who come back" in text
    # the chrome's kicker and running name share the band above the content
    assert _overlaps(prs, below=0.8) == []
    db.close()
