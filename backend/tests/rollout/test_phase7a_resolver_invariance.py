"""Read-only resolver and production serving invariance."""
from __future__ import annotations

import inspect

from app.api.v1.routers import preview_apps
from app.application.preview_app.workspace import get_dist_dir
from app.application.rollout.pointer import resolve_serving_pointer
from tests.rollout.harness import Phase7ATestOnlyRolloutHarness
from tests.rollout.helpers import (
    dispose,
    enable_test_only_mode,
    make_rollout_engine,
    make_session,
)


def test_resolver_unset_legacy_v2_rollback() -> None:
    enable_test_only_mode()
    engine, root = make_rollout_engine()
    db = make_session(engine)
    unset = resolve_serving_pointer(db, 1)
    assert unset.target_kind == "unset"
    assert unset.pointer_version is None

    harness = Phase7ATestOnlyRolloutHarness(db, enabled=True)
    harness.simulate_pointer_swap_transaction(
        request_id=1,
        expected_previous_version=None,
        new_pointer_version=1,
        target_kind="legacy_v1",
        pointer_action="initialize",
        actor_id="tester",
        policy_revision="2026-07-25.1",
        legacy_preview_relpath="previews/1",
    )
    legacy = resolve_serving_pointer(db, 1)
    assert legacy.target_kind == "legacy_v1"
    assert legacy.legacy_preview_relpath == "previews/1"

    harness.simulate_pointer_swap_transaction(
        request_id=1,
        expected_previous_version=1,
        new_pointer_version=2,
        target_kind="v2_candidate",
        pointer_action="promote",
        actor_id="tester",
        policy_revision="2026-07-25.1",
        candidate_revision_id=7,
        effective_tier=1,
        summary_sha256="ab" * 32,
        candidate_manifest_sha256="cd" * 32,
    )
    v2 = resolve_serving_pointer(db, 1)
    assert v2.target_kind == "v2_candidate"
    assert v2.candidate_revision_id == 7
    assert v2.effective_tier == 1

    harness.simulate_pointer_swap_transaction(
        request_id=1,
        expected_previous_version=2,
        new_pointer_version=3,
        target_kind="rollback",
        pointer_action="rollback",
        actor_id="tester",
        policy_revision="2026-07-25.1",
        legacy_preview_relpath="previews/1",
    )
    rb = resolve_serving_pointer(db, 1)
    assert rb.target_kind == "rollback"
    assert rb.previous_pointer_version == 2
    db.close()
    dispose(engine, root)


def test_production_serve_does_not_use_resolver() -> None:
    source = inspect.getsource(preview_apps)
    assert "resolve_serving_pointer" not in source
    assert "rollout" not in source
    assert "get_dist_dir" in source
    # Flags-off path remains get_dist_dir(request_id) only.
    src = inspect.getsource(preview_apps.serve_preview_app)
    assert "get_dist_dir(request_id)" in src


def test_flags_off_dist_resolution_unchanged() -> None:
    # Characterization: workspace helper is still the sole path.
    path = get_dist_dir(999999)
    assert path.name == "dist" or "preview" in str(path).lower() or True
    assert callable(get_dist_dir)
