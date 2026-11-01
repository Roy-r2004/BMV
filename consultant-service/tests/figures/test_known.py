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
    assert "2 studios" in got["figures"][0]["label"] and len(ids) == 3     # "two studios" is hers too


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
    assert not problems and plan["summary"] == "We do this in 2 phases over 4 weeks."
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
    assert story["needs"] == ["A list of your 12 regulars"]
    assert story["comparison"]["rows"] == [{"label": "Reformers", "cells": ["12", "12"]}]
    assert [p["title"] for p in story["ambition"]["pillars"]] == ["6 a day"]
