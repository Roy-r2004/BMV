"""Rewrite AiFeaturesPage with AiFeatureDeck and rebuild preview dist."""
from __future__ import annotations

import sys

from app.application.preview_app.build import run_build
from app.application.preview_app.workspace import get_workspace, read_file, write_file
from app.application.services.ai_features import (
    ai_feature_hub_page_source,
    ai_features_from_request,
)
from app.domain.models.request import Request
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.templating.renderer import get_template_renderer


def main(request_id: int) -> int:
    db = SessionLocal()
    try:
        req = db.query(Request).filter(Request.id == request_id).first()
        if not req:
            print(f"missing request {request_id}")
            return 1
        features = ai_features_from_request(req)
        ws = get_workspace(request_id)
        before = read_file(ws, "src/pages/AiFeaturesPage.tsx") or ""
        print("before_has_deck", "AiFeatureDeck" in before)
        print("before_has_stub", "Signature package" in before or "Your details" in before)
        src = ai_feature_hub_page_source(
            brand_name=req.business_name or "Brand",
            features=features,
        )
        write_file(ws, "src/pages/AiFeaturesPage.tsx", src)
        ok, _log = run_build(
            ws, f"/api/preview-apps/{request_id}", get_template_renderer()
        )
        after = read_file(ws, "src/pages/AiFeaturesPage.tsx") or ""
        print("after_has_deck", "AiFeatureDeck" in after)
        print("build_ok", ok)
        return 0 if ok and "AiFeatureDeck" in after else 2
    finally:
        db.close()


if __name__ == "__main__":
    rid = int(sys.argv[1]) if len(sys.argv) > 1 else 11
    raise SystemExit(main(rid))
