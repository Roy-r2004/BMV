"""Seed demo gallery data when the database is empty (e.g. Render free redeploy)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.request import Request
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)


def _seed_paths() -> list[Path]:
    """Resolve seed file from known locations (local + Render rootDir=backend)."""
    candidates = [
        # backend/data/… (correct package layout)
        settings.BASE_DIR.parent / "data" / "seed_platesync.json",
        # cwd-relative (Render start from backend/)
        Path.cwd() / "data" / "seed_platesync.json",
        # accidental nest under app/data
        settings.BASE_DIR / "data" / "seed_platesync.json",
    ]
    return candidates


def _load_seed() -> dict | None:
    for path in _seed_paths():
        if path.is_file():
            logger.info("Loading demo seed from %s", path)
            return json.loads(path.read_text(encoding="utf-8"))
    logger.warning(
        "Demo seed file not found. Tried: %s",
        ", ".join(str(p) for p in _seed_paths()),
    )
    return None


def seed_demo_if_empty() -> None:
    """Insert PlateSync demo request if there are no gallery-ready demos."""
    data = _load_seed()
    if not data:
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
            logger.info("Demo gallery already has %s item(s); skip seed", existing)
            return

        name = (data.get("business_name") or "").strip()
        if name and db.query(Request).filter(Request.business_name == name).first():
            logger.info("PlateSync row already exists; skip seed")
            return

        allowed = {c.name for c in Request.__table__.columns}
        payload = {k: v for k, v in data.items() if k in allowed}
        req = Request(**payload)
        db.add(req)
        db.commit()
        logger.info("Seeded demo request: %s", data.get("concept_name") or name)
    except Exception:
        db.rollback()
        logger.exception("Failed to seed demo data")
    finally:
        db.close()
