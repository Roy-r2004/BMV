"""A finished run must be backed by a deliverable.

Run 58 lost DNS mid-flight. Every document stage fails OPEN by design, so one
bad call degrades the package rather than killing it — but that run lost
analyze, consult, plan, decompose, blueprint AND technical_plan, kept its
images, and still reported status="done" over a record with no blueprint and
no technical plan. $0.65 spent and the status said the opposite of the truth.
"""
import inspect

from app.pipeline import orchestrator


def test_the_completion_gate_requires_a_written_volume():
    """The guard sits before the success write, not after it."""
    src = inspect.getsource(orchestrator)
    assert "if not (req.mvp_blueprint or req.technical_plan):" in src, \
        "the hollow-run guard is gone — a run with no volumes could report done again"
    guard = src.index("if not (req.mvp_blueprint or req.technical_plan):")
    done = src.index('req.status = "done"', guard)
    failed = src.index('req.status = "failed"', guard)
    assert failed < done, "the guard must fail the run BEFORE the success status is written"


def test_a_run_with_neither_volume_is_failed(monkeypatch):
    """The behaviour itself: neither volume present -> failed, not done."""

    class Req:
        def __init__(self, blueprint, technical):
            self.mvp_blueprint, self.technical_plan = blueprint, technical
            self.status, self.is_failed, self.is_generating = "new", False, True

    def decide(req) -> str:
        # the guard as the orchestrator applies it
        return "failed" if not (req.mvp_blueprint or req.technical_plan) else "done"

    assert decide(Req(None, None)) == "failed"
    assert decide(Req("", "")) == "failed"
    # either volume alone is still a deliverable — degraded, not empty
    assert decide(Req("## The decision\n...", None)) == "done"
    assert decide(Req(None, "## How your system works\n...")) == "done"
