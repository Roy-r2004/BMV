import json
from typing import Optional

from app.domain.models.request import Request
from app.infrastructure.web.reference_scraper import fix_encoding


def format_reference_analysis(req: Request) -> Optional[str]:
    """Screenshot vision analysis, or a readable summary from the reference URL."""
    if req.screenshot_analysis:
        return req.screenshot_analysis

    if not req.reference_url and not req.reference_metadata:
        return None

    meta: dict = {}
    if req.reference_metadata:
        try:
            meta = json.loads(req.reference_metadata)
        except Exception:
            meta = {}

    lines: list[str] = []

    if req.reference_url:
        lines.append(f"**Reference tool:** {req.reference_url}")

    if req.what_you_like:
        lines.append(f"**What you admire:** {req.what_you_like}")

    if meta.get("title"):
        lines.append(f"**Site title:** {fix_encoding(meta['title'])}")

    if meta.get("description"):
        lines.append(f"**Positioning:** {fix_encoding(meta['description'])}")

    if meta.get("h1"):
        lines.append(f"**Main headline:** {fix_encoding(meta['h1'])}")

    if meta.get("visible_text_snippet"):
        snippet = fix_encoding(meta["visible_text_snippet"])
        lines.append(f"**Key messaging:** {snippet[:280]}{'…' if len(snippet) > 280 else ''}")

    if not lines:
        return None

    lines.append(
        "\n*We studied this reference to understand layout patterns, messaging tone, "
        "and the user experience you want — then adapted those ideas for your business.*"
    )
    return "\n\n".join(lines)
