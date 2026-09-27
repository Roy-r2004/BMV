"""Thin HTTP client for the text calls this service makes (analysis,
consulting, planning, the diagnosis and every document stage), routed
through OpenRouter so there's one key and one place cost is tracked.

Deliberately not importing anything from `backend/` — this service is fully
isolated (see the plan). Each function returns raw response data; callers
are responsible for logging an AiUsageEvent row.
"""

import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger("consultant.provider")

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

# Upstream conditions that are worth one more attempt: the provider behind
# OpenRouter was busy, not wrong. Anything else (a bad request, a refusal,
# an unknown model) will fail identically on a retry.
RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504, 520, 522, 524}


class AiProviderError(Exception):
    pass


def _upstream_error(body: dict) -> dict | None:
    """OpenRouter reports a mid-stream upstream failure INSIDE an HTTP 200:
    `choices[0].error` is set, `finish_reason` becomes "error", and
    `message.content` holds whatever partial text arrived before the
    failure — a JSON object cut off mid-string.

    Observed on this key 2026-08-11: 2 of 6 consecutive ui_spec calls came
    back this way with a 429 ("temporarily rate-limited upstream"). Because
    only the HTTP status was checked, those counted as successes; the
    truncated JSON then failed to parse and the stage fell back to its
    generic deterministic specs — a real lead would have been shown a demo
    with "Alex" and "Bookings Today" instead of their own business. A
    silent 33% quality cliff, invisible in the ledger as a success row.
    """
    choice = (body.get("choices") or [{}])[0]
    error = choice.get("error") or body.get("error")
    if error:
        return error if isinstance(error, dict) else {"message": str(error)}
    if choice.get("finish_reason") == "error":
        return {"message": "upstream reported finish_reason=error"}
    return None


def _is_retryable(error: dict) -> bool:
    code = error.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    if code in RETRYABLE_STATUS:
        return True
    metadata = error.get("metadata") or {}
    return "rate_limit" in str(metadata.get("error_type", "")).lower()


def _headers() -> dict:
    if not settings.OPENROUTER_API_KEY:
        raise AiProviderError("OPENROUTER_API_KEY is not set")
    return {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }


def chat(
    model: str, messages: list[dict], *, max_tokens: int = 2000,
    timeout: float = 60.0, retries: int = 1,
) -> dict:
    """Calls OpenRouter's chat completions endpoint. Returns the parsed JSON body.

    max_tokens is capped explicitly — without it OpenRouter defaults to the
    model's full context window (65535 for gemini-2.5-flash), which a
    low-balance key can't afford and gets rejected with a 402 before the
    call even runs. These are short JSON responses; 2000 is generous.

    Raises AiProviderError on an upstream failure even when it arrives as an
    HTTP 200 (see _upstream_error) — every caller already wraps this in a
    try/except with a ledgered fallback, so a loud failure lands in the
    ledger as success=False instead of quietly parsing truncated JSON.

    `retries` spaced re-attempts are made for transient conditions only
    (upstream rate limits, 5xx, transport drops). A recovered attempt is
    logged as a warning and NOT ledgered — the ledger counts calls, not
    attempts — so upstream flakiness rates come from the logs, while
    exhausted retries still show up as the caller's success=False row.
    """
    last_error: str | None = None
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(3 * attempt)
        try:
            resp = httpx.post(
                CHAT_URL,
                headers=_headers(),
                json={"model": model, "messages": messages, "max_tokens": max_tokens},
                timeout=timeout,
            )
        except httpx.TransportError as exc:
            last_error = f"transport error: {exc}"
            if attempt < retries:
                logger.warning("retrying text call: model=%s %s", model, last_error)
                continue
            raise AiProviderError(f"OpenRouter chat failed for {model}: {last_error}") from exc

        if resp.status_code >= 400:
            last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
            if attempt < retries and resp.status_code in RETRYABLE_STATUS:
                logger.warning("retrying text call: model=%s %s", model, last_error)
                continue
            raise AiProviderError(f"OpenRouter {resp.status_code}: {resp.text[:500]}")

        body = resp.json()
        error = _upstream_error(body)
        if error is None:
            return body
        last_error = f"upstream error {error.get('code')}: {str(error.get('message'))[:300]}"
        if attempt < retries and _is_retryable(error):
            logger.warning("retrying text call: model=%s %s", model, last_error)
            continue
        raise AiProviderError(f"OpenRouter chat failed for {model}: {last_error}")

    raise AiProviderError(f"OpenRouter chat failed for {model}: {last_error}")
