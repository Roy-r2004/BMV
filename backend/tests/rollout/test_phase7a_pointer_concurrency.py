"""Pointer unique-index-safe transaction ordering simulations."""
from __future__ import annotations

from sqlalchemy import text

from tests.rollout.harness import Phase7ATestOnlyRolloutHarness
from tests.rollout.helpers import (
    dispose,
    enable_test_only_mode,
    make_rollout_engine,
    make_session,
)


def test_future_safe_pointer_swap_sequence_and_rollback() -> None:
    enable_test_only_mode()
    engine, root = make_rollout_engine()
    db = make_session(engine)
    harness = Phase7ATestOnlyRolloutHarness(db, enabled=True)

    # Initialize legacy pointer via harness as version 1
    result = harness.simulate_pointer_swap_transaction(
        request_id=1,
        expected_previous_version=None,
        new_pointer_version=1,
        target_kind="legacy_v1",
        pointer_action="initialize",
        actor_id="tester",
        policy_revision="2026-07-25.1",
        legacy_preview_relpath="previews/1",
    )
    assert result["rolled_back"] is False

    # Failed swap must roll back previous-pointer update, new pointer,
    # decision transition, and audit together.
    db2 = make_session(engine)
    harness2 = Phase7ATestOnlyRolloutHarness(db2, enabled=True)
    rolled = harness2.simulate_pointer_swap_transaction(
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
        fail_before_commit=True,
    )
    assert rolled["rolled_back"] is True

    with engine.connect() as conn:
        currents = conn.execute(
            text(
                "SELECT pointer_version, is_current, target_kind "
                "FROM preview_serving_pointer_versions WHERE request_id=1"
            )
        ).all()
        assert currents == [(1, 1, "legacy_v1")]
        decisions = conn.execute(
            text("SELECT decision_status FROM preview_promotion_decisions")
        ).all()
        # Only the successful initialize decision remains (requested);
        # applied is tracked via status events for that decision.
        assert len(decisions) == 1
        events = conn.execute(
            text(
                "SELECT status FROM preview_promotion_decision_status_events"
            )
        ).all()
        assert events == [("applied",)]

    # Version conflict leaves zero partial rows
    db3 = make_session(engine)
    harness3 = Phase7ATestOnlyRolloutHarness(db3, enabled=True)
    try:
        harness3.simulate_pointer_swap_transaction(
            request_id=1,
            expected_previous_version=99,
            new_pointer_version=2,
            target_kind="v2_candidate",
            pointer_action="promote",
            actor_id="tester",
            policy_revision="2026-07-25.1",
            candidate_revision_id=7,
        )
    except Exception as exc:
        assert "version conflict" in str(exc)
    else:
        raise AssertionError("expected version conflict")

    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT COUNT(*) FROM preview_serving_pointer_versions")
        ).scalar() == 1
        assert (
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM preview_serving_pointer_versions "
                    "WHERE is_current=1"
                )
            ).scalar()
            == 1
        )

    # Successful promote never temporarily needs two current rows:
    # previous is marked non-current before new current insert.
    db4 = make_session(engine)
    harness4 = Phase7ATestOnlyRolloutHarness(db4, enabled=True)
    ok = harness4.simulate_pointer_swap_transaction(
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
    assert ok["pointer_version"] == 2
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT pointer_version, is_current FROM "
                "preview_serving_pointer_versions WHERE request_id=1 "
                "ORDER BY pointer_version"
            )
        ).all()
        assert rows == [(1, 0), (2, 1)]

    db.close()
    db2.close()
    db3.close()
    db4.close()
    dispose(engine, root)


def test_partial_unique_index_rejects_two_current_rows() -> None:
    enable_test_only_mode()
    engine, root = make_rollout_engine()
    db = make_session(engine)
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
    with engine.connect() as conn:
        try:
            with conn.begin():
                conn.execute(
                    text(
                        "INSERT INTO preview_serving_pointer_versions ("
                        "request_id,pointer_version,target_kind,"
                        "legacy_preview_relpath,pointer_action,actor_id,"
                        "policy_revision,created_at,is_current,pointer_sha256"
                        ") VALUES ("
                        "1,2,'legacy_v1','x','initialize','t','p',"
                        "'2026-07-25',1,:sha)"
                    ),
                    {"sha": "d" * 64},
                )
        except Exception:
            pass
        else:
            raise AssertionError("partial unique index allowed two current rows")
    db.close()
    dispose(engine, root)
