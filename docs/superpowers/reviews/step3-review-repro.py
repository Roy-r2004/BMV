"""Reviewer repros for Step 3. Not part of the repo. Each test PRINTS evidence;
assertions state the DEFECT (a passing test here = defect reproduced)."""
from __future__ import annotations

import json
from decimal import Decimal

import pymupdf
import pytest

from app.ai import provider
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.figures.model import Figure, TheirsSource, as_json
from app.models import Request

TERMS = [
    {"kind": "claim", "id": "CF-04", "value": "22", "sign": 1, "label": "her price"},
    {"kind": "constant", "value": "5", "sign": 1, "label": "days"},
    {"kind": "proposed", "value": "0.75", "sign": 1, "label": "who stay"},
]
THEIRS = Figure("CF-04", Decimal("22"), "USD", None, "theirs",
                TheirsSource(1, "price", "We charge twenty-two a class.", None, None), 0)
PHASES = [{"when": "Week 1", "title": "Set the week", "do": "Tell them.", "you": "You send it."},
          {"when": "Weeks 2 to 6", "title": "Watch it", "do": "Watch.", "you": "You look."}]
SECRET = "My partner Dana keeps losing the bookings and I am thinking of firing her."


def _text(path):
    doc = pymupdf.open(path)
    try:
        return [p.get_text() for p in doc]
    finally:
        doc.close()


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    yield s
    s.close()


def _row(db, **columns):
    row = Request(
        business_name="Halo", business_description="A studio.", email="a@b.c",
        status="done", is_generating=False, concept_name="Halo",
        brief_json=json.dumps({"question": "Should the studio keep the evening class?"}),
        main_problem=SECRET,
        case_file_json=json.dumps([as_json(THEIRS)]),
        action_plan_json=json.dumps({"status": "ready", "phases": PHASES}),
        answer_json=json.dumps({"headline": "You are full.", "turn": "Keep the class.",
                                 "move": {"value": 82.5, "unit": "USD", "period": "year", "terms": TERMS}}),
        mvp_blueprint="## The plan\nA studio keeps its classes full.\n",
        technical_plan="## The build\nThe booking is the work.\n",
        roles_json=json.dumps([{"name": "the desk", "purpose": "books the class"}]),
    )
    for k, v in columns.items():
        setattr(row, k, v)
    from tests._integrity_stub import stamp_clean
    stamp_clean(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _chat(body):
    def chat(model, messages, max_tokens=None, **kwargs):
        return {"choices": [{"message": {"content": json.dumps(body)}}], "usage": {}}
    return chat


# 1. The stage accepts register words with a bare number and a title with a token;
#    the blueprint prints both, and the law records nothing for them.
def test_register_words_and_tokens_skip_the_law(db, monkeypatch):
    from app.figures import law
    from app.pipeline import export_pdf
    from app.storyline.stage import write

    reply = {
        "register": [
            {"phase": 1, "recommendation": "Raise the price to $999 a class.", "changes": "Adds 40 bookings.",
             "owner": "the owner", "depends_on": [], "share_pct": 60, "cost_figure": None,
             "cost_needs": "a quote of $5,000 from the builder"},
            {"phase": 2, "recommendation": "Watch the week.", "changes": "The room.",
             "owner": "the desk", "depends_on": [1], "share_pct": 40, "cost_figure": "CF-04", "cost_needs": None},
        ],
        "sections": [{"id": "fact-base", "title": "The class stays full at {{F:CF-04}}",
                      "takeaway": "Keep the price at {{F:CF-04}}."}],
    }
    row = _row(db, status="generating", is_generating=True)
    monkeypatch.setattr(provider, "chat", _chat(reply))
    write(db, row.id)
    db.refresh(row)
    print("\nSTORED:", row.storyline_json[:400])
    row.status, row.is_generating = "done", False
    db.commit()
    db.refresh(row)
    path = export_pdf.build_pdf(row, "blueprint")
    pages = _text(path)
    full = "\n".join(pages)
    for needle in ("$999", "40 bookings", "$5,000", "{{F:CF-04}}"):
        print(f"PDF has {needle!r}:", needle in full)
    found = law.recorded(row).get("Volume I") or []
    print("LAW FINDINGS Volume I:", [(f.number, f.page) for f in found])
    print("RELEASE:", export_pdf.release_status(row)["status"], export_pdf.release_status(row)["reasons"])
    assert "$999" in full and "{{F:CF-04}}" in full
    assert not any(f.number in ("$999", "$5,000") for f in found)


# 2. A run with an answer but no storyline (every Step-2 run) now opens on the answer page.
def test_legacy_run_with_answer_changes(db):
    from app.pipeline import export_pdf
    from app.storyline.build import build

    row = _row(db, storyline_json=None)
    print("\nbuild() for a legacy run:", type(build(row)).__name__)
    pages = _text(export_pdf.build_pdf(row, "blueprint"))
    print("PAGE 1:", pages[0][:300].replace("\n", " | "))
    assert "What this rests on" in pages[0] or "Should the studio" in pages[0]


# 3. The share link's JSON carries the owner's intake words.
def test_shared_payload_leaks_main_problem(db):
    from fastapi.testclient import TestClient
    from main import app

    _row(db, share_token="reviewer-share-1")
    body = TestClient(app).get("/api/shared/reviewer-share-1").json()
    page = body.get("answer_page") or {}
    print("\nSHARED answer_page.believed:", page.get("believed"))
    print("SHARED answer_page.question:", page.get("question"))
    assert page.get("believed") == SECRET


# 4. The DRAFT cover prints release reasons verbatim (jargon / internal words).
def test_draft_cover_prints_internal_reasons(db):
    from app.pipeline import export_pdf as ep

    row = _row(db, qa_report_json=json.dumps({"checks": [], "findings": [
        {"id": "x", "severity": "high", "title": "open finding", "detail": "x"}]}))
    cover = " ".join(getattr(f, "text", "") for f in ep._cover("blueprint", "The Blueprint", "Volume I", row))
    print("\nCOVER:", cover[:600])
    assert "quality bench" in cover or "integrity layer" in cover


# 5. The waterfall prints a non-money term as dollars and tags a product of the client's numbers as theirs.
def test_waterfall_units_and_tags(db):
    from app.storyline.exhibits import for_section

    terms = [
        {"kind": "claim", "id": "CF-09", "value": "12", "sign": 1, "label": "empty spots a week"},
        {"kind": "claim", "id": "CF-04", "value": "22", "sign": 1, "label": "her price"},
        {"kind": "proposed", "value": "0.75", "sign": 1, "label": "who stay"},
    ]
    row = _row(db, answer_json=json.dumps({"headline": "x", "move": {"value": 198, "unit": "USD",
                                                                      "period": "week", "terms": terms}}))
    ex = for_section(row, "prize")
    for r in ex.data["rows"]:
        print("\nWATERFALL ROW:", r["label"], r["display"], r["tag"])
    first, second = ex.data["rows"][0], ex.data["rows"][1]
    assert first["display"].startswith("$")          # 12 spots printed as money
    assert second["tag"] == "yours"                  # 12 x 22 is worked out, tagged as the client's


# 6. The deck: a 12-row exhibit runs under the section takeaway and past the slide foot.
def test_deck_exhibit_rows_overlap(db, monkeypatch):
    from app.storyline import files

    grid = {"grid": [{"day": "Mon", "slots": [{"time": f"Class {chr(65 + i)}", "taken": 3} for i in range(14)]}]}
    row = _row(db, capacity_json=json.dumps(grid),
               storyline_json=json.dumps({"register": [
                   {"phase": 1, "recommendation": "Keep it.", "changes": "x", "owner": "o", "depends_on": [],
                    "share_pct": 100, "cost_figure": "CF-04", "cost_needs": None}],
                   "sections": [{"id": "week", "title": "The week is full", "takeaway": "The evening class stays."}]}))
    from pptx import Presentation
    path = files.render_file(row, "deck")
    prs = Presentation(path)
    H = prs.slide_height
    for n, slide in enumerate(prs.slides, 1):
        boxes = [(s.top, s.top + s.height, s.text_frame.text[:30]) for s in slide.shapes if s.has_text_frame]
        if any("The week is full" in b[2] for b in boxes):
            print("\nSLIDE", n, "height(in)=", H / 914400)
            for top, bottom, text in boxes:
                print(f"  {top/914400:.2f}-{bottom/914400:.2f} {text!r}")
            take = [b for b in boxes if b[2].startswith("The evening class stays")][0]
            rows = [b for b in boxes if b[2].startswith("Class ") or b[2].startswith("Other")]
            assert any(r[1] > take[0] for r in rows) or any(r[1] > H for r in rows)


# 7. The same stored title in the deck, the PDF and the web.
def test_title_token_in_each_file(db):
    from pptx import Presentation
    from app.pipeline import export_pdf
    from app.storyline import files
    from app.storyline.build import for_web

    row = _row(db, storyline_json=json.dumps({"register": [
        {"phase": 1, "recommendation": "Keep the price at {{F:CF-04}}.", "changes": "x", "owner": "o",
         "depends_on": [], "share_pct": 60, "cost_figure": "CF-04", "cost_needs": None},
        {"phase": 2, "recommendation": "Watch.", "changes": "x", "owner": "o",
         "depends_on": [1], "share_pct": 40, "cost_figure": "CF-04", "cost_needs": None}],
        "sections": [{"id": "fact-base", "title": "The class stays full at {{F:CF-04}}", "takeaway": "x"}]}))
    pdf = "\n".join(_text(export_pdf.build_pdf(row, "blueprint")))
    prs = Presentation(files.render_file(row, "deck"))
    deck = "\n".join(s.text_frame.text for sl in prs.slides for s in sl.shapes if s.has_text_frame)
    web = for_web(row)["register"]["rows"][0]["recommendation"]
    print("\nPDF title line:", [l for l in pdf.splitlines() if "stays full" in l])
    print("DECK title line:", [l for l in deck.splitlines() if "stays full" in l])
    print("PDF register:", [l for l in pdf.splitlines() if "Keep the price" in l])
    print("DECK register:", [l for l in deck.splitlines() if "Keep the price" in l])
    print("WEB register:", web)


# 8. The waterfall's own figures join the known set, so the law accepts them in any text.
def test_waterfall_figures_vouch_for_numbers(db):
    from app.figures.bind import bind
    from app.figures.known import known_for

    terms = [
        {"kind": "claim", "id": "CF-04", "value": "22", "sign": 1, "label": "her price"},
        {"kind": "claim", "id": "CF-04", "value": "22", "sign": 1, "label": "her price again"},
        {"kind": "proposed", "value": "0.75", "sign": 1, "label": "who stay"},
    ]
    row = _row(db, answer_json=json.dumps({"headline": "x", "move": {"value": 363, "unit": "USD",
                                                                      "period": "week", "terms": terms}}))
    known = known_for(row)
    f = known.get("EX-PRIZE-2")
    print("\nEX-PRIZE-2:", f.value, f.unit, f.kind, type(f.source).__name__)
    without = known_for(row, leave_out={"exhibits"})
    text = "Her studio already makes $484 a week."
    print("unresolved with exhibits:", [u.text for u in bind(text, known).unresolved])
    print("unresolved without exhibits:", [u.text for u in bind(text, without).unresolved])
    assert f.kind == "theirs"
