"""Pins for pairwise judging — the instrument the DoD's "beats the old
default on >= 4 of 5 briefs" is measured with.

The one property that makes it an instrument rather than a coin flip: a
verdict counts only if it survives swapping the images. Measured
2026-08-11, the first comparator tried (gemini-2.5-flash) answered "A" in
all six runs across three briefs — pure position bias. Without the swap
test that would have been reported as a clean 3-0 sweep.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from unittest.mock import patch

from app.ai import provider
from app.pipeline import pairwise
from app.templating import render


def _response(payload: str) -> dict:
    return {
        "choices": [{"finish_reason": "stop", "message": {"content": payload}}],
        "usage": {"cost": 0.017},
    }


def _verdict(winner: str) -> str:
    return f'{{"winner": "{winner}", "margin": "clear", "why": "reason", "a_defects": [], "b_defects": []}}'


def test_a_verdict_that_survives_the_swap_is_a_win(dental_spec):
    # "pro" passed first: forward picks A (=pro); reversed, pro is B — a
    # judge actually looking at the images picks B. Same winner both ways.
    with patch.object(pairwise.provider, "chat", side_effect=[_response(_verdict("A")), _response(_verdict("B"))]), \
         patch.object(pairwise, "log_usage"):
        result = pairwise.compare(None, None, b"pro", b"flash", dental_spec, left_label="pro", right_label="flash")

    assert result["winner"] == "pro"
    assert result["consistent"] is True


def test_position_bias_is_reported_as_a_tie_not_a_win(dental_spec):
    """Answering "A" both times means the judge picked whatever came first."""
    with patch.object(pairwise.provider, "chat", side_effect=[_response(_verdict("A")), _response(_verdict("A"))]), \
         patch.object(pairwise, "log_usage"):
        result = pairwise.compare(None, None, b"pro", b"flash", dental_spec, left_label="pro", right_label="flash")

    assert result["winner"] == "tie"
    assert result["consistent"] is False
    assert (result["forward_pick"], result["reverse_pick"]) == ("pro", "flash")


def test_an_explicit_tie_stays_a_tie(dental_spec):
    with patch.object(pairwise.provider, "chat", side_effect=[_response(_verdict("tie")), _response(_verdict("tie"))]), \
         patch.object(pairwise, "log_usage"):
        result = pairwise.compare(None, None, b"a", b"b", dental_spec)
    assert result["winner"] == "tie"
    assert result["consistent"] is False


def test_the_second_call_really_swaps_the_images(dental_spec):
    sent = []

    def capture(_model, messages, **_kw):
        parts = messages[0]["content"]
        images = [p["image_url"]["url"] for p in parts if p["type"] == "image_url"]
        sent.append(images)
        return _response(_verdict("A"))

    with patch.object(pairwise.provider, "chat", side_effect=capture), \
         patch.object(pairwise, "log_usage"):
        pairwise.compare(None, None, b"LEFT", b"RIGHT", dental_spec)

    assert len(sent) == 2
    assert sent[0] == list(reversed(sent[1])), "the swap test only works if the order actually swaps"


def test_each_image_is_labeled_immediately_before_its_bytes(dental_spec):
    """A bare "the first image is A" was not enough for the first judge
    tried; the labels are part of the instrument, not decoration."""
    captured = {}

    def capture(_model, messages, **_kw):
        captured["parts"] = messages[0]["content"]
        return _response(_verdict("A"))

    with patch.object(pairwise.provider, "chat", side_effect=capture), \
         patch.object(pairwise, "log_usage"):
        pairwise._judge_once(None, None, b"one", b"two", dental_spec)

    kinds = [p["type"] for p in captured["parts"]]
    texts = [p["text"] for p in captured["parts"] if p["type"] == "text"]
    assert "=== IMAGE A ===" in texts and "=== IMAGE B ===" in texts
    a_index = kinds.index("image_url")
    assert captured["parts"][a_index - 1]["text"] == "=== IMAGE A ==="


def test_a_judge_that_returned_no_text_is_an_error_not_a_tie(dental_spec):
    """finish_reason=length with content=None happens when a reasoning
    judge spends its whole budget thinking. Counting that as "no
    difference" would silently dilute every verdict in the set."""
    empty = {"choices": [{"finish_reason": "length", "message": {"content": None, "refusal": None}}]}

    with patch.object(pairwise.provider, "chat", return_value=empty), \
         patch.object(pairwise, "log_usage"):
        with pytest.raises(provider.AiProviderError) as exc:
            pairwise._judge_once(None, None, b"a", b"b", dental_spec)
    assert "length" in str(exc.value)


def test_pairwise_uses_its_own_configured_judge(dental_spec):
    used = []

    def capture(model, _messages, **_kw):
        used.append(model)
        return _response(_verdict("A"))

    with patch.object(pairwise.provider, "chat", side_effect=capture), \
         patch.object(pairwise.settings, "PAIRWISE_JUDGE_MODEL", "anthropic/claude-sonnet-5"), \
         patch.object(pairwise.settings, "QA_MODEL", "google/gemini-2.5-flash"), \
         patch.object(pairwise, "log_usage"):
        pairwise._judge_once(None, None, b"a", b"b", dental_spec)

    assert used == ["anthropic/claude-sonnet-5"], "the comparator is a separate instrument from the per-image judge"


# ── the v2 rubric (session 33) ───────────────────────────────────────────

def test_the_rubric_forbids_text_claims_outright(dental_spec):
    """Two judges have now failed this instrument the same way: pick the
    first-presented image, then justify it with a spelling claim the
    text-truth gate contradicts on the same file. v2 removes the question
    rather than hoping for a better answer to it."""
    prompt = render("image_pairwise_judge.j2",
                    screen_title="Dashboard", product_name="P", business_name="B", industry="I")

    assert "may not make any claim about text content, spelling, wording or text accuracy" in prompt
    assert "If your reason for preferring one image is that its text is more correct, discard the reason" in prompt
    # v1 led with text truth as criterion 1. It must not be a criterion at all.
    assert "TEXT TRUTH" not in prompt
    assert "must be spelled exactly" not in prompt


def test_the_rubric_makes_a_tie_a_real_answer(dental_spec):
    """The pressure to name a winner is what the position bias hid behind."""
    prompt = render("image_pairwise_judge.j2",
                    screen_title="Dashboard", product_name="P", business_name="B", industry="I")
    assert '"tie" is a real answer here, not a failure to decide' in prompt
    assert "The order the images appear in this message is arbitrary" in prompt


def test_the_rubric_no_longer_judges_a_corner_the_pipeline_stopped_reserving(dental_spec):
    """WATERMARK_STYLE=footer since session 32. v1 scored images against a
    reserved bottom-right corner that no prompt asks for any more."""
    prompt = render("image_pairwise_judge.j2",
                    screen_title="Dashboard", product_name="P", business_name="B", industry="I")
    assert "logo corner" not in prompt
    assert "reserved" not in prompt


def test_the_rubric_still_names_the_defects_the_dod_lists(dental_spec):
    """DoD line 2's defect list is what this instrument is now for."""
    prompt = render("image_pairwise_judge.j2",
                    screen_title="Dashboard", product_name="P", business_name="B", industry="I")
    for defect in ("Duplication", "Clipping and truncation", "Blank and unlabelled elements",
                   "Chrome that is not the application"):
        assert defect in prompt
