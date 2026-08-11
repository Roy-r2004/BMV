"""Optional vision-model QA over generated screenshot candidates.
Prompt version: image-quality-judge-v1 (prompts/image_quality_judge.j2).

Fail-open by design: if the judge call/parse fails on BOTH attempts, the
candidate passes with a null score and the failure is logged — a QA outage
must never take down image generation itself. One retry first, though:
real runs have shown transient timeouts on this call, and a judge that
never actually looked at the image is worse than a slightly slower one.
"""

import base64
import logging
import time

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.pipeline._shared import extract_json_from_text, log_usage
from app.templating import render
from app.ui_spec import UIDemoSpec

logger = logging.getLogger("consultant.image_qa")

JUDGE_PROMPT_VERSION = "image-quality-judge-v1"


def review_image(db: Session, request_id: int, image_bytes: bytes, spec: UIDemoSpec) -> dict:
    """Returns {"score": float | None, "issues": list[str], "approved": bool}."""
    if not settings.ENABLE_VISION_QA:
        return {"score": None, "issues": [], "approved": True}

    prompt = render(
        "image_quality_judge.j2",
        screen_title=spec.screen_title,
        product_name=spec.product.name,
        business_name=spec.business.name,
        industry=spec.business.industry,
        min_score=settings.QA_MIN_SCORE,
    )
    data_uri = "data:image/png;base64," + base64.b64encode(image_bytes).decode()

    last_exc: Exception | None = None
    for attempt in range(2):
        if attempt:
            time.sleep(2)
        try:
            body = provider.chat(
                settings.QA_MODEL,
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_uri}},
                        ],
                    }
                ],
                max_tokens=1000,
            )
            parsed = extract_json_from_text(body["choices"][0]["message"]["content"])
            approved = parsed.get("approved")
            if isinstance(approved, str):
                # bool("false") is True — a judge that emits string booleans must
                # not silently approve everything (found in review).
                approved = approved.strip().lower() == "true"
            verdict = {
                "score": float(parsed["score"]) if parsed.get("score") is not None else None,
                "issues": [str(i) for i in (parsed.get("issues") or [])][:10],
                "approved": bool(approved),
            }
            log_usage(
                db, request_id,
                provider="openrouter", model=settings.QA_MODEL, purpose="image_qa",
                usage=body.get("usage"), success=True,
            )
            return verdict
        except Exception as exc:
            last_exc = exc

    log_usage(
        db, request_id,
        provider="openrouter", model=settings.QA_MODEL, purpose="image_qa",
        success=False, error=f"failed after retry: {str(last_exc)[:480]}",
    )
    logger.warning("image QA failed open after retry: request=%s error=%s", request_id, last_exc)
    return {"score": None, "issues": [f"qa-failed after retry: {str(last_exc)[:120]}"], "approved": True}
