import json
import logging
import re

import httpx
from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import extract_json_from_text, log_usage
from app.templating import render

logger = logging.getLogger("consultant.research")

_STRIP_BLOCKS = re.compile(r"<(script|style|nav|footer|header|noscript)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")

# Enough for the extraction model to work with without inflating the call's
# cost — this is a supporting signal, not the primary input.
MAX_PAGE_CHARS = 6000
# Below this, a fetched page is almost certainly a JS-only shell (nothing
# server-rendered) rather than real content — not worth an LLM call.
MIN_PAGE_CHARS = 200


def _html_to_text(html: str) -> str:
    """Strips a fetched page to plain text for the extraction model. No
    parsing library on purpose — the model already tolerates leftover
    navigation noise, and this stays dependency-free (no Docker image
    change for a supporting, optional stage)."""
    stripped = _STRIP_BLOCKS.sub(" ", html)
    text = _TAG.sub(" ", stripped)
    return _WHITESPACE.sub(" ", text).strip()[:MAX_PAGE_CHARS]


def research_business(db: Session, request_id: int) -> dict | None:
    """Optional stage run before analysis: if the owner gave their own
    site/profile URL, fetch it and extract real business signals, so the
    diagnosis is grounded in what the business actually says about itself
    rather than only what they typed into a five-step form.

    Fails open at every step — unreachable URL, blocked fetch, a JS-only
    page with nothing to read, a malformed extraction response — and always
    returns None rather than raising. The pipeline proceeds exactly as it
    did before this stage existed; nothing downstream depends on this
    having succeeded.
    """
    req = db.get(Request, request_id)
    if req is None or not req.site_url:
        return None

    try:
        resp = httpx.get(
            req.site_url,
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; BuildMyVersionBot/1.0)"},
        )
        resp.raise_for_status()
        page_text = _html_to_text(resp.text)
    except Exception as exc:
        logger.warning("site fetch failed: request=%s url=%s error=%s", request_id, req.site_url, exc)
        return None

    if len(page_text) < MIN_PAGE_CHARS:
        logger.info("site research skipped (too little content): request=%s url=%s", request_id, req.site_url)
        return None

    try:
        prompt = render(
            "research_extract.j2",
            business_name=req.business_name or "",
            source_url=req.site_url,
            page_text=page_text,
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=800)
        content = body["choices"][0]["message"]["content"]
        result = extract_json_from_text(content)
        result.setdefault("services", [])
        result.setdefault("highlights", [])
        result["source_url"] = req.site_url
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="research",
            usage=body.get("usage"), success=True,
        )
    except Exception as exc:
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="research",
            success=False, error=str(exc)[:500],
        )
        return None

    req.site_research_json = json.dumps(result)
    db.commit()
    return result
