"""The files open on the answer. The register is in the blueprint. A run
with no answer is the file it was before.
"""
from __future__ import annotations

import hashlib
import json
import os
from decimal import Decimal

import pymupdf

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.figures.model import Figure, TheirsSource, as_json
from app.models import Request
from app.pipeline import export_pdf
from app.storyline.pdf import answer_page_flowables
from app.storyline.build import build

TERMS = [
    {"kind": "claim", "id": "CF-04", "value": "22", "sign": 1, "label": "her price"},
    {"kind": "constant", "value": "5", "sign": 1, "label": "days"},
    {"kind": "proposed", "value": "0.75", "sign": 1, "label": "who stay"},
]
THEIRS = Figure("CF-04", Decimal("22"), "USD", None, "theirs",
                TheirsSource(1, "price", "We charge twenty-two a class.", None, None), 0)
HEDGING = ("confident", "not sure", "validation", "AI-native", "review by a human")
QUESTION = "Should the studio keep the evening class?"


def _pages(path: str) -> list[str]:
    doc = pymupdf.open(path)
    try:
        return [page.get_text() for page in doc]
    finally:
        doc.close()


def _seed(db, **columns) -> Request:
    phases = [{"when": "Week 1", "title": "Set the week", "do": "Tell them.", "you": "You send it."},
              {"when": "Later", "title": "Watch it", "do": "Watch.", "you": "You look."}]
    rows = []
    for n, share in enumerate((60, 40), 1):
        rows.append({
            "phase": n, "recommendation": "Keep the evening class." if n == 1 else "Watch the week.",
            "changes": "The evening class.", "owner": "the owner", "depends_on": [1] if n > 1 else [],
            "share_pct": share, "cost_figure": "CF-04", "cost_needs": None,
        })
    row = Request(
        business_name="Halo", business_description="A studio.", email="a@b.c",
        status="done", is_generating=False, concept_name="Halo",
        brief_json=json.dumps({"question": QUESTION}),
        case_file_json=json.dumps([as_json(THEIRS)]),
        action_plan_json=json.dumps({"status": "ready", "phases": phases}),
        answer_json=json.dumps({"headline": "You are full.", "turn": "Keep the class.",
                                 "move": {"value": 82.5, "unit": "USD", "period": "year", "terms": TERMS}}),
        storyline_json=json.dumps({"register": rows, "sections": [
            {"id": "week", "title": "How full the week is", "takeaway": "The evening class is the one to keep."},
        ]}),
        mvp_blueprint="## The plan\nA studio keeps its classes full.\n",
        technical_plan="## The build\nThe booking is the work.\n",
        procedures_json=json.dumps({"procedures": [{"name": "Opening", "trigger": "the morning",
                                                    "steps": [{"actor": "owner", "step": "unlock"}],
                                                    "exceptions": []}]}),
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


def test_every_pdf_kind_opens_with_the_answer_page(tmp_path, monkeypatch):
    db, row = _ready(tmp_path, monkeypatch)
    for kind in ("blueprint", "technical", "operations"):
        pages = _pages(export_pdf.build_pdf(row, kind))
        assert QUESTION in pages[0] and "What this rests on" in pages[0], kind
    db.close()


def test_the_register_is_in_the_blueprint_and_only_referenced_elsewhere(tmp_path, monkeypatch):
    db, row = _ready(tmp_path, monkeypatch)
    blueprint = "\n".join(_pages(export_pdf.build_pdf(row, "blueprint")))
    technical = "\n".join(_pages(export_pdf.build_pdf(row, "technical")))
    assert "Keep the evening class." in blueprint
    assert "The register is in the blueprint." in technical
    assert "Keep the evening class." not in technical
    db.close()


def test_a_legacy_run_builds_as_before(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    row = _seed(db, answer_json=None, storyline_json=None, brief_json=None)
    first = export_pdf.build_pdf(row, "blueprint")
    digest = hashlib.sha256(open(first, "rb").read()).hexdigest()
    os.remove(first)
    second = export_pdf.build_pdf(row, "blueprint")
    assert hashlib.sha256(open(second, "rb").read()).hexdigest() == digest
    assert "What this rests on" not in "\n".join(_pages(second))
    db.close()


def test_answer_page_fits_one_page_at_the_longest_inputs(tmp_path, monkeypatch):
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate

    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    long = "the evening class " * 12
    row = _seed(db, brief_json=json.dumps({"question": long.strip()}),
                main_problem=long.strip(),
                answer_json=json.dumps({"headline": long.strip(), "turn": long.strip(),
                                        "move": {"value": 82.5, "unit": "USD", "period": "year", "terms": TERMS}}))
    path = os.path.join(str(tmp_path), "answer.pdf")
    doc = BaseDocTemplate(path, pagesize=A4)
    frame = Frame(18 * 2.834, 20 * 2.834, A4[0] - 36 * 2.834, A4[1] - 36 * 2.834, id="body")
    doc.addPageTemplates([PageTemplate(id="body", frames=[frame])])
    doc.build(answer_page_flowables(build(row)))
    assert len(_pages(path)) == 1
    db.close()


def test_pdf_text_has_no_hedging_words(tmp_path, monkeypatch):
    db, row = _ready(tmp_path, monkeypatch)
    for kind in ("blueprint", "technical", "operations"):
        text = "\n".join(_pages(export_pdf.build_pdf(row, kind)))
        for word in HEDGING:
            assert word not in text, (kind, word)
    db.close()


def test_register_rows_at_the_maximum_do_not_clip(tmp_path, monkeypatch):
    from app.engine.gates.presentation import clipping_findings

    db, row = _ready(tmp_path, monkeypatch)
    shares = [13] * 4 + [12] * 4
    rows = []
    for n, share in enumerate(shares, 1):
        rows.append({
            "phase": 1, "recommendation": f"Keep the class {n}.", "changes": "The week.",
            "owner": "the owner", "depends_on": [], "share_pct": share,
            "cost_figure": "CF-04", "cost_needs": None,
        })
    row.storyline_json = json.dumps({"register": rows, "sections": []})
    db.commit()
    path = export_pdf.build_pdf(row, "blueprint")
    # The cover's panel is painted outside the body frame on purpose. A row
    # that clips would be a finding that is not one of those spans.
    found = [
        reason for reason in clipping_findings(path, frame_mm={"left": 18, "bottom": 20, "top": 16})
        if not reason.endswith(export_pdf.COVER_PANEL_SPANS)
    ]
    assert found == []
    db.close()


def test_a_one_person_studio_operations_manual_is_not_padded(tmp_path, monkeypatch):
    db, row = _ready(tmp_path, monkeypatch)
    pages = _pages(export_pdf.build_pdf(row, "operations"))
    assert 1 <= len(pages) <= 6
    db.close()


def test_the_rests_line_names_our_estimates_when_that_is_what_it_rests_on():
    from app.storyline.model import RestsOn
    from app.storyline.pdf import rests_line

    assert rests_line(RestsOn(0, 0, 2, 0, 0, 0)) == "What this rests on: our estimates."
    assert rests_line(RestsOn(0, 0, 0, 0, 0, 0)) is None


def test_a_system_file_is_not_judged_on_the_volume_frame(tmp_path, monkeypatch):
    db, row = _ready(tmp_path, monkeypatch)
    folder = os.path.join(str(tmp_path), "exports")
    os.makedirs(folder)
    system = os.path.join(folder, f"{row.id}-system.pdf")
    open(system, "wb").close()
    seen = []

    def record(path, frame_mm=None):
        seen.append(os.path.basename(path))
        return []

    monkeypatch.setattr("app.engine.gates.presentation.clipping_findings", record)
    export_pdf._presentation_reasons(row)
    assert seen == []
    db.close()


def _deck_text(path: str) -> str:
    from pptx import Presentation

    prs = Presentation(path)
    return "\n".join(s.text_frame.text for sl in prs.slides for s in sl.shapes if s.has_text_frame)


def test_register_words_on_a_page_go_through_the_number_law(tmp_path, monkeypatch):
    # Review C1: a stored "$999" and "$5,000" printed on the register page and the
    # law recorded nothing for Volume I.
    from app.figures import law

    db, row = _ready(tmp_path, monkeypatch)
    stored = json.loads(row.storyline_json)
    stored["register"][0]["recommendation"] = "Raise the price to $999 a class."
    stored["register"][1]["cost_figure"] = None
    stored["register"][1]["cost_needs"] = "a quote of $5,000 from the builder"
    row.storyline_json = json.dumps(stored)
    db.commit()
    export_pdf.build_pdf(row, "blueprint")
    numbers = {f.number for f in law.recorded(row)["Volume I"]}
    assert {"$999", "$5,000"} <= numbers
    assert any("$999" in reason for reason in export_pdf.release_status(row)["reasons"])
    db.close()


def test_the_flex_footnote_is_not_a_number_nobody_owns(tmp_path, monkeypatch):
    from app.figures import law

    db, row = _ready(tmp_path, monkeypatch)
    text = "\n".join(_pages(export_pdf.build_pdf(row, "blueprint")))
    assert "Flexes our assumption of 75% by 20% either way." in text
    assert law.recorded(row)["Volume I"] == []
    db.close()


def test_a_title_token_prints_as_its_figure_in_every_file(tmp_path, monkeypatch):
    # Review C2: the blueprint printed "{{F:CF-04}}" where the deck printed "$22".
    from app.storyline import files
    from app.storyline.build import for_web

    db, row = _ready(tmp_path, monkeypatch)
    stored = json.loads(row.storyline_json)
    stored["register"][0]["recommendation"] = "Keep the price at {{F:CF-04}}."
    stored["sections"] = [{"id": "fact-base", "title": "The class stays full at {{F:CF-04}}", "takeaway": "x"}]
    row.storyline_json = json.dumps(stored)
    row.roles_json = json.dumps([{"name": "the desk", "purpose": "books the class"}])
    db.commit()
    pdf = "\n".join(_pages(export_pdf.build_pdf(row, "blueprint")))
    deck = _deck_text(files.render_file(row, "deck"))
    web = for_web(row)
    for text in (pdf, deck):
        assert "{{" not in text
        assert "The class stays full at $22" in text
        assert "Keep the price at $22." in text
    assert web["register"]["rows"][0]["recommendation"] == "Keep the price at $22."
    db.close()


def test_a_run_from_before_the_storyline_opens_every_file_on_its_cover(tmp_path, monkeypatch):
    # Review H2: a Step-2 run (answer stored, storyline_json NULL) opened every
    # volume and the roadmap on the answer page instead of the cover.
    from app.storyline import roadmap

    db, row = _ready(tmp_path, monkeypatch)
    row.storyline_json = None
    db.commit()
    assert build(row) is None
    for kind in ("blueprint", "technical", "operations"):
        pages = _pages(export_pdf.build_pdf(row, kind))
        assert "Prepared exclusively" in pages[0], kind
        text = "\n".join(pages)
        assert QUESTION not in text and "What this rests on" not in text, kind
        assert "The register" not in text, kind
    road = "\n".join(_pages(roadmap.build_roadmap_pdf(row)))
    assert QUESTION not in road and "The register is in the blueprint." not in road
    db.close()


def test_volume_iv_opens_on_the_whole_answer_page_after_its_doctype(tmp_path, monkeypatch):
    # Review H3/M6: the answer was concatenated in front of the template's
    # <!doctype html> (quirks mode for every page) and was only the question
    # and the rests-on line.
    from app.screens import export as screens_export
    from app.screens import render

    db, row = _ready(tmp_path, monkeypatch)
    row.main_problem = "The evening class is too quiet."
    db.commit()
    html, _found = screens_export._proposal(row, render.load_example())
    assert html.lstrip().lower().startswith("<!doctype html>")
    first = screens_export.page_texts(html)[0]
    for part in (QUESTION, "You are full.", "Keep the class.", "What you believed:",
                 "The evening class is too quiet.", "Monday:", "What this rests on"):
        assert part in first, part
    db.close()


def test_volume_iv_of_a_run_with_no_storyline_has_no_answer_page(tmp_path, monkeypatch):
    from app.screens import export as screens_export
    from app.screens import render

    db, row = _ready(tmp_path, monkeypatch)
    row.storyline_json = None
    db.commit()
    html, _found = screens_export._proposal(row, render.load_example())
    assert QUESTION not in html and "What this rests on" not in html
    db.close()


def test_the_blueprint_register_has_every_column_its_ranges_cost_and_headline(tmp_path, monkeypatch):
    # Review H5: each row printed as "{recommendation} {when} {owner}" run together,
    # with no range, no cost, no "what it changes", no dependency and no headline.
    from app.figures import law
    from app.storyline.build import for_web

    db, row = _ready(tmp_path, monkeypatch)
    stored = json.loads(row.storyline_json)
    stored["register"][1]["cost_figure"] = None
    stored["register"][1]["cost_needs"] = "a quote from the builder"
    row.storyline_json = json.dumps(stored)
    db.commit()
    text = " ".join("\n".join(_pages(export_pdf.build_pdf(row, "blueprint"))).split())
    for column in ("Recommendation", "What it changes", "Value", "Cost", "Owner", "When", "Depends on"):
        assert column in text, column
    assert "$39.60 to $59.40 a year" in text and "$26.40 to $39.60 a year" in text
    assert "All together" in text and "$66 to $99 a year" in text
    assert "Not priced yet" in text and "Not priced yet: needs a quote from the builder." in text
    assert "After 1" in text
    assert law.recorded(row)["Volume I"] == []
    web = for_web(row)["register"]
    assert web["rows"][0]["cost"]["display"] == "$22" and web["rows"][1]["cost"] is None
    assert web["rows"][1]["cost_text"] == "Not priced yet"
    assert web["rows"][1]["cost_needs"] == "a quote from the builder"
    assert web["rows"][0]["value_text"] == "$39.60 to $59.40 a year"
    assert web["total"]["low"]["display"] == "$66" and web["total_text"] == "$66 to $99 a year"
    db.close()


GRID = {"shape": "weekly_grid", "unit": "spot", "unit_plural": "spots",
        "grid": [{"day": "Mon", "slots": [{"time": "Morning", "taken": 4, "capacity": 12},
                                          {"time": "Evening", "taken": 11, "capacity": 12}]}]}


def test_an_exhibit_reaches_its_lead_page_with_its_number_foot_and_stamp(tmp_path, monkeypatch):
    # Review M1: draw_pdf was called nowhere, the lead page printed only the
    # caption, every exhibit was "1.1", and there was no foot and no stamp.
    from app.figures import law
    from app.storyline.pagelaw import check_section

    db, row = _ready(tmp_path, monkeypatch)
    row.capacity_json = json.dumps(GRID)
    stored = json.loads(row.storyline_json)
    stored["sections"] = [{"id": "fact-base", "title": "The studio is full in the evening", "takeaway": "x"},
                          {"id": "week", "title": "How full the week is", "takeaway": "The evening class stays."}]
    row.storyline_json = json.dumps(stored)
    db.commit()
    story = build(row)
    week = story.sections[1]
    assert week.exhibit.id == "2.1" and check_section(week) == []
    assert week.foot[-1] == "Source: Your week; BMV analysis"
    text = " ".join("\n".join(_pages(export_pdf.build_pdf(row, "blueprint"))).split())
    assert "Exhibit 2.1: How full each class is" in text
    assert "Evening 11 spots worked out" in text
    assert "Source: Your week; BMV analysis" in text
    assert "Note: worked out is our arithmetic on your figures" in text
    assert law.recorded(row)["Volume I"] == []
    db.close()


def test_a_section_with_our_estimate_carries_the_estimate_stamp(tmp_path, monkeypatch):
    db, row = _ready(tmp_path, monkeypatch)
    stored = json.loads(row.storyline_json)
    stored["sections"] = [{"id": "prize", "title": "Where the prize comes from", "takeaway": "x"}]
    row.storyline_json = json.dumps(stored)
    db.commit()
    prize = build(row).sections[0]
    assert prize.stamp == "ESTIMATE"
    text = "\n".join(_pages(export_pdf.build_pdf(row, "blueprint")))
    assert "ESTIMATE" in text and "Exhibit 1.1: Where the prize comes from" in " ".join(text.split())
    db.close()
