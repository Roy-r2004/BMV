"""C23 benchmark, replay: a recorded run re-checked with no provider behind it.

A real benchmark run costs money and cannot be repeated for every commit. What
CAN be repeated is the checking: `RecordingProvider` writes every response to a
cassette keyed by `prompt_hash()`, and replaying that cassette re-runs the whole
engagement - the same registry, the same bundle, the same assertions - for
nothing.

Two laws matter here and both are pinned below:

  * a replay is the same run, not a similar one. If the bundle digest moved
    between recording and replay, a cassette would be a souvenir rather than
    evidence, and the real-run acceptance evidence would be unreproducible.
  * a miss is an error, never an invention. `RecordingProvider` with no inner
    provider returns an error response for a prompt it never recorded, which
    the engine treats like any outage; nothing is fabricated to fill the hole.
    A bumped `schema_version` is deliberately a miss (S10): a recording made
    for one output shape must never be validated against another.
"""
from __future__ import annotations

import os

import pytest

from app.engine.benchmark import assertions as A
from app.engine.benchmark import cases as C
from app.engine.benchmark import harness as H
from app.engine.benchmark.oracle import structural_oracle
from app.engine.llm import FakeProvider, ModelCall, RecordingProvider

import app.engine.methods.builtin  # noqa: F401  - registration by import

CASE_ID = "adv-regulated-question"


@pytest.fixture(scope="module")
def case():
    return C.load_case(CASE_ID)


@pytest.fixture(scope="module")
def cassette(tmp_path_factory, case):
    """One recorded run. The inner provider is the structural oracle, so the
    recording is free; what is being tested is the record/replay path, which is
    the same one a paid run uses."""
    path = str(tmp_path_factory.mktemp("cassettes") / "run.json")
    recorder = RecordingProvider(FakeProvider(oracle=structural_oracle), path)
    bundle = H.run_case(case, recorder)
    return path, bundle, recorder


def test_a_replayed_run_is_the_same_run(cassette, case):
    path, recorded, recorder = cassette
    assert recorder.misses > 0 and os.path.exists(path)
    replayed = H.run_case(case, RecordingProvider(None, path))
    assert replayed.digest() == recorded.digest()


def test_the_assertions_pass_from_the_cassette_alone(cassette, case):
    path, _recorded, _recorder = cassette
    replayed = H.run_case(case, RecordingProvider(None, path))
    failures = A.adversarial_failures(replayed, case)
    assert failures == [], "\n".join(failures)


def test_replay_places_no_call_of_its_own(cassette, case):
    path, recorded, _recorder = cassette
    player = RecordingProvider(None, path)
    H.run_case(case, player)
    assert player.hits > 0
    # Every prompt the replay issued was one the recording holds: a miss would
    # be an outage the engine reported, and the bundle would differ.
    assert player.misses == 0


def test_a_cassette_miss_is_an_error_and_never_an_invention(cassette):
    path, _recorded, _recorder = cassette
    player = RecordingProvider(None, path)
    call = ModelCall(purpose="extract_turn",
                     messages=({"role": "user", "content": "a prompt nobody recorded"},))
    response = player.complete(call)
    assert response.text is None
    assert response.error is not None and "cassette miss" in response.error


def test_a_bumped_schema_version_is_a_miss(cassette, case):
    """S10: a recording is replayed only against the exact output shape it was
    made for. Without this, a widened schema would silently reuse answers that
    were never validated against it."""
    path, _recorded, _recorder = cassette
    player = RecordingProvider(None, path)
    recorded_prompt = None
    for key, entries in player._entries.items():                      # noqa: SLF001 - the shape under test
        if entries:
            recorded_prompt = key
            break
    assert recorded_prompt is not None
    original = ModelCall(purpose="extract_turn",
                         messages=({"role": "user", "content": "anything"},), schema_version=1)
    bumped = ModelCall(purpose="extract_turn",
                       messages=({"role": "user", "content": "anything"},), schema_version=2)
    assert original.prompt_hash() != bumped.prompt_hash()
