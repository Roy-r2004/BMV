"""Pins for the three review findings on the image stage.

1. Candidate attempt numbers are filenames — they must stay unique when a
   mid-list candidate errors and a regeneration follows (was: [ok, err, ok]
   scored as attempts 0/2 and the regen re-used 2, overwriting a file).
2. Non-selected candidates are watermarked before hitting disk — everything
   under UPLOADS_DIR is statically served, so a raw candidate is an
   unbranded full-quality demo at a guessable URL.
3. DASHBOARD_CANDIDATES actually caps the anchor's composition variants —
   it is the documented cost knob and had decoupled from generation.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

from app.pipeline import images as images_mod
from app.pipeline import prompt_builder


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
    return buf.getvalue()


def _candidate(variant_id: str, *, error: Exception | None = None) -> dict:
    if error is not None:
        return {"prompt": f"p-{variant_id}", "variant_id": variant_id, "error": error, "latency_s": 0.1}
    return {
        "prompt": f"p-{variant_id}",
        "variant_id": variant_id,
        "image_bytes": _png(),
        "usage": None,
        "latency_s": 0.1,
        "error": None,
    }


def test_attempt_numbers_stay_unique_through_error_and_regeneration(dental_spec, monkeypatch):
    passes = []

    def fake_generate(prompts, reference_images, fallback_prompt=None):
        if not passes:
            passes.append("first")
            return [_candidate("v0"), _candidate("v1", error=RuntimeError("boom")), _candidate("v2")]
        return [_candidate("v2")]

    monkeypatch.setattr(images_mod, "_generate_candidates", fake_generate)
    monkeypatch.setattr(
        images_mod.qa, "review_image",
        lambda db, rid, img, spec: {"approved": False, "score": 1, "issues": []},
    )
    monkeypatch.setattr(images_mod, "log_usage", lambda *a, **k: None)
    monkeypatch.setattr(images_mod.settings, "MAX_REGENERATIONS", 1)

    selected, scored = images_mod._render_screen(
        db=None, request_id=1, spec=dental_spec,
        prompts=[{"prompt": "p", "variant_id": v} for v in ("v0", "v1", "v2")],
        prompt_version="v", reference_images=None,
    )

    attempts = [c["attempt"] for c in scored]
    assert len(attempts) == 3  # two survivors + one regeneration
    assert len(set(attempts)) == len(attempts), f"filename collision: {attempts}"
    assert selected is not None  # best-effort ships even when nothing approved


def test_non_selected_candidates_are_watermarked_on_disk(dental_spec, monkeypatch, tmp_path):
    marked: list[bytes] = []

    def spy_watermark(image_bytes: bytes) -> bytes:
        marked.append(image_bytes)
        return b"WATERMARKED:" + image_bytes

    monkeypatch.setattr(images_mod, "_apply_bmv_watermark", spy_watermark)
    monkeypatch.setattr(images_mod.settings, "UPLOADS_DIR", str(tmp_path))

    class _Db:
        def add(self, row):  # noqa: D401 — test double
            self.row = row

        def commit(self):
            pass

    winner = _candidate("v0")
    winner["attempt"] = 0
    winner["verdict"] = {"score": 9, "issues": [], "approved": True}
    loser = _candidate("v1")
    loser["attempt"] = 1
    loser["verdict"] = {"score": 5, "issues": [], "approved": False}

    images_mod._save_selected(
        _Db(), 7, dental_spec, "operations-dashboard", winner, [winner, loser], "v",
    )

    assert len(marked) == 2, "both the selected image and the candidate must be watermarked"
    candidate_file = tmp_path / "images" / "7" / "candidates" / f"{dental_spec.screen_slug}_cand1.png"
    assert candidate_file.read_bytes().startswith(b"WATERMARKED:")


def test_dashboard_candidates_caps_anchor_variants(dental_spec, monkeypatch):
    captured: dict = {}

    def fake_render(db, request_id, spec, prompts, prompt_version, reference_images, fallback_prompt=None):
        captured["prompts"] = prompts
        return None, []  # anchor produces nothing -> function exits early

    class _Db:
        def get(self, model, pk):
            return object()  # request exists

    monkeypatch.setattr(images_mod, "_render_screen", fake_render)
    monkeypatch.setattr(images_mod.settings, "DASHBOARD_CANDIDATES", 2)

    result = images_mod.generate_demo_screens(_Db(), 1, "operations-dashboard", [dental_spec])

    assert result == []
    assert len(captured["prompts"]) == 2
    expected = [v["id"] for v in prompt_builder.COMPOSITION_VARIANTS[:2]]
    assert [p["variant_id"] for p in captured["prompts"]] == expected
