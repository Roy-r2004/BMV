"""AppSpec deterministic sanitizer package."""
from __future__ import annotations

from app.domain.appspec.sanitize.pipeline import sanitize_app_spec_payload

__all__ = [
    "sanitize_app_spec_payload",
]
