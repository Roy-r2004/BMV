"""Optional vision-model QA over generated screenshot candidates.
Prompt versions: image-quality-judge-v1 (prompts/image_quality_judge.j2)
and image-text-transcription-v1 (prompts/image_text_transcription.j2).

Two instruments, deliberately separate:

1. The aesthetic judge scores craft and approves or rejects.
2. The text-truth gate (W3) transcribes what is actually rendered and
   diffs it against the spec in code (pipeline/text_truth.py). It can only
   ever REJECT — a screen carrying the client's name misspelled is
   unusable however beautiful it is, and no aesthetic score may override
   that. It can never rescue a screen the judge rejected.

Fail-open by design: if the judge call/parse fails on BOTH attempts, the
candidate passes with a null score and the failure is logged — a QA outage
must never take down image generation itself. One retry first, though:
real runs have shown transient timeouts on this call, and a judge that
never actually looked at the image is worse than a slightly slower one.
The transcription call fails open the same way, for the same reason: an
outage in the gate must not reject every candidate a request has.
"""

import base64
import logging
import time

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.pipeline import text_truth
from app.pipeline._shared import extract_json_from_text, log_usage
from app.templating import render
from app.ui_spec import UIDemoSpec

logger = logging.getLogger("consultant.image_qa")

JUDGE_PROMPT_VERSION = "image-quality-judge-v1"
TRANSCRIPTION_PROMPT_VERSION = "image-text-transcription-v1"


def transcribe(db: Session, request_id: int, image_bytes: bytes) -> list[str] | None:
    """Every string visible in the image, as rendered. None when the call or
    parse failed — the caller must treat that as "unknown", never as "no
    text found", which would fail every brand-critical string at once."""
    prompt = render("image_text_transcription.j2")
    data_uri = "data:image/png;base64," + base64.b64encode(image_bytes).decode()
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
            max_tokens=2000,
        )
        parsed = extract_json_from_text(body["choices"][0]["message"]["content"])
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.QA_MODEL, purpose="image_text",
            usage=body.get("usage"), success=True,
        )
        return [str(t) for t in (parsed.get("text") or [])]
    except Exception as exc:
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.QA_MODEL, purpose="image_text",
            success=False, error=str(exc)[:480],
        )
        logger.warning("text transcription failed open: request=%s error=%s", request_id, exc)
        return None


def _apply_text_truth_gate(db: Session, request_id: int, image_bytes: bytes, spec: UIDemoSpec, verdict: dict) -> dict:
    """Adds "text_truth" to the verdict and, on failure, forces approval off.

    Only ever subtracts. A verdict the aesthetic judge already rejected
    stays rejected even if every brand string is perfect.
    """
    # ENABLE_VISION_QA is the master cost switch for vision calls ("no QA
    # calls on this deployment"). The gate is a vision call, so it obeys
    # that switch too — turning QA off and still being billed for a
    # transcription per candidate would be a nasty surprise.
    if not (settings.ENABLE_VISION_QA and settings.ENABLE_TEXT_TRUTH_GATE):
        return verdict

    transcript = transcribe(db, request_id, image_bytes)
    if transcript is None:
        verdict["text_truth"] = {"passed": None, "reason": "transcription unavailable"}
        return verdict

    result = text_truth.check(spec, transcript)
    verdict["text_truth"] = {
        "passed": result["passed"],
        "checked": result["checked"],
        "failures": result["failures"],
        "absent": result["absent"],
    }
    if not result["passed"]:
        issues = text_truth.describe(result)
        verdict["issues"] = (verdict.get("issues") or []) + issues
        verdict["approved"] = False
        logger.info(
            "text-truth gate rejected a candidate: request=%s screen=%s %s",
            request_id, spec.screen_slug, "; ".join(issues[:3]),
        )
    return verdict


def review_image(db: Session, request_id: int, image_bytes: bytes, spec: UIDemoSpec) -> dict:
    """Returns {"score": float | None, "issues": list[str], "approved": bool,
    "text_truth": {...} | absent}."""
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
            return _apply_text_truth_gate(db, request_id, image_bytes, spec, verdict)
        except Exception as exc:
            last_exc = exc

    log_usage(
        db, request_id,
        provider="openrouter", model=settings.QA_MODEL, purpose="image_qa",
        success=False, error=f"failed after retry: {str(last_exc)[:480]}",
    )
    logger.warning("image QA failed open after retry: request=%s error=%s", request_id, last_exc)
    # Still gated: the aesthetic judge being down is no reason to ship the
    # client's name misspelled — that check is a separate call and may well
    # have succeeded.
    return _apply_text_truth_gate(
        db, request_id, image_bytes, spec,
        {"score": None, "issues": [f"qa-failed after retry: {str(last_exc)[:120]}"], "approved": True},
    )
