"""Shared pure Phase 7D/7E breaker metric snapshot calculation."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Sequence

from app.domain.schemas.breaker import BreakerMetricSnapshot
from app.domain.schemas.rollout import CircuitBreakerPolicyContract


def canonical_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def nearest_rank_p95(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return float(ordered[rank - 1])


def compute_breaker_metric_snapshot(
    *,
    policy: CircuitBreakerPolicyContract,
    metric_classes: Iterable[str],
    outcomes: Iterable[str] | None = None,
    duration_seconds: Iterable[float | None] | None = None,
) -> BreakerMetricSnapshot:
    """Compute snapshot from parallel class/outcome/latency sequences.

    Prefer :func:`compute_breaker_metric_snapshot_from_rows` for ORM rows.
    """
    classes = list(metric_classes)
    durs = list(duration_seconds) if duration_seconds is not None else [None] * len(classes)
    if len(durs) != len(classes):
        raise ValueError("duration_seconds length must match metric_classes")
    rows = [
        {"metric_class": c, "duration_s": d} for c, d in zip(classes, durs, strict=True)
    ]
    return _snapshot_from_normalized(policy, rows)


def compute_breaker_metric_snapshot_from_rows(
    policy: CircuitBreakerPolicyContract,
    samples: Sequence[Any],
) -> BreakerMetricSnapshot:
    """samples: objects with metric_class and optional duration_ms."""
    rows: list[dict[str, Any]] = []
    for s in samples:
        duration_s = None
        dur_ms = getattr(s, "duration_ms", None)
        if dur_ms is not None:
            duration_s = float(dur_ms) / 1000.0
        rows.append(
            {
                "metric_class": str(getattr(s, "metric_class")),
                "duration_s": duration_s,
            }
        )
    return _snapshot_from_normalized(policy, rows)


def _snapshot_from_normalized(
    policy: CircuitBreakerPolicyContract,
    rows: Sequence[dict[str, Any]],
) -> BreakerMetricSnapshot:
    promo = [
        r
        for r in rows
        if r["metric_class"]
        in ("promotion_write_success", "promotion_write_failure")
    ]
    promo_fail = [
        r for r in promo if r["metric_class"] == "promotion_write_failure"
    ]
    health = [
        r
        for r in rows
        if r["metric_class"]
        in ("serving_health_success", "serving_health_failure")
    ]
    health_fail = [
        r for r in health if r["metric_class"] == "serving_health_failure"
    ]
    latencies = [
        float(r["duration_s"])
        for r in rows
        if r["metric_class"] == "serving_latency" and r["duration_s"] is not None
    ]
    streak = 0
    for r in reversed(health):
        if r["metric_class"] == "serving_health_failure":
            streak += 1
        else:
            break
    promo_rate = (len(promo_fail) / len(promo)) if promo else 0.0
    health_rate = (len(health_fail) / len(health)) if health else 0.0
    p95 = nearest_rank_p95(latencies) if policy.p95_serving_latency_enabled else None
    trips: list[str] = []
    if (
        len(promo) >= policy.min_samples
        and promo_rate >= policy.promotion_write_failure_threshold
    ):
        trips.append("promotion_write_failure_rate")
    if (
        len(health) >= policy.min_samples
        and health_rate >= policy.serving_health_failure_threshold
    ):
        trips.append("serving_health_failure_rate")
    if streak >= policy.consecutive_serving_health_failures:
        trips.append("consecutive_serving_health_failures")
    if (
        policy.p95_serving_latency_enabled
        and p95 is not None
        and len(latencies) >= policy.min_samples
        and p95 >= policy.p95_serving_latency_seconds
    ):
        trips.append("p95_serving_latency")
    body = {
        "window_seconds": policy.window_seconds,
        "min_samples": policy.min_samples,
        "promotion_write_samples": len(promo),
        "promotion_write_failures": len(promo_fail),
        "promotion_write_failure_rate": promo_rate,
        "serving_health_samples": len(health),
        "serving_health_failures": len(health_fail),
        "serving_health_failure_rate": health_rate,
        "consecutive_serving_health_failures": streak,
        "latency_samples": len(latencies),
        "p95_serving_latency_seconds": p95,
        "p95_enabled": policy.p95_serving_latency_enabled,
        "trip_reasons": trips,
    }
    return BreakerMetricSnapshot(**body, snapshot_sha256=canonical_sha256(body))


__all__ = [
    "canonical_sha256",
    "compute_breaker_metric_snapshot",
    "compute_breaker_metric_snapshot_from_rows",
    "nearest_rank_p95",
]
