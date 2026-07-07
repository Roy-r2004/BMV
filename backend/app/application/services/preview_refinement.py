import json
import threading
from datetime import datetime

from sqlalchemy.orm import Session

from app.application.preview_app.chat_refinement import refine_preview_app_from_chat
from app.application.preview_app.workspace import get_workspace
from app.application.prompts import PromptTemplate
from app.application.pipelines._shared import business_info, get_request
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models import PreviewChatMessage, Request
from app.application.services.visual_demo_enrichment import enrich_visual_demo
from app.application.services.visual_demo_merge import merge_visual_demo
from app.infrastructure.ai_providers.factory import get_ai_provider
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.templating.renderer import get_template_renderer
from app.shared.json_utils import extract_json_from_text


def get_chat_history(db: Session, request_id: int) -> list[dict]:
    messages = (
        db.query(PreviewChatMessage)
        .filter(PreviewChatMessage.request_id == request_id)
        .order_by(PreviewChatMessage.created_at.asc())
        .all()
    )
    return [
        {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created_at.isoformat(),
        }
        for msg in messages
    ]


def _format_chat_history(messages: list[PreviewChatMessage]) -> str:
    if not messages:
        return "No previous messages."
    lines = []
    for msg in messages[-12:]:
        speaker = "User" if msg.role == "user" else "Assistant"
        lines.append(f"{speaker}: {msg.content}")
    return "\n".join(lines)


def _save_message(db: Session, request_id: int, role: str, content: str) -> PreviewChatMessage:
    msg = PreviewChatMessage(request_id=request_id, role=role, content=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def _current_visual_demo(req: Request) -> dict:
    if not req.visual_demo_json:
        return {}
    try:
        return json.loads(req.visual_demo_json)
    except Exception:
        return {}


def _current_features(req: Request) -> list[str]:
    if not req.preview_features:
        return []
    try:
        data = json.loads(req.preview_features)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _apply_visual_demo(req: Request, existing: dict, updated: dict) -> dict:
    merged = merge_visual_demo(existing, updated)
    return enrich_visual_demo(merged, req)


def _current_generated_pages(req: Request) -> dict:
    if not req.generated_pages:
        return {}
    try:
        return json.loads(req.generated_pages)
    except Exception:
        return {}


def _has_live_preview_app(req: Request, generated_pages: dict) -> bool:
    pa = generated_pages.get("preview_app") or {}
    if not pa and not get_workspace(req.id).is_dir():
        return False
    if pa.get("url") or pa.get("status") in ("ready", "failed", "rebuilding"):
        return get_workspace(req.id).is_dir()
    return get_workspace(req.id).is_dir()


def _mark_preview_rebuilding(db: Session, req: Request, generated_pages: dict) -> None:
    pa = generated_pages.setdefault("preview_app", {})
    pa["status"] = "rebuilding"
    req.generated_pages = json.dumps(generated_pages)
    req.updated_at = datetime.utcnow()
    db.commit()


def _run_chat_preview_rebuild(request_id: int, user_message: str) -> None:
    """Background worker: patch + rebuild the live React preview from chat."""
    bg_db = SessionLocal()
    try:
        result = refine_preview_app_from_chat(
            bg_db,
            request_id,
            user_message,
            get_ai_provider(),
            get_template_renderer(),
        )
        reply = result.get("reply") or "Your live preview has been updated."
        changes = result.get("changes_made") or []
        if changes:
            reply = f"{reply}\n\nChanges: " + "; ".join(changes[:6])
        if not result.get("preview_rebuild_succeeded") and not result.get("reverted"):
            reply += "\n\nThe rebuild hit errors — try one focused change at a time."
        _save_message(bg_db, request_id, "assistant", reply)
    except Exception as exc:
        req = bg_db.query(Request).filter(Request.id == request_id).first()
        if req and req.generated_pages:
            try:
                gp = json.loads(req.generated_pages)
                pa = gp.get("preview_app") or {}
                if pa.get("status") == "rebuilding":
                    pa["status"] = "failed"
                    gp["preview_app"] = pa
                    req.generated_pages = json.dumps(gp)
                    bg_db.commit()
            except Exception:
                pass
        _save_message(
            bg_db,
            request_id,
            "assistant",
            f"I couldn't rebuild the live preview: {exc}. Try describing one specific change "
            "(e.g. 'Visitor role should open the dashboard, not login').",
        )
    finally:
        bg_db.close()


def refine_preview(
    db: Session,
    request_id: int,
    user_message: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> dict:
    req = get_request(db, request_id)
    if not req.mvp_blueprint:
        raise ValueError("Preview is still being generated. Please try again shortly.")

    user_message = user_message.strip()
    if not user_message:
        raise ValueError("Message cannot be empty.")

    _save_message(db, request_id, "user", user_message)

    generated_pages = _current_generated_pages(req)

    # Live React preview → rebuild from chat instructions (not JSON mockup tweaks).
    if _has_live_preview_app(req, generated_pages):
        _mark_preview_rebuilding(db, req, generated_pages)
        threading.Thread(
            target=_run_chat_preview_rebuild,
            args=(request_id, user_message),
            daemon=True,
        ).start()
        reply = (
            "Got it — I'm updating your live preview app with that change now. "
            "This usually takes a few minutes. The preview will refresh automatically when ready."
        )
        assistant = _save_message(db, request_id, "assistant", reply)
        return {
            "reply": reply,
            "changes_made": ["Live preview rebuild started"],
            "message_id": assistant.id,
            "preview_updated": True,
            "preview_rebuild_started": True,
            "concept_name": req.concept_name,
            "preview_summary": req.preview_summary,
            "preview_features": _current_features(req),
            "business_fit_score": req.business_fit_score,
            "visual_demo": _current_visual_demo(req) or None,
        }

    history = (
        db.query(PreviewChatMessage)
        .filter(PreviewChatMessage.request_id == request_id)
        .order_by(PreviewChatMessage.created_at.asc())
        .all()
    )

    visual_demo = _current_visual_demo(req)
    features = _current_features(req)
    experience_plan = generated_pages.get("experience_plan") or {}

    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_REFINEMENT,
        business_information=business_info(req),
        concept_name=req.concept_name or "Custom Business MVP",
        preview_summary=req.preview_summary or "A tailored MVP for your business.",
        preview_features=json.dumps(features),
        business_fit_score=req.business_fit_score or 80,
        experience_plan=json.dumps(experience_plan, ensure_ascii=False, indent=2)[:8000],
        mvp_blueprint_snippet=(req.mvp_blueprint or "")[:4000],
        visual_demo=json.dumps(visual_demo, indent=2) if visual_demo else "{}",
        chat_history=_format_chat_history(history[:-1]),
        user_message=user_message,
    )

    try:
        response = ai_provider.ask_chat(settings.TEXT_MODEL, [{"role": "user", "content": prompt}])
        result = extract_json_from_text(response)
    except Exception as exc:
        fallback_reply = (
            "I couldn't apply that to the preview mockup. Try a specific change like: "
            "use purple colors, rename the concept, or add a habit-tracking feature."
        )
        assistant = _save_message(db, request_id, "assistant", fallback_reply)
        return {
            "reply": fallback_reply,
            "changes_made": [],
            "message_id": assistant.id,
            "preview_updated": False,
            "preview_rebuild_started": False,
            "error": str(exc),
        }

    reply = result.get("reply") or "I've noted your feedback. Let me know if you'd like any other changes."
    changes_made = result.get("changes_made") or []

    assistant = _save_message(db, request_id, "assistant", reply)

    preview_updated = False
    if result.get("concept_name"):
        req.concept_name = result["concept_name"]
        preview_updated = True
    if result.get("preview_summary"):
        req.preview_summary = result["preview_summary"]
        preview_updated = True
    if result.get("preview_features"):
        req.preview_features = json.dumps(result["preview_features"])
        preview_updated = True
    if result.get("business_fit_score") is not None:
        req.business_fit_score = int(result["business_fit_score"])
        preview_updated = True

    if result.get("visual_demo"):
        demo = _apply_visual_demo(req, visual_demo, result["visual_demo"])
        req.visual_demo_json = json.dumps(demo)
        req.visual_demo_generated_at = datetime.utcnow()
        preview_updated = True
    elif preview_updated and visual_demo:
        demo = enrich_visual_demo(visual_demo, req)
        req.visual_demo_json = json.dumps(demo)
        req.visual_demo_generated_at = datetime.utcnow()

    if result.get("experience_plan"):
        generated_pages["experience_plan"] = result["experience_plan"]
        req.generated_pages = json.dumps(generated_pages)
        preview_updated = True

    if preview_updated:
        req.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(req)

    return {
        "reply": reply,
        "changes_made": changes_made,
        "message_id": assistant.id,
        "preview_updated": preview_updated,
        "preview_rebuild_started": False,
        "concept_name": req.concept_name,
        "preview_summary": req.preview_summary,
        "preview_features": _current_features(req),
        "business_fit_score": req.business_fit_score,
        "visual_demo": _current_visual_demo(req) or None,
    }
