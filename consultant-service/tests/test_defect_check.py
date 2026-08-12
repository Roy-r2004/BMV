"""Pins for the per-screen structural defect check (JOB 3, session 34).

The two-stage shape is the contract: one inspector reports countable
structural defects, each claim goes to a separate verifier told to refute
it, and ONLY a claim both stages agree on may reject a candidate. Session
33's sweep — the existence proof this wires in — made 16 claims that were
refuted; single-stage, each of those was a false rejection costing a
regeneration. So the pins here are as much about what must NOT reject as
what must.

Also pinned: the concurrency that pays for the check. The three primary
instruments fire together (a barrier fake would deadlock if they were
serial), and follow-up screens run in parallel on their own DB sessions.
"""

import io
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch

from PIL import Image

from app.pipeline import defect_check
from app.pipeline import images as images_mod
from app.pipeline import qa

_buf = io.BytesIO()
Image.new("RGB", (4, 4), "white").save(_buf, format="PNG")
VALID_PNG = _buf.getvalue()


class _FakeDb:
    def add(self, *_): ...
    def commit(self): ...
    def get(self, *_): return object()


def _resp(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}], "usage": {"cost": 0.001}}


def _routed_chat(judge=None, transcription=None, inspector=None, verifier=None):
    """Answers by INSTRUMENT (the instruments run concurrently, so order
    fakes are races). Values: one response, an Exception, or a list."""
    routes = {
        "product design director": judge,
        "transcribe the misspelling": transcription,
        "meticulous QA inspector": inspector,
        "adversarial verifier": verifier,
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


APPROVING_JUDGE = '{"score": 9.0, "issues": [], "approved": true}'
ONE_CLAIM = (
    '{"defects": [{"kind": "duplicated_panel", "where": "bottom row",'
    ' "what": "the same recommendation card is drawn twice"}]}'
)


def _review(fake):
    with patch.object(qa.provider, "chat", side_effect=fake), \
         patch.object(qa, "log_usage"), \
         patch.object(qa.settings, "ENABLE_TEXT_TRUTH_GATE", False), \
         patch.object(qa.settings, "ENABLE_DEFECT_CHECK", True):
        return qa.review_image(_FakeDb(), 1, VALID_PNG, _spec())


def _spec():
    import pytest  # noqa: F401

    from app.ui_spec import UIDemoSpec
    return UIDemoSpec.model_validate({
        "business": {"name": "SmileBright Dental", "industry": "Dental Clinic", "primary_color": "#0e9594"},
        "product": {"name": "SmileBright Operations", "purpose": "clinic ops", "screen_type": "dashboard"},
        "user": {"name": "Dr. Carter", "role": "Owner"},
        "navigation": ["Dashboard", "Patients"],
        "greeting": "Good morning",
        "subheading": "Today",
        "kpis": [{"label": "Appointments", "value": "18"}],
        "style": {"archetype": "operations-dashboard", "density": "normal"},
    })


# ── the two-stage contract ───────────────────────────────────────────────

def test_a_confirmed_claim_rejects_the_candidate():
    verdict = _review(_routed_chat(
        judge=_resp(APPROVING_JUDGE),
        inspector=_resp(ONE_CLAIM),
        verifier=_resp('{"verdict": "confirmed", "reason": "both cards identical at the named spot"}'),
    ))
    assert verdict["approved"] is False
    assert verdict["defects"]["confirmed"][0]["kind"] == "duplicated_panel"
    assert any("structural defect" in i for i in verdict["issues"])
    assert verdict["score"] == 9.0, "the aesthetic score is reported honestly, not zeroed"


def test_a_refuted_claim_rejects_nothing():
    """The 16 refuted claims of session 33, as a pin: inspector noise must
    cost nothing but the verifier call that killed it."""
    verdict = _review(_routed_chat(
        judge=_resp(APPROVING_JUDGE),
        inspector=_resp(ONE_CLAIM),
        verifier=_resp('{"verdict": "refuted", "reason": "the two cards differ in title and rows"}'),
    ))
    assert verdict["approved"] is True
    assert verdict["defects"] == {"claims": 1, "confirmed": []}


def test_a_clean_report_spends_no_verifier_calls():
    verifier_calls = []
    fake = _routed_chat(
        judge=_resp(APPROVING_JUDGE),
        inspector=_resp('{"defects": []}'),
        verifier=verifier_calls,  # popping from an empty list would raise
    )
    verdict = _review(fake)
    assert verdict["approved"] is True
    assert verdict["defects"] == {"claims": 0, "confirmed": []}


def test_off_rubric_and_text_claims_die_before_the_verifier():
    """The inspector rubric forbids text claims; a model that makes one
    anyway must not get it verified — text truth is text_truth.py's job."""
    result = defect_check.inspect_call.__wrapped__ if hasattr(defect_check.inspect_call, "__wrapped__") else None
    with patch.object(defect_check.provider, "chat", return_value=_resp(
        '{"defects": ['
        '{"kind": "misspelled_label", "where": "nav", "what": "Cilents"},'
        '{"kind": "clipping_or_truncation", "where": "right edge", "what": "card cut off"}'
        ']}'
    )):
        out = defect_check.inspect_call(VALID_PNG, _spec())
    assert [c["kind"] for c in out["claims"]] == ["clipping_or_truncation"]


def test_verifier_defaults_to_refuted_on_garbage_and_on_error():
    with patch.object(defect_check.provider, "chat", return_value=_resp("not json at all")):
        assert defect_check.verify_call(VALID_PNG, {"kind": "k", "where": "w", "what": "x"}, _spec())["confirmed"] is False
    with patch.object(defect_check.provider, "chat", side_effect=RuntimeError("down")):
        assert defect_check.verify_call(VALID_PNG, {"kind": "k", "where": "w", "what": "x"}, _spec())["confirmed"] is False
    with patch.object(defect_check.provider, "chat", return_value=_resp('{"verdict": "probably", "reason": ""}')):
        assert defect_check.verify_call(VALID_PNG, {"kind": "k", "where": "w", "what": "x"}, _spec())["confirmed"] is False


def test_an_inspector_outage_fails_open():
    verdict = _review(_routed_chat(
        judge=_resp(APPROVING_JUDGE),
        inspector=RuntimeError("inspector down"),
    ))
    assert verdict["approved"] is True
    assert verdict["defects"] == {"claims": 0, "confirmed": []}


def test_the_check_only_subtracts_never_rescues():
    """A screen the judge rejected stays rejected however clean the
    inspector found it."""
    verdict = _review(_routed_chat(
        judge=_resp('{"score": 3.0, "issues": ["mess"], "approved": false}'),
        inspector=_resp('{"defects": []}'),
    ))
    assert verdict["approved"] is False


def test_best_effort_prefers_a_clean_screen_over_a_prettier_defective_one(dental_spec):
    """Request 77, replayed as a pin: every candidate rejected, one carries
    a confirmed floating backdrop at 8.1, the regeneration is clean at 7.8.
    The clean one ships — a prospect notices the defect, not the 0.3."""
    responses = iter([
        {"score": 8.1, "issues": [], "approved": False,
         "defects": {"claims": 1, "confirmed": [{"kind": "non_app_chrome", "where": "all", "what": "floating"}]}},
        {"score": 7.8, "issues": [], "approved": False,
         "defects": {"claims": 0, "confirmed": []}},
    ])

    with patch.object(images_mod.provider, "generate_image", return_value={"image_bytes": VALID_PNG, "usage": None}), \
         patch.object(images_mod.qa, "review_image", side_effect=lambda *a, **k: next(responses)), \
         patch.object(images_mod, "log_usage"), \
         patch.object(images_mod.settings, "MAX_REGENERATIONS", 1):
        selected, scored = images_mod._render_screen(
            _FakeDb(), 1, dental_spec, [{"prompt": "p", "variant_id": None, "model": "m"}],
            "v", reference_images=None,
        )

    assert len(scored) == 2
    assert selected["verdict"]["score"] == 7.8, "the defect-free candidate ships"


# ── the concurrency that pays for it ─────────────────────────────────────

def test_the_three_instruments_fire_concurrently():
    """Each instrument's fake blocks until all three have STARTED. If
    review_image ran them serially, the first would wait forever — the
    barrier converts 'accidentally serial again' into a loud timeout
    instead of a silently slower request path."""
    barrier = threading.Barrier(3, timeout=10)

    def _blocking(resp):
        def _f(*a, **k):
            barrier.wait()
            return resp
        return _f

    routes = {
        "product design director": _blocking(_resp(APPROVING_JUDGE)),
        "transcribe the misspelling": _blocking(_resp('{"text": [], "uncertain": []}')),
        "meticulous QA inspector": _blocking(_resp('{"defects": []}')),
    }

    def _fake(model, messages, **kwargs):
        content = messages[0]["content"]
        text = content[0]["text"] if isinstance(content, list) else content
        for marker, fn in routes.items():
            if marker in text:
                return fn()
        raise AssertionError(f"unrouted: {text[:60]}")

    with patch.object(qa.provider, "chat", side_effect=_fake), \
         patch.object(qa, "log_usage"), \
         patch.object(qa.settings, "ENABLE_TEXT_TRUTH_GATE", True), \
         patch.object(qa.settings, "ENABLE_DEFECT_CHECK", True):
        verdict = qa.review_image(_FakeDb(), 1, VALID_PNG, _spec())
    # Reaching here at all is the pin — serial instruments deadlock on the
    # barrier. (approved is False here because an empty transcript rightly
    # fails the text gate; that behaviour has its own pin in
    # test_text_truth.py and is not this test's subject.)
    assert verdict["score"] == 9.0
    assert verdict["defects"] == {"claims": 0, "confirmed": []}


def test_followup_screens_run_in_parallel_on_their_own_sessions(dental_spec):
    """Two follow-ups, each generation blocking until BOTH have started —
    serial screens would deadlock. And each screen's DB writes go to a
    session opened by its own worker, never the caller's."""
    barrier = threading.Barrier(2, timeout=10)
    sessions_seen = []

    def fake_generate(prompt, *, model=None, reference_images=None, **_):
        if reference_images is not None or True:
            pass
        # only follow-up calls block; the anchor generates alone first
        if fake_generate.anchor_done:
            barrier.wait()
        return {"image_bytes": VALID_PNG, "usage": None}
    fake_generate.anchor_done = False

    def fake_review(db, request_id, image_bytes, spec):
        sessions_seen.append((spec.product.screen_type, id(db)))
        return {"score": 9.0, "issues": [], "approved": True}

    specs = []
    for screen_type in ("dashboard", "patients", "analytics"):
        spec = dental_spec.model_copy(deep=True)
        spec.product.screen_type = screen_type
        specs.append(spec)

    caller_db = _FakeDb()
    with patch.object(images_mod.provider, "generate_image", side_effect=fake_generate), \
         patch.object(images_mod.qa, "review_image", side_effect=fake_review), \
         patch.object(images_mod, "log_usage"), \
         patch.object(images_mod, "_save_selected", side_effect=lambda db, *a, **k: db):
        # flip the flag once the anchor screen is done: generate_demo_screens
        # renders the anchor before any follow-up, so wrap _render_screen
        original = images_mod._render_screen

        def tracking_render(db, request_id, spec, *args, **kwargs):
            result = original(db, request_id, spec, *args, **kwargs)
            fake_generate.anchor_done = True
            return result

        with patch.object(images_mod, "_render_screen", side_effect=tracking_render):
            rows = images_mod.generate_demo_screens(caller_db, 1, "operations-dashboard", specs)

    assert len(rows) == 3
    by_screen = dict(sessions_seen)
    assert by_screen["patients"] != id(caller_db), "follow-up ran on the caller's session"
    assert by_screen["analytics"] != id(caller_db)
    assert by_screen["patients"] != by_screen["analytics"], "follow-ups shared one session"
    assert by_screen["dashboard"] == id(caller_db), "the anchor stays on the caller's session"


# ── self-refuting claims die in code, not at the verifier (session 36) ───
# Request 84: the inspector claimed ticks 0, 15, 30, 45, 60, 75, 90 were
# "not evenly stepped" and the verifier CONFIRMED it while its own reason
# restated the even 15-step — an LLM cannot be trusted with arithmetic
# about text it is quoting. The check is code now. Narrow on purpose:
# "stepped" claims only, and a non-numeric tick like '6+' keeps the claim.

def test_the_request_84_false_confirm_class_is_refuted_in_code():
    assert defect_check._claim_refutes_itself(
        "malformed_data_display",
        "The y-axis tick values (0, 15, 30, 45, 60, 75, 90) are not evenly "
        "stepped, despite being evenly spaced.",
    )


def test_a_genuinely_uneven_axis_still_reaches_the_verifier():
    # Request 90's real defect: steps of 300/400/500/600/500.
    assert not defect_check._claim_refutes_itself(
        "malformed_data_display",
        "The Y-axis tick values are unevenly stepped with the values 4800, "
        "4500, 4100, 3600, 3000, 2500, which are not evenly spaced at even intervals.",
    )
    # Request 98's real defect: 800/2000/1000/1800.
    assert not defect_check._claim_refutes_itself(
        "malformed_data_display",
        "The Y-axis tick labels are not evenly stepped at even spacing, "
        "showing 18200, 19000, 21000, 22000, 23800 for visually equal steps.",
    )


def test_a_six_plus_tick_keeps_its_claim_even_though_the_numbers_look_even():
    # Request 87: 0..5 then '6+' at the same visual interval — the values
    # alone are an even unit step; the '+' is the defect.
    assert not defect_check._claim_refutes_itself(
        "malformed_data_display",
        "The Y-axis has tick values 0, 1, 2, 3, 4, 5, followed by '6+' at "
        "the same visual interval as the other single-unit steps, making "
        "the axis unevenly stepped.",
    )


def test_geometry_claims_are_never_second_guessed_by_arithmetic():
    # Request 87 analytics: misaligned markers — a claim about pixels, not
    # about the quoted numbers; quoted values cannot refute it.
    assert not defect_check._claim_refutes_itself(
        "malformed_data_display",
        "The data points are not consistently aligned with their tick marks; "
        "the marker for Wk 1 is shifted left of the Wk 1 label at values 10, 20, 30.",
    )


def test_inspect_call_drops_the_self_refuting_claim_before_it_costs_a_verifier():
    import json

    body = {
        "choices": [{"message": {"content": json.dumps({
            "defects": [
                {"kind": "malformed_data_display", "where": "y-axis",
                 "what": "Tick values 0, 15, 30, 45, 60, 75, 90 are not evenly stepped."},
                {"kind": "duplicated_panel", "where": "header",
                 "what": "The Confirm button appears twice."},
            ],
        })}}],
        "usage": {},
    }
    from app.ui_spec import UIDemoSpec
    with patch.object(defect_check.provider, "chat", return_value=body):
        result = defect_check.inspect_call(VALID_PNG, UIDemoSpec.model_validate({}))
    kinds = [c["kind"] for c in result["claims"]]
    assert kinds == ["duplicated_panel"], "the arithmetic-refuted claim must die before the verifier"
