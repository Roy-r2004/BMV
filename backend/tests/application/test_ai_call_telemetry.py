"""The two `ai_usage_events` defects Phase 0.6 exists to close.

**One.** `request_id` was NULL on 39 of request 67's 58 rows — every call the
codegen, critic and vision fan-outs made. `ai_run_scope` keeps the request id in
a `ContextVar`, and a `ContextVar` does not cross `Executor.submit`: the pool
thread starts with an empty context and the attribution silently reverts to its
default. Per-request cost and latency queries undercounted by roughly two
thirds, which is the difference between "the repair loop is expensive" and "the
repair loop is half the run".

**Two.** `success` meant HTTP 200. Two of request 67's three dead fix-agent
calls were recorded `success = true` — 200s carrying JSON no extractor could
read. The transport verdict and the usability verdict are now separate columns
and this file pins them apart.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

from app.application.preview_app.parallel import parallel_map  # noqa: E402
from app.application.services.ai_context import (  # noqa: E402
    UNUSABLE_EMPTY,
    UNUSABLE_TRANSPORT,
    UNUSABLE_TRUNCATED,
    UNUSABLE_UNPARSEABLE,
    ai_call,
    ai_run_scope,
    current_ai_call,
    get_ai_purpose,
    get_ai_request_id,
    set_ai_purpose,
)


@pytest.fixture()
def captured() -> list[list[dict]]:
    """Collect what an outermost `ai_call` scope would have written."""

    return []


def _flush_into(sink: list[list[dict]]):
    return lambda rows: sink.append(rows)


# --------------------------------------------------------------------------
# defect 1 — the request id must reach a worker thread
# --------------------------------------------------------------------------


def test_a_pool_worker_sees_the_request_it_is_working_on() -> None:
    """`parallel_map` is how codegen, the critic and the vision fan-out run."""

    with ai_run_scope(67, purpose="codegen"):
        results = parallel_map(
            [1, 2, 3, 4],
            lambda _item: (get_ai_request_id(), get_ai_purpose()),
            max_workers=4,
        )

    assert [result for _item, result, _exc in results] == [(67, "codegen")] * 4


def test_the_serial_path_and_the_pool_path_attribute_identically() -> None:
    """`max_workers=1` short-circuits the pool; both must agree, or the census
    changes shape whenever concurrency is tuned."""

    with ai_run_scope(70, purpose="vision"):
        serial = parallel_map([1, 2], lambda _i: get_ai_request_id(), max_workers=1)
        pooled = parallel_map([1, 2], lambda _i: get_ai_request_id(), max_workers=2)

    assert [r for _i, r, _e in serial] == [r for _i, r, _e in pooled] == [70, 70]


def test_each_worker_gets_its_own_context_copy() -> None:
    """A `Context` cannot be entered twice concurrently — one shared copy would
    raise `cannot enter context` under real parallelism, intermittently."""

    barrier = threading.Barrier(4, timeout=10)

    def _worker(_item: int) -> int | None:
        barrier.wait()
        set_ai_purpose("mutated-by-worker")
        return get_ai_request_id()

    with ai_run_scope(71, purpose="codegen"):
        results = parallel_map([1, 2, 3, 4], _worker, max_workers=4)
        # A worker's mutation must not leak back into the submitting context.
        assert get_ai_purpose() == "codegen"

    assert [r for _i, r, e in results] == [71, 71, 71, 71]
    assert all(e is None for _i, _r, e in results)


def test_a_worker_outside_any_run_scope_still_reports_no_request() -> None:
    results = parallel_map([1, 2], lambda _i: get_ai_request_id(), max_workers=2)

    assert [r for _i, r, _e in results] == [None, None]


# --------------------------------------------------------------------------
# defect 2 — usable is not 200
# --------------------------------------------------------------------------


def test_a_200_the_caller_could_not_parse_is_recorded_unusable(captured) -> None:
    with ai_call("fix_agent", writer="primary", flush=_flush_into(captured)) as call:
        call.record({"success": True, "usable": True, "latency_ms": 90_000})
        call.unusable(UNUSABLE_UNPARSEABLE)

    (rows,) = captured
    assert rows[0]["success"] is True, "the transport verdict is untouched"
    assert rows[0]["usable"] is False
    assert rows[0]["unusable_reason"] == UNUSABLE_UNPARSEABLE


def test_a_usable_verdict_does_not_resurrect_a_transport_failure(captured) -> None:
    """A timeout is not reclassified because a later ask in the same scope
    parsed. The provider's own condemnation is the more specific fact."""

    with ai_call("fix_agent", flush=_flush_into(captured)) as call:
        call.record(
            {"success": False, "usable": False, "unusable_reason": UNUSABLE_TRANSPORT}
        )
        call.record({"success": True, "usable": True})
        call.mark_usable()

    (rows,) = captured
    assert rows[0]["usable"] is False
    assert rows[0]["unusable_reason"] == UNUSABLE_TRANSPORT
    assert rows[1]["usable"] is True


def test_the_scope_stamps_stage_writer_and_attempt(captured) -> None:
    with ai_call("quality_repair", writer="strict-retry", attempt=2,
                 flush=_flush_into(captured)) as call:
        call.record({"success": True, "usable": True})

    (rows,) = captured
    assert rows[0]["stage"] == "quality_repair"
    assert rows[0]["writer"] == "strict-retry"
    assert rows[0]["attempt"] == 2


def test_ops_applied_reaches_a_row_adjudicated_three_calls_earlier(captured) -> None:
    """Request 68's 882.2 s repair loop applied zero file operations.

    The count is only known after the plan has been applied, long after the ask
    that produced it was adjudicated. Nesting is what lets both facts land on
    one row without a second write.
    """

    with ai_call("quality_repair", flush=_flush_into(captured)) as outer:
        with ai_call("quality_repair", writer="primary") as inner:
            inner.record({"success": True, "usable": True, "latency_ms": 300_000})
            inner.unusable(UNUSABLE_UNPARSEABLE)
        outer.applied_ops(0)

    (rows,) = captured
    assert rows[0]["usable"] is False
    assert rows[0]["ops_applied"] == 0


def test_only_the_outermost_scope_writes(captured) -> None:
    with ai_call("fix_agent", flush=_flush_into(captured)) as outer:
        with ai_call("fix_agent", writer="primary") as inner:
            inner.record({"success": True, "usable": True})
        assert captured == [], "an inner scope must not write on its own"
        outer.applied_ops(3)

    assert len(captured) == 1
    assert captured[0][0]["ops_applied"] == 3


def test_an_inner_verdict_survives_the_bubble_to_the_parent(captured) -> None:
    """Two asks in one repair round, one useless and one not."""

    with ai_call("fix_agent", flush=_flush_into(captured)) as outer:
        with ai_call("fix_agent", writer="primary") as first:
            first.record({"success": True, "usable": True, "latency_ms": 90_000})
            first.unusable(UNUSABLE_UNPARSEABLE)
        with ai_call("fix_agent", writer="strict-retry", attempt=2) as second:
            second.record({"success": True, "usable": True, "latency_ms": 41_000})
            second.mark_usable()
        outer.applied_ops(2)

    (rows,) = captured
    assert [row["usable"] for row in rows] == [False, True]
    assert [row["writer"] for row in rows] == ["primary", "strict-retry"]
    assert all(row["ops_applied"] == 2 for row in rows)


def test_an_exception_inside_the_scope_still_flushes_and_still_propagates(
    captured,
) -> None:
    """Telemetry must never swallow a failed ask — `return` in a `finally`
    block would do exactly that."""

    with pytest.raises(RuntimeError, match="provider exploded"):
        with ai_call("codegen", flush=_flush_into(captured)) as call:
            call.record({"success": False, "usable": False})
            raise RuntimeError("provider exploded")

    assert captured and captured[0][0]["usable"] is False


def test_a_flush_that_raises_cannot_break_the_pipeline() -> None:
    def _explodes(_rows):
        raise RuntimeError("database is down")

    with ai_call("codegen", flush=_explodes) as call:
        call.record({"success": True, "usable": True})


def test_an_empty_scope_writes_nothing(captured) -> None:
    with ai_call("codegen", flush=_flush_into(captured)):
        pass

    assert captured == []


def test_the_scope_is_torn_down_even_when_the_body_raises() -> None:
    with pytest.raises(ValueError):
        with ai_call("codegen"):
            raise ValueError("boom")

    assert current_ai_call() is None


def test_adjudicate_maps_a_boolean_to_the_two_verdicts(captured) -> None:
    with ai_call("codegen", flush=_flush_into(captured)) as call:
        call.record({"success": True, "usable": True})
        call.adjudicate(False, reason=UNUSABLE_EMPTY)
    with ai_call("codegen", flush=_flush_into(captured)) as call:
        call.record({"success": True, "usable": True})
        call.adjudicate(True)

    assert captured[0][0]["unusable_reason"] == UNUSABLE_EMPTY
    assert captured[1][0]["usable"] is True
    assert captured[1][0]["unusable_reason"] is None


# --------------------------------------------------------------------------
# the provider-side half of the verdict
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("success", "output_chars", "finish_reason", "expected", "reason"),
    [
        (True, 4_000, "stop", True, None),
        (False, 0, "", False, UNUSABLE_TRANSPORT),
        (True, 0, "stop", False, UNUSABLE_EMPTY),
        (True, 12_000, "length", False, UNUSABLE_TRUNCATED),
        (True, 12_000, "max_tokens", False, UNUSABLE_TRUNCATED),
        (True, None, "stop", True, None),
        # 18 of the 19 failed calls across requests 66-71 are this shape. The
        # socket was fine; the model ran out of tokens. Calling it "transport"
        # points the next engineer at the network.
        (False, 12_000, "length", False, UNUSABLE_TRUNCATED),
    ],
)
def test_the_provider_condemns_the_obvious_cases_without_being_asked(
    success, output_chars, finish_reason, expected, reason
) -> None:
    from app.application.services.admin_ops import presumed_usable

    usable, why = presumed_usable(
        success=success, output_chars=output_chars, finish_reason=finish_reason
    )

    assert usable is expected
    assert why == reason


def test_truncation_beats_a_healthy_looking_transport() -> None:
    """`finish_reason: length` was one of request 67's six fix-agent failures.

    It is a 200 with thousands of characters in it. Nothing about the transport
    column can express that the answer stops mid-token.
    """

    from app.application.services.admin_ops import presumed_usable

    usable, reason = presumed_usable(
        success=True, output_chars=30_000, finish_reason="length"
    )

    assert usable is False
    assert reason == UNUSABLE_TRUNCATED
