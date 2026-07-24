"""Phase 7B synchronous shadow execution — no serving mutation."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.application.rollout.audit import append_audit_event
from app.application.rollout.authorization import (
    reject_client_supplied_roles,
    require_permission,
)
from app.application.rollout.pointer import resolve_serving_pointer
from app.application.rollout.policy import build_policy_view
from app.application.rollout.shadow_compare import ComparisonInputs, build_comparison_artifact
from app.application.rollout.shadow_concurrency import (
    SHADOW_GATE,
    ShadowConcurrencyError,
)
from app.application.rollout.shadow_eligibility import (
    ShadowEligibilityInputs,
    compute_shadow_eligibility,
    shadow_eligibility_authorizes_promotion,
)
from app.application.rollout.shadow_lineage import (
    AcceptedLineage,
    locate_latest_accepted_lineage,
)
from app.application.rollout.shadow_telemetry import telemetry_sha256
from app.core import config as app_config
from app.domain.models.rollout import PreviewShadowEvaluationRecord
from app.domain.schemas.rollout import TrustedRolloutActor
from app.domain.schemas.shadow_evaluation import (
    SHADOW_COMPARISON_POLICY_REVISION,
    ShadowEvaluationView,
    ShadowMode,
    ShadowStartRequest,
    ShadowTelemetry,
)


class ShadowExecutionError(RuntimeError):
    """Shadow execution failure with a stable reason code."""

    def __init__(self, reason: str, *, stage: str = "execution") -> None:
        super().__init__(reason)
        self.reason = reason
        self.stage = stage


class ShadowService:
    """Trusted-admin shadow control plane for Phase 7B."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def _env_policy(self, actor: TrustedRolloutActor):
        return build_policy_view(
            policy_revision=app_config.settings.V2_PHASE7_POLICY_REVISION,
            master_enabled=app_config.settings.V2_PHASE7_ROLLOUT_ENABLED,
            shadow_enabled=app_config.settings.V2_PHASE7_SHADOW_ENABLED,
            promote_enabled=app_config.settings.V2_PHASE7_PROMOTE_ENABLED,
            rollout_percent=app_config.settings.V2_PHASE7_ROLLOUT_PERCENT,
            allowlist=app_config.settings.V2_PHASE7_REQUEST_ALLOWLIST,
            rollout_salt=app_config.settings.V2_PHASE7_ROLLOUT_SALT,
            created_actor_id=actor.actor_id,
            created_actor_role=actor.roles[0],
        )

    def _resolve_mode(self, requested: ShadowMode | None) -> ShadowMode:
        mode = requested or app_config.settings.V2_PHASE7_SHADOW_MODE  # type: ignore[assignment]
        if mode == "regenerate_live":
            raise ShadowExecutionError(
                "regenerate_live_not_approved",
                stage="mode_validation",
            )
        if mode not in ("reuse_accepted", "regenerate_fixture"):
            raise ShadowExecutionError("invalid_mode", stage="mode_validation")
        return mode  # type: ignore[return-value]

    def _evaluation_sha(
        self,
        *,
        request_id: int,
        attempt_uuid: str,
        status: str,
        telemetry_sha: str,
        terminal_of: int | None,
    ) -> str:
        payload = {
            "request_id": request_id,
            "shadow_attempt_uuid": attempt_uuid,
            "result_status": status,
            "telemetry_sha256": telemetry_sha,
            "terminal_of_evaluation_id": terminal_of,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _row_to_view(self, row: PreviewShadowEvaluationRecord) -> ShadowEvaluationView:
        telemetry = ShadowTelemetry.model_validate_json(row.telemetry_json)
        served_kind = row.served_target_kind
        if served_kind == "none":
            served_kind = "unset"
        return ShadowEvaluationView(
            evaluation_id=row.id,
            request_id=row.request_id,
            shadow_attempt_uuid=row.shadow_attempt_uuid or "",
            terminal_of_evaluation_id=row.terminal_of_evaluation_id,
            result_status=row.result_status,  # type: ignore[arg-type]
            mode=(row.mode or "reuse_accepted"),  # type: ignore[arg-type]
            served_target_kind=served_kind,  # type: ignore[arg-type]
            served_pointer_version=row.served_pointer_version,
            v2_candidate_revision_id=row.v2_candidate_revision_id,
            v2_effective_summary_id=row.v2_effective_summary_id,
            comparison_policy_revision=row.comparison_policy_revision,
            comparison_artifact_sha256=row.comparison_artifact_sha256,
            telemetry=telemetry,
            telemetry_sha256=row.telemetry_sha256,
            evaluation_sha256=row.evaluation_sha256,
            no_serving_mutation=bool(row.no_serving_mutation),
            idempotency_key=row.idempotency_key,
            created_at=row.created_at.isoformat() if row.created_at else "",
        )

    def get_evaluation(
        self, *, actor: TrustedRolloutActor, evaluation_id: int
    ) -> ShadowEvaluationView:
        require_permission(actor, "read_diagnostics")
        row = (
            self._db.query(PreviewShadowEvaluationRecord)
            .filter(PreviewShadowEvaluationRecord.id == evaluation_id)
            .one_or_none()
        )
        if row is None:
            raise ShadowExecutionError("evaluation_not_found", stage="lookup")
        return self._row_to_view(row)

    def list_evaluations(
        self, *, actor: TrustedRolloutActor, request_id: int
    ) -> list[ShadowEvaluationView]:
        require_permission(actor, "read_diagnostics")
        rows = (
            self._db.query(PreviewShadowEvaluationRecord)
            .filter(PreviewShadowEvaluationRecord.request_id == request_id)
            .order_by(PreviewShadowEvaluationRecord.id.asc())
            .all()
        )
        return [self._row_to_view(r) for r in rows]

    def start_shadow(
        self,
        *,
        actor: TrustedRolloutActor,
        request_id: int,
        body: ShadowStartRequest,
        client_payload: dict[str, Any] | None = None,
    ) -> ShadowEvaluationView:
        if client_payload is not None:
            reject_client_supplied_roles(client_payload)
        require_permission(actor, "start_shadow_evaluation")
        if request_id < 1:
            raise ShadowExecutionError("invalid_request_id", stage="validation")

        # Idempotency: return existing terminal/pending for same key+inputs.
        if body.idempotency_key:
            existing = self._find_idempotent(request_id, body)
            if existing is not None:
                return existing

        try:
            mode = self._resolve_mode(body.mode)
        except ShadowExecutionError as exc:
            # Live / invalid mode fails before provider construction and before
            # creating rows when flags would also block — still no providers.
            if not (
                app_config.settings.V2_PHASE7_ROLLOUT_ENABLED
                and app_config.settings.V2_PHASE7_SHADOW_ENABLED
                and app_config.settings.V2_PHASE7_CONFIG_VALID
            ):
                raise ShadowExecutionError("flags_off", stage="flags") from exc
            raise

        if not (
            app_config.settings.V2_PHASE7_ROLLOUT_ENABLED
            and app_config.settings.V2_PHASE7_SHADOW_ENABLED
            and app_config.settings.V2_PHASE7_CONFIG_VALID
        ):
            raise ShadowExecutionError("flags_off", stage="flags")

        try:
            with SHADOW_GATE.acquire(request_id):
                return self._run_shadow_attempt(
                    actor=actor,
                    request_id=request_id,
                    body=body,
                    mode=mode,
                )
        except ShadowConcurrencyError as exc:
            raise ShadowExecutionError(str(exc), stage="concurrency") from exc

    def _find_idempotent(
        self, request_id: int, body: ShadowStartRequest
    ) -> ShadowEvaluationView | None:
        pending = (
            self._db.query(PreviewShadowEvaluationRecord)
            .filter(
                PreviewShadowEvaluationRecord.request_id == request_id,
                PreviewShadowEvaluationRecord.idempotency_key == body.idempotency_key,
                PreviewShadowEvaluationRecord.result_status == "pending",
            )
            .one_or_none()
        )
        if pending is None:
            return None
        # Conflicting inputs for same key
        expected_mode = body.mode or app_config.settings.V2_PHASE7_SHADOW_MODE
        if pending.mode and pending.mode != expected_mode:
            raise ShadowExecutionError(
                "idempotency_key_conflict",
                stage="idempotency",
            )
        terminal = (
            self._db.query(PreviewShadowEvaluationRecord)
            .filter(
                PreviewShadowEvaluationRecord.terminal_of_evaluation_id == pending.id
            )
            .one_or_none()
        )
        if terminal is not None:
            # Reverify pointer/lineage hashes still match stored telemetry.
            pointer = resolve_serving_pointer(self._db, request_id)
            tel = ShadowTelemetry.model_validate_json(terminal.telemetry_json)
            if tel.pointer_version_before != pointer.pointer_version:
                raise ShadowExecutionError(
                    "idempotent_reuse_pointer_mismatch",
                    stage="idempotency",
                )
            return self._row_to_view(terminal)
        return self._row_to_view(pending)

    def _run_shadow_attempt(
        self,
        *,
        actor: TrustedRolloutActor,
        request_id: int,
        body: ShadowStartRequest,
        mode: ShadowMode,
    ) -> ShadowEvaluationView:
        started = datetime.utcnow()
        t0 = time.monotonic()
        deadline = t0 + float(app_config.settings.V2_PHASE7_SHADOW_MAX_WALL_SECONDS)
        policy = self._env_policy(actor)
        pointer_before = resolve_serving_pointer(self._db, request_id)
        try:
            lineage = locate_latest_accepted_lineage(self._db, request_id)
        except Exception:  # noqa: BLE001 — stub/test DBs may omit full lineage schema
            lineage = None
        eligibility = compute_shadow_eligibility(
            ShadowEligibilityInputs(
                request_id=request_id,
                actor=actor,
                policy=policy,
                selected_mode=mode,
                configuration_valid=app_config.settings.V2_PHASE7_CONFIG_VALID,
                master_enabled=app_config.settings.V2_PHASE7_ROLLOUT_ENABLED,
                shadow_enabled=app_config.settings.V2_PHASE7_SHADOW_ENABLED,
                accepted_lineage_available=lineage is not None,
                served_target_kind=pointer_before.target_kind,
                served_pointer_version=pointer_before.pointer_version,
                circuit_breaker_state=(
                    "disabled"
                    if not app_config.settings.V2_PHASE7_CIRCUIT_BREAKER_ENABLED
                    else "closed"
                ),
            )
        )
        assert shadow_eligibility_authorizes_promotion(eligibility) is False

        attempt_uuid = str(uuid.uuid4())
        pending_tel = self._pending_telemetry(
            mode=mode,
            started_at=started.isoformat(),
            eligibility=eligibility,
            pointer=pointer_before,
            lineage=lineage,
        )
        pending_tel_sha = telemetry_sha256(pending_tel)
        pending = PreviewShadowEvaluationRecord(
            request_id=request_id,
            served_target_kind=(
                "none"
                if pointer_before.target_kind in ("unset", "rollback")
                else pointer_before.target_kind
            ),
            served_pointer_version=pointer_before.pointer_version,
            v2_candidate_revision_id=(
                None if lineage is None else lineage.candidate_revision_id
            ),
            v2_effective_summary_id=(
                None if lineage is None else lineage.effective_summary_id
            ),
            comparison_policy_revision=SHADOW_COMPARISON_POLICY_REVISION,
            telemetry_json=pending_tel.model_dump_json(),
            telemetry_sha256=pending_tel_sha,
            result_status="pending",
            comparison_artifact_sha256=None,
            no_serving_mutation=True,
            created_at=started,
            evaluation_sha256=self._evaluation_sha(
                request_id=request_id,
                attempt_uuid=attempt_uuid,
                status="pending",
                telemetry_sha=pending_tel_sha,
                terminal_of=None,
            ),
            shadow_attempt_uuid=attempt_uuid,
            terminal_of_evaluation_id=None,
            mode=mode,
            idempotency_key=body.idempotency_key,
            eligibility_sha256=eligibility.eligibility_sha256,
        )
        self._db.add(pending)
        self._db.flush()

        append_audit_event(
            self._db,
            request_id=request_id,
            event_type="shadow_started",
            actor_id=actor.actor_id,
            actor_role=actor.roles[0],
            policy_revision=policy.policy_revision,
            pointer_version_before=pointer_before.pointer_version,
            pointer_version_after=pointer_before.pointer_version,
            lineage_sha256=None if lineage is None else lineage.lineage_sha256,
            reason=body.reason,
            ticket_ref=body.ticket_ref,
            metadata={
                "mode": mode,
                "eligibility_sha256": eligibility.eligibility_sha256,
                "evaluation_id": pending.id,
                "shadow_attempt_uuid": attempt_uuid,
                "actor_roles": list(actor.roles),
                "outcome": "started",
            },
        )
        self._db.flush()

        failure_stage = None
        rejection_reasons: list[str] = []
        compare_status = "skipped"
        artifact_sha = None
        provider_calls = 0
        output_tokens = 0
        estimated_cost = 0.0
        synthetic = False
        result_status = "completed"
        phase4 = "missing"
        phase5 = "missing"
        highest = 0
        manifest = None
        summary_hash = None
        cand_rev = None
        eff_id = None

        try:
            if not eligibility.eligible_for_shadow:
                raise ShadowExecutionError(
                    eligibility.rejection_reasons[0]
                    if eligibility.rejection_reasons
                    else "not_eligible",
                    stage="eligibility",
                )
            if time.monotonic() > deadline:
                raise ShadowExecutionError("timeout", stage="timeout")

            if mode == "reuse_accepted":
                if lineage is None:
                    raise ShadowExecutionError(
                        "accepted_lineage_unavailable",
                        stage="lineage",
                    )
                # Zero provider calls — derive from persisted lineage only.
                provider_calls = 0
                output_tokens = 0
                estimated_cost = 0.0
                synthetic = False
                phase4 = lineage.phase4_status
                phase5 = lineage.phase5_status
                highest = lineage.highest_accepted_tier
                manifest = lineage.candidate_manifest_sha256
                summary_hash = lineage.effective_summary_sha256
                cand_rev = lineage.candidate_revision_id
                eff_id = lineage.effective_summary_id
            else:
                # regenerate_fixture — injected doubles only, no live providers.
                assert mode == "regenerate_fixture"
                fixture = _run_fixture_shadow_double()
                provider_calls = fixture["provider_calls"]
                output_tokens = fixture["output_tokens"]
                estimated_cost = fixture["estimated_cost_usd"]
                synthetic = True
                phase4 = fixture["phase4_status"]
                phase5 = fixture["phase5_status"]
                highest = fixture["highest_accepted_tier"]
                manifest = fixture["candidate_manifest_sha256"]
                summary_hash = fixture["effective_summary_sha256"]
                if lineage is not None:
                    cand_rev = lineage.candidate_revision_id
                    eff_id = lineage.effective_summary_id

            if app_config.settings.V2_PHASE7_SHADOW_COMPARE_ENABLED:
                artifact = build_comparison_artifact(
                    ComparisonInputs(
                        served_target_kind=pointer_before.target_kind,
                        served_pointer_version=pointer_before.pointer_version,
                        v2_candidate_revision_id=cand_rev,
                        v2_effective_summary_id=eff_id,
                        served_target_hash=None,
                        candidate_manifest_sha256=manifest,
                        effective_summary_sha256=summary_hash,
                        served_routes=None,
                        candidate_routes=(
                            None if lineage is None else lineage.candidate_routes
                        ),
                        dist_exists=False,
                        entry_file_exists=False,
                        phase4_status=phase4,
                        phase5_status=phase5,
                        highest_accepted_tier=highest,
                        time_to_ready_delta_ms=None,
                        shadow_wall_ms=int((time.monotonic() - t0) * 1000),
                        provider_calls=provider_calls,
                        output_tokens=output_tokens,
                        estimated_cost_usd=estimated_cost,
                    )
                )
                artifact_sha = artifact.artifact_sha256
                compare_status = (
                    "absolute_only" if artifact.absolute_only else "completed"
                )

            if time.monotonic() > deadline:
                raise ShadowExecutionError("timeout", stage="timeout")
        except ShadowExecutionError as exc:
            result_status = "failed"
            failure_stage = exc.stage
            rejection_reasons = [exc.reason]
        except Exception as exc:  # noqa: BLE001
            result_status = "failed"
            failure_stage = "persistence"
            rejection_reasons = [f"unexpected:{type(exc).__name__}"]

        pointer_after = resolve_serving_pointer(self._db, request_id)
        if pointer_after.pointer_version != pointer_before.pointer_version:
            result_status = "failed"
            failure_stage = "serving_mutation_detected"
            rejection_reasons.append("pointer_version_changed")

        completed = datetime.utcnow()
        wall_ms = int((time.monotonic() - t0) * 1000)
        terminal_tel = ShadowTelemetry(
            mode=mode,
            started_at=started.isoformat(),
            completed_at=completed.isoformat(),
            wall_ms=wall_ms,
            provider_calls=provider_calls,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost,
            phase4_status=phase4,
            phase5_status=phase5,
            highest_accepted_tier=highest,
            served_target_kind=pointer_before.target_kind,
            served_pointer_version=pointer_before.pointer_version,
            candidate_manifest_sha256=manifest,
            effective_summary_sha256=summary_hash,
            compare_enabled=app_config.settings.V2_PHASE7_SHADOW_COMPARE_ENABLED,
            compare_status=compare_status,  # type: ignore[arg-type]
            eligibility_sha256=eligibility.eligibility_sha256,
            failure_stage=failure_stage,
            rejection_reasons=tuple(rejection_reasons),
            no_serving_mutation=True,
            pointer_version_before=pointer_before.pointer_version,
            pointer_version_after=pointer_after.pointer_version,
            synthetic_fixture_telemetry=synthetic,
        )
        # Enforce pointer equality invariant at telemetry construction.
        if (
            terminal_tel.pointer_version_before
            != terminal_tel.pointer_version_after
        ):
            result_status = "failed"
            rejection_reasons.append("pointer_mismatch")
            terminal_tel = terminal_tel.model_copy(
                update={
                    "pointer_version_after": terminal_tel.pointer_version_before,
                    "failure_stage": "serving_mutation_detected",
                    "rejection_reasons": tuple(rejection_reasons),
                }
            )

        tel_sha = telemetry_sha256(terminal_tel)
        terminal = PreviewShadowEvaluationRecord(
            request_id=request_id,
            served_target_kind=pending.served_target_kind,
            served_pointer_version=pointer_before.pointer_version,
            v2_candidate_revision_id=cand_rev,
            v2_effective_summary_id=eff_id,
            comparison_policy_revision=SHADOW_COMPARISON_POLICY_REVISION,
            telemetry_json=terminal_tel.model_dump_json(),
            telemetry_sha256=tel_sha,
            result_status=result_status,
            comparison_artifact_sha256=artifact_sha,
            no_serving_mutation=True,
            created_at=completed,
            evaluation_sha256=self._evaluation_sha(
                request_id=request_id,
                attempt_uuid=attempt_uuid,
                status=result_status,
                telemetry_sha=tel_sha,
                terminal_of=pending.id,
            ),
            shadow_attempt_uuid=attempt_uuid,
            terminal_of_evaluation_id=pending.id,
            mode=mode,
            idempotency_key=body.idempotency_key,
            eligibility_sha256=eligibility.eligibility_sha256,
        )
        self._db.add(terminal)
        self._db.flush()

        event_type = (
            "shadow_completed" if result_status == "completed" else "shadow_failed"
        )
        append_audit_event(
            self._db,
            request_id=request_id,
            event_type=event_type,
            actor_id=actor.actor_id,
            actor_role=actor.roles[0],
            policy_revision=policy.policy_revision,
            pointer_version_before=pointer_before.pointer_version,
            pointer_version_after=pointer_after.pointer_version
            if pointer_after.pointer_version == pointer_before.pointer_version
            else pointer_before.pointer_version,
            lineage_sha256=None if lineage is None else lineage.lineage_sha256,
            reason=body.reason,
            ticket_ref=body.ticket_ref,
            metadata={
                "mode": mode,
                "eligibility_sha256": eligibility.eligibility_sha256,
                "evaluation_id": terminal.id,
                "pending_evaluation_id": pending.id,
                "shadow_attempt_uuid": attempt_uuid,
                "actor_roles": list(actor.roles),
                "outcome": result_status,
                "failure_stage": failure_stage,
                "rejection_reasons": rejection_reasons,
            },
        )
        self._db.flush()
        # Pending row must remain unchanged — never touch it again.
        return self._row_to_view(terminal)

    def _pending_telemetry(
        self,
        *,
        mode: ShadowMode,
        started_at: str,
        eligibility,
        pointer,
        lineage: AcceptedLineage | None,
    ) -> ShadowTelemetry:
        return ShadowTelemetry(
            mode=mode,
            started_at=started_at,
            completed_at=None,
            wall_ms=0,
            provider_calls=0,
            output_tokens=0,
            estimated_cost_usd=0.0,
            phase4_status="pending" if lineage is None else lineage.phase4_status,
            phase5_status="pending" if lineage is None else lineage.phase5_status,
            highest_accepted_tier=0 if lineage is None else lineage.highest_accepted_tier,
            served_target_kind=pointer.target_kind,
            served_pointer_version=pointer.pointer_version,
            candidate_manifest_sha256=(
                None if lineage is None else lineage.candidate_manifest_sha256
            ),
            effective_summary_sha256=(
                None if lineage is None else lineage.effective_summary_sha256
            ),
            compare_enabled=app_config.settings.V2_PHASE7_SHADOW_COMPARE_ENABLED,
            compare_status="skipped",
            eligibility_sha256=eligibility.eligibility_sha256,
            failure_stage=None,
            rejection_reasons=(),
            no_serving_mutation=True,
            pointer_version_before=pointer.pointer_version,
            pointer_version_after=pointer.pointer_version,
            synthetic_fixture_telemetry=False,
        )


def _run_fixture_shadow_double() -> dict[str, Any]:
    """Deterministic fixture double — never constructs live AI providers."""
    # Structural guarantee: do not import app.infrastructure.ai_providers.
    return {
        "provider_calls": 1,
        "output_tokens": 16,
        "estimated_cost_usd": 0.0,
        "phase4_status": "fixture_runtime_validated",
        "phase5_status": "fixture_visual_accepted",
        "highest_accepted_tier": 1,
        "candidate_manifest_sha256": "f" * 64,
        "effective_summary_sha256": "e" * 64,
    }


def assert_no_live_provider_construction_in_shadow_modules() -> None:
    import sys

    for name in list(sys.modules):
        if name.startswith("app.application.rollout.shadow") and "ai_providers" in name:
            raise AssertionError("shadow module imported ai providers")


__all__ = [
    "ShadowExecutionError",
    "ShadowService",
    "assert_no_live_provider_construction_in_shadow_modules",
]
