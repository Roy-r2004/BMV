import io
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

from PIL import Image
from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import GeneratedImage, Request
from app.pipeline._shared import log_usage


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
    mark_size = max(56, min(160, round(base.width * 0.09)))
    padding = round(base.width * 0.025)
    mark = logo.resize((mark_size, mark_size), Image.LANCZOS)
    base.paste(mark, (base.width - mark_size - padding, base.height - mark_size - padding), mark)

    out = io.BytesIO()
    base.save(out, format="PNG")
    return out.getvalue()


def generate_images(
    db: Session,
    request_id: int,
    employees: list[dict],
    image_prompts: list[dict],
) -> list[GeneratedImage]:
    """Stage 5: calls the image model for every crafted prompt in parallel
    (network-bound, no DB access inside worker threads — results are
    written back on the calling thread once all calls finish).

    `GeneratedImage.role_id`/`role_label` hold AI-employee id/title now, not
    product roles/screens — see image_prompts.py's module docstring for why.
    Column names kept as-is to avoid an unnecessary rename; they're a
    generic "what is this image about" pairing either way.
    """
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    employee_titles = {e.get("id", "employee"): e.get("title", "AI Employee") for e in employees}

    def _call(item):
        try:
            return (item, provider.generate_image(item["prompt"]), None)
        except Exception as exc:
            return (item, None, exc)

    results = []
    with ThreadPoolExecutor(max_workers=min(4, len(image_prompts) or 1)) as pool:
        futures = [pool.submit(_call, item) for item in image_prompts]
        for future in as_completed(futures):
            results.append(future.result())

    out_dir = os.path.join(settings.UPLOADS_DIR, "images", str(request_id))
    os.makedirs(out_dir, exist_ok=True)

    saved: list[GeneratedImage] = []
    for item, result, error in results:
        role_id = item.get("role_id", "role")
        variant = item.get("variant", 0)

        if error is not None or result is None:
            log_usage(
                db, request_id,
                provider="openrouter", model=settings.IMAGE_MODEL, purpose="image",
                image_count=1, success=False, error=str(error)[:500] if error else "unknown error",
            )
            continue

        file_name = f"{role_id}_{variant}.png"
        with open(os.path.join(out_dir, file_name), "wb") as f:
            f.write(_apply_bmv_watermark(result["image_bytes"]))

        image_row = GeneratedImage(
            request_id=request_id,
            role_id=role_id,
            role_label=employee_titles.get(role_id, "AI Employee"),
            variant=variant,
            file_path=f"/uploads/images/{request_id}/{file_name}",
            prompt=item.get("prompt", ""),
        )
        db.add(image_row)
        saved.append(image_row)

        log_usage(
            db, request_id,
            provider="openrouter", model=settings.IMAGE_MODEL, purpose="image",
            usage=result.get("usage"), image_count=1, success=True,
        )

    db.commit()
    return saved
