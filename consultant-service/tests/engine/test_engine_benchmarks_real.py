"""C23 benchmark, real mode: the costed run, skipped unless asked for.

The structural oracle proves the deterministic core reacts to input. It cannot
prove the questions are good, that the central decision is the right one, or
that a regulated matter was correctly identified - those are model judgements,
and only a paid run is evidence about them (design 17.5, risk 3 and risk 5).

So this file is skipped unless ENGINE_BENCHMARK_REAL=1 is set, and even then it
runs ONE case under a --max-usd ceiling and records a cassette, so the same
transcript can be re-checked afterwards for nothing
(`test_engine_benchmarks_replay.py`). The credit probe runs first: a run that
cannot buy ten tokens should discover that on its first call, not its fortieth.

    ENGINE_BENCHMARK_REAL=1 ENGINE_BENCHMARK_MODEL=<slug> \
      ./.venv/Scripts/python.exe -m pytest tests/engine/test_engine_benchmarks_real.py -q
"""
from __future__ import annotations

import os

import pytest

from app.engine.benchmark import __main__ as cli
from app.engine.benchmark import assertions as A
from app.engine.benchmark import cases as C
from app.engine.benchmark import harness as H
from app.engine.llm import OpenRouterProvider, RecordingProvider

import app.engine.methods.builtin  # noqa: F401  - registration by import

ENABLED = os.environ.get("ENGINE_BENCHMARK_REAL") == "1"
CASE_ID = os.environ.get("ENGINE_BENCHMARK_CASE", "adv-regulated-question")
MODEL = os.environ.get("ENGINE_BENCHMARK_MODEL") or None
MAX_USD = float(os.environ.get("ENGINE_BENCHMARK_MAX_USD", "3"))

pytestmark = pytest.mark.skipif(
    not ENABLED, reason="real-model benchmark costs money; set ENGINE_BENCHMARK_REAL=1 to run it")


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    """One paid run, behind the credit probe and the ceiling."""
    case = C.load_case(CASE_ID)
    path = str(tmp_path_factory.mktemp("real") / "cassette.json")
    provider = RecordingProvider(OpenRouterProvider(default_model=MODEL), path)
    error = cli.credit_probe(provider, MODEL)
    if error:
        pytest.skip(f"credit probe failed, nothing spent: {error}")
    bundle = H.run_case(case, provider, client_provider=provider, model=MODEL, max_usd=MAX_USD)
    return case, bundle, path


def test_the_real_run_stays_inside_its_ceiling(recorded):
    _case, bundle, _path = recorded
    assert bundle.cost_usd <= MAX_USD
    assert bundle.model_calls > 0


def test_the_real_run_holds_the_same_laws(recorded):
    case, bundle, _path = recorded
    failures = A.adversarial_failures(bundle, case)
    assert failures == [], "\n".join(failures)


def test_the_real_run_left_a_cassette_to_recheck(recorded):
    _case, _bundle, path = recorded
    assert os.path.exists(path) and os.path.getsize(path) > 0


def test_the_skip_is_the_default():
    """The guard itself: without the environment variable this file spends
    nothing. A benchmark that quietly billed a test run would be found out by
    the invoice, not by the suite."""
    assert ENABLED is (os.environ.get("ENGINE_BENCHMARK_REAL") == "1")
