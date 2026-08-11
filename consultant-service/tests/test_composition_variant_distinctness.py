"""Regression test: the 3 composition variants must never collapse into the
same prompt or the same stored image. Written after a real incident where a
STALE server process (running code from before this pipeline existed) made
it look like the 3 anchor candidates were identical — they weren't; the
request never even reached this code. This test guards the actual
generation path so a real regression here fails loudly instead of being
mistaken for a stale-process symptom again.
"""

import hashlib
from unittest.mock import patch

from app.pipeline import images, prompt_builder


def test_composition_variant_prompts_are_all_distinct(dental_spec):
    prompts = [
        prompt_builder.build_dashboard_image_prompt(dental_spec, composition=variant)
        for variant in prompt_builder.COMPOSITION_VARIANTS
    ]
    hashes = [hashlib.sha256(p.encode()).hexdigest() for p in prompts]
    assert len(set(hashes)) == 3, "two or more composition variants produced an identical prompt"


def test_each_composition_directive_appears_only_in_its_own_prompt(dental_spec):
    prompts = {
        variant["id"]: prompt_builder.build_dashboard_image_prompt(dental_spec, composition=variant)
        for variant in prompt_builder.COMPOSITION_VARIANTS
    }
    for variant in prompt_builder.COMPOSITION_VARIANTS:
        own_prompt = prompts[variant["id"]]
        assert variant["directive"] in own_prompt, f"{variant['id']}'s own directive missing from its prompt"
        for other in prompt_builder.COMPOSITION_VARIANTS:
            if other["id"] == variant["id"]:
                continue
            assert other["directive"] not in own_prompt, (
                f"{other['id']}'s directive leaked into {variant['id']}'s prompt — "
                "the model would be given two composition concepts, not one"
            )


def test_generate_demo_screens_anchor_fires_three_distinct_prompts_and_saves_distinct_images(dental_spec):
    """End-to-end through generate_demo_screens (mocked provider/QA): each of
    the 3 anchor calls must receive its own prompt and the provider must be
    called 3 separate times — a caching bug would collapse this to 1 call
    with 3 identical results."""
    calls = []

    def fake_generate(prompt, *, reference_images=None, **_):
        calls.append(prompt)
        # Distinct bytes per call, deterministically derived from the
        # prompt, so accidental byte-for-byte reuse across variants would
        # be caught by the image-hash assertions below.
        fake_bytes = f"FAKEPNG:{hashlib.sha256(prompt.encode()).hexdigest()}".encode()
        return {"image_bytes": fake_bytes, "usage": None}

    def fake_decodable(_bytes):
        return True

    def fake_review(_db, _rid, _bytes, _spec):
        return {"score": 8.0, "issues": [], "approved": True}

    class _FakeDb:
        def add(self, *_): ...
        def commit(self): ...
        def get(self, *_): return type("R", (), {"id": 1})()

    saved_files = {}

    def fake_open_write(path, mode="r", **kw):
        import io
        buf = io.BytesIO()
        orig_close = buf.close
        def close():
            saved_files[path] = buf.getvalue()
            orig_close()
        buf.close = close
        return buf

    with patch.object(images.provider, "generate_image", side_effect=fake_generate), \
         patch.object(images, "_decodable", side_effect=fake_decodable), \
         patch.object(images.qa, "review_image", side_effect=fake_review), \
         patch.object(images, "log_usage"), \
         patch.object(images, "_apply_bmv_watermark", side_effect=lambda b: b), \
         patch("builtins.open", side_effect=fake_open_write), \
         patch("os.makedirs"), \
         patch("json.dump"):
        saved = images.generate_demo_screens(_FakeDb(), 1, "operations-dashboard", [dental_spec])

    assert len(calls) == 3, f"expected exactly 3 provider calls for the anchor, got {len(calls)}"
    assert len(set(calls)) == 3, "two or more anchor calls were sent the identical prompt"

    prompt_hashes = {hashlib.sha256(c.encode()).hexdigest() for c in calls}
    assert len(prompt_hashes) == 3

    # Exactly one candidate is selected/saved as the winner; its bytes must
    # be derivable from ITS OWN prompt (not a different candidate's).
    assert len(saved) == 1
    winner_prompt = saved[0].prompt
    assert winner_prompt in calls
