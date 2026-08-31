"""app/engine/benchmark/__main__.py - the costed benchmark runner (design 19).

    python -m app.engine.benchmark --case <id> --model <slug> --max-usd 3 \
        --out uploads/benchmarks/<case>/<ts>/

Three modes, and which one is running is always printed:

  fake     (default) the structural oracle. Free, deterministic, no network.
  real     --model names a paid model. Every call is recorded to a cassette in
           the output directory, so the run can be replayed later for nothing.
  replay   --replay <cassette> re-runs from a recording with no provider behind
           it. A miss is an error response, never an invention (RecordingProvider).

Money is spent only after a credit probe: one deliberately tiny call, placed
before the engagement starts, whose failure ends the run at a cost of one call
rather than forty. `--max-usd` is a ceiling `CountingProvider` enforces before
each call, not a report printed after the money is gone.

Output goes under `uploads/benchmarks/` (gitignored, MF3.3): the bundle, the
assertion report and the cassette. Nothing is written into the repository.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Sequence

from app.engine.benchmark import assertions as assertions_mod
from app.engine.benchmark import cases as cases_mod
from app.engine.benchmark.harness import BudgetExceeded, Bundle, run_case
from app.engine.benchmark.oracle import structural_oracle
from app.engine.llm import FakeProvider, ModelCall, ModelProvider, OpenRouterProvider, RecordingProvider

# The three modes, named once. A branch that compared against a literal would
# be a string deciding control flow inside app/engine, which the universality
# whitelist law (design 18.2) forbids wherever it appears.
MODE_FAKE = "fake"
MODE_REAL = "real"
MODE_REPLAY = "replay"
ENTRY_POINT = "__main__"

CASSETTE_NAME = "cassette.json"
BUNDLE_NAME = "bundle.json"
REPORT_NAME = "report.json"
PROBE_PURPOSE = "bench:credit_probe"


def _uploads_root() -> str:
    try:
        from app.config import settings
        return str(settings.UPLOADS_DIR)
    except Exception:                                      # pragma: no cover - settings optional
        return "uploads"


def _out_dir(explicit: str | None, case_id: str) -> str:
    if explicit:
        return explicit
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return os.path.join(_uploads_root(), "benchmarks", case_id, stamp)


def credit_probe(provider: ModelProvider, model: str | None) -> str | None:
    """One minimal call before the engagement. Returns the error, or None.

    The point is the size: a run that cannot buy ten tokens must not be allowed
    to discover that on its fortieth call, having spent the client's money on a
    transcript nobody will read."""
    call = ModelCall(purpose=PROBE_PURPOSE, messages=({"role": "user", "content": "ok"},),
                     model=model, max_tokens=8)
    response = provider.complete(call)
    if response.error is not None:
        return response.error
    if not response.text:
        return "the probe returned no text"
    return None


def _provider(args: argparse.Namespace, out_dir: str) -> tuple[ModelProvider, str]:
    if args.replay:
        return RecordingProvider(None, args.replay), MODE_REPLAY
    if args.model:
        inner = OpenRouterProvider(default_model=args.model)
        return RecordingProvider(inner, os.path.join(out_dir, CASSETTE_NAME)), MODE_REAL
    return FakeProvider(oracle=structural_oracle), MODE_FAKE


def _report(bundle: Bundle, case: cases_mod.LoadedCase) -> dict[str, Any]:
    return {
        "case": case.id,
        "adversarial": case.adversarial,
        "checks": list(case.keys.checks),
        "failures": assertions_mod.adversarial_failures(bundle, case),
        "revealed_changers": bundle.revealed_changers,
        "release_status": bundle.release_status,
        "model_calls": bundle.model_calls,
        "cost_usd": bundle.cost_usd,
    }


def _write(directory: str, name: str, payload: Any) -> str:
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True, ensure_ascii=False)
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.engine.benchmark")
    parser.add_argument("--case", action="append", default=[],
                        help="case id; repeatable. Omit for every case in the directory.")
    parser.add_argument("--model", default=None, help="model slug; omit to run the structural oracle")
    parser.add_argument("--max-usd", type=float, default=None, dest="max_usd",
                        help="ceiling enforced before each call")
    parser.add_argument("--out", default=None, help="output directory (default uploads/benchmarks/<case>/<ts>)")
    parser.add_argument("--replay", default=None, help="cassette to replay, with no provider behind it")
    parser.add_argument("--dir", default=None, help="benchmark case directory")
    args = parser.parse_args(argv)

    ids = args.case or list(cases_mod.case_ids(args.dir))
    failures: list[str] = []
    for case_id in ids:
        case = cases_mod.load_case(case_id, args.dir)
        out_dir = _out_dir(args.out, case_id)
        provider, mode = _provider(args, out_dir)
        print(f"[{case_id}] mode={mode} model={args.model or '-'} out={out_dir}")

        if mode == MODE_REAL:
            error = credit_probe(provider, args.model)
            if error:
                print(f"[{case_id}] credit probe failed, nothing spent: {error}", file=sys.stderr)
                return 2

        try:
            bundle = run_case(case, provider, max_usd=args.max_usd, model=args.model)
        except BudgetExceeded as exc:
            print(f"[{case_id}] stopped at the ceiling: {exc}", file=sys.stderr)
            return 3

        _write(out_dir, BUNDLE_NAME, bundle.as_dict())
        report = _report(bundle, case)
        _write(out_dir, REPORT_NAME, report)
        failures.extend(report["failures"])
        print(f"[{case_id}] calls={bundle.model_calls} cost={bundle.cost_usd} "
              f"release={bundle.release_status} failures={len(report['failures'])}")

    if failures:
        print(f"{len(failures)} adversarial failures", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        return 1
    return 0


if __name__ == ENTRY_POINT:                                # pragma: no cover - entry point
    raise SystemExit(main())
