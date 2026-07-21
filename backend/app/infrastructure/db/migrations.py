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
    """Add any missing columns to the `requests` table. Never raises."""
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
                conn.commit()
    except Exception:
        pass
