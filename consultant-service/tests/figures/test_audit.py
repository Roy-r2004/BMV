"""The number audit (`python -m app.figures.audit <request public id> [--json]`).

Pins: a package with one number nobody owns exits 1 and the table names the
document, the page and the number; a clean one exits 0; an unknown id, or bad
usage, exits 2 with a plain message; `--json` is the same report; the command
writes nothing to the request row; a build that fails is "could not check <document>"
and never its error; and the snippet and the output stay safe on any terminal.
"""
import json
import os
import re
import secrets
import subprocess
import sys

import pytest

from app.figures import audit, law

FACTS = [{"question": "How many no-shows do you get in a week?", "answer": "About 3 no-shows a week"},
         {"question": "What does one visit cost?", "answer": "$95 a visit"}]
CLEAN_MD = ("## Executive summary\nA plan for the clinic: fewer missed visits and a calmer front desk.\n\n"
            "### Where you are today\n- **Bookings:** taken by phone\n1. answer every call\n")
INJECTED_MD = CLEAN_MD.replace("a calmer front desk.", "a calmer front desk that loses 37 calls on a busy day.")
CONVERSION = {"item": "Missed bookings", "arithmetic": "40 calls \N{MULTIPLICATION SIGN} 30% conversion \N{MULTIPLICATION SIGN} $95 \N{MULTIPLICATION SIGN} 52",
              "annual": "$59,280/year", "arithmetic_verified": True, "unit": "USD"}
CALLS = [{"question": "How many calls do you get in a week?", "answer": "We get 40 calls a week"},
         {"question": "What does one visit cost?", "answer": "$95 a visit"}]


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


def _seed(db, **overrides):
    from app.models import Request
    from tests._integrity_stub import stamp_clean

    fields = dict(business_name="Beacon Physiotherapy", business_description="A physiotherapy clinic.",
                  concept_name="BeaconOS", email="t@example.com", status="done", is_generating=False,
                  public_id="audit-" + secrets.token_hex(4), ops_numbers_json=json.dumps(FACTS),
                  qa_report_json=json.dumps({"checks": [], "findings": []}))
    fields.update(overrides)
    row = Request(**fields)
    stamp_clean(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _pages_holding(pdf_path: str, needle: str) -> list[int]:
    import pymupdf

    doc = pymupdf.open(pdf_path)
    try:
        return [n + 1 for n, page in enumerate(doc) if needle in re.sub(r"\s+", " ", page.get_text())]
    finally:
        doc.close()


def _run(capsys, *argv):
    code = audit.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _table_lines(out: str) -> list[str]:
    """The table's rows: the lines that start with a document's name and hold a place."""
    return [l for l in out.splitlines() if re.match(r"(Volume (I|II|III|IV)|The deck)\s+(page|slide) ", l)]


# -- a package with a number nobody owns ------------------------------------------------------

def test_a_number_nobody_owns_exits_1_and_the_table_names_the_page_and_the_number(db, capsys):
    from app.pipeline import export_pdf as ep

    row = _seed(db, mvp_blueprint=INJECTED_MD)
    path = ep.build_pdf(row, "blueprint")
    (page,) = _pages_holding(path, "loses 37 calls")
    code, out, err = _run(capsys, row.public_id)
    assert code == 1 and err == ""
    (line,) = _table_lines(out)
    cells = re.split(r"\s{2,}", line)
    assert cells[0] == "Volume I" and cells[1] == f"page {page}" and cells[2] == "37"
    assert "loses 37 calls" in cells[3]
    assert cells[4] == audit.REASON
    assert "Volume I: 1 number nobody owns" in out.splitlines()
    assert "Volume II: not produced" in out.splitlines()
    assert out.splitlines()[out.splitlines().index("Volume I: 1 number nobody owns") - 1] == ""
    assert "Package status: draft because of the number law" in out.splitlines()
    assert "Document" in out and "Snippet" in out and "Reason" in out


def test_a_volume_not_built_since_the_last_change_is_reported_with_its_page_not_located(db, capsys):
    row = _seed(db, mvp_blueprint=INJECTED_MD)
    code, out, _ = _run(capsys, row.public_id)
    assert code == 1
    (line,) = _table_lines(out)
    assert re.split(r"\s{2,}", line)[:3] == ["Volume I", "page not located", "37"]
    assert "Volume I: 1 number nobody owns" in out
    # the only files written are the law's own findings files, through its own pass
    from app.config import settings

    assert sorted(os.listdir(os.path.join(settings.UPLOADS_DIR, "exports"))) == sorted(
        f"{row.id}-law-{slug}.json" for slug in ("volume-i", "volume-ii", "volume-iii", "volume-iv", "the-deck"))


def test_the_deck_is_placed_on_its_slide(db, capsys):
    row = _seed(db, mvp_blueprint=CLEAN_MD, roles_json="[]",
                business_analysis_json=json.dumps({"pain_points": ["The front desk misses 37 calls a week"]}))
    code, out, _ = _run(capsys, row.public_id)
    assert code == 1
    (line,) = _table_lines(out)
    assert re.split(r"\s{2,}", line)[:3] == ["The deck", "slide 2", "37"]
    assert "The deck: 1 number nobody owns" in out


def test_a_number_inside_a_working_says_so(db, capsys):
    bc = {"financial_model": {"lines": [CONVERSION]}}
    row = _seed(db, mvp_blueprint=CLEAN_MD, business_case_json=json.dumps(bc), ops_numbers_json=json.dumps(CALLS))
    code, out, _ = _run(capsys, row.public_id)
    assert code == 1
    (line,) = _table_lines(out)
    assert line.endswith(audit.REASON + " (in the working)") and re.split(r"\s{2,}", line)[2] == "30%"


def test_a_numeric_id_works_as_it_does_in_the_app(db, capsys):
    row = _seed(db, mvp_blueprint=INJECTED_MD)
    code, out, _ = _run(capsys, str(row.id))
    assert code == 1 and "Volume I: 1 number nobody owns" in out


# -- a clean package -------------------------------------------------------------------------

def test_a_clean_package_exits_0(db, capsys):
    from app.figures.known import known_for

    row = _seed(db, mvp_blueprint=CLEAN_MD)
    code, out, err = _run(capsys, row.public_id)
    assert code == 0 and err == ""
    assert _table_lines(out) == []
    assert "No number nobody owns was found." in out
    assert "Volume I: checked" in out.splitlines()
    assert "Package status: final" in out.splitlines()
    # the figures the request knows, by kind, in the client's words
    counts = known_for(row).counts()
    shown = dict(re.findall(r"^  (yours|worked out|our estimate|reference): (\d+)$", out, re.M))
    assert shown["yours"] == str(counts["theirs"]) and int(shown["yours"]) >= 2
    assert set(shown) == {"yours", "worked out", "our estimate", "reference"}


# -- usage and a request that does not exist ----------------------------------------------------

def test_an_unknown_id_prints_a_plain_message_and_exits_2(db, capsys):
    code, out, err = _run(capsys, "no-such-request")
    assert code == 2 and out == ""
    assert err.strip() == "No request with the id 'no-such-request' was found."
    assert code == 2 and audit.main(["99999999"]) == 2


@pytest.mark.parametrize("argv", [[], ["--json"], ["a", "b"], ["--nope", "x"], [" "]])
def test_bad_usage_exits_2(capsys, argv):
    code, out, err = _run(capsys, *argv)
    assert code == 2 and out == "" and err.strip()
    assert "Traceback" not in err


def test_the_module_runs_as_a_command(db):
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    run = lambda *argv: subprocess.run([sys.executable, "-m", "app.figures.audit", *argv], cwd=root,  # noqa: E731
                                       capture_output=True, text=True, timeout=180)
    missing = run("no-such-request")
    assert missing.returncode == 2 and missing.stdout == ""
    assert "No request with the id" in missing.stderr and "Traceback" not in missing.stderr
    usage = run()
    assert usage.returncode == 2 and "usage:" in usage.stderr


def test_a_failed_build_leaves_no_trace_of_its_error_on_the_terminal(db, tmp_path):
    """As a command nothing configures logging, so a logged failure would reach the
    terminal with its traceback: the audit must hold it back."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    row = _seed(db, mvp_blueprint=CLEAN_MD)
    script = ("import sys\n"
              "from app.pipeline import export_pdf as ep\n"
              "def boom(req, kind):\n    raise RuntimeError('secret-internal-detail')\n"
              "ep.check_volume = boom\n"
              "from app.figures import audit\n"
              "sys.exit(audit.main([sys.argv[1]]))\n")
    done = subprocess.run([sys.executable, "-c", script, row.public_id], cwd=root, capture_output=True, text=True,
                          timeout=180, env={**os.environ, "UPLOADS_DIR": str(tmp_path)})
    assert done.returncode == 1, done.stderr
    assert "could not check Volume I" in done.stdout
    for leak in ("secret-internal-detail", "RuntimeError", "Traceback", "release law"):
        assert leak not in done.stdout + done.stderr


# -- --json ----------------------------------------------------------------------------------

def test_json_is_the_same_report(db, capsys):
    from app.pipeline import export_pdf as ep

    row = _seed(db, mvp_blueprint=INJECTED_MD)
    ep.build_pdf(row, "blueprint")
    text_code, text, _ = _run(capsys, row.public_id)
    json_code, raw, err = _run(capsys, row.public_id, "--json")
    assert err == "" and json_code == text_code == 1
    report = json.loads(raw)
    assert [d["document"] for d in report["documents"]] == [w for w, _ in law.DOCUMENTS]
    found = [(d["document"], f["place"], f["number"], f["snippet"]) for d in report["documents"] for f in d["findings"]]
    shown = [tuple(re.split(r"\s{2,}", l)[:4]) for l in _table_lines(text)]
    assert found == shown and len(found) == 1
    # and it is what the law recorded for the page it names
    (recorded,) = law.recorded(row)["Volume I"]
    assert report["documents"][0]["findings"][0]["page"] == recorded.page
    assert report["numbers_nobody_owns"] == 1 and report["clean"] is False
    assert f"Package status: {report['status_line']}" in text
    assert report["status"] == "draft" and report["status_line"] == "draft because of the number law"
    assert set(report["figures"]) == {"yours", "worked out", "our estimate", "reference"}
    assert [d["summary"] for d in report["documents"]] == [l for l in text.splitlines()
                                                           if re.match(r"(Volume I{1,3}V?|Volume IV|The deck):", l)]


def test_json_of_a_clean_package_has_no_findings_and_exits_0(db, capsys):
    row = _seed(db, mvp_blueprint=CLEAN_MD)
    code, raw, _ = _run(capsys, row.public_id, "--json")
    report = json.loads(raw)
    assert code == 0 and report["clean"] is True and report["status"] == "final"
    assert all(d["findings"] == [] for d in report["documents"])


# -- read-only -----------------------------------------------------------------------------------

def _columns(rid: int) -> dict:
    from app.database import SessionLocal
    from app.models import Request

    session = SessionLocal()
    try:
        r = session.get(Request, rid)
        return {c.name: getattr(r, c.name) for c in Request.__table__.columns}
    finally:
        session.close()


def test_the_command_does_not_write_the_request_row(db, capsys):
    from app.screens import render, schema

    system, _ = schema.shape_system(render.load_example())
    row = _seed(db, mvp_blueprint=INJECTED_MD, technical_plan="## The build\nWe will add 41 screens.\n",
                roles_json="[]", screens_json=json.dumps(system),
                business_analysis_json=json.dumps({"pain_points": ["The front desk misses 37 calls a week"]}))
    before = _columns(row.id)
    for argv in ([row.public_id], [row.public_id, "--json"]):
        code, out, _ = _run(capsys, *argv)
        assert code == 1 and out
        after = _columns(row.id)
        assert after == before
        assert after["updated_at"] == before["updated_at"]


def test_the_command_does_not_commit_the_session(db, capsys, monkeypatch):
    from sqlalchemy.orm import Session

    real = Session.commit
    commits = []
    monkeypatch.setattr(Session, "commit", lambda self: commits.append(1) or real(self))
    row = _seed(db, mvp_blueprint=INJECTED_MD)
    seeded = len(commits)
    _run(capsys, row.public_id)
    assert len(commits) == seeded


# -- a build that fails --------------------------------------------------------------------------

def test_a_build_that_fails_is_could_not_check_and_never_its_error(db, capsys, monkeypatch):
    import logging

    from app.pipeline import export_pdf as ep

    def broken(req, kind):
        raise RuntimeError("secret-internal-detail /srv/app/path.py line 12")

    monkeypatch.setattr(ep, "check_volume", broken)
    row = _seed(db, mvp_blueprint=CLEAN_MD, roles_json="[]",
                business_analysis_json=json.dumps({"pain_points": ["The front desk misses 37 calls a week"]}))
    disabled = logging.root.manager.disable
    code, out, err = _run(capsys, row.public_id)
    assert logging.root.manager.disable == disabled, "the audit gives the logging back as it found it"
    everything = out + err
    for leak in ("secret-internal-detail", "RuntimeError", "Traceback", "path.py"):
        assert leak not in everything
    lines = out.splitlines()
    for volume in ("Volume I", "Volume II", "Volume III"):
        assert f"could not check {volume}" in lines
    # the others are checked, and what they found is reported
    assert code == 1
    assert "The deck: 1 number nobody owns" in lines
    (line,) = _table_lines(out)
    assert re.split(r"\s{2,}", line)[:3] == ["The deck", "slide 2", "37"]


def test_a_package_that_could_not_be_checked_is_not_clean(db, capsys, monkeypatch):
    from app.pipeline import export_pdf as ep

    monkeypatch.setattr(ep, "check_volume", lambda req, kind: (_ for _ in ()).throw(ValueError("hidden")))
    row = _seed(db, mvp_blueprint=CLEAN_MD)
    code, out, _ = _run(capsys, row.public_id, "--json")
    report = json.loads(out)
    assert code == 1 and report["clean"] is False and report["documents_not_checked"] == 3
    assert "hidden" not in out


def test_a_failure_to_read_the_database_is_a_plain_message(db, capsys, monkeypatch):
    monkeypatch.setattr(audit, "_find", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret database detail")))
    code, out, err = _run(capsys, "anything")
    assert code == 2 and out == "" and err.strip() == "Could not read the database."


def test_a_failure_in_the_report_is_a_plain_message(db, capsys, monkeypatch):
    row = _seed(db, mvp_blueprint=CLEAN_MD)
    monkeypatch.setattr(audit, "build_report", lambda req: (_ for _ in ()).throw(RuntimeError("secret report detail")))
    code, out, err = _run(capsys, row.public_id)
    assert code == 2 and out == "" and err.strip() == "The audit could not be completed."


# -- client text never acts on the owner's terminal ------------------------------------------------

#: A clear-screen, a set-window-title and a bell, then a right-to-left override, as a client could type them.
RLO = "\N{RIGHT-TO-LEFT OVERRIDE}"
HOSTILE = "\x1b[2J\x1b]0;pwned\x07" + RLO + "\r\x08"


def _hostile_row(db):
    md = CLEAN_MD.replace("a calmer front desk.", f"a calmer front desk {HOSTILE}that loses 37 calls on a busy day.")
    return _seed(db, mvp_blueprint=md, business_name=f"Beacon {HOSTILE}Physiotherapy",
                 ops_numbers_json=json.dumps(FACTS + [{"question": "Anything else?", "answer": f"We {HOSTILE}hope so"}]))


def _unsafe(text: str) -> list[str]:
    import unicodedata

    return sorted({f"U+{ord(c):04X}" for c in text if c != "\n" and unicodedata.category(c) in ("Cc", "Cf", "Cs", "Co", "Cn")})


def test_a_clients_escape_sequences_never_reach_the_terminal_and_the_number_is_still_found(db, capsys):
    row = _hostile_row(db)
    assert "\x1b" in row.mvp_blueprint and RLO in row.business_name
    code, out, err = _run(capsys, row.public_id)
    assert code == 1
    assert _unsafe(out + err) == [], _unsafe(out + err)
    assert "\x1b" not in out and RLO not in out and "\x07" not in out and "\r" not in out and "\x08" not in out
    (line,) = _table_lines(out)
    cells = re.split(r"\s{2,}", line)
    assert cells[:3] == ["Volume I", "page not located", "37"] and "loses 37 calls" in cells[3]
    assert "pwned" in out                                # the words stay; only what acts on a terminal is gone
    assert out.splitlines()[0].startswith("Number audit for audit-") and "Physiotherapy" in out.splitlines()[0]


def test_json_of_the_same_package_is_ascii_escaped(db, capsys):
    row = _hostile_row(db)
    code, raw, _ = _run(capsys, row.public_id, "--json")
    assert code == 1
    assert _unsafe(raw) == [] and all(ord(c) < 128 for c in raw)
    report = json.loads(raw)
    assert report["documents"][0]["findings"][0]["number"] == "37"
    assert "\x1b" not in raw and "\\u001b" in raw        # escaped, so it is data and not a command


@pytest.mark.parametrize("text", [HOSTILE, "a\x00b\x7fc\x9bd", "x\N{ZERO WIDTH SPACE}y\N{LEFT-TO-RIGHT ISOLATE}z\N{ZERO WIDTH NO-BREAK SPACE}", "lone \ud800 surrogate",
                                  "private \ue000 use", "unassigned \u0378", "tab\tand\nnewline\r\nlines",
                                  "\N{LINE SEPARATOR}line\N{PARAGRAPH SEPARATOR}separators"])
def test_safe_replaces_everything_a_terminal_could_act_on(text):
    got = audit.safe(text)
    assert _unsafe(got) == [] and "\n" not in got and "\t" not in got
    assert audit.safe("plain words 37 \N{MULTIPLICATION SIGN} ok") == "plain words 37 \N{MULTIPLICATION SIGN} ok"
    assert audit.safe("\x1b[2J") == "?[2J"
    assert audit.safe("a \N{RIGHT-TO-LEFT OVERRIDE} b") == "a ? b"
    assert len(audit.safe("w" * 1000, 50)) == 50 and audit.safe("w" * 1000, 50).endswith("...")
    assert audit.safe(None) == ""


def test_the_last_pass_before_printing_scrubs_what_a_field_missed():
    import io

    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", newline="\n")
    audit._say("Not found: \x1b[31mred\x1b[0m\N{RIGHT-TO-LEFT OVERRIDE}\nsecond line", stream)
    stream.flush()
    assert stream.buffer.getvalue() == b"Not found: ?[31mred?[0m?\nsecond line\n"


# -- the words ------------------------------------------------------------------------------------

def test_a_long_snippet_is_cut_around_its_number():
    long = "word " * 30 + "37 calls" + " word" * 30
    short = audit._short(long, "37")
    assert len(short) <= audit.SNIPPET_MAX + 6 and "37 calls" in short
    assert short.startswith("...") and short.endswith("...")
    assert audit._short("a short one with 37", "37") == "a short one with 37"
    assert audit._short("37 at the start " + "x " * 60, "37").startswith("37 at")


def test_output_is_safe_on_a_terminal_that_cannot_show_a_character():
    import io

    stream = io.TextIOWrapper(io.BytesIO(), encoding="ascii", errors="strict", newline="\n")
    audit._say("3 \N{MULTIPLICATION SIGN} more bookings", stream)
    stream.flush()
    assert stream.buffer.getvalue() == b"3 ? more bookings\n"
