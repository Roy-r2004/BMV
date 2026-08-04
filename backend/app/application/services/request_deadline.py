"""Request-scoped wall-clock deadline for preview generation.

The product promise is a preview in under ten minutes. Nothing in the pipeline
enforced that: request 68 ran 1,675 s, and its quality-repair loop alone was
882 s — 52.7 % of the run — for **zero applied file operations**.

Measuring the runs (Phase 0.6, requests 66-71, 360 calls, 6,836 AI seconds)
settled two things that shape this module:

* **The pipeline is serial.** AI seconds / wall clock is 1.007-1.100 on every
  run, so a wall-clock budget really is a budget over model latency, and
  subtracting one stage's cost from the whole is valid arithmetic.
* **A mean is useless here.** p95/p50 is 2.4x. `z-ai/glm-5.2` is 6 % of calls
  and 37 % of the seconds, at p95 233 s for a *single* ask. The tail is the
  product, not an outlier.

## Why 540 and not 480

480 s was the first proposal. At t=480 **all six measured runs were still
inside `build` or `codegen`** — not one had produced a preview, and
P(mandatory path > 480 s) is 42 %. A deadline that forces mandatory
degradation on two runs in five is not a contract, it is a second failure
mode. 480 also does not close arithmetically: pre-preview work is p50 124 s
(not the 94 s minimum), and 124 + 480 + 60 > 600.

540 s from the top of the pipeline, with `RESERVE_SECONDS` held back for the
post-deadline render-smoke and capture pass (measured 41-42 s), gives
P(mandatory > 540) = 13 % and lands inside the 600 s cap.

**This module alone does not deliver 600 s.** It bounds the run; the per-ask
ceiling that keeps one `glm-5.2` call from eating 233 s of the budget is what
makes the bound rarely bite. Both ship together or neither works.

## The degradation contract

A deadline that simply kills the run trades a slow preview for no preview,
and two of three observed runs already shipped nothing. So:

* An **elective** stage that would start past the deadline is **skipped**.
* A **mandatory** stage past the deadline still runs, but falls through to its
  deterministic default rather than paying for a model call.

Either way the stage is recorded in `degradations()`, which is machine-readable
so the gate and the `viewable` decision can read it. A run that degraded and a
run that did not must never look alike — that is the failure this codebase
keeps rediscovering under other names.

The deadline lives in a `ContextVar` and therefore crosses threads only via
`ai_context.propagated_context()`, which the parallel workers already use.

## Why blocked time is recorded

Two process-wide locks serialize concurrent generations: `_SESSION_LOCK` in
`screenshot` and `_install_lock` in `npm_shared`. Neither is visible to the run
waiting on it — the deadline keeps ticking while that run does nothing, and it
then degrades stages it had the time for. A degradation caused by another
request's browser session is not the same event as a degradation caused by this
request being slow, and a report that cannot tell them apart will conclude the
contract works when it has merely mislabelled the cause. `contended_lock`
charges the wait to whichever request paid it; `finalize` publishes the total.
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator

from app.infrastructure.logging import get_logger

log = get_logger("Deadline")

#: Total wall clock for one generation, stamped before the blueprint call.
#: See the module docstring for why this is 540 and not 480.
DEFAULT_TOTAL_SECONDS = 540.0

#: Held back for work that must happen *after* the deadline: the post-gate
#: render smoke probe and its capture pass. Measured 41 s and 42 s on requests
#: 66 and 67. 540 + 60 = 600, the cap.
RESERVE_SECONDS = 60.0

#: A single logical ask — inclusive of every transport retry and every model
#: failover. Before this, `timeout=120` x `_WALL_CLOCK_BUDGET_FACTOR=2.5` x
#: `attempts=2` was 600 s per ask, and `hard_deadline` was enforced per
#: *attempt*, so failing over to another model doubled it again. One repair
#: call was held open for 1,040 s.
DEFAULT_ASK_CEILING_SECONDS = 120.0

#: A retry of the whole preview generation needs at least this much runway to
#: be worth starting. `orchestrator` retries once on any exception; without
#: this it inherits a fresh budget and the cap means nothing.
MIN_RETRY_RUNWAY_SECONDS = 180.0

#: Below this a lock wait is an uncontended acquisition, not contention. Logged
#: at debug; still summed, because ten sub-second waits are still a wait.
CONTENTION_LOG_THRESHOLD_SECONDS = 1.0


#: Stages the pipeline cannot omit and still have produced a preview. Past the
#: deadline these do not stop — they take their deterministic path.
MANDATORY_STAGES = frozenset(
    {
        "appspec",
        "architect",
        "assemble",
        "blueprint",
        "build",
        "codegen",
        "finalize",
        "planning",
        "render_smoke",
    }
)

#: Stages that improve a preview but whose absence still leaves one. Past the
#: deadline these are skipped outright.
ELECTIVE_STAGES = frozenset(
    {
        "build_plans",
        "demo",
        "proposal",
        "quality_repair",
        "reference_analysis",
        "refine",
        "tech",
        "visual_critic",
    }
)


class RequestDeadlineExceeded(RuntimeError):
    """Raised when a caller asks for model time the request no longer has."""

    def __init__(self, stage: str, remaining: float) -> None:
        super().__init__(
            f"request deadline exceeded at stage={stage} (remaining={remaining:.1f}s)"
        )
        self.stage = stage
        self.remaining = remaining


@dataclass
class Degradation:
    stage: str
    reason: str
    elapsed_seconds: float

    def as_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "reason": self.reason,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
        }


@dataclass
class RequestDeadline:
    """One generation's wall-clock budget, on a monotonic clock.

    Monotonic on purpose: a wall-clock jump (NTP, container suspend) must not
    hand a run more budget or less.
    """

    request_id: object
    total_seconds: float = DEFAULT_TOTAL_SECONDS
    reserve_seconds: float = RESERVE_SECONDS
    started_at: float = field(default_factory=time.monotonic)
    _degradations: list[Degradation] = field(default_factory=list, repr=False)
    _waits: dict[str, float] = field(default_factory=dict, repr=False)
    _stage_calls: dict[str, int] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def deadline_at(self) -> float:
        return self.started_at + self.total_seconds

    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def remaining(self) -> float:
        """Seconds left before the deadline. Negative once past it."""
        return self.deadline_at - time.monotonic()

    def expired(self) -> bool:
        return self.remaining() <= 0.0

    def has_runway(self, seconds: float) -> bool:
        return self.remaining() >= seconds

    def consume_stage_call(self, stage: str, limit: int) -> bool:
        """Take one AI call from `stage`'s **request-wide** budget.

        Returns False once the stage has spent `limit` calls on this request,
        however many times the stage was entered.

        A ceiling held on the stage object instead of here is a ceiling per
        *invocation*, and a stage entered more than once per generation then has
        no effective ceiling at all. `appspec` is entered twice — the
        orchestrator defines the contract and the preview pipeline confirms it —
        and was measured on requests 92-94 making 7, 6 and 10 calls against a
        configured 6, because each entry minted a fresh budget. The tally lives
        on the deadline because that is the object already scoped to exactly one
        generation and already crossing threads with it.
        """
        with self._lock:
            used = self._stage_calls.get(stage, 0)
            if used >= max(1, int(limit)):
                return False
            self._stage_calls[stage] = used + 1
            return True

    def stage_calls_used(self, stage: str) -> int:
        with self._lock:
            return self._stage_calls.get(stage, 0)

    def record_degradation(self, stage: str, reason: str) -> None:
        entry = Degradation(stage=stage, reason=reason, elapsed_seconds=self.elapsed())
        with self._lock:
            # One row per (stage, reason). A stage that degrades in a loop must
            # not bury the others under a hundred identical rows.
            for existing in self._degradations:
                if existing.stage == stage and existing.reason == reason:
                    return
            self._degradations.append(entry)
        log.warning(
            "request %s degraded stage=%s reason=%s elapsed=%.1fs remaining=%.1fs",
            self.request_id,
            stage,
            reason,
            entry.elapsed_seconds,
            self.remaining(),
        )

    def degradations(self) -> list[dict[str, object]]:
        with self._lock:
            return [entry.as_dict() for entry in self._degradations]

    def degraded_stages(self) -> list[str]:
        with self._lock:
            seen: list[str] = []
            for entry in self._degradations:
                if entry.stage not in seen:
                    seen.append(entry.stage)
            return seen

    def record_wait(self, resource: str, seconds: float) -> None:
        """Charge `seconds` of blocked-on-a-lock time to this request."""
        if seconds <= 0.0:
            return
        with self._lock:
            self._waits[resource] = self._waits.get(resource, 0.0) + float(seconds)

    def waits(self) -> dict[str, float]:
        with self._lock:
            return {name: round(value, 1) for name, value in self._waits.items()}

    def blocked_seconds(self) -> float:
        """Total wall clock this request spent waiting on a process-wide lock.

        Read this next to `elapsed()` before believing a degradation: a run that
        degraded with 200 s of this did not run out of its own time, it ran out
        of somebody else's.
        """
        with self._lock:
            return sum(self._waits.values())

    def ask_budget(self, requested: float | None = None) -> float:
        """Wall clock one logical ask may spend. **Zero means do not call.**

        Never larger than the request has left: an ask that outlives its own
        request is how a "bounded" call reached 1,040 s.

        Zero rather than a small positive floor, and that distinction is not
        cosmetic. The floor was 1 s, and request 72 showed what that buys: past
        the deadline every ask got a 1 s budget, `_run_with_heartbeat` only
        checks its deadline once per heartbeat (20 s), so each doomed call still
        waited 20 s, failed with a transport error, retried, and failed over to
        the next model. The stage spent **29 minutes past a deadline that had
        already expired**, making calls that could never succeed.

        A budget of zero makes `call_with_retry` refuse before the first
        attempt, which is a clean immediate failure the caller's deterministic
        fallback already handles. That is the degradation contract working;
        1 s was the contract quietly inverted into a fast-fail retry loop.
        """
        ceiling = DEFAULT_ASK_CEILING_SECONDS if requested is None else float(requested)
        ceiling = min(ceiling, DEFAULT_ASK_CEILING_SECONDS)
        return max(0.0, min(ceiling, self.remaining()))


_request_deadline: ContextVar[RequestDeadline | None] = ContextVar(
    "request_deadline", default=None
)


def current_deadline() -> RequestDeadline | None:
    return _request_deadline.get()


@contextmanager
def request_deadline_scope(
    request_id: object,
    *,
    total_seconds: float = DEFAULT_TOTAL_SECONDS,
    reserve_seconds: float = RESERVE_SECONDS,
) -> Iterator[RequestDeadline]:
    """Stamp a deadline for the whole generation.

    Re-entrant by design: a nested scope for the same request **inherits the
    outer deadline** rather than minting a fresh one. `generate_preview_app`
    is called twice by the orchestrator's retry path, and a second stamp there
    would hand the retry a whole new budget — which is exactly the hole this
    module exists to close.
    """
    existing = _request_deadline.get()
    if existing is not None and str(existing.request_id) == str(request_id):
        yield existing
        return

    deadline = RequestDeadline(
        request_id=request_id,
        total_seconds=float(total_seconds),
        reserve_seconds=float(reserve_seconds),
    )
    token = _request_deadline.set(deadline)
    log.info(
        "request %s deadline armed: %.0fs (+%.0fs reserved for post-deadline work)",
        request_id,
        deadline.total_seconds,
        deadline.reserve_seconds,
    )
    try:
        yield deadline
    finally:
        _request_deadline.reset(token)
        if deadline.expired():
            log.warning(
                "request %s finished %.1fs past its deadline; degraded=%s",
                request_id,
                -deadline.remaining(),
                deadline.degraded_stages() or "none",
            )


def remaining_seconds(default: float | None = None) -> float | None:
    """Seconds left, or `default` when no deadline is armed."""
    deadline = current_deadline()
    return default if deadline is None else deadline.remaining()


def ask_budget_seconds(requested: float | None = None) -> float:
    """Wall clock one logical ask may spend, honouring the request deadline."""
    deadline = current_deadline()
    if deadline is None:
        ceiling = (
            DEFAULT_ASK_CEILING_SECONDS if requested is None else float(requested)
        )
        return max(1.0, min(ceiling, DEFAULT_ASK_CEILING_SECONDS))
    return deadline.ask_budget(requested)


def record_degradation(stage: str, reason: str) -> None:
    deadline = current_deadline()
    if deadline is not None:
        deadline.record_degradation(stage, reason)


def degradations() -> list[dict[str, object]]:
    deadline = current_deadline()
    return [] if deadline is None else deadline.degradations()


def is_elective(stage: str) -> bool:
    return stage in ELECTIVE_STAGES


def should_skip_elective(stage: str) -> bool:
    """True when `stage` is elective and the request is out of time.

    Records the degradation as a side effect, so a skipped stage can never be
    silent — a run that skipped the visual critic and a run that ran it must
    not describe themselves the same way.
    """
    deadline = current_deadline()
    if deadline is None or not deadline.expired():
        return False
    if stage not in ELECTIVE_STAGES:
        return False
    deadline.record_degradation(stage, "skipped_past_deadline")
    return True


def claim_model_time(stage: str, *, mandatory: bool | None = None) -> bool:
    """Ask whether `stage` may still pay for a model call.

    Returns True when it may. Returns False — having recorded the degradation —
    when the deadline has passed, so a **mandatory** stage takes its
    deterministic path instead of its model path. Callers that cannot degrade
    should use `require_model_time`.
    """
    deadline = current_deadline()
    if deadline is None or not deadline.expired():
        return True
    if mandatory is None:
        mandatory = stage not in ELECTIVE_STAGES
    deadline.record_degradation(
        stage, "deterministic_fallback_past_deadline" if mandatory else "skipped_past_deadline"
    )
    return False


def require_model_time(stage: str) -> None:
    """Raise if the request is out of time. For callers with no fallback."""
    deadline = current_deadline()
    if deadline is not None and deadline.expired():
        deadline.record_degradation(stage, "no_model_time_remaining")
        raise RequestDeadlineExceeded(stage, deadline.remaining())


def publish_degradations(db: object, request_id: int) -> list[str]:
    """Write the *final* degradation list onto the stored `preview_app`.

    `finalize` publishes what it knows, but it runs inside `generate_preview_app`
    and the three ELECTIVE document stages (`tech`, `proposal`, `build_plans`)
    are skipped **after** it returns. So the stored marker could never contain
    them: requests 73, 75 and 76 each degraded three stages and each stored
    `degraded: []`. The roadmap recorded that marker as done and "seen on 73" —
    it was only ever seen in a log line at scope exit, which is the difference
    between a measurement and a reader for it.

    Returns the stage list written, or `[]` when there is nothing to write.
    Never raises: a bookkeeping write must not fail a delivered generation.
    """
    import json

    deadline = current_deadline()
    if deadline is None:
        return []
    entries = deadline.degradations()
    if not entries:
        return []
    stages = [str(entry["stage"]) for entry in entries]
    try:
        from app.application.pipelines._shared import get_request

        req = get_request(db, request_id)
        stored = json.loads(getattr(req, "generated_pages", None) or "{}")
        preview_app = stored.get("preview_app")
        if not isinstance(preview_app, dict):
            # A run that never produced a preview has nowhere to hang this. The
            # log line at scope exit stays the only record — say so rather than
            # invent a container that no reader expects.
            log.warning(
                "request %s degraded %s stage(s) but stored no preview_app to record "
                "them on: %s",
                request_id,
                len(stages),
                ", ".join(stages),
            )
            return []
        preview_app["degraded"] = stages
        preview_app["degradations"] = entries
        preview_app["blocked_seconds"] = round(deadline.blocked_seconds(), 1)
        preview_app["contention"] = deadline.waits()
        preview_app["elapsed_seconds"] = int(deadline.elapsed())
        preview_app["deadline_exceeded"] = deadline.expired()
        stored["preview_app"] = preview_app
        req.generated_pages = json.dumps(stored)
        db.commit()  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        log.warning("request %s: could not publish degradations (%s)", request_id, exc)
        return []
    return stages


def record_wait(resource: str, seconds: float) -> None:
    deadline = current_deadline()
    if deadline is not None:
        deadline.record_wait(resource, seconds)


def blocked_seconds() -> float:
    deadline = current_deadline()
    return 0.0 if deadline is None else deadline.blocked_seconds()


def contention_waits() -> dict[str, float]:
    deadline = current_deadline()
    return {} if deadline is None else deadline.waits()


def seconds_to_hard_cap() -> float | None:
    """Wall clock left before `total + reserve` — the 600 s the product promises.

    `remaining()` goes negative past the deadline and the reserve is what is
    deliberately left for post-deadline work, so this is the only number that
    answers "how long may this still take". None when no deadline is armed.
    """
    deadline = current_deadline()
    if deadline is None:
        return None
    return max(0.0, deadline.remaining() + deadline.reserve_seconds)


@contextmanager
def contended_lock(
    lock: "threading.Lock", resource: str, *, timeout: float | None = None
) -> Iterator[bool]:
    """Hold `lock`, charging the time spent waiting for it to this request.

    The wait is measured around `acquire()` and recorded before the body runs,
    so a run that is still blocked when something else inspects the deadline has
    not yet been credited — that is deliberate. The number only becomes true
    once the wait is over, and reporting a partial wait as a total would be the
    same class of lie as a guard that reports success while the defect ships.

    Releasing is unconditional: an exception inside the body must not strand a
    process-wide lock and take every later generation down with it.

    Yields True when the lock was taken. With `timeout` set it can yield **False**
    without holding it — the caller must check. An unbounded wait is how request
    77 reached 619.7 s: the wait itself is not work, and nothing was stopping it
    from outlasting the cap.
    """
    started = time.monotonic()
    acquired = lock.acquire() if timeout is None else lock.acquire(timeout=max(0.0, timeout))
    waited = time.monotonic() - started
    try:
        record_wait(resource, waited)
        if waited >= CONTENTION_LOG_THRESHOLD_SECONDS or not acquired:
            deadline = current_deadline()
            log.warning(
                "request %s %s %.1fs on %s (%.1fs of its deadline remaining)",
                None if deadline is None else deadline.request_id,
                "blocked" if acquired else "GAVE UP after",
                waited,
                resource,
                float("inf") if deadline is None else deadline.remaining(),
            )
        yield acquired
    finally:
        if acquired:
            lock.release()


def has_retry_runway(seconds: float = MIN_RETRY_RUNWAY_SECONDS) -> bool:
    """Whether a whole-generation retry is worth starting.

    The orchestrator retries `generate_preview_app` once on any exception. With
    no deadline that retry is free; with one it must fit inside what is left.
    """
    deadline = current_deadline()
    return True if deadline is None else deadline.has_runway(seconds)


__all__ = [
    "CONTENTION_LOG_THRESHOLD_SECONDS",
    "DEFAULT_ASK_CEILING_SECONDS",
    "DEFAULT_TOTAL_SECONDS",
    "ELECTIVE_STAGES",
    "MANDATORY_STAGES",
    "MIN_RETRY_RUNWAY_SECONDS",
    "RESERVE_SECONDS",
    "Degradation",
    "RequestDeadline",
    "RequestDeadlineExceeded",
    "ask_budget_seconds",
    "blocked_seconds",
    "claim_model_time",
    "contended_lock",
    "contention_waits",
    "current_deadline",
    "degradations",
    "has_retry_runway",
    "is_elective",
    "publish_degradations",
    "record_degradation",
    "record_wait",
    "remaining_seconds",
    "request_deadline_scope",
    "require_model_time",
    "should_skip_elective",
]
