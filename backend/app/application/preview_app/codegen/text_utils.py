"""Deprecated shim — import from ``app.application.preview_app.text_utils``."""
from __future__ import annotations

from app.application.preview_app.text_utils import (  # noqa: F401
    _FENCE_RE,
    _bounded_json,
    _parse_json,
    _strip_fences,
    bounded_json,
    parse_json,
    strip_fences,
)

__all__ = [
    "_FENCE_RE",
    "_bounded_json",
    "_parse_json",
    "_strip_fences",
    "bounded_json",
    "parse_json",
    "strip_fences",
]
