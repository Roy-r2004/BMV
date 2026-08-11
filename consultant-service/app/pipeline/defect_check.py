"""Per-screen structural defect check (JOB 3, session 34).

Two stages, deliberately: one inspector reports countable structural
defects, then EACH claim goes to a separate verifier told to refute it and
defaulting to refuted when uncertain. That two-stage shape is the same
thing that makes the pairwise judge trustworthy, and it is the shape that
found 13 of 15 screens defective on the session-33 golden set (16 further
claims were made and refuted — every one of those, single-stage, would
have been a false rejection). Single-stage judging has failed this project
three times; see prompts/image_pairwise_judge.j2 for the history.

Text claims are forbidden in both rubrics. Text truth is text_truth.py's
job and nothing else's.

This module makes NETWORK calls only and touches no database — qa.py
orchestrates it alongside the aesthetic judge and the transcription call
and writes every usage row from its own thread, so the calls here can run
concurrently without threading a Session anywhere it could be shared.

Every function fails OPEN by returning claims=[] / confirmed=False with
the error recorded: a defect-check outage must never reject every
candidate a request has. The asymmetry is deliberate and matches the
verifier's own stance — when in doubt, the screen ships and the doubt is
logged.
"""

import base64
import logging

from app.ai import provider
from app.config import settings
from app.templating import render
from app.ui_spec import UIDemoSpec

logger = logging.getLogger("consultant.defect_check")

INSPECTOR_PROMPT_VERSION = "image-defect-inspector-v1"
VERIFIER_PROMPT_VERSION = "image-defect-verifier-v1"

# An inspector that returns a wall of claims is padding, and every claim
# costs a verifier call. The rubric says at most 4; this enforces it.
MAX_CLAIMS_PER_SCREEN = 4

VALID_KINDS = {
    "duplicated_panel",
    "clipping_or_truncation",
    "blank_or_unlabelled",
    "non_app_chrome",
    "malformed_data_display",
}


def _data_uri(image_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(image_bytes).decode()


def inspect_call(image_bytes: bytes, spec: UIDemoSpec) -> dict:
    """One inspector pass over one screenshot. Returns
    {"claims": [...], "usage": dict | None, "error": str | None} — claims
    is [] on any failure (fail open)."""
    prompt = render(
        "image_defect_inspector.j2",
        screen_title=spec.screen_title,
        product_name=spec.product.name,
        business_name=spec.business.name,
        industry=spec.business.industry,
    )
    try:
        from app.pipeline._shared import extract_json_from_text

        body = provider.chat(
            settings.DEFECT_MODEL,
            [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": _data_uri(image_bytes)}},
                ],
            }],
            max_tokens=1200,
        )
        parsed = extract_json_from_text(body["choices"][0]["message"]["content"])
        claims = []
        for item in (parsed.get("defects") or [])[:MAX_CLAIMS_PER_SCREEN]:
            kind = str(item.get("kind", "")).strip()
            if kind not in VALID_KINDS:
                continue  # off-rubric claims (including any text claim) die here
            claims.append({
                "kind": kind,
                "where": str(item.get("where", ""))[:300],
                "what": str(item.get("what", ""))[:300],
            })
        return {"claims": claims, "usage": body.get("usage"), "error": None}
    except Exception as exc:
        logger.warning("defect inspector failed open: %s", exc)
        return {"claims": [], "usage": None, "error": str(exc)[:480]}


def verify_call(image_bytes: bytes, claim: dict, spec: UIDemoSpec) -> dict:
    """One adversarial verifier pass over one claim. Returns
    {"confirmed": bool, "reason": str, "usage": dict | None,
    "error": str | None} — confirmed is False on any failure or any
    ambiguity, which is the refute-by-default stance in code."""
    prompt = render(
        "image_defect_verifier.j2",
        screen_title=spec.screen_title,
        product_name=spec.product.name,
        claim_kind=claim["kind"],
        claim_where=claim["where"],
        claim_what=claim["what"],
    )
    try:
        from app.pipeline._shared import extract_json_from_text

        body = provider.chat(
            settings.DEFECT_MODEL,
            [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": _data_uri(image_bytes)}},
                ],
            }],
            max_tokens=600,
        )
        parsed = extract_json_from_text(body["choices"][0]["message"]["content"])
        verdict = str(parsed.get("verdict", "")).strip().lower()
        return {
            # Anything that is not the exact word "confirmed" is a refutation,
            # including a missing or creative verdict field.
            "confirmed": verdict == "confirmed",
            "reason": str(parsed.get("reason", ""))[:300],
            "usage": body.get("usage"),
            "error": None,
        }
    except Exception as exc:
        logger.warning("defect verifier failed open (claim refuted): %s", exc)
        return {"confirmed": False, "reason": "", "usage": None, "error": str(exc)[:480]}
