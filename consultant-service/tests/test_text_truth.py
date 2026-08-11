"""Pins for W3 — the text-truth gate.

The failures this exists for are real, from the W1 bake-off: one model
rendered "Hartwell Chamers" for "Hartwell Chambers" and "Northgate Roast
Inteligence" for "Intelligence", and the aesthetic judge scored both
screens in the 8s while reporting the text as correct.

Two halves are pinned separately: the pure diff (text_truth.check) and the
wiring that turns a failed diff into a rejection the existing regeneration
path acts on.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch

from PIL import Image

from app.pipeline import images as images_mod
from app.pipeline import qa, text_truth

_buf = io.BytesIO()
Image.new("RGB", (4, 4), "white").save(_buf, format="PNG")
VALID_PNG = _buf.getvalue()


class _FakeDb:
    def add(self, *_): ...
    def commit(self): ...
    def get(self, *_): return object()


def _full_transcript(spec) -> list[str]:
    return [spec.business.name, spec.product.name, *spec.navigation, "Appointments Today", "18"]


# ── the diff ─────────────────────────────────────────────────────────────

def test_exactly_rendered_strings_pass(dental_spec):
    result = text_truth.check(dental_spec, _full_transcript(dental_spec))
    assert result["passed"] is True
    assert result["checked"] == 2 + len(dental_spec.navigation)


def test_a_misspelled_product_name_fails_and_is_named(dental_spec):
    transcript = _full_transcript(dental_spec)
    transcript[1] = "SmileBright Operatons"

    result = text_truth.check(dental_spec, transcript)
    assert result["passed"] is False
    failure = next(f for f in result["failures"] if f["field"] == "product_name")
    assert failure["kind"] == "misspelled"
    assert failure["closest"] == "smilebright operatons"
    assert 'rendered as "smilebright operatons"' in text_truth.describe(result)[0]


def test_a_business_name_that_is_simply_absent_is_not_a_failure(dental_spec):
    """Real product UIs show the product wordmark, not the client's company
    name — no model in the bake-off rendered "Hartwell & Grey LLP" anywhere,
    correctly. The rule is: if it appears, it must be right."""
    transcript = [t for t in _full_transcript(dental_spec) if t != dental_spec.business.name]

    result = text_truth.check(dental_spec, transcript)
    assert result["passed"] is True
    assert [a["expected"] for a in result["absent"]] == [dental_spec.business.name]


def test_a_misspelled_business_name_that_IS_rendered_fails(dental_spec):
    transcript = _full_transcript(dental_spec)
    transcript[0] = "SmileBrite Dental"

    result = text_truth.check(dental_spec, transcript)
    assert result["passed"] is False
    failure = next(f for f in result["failures"] if f["field"] == "business_name")
    assert failure["kind"] == "misspelled"


def test_a_missing_product_name_is_a_failure(dental_spec):
    transcript = [t for t in _full_transcript(dental_spec) if t != dental_spec.product.name]

    result = text_truth.check(dental_spec, transcript)
    assert result["passed"] is False
    failure = next(f for f in result["failures"] if f["field"] == "product_name")
    assert failure["kind"] == "missing"


def test_a_wordmark_wrapped_across_two_lines_still_matches(dental_spec):
    """Every model tested wraps the sidebar wordmark; a transcriber returns
    the two LINES, not the logical string. Matching per-entry only called
    four correct screens misspelled."""
    transcript = ["SmileBright", "Operations", *dental_spec.navigation]

    assert text_truth.check(dental_spec, transcript)["passed"] is True


def test_case_and_spacing_differences_are_not_failures(dental_spec):
    """A sidebar rendering "DASHBOARD" is styling, not a misspelling —
    failing it would burn a regeneration on a correct screen."""
    transcript = [
        dental_spec.business.name.upper(),
        "  " + dental_spec.product.name + " ",
        *[label.upper() for label in dental_spec.navigation],
    ]
    assert text_truth.check(dental_spec, transcript)["passed"] is True


def test_a_label_rendered_inside_a_longer_line_still_counts(dental_spec):
    transcript = [
        dental_spec.business.name,
        dental_spec.product.name,
        *[f"{label}  12" for label in dental_spec.navigation],
    ]
    assert text_truth.check(dental_spec, transcript)["passed"] is True


def test_a_truncated_label_does_not_pass_as_its_longer_self(dental_spec):
    """"Recal" sits inside "Recall" — a bare substring test would give a
    dropped character a free pass in exactly the case this gate exists for."""
    dental_spec.navigation = ["Dashboard", "Recall"]
    transcript = [dental_spec.product.name, "Dashboard", "Recal"]

    result = text_truth.check(dental_spec, transcript)
    assert result["passed"] is False
    assert [f["expected"] for f in result["failures"]] == ["Recall"]


def test_only_the_navigation_the_prompt_asked_for_is_checked(dental_spec):
    """prompt_builder sends navigation[:8]; holding the screen to a 9th
    label it was never given would be an unfixable permanent failure."""
    dental_spec.navigation = [f"Item{i}" for i in range(12)]
    transcript = [dental_spec.business.name, dental_spec.product.name, *dental_spec.navigation[:8]]

    result = text_truth.check(dental_spec, transcript)
    assert result["passed"] is True
    assert result["checked"] == 10  # business + product + 8 nav


def test_an_empty_transcript_fails_every_required_string(dental_spec):
    result = text_truth.check(dental_spec, [])
    assert result["passed"] is False
    # Everything except the business name, whose absence is allowed.
    assert len(result["failures"]) == result["checked"] - 1
    assert len(result["absent"]) == 1


# ── the wiring ───────────────────────────────────────────────────────────

def _qa_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}], "usage": {"cost": 0.001}}


def _routed_chat(judge=None, transcription=None):
    """A provider.chat fake that answers by INSTRUMENT, not by call order.
    review_image fires its instruments concurrently (session 34), so a test
    that hands out responses in arrival order is a race. Each value may be
    a single response, an Exception to raise, or a list consumed in order
    (an instrument's own retries ARE serial)."""
    routes = {
        "product design director": judge,
        "transcribe the misspelling": transcription,
    }

    def _fake(model, messages, **kwargs):
        content = messages[0]["content"]
        text = content[0]["text"] if isinstance(content, list) else content
        for marker, resp in routes.items():
            if resp is not None and marker in text:
                item = resp.pop(0) if isinstance(resp, list) else resp
                if isinstance(item, Exception):
                    raise item
                return item
        raise AssertionError(f"unrouted chat call: {text[:80]}")

    return _fake


def test_gate_rejects_a_high_scoring_but_misspelled_screen(dental_spec):
    """The whole point: aesthetics never override the client's name."""
    fake = _routed_chat(
        judge=_qa_response('{"score": 9.4, "issues": [], "approved": true}'),
        transcription=_qa_response('{"text": ["SmileBright Dental", "SmileBright Operatons"], "uncertain": []}'),
    )
    with patch.object(qa.provider, "chat", side_effect=fake), \
         patch.object(qa, "log_usage"), \
         patch.object(qa.settings, "ENABLE_TEXT_TRUTH_GATE", True), \
         patch.object(qa.settings, "ENABLE_DEFECT_CHECK", False):
        verdict = qa.review_image(_FakeDb(), 1, VALID_PNG, dental_spec)

    assert verdict["approved"] is False
    assert verdict["score"] == 9.4, "the aesthetic score is reported honestly, not zeroed"
    assert verdict["text_truth"]["passed"] is False
    assert any("text-truth" in issue for issue in verdict["issues"])


def test_gate_cannot_rescue_a_screen_the_judge_rejected(dental_spec):
    fake = _routed_chat(
        judge=_qa_response('{"score": 3.0, "issues": ["garbled chart"], "approved": false}'),
        transcription=_qa_response(
            '{"text": ["SmileBright Dental", "SmileBright Operations", "Dashboard", "Schedule",'
            ' "Patients", "Recall", "Reports", "Settings"], "uncertain": []}'
        ),
    )
    with patch.object(qa.provider, "chat", side_effect=fake), \
         patch.object(qa, "log_usage"), \
         patch.object(qa.settings, "ENABLE_TEXT_TRUTH_GATE", True), \
         patch.object(qa.settings, "ENABLE_DEFECT_CHECK", False):
        verdict = qa.review_image(_FakeDb(), 1, VALID_PNG, dental_spec)

    assert verdict["approved"] is False


def test_a_transcription_outage_fails_open(dental_spec):
    """An outage in the gate must not reject every candidate a request has."""
    fake = _routed_chat(
        judge=_qa_response('{"score": 8.6, "issues": [], "approved": true}'),
        transcription=RuntimeError("transcription down"),
    )
    with patch.object(qa.provider, "chat", side_effect=fake), \
         patch.object(qa, "log_usage"), \
         patch.object(qa.settings, "ENABLE_TEXT_TRUTH_GATE", True), \
         patch.object(qa.settings, "ENABLE_DEFECT_CHECK", False):
        verdict = qa.review_image(_FakeDb(), 1, VALID_PNG, dental_spec)

    assert verdict["approved"] is True
    assert verdict["text_truth"]["passed"] is None


def test_gate_still_runs_when_the_aesthetic_judge_is_down(dental_spec):
    fake = _routed_chat(
        judge=[RuntimeError("judge down"), RuntimeError("judge down")],
        transcription=_qa_response('{"text": ["SmileBright Dental", "Smilebrite Operations"], "uncertain": []}'),
    )
    with patch.object(qa.provider, "chat", side_effect=fake), \
         patch.object(qa, "log_usage"), patch.object(qa.time, "sleep"), \
         patch.object(qa.settings, "ENABLE_TEXT_TRUTH_GATE", True), \
         patch.object(qa.settings, "ENABLE_DEFECT_CHECK", False):
        verdict = qa.review_image(_FakeDb(), 1, VALID_PNG, dental_spec)

    assert verdict["score"] is None
    assert verdict["approved"] is False, "a QA outage is no reason to ship a misspelled client name"


def test_gate_can_be_disabled(dental_spec):
    judged = _qa_response('{"score": 9.0, "issues": [], "approved": true}')
    calls = []

    def only_the_judge(*args, **kwargs):
        calls.append(1)
        return judged

    with patch.object(qa.provider, "chat", side_effect=only_the_judge), \
         patch.object(qa, "log_usage"), \
         patch.object(qa.settings, "ENABLE_TEXT_TRUTH_GATE", False), \
         patch.object(qa.settings, "ENABLE_DEFECT_CHECK", False):
        verdict = qa.review_image(_FakeDb(), 1, VALID_PNG, dental_spec)

    assert calls == [1], "no transcription call when the gate is off"
    assert verdict["approved"] is True
    assert "text_truth" not in verdict


# ── the regeneration path ────────────────────────────────────────────────

def test_a_text_failure_triggers_the_regeneration(dental_spec):
    """The gate reuses the existing "nothing approved" path — it does not
    add a second, separate retry budget."""
    generated = []

    def fake_generate(prompts, reference_images, fallback_prompt=None):
        generated.append(len(prompts))
        return [
            {"prompt": p["prompt"], "variant_id": p.get("variant_id"), "model": p.get("model"),
             "image_bytes": VALID_PNG, "usage": None, "latency_s": 0.1, "error": None}
            for p in prompts
        ]

    verdicts = iter([
        {"score": 9.5, "issues": [], "approved": False, "text_truth": {"passed": False, "failures": []}},
        {"score": 8.0, "issues": [], "approved": True, "text_truth": {"passed": True, "failures": []}},
    ])

    with patch.object(images_mod, "_generate_candidates", side_effect=fake_generate), \
         patch.object(images_mod.qa, "review_image", side_effect=lambda *_: next(verdicts)), \
         patch.object(images_mod, "log_usage"), \
         patch.object(images_mod.settings, "MAX_REGENERATIONS", 1):
        selected, scored = images_mod._render_screen(
            _FakeDb(), 1, dental_spec,
            [{"prompt": "p", "variant_id": "v0", "model": "m"}], "v1", reference_images=None,
        )

    assert generated == [1, 1], "exactly one regeneration, the existing budget"
    assert selected["verdict"]["score"] == 8.0
    assert selected["verdict"]["text_truth"]["passed"] is True


def test_best_effort_prefers_correct_text_over_a_higher_score(dental_spec):
    """When everything was rejected, a plainer screen that spells the
    client's name right beats a prettier one that does not."""
    def fake_generate(prompts, reference_images, fallback_prompt=None):
        return [
            {"prompt": p["prompt"], "variant_id": p.get("variant_id"), "model": p.get("model"),
             "image_bytes": VALID_PNG, "usage": None, "latency_s": 0.1, "error": None}
            for p in prompts
        ]

    verdicts = iter([
        {"score": 9.6, "issues": [], "approved": False, "text_truth": {"passed": False, "failures": []}},
        {"score": 7.1, "issues": [], "approved": False, "text_truth": {"passed": True, "failures": []}},
        {"score": 9.9, "issues": [], "approved": False, "text_truth": {"passed": False, "failures": []}},
    ])

    with patch.object(images_mod, "_generate_candidates", side_effect=fake_generate), \
         patch.object(images_mod.qa, "review_image", side_effect=lambda *_: next(verdicts)), \
         patch.object(images_mod, "log_usage"), \
         patch.object(images_mod.settings, "MAX_REGENERATIONS", 0):
        selected, _ = images_mod._render_screen(
            _FakeDb(), 1, dental_spec,
            [{"prompt": f"p{i}", "variant_id": f"v{i}", "model": "m"} for i in range(3)],
            "v1", reference_images=None,
        )

    assert selected["verdict"]["score"] == 7.1


def test_unknown_text_truth_outranks_known_bad_in_the_fallback(dental_spec):
    def fake_generate(prompts, reference_images, fallback_prompt=None):
        return [
            {"prompt": p["prompt"], "variant_id": p.get("variant_id"), "model": p.get("model"),
             "image_bytes": VALID_PNG, "usage": None, "latency_s": 0.1, "error": None}
            for p in prompts
        ]

    verdicts = iter([
        {"score": 9.6, "issues": [], "approved": False, "text_truth": {"passed": False, "failures": []}},
        {"score": 8.0, "issues": [], "approved": False, "text_truth": {"passed": None}},
    ])

    with patch.object(images_mod, "_generate_candidates", side_effect=fake_generate), \
         patch.object(images_mod.qa, "review_image", side_effect=lambda *_: next(verdicts)), \
         patch.object(images_mod, "log_usage"), \
         patch.object(images_mod.settings, "MAX_REGENERATIONS", 0):
        selected, _ = images_mod._render_screen(
            _FakeDb(), 1, dental_spec,
            [{"prompt": f"p{i}", "variant_id": f"v{i}", "model": "m"} for i in range(2)],
            "v1", reference_images=None,
        )

    assert selected["verdict"]["score"] == 8.0


def test_the_product_wordmark_is_not_a_misspelling_of_the_business_name(dental_spec):
    """Measured on the golden set 2026-08-11: the salon screen renders
    "Lumière Studio OS" (its product name, correctly), which scores similar
    enough to the business name "Lumière Hair Studio" to be reported as a
    misspelling of it. The gate spent a regeneration on a correct screen and
    that request cost 60% more than its siblings."""
    dental_spec.business.name = "Lumière Hair Studio"
    dental_spec.product.name = "Lumière Studio OS"
    transcript = ["Lumière Studio OS", *dental_spec.navigation]

    result = text_truth.check(dental_spec, transcript)
    assert result["passed"] is True
    assert [a["expected"] for a in result["absent"]] == ["Lumière Hair Studio"]


def test_a_genuine_misspelling_still_fails_when_other_strings_are_fine(dental_spec):
    """The guard above must not become a blanket amnesty."""
    transcript = ["Smilebrite Dental", dental_spec.product.name, *dental_spec.navigation]

    result = text_truth.check(dental_spec, transcript)
    assert result["passed"] is False
    assert result["failures"][0]["closest"] == "smilebrite dental"


# ── the magnified bands (session 33) ─────────────────────────────────────

def test_the_transcription_call_carries_magnified_bands():
    """The gate missed "Cilents" for "Clients" on the salon schedule screen
    and reported it as passing. The transcription prompt already said "do
    not correct a misspelling" and had said so since it was written — what
    the model lacked was resolution, not willingness, so the fix hands it
    the same pixels bigger rather than asking again."""
    import io as _io

    from PIL import Image as _Image

    from app.pipeline import qa as qa_mod

    buf = _io.BytesIO()
    _Image.new("RGB", (1376, 814), "black").save(buf, format="PNG")
    sent = {}

    def fake_chat(model, messages, **kwargs):
        sent["content"] = messages[0]["content"]
        return {"choices": [{"message": {"content": '{"text": ["Clients"]}'}}], "usage": {}}

    class _Db:
        def add(self, *_): ...
        def commit(self): ...

    with patch.object(qa_mod.provider, "chat", side_effect=fake_chat):
        qa_mod.transcribe(_Db(), 1, buf.getvalue())

    images = [p for p in sent["content"] if p["type"] == "image_url"]
    assert len(images) == 3, "the full screenshot plus a magnified top band and left band"
    # The wording matters less than the instruction: the crops must arrive
    # introduced as magnified views to be read glyph by glyph. (The exact
    # factor is adaptive since 2K follow-ups — see tests/test_image_size.py.)
    assert any(
        "cropped and magnified" in p.get("text", "") and "character by character" in p.get("text", "")
        for p in sent["content"] if p["type"] == "text"
    )


def test_the_bands_can_be_switched_off_wholesale():
    import io as _io

    from PIL import Image as _Image

    from app.pipeline import qa as qa_mod

    buf = _io.BytesIO()
    _Image.new("RGB", (400, 300), "black").save(buf, format="PNG")
    sent = {}

    def fake_chat(model, messages, **kwargs):
        sent["content"] = messages[0]["content"]
        return {"choices": [{"message": {"content": '{"text": []}'}}], "usage": {}}

    class _Db:
        def add(self, *_): ...
        def commit(self): ...

    with patch.object(qa_mod.provider, "chat", side_effect=fake_chat), \
         patch.object(qa_mod.settings, "ENABLE_TEXT_TRUTH_ZOOM", False):
        qa_mod.transcribe(_Db(), 1, buf.getvalue())

    assert len([p for p in sent["content"] if p["type"] == "image_url"]) == 1


def test_an_unmagnifiable_image_still_transcribes():
    """A gate that cannot crop must run at the old fidelity, not fail."""
    from app.pipeline import qa as qa_mod

    assert qa_mod._magnified_bands(b"not an image") == []
