"""Static file serving for built React preview apps (Vite `dist/` output)."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.application.preview_app.workspace import get_dist_dir

router = APIRouter(tags=["preview-apps"])

# Previews are regenerated often; never let the browser/iframe keep a broken
# error-boundary shell or stale index.html that points at an old JS bundle.
_NO_STORE = {
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
}


@router.get("/api/preview-apps/{request_id}/{full_path:path}")
async def serve_preview_app(request_id: int, full_path: str):
    """Serve built Vite preview app static assets."""
    dist = get_dist_dir(request_id)
    if not dist.is_dir():
        raise HTTPException(status_code=404, detail="Preview app not found")

    if full_path in ("", "index.html"):
        target = dist / "index.html"
    else:
        target = dist / full_path

    try:
        target = target.resolve()
        dist_resolved = dist.resolve()
        if not str(target).startswith(str(dist_resolved)):
            raise HTTPException(status_code=404, detail="Not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Not found") from None

    if target.is_file():
        return FileResponse(target, headers=_NO_STORE)

    spa = dist / "index.html"
    if spa.is_file():
        return FileResponse(spa, headers=_NO_STORE)

    raise HTTPException(status_code=404, detail="Not found")
