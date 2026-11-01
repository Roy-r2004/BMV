"""The known set: the one set of figures every check reads.

Pins: the client's figures come from their answers and never from our questions;
the capacity picture's computed figures, the registry's derived and proposed
claims, the answer's move and proposals and the roadmap's figures are all in it;
a row from before any of them existed still works; and every checking stage
(the answer, the roadmap, the week, the screens, the interview) reads it with
the strict reader, so a small number or a number word is no longer let through.
"""
import json
import time
from decimal import Decimal

import pytest

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


# -- the stages read it ------------------------------------------------------------------

HALO = ["12 reformers. Six classes a day, six days a week.", "About 10 of 12 in a typical class.",
        "$22 a class.", "Two others nearby, both $32 a class."]
CLAIMS = [{"id": "CF-04", "value": 22, "unit": "USD", "text": "$22 a class", "provenance": "client_input"},
          {"id": "CF-06", "value": 32, "unit": "USD", "text": "$32", "provenance": "client_input"}]


def _answer(raw, texts=HALO):
    from app.pipeline import answer
    return answer.shape(raw, CLAIMS, K.known_for_texts(texts), K.hours_in(texts))


def test_a_headline_with_twelve_she_never_gave_is_dropped_and_kept_when_she_did():
    raw = {"headline": "You turn away twelve people a week.", "sub": ""}
    got, problems = _answer(raw, ["$22 a class."])
    assert got is None and any("twelve" in p for p in problems)
    got, problems = _answer(raw, ["We turn away twelve people a week."])
    assert got["headline"] == "You turn away 12 people a week." and not problems


def test_a_headline_figure_keeps_the_ids_of_both_figures_it_names_and_an_unmatched_one_is_dropped():
    raw = {"headline": "You are the cheapest nearby.",
           "figures": [{"value": "$22 vs $32", "label": "you and two studios nearby", "cites": ["CF-04", "CF-06"]},
                       {"value": "$22 vs $35", "label": "made up", "cites": ["CF-04"]}]}
    got, problems = _answer(raw)
    known = K.known_for_texts(HALO)
    ids = got["figures"][0]["ids"]
    assert [f["value"] for f in got["figures"]] == ["$22 vs $32"] and problems
    assert [known.get(i).value for i in ids[:2]] == [22, 32] and all(known.get(i).unit == "USD" for i in ids[:2])
    assert "2 studios" in got["figures"][0]["label"]     # "two studios" is bound too
    assert len(ids) == 2                                  # but the ids are the value's only


@pytest.mark.parametrize("value", ["Week 4", "Phase 2", "Q3"])
def test_a_headline_figure_that_names_no_figure_is_dropped(value):
    # a plan position, a label and an identifier pass the reader, but a headline figure must BE a figure
    got, problems = _answer({"headline": "You are full.", "figures": [{"value": value, "label": "x", "cites": ["CF-04"]}]})
    assert got["figures"] == [] and problems


def test_the_plan_name_comes_from_the_stored_duration_figure_never_the_models_words():
    from app.figures.model import from_json
    got, _ = _answer({"headline": "You are full.", "action": {"weeks": 6, "name": "eight-week sprint"}})
    figure = from_json(got["action"]["figure"])
    assert figure.id == "PLAN-WEEKS" and figure.kind == "ours" and figure.value == 6 and figure.unit == "week"
    assert got["action"]["name"] == "6-week plan"
    got, _ = _answer({"headline": "You are full.", "action": {"weeks": 4, "name": "Evening price pilot"}})
    assert got["action"]["name"] == "Evening price pilot"          # no number in it: the model's own name stays
    got, _ = _answer({"headline": "You are full.", "action": {"weeks": 30}})
    assert got["action"]["name"] == "12-week plan"                 # held to the bound
    # the roadmap reads the same figure from the stored answer, so its prose can say it
    req = _req(answer_json=json.dumps(got))
    assert K.known_for(req).get("PLAN-WEEKS") == from_json(got["action"]["figure"])


def _roadmap(**over):
    raw = {"summary": "We do this in two phases over four weeks.",
           "phases": [{"when": "Weeks 1 to 2", "title": "Set the evening price",
                       "do": "Over two weeks we move the evening classes to $22 and tell your regulars.", "by": "us"},
                      {"when": "Weeks 3 to 4", "title": "Watch the evenings",
                       "do": "We track evening fill against 10 of 12 each week.", "by": "us"}],
           "decisions": [{"question": "Go ahead?", "detail": "", "options": ["Yes", "Not yet"]}],
           "assumptions": []}
    raw.update(over)
    return raw


def test_the_roadmap_registers_its_lengths_as_ours_and_its_prose_binds_to_them():
    from app.figures.model import from_json
    from app.pipeline import action_plan
    plan, problems = action_plan.shape(_roadmap(), K.known_for_texts(HALO))
    # "over four weeks" is a limit: it binds only on the figure's exact value (PLAN-WEEKS
    # is 4) and is never rewritten, so the model's wording stays; "two phases" is a count
    assert not problems and plan["summary"] == "We do this in 2 phases over four weeks."
    # a limit that is not the figure's exact value names nothing, and the summary goes
    plan, problems = action_plan.shape(_roadmap(summary="We do this over five weeks."), K.known_for_texts(HALO))
    assert plan["summary"] == "" and any("five" in p for p in problems)
    figures = {f.id: f for f in map(from_json, plan["figures"])}
    assert {i: (f.value, f.unit, f.kind) for i, f in figures.items()} == {
        "PLAN-WEEKS": (4, "week", "ours"), "PLAN-PHASE-1-WEEKS": (2, "week", "ours"),
        "PLAN-PHASE-2-WEEKS": (2, "week", "ours"), "PLAN-PHASES": (2, "phases", "ours")}
    # with the answer's plan length, the roadmap uses that one
    plan, problems = action_plan.shape(_roadmap(summary="A six-week plan."), K.known_for_texts(HALO),
                                       plan_weeks=K.plan_weeks_figure(6))
    assert plan["summary"] == "A 6-week plan."
    assert any(f["id"] == "PLAN-WEEKS" and f["value"] == "6" for f in plan["figures"])


def test_a_roadmap_phase_with_an_invented_price_or_a_small_invented_number_is_dropped():
    from app.pipeline import action_plan
    raw = _roadmap()
    raw["phases"].append({"when": "Week 5", "title": "Match the studio down the road",
                          "do": "We move to $35 like them.", "by": "us"})
    raw["phases"].append({"when": "Month 3 on", "title": "Add 3 classes", "do": "We add classes.", "by": "us"})
    plan, problems = action_plan.shape(raw, K.known_for_texts(HALO))
    assert [p["title"] for p in plan["phases"]] == ["Set the evening price", "Watch the evenings"]
    assert any("$35" in p for p in problems) and any(p.endswith(": 3") for p in problems)


def test_interview_fact_values_are_held_to_every_number_in_their_words():
    from app.routers import discovery
    facts = [{"key": "price", "label": "Price", "status": "need", "value": ""},
             {"key": "phase", "label": "Phase", "status": "need", "value": ""}]
    texts = ["We charge $22 a class, six classes a day, since 2019."]
    updates, _ = discovery.shape_fact_updates(
        [{"key": "price", "value": "$22, six a day, since 2019"},          # all theirs
         {"key": "price", "value": "twelve a day"},                        # a number word she never gave
         {"key": "price", "value": "1 in 20"},                             # a small number is a number
         {"key": "price", "value": "the 3rd class"},                       # an ordinal
         {"key": "price", "value": "$22 at 7pm"},                          # a time she never named
         {"key": "phase", "value": "Phase 4"},                             # digits behind a label
         {"key": "price", "value": "since 2020"}], [], facts, texts)      # a date she never wrote
    assert updates == [{"key": "price", "value": "$22, six a day, since 2019"}]
    # a value read off a quote: the quote must be theirs, and every number in the value in the quote
    assert discovery._fact_value("$22", "We charge $22 a class", texts) == "$22"
    assert discovery._fact_value("$22, six a day", "We charge $22 a class", texts) == ""


def test_a_number_only_our_interview_question_holds_does_not_back_a_fact():
    from app.routers import discovery
    ops = json.dumps([{"question": "Do you run 14 classes a week?", "answer": "Yes, about that."}])
    assert discovery._answers(ops) == ["Yes, about that."]
    updates, _ = discovery.shape_fact_updates([{"key": "price", "value": "14 a week"}], [],
                                              [{"key": "price", "label": "x", "status": "need", "value": ""}],
                                              discovery._answers(ops))
    assert updates == []
    out = discovery.shape_casefile({"summary": "You run 14 classes a week. You want an app.",
                                    "their_fix": "14 classes"},
                                   {"q1": "Do you run 14 classes a week? — Yes, about that."}, True,
                                   theirs={"q1": "Yes, about that."})
    assert out["summary"] == "You want an app." and out["their_fix"] is None


def test_the_week_is_checked_in_their_words_and_a_price_is_not_a_count():
    from app.pipeline import capacity
    grid = {"shape": "weekly_grid", "unit": "seat", "per_slot": 22, "slots_per_day": 6, "days_per_week": 6}
    assert capacity.shape(grid, ["Six sittings a day, six days a week. Lunch is $22."]) is None
    assert capacity.shape(grid, ["22 seats. Six sittings a day, six days a week."])["capacity"] == 22 * 36


def test_screens_captions_and_story_are_bound_and_an_unmatched_item_is_dropped():
    from app.screens import generate
    known = K.known_for_texts(HALO)
    assert generate._clean_text("You run twelve reformers. You will run 40.", known, set()) == "You run 12 reformers."
    story = generate._check_story({"headline": "Twelve reformers, full",
                                   "needs": ["A list of your 12 regulars", "3 new staff"],
                                   "comparison": {"rows": [{"label": "Price", "cells": ["$22", "$40"]},
                                                           {"label": "Reformers", "cells": ["12", "twelve"]}]},
                                   "ambition": {"pillars": [{"title": "Six a day", "text": "x"},
                                                            {"title": "Nine a day", "text": "x"}]}},
                                  known, set())
    assert story["headline"] == "12 reformers, full"
    # a count carries its noun: "12 reformers" does not back "12 regulars"
    assert story["needs"] == []
    assert story["comparison"]["rows"] == [{"label": "Reformers", "cells": ["12", "12"]}]
    assert [p["title"] for p in story["ambition"]["pillars"]] == ["6 a day"]
    # when her own words give "12 regulars", the need stands
    theirs = K.known_for_texts([*HALO, "We have 12 regulars."])
    assert generate._check_story({"needs": ["A list of your 12 regulars"]}, theirs, set())["needs"] == [
        "A list of your 12 regulars"]


# -- review fixes ----------------------------------------------------------------------------

def _plan(raw_phases, plan_weeks=None):
    from app.pipeline import action_plan
    return action_plan.shape(_roadmap(phases=raw_phases), K.known_for_texts(HALO), plan_weeks=plan_weeks)


def test_a_phase_span_past_the_plan_is_refused_and_its_length_vouches_for_nothing():
    ok = {"when": "Weeks 3 to 4", "title": "Watch the evenings", "do": "We track evening fill each week.", "by": "us"}
    long = {"when": "Weeks 1 to 20", "title": "Move the price", "do": "Over 20 weeks we move it.", "by": "us"}
    plan, problems = _plan([long, ok, dict(ok, when="Weeks 5 to 6")], plan_weeks=K.plan_weeks_figure(6))
    assert [p["when"] for p in plan["phases"]] == ["Weeks 3 to 4", "Weeks 5 to 6"]
    assert any("week 20" in p for p in problems)
    assert all(f["value"] != "20" for f in plan["figures"])
    # with no plan length from the answer, the longest plan we make is the bound
    plan, _ = _plan([long, ok, dict(ok, when="Weeks 5 to 6")])
    assert [p["when"] for p in plan["phases"]] == ["Weeks 3 to 4", "Weeks 5 to 6"]


def test_a_quantity_in_a_phases_when_must_name_a_figure():
    ok = {"when": "Weeks 1 to 2", "title": "Set the price", "do": "We move it to $22.", "by": "us"}
    plan, problems = _plan([ok, dict(ok, when="Weeks 3 to 4"), dict(ok, when="When revenue hits $10k")])
    assert [p["when"] for p in plan["phases"]] == ["Weeks 1 to 2", "Weeks 3 to 4"]
    assert any("$10k" in p for p in problems)


def test_an_old_answer_without_a_length_figure_gives_its_stored_weeks_to_the_roadmap():
    req = _req(answer_json=json.dumps({"headline": "x", "action": {"weeks": 8, "name": "8-week plan"}}))
    assert K.known_for(req).get("PLAN-WEEKS") == K.plan_weeks_figure(8)


@pytest.mark.parametrize("name", ["one-month pilot", "a fortnight sprint", "Sprint 2", "Two-quarter rollout"])
def test_a_plan_name_that_says_how_long_is_rendered_from_the_length(name):
    got, _ = _answer({"headline": "You are full.", "action": {"weeks": 6, "name": name}})
    assert got["action"]["name"] == "6-week plan"


def test_a_plan_name_with_no_duration_is_kept():
    got, _ = _answer({"headline": "You are full.", "action": {"weeks": 6, "name": "Booking pilot"}})
    assert got["action"]["name"] == "Booking pilot"


def test_the_plan_length_bounds_are_settings(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "PLAN_WEEKS_MAX", 8)
    monkeypatch.setattr(settings, "PLAN_WEEKS_DEFAULT", 4)
    assert _answer({"headline": "You are full.", "action": {"weeks": 30}})[0]["action"]["weeks"] == 8
    assert _answer({"headline": "You are full.", "action": {}})[0]["action"]["weeks"] == 4


@pytest.mark.parametrize("bad", [
    {"capacity_json": json.dumps({"shape": "total", "derived": 5})},
    {"capacity_json": json.dumps({"shape": "total", "unit_plural": 7, "derived": [{"key": "CAP-01", "value": 3}]})},
    {"answer_json": json.dumps({"move": {"value": 100, "proposed": 7}})},
    {"answer_json": json.dumps({"move": {"value": 100, "proposed": [], "cites": "CF-01"}})},
    {"answer_json": json.dumps({"move": {"value": 1e300, "unit": 5, "proposed": [{"value": "x"}]}})},
    {"answer_json": json.dumps({"action": {"weeks": "six", "figure": "nope"}})},
])
def test_known_for_never_raises_on_malformed_stored_json(bad):
    known = K.known_for(_req(**bad))
    assert isinstance(known, FigureSet)


def test_a_non_string_unit_plural_falls_back_to_no_unit():
    fig = K.capacity_figures({"shape": "total", "unit_plural": 7, "derived": [{"key": "CAP-01", "value": 3}]})
    assert fig[0].unit == ""


@pytest.mark.parametrize("words", ["Lunch is A$22.", "Lunch is 22 AUD.", "Lunch is CAD 22.", "A sitting takes 22 minutes."])
def test_money_in_any_currency_or_a_length_of_time_is_not_a_count_in_the_week(words):
    from app.pipeline import capacity
    grid = {"shape": "weekly_grid", "unit": "seat", "per_slot": 22, "slots_per_day": 6, "days_per_week": 6}
    assert capacity.shape(grid, [f"Six sittings a day, six days a week. {words}"]) is None


def test_the_days_a_week_may_be_counted_in_days():
    from app.pipeline import capacity
    grid = {"shape": "weekly_grid", "unit": "seat", "per_slot": 22, "slots_per_day": 3, "days_per_week": 5}
    assert capacity.shape(grid, ["22 seats, 3 sittings, open 5 days a week."])["capacity"] == 22 * 3 * 5


def test_an_interview_value_is_held_the_way_every_stage_binds():
    from app.routers import discovery
    theirs = discovery._TheirWords(["We charge $22 a class. We open at 6pm. We started 2019."])
    assert theirs.missing("22 classes") == ["22"]          # a count is not backed by money
    assert theirs.missing("$22") == []
    assert theirs.missing("Phase 6") == ["6"]              # a digit inside a time backs no label
    assert theirs.missing("since 2019") == []              # a bare year backs the date
    assert theirs.missing("since 2018") == ["2018"]


def test_fact_updates_read_their_words_once():
    from app.routers import discovery
    calls = []
    real = discovery._TheirWords.__init__

    def counting(self, texts):
        calls.append(1)
        real(self, texts)

    facts = [{"key": f"k{i}", "label": "x", "status": "need", "value": ""} for i in range(10)]
    updates = [{"key": f"k{i}", "value": "$22 a class"} for i in range(10)]
    discovery._TheirWords.__init__ = counting
    try:
        start = time.perf_counter()
        got, _ = discovery.shape_fact_updates(updates, [], facts, ["We charge $22 a class."] * 20)
        elapsed = time.perf_counter() - start
    finally:
        discovery._TheirWords.__init__ = real
    assert len(got) == 10 and calls == [1] and elapsed < 2


def test_the_client_texts_have_one_source():
    from app.figures import casefile
    from app.routers import discovery
    req = _req(business_description="A studio.\n\nFigures the client did not know: rent",
               ops_numbers_json=_pairs(("Q with 14?", "We run 12."), ("Empty?", "  ")))
    assert K.client_texts(req) == casefile.client_texts(req) == ["We run 12.", "A studio."]
    assert discovery._answers(req.ops_numbers_json) == casefile.answers(req.ops_numbers_json) == ["We run 12."]


# -- re-review fixes ---------------------------------------------------------------------------

@pytest.mark.parametrize("when", ["Week 1 to 2", "Week 2 to 4", "Weeks 3 - 6", "Weeks 1 – 2",
                                  "Week 1 through 3", "Week 1 and 2"])
def test_a_when_that_is_a_span_of_weeks_is_kept_as_written(when):
    ok = {"when": when, "title": "Set the price", "do": "We move it to $22.", "by": "us"}
    plan, _ = _plan([ok, dict(ok, when="Weeks 5 to 6")], plan_weeks=K.plan_weeks_figure(6))
    assert [p["when"] for p in plan["phases"]] == [when, "Weeks 5 to 6"]


@pytest.mark.parametrize("when", ["When revenue hits $10k", "Month 1 to 3 then $5k"])
def test_any_other_when_is_bound_and_a_quantity_in_it_drops_the_phase(when):
    ok = {"when": "Weeks 1 to 2", "title": "Set the price", "do": "We move it to $22.", "by": "us"}
    plan, problems = _plan([ok, dict(ok, when="Weeks 3 to 4"), dict(ok, when=when)])
    assert [p["when"] for p in plan["phases"]] == ["Weeks 1 to 2", "Weeks 3 to 4"] and problems


def test_a_pool_sold_in_hours_is_counted_in_hours():
    from app.pipeline import capacity
    pool = {"shape": "total", "unit": "hour", "unit_plural": "hours", "total_capacity": 30, "total_taken": 24,
            "period": "week"}
    pic = capacity.shape(pool, ["I can do 30 hours a week and use 24 of them."])
    assert pic["capacity"] == 30 and pic["taken"] == 24
    # a length of time still vouches for no count of anything else
    seats = {"shape": "weekly_grid", "unit": "seat", "per_slot": 22, "slots_per_day": 6, "days_per_week": 6}
    assert capacity.shape(seats, ["Six sittings a day, six days a week. A sitting takes 22 minutes."]) is None
    assert capacity.shape(dict(pool, unit="order", unit_plural="orders"),
                          ["I can do 30 hours a week and use 24 of them."]) is None


def test_the_shortest_plan_may_not_pass_the_longest(caplog):
    import os
    import subprocess
    import sys

    from app import config
    with caplog.at_level("WARNING", logger="consultant.config"):
        assert config._at_most("PLAN_WEEKS_MIN", 12, "PLAN_WEEKS_MAX", 8) == 8
    assert "PLAN_WEEKS_MIN=12 is above PLAN_WEEKS_MAX=8" in caplog.text
    assert config._at_most("PLAN_WEEKS_MIN", 2, "PLAN_WEEKS_MAX", 8) == 2
    # at load, from the environment (a fresh interpreter, so this process's settings are untouched)
    env = dict(os.environ, PLAN_WEEKS_MIN="12", PLAN_WEEKS_MAX="5")
    out = subprocess.run([sys.executable, "-c", "from app.config import settings as s; "
                          "print(s.PLAN_WEEKS_MIN, s.PLAN_WEEKS_MAX)"],
                         env=env, capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(
                             os.path.dirname(os.path.abspath(__file__)))), timeout=60)
    assert out.stdout.split() == ["5", "5"]


# -- whole-branch review: a roadmap loses sentences, not phases --------------------------------

REALISTIC = [
    {"when": "Weeks 1 to 2", "title": "Win back the regulars", "by": "us",
     "do": "We message your 200 regulars about the evening slots. We set up the waiting list for you.",
     "you": "A 1-hour session"},
    {"when": "Weeks 3 to 4", "title": "Fill the gaps", "by": "us",
     "do": "We answer every enquiry within 15 minutes. We put the 48 empty spots on the booking page. "
           "We watch the evenings with you each week."},
]


def test_a_phase_with_unowned_operational_numbers_keeps_its_other_sentences():
    plan, problems = _plan(REALISTIC)
    assert [p["title"] for p in plan["phases"]] == ["Win back the regulars", "Fill the gaps"]
    assert plan["phases"][0]["do"] == "We set up the waiting list for you."
    assert plan["phases"][0]["you"] == ""                       # "a 1-hour session" names nothing
    assert plan["phases"][1]["do"] == "We watch the evenings with you each week."
    # the retry is told exactly what went
    for gone in ("200 regulars", "within 15 minutes", "48 empty spots", "1-hour session"):
        assert any(gone in p for p in problems), gone


def test_a_phase_whose_whole_do_is_unowned_or_whose_title_is_goes_and_too_few_still_fail():
    from app.pipeline import action_plan
    bare = [dict(REALISTIC[0], do="We message your 200 regulars."), dict(REALISTIC[1], title="Fill 48 spots")]
    plan, problems = _plan(bare)
    assert plan is None and "fewer than two usable phases" in problems
    assert any("nothing left" in p for p in problems)
    assert action_plan.shape(_roadmap(phases=bare), K.known_for_texts(HALO))[0] is None


def test_a_roadmap_that_cleans_down_to_one_phase_is_retried_then_stops_the_run(monkeypatch):
    from app.database import Base, SessionLocal, engine
    from app.pipeline import action_plan
    from app.pipeline.failure import StageFailed

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    row = Request(business_name="Halo", business_description="A pilates studio.", email="o@example.com",
                  ops_numbers_json=_pairs(("What do you charge?", "$22 a class")))
    db.add(row)
    db.commit()
    calls = []

    def reply(call, parse, record):
        calls.append(1)
        return _roadmap(phases=[dict(REALISTIC[0], do="We message your 200 regulars."), REALISTIC[1]])

    monkeypatch.setattr(action_plan, "ask_until_usable", reply)
    try:
        with pytest.raises(StageFailed) as stopped:
            action_plan.write(db, row.id)
        assert stopped.value.stage == "roadmap" and "fewer than two usable phases" in str(stopped.value.cause)
        assert len(calls) == 2
        db.refresh(row)
        assert json.loads(row.action_plan_json) == {"status": "failed"}
    finally:
        db.close()


def test_a_decision_keeps_its_question_and_the_options_that_name_no_unowned_price():
    plan, problems = action_plan_shape(decisions=[
        {"question": "Which evening price?", "detail": "Daytime stays at $22. The studio down the road charges $35.",
         "options": ["Keep $22", "Raise to $40", "Not yet"]},
        {"question": "Charge $40 at weekends?", "options": ["Yes", "No"]},
        {"question": "Go ahead?", "options": ["Raise to $40", "Yes"]}])
    assert [d["question"] for d in plan["decisions"]] == ["Which evening price?"]
    assert plan["decisions"][0]["options"] == ["Keep $22", "Not yet"]
    assert plan["decisions"][0]["detail"] == "Daytime stays at $22."


def action_plan_shape(**over):
    from app.pipeline import action_plan
    return action_plan.shape(_roadmap(**over), K.known_for_texts(HALO))


def test_a_number_the_roadmap_labels_as_our_proposal_is_ours_and_binds():
    from app.figures.model import from_json
    plan, _ = action_plan_shape(decisions=[
        {"question": "Which evening price?", "options": ["$26 (proposed)", "Keep $22"]},
        {"question": "How long a trial?", "options": ["4 weeks (our proposal)", "Not yet"]}],
        summary="We trial $26 (proposed) evenings. We also try $30 with no label.")
    assert plan["decisions"][0]["options"] == ["$26 (proposed)", "Keep $22"]
    assert plan["decisions"][1]["options"] == ["4 weeks (our proposal)", "Not yet"]
    assert plan["summary"] == "We trial $26 (proposed) evenings."      # an unlabelled price still goes
    figures = {f.id: f for f in map(from_json, plan["figures"])}
    assert (figures["PLAN-PROP-1"].value, figures["PLAN-PROP-1"].unit, figures["PLAN-PROP-1"].kind) == (26, "USD", "ours")
    assert figures["PLAN-PROP-1"].source.note == "proposed in the roadmap"
    assert (figures["PLAN-PROP-2"].value, figures["PLAN-PROP-2"].unit) == (4, "week")


def test_the_proposals_a_roadmap_may_label_are_bounded(monkeypatch):
    from app.config import settings
    from app.pipeline import action_plan
    monkeypatch.setattr(settings, "PLAN_PROPOSED_FIGURES_MAX", 2)
    raw = _roadmap(summary="We try $24 (proposed), $25 (proposed) and $26 (proposed). Again $24 (proposed).")
    got = action_plan.proposed_figures(raw)
    assert [f.value for f in got] == [24, 25]


# -- the set, as a prompt shows it -------------------------------------------------------

def _theirs(n: int, value=22, unit="USD", quote="I charge $22 a class") -> Figure:
    from app.figures.model import TheirsSource
    return Figure(f"T{n}-1", Decimal(value), unit, None, "theirs", TheirsSource(n, None, quote, None, None), 0)


def _derived(key="CAP-01", value=432, unit="reformer spots", period="week", text="12 x 6 a day x 6 days") -> Figure:
    from app.figures.model import Working
    return Figure(key, Decimal(value), unit, period, "derived", Working((), "capacity", text), 0)


def _ours(key="PLAN-WEEKS", value=6, unit="week", note="the length of the plan we propose") -> Figure:
    return Figure(key, Decimal(value), unit, None, "ours", Proposal(note=note), 0)


def _reference() -> Figure:
    from app.figures.model import Reference
    return Figure("REF-1", Decimal(40), "percent", None, "reference",
                  Reference("Pilates Institute", 2024, "studios in Europe", "https://example.org"), 0)


def test_one_line_per_figure_with_its_id_its_number_and_whose_it_is():
    lines = K.prompt_lines(FigureSet([_theirs(1), _derived(), _ours()])).splitlines()
    assert lines == ["T1-1 | $22 | yours | I charge $22 a class",
                     "CAP-01 | 432 reformer spots a week | worked out | 12 x 6 a day x 6 days",
                     "PLAN-WEEKS | 6 weeks | our estimate | the length of the plan we propose"]


def test_theirs_come_first_then_derived_reference_and_ours_each_in_the_order_added():
    figs = [_ours("PROP-1", 100, "USD", "proposed price"), _derived("CAP-02", 5, "seats", None, "x"),
            _theirs(2, 12, ""), _reference(), _theirs(1), _derived("CAP-01"), _ours()]
    ids = [line.split(" | ")[0] for line in K.prompt_lines(FigureSet(figs)).splitlines()]
    assert ids == ["T2-1", "T1-1", "CAP-02", "CAP-01", "REF-1", "PROP-1", "PLAN-WEEKS"]
    assert K.prompt_lines(FigureSet(figs)) == K.prompt_lines(FigureSet(figs))      # stable


def test_a_period_is_said_only_when_it_is_a_calendar_word_and_a_note_cannot_break_a_line():
    odd = _derived("CAP-09", 7, "", "as stated", "two | lines" + chr(10) + "of words")
    assert K.prompt_lines(FigureSet([odd])) == "CAP-09 | 7 | worked out | two / lines of words"
    assert "432 reformer spots a week" in K.prompt_lines(FigureSet([_derived()]))
    long_quote = " ".join(["word"] * 60)
    note = K.prompt_lines(FigureSet([_theirs(1, quote=long_quote)])).split(" | ")[3]
    assert len(note) <= K.PROMPT_NOTE_CHARS + 1 and note.endswith(chr(0x2026)) and not note.startswith(" ")


def test_an_empty_set_is_none():
    assert K.prompt_lines(FigureSet()) == "none"


def test_the_list_is_bounded_and_what_is_left_out_is_theirs_and_derived(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "PROMPT_FIGURE_LINES", 12)
    figs = ([_theirs(n, n) for n in range(1, 8)] + [_derived(f"CAP-{n:02d}", n) for n in range(1, 6)]
            + [_ours(f"PROP-{n}", n, "USD") for n in range(1, 6)])
    lines = K.prompt_lines(FigureSet(figs)).splitlines()
    assert len(lines) == 12
    # all five proposals stay; the room left is shared by derived and theirs, the earliest of each
    assert [l.split(" | ")[0] for l in lines[:-1]] == (["T1-1", "T2-1", "T3-1", "CAP-01", "CAP-02", "CAP-03"]
                                                       + [f"PROP-{n}" for n in range(1, 6)])
    assert lines[-1] == ("... and 6 more figures exist but are not listed here (4 yours, 2 worked out); "
                         "write only the numbers listed above")
    monkeypatch.setattr(settings, "PROMPT_FIGURE_LINES", 17)          # exactly as many as there are: no summary
    assert len(K.prompt_lines(FigureSet(figs)).splitlines()) == 17
    assert "more figures" not in K.prompt_lines(FigureSet(figs))


def test_eighty_of_theirs_never_push_out_the_move_or_the_plans_length(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "PROMPT_FIGURE_LINES", 60)
    ours = K.move_figures(MOVE) + [K.plan_weeks_figure(6)]            # MOVE, PROP-1, PLAN-WEEKS
    assert [f.id for f in ours] == ["MOVE", "PROP-1", "PLAN-WEEKS"]
    lines = K.prompt_lines(FigureSet([_theirs(n, n) for n in range(1, 81)] + ours)).splitlines()
    ids = [l.split(" | ")[0] for l in lines]
    assert len(lines) == 60
    assert ids[-4:-1] == ["MOVE", "PROP-1", "PLAN-WEEKS"]
    assert ids[:-4] == [f"T{n}-1" for n in range(1, 57)]             # the 56 earliest answers of theirs
    assert lines[-1] == ("... and 24 more figures exist but are not listed here (24 yours); "
                         "write only the numbers listed above")
    # and with derived figures in the mix, the proposals still stay
    mixed = [_theirs(n, n) for n in range(1, 81)] + [_derived(f"CAP-{n:02d}", n) for n in range(1, 41)] + ours
    lines = K.prompt_lines(FigureSet(mixed)).splitlines()
    ids = [l.split(" | ")[0] for l in lines]
    assert len(lines) == 60 and {"MOVE", "PROP-1", "PLAN-WEEKS"} <= set(ids)
    assert sum(i.startswith("T") for i in ids) == 28 and sum(i.startswith("CAP") for i in ids) == 28


def test_more_proposals_than_half_the_room_still_leave_the_client_some(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "PROMPT_FIGURE_LINES", 10)
    ours = K.move_figures(MOVE) + [K.plan_weeks_figure(6)] + [_ours(f"PT-{n:02d}", n) for n in range(1, 8)]
    ids = [l.split(" | ")[0] for l in K.prompt_lines(FigureSet([_theirs(n, n) for n in range(1, 21)] + ours)).splitlines()]
    assert len(ids) == 10
    assert ids[-5:-1] == ["MOVE", "PROP-1", "PLAN-WEEKS", "PT-01"]    # the plan's own figures first, then the rest
    assert ids[:-5] == [f"T{n}-1" for n in range(1, 6)]               # budget 9: four proposals, five of theirs


def _theirs_id(id: str, value=22) -> Figure:
    from app.figures.model import TheirsSource
    return Figure(id, Decimal(value), "", None, "theirs", TheirsSource(None, None, "words", None, None), 0)


def test_when_theirs_are_cut_the_files_cells_go_first_then_the_latest_interview_turns(monkeypatch):
    from app.config import settings
    form = [_theirs_id("F-business_description-1", 5), _theirs_id("F-main_problem-1", 6)]
    turns = [_theirs_id(f"T{n}-1", n) for n in range(1, 9)]
    files = [_theirs_id(f"E{n}-1", 100 + n) for n in range(1, 6)]
    # the set holds the interview first, then the form, then the files, as the case file builds it
    figs = FigureSet(turns + form + files + [_ours()])

    def ids(limit):
        monkeypatch.setattr(settings, "PROMPT_FIGURE_LINES", limit)
        return [l.split(" | ")[0] for l in K.prompt_lines(figs).splitlines()]

    # room for ten of theirs: the form and every turn; the five cells of the files are cut
    got = ids(12)
    assert got[:-1] == [f"T{n}-1" for n in range(1, 9)] + ["F-business_description-1", "F-main_problem-1", "PLAN-WEEKS"]
    assert got[-1].startswith("... and 5 more figures exist")
    # room for six: the form stays, the latest turns go, last first, and the files were already gone
    got = ids(8)
    assert got[:-1] == ["T1-1", "T2-1", "T3-1", "T4-1", "F-business_description-1", "F-main_problem-1", "PLAN-WEEKS"]
    # room for twelve: the form, every turn, and the first two cells of the files
    got = ids(14)
    assert got[:-1] == ([f"T{n}-1" for n in range(1, 9)] + ["F-business_description-1", "F-main_problem-1"]
                        + ["E1-1", "E2-1", "PLAN-WEEKS"])


def test_the_roadmaps_phase_lengths_stay_at_the_default_budget(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "PROMPT_FIGURE_LINES", 60)
    phases = [Figure(K.phase_weeks_id(n), Decimal(2), "week", None, "ours", Proposal(note="a phase"), 0)
              for n in range(1, 7)]
    plan = [K.plan_weeks_figure(12), Figure(K.PLAN_PHASES_ID, Decimal(6), "phases", None, "ours", Proposal(note="n"), 0)]
    ids = [l.split(" | ")[0] for l in K.prompt_lines(
        FigureSet([_theirs(n, n) for n in range(1, 90)] + plan + phases)).splitlines()]
    assert len(ids) == 60 and {"PLAN-WEEKS", "PLAN-PHASES", *(K.phase_weeks_id(n) for n in range(1, 7))} <= set(ids)


def test_derived_lends_its_room_to_theirs_and_theirs_to_derived(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "PROMPT_FIGURE_LINES", 20)
    few_derived = [_theirs(n, n) for n in range(1, 31)] + [_derived(f"CAP-{n:02d}", n) for n in range(1, 4)]
    ids = [l.split(" | ")[0] for l in K.prompt_lines(FigureSet(few_derived + [_ours()])).splitlines()]
    assert sum(i.startswith("CAP") for i in ids) == 3 and sum(i.startswith("T") for i in ids) == 15
    few_theirs = [_theirs(n, n) for n in range(1, 4)] + [_derived(f"CAP-{n:02d}", n) for n in range(1, 31)]
    ids = [l.split(" | ")[0] for l in K.prompt_lines(FigureSet(few_theirs + [_ours()])).splitlines()]
    assert sum(i.startswith("T") for i in ids) == 3 and sum(i.startswith("CAP") for i in ids) == 15
    assert "PLAN-WEEKS" in ids and ids[-1].startswith("...")


def test_the_bound_is_a_setting_held_between_ten_and_two_hundred(monkeypatch):
    from app import config
    from app.config import settings
    assert 10 <= settings.PROMPT_FIGURE_LINES <= 200
    for given, held in (("5", 10), ("60", 60), ("5000", 200), ("many", 60)):
        monkeypatch.setenv("PROMPT_FIGURE_LINES", given)
        assert config._env_int_within("PROMPT_FIGURE_LINES", 60, 10, 200) == held


def test_a_request_lists_its_own_figures_by_the_ids_it_can_be_cited_with():
    req = _req(ops_numbers_json=_pairs(("What do you charge?", "$22 a class")),
               capacity_json=json.dumps(PICTURE), answer_json=json.dumps({"headline": "x", "move": MOVE}))
    lines = K.prompt_lines(K.known_for(req)).splitlines()
    assert lines[0] == "T1-1 | $22 | yours | $22 a class"
    assert "CAP-05 | 144 reformer spots a week | worked out | 12 x 2 x 6 days" in lines
    assert "MOVE | ~$45,000 a year | our estimate | moving 6pm and 7pm to $28" in lines
    assert lines[-1].startswith("PROP-1 | $28 | our estimate")


# -- the prompts carry it ----------------------------------------------------------------

#: The prompts that write prose for a client. The case file and interview prompts read
#: the client's own answers and carry no block.
FIGURE_PROMPTS = ("answer.j2", "roadmap.j2", "decompose.j2", "blueprint.j2", "technical_plan.j2", "playbook.j2",
                  "screens_plan.j2", "screen.j2")
NO_BLOCK_PROMPTS = ("casefile.j2", "interview.j2")
#: The prompts whose reply the stage binds (`bind` resolves a {{F:id}} token): the answer, the roadmap, and the
#: screens plan (captions and story). The others' replies are printed as written, so a token there would reach
#: the client as {{F:CF-04}}; their prompts must not teach it.
TOKEN_PROMPTS = ("answer.j2", "roadmap.j2", "screens_plan.j2")
TOKEN = "{% raw %}{{F:id}}{% endraw %}"


def _template(name: str) -> str:
    from pathlib import Path
    return (Path(__file__).resolve().parents[2] / "app" / "prompts" / name).read_text(encoding="utf-8")


def test_each_prompt_that_writes_for_a_client_has_the_block_and_the_rule():
    for name in FIGURE_PROMPTS:
        text = _template(name)
        assert "FIGURES YOU MAY USE" in text and "{{ figures_block" in text, name
        assert "exactly as listed" in text, name
        assert "never \"1 of" in text or "do not round it" in text, name
        assert (TOKEN in text) == (name in TOKEN_PROMPTS), name
    for name in NO_BLOCK_PROMPTS:
        assert "figures_block" not in _template(name), name


class _Stop(Exception):
    """Raised by a recording render, so no model is asked."""


def _recording(monkeypatch, module, attr="render"):
    """Make `module.<attr>` render the real template, keep the text, and stop."""
    seen = []
    real = getattr(module, attr)

    real = getattr(real, "real", real)           # a render already recorded once

    def record(name, **kw):
        seen.append((name, real(name, **kw)))
        raise _Stop

    record.real = real
    monkeypatch.setattr(module, attr, record)
    return seen


def _stored_row(**fields):
    import os
    from app.database import Base, SessionLocal, engine
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    row = _req(owner_email="owner@example.com", public_id=f"halo{os.urandom(4).hex()}", **fields)
    db.add(row)
    db.commit()
    return db, row.id


def _full_row(**more):
    return _stored_row(
        ops_numbers_json=_pairs(("What do you charge?", "$22 a class")), capacity_json=json.dumps(PICTURE),
        answer_json=json.dumps({"headline": "x", "move": MOVE}), **more)


def _shows(text: str) -> None:
    assert "FIGURES YOU MAY USE" in text and "{{ figures_block }}" not in text
    assert "T1-1 | $22 | yours | $22 a class" in text
    assert "CAP-05 | 144 reformer spots a week | worked out" in text


def test_the_answer_prompt_lists_the_figures_it_may_use(monkeypatch):
    from app.pipeline import answer
    seen = []

    def chat(model, messages, **kw):
        seen.append(messages[0]["content"])
        return {"choices": [{"message": {"content": json.dumps({"headline": "You're full."})}}], "usage": {}}

    monkeypatch.setattr("app.ai.provider.chat", chat)
    db, rid = _full_row()
    answer.write(db, rid, {"consulting_summary": "Fill the quiet hours."})
    _shows(seen[0])
    assert "MOVE |" not in seen[0]          # the answer writes its own move: the old one vouches for nothing
    db.close()


def test_the_roadmap_prompt_lists_the_figures_it_may_use(monkeypatch):
    import pytest
    from app.pipeline import action_plan
    from app.pipeline.failure import StageFailed
    seen = _recording(monkeypatch, action_plan)
    db, rid = _full_row()
    with pytest.raises(StageFailed):                  # the stage stops where the recording render does
        action_plan.write(db, rid)
    assert seen and seen[0][0] == "roadmap.j2"
    _shows(seen[0][1])
    assert "MOVE | ~$45,000 a year | our estimate" in seen[0][1]       # the answer's move is known to the roadmap
    db.close()


def test_the_decomposition_blueprint_technical_plan_and_playbook_prompts_list_the_figures(monkeypatch):
    import pytest
    from app.figures.model import _APPROVAL_PROPOSED
    from app.pipeline import blueprint, decompose, playbook
    from app.pipeline.failure import StageFailed
    db, rid = _full_row()
    req = db.get(Request, rid)
    req.registry_json = json.dumps({"claims": [
        {"id": "PT-09", "value": 0.7, "unit": "%", "provenance": "consultant_proposed",
         "approval_status": _APPROVAL_PROPOSED, "text": "an old threshold"}]})
    db.commit()
    nothing = {"modules": [], "business_case": {}, "registry": {}}

    seen = _recording(monkeypatch, decompose)
    with pytest.raises(StageFailed):
        decompose.decompose_business(db, rid, {}, {}, {})
    assert seen[0][0] == "decompose.j2"
    _shows(seen[0][1])
    assert "PT-09" not in seen[0][1]        # the registry is rebuilt from this decomposition

    seen = _recording(monkeypatch, blueprint)
    with pytest.raises(_Stop):
        blueprint.write_blueprint(db, rid, {}, {}, {}, nothing)
    assert seen[0][0] == "blueprint.j2"
    _shows(seen[0][1])
    assert "PT-09 | 70% | our estimate" in seen[0][1]                 # the registry the documents are built on

    seen = _recording(monkeypatch, blueprint)
    with pytest.raises(_Stop):
        blueprint.write_technical_plan(db, rid, {}, {}, nothing)
    assert seen[0][0] == "technical_plan.j2"
    _shows(seen[0][1])

    seen = _recording(monkeypatch, playbook)
    with pytest.raises(StageFailed):
        playbook.write_playbook(db, rid, {}, nothing)
    assert seen[0][0] == "playbook.j2"
    _shows(seen[0][1])
    db.close()


def test_the_screen_prompts_list_the_figures(monkeypatch):
    import pytest
    from app.screens import generate
    db, rid = _full_row()
    inputs = generate._inputs(db.get(Request, rid))
    assert inputs["figures_block"] == K.prompt_lines(inputs["known"])

    seen = _recording(monkeypatch, generate, "render_prompt")
    with pytest.raises(_Stop):
        generate._plan(db, rid, inputs)
    assert seen[0][0] == "screens_plan.j2"
    _shows(seen[0][1])

    plan = {"product": {"name": "Halo", "tagline": "studio", "workspace": "Halo", "signed_in": "R. H.",
                        "date_line": "Monday"}, "nav": [{"items": [{"label": "Today"}]}], "cast": []}
    screen = {"id": "today", "title": "Today", "caption": "c", "brief": "b", "blocks": ["kpis"]}
    seen = _recording(monkeypatch, generate, "render_prompt")
    with pytest.raises(_Stop):
        generate._draw(inputs, plan, screen)
    assert seen[0][0] == "screen.j2"
    _shows(seen[0][1])
    assert "$20,000" in seen[0][1] and "$18,400" not in seen[0][1]       # the block guide's example
    db.close()


def test_the_roadmap_prompt_says_the_plan_length_is_a_ceiling_and_when_holds_only_weeks(monkeypatch):
    import pytest
    from app.config import settings
    from app.pipeline import action_plan
    from app.pipeline.failure import StageFailed
    answer = {"headline": "x", "action": {"weeks": 6, "name": "pricing pilot", "figure": as_json(K.plan_weeks_figure(6))}}

    seen = _recording(monkeypatch, action_plan)
    db, rid = _stored_row(ops_numbers_json=_pairs(("What do you charge?", "$22 a class")), answer_json=json.dumps(answer))
    with pytest.raises(StageFailed):
        action_plan.write(db, rid)
    text = seen[0][1]
    assert "PLAN-WEEKS | 6 weeks | our estimate" in text                       # the figure is listed ...
    assert "THE PLAN IS 6 WEEKS LONG (PLAN-WEEKS in the list above): that is a ceiling." in text
    assert "none runs past week 6" in text and "a phase that does is refused" in text
    assert "holds week positions only: no money, no percent, no other number" in text
    db.close()

    seen = _recording(monkeypatch, action_plan)               # ... and with no plan length proposed, the longest plan
    db, rid = _stored_row(ops_numbers_json=_pairs(("What do you charge?", "$22 a class")))
    with pytest.raises(StageFailed):
        action_plan.write(db, rid)
    assert f"NO PLAN RUNS LONGER THAN {settings.PLAN_WEEKS_MAX} WEEKS: that is a ceiling." in seen[0][1]
    assert "PLAN-WEEKS |" not in seen[0][1]
    db.close()


# -- the analysis, decision and diagnosis prompts carry it too: their replies are bound ------

STAGE_PROMPTS = ("analyze.j2", "decide.j2", "diagnose.j2", "test_hypothesis.j2", "challenge.j2")


def test_the_prompts_whose_replies_are_bound_have_the_block_and_teach_the_token():
    for name in STAGE_PROMPTS:
        text = _template(name)
        assert "FIGURES YOU MAY USE" in text and "{{ figures_block }}" in text, name
        assert "exactly as listed" in text and TOKEN in text and "never \"1 of" in text, name


def _stage_model(monkeypatch, replies: dict) -> list[str]:
    """The model answers a prompt from the reply whose key it starts with; returns the prompts sent."""
    seen: list[str] = []

    def chat(model, messages, **kw):
        prompt = messages[0]["content"]
        seen.append(prompt)
        for start, reply in replies.items():
            if prompt.startswith(start):
                return {"choices": [{"message": {"content": json.dumps(reply)}}], "usage": {}}
        raise AssertionError("no reply for: " + prompt[:60])

    monkeypatch.setattr("app.ai.provider.chat", chat)
    return seen


def test_the_analysis_prompt_lists_their_figures_and_only_theirs(monkeypatch):
    from app.pipeline import analyze
    seen = _stage_model(monkeypatch, {"You are a senior business analyst": {
        "business_model": "Appointments", "target_customer_profile": "Regulars.", "pain_points": ["Full evenings."],
        "growth_opportunity": "Fill the mornings."}})
    db, rid = _full_row()
    analyze.analyze_business(db, rid)
    assert "FIGURES YOU MAY USE" in seen[0] and "{{ figures_block }}" not in seen[0]
    assert "T1-1 | $22 | yours | $22 a class" in seen[0]
    assert "CAP-05" not in seen[0]            # the week is read after the analysis, as the check knows
    db.close()


def test_the_decision_prompt_lists_their_figures_and_their_week(monkeypatch):
    from app.pipeline import decide
    seen = _stage_model(monkeypatch, {"You are the partner who signs": {
        "intervention_kind": "software", "consulting_summary": "Fill the quiet hours."}})
    db, rid = _full_row()
    decide.decide(db, rid, {})
    _shows(seen[0])
    assert "MOVE |" not in seen[0]            # the answer is written after the decision
    db.close()


def test_the_diagnosis_and_its_two_reviewers_list_the_figures_the_check_reads(monkeypatch):
    from app.pipeline import diagnose
    hypotheses = [{"id": f"H{n}", "statement": s, "area": "capacity", "software_can_fix": True,
                   "would_support": "a full week", "would_refute": "an empty week", "cites": [], "from_owner": False}
                  for n, s in enumerate(("Evenings are full.", "Mornings are empty.", "Prices are too low."), 1)]
    seen = _stage_model(monkeypatch, {
        "You are a diagnostic consultant": {"hypotheses": hypotheses},
        "You are testing one hypothesis": {"verdict": "supported", "because": "The evenings are full.", "cites": []},
        "You are a skeptical partner": {"kills": False, "because": "It held.", "weakness": ""}})
    db, rid = _full_row()
    diagnose.diagnose(db, rid, {})
    kinds = {"You are a diagnostic consultant": 0, "You are testing one hypothesis": 0, "You are a skeptical partner": 0}
    for prompt in seen:
        kinds[next(k for k in kinds if prompt.startswith(k))] += 1
        _shows(prompt)
    assert kinds["You are a diagnostic consultant"] == 1 and kinds["You are testing one hypothesis"] == 3
    assert kinds["You are a skeptical partner"] == 2
    db.close()


# -- the review's wording rulings ----------------------------------------------------------

BOUND_WITH_CLAIMS = ("answer.j2", "roadmap.j2", "screens_plan.j2", "diagnose.j2", "test_hypothesis.j2", "challenge.j2",
                     "decide.j2")
PRINT_AS_WRITTEN = ("decompose.j2", "blueprint.j2", "technical_plan.j2", "playbook.j2", "pilot_sop.j2", "journey.j2",
                    "governance.j2", "procedures.j2", "checklists.j2", "organization.j2", "module_spec.j2",
                    "tech_spec.j2", "plan.j2")


def test_a_prompt_with_a_claims_list_and_a_figures_list_says_which_ids_go_where():
    for name in BOUND_WITH_CLAIMS:
        text = _template(name)
        assert "never a claim id" in text, name
        assert "claim ids" in text.lower() or "claim id" in text, name
    answer = _template("answer.j2")
    assert "one of the claims above, by its claim id" in answer and "one of the figures above, by id" not in answer
    assert "CLAIM ids (CF-, CE-, CAP-)" in _template("diagnose.j2") and "CLAIM ids" in _template("roadmap.j2")


def test_every_prompt_whose_reply_prints_as_written_has_the_block_and_never_teaches_the_token():
    for name in PRINT_AS_WRITTEN:
        text = _template(name)
        assert "FIGURES YOU MAY USE" in text and '{{ figures_block | default("none") }}' in text, name
        assert "exactly as listed" in text and "{{F:" not in text, name
        if name not in ("decompose.j2", "blueprint.j2", "technical_plan.j2", "playbook.j2"):
            assert "say anything else in words" in text, name


def test_the_decomposition_prompt_separates_the_owners_numbers_from_ours():
    text = _template("decompose.j2")
    assert 'tagged "yours"' in text and '"our estimate" or "reference"' in text
    assert 'never close a calculation with "by your own figures" when it rests on one' in text


def test_the_playbook_asks_for_week_positions_and_no_lengths_of_time():
    text = _template("playbook.j2")
    assert "30 days" not in text.lower() and "30 DAYS" not in text
    assert '"week 1", "weeks 2 to 4"' in text and "never a length of time" in text


def test_the_roadmap_prompt_reconciles_three_to_six_phases_with_a_short_plan():
    text = _template("roadmap.j2")
    assert "phases may share a week position and there are never more phases than weeks" in text
    assert "the plan length is the ceiling" in text


def test_the_hypothesis_test_shows_its_steps_with_listed_numbers_and_says_the_rest_in_words():
    text = _template("test_hypothesis.j2")
    assert "show your steps in one line using only the numbers listed above" in text
    assert "is said in words" in text and "show it in one line, and cite" not in text


def _by_template(monkeypatch, module, replies: dict) -> list:
    """`module.render` renders the real template and remembers it; the model answers each prompt from the
    reply for its template (an error is raised, so a stage that tolerates it goes on). Returns the
    (template, prompt) pairs in call order."""
    import threading
    seen, names, lock = [], {}, threading.Lock()
    real = getattr(module, "render")
    real = getattr(real, "real", real)

    def render_(name, **kw):
        text = real(name, **kw)
        with lock:
            seen.append((name, text))
            names[text] = name
        return text

    def chat(model, messages, **kw):
        reply = replies[names[messages[0]["content"]]]
        return {"choices": [{"message": {"content": json.dumps(reply)}}], "usage": {}}

    render_.real = real
    monkeypatch.setattr(module, "render", render_)
    monkeypatch.setattr("app.ai.provider.chat", chat)
    return seen


def _has_the_block_and_no_token(seen: list, wanted: set) -> None:
    got = {name for name, _ in seen}
    assert wanted <= got, (wanted, got)
    for name, text in seen:
        if name in wanted:
            _shows(text)
            assert "{{F:" not in text and "{{ figures_block" not in text, name


def test_the_module_calls_and_the_plan_prompt_list_the_figures(monkeypatch):
    from app.pipeline import decompose, plan
    two = {"modules": [{"id": "m0", "name": "Module 0", "purpose": "Book classes"},
                       {"id": "m1", "name": "Module 1", "purpose": "Take payment"}], "business_case": {}}
    seen = _by_template(monkeypatch, decompose, {"decompose.j2": two, "module_spec.j2": {"features": []},
                                                 "tech_spec.j2": {"data_model": []}})
    db, rid = _full_row()
    try:
        decompose.decompose_business(db, rid, {}, {}, {})
    except Exception:
        pass                      # what the stage makes of these replies is not this test's business
    _has_the_block_and_no_token(seen, {"decompose.j2", "module_spec.j2", "tech_spec.j2"})
    assert [n for n, _ in seen].count("module_spec.j2") == 2 and [n for n, _ in seen].count("tech_spec.j2") == 2
    db.close()

    seen = _by_template(monkeypatch, plan, {"plan.j2": {"concept_name": "Halo", "roles": []}})
    db, rid = _full_row()
    try:
        plan.plan_integration(db, rid, {"consulting_summary": "Fill the quiet hours."})
    except Exception:
        pass
    _has_the_block_and_no_token(seen, {"plan.j2"})
    db.close()


def test_the_consultancy_layers_prompts_list_the_figures(monkeypatch):
    from app.pipeline import extras
    seen = _by_template(monkeypatch, extras, {n: {} for n in (
        "pilot_sop.j2", "journey.j2", "governance.j2", "procedures.j2", "checklists.j2", "organization.j2")})
    db, rid = _full_row()
    decomposition = {"modules": [{"id": "m0", "name": "Module 0", "purpose": "Book classes", "spec": {}}],
                     "business_case": {"pilot_gate": {"duration": "4 weeks"}}, "registry": {}}
    try:
        extras.build_extras(db, rid, {}, decomposition)
    except Exception:
        pass
    _has_the_block_and_no_token(seen, {"pilot_sop.j2", "journey.j2", "governance.j2", "procedures.j2",
                                       "checklists.j2", "organization.j2"})
    db.close()
