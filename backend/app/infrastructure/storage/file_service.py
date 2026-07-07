"""Local filesystem storage for uploaded reference files."""
import os
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm", ".mov"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def ensure_upload_dir() -> None:
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


def save_upload(file: UploadFile) -> str:
    ensure_upload_dir()
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(settings.UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        content = file.file.read()
        f.write(content)
    return filepath


def is_image_file(filepath: str) -> bool:
    return Path(filepath).suffix.lower() in IMAGE_EXTENSIONS
