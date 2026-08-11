"""Thin HTTP client for both AI calls this service makes — text (analyze /
consult / plan / image-prompt-crafting) and image generation — both routed
through OpenRouter so there's one key and one place cost is tracked.

Deliberately not importing anything from `backend/` — this service is fully
isolated (see the plan). Each function returns raw response data; callers
are responsible for logging an AiUsageEvent row.
"""

import base64
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


def generate_image(
    prompt: str,
    *,
    model: str | None = None,
    reference_images: list[bytes] | None = None,
    max_tokens: int = 10000,
    timeout: float = 120.0,
) -> dict:
    """Calls an image-output-capable model via OpenRouter's chat completions
    endpoint (modalities=["image", "text"]). Returns {"image_bytes": bytes, "usage": dict | None}.

    reference_images: optional PNG bytes attached alongside the prompt as
    image_url content parts — used for multi-screen visual consistency
    (screen 2+ receives the selected anchor screenshot and is asked to
    preserve its design). Models that can't take image input will error;
    callers gate this on config, and generate_demo_screens retries once
    without references on failure.

    max_tokens is generous (not the usual tight cap) — this model spends
    ~1000-1500 tokens on internal reasoning before the ~4000+ tokens of
    actual image output. Seen in testing: a 4096 cap let reasoning alone
    exhaust the budget and return `finish_reason: "length"` with zero
    image — a real, silent-looking failure, not a cost-safety trade-off
    worth making here.
    """
    if reference_images:
        content: list | str = [{"type": "text", "text": prompt}] + [
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64," + base64.b64encode(img).decode()},
            }
            for img in reference_images
        ]
    else:
        content = prompt

    # Image responses are ~1MB JSON bodies streamed over long-lived
    # connections — transport drops mid-body (RemoteProtocolError: "peer
    # closed connection") happen in practice, seen taking out all parallel
    # candidates of a request at once. Upstream rate limits arrive the same
    # way the text path sees them: an HTTP 200 carrying choices[0].error and
    # no image at all. Neither bills, so a couple of spaced retries are free
    # insurance for a lead's request.
    resolved_model = model or settings.IMAGE_MODEL
    last_error: str | None = None
    for attempt in range(3):
        if attempt:
            time.sleep(3 * attempt)
        try:
            resp = httpx.post(
                CHAT_URL,
                headers=_headers(),
                json={
                    "model": resolved_model,
                    "messages": [{"role": "user", "content": content}],
                    "modalities": ["image", "text"],
                    "max_tokens": max_tokens,
                },
                timeout=timeout,
            )
        except httpx.TransportError as exc:
            last_error = f"transport error: {exc}"
            logger.warning("retrying image call: model=%s %s", resolved_model, last_error)
            continue

        if resp.status_code >= 400:
            last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
            if resp.status_code in RETRYABLE_STATUS:
                logger.warning("retrying image call: model=%s %s", resolved_model, last_error)
                continue
            raise AiProviderError(f"OpenRouter image {resp.status_code}: {resp.text[:500]}")

        body = resp.json()
        error = _upstream_error(body)
        if error is not None:
            last_error = f"upstream error {error.get('code')}: {str(error.get('message'))[:300]}"
            if _is_retryable(error):
                logger.warning("retrying image call: model=%s %s", resolved_model, last_error)
                continue
            raise AiProviderError(f"OpenRouter image failed for {resolved_model}: {last_error}")

        message = (body.get("choices") or [{}])[0].get("message", {})
        images = message.get("images") or []
        if not images:
            raise AiProviderError(f"OpenRouter image response had no images: {body}")

        url = (images[0].get("image_url") or {}).get("url", "")
        if url.startswith("data:"):
            _, _, b64 = url.partition(",")
            return {"image_bytes": base64.b64decode(b64), "usage": body.get("usage")}
        if url:
            image_resp = httpx.get(url, timeout=timeout)
            image_resp.raise_for_status()
            return {"image_bytes": image_resp.content, "usage": body.get("usage")}

        raise AiProviderError(f"OpenRouter image response had an empty image_url: {body}")

    raise AiProviderError(f"OpenRouter image failed for {resolved_model} after retries: {last_error}")
