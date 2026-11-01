"""The known set: the one set of figures every check reads.

Pins: the client's figures come from their answers and never from our questions;
the capacity picture's computed figures, the registry's derived and proposed
claims, the answer's move and proposals and the roadmap's figures are all in it;
a row from before any of them existed still works; and every checking stage
(the answer, the roadmap, the week, the screens, the interview) reads it with
the strict reader, so a small number or a number word is no longer let through.
"""
import json
from decimal import Decimal

from app.figures import known as K
from app.figures.model import Figure, FigureSet, Proposal, as_json
from app.models import Request


def _req(**fields) -> Request:
    base = dict(business_name="Halo Reformer Studio", business_description="A pilates studio.",
                email="owner@example.com")
    base.update(fields)
    return Request(**base)


def _pairs(*pairs) -> str:
    return json.dumps([{"question": q, "answer": a} for q, a in pairs])


PICTURE = {"shape": "weekly_grid", "unit": "reformer spot", "unit_plural": "reformer spots",
           "derived": [{"key": "CAP-01", "value": 432, "label": "reformer spots a week",
                        "working": "12 x 6 a day x 6 days"},
                       {"key": "CAP-05", "value": 144, "label": "reformer spots a week in the slots that sell out",
                        "working": "12 x 2 x 6 days"}]}

MOVE = {"label": "moving 6pm and 7pm to $28", "value": 44928.0, "rounded": 45000, "money": True,
        "unit": "USD", "period": "year", "display": "~ $45,000 a year", "working": "144 x $6 x 52 = $44,928",
        "proposed": [{"value": 28.0, "label": "proposed evening price"}], "cites": ["CAP-05", "CF-04"]}


# -- known_for ---------------------------------------------------------------------------

def test_known_for_holds_a_derived_capacity_figure_and_the_move():
    req = _req(ops_numbers_json=_pairs(("What do you charge?", "$22 a class")),
               capacity_json=json.dumps(PICTURE), answer_json=json.dumps({"headline": "x", "move": MOVE}))
    known = K.known_for(req)
    cap = known.get("CAP-05")
    assert cap.kind == "derived" and cap.value == 144 and cap.period == "week"
    move = known.get("MOVE")
    assert move.kind == "ours" and move.value == Decimal("44928") and move.unit == "USD"
    assert known.match(Decimal(45000), "USD") == [move]          # said rounded, as the page says it
    prop = known.get("PROP-1")
    assert prop.kind == "ours" and prop.unit == "USD" and prop.value == 28
    assert [f.value for f in known.by_kind("theirs")] == [Decimal(22)]


def test_a_move_with_no_proposal_is_derived():
    move = dict(MOVE, proposed=[])
    assert K.move_figures(move)[0].kind == "derived"


def test_a_number_only_in_our_question_is_not_known():
    req = _req(business_description="A studio.",
               ops_numbers_json=_pairs(("Do you run 14 classes a week, or more?", "About that, yes.")))
    known = K.known_for(req)
    assert not known.match(Decimal(14))
    assert not K.known_for_texts(["About that, yes."]).match(Decimal(14))
    assert K.client_texts(req) == ["About that, yes.", "A studio."]


def test_registry_derived_and_proposed_claims_are_known_but_not_the_clients_own():
    registry = {"claims": [
        {"id": "CF-01", "value": 22, "unit": "USD", "provenance": "client_input", "approval_status": "client_stated"},
        {"id": "DV-01", "value": 31937.5, "unit": "USD", "provenance": "machine_computed",
         "approval_status": "machine_verified", "type": "derived_value", "source": "lines[0]: 3 x 95 x 52"},
        {"id": "PT-01", "value": 0.85, "unit": "%", "provenance": "consultant_proposed",
         "approval_status": "consultant_proposed — client approval required", "text": "85% fill"},
        {"id": "XX-01", "value": "n/a", "provenance": "machine_computed"},
        {"id": "RJ-01", "value": 5, "provenance": "consultant_proposed", "approval_status": "rejected"},
    ]}
    known = K.known_for(_req(registry_json=json.dumps(registry)))
    assert "CF-01" not in known and "XX-01" not in known and "RJ-01" not in known
    assert known.get("DV-01").kind == "derived"
    assert known.get("PT-01").kind == "ours" and known.get("PT-01").value == 85


def test_the_roadmaps_figures_are_known():
    plan = {"status": "ready", "figures": [as_json(K.plan_weeks_figure(6)), {"not": "a figure"}]}
    known = K.known_for(_req(action_plan_json=json.dumps(plan)))
    assert known.get("PLAN-WEEKS").value == 6 and known.get("PLAN-WEEKS").unit == "week"


def test_an_old_row_with_nothing_stored_still_gives_a_set():
    req = _req(business_description="We have 12 reformers.")
    known = K.known_for(req)
    assert [f.value for f in known] == [Decimal(12)]
    broken = _req(capacity_json="{not json", answer_json="[]", action_plan_json='{"figures": "x"}',
                  registry_json='{"claims": [1, 2]}')
    assert len(K.known_for(broken)) == 0


def test_a_stage_leaves_out_its_own_old_output_and_adds_what_it_just_computed():
    req = _req(answer_json=json.dumps({"move": MOVE}))
    assert "MOVE" not in K.known_for(req, leave_out={"answer"})
    fresh = Figure("MOVE", Decimal(100), "USD", "year", "ours", Proposal(note="new"), 0)
    assert K.known_for(req, [fresh]).get("MOVE") == fresh
    assert K.with_extra(FigureSet(), [fresh]).get("MOVE") == fresh


def test_hours_come_from_their_words():
    req = _req(ops_numbers_json=_pairs(("When are you busiest, 8am?", "The 6pm and 7pm classes.")))
    assert K.hours_for(req) == {18, 19}
