"""Pins the owner's rule (session 35): every generation is a customer run.

Golden-brief cells used to skip the six text stages and replay a frozen
UIDemoSpec into `generate_demo_screens`, writing outside UPLOADS_DIR. That
made the evaluation rig measure something no customer could ever receive,
and it is why sessions 31-34 produced screens that never appeared at
/studio/<id>.

The rule now: `scripts/bakeoff.py` submits the brief's INTAKE and calls
`orchestrator.run` — the identical entry point `POST /api/requests` hands
to its background thread. The frozen path survives only behind an explicit
--frozen-specs flag, for reproducing a historical cell.

These tests spend nothing: the orchestrator is stubbed, so what is pinned
is which path the runner takes, not what a model returns.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import GeneratedImage, Request


@pytest.fixture
def rig(tmp_path, monkeypatch):
    """Runs bakeoff.main() against a stubbed orchestrator and a scratch
    results file, and reports which path it took."""
    import scripts.bakeoff as bakeoff

    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(bakeoff, "OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(bakeoff, "RESULTS_PATH", str(tmp_path / "out" / "results.json"))
    # bakeoff is a one-shot process and writes its cell's condition straight
    # onto `settings`. Under pytest that same object outlives the test, so
    # every knob it can touch is restored here — an earlier version of this
    # fixture leaked IMAGE_MODEL_ANCHOR and took nine unrelated tests with it.
    for name in (
        "UPLOADS_DIR", "IMAGE_MODEL_ANCHOR", "IMAGE_MODEL_FOLLOWUP", "ENABLE_ART_PACKS",
        "IMAGE_REGISTER", "WATERMARK_STYLE", "DASHBOARD_CANDIDATES", "SECONDARY_CANDIDATES",
        "USE_DESIGN_SHEET", "DEMO_SCREEN_COUNT",
    ):
        monkeypatch.setattr(settings, name, getattr(settings, name))
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path / "uploads"))

    calls: dict = {"orchestrator": [], "frozen": []}

    def fake_run(request_id: int) -> None:
        calls["orchestrator"].append(request_id)
        db = SessionLocal()
        db.add(GeneratedImage(
            request_id=request_id, role_id="dashboard", role_label="Dashboard", variant=0,
            file_path=f"/uploads/images/{request_id}/dashboard_0.png", prompt="p",
            screen_type="dashboard", model="google/gemini-3-pro-image", qa_score=8.5,
        ))
        req = db.get(Request, request_id)
        req.status, req.is_generating, req.concept_name = "done", False, "SmileBright Operations"
        db.commit()
        db.close()

    def fake_frozen(db, request_id, archetype_id, specs, **kwargs):
        calls["frozen"].append(request_id)
        return []

    from app.pipeline import orchestrator
    from app.pipeline import images as images_stage

    monkeypatch.setattr(orchestrator, "run", fake_run)
    monkeypatch.setattr(images_stage, "generate_demo_screens", fake_frozen)

    def run(*argv: str):
        monkeypatch.setattr(sys, "argv", ["bakeoff.py", *argv])
        bakeoff.main()
        with open(bakeoff.RESULTS_PATH, encoding="utf-8") as f:
            return calls, json.load(f)[-1]

    return run


def test_a_cell_runs_the_same_entry_point_the_public_route_does(rig):
    calls, row = rig("--brief", "dental", "--model", "google/gemini-3-pro-image")

    assert calls["orchestrator"], "a cell must go through orchestrator.run, not straight to the image stage"
    assert not calls["frozen"], "the frozen replay must not run without --frozen-specs"
    assert row["pipeline"] == "full"


def test_a_full_cell_lands_under_uploads_so_the_customer_can_open_it(rig):
    """The whole point: /studio/<id> has to be able to serve these bytes."""
    before = settings.UPLOADS_DIR
    calls, row = rig("--brief", "law", "--model", "google/gemini-3-pro-image")

    assert settings.UPLOADS_DIR == before, "a full run must never redirect UPLOADS_DIR"
    assert row["screens"][0]["file_path"].startswith("/uploads/images/")


def test_a_full_cell_moves_through_the_states_the_route_drives(rig):
    calls, row = rig("--brief", "retail", "--model", "google/gemini-3-pro-image")

    request_id = calls["orchestrator"][-1]
    db = SessionLocal()
    req = db.get(Request, request_id)
    # Started as a real request would, and finished where the orchestrator left it.
    assert req.email == "bakeoff@example.com"
    assert req.status == "done" and req.is_generating is False
    db.close()
    assert row["status"] == "done"
    assert row["concept_name"] == "SmileBright Operations"


def test_a_full_cell_checkpoints_the_wal_so_the_studio_service_can_see_it(rig):
    """The DB is shared across containers on a bind mount, where a
    long-lived reader's WAL-index view goes stale: /studio/91 404'd in
    session 36 while its row sat in the WAL. A cell hands its run over by
    checkpointing on the way out — when bakeoff exits, the run must be in
    the MAIN file, not only in a journal other processes may miss."""
    rig("--brief", "dental", "--model", "google/gemini-3-pro-image", "--label", "ckpt")

    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    wal = db_path + "-wal"
    assert (not os.path.exists(wal)) or os.path.getsize(wal) == 0, (
        "bakeoff exited with frames still in the WAL — the studio service "
        "may not see this run"
    )


def test_the_frozen_replay_still_exists_but_only_when_asked_for(rig):
    """Sessions 31-34 were all measured this way; a past cell stays checkable."""
    calls, row = rig("--brief", "dental", "--model", "google/gemini-3-pro-image",
                     "--label", "replay", "--frozen-specs")

    assert calls["frozen"], "--frozen-specs must still replay the brief's specs"
    assert not calls["orchestrator"]
    assert row["pipeline"] == "frozen"


def test_a_frozen_replay_is_quarantined_from_the_real_uploads_dir(rig):
    """Its request ids are not unique across throwaway DBs — one cell
    overwriting another's screenshots has already cost a $0.353 result."""
    before = settings.UPLOADS_DIR
    rig("--brief", "law", "--model", "google/gemini-3-pro-image",
        "--label", "replay", "--frozen-specs")

    assert settings.UPLOADS_DIR != before
