"""Pins for the 2K follow-up canvas (JOB 1, session 34).

Session 33's worst credibility class — collapsed letterforms ("Cilents",
"Portfollo", "Highiights", "beoking", "10:1S", "SLB" for "5lb") — was
five of six on flash FOLLOW-UP screens: ten-pixel glyphs where i/l/1 and
S/5 become the same shape. (The sixth, "SLB", was a pro anchor — a
residual risk resolution cannot fix, owned by the text-truth gate.) The
probe (docs/evidence/session34/probe/) showed gemini-3.1-flash-image
honours image_config 2K (2752x1536, same 1.79:1 shape, $0.1019 vs $0.070)
while gemini-3-pro-image silently ignores it on both slugs. So:
follow-ups ask for 2K by default, the anchor asks for nothing, and
everything about that is pinned here.

The properties that matter:

  1. image_config reaches the request body when set, and is ABSENT when
     not — a stray empty dict could change provider routing.
  2. The size rides per-item like `model` does, so the regeneration retry
     re-fires the size the candidate ran at rather than silently reverting.
  3. The text-truth band magnification adapts: exactly the old 3x at the
     1376/1408 default, capped at 2K so the payload cannot balloon into a
     failed — and therefore OPEN — gate.
  4. The cost model prices the size the pipeline will actually request.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch

from PIL import Image

from app.ai import provider
from app.config import settings
from app.pipeline import cost_model
from app.pipeline import images as images_mod
from app.pipeline import qa

_buf = io.BytesIO()
Image.new("RGB", (4, 4), "white").save(_buf, format="PNG")
VALID_PNG = _buf.getvalue()

FLASH = "google/gemini-3.1-flash-image"


class _FakeDb:
    def add(self, *_): ...
    def commit(self): ...
    def get(self, *_): return object()


# ── the request body ─────────────────────────────────────────────────────

class _Resp:
    status_code = 200

    def json(self):
        return {
            "choices": [{"message": {"images": [{"image_url": {"url": "data:image/png;base64,aWjD"}}]}}],
            "usage": {},
        }


def test_image_config_reaches_the_request_body():
    sent = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.update(json)
        return _Resp()

    with patch.object(provider.httpx, "post", side_effect=fake_post), \
         patch.object(provider.settings, "OPENROUTER_API_KEY", "k"):
        provider.generate_image("p", model=FLASH, image_config={"image_size": "2K", "aspect_ratio": "16:9"})

    assert sent["image_config"] == {"image_size": "2K", "aspect_ratio": "16:9"}


def test_no_image_config_means_no_field_at_all():
    sent = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.update(json)
        return _Resp()

    with patch.object(provider.httpx, "post", side_effect=fake_post), \
         patch.object(provider.settings, "OPENROUTER_API_KEY", "k"):
        provider.generate_image("p", model=FLASH)

    assert "image_config" not in sent


# ── the role split ───────────────────────────────────────────────────────

def test_shipped_defaults_are_2k_followups_and_untouched_anchor():
    """The measured facts behind the default: flash honours 2K, pro ignores
    it, and every collapsed letterform in the s33 sweep was a flash
    follow-up. An anchor size would today be a no-op that costs risk."""
    assert settings.image_config_for_role("followup") == {"image_size": "2K", "aspect_ratio": "16:9"}
    assert settings.image_config_for_role("anchor") is None


def test_followup_calls_carry_2k_and_anchor_calls_carry_nothing(dental_spec):
    seen = []

    def fake_generate(prompt, *, model=None, reference_images=None, image_config=None, **_):
        seen.append(image_config)
        return {"image_bytes": VALID_PNG, "usage": None}

    specs = []
    for screen_type in ("dashboard", "patients"):
        spec = dental_spec.model_copy(deep=True)
        spec.product.screen_type = screen_type
        specs.append(spec)

    with patch.object(images_mod.provider, "generate_image", side_effect=fake_generate), \
         patch.object(images_mod.qa, "review_image", return_value={"score": 9.0, "issues": [], "approved": True}), \
         patch.object(images_mod, "log_usage"), \
         patch.object(images_mod, "_save_selected", side_effect=lambda *a, **k: object()):
        images_mod.generate_demo_screens(_FakeDb(), 1, "operations-dashboard", specs)

    anchor_calls = seen[: settings.DASHBOARD_CANDIDATES]
    followup_calls = seen[settings.DASHBOARD_CANDIDATES:]
    assert followup_calls, "no follow-up call was made — the test lost its subject"
    assert all(cfg is None for cfg in anchor_calls)
    assert all(cfg == {"image_size": "2K", "aspect_ratio": "16:9"} for cfg in followup_calls)


def test_regeneration_refires_the_same_image_config():
    """A retry that silently reverted to the default size would re-create
    the ten-pixel glyphs on exactly the screens that already failed once."""
    seen = []

    def fake_generate(prompt, *, model=None, reference_images=None, image_config=None, **_):
        seen.append(image_config)
        return {"image_bytes": VALID_PNG, "usage": None}

    cfg = {"image_size": "2K", "aspect_ratio": "16:9"}
    with patch.object(images_mod.provider, "generate_image", side_effect=fake_generate), \
         patch.object(images_mod.qa, "review_image", return_value={"score": 2.0, "issues": [], "approved": False}), \
         patch.object(images_mod, "log_usage"):
        images_mod._render_screen(
            _FakeDb(), 1, _spec_like(), [{"prompt": "p", "variant_id": None, "model": FLASH, "image_config": cfg}],
            "v", reference_images=None,
        )

    assert len(seen) == 2, "expected the original call plus exactly one regeneration"
    assert seen == [cfg, cfg]


def _spec_like():
    """_render_screen only touches spec.screen_slug / style.archetype here."""
    class _Style:
        archetype = "operations-dashboard"

    class _Spec:
        screen_slug = "dashboard"
        style = _Style()

    return _Spec()


# ── the text-truth bands ─────────────────────────────────────────────────

def _band_sizes(width, height):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, format="PNG")
    return [Image.open(io.BytesIO(b)).size for b in qa._magnified_bands(buf.getvalue())]


def test_default_size_bands_are_exactly_the_old_3x():
    """The band fix shipped in session 33 against 1376/1408-wide images and
    is still unverified against a reproduced misspelling — its behaviour at
    those sizes must not drift while it waits for its proof."""
    assert _band_sizes(1376, 768) == [(1376 * 3, round(768 * 0.14) * 3), (round(1376 * 0.22) * 3, 768 * 3)]
    assert _band_sizes(1408, 768) == [(1408 * 3, round(768 * 0.14) * 3), (round(1408 * 0.22) * 3, 768 * 3)]


def test_2k_bands_stay_under_the_payload_ceiling():
    top, left = _band_sizes(2752, 1536)
    assert top == (2752, 215), "a 2752-wide band is already past the 4224 target: crop only, no upscale"
    assert left == (605 * 2, 1536 * 2), "the left band still has room for 2x"
    assert max(*top, *left) <= 4224


# ── the money ────────────────────────────────────────────────────────────

def test_the_2k_rate_is_the_ledger_measured_one():
    assert cost_model._rate(FLASH, "2K") == 0.10341
    assert cost_model._rate(FLASH, None) == 0.06959


def test_an_unmeasured_size_is_costed_at_the_most_expensive_known_rate():
    assert cost_model._rate(FLASH, "4K") == cost_model.UNMEASURED_IMAGE_COST_USD


def test_the_projection_prices_the_sizes_the_pipeline_requests():
    """At shipped defaults the follow-ups bill at the 2K rate and the whole
    request still projects inside the $0.60 DoD line."""
    projection = cost_model.projected_request_cost("operations-dashboard")
    at_default_size = cost_model.MEASURED_IMAGE_COST_USD[FLASH]
    at_2k = cost_model.MEASURED_IMAGE_COST_2K_USD[FLASH]
    assert projection["nominal_usd"] <= 0.60
    delta = round(projection["followup_candidates"] * (at_2k - at_default_size), 5)
    with patch.object(settings, "IMAGE_SIZE_FOLLOWUP", ""):
        cheaper = cost_model.projected_request_cost("operations-dashboard")
    assert round(projection["nominal_usd"] - cheaper["nominal_usd"], 5) == delta
