"""Admin alerts — persist + optional webhook notify."""
from __future__ import annotations

from datetime import datetime, timedelta

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.admin_ops import AdminAlert
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.logging import get_logger

log = get_logger("AdminAlerts")


def emit_alert(
    *,
    kind: str,
    title: str,
    body: str = "",
    severity: str = "info",
    request_id: int | None = None,
    dedupe_minutes: int = 10,
) -> None:
    """Create an alert (deduped) and optionally POST to ADMIN_ALERT_WEBHOOK_URL."""
    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(minutes=max(1, dedupe_minutes))
        q = db.query(AdminAlert).filter(
            AdminAlert.kind == kind,
            AdminAlert.created_at >= since,
            AdminAlert.acknowledged.is_(False),
        )
        if request_id is not None:
            q = q.filter(AdminAlert.request_id == request_id)
        else:
            q = q.filter(AdminAlert.request_id.is_(None))
        if q.first():
            return

        row = AdminAlert(
            kind=kind[:80],
            severity=(severity or "info")[:20],
            title=title[:240],
            body=(body or "")[:4000] or None,
            request_id=request_id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        _post_webhook(row)
    except Exception:
        log.exception("failed to emit alert kind=%s", kind)
        db.rollback()
    finally:
        db.close()


def _post_webhook(row: AdminAlert) -> None:
    url = settings.ADMIN_ALERT_WEBHOOK_URL
    if not url:
        return
    payload = {
        "content": f"**[{row.severity}] {row.title}**\n{row.body or ''}"
        + (f"\nrequest #{row.request_id}" if row.request_id else ""),
        "text": f"[{row.severity}] {row.title}: {row.body or ''}",
        "kind": row.kind,
        "severity": row.severity,
        "title": row.title,
        "body": row.body,
        "request_id": row.request_id,
    }
    try:
        requests.post(url, json=payload, timeout=8)
    except Exception as exc:
        log.warning("alert webhook failed: %s", exc)


def list_alerts(db: Session, *, unread_only: bool = False, limit: int = 50) -> list[dict]:
    q = db.query(AdminAlert).order_by(AdminAlert.created_at.desc())
    if unread_only:
        q = q.filter(AdminAlert.acknowledged.is_(False))
    rows = q.limit(min(limit, 200)).all()
    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "kind": r.kind,
            "severity": r.severity,
            "title": r.title,
            "body": r.body,
            "request_id": r.request_id,
            "acknowledged": bool(r.acknowledged),
        }
        for r in rows
    ]


def acknowledge_alert(db: Session, alert_id: int) -> bool:
    row = db.query(AdminAlert).filter(AdminAlert.id == alert_id).first()
    if not row:
        return False
    row.acknowledged = True
    db.commit()
    return True


def acknowledge_all(db: Session) -> int:
    n = (
        db.query(AdminAlert)
        .filter(AdminAlert.acknowledged.is_(False))
        .update({AdminAlert.acknowledged: True}, synchronize_session=False)
    )
    db.commit()
    return int(n or 0)
