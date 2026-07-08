"""Keep only PlateSync demo data in local SQLite; remove other demos."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "buildmyversion.db"


def main() -> None:
    if not DB.is_file():
        raise SystemExit(f"DB not found: {DB}")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, business_name, concept_name FROM requests ORDER BY id"
    ).fetchall()
    print("Before:")
    for r in rows:
        print(f"  #{r['id']} {r['business_name']} | {r['concept_name']}")

    keep = [
        r
        for r in rows
        if "platesync" in (r["business_name"] or "").lower()
        or "platesync" in (r["concept_name"] or "").lower()
    ]
    if not keep:
        raise SystemExit("No PlateSync request found — aborting.")

    keep_ids = {r["id"] for r in keep}
    delete_ids = [r["id"] for r in rows if r["id"] not in keep_ids]
    print(f"\nKeeping request ids: {sorted(keep_ids)}")
    print(f"Deleting request ids: {delete_ids}")

    if delete_ids:
        placeholders = ",".join("?" * len(delete_ids))
        # preview chat tied to requests
        conn.execute(
            f"DELETE FROM preview_chat_messages WHERE request_id IN ({placeholders})",
            delete_ids,
        )
        conn.execute(
            f"DELETE FROM requests WHERE id IN ({placeholders})",
            delete_ids,
        )

    # Optional: leave users/workspaces (AI catalog edits) intact
    remaining = conn.execute(
        "SELECT id, business_name, concept_name FROM requests ORDER BY id"
    ).fetchall()
    print("\nAfter:")
    for r in remaining:
        print(f"  #{r['id']} {r['business_name']} | {r['concept_name']}")

    counts = {
        "requests": conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0],
        "preview_chat_messages": conn.execute(
            "SELECT COUNT(*) FROM preview_chat_messages"
        ).fetchone()[0],
        "users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "solution_workspaces": conn.execute(
            "SELECT COUNT(*) FROM solution_workspaces"
        ).fetchone()[0],
    }
    print("\nCounts:", counts)
    conn.commit()
    conn.close()
    print(f"\nDone. Local DB ready at: {DB}")


if __name__ == "__main__":
    main()
