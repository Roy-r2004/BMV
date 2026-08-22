"""Test helper: stamp a clean, current integrity report on a row — for tests
that exercise OTHER release laws on fixture rows that never ran the pipeline.
Production rows get their report from integrity.enforce()."""
import json
from datetime import datetime

from app.pipeline import integrity


def stamp_clean(row, db=None):
    row.integrity_report_json = json.dumps({
        "version": integrity.VERSION, "ran_at": datetime.utcnow().isoformat() + "Z", "facts": {}, "corrections": {},
        "rejected_rewrites": [], "findings": [], "clean": True, "content_hash": integrity.content_hash(integrity.load(row)),
        "note": "test fixture — stamped clean",
    })
    if db is not None:
        db.commit()
    return row
