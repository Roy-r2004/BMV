"""Seed the real local PlateSync demo (DB row + built preview dist) when empty."""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.request import Request
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)


def _seed_json_paths() -> list[Path]:
    return [
        settings.BASE_DIR.parent / "data" / "seed_platesync.json",
        Path.cwd() / "data" / "seed_platesync.json",
        settings.BASE_DIR / "data" / "seed_platesync.json",
    ]


def _seed_dist_paths() -> list[Path]:
    return [
        settings.BASE_DIR.parent / "data" / "seed_preview_dist",
        Path.cwd() / "data" / "seed_preview_dist",
        settings.BASE_DIR / "data" / "seed_preview_dist",
    ]


def _first_existing(paths: list[Path], *, is_dir: bool = False) -> Path | None:
    for path in paths:
        if is_dir and path.is_dir():
            return path
        if not is_dir and path.is_file():
            return path
    return None


def _rewrite_preview_asset_paths(dist_dir: Path, request_id: int) -> None:
    """Seeded builds hardcode /api/preview-apps/4/... — remap to the real request id."""
    import re

    target_prefix = f"/api/preview-apps/{request_id}/"
    pattern = re.compile(r"/api/preview-apps/\d+/")
    for path in dist_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".html", ".js", ".css", ".json", ".map", ".svg"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        updated = pattern.sub(target_prefix, text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            logger.info("Rewrote preview asset paths in %s", path.name)


def _install_preview_dist(request_id: int) -> bool:
    src = _first_existing(_seed_dist_paths(), is_dir=True)
    if not src:
        logger.warning("Seed preview dist not found; gallery will show without live iframe")
        return False

    dest = settings.PREVIEW_APPS_DIR / str(request_id) / "dist"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(src, dest)
    _rewrite_preview_asset_paths(dest, request_id)
    logger.info("Installed seeded preview dist at %s", dest)
    return True


def _remap_generated_pages(raw: str | None, request_id: int) -> str | None:
    if not raw:
        return raw
    try:
        gp = json.loads(raw)
    except Exception:
        return raw
    pa = gp.setdefault("preview_app", {})
    pa["url"] = f"/api/preview-apps/{request_id}/"
    pa["status"] = "ready"
    return json.dumps(gp)


def _has_live_preview(req: Request) -> bool:
    raw = req.generated_pages or ""
    if not raw or "preview_app" not in raw:
        return False
    try:
        pa = (json.loads(raw).get("preview_app") or {})
        return pa.get("status") == "ready" and bool(pa.get("url"))
    except Exception:
        return False


def seed_demo_if_empty() -> None:
    """Insert/upgrade the real PlateSync demo (full local export + live dist)."""
    seed_path = _first_existing(_seed_json_paths())
    if not seed_path:
        logger.warning(
            "Demo seed file not found. Tried: %s",
            ", ".join(str(p) for p in _seed_json_paths()),
        )
        return

    data = json.loads(seed_path.read_text(encoding="utf-8"))
    logger.info("Loading demo seed from %s", seed_path)
    name = (data.get("business_name") or "").strip() or "PlateSync ERP"

    db: Session = SessionLocal()
    try:
        existing_rows = (
            db.query(Request)
            .filter(
                Request.concept_name.isnot(None),
                Request.concept_name != "",
                Request.visual_demo_json.isnot(None),
                Request.visual_demo_json != "",
            )
            .all()
        )

        # If a complete live PlateSync already exists, refresh dist + asset paths
        complete = next((r for r in existing_rows if _has_live_preview(r)), None)
        if complete is not None:
            _install_preview_dist(complete.id)
            # Keep generated_pages URL aligned with this request id
            remapped = _remap_generated_pages(complete.generated_pages, complete.id)
            if remapped and remapped != complete.generated_pages:
                complete.generated_pages = remapped
                db.commit()
            logger.info("Real PlateSync already seeded (id=%s); refreshed preview dist", complete.id)
            return

        # Remove incomplete/fallback gallery rows so we can replace with the real one
        for row in existing_rows:
            db.delete(row)
        if existing_rows:
            db.flush()
            logger.info("Removed %s incomplete demo row(s) before reseeding", len(existing_rows))

        allowed = {c.name for c in Request.__table__.columns}
        payload = {k: v for k, v in data.items() if k in allowed and k != "id"}
        generated = payload.pop("generated_pages", None)
        req = Request(**payload)
        db.add(req)
        db.flush()

        req.generated_pages = _remap_generated_pages(generated, req.id)
        db.commit()
        db.refresh(req)

        _install_preview_dist(req.id)
        logger.info(
            "Seeded real PlateSync demo id=%s concept=%s",
            req.id,
            data.get("concept_name") or name,
        )
    except Exception:
        db.rollback()
        logger.exception("Failed to seed demo data")
    finally:
        db.close()
