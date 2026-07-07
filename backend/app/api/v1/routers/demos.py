"""Public demo listing — a single implementation mounted at both legacy paths.

`/api/demos` and `/api/requests/demos` previously had two separate
implementations (one dead, one live, plus a third inline in `main.py`). This
is the one true implementation; both URLs stay byte-identical for the
frontend.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.application.services.demo_list import build_demo_list
from app.domain.schemas.demo import DemoListResponse

router = APIRouter(tags=["demos"])


@router.get("/api/demos", response_model=DemoListResponse)
def list_public_demos(db: Session = Depends(get_db)):
    """Public list of completed live product demos — newest first."""
    return build_demo_list(db)


@router.get("/api/requests/demos", response_model=DemoListResponse)
def list_request_demos(db: Session = Depends(get_db)):
    """Same demo list, mounted under /api/requests for the requests page."""
    return build_demo_list(db)
