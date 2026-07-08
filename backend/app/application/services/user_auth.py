"""User signup, login, and session tokens."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domain.models import SolutionEditMessage, SolutionWorkspace, User, UserSession

SESSION_DAYS = 30
PBKDF2_ITERATIONS = 120_000


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS)
    return f"{salt}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS)
    return secrets.compare_digest(check.hex(), digest)


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def create_user(db: Session, *, name: str, email: str, password: str) -> User:
    normalized = email.strip().lower()
    if db.query(User).filter(User.email == normalized).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(name=name.strip(), email=normalized, password_hash=_hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, *, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user or not _verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return user


def create_session(db: Session, user: User) -> str:
    token = _new_token()
    session = UserSession(
        user_id=user.id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(days=SESSION_DAYS),
    )
    db.add(session)
    db.commit()
    return token


def get_user_by_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    session = (
        db.query(UserSession)
        .filter(UserSession.token == token, UserSession.expires_at > datetime.utcnow())
        .first()
    )
    if not session:
        return None
    return db.query(User).filter(User.id == session.user_id).first()


def logout_session(db: Session, token: str) -> None:
    db.query(UserSession).filter(UserSession.token == token).delete()
    db.commit()


def get_or_create_workspace(db: Session, user_id: int, solution_id: str) -> SolutionWorkspace:
    ws = (
        db.query(SolutionWorkspace)
        .filter(SolutionWorkspace.user_id == user_id, SolutionWorkspace.solution_id == solution_id)
        .first()
    )
    if ws:
        return ws
    ws = SolutionWorkspace(user_id=user_id, solution_id=solution_id, overlay_json="{}")
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


def parse_overlay(ws: SolutionWorkspace) -> dict:
    try:
        data = json.loads(ws.overlay_json or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def save_overlay(db: Session, ws: SolutionWorkspace, overlay: dict) -> SolutionWorkspace:
    ws.overlay_json = json.dumps(overlay)
    ws.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ws)
    return ws


def reset_workspace(db: Session, user_id: int, solution_id: str) -> SolutionWorkspace:
    """Clear this user's personal copy back to the shared template defaults."""
    ws = get_or_create_workspace(db, user_id, solution_id)
    ws.overlay_json = "{}"
    ws.updated_at = datetime.utcnow()
    db.query(SolutionEditMessage).filter(SolutionEditMessage.workspace_id == ws.id).delete()
    db.commit()
    db.refresh(ws)
    return ws


def list_messages(db: Session, workspace_id: int) -> list[SolutionEditMessage]:
    return (
        db.query(SolutionEditMessage)
        .filter(SolutionEditMessage.workspace_id == workspace_id)
        .order_by(SolutionEditMessage.created_at.asc())
        .all()
    )


def add_message(
    db: Session,
    workspace_id: int,
    *,
    role: str,
    content: str,
    attachment_name: str | None = None,
    attachment_path: str | None = None,
) -> SolutionEditMessage:
    msg = SolutionEditMessage(
        workspace_id=workspace_id,
        role=role,
        content=content,
        attachment_name=attachment_name,
        attachment_path=attachment_path,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg
