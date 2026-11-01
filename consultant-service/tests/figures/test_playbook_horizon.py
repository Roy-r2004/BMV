"""A playbook horizon is a week position, or a proposal that says so.

The playbook prompt asks for "week 1", "weeks 2 to 4", "during the build". The
integrity law that flags a schedule stated as fact must accept the positions the
prompt asks for and still flag a quantity (a length of time, an amount) that is not
labelled as a proposal.
"""
import pytest

from app.pipeline import canon as C
from app.pipeline import integrity as it


@pytest.mark.parametrize("horizon", [
    "week 1", "Week 1", "weeks 2 to 4", "Weeks 2-4", "weeks 2-4", "week 12", "month 3", "Month 3", "months 2 to 3",
    "by week 4", "during weeks 2 to 4", "Week 1 and 2", "day 30",
])
def test_a_position_on_the_plans_time_axis_is_not_a_quantity(horizon):
    assert it.is_plan_position(horizon)


@pytest.mark.parametrize("horizon", [
    "30 days", "first 30 days", "$5k", "6 weeks", "Weeks 1 to 4 and 90 days", "May 12", "in 2026", "Phase 2",
    "after 3 months", "week 1, then $200",
])
def test_anything_else_with_a_digit_is_a_quantity(horizon):
    assert not it.is_plan_position(horizon)


def _findings(*steps):
    content = {"playbook": {"steps": [dict(title="Set the price", **s) for s in steps]}}
    return [f for f in it.structure_findings(content, C.Canon([])) if f.where.startswith("playbook:")]


def test_the_law_passes_positions_and_proposals_and_flags_the_rest():
    assert _findings({"horizon": "week 1"}, {"horizon": "weeks 2 to 4"}, {"horizon": "month 3"},
                     {"horizon": "during the build"}, {"horizon": "every week after launch"}) == []
    assert _findings({"horizon": "6 weeks (proposed - client approval required)"}) == []
    flagged = _findings({"horizon": "30 days"}, {"horizon": "$5k"}, {"horizon": "first 30 days"})
    assert [f.issue for f in flagged] == ["a schedule horizon is stated as fact: '30 days'",
                                          "a schedule horizon is stated as fact: '$5k'",
                                          "a schedule horizon is stated as fact: 'first 30 days'"]
    assert all(f.kind == it.MISCLASSIFIED for f in flagged)


def test_the_when_of_a_step_is_held_to_the_same_rule():
    assert _findings({"horizon": "week 1", "when": "weeks 2 to 3"}) == []
    assert len(_findings({"horizon": "week 1", "when": "30 days"})) == 1
