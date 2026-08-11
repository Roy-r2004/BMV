"""Stage 5: renders the demo screenshots from the structured UIDemoSpecs.

    anchor screen: 3 DISTINCT composition-variant prompts (not re-rolls of
        one prompt) -> vision QA each -> select strongest approved ->
        (max one regeneration, retrying the best-scoring variant) -> watermark -> save
    follow-up screens: same as before -> N re-rolls of one prompt (with the
        winning anchor attached as a style reference) -> vision QA -> select
        -> (max one regeneration) -> watermark -> save

Composition strategy is a first-class generation variable (not sampling
noise): each anchor candidate gets a genuinely different art-direction
directive (prompt_builder.COMPOSITION_VARIANTS) layered on identical
data/branding/design constraints, so the 3 candidates explore real layout
alternatives. Which variant wins is business-dependent — nothing here
assumes one variant is always best; every generation scores fresh.

QA and regeneration are config knobs (see config.py) because this is lead
gen — cost per request matters.

All AI calls happen in worker threads (network-bound); DB writes and QA
bookkeeping stay on the calling thread, same discipline as the rest of the
pipeline.
"""

import io
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from PIL import Image
from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import GeneratedImage, Request
from app.pipeline import prompt_builder, qa
from app.pipeline._shared import log_usage
from app.ui_spec import UIDemoSpec

logger = logging.getLogger("consultant.images")


@lru_cache(maxsize=1)
def _bmv_logo() -> Image.Image | None:
    if not os.path.isfile(settings.BMV_LOGO_PATH):
        return None
    return Image.open(settings.BMV_LOGO_PATH).convert("RGBA")


def _apply_bmv_watermark(image_bytes: bytes) -> bytes:
    """Composites the real BMV logo into the bottom-right corner — more
    reliable than asking the image model to draw legible small text (we've
    seen it garble URLs/labels at that scale). No-op if the logo file isn't
    present, so this never breaks image generation.
    """
    logo = _bmv_logo()
    if logo is None:
        return image_bytes

    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    mark_size = max(48, min(120, round(base.width * 0.07)))
    padding = round(base.width * 0.02)
    mark = logo.resize((mark_size, mark_size), Image.LANCZOS)
    base.paste(mark, (base.width - mark_size - padding, base.height - mark_size - padding), mark)

    out = io.BytesIO()
    base.save(out, format="PNG")
    return out.getvalue()


def _decodable(image_bytes: bytes) -> bool:
    try:
        Image.open(io.BytesIO(image_bytes)).load()
        return True
    except Exception:
        return False


def _generate_candidates(
    prompts: list[dict], reference_images: list[bytes] | None,
    fallback_prompt: str | None = None,
) -> list[dict]:
    """Fires one call per entry in `prompts` (each `{"prompt": str,
    "variant_id": str | None}`) in parallel. For the anchor screen these are
    3 genuinely different composition-variant prompts; for follow-up
    screens (and anchor regeneration retries) it's the same prompt repeated.
    Each result: {"prompt", "variant_id", "image_bytes", "usage",
    "latency_s", "error", "used_reference", "dropped_reference_error"}.

    A call made WITH a reference image that fails is retried once without
    it — some models can't take image input, and a slightly less consistent
    screenshot beats no screenshot. The retry uses `fallback_prompt`: the
    continuation prompt says "the attached image is..." and orders the model
    to preserve a design it can't see, so it must never be sent without its
    attachment (found in review).

    Bytes that don't decode as an image are treated as a failed candidate
    here, so junk model output degrades to a retry instead of crashing the
    save step and failing the whole request.
    """

    def _one(item: dict) -> dict:
        prompt = item["prompt"]
        variant_id = item.get("variant_id")
        start = time.monotonic()
        refs = reference_images
        dropped_reference_error: Exception | None = None
        try:
            result = provider.generate_image(prompt, reference_images=refs)
        except Exception as first_exc:
            if not refs:
                return {"error": first_exc, "latency_s": time.monotonic() - start, "variant_id": variant_id, "prompt": prompt}
            try:
                dropped_reference_error = first_exc
                refs = None
                result = provider.generate_image(fallback_prompt or prompt)
            except Exception as second_exc:
                return {"error": second_exc, "latency_s": time.monotonic() - start, "variant_id": variant_id, "prompt": prompt}
        if not _decodable(result.get("image_bytes") or b""):
            return {
                "error": ValueError("model returned undecodable image bytes"),
                "latency_s": time.monotonic() - start, "variant_id": variant_id, "prompt": prompt,
            }
        return {
            "prompt": prompt,
            "variant_id": variant_id,
            "image_bytes": result["image_bytes"],
            "usage": result.get("usage"),
            "latency_s": time.monotonic() - start,
            "error": None,
            "used_reference": bool(refs),
            "dropped_reference_error": dropped_reference_error,
        }

    with ThreadPoolExecutor(max_workers=min(4, max(1, len(prompts)))) as pool:
        return list(pool.map(_one, prompts))


def _select_best(candidates: list[dict]) -> dict | None:
    """Best approved candidate by QA score; unscored (fail-open) approvals
    rank below scored ones. Returns None when nothing was approved."""
    approved = [c for c in candidates if c.get("verdict", {}).get("approved")]
    if not approved:
        return None
    return max(approved, key=lambda c: (c["verdict"]["score"] is not None, c["verdict"]["score"] or 0))


def _render_screen(
    db: Session,
    request_id: int,
    spec: UIDemoSpec,
    prompts: list[dict],
    prompt_version: str,
    reference_images: list[bytes] | None,
    fallback_prompt: str | None = None,
) -> tuple[dict | None, list[dict]]:
    """Generates candidates for one screen (one call per entry in `prompts`
    — either N re-rolls of the same prompt or N distinct composition
    variants), QAs them, applies the (single) regeneration pass if nothing
    was approved, and returns (selected_candidate_or_best_effort,
    all_candidates)."""
    candidates = _generate_candidates(prompts, reference_images, fallback_prompt)

    scored: list[dict] = []
    for i, cand in enumerate(candidates):
        if cand.get("error") is not None:
            log_usage(
                db, request_id,
                provider="openrouter", model=settings.IMAGE_MODEL, purpose="image",
                image_count=1, success=False, error=str(cand["error"])[:500],
            )
            logger.warning(
                "candidate failed: request=%s screen=%s attempt=%s variant=%s error=%s",
                request_id, spec.screen_slug, i, cand.get("variant_id"), cand["error"],
            )
            continue
        if cand.get("dropped_reference_error") is not None:
            # The billed-or-not first attempt with the reference must still
            # leave a trace — otherwise the retry makes it look like the
            # reference path never failed at all.
            log_usage(
                db, request_id,
                provider="openrouter", model=settings.IMAGE_MODEL, purpose="image",
                image_count=1, success=False,
                error=f"reference attempt failed, retried without: {str(cand['dropped_reference_error'])[:400]}",
            )
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.IMAGE_MODEL, purpose="image",
            usage=cand.get("usage"), image_count=1, success=True,
        )
        cand["verdict"] = qa.review_image(db, request_id, cand["image_bytes"], spec)
        cand["attempt"] = i
        logger.info(
            "candidate scored: request=%s screen=%s archetype=%s model=%s attempt=%s variant=%s "
            "latency=%.1fs qa_score=%s approved=%s issues=%s",
            request_id, spec.screen_slug, spec.style.archetype, settings.IMAGE_MODEL, i, cand.get("variant_id"),
            cand["latency_s"], cand["verdict"]["score"], cand["verdict"]["approved"],
            "; ".join(cand["verdict"]["issues"][:3]) or "-",
        )
        scored.append(cand)

    selected = _select_best(scored)
    # Regenerate when nothing was approved — INCLUDING when every candidate
    # errored (scored empty): parallel candidates fail together on transient
    # provider blips, and that's exactly when one spaced retry saves the
    # request (found in review — the old `and scored` guard skipped it).
    # The retry reuses whichever prompt scored best so far (or the first
    # prompt if everything errored) rather than re-firing every variant —
    # keeps the regeneration budget at exactly +1 image regardless of mode.
    if selected is None and settings.MAX_REGENERATIONS > 0:
        if scored:
            retry_source = max(scored, key=lambda c: c["verdict"]["score"] or 0)
        else:
            retry_source = prompts[0]
        retry_item = {"prompt": retry_source["prompt"], "variant_id": retry_source.get("variant_id")}
        logger.info(
            "no approved candidate, regenerating once: request=%s screen=%s variant=%s",
            request_id, spec.screen_slug, retry_item["variant_id"],
        )
        extra = _generate_candidates([retry_item], reference_images, fallback_prompt)
        for cand in extra:
            if cand.get("error") is not None:
                log_usage(
                    db, request_id,
                    provider="openrouter", model=settings.IMAGE_MODEL, purpose="image",
                    image_count=1, success=False, error=str(cand["error"])[:500],
                )
                continue
            log_usage(
                db, request_id,
                provider="openrouter", model=settings.IMAGE_MODEL, purpose="image",
                usage=cand.get("usage"), image_count=1, success=True,
            )
            cand["verdict"] = qa.review_image(db, request_id, cand["image_bytes"], spec)
            cand["attempt"] = len(scored)
            scored.append(cand)
        selected = _select_best(scored)

    if selected is None and scored:
        # Nothing approved even after regeneration: ship the best-scoring
        # candidate anyway. A weaker screenshot beats a failed request.
        selected = max(scored, key=lambda c: c["verdict"]["score"] or 0)
        logger.warning(
            "shipping unapproved best-effort candidate: request=%s screen=%s score=%s",
            request_id, spec.screen_slug, selected["verdict"]["score"],
        )
    return selected, scored


def _save_selected(
    db: Session,
    request_id: int,
    spec: UIDemoSpec,
    archetype_id: str,
    selected: dict,
    all_candidates: list[dict],
    prompt_version: str,
) -> GeneratedImage:
    out_dir = os.path.join(settings.UPLOADS_DIR, "images", str(request_id))
    os.makedirs(out_dir, exist_ok=True)

    file_name = f"{spec.screen_slug}_0.png"
    with open(os.path.join(out_dir, file_name), "wb") as f:
        f.write(_apply_bmv_watermark(selected["image_bytes"]))

    # Non-selected candidates + per-image metadata go to disk (not the DB) —
    # enough to compare prompt/model/composition performance later without
    # bloating rows.
    candidates_dir = os.path.join(out_dir, "candidates")
    os.makedirs(candidates_dir, exist_ok=True)
    for cand in all_candidates:
        if cand is not selected:
            with open(os.path.join(candidates_dir, f"{spec.screen_slug}_cand{cand['attempt']}.png"), "wb") as f:
                f.write(cand["image_bytes"])

    composition_variant = selected.get("variant_id")
    saved_prompt_version = prompt_version + ("+composition" if composition_variant else "")
    metadata = {
        "business_id": request_id,
        "screen": spec.product.screen_type,
        "archetype": archetype_id,
        "composition_variant": composition_variant,
        "provider": "openrouter",
        "model": settings.IMAGE_MODEL,
        "prompt_version": saved_prompt_version,
        "qa_score": selected["verdict"]["score"],
        "qa_issues": selected["verdict"]["issues"],
        "candidates": [
            {
                "attempt": c["attempt"],
                "variant": c.get("variant_id"),
                "qa_score": c["verdict"]["score"],
                "approved": c["verdict"]["approved"],
                "latency_s": round(c["latency_s"], 1),
                "selected": c is selected,
            }
            for c in all_candidates
        ],
    }
    with open(os.path.join(out_dir, f"{spec.screen_slug}_0.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    row = GeneratedImage(
        request_id=request_id,
        role_id=spec.screen_slug,
        role_label=spec.screen_title,
        variant=0,
        file_path=f"/uploads/images/{request_id}/{file_name}",
        prompt=selected["prompt"],
        screen_type=spec.product.screen_type,
        archetype=archetype_id,
        composition_variant=composition_variant,
        provider="openrouter",
        model=settings.IMAGE_MODEL,
        prompt_version=saved_prompt_version,
        qa_score=selected["verdict"]["score"],
        qa_issues=json.dumps(selected["verdict"]["issues"]),
    )
    db.add(row)
    db.commit()
    return row


def generate_demo_screens(
    db: Session,
    request_id: int,
    archetype_id: str,
    ui_specs: list[UIDemoSpec],
    anchor_reference_images: list[bytes] | None = None,
) -> list[GeneratedImage]:
    """anchor_reference_images: optional EXTERNAL style-reference image(s)
    attached to the anchor call itself (not the usual follow-up-screen
    references). Tested and found to lower quality (the model tends to
    clone the reference cheaply rather than exceed it) — normal runs never
    pass this; kept only so the comparison remains reproducible."""
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")
    if not ui_specs:
        return []

    saved: list[GeneratedImage] = []

    # ── Anchor screen: 3 distinct composition variants, not re-rolls ──────
    anchor_spec = ui_specs[0]
    anchor_prompts = [
        {
            "prompt": prompt_builder.build_dashboard_image_prompt(anchor_spec, composition=variant),
            "variant_id": variant["id"],
        }
        for variant in prompt_builder.COMPOSITION_VARIANTS
    ]
    anchor_selected, anchor_pool = _render_screen(
        db, request_id, anchor_spec, anchor_prompts,
        prompt_builder.DASHBOARD_IMAGE_PROMPT_VERSION,
        reference_images=anchor_reference_images,
    )
    if anchor_selected is None:
        logger.error("anchor screen produced no usable image: request=%s", request_id)
        return []
    saved.append(
        _save_selected(
            db, request_id, anchor_spec, archetype_id, anchor_selected, anchor_pool,
            prompt_builder.DASHBOARD_IMAGE_PROMPT_VERSION,
        )
    )

    # ── Follow-up screens: anchor attached as the style reference ─────────
    anchor_reference = [anchor_selected["image_bytes"]] if settings.USE_REFERENCE_IMAGES else None
    for spec in ui_specs[1:]:
        standalone_prompt = prompt_builder.build_dashboard_image_prompt(spec)
        if settings.USE_REFERENCE_IMAGES:
            prompt = prompt_builder.build_continuation_prompt(spec, anchor_spec.screen_title)
            version = prompt_builder.SCREEN_CONTINUATION_PROMPT_VERSION
        else:
            prompt = standalone_prompt
            version = prompt_builder.DASHBOARD_IMAGE_PROMPT_VERSION
        prompts = [{"prompt": prompt, "variant_id": None} for _ in range(settings.SECONDARY_CANDIDATES)]
        selected, pool = _render_screen(
            db, request_id, spec, prompts, version,
            reference_images=anchor_reference, fallback_prompt=standalone_prompt,
        )
        if selected is None:
            logger.warning("screen produced no usable image, skipping: request=%s screen=%s", request_id, spec.screen_slug)
            continue
        saved.append(_save_selected(db, request_id, spec, archetype_id, selected, pool, version))

    return saved
