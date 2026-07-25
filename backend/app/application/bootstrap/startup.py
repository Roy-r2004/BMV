"""Fail-closed database bootstrap and schema readiness verification."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.infrastructure.db.commercial_migrations import (
    COMMERCIAL_SCHEMA_VERSION,
    commercial_schema_version,
    migrate_commercial_expanded_preview,
)
from app.infrastructure.db.phase7a_migrations import (
    migrate_phase7a_rollout,
    phase7a_schema_version,
)
from app.infrastructure.db.phase7b_migrations import (
    migrate_phase7b_shadow,
    phase7b_schema_version,
)
from app.infrastructure.db.phase7c_migrations import (
    migrate_phase7c_promotion,
    phase7c_schema_version,
)
from app.infrastructure.db.phase7d_migrations import (
    migrate_phase7d_breaker,
    phase7d_schema_version,
)
from app.infrastructure.db.phase7e_migrations import (
    migrate_phase7e_ops,
    phase7e_schema_version,
)
from app.infrastructure.db.phase7f_migrations import (
    PHASE7F_SCHEMA_VERSION,
    migrate_phase7f_percent_canary,
    phase7f_schema_version,
)
from app.infrastructure.logging import get_logger

log = get_logger("Startup")

REQUIRED_SCHEMA_VERSIONS = {
    "phase7a": "phase7a.1",
    "phase7b": "phase7b.1",
    "phase7c": "phase7c.1",
    "phase7d": "phase7d.1",
    "phase7e": "phase7e.1",
    "phase7f": PHASE7F_SCHEMA_VERSION,
    "commercial": COMMERCIAL_SCHEMA_VERSION,
}

REQUIRED_PHASE7_TABLES = (
    "preview_rollout_policies",
    "preview_serving_pointer_versions",
    "preview_shadow_evaluations",
    "preview_promotion_decisions",
    "preview_circuit_breaker_states",
    "preview_rollout_alert_events",
    "preview_live_canary_approvals",
    "preview_live_canary_executions",
    "preview_phase7f_schema_meta",
    "expanded_preview_requests",
    "expanded_preview_status_events",
    "commercial_schema_meta",
)


@dataclass
class StartupMigrationResult:
    migration_started: bool = False
    migration_completed: bool = False
    schema_versions_found: dict[str, str | None] = field(default_factory=dict)
    required_versions_expected: dict[str, str] = field(
        default_factory=lambda: dict(REQUIRED_SCHEMA_VERSIONS)
    )
    missing_versions: list[str] = field(default_factory=list)
    missing_tables: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    failure_reason: str | None = None
    ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StartupMigrationError(RuntimeError):
    def __init__(self, result: StartupMigrationResult):
        self.result = result
        super().__init__(result.failure_reason or "startup migration failed")


def redact_database_url(url: str) -> str:
    """Return a log-safe database locator without credentials."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "local"
        db = (parsed.path or "").lstrip("/") or "db"
        return f"{parsed.scheme}://{host}/{db}"
    except Exception:
        return "database:redacted"


def collect_schema_versions(engine: Engine) -> dict[str, str | None]:
    return {
        "phase7a": phase7a_schema_version(engine),
        "phase7b": phase7b_schema_version(engine),
        "phase7c": phase7c_schema_version(engine),
        "phase7d": phase7d_schema_version(engine),
        "phase7e": phase7e_schema_version(engine),
        "phase7f": phase7f_schema_version(engine),
        "commercial": commercial_schema_version(engine),
    }


def verify_schema_ready(engine: Engine) -> StartupMigrationResult:
    result = StartupMigrationResult(migration_started=False, migration_completed=True)
    result.schema_versions_found = collect_schema_versions(engine)
    for key, expected in REQUIRED_SCHEMA_VERSIONS.items():
        found = result.schema_versions_found.get(key)
        if found != expected:
            result.missing_versions.append(f"{key}:{expected}")
    tables = set(inspect(engine).get_table_names())
    result.missing_tables = [t for t in REQUIRED_PHASE7_TABLES if t not in tables]
    result.ready = not result.missing_versions and not result.missing_tables
    if not result.ready:
        parts = []
        if result.missing_versions:
            parts.append("missing_versions=" + ",".join(result.missing_versions))
        if result.missing_tables:
            parts.append("missing_tables=" + ",".join(result.missing_tables))
        result.failure_reason = "; ".join(parts)
    return result


def run_required_migrations(engine: Engine) -> None:
    """Run Phase 7 + commercial migrations (idempotent). Raises on failure."""
    from app.infrastructure.db.migrations import (
        migrate_candidate_revision_target_tier,
        migrate_tier_orchestration_target_tier,
    )

    migrate_candidate_revision_target_tier(engine)
    migrate_tier_orchestration_target_tier(engine)
    migrate_phase7a_rollout(engine)
    migrate_phase7b_shadow(engine)
    migrate_phase7c_promotion(engine)
    migrate_phase7d_breaker(engine)
    migrate_phase7e_ops(engine)
    migrate_phase7f_percent_canary(engine)
    migrate_commercial_expanded_preview(engine)


def bootstrap_database(
    *,
    engine: Engine,
    create_all,
    run_legacy_column_migrations,
    database_url: str,
) -> StartupMigrationResult:
    """Create schema, migrate, and verify. Fail closed on errors."""
    started = time.monotonic()
    result = StartupMigrationResult(migration_started=True)
    safe_db = redact_database_url(database_url)
    try:
        create_all(bind=engine)
        run_legacy_column_migrations()
        run_required_migrations(engine)
        verified = verify_schema_ready(engine)
        result.schema_versions_found = verified.schema_versions_found
        result.missing_versions = verified.missing_versions
        result.missing_tables = verified.missing_tables
        result.ready = verified.ready
        result.failure_reason = verified.failure_reason
        result.migration_completed = True
        result.elapsed_ms = int((time.monotonic() - started) * 1000)
        if not result.ready:
            log.error(
                "schema_verification_failed db=%s elapsed_ms=%s reason=%s",
                safe_db,
                result.elapsed_ms,
                result.failure_reason,
            )
            raise StartupMigrationError(result)
        log.info(
            "schema_ready db=%s elapsed_ms=%s versions=%s",
            safe_db,
            result.elapsed_ms,
            result.schema_versions_found,
        )
        return result
    except StartupMigrationError:
        raise
    except Exception as exc:
        result.elapsed_ms = int((time.monotonic() - started) * 1000)
        result.migration_completed = False
        result.ready = False
        result.failure_reason = f"{type(exc).__name__}: {exc}"
        # Never include raw DATABASE_URL (may hold credentials).
        log.error(
            "migration_failed db=%s elapsed_ms=%s error=%s",
            safe_db,
            result.elapsed_ms,
            result.failure_reason,
        )
        raise StartupMigrationError(result) from exc


def database_reachable(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


__all__ = [
    "REQUIRED_SCHEMA_VERSIONS",
    "StartupMigrationError",
    "StartupMigrationResult",
    "bootstrap_database",
    "collect_schema_versions",
    "database_reachable",
    "redact_database_url",
    "run_required_migrations",
    "verify_schema_ready",
]
