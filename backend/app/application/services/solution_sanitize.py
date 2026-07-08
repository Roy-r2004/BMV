"""Sanitize user-generated CSS/markup before storing in workspace."""
from __future__ import annotations

import re

_CSS_BLOCKED = re.compile(
    r"@import|javascript:|expression\s*\(|behavior\s*:|binding\s*:|url\s*\(\s*['\"]?\s*data:",
    re.I,
)

_MARKUP_BLOCKED_TAGS = re.compile(r"<\s*/?\s*(script|iframe|object|embed|form|link|meta)\b", re.I)
_ON_ATTR = re.compile(r"\s+on[a-z]+\s*=\s*['\"][^'\"]*['\"]", re.I)
_JS_HREF = re.compile(r"href\s*=\s*['\"]javascript:[^'\"]*['\"]", re.I)


def sanitize_css(content: str, *, max_len: int = 12_000) -> str:
    text = (content or "").strip()[:max_len]
    if _CSS_BLOCKED.search(text):
        raise ValueError("CSS contains blocked directives.")
    return text


def sanitize_markup(content: str, *, max_len: int = 16_000) -> str:
    text = (content or "").strip()[:max_len]
    if _MARKUP_BLOCKED_TAGS.search(text):
        raise ValueError("Markup contains blocked tags.")
    text = _ON_ATTR.sub("", text)
    text = _JS_HREF.sub("", text)
    return text


def sanitize_file_entry(entry: dict) -> dict | None:
    if not isinstance(entry, dict):
        return None
    path = str(entry.get("path") or "").strip()
    content = str(entry.get("content") or "")
    kind = str(entry.get("kind") or "markup").lower()
    file_id = str(entry.get("id") or path or "").strip()
    if not path or not file_id or not content.strip():
        return None
    if ".." in path or path.startswith("/"):
        return None
    if kind == "css":
        content = sanitize_css(content)
    else:
        kind = "markup"
        content = sanitize_markup(content)
    return {"id": file_id, "path": path, "kind": kind, "content": content}
