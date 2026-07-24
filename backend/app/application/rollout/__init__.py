"""Phase 7A rollout control plane — advisory eligibility and read-only resolution.

No production write executor for promotion, rollback, or pointer swap exists in
this package. Test-only mutation helpers live under tests/rollout/.
"""

from app.application.rollout.eligibility import compute_promotion_eligibility
from app.application.rollout.pointer import resolve_serving_pointer
from app.application.rollout.shadow_service import ShadowService
from app.application.rollout.targeting import compute_sticky_bucket

__all__ = [
    "ShadowService",
    "compute_promotion_eligibility",
    "compute_sticky_bucket",
    "resolve_serving_pointer",
]
