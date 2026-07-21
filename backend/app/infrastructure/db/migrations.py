"""Ad-hoc column migrations.

Lightweight alternative to Alembic for this project's simple schema —
adds columns that may be missing in databases created by older versions of
the app. Safe to call on every startup: it only adds columns that don't
already exist, and never raises.
"""
from sqlalchemy import text

from app.core.config import settings
from app.infrastructure.db.session import engine

_REQUESTS_TABLE_MIGRATIONS: list[tuple[str, str]] = [
    ("generated_pages", "ALTER TABLE requests ADD COLUMN generated_pages TEXT"),
    ("project_type", "ALTER TABLE requests ADD COLUMN project_type VARCHAR"),
    ("existing_product_url", "ALTER TABLE requests ADD COLUMN existing_product_url VARCHAR"),
    ("generation_log", "ALTER TABLE requests ADD COLUMN generation_log TEXT"),
    ("ai_features", "ALTER TABLE requests ADD COLUMN ai_features TEXT"),
    ("build_plans", "ALTER TABLE requests ADD COLUMN build_plans TEXT"),
]


def run_sqlite_migrations() -> None:
    """Add any missing columns. Never raises."""
    url = settings.DATABASE_URL
    try:
        with engine.connect() as conn:
            if url.startswith("sqlite"):
                existing = {
                    row[1] for row in conn.execute(text("PRAGMA table_info(requests)"))
                }
                for column, ddl in _REQUESTS_TABLE_MIGRATIONS:
                    if column not in existing:
                        conn.execute(text(ddl))
                user_cols = {
                    row[1] for row in conn.execute(text("PRAGMA table_info(users)"))
                }
                if "is_admin" not in user_cols:
                    conn.execute(
                        text(
                            "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"
                        )
                    )
                req_cols = {
                    row[1] for row in conn.execute(text("PRAGMA table_info(requests)"))
                }
                if "generation_cancel" not in req_cols:
                    conn.execute(
                        text(
                            "ALTER TABLE requests ADD COLUMN generation_cancel BOOLEAN DEFAULT 0"
                        )
                    )
                settings_cols = {
                    row[1]
                    for row in conn.execute(text("PRAGMA table_info(admin_settings)"))
                }
                if settings_cols and "request_budget_usd" not in settings_cols:
                    conn.execute(
                        text(
                            "ALTER TABLE admin_settings ADD COLUMN request_budget_usd FLOAT"
                        )
                    )
                conn.commit()
                return

            if url.startswith("postgresql"):
                for column, _ddl in _REQUESTS_TABLE_MIGRATIONS:
                    conn.execute(
                        text(
                            "ALTER TABLE requests ADD COLUMN IF NOT EXISTS "
                            f"{column} TEXT"
                        )
                    )
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                        "is_admin BOOLEAN NOT NULL DEFAULT FALSE"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE requests ADD COLUMN IF NOT EXISTS "
                        "generation_cancel BOOLEAN DEFAULT FALSE"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE admin_settings ADD COLUMN IF NOT EXISTS "
                        "request_budget_usd DOUBLE PRECISION"
                    )
                )
                conn.commit()
    except Exception:
        pass
