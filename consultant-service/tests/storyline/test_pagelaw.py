"""The page law is measured, not hoped for.

A title that needs a third line is named. The type size stays the size it
is. The foot goes in one order. A stamp is one of the five words. A page
that clips makes the file a draft, and the reason names the page.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.database import Base, SessionLocal, engine
from app.models import Request
from app.pipeline.export_pdf import release_status
from app.storyline.model import Exhibit, Section
from app.storyline.pagelaw import TITLE_SIZE, check_section


def _section(title, **over) -> Section:
    fields = dict(id="week", title=title, takeaway="The class stays.", exhibit=None,
                  footnotes=(), note=None, sources=(), stamp=None)
    fields.update(over)
    return Section(**fields)


def test_a_two_line_title_passes_and_a_three_line_title_is_named():
    assert check_section(_section("Keep the evening class")) == []
    long = " ".join(["evening"] * 80)
    reasons = check_section(_section(long))
    assert reasons and "two lines" in " ".join(reasons)


def test_a_title_is_never_shrunk(monkeypatch):
    seen = []

    def width(text, font, size):
        seen.append(size)
        return 1.0

    monkeypatch.setattr("app.storyline.pagelaw.stringWidth", width)
    assert check_section(_section("Keep the evening class")) == []
    assert seen and set(seen) == {TITLE_SIZE}


def _lined(title, foot, exhibit=None):
    return SimpleNamespace(
        id="week", title=title, takeaway="The class stays.", exhibit=exhibit,
        footnotes=(), note=None, sources=(), stamp=None, foot=foot,
    )


def test_foot_parts_out_of_order_are_reported():
    section = _lined("Keep the evening class", (
        "Source: the class list. BMV analysis",
        "1. Her price.",
    ))
    reasons = check_section(section)
    assert any("order" in reason.lower() for reason in reasons)


def test_source_line_ends_with_bmv_analysis_only_when_a_number_is_ours_or_derived():
    ours = Exhibit("1.1", "bar", "How full", "Each class.",
                   {"rows": [{"tag": "our estimate"}]}, "The move")
    theirs = Exhibit("1.1", "bar", "How full", "Each class.",
                     {"rows": [{"tag": "yours"}]}, "Her week")
    missing = check_section(_lined("Keep the evening class", ("Source: the class list.",), ours))
    extra = check_section(_lined("Keep the evening class", ("Source: the class list. BMV analysis",), theirs))
    assert any("BMV analysis" in reason for reason in missing)
    assert any("BMV analysis" in reason for reason in extra)
    assert check_section(_lined(
        "Keep the evening class", ("Source: the class list. BMV analysis",), ours)) == []


def test_unknown_stamp_is_rejected():
    assert check_section(_section("Keep the evening class", stamp="ESTIMATE")) == []
    reasons = check_section(_section("Keep the evening class", stamp="DRAFT"))
    assert reasons and "DRAFT" in " ".join(reasons)


def test_a_clipped_pdf_becomes_a_draft_naming_its_page(tmp_path, monkeypatch):
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(tmp_path))
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    row = Request(
        business_name="Halo", business_description="A studio.", email="a@b.c",
        status="done", is_generating=False, mvp_blueprint="The plan.",
        storyline_json="{}",
        qa_report_json=json.dumps({"checks": [], "findings": []}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    folder = os.path.join(str(tmp_path), "exports")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{row.id}-blueprint.pdf")
    sheet = canvas.Canvas(path, pagesize=A4)
    sheet.setFont("Helvetica", 10)
    sheet.drawString(2, 400, "This line sits in the margin.")
    sheet.showPage()
    sheet.save()
    status = release_status(row)
    assert status["status"] == "draft"
    assert any("page 1" in reason for reason in status["reasons"])
    db.close()
