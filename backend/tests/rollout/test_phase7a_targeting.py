"""Frozen sticky-bucket vectors and cohort properties."""
from __future__ import annotations

import hashlib
import os

import pytest

from app.application.rollout.targeting import (
    FROZEN_STICKY_VECTORS,
    StickyBucketError,
    compute_sticky_bucket,
)


def test_frozen_64bit_vectors() -> None:
    for salt, request_id, first8, bucket in FROZEN_STICKY_VECTORS:
        result = compute_sticky_bucket(
            salt=salt, request_id=request_id, rollout_percent=100
        )
        assert result.digest_first8_hex == first8
        assert result.bucket == bucket
        material = f"{salt}:{request_id}".encode("utf-8")
        expected = hashlib.sha256(material).digest()[:8].hex()
        assert first8 == expected


def test_zero_percent_selects_nobody() -> None:
    for _, request_id, _, _ in FROZEN_STICKY_VECTORS:
        result = compute_sticky_bucket(
            salt="2026-07-25.1", request_id=request_id, rollout_percent=0
        )
        assert result.percent_eligible is False


def test_hundred_percent_selects_everybody() -> None:
    for _, request_id, _, _ in FROZEN_STICKY_VECTORS:
        result = compute_sticky_bucket(
            salt="2026-07-25.1", request_id=request_id, rollout_percent=100
        )
        assert result.percent_eligible is True


def test_increasing_percent_preserves_cohort() -> None:
    salt = "2026-07-25.1"
    for request_id in ("1", "42", "100", "999", "23104"):
        low = compute_sticky_bucket(salt=salt, request_id=request_id, rollout_percent=40)
        high = compute_sticky_bucket(salt=salt, request_id=request_id, rollout_percent=80)
        if low.percent_eligible:
            assert high.percent_eligible


def test_changing_salt_may_reshuffle() -> None:
    a = compute_sticky_bucket(salt="2026-07-25.1", request_id=42, rollout_percent=50)
    b = compute_sticky_bucket(salt="2026-07-25.2", request_id=42, rollout_percent=50)
    # Buckets are independent; reshuffle means salt change can change membership.
    assert a.digest_first8_hex != b.digest_first8_hex


def test_python_hash_randomization_has_no_effect() -> None:
    # PYTHONHASHSEED must not affect sticky buckets (we do not use hash()).
    before = compute_sticky_bucket(
        salt="2026-07-25.1", request_id=23104, rollout_percent=66
    )
    os.environ["PYTHONHASHSEED"] = "0"
    after = compute_sticky_bucket(
        salt="2026-07-25.1", request_id=23104, rollout_percent=66
    )
    assert before.bucket == after.bucket == 66
    assert before.digest_first8_hex == after.digest_first8_hex


def test_rejects_malformed_inputs() -> None:
    with pytest.raises(StickyBucketError):
        compute_sticky_bucket(salt="  ", request_id=1, rollout_percent=10)
    with pytest.raises(StickyBucketError):
        compute_sticky_bucket(salt="x", request_id="", rollout_percent=10)
    with pytest.raises(StickyBucketError):
        compute_sticky_bucket(salt="x", request_id=1, rollout_percent=101)
    with pytest.raises(StickyBucketError):
        compute_sticky_bucket(salt="x", request_id=-1, rollout_percent=10)


def test_boundary_bucket_equals_percent_not_eligible() -> None:
    # request 42 → bucket 89; percent 89 → not eligible; 90 → eligible
    assert (
        compute_sticky_bucket(
            salt="2026-07-25.1", request_id=42, rollout_percent=89
        ).percent_eligible
        is False
    )
    assert (
        compute_sticky_bucket(
            salt="2026-07-25.1", request_id=42, rollout_percent=90
        ).percent_eligible
        is True
    )
