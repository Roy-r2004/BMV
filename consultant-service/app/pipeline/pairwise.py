"""Pairwise image judging — "which of these two is better", with the same
FIXED judge model the per-image QA uses.

Why this exists alongside qa.py: absolute 1-10 scoring saturates. Once every
candidate clears "looks like real software", scores bunch in the 8s and stop
discriminating between a good screenshot and an excellent one. A judge asked
to choose between two concrete images recovers that signal, and it is the
form the roadmap's DoD is written in ("beats the old default on >= 4 of 5").

Position bias is real — judges favor whichever image came first — so
`compare` runs every pair twice with the order swapped and reports a winner
only when both orders agree. A disagreement is reported as a tie, not
silently resolved in favor of the first run.

Used by evaluation scripts (bake-off, prompt-pack A/B, the W5 experiment),
never by the request pipeline.
"""

import base64
import logging

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.pipeline._shared import extract_json_from_text, log_usage
from app.templating import render
from app.ui_spec import UIDemoSpec

logger = logging.getLogger("consultant.pairwise")

PAIRWISE_PROMPT_VERSION = "image-pairwise-judge-v2"

# Generous on purpose, the same lesson the image path already carries: a
# reasoning-capable judge spends tokens thinking BEFORE it writes anything,
# and a tight cap returns finish_reason="length" with content=None — a call
# that billed in full and produced no verdict. The answer itself is ~150
# tokens; the headroom is for the comparison it does first.
PAIRWISE_MAX_TOKENS = 4000


def _data_uri(image_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(image_bytes).decode()


def _judge_once(db: Session | None, request_id: int | None, first: bytes, second: bytes, spec: UIDemoSpec) -> dict:
    prompt = render(
        "image_pairwise_judge.j2",
        screen_title=spec.screen_title,
        product_name=spec.product.name,
        business_name=spec.business.name,
        industry=spec.business.industry,
    )
    # Each image is introduced by its own text part rather than both being
    # appended after one prompt. Measured on this judge 2026-08-11: with a
    # bare "the first attached image is A", it answered "A" in both orders
    # on all three briefs — it was reading position, not pixels, and even
    # rationalized opposite defects for the same image. Naming each image
    # immediately before its bytes is what makes the swap test meaningful.
    body = provider.chat(
        settings.PAIRWISE_JUDGE_MODEL,
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "text", "text": "=== IMAGE A ==="},
                    {"type": "image_url", "image_url": {"url": _data_uri(first)}},
                    {"type": "text", "text": "=== IMAGE B ==="},
                    {"type": "image_url", "image_url": {"url": _data_uri(second)}},
                    {"type": "text", "text": (
                        "Compare IMAGE A and IMAGE B as instructed. Their order in this message "
                        "carries no meaning — judge only what is rendered in each."
                    )},
                ],
            }
        ],
        max_tokens=PAIRWISE_MAX_TOKENS,
    )
    choice = body["choices"][0]
    content = choice["message"].get("content")
    if not content:
        # A judge that returned no text must not become a silent tie — that
        # would quietly count as "no difference" and dilute every verdict.
        raise provider.AiProviderError(
            f"pairwise judge returned no content (finish_reason={choice.get('finish_reason')}, "
            f"refusal={choice['message'].get('refusal')!r})"
        )
    parsed = extract_json_from_text(content)
    if db is not None:
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.PAIRWISE_JUDGE_MODEL, purpose="image_pairwise",
            usage=body.get("usage"), success=True,
        )
    winner = str(parsed.get("winner", "tie")).strip().upper()
    return {
        "winner": winner if winner in ("A", "B") else "TIE",
        "margin": str(parsed.get("margin", "")).strip().lower(),
        "why": str(parsed.get("why", ""))[:400],
        "a_defects": [str(d)[:120] for d in (parsed.get("a_defects") or [])][:6],
        "b_defects": [str(d)[:120] for d in (parsed.get("b_defects") or [])][:6],
    }


def compare(
    db: Session | None, request_id: int | None,
    left_bytes: bytes, right_bytes: bytes, spec: UIDemoSpec,
    *, left_label: str = "left", right_label: str = "right",
) -> dict:
    """Judges left vs right in BOTH orders. Returns
    {"winner": left_label | right_label | "tie", "consistent": bool, "runs": [...]}.

    Only a verdict that survives the swap counts as a win — the whole point
    of a two-order run is that a judge which just prefers the first image
    would otherwise hand every comparison to whichever side the caller
    happened to pass first.
    """
    forward = _judge_once(db, request_id, left_bytes, right_bytes, spec)
    reverse = _judge_once(db, request_id, right_bytes, left_bytes, spec)

    forward_pick = {"A": left_label, "B": right_label}.get(forward["winner"], "tie")
    reverse_pick = {"A": right_label, "B": left_label}.get(reverse["winner"], "tie")

    consistent = forward_pick == reverse_pick and forward_pick != "tie"
    result = {
        "winner": forward_pick if consistent else "tie",
        "consistent": consistent,
        "forward_pick": forward_pick,
        "reverse_pick": reverse_pick,
        "runs": [
            {"order": f"{left_label} first", **forward},
            {"order": f"{right_label} first", **reverse},
        ],
    }
    if not consistent:
        logger.info(
            "pairwise disagreed across orders (reported as tie): %s vs %s -> %s / %s",
            left_label, right_label, forward_pick, reverse_pick,
        )
    return result
