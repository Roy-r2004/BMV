"""Re-enrich visual demo for an existing request."""
import json
import sys

from app.infrastructure.db.session import SessionLocal
from app.domain.models.request import Request
from app.infrastructure.ai_providers.factory import get_ai_provider
from app.infrastructure.templating.renderer import get_template_renderer
from app.application.services.visual_demo_enrichment import enrich_visual_demo
from app.application.pipelines.visual_demo import generate_visual_demo


def main():
    request_id = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    db = SessionLocal()
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        print("Not found")
        return

    ai_provider = get_ai_provider()
    template_renderer = get_template_renderer()

    try:
        demo = generate_visual_demo(db, request_id, ai_provider, template_renderer)
    except Exception:
        db.rollback()
        db2 = SessionLocal()
        req = db2.query(Request).filter(Request.id == request_id).first()
        demo = json.loads(req.visual_demo_json or "{}")
        demo = enrich_visual_demo(demo, req)
        req.visual_demo_json = json.dumps(demo)
        db2.commit()
        db2.close()
    else:
        demo = json.loads(req.visual_demo_json or "{}")

    print("concept:", req.concept_name)
    print("features:", [c.get("title") for c in demo.get("feature_cards", [])])
    pc = demo.get("preview_content", {})
    print("theme:", pc.get("image_theme"))
    svcs = (pc.get("website") or {}).get("services") or []
    print("services:", [s.get("name") for s in svcs])
    print(f"VIEW: http://localhost:5175/result/{request_id}")
    db.close()


if __name__ == "__main__":
    main()
