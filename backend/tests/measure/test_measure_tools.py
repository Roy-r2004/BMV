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
codegen_cost = _load("codegen_cost")


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


# --- analyse.run_row --------------------------------------------------------
#
# Every defect this tool has shipped has been one key in this dict read from a
# record nothing writes. `gate_issues` went four trios that way; `viewable` went
# every trio, and duo 1 filed `viewable: None` on two runs that shipped `ready`
# as an unexplained pipeline defect. The row was unreachable by a test until it
# was lifted out of the query loop.


def test_viewable_is_derived_from_status_not_read_from_a_key_nobody_writes() -> None:
    """`finalize` keeps `viewable` as a local and publishes `status` and `url`.

    Reading `preview_app["viewable"]` therefore returns `None` for every run
    that has ever existed — including the two that shipped.
    """

    ready = analyse.run_row({"preview_app": {"status": "ready", "url": "/x/95/"}})
    failed = analyse.run_row({"preview_app": {"status": "failed", "url": None}})

    assert ready["viewable"] is True
    assert failed["viewable"] is False


def test_a_run_that_stored_no_preview_app_reports_viewable_as_unknown() -> None:
    """Requests 92 and 94 stored nothing at all. `False` would say the pipeline
    decided not to serve; the truth is that it never got as far as deciding."""

    assert analyse.run_row({})["viewable"] is None
    assert analyse.run_row({"preview_app": {}})["viewable"] is None


def test_the_withheld_reason_is_read_from_the_record() -> None:
    row = analyse.run_row(
        {"preview_app": {"status": "failed", "withheld_reason": "quality_gate_failed"}}
    )

    assert row["withheld_reason"] == "quality_gate_failed"
    assert row["viewable"] is False


# --- codegen_cost -----------------------------------------------------------
#
# The `codegen` stage total is the p50 term (315 s / 24 calls on 95, 436.9 s /
# 33 on 96) and had never been decomposed. Fixtures below are request 95's real
# row shape and timings, because the trap here is the same one appspec had: the
# obvious bucket is not the expensive one.


def _usage(
    request_id: int,
    *,
    stage: str,
    writer: str | None,
    ends_at: float,
    latency_ms: int,
    attempt: int = 1,
    usable: bool | None = None,
) -> dict:
    return {
        "request_id": request_id,
        "stage": stage,
        "writer": writer,
        "model": "google/gemini-2.5-flash",
        "attempt": attempt,
        "latency_ms": latency_ms,
        "success": True,
        "usable": usable,
        "output_chars": 0,
        "ts": ends_at,
    }


def _request_95_shape() -> list[dict]:
    """Request 95, to the second, from `ai_usage_events`.

    t=0 is 17:19:49, when the plan phase started on the pipeline's second
    attempt. The three unscoped calls that follow are `build_experience_plan`
    and `validate_and_expand_plan`; the fourth is `build_design_manifest`. The
    architect call lands at t=136 and every scoped codegen writer after it.
    """

    return [
        _usage(95, stage="appspec", writer="authoring", ends_at=-36.0, latency_ms=29503),
        _usage(95, stage="codegen", writer=None, ends_at=56.0, latency_ms=55983),
        _usage(95, stage="codegen", writer=None, ends_at=91.7, latency_ms=35698),
        _usage(95, stage="codegen", writer=None, ends_at=125.9, latency_ms=34158),
        _usage(95, stage="codegen", writer=None, ends_at=136.3, latency_ms=5837),
        _usage(
            95,
            stage="architect",
            writer="architect:google/gemini-2.5-flash",
            ends_at=159.5,
            latency_ms=23095,
        ),
        _usage(95, stage="codegen", writer="slot_fill", ends_at=169.2, latency_ms=9861,
               usable=False),
        _usage(95, stage="codegen", writer="slot_fill", ends_at=180.0, latency_ms=6710,
               attempt=2, usable=False),
        _usage(95, stage="codegen", writer="utility_content", ends_at=171.2,
               latency_ms=2241, usable=True),
    ]


def test_the_codegen_stage_total_is_not_all_codegen() -> None:
    """41 % of `codegen`'s AI time on duo 1 is not a codegen writer.

    `stage` falls back to the run *purpose* for a call made outside any
    `ai_call` scope, and `generate_preview_app` runs the whole preview pipeline
    under `purpose="codegen"`. The plan phase's planner, validator and design
    manifest have no scope, so the stage total claims them. Folding them into a
    writer would have reproduced exactly the appspec mistake — bounding the
    loop that looked expensive rather than the one that was.
    """

    report = codegen_cost.summarize(_request_95_shape())

    writers = report["per_writer"]
    assert codegen_cost.UNATTRIBUTED_PRE in writers
    assert writers[codegen_cost.UNATTRIBUTED_PRE]["calls"] == 4
    # 55.983 + 35.698 + 34.158 + 5.837
    assert writers[codegen_cost.UNATTRIBUTED_PRE]["seconds"] == pytest.approx(131.676)
    assert report["unattributed_seconds"] == pytest.approx(131.676)
    # …and it must not have been merged into a real writer.
    assert writers["slot_fill"]["calls"] == 2


def test_the_architect_call_is_the_boundary_and_it_is_the_calls_start() -> None:
    """The split is `began < architect_start`, not `ended < architect_end`.

    Request 95's design-manifest call ends 23.2 s *after* the architect call
    ends, because they do not overlap in the way an end-timestamp comparison
    implies. Comparing ends puts a plan-phase call on the codegen side.
    """

    rows = _request_95_shape()
    starts = codegen_cost.architect_boundaries(rows)
    assert starts[95] == pytest.approx(136.405)

    manifest = rows[4]
    assert manifest["ts"] == pytest.approx(136.3)
    assert codegen_cost.writer_of(manifest, starts[95]) == codegen_cost.UNATTRIBUTED_PRE


def test_a_run_with_no_architect_row_refuses_to_place_its_unscoped_calls() -> None:
    """Requests 92 and 94 never reached the architect. A tool that defaults the
    boundary to zero would report every unscoped call as post-architect and
    invent a codegen cost for a run that never generated code."""

    rows = [
        _usage(94, stage="codegen", writer=None, ends_at=40.0, latency_ms=40000),
    ]
    report = codegen_cost.summarize(rows)

    assert codegen_cost.UNATTRIBUTED_UNKNOWN in report["per_writer"]
    assert codegen_cost.UNATTRIBUTED_POST not in report["per_writer"]
    assert report["unattributed_seconds"] == pytest.approx(40.0)


def test_discarded_slot_fill_spend_is_counted_separately_from_re_asks() -> None:
    """`usable = false` is time bought and thrown away, and on duo 1 it is 28 of
    `slot_fill`'s 40 calls. A re-ask and a discard are different facts: the
    second attempt of a pair can itself be discarded, which is what request 96
    did ten times."""

    report = codegen_cost.summarize(_request_95_shape())
    slot_fill = report["per_writer"]["slot_fill"]

    assert slot_fill["unusable"] == 2
    assert slot_fill["unusable_seconds"] == pytest.approx(16.571)
    assert slot_fill["retries"] == 1
    assert slot_fill["retry_seconds"] == pytest.approx(6.710)
    assert report["per_writer"]["utility_content"]["unusable_seconds"] == 0.0


def test_other_stages_do_not_leak_into_the_codegen_total() -> None:
    """The appspec row in the fixture is 29.5 s and must not be billed here —
    but it still has to be *read*, because the architect boundary comes from a
    row this filter would otherwise drop."""

    report = codegen_cost.summarize(_request_95_shape())

    assert report["calls"] == 7
    assert report["seconds"] == pytest.approx(150.488)
    assert "authoring" not in report["per_writer"]
