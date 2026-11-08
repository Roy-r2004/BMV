"""The sums that decide the question: the model picks them, code does them."""
import json
from decimal import Decimal

import pytest

from app.figures import sums
from app.figures.known import known_for
from app.figures.model import Figure, FigureSet, Proposal, TheirsSource, Working, display


def theirs(id_, value, unit):
    return Figure(id_, Decimal(value), unit, None, "theirs", TheirsSource(None, None, "q", None, None), 0)


KNOWN = FigureSet([theirs("A", "500", "bookings"), theirs("B", "180", "AED"), theirs("C", "20", "percent"),
                   theirs("D", "180000", "AED"), theirs("E", "18000", "AED")])


def sum_(op, inputs, unit="AED", period="month", label="a sum", **kw):
    return {"label": label, "op": op, "inputs": inputs, "unit": unit, "period": period, **kw}


def test_code_does_the_arithmetic_and_keeps_the_working():
    [gross] = sums.compute([sum_("product", ["A", "B"], label="takings at the goal")], KNOWN)
    assert gross.id == "SUM-1" and gross.value == Decimal("90000") and gross.kind == "derived"
    assert gross.source.text.startswith("takings at the goal: ") and "90,000" in gross.source.text


def test_a_percent_is_used_as_a_share_and_reads_as_a_percent():
    [_, share] = sums.compute([sum_("product", ["A", "B"]), sum_("product", ["SUM-1", "C"])], KNOWN)
    assert share.value == Decimal("18000")
    assert "20%" in share.source.text and "0.01" not in share.source.text


def test_a_later_sum_can_use_an_earlier_one():
    out = sums.compute([sum_("product", ["A", "B"]), sum_("product", ["SUM-1", "C"]),
                        sum_("difference", ["SUM-2", "E"])], KNOWN)
    assert out[2].value == Decimal("0")


def test_a_ratio_gives_a_readable_number():
    [months] = sums.compute([sum_("ratio", ["D", "E"], unit="months", period=None)], KNOWN)
    assert months.value == Decimal("10") and display(months).startswith("10")


def test_a_calendar_constant_is_allowed():
    [yearly] = sums.compute([sum_("product", ["E"], period="year", constants=[{"value": 12, "label": "months a year"}])], KNOWN)
    assert yearly.value == Decimal("216000")


@pytest.mark.parametrize("bad", [
    sum_("product", ["A", "NOPE"]),                                # a figure nobody has
    sum_("product", ["A", 999]),                                   # a number written in, not cited
    sum_("divide", ["A", "B"]),                                    # not an operation
    sum_("ratio", ["A", "ZERO"]),                                  # division by zero
    sum_("total", ["A", "B"]),                                     # bookings added to dirhams
    sum_("product", ["E"], constants=[{"value": 37, "label": "invented"}]),  # not a calendar constant
    "not a sum",
])
def test_a_sum_that_cannot_be_trusted_is_left_out(bad):
    known = FigureSet([*KNOWN, theirs("ZERO", "0", "AED")])
    assert sums.compute([bad], known) == []


def test_a_bad_sum_does_not_lose_the_good_ones_and_a_later_sum_cannot_lean_on_it():
    out = sums.compute([sum_("product", ["A", "NOPE"]), sum_("product", ["A", "B"]), sum_("product", ["SUM-1", "C"])], KNOWN)
    assert [f.value for f in out] == [Decimal("90000")]


def test_a_sum_resting_on_our_own_proposal_is_ours():
    ours = Figure("P", Decimal("2"), "times", None, "ours", Proposal(note="a guess"), 0)
    [f] = sums.compute([sum_("product", ["E", "P"])], FigureSet([*KNOWN, ours]))
    assert f.kind == "ours"


def test_the_number_of_sums_is_bounded():
    many = [sum_("product", ["A", "B"]) for _ in range(40)]
    from app.config import settings
    assert len(sums.compute(many, KNOWN)) == settings.SUMS_MAX


def _row(**kw):
    from app.models import Request
    base = dict(business_name="X", business_description="d", email="e@x.co", main_problem="Is there a business in it?")
    base.update(kw)
    return Request(**base)


def test_stored_sums_join_what_the_request_knows():
    from app.figures.model import as_json
    [f] = sums.compute([sum_("product", ["A", "B"])], KNOWN)
    known = known_for(_row(sums_json=json.dumps([as_json(f)])))
    assert known.get("SUM-1") == f


def test_worked_out_sums_become_claims_and_estimates_do_not():
    from app.figures.model import as_json
    ours = Figure("P", Decimal("2"), "times", None, "ours", Proposal(note="a guess"), 0)
    done = sums.compute([sum_("product", ["A", "B"]), sum_("product", ["E", "P"])], FigureSet([*KNOWN, ours]))
    claims = sums.as_claims(_row(sums_json=json.dumps([as_json(f) for f in done])))
    assert [c["id"] for c in claims] == ["SUM-1"] and claims[0]["provenance"] == "machine_computed"


@pytest.mark.parametrize("verdict,confidence,expected", [
    ("supported", "high", True), ("supported", "medium", True), ("supported", "low", False),
    ("untestable", "high", False), ("refuted", "high", False),
])
def test_only_a_proven_explanation_counts_as_settled(verdict, confidence, expected):
    from app.pipeline.answer import settled
    diagnosis = {"leading": "h1", "hypotheses": [{"id": "h1", "test": {"verdict": verdict}}]}
    assert settled(_row(diagnosis_json=json.dumps(diagnosis)), {"confidence": confidence}) is expected


def test_the_answer_prompt_forbids_stating_an_unproven_cause_only_when_unproven():
    from app.templating import render
    args = dict(business_name="X", main_problem="p", kind="k", central_problem="c", summary="s", why_not="w", confidence="low",
                unverified="u", leading="l", claims="c", figures_block="f")
    assert "was NOT proven" in render("answer.j2", settled=False, **args)
    assert "was NOT proven" not in render("answer.j2", settled=True, **args)


def summed(id_, value, inputs=("T1",)):
    return Figure(id_, Decimal(value), "AED", None, "derived", Working(tuple(inputs), "product", f"working of {id_}"), 0)


def test_a_share_of_a_whole_reads_as_a_percent():
    known = FigureSet([theirs("N", 96, "no-shows"), theirs("D", 480, "booked")])
    [rate] = sums.compute([sum_("ratio", ["N", "D"], unit="percent", period=None)], known)
    assert rate.value == Decimal("20") and "100" not in rate.source.text


def _write_with_a_check(monkeypatch, verdicts):
    from app.config import settings
    from app.database import Base, SessionLocal, engine
    from app.models import Request

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    row = _row(ops_numbers_json=json.dumps([{"id": "a", "question": "How many?", "answer": "500 bookings at AED 180"}]))
    db.add(row)
    db.commit()
    asks, checks = [], list(verdicts)

    def chat(model, messages, **k):
        content = messages[0]["content"]
        if "second pair of eyes" in content:
            return {"choices": [{"message": {"content": json.dumps(checks.pop(0))}}], "usage": {}}
        asks.append(content)
        return {"choices": [{"message": {"content": '{"sums": []}'}}], "usage": {}}

    monkeypatch.setattr(sums.provider, "chat", chat)
    monkeypatch.setattr(sums, "compute", lambda proposed, known: [summed("SUM-1", 5)])
    sums.write(db, row.id)
    db.refresh(row)
    stored = row.sums_json
    db.delete(db.get(Request, row.id))
    db.commit()
    db.close()
    return asks, stored, settings


def test_a_sum_that_adds_up_but_means_the_wrong_thing_is_sent_back(monkeypatch):
    asks, stored, _ = _write_with_a_check(monkeypatch, [{"wrong": [{"id": "SUM-1", "why": "ignores the commission"}]}, {"wrong": []}])
    assert len(asks) == 2 and "ignores the commission" in asks[1] and stored


def test_a_sum_still_wrong_after_a_second_try_is_dropped(monkeypatch):
    _, stored, _ = _write_with_a_check(monkeypatch, [{"wrong": [{"id": "SUM-1", "why": "no"}]}, {"wrong": [{"id": "SUM-1", "why": "no"}]}])
    assert stored is None


def test_what_leaned_on_a_wrong_sum_goes_with_it():
    figures = [summed("SUM-1", 5), summed("SUM-2", 6, ["SUM-1"]), summed("SUM-3", 7)]
    assert [f.id for f in sums._without(figures, {"SUM-1"})] == ["SUM-3"]


def test_when_the_first_model_cannot_answer_the_second_is_asked(monkeypatch):
    from app.config import settings
    from app.database import Base, SessionLocal, engine
    from app.models import Request

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    row = _row(ops_numbers_json=json.dumps([{"id": "a", "question": "How many?", "answer": "500 bookings at AED 180"}]))
    db.add(row)
    db.commit()
    asked = []

    def chat(model, *a, **k):
        asked.append(model)
        content = "thinking out loud, no JSON here" if model == settings.REASONING_MODEL else '{"sums": []}'
        return {"choices": [{"message": {"content": content}}], "usage": {}}

    monkeypatch.setattr(sums.provider, "chat", chat)
    monkeypatch.setattr(sums, "compute", lambda proposed, known: [summed("SUM-1", 5)])
    monkeypatch.setattr(sums, "_wrong_sums", lambda *a: {})
    sums.write(db, row.id)
    db.refresh(row)
    assert asked[-1] == settings.ANALYSIS_MODEL and asked[0] == settings.REASONING_MODEL and row.sums_json
    db.delete(db.get(Request, row.id))
    db.commit()
    db.close()


def test_a_bad_reply_means_no_sums_not_a_stopped_run(monkeypatch):
    from app.database import Base, SessionLocal, engine
    from app.models import Request

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    row = _row(ops_numbers_json=json.dumps([{"id": "a", "question": "How many?", "answer": "500 bookings at AED 180"}]))
    db.add(row)
    db.commit()

    def broken(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(sums.provider, "chat", broken)
    sums.write(db, row.id)
    db.refresh(row)
    assert row.sums_json is None
    db.delete(db.get(Request, row.id))
    db.commit()
    db.close()
