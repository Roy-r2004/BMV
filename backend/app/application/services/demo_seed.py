"""Seed demo gallery data when the database is empty (e.g. Render free redeploy)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.domain.models.request import Request
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)

_SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "seed_platesync.json"


def seed_demo_if_empty() -> None:
    """Insert PlateSync demo request if there are no gallery-ready demos."""
    if not _SEED_PATH.is_file():
        return

    db: Session = SessionLocal()
    try:
        existing = (
            db.query(Request)
            .filter(
                Request.concept_name.isnot(None),
                Request.concept_name != "",
                Request.visual_demo_json.isnot(None),
                Request.visual_demo_json != "",
            )
            .count()
        )
        if existing > 0:
            return

        data = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
        # Avoid duplicate if a partial PlateSync row exists without visual demo
        name = (data.get("business_name") or "").strip()
        if name and db.query(Request).filter(Request.business_name == name).first():
            return

        req = Request(**{k: v for k, v in data.items() if hasattr(Request, k)})
        db.add(req)
        db.commit()
        logger.info("Seeded demo request: %s", data.get("concept_name") or name)
    except Exception:
        db.rollback()
        logger.exception("Failed to seed demo data")
    finally:
        db.close()
