"""The release law: a rendered document holds no number nobody owns.

Pins: `check` binds what it can and records the rest, never raises, and reads
nothing outside a scope (so the engine's work products are unchanged); page
furniture, labels, dates and plan positions pass; a sample region is not read
and cannot be drawn without its stamp; the blueprint PDF with one untagged
number is a draft whose reason names the page, and the same PDF without it is
not; a verified financial-model line passes and an unverified one is flagged;
the deck names the slide; a rebuild replaces stale findings; the proposal's
cover hero is the answer's first headline figure, never a sample tile; and the
client's emails carry no figures.
"""
import json
import os
import re

import pytest

from app.figures import law
from app.figures.known import known_for_texts
from app.figures.model import FigureSet

REASON_TAIL = " none of the client's figures, our workings, our estimates or a cited reference"


#: the client's figures as the case file reads them from their own words
KNOWN = known_for_texts(["I have 12 reformers and charge $22 a class."])


# -- check ------------------------------------------------------------------------------------

def test_outside_a_scope_check_reads_nothing_and_finds_nothing():
    assert law.active() is None
    assert law.check("They lose 37 calls a week.") == "They lose 37 calls a week."


def test_check_binds_what_it_knows_and_records_what_it_does_not():
    with law.scope(KNOWN, where="Volume I") as s:
        out = law.check("You have twelve reformers at $22 a class and lose 37 calls a week.")
    assert out == "You have 12 reformers at $22 a class and lose 37 calls a week."
    assert [(f.number, f.region, f.page) for f in s.findings] == [("37", "Volume I", None)]
    assert "37 calls a week" in s.findings[0].snippet


def test_furniture_labels_dates_and_plan_positions_pass():
    """Review Focus 3: a document whose only numbers are page furniture, labels,
    dates and plan positions passes the law."""
    with law.scope(FigureSet(), where="Volume II") as s:
        for text in ("Volume II", "See page 7.", "Phase 2", "Section 3 and Exhibit 2.1",
                     "We start on 3 March 2026.", "Measure it in week 1.", "Weeks 1-2: set up",
                     "Prepared exclusively · November 01, 2026"):
            assert law.check(text) == text
    assert s.findings == []


def test_a_clock_time_is_checked_against_the_hours_they_gave():
    with law.scope(FigureSet(), where="Volume I", hours={18}) as s:
        law.check("Classes at 6pm fill first; the 9pm slot is new.")
    assert [f.number for f in s.findings] == ["9pm"]


@pytest.mark.parametrize("weird", [None, 37, 3.5, b"37 calls", "", " ", "\x00 37 \x00", "\ud800 37",
                                   "{{F:", "{{F:NOPE}} and {{F:", "9" * 5000, "$" * 300 + "1",
                                   "1,2,3,4,5,6,7,8,9," * 200, "٣٥ calls"])
def test_check_never_raises_on_weird_input(weird):
    with law.scope(KNOWN, where="Volume I"):
        out = law.check(weird)
    if not isinstance(weird, str):
        assert out is weird


def test_a_binder_that_fails_still_reports_every_number(monkeypatch):
    from app.figures import bind as bind_module

    def broken(*a, **k):
        raise RuntimeError("binder bug")

    monkeypatch.setattr(bind_module, "bind", broken)
    with law.scope(KNOWN, where="Volume I") as s:
        out = law.check("They lose 37 calls and 12 hours.")
    assert out == "They lose 37 calls and 12 hours."
    assert [f.number for f in s.findings] == ["37", "12"]


def test_a_stage_that_fails_part_way_records_each_number_once(monkeypatch):
    real = law.snippet
    calls = {"n": 0}

    def flaky(text, start, end):
        calls["n"] += 1
        if calls["n"] == 2:                     # the binder's second finding fails
            raise RuntimeError("snippet bug")
        return real(text, start, end)

    monkeypatch.setattr(law, "snippet", flaky)
    with law.scope(FigureSet(), where="Volume I") as s:
        law.check("They lose 37 calls and 41 hours.")
    assert [f.number for f in s.findings] == ["37", "41"]


def test_a_working_passes_its_constants_and_a_fraction_of_a_percent_we_hold():
    known = known_for_texts(["About 12% of visits are no-shows, at $95 a visit."])
    with law.scope(known, where="Volume I") as s:
        law.check("900 × 0.12 × $95 × 52", region="working", constants=[52, 12],
                  fractions_as_percent=True)
    # "900 x" is read with its operator; it is the one operand nobody gave
    assert [(f.number.split()[0], f.region) for f in s.findings] == [("900", "working")]


def test_the_record_path_takes_only_a_whole_number_id(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    assert law.findings_path(12, "Volume I").endswith("12-law-volume-i.json")
    assert law.findings_path("12", "Volume I") == law.findings_path(12, "Volume I")
    for bad in (None, True, "abc", 12.5, "../12", "12/x"):
        assert law.findings_path(bad, "Volume I") is None


def test_saves_of_one_document_never_share_a_temporary_file(tmp_path, monkeypatch):
    import threading
    from datetime import datetime

    from app.config import settings

    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    results = []

    def save(n):
        results.append(law.save(7, "Volume I", [law.Finding(str(n), f"x {n}", "Volume I", n)],
                                built_at=datetime(2026, 1, 1)))

    threads = [threading.Thread(target=save, args=(n,)) for n in range(1, 9)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(results)
    left = os.listdir(os.path.join(str(tmp_path), "exports"))
    assert left == ["7-law-volume-i.json"], left
    with open(os.path.join(str(tmp_path), "exports", left[0]), encoding="utf-8") as fh:
        assert len(json.load(fh)["findings"]) == 1


def test_an_unstamped_sample_is_not_a_value_error():
    assert not issubclass(law.UnstampedSample, ValueError)


@pytest.mark.parametrize("numbers", ["number half a dozen matches", "number twelve hundred matches",
                                     "number $9,000 matches", "numbers 35, half a dozen and 12 match"])
def test_the_clients_sentence_covers_numbers_written_with_spaces(numbers):
    from app.pipeline.method_note import GENERIC_REASON, plain_reason

    reason = f"Volume I, page 7: the {numbers}" + REASON_TAIL
    assert plain_reason(reason) != GENERIC_REASON
    assert plain_reason("also " + reason) == GENERIC_REASON


def test_findings_are_stable_and_sorted():
    def run():
        with law.scope(FigureSet(), where="Volume I") as s:
            law.check("First 41 here.")
            law.check("Then 43 there.")
        return s.findings

    assert run() == run()
    mixed = [law.Finding("5", "a 5", "The deck", 2), law.Finding("9", "b 9", "Volume I", None),
             law.Finding("7", "c 7", "Volume I", 4), law.Finding("8", "d 8", "Volume I", 4),
             law.Finding("6", "e 6", "Volume II", 1)]
    assert [f.number for f in law.sorted_findings(mixed)] == ["7", "8", "9", "6", "5"]
    assert law.sorted_findings(law.sorted_findings(mixed)) == law.sorted_findings(mixed)


def test_one_reason_per_page_in_team_words():
    by_doc = {"Volume I": [law.Finding("35", "x 35", "Volume I", 7), law.Finding("12", "y 12", "Volume I", 7),
                           law.Finding("35", "z 35", "Volume I", 7), law.Finding("4", "w 4", "Volume I", None)],
              "The deck": [law.Finding("9", "v 9", "The deck", 3)], "Volume II": None}
    assert law.page_reasons(by_doc) == [
        ("Volume I", "page 7", "the numbers 35 and 12 match"),
        ("Volume I", "page not located", "the number 4 matches"),
        ("The deck", "slide 3", "the number 9 matches"),
    ]


def test_a_sample_region_is_not_read():
    with law.scope(FigureSet(), where="Volume IV") as s:
        with law.sample_region():
            assert law.check("58/72 spots filled") == "58/72 spots filled"
        law.check("58 spots")
    assert [f.number for f in s.findings] == ["58"]


# -- the PDF volumes ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path, monkeypatch):
    from app import models  # noqa: F401 - registers the tables on Base
    from app.config import settings
    from app.database import Base, SessionLocal, engine

    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


FACTS = json.dumps([{"question": "How many no-shows do you get in a week?", "answer": "About 3 no-shows a week"},
                    {"question": "What does one visit cost?", "answer": "$95 a visit"}])
VERIFIED = {"item": "No-shows", "arithmetic": "3 no-shows/week × $95 × 52 weeks",
            "annual": "$14,820/year", "arithmetic_verified": True, "unit": "USD"}
UNVERIFIED = {"item": "Front desk time", "arithmetic": "front desk hours plus overtime", "annual": "$9,000/year"}
CLEAN_MD = ("## Executive summary\nA plan for the clinic: fewer missed visits and a calmer front desk.\n\n"
            "### Where you are today\n- **Bookings:** taken by phone\n1. answer every call\n")
INJECTED_MD = CLEAN_MD.replace("a calmer front desk.", "a calmer front desk that loses 37 calls on a busy day.")


def _seed(db, **overrides):
    from app.models import Request
    from tests._integrity_stub import stamp_clean

    row = Request(business_name="Beacon Physiotherapy", business_description="A physiotherapy clinic.",
                  concept_name="BeaconOS", email="t@example.com", status="done", is_generating=False,
                  ops_numbers_json=FACTS, qa_report_json=json.dumps({"checks": [], "findings": []}))
    for k, v in overrides.items():
        setattr(row, k, v)
    stamp_clean(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _law_reasons(status: dict) -> list[str]:
    return [r for r in status["reasons"] if r.endswith(REASON_TAIL)]


def _pages_holding(pdf_path: str, needle: str) -> list[int]:
    import pymupdf

    doc = pymupdf.open(pdf_path)
    try:
        return [n + 1 for n, page in enumerate(doc) if needle in re.sub(r"\s+", " ", page.get_text())]
    finally:
        doc.close()


def test_acceptance_an_untagged_number_makes_the_blueprint_a_draft_that_names_its_page(db):
    from app.pipeline import export_pdf as ep

    row = _seed(db, mvp_blueprint=INJECTED_MD)
    path = ep.build_pdf(row, "blueprint")
    status = ep.release_status(row)
    assert status["status"] == "draft"
    pages = _pages_holding(path, "loses 37 calls")
    assert len(pages) == 1
    assert _law_reasons(status) == [f"Volume I, page {pages[0]}: the number 37 matches" + REASON_TAIL]
    assert status["law"]["Volume I"] == "1 number nobody owns"


def test_acceptance_the_same_blueprint_without_it_is_not_a_draft_because_of_the_law(db):
    from app.pipeline import export_pdf as ep

    row = _seed(db, mvp_blueprint=CLEAN_MD)
    ep.build_pdf(row, "blueprint")
    status = ep.release_status(row)
    assert _law_reasons(status) == []
    assert status["status"] == "final", status["reasons"]
    assert law.recorded(row)["Volume I"] == []
    assert status["law"]["Volume I"] == "checked"
    # every document of the package was checked before the cover was stamped
    assert set(status["law"].values()) <= {"checked", "not produced"}, status["law"]


# -- the package-level gate ------------------------------------------------------------------

def _cover_text(path: str) -> str:
    import pymupdf

    doc = pymupdf.open(path)
    try:
        return doc[0].get_text()
    finally:
        doc.close()


def test_a_finding_in_volume_two_stamps_volume_one_draft_even_when_volume_one_is_built_first(db):
    from app.pipeline import export_pdf as ep
    from tests._integrity_stub import stamp_clean

    row = _seed(db, mvp_blueprint=CLEAN_MD, technical_plan="## The build\nWe will add 37 screens.\n")
    path = ep.build_pdf(row, "blueprint")
    assert "DRAFT" in _cover_text(path)
    status = ep.release_status(row)
    assert status["status"] == "draft"
    assert _law_reasons(status) == ["Volume II, page not located: the number 37 matches" + REASON_TAIL]
    # the data changes and Volume II is clean: Volume I is rebuilt, and FINAL
    row.technical_plan = "## The build\nWe will add the screens.\n"
    stamp_clean(row)
    db.commit()
    db.refresh(row)
    path = ep.build_pdf(row, "blueprint")
    assert "DRAFT" not in _cover_text(path)
    assert ep.release_status(row)["status"] == "final"


def test_a_cached_volume_is_rebuilt_when_the_package_status_changes(db):
    from app.pipeline import export_pdf as ep

    row = _seed(db, mvp_blueprint=CLEAN_MD)
    path = ep.build_pdf(row, "blueprint")
    assert "DRAFT" not in _cover_text(path)
    mtime = os.path.getmtime(path)
    assert ep.build_pdf(row, "blueprint") == path and os.path.getmtime(path) == mtime   # served
    # another document of the package now holds a finding, with no data change
    law.save(row.id, "Volume II", [law.Finding("37", "add 37 screens", "Volume II", 3)])
    assert ep.release_status(row)["status"] == "draft"
    path = ep.build_pdf(row, "blueprint")
    assert os.path.getmtime(path) != mtime and "DRAFT" in _cover_text(path)


def test_the_deck_and_the_proposal_are_checked_with_the_package(db):
    from app.pipeline import export_pdf as ep
    from app.screens import schema

    system, _ = schema.shape_system(_system())
    row = _seed(db, mvp_blueprint=CLEAN_MD, roles_json="[]", concept_name="BeaconOS",
                business_analysis_json=json.dumps({"pain_points": ["The front desk misses 37 calls a week"]}),
                screens_json=json.dumps(system))
    path = ep.build_pdf(row, "blueprint")
    assert "DRAFT" in _cover_text(path)
    deck = law.recorded(row)["The deck"]
    assert [(f.number, f.page) for f in deck] == [("37", 2)]
    # the proposal's own story words, each placed on a proposal page without printing it
    proposal = law.recorded(row)["Volume IV"]
    assert proposal and all(isinstance(f.page, int) for f in proposal)


def test_the_engines_reading_of_a_package_makes_its_records_whole(db):
    from app.engine.legacy import r30_adapter

    row = _seed(db, mvp_blueprint=CLEAN_MD, technical_plan="## The build\nWe will add 37 screens.\n")
    assert law.recorded(row)["Volume II"] is None
    outputs = r30_adapter.load_outputs(row)
    assert outputs.release["status"] == "draft"
    assert [f.number for f in law.recorded(row)["Volume II"]] == ["37"]


def test_the_draft_stamp_of_a_volume_comes_from_its_own_findings(db):
    """The cover is stamped while the volume is built: the law's findings for
    that very build reach it, so the first build of a dirty volume is DRAFT."""
    import pymupdf

    from app.pipeline import export_pdf as ep

    row = _seed(db, mvp_blueprint=INJECTED_MD)
    doc = pymupdf.open(ep.build_pdf(row, "blueprint"))
    try:
        first_body_page = doc[2].get_text()
        cover = doc[0].get_text()
    finally:
        doc.close()
    assert "DRAFT" in cover and "DRAFT" in first_body_page


def test_page_numbers_and_volume_numerals_pass(db):
    """Review Focus 3, on a real volume: Volume II's cover numeral, its page
    numbers and section numbers, and content holding only labels and dates."""
    from app.pipeline import export_pdf as ep

    md = ("## Phase 2\nSee page 7 for the plan. We start on 3 March 2026. The first check is in week 1.\n\n"
          "### Step 4\n- **Section 3:** the build\n")
    row = _seed(db, technical_plan=md)
    ep.build_pdf(row, "technical")
    assert law.recorded(row)["Volume II"] == []
    assert _law_reasons(ep.release_status(row)) == []


def test_a_verified_financial_line_passes_and_an_unverified_one_is_flagged(db):
    """Review Focus 5. The verified line's result is a derived figure (its
    working is the figure's own, drawn by code); the unverified line's result
    is a number nobody worked out, so it is a finding."""
    from app.pipeline import export_pdf as ep

    bc = {"financial_model": {"lines": [VERIFIED, UNVERIFIED]}}
    row = _seed(db, mvp_blueprint=CLEAN_MD, business_case_json=json.dumps(bc))
    path = ep.build_pdf(row, "blueprint")
    found = law.recorded(row)["Volume I"]
    assert [f.number for f in found] == ["$9,000"]
    assert found[0].page == _pages_holding(path, "$9,000")[0]
    assert _pages_holding(path, "$14,820")            # the verified line printed, and passed


CONVERSION = {"item": "Missed bookings", "arithmetic": "40 calls × 30% conversion × $95 × 52",
              "annual": "$59,280/year", "arithmetic_verified": True, "unit": "USD"}
CALLS = [{"question": "How many calls do you get in a week?", "answer": "We get 40 calls a week"},
         {"question": "What does one visit cost?", "answer": "$95 a visit"}]


def test_an_operand_nobody_gave_in_a_verified_working_is_a_finding(db):
    """Review Focus 5, the operands: the product is verified, the 30% is not
    the client's, so the working holds a number nobody owns."""
    from app.pipeline import export_pdf as ep

    bc = {"financial_model": {"lines": [CONVERSION]}}
    row = _seed(db, mvp_blueprint=CLEAN_MD, business_case_json=json.dumps(bc), ops_numbers_json=json.dumps(CALLS))
    path = ep.build_pdf(row, "blueprint")
    found = law.recorded(row)["Volume I"]
    assert [(f.number, f.region) for f in found] == [("30%", "working")]
    assert found[0].page == _pages_holding(path, "30% conversion")[0]


def test_a_verified_working_whose_operands_are_theirs_passes(db):
    from app.pipeline import export_pdf as ep

    facts = CALLS + [{"question": "How many callers book?", "answer": "About 30% of callers book"}]
    bc = {"financial_model": {"lines": [CONVERSION]}}
    row = _seed(db, mvp_blueprint=CLEAN_MD, business_case_json=json.dumps(bc), ops_numbers_json=json.dumps(facts))
    ep.build_pdf(row, "blueprint")
    assert law.recorded(row)["Volume I"] == []


def test_a_number_in_a_discovery_question_is_checked(db):
    from app.pipeline import export_pdf as ep

    facts = [{"question": "Do you get more than 25 calls on a busy day?", "answer": "Yes, most days"}]
    row = _seed(db, mvp_blueprint=CLEAN_MD, ops_numbers_json=json.dumps(facts))
    ep.build_pdf(row, "blueprint")
    assert [(f.number, f.region) for f in law.recorded(row)["Volume I"]] == [("25", "evidence question")]


def test_the_scoreboard_passes_an_owned_number_and_flags_an_unowned_one(db):
    from app.pipeline import export_pdf as ep

    facts = [{"question": "How many calls go unanswered?", "answer": "About 12 calls a day go unanswered"}]
    board = [{"metric": "Unanswered calls", "baseline": "12 calls a day", "target": "4 calls a day",
              "owner": "you", "review": "weekly"}]
    row = _seed(db, mvp_blueprint=CLEAN_MD, ops_numbers_json=json.dumps(facts), scoreboard_json=json.dumps(board))
    ep.build_pdf(row, "blueprint")
    assert [f.number for f in law.recorded(row)["Volume I"]] == ["4"]


def test_the_pilot_gate_passes_its_own_proposals_and_flags_an_unowned_number(db):
    from app.pipeline import export_pdf as ep

    gate = {"primary_metric": "no-shows", "duration": "6 weeks", "duration_value": 6, "duration_unit": "week",
            "population": "every new patient", "target": "20% fewer no-shows"}
    row = _seed(db, mvp_blueprint=CLEAN_MD, business_case_json=json.dumps({"pilot_gate": gate}))
    ep.build_pdf(row, "blueprint")
    assert [f.number for f in law.recorded(row)["Volume I"]] == ["20%"]


def test_a_rebuild_replaces_stale_findings(db):
    from app.pipeline import export_pdf as ep
    from tests._integrity_stub import stamp_clean

    row = _seed(db, mvp_blueprint=INJECTED_MD)
    ep.build_pdf(row, "blueprint")
    assert [f.number for f in law.recorded(row)["Volume I"]] == ["37"]
    row.mvp_blueprint = CLEAN_MD
    stamp_clean(row)
    db.commit()
    db.refresh(row)
    # the data changed: the old build's findings are no longer this package's
    status = ep.release_status(row)
    assert _law_reasons(status) == []
    assert status["law"]["Volume I"] == "not yet checked"
    ep.build_pdf(row, "blueprint")
    assert law.recorded(row)["Volume I"] == []
    assert ep.release_status(row)["status"] == "final"


def test_a_cached_volume_still_reports_its_findings(db):
    from app.pipeline import export_pdf as ep

    row = _seed(db, mvp_blueprint=INJECTED_MD)
    first = ep.build_pdf(row, "blueprint")
    mtime = os.path.getmtime(first)
    assert ep.build_pdf(row, "blueprint") == first and os.path.getmtime(first) == mtime   # served from cache
    assert len(_law_reasons(ep.release_status(row))) == 1


def test_the_engines_choke_points_are_unchanged_outside_a_scope():
    from app.pipeline import export_pdf as ep

    assert ep._rich("They lose **37** calls & more") == "They lose <b>37</b> calls &amp; more"


# -- the deck ----------------------------------------------------------------------------------

def test_the_deck_names_the_slide(db):
    from app.pipeline import export_pdf as ep
    from app.pipeline import export_pptx

    row = _seed(db, mvp_blueprint=CLEAN_MD)
    analysis = {"pain_points": ["The front desk misses 37 calls a week"]}
    prs = export_pptx.build_presentation(row, analysis, {}, {"concept_name": "BeaconOS"}, [])
    texts = [" ".join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame) for slide in prs.slides]
    slide_no = next(n for n, t in enumerate(texts, 1) if "37 calls" in t)
    found = law.recorded(row)["The deck"]
    assert [(f.number, f.page) for f in found] == [("37", slide_no)]
    assert f"The deck, slide {slide_no}: the number 37 matches" + REASON_TAIL in ep.release_status(row)["reasons"]


def test_the_decks_own_furniture_passes(db):
    """Slide numerals, the screen counter in a kicker, the date on the cover and
    the closing copy ("Three ways forward ... ninety minutes") are drawn by code."""
    from app.pipeline import export_pptx

    row = _seed(db, mvp_blueprint=CLEAN_MD,
                modules_json=json.dumps([{"id": "a", "name": "Bookings", "purpose": "books visits"},
                                         {"id": "b", "name": "Billing", "purpose": "bills visits"}]))
    export_pptx.build_presentation(row, {"pain_points": ["Calls go unanswered"]}, {}, {"concept_name": "BeaconOS"}, [])
    assert law.recorded(row)["The deck"] == []


def test_a_concept_name_with_a_digit_is_drawn_on_the_deck_as_in_the_pdf(db):
    from app.pipeline import export_pdf as ep
    from app.pipeline import export_pptx

    row = _seed(db, mvp_blueprint=CLEAN_MD, concept_name="Studio 54 Desk")
    export_pptx.build_presentation(row, {"pain_points": ["Calls go unanswered"]}, {},
                                   {"concept_name": "Studio 54 Desk"}, [])
    assert law.recorded(row)["The deck"] == []
    ep.build_pdf(row, "blueprint")
    assert law.recorded(row)["Volume I"] == []


# -- the screens and the proposal ---------------------------------------------------------------

def _system():
    from app.screens import render

    return render.load_example()


def test_a_number_in_a_screen_caption_is_a_finding_and_one_in_a_sample_block_is_not():
    from app.screens import render

    system = _system()
    system["screens"][0]["caption"] = "The owner sees 8,642 bookings at a glance."
    ctx = render.proposal_context(system, business_name="Halo Reformer Studio")
    with law.scope(FigureSet(), where="Volume IV") as s:
        render.proposal_html(system, ctx)
    assert "8,642" in [f.number for f in s.findings]

    system = _system()
    system["screens"][0]["rows"][0][0]["items"][0]["value"] = "8,642"
    ctx = render.proposal_context(system, business_name="Halo Reformer Studio")
    with law.scope(FigureSet(), where="Volume IV") as s:
        html = render.proposal_html(system, ctx)
    assert "8,642" in html
    assert "8,642" not in [f.number for f in s.findings]


def test_a_sample_region_without_its_stamp_refuses_to_render():
    from app.screens import render

    stamped = render._env.from_string("{% call sample() %}<span>Sample data</span>{{ x }}{% endcall %}")
    assert "58/72" in stamped.render(x="58/72")
    bare = render._env.from_string("{% call sample() %}<p>{{ x }}</p>{% endcall %}")
    with pytest.raises(law.UnstampedSample):
        bare.render(x="58/72")


def test_the_live_system_page_still_renders_with_its_stamp():
    from app.screens import render

    html = render.system_html(_system(), "web")
    assert "Sample data" in html


def test_the_proposal_cover_hero_is_the_answers_first_headline_figure_never_a_sample_tile():
    from app.screens import render

    system = _system()
    tile = system["screens"][0]["rows"][0][0]["items"][0]["value"]
    answer = {"figures": [{"value": "$22", "label": "a class at the evening price today", "ids": ["A1-2"]}]}
    ctx = render.proposal_context(system, business_name="Halo Reformer Studio", answer=answer)
    assert ctx["hero_kpi"]["value"] == "$22" and ctx["hero_kpi"]["ids"] == ["A1-2"]
    cover = render.proposal_html(system, ctx).split("{# ── ambition", 1)[0].split('<section class="page', 2)[1]
    assert "$22" in cover and tile not in cover and ">Sample<" not in cover

    bare = render.proposal_context(system, business_name="Halo Reformer Studio", answer={"figures": []})
    assert bare["hero_kpi"] is None
    assert render.proposal_context(system, business_name="Halo Reformer Studio")["hero_kpi"] is None


def _system_row(db, caption: str):
    from app.screens import schema

    system, _ = schema.shape_system(_system())
    system["screens"][0]["caption"] = caption
    return _seed(db, mvp_blueprint=CLEAN_MD, screens_json=json.dumps(system))


def _print_sections(html: str, out_path: str) -> str:
    """A stand-in printer: one PDF page per proposal page, holding its text."""
    import html as html_lib

    import pymupdf

    doc = pymupdf.open()
    for section in html.split('<section class="page')[1:]:
        section = re.sub(r"<style.*?</style>|<svg.*?</svg>", " ", section, flags=re.S)
        text = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", section.split(">", 1)[1])))
        page = doc.new_page(width=1600, height=1200)
        page.insert_textbox(pymupdf.Rect(20, 20, 1580, 1180), text, fontsize=7)
    doc.save(out_path)
    doc.close()
    return out_path


def test_the_proposal_pdf_names_the_page_of_a_caption_number(db, monkeypatch):
    from app.pipeline import export_pdf as ep
    from app.screens import browser
    from app.screens import export as screens_export

    monkeypatch.setattr(browser, "render_pdf", _print_sections)
    row = _system_row(db, "The owner sees 8,642 bookings at a glance.")
    path = screens_export.build_system_pdf(row)
    # the example's own story holds number words this fixture's client never
    # gave ("twelve reformers"): those are findings too, on their own pages
    # the caption prints twice: on its screen's page and, as the first sentence,
    # on the platform page; each printing is a finding on its own page
    found = [f for f in law.recorded(row)["Volume IV"] if f.number == "8,642"]
    pages = _pages_holding(path, "8,642 bookings")
    assert len(pages) == 2 and [f.page for f in found] == pages
    reasons = ep.release_status(row)["reasons"]
    for page in pages:
        assert any(r.startswith(f"Volume IV, page {page}: the number") and "8,642" in r and r.endswith(REASON_TAIL)
                   for r in reasons), (page, reasons)


@pytest.mark.skipif(not __import__("app.screens.browser", fromlist=["available"]).available(),
                    reason="no browser here")
def test_with_a_browser_the_proposal_pdf_names_the_page_too(db):
    from app.screens import export as screens_export

    row = _system_row(db, "The owner sees 8,642 bookings at a glance.")
    path = screens_export.build_system_pdf(row)
    found = [f for f in law.recorded(row)["Volume IV"] if f.number == "8,642"]
    assert [f.page for f in found] == _pages_holding(path, "8,642 bookings")
    # the sample data in the frames (tiles such as "58/72") is never a finding
    assert not [f for f in law.recorded(row)["Volume IV"] if "58" in f.number]


def test_the_proposal_prints_a_proposed_price_as_its_figure():
    from app.screens import render

    move = {"label": "moving 6pm and 7pm to $28", "value": 44928.0, "rounded": 45000, "money": True,
            "unit": "USD", "period": "year", "display": "≈ $45,000 a year",
            "working": "144 spots × $6 × 52 weeks = $44,928",
            "proposed": [{"value": 28.0, "label": "proposed evening price", "unit": "USD"}], "cites": []}
    ctx = render.proposal_context(_system(), business_name="Halo Reformer Studio", answer={"move": move})
    assert "($28)" in ctx["move"]["proposed"]


# -- the client's emails -----------------------------------------------------------------------

def test_client_emails_carry_no_figures(monkeypatch):
    from app import mailer

    sent = []
    monkeypatch.setattr(mailer, "send_now", lambda to, subject, body: sent.append(body) or True)
    monkeypatch.setattr(mailer, "send_async", lambda to, subject, body: sent.append(body))
    mailer.notify_owner_ready("beacon-physio-x", "o@example.com", "Beacon Physiotherapy")
    mailer.notify_owner_released("beacon-physio-x", "o@example.com", "Beacon Physiotherapy", "BeaconOS")
    assert len(sent) == 2
    for body in sent:
        rest = body.replace(mailer._run_url("beacon-physio-x"), "")
        assert not any(ch.isdigit() for ch in rest), rest
