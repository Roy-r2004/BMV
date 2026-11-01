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
