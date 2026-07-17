"""Ensure auto-seeded mock list stubs include ISO date fields."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.application.preview_app.safety.mock_data import (  # noqa: E402
    _seeded_list_export,
    enrich_date_starved_mock_exports,
)
from app.application.preview_app.workspace import write_file  # noqa: E402


def test_seeded_list_has_dates() -> None:
    rows = json.loads(_seeded_list_export("mockUpcomingClasses", "Northshore Clay"))
    assert len(rows) >= 3
    for row in rows:
        assert row.get("date")
        assert row.get("time")
        assert row.get("dropOffDate")
        assert row.get("dropOffTime")
        assert row.get("scheduledAt")
        # Must parse as a real Date in JS / Python
        assert date_ok(row["date"])
        assert "T" in row["scheduledAt"]


def date_ok(value: str) -> bool:
    from datetime import date

    date.fromisoformat(value)
    return True


def test_enrich_rewrites_thin_stubs() -> None:
    thin = (
        'export const mockUpcomingClasses = [{"id": "x-1", "name": "x 1", '
        '"title": "x 1", "label": "x 1", "status": "Open", '
        '"detail": "Sample Brand record for demo lists", "amount": 52, "count": 4}];\n'
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src" / "data").mkdir(parents=True)
        write_file(root, "src/data/mock.ts", thin)
        fixed = enrich_date_starved_mock_exports(root, "Brand")
        assert fixed == ["mockUpcomingClasses"]
        text = (root / "src" / "data" / "mock.ts").read_text(encoding="utf-8")
        assert '"date"' in text
        assert '"dropOffDate"' in text
        # Idempotent
        assert enrich_date_starved_mock_exports(root, "Brand") == []


if __name__ == "__main__":
    test_seeded_list_has_dates()
    test_enrich_rewrites_thin_stubs()
    print("ok")
