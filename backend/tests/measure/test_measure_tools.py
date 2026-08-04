"""The measurement tools get tests, because both have shipped a silent defect.

`analyse.py` read a `preview_app["gate_issues"]` key that nothing ever wrote, so
every evidence table it produced for four trios reported `gate_issues: 0` — the
roadmap's per-code counts had to be grepped out of container logs instead.
`tail.py` hardcoded `RUNS = [74…82]` and skips any run with no stored elapsed, so
asked about trio 7 it printed nothing and said nothing about printing nothing;
pre-flight question 10 went unanswered in the first write-up for that reason
alone.

Neither defect was in the pipeline. Both were in the instrument, and both would
have been caught by the arithmetic being called once from a test. Nothing here
touches a database: `main()` does the SQL and these functions do the sums.

The fixtures are the real shape of requests 92-94, because the thing that misled
me about that trio was reading the raw table and drawing the obvious conclusion
from it.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

MEASURE = Path(__file__).resolve().parents[2] / "scripts" / "measure"


def _load(name: str) -> ModuleType:
    """Import a measurement script by path.

    They are scripts, not a package, and they import `app.…` at module scope
    for a live engine — so `analyse` is loaded here for its pure helpers only.
    """

    spec = importlib.util.spec_from_file_location(f"_measure_{name}", MEASURE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


analyse = _load("analyse")
tail = _load("tail")


def _revision(
    rev_id: int,
    *,
    status: str = "rejected",
    sha: str = "aaa",
    parent: int | None = None,
    issues: list[dict] | None = None,
    terminal: str = "schema_parse_failed",
    is_valid: bool = False,
) -> dict:
    return {
        "id": rev_id,
        "revision": rev_id,
        "status": status,
        "app_spec_sha256": sha,
        "parent_revision_id": parent,
        "deterministic_validation_json": json.dumps(
            {"is_valid": is_valid, "issues": issues or []}
        ),
        "generation_metadata_json": json.dumps({"terminal_reason": terminal}),
    }


def test_no_revisions_is_reported_as_such_not_as_zero_accepted() -> None:
    """Requests 92 and 94 stored no `preview_app` at all. A tool that reports
    `accepted: 0` for "the stage never ran" and for "it ran and failed" has
    merged the two facts this repo keeps rediscovering it needs apart."""

    out = analyse.appspec_health([])
    assert out["revisions"] == 0
    assert "note" in out


def test_revisions_overcount_attempts_because_a_candidate_is_stored_twice() -> None:
    """Request 92's real shape: 8 revisions, 4 distinct candidates.

    A candidate is persisted before and after the graph-repair pass, so a repair
    that changed nothing writes the same `app_spec_sha256` again. Reading
    `revisions` as "attempts" overstates the work by 2x.
    """

    rows = [
        _revision(182, sha="93c3", parent=None),
        _revision(183, sha="0174", parent=182),
        _revision(184, sha="cb92", parent=183),
        _revision(185, sha="cb92", parent=184, terminal="deterministic_validation_failed"),
        _revision(192, sha="6526", parent=None),
        _revision(193, sha="df20", parent=192),
        _revision(194, sha="4e77", parent=None, terminal="pre_graph_repair"),
        _revision(195, sha="4e77", parent=194, terminal="deterministic_validation_failed"),
    ]
    out = analyse.appspec_health(rows)

    assert out["revisions"] == 8
    assert out["distinct_candidates"] == 6
    assert out["accepted"] == 0
    # The number 1.13 exists to move: three authoring calls that started over.
    assert out["fresh_authoring_chains"] == 3


def test_a_bounded_run_authors_once() -> None:
    """What the duo should show after `27b12bf`: one authoring chain, repaired."""

    rows = [
        _revision(200, sha="a1", parent=None),
        _revision(201, sha="a2", parent=200),
        _revision(202, sha="a3", parent=201, status="accepted", is_valid=True),
    ]
    out = analyse.appspec_health(rows)

    assert out["fresh_authoring_chains"] == 1
    assert out["accepted"] == 1
    assert out["final_is_valid"] is True


def test_the_verdict_is_the_final_revision_not_a_count_over_all_of_them() -> None:
    """Counting codes across every revision said `state_ids` dominated trio 7.

    Per final revision, 92, 93 and 94 failed on three different things. A
    superseded revision is history, not a cause — this is the assertion that
    would have stopped me publishing the wrong summary.
    """

    rows = [
        _revision(
            1,
            sha="x1",
            parent=None,
            issues=[
                {
                    "code": "app_spec_schema_parse_failed",
                    "detail": [
                        {"loc": ["pages", 0, "state_ids"], "msg": "too_short"},
                        {"loc": ["pages", 1, "state_ids"], "msg": "too_short"},
                    ],
                }
            ],
        ),
        _revision(
            2,
            sha="x2",
            parent=1,
            terminal="deterministic_validation_failed",
            issues=[
                {"code": "missing_reference"},
                {"code": "page_membership_mismatch"},
                {"code": "page_membership_mismatch"},
            ],
        ),
    ]
    out = analyse.appspec_health(rows)

    assert out["final_revision_id"] == 2
    assert out["final_blocking"] == [
        ("missing_reference", 1),
        ("page_membership_mismatch", 2),
    ]
    # The earlier revision's state_ids failures are not the run's verdict.
    assert not any("state_ids" in path for path, _ in out["final_blocking_paths"])


def test_the_failing_field_paths_come_out_of_the_final_revision() -> None:
    rows = [
        _revision(
            9,
            sha="y1",
            parent=None,
            issues=[
                {
                    "code": "app_spec_schema_parse_failed",
                    "detail": [
                        {"loc": ["actions", 6, "kind"], "msg": "enum"},
                        {"loc": ["actions", 7, "kind"], "msg": "enum"},
                        {"loc": ["pages", 0, "state_ids"], "msg": "too_short"},
                    ],
                }
            ],
        )
    ]
    out = analyse.appspec_health(rows)

    assert out["final_blocking_paths"][0] == ("actions.6.kind", 1)
    assert dict(out["final_blocking_paths"])["pages.0.state_ids"] == 1


def test_terminal_reasons_are_kept_per_revision() -> None:
    rows = [
        _revision(1, sha="a", parent=None, terminal="schema_parse_failed"),
        _revision(2, sha="b", parent=1, terminal="schema_parse_failed"),
        _revision(3, sha="c", parent=2, terminal="deterministic_validation_failed"),
    ]
    out = analyse.appspec_health(rows)

    assert out["terminal_reasons"] == [
        ("deterministic_validation_failed", 1),
        ("schema_parse_failed", 2),
    ]


def test_corrupt_stored_json_does_not_take_the_whole_report_down() -> None:
    """One unreadable revision must not cost the other runs their numbers."""

    rows = [
        {
            "id": 5,
            "revision": 1,
            "status": "rejected",
            "app_spec_sha256": "z",
            "parent_revision_id": None,
            "deterministic_validation_json": "{not json",
            "generation_metadata_json": "{also not json",
        }
    ]
    out = analyse.appspec_health(rows)

    assert out["revisions"] == 1
    assert out["final_blocking"] == []
    assert out["terminal_reasons"] == [("-", 1)]


@pytest.mark.parametrize(
    "argv, expected",
    [
        ([], [74, 75, 76, 77, 78, 79, 80, 81, 82]),
        (["7"], [92, 93, 94]),
        (["2"], [77, 78, 79]),
        (["95", "96"], [95, 96]),
    ],
)
def test_tail_runs_are_selectable(argv: list[str], expected: list[int]) -> None:
    """`tail.py` could only ever be asked about runs 74-82.

    Importable at all only because neither tool parses `sys.argv` at module
    scope any more — under pytest that argv is a list of test paths, which is
    what made both of these unimportable and therefore untested.
    """

    assert tail._runs(argv) == expected


def test_a_void_trio_is_refused_by_both_tools_rather_than_silently_substituted() -> None:
    """Trio 6 is void on credits.

    Absent from the table, `tail.py 6` falls through to "explicit run ids" and
    decomposes request **6** — a real, unrelated run from another week — and
    reports it under the heading the caller asked for. The void trio is
    therefore present and null, not missing.
    """

    with pytest.raises(ValueError):
        tail._runs(["6"])

    with pytest.raises(SystemExit):
        analyse.select_trio(["6"])


def test_an_unknown_trio_key_names_the_ones_that_exist() -> None:
    with pytest.raises(SystemExit) as excinfo:
        analyse.select_trio(["99"])
    assert "known:" in str(excinfo.value)


def test_the_default_trio_is_unchanged_for_a_bare_invocation() -> None:
    """`analyse.py` with no argument has always meant trio 1. Callers depend on
    it, so the argv move must not have quietly changed the default."""

    ids, launch = analyse.select_trio([])
    assert ids == [74, 75, 76]
    assert set(launch) == {74, 75, 76}
