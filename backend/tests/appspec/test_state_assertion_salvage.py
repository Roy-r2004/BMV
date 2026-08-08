"""An assertion naming a state the spec never declared must not cost the run.

Requests 149, 154 and 155 all died here, three of the six occurrences in the
archive and two of session 27's six launches. The shape is always the same — the
model writes

    { "kind": "state", "state_id": null, "description": "The hire booking is confirmed." }

against a page whose only declared state is *"Hire Booking Form Displayed"*. It is
an explicit `null`, not an omission: the model is saying it wants to assert a
state and does not have one.

The repair pass then had no legal move. `app_spec_repair.j2` told it to *"add the
missing `state_id` … (a state on the asserted page), or change its kind"*, and no
state on that page means what the assertion means — while the `missing_reference`
rule three lines below it has always offered the escape that matters, *"declare
the missing object in its top-level collection"*. So the model re-emitted the
identical payload, `_issue_identity_signature` matched its parent, and R2 failed
the run closed. That behaviour is right; it was the instruction that dead-ended.

Two changes, in this order of preference:

1. **The prompt gets the same escape** — declare the state, list it in the page's
   `state_ids`, make it non-initial and reachable. The model is the only thing
   that can write that coherently.
2. **A bounded salvage where the run would otherwise be discarded.** It is
   deliberately not a heal and must never run first: dropping the assertion loses
   a claim, and declaring the state keeps it.

The fixtures are the two rejected AppSpecs verbatim out of
`app_spec_revisions.app_spec_json`, with the validator report that rejected them.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# `sanitize.reference_integrity` reaches back into `app.application.appspec` for
# `canonical_json`, so importing `heal` as the very first thing in a process
# starts that cycle from the wrong end and fails. Production always enters
# through the application package; do the same here.
import app.application.appspec  # noqa: F401  isort:skip
from app.domain.appspec.sanitize.heal import (  # noqa: E402
    drop_unbindable_state_assertions,
    heal_app_spec_payload,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "session27"


def _rejected(request_id: int) -> tuple[dict, dict]:
    data = json.loads(
        (FIXTURES / f"rejected_state_assertion_{request_id}.json").read_text(
            encoding="utf-8"
        )
    )
    return data["app_spec"], data["validation"]


def _state_assertion_issues(validation: dict) -> list[dict]:
    return [
        issue
        for issue in validation["issues"]
        if issue["code"] == "state_assertion_state_required"
    ]


# --------------------------------------------------------------------------- #
# the fixtures are what we think they are


@pytest.mark.parametrize("request_id", [154, 155])
def test_the_fixture_is_the_run_that_died(request_id: int) -> None:
    spec, validation = _rejected(request_id)
    issues = _state_assertion_issues(validation)
    assert issues, "the fixture no longer carries the defect"
    assert len(validation["issues"]) == len(issues), (
        "the fixture has picked up unrelated issues — the salvage is scoped to "
        "this code alone and the test would stop proving that"
    )
    for issue in issues:
        test_index, assertion_index = issue["path"][1], issue["path"][3]
        assertion = spec["acceptance_tests"][test_index]["assertions"][assertion_index]
        assert assertion["kind"] == "state"
        assert assertion.get("state_id") is None


@pytest.mark.parametrize("request_id", [154, 155])
def test_the_state_the_assertion_wants_really_does_not_exist(request_id: int) -> None:
    """The reason a backfill cannot work: it is a missing entity, not a missing field.

    Naming the nearest state on the page would assert something else — 155's page
    has *"booking form displayed"* and the assertion is about *"confirmed"*.
    """
    spec, validation = _rejected(request_id)
    states_by_page: dict[str, list[str]] = {}
    for state in spec["states"]:
        states_by_page.setdefault(state["page_id"], []).append(state["name"].lower())
    for issue in _state_assertion_issues(validation):
        test = spec["acceptance_tests"][issue["path"][1]]
        assertions = test["assertions"]
        index = issue["path"][3]
        page_id = next(
            (
                assertions[i].get("page_id")
                for i in range(index, -1, -1)
                if assertions[i].get("page_id")
            ),
            None,
        )
        wanted = assertions[index]["description"].lower()
        for name in states_by_page.get(page_id or "", []):
            assert name not in wanted, (
                f"{request_id}: state {name!r} would have bound — the fixture no "
                "longer shows a missing entity"
            )


# --------------------------------------------------------------------------- #
# the salvage


@pytest.mark.parametrize(
    "request_id,expected_drops", [(154, 2), (155, 1)]
)
def test_the_salvage_removes_exactly_the_unbindable_assertions(
    request_id: int, expected_drops: int
) -> None:
    spec, validation = _rejected(request_id)
    before = [len(t["assertions"]) for t in spec["acceptance_tests"]]

    salvaged, actions = drop_unbindable_state_assertions(spec, validation)

    assert len(actions) == expected_drops
    after = [len(t["assertions"]) for t in salvaged["acceptance_tests"]]
    assert sum(before) - sum(after) == expected_drops
    assert len(salvaged["acceptance_tests"]) == len(spec["acceptance_tests"])
    # Nothing of the kind survives, and nothing else was touched.
    remaining = [
        assertion
        for test in salvaged["acceptance_tests"]
        for assertion in test["assertions"]
        if assertion.get("kind") == "state" and assertion.get("state_id") is None
    ]
    assert remaining == []
    for key in spec:
        if key == "acceptance_tests":
            continue
        assert salvaged[key] == spec[key], f"{key} was modified"


@pytest.mark.parametrize("request_id", [154, 155])
def test_the_salvaged_spec_actually_validates(request_id: int) -> None:
    """The point of the whole thing: these two runs would have shipped.

    Not a claim about the salvage's inputs — the real validator, over the real
    payload, after the drop. Both specs were one unexpressible sentence away from
    passing, and the pipeline threw the paid run away instead.
    """
    from app.domain.appspec.validation.validate import validate_app_spec
    from app.domain.schemas.app_spec import AppSpec

    spec, validation = _rejected(request_id)
    assert validate_app_spec(AppSpec.model_validate(spec)).issues, (
        "the fixture must fail before the salvage or it proves nothing"
    )

    salvaged, actions = drop_unbindable_state_assertions(spec, validation)
    assert actions

    report = validate_app_spec(AppSpec.model_validate(salvaged))
    assert not report.issues, [(issue.code, issue.message) for issue in report.issues]
    assert report.passed


def test_two_drops_in_one_test_do_not_shift_each_other() -> None:
    """Indices come from the validator and are dropped descending.

    154 drops from two different tests, so it does not prove this on its own;
    ascending removal would take the wrong assertion out of a test with two.
    """
    spec = {
        "acceptance_tests": [
            {
                "id": "TEST-A",
                "assertions": [
                    {"kind": "route", "page_id": "PAGE-A"},
                    {"kind": "state", "state_id": None, "description": "first"},
                    {"kind": "visible", "evidence_id": "EVIDENCE-A"},
                    {"kind": "state", "state_id": None, "description": "second"},
                ],
            }
        ]
    }
    validation = {
        "issues": [
            {
                "code": "state_assertion_state_required",
                "path": ["acceptance_tests", 0, "assertions", 1, "state_id"],
            },
            {
                "code": "state_assertion_state_required",
                "path": ["acceptance_tests", 0, "assertions", 3, "state_id"],
            },
        ]
    }
    salvaged, actions = drop_unbindable_state_assertions(spec, validation)
    assert len(actions) == 2
    kinds = [a["kind"] for a in salvaged["acceptance_tests"][0]["assertions"]]
    assert kinds == ["route", "visible"]


def test_the_last_assertion_in_a_test_is_never_dropped() -> None:
    """`assertions` has `min_length=1`; a spec with nothing else still fails closed."""
    spec = {
        "acceptance_tests": [
            {
                "id": "TEST-ONLY",
                "assertions": [
                    {"kind": "state", "state_id": None, "description": "the only one"}
                ],
            }
        ]
    }
    validation = {
        "issues": [
            {
                "code": "state_assertion_state_required",
                "path": ["acceptance_tests", 0, "assertions", 0, "state_id"],
            }
        ]
    }
    salvaged, actions = drop_unbindable_state_assertions(spec, validation)
    assert actions == []
    assert salvaged == spec


def test_the_salvage_ignores_every_other_code() -> None:
    """Scoped to one code. A `missing_reference` run must reach its own repair."""
    spec, validation = _rejected(155)
    other = {
        "issues": [
            {"code": "missing_reference", "path": ["states", 0, "page_id"]},
            {"code": "page_initial_state_count", "path": ["pages", 0, "state_ids"]},
        ]
    }
    salvaged, actions = drop_unbindable_state_assertions(spec, other)
    assert actions == []
    assert salvaged == spec


def test_a_sibling_assertion_code_is_not_salvage_material() -> None:
    """The path shape is not the filter — the code is.

    `visible_assertion_evidence_required` and `route_assertion_page_required`
    point at the same `acceptance_tests[i].assertions[j]` shape, and both are
    genuinely repairable: the evidence or the page exists and the model only has
    to cite it. Dropping those assertions would delete coverage over a defect the
    repair pass fixes routinely, and the path guard alone cannot tell them apart.
    """
    spec = {
        "acceptance_tests": [
            {
                "id": "TEST-A",
                "assertions": [
                    {"kind": "route", "page_id": None, "description": "on the page"},
                    {"kind": "visible", "evidence_id": None, "description": "it shows"},
                    {"kind": "state", "state_id": "STATE-A", "description": "loaded"},
                ],
            }
        ]
    }
    validation = {
        "issues": [
            {
                "code": "route_assertion_page_required",
                "path": ["acceptance_tests", 0, "assertions", 0, "page_id"],
            },
            {
                "code": "visible_assertion_evidence_required",
                "path": ["acceptance_tests", 0, "assertions", 1, "evidence_id"],
            },
        ]
    }
    salvaged, actions = drop_unbindable_state_assertions(spec, validation)
    assert actions == []
    assert salvaged == spec


# --------------------------------------------------------------------------- #
# ordering: the salvage must not pre-empt the repair that keeps the claim


@pytest.mark.parametrize("request_id", [154, 155])
def test_the_deterministic_heal_pass_leaves_this_code_alone(request_id: int) -> None:
    """The load-bearing ordering test.

    `heal_app_spec_payload` runs *before* the model's repair. If the salvage were
    wired in there it would delete the assertion the model is about to fix
    properly by declaring the missing state — a cheaper answer arriving first and
    winning. It is reachable only from the terminal branch, and this is what says
    so.
    """
    spec, validation = _rejected(request_id)
    healed, actions = heal_app_spec_payload(spec, validation)
    assert not any("state_assertion" in action for action in actions), actions
    assert healed["acceptance_tests"] == spec["acceptance_tests"]
