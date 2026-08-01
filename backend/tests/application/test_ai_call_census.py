"""Phase 0.6 — the arithmetic that sizes the 600 s deadline.

Two things are asserted here and nothing else will do.

1. **Usable is not 200.** A call that returned HTTP 200 carrying JSON no
   extractor could read bought the pipeline nothing, and must not be counted as
   a success. Request 67 recorded two of its three dead fix-agent calls as
   `success = true`; that is what hid roughly three minutes per run for several
   sessions.
2. **p95 is a convolution, not a multiplication.** p95-per-call × call-count
   asks for the probability that every call is simultaneously at its own tail —
   0.05¹⁶ for a sixteen-call run. The census has to answer the question that was
   actually asked: the 95th percentile of the sum.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

from app.application.services.ai_call_census import (  # noqa: E402
    ELECTIVE_STAGES,
    MANDATORY_STAGES,
    CallRecord,
    census_report,
    convolve,
    latency_summary,
    mandatory_floor,
    percentile,
    run_latency_distribution,
    summarize_by,
    unclassified_stages,
    wasted_seconds,
)


def _record(**kwargs) -> CallRecord:
    base = dict(
        request_id=67,
        stage="codegen",
        model="z-ai/glm-5.2",
        latency_ms=20_000,
        success=True,
    )
    base.update(kwargs)
    return CallRecord(**base)


# --------------------------------------------------------------------------
# usable is not 200
# --------------------------------------------------------------------------


def test_a_200_with_unusable_output_is_not_counted_as_a_success() -> None:
    """The defect the roadmap names: transport success masquerading as value."""

    rows = [
        _record(stage="fix_agent", latency_ms=90_000, success=True, usable=False),
        _record(stage="fix_agent", latency_ms=87_000, success=True, usable=False),
        _record(stage="fix_agent", latency_ms=41_000, success=True, usable=True),
    ]

    dead_calls, dead_seconds = wasted_seconds(rows)

    assert dead_calls == 2, "both 200s that produced nothing must be counted"
    assert dead_seconds == pytest.approx(177.0)


def test_a_transport_failure_is_unusable_even_with_no_verdict() -> None:
    """No caller adjudicates a call that never returned; the row still counts."""

    dead_calls, dead_seconds = wasted_seconds(
        [_record(latency_ms=120_000, success=False, usable=None)]
    )

    assert dead_calls == 1
    assert dead_seconds == pytest.approx(120.0)


def test_an_unadjudicated_200_is_not_counted_as_waste() -> None:
    """Rows predating the census have `usable = NULL`.

    Reading NULL as "unusable" would let the report inflate itself with its own
    blind spot — the first census would claim a waste figure it never measured.
    """

    dead_calls, dead_seconds = wasted_seconds(
        [_record(latency_ms=30_000, success=True, usable=None)]
    )

    assert dead_calls == 0
    assert dead_seconds == 0.0


def test_the_report_says_how_many_rows_it_could_not_adjudicate() -> None:
    report = census_report(
        [
            _record(usable=None),
            _record(usable=True),
            _record(request_id=None, usable=True),
        ]
    )

    assert report["rows_unadjudicated"] == 1
    assert report["rows_missing_request_id"] == 1


# --------------------------------------------------------------------------
# percentiles
# --------------------------------------------------------------------------


def test_percentile_interpolates_between_ranks() -> None:
    """Nearest-rank would make p95 of five samples just the maximum."""

    assert percentile([10.0, 20.0, 30.0, 40.0, 50.0], 0.50) == pytest.approx(30.0)
    assert percentile([10.0, 20.0, 30.0, 40.0, 50.0], 0.95) == pytest.approx(48.0)
    assert percentile([10.0, 20.0, 30.0, 40.0, 50.0], 0.95) != 50.0


def test_percentile_of_one_sample_is_that_sample() -> None:
    assert percentile([7.5], 0.95) == pytest.approx(7.5)


def test_percentile_of_nothing_is_zero_not_an_error() -> None:
    assert percentile([], 0.95) == 0.0


def test_percentile_rejects_a_quantile_outside_the_unit_interval() -> None:
    with pytest.raises(ValueError):
        percentile([1.0, 2.0], 95)


def test_latency_summary_reports_seconds_from_milliseconds() -> None:
    summary = latency_summary(
        [_record(latency_ms=1_000), _record(latency_ms=3_000)]
    )

    assert summary.n == 2
    assert summary.mean_s == pytest.approx(2.0)
    assert summary.total_s == pytest.approx(4.0)


def test_summaries_group_by_model_and_by_stage_independently() -> None:
    rows = [
        _record(stage="codegen", model="a", latency_ms=10_000),
        _record(stage="vision", model="a", latency_ms=30_000),
        _record(stage="vision", model="b", latency_ms=50_000),
    ]

    by_model = summarize_by(rows, "model")
    by_stage = summarize_by(rows, "stage")

    assert by_model["a"].n == 2 and by_model["b"].n == 1
    assert by_stage["vision"].n == 2
    assert by_stage["vision"].total_s == pytest.approx(80.0)


# --------------------------------------------------------------------------
# convolution
# --------------------------------------------------------------------------


def test_convolution_sums_two_independent_distributions() -> None:
    """Two fair coins over {1 s, 3 s} give 2 s / 4 s / 6 s at 1/4, 1/2, 1/4."""

    coin = {1: 0.5, 3: 0.5}

    joint = convolve(coin, coin)

    assert joint[2] == pytest.approx(0.25)
    assert joint[4] == pytest.approx(0.50)
    assert joint[6] == pytest.approx(0.25)
    assert sum(joint.values()) == pytest.approx(1.0)


def test_a_run_of_n_identical_calls_sums_to_n_times_the_call() -> None:
    distribution = run_latency_distribution({"codegen": [10.0]}, {"codegen": 4})

    assert distribution.percentile_s(0.50) == pytest.approx(40.0)
    assert distribution.percentile_s(0.95) == pytest.approx(40.0)


def test_the_derived_p95_is_far_below_per_call_p95_times_call_count() -> None:
    """The whole reason the roadmap demands convolution.

    Sixteen calls that are usually 20 s and 15 % of the time 120 s: multiplying
    the per-call p95 by sixteen claims every one of them is simultaneously at
    its tail. The sum's p95 is nowhere near that.
    """

    samples = [20.0] * 17 + [120.0] * 3
    per_call_p95 = percentile(samples, 0.95)

    distribution = run_latency_distribution({"codegen": samples}, {"codegen": 16})
    derived_p95 = distribution.percentile_s(0.95)

    assert per_call_p95 * 16 == pytest.approx(1_920.0), "the naive figure"
    assert derived_p95 < per_call_p95 * 16 / 2
    assert derived_p95 > 16 * 20.0, "the tail must still be above the all-typical case"


def test_convolution_is_not_the_mean_times_the_call_count() -> None:
    samples = [10.0] * 9 + [200.0]
    distribution = run_latency_distribution({"s": samples}, {"s": 10})

    mean_times_n = (sum(samples) / len(samples)) * 10

    assert distribution.mean_s() == pytest.approx(mean_times_n, rel=0.02)
    assert distribution.percentile_s(0.95) > mean_times_n


def test_fixed_overhead_shifts_the_whole_distribution() -> None:
    distribution = run_latency_distribution({"s": [10.0]}, {"s": 2}).shift_s(94.0)

    assert distribution.percentile_s(0.50) == pytest.approx(114.0)


def test_a_stage_with_no_samples_contributes_nothing() -> None:
    distribution = run_latency_distribution({"codegen": [10.0]}, {"codegen": 1, "ghost": 5})

    assert distribution.percentile_s(0.50) == pytest.approx(10.0)


# --------------------------------------------------------------------------
# the mandatory floor
# --------------------------------------------------------------------------


def test_the_floor_counts_only_stages_a_run_cannot_skip() -> None:
    census = {"blueprint": 1, "architect": 1, "codegen": 5, "quality_repair": 7}

    assert mandatory_floor(census) == 7
    assert "quality_repair" not in MANDATORY_STAGES


def test_the_floor_rounds_up_because_half_a_model_call_does_not_exist() -> None:
    assert mandatory_floor({"codegen": 5.5, "architect": 1.0}) == 7


def test_the_floor_of_an_all_elective_census_is_zero() -> None:
    assert mandatory_floor({"vision": 6, "quality_repair": 3}) == 0


def test_the_build_stages_ai_calls_are_elective_because_vite_makes_none() -> None:
    """Running vite is mandatory; every model call under `build` is the fix
    agent, which the deadline may skip. Request 70 spent 477 s there."""

    assert "build" in ELECTIVE_STAGES
    assert "build" not in MANDATORY_STAGES
    assert mandatory_floor({"build": 8, "codegen": 5}) == 5


def test_the_providers_default_purpose_is_never_silently_classified() -> None:
    """`pipeline` is what a call records when the request context never reached
    it. Filing it under either class invents a number."""

    assert unclassified_stages(["pipeline", "codegen", "vision"]) == ["pipeline"]
    assert mandatory_floor({"pipeline": 12, "codegen": 5}) == 5


@pytest.mark.parametrize(
    "stage",
    [
        # explicit `ai_call` stage names
        "architect", "codegen", "seed", "fix_agent", "quality_repair",
        "design_critic", "refine", "vision",
        # progress stage names a call inherits when no scope named one
        "analyze", "blueprint", "appspec", "demo", "critic", "visual_critic",
        "build", "tech", "proposal", "build_plans", "quality_gate",
    ],
)
def test_every_stage_the_pipeline_emits_is_classified(stage: str) -> None:
    """An unclassified stage silently leaves the mandatory floor.

    Both sources of a stage name have to be covered: the `ai_call` scopes and
    `progress.py:_STAGE_ORDER`, which is what a call without a scope inherits.
    """

    assert stage in MANDATORY_STAGES | ELECTIVE_STAGES


def test_the_report_names_the_stages_it_could_not_classify() -> None:
    report = census_report(
        [_record(stage="pipeline"), _record(stage="codegen")]
    )

    assert report["unclassified_stages"] == ["pipeline"]


def test_calls_per_run_ignores_rows_whose_request_id_never_propagated() -> None:
    """A partial numerator over a whole denominator is worse than no number."""

    report = census_report(
        [
            _record(request_id=67, stage="codegen"),
            _record(request_id=67, stage="codegen"),
            _record(request_id=None, stage="codegen"),
            _record(request_id=68, stage="codegen"),
            _record(request_id=68, stage="codegen"),
        ]
    )

    assert report["calls_per_run"]["codegen"]["median"] == pytest.approx(2.0)
    assert report["calls_per_run"]["codegen"]["runs"] == 2


def test_census_report_carries_both_whole_run_and_mandatory_only_tails() -> None:
    rows = [
        _record(request_id=67, stage="codegen", latency_ms=20_000),
        _record(request_id=67, stage="quality_repair", latency_ms=300_000),
        _record(request_id=68, stage="codegen", latency_ms=20_000),
        _record(request_id=68, stage="quality_repair", latency_ms=300_000),
    ]

    report = census_report(rows)

    assert report["run_p95_s"] > report["mandatory_p95_s"]
    assert report["mandatory_p95_s"] == pytest.approx(20.0, abs=1.5)
