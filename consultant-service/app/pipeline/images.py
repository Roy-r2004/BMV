import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import GeneratedImage, Request
from app.pipeline._shared import log_usage


def generate_images(
    db: Session,
    request_id: int,
    roles: list[dict],
    image_prompts: list[dict],
) -> list[GeneratedImage]:
    """Stage 5: calls the image model for every crafted prompt in parallel
    (network-bound, no DB access inside worker threads — results are
    written back on the calling thread once all calls finish)."""
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    role_labels = {r.get("id", "role"): r.get("label", "Role") for r in roles}

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
            f.write(result["image_bytes"])

        image_row = GeneratedImage(
            request_id=request_id,
            role_id=role_id,
            role_label=role_labels.get(role_id, "Role"),
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
