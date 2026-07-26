"""Phase 3A provider-call budgeting policy (revision 2026-07-26.1).

Enforces per-substage and total provider-call limits with an append-only
event ledger so budget state can be reconstructed after a restart.

Typed denial codes replace the previous vague "exceeded budget" string:
  - phase3a_substage_call_budget_exhausted  – per-stage cap reached
  - phase3a_total_call_budget_exhausted     – global cap reached
  - phase3a_required_call_reservation_violation – later-stage reservation violated
  - phase3a_optional_enrichment_skipped     – informational: optional AI skipped
  - phase3a_no_budget_for_repair            – repair call denied by budget
  - phase3a_counter_inconsistent            – ledger/metrics mismatch

Key invariants
--------------
* content_data_plan holds a reservation of 1 call until it resolves.
  Deterministic success releases the reservation without charging it.
  AI success charges 1 and releases the reservation simultaneously.
* Transport retries (sdk-level) are NOT separate application charges;
  the provider call count matches approved logical calls, not wire attempts.
* approve() must be called BEFORE constructing the provider request.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from app.core.config import settings

PHASE3A_CALL_BUDGET_POLICY_REVISION = "2026-07-26.1"

Phase3ABudgetCode = Literal[
    "phase3a_total_call_budget_exhausted",
    "phase3a_substage_call_budget_exhausted",
    "phase3a_required_call_reservation_violation",
    "phase3a_optional_enrichment_skipped",
    "phase3a_no_budget_for_repair",
    "phase3a_counter_inconsistent",
]

# Maximum AI provider calls allowed per substage.
# Deterministic stages are 0 because they never invoke a provider.
_SUBSTAGE_CAPS: dict[str, int] = {
    "page_purpose_contract": 0,
    "business_component_plan": 2,
    "content_data_plan": 1,
    "interaction_contract": 0,
    "component_dependency_graph": 0,
}

# Calls reserved for a later stage until that stage resolves.
# The reservation prevents earlier stages from exhausting the global budget
# before later required stages have had a chance to run.
_SUBSTAGE_RESERVATION: dict[str, int] = {
    "content_data_plan": 1,
}


@dataclass
class LedgerEvent:
    kind: str  # approved | denied | cache_hit | deterministic_success | reservation_released | ...
    stage: str
    wall_elapsed_ms: int
    attempt_type: str = ""   # ai | deterministic | cache
    used_before: int = 0
    reserved_before: int = 0
    failure_code: str = ""


class Phase3ACallBudget:
    """Append-only call ledger that enforces per-substage and global limits.

    All approve / release_reservation / record_* calls append events; the
    ledger can be serialised with snapshot() and fully reconstructed from
    those events with reconstruct_from_events().
    """

    def __init__(self) -> None:
        self.total_max: int = settings.V2_COMPOSITION_CONTRACT_MAX_CALLS
        self._substage_caps: dict[str, int] = dict(_SUBSTAGE_CAPS)
        # Remaining reservations per stage (counts down as calls are approved
        # or reservations are explicitly released).
        self._reservations: dict[str, int] = dict(_SUBSTAGE_RESERVATION)
        self._used: dict[str, int] = dict.fromkeys(_SUBSTAGE_CAPS, 0)
        self._total_used: int = 0
        self._total_reserved: int = sum(_SUBSTAGE_RESERVATION.values())
        self._events: list[LedgerEvent] = []
        self._started: float = time.monotonic()

    @classmethod
    def create(cls) -> "Phase3ACallBudget":
        return cls()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _wall_ms(self) -> int:
        return int((time.monotonic() - self._started) * 1000)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def approve(
        self,
        stage: str,
        *,
        attempt_type: str = "ai",
        wall_remaining: float | None = None,
    ) -> tuple[bool, str]:
        """Approve or deny a single provider call BEFORE it is made.

        Returns ``(approved, failure_code)``.  ``failure_code`` is the empty
        string on approval; one of the Phase3ABudgetCode literals on denial.

        Approval charges the call immediately (idempotent with the provider
        call that follows) and consumes any reservation held by *stage*.
        """
        used_before = self._total_used
        reserved_before = self._total_reserved

        substage_cap = self._substage_caps.get(stage, 0)
        stage_used = self._used.get(stage, 0)

        # Per-substage cap check
        if stage_used >= substage_cap:
            code: str = "phase3a_substage_call_budget_exhausted"
            self._events.append(LedgerEvent(
                kind="denied",
                stage=stage,
                wall_elapsed_ms=self._wall_ms(),
                attempt_type=attempt_type,
                used_before=used_before,
                reserved_before=reserved_before,
                failure_code=code,
            ))
            return False, code

        # Global cap check – this call (1) + reservations for OTHER stages
        # must not exceed total_max.
        own_reservation = self._reservations.get(stage, 0)
        other_reservations = self._total_reserved - own_reservation
        if self._total_used + 1 + other_reservations > self.total_max:
            code = "phase3a_total_call_budget_exhausted"
            self._events.append(LedgerEvent(
                kind="denied",
                stage=stage,
                wall_elapsed_ms=self._wall_ms(),
                attempt_type=attempt_type,
                used_before=used_before,
                reserved_before=reserved_before,
                failure_code=code,
            ))
            return False, code

        # --- Approved ---
        self._used[stage] = stage_used + 1
        self._total_used += 1
        # Consuming the reservation for this stage (if any) as the call is charged.
        if own_reservation > 0:
            self._reservations[stage] = own_reservation - 1
            self._total_reserved -= 1

        self._events.append(LedgerEvent(
            kind="approved",
            stage=stage,
            wall_elapsed_ms=self._wall_ms(),
            attempt_type=attempt_type,
            used_before=used_before,
            reserved_before=reserved_before,
        ))
        return True, ""

    def record_denied(
        self,
        stage: str,
        *,
        failure_code: str,
        attempt_type: str = "ai",
    ) -> None:
        """Record an externally-observed denial (informational)."""
        self._events.append(LedgerEvent(
            kind="denied_external",
            stage=stage,
            wall_elapsed_ms=self._wall_ms(),
            attempt_type=attempt_type,
            used_before=self._total_used,
            reserved_before=self._total_reserved,
            failure_code=failure_code,
        ))

    def record_cache_hit(self, stage: str) -> None:
        """Record a cache hit (0 provider calls, 0 budget charge)."""
        self._events.append(LedgerEvent(
            kind="cache_hit",
            stage=stage,
            wall_elapsed_ms=self._wall_ms(),
            attempt_type="cache",
            used_before=self._total_used,
            reserved_before=self._total_reserved,
        ))

    def record_deterministic(self, stage: str) -> None:
        """Record a successful deterministic execution (0 provider calls)."""
        self._events.append(LedgerEvent(
            kind="deterministic_success",
            stage=stage,
            wall_elapsed_ms=self._wall_ms(),
            attempt_type="deterministic",
            used_before=self._total_used,
            reserved_before=self._total_reserved,
        ))

    def release_reservation(self, stage: str) -> None:
        """Release an unused call reservation held for *stage*.

        Called when a stage resolves via deterministic projection and the
        reserved AI call is no longer needed.  Releases budget headroom for
        earlier stages (e.g. BCP repair) without consuming the reservation.
        """
        res = self._reservations.get(stage, 0)
        if res <= 0:
            return
        before_reserved = self._total_reserved
        self._reservations[stage] = res - 1
        self._total_reserved -= 1
        self._events.append(LedgerEvent(
            kind="reservation_released",
            stage=stage,
            wall_elapsed_ms=self._wall_ms(),
            attempt_type="deterministic",
            used_before=self._total_used,
            reserved_before=before_reserved,
        ))

    # ------------------------------------------------------------------
    # Serialisation / reconstruction
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Return a JSON-serialisable snapshot of the full ledger."""
        return {
            "policy_revision": PHASE3A_CALL_BUDGET_POLICY_REVISION,
            "total_max": self.total_max,
            "total_used": self._total_used,
            "total_reserved": self._total_reserved,
            "substage_caps": dict(self._substage_caps),
            "substage_used": dict(self._used),
            "reservations": dict(self._reservations),
            "events": [
                {
                    "kind": e.kind,
                    "stage": e.stage,
                    "wall_elapsed_ms": e.wall_elapsed_ms,
                    "attempt_type": e.attempt_type,
                    "used_before": e.used_before,
                    "reserved_before": e.reserved_before,
                    "failure_code": e.failure_code,
                }
                for e in self._events
            ],
        }

    @classmethod
    def reconstruct_from_events(
        cls,
        events: list[dict],
        *,
        total_max: int | None = None,
    ) -> "Phase3ACallBudget":
        """Reconstruct budget state by replaying a persisted event list.

        Suitable for idempotent restart: the reconstructed budget reflects
        exactly the calls that were approved in a prior run.
        """
        budget = cls()
        if total_max is not None:
            budget.total_max = total_max
        # Reset to initial state then replay
        budget._used = dict.fromkeys(_SUBSTAGE_CAPS, 0)
        budget._total_used = 0
        budget._reservations = dict(_SUBSTAGE_RESERVATION)
        budget._total_reserved = sum(_SUBSTAGE_RESERVATION.values())
        budget._events = []

        for event in events:
            kind = event.get("kind", "")
            stage = event.get("stage", "")
            if kind == "approved":
                budget._used[stage] = budget._used.get(stage, 0) + 1
                budget._total_used += 1
                res = budget._reservations.get(stage, 0)
                if res > 0:
                    budget._reservations[stage] = res - 1
                    budget._total_reserved -= 1
            elif kind == "reservation_released":
                res = budget._reservations.get(stage, 0)
                if res > 0:
                    budget._reservations[stage] = res - 1
                    budget._total_reserved -= 1
            budget._events.append(LedgerEvent(
                kind=kind,
                stage=stage,
                wall_elapsed_ms=event.get("wall_elapsed_ms", 0),
                attempt_type=event.get("attempt_type", ""),
                used_before=event.get("used_before", 0),
                reserved_before=event.get("reserved_before", 0),
                failure_code=event.get("failure_code", ""),
            ))

        return budget


__all__ = [
    "PHASE3A_CALL_BUDGET_POLICY_REVISION",
    "LedgerEvent",
    "Phase3ACallBudget",
    "Phase3ABudgetCode",
]
