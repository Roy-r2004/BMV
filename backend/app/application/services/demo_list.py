import json

from sqlalchemy.orm import Session

from app.domain.models.request import Request
from app.domain.schemas.demo import DemoListItem, DemoListResponse
from app.application.services.preview_parser import parse_preview_features


def _theme_colors(visual_demo_json: str | None) -> tuple[str | None, str | None]:
    if not visual_demo_json:
        return None, None
    try:
        demo = json.loads(visual_demo_json)
        theme = demo.get("visual_theme") or {}
        return theme.get("primary_color"), theme.get("secondary_color")
    except Exception:
        return None, None


def build_demo_list(db: Session) -> DemoListResponse:
    rows = (
        db.query(Request)
        .filter(
            Request.concept_name.isnot(None),
            Request.concept_name != "",
            Request.visual_demo_json.isnot(None),
            Request.visual_demo_json != "",
        )
        .order_by(Request.created_at.desc())
        .all()
    )

    demos: list[DemoListItem] = []
    for req in rows:
        primary, secondary = _theme_colors(req.visual_demo_json)
        demos.append(
            DemoListItem(
                id=req.id,
                business_name=req.business_name,
                concept_name=req.concept_name or req.business_name,
                industry=req.industry,
                business_fit_score=req.business_fit_score,
                preview_summary=req.preview_summary,
                preview_features=parse_preview_features(req.preview_features),
                primary_color=primary,
                secondary_color=secondary,
                reference_url=req.reference_url,
                created_at=req.created_at,
            )
        )

    return DemoListResponse(demos=demos)
