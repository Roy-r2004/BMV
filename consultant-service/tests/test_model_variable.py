"""Pins for `model` as a first-class per-call generation variable (W1).

The bake-off, and the per-role tiering it may adopt, both depend on one
property: the model that ACTUALLY produced a candidate is the model that
gets recorded — in the ledger, in the log line, in the saved metadata and
on the row. A global `settings.IMAGE_MODEL` read anywhere downstream would
silently mis-attribute every measurement the bake-off is meant to produce.

Defaults are unchanged: with no override and no measured archetype entry,
every call resolves to IMAGE_MODEL exactly as before.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch

from PIL import Image

from app.config import settings
from app.pipeline import images as images_mod

_buf = io.BytesIO()
Image.new("RGB", (4, 4), "white").save(_buf, format="PNG")
VALID_PNG = _buf.getvalue()

PRO = "google/gemini-3-pro-image"
FLASH = "google/gemini-3.1-flash-image"


class _FakeDb:
    def add(self, *_): ...
    def commit(self): ...
    def get(self, *_): return object()


# ── the call itself ──────────────────────────────────────────────────────

def test_per_item_model_reaches_the_provider_and_tags_the_result():
    seen = []

    def fake_generate(prompt, *, model=None, reference_images=None, **_):
        seen.append(model)
        return {"image_bytes": VALID_PNG, "usage": None}

    with patch.object(images_mod.provider, "generate_image", side_effect=fake_generate):
        results = images_mod._generate_candidates(
            [
                {"prompt": "p1", "variant_id": "hero-intelligence", "model": PRO},
                {"prompt": "p2", "variant_id": "command-center", "model": FLASH},
            ],
            None,
        )

    assert sorted(seen) == sorted([PRO, FLASH])
    assert {r["variant_id"]: r["model"] for r in results} == {
        "hero-intelligence": PRO,
        "command-center": FLASH,
    }


def test_item_without_model_falls_back_to_configured_default():
    seen = []

    def fake_generate(prompt, *, model=None, **_):
        seen.append(model)
        return {"image_bytes": VALID_PNG, "usage": None}

    with patch.object(images_mod.provider, "generate_image", side_effect=fake_generate), \
         patch.object(images_mod.settings, "IMAGE_MODEL", "configured/default"):
        results = images_mod._generate_candidates([{"prompt": "p", "variant_id": None}], None)

    assert seen == ["configured/default"]
    assert results[0]["model"] == "configured/default"


def test_failed_candidate_still_carries_its_model():
    """A model that fails is a bake-off result too — an untagged failure
    would quietly drop out of the per-model tally."""
    with patch.object(images_mod.provider, "generate_image", side_effect=RuntimeError("boom")):
        results = images_mod._generate_candidates([{"prompt": "p", "variant_id": None, "model": FLASH}], None)

    assert results[0]["error"] is not None
    assert results[0]["model"] == FLASH


def test_referenceless_retry_keeps_the_same_model():
    seen = []

    def fake_generate(prompt, *, model=None, reference_images=None, **_):
        seen.append((model, bool(reference_images)))
        if reference_images:
            raise RuntimeError("model cannot accept image input")
        return {"image_bytes": VALID_PNG, "usage": None}

    with patch.object(images_mod.provider, "generate_image", side_effect=fake_generate):
        results = images_mod._generate_candidates(
            [{"prompt": "continuation", "variant_id": None, "model": FLASH}],
            [b"anchor"],
            fallback_prompt="standalone",
        )

    assert results[0]["error"] is None
    assert seen == [(FLASH, True), (FLASH, False)]


# ── the ledger ───────────────────────────────────────────────────────────

def test_ledger_records_each_candidates_own_model(dental_spec):
    logged = []

    def fake_generate(prompts, reference_images, fallback_prompt=None):
        return [
            {"prompt": "p1", "variant_id": "v0", "model": PRO,
             "image_bytes": VALID_PNG, "usage": None, "latency_s": 0.1, "error": None},
            {"prompt": "p2", "variant_id": "v1", "model": FLASH,
             "error": RuntimeError("boom"), "latency_s": 0.1},
        ]

    with patch.object(images_mod, "_generate_candidates", side_effect=fake_generate), \
         patch.object(images_mod.qa, "review_image",
                      return_value={"score": 9.0, "issues": [], "approved": True}), \
         patch.object(images_mod, "log_usage",
                      side_effect=lambda db, rid, **kw: logged.append((kw["model"], kw["success"]))), \
         patch.object(images_mod.settings, "IMAGE_MODEL", "must/not/be/used"):
        images_mod._render_screen(
            _FakeDb(), 1, dental_spec,
            [{"prompt": "p", "variant_id": None, "model": PRO}], "v1", reference_images=None,
        )

    assert (PRO, True) in logged
    assert (FLASH, False) in logged
    assert not any(m == "must/not/be/used" for m, _ in logged)


def test_regeneration_inherits_the_retried_candidates_model(dental_spec):
    """Under tiering the anchor and follow-ups run different models; a
    regeneration that silently reverted to the global default would make
    the ledger describe a run that never happened."""
    calls = []

    def fake_generate(prompts, reference_images, fallback_prompt=None):
        calls.append([(p["prompt"], p.get("model")) for p in prompts])
        return [
            {"prompt": p["prompt"], "variant_id": p.get("variant_id"), "model": p.get("model"),
             "image_bytes": VALID_PNG, "usage": None, "latency_s": 0.1, "error": None}
            for p in prompts
        ]

    scores = iter([4.0, 6.0, 8.0])  # two rejected, then the retry approves

    with patch.object(images_mod, "_generate_candidates", side_effect=fake_generate), \
         patch.object(images_mod.qa, "review_image",
                      side_effect=lambda *_: (lambda s: {"score": s, "issues": [], "approved": s >= 7})(next(scores))), \
         patch.object(images_mod, "log_usage"), \
         patch.object(images_mod.settings, "MAX_REGENERATIONS", 1), \
         patch.object(images_mod.settings, "IMAGE_MODEL", "must/not/be/used"):
        selected, _ = images_mod._render_screen(
            _FakeDb(), 1, dental_spec,
            [{"prompt": "hero", "variant_id": "v0", "model": FLASH},
             {"prompt": "command", "variant_id": "v1", "model": FLASH}],
            "v1", reference_images=None,
        )

    assert calls[-1] == [("command", FLASH)]  # best-scoring prompt, same model
    assert selected["model"] == FLASH


def test_regeneration_after_total_failure_keeps_the_requested_model(dental_spec):
    """Every candidate errored, so there is no scored candidate to inherit
    from — the retry must fall back to the prompt ITEM's model, not the
    global default."""
    calls = []

    def fake_generate(prompts, reference_images, fallback_prompt=None):
        calls.append([(p["prompt"], p.get("model")) for p in prompts])
        return [
            {"prompt": p["prompt"], "variant_id": p.get("variant_id"), "model": p.get("model"),
             "error": RuntimeError("boom"), "latency_s": 0.1}
            for p in prompts
        ]

    with patch.object(images_mod, "_generate_candidates", side_effect=fake_generate), \
         patch.object(images_mod, "log_usage"), \
         patch.object(images_mod.settings, "MAX_REGENERATIONS", 1), \
         patch.object(images_mod.settings, "IMAGE_MODEL", "must/not/be/used"):
        selected, scored = images_mod._render_screen(
            _FakeDb(), 1, dental_spec,
            [{"prompt": "hero", "variant_id": "v0", "model": FLASH}], "v1", reference_images=None,
        )

    assert selected is None and scored == []
    assert calls[-1] == [("hero", FLASH)]


# ── what gets persisted ──────────────────────────────────────────────────

def test_saved_metadata_and_row_record_the_producing_model(dental_spec, tmp_path):
    winner = {
        "image_bytes": VALID_PNG, "prompt": "hero", "variant_id": "hero-intelligence", "model": PRO,
        "attempt": 0, "latency_s": 12.3, "verdict": {"score": 8.7, "issues": [], "approved": True},
    }
    loser = {
        "image_bytes": VALID_PNG, "prompt": "command", "variant_id": "command-center", "model": FLASH,
        "attempt": 1, "latency_s": 9.9, "verdict": {"score": 6.0, "issues": [], "approved": False},
    }

    with patch.object(images_mod.settings, "UPLOADS_DIR", str(tmp_path)), \
         patch.object(images_mod.settings, "IMAGE_MODEL", "must/not/be/used"):
        row = images_mod._save_selected(
            _FakeDb(), 1, dental_spec, "operations-dashboard", winner, [winner, loser], "dashboard-image-v1",
        )

    assert row.model == PRO
    metadata = json.loads((tmp_path / "images" / "1" / "dashboard_0.json").read_text())
    assert metadata["model"] == PRO
    assert [c["model"] for c in metadata["candidates"]] == [PRO, FLASH]


# ── per-role tiering ─────────────────────────────────────────────────────

def test_anchor_and_followups_can_run_different_models(dental_spec):
    """The tiering shape: pro-class anchor, flash-class follow-ups
    conditioned on the anchor."""
    seen: list[tuple[str, list]] = []

    def fake_render(db, request_id, spec, prompts, prompt_version, reference_images, fallback_prompt=None):
        seen.append((spec.screen_slug, [p.get("model") for p in prompts]))
        return (
            {"image_bytes": VALID_PNG, "prompt": prompts[0]["prompt"],
             "variant_id": prompts[0].get("variant_id"), "model": prompts[0].get("model"),
             "attempt": 0, "latency_s": 1.0, "verdict": {"score": 9, "issues": [], "approved": True}},
            [],
        )

    follow_up = dental_spec.model_copy(deep=True)
    follow_up.product.screen_type = "schedule"  # screen_title/slug derive from this

    with patch.object(images_mod, "_render_screen", side_effect=fake_render), \
         patch.object(images_mod, "_save_selected", return_value=object()), \
         patch.object(images_mod.settings, "DASHBOARD_CANDIDATES", 2), \
         patch.object(images_mod.settings, "SECONDARY_CANDIDATES", 1):
        images_mod.generate_demo_screens(
            _FakeDb(), 1, "operations-dashboard", [dental_spec, follow_up],
            anchor_model=PRO, followup_model=FLASH,
        )

    assert seen[0][1] == [PRO, PRO]      # both anchor composition variants
    assert seen[1][1] == [FLASH]         # follow-up screen


def test_default_run_still_resolves_to_the_configured_image_model(dental_spec):
    seen: list[list] = []

    def fake_render(db, request_id, spec, prompts, prompt_version, reference_images, fallback_prompt=None):
        seen.append([p.get("model") for p in prompts])
        return None, []

    with patch.object(images_mod, "_render_screen", side_effect=fake_render), \
         patch.object(images_mod.settings, "DASHBOARD_CANDIDATES", 1), \
         patch.object(images_mod.settings, "IMAGE_MODEL", "configured/default"), \
         patch.object(images_mod.settings, "IMAGE_MODEL_ANCHOR", ""), \
         patch.object(images_mod.settings, "ARCHETYPE_IMAGE_MODELS", {}):
        images_mod.generate_demo_screens(_FakeDb(), 1, "operations-dashboard", [dental_spec])

    assert seen == [["configured/default"]]


# ── config resolution ────────────────────────────────────────────────────

def test_unmeasured_archetype_falls_back_to_image_model():
    with patch.object(settings, "ARCHETYPE_IMAGE_MODELS", {}), \
         patch.object(settings, "IMAGE_MODEL_ANCHOR", ""), \
         patch.object(settings, "IMAGE_MODEL_FOLLOWUP", ""), \
         patch.object(settings, "IMAGE_MODEL", "configured/default"):
        assert settings.anchor_model_for("crm-dashboard") == "configured/default"
        assert settings.followup_model_for(None) == "configured/default"


def test_measured_archetype_table_is_used_and_env_override_outranks_it():
    table = {"crm-dashboard": {"anchor": PRO, "followup": FLASH}}
    with patch.object(settings, "ARCHETYPE_IMAGE_MODELS", table), \
         patch.object(settings, "IMAGE_MODEL_ANCHOR", ""), \
         patch.object(settings, "IMAGE_MODEL_FOLLOWUP", ""), \
         patch.object(settings, "IMAGE_MODEL", "configured/default"):
        assert settings.anchor_model_for("crm-dashboard") == PRO
        assert settings.followup_model_for("crm-dashboard") == FLASH
        # An archetype with no measured entry is untouched by another's.
        assert settings.anchor_model_for("analytics-dashboard") == "configured/default"

    with patch.object(settings, "ARCHETYPE_IMAGE_MODELS", table), \
         patch.object(settings, "IMAGE_MODEL_ANCHOR", "override/anchor"), \
         patch.object(settings, "IMAGE_MODEL_FOLLOWUP", "override/followup"):
        assert settings.anchor_model_for("crm-dashboard") == "override/anchor"
        assert settings.followup_model_for("crm-dashboard") == "override/followup"
