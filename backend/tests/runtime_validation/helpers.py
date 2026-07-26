from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.application.candidate_generation.service import (
    build_v2_candidate_revision,
)
from app.application.runtime_validation.service import (
    validate_v2_candidate_runtime,
)
from app.core.config import settings
from app.domain.models import CandidateRevisionRecord
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.candidate_generation.helpers import (
    CandidateFixtureAI,
    PreparedPhase3A,
    prepare_phase3a,
)


@dataclass(frozen=True)
class PreparedRuntimeCandidate:
    prepared: PreparedPhase3A
    phase3b_result: dict
    revision: CandidateRevisionRecord
    candidate_path: Path
    fixture_ai: CandidateFixtureAI


@pytest.fixture
def isolated_runtime_paths(monkeypatch):
    token = uuid.uuid4().hex
    root = Path(__file__).resolve().parent / ".runtime" / token
    # Keep validations outside PREVIEW_TEMPLATE_DIR so module resolution
    # cannot accidentally walk up into template node_modules (prod layout).
    validations = root / "runtime-validation"
    monkeypatch.setattr(
        settings,
        "PREVIEW_CANDIDATES_DIR",
        root / "candidates",
    )
    monkeypatch.setattr(
        settings,
        "PREVIEW_APPS_DIR",
        root / "accepted",
    )
    monkeypatch.setattr(
        settings,
        "PREVIEW_VALIDATIONS_DIR",
        validations,
    )
    monkeypatch.setattr(
        settings,
        "V2_RUNTIME_VALIDATION_ENABLED",
        True,
    )
    monkeypatch.setattr(settings, "PREVIEW_GENERATOR_V2", True)
    yield root, validations
    for path in (root, validations):
        if path.exists():
            shutil.rmtree(path)


def prepare_runtime_candidate(
    *,
    request_id: int = 1801,
) -> PreparedRuntimeCandidate:
    prepared = prepare_phase3a(request_id=request_id)
    ai = CandidateFixtureAI()
    phase3b = build_v2_candidate_revision(
        prepared.db,
        prepared.req.id,
        ai,
        JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        req=prepared.req,
        phase3a_result=prepared.phase3a_result,
    )
    revision = (
        prepared.db.query(CandidateRevisionRecord)
        .filter(CandidateRevisionRecord.request_id == prepared.req.id)
        .order_by(CandidateRevisionRecord.id.desc())
        .first()
    )
    assert revision is not None and revision.workspace_relpath
    return PreparedRuntimeCandidate(
        prepared=prepared,
        phase3b_result=phase3b,
        revision=revision,
        candidate_path=(
            settings.PREVIEW_CANDIDATES_DIR / revision.workspace_relpath
        ),
        fixture_ai=ai,
    )


def run_phase4(prepared: PreparedRuntimeCandidate) -> dict:
    return validate_v2_candidate_runtime(
        prepared.prepared.db,
        prepared.prepared.req.id,
        req=prepared.prepared.req,
        phase3b_result=prepared.phase3b_result,
    )


__all__ = [
    "PreparedRuntimeCandidate",
    "isolated_runtime_paths",
    "prepare_runtime_candidate",
    "run_phase4",
]
