import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.application.services.catalog_integrate import integrate_catalog_feature, remove_catalog_feature
from app.application.services.solution_edit import refine_solution_from_chat
from app.application.services.user_auth import get_or_create_workspace, list_messages, parse_overlay, reset_workspace
from app.data.ai_feature_catalog import list_catalog_for_solution
from app.core.config import settings
from app.domain.models import User
from app.domain.schemas.solution_workspace import (
    AIFeatureCatalogItemOut,
    AIFeatureCatalogResponse,
    IntegrateFeatureResponse,
    SolutionChatHistoryResponse,
    SolutionChatSendResponse,
    SolutionEditMessageOut,
    SolutionWorkspaceResponse,
)

router = APIRouter(prefix="/api/solutions", tags=["solution-workspaces"])

ATTACH_DIR = Path(settings.UPLOAD_DIR) / "solution_attachments"


def _message_out(m) -> SolutionEditMessageOut:
    return SolutionEditMessageOut(
        id=m.id,
        role=m.role,
        content=m.content,
        attachment_name=m.attachment_name,
        created_at=m.created_at,
    )


@router.get("/{solution_id}/workspace", response_model=SolutionWorkspaceResponse)
def get_workspace(
    solution_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws = get_or_create_workspace(db, user.id, solution_id)
    return SolutionWorkspaceResponse(
        solution_id=solution_id,
        overlay=parse_overlay(ws),
        updated_at=ws.updated_at,
    )


@router.post("/{solution_id}/workspace/reset", response_model=SolutionWorkspaceResponse)
def reset_user_workspace(
    solution_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reset only this user's personal copy — other users and the public template are unchanged."""
    ws = reset_workspace(db, user.id, solution_id)
    return SolutionWorkspaceResponse(
        solution_id=solution_id,
        overlay=parse_overlay(ws),
        updated_at=ws.updated_at,
    )


@router.get("/{solution_id}/catalog", response_model=AIFeatureCatalogResponse)
def get_ai_feature_catalog(
    solution_id: str,
    user: User = Depends(get_current_user),
):
    """Pre-built AI features available for one-click integration on this solution."""
    items = list_catalog_for_solution(solution_id)
    return AIFeatureCatalogResponse(
        features=[
            AIFeatureCatalogItemOut(
                id=item["id"],
                title=item["title"],
                description=item["description"],
                category=item["category"],
                icon=item["icon"],
            )
            for item in items
        ],
    )


@router.post("/{solution_id}/catalog/{feature_id}/integrate", response_model=IntegrateFeatureResponse)
def integrate_ai_feature(
    solution_id: str,
    feature_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Apply a catalog feature patch to the signed-in user's personal workspace copy."""
    overlay, reply, changes = integrate_catalog_feature(
        db,
        user_id=user.id,
        solution_id=solution_id,
        feature_id=feature_id,
    )
    return IntegrateFeatureResponse(
        reply=reply,
        changes_made=changes,
        overlay=overlay,
        feature_id=feature_id,
        integrated=True,
    )


@router.post("/{solution_id}/catalog/{feature_id}/remove", response_model=IntegrateFeatureResponse)
def remove_ai_feature(
    solution_id: str,
    feature_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Undo a catalog feature — removes only what that feature added."""
    overlay, reply, changes = remove_catalog_feature(
        db,
        user_id=user.id,
        solution_id=solution_id,
        feature_id=feature_id,
    )
    return IntegrateFeatureResponse(
        reply=reply,
        changes_made=changes,
        overlay=overlay,
        feature_id=feature_id,
        integrated=False,
    )


@router.get("/{solution_id}/chat", response_model=SolutionChatHistoryResponse)
def get_chat(
    solution_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws = get_or_create_workspace(db, user.id, solution_id)
    messages = list_messages(db, ws.id)
    return SolutionChatHistoryResponse(
        messages=[_message_out(m) for m in messages],
        overlay=parse_overlay(ws),
    )


@router.post("/{solution_id}/chat", response_model=SolutionChatSendResponse)
async def send_chat(
    solution_id: str,
    message: str = Form(...),
    attachment: UploadFile | None = File(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    text = message.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Message is required.")

    attachment_name: str | None = None
    attachment_path: str | None = None
    if attachment and attachment.filename:
        ATTACH_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}_{Path(attachment.filename).name}"
        dest = ATTACH_DIR / safe_name
        content = await attachment.read()
        if len(content) > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Attachment must be under 8MB.")
        dest.write_bytes(content)
        attachment_name = attachment.filename
        attachment_path = str(dest)

    overlay, reply, changes = refine_solution_from_chat(
        db,
        user_id=user.id,
        solution_id=solution_id,
        message=text,
        attachment_name=attachment_name,
        attachment_path=attachment_path,
    )
    return SolutionChatSendResponse(
        reply=reply,
        changes_made=changes,
        overlay=overlay,
        workspace_updated=bool(changes),
    )
