"""JOB 1 resolution probe — does image_config get honoured through OpenRouter?

Fires the REAL salon anchor prompt (the brief whose s33 run shipped
"Cilents") at image_size=2K / aspect_ratio=16:9 on both production models,
and records what actually came back: pixel dimensions, billed cost, latency.

Direct calls, outside the service — so the service ledger will NOT carry
these rows. Cost is taken from the response usage block instead and written
to results.json here. Two calls, run sequentially.
"""

import base64
import io
import json
import os
import sys
import time

import httpx
from PIL import Image

PROBE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_FILE = os.path.join(PROBE_DIR, "salon-anchor-prompt.txt")

with open(PROMPT_FILE, encoding="utf-8") as f:
    content = f.read()
# strip the "# source:..." header block preview_prompt.py writes
prompt = content.split("\n\n", 1)[1]

KEY = os.environ["OPENROUTER_API_KEY"]
IMAGE_CONFIG = {"image_size": "2K", "aspect_ratio": "16:9"}
MODELS = ["google/gemini-3-pro-image", "google/gemini-3.1-flash-image"]

results = []
for model in MODELS:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
        "max_tokens": 30000,
        "image_config": IMAGE_CONFIG,
        "usage": {"include": True},
    }
    start = time.monotonic()
    try:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
            json=body,
            timeout=300.0,
        )
        latency = time.monotonic() - start
        rec = {"model": model, "image_config": IMAGE_CONFIG, "http_status": resp.status_code, "latency_s": round(latency, 1)}
        if resp.status_code >= 400:
            rec["error"] = resp.text[:500]
            results.append(rec)
            print(json.dumps(rec, indent=2))
            continue
        payload = resp.json()
        choice = (payload.get("choices") or [{}])[0]
        err = choice.get("error") or payload.get("error")
        if err:
            rec["error"] = str(err)[:500]
            results.append(rec)
            print(json.dumps(rec, indent=2))
            continue
        images = (choice.get("message") or {}).get("images") or []
        if not images:
            rec["error"] = "no images in response"
            rec["finish_reason"] = choice.get("finish_reason")
            results.append(rec)
            print(json.dumps(rec, indent=2))
            continue
        url = (images[0].get("image_url") or {}).get("url", "")
        _, _, b64 = url.partition(",")
        raw = base64.b64decode(b64)
        im = Image.open(io.BytesIO(raw))
        out_name = model.split("/")[-1] + "_2k.png"
        with open(os.path.join(PROBE_DIR, out_name), "wb") as f:
            f.write(raw)
        rec.update({
            "width": im.width,
            "height": im.height,
            "megapixels": round(im.width * im.height / 1e6, 2),
            "usage": payload.get("usage"),
            "file": out_name,
        })
        results.append(rec)
        print(json.dumps({k: v for k, v in rec.items() if k != "usage"}, indent=2))
        print("  usage:", json.dumps(payload.get("usage")))
    except Exception as exc:
        rec = {"model": model, "error": f"{type(exc).__name__}: {exc}", "latency_s": round(time.monotonic() - start, 1)}
        results.append(rec)
        print(json.dumps(rec, indent=2))

with open(os.path.join(PROBE_DIR, "results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print("\nwrote results.json")
