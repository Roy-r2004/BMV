"""QA parsing and candidate selection — mocked provider, no real AI calls."""

import io
import json

from unittest.mock import patch

from PIL import Image

from app.config import settings
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
    # Gate off: this pins the judge's own parsing. What the W3 text-truth
    # gate then adds to (and subtracts from) a verdict is pinned separately
    # in test_text_truth.py.
    with patch.object(qa.provider, "chat", return_value=_chat_response(
        '{"score": 8.7, "issues": ["minor icon blur"], "approved": true}'
    )), patch.object(qa, "log_usage"), patch.object(qa.settings, "ENABLE_TEXT_TRUTH_GATE", False), patch.object(qa.settings, "ENABLE_DEFECT_CHECK", False):
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
    )), patch.object(qa, "log_usage"), patch.object(qa.settings, "ENABLE_TEXT_TRUTH_GATE", False), patch.object(qa.settings, "ENABLE_DEFECT_CHECK", False):
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


# ── regeneration fires on what a prospect would notice (session 36) ──────
# The re-roll is judged on the candidate that would actually ship: hard
# failures (text-truth, confirmed defect, all-errored) and genuinely bad
# screens buy it; a marginal score does not, because on a score-only miss
# the approval path and the best-effort fallback ship the same image.


def _verdict(score, *, approved=False, text=True, defects=0):
    return {
        "score": score, "issues": [], "approved": approved,
        "text_truth": {"passed": text},
        "defects": {"confirmed": [{"kind": "malformed_data_display"}] * defects},
    }


def _reviews(*verdicts):
    seq = iter(verdicts)

    def fake_review(_db, _rid, _bytes, _spec):
        return next(seq)

    return fake_review


def _run_one_screen(dental_spec, *verdicts):
    calls = []

    def fake_generate(prompt, **_):
        calls.append(prompt)
        return {"image_bytes": VALID_PNG, "usage": None}

    with patch.object(images.provider, "generate_image", side_effect=fake_generate), \
         patch.object(images.qa, "review_image", side_effect=_reviews(*verdicts)), \
         patch.object(images, "log_usage"), \
         patch.object(images.settings, "MAX_REGENERATIONS", 1):
        selected, scored = images._render_screen(
            _FakeDb(), 1, dental_spec, [{"prompt": "p", "variant_id": None}], "v1",
            reference_images=None,
        )
    return calls, selected


def test_a_marginal_score_only_miss_ships_without_buying_the_regeneration(dental_spec):
    """Requests 90 and 91: a clean 7.9/7.8 re-rolled at ~$0.145 apiece and
    both re-rolls were thrown away. A marginal miss must not buy an image."""
    calls, selected = _run_one_screen(dental_spec, _verdict(7.8))
    assert len(calls) == 1, "a marginal score-only miss bought a second image"
    assert selected["verdict"]["score"] == 7.8


def test_a_bad_screen_still_buys_the_regeneration(dental_spec):
    """Request 6: a 6.5 re-rolled into a 7.9 that shipped. Below
    QA_REGEN_SCORE_FLOOR the re-roll is still worth its money."""
    calls, selected = _run_one_screen(dental_spec, _verdict(6.5), _verdict(7.9))
    assert len(calls) == 2
    assert selected["verdict"]["score"] == 7.9


def test_a_text_truth_failure_buys_the_regeneration_at_any_score(dental_spec):
    """Request 68: a 9.2 that misspelled the brand re-rolled into an 8.5
    that spelled it right, and the 8.5 shipped."""
    calls, selected = _run_one_screen(
        dental_spec, _verdict(9.2, text=False), _verdict(8.5))
    assert len(calls) == 2
    assert selected["verdict"]["score"] == 8.5, "text truth outranks score in the fallback"


def test_a_confirmed_defect_buys_the_regeneration(dental_spec):
    calls, selected = _run_one_screen(
        dental_spec, _verdict(8.5, defects=1), _verdict(8.0, approved=True))
    assert len(calls) == 2
    assert selected["verdict"]["score"] == 8.0


def test_every_candidate_erroring_still_buys_the_spaced_retry(dental_spec):
    """Concurrent candidates fail together on a provider blip; the spaced
    retry is the only recovery a request has (found in review — an old
    `and scored` guard skipped exactly this case)."""
    attempts = []

    def flaky_generate(prompt, **_):
        attempts.append(prompt)
        if len(attempts) == 1:
            raise RuntimeError("provider blip")
        return {"image_bytes": VALID_PNG, "usage": None}

    with patch.object(images.provider, "generate_image", side_effect=flaky_generate), \
         patch.object(images.qa, "review_image", side_effect=_reviews(_verdict(8.0, approved=True))), \
         patch.object(images, "log_usage"), \
         patch.object(images.settings, "MAX_REGENERATIONS", 1):
        selected, _ = images._render_screen(
            _FakeDb(), 1, dental_spec, [{"prompt": "p", "variant_id": None}], "v1",
            reference_images=None,
        )
    assert len(attempts) == 2
    assert selected is not None


def test_the_regen_floor_sits_below_the_approval_floor():
    """A regen floor above QA_MIN_SCORE would re-roll approved screens'
    neighbours for no reason; the two must stay ordered."""
    assert settings.QA_REGEN_SCORE_FLOOR <= settings.QA_MIN_SCORE


# ── the gate and the standard it is judged against (session 33) ──────────

# DoD line 2, consultant-service/ROADMAP.md: "No shipped screen scores below
# 8/10 on the fixed QA judge". Written here as a constant because the whole
# point of these two tests is that the number in the roadmap and the number
# the pipeline enforces must be the same number.
DOD_MIN_SHIPPED_SCORE = 8.0


def test_the_approval_gate_enforces_the_score_the_dod_is_judged_against():
    """Until 2026-08-12 the gate accepted 7 while the DoD demanded 8. Nothing
    said so, and sessions 31 and 32 passed that clause by luck — every screen
    happened to land at 8 or above. Session 33's golden set shipped four
    screens between 7.5 and 7.9 and the clause failed."""
    assert settings.QA_MIN_SCORE >= DOD_MIN_SHIPPED_SCORE, (
        f"the gate approves screens at {settings.QA_MIN_SCORE} but the DoD "
        f"forbids shipping below {DOD_MIN_SHIPPED_SCORE} — one of the two is wrong"
    )


def test_a_candidate_under_the_dod_floor_is_not_approved(dental_spec):
    """The gate as behaviour, not as a number: a 7.9 was shippable before this
    change and must not be now."""
    body = {"choices": [{"message": {"content": '{"score": 7.9, "issues": [], "approved": true}'}}], "usage": {}}

    with patch.object(qa.provider, "chat", return_value=body), \
         patch.object(qa.settings, "ENABLE_TEXT_TRUTH_GATE", False), patch.object(qa.settings, "ENABLE_DEFECT_CHECK", False), \
         patch.object(qa, "log_usage"):
        verdict = qa.review_image(_FakeDb(), 1, VALID_PNG, dental_spec)

    assert verdict["score"] == 7.9
    assert not verdict["approved"], "a screen below the DoD floor was approved"


def test_a_missing_score_keeps_the_judges_own_verdict(dental_spec):
    """Fail-open contract: a judge that returned no number must not reject
    every candidate a request has."""
    body = {"choices": [{"message": {"content": '{"issues": [], "approved": true}'}}], "usage": {}}

    with patch.object(qa.provider, "chat", return_value=body), \
         patch.object(qa.settings, "ENABLE_TEXT_TRUTH_GATE", False), patch.object(qa.settings, "ENABLE_DEFECT_CHECK", False), \
         patch.object(qa, "log_usage"):
        verdict = qa.review_image(_FakeDb(), 1, VALID_PNG, dental_spec)

    assert verdict["score"] is None and verdict["approved"]


def test_the_code_gate_only_ever_subtracts(dental_spec):
    """A judge that says no is not overruled by a high score."""
    body = {"choices": [{"message": {"content": '{"score": 9.4, "issues": ["x"], "approved": false}'}}], "usage": {}}

    with patch.object(qa.provider, "chat", return_value=body), \
         patch.object(qa.settings, "ENABLE_TEXT_TRUTH_GATE", False), patch.object(qa.settings, "ENABLE_DEFECT_CHECK", False), \
         patch.object(qa, "log_usage"):
        verdict = qa.review_image(_FakeDb(), 1, VALID_PNG, dental_spec)

    assert not verdict["approved"]


# ── a failed-open defect check is unknown, not clean (request 107) ────────
# A 429 killed the inspector on a candidate that visibly carried a
# duplicated panel; the rank saw "no confirmed defects" and believed it
# clean. Three states now: inspected-clean > unknown > confirmed.


def _rank_cand(score, *, checked, confirmed=0):
    return {"verdict": {
        "score": score, "issues": [], "approved": False,
        "text_truth": {"passed": True},
        "defects": {"confirmed": [{"kind": "duplicated_panel"}] * confirmed, "checked": checked},
    }}


def test_inspected_clean_outranks_a_failed_open_check_regardless_of_score():
    checked_75 = _rank_cand(7.5, checked=True)
    unknown_90 = _rank_cand(9.0, checked=False)
    assert images._fallback_rank(checked_75) > images._fallback_rank(unknown_90)


def test_request_107s_unknown_still_outranks_the_confirmed_and_that_is_deliberate():
    """The 6.8 whose inspector died still ships over the 8.7 with one
    confirmed defect — unknown is not known-bad, the text rank's own
    principle. The cure for 107's blind spot is inspector retry under
    throttling, not a rank that punishes missing data harder than known
    damage. What this change buys is that the blindness is recorded
    (defects_checked in the metadata) and ranked below verified clean."""
    unknown_68 = _rank_cand(6.8, checked=False)
    confirmed_87 = _rank_cand(8.7, checked=True, confirmed=1)
    assert images._fallback_rank(unknown_68) > images._fallback_rank(confirmed_87)


def test_a_failed_open_inspector_is_recorded_as_unchecked_not_clean(dental_spec):
    body = {"choices": [{"message": {"content": '{"score": 9.0, "issues": [], "approved": true}'}}], "usage": {}}
    with patch.object(qa.provider, "chat", return_value=body), \
         patch.object(qa.settings, "ENABLE_TEXT_TRUTH_GATE", False), \
         patch.object(qa.settings, "ENABLE_DEFECT_CHECK", True), \
         patch.object(qa.defect_check, "inspect_call",
                      return_value={"claims": [], "usage": None, "error": "upstream 429"}), \
         patch.object(qa, "log_usage"):
        verdict = qa.review_image(_FakeDb(), 1, VALID_PNG, dental_spec)
    assert verdict["defects"]["checked"] is False
    assert verdict["defects"]["confirmed"] == []
