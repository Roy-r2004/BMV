from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.application.services.user_auth import authenticate_user, create_session, create_user, get_user_by_token, logout_session
from app.domain.models import User
from app.domain.schemas.user_auth import AuthResponse, LoginRequest, MeResponse, SignupRequest, UserPublic

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _public(user: User) -> UserPublic:
    return UserPublic(id=user.id, name=user.name, email=user.email, created_at=user.created_at)


@router.post("/signup", response_model=AuthResponse)
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    if "@" not in body.email:
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    user = create_user(db, name=body.name, email=body.email, password=body.password)
    token = create_session(db, user)
    return AuthResponse(token=token, user=_public(user))


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, email=body.email, password=body.password)
    token = create_session(db, user)
    return AuthResponse(token=token, user=_public(user))


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)):
    return MeResponse(user=_public(user))


@router.post("/logout")
def logout(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    token = _extract_bearer(authorization)
    if token:
        logout_session(db, token)
    return {"success": True}


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None
