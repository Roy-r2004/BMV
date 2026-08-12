"""Optional vision-model QA over generated screenshot candidates.
Prompt versions: image-quality-judge-v1 (prompts/image_quality_judge.j2),
image-text-transcription-v1 (prompts/image_text_transcription.j2),
image-defect-inspector-v1 / image-defect-verifier-v1 (defect_check.py).

Three instruments, deliberately separate:

1. The aesthetic judge scores craft and approves or rejects. The threshold
   is enforced in code, not by the judge (see review_image).
2. The text-truth gate (W3) transcribes what is actually rendered and
   diffs it against the spec in code (pipeline/text_truth.py). It can only
   ever REJECT — a screen carrying the client's name misspelled is
   unusable however beautiful it is, and no aesthetic score may override
   that. It can never rescue a screen the judge rejected.
3. The structural defect check (JOB 3): one inspector reports countable
   structural defects, each claim goes to a separate verifier told to
   refute it (pipeline/defect_check.py). A claim both stages agree on
   rejects the candidate. Like text truth, it only subtracts.

The three primary calls are independent reads of the same bytes, so they
run CONCURRENTLY — this is what pays for the defect check without blowing
the 3-minute request line. Every DB write happens on the calling thread
after the joins; the worker threads only do network I/O, so no Session is
ever shared across threads.

Fail-open by design: if the judge call/parse fails on BOTH attempts, the
candidate passes with a null score and the failure is logged — a QA outage
must never take down image generation itself. The transcription call and
both defect stages fail open the same way, for the same reason.
"""

import base64
import io
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.pipeline import defect_check, text_truth
from app.pipeline._shared import extract_json_from_text, log_usage
from app.templating import render
from app.ui_spec import UIDemoSpec

logger = logging.getLogger("consultant.image_qa")

JUDGE_PROMPT_VERSION = "image-quality-judge-v1"
TRANSCRIPTION_PROMPT_VERSION = "image-text-transcription-v1"


def _magnified_bands(image_bytes: bytes) -> list[bytes]:
    """The top band and the left band, upscaled — the two places the
    brand-critical strings live (a top navigation bar or a left sidebar,
    plus the product wordmark in the corner of whichever it is).

    This exists because of a measured miss. On the session-33 golden set the
    salon schedule screen rendered its navigation item as "Cilents" — i and
    l transposed — and the gate reported the screen as passing, because the
    transcriber read back "Clients". The anchor of the same run rendered
    "Clients" correctly in the same slot at the same size, so the difference
    is in the pixels, not in the reading.

    The transcription prompt has told the model "if a word looks misspelled,
    transcribe the misspelling — do not correct it" since it was written. It
    did not help, which is this project's recurring lesson: an instruction
    against a behaviour does not remove the behaviour. What the model was
    short of is not willingness but RESOLUTION — the nav label is roughly
    ten pixels tall in a 1376px-wide image, and a vision model downsamples
    before it reads. Handing it the same pixels at 3x is a change to what it
    can see rather than to what it is asked to do.

    Deterministic, PIL-only, no extra model call — the crops ride along as
    additional images on the transcription call that was already happening.
    Failure here returns nothing rather than raising: a gate that cannot
    magnify must still run at the old fidelity.

    The magnification factor is chosen per band so the scaled long edge
    lands at or under 4224px — which is exactly 3x at the 1376/1408-wide
    default output, so nothing changes there. It exists because follow-ups
    now render at 2K (2752px wide): a blind 3x would make a 8256px-wide
    payload whose only effects are upload weight and the risk of the call
    failing — which fails OPEN, silently un-gating exactly the screens the
    gate exists for. A 2K band at 1x already carries twice the glyph pixels
    the 1K pipeline's source did.
    """
    try:
        base = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        width, height = base.size
        bands = [
            base.crop((0, 0, width, max(1, round(height * 0.14)))),      # top bar / wordmark
            base.crop((0, 0, max(1, round(width * 0.22)), height)),      # left sidebar / wordmark
        ]
        out = []
        for band in bands:
            if band.width < 8 or band.height < 8:
                continue
            factor = max(1, min(3, 4224 // max(band.width, band.height)))
            scaled = band if factor == 1 else band.resize(
                (band.width * factor, band.height * factor), Image.LANCZOS,
            )
            buffer = io.BytesIO()
            scaled.save(buffer, format="PNG")
            out.append(buffer.getvalue())
        return out
    except Exception as exc:
        logger.warning("could not magnify text bands, transcribing at source resolution: %s", exc)
        return []


def _uri(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode()


# ── the three instruments as pure network calls (no DB — the caller logs) ─

def _transcribe_call(image_bytes: bytes) -> dict:
    """{"transcript": list[str] | None, "usage": dict | None, "error": ...}.
    None means the call or parse failed — "unknown", never "no text found",
    which would fail every brand-critical string at once."""
    prompt = render("image_text_transcription.j2")
    content: list[dict] = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": _uri(image_bytes)}},
    ]
    bands = _magnified_bands(image_bytes) if settings.ENABLE_TEXT_TRUTH_ZOOM else []
    if bands:
        content.append({
            "type": "text",
            "text": (
                "The images that follow are the same screenshot's top band and left band, cropped and magnified. "
                "They contain no text the first image does not. Read the wordmark and the navigation "
                "items from these, character by character, and report what is drawn there rather than "
                "the word you expect it to be."
            ),
        })
        content.extend({"type": "image_url", "image_url": {"url": _uri(b)}} for b in bands)
    try:
        body = provider.chat(
            settings.QA_MODEL,
            [{"role": "user", "content": content}],
            max_tokens=2000,
        )
        parsed = extract_json_from_text(body["choices"][0]["message"]["content"])
        return {
            "transcript": [str(t) for t in (parsed.get("text") or [])],
            "usage": body.get("usage"),
            "error": None,
        }
    except Exception as exc:
        return {"transcript": None, "usage": None, "error": str(exc)[:480]}


def _judge_call(image_bytes: bytes, spec: UIDemoSpec) -> dict:
    """{"verdict": {...} | None, "usage": dict | None, "error": ...} with
    the retry inside — verdict None means failed after retry (fail open)."""
    prompt = render(
        "image_quality_judge.j2",
        screen_title=spec.screen_title,
        product_name=spec.product.name,
        business_name=spec.business.name,
        industry=spec.business.industry,
        min_score=settings.QA_MIN_SCORE,
    )
    data_uri = _uri(image_bytes)
    last_exc: Exception | None = None
    for attempt in range(2):
        if attempt:
            time.sleep(2)
        try:
            body = provider.chat(
                settings.QA_MODEL,
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_uri}},
                        ],
                    }
                ],
                max_tokens=1000,
            )
            parsed = extract_json_from_text(body["choices"][0]["message"]["content"])
            approved = parsed.get("approved")
            if isinstance(approved, str):
                # bool("false") is True — a judge that emits string booleans must
                # not silently approve everything (found in review).
                approved = approved.strip().lower() == "true"
            score = float(parsed["score"]) if parsed.get("score") is not None else None
            # The threshold is enforced HERE, not by the judge. QA_MIN_SCORE
            # was only ever interpolated into the judge's prompt and the
            # judge's own `approved` boolean was taken at face value — so
            # raising the number changed the wording of a request and nothing
            # about what shipped. Found 2026-08-12 when the owner raised the
            # gate to 8 and a candidate scoring 7.9 was still approved.
            #
            # Same principle the text-truth gate already follows: a rule the
            # product depends on is decided in code, where it cannot be
            # talked out of a difference. A missing score keeps the judge's
            # verdict, which preserves the module's fail-open contract — a
            # judge that returned no number must not reject every candidate.
            if score is not None and score < settings.QA_MIN_SCORE:
                approved = False
            return {
                "verdict": {
                    "score": score,
                    "issues": [str(i) for i in (parsed.get("issues") or [])][:10],
                    "approved": bool(approved),
                },
                "usage": body.get("usage"),
                "error": None,
            }
        except Exception as exc:
            last_exc = exc
    return {"verdict": None, "usage": None, "error": f"failed after retry: {str(last_exc)[:480]}"}


# ── public wrappers ──────────────────────────────────────────────────────

def transcribe(db: Session, request_id: int, image_bytes: bytes, screen: str | None = None) -> list[str] | None:
    """Every string visible in the image, as rendered. None when the call or
    parse failed. Ledgers its own usage row."""
    result = _transcribe_call(image_bytes)
    log_usage(
        db, request_id,
        provider="openrouter", model=settings.QA_MODEL, purpose="image_text",
        usage=result["usage"], success=result["error"] is None,
        error=result["error"], screen=screen,
    )
    if result["error"] is not None:
        logger.warning("text transcription failed open: request=%s error=%s", request_id, result["error"])
    return result["transcript"]


def _apply_text_truth(verdict: dict, spec: UIDemoSpec, transcript: list[str] | None) -> dict:
    """Adds "text_truth" to the verdict and, on failure, forces approval off.

    Only ever subtracts. A verdict the aesthetic judge already rejected
    stays rejected even if every brand string is perfect.
    """
    if transcript is None:
        verdict["text_truth"] = {"passed": None, "reason": "transcription unavailable"}
        return verdict
    result = text_truth.check(spec, transcript)
    verdict["text_truth"] = {
        "passed": result["passed"],
        "checked": result["checked"],
        "failures": result["failures"],
        "absent": result["absent"],
    }
    if not result["passed"]:
        issues = text_truth.describe(result)
        verdict["issues"] = (verdict.get("issues") or []) + issues
        verdict["approved"] = False
    return verdict


def review_image(db: Session, request_id: int, image_bytes: bytes, spec: UIDemoSpec) -> dict:
    """Returns {"score": float | None, "issues": list[str], "approved": bool,
    "text_truth": {...} | absent, "defects": {...} | absent}.

    Fires the judge, the transcription and the defect inspector
    CONCURRENTLY (independent reads of the same bytes), then the
    per-claim verifiers, then writes every ledger row from this thread.
    """
    if not settings.ENABLE_VISION_QA:
        return {"score": None, "issues": [], "approved": True}

    run_text = settings.ENABLE_TEXT_TRUTH_GATE
    run_defects = settings.ENABLE_DEFECT_CHECK

    with ThreadPoolExecutor(max_workers=3) as pool:
        judge_future = pool.submit(_judge_call, image_bytes, spec)
        transcribe_future = pool.submit(_transcribe_call, image_bytes) if run_text else None
        inspect_future = pool.submit(defect_check.inspect_call, image_bytes, spec) if run_defects else None

        judge_result = judge_future.result()
        transcribe_result = transcribe_future.result() if transcribe_future else None
        inspect_result = inspect_future.result() if inspect_future else None

        # Verifiers reuse the pool — the three primaries are done by now.
        verify_futures = []
        if inspect_result and inspect_result["claims"]:
            verify_futures = [
                pool.submit(defect_check.verify_call, image_bytes, claim, spec)
                for claim in inspect_result["claims"]
            ]
        verify_results = [f.result() for f in verify_futures]

    # ── everything below is on the calling thread: DB, verdict assembly ──
    log_usage(
        db, request_id,
        provider="openrouter", model=settings.QA_MODEL, purpose="image_qa",
        usage=judge_result["usage"], success=judge_result["error"] is None,
        error=judge_result["error"], screen=spec.screen_slug,
    )
    if judge_result["verdict"] is not None:
        verdict = judge_result["verdict"]
    else:
        logger.warning("image QA failed open after retry: request=%s error=%s", request_id, judge_result["error"])
        # Still gated below: the aesthetic judge being down is no reason to
        # ship the client's name misspelled or a duplicated panel — those
        # checks are separate calls and may well have succeeded.
        verdict = {"score": None, "issues": [f"qa-failed {str(judge_result['error'])[:120]}"], "approved": True}

    if run_text and transcribe_result is not None:
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.QA_MODEL, purpose="image_text",
            usage=transcribe_result["usage"], success=transcribe_result["error"] is None,
            error=transcribe_result["error"], screen=spec.screen_slug,
        )
        if transcribe_result["error"] is not None:
            logger.warning(
                "text transcription failed open: request=%s error=%s",
                request_id, transcribe_result["error"],
            )
        verdict = _apply_text_truth(verdict, spec, transcribe_result["transcript"])
        if verdict.get("text_truth", {}).get("passed") is False:
            logger.info(
                "text-truth gate rejected a candidate: request=%s screen=%s %s",
                request_id, spec.screen_slug,
                "; ".join(verdict["issues"][-3:]),
            )

    if run_defects and inspect_result is not None:
        log_usage(
            db, request_id,
            provider="openrouter", model=settings.DEFECT_MODEL, purpose="image_defect",
            usage=inspect_result["usage"], success=inspect_result["error"] is None,
            error=inspect_result["error"], screen=spec.screen_slug,
        )
        confirmed = []
        for claim, verification in zip(inspect_result["claims"], verify_results):
            log_usage(
                db, request_id,
                provider="openrouter", model=settings.DEFECT_MODEL, purpose="image_defect_verify",
                usage=verification["usage"], success=verification["error"] is None,
                error=verification["error"], screen=spec.screen_slug,
            )
            if verification["confirmed"]:
                confirmed.append({**claim, "verifier_reason": verification["reason"]})
        verdict["defects"] = {
            "claims": len(inspect_result["claims"]),
            "confirmed": confirmed,
            # A fail-open inspector must be distinguishable from a clean
            # pass downstream: on request 107 a 429 killed the inspector,
            # the candidate recorded zero defects while visibly carrying a
            # duplicated panel, and the fallback rank treated the blindness
            # as cleanliness. claims==0 with an error is unknown, not clean.
            "checked": inspect_result["error"] is None,
        }
        if confirmed:
            verdict["issues"] = (verdict.get("issues") or []) + [
                f"structural defect ({c['kind']}): {c['what']}" for c in confirmed
            ]
            verdict["approved"] = False
            logger.info(
                "defect check rejected a candidate: request=%s screen=%s %s",
                request_id, spec.screen_slug,
                "; ".join(f"{c['kind']}@{c['where'][:60]}" for c in confirmed[:3]),
            )

    return verdict
