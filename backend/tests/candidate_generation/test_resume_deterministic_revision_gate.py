"""Regression: stale staging must not resume across deterministic builder bumps."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.application.candidate_generation.policy import (
    CANDIDATE_DETERMINISTIC_REVISION,
)
from app.application.candidate_generation.workspace import (
    _verified_resume,
)
from app.core.config import settings


def test_verified_resume_rejects_mismatched_deterministic_revision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    candidates = tmp_path / "candidates"
    monkeypatch.setattr(settings, "PREVIEW_CANDIDATES_DIR", candidates)
    staging = candidates / "9" / ".staging" / str(uuid.uuid4())
    staging.mkdir(parents=True)
    payload = {
        "request_id": 9,
        "revision_uuid": staging.name,
        "upstream_sha256": "a" * 64,
        "policy_revision": settings.V2_CANDIDATE_POLICY_REVISION,
        "deterministic_revision": "stale-revision",
        "completed_artifacts": {},
        "completed_stage_state": {
            "business_components": {"status": "completed"},
        },
        "candidate_call_ledger": {"events": [{"kind": "approved"}]},
        "candidate_provider_attempts": [{"attempt_id": "x"}],
    }
    (staging / ".attempt.json").write_text(json.dumps(payload), encoding="utf-8")
    assert (
        _verified_resume(
            staging,
            request_id=9,
            upstream_sha256="a" * 64,
        )
        is None
    )


def test_verified_resume_accepts_current_deterministic_revision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    candidates = tmp_path / "candidates"
    monkeypatch.setattr(settings, "PREVIEW_CANDIDATES_DIR", candidates)
    staging = candidates / "9" / ".staging" / str(uuid.uuid4())
    staging.mkdir(parents=True)
    payload = {
        "request_id": 9,
        "revision_uuid": staging.name,
        "upstream_sha256": "b" * 64,
        "policy_revision": settings.V2_CANDIDATE_POLICY_REVISION,
        "deterministic_revision": CANDIDATE_DETERMINISTIC_REVISION,
        "completed_artifacts": {},
        "completed_stage_state": {},
        "candidate_call_ledger": {},
        "candidate_provider_attempts": [],
    }
    (staging / ".attempt.json").write_text(json.dumps(payload), encoding="utf-8")
    resumed = _verified_resume(
        staging,
        request_id=9,
        upstream_sha256="b" * 64,
    )
    assert resumed is not None
    assert resumed.resumed is True
