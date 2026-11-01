"""Step 2's acceptance, one test per line of the spec.

    a. A package rendered from a fixture with one untagged number fails the release
       law and names the page (the blueprint, the deck and the proposal, each on its
       own), and the page really holds the number. The same fixture without the
       number is not a draft because of the law.
    b. The checker covers the word, multiplier, ordinal and small-number cases that
       used to pass, and the leniency parameter is gone.
    c. An interview with a number the client never gave produces no fact for it.
    d. The draft-rate probe: the example proposal under the law with nothing known
       and with something known. Structure only, never a count.
    e. The release law end to end through the web: the decision payload carries no
       number the request does not know, and a tag on every figure it shows.

Every non-ASCII character below is written as an escape so the file stays ASCII.
"""
import inspect
import json
import os
import re
from decimal import Decimal

import pytest

from app.figures import law, read
from app.figures.known import known_for_texts
from app.figures.model import FigureSet

REASON_TAIL = " none of the client's figures, our workings, our estimates or a cited reference"

#: The words a client sees beside a figure (`model.tag_word`).
TAG_WORDS = {"yours", "worked out", "our estimate", "reference"}


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


FACTS = [{"question": "How many no-shows do you get in a week?", "answer": "About 3 no-shows a week"},
         {"question": "What does one visit cost?", "answer": "$95 a visit"}]
CLEAN_MD = ("## Executive summary\nA plan for the clinic: fewer missed visits and a calmer front desk.\n\n"
            "### Where you are today\n- **Bookings:** taken by phone\n1. answer every call\n")
#: One number nobody gave, in the middle of a sentence.
INJECTED_MD = CLEAN_MD.replace("a calmer front desk.", "a calmer front desk that loses 37 calls on a busy day.")


def _seed(db, **overrides):
    from app.models import Request
    from tests._integrity_stub import stamp_clean

    fields = dict(business_name="Beacon Physiotherapy", business_description="A physiotherapy clinic.",
                  concept_name="BeaconOS", email="t@example.com", status="done", is_generating=False,
                  ops_numbers_json=json.dumps(FACTS), qa_report_json=json.dumps({"checks": [], "findings": []}))
    fields.update(overrides)
    row = Request(**fields)
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


def _slides_holding(prs, needle: str) -> list[int]:
    texts = [" ".join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame) for slide in prs.slides]
    return [n for n, t in enumerate(texts, 1) if needle in re.sub(r"\s+", " ", t)]


# -- a. one untagged number fails the release law and names the page ----------------------------

def test_a_blueprint_with_one_untagged_number_is_a_draft_that_names_its_page(db):
    from app.pipeline import export_pdf as ep

    row = _seed(db, mvp_blueprint=INJECTED_MD)
    path = ep.build_pdf(row, "blueprint")
    pages = _pages_holding(path, "loses 37 calls")
    assert len(pages) == 1, "the injected number is on exactly one printed page"
    status = ep.release_status(row)
    assert status["status"] == "draft"
    assert _law_reasons(status) == [f"Volume I, page {pages[0]}: the number 37 matches" + REASON_TAIL]
    assert status["reasons"] == _law_reasons(status), "the number is the only thing wrong with this package"


def test_the_same_blueprint_without_the_number_is_not_a_draft_because_of_the_law(db):
    from app.pipeline import export_pdf as ep

    row = _seed(db, mvp_blueprint=CLEAN_MD)
    path = ep.build_pdf(row, "blueprint")
    assert _pages_holding(path, "loses 37 calls") == []
    status = ep.release_status(row)
    assert _law_reasons(status) == []
    assert status["status"] == "final", status["reasons"]


def test_a_deck_with_one_untagged_number_is_a_draft_that_names_its_slide(db):
    from app.pipeline import export_pdf as ep
    from app.pipeline import export_pptx

    def deck(pain: str):
        row = _seed(db, mvp_blueprint=CLEAN_MD)
        law.ensure_records(row)                    # the package is checked as a build checks it
        prs = export_pptx.build_presentation(row, {"pain_points": [pain]}, {}, {"concept_name": "BeaconOS"}, [])
        return row, prs

    row, prs = deck("The front desk misses 37 calls a week")
    slides = _slides_holding(prs, "37 calls")
    assert len(slides) == 1, "the injected number is on exactly one slide"
    status = ep.release_status(row)
    assert status["status"] == "draft"
    assert _law_reasons(status) == [f"The deck, slide {slides[0]}: the number 37 matches" + REASON_TAIL]

    clean_row, clean_prs = deck("The front desk misses calls")
    assert _slides_holding(clean_prs, "37 calls") == []
    clean = ep.release_status(clean_row)
    assert _law_reasons(clean) == [] and clean["status"] == "final", clean["reasons"]


#: What this fixture's client said, among other things: the example proposal's own story
#: speaks of a seventh day and of the 6pm and 7pm classes, so a client who never said
#: either would own no such number (and a clock time is held to the hours they named).
EXAMPLE_OWNER = {"question": "When are you busiest, and would you open on a Sunday?",
                 "answer": "The 6pm and 7pm classes fill first. We could open a seventh day"}


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


def _proposal_row(db, caption: str | None):
    from app.screens import render, schema

    system, _ = schema.shape_system(render.load_example())
    if caption is not None:
        system["screens"][0]["caption"] = caption
    return _seed(db, mvp_blueprint=CLEAN_MD, screens_json=json.dumps(system),
                 ops_numbers_json=json.dumps(FACTS + [EXAMPLE_OWNER]))


def test_a_proposal_with_one_untagged_number_is_a_draft_that_names_its_page(db, monkeypatch):
    from app.pipeline import export_pdf as ep
    from app.screens import browser
    from app.screens import export as screens_export

    monkeypatch.setattr(browser, "render_pdf", _print_sections)
    row = _proposal_row(db, "The owner sees 8,642 bookings at a glance.")
    law.ensure_records(row)
    path = screens_export.build_system_pdf(row)
    # the caption prints on its screen's page and again on the platform page
    pages = _pages_holding(path, "8,642 bookings")
    assert pages, "the injected number is on a printed page"
    status = ep.release_status(row)
    assert status["status"] == "draft"
    named = sorted(int(m.group(1)) for r in _law_reasons(status)
                   if (m := re.fullmatch(r"Volume IV, page (\d+): the number 8,642 matches" + re.escape(REASON_TAIL), r)))
    assert named == pages
    assert len(_law_reasons(status)) == len(pages), "no other number in the proposal is unowned"


def test_the_same_proposal_without_the_number_is_not_a_draft_because_of_the_law(db, monkeypatch):
    from app.pipeline import export_pdf as ep
    from app.screens import browser
    from app.screens import export as screens_export

    monkeypatch.setattr(browser, "render_pdf", _print_sections)
    row = _proposal_row(db, None)
    law.ensure_records(row)
    path = screens_export.build_system_pdf(row)
    assert _pages_holding(path, "8,642") == []
    status = ep.release_status(row)
    assert _law_reasons(status) == [] and status["status"] == "final", status["reasons"]


# -- b. the checker covers what used to pass -----------------------------------------------------

D = Decimal
UNRELATED = known_for_texts(["I charge $22 a class and have 40 members."])

#: (text, the values the checker flags in it)
USED_TO_PASS = [
    ("twelve classes a week", [D(12)]),
    ("a dozen spots are free", [D(12)]),
    ("3x more bookings", [D(3)]),
    ("3\N{MULTIPLICATION SIGN} more bookings", [D(3)]),
    ("the 3rd phase", [D(3)]),
    ("the 3rd class", [D(3)]),
    ("8 hrs a week", [D(8)]),
    ("12 reformers", [D(12)]),
    ("2-3 weeks", [D(2), D(3)]),
    ("six-week pilot", [D(6)]),
    ("1.5 hours", [D("1.5")]),
    ("one in 20", [D(20)]),
]


@pytest.mark.parametrize("known", [FigureSet(), UNRELATED], ids=["nothing known", "unrelated figures known"])
@pytest.mark.parametrize("text,values", USED_TO_PASS, ids=[t for t, _ in USED_TO_PASS])
def test_the_checker_flags_what_used_to_pass(text, values, known):
    assert [m.value for m in read.unsupported(text, known)] == values


@pytest.mark.parametrize("text,owner", [
    ("twelve classes a week", "I have 12 reformers"),
    ("a dozen spots are free", "I have 12 reformers"),
    ("12 reformers", "I have 12 reformers"),
    ("one in 20", "About 20 of them come back"),
    ("8 hrs a week", "I spend 8 hours a week on it"),
], ids=lambda v: v if isinstance(v, str) else None)
def test_the_same_words_pass_once_the_client_owns_the_number(text, owner):
    """It is ownership that clears a number, not a rule about its shape."""
    assert read.unsupported(text, known_for_texts([owner])) == []


def test_a_date_or_a_plan_position_is_not_a_quantity():
    assert read.unsupported("Measure it in week 1, then again in week 4.", FigureSet()) == []
    assert read.unsupported("We start on 3 March 2026.", FigureSet()) == []


def test_the_leniency_parameter_no_longer_exists():
    from app.config import settings
    from app.pipeline import figures as old

    for fn in (read.unsupported, read.supported, read.mentions):
        assert not [p for p in inspect.signature(fn).parameters if "lenien" in p.lower()], fn.__name__
    assert not hasattr(old, "unsupported")
    assert not [n for n in dir(old) if "lenien" in n.lower()]
    assert not [n for n in dir(read) if "lenien" in n.lower()]
    assert not [n for n in dir(settings) if "lenien" in n.lower()]


# -- c. a number the client never gave produces no fact -----------------------------------------

#: Our side of the interview: the question put to them mentions 40; their answer may not.
OUR_QUESTION = "Do you run about 40 classes a week?"
PROBLEM = "I run a pilates studio. We charge $22 a class and the 6pm class is always full."


def _fact_list():
    return [{"key": "price", "group": "Money", "label": "What you charge", "field": "", "status": "need", "value": ""},
            {"key": "volume", "group": "Customers", "label": "Classes a week", "field": "", "status": "need", "value": ""}]


def test_a_fact_value_with_a_number_only_our_question_holds_is_dropped():
    from app.routers import discovery

    reply = [{"key": "volume", "value": "40 a week"}, {"key": "price", "value": "$22 a class"}]
    # their words alone: what they first wrote and what they answered, never our question
    theirs = [PROBLEM, "Quite a lot, mostly evenings"]
    updates, _ = discovery.shape_fact_updates(reply, [], _fact_list(), theirs)
    assert updates == [{"key": "price", "value": "$22 a class"}], "40 is in our question, not in their words"
    assert OUR_QUESTION not in theirs


def test_the_same_fact_value_is_kept_when_the_client_gave_the_number():
    from app.routers import discovery

    reply = [{"key": "volume", "value": "40 a week"}]
    theirs = [PROBLEM, "We run 40 classes a week, mostly evenings"]
    updates, _ = discovery.shape_fact_updates(reply, [], _fact_list(), theirs)
    assert updates == [{"key": "volume", "value": "40 a week"}]


def _interview(client, monkeypatch, answer: str, reply_value: str):
    body = {"choices": [{"message": {"content": json.dumps({
        "questions": [{"id": "members", "label": "How many members do you have?", "placeholder": "e.g. 120", "why": "scale"}],
        "updates": [{"key": "volume", "value": reply_value}], "new_facts": []})}}], "usage": {}}
    monkeypatch.setattr("app.ai.provider.chat", lambda *a, **k: body)
    return client.post("/api/discovery/interview", data={
        "main_problem": PROBLEM, "business_name": "Halo Reformer Studio", "round": "2",
        "facts": json.dumps(_fact_list()),
        "ops_numbers": json.dumps([{"id": "classes", "question": OUR_QUESTION, "answer": answer}])})


@pytest.fixture
def web(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from main import app

    from app.config import settings
    from app.database import Base, engine

    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path))
    return TestClient(app)


def test_the_interview_makes_no_fact_from_a_number_only_our_question_holds(web, monkeypatch):
    got = _interview(web, monkeypatch, "Quite a lot, mostly evenings", "40 a week")
    assert got.status_code == 200, got.text
    assert got.json()["updates"] == []


def test_the_interview_makes_the_fact_when_their_answer_holds_the_number(web, monkeypatch):
    got = _interview(web, monkeypatch, "We run 40 classes a week, mostly evenings", "40 a week")
    assert got.status_code == 200, got.text
    assert got.json()["updates"] == [{"key": "volume", "value": "40 a week"}]


# -- d. the draft-rate probe ---------------------------------------------------------------------

def _example_findings(known: FigureSet, hours=None) -> list:
    from app.screens import render, schema

    system, _ = schema.shape_system(render.load_example())
    ctx = render.proposal_context(system, business_name="Halo Reformer Studio")
    with law.scope(known, where="Volume IV", hours=hours) as s:
        render.proposal_html(system, ctx)
    return s.findings


def test_the_example_proposal_under_the_law_with_nothing_known_and_with_something_known():
    """Informational: how many numbers the example proposal leaves nobody owning is
    not pinned, only what a finding is. Every finding names its region, holds its
    number in the words around it, and owning a number can only remove findings;
    a package whose numbers are all owned has none."""
    bare = _example_findings(FigureSet())
    for f in bare:
        assert f.region == "Volume IV" and f.number and f.snippet and f.number in f.snippet, f

    realistic = known_for_texts(["I run six days a week at $22 a class, and I have 12 reformers.",
                                 "We could open a seventh day if the evenings keep selling out."])
    some = _example_findings(realistic)
    assert {(f.number, f.snippet) for f in some} <= {(f.number, f.snippet) for f in bare}
    for f in some:
        assert f.region == "Volume IV" and f.number and f.snippet

    # owned: the sentences the findings sit in are the client's own words
    owned = _example_findings(known_for_texts([f.snippet for f in bare]))
    assert owned == []


def test_every_finding_in_a_proposal_row_is_placed_on_a_page(db):
    """The same probe on a row: the law-only pass places each finding on the
    proposal page that holds it, and a client who owns the numbers has none."""
    bare = _proposal_row_without(db)
    law.ensure_records(bare)
    found = law.recorded(bare)["Volume IV"]
    assert found is not None
    assert all(f.region == "Volume IV" and isinstance(f.page, int) and f.page >= 1 for f in found), found

    owned = _seed(db, mvp_blueprint=CLEAN_MD, screens_json=bare.screens_json,
                  ops_numbers_json=json.dumps(FACTS + [{"question": "Anything else?",
                                                        "answer": " ".join(f.snippet for f in found)}]))
    law.ensure_records(owned)
    assert law.recorded(owned)["Volume IV"] == []


def _proposal_row_without(db):
    from app.screens import render, schema

    system, _ = schema.shape_system(render.load_example())
    return _seed(db, mvp_blueprint=CLEAN_MD, screens_json=json.dumps(system))


# -- e. the release law end to end through the web ------------------------------------------------

QUESTIONS = [
    ("How many reformers do you have, and how are classes scheduled?", "12 reformers. Six 50-minute classes a day, six days a week."),
    ("How full is a typical class?", "About 10 of 12. The 6pm and 7pm ones have a waiting list most weeks."),
    ("What do you charge a class?", "$22 a class, $200 for 10"),
    ("What do the studios nearby charge?", "Two studios nearby, both $32 a class."),
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
#: A number nobody gave, four times over: in the sub, in a headline figure, in the roadmap's
#: summary and in one of its phases.
NOBODY = "87"
RAW_ANSWER = {
    "headline": "Your evenings sell out at $22 a class while others charge $32.",
    "turn": "Moving them to $28 is worth about $45,000 a year.",
    "sub": ("Your 12 reformers hold 432 reformer spots a week, and 144 reformer spots are in the evenings that "
            f"sell out. Studios like yours lose {NOBODY} calls a week."),
    "figures": [{"value": "$22 vs $32", "label": "you and two studios nearby", "cites": ["CF-04", "CF-06"]},
                {"value": f"{NOBODY} calls", "label": "lost by studios like yours", "cites": ["CF-04"]},
                {"value": "144 reformer spots", "label": "a week in the evenings that sell out", "cites": ["CAP-05"]}],
    "move": MOVE, "action": {"weeks": 6, "name": "six-week pilot"}}
RAW_ROADMAP = {
    "summary": f"We move the evenings to $28 and win back {NOBODY} bookings over six weeks.",
    "phases": [{"when": "Weeks 1 to 2", "title": "Set the evening price",
                "do": "We move the 6pm and 7pm classes to $28 and tell your regulars.", "by": "us"},
               {"when": "Weeks 3 to 6", "title": "Watch the evenings",
                "do": f"We track how full the evenings are each week and expect {NOBODY} more bookings.",
                "by": "together", "you": ""},
               {"when": "Weeks 5 to 6", "title": "Keep the price",
                "do": "We keep $28 for the evenings if they stay full.", "by": "us"}],
    "decisions": [{"question": "Go ahead with $28 evenings?", "detail": "Daytime stays at $22.",
                   "options": ["Yes", "Not yet"]}],
    "assumptions": ["Regulars accept $28"]}
DECISION = {"consulting_summary": "Your evenings are full and your price is the lowest nearby.",
            "central_problem": "The evening price leaves money on the table.",
            "recommended_ai_employees": [], "recommended_features": [], "unverified": []}


def _web_fields(**over):
    base = dict(
        business_name="Halo Reformer Studio", business_description=DESCRIPTION, email="owner@example.com",
        owner_email="test@example.com", status="done", is_generating=False,
        ops_numbers_json=json.dumps([{"id": f"q{i}", "question": q, "answer": a}
                                     for i, (q, a) in enumerate(QUESTIONS, 1)]),
        consulting_recommendations_json=json.dumps(DECISION))
    base.update(over)
    return base


def _written_by_the_stages() -> tuple[dict, list[str]]:
    """The columns of a finished run, written by the stages' own `shape` functions
    from a model reply that holds a number nobody gave, and what those stages said
    about it."""
    from app.figures import known as K
    from app.models import Request
    from app.pipeline import action_plan, answer, capacity

    row = Request(**_web_fields())
    picture = capacity.shape(GRID, [a for _, a in QUESTIONS] + [DESCRIPTION])
    row.capacity_json = json.dumps(picture)
    known, hours = K.known_for(row), K.hours_for(row)
    claims = [{"id": "CF-04", "value": 22, "unit": "USD", "text": "$22 a class", "provenance": "client_input"},
              {"id": "CF-06", "value": 32, "unit": "USD", "text": "$32", "provenance": "client_input"},
              ] + capacity.as_claims(picture)
    stored, problems = answer.shape(RAW_ANSWER, claims, known, hours)
    assert stored, problems
    plan_weeks = next(f for f in K.answer_figures(stored) if f.id == K.PLAN_WEEKS_ID)
    plan, plan_problems = action_plan.shape(RAW_ROADMAP, K.with_extra(known, K.answer_figures(stored)), hours, plan_weeks)
    assert plan, plan_problems
    return (_web_fields(capacity_json=json.dumps(picture), answer_json=json.dumps(stored),
                        action_plan_json=json.dumps(plan)), problems + plan_problems)


def _prose(answer: dict | None, plan: dict | None) -> list[str]:
    out: list[str] = []
    a = answer or {}
    out += [a.get("headline"), a.get("turn"), a.get("sub"), (a.get("action") or {}).get("name")]
    for f in a.get("figures") or []:
        out += [f.get("value"), f.get("label")]
    p = plan or {}
    out += [p.get("summary")] + list(p.get("assumptions") or [])
    for ph in p.get("phases") or []:
        out += [ph.get("when"), ph.get("title"), ph.get("do"), ph.get("you")]
    for d in p.get("decisions") or []:
        out += [d.get("question"), d.get("detail")] + list(d.get("options") or [])
    return [t for t in out if isinstance(t, str) and t]


def _figures_shown(body: dict) -> set[str]:
    """The ids of the figures the served page draws, read off the served payload by
    its own keys (not by the code that built the map)."""
    shown: set[str] = set()
    a = body.get("answer") or {}
    for field in ("headline", "turn", "sub"):
        shown |= {p["figure"] for p in a.get(f"{field}_segments") or [] if "figure" in p}
    for f in a.get("figures") or []:
        shown |= set(f.get("ids") or [])
        for key in ("value_segments", "label_segments"):
            shown |= {p["figure"] for p in f.get(key) or [] if "figure" in p}
    move = a.get("move") or {}
    shown |= {x for x in [move.get("figure_id")] + [p.get("figure_id") for p in move.get("proposed") or []] if x}
    if (a.get("action") or {}).get("figure"):
        shown.add(a["action"]["figure"]["id"])
    shown |= {d["key"] for d in (body.get("capacity") or {}).get("derived") or [] if d.get("key")}
    shown |= {f["id"] for f in (body.get("action_plan") or {}).get("figures") or []
              if f.get("id") and f["id"] != "PLAN-PHASES"}                  # the phase count is drawn nowhere
    return shown


def test_the_decision_payload_serves_no_number_nobody_owns_and_a_tag_on_every_figure_it_shows(web):
    from app.database import SessionLocal
    from app.figures import known as K
    from app.figures.bind import bind
    from app.models import Request

    fields, problems = _written_by_the_stages()
    assert any(NOBODY in p for p in problems), problems          # the stages did meet the number, and said so
    db = SessionLocal()
    row = Request(**fields)
    db.add(row)
    db.commit()
    rid = row.id
    known, hours = K.known_for(row), K.hours_for(row)
    db.close()

    got = web.get(f"/api/requests/{rid}/decision")
    assert got.status_code == 200, got.text
    body = got.json()

    # the prose the page reads: no number that no figure of the request owns, and none left unbound
    texts = _prose(body["answer"], body["action_plan"])
    assert any(re.search(r"\d", t) for t in texts), "the fixture keeps the numbers it owns"
    for t in texts:
        assert read.unsupported(t, known, hours=hours) == [], t
        assert bind(t, known, hours=hours).unresolved == [], t
    assert NOBODY not in json.dumps([body["answer"], body["action_plan"]])
    # the pieces a page tags: a number in a plain (untagged) piece would be a number no figure owns
    answer = body["answer"]
    pieces = [p for field in ("headline", "turn", "sub") for p in answer[f"{field}_segments"]]
    assert any("figure" in p for p in pieces)
    for p in pieces:
        if "figure" not in p:
            assert read.unsupported(p["text"], known, hours=hours) == [], p

    # a tag on every figure shown, in the client's words, of the kind the figure is
    shown = _figures_shown(body)
    assert shown, "the page shows figures"
    assert shown <= set(body["figures"]), sorted(shown - set(body["figures"]))
    for fid in shown:
        entry = body["figures"][fid]
        assert entry["tag"] in TAG_WORDS and entry["kind"] in {"theirs", "derived", "ours", "reference"}, (fid, entry)
        assert entry["tag"] == {"theirs": "yours", "derived": "worked out", "ours": "our estimate",
                                "reference": "reference"}[entry["kind"]]
        assert entry["display"] and entry["source"]
    assert {body["figures"][f]["tag"] for f in shown} >= {"yours", "worked out", "our estimate"}
