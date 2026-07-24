"""Explicit transactional Phase 7A rollout migrations (SQLite + Postgres)."""
from __future__ import annotations

from typing import Literal

from sqlalchemy import Engine, inspect, text

PHASE7A_SCHEMA_VERSION = "phase7a.1"

PHASE7A_TABLES_CREATE_ORDER = (
    "preview_rollout_policies",
    "preview_live_canary_approvals",
    "preview_live_canary_approval_status_events",
    "preview_circuit_breaker_policies",
    "preview_circuit_breaker_states",
    "preview_promotion_decisions",
    "preview_promotion_decision_status_events",
    "preview_serving_pointer_versions",
    "preview_rollout_audit_events",
    "preview_shadow_evaluations",
    "preview_phase7a_schema_meta",
)

PHASE7A_TABLES_DROP_ORDER = tuple(reversed(PHASE7A_TABLES_CREATE_ORDER))

_STRICT_APPEND_ONLY_TABLES = (
    "preview_rollout_policies",
    "preview_promotion_decisions",
    "preview_promotion_decision_status_events",
    "preview_rollout_audit_events",
    "preview_shadow_evaluations",
    "preview_live_canary_approvals",
    "preview_live_canary_approval_status_events",
    "preview_circuit_breaker_policies",
    "preview_circuit_breaker_states",
)


def phase7a_schema_version(bind: Engine) -> str | None:
    with bind.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        if "preview_phase7a_schema_meta" not in tables:
            return None
        row = conn.execute(
            text(
                "SELECT schema_version FROM preview_phase7a_schema_meta "
                "ORDER BY id DESC LIMIT 1"
            )
        ).first()
        return None if row is None else str(row[0])


def _downgrade_guards(conn) -> None:
    tables = set(inspect(conn).get_table_names())
    if "preview_serving_pointer_versions" in tables:
        current_v2 = conn.execute(
            text(
                "SELECT COUNT(*) FROM preview_serving_pointer_versions "
                "WHERE is_current = 1 AND target_kind = 'v2_candidate'"
            )
        ).scalar()
        if current_v2:
            raise RuntimeError(
                "Phase 7A downgrade rejected: current v2 serving pointer exists"
            )
        any_pointer = conn.execute(
            text("SELECT COUNT(*) FROM preview_serving_pointer_versions")
        ).scalar()
        if any_pointer:
            raise RuntimeError(
                "Phase 7A downgrade rejected: serving pointer history must be preserved"
            )
    if "preview_promotion_decisions" in tables:
        applied = conn.execute(
            text(
                "SELECT COUNT(*) FROM preview_promotion_decisions "
                "WHERE decision_status IN ('applied','test_only_simulated')"
            )
        ).scalar()
        if applied:
            raise RuntimeError(
                "Phase 7A downgrade rejected: applied/simulated pointer dependency exists"
            )
    if "preview_promotion_decision_status_events" in tables:
        applied_events = conn.execute(
            text(
                "SELECT COUNT(*) FROM preview_promotion_decision_status_events "
                "WHERE status IN ('applied','test_only_simulated')"
            )
        ).scalar()
        if applied_events:
            raise RuntimeError(
                "Phase 7A downgrade rejected: applied status events must be preserved"
            )
    # Any Phase 7 history row blocks silent deletion.
    for table in PHASE7A_TABLES_CREATE_ORDER:
        if table == "preview_phase7a_schema_meta":
            continue
        if table not in tables:
            continue
        count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if count:
            raise RuntimeError(
                f"Phase 7A downgrade rejected: {table} contains history rows"
            )


def _sqlite_create_tables(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS preview_rollout_policies (
              id INTEGER PRIMARY KEY,
              policy_revision VARCHAR(64) NOT NULL UNIQUE,
              master_enabled BOOLEAN NOT NULL,
              shadow_enabled BOOLEAN NOT NULL,
              promote_enabled BOOLEAN NOT NULL,
              rollout_percent INTEGER NOT NULL
                CHECK (rollout_percent >= 0 AND rollout_percent <= 100),
              allowlist_json TEXT NOT NULL,
              allowlist_sha256 CHAR(64) NOT NULL,
              circuit_breaker_policy_json TEXT NOT NULL,
              circuit_breaker_policy_sha256 CHAR(64) NOT NULL,
              rollout_salt VARCHAR(128) NOT NULL,
              configuration_sha256 CHAR(64) NOT NULL UNIQUE,
              created_at TEXT NOT NULL,
              created_actor_id VARCHAR(128) NOT NULL,
              created_actor_role VARCHAR(64) NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS preview_live_canary_approvals (
              id INTEGER PRIMARY KEY,
              approval_uuid VARCHAR(36) NOT NULL UNIQUE,
              request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
              provider_model_allowlist_json TEXT NOT NULL,
              max_calls INTEGER NOT NULL,
              max_output_tokens INTEGER NOT NULL,
              max_cost_usd REAL NOT NULL,
              max_wall_seconds INTEGER NOT NULL,
              expires_at TEXT NOT NULL,
              approver_id VARCHAR(128) NOT NULL,
              ticket_ref VARCHAR(256) NOT NULL,
              policy_revision VARCHAR(64) NOT NULL,
              initial_status VARCHAR(32) NOT NULL,
              approval_sha256 CHAR(64) NOT NULL UNIQUE,
              created_at TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS preview_live_canary_approval_status_events (
              id INTEGER PRIMARY KEY,
              approval_id INTEGER NOT NULL
                REFERENCES preview_live_canary_approvals(id) ON DELETE RESTRICT,
              status VARCHAR(32) NOT NULL
                CHECK (status IN ('approved','consumed','expired','revoked')),
              actor_id VARCHAR(128) NOT NULL,
              reason TEXT NOT NULL,
              created_at TEXT NOT NULL,
              event_sha256 CHAR(64) NOT NULL UNIQUE
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS preview_circuit_breaker_policies (
              id INTEGER PRIMARY KEY,
              policy_revision VARCHAR(64) NOT NULL UNIQUE,
              policy_json TEXT NOT NULL,
              policy_sha256 CHAR(64) NOT NULL UNIQUE,
              created_at TEXT NOT NULL,
              created_actor_id VARCHAR(128) NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS preview_circuit_breaker_states (
              id INTEGER PRIMARY KEY,
              policy_id INTEGER NOT NULL
                REFERENCES preview_circuit_breaker_policies(id) ON DELETE RESTRICT,
              scope_key VARCHAR(128) NOT NULL,
              state VARCHAR(32) NOT NULL
                CHECK (state IN ('closed','open','half_open','disabled')),
              metric_class VARCHAR(64) NOT NULL,
              reason TEXT NOT NULL,
              created_at TEXT NOT NULL,
              state_sha256 CHAR(64) NOT NULL UNIQUE
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS preview_promotion_decisions (
              id INTEGER PRIMARY KEY,
              request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
              decision_type VARCHAR(32) NOT NULL
                CHECK (decision_type IN ('promote','rollback','reject','request')),
              decision_status VARCHAR(32) NOT NULL
                CHECK (decision_status IN (
                  'requested','rejected','cancelled','test_only_simulated','applied'
                )),
              candidate_revision_id INTEGER
                REFERENCES candidate_revisions(id) ON DELETE RESTRICT,
              effective_tier_summary_id INTEGER
                REFERENCES candidate_effective_tier_summaries(id) ON DELETE RESTRICT,
              phase4_validation_summary_id INTEGER
                REFERENCES candidate_validation_summaries(id) ON DELETE RESTRICT,
              phase5_visual_summary_id INTEGER
                REFERENCES candidate_visual_summaries(id) ON DELETE RESTRICT,
              lineage_sha256 CHAR(64) NOT NULL,
              candidate_manifest_sha256 CHAR(64),
              actor_id VARCHAR(128) NOT NULL,
              actor_role VARCHAR(64) NOT NULL,
              reason TEXT NOT NULL,
              ticket_ref VARCHAR(256),
              policy_revision VARCHAR(64) NOT NULL,
              eligibility_sha256 CHAR(64) NOT NULL,
              idempotency_key VARCHAR(128),
              requested_at TEXT NOT NULL,
              rejection_reason TEXT,
              previous_pointer_version INTEGER,
              resulting_pointer_version INTEGER,
              decision_sha256 CHAR(64) NOT NULL UNIQUE,
              UNIQUE (request_id, idempotency_key)
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS preview_promotion_decision_status_events (
              id INTEGER PRIMARY KEY,
              decision_id INTEGER NOT NULL
                REFERENCES preview_promotion_decisions(id) ON DELETE RESTRICT,
              status VARCHAR(32) NOT NULL
                CHECK (status IN (
                  'requested','rejected','cancelled','test_only_simulated','applied'
                )),
              actor_id VARCHAR(128) NOT NULL,
              reason TEXT NOT NULL,
              created_at TEXT NOT NULL,
              event_sha256 CHAR(64) NOT NULL UNIQUE
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS preview_serving_pointer_versions (
              id INTEGER PRIMARY KEY,
              request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
              pointer_version INTEGER NOT NULL,
              target_kind VARCHAR(16) NOT NULL
                CHECK (target_kind IN ('legacy_v1','v2_candidate','rollback')),
              candidate_revision_id INTEGER
                REFERENCES candidate_revisions(id) ON DELETE RESTRICT,
              legacy_preview_relpath VARCHAR(512),
              effective_tier INTEGER,
              effective_summary_id INTEGER
                REFERENCES candidate_effective_tier_summaries(id) ON DELETE RESTRICT,
              summary_sha256 CHAR(64),
              candidate_manifest_sha256 CHAR(64),
              previous_pointer_version INTEGER,
              pointer_action VARCHAR(32) NOT NULL
                CHECK (pointer_action IN ('initialize','promote','rollback')),
              decision_id INTEGER
                REFERENCES preview_promotion_decisions(id) ON DELETE RESTRICT,
              actor_id VARCHAR(128) NOT NULL,
              policy_revision VARCHAR(64) NOT NULL,
              created_at TEXT NOT NULL,
              is_current BOOLEAN NOT NULL,
              pointer_sha256 CHAR(64) NOT NULL UNIQUE,
              UNIQUE (request_id, pointer_version)
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_serving_pointer_one_current
            ON preview_serving_pointer_versions(request_id)
            WHERE is_current = 1
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS preview_rollout_audit_events (
              id INTEGER PRIMARY KEY,
              request_id INTEGER REFERENCES requests(id) ON DELETE CASCADE,
              event_type VARCHAR(64) NOT NULL,
              actor_id VARCHAR(128) NOT NULL,
              actor_role VARCHAR(64) NOT NULL,
              policy_revision VARCHAR(64),
              decision_id INTEGER
                REFERENCES preview_promotion_decisions(id) ON DELETE RESTRICT,
              pointer_version_before INTEGER,
              pointer_version_after INTEGER,
              lineage_sha256 CHAR(64),
              reason TEXT,
              ticket_ref VARCHAR(256),
              metadata_json TEXT NOT NULL,
              metadata_sha256 CHAR(64) NOT NULL,
              created_at TEXT NOT NULL,
              event_sha256 CHAR(64) NOT NULL UNIQUE
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS preview_shadow_evaluations (
              id INTEGER PRIMARY KEY,
              request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
              served_target_kind VARCHAR(16) NOT NULL
                CHECK (served_target_kind IN ('legacy_v1','v2_candidate','none')),
              served_pointer_version INTEGER,
              v2_candidate_revision_id INTEGER
                REFERENCES candidate_revisions(id) ON DELETE RESTRICT,
              v2_effective_summary_id INTEGER
                REFERENCES candidate_effective_tier_summaries(id) ON DELETE RESTRICT,
              comparison_policy_revision VARCHAR(64) NOT NULL,
              telemetry_json TEXT NOT NULL,
              telemetry_sha256 CHAR(64) NOT NULL,
              result_status VARCHAR(32) NOT NULL
                CHECK (result_status IN ('pending','completed','failed')),
              comparison_artifact_sha256 CHAR(64),
              no_serving_mutation BOOLEAN NOT NULL
                CHECK (no_serving_mutation = 1),
              created_at TEXT NOT NULL,
              evaluation_sha256 CHAR(64) NOT NULL UNIQUE
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS preview_phase7a_schema_meta (
              id INTEGER PRIMARY KEY,
              schema_version VARCHAR(64) NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
    )


def _sqlite_append_only_triggers(conn) -> None:
    for table in _STRICT_APPEND_ONLY_TABLES:
        conn.execute(
            text(
                f"""
                CREATE TRIGGER IF NOT EXISTS trg_{table}_no_update
                BEFORE UPDATE ON {table}
                BEGIN
                  SELECT RAISE(ABORT, 'Phase 7A append-only: UPDATE forbidden on {table}');
                END
                """
            )
        )
        conn.execute(
            text(
                f"""
                CREATE TRIGGER IF NOT EXISTS trg_{table}_no_delete
                BEFORE DELETE ON {table}
                BEGIN
                  SELECT RAISE(ABORT, 'Phase 7A append-only: DELETE forbidden on {table}');
                END
                """
            )
        )
    # Pointer versions: DELETE forbidden; UPDATE only when immutable cols unchanged.
    conn.execute(
        text(
            """
            CREATE TRIGGER IF NOT EXISTS trg_preview_serving_pointer_versions_no_delete
            BEFORE DELETE ON preview_serving_pointer_versions
            BEGIN
              SELECT RAISE(ABORT,
                'Phase 7A append-only: DELETE forbidden on preview_serving_pointer_versions');
            END
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TRIGGER IF NOT EXISTS trg_preview_serving_pointer_versions_immutable
            BEFORE UPDATE ON preview_serving_pointer_versions
            FOR EACH ROW
            WHEN
              OLD.request_id IS NOT NEW.request_id OR
              OLD.pointer_version IS NOT NEW.pointer_version OR
              OLD.target_kind IS NOT NEW.target_kind OR
              OLD.candidate_revision_id IS NOT NEW.candidate_revision_id OR
              OLD.legacy_preview_relpath IS NOT NEW.legacy_preview_relpath OR
              OLD.effective_tier IS NOT NEW.effective_tier OR
              OLD.effective_summary_id IS NOT NEW.effective_summary_id OR
              OLD.summary_sha256 IS NOT NEW.summary_sha256 OR
              OLD.candidate_manifest_sha256 IS NOT NEW.candidate_manifest_sha256 OR
              OLD.previous_pointer_version IS NOT NEW.previous_pointer_version OR
              OLD.pointer_action IS NOT NEW.pointer_action OR
              OLD.decision_id IS NOT NEW.decision_id OR
              OLD.actor_id IS NOT NEW.actor_id OR
              OLD.policy_revision IS NOT NEW.policy_revision OR
              OLD.created_at IS NOT NEW.created_at OR
              OLD.pointer_sha256 IS NOT NEW.pointer_sha256
            BEGIN
              SELECT RAISE(ABORT,
                'Phase 7A: only is_current may change on preview_serving_pointer_versions');
            END
            """
        )
    )


def _postgres_create_tables(conn) -> None:
    # Postgres DDL mirrors SQLite with TIMESTAMPTZ and boolean TRUE partial index.
    statements = [
        """
        CREATE TABLE IF NOT EXISTS preview_rollout_policies (
          id SERIAL PRIMARY KEY,
          policy_revision VARCHAR(64) NOT NULL UNIQUE,
          master_enabled BOOLEAN NOT NULL,
          shadow_enabled BOOLEAN NOT NULL,
          promote_enabled BOOLEAN NOT NULL,
          rollout_percent SMALLINT NOT NULL
            CHECK (rollout_percent >= 0 AND rollout_percent <= 100),
          allowlist_json TEXT NOT NULL,
          allowlist_sha256 CHAR(64) NOT NULL,
          circuit_breaker_policy_json TEXT NOT NULL,
          circuit_breaker_policy_sha256 CHAR(64) NOT NULL,
          rollout_salt VARCHAR(128) NOT NULL,
          configuration_sha256 CHAR(64) NOT NULL UNIQUE,
          created_at TIMESTAMPTZ NOT NULL,
          created_actor_id VARCHAR(128) NOT NULL,
          created_actor_role VARCHAR(64) NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS preview_live_canary_approvals (
          id SERIAL PRIMARY KEY,
          approval_uuid VARCHAR(36) NOT NULL UNIQUE,
          request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
          provider_model_allowlist_json TEXT NOT NULL,
          max_calls INTEGER NOT NULL,
          max_output_tokens INTEGER NOT NULL,
          max_cost_usd DOUBLE PRECISION NOT NULL,
          max_wall_seconds INTEGER NOT NULL,
          expires_at TIMESTAMPTZ NOT NULL,
          approver_id VARCHAR(128) NOT NULL,
          ticket_ref VARCHAR(256) NOT NULL,
          policy_revision VARCHAR(64) NOT NULL,
          initial_status VARCHAR(32) NOT NULL,
          approval_sha256 CHAR(64) NOT NULL UNIQUE,
          created_at TIMESTAMPTZ NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS preview_live_canary_approval_status_events (
          id SERIAL PRIMARY KEY,
          approval_id INTEGER NOT NULL
            REFERENCES preview_live_canary_approvals(id) ON DELETE RESTRICT,
          status VARCHAR(32) NOT NULL
            CHECK (status IN ('approved','consumed','expired','revoked')),
          actor_id VARCHAR(128) NOT NULL,
          reason TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL,
          event_sha256 CHAR(64) NOT NULL UNIQUE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS preview_circuit_breaker_policies (
          id SERIAL PRIMARY KEY,
          policy_revision VARCHAR(64) NOT NULL UNIQUE,
          policy_json TEXT NOT NULL,
          policy_sha256 CHAR(64) NOT NULL UNIQUE,
          created_at TIMESTAMPTZ NOT NULL,
          created_actor_id VARCHAR(128) NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS preview_circuit_breaker_states (
          id SERIAL PRIMARY KEY,
          policy_id INTEGER NOT NULL
            REFERENCES preview_circuit_breaker_policies(id) ON DELETE RESTRICT,
          scope_key VARCHAR(128) NOT NULL,
          state VARCHAR(32) NOT NULL
            CHECK (state IN ('closed','open','half_open','disabled')),
          metric_class VARCHAR(64) NOT NULL,
          reason TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL,
          state_sha256 CHAR(64) NOT NULL UNIQUE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS preview_promotion_decisions (
          id SERIAL PRIMARY KEY,
          request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
          decision_type VARCHAR(32) NOT NULL
            CHECK (decision_type IN ('promote','rollback','reject','request')),
          decision_status VARCHAR(32) NOT NULL
            CHECK (decision_status IN (
              'requested','rejected','cancelled','test_only_simulated','applied'
            )),
          candidate_revision_id INTEGER
            REFERENCES candidate_revisions(id) ON DELETE RESTRICT,
          effective_tier_summary_id INTEGER
            REFERENCES candidate_effective_tier_summaries(id) ON DELETE RESTRICT,
          phase4_validation_summary_id INTEGER
            REFERENCES candidate_validation_summaries(id) ON DELETE RESTRICT,
          phase5_visual_summary_id INTEGER
            REFERENCES candidate_visual_summaries(id) ON DELETE RESTRICT,
          lineage_sha256 CHAR(64) NOT NULL,
          candidate_manifest_sha256 CHAR(64),
          actor_id VARCHAR(128) NOT NULL,
          actor_role VARCHAR(64) NOT NULL,
          reason TEXT NOT NULL,
          ticket_ref VARCHAR(256),
          policy_revision VARCHAR(64) NOT NULL,
          eligibility_sha256 CHAR(64) NOT NULL,
          idempotency_key VARCHAR(128),
          requested_at TIMESTAMPTZ NOT NULL,
          rejection_reason TEXT,
          previous_pointer_version INTEGER,
          resulting_pointer_version INTEGER,
          decision_sha256 CHAR(64) NOT NULL UNIQUE,
          UNIQUE (request_id, idempotency_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS preview_promotion_decision_status_events (
          id SERIAL PRIMARY KEY,
          decision_id INTEGER NOT NULL
            REFERENCES preview_promotion_decisions(id) ON DELETE RESTRICT,
          status VARCHAR(32) NOT NULL
            CHECK (status IN (
              'requested','rejected','cancelled','test_only_simulated','applied'
            )),
          actor_id VARCHAR(128) NOT NULL,
          reason TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL,
          event_sha256 CHAR(64) NOT NULL UNIQUE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS preview_serving_pointer_versions (
          id SERIAL PRIMARY KEY,
          request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
          pointer_version INTEGER NOT NULL,
          target_kind VARCHAR(16) NOT NULL
            CHECK (target_kind IN ('legacy_v1','v2_candidate','rollback')),
          candidate_revision_id INTEGER
            REFERENCES candidate_revisions(id) ON DELETE RESTRICT,
          legacy_preview_relpath VARCHAR(512),
          effective_tier SMALLINT,
          effective_summary_id INTEGER
            REFERENCES candidate_effective_tier_summaries(id) ON DELETE RESTRICT,
          summary_sha256 CHAR(64),
          candidate_manifest_sha256 CHAR(64),
          previous_pointer_version INTEGER,
          pointer_action VARCHAR(32) NOT NULL
            CHECK (pointer_action IN ('initialize','promote','rollback')),
          decision_id INTEGER
            REFERENCES preview_promotion_decisions(id) ON DELETE RESTRICT,
          actor_id VARCHAR(128) NOT NULL,
          policy_revision VARCHAR(64) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL,
          is_current BOOLEAN NOT NULL,
          pointer_sha256 CHAR(64) NOT NULL UNIQUE,
          UNIQUE (request_id, pointer_version)
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_serving_pointer_one_current
        ON preview_serving_pointer_versions(request_id)
        WHERE is_current IS TRUE
        """,
        """
        CREATE TABLE IF NOT EXISTS preview_rollout_audit_events (
          id SERIAL PRIMARY KEY,
          request_id INTEGER REFERENCES requests(id) ON DELETE CASCADE,
          event_type VARCHAR(64) NOT NULL,
          actor_id VARCHAR(128) NOT NULL,
          actor_role VARCHAR(64) NOT NULL,
          policy_revision VARCHAR(64),
          decision_id INTEGER
            REFERENCES preview_promotion_decisions(id) ON DELETE RESTRICT,
          pointer_version_before INTEGER,
          pointer_version_after INTEGER,
          lineage_sha256 CHAR(64),
          reason TEXT,
          ticket_ref VARCHAR(256),
          metadata_json TEXT NOT NULL,
          metadata_sha256 CHAR(64) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL,
          event_sha256 CHAR(64) NOT NULL UNIQUE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS preview_shadow_evaluations (
          id SERIAL PRIMARY KEY,
          request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
          served_target_kind VARCHAR(16) NOT NULL
            CHECK (served_target_kind IN ('legacy_v1','v2_candidate','none')),
          served_pointer_version INTEGER,
          v2_candidate_revision_id INTEGER
            REFERENCES candidate_revisions(id) ON DELETE RESTRICT,
          v2_effective_summary_id INTEGER
            REFERENCES candidate_effective_tier_summaries(id) ON DELETE RESTRICT,
          comparison_policy_revision VARCHAR(64) NOT NULL,
          telemetry_json TEXT NOT NULL,
          telemetry_sha256 CHAR(64) NOT NULL,
          result_status VARCHAR(32) NOT NULL
            CHECK (result_status IN ('pending','completed','failed')),
          comparison_artifact_sha256 CHAR(64),
          no_serving_mutation BOOLEAN NOT NULL DEFAULT TRUE
            CHECK (no_serving_mutation IS TRUE),
          created_at TIMESTAMPTZ NOT NULL,
          evaluation_sha256 CHAR(64) NOT NULL UNIQUE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS preview_phase7a_schema_meta (
          id SERIAL PRIMARY KEY,
          schema_version VARCHAR(64) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    ]
    for stmt in statements:
        conn.execute(text(stmt))


def _postgres_append_only_triggers(conn) -> None:
    conn.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION phase7a_reject_mutation()
            RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'Phase 7A append-only: % forbidden on %',
                TG_OP, TG_TABLE_NAME;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    for table in _STRICT_APPEND_ONLY_TABLES:
        conn.execute(text(f"DROP TRIGGER IF EXISTS trg_{table}_no_update ON {table}"))
        conn.execute(
            text(
                f"""
                CREATE TRIGGER trg_{table}_no_update
                BEFORE UPDATE ON {table}
                FOR EACH ROW EXECUTE PROCEDURE phase7a_reject_mutation()
                """
            )
        )
        conn.execute(text(f"DROP TRIGGER IF EXISTS trg_{table}_no_delete ON {table}"))
        conn.execute(
            text(
                f"""
                CREATE TRIGGER trg_{table}_no_delete
                BEFORE DELETE ON {table}
                FOR EACH ROW EXECUTE PROCEDURE phase7a_reject_mutation()
                """
            )
        )
    conn.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION phase7a_pointer_immutable_guard()
            RETURNS trigger AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION
                  'Phase 7A append-only: DELETE forbidden on preview_serving_pointer_versions';
              END IF;
              IF NEW.request_id IS DISTINCT FROM OLD.request_id
                 OR NEW.pointer_version IS DISTINCT FROM OLD.pointer_version
                 OR NEW.target_kind IS DISTINCT FROM OLD.target_kind
                 OR NEW.candidate_revision_id IS DISTINCT FROM OLD.candidate_revision_id
                 OR NEW.legacy_preview_relpath IS DISTINCT FROM OLD.legacy_preview_relpath
                 OR NEW.effective_tier IS DISTINCT FROM OLD.effective_tier
                 OR NEW.effective_summary_id IS DISTINCT FROM OLD.effective_summary_id
                 OR NEW.summary_sha256 IS DISTINCT FROM OLD.summary_sha256
                 OR NEW.candidate_manifest_sha256 IS DISTINCT FROM OLD.candidate_manifest_sha256
                 OR NEW.previous_pointer_version IS DISTINCT FROM OLD.previous_pointer_version
                 OR NEW.pointer_action IS DISTINCT FROM OLD.pointer_action
                 OR NEW.decision_id IS DISTINCT FROM OLD.decision_id
                 OR NEW.actor_id IS DISTINCT FROM OLD.actor_id
                 OR NEW.policy_revision IS DISTINCT FROM OLD.policy_revision
                 OR NEW.created_at IS DISTINCT FROM OLD.created_at
                 OR NEW.pointer_sha256 IS DISTINCT FROM OLD.pointer_sha256 THEN
                RAISE EXCEPTION
                  'Phase 7A: only is_current may change on preview_serving_pointer_versions';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    conn.execute(
        text(
            "DROP TRIGGER IF EXISTS trg_preview_serving_pointer_versions_guard "
            "ON preview_serving_pointer_versions"
        )
    )
    conn.execute(
        text(
            """
            CREATE TRIGGER trg_preview_serving_pointer_versions_guard
            BEFORE UPDATE OR DELETE ON preview_serving_pointer_versions
            FOR EACH ROW EXECUTE PROCEDURE phase7a_pointer_immutable_guard()
            """
        )
    )


def migrate_phase7a_rollout(
    bind: Engine,
    *,
    direction: Literal["upgrade", "downgrade"] = "upgrade",
) -> None:
    """Transactional Phase 7A schema migration with downgrade guards."""
    dialect = bind.dialect.name
    if dialect not in ("sqlite", "postgresql"):
        raise RuntimeError(f"Phase 7A migration unsupported dialect: {dialect}")

    if direction == "downgrade":
        with bind.begin() as conn:
            _downgrade_guards(conn)
            for table in PHASE7A_TABLES_DROP_ORDER:
                if table in inspect(conn).get_table_names():
                    conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
            if dialect == "postgresql":
                conn.execute(text("DROP FUNCTION IF EXISTS phase7a_reject_mutation() CASCADE"))
                conn.execute(
                    text("DROP FUNCTION IF EXISTS phase7a_pointer_immutable_guard() CASCADE")
                )
        return

    # upgrade
    try:
        with bind.begin() as conn:
            if dialect == "sqlite":
                conn.execute(text("PRAGMA foreign_keys=ON"))
                _sqlite_create_tables(conn)
                _sqlite_append_only_triggers(conn)
            else:
                _postgres_create_tables(conn)
                _postgres_append_only_triggers(conn)
            existing = conn.execute(
                text(
                    "SELECT COUNT(*) FROM preview_phase7a_schema_meta "
                    "WHERE schema_version = :v"
                ),
                {"v": PHASE7A_SCHEMA_VERSION},
            ).scalar()
            if not existing:
                conn.execute(
                    text(
                        "INSERT INTO preview_phase7a_schema_meta "
                        "(schema_version, created_at) VALUES (:v, CURRENT_TIMESTAMP)"
                    ),
                    {"v": PHASE7A_SCHEMA_VERSION},
                )
    except Exception:
        # begin() already rolls back on exception
        raise


__all__ = [
    "PHASE7A_SCHEMA_VERSION",
    "PHASE7A_TABLES_CREATE_ORDER",
    "migrate_phase7a_rollout",
    "phase7a_schema_version",
]
