"""Step 3's acceptance: the smallest package and the largest one.

Every file that the list says is ready is built. A page that clips, a title
that is only a label, a register that does not add up, and a hedging word
all fail here. A run from before the storyline still builds.
"""
from __future__ import annotations

import json
import re
import zipfile
from decimal import Decimal

import pymupdf
import pytest

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.figures.known import plan_weeks_figure
from app.figures.model import Figure, TheirsSource, as_json
from app.models import Request
from app.pipeline import export_pdf
from app.storyline.build import build
from app.storyline.flex import flexed
from app.storyline.pagelaw import title_lines

TERMS = [
    {"kind": "claim", "id": "CF-04", "value": "22", "sign": 1, "label": "her price"},
    {"kind": "constant", "value": "5", "sign": 1, "label": "days"},
    {"kind": "proposed", "value": "0.75", "sign": 1, "label": "who stay"},
]
THEIRS = Figure("CF-04", Decimal("22"), "USD", None, "theirs",
                TheirsSource(1, "price", "We charge twenty-two a class.", None, None), 0)
WEEKS = plan_weeks_figure(6)
HEDGING = ("confident", "not sure", "validation", "AI-native", "review by a human",
           "requires validation", "human review")
VERBS = {"is", "are", "stays", "stay", "fills", "keeps", "covers", "opens", "holds",
         "trains", "runs", "takes", "stops", "gives", "shows"}
BARE = {"the opportunity", "overview", "summary", "background", "introduction"}
TITLES = (
    "The evening class stays open",
    "The week stays full",
    "The desk covers the phone",
    "The owner keeps the price",
    "The room holds the class",
    "The plan runs this season",
    "The desk takes the booking",
    "The studio keeps the class",
)


def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def _sections(n: int) -> list[dict]:
    kinds = ("plan", "scoreboard", "prize", "week", "grid", "plan", "scoreboard", "prize")
    return [{"id": kinds[i], "title": TITLES[i], "takeaway": "This is the part that follows."}
            for i in range(n)]


_RECOMMENDATIONS = (
    "Keep the evening class.",
    "Watch the week.",
    "Cover the phone.",
    "Hold the price.",
    "Open the room.",
    "Train the desk.",
    "Book the sitting.",
    "Keep the morning class.",
)


def _register(shares: tuple[int, ...]) -> list[dict]:
    rows = []
    for n, share in enumerate(shares):
        rows.append({
            "phase": 1 if n == 0 else 2,
            "recommendation": _RECOMMENDATIONS[n],
            "changes": "The evening class.",
            "owner": "the owner",
            "depends_on": [] if n == 0 else [1],
            "share_pct": share,
            "cost_figure": "CF-04",
            "cost_needs": None,
        })
    return rows


def _seed(db, *, shares: tuple[int, ...], sections: int) -> Request:
    phases = [
        {"when": "Week 1", "title": "Set the week", "do": "Tell them the class stays.",
         "you": "You send the note.", "by": "us"},
        {"when": "Weeks 3 to 6", "title": "Watch the room", "do": "Watch which evening fills.",
         "you": "You look at the room.", "by": "together"},
    ]
    plan = {"status": "ready", "phases": phases, "decisions": [
        {"id": "d1", "question": "Who covers the desk?", "options": ["You cover it.", "We hire cover."]},
    ], "figures": [as_json(WEEKS)]}
    row = Request(
        business_name="Halo", business_description="A studio.", email="a@b.c",
        status="done", is_generating=False, concept_name="Halo",
        brief_json=json.dumps({"question": "Should the studio keep the evening class?"}),
        case_file_json=json.dumps([as_json(THEIRS)]),
        main_problem="The evening class looks empty.",
        answer_json=json.dumps({
            "headline": "You are full.", "turn": "Keep the class.",
            "move": {"value": 82.5, "unit": "USD", "period": "year", "terms": TERMS},
            "action": {"weeks": 6, "figure": as_json(WEEKS)},
        }),
        storyline_json=json.dumps({"register": _register(shares), "sections": _sections(sections)}),
        action_plan_json=json.dumps(plan),
        scoreboard_json=json.dumps([{
            "metric": "the room", "baseline": "the desk is full", "target": "the desk has room",
            "owner": "you", "review": "weekly",
        }]),
        mvp_blueprint="## The plan\nA studio keeps its classes full.\n",
        technical_plan="## The build\nThe booking is the work.\n",
        procedures_json=json.dumps({"procedures": [{"name": "Opening", "trigger": "the morning",
                                                    "steps": [{"actor": "owner", "step": "unlock"}],
                                                    "exceptions": []}]}),
        roles_json=json.dumps([{"name": "the desk", "purpose": "books the class"}]),
    )
    from tests._integrity_stub import stamp_clean
    stamp_clean(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _fixtures(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    small = _seed(db, shares=(60, 40), sections=1)
    large = _seed(db, shares=(13, 13, 13, 13, 12, 12, 12, 12), sections=8)
    return db, (small, large)


def _text(path: str) -> str:
    doc = pymupdf.open(path)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _render(row):
    from app.storyline.files import files_for, render_file

    built = {}
    for item in files_for(row):
        if item.key == "zip" or not item.available:
            continue
        built[item.key] = render_file(row, item.key)
    return built


def _deck_overflows(path: str) -> list[str]:
    """A text box whose words need more lines than the box is tall."""
    from pptx import Presentation

    prs = Presentation(path)
    bad = []
    for number, slide in enumerate(prs.slides, 1):
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            frame = shape.text_frame
            text = frame.text.strip()
            if not text:
                continue
            size = 14.0
            for paragraph in frame.paragraphs:
                for run in paragraph.runs:
                    if run.font.size is not None:
                        size = run.font.size.pt
            # An English Metric Unit is 12700 points.
            width_pt = shape.width / 12700
            height_pt = shape.height / 12700
            chars = max(8, int(width_pt / (size * 0.5)))
            lines = 0
            for block in text.split("\n"):
                words = block.split() or [""]
                current = ""
                count = 1
                for word in words:
                    trial = word if not current else f"{current} {word}"
                    if len(trial) <= chars:
                        current = trial
                    else:
                        count += 1
                        current = word
                lines += count
            capacity = height_pt / (size * 1.15)
            if lines > capacity + 1:
                bad.append(f"slide {number}: {text[:48]!r} needs {lines} lines in a box for {capacity:.1f}")
    return bad


@pytest.mark.parametrize("which", ["small", "large"])
def test_minimum_and_maximum_fixtures_render_every_file_without_a_clipped_page(tmp_path, monkeypatch, which):
    from app.storyline.pagelaw import pdf_findings

    db, rows = _fixtures(tmp_path, monkeypatch)
    row = rows[0 if which == "small" else 1]
    built = _render(row)
    assert set(built) >= {"blueprint", "technical", "operations", "roadmap", "deck"}
    for key, path in built.items():
        if not path.endswith(".pdf"):
            continue
        assert pdf_findings(path) == [], key
    deck = built["deck"]
    assert _deck_overflows(deck) == []
    db.close()


@pytest.mark.parametrize("which", ["small", "large"])
def test_register_sums_to_the_headline_in_every_fixture(tmp_path, monkeypatch, which):
    db, rows = _fixtures(tmp_path, monkeypatch)
    row = rows[0 if which == "small" else 1]
    story = build(row)
    assert story is not None and story.register is not None
    low, mid, high = flexed(TERMS, settings.VALUE_FLEX_PCT)
    register = story.register
    assert sum((item.value.low for item in register.rows), Decimal(0)) == low
    assert sum((item.value.mid for item in register.rows), Decimal(0)) == mid
    assert sum((item.value.high for item in register.rows), Decimal(0)) == high
    db.close()


def test_every_page_passes_the_presentation_law(tmp_path, monkeypatch):
    db, rows = _fixtures(tmp_path, monkeypatch)
    for row in rows:
        for key, path in _render(row).items():
            if not str(path).endswith(".pdf"):
                continue
            assert export_pdf.presentation_findings(path) == [], key
    db.close()


def test_reading_only_the_proof_titles_gives_the_argument(tmp_path, monkeypatch):
    db, rows = _fixtures(tmp_path, monkeypatch)
    for row in rows:
        story = build(row)
        titles = [section.title for section in story.sections]
        assert titles
        for title in titles:
            words = {word.strip(".,").lower() for word in title.split()}
            assert words & VERBS, title
            assert title.lower() not in BARE
            assert title_lines(title) <= 2
        text = _text(_render(row)["blueprint"])
        places = [text.index(title) for title in titles]
        assert places == sorted(places)
    db.close()


def test_zip_has_exactly_the_available_files(tmp_path, monkeypatch):
    from app.routers.requests import build_zip
    from app.storyline.files import files_for

    db, rows = _fixtures(tmp_path, monkeypatch)
    row = rows[0]
    path, _stub = build_zip(row)
    expected = {item.filename for item in files_for(row) if item.available and item.key != "zip"}
    with zipfile.ZipFile(path) as bundle:
        names = {name.rsplit("/", 1)[-1] for name in bundle.namelist()}
    assert names == expected
    assert "The package.zip" not in names
    db.close()


def test_no_file_contains_a_hedging_word(tmp_path, monkeypatch):
    from pptx import Presentation

    db, rows = _fixtures(tmp_path, monkeypatch)
    for row in rows:
        for key, path in _render(row).items():
            if str(path).endswith(".pdf"):
                text = _text(path)
            else:
                prs = Presentation(path)
                text = "\n".join(
                    shape.text_frame.text
                    for slide in prs.slides
                    for shape in slide.shapes
                    if getattr(shape, "has_text_frame", False)
                )
            lowered = text.lower()
            for word in HEDGING:
                assert re.search(rf"\b{re.escape(word.lower())}\b", lowered) is None, (key, word)
    db.close()


def test_old_runs_still_build(tmp_path, monkeypatch):
    db = _db(tmp_path, monkeypatch)
    row = Request(
        business_name="Halo", business_description="A studio.", email="a@b.c",
        status="done", is_generating=False,
        mvp_blueprint="## The plan\nA studio keeps its classes full.\n",
        technical_plan="## The build\nThe booking is the work.\n",
    )
    from tests._integrity_stub import stamp_clean
    stamp_clean(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    assert build(row) is None
    blueprint = export_pdf.build_pdf(row, "blueprint")
    assert "A studio keeps its classes full" in _text(blueprint)
    db.close()
