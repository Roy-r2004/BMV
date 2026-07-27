"""Regression: stale deterministic cache rows must rebuild, not fail hard."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.application.candidate_generation.service import _load_deterministic_stage
from app.domain.schemas.preview_candidate import (
    CandidateArtifactManifest,
    CandidateFileDescriptor,
)

_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64
_HASH_D = "d" * 64


def _file(path: str, digest: str) -> CandidateFileDescriptor:
    return CandidateFileDescriptor(
        path=path,
        file_kind="runtime",
        owner_contract_ids=("foundation",),
        sha256=digest,
        byte_count=12,
    )


def _policy() -> SimpleNamespace:
    return SimpleNamespace(
        stage="foundation",
        prompt_revision="rev-test",
        model="deterministic",
        model_family="deterministic",
        provider="local",
        max_tokens=0,
        temperature=0.0,
        timeout_seconds=0,
        ai_authored=False,
        policy_revision="policy-test",
    )


def _row(*, row_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=row_id,
        cacheable=True,
        artifact_kind="foundation",
        provider="local",
        provider_call_count=0,
        repair_call_count=0,
        repair_reason=None,
        transport_retry_count=0,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        cost_usd=0.0,
        latency_ms=1,
        prompt_revision="rev-test",
        effective_model="deterministic",
        model_family="deterministic",
    )


def test_stale_deterministic_cache_is_invalidated_and_rebuilt() -> None:
    stale_manifest = CandidateArtifactManifest(
        artifact_kind="foundation",
        input_hashes=(_HASH_A,),
        files=(_file("src/stale.tsx", _HASH_C),),
    )
    fresh_manifest = CandidateArtifactManifest(
        artifact_kind="foundation",
        input_hashes=(_HASH_B,),
        files=(_file("src/fresh.tsx", _HASH_D),),
    )
    assert stale_manifest != fresh_manifest

    row = _row(row_id=1)
    repository = MagicMock()
    repository.find_cache.return_value = row
    repository.load_cached.return_value = stale_manifest
    repository.db = MagicMock()
    source = SimpleNamespace(
        path="src/fresh.tsx",
        source="export {}",
        file_kind="runtime",
        owner_contract_ids=(),
    )
    context = SimpleNamespace(refs=SimpleNamespace(request_id=99))

    import app.application.candidate_generation.service as service_mod

    original_resolve = service_mod.resolve_candidate_stage_policy
    original_manifest = service_mod.source_manifest
    try:
        service_mod.resolve_candidate_stage_policy = lambda _kind: _policy()
        service_mod.source_manifest = lambda **_kwargs: fresh_manifest
        stage = _load_deterministic_stage(
            repository=repository,
            context=context,
            artifact_kind="foundation",
            sources=(source,),
            dependency_sha="dep",
            input_hashes=(_HASH_B,),
            parent_row=None,
        )
    finally:
        service_mod.resolve_candidate_stage_policy = original_resolve
        service_mod.source_manifest = original_manifest

    assert row.cacheable is False
    repository.db.flush.assert_called()
    assert stage.metrics.cache_hit is False
    assert stage.row is None
    assert stage.artifact == fresh_manifest


def test_matching_deterministic_cache_still_hits() -> None:
    manifest = CandidateArtifactManifest(
        artifact_kind="foundation",
        input_hashes=(_HASH_A,),
        files=(_file("src/main.tsx", _HASH_C),),
    )
    row = _row(row_id=2)
    repository = MagicMock()
    repository.find_cache.return_value = row
    repository.load_cached.return_value = manifest
    repository.db = MagicMock()
    source = SimpleNamespace(
        path="src/main.tsx",
        source="export {}",
        file_kind="runtime",
        owner_contract_ids=(),
    )
    context = SimpleNamespace(refs=SimpleNamespace(request_id=99))

    import app.application.candidate_generation.service as service_mod

    original_resolve = service_mod.resolve_candidate_stage_policy
    original_manifest = service_mod.source_manifest
    try:
        service_mod.resolve_candidate_stage_policy = lambda _kind: _policy()
        service_mod.source_manifest = lambda **_kwargs: manifest
        stage = _load_deterministic_stage(
            repository=repository,
            context=context,
            artifact_kind="foundation",
            sources=(source,),
            dependency_sha="dep",
            input_hashes=(_HASH_A,),
            parent_row=None,
        )
    finally:
        service_mod.resolve_candidate_stage_policy = original_resolve
        service_mod.source_manifest = original_manifest

    assert row.cacheable is True
    assert stage.metrics.cache_hit is True
    assert stage.row is row
