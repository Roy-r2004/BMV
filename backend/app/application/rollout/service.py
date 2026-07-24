"""Phase 7A rollout application service — advisory + read-only only.

There is intentionally no promote/rollback/pointer-swap executor here.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.application.rollout.audit import append_audit_event
from app.application.rollout.authorization import (
    reject_client_supplied_roles,
    require_permission,
)
from app.application.rollout.eligibility import (
    EligibilityInputs,
    compute_promotion_eligibility,
    eligibility_authorizes_write,
)
from app.application.rollout.pointer import resolve_serving_pointer
from app.application.rollout.policy import build_policy_view
from app.application.rollout.repository import RolloutRepository
from app.core.config import settings
from app.domain.schemas.rollout import (
    PromotionEligibilityResult,
    RolloutPolicyView,
    ServingPointerView,
    TrustedRolloutActor,
)


class RolloutControlPlaneService:
    """Diagnostic/control-plane surface for Phase 7A."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = RolloutRepository(db)

    def current_env_policy_view(self, actor: TrustedRolloutActor) -> RolloutPolicyView:
        require_permission(actor, "read_diagnostics")
        return build_policy_view(
            policy_revision=settings.V2_PHASE7_POLICY_REVISION,
            master_enabled=settings.V2_PHASE7_ROLLOUT_ENABLED,
            shadow_enabled=settings.V2_PHASE7_SHADOW_ENABLED,
            promote_enabled=settings.V2_PHASE7_PROMOTE_ENABLED,
            rollout_percent=settings.V2_PHASE7_ROLLOUT_PERCENT,
            allowlist=settings.V2_PHASE7_REQUEST_ALLOWLIST,
            rollout_salt=settings.V2_PHASE7_ROLLOUT_SALT,
            created_actor_id=actor.actor_id,
            created_actor_role=actor.roles[0],
        )

    def resolve_pointer(
        self, *, actor: TrustedRolloutActor, request_id: int
    ) -> ServingPointerView:
        require_permission(actor, "read_diagnostics")
        view = resolve_serving_pointer(self._db, request_id)
        append_audit_event(
            self._db,
            request_id=request_id,
            event_type="pointer_resolved",
            actor_id=actor.actor_id,
            actor_role=actor.roles[0],
            policy_revision=settings.V2_PHASE7_POLICY_REVISION,
            metadata={"target_kind": view.target_kind},
        )
        return view

    def compute_eligibility(
        self,
        *,
        actor: TrustedRolloutActor,
        inputs: EligibilityInputs,
        client_payload: dict | None = None,
    ) -> PromotionEligibilityResult:
        if client_payload is not None:
            reject_client_supplied_roles(client_payload)
        require_permission(actor, "compute_promotion_eligibility")
        # Always recompute from the provided current-state inputs.
        result = compute_promotion_eligibility(inputs)
        assert eligibility_authorizes_write(result) is False
        append_audit_event(
            self._db,
            request_id=inputs.request_id,
            event_type="eligibility_computed",
            actor_id=actor.actor_id,
            actor_role=actor.roles[0],
            policy_revision=inputs.policy.policy_revision,
            metadata={
                "eligibility_sha256": result.eligibility_sha256,
                "eligible_for_promote": result.eligible_for_promote,
                "advisory_only": True,
            },
        )
        return result

    def create_policy_version(
        self, *, actor: TrustedRolloutActor, view: RolloutPolicyView
    ):
        row = self._repo.insert_policy_version(actor=actor, view=view)
        append_audit_event(
            self._db,
            request_id=None,
            event_type="rollout_policy_changed",
            actor_id=actor.actor_id,
            actor_role=actor.roles[0],
            policy_revision=view.policy_revision,
            metadata={"configuration_sha256": view.configuration_sha256},
        )
        return row

    # Explicit absences — structural proof for tests.
    def promote(self, *args, **kwargs):  # noqa: ANN001
        raise RuntimeError("Phase 7A has no promote executor")

    def rollback(self, *args, **kwargs):  # noqa: ANN001
        raise RuntimeError("Phase 7A has no rollback executor")

    def apply_pointer_swap(self, *args, **kwargs):  # noqa: ANN001
        raise RuntimeError("Phase 7A has no pointer-swap executor")


__all__ = ["RolloutControlPlaneService"]
