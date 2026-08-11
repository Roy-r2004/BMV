"""QA parsing and candidate selection — mocked provider, no real AI calls."""

import io
import json

from unittest.mock import patch

from PIL import Image

from app.pipeline import images, qa

_buf = io.BytesIO()
Image.new("RGB", (4, 4), "white").save(_buf, format="PNG")
VALID_PNG = _buf.getvalue()


class _FakeDb:
    def add(self, *_): ...
    def commit(self): ...
    def get(self, *_): return None


def _chat_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}], "usage": {"cost": 0.0001}}


def test_qa_parses_verdict(dental_spec):
    with patch.object(qa.provider, "chat", return_value=_chat_response(
        '{"score": 8.7, "issues": ["minor icon blur"], "approved": true}'
    )), patch.object(qa, "log_usage"):
        verdict = qa.review_image(_FakeDb(), 1, b"png-bytes", dental_spec)
    assert verdict == {"score": 8.7, "issues": ["minor icon blur"], "approved": True}


def test_qa_fails_open_on_garbage_response(dental_spec):
    with patch.object(qa.provider, "chat", return_value=_chat_response("not json at all")), \
         patch.object(qa, "log_usage"):
        verdict = qa.review_image(_FakeDb(), 1, b"png-bytes", dental_spec)
    assert verdict["approved"] is True
    assert verdict["score"] is None
    assert verdict["issues"]


def test_qa_disabled_returns_neutral_approval(dental_spec):
    with patch.object(qa.settings, "ENABLE_VISION_QA", False):
        verdict = qa.review_image(_FakeDb(), 1, b"png-bytes", dental_spec)
    assert verdict == {"score": None, "issues": [], "approved": True}


def test_select_best_prefers_highest_approved_score():
    candidates = [
        {"verdict": {"score": 6.0, "approved": True}},
        {"verdict": {"score": 9.1, "approved": True}},
        {"verdict": {"score": 9.8, "approved": False}},
    ]
    assert images._select_best(candidates)["verdict"]["score"] == 9.1


def test_select_best_ranks_scored_above_fail_open_none():
    candidates = [
        {"verdict": {"score": None, "approved": True}},
        {"verdict": {"score": 7.2, "approved": True}},
    ]
    assert images._select_best(candidates)["verdict"]["score"] == 7.2


def test_select_best_returns_none_when_nothing_approved():
    candidates = [{"verdict": {"score": 9.9, "approved": False}}]
    assert images._select_best(candidates) is None


def test_generate_candidates_retries_without_reference_on_failure():
    calls = []

    def fake_generate(prompt, *, reference_images=None, **_):
        calls.append(reference_images)
        if reference_images:
            raise RuntimeError("model cannot accept image input")
        return {"image_bytes": VALID_PNG, "usage": None}

    with patch.object(images.provider, "generate_image", side_effect=fake_generate):
        results = images._generate_candidates([{"prompt": "prompt", "variant_id": None}], [b"anchor"])
    assert results[0]["error"] is None
    assert results[0]["used_reference"] is False
    assert calls == [[b"anchor"], None]


def test_qa_string_false_is_not_approval(dental_spec):
    with patch.object(qa.provider, "chat", return_value=_chat_response(
        '{"score": 3.0, "issues": ["garbled text"], "approved": "false"}'
    )), patch.object(qa, "log_usage"):
        verdict = qa.review_image(_FakeDb(), 1, b"png-bytes", dental_spec)
    assert verdict["approved"] is False


def test_referenceless_retry_uses_fallback_prompt():
    prompts_sent = []

    def fake_generate(prompt, *, reference_images=None, **_):
        prompts_sent.append((prompt, bool(reference_images)))
        if reference_images:
            raise RuntimeError("model cannot accept image input")
        return {"image_bytes": VALID_PNG, "usage": None}

    with patch.object(images.provider, "generate_image", side_effect=fake_generate):
        results = images._generate_candidates(
            [{"prompt": "continuation: the attached image is...", "variant_id": None}], [b"anchor"],
            fallback_prompt="standalone prompt",
        )
    assert results[0]["error"] is None
    assert prompts_sent == [("continuation: the attached image is...", True), ("standalone prompt", False)]


def test_undecodable_bytes_become_candidate_error():
    with patch.object(images.provider, "generate_image", return_value={"image_bytes": b"not a png", "usage": None}):
        results = images._generate_candidates([{"prompt": "prompt", "variant_id": None}], None)
    assert results[0]["error"] is not None
    assert "undecodable" in str(results[0]["error"])


def test_generate_candidates_tags_results_with_variant_id():
    with patch.object(images.provider, "generate_image", return_value={"image_bytes": VALID_PNG, "usage": None}):
        results = images._generate_candidates(
            [{"prompt": "p1", "variant_id": "hero-intelligence"}, {"prompt": "p2", "variant_id": "command-center"}],
            None,
        )
    assert {r["variant_id"] for r in results} == {"hero-intelligence", "command-center"}


def test_render_screen_regeneration_retries_best_scoring_variant(dental_spec):
    """When nothing is approved, the retry should reuse the single
    best-scoring candidate's own prompt/variant, not re-fire every variant."""
    calls = []

    def fake_generate(prompt, **_):
        calls.append(prompt)
        return {"image_bytes": VALID_PNG, "usage": None}

    scores = iter([4.0, 6.0, 5.0, 8.0])  # 3 initial (none approved) + 1 retry (approved)

    def fake_review(_db, _rid, _bytes, _spec):
        score = next(scores)
        return {"score": score, "issues": [], "approved": score >= 7}

    prompts = [
        {"prompt": "hero prompt", "variant_id": "hero-intelligence"},
        {"prompt": "command prompt", "variant_id": "command-center"},
        {"prompt": "exec prompt", "variant_id": "executive-overview"},
    ]
    with patch.object(images.provider, "generate_image", side_effect=fake_generate), \
         patch.object(images.qa, "review_image", side_effect=fake_review), \
         patch.object(images, "log_usage"), \
         patch.object(images.settings, "MAX_REGENERATIONS", 1):
        selected, scored = images._render_screen(_FakeDb(), 1, dental_spec, prompts, "v1", reference_images=None)

    assert selected["verdict"]["score"] == 8.0
    # Retry used command-center's prompt (the best-scoring of the 3 initial, at 6.0)
    assert calls[-1] == "command prompt"


def test_save_selected_persists_composition_variant(dental_spec, tmp_path):
    selected = {
        "image_bytes": VALID_PNG, "prompt": "hero prompt", "variant_id": "hero-intelligence",
        "attempt": 0, "latency_s": 12.3, "verdict": {"score": 8.7, "issues": [], "approved": True},
    }
    with patch.object(images.settings, "UPLOADS_DIR", str(tmp_path)):
        row = images._save_selected(_FakeDb(), 1, dental_spec, "operations-dashboard", selected, [selected], "dashboard-image-v1")
    assert row.composition_variant == "hero-intelligence"
    assert row.prompt_version == "dashboard-image-v1+composition"

    metadata = json.loads((tmp_path / "images" / "1" / "dashboard_0.json").read_text())
    assert metadata["composition_variant"] == "hero-intelligence"
    assert metadata["candidates"][0]["variant"] == "hero-intelligence"
