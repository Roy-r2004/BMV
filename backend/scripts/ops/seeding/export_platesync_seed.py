"""Export full local PlateSync request + built preview dist for Render seeding."""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "buildmyversion.db"
OUT_JSON = ROOT / "data" / "seed_platesync.json"
OUT_DIST = ROOT / "data" / "seed_preview_dist"
SRC_DIST = ROOT / "app" / "uploads" / "preview-apps" / "4" / "dist"

# Full request fields needed for gallery + result preview (exclude local-only paths)
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
    "generated_pages",
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
    if seed.get("build_requested") is not None:
        seed["build_requested"] = bool(seed["build_requested"])

    # Normalize generated_pages URL placeholder — seed runtime remaps to real id
    if seed.get("generated_pages"):
        try:
            gp = json.loads(seed["generated_pages"])
            pa = gp.setdefault("preview_app", {})
            pa["url"] = "/api/preview-apps/{request_id}/"
            pa["status"] = "ready"
            seed["generated_pages"] = json.dumps(gp)
        except Exception as exc:
            raise SystemExit(f"Invalid generated_pages JSON: {exc}") from exc

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(seed, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT_JSON} ({OUT_JSON.stat().st_size} bytes)")

    if not SRC_DIST.is_dir():
        raise SystemExit(f"Missing built preview dist: {SRC_DIST}")

    if OUT_DIST.exists():
        shutil.rmtree(OUT_DIST)
    shutil.copytree(SRC_DIST, OUT_DIST)
    files = list(OUT_DIST.rglob("*"))
    size = sum(f.stat().st_size for f in files if f.is_file())
    print(f"Copied dist -> {OUT_DIST} ({len([f for f in files if f.is_file()])} files, {size/1024:.0f} KB)")
    conn.close()


if __name__ == "__main__":
    main()
