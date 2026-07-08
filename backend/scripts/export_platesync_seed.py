"""Export PlateSync request as a seed JSON for Render auto-seed."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "buildmyversion.db"
OUT = ROOT / "data" / "seed_platesync.json"

# Keep gallery + detail useful; skip huge/local-only blobs that won't work on Render without files
KEEP_FIELDS = [
    "business_name",
    "industry",
    "business_description",
    "target_customers",
    "main_problem",
    "reference_url",
    "what_you_like",
    "desired_outcome",
    "needs_ai",
    "budget_range",
    "timeline",
    "email",
    "whatsapp",
    "status",
    "mvp_blueprint",
    "visual_demo_json",
    "technical_plan",
    "proposal_draft",
    "business_fit_score",
    "concept_name",
    "preview_summary",
    "preview_features",
    "project_type",
    "build_requested",
]


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM requests WHERE lower(business_name) LIKE '%platesync%' "
        "OR lower(concept_name) LIKE '%platesync%' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        raise SystemExit("PlateSync not found in local DB")

    raw = dict(row)
    seed = {k: raw.get(k) for k in KEEP_FIELDS}
    # Normalize bool/int for JSON
    if seed.get("build_requested") is not None:
        seed["build_requested"] = bool(seed["build_requested"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(seed, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
    print(f"concept: {seed.get('concept_name')}")
    conn.close()


if __name__ == "__main__":
    main()
