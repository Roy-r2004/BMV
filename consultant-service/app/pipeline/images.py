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

Threading (session 34): follow-up SCREENS run concurrently, each on its
own DB session (orchestrator.run's own pattern) — they are independent of
each other and serializing them was the request path's biggest block of
avoidable wall clock. Within a screen, candidate generations run in
parallel as before, and qa.review_image fires its three instruments
concurrently. No SQLAlchemy Session is ever shared across threads: the
caller's session handles the anchor, each screen worker owns one for its
subtree.
"""

import io
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from PIL import Image, ImageChops, ImageFilter, ImageStat
from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import GeneratedImage, Request
from app.pipeline import compositing, prompt_builder, qa
from app.pipeline._shared import log_usage
from app.ui_spec import UIDemoSpec

logger = logging.getLogger("consultant.images")


@lru_cache(maxsize=1)
def _bmv_logo() -> Image.Image | None:
    if not os.path.isfile(settings.BMV_LOGO_PATH):
        return None
    return Image.open(settings.BMV_LOGO_PATH).convert("RGBA")


def _mean_edge_color(base: Image.Image) -> tuple[int, int, int]:
    """Average colour of the interface's bottom edge — the footer strip is
    tinted from it so the bar reads as part of the same object rather than
    a black rectangle stapled underneath."""
    band = base.convert("RGB").crop((0, max(0, base.height - 4), base.width, base.height))
    pixels = list(band.getdata()) or [(20, 20, 20)]
    n = len(pixels)
    return tuple(sum(p[i] for p in pixels) // n for i in range(3))  # type: ignore[return-value]


def _footer_watermark(image_bytes: bytes, logo: Image.Image) -> bytes:
    """Grows the canvas by a thin strip BELOW the interface and puts the mark
    there. The rendered UI is never covered, which is the whole point: the
    corner variant needed the image prompt to keep a 12%x17% block of canvas
    empty, and that reservation lost three separate comparisons in session 31
    (see docs/evidence/session31/art-packs-ab.md). Costs ~5% of height."""
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    # 6%, not 5%: at 5% of a 1408x806 anchor the mark lands at ~24px and reads
    # as a speck on the strip. Checked by looking at it, not by arithmetic.
    strip_h = max(28, round(base.height * 0.06))

    r, g, b = _mean_edge_color(base)
    strip_color = tuple(max(10, round(c * 0.18)) for c in (r, g, b))

    canvas = Image.new("RGBA", (base.width, base.height + strip_h), (*strip_color, 255))
    canvas.paste(base, (0, 0))
    # Hairline separator so the strip has an edge instead of bleeding into a
    # dark interface — visible in both registers, invisible as a "border".
    hairline = Image.new("RGBA", (base.width, 1), (255, 255, 255, 38))
    canvas.alpha_composite(hairline, (0, base.height))

    pad = max(2, strip_h // 8)
    mark_size = max(6, min(strip_h - 2 * pad, base.width - 2))
    mark = logo.resize((mark_size, mark_size), Image.LANCZOS)
    x = max(0, base.width - mark_size - max(pad, round(base.width * 0.015)))
    y = base.height + (strip_h - mark_size) // 2
    canvas.paste(mark, (x, y), mark)

    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def _corner_watermark(image_bytes: bytes, logo: Image.Image) -> bytes:
    """The original mark, pasted over the bottom-right of the interface.
    Retained so the footer change can be compared against it and rolled back
    from one env var — not because anything selects it."""
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    mark_size = max(48, min(120, round(base.width * 0.07)))
    padding = round(base.width * 0.02)
    mark = logo.resize((mark_size, mark_size), Image.LANCZOS)
    base.paste(mark, (base.width - mark_size - padding, base.height - mark_size - padding), mark)

    out = io.BytesIO()
    base.save(out, format="PNG")
    return out.getvalue()


def _apply_bmv_watermark(image_bytes: bytes) -> bytes:
    """Composites the real BMV logo onto an image — more reliable than asking
    the image model to draw legible small text (we've seen it garble
    URLs/labels at that scale). No-op if the logo file isn't present, so this
    never breaks image generation.

    EVERY byte written under UPLOADS_DIR goes through here; the directory is
    statically served, so an unmarked file is an unbranded full-quality demo
    at a guessable URL. Pinned by tests/test_images_hardening.py.
    """
    logo = _bmv_logo()
    if logo is None:
        return image_bytes
    if settings.WATERMARK_STYLE == "corner":
        return _corner_watermark(image_bytes, logo)
    return _footer_watermark(image_bytes, logo)


def _decodable(image_bytes: bytes) -> bool:
    try:
        Image.open(io.BytesIO(image_bytes)).load()
        return True
    except Exception:
        return False


def _floating_backdrop_bbox(im: Image.Image) -> tuple[int, int, int, int] | None:
    """Where the model drew the interface as a card floating on a backdrop,
    the box to crop to — None when the screen is full-bleed and must not be
    touched.

    The prompt forbids the backdrop in two places and the model draws it
    anyway (5 of 15 screens on the session-33 set; session 32 "fixed" it
    twice). So this stops asking and detects it instead, from the one
    property that separates a backdrop from the interface: the interface has
    small text and hairlines everywhere — high LOCAL contrast — while a
    backdrop, flat or gradient, has almost none. The bounding box of
    local-contrast pixels is the interface plus anything hanging off it,
    which is exactly what the brief says to keep.

    Three guards, each of which independently refuses the crop, because a
    false positive that shaves real UI is much worse than a missed backdrop:

      1. the content box must float — a real margin on ALL four sides
         (full-bleed screens touch at least one edge);
      2. it must fill most of the frame — this is a screenshot, not a
         thumbnail on a poster;
      3. the ring must be a DIFFERENT surface from the interface's own
         ground, where "ground" is sampled from the FLAT pixels of a frame
         just inside the box edge — the app's own padding. On a full-bleed
         screen that frame is literally the same surface as the ring;
         under a floating card it is the card, a different color entirely
         (distance ~240 on the salon set vs ~10 on full-bleed law). Two
         earlier cuts of this guard are worth remembering: a thin
         unmasked band at the box edge let PANEL EDGES dominate and
         false-positived two full-bleed law screens, and flat pixels over
         the whole interior let a large smooth PHOTOGRAPH drag the mean
         and false-positived all three. Padding ground, flat-masked, is
         the surface the ring must be compared against. Too few flat
         pixels to establish ground = refuse, same as every other doubt.
    """
    rgb = im.convert("RGB")
    width, height = rgb.size
    # Local contrast: the difference between the image and a lightly blurred
    # copy of itself. Text and hairlines survive; flat color and smooth
    # gradients cancel to ~0. MinFilter kills isolated grain so a noisy
    # backdrop pixel cannot inflate the box.
    contrast = ImageChops.difference(rgb, rgb.filter(ImageFilter.GaussianBlur(2))).convert("L")
    mask = contrast.point(lambda p: 255 if p >= 8 else 0).filter(ImageFilter.MinFilter(3))
    bbox = mask.getbbox()
    if bbox is None:
        return None
    # 3px INSIDE the contrast boundary: the card's edge is a soft multi-pixel
    # blend into the backdrop, and cropping at the outermost contrast pixel
    # keeps a visible sliver of it. Content sits far deeper inside the card
    # than 3px (the card's own padding), so this cuts blend, never UI.
    left, top, right, bottom = bbox[0] + 3, bbox[1] + 3, bbox[2] - 3, bbox[3] - 3
    margins = (left, top, width - right, height - bottom)
    if min(margins) < max(6, round(0.012 * min(width, height))):
        return None
    if (right - left) < 0.55 * width or (bottom - top) < 0.55 * height:
        return None
    # A floating card is drawn roughly centered — near-even margins (the
    # salon set: 21-26px all round). App padding is NOT symmetric: the nav
    # bar hugs the top, so a full-bleed screen's content box sits high
    # (session-33 law: 18px top vs 61px bottom — and that screen must not
    # be cropped). Lopsided margins mean this is layout, not a backdrop.
    if max(margins) / max(1, min(margins)) > 2.5:
        return None

    def _mean(box: tuple[int, int, int, int], stat_mask: Image.Image | None = None) -> tuple[float, ...]:
        region = rgb.crop(box)
        if stat_mask is None:
            return tuple(ImageStat.Stat(region).mean)
        return tuple(ImageStat.Stat(region, stat_mask.crop(box)).mean)

    # The ring: everything outside the content box, sampled as four strips.
    ring_strips = [
        _mean((0, 0, width, top)),
        _mean((0, bottom, width, height)),
        _mean((0, top, left, bottom)),
        _mean((right, top, width, bottom)),
    ]
    ring = tuple(sum(c[i] for c in ring_strips) / len(ring_strips) for i in range(3))

    # The interface's own ground: flat pixels of a frame just inside the box
    # edge (3px of edge blend skipped, then a band ~4% of the frame deep).
    frame_t = max(12, round(0.04 * min(right - left, bottom - top)))
    frame_box = (left + 3, top + 3, right - 3, bottom - 3)
    flat = mask.crop(frame_box).point(lambda p: 0 if p else 255)
    core = (frame_t, frame_t, (frame_box[2] - frame_box[0]) - frame_t, (frame_box[3] - frame_box[1]) - frame_t)
    if core[2] > core[0] and core[3] > core[1]:
        flat.paste(0, core)  # only the frame band counts, not the interior
    stat = ImageStat.Stat(rgb.crop(frame_box), flat)
    if sum(stat.count) < 3 * 500:
        return None  # not enough flat padding to establish a ground
    interior = tuple(stat.mean)

    if sum((a - b) ** 2 for a, b in zip(ring, interior)) ** 0.5 < 40:
        return None
    return (left, top, right, bottom)


def _crop_floating_backdrop(image_bytes: bytes) -> bytes:
    """Applied to every screen candidate before QA, so the judge scores what
    would actually ship. Returns the bytes unchanged — bit for bit — unless
    every guard in _floating_backdrop_bbox agrees there is a backdrop, and
    returns the original on ANY failure: a crop must never cost a request
    its screenshot."""
    if not settings.ENABLE_BACKDROP_CROP:
        return image_bytes
    try:
        im = Image.open(io.BytesIO(image_bytes))
        bbox = _floating_backdrop_bbox(im)
        if bbox is None:
            return image_bytes
        out = io.BytesIO()
        im.crop(bbox).save(out, format="PNG")
        logger.info(
            "cropped a floating backdrop: %sx%s -> %sx%s",
            im.width, im.height, bbox[2] - bbox[0], bbox[3] - bbox[1],
        )
        return out.getvalue()
    except Exception as exc:
        logger.warning("backdrop crop failed, keeping the original bytes: %s", exc)
        return image_bytes


def _generate_candidates(
    prompts: list[dict], reference_images: list[bytes] | None,
    fallback_prompt: str | None = None,
) -> list[dict]:
    """Fires one call per entry in `prompts` (each `{"prompt": str,
    "variant_id": str | None, "model": str | None}`) in parallel. For the
    anchor screen these are 3 genuinely different composition-variant
    prompts; for follow-up screens (and anchor regeneration retries) it's
    the same prompt repeated. Each result: {"prompt", "variant_id", "model",
    "image_bytes", "usage", "latency_s", "error", "used_reference",
    "dropped_reference_error"}.

    `model` is a per-call generation variable, exactly like `variant_id`:
    resolved once here (falling back to settings.IMAGE_MODEL) and carried on
    every result — including failures — so the ledger, the log line and the
    saved metadata record the model that ACTUALLY produced each candidate.
    That's what makes a bake-off matrix and per-role tiering (pro-class
    anchor, flash-class follow-ups) expressible without a global mutation.

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
        model = item.get("model") or settings.IMAGE_MODEL
        # Per-item like `model`, and carried on every result — including
        # failures — so the regeneration retry re-fires the size the
        # original candidate ran at rather than silently reverting.
        image_config = item.get("image_config")
        start = time.monotonic()
        refs = reference_images
        dropped_reference_error: Exception | None = None
        try:
            result = provider.generate_image(prompt, model=model, reference_images=refs, image_config=image_config)
        except Exception as first_exc:
            if not refs:
                return {"error": first_exc, "latency_s": time.monotonic() - start, "variant_id": variant_id, "model": model, "prompt": prompt, "image_config": image_config}
            try:
                dropped_reference_error = first_exc
                refs = None
                result = provider.generate_image(fallback_prompt or prompt, model=model, image_config=image_config)
            except Exception as second_exc:
                return {"error": second_exc, "latency_s": time.monotonic() - start, "variant_id": variant_id, "model": model, "prompt": prompt, "image_config": image_config}
        if not _decodable(result.get("image_bytes") or b""):
            return {
                "error": ValueError("model returned undecodable image bytes"),
                "latency_s": time.monotonic() - start, "variant_id": variant_id, "model": model, "prompt": prompt, "image_config": image_config,
            }
        return {
            "prompt": prompt,
            "variant_id": variant_id,
            "model": model,
            "image_config": image_config,
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
        cand_model = cand.get("model") or settings.IMAGE_MODEL
        if cand.get("error") is not None:
            log_usage(
                db, request_id,
                provider="openrouter", model=cand_model, purpose="image",
                image_count=1, success=False, error=str(cand["error"])[:500],
                screen=spec.screen_slug,
            )
            logger.warning(
                "candidate failed: request=%s screen=%s attempt=%s variant=%s model=%s error=%s",
                request_id, spec.screen_slug, i, cand.get("variant_id"), cand_model, cand["error"],
            )
            continue
        if cand.get("dropped_reference_error") is not None:
            # The billed-or-not first attempt with the reference must still
            # leave a trace — otherwise the retry makes it look like the
            # reference path never failed at all.
            log_usage(
                db, request_id,
                provider="openrouter", model=cand_model, purpose="image",
                image_count=1, success=False,
                error=f"reference attempt failed, retried without: {str(cand['dropped_reference_error'])[:400]}",
                screen=spec.screen_slug,
            )
        log_usage(
            db, request_id,
            provider="openrouter", model=cand_model, purpose="image",
            usage=cand.get("usage"), image_count=1, success=True,
            screen=spec.screen_slug,
        )
        # Backdrop crop BEFORE QA: the judge must score the artifact that
        # would ship, and a screen that stops floating here needs no
        # regeneration for having floated.
        cand["image_bytes"] = _crop_floating_backdrop(cand["image_bytes"])
        cand["verdict"] = qa.review_image(db, request_id, cand["image_bytes"], spec)
        # Attempt numbers double as candidate FILENAMES in _save_selected, so
        # they must be unique among *scored* candidates. The positional index
        # is not: with [ok, error, ok] the survivors take 0 and 2, and the
        # regeneration pass (len(scored) == 2) collides with the last one —
        # two images writing cand2.png, one silently overwriting the other.
        cand["attempt"] = len(scored)
        logger.info(
            "candidate scored: request=%s screen=%s archetype=%s model=%s attempt=%s variant=%s "
            "latency=%.1fs qa_score=%s approved=%s issues=%s",
            request_id, spec.screen_slug, spec.style.archetype, cand_model, i, cand.get("variant_id"),
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
        # The retry inherits the retried candidate's own model, not the
        # global default — under tiering/bake-off the two differ, and a
        # regeneration silently switching models would make the ledger and
        # the saved metadata describe a run that never happened.
        retry_item = {
            "prompt": retry_source["prompt"],
            "variant_id": retry_source.get("variant_id"),
            "model": retry_source.get("model"),
            "image_config": retry_source.get("image_config"),
        }
        logger.info(
            "no approved candidate, regenerating once: request=%s screen=%s variant=%s model=%s",
            request_id, spec.screen_slug, retry_item["variant_id"], retry_item["model"] or settings.IMAGE_MODEL,
        )
        extra = _generate_candidates([retry_item], reference_images, fallback_prompt)
        for cand in extra:
            cand_model = cand.get("model") or settings.IMAGE_MODEL
            if cand.get("error") is not None:
                log_usage(
                    db, request_id,
                    provider="openrouter", model=cand_model, purpose="image",
                    image_count=1, success=False, error=str(cand["error"])[:500],
                    screen=spec.screen_slug,
                )
                continue
            log_usage(
                db, request_id,
                provider="openrouter", model=cand_model, purpose="image",
                usage=cand.get("usage"), image_count=1, success=True,
                screen=spec.screen_slug,
            )
            cand["image_bytes"] = _crop_floating_backdrop(cand["image_bytes"])
            cand["verdict"] = qa.review_image(db, request_id, cand["image_bytes"], spec)
            cand["attempt"] = len(scored)
            scored.append(cand)
        selected = _select_best(scored)

    if selected is None and scored:
        # Nothing approved even after regeneration: ship the best candidate
        # anyway. A weaker screenshot beats a failed request.
        #
        # Text truth outranks the aesthetic score here, and only here. When
        # every candidate has been rejected, the choice is between a
        # prettier screen carrying the client's name misspelled and a
        # plainer one that spells it right — and the misspelling is the
        # thing a prospect actually notices. Candidates whose transcription
        # call failed (passed is None) rank between the two: unknown, not
        # known-bad.
        #
        # Confirmed structural defects rank the same way, between text and
        # score: on the first funded run of the defect check (request 77,
        # session 34) the dashboard's regeneration produced a CLEAN 7.8 and
        # this rank shipped the 8.1 carrying a verifier-confirmed floating
        # backdrop instead. A prospect notices the defect, not the 0.3.
        def _fallback_rank(cand: dict) -> tuple[int, int, float]:
            passed = (cand["verdict"].get("text_truth") or {}).get("passed", None)
            text_rank = {True: 2, None: 1, False: 0}[passed]
            clean_rank = 0 if (cand["verdict"].get("defects") or {}).get("confirmed") else 1
            return text_rank, clean_rank, cand["verdict"]["score"] or 0

        selected = max(scored, key=_fallback_rank)
        logger.warning(
            "shipping unapproved best-effort candidate: request=%s screen=%s score=%s text_truth=%s",
            request_id, spec.screen_slug, selected["verdict"]["score"],
            (selected["verdict"].get("text_truth") or {}).get("passed"),
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
    nav_edge: str = "left",
) -> GeneratedImage:
    out_dir = os.path.join(settings.UPLOADS_DIR, "images", str(request_id))
    os.makedirs(out_dir, exist_ok=True)

    file_name = f"{spec.screen_slug}_0.png"
    with open(os.path.join(out_dir, file_name), "wb") as f:
        f.write(_apply_bmv_watermark(selected["image_bytes"]))

    # W4 presentation composites, built from the RAW bytes: the compositor
    # puts the BMV mark on its own backdrop, clear of the interface, so the
    # hero shot is not carrying two logos (and not carrying one over a
    # card). Still branded, so the "no unbranded bytes under /uploads"
    # policy holds for these files too. Deterministic and free — a failure
    # here must never cost a request its screenshot, so it is logged and
    # swallowed.
    composites: list[str] = []
    if settings.ENABLE_PRESENTATION_COMPOSITING:
        try:
            for variant, data in compositing.compose_presentation(
                selected["image_bytes"],
                primary_color=spec.business.primary_color,
                secondary_color=spec.business.secondary_color,
                logo_path=settings.BMV_LOGO_PATH,
                nav_edge=nav_edge,
            ).items():
                composite_name = f"{spec.screen_slug}_{variant}.png"
                with open(os.path.join(out_dir, composite_name), "wb") as f:
                    f.write(data)
                composites.append(composite_name)
        except Exception as exc:
            logger.warning(
                "presentation compositing failed, shipping the screenshot alone: request=%s screen=%s error=%s",
                request_id, spec.screen_slug, exc,
            )

    # Non-selected candidates + per-image metadata go to disk (not the DB) —
    # enough to compare prompt/model/composition performance later without
    # bloating rows. Watermarked like the selected image: everything under
    # UPLOADS_DIR is statically served (main.py mounts /uploads), so a raw
    # candidate here is a full-quality UNBRANDED copy of the demo at a
    # guessable URL — exactly what the watermark exists to prevent.
    candidates_dir = os.path.join(out_dir, "candidates")
    os.makedirs(candidates_dir, exist_ok=True)
    for cand in all_candidates:
        if cand is not selected:
            with open(os.path.join(candidates_dir, f"{spec.screen_slug}_cand{cand['attempt']}.png"), "wb") as f:
                f.write(_apply_bmv_watermark(cand["image_bytes"]))

    composition_variant = selected.get("variant_id")
    selected_model = selected.get("model") or settings.IMAGE_MODEL
    saved_prompt_version = prompt_version + ("+composition" if composition_variant else "")
    metadata = {
        "business_id": request_id,
        "screen": spec.product.screen_type,
        "archetype": archetype_id,
        "composition_variant": composition_variant,
        "provider": "openrouter",
        "model": selected_model,
        "prompt_version": saved_prompt_version,
        "qa_score": selected["verdict"]["score"],
        "qa_issues": selected["verdict"]["issues"],
        "text_truth": selected["verdict"].get("text_truth"),
        "defects": selected["verdict"].get("defects"),
        "composites": composites,
        "candidates": [
            {
                "attempt": c["attempt"],
                "variant": c.get("variant_id"),
                "model": c.get("model") or settings.IMAGE_MODEL,
                "qa_score": c["verdict"]["score"],
                "text_truth_passed": (c["verdict"].get("text_truth") or {}).get("passed"),
                "defects_confirmed": len((c["verdict"].get("defects") or {}).get("confirmed", [])),
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
        model=selected_model,
        prompt_version=saved_prompt_version,
        qa_score=selected["verdict"]["score"],
        qa_issues=json.dumps(selected["verdict"]["issues"]),
        text_truth_json=(
            json.dumps(selected["verdict"]["text_truth"])
            if selected["verdict"].get("text_truth") is not None else None
        ),
        # The spec the shipped candidate was drawn from — see the column's
        # comment. Stored whole rather than as a hand-picked slice: the
        # result page projects what it needs, and a spec that outlives its
        # render costs a few KB against never being able to reconstruct it.
        spec_json=spec.model_dump_json(),
    )
    db.add(row)
    db.commit()
    return row


def _save_design_sheet(request_id: int, image_bytes: bytes) -> None:
    """The style board lands beside the screens, watermarked like every
    other byte under UPLOADS_DIR (it is statically served)."""
    out_dir = os.path.join(settings.UPLOADS_DIR, "images", str(request_id))
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "design_sheet.png"), "wb") as f:
        f.write(_apply_bmv_watermark(image_bytes))


def generate_demo_screens(
    db: Session,
    request_id: int,
    archetype_id: str,
    ui_specs: list[UIDemoSpec],
    anchor_reference_images: list[bytes] | None = None,
    anchor_model: str | None = None,
    followup_model: str | None = None,
    use_design_sheet: bool | None = None,
) -> list[GeneratedImage]:
    """anchor_reference_images: optional EXTERNAL style-reference image(s)
    attached to the anchor call itself (not the usual follow-up-screen
    references). Tested and found to lower quality (the model tends to
    clone the reference cheaply rather than exceed it) — normal runs never
    pass this; kept only so the comparison remains reproducible.

    anchor_model / followup_model: per-ROLE model overrides. Split in two
    because the anchor and the follow-ups are different jobs — the anchor
    invents the design from scratch, the follow-ups copy a design they're
    handed as a reference image — which is exactly what makes tiering
    (pro-class anchor, flash-class follow-ups) plausible. Both default to
    the per-archetype config default, so an ordinary request is unchanged.

    use_design_sheet (W5): generate a design-system style board first and
    condition EVERY screen on it, including the anchor, instead of letting
    follow-ups inherit whatever the anchor happened to do. Costs one extra
    image; off unless the experiment says otherwise."""
    anchor_model = anchor_model or settings.anchor_model_for(archetype_id)
    followup_model = followup_model or settings.followup_model_for(archetype_id)
    if use_design_sheet is None:
        use_design_sheet = settings.USE_DESIGN_SHEET
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")
    if not ui_specs:
        return []

    saved: list[GeneratedImage] = []

    # ── W5: the design sheet, generated before any screen ─────────────────
    # A failure here must not cost the request its screenshots, so it
    # degrades to the ordinary anchor-as-reference path.
    if use_design_sheet and not anchor_reference_images:
        sheet = _generate_candidates(
            [{
                "prompt": prompt_builder.build_design_sheet_prompt(ui_specs[0], archetype_id),
                "variant_id": "design-sheet",
                "model": anchor_model,
                "image_config": settings.image_config_for_role("anchor"),
            }],
            None,
        )[0]
        cand_model = sheet.get("model") or settings.IMAGE_MODEL
        log_usage(
            db, request_id,
            provider="openrouter", model=cand_model, purpose="image",
            usage=sheet.get("usage"), image_count=1,
            success=sheet.get("error") is None,
            error=str(sheet["error"])[:500] if sheet.get("error") else None,
            screen="design_sheet",
        )
        if sheet.get("error") is None:
            anchor_reference_images = [sheet["image_bytes"]]
            _save_design_sheet(request_id, sheet["image_bytes"])
            logger.info("design sheet generated and attached to every screen: request=%s", request_id)
        else:
            logger.warning(
                "design sheet failed, falling back to anchor-as-reference: request=%s error=%s",
                request_id, sheet["error"],
            )

    # ── Anchor screen: distinct composition variants, not re-rolls ────────
    # DASHBOARD_CANDIDATES is the cost knob the module docstring promises
    # ("this is lead gen — cost per request matters"): it caps how many
    # composition variants the anchor explores. It had decoupled from the
    # generation path when variants replaced re-rolls — defined, documented
    # in .env.example, and read by nothing.
    anchor_spec = ui_specs[0]
    anchor_variants = prompt_builder.COMPOSITION_VARIANTS[
        : max(1, settings.DASHBOARD_CANDIDATES)
    ]
    anchor_prompts = [
        {
            "prompt": prompt_builder.build_dashboard_image_prompt(
                anchor_spec, composition=variant, archetype_id=archetype_id,
            ),
            "variant_id": variant["id"],
            "model": anchor_model,
            "image_config": settings.image_config_for_role("anchor"),
        }
        for variant in anchor_variants
    ]
    anchor_version = prompt_builder.prompt_version(
        prompt_builder.DASHBOARD_IMAGE_PROMPT_VERSION, anchor_spec, archetype_id,
    )
    anchor_selected, anchor_pool = _render_screen(
        db, request_id, anchor_spec, anchor_prompts, anchor_version,
        reference_images=anchor_reference_images,
    )
    if anchor_selected is None:
        logger.error("anchor screen produced no usable image: request=%s", request_id)
        return []
    # Where the navigation sits is decided once, by the anchor, and every
    # follow-up inherits it from the anchor image. The detail crops have to
    # follow the same decision or they crop past a sidebar that is not there.
    nav_edge = "top" if prompt_builder.is_tool_screen(anchor_spec) else "left"
    saved.append(
        _save_selected(
            db, request_id, anchor_spec, archetype_id, anchor_selected, anchor_pool, anchor_version,
            nav_edge=nav_edge,
        )
    )

    # ── Follow-up screens: anchor (or the design sheet) as the reference ──
    # Under W5 every screen shares the sheet as its ancestor, so a follow-up
    # is not copying a screen that may itself have gone wrong.
    if not settings.USE_REFERENCE_IMAGES:
        anchor_reference = None
    elif use_design_sheet and anchor_reference_images:
        anchor_reference = anchor_reference_images
    else:
        anchor_reference = [anchor_selected["image_bytes"]]

    def _one_followup(spec: UIDemoSpec) -> GeneratedImage | None:
        """One follow-up screen, generation through save, on its OWN DB
        session — the same pattern orchestrator.run uses, for the same
        reason: a SQLAlchemy Session must never be shared across threads.
        The screens are independent of each other (each references the
        anchor, none references a sibling), and running them serially was
        the request path's single biggest block of avoidable wall clock —
        the 3-minute DoD line is what pays for this thread, and the defect
        check (JOB 3) is what spends the headroom.
        """
        from app.database import SessionLocal

        # expire_on_commit=False: the row this returns outlives the session —
        # the caller (and bakeoff's report) reads its columns after close().
        screen_db = SessionLocal(expire_on_commit=False)
        try:
            standalone_prompt = prompt_builder.build_dashboard_image_prompt(spec, archetype_id=archetype_id)
            if settings.USE_REFERENCE_IMAGES:
                prompt = prompt_builder.build_continuation_prompt(spec, anchor_spec.screen_title, archetype_id)
                base_version = prompt_builder.SCREEN_CONTINUATION_PROMPT_VERSION
            else:
                prompt = standalone_prompt
                base_version = prompt_builder.DASHBOARD_IMAGE_PROMPT_VERSION
            version = prompt_builder.prompt_version(base_version, spec, archetype_id)
            prompts = [
                {
                    "prompt": prompt,
                    "variant_id": None,
                    "model": followup_model,
                    "image_config": settings.image_config_for_role("followup"),
                }
                for _ in range(settings.SECONDARY_CANDIDATES)
            ]
            selected, pool = _render_screen(
                screen_db, request_id, spec, prompts, version,
                reference_images=anchor_reference, fallback_prompt=standalone_prompt,
            )
            if selected is None:
                logger.warning("screen produced no usable image, skipping: request=%s screen=%s", request_id, spec.screen_slug)
                return None
            return _save_selected(screen_db, request_id, spec, archetype_id, selected, pool, version, nav_edge=nav_edge)
        except Exception:
            # One screen's hard failure must not take its siblings down with
            # it — the request ships with fewer screens (loudly) instead of
            # failing outright, and the anchor path still fails the request
            # when nothing at all was produced.
            logger.exception("follow-up screen failed: request=%s screen=%s", request_id, spec.screen_slug)
            return None
        finally:
            screen_db.close()

    followup_specs = list(ui_specs[1:])
    if followup_specs:
        with ThreadPoolExecutor(max_workers=min(3, len(followup_specs))) as screen_pool:
            for row in screen_pool.map(_one_followup, followup_specs):
                if row is not None:
                    saved.append(row)

    return saved
