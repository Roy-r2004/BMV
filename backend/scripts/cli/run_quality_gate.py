"""Run the automated quality lock on a preview workspace (no manual steps)."""
from __future__ import annotations

import sys

from app.application.preview_app.quality_gate import evaluate_quality_gate, run_quality_gate_with_heal
from app.application.preview_app.workspace import get_workspace
from app.domain.models.request import Request
from app.infrastructure.db.session import SessionLocal
import json


def main(request_id: int, *, heal: bool = True) -> int:
    db = SessionLocal()
    try:
        req = db.query(Request).filter(Request.id == request_id).first()
        if not req:
            print(f"missing request {request_id}")
            return 1
        architect: dict = {}
        if req.generated_pages:
            try:
                gp = json.loads(req.generated_pages)
                architect = {
                    "routes": (gp.get("preview_app") or {}).get("routes") or [],
                    "roles": gp.get("roles") or [],
                }
            except Exception:
                pass
        ws = get_workspace(request_id)
        brand = req.business_name or "Brand"
        if heal:
            report = run_quality_gate_with_heal(
                ws, architect, brand_name=brand, req=req, require_ai_hub=True
            )
        else:
            report = evaluate_quality_gate(ws, architect, require_ai_hub=True)
        print("ok" if report.ok else "FAIL")
        if report.healed:
            print("healed:", ", ".join(report.healed))
        for issue in report.issues:
            print(f"  - {issue.code}: {issue.message} ({issue.path})")
        return 0 if report.ok else 2
    finally:
        db.close()


if __name__ == "__main__":
    rid = int(sys.argv[1]) if len(sys.argv) > 1 else 11
    heal = "--no-heal" not in sys.argv
    raise SystemExit(main(rid, heal=heal))
