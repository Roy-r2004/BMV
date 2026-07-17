"""AppSpec sanitize — kind aliases and helpers."""
from __future__ import annotations

from typing import Any, Mapping

_VALID_EVIDENCE_KINDS = {
    "text",
    "metric",
    "list",
    "table",
    "chart",
    "form",
    "status",
    "navigation",
    "media",
}

_VALID_ASSERTION_KINDS = {
    "route",
    "visible",
    "state",
    "data",
    "count",
    "accessibility",
    "no_runtime_errors",
}

_EVIDENCE_KIND_ALIASES = {
    "data": "status",
    "email": "text",
    "confirmation": "text",
    "message": "text",
}

_ASSERTION_KIND_ALIASES = {
    "list": "visible",
    "form": "visible",
    "text": "visible",
    "status": "state",
    "metric": "count",
    "table": "visible",
    "chart": "visible",
    "navigation": "route",
    "media": "visible",
}

def _normalize_kind(
    value: Any,
    *,
    valid: set[str],
    aliases: Mapping[str, str],
    default: str,
) -> str:
    text = str(value or default).strip().casefold()
    if text in valid:
        return text
    mapped = aliases.get(text)
    if mapped in valid:
        return mapped
    return default

def _humanize_identifier(identifier: str) -> str:
    text = str(identifier or "").strip()
    for prefix in ("FIELD-", "ENTITY-", "REQ-", "PAGE-", "CAP-"):
        if text.upper().startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.replace("-", " ").replace("_", " ").title() or "Unnamed"
