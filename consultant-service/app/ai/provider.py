"""Thin HTTP client for both AI calls this service makes — text (analyze /
consult / plan / image-prompt-crafting) and image generation — both routed
through OpenRouter so there's one key and one place cost is tracked.

Deliberately not importing anything from `backend/` — this service is fully
isolated (see the plan). Each function returns raw response data; callers
are responsible for logging an AiUsageEvent row.
"""

import base64
import time

import httpx

from app.config import settings

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


class AiProviderError(Exception):
    pass


def _headers() -> dict:
    if not settings.OPENROUTER_API_KEY:
        raise AiProviderError("OPENROUTER_API_KEY is not set")
    return {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }


def chat(model: str, messages: list[dict], *, max_tokens: int = 2000, timeout: float = 60.0) -> dict:
    """Calls OpenRouter's chat completions endpoint. Returns the parsed JSON body.

    max_tokens is capped explicitly — without it OpenRouter defaults to the
    model's full context window (65535 for gemini-2.5-flash), which a
    low-balance key can't afford and gets rejected with a 402 before the
    call even runs. These are short JSON responses; 2000 is generous.
    """
    resp = httpx.post(
        CHAT_URL,
        headers=_headers(),
        json={"model": model, "messages": messages, "max_tokens": max_tokens},
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise AiProviderError(f"OpenRouter {resp.status_code}: {resp.text[:500]}")
    return resp.json()


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
    # candidates of a request at once. Failed calls don't bill, so a couple
    # of spaced retries are free insurance for a lead's request.
    last_transport_error: Exception | None = None
    for attempt in range(3):
        if attempt:
            time.sleep(3 * attempt)
        try:
            resp = httpx.post(
                CHAT_URL,
                headers=_headers(),
                json={
                    "model": model or settings.IMAGE_MODEL,
                    "messages": [{"role": "user", "content": content}],
                    "modalities": ["image", "text"],
                    "max_tokens": max_tokens,
                },
                timeout=timeout,
            )
            break
        except httpx.TransportError as exc:
            last_transport_error = exc
    else:
        raise AiProviderError(f"OpenRouter image transport failed after retries: {last_transport_error}")
    if resp.status_code >= 400:
        raise AiProviderError(f"OpenRouter image {resp.status_code}: {resp.text[:500]}")

    body = resp.json()
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
