"""Boot-time admin account + settings so deploys need no manual SQL."""
from __future__ import annotations

from app.application.services.admin_ops import ensure_settings
from app.application.services.user_auth import _hash_password
from app.core.config import settings
from app.domain.models import User
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.logging import get_logger

log = get_logger("AdminBootstrap")


def bootstrap_admin() -> None:
    """Ensure admin_settings row exists and promote/create the bootstrap admin user."""
    db = SessionLocal()
    try:
        ensure_settings(db)

        email = (settings.ADMIN_EMAIL or "").strip().lower()
        if not email or "@" not in email:
            log.info("ADMIN_EMAIL unset/invalid — skipping admin user bootstrap")
            return

        password = (settings.ADMIN_USER_PASSWORD or settings.ADMIN_PASSWORD or "").strip()
        if len(password) < 8:
            log.warning(
                "Admin bootstrap password too short (<8) — set ADMIN_USER_PASSWORD or ADMIN_PASSWORD"
            )
            return

        name = (settings.ADMIN_NAME or "Admin").strip() or "Admin"
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                name=name,
                email=email,
                password_hash=_hash_password(password),
                is_admin=True,
            )
            db.add(user)
            db.commit()
            log.info("Created bootstrap admin user %s", email)
            return

        changed = False
        if not bool(getattr(user, "is_admin", False)):
            user.is_admin = True
            changed = True
        if settings.ADMIN_SYNC_PASSWORD:
            user.password_hash = _hash_password(password)
            changed = True
        if name and user.name != name:
            user.name = name
            changed = True
        if changed:
            db.commit()
            log.info("Updated bootstrap admin user %s (is_admin/password sync)", email)
        else:
            log.info("Bootstrap admin user %s already ready", email)
    except Exception:
        log.exception("Admin bootstrap failed")
        db.rollback()
    finally:
        db.close()
