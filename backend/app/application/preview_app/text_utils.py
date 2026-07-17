"""Shared JSON and markdown-fence helpers for preview pipeline agents.

Neutral module — used by codegen, safety, assemble, and pipeline without
creating a codegen↔safety dependency.
"""
from __future__ import annotations

import json
import re

from app.shared.json_utils import extract_json_from_text

_FENCE_RE = re.compile(r"^```(?:tsx?|typescript|javascript|css)?\s*\n?", re.MULTILINE)


def strip_fences(text: str) -> str:
    raw = text.strip()
    fence_match = re.search(
        r"```(?:tsx?|typescript|javascript|css)?\s*\n([\s\S]*?)\n```",
        raw,
    )
    if fence_match:
        return fence_match.group(1).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[^\n]*\n", "", raw)
        raw = re.sub(r"\n```\s*$", "", raw)
    return raw.strip()


# Back-compat aliases used throughout the package split.
_strip_fences = strip_fences


def parse_json(raw: str) -> dict:
    if not raw or not raw.strip():
        raise ValueError("Empty response from model")
    try:
        return extract_json_from_text(raw)
    except Exception as first:
        from app.shared.json_utils import _strip_markdown_fence_once

        try:
            return json.loads(_strip_markdown_fence_once(raw))
        except Exception:
            raise ValueError(f"Could not parse model JSON: {first}") from first


_parse_json = parse_json


def bounded_json(value, max_chars: int) -> str:
    """Serialize as valid JSON within a hard character budget."""
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(raw) <= max_chars:
        return raw

    def _compact(item, depth: int = 0):
        if isinstance(item, str):
            return item[:500]
        if isinstance(item, list):
            return [_compact(child, depth + 1) for child in item[:12]]
        if isinstance(item, dict):
            return {str(key): _compact(child, depth + 1) for key, child in item.items()}
        return item

    compact = json.dumps(_compact(value), ensure_ascii=False, separators=(",", ":"))
    if len(compact) <= max_chars:
        return compact

    low, high = 0, len(compact)
    best = json.dumps({"truncated": True, "preview": ""}, separators=(",", ":"))
    while low <= high:
        middle = (low + high) // 2
        candidate = json.dumps(
            {"truncated": True, "preview": compact[:middle]},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(candidate) <= max_chars:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    return best


_bounded_json = bounded_json
