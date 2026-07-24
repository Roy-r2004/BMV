"""One-time import: local SQLite -> Render Postgres.

Usage (from repo root, with your Render External Database URL):

  set DATABASE_URL=postgresql://USER:PASS@HOST/DB
  python backend/scripts/import_sqlite_to_postgres.py

Or:

  python backend/scripts/import_sqlite_to_postgres.py --sqlite backend/buildmyversion.db --postgres "postgresql://..."

This copies:
  users, user_sessions, requests, customer_source_artifacts,
  product_strategy_revisions, app_spec_revisions, preview_tier_artifacts,
  preview_chat_messages, solution_workspaces, solution_edit_messages

Safe to re-run: clears destination tables first (in FK-safe order), then inserts.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import Boolean, create_engine, inspect, text
from sqlalchemy.engine import Engine


TABLES_IN_ORDER = [
    "users",
    "user_sessions",
    "requests",
    "customer_source_artifacts",
    "product_strategy_revisions",
    "app_spec_revisions",
    "preview_tier_artifacts",
    "preview_chat_messages",
    "solution_workspaces",
    "solution_edit_messages",
]

CLEAR_ORDER = list(reversed(TABLES_IN_ORDER))


def normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def sqlite_rows(conn: sqlite3.Connection, table: str) -> tuple[list[str], list[tuple]]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cur.fetchall()]
    if not columns:
        return [], []
    # Stable parent-before-child order also satisfies AppSpec's self-referential
    # parent_revision_id foreign key during the row-by-row Postgres import.
    order_by = " ORDER BY id" if "id" in columns else ""
    rows = conn.execute(
        f"SELECT {', '.join(columns)} FROM {table}{order_by}"
    ).fetchall()
    return columns, rows


def clear_postgres(engine: Engine) -> None:
    with engine.begin() as conn:
        for table in CLEAR_ORDER:
            exists = conn.execute(
                text("SELECT to_regclass(:name)"),
                {"name": table},
            ).scalar()
            if exists:
                conn.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))


def copy_table(sqlite_conn: sqlite3.Connection, engine: Engine, table: str) -> int:
    columns, rows = sqlite_rows(sqlite_conn, table)
    if not columns:
        print(f"  skip {table}: not in SQLite")
        return 0
    if not rows:
        print(f"  {table}: 0 rows")
        return 0

    placeholders = ", ".join([f":{c}" for c in columns])
    col_list = ", ".join([f'"{c}"' for c in columns])
    sql = text(f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})')
    boolean_columns = {
        column["name"]
        for column in inspect(engine).get_columns(table)
        if isinstance(column["type"], Boolean)
    }

    with engine.begin() as conn:
        # Ensure table exists (created by app startup). If missing, fail clearly.
        exists = conn.execute(text("SELECT to_regclass(:name)"), {"name": table}).scalar()
        if not exists:
            raise RuntimeError(
                f'Table "{table}" missing in Postgres. Deploy/start the API once so tables are created, then re-run.'
            )
        for row in rows:
            payload = {col: row[i] for i, col in enumerate(columns)}
            for column in boolean_columns:
                if column in payload and payload[column] is not None:
                    payload[column] = bool(payload[column])
            conn.execute(sql, payload)

        # Keep serial sequences in sync with imported IDs
        if "id" in columns:
            conn.execute(
                text(
                    f"""
                    SELECT setval(
                      pg_get_serial_sequence('"{table}"', 'id'),
                      COALESCE((SELECT MAX(id) FROM "{table}"), 1),
                      true
                    )
                    """
                )
            )

    print(f"  {table}: {len(rows)} rows")
    return len(rows)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    default_sqlite = root / "backend" / "buildmyversion.db"

    parser = argparse.ArgumentParser(description="Import local SQLite into Render Postgres")
    parser.add_argument("--sqlite", default=str(default_sqlite), help="Path to local SQLite DB")
    parser.add_argument(
        "--postgres",
        default="",
        help="Postgres URL (or set DATABASE_URL / TARGET_DATABASE_URL)",
    )
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.is_file():
        print(f"SQLite file not found: {sqlite_path}", file=sys.stderr)
        return 1

    import os

    pg_url = (
        args.postgres
        or os.getenv("TARGET_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()
    if not pg_url or pg_url.startswith("sqlite"):
        print(
            "Provide a Postgres URL via --postgres or TARGET_DATABASE_URL / DATABASE_URL",
            file=sys.stderr,
        )
        return 1

    pg_url = normalize_url(pg_url)
    print(f"Source: {sqlite_path}")
    print(f"Target: {pg_url.split('@')[-1] if '@' in pg_url else pg_url}")

    sqlite_conn = sqlite3.connect(str(sqlite_path))
    engine = create_engine(pg_url)

    print("Clearing destination tables…")
    clear_postgres(engine)

    print("Importing…")
    total = 0
    for table in TABLES_IN_ORDER:
        total += copy_table(sqlite_conn, engine, table)

    sqlite_conn.close()
    print(f"Done. Imported {total} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
