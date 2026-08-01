"""Phase 0.6 — per-call latency distribution and the run-level call census.

The roadmap commits to a hard 600 s cap delivered by a request-scoped deadline.
That deadline cannot be sized from a mean: measured p95/p50 on this pipeline is
2.4×, so a budget set from the average either binds on every run or never binds
at all. The number has to come from the distribution of the *sum*, and the sum
of independent per-call latencies is a convolution — not the mean times the call
count, and not the p95 times the call count either.

Why not p95 × N. Taking the 95th percentile of one call and multiplying by the
number of calls asks for the probability that *every* call is simultaneously at
its own p95. For 16 independent calls that is 0.05¹⁶. The convolution says what
is actually being asked: the 95th percentile of the total.

Three things live here, all pure:

* `latency_summary` — p50 / p95 / mean / n over a set of rows, grouped by model
  or by stage.
* `run_latency_distribution` — the discrete convolution over a census, and the
  percentile read off it.
* `mandatory_floor` — how many logical calls a run cannot avoid making, which
  is what turns a ledger claim into an arithmetic one.

Everything takes plain `CallRecord`s so the arithmetic is testable without a
database. `scripts/cli/ai_call_census.py` is the shell that loads them.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

#: Stages the pipeline cannot skip and still produce a site. The deadline in
#: Phase 1.1 may skip an ELECTIVE stage outright; a MANDATORY stage that would
#: cross the deadline falls through to its deterministic default instead. This
#: table is the census's half of that contract — it is what makes "16–17
#: mandatory calls" a number rather than an assertion.
#: Names come from two places and both are covered: the explicit `ai_call`
#: stage, and the progress stage (`progress.py:_STAGE_ORDER`) that a call
#: inherits when no scope named one.
MANDATORY_STAGES: frozenset[str] = frozenset(
    {
        "appspec",
        "appspec_failed",
        "architect",
        "blueprint",
        "codegen",
        "demo",
        "planning",
        "seed",
    }
)

#: Stages a run can lose entirely and still ship something a user can look at.
#:
#: `build` is here on purpose and it is the least obvious entry. Running vite is
#: mandatory, but vite is deterministic and makes no model call — every AI call
#: recorded under `build` is the typecheck/build **fix agent**, which the
#: deadline may skip. Request 67 spent 156 s there and request 70 spent 477 s.
ELECTIVE_STAGES: frozenset[str] = frozenset(
    {
        "analyze",
        "build",
        "build_failed",
        "build_plans",
        "critic",
        "design_critic",
        "fix_agent",
        "proposal",
        "quality_gate",
        "quality_repair",
        "refine",
        "tech",
        "vision",
        "visual_critic",
    }
)


def unclassified_stages(stages: Iterable[str]) -> list[str]:
    """Stages in neither table — the census must never guess at these.

    `pipeline` is the standing example: it is the provider's *default* purpose,
    what a call records when the request context never reached it. Silently
    filing those under MANDATORY would inflate the floor with critic and refine
    work; filing them under ELECTIVE would hide planning work the run cannot
    skip. They are named in the report instead.
    """

    known = MANDATORY_STAGES | ELECTIVE_STAGES
    return sorted({stage for stage in stages if stage not in known})


@dataclass(frozen=True)
class CallRecord:
    """One row of `ai_usage_events`, reduced to what the census needs."""

    request_id: int | None
    stage: str
    model: str
    latency_ms: int
    success: bool
    usable: bool | None = None
    writer: str | None = None
    attempt: int | None = None
    ops_applied: int | None = None
    finish_reason: str | None = None

    @property
    def latency_s(self) -> float:
        return max(0, int(self.latency_ms or 0)) / 1000.0

    @property
    def produced_nothing(self) -> bool:
        """Did this call buy the pipeline nothing?

        `usable is None` means the row predates adjudication. It is *not* read
        as a failure — an unmeasured call must not be counted as waste, or the
        first report inflates itself with its own blind spot.
        """

        if self.usable is None:
            return not self.success
        return not self.usable


@dataclass(frozen=True)
class LatencySummary:
    n: int
    p50_s: float
    p95_s: float
    mean_s: float
    total_s: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n": self.n,
            "p50_s": round(self.p50_s, 1),
            "p95_s": round(self.p95_s, 1),
            "mean_s": round(self.mean_s, 1),
            "total_s": round(self.total_s, 1),
        }


def percentile(values: Sequence[float], q: float) -> float:
    """Linear interpolation between closest ranks — numpy's default method.

    Named explicitly because the choice moves the answer on the small samples
    this census works with: on 5 observations, nearest-rank p95 is just the
    maximum, which would make every p95 in the report the worst thing that ever
    happened rather than an estimate.
    """

    if not values:
        return 0.0
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"percentile q must be in [0, 1], got {q}")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = q * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return float(ordered[low] * (1.0 - weight) + ordered[high] * weight)


def latency_summary(records: Iterable[CallRecord]) -> LatencySummary:
    samples = [record.latency_s for record in records]
    if not samples:
        return LatencySummary(n=0, p50_s=0.0, p95_s=0.0, mean_s=0.0, total_s=0.0)
    return LatencySummary(
        n=len(samples),
        p50_s=percentile(samples, 0.50),
        p95_s=percentile(samples, 0.95),
        mean_s=sum(samples) / len(samples),
        total_s=sum(samples),
    )


def summarize_by(
    records: Iterable[CallRecord],
    key: str,
) -> dict[str, LatencySummary]:
    """Group by `stage` or `model` (any `CallRecord` attribute) and summarize."""

    buckets: dict[str, list[CallRecord]] = defaultdict(list)
    for record in records:
        buckets[str(getattr(record, key) or "unknown")].append(record)
    return {name: latency_summary(rows) for name, rows in sorted(buckets.items())}


def wasted_seconds(records: Iterable[CallRecord]) -> tuple[int, float]:
    """Calls that produced nothing usable, and the wall clock they cost."""

    dead = [record for record in records if record.produced_nothing]
    return len(dead), sum(record.latency_s for record in dead)


def calls_per_run(records: Iterable[CallRecord]) -> dict[str, dict[str, float]]:
    """Per-stage call counts across runs: min / median / max over request ids.

    Rows with no request id are excluded — before the context-propagation fix
    that was 39 of request 67's 58 rows, and averaging them into a per-run count
    would divide a partial numerator by a whole denominator.
    """

    per_run: dict[int, Counter[str]] = defaultdict(Counter)
    for record in records:
        if record.request_id is None:
            continue
        per_run[record.request_id][record.stage] += 1
    if not per_run:
        return {}
    stages = sorted({stage for counts in per_run.values() for stage in counts})
    out: dict[str, dict[str, float]] = {}
    for stage in stages:
        counts = [float(counts_for_run[stage]) for counts_for_run in per_run.values()]
        out[stage] = {
            "min": min(counts),
            "median": percentile(counts, 0.50),
            "max": max(counts),
            "runs": float(len(counts)),
        }
    return out


def mandatory_floor(
    census: Mapping[str, float],
    mandatory: Iterable[str] = MANDATORY_STAGES,
) -> int:
    """Logical calls a run cannot avoid: the mandatory stages' call counts.

    `census` maps stage → calls per run. Rounded up, because half a model call
    does not exist and the floor must not be optimistic.
    """

    mandatory_set = set(mandatory)
    total = sum(
        float(count) for stage, count in census.items() if stage in mandatory_set
    )
    return int(-(-total // 1)) if total > 0 else 0


@dataclass
class RunDistribution:
    """The distribution of a whole run's AI wall clock, by convolution."""

    bin_ms: int
    #: bin index -> probability mass
    mass: dict[int, float] = field(default_factory=lambda: {0: 1.0})

    def percentile_s(self, q: float) -> float:
        if not self.mass:
            return 0.0
        cumulative = 0.0
        for index in sorted(self.mass):
            cumulative += self.mass[index]
            if cumulative >= q - 1e-12:
                return index * self.bin_ms / 1000.0
        return max(self.mass) * self.bin_ms / 1000.0

    def mean_s(self) -> float:
        return sum(
            index * self.bin_ms / 1000.0 * weight for index, weight in self.mass.items()
        )

    def shift_s(self, seconds: float) -> "RunDistribution":
        """Add a fixed, non-model cost (capture, build, deterministic work)."""

        offset = int(round(seconds * 1000 / self.bin_ms))
        return RunDistribution(
            bin_ms=self.bin_ms,
            mass={index + offset: weight for index, weight in self.mass.items()},
        )


def _histogram(samples_s: Sequence[float], bin_ms: int) -> dict[int, float]:
    if not samples_s:
        return {0: 1.0}
    weight = 1.0 / len(samples_s)
    out: dict[int, float] = defaultdict(float)
    for value in samples_s:
        out[int(round(max(0.0, value) * 1000 / bin_ms))] += weight
    return dict(out)


_PRUNE_BELOW = 1e-12


def convolve(
    left: Mapping[int, float],
    right: Mapping[int, float],
) -> dict[int, float]:
    """Distribution of the sum of two independent discrete variables."""

    out: dict[int, float] = defaultdict(float)
    for i, wi in left.items():
        if wi < _PRUNE_BELOW:
            continue
        for j, wj in right.items():
            product = wi * wj
            if product >= _PRUNE_BELOW:
                out[i + j] += product
    return dict(out)


def run_latency_distribution(
    stage_samples: Mapping[str, Sequence[float]],
    census: Mapping[str, float],
    *,
    bin_ms: int = 1000,
) -> RunDistribution:
    """Convolve each stage's empirical latency, repeated by its call count.

    A stage that runs `n` times contributes `n` independent draws from its own
    measured distribution. This is the operation the roadmap's Phase 2 DoD calls
    for by name — "derived by convolution over the 0.6 census, not asserted".

    Independence is an assumption, and it is the optimistic direction: model
    latencies on one provider correlate on a bad day, so the real tail is at
    least this long. Stated here rather than buried, because it is the reason
    the recommended deadline carries headroom rather than sitting on the number.
    """

    distribution = RunDistribution(bin_ms=bin_ms)
    for stage, count in sorted(census.items()):
        samples = stage_samples.get(stage) or []
        repeats = int(round(float(count)))
        if not samples or repeats <= 0:
            continue
        histogram = _histogram(samples, bin_ms)
        for _ in range(repeats):
            distribution.mass = convolve(distribution.mass, histogram)
    return distribution


def census_report(
    records: Sequence[CallRecord],
    *,
    fixed_overhead_s: float = 0.0,
    bin_ms: int = 1000,
    mandatory: Iterable[str] = MANDATORY_STAGES,
) -> dict[str, object]:
    """Everything Phase 0.6 owes the deadline decision, in one dict."""

    by_stage = summarize_by(records, "stage")
    by_model = summarize_by(records, "model")
    dead_calls, dead_seconds = wasted_seconds(records)
    per_run = calls_per_run(records)
    census = {stage: stats["median"] for stage, stats in per_run.items()}
    stage_samples = {
        stage: [record.latency_s for record in records if record.stage == stage]
        for stage in by_stage
    }
    distribution = run_latency_distribution(
        stage_samples, census, bin_ms=bin_ms
    ).shift_s(fixed_overhead_s)
    mandatory_census = {
        stage: count for stage, count in census.items() if stage in set(mandatory)
    }
    mandatory_distribution = run_latency_distribution(
        stage_samples, mandatory_census, bin_ms=bin_ms
    ).shift_s(fixed_overhead_s)
    return {
        "rows": len(records),
        "rows_missing_request_id": sum(1 for r in records if r.request_id is None),
        "rows_unadjudicated": sum(1 for r in records if r.usable is None),
        "unclassified_stages": unclassified_stages(by_stage),
        "by_stage": {name: summary.as_dict() for name, summary in by_stage.items()},
        "by_model": {name: summary.as_dict() for name, summary in by_model.items()},
        "calls_per_run": per_run,
        "census": census,
        "mandatory_floor": mandatory_floor(census, mandatory),
        "unusable_calls": dead_calls,
        "unusable_seconds": round(dead_seconds, 1),
        "run_p50_s": round(distribution.percentile_s(0.50), 1),
        "run_p95_s": round(distribution.percentile_s(0.95), 1),
        "run_mean_s": round(distribution.mean_s(), 1),
        "mandatory_p50_s": round(mandatory_distribution.percentile_s(0.50), 1),
        "mandatory_p95_s": round(mandatory_distribution.percentile_s(0.95), 1),
        "fixed_overhead_s": fixed_overhead_s,
    }


__all__ = [
    "ELECTIVE_STAGES",
    "MANDATORY_STAGES",
    "CallRecord",
    "LatencySummary",
    "RunDistribution",
    "calls_per_run",
    "census_report",
    "convolve",
    "latency_summary",
    "mandatory_floor",
    "percentile",
    "run_latency_distribution",
    "summarize_by",
    "unclassified_stages",
    "wasted_seconds",
]
