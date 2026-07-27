from __future__ import annotations

import inspect
import shutil
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError

from app.application.visual_evaluation import service as phase5_service
from app.application.preview_app.pipeline import v2_contract
from app.application.visual_evaluation.baseline import blind_label_order
from app.application.visual_evaluation.cache import evaluation_cache_key
from app.application.visual_evaluation.evidence import (
    _group_by_route,
    _inspect_png,
)
from app.application.visual_evaluation.hard_gates import run_hard_gates
from app.application.visual_evaluation.policy import (
    acceptance_policy,
    resolve_model_capability,
    resolve_visual_routing,
    score_band_policy,
    visual_limits,
)
from app.application.visual_evaluation.scoring import (
    compute_acceptance,
    validate_critic_group,
)
from app.core.config import settings
from app.domain.schemas.visual_evaluation import (
    CandidateBaselineComparison,
    ImageBundleGroup,
    ModelCapabilityResolution,
    RefinementOutput,
    ScoreBandPolicy,
    ScreenshotVisualEvidence,
    VisualAcceptancePolicy,
    VisualDimensionAssessment,
    VisualEvaluationRefs,
    VisualEvidenceBundle,
    VisualHardGateReport,
    VisualReviewerDecision,
    VisualScorecard,
    VisualCallMetrics,
)
from app.infrastructure.db.base import Base
from tests.visual_evaluation.helpers import _dimension_rows


SHA_A = "a" * 64
SHA_B = "b" * 64


def _refs(screenshot_set: str = SHA_A):
    return VisualEvaluationRefs.model_construct(
        request_id=1,
        candidate_revision_id=1,
        candidate_revision_uuid="00000000-0000-0000-0000-000000000001",
        candidate_manifest_sha256=SHA_A,
        runtime_attempt_id=1,
        runtime_summary_id=1,
        runtime_summary_sha256=SHA_A,
        build_attempt_id=1,
        build_hash=SHA_A,
        screenshot_set_sha256=screenshot_set,
        design_contract_refs=None,
        page_purpose_sha256=SHA_A,
        business_component_plan_sha256=SHA_A,
        content_data_plan_sha256=SHA_A,
        interaction_contract_sha256=SHA_A,
        component_dependency_graph_sha256=SHA_A,
        visual_policy_revision="2026-07-24.1",
    )


def _evidence(
    *,
    index: int,
    page: str = "PAGE-ONE",
    route: str = "/one",
    viewport: str = "desktop",
    perceptual: str = SHA_A,
    structural: str = SHA_B,
    byte_count: int = 100,
) -> ScreenshotVisualEvidence:
    return ScreenshotVisualEvidence(
        evidence_id=f"VE-{index:03d}",
        page_id=page,
        route=route,
        viewport=viewport,
        relative_path=f"screens/{index}.png",
        sha256=f"{index:064x}",
        byte_count=byte_count,
        width=1440 if viewport == "desktop" else 390,
        height=900 if viewport == "desktop" else 844,
        mode="RGBA",
        alpha_opaque_ratio=1.0,
        luminance_mean=120,
        luminance_stddev=30,
        entropy=4.0,
        perceptual_sha256=perceptual,
        structural_sha256=structural,
        blank=False,
        transparent=False,
        materially_uniform=False,
    )


def _bundle(rows: tuple[ScreenshotVisualEvidence, ...]) -> VisualEvidenceBundle:
    group = ImageBundleGroup(
        group_index=0,
        page_ids=tuple(dict.fromkeys(item.page_id for item in rows)),
        evidence_ids=tuple(item.evidence_id for item in rows),
        image_count=len(rows),
        aggregate_image_bytes=sum(item.byte_count for item in rows),
        group_sha256=SHA_A,
    )
    return VisualEvidenceBundle(
        refs=_refs(),
        capture_policy_revision="2026-07-24.1",
        browser_version="fixture-chromium",
        ordered_screenshots=rows,
        grouping_manifest=(group,),
        ordered_screenshot_hashes=tuple(item.sha256 for item in rows),
        screenshot_set_sha256=SHA_A,
        cache_key=SHA_A,
    )


def _hard_gate(bundle: VisualEvidenceBundle) -> VisualHardGateReport:
    return VisualHardGateReport(
        refs=bundle.refs,
        cache_key=SHA_A,
        checks=("verified",),
        findings=(),
        passed=True,
    )


def _scorecard(
    bundle: VisualEvidenceBundle,
    *,
    score: int,
) -> VisualScorecard:
    rows = [
        item.model_dump(mode="json")
        for item in bundle.ordered_screenshots
    ]
    return VisualScorecard(
        actor="critic",
        subject="original",
        group_index=0,
        dimensions=tuple(
            VisualDimensionAssessment.model_validate(item)
            for item in _dimension_rows(rows, score=score)
        ),
        findings=(),
    )


def _reviewer(
    bundle: VisualEvidenceBundle,
    *,
    score: int,
    recommendation: str,
) -> VisualReviewerDecision:
    rows = [
        item.model_dump(mode="json")
        for item in bundle.ordered_screenshots
    ]
    return VisualReviewerDecision(
        subject="original",
        recommendation=recommendation,
        confidence=0.9,
        dimensions=tuple(
            VisualDimensionAssessment.model_validate(item)
            for item in _dimension_rows(rows, score=score)
        ),
        disagreements=(),
        blocking_findings=(),
        score_band_concerns=(),
        comparative_result="not_applicable",
        comparative_dimensions=(),
    )


def test_configured_models_resolve_multimodal_and_independent(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    routes = resolve_visual_routing()
    assert routes[0].capability.model == "openai/gpt-4o"
    assert routes[0].capability.capability == "multimodal_chat"
    assert routes[1].capability.model == "google/gemini-2.5-flash"
    assert routes[1].capability.capability == "multimodal_chat"
    assert routes[0].capability.family != routes[1].capability.family
    assert routes[3].capability.capability == "text_chat"


def test_unknown_or_non_multimodal_models_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    with pytest.raises(ValueError, match="Unknown Phase 5 capability"):
        resolve_model_capability(
            "unknown/vision-model",
            require_multimodal=True,
        )
    with pytest.raises(ValueError, match="not registered for multimodal"):
        resolve_model_capability(
            "deepseek/deepseek-v4-pro",
            require_multimodal=True,
        )


def test_economy_model_is_not_a_silent_fallback(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    monkeypatch.setattr(
        settings,
        "V2_VISUAL_CRITIC_MODEL",
        "unknown/unavailable",
    )
    monkeypatch.setattr(
        settings,
        "V2_VISUAL_ECONOMY_FALLBACK_ENABLED",
        False,
    )
    with pytest.raises(ValueError, match="Unknown Phase 5 capability"):
        resolve_visual_routing()


def test_scorecard_requires_exact_fourteen_dimensions() -> None:
    bundle = _bundle((_evidence(index=1),))
    payload = _scorecard(bundle, score=85).model_dump(mode="json")
    payload["dimensions"] = payload["dimensions"][:-1]
    with pytest.raises(ValidationError, match="at least 14"):
        VisualScorecard.model_validate(payload)
    payload = _scorecard(bundle, score=85).model_dump(mode="json")
    payload["dimensions"][1]["dimension"] = payload["dimensions"][0][
        "dimension"
    ]
    with pytest.raises(ValidationError, match="exact 14 dimensions"):
        VisualScorecard.model_validate(payload)


def test_score_band_requires_evidence_linked_anchored_rationale() -> None:
    bundle = _bundle((_evidence(index=1),))
    scorecard = _scorecard(bundle, score=85)
    bad = scorecard.model_copy(
        update={
            "dimensions": (
                scorecard.dimensions[0].model_copy(
                    update={"rationale": "This looks generally good enough."}
                ),
                *scorecard.dimensions[1:],
            )
        }
    )
    healed = validate_critic_group(
        bad,
        subject="original",
        group=bundle.grouping_manifest[0],
        bundle=bundle,
        hard_gate=_hard_gate(bundle),
    )
    rationale = healed.dimensions[0].rationale.casefold()
    assert bad.dimensions[0].evidence_ids[0].casefold() in rationale
    assert any(token in rationale for token in ("strong", "professional", "minor"))


def test_deterministic_acceptance_and_reviewer_disagreement() -> None:
    bundle = _bundle((_evidence(index=1),))
    critic = _scorecard(bundle, score=85).model_copy(
        update={"group_index": None}
    )
    accepted = compute_acceptance(
        critic,
        _reviewer(bundle, score=85, recommendation="accept"),
        _hard_gate(bundle),
        VisualAcceptancePolicy(),
    )
    assert accepted.accepted is True
    disagreed = compute_acceptance(
        critic,
        _reviewer(bundle, score=70, recommendation="reject"),
        _hard_gate(bundle),
        VisualAcceptancePolicy(),
    )
    assert disagreed.accepted is False
    assert disagreed.agreement is False


def test_provider_aware_grouping_preserves_whole_route_order() -> None:
    rows = (
        _evidence(index=1, page="PAGE-A", route="/a", viewport="mobile"),
        _evidence(index=2, page="PAGE-A", route="/a", viewport="desktop"),
        _evidence(index=3, page="PAGE-B", route="/b", viewport="mobile"),
        _evidence(index=4, page="PAGE-B", route="/b", viewport="desktop"),
    )
    capability = ModelCapabilityResolution(
        provider="openrouter",
        model="openai/gpt-4o",
        family="openai",
        capability="multimodal_chat",
        message_format="openai_content_parts",
        max_images=2,
        max_image_bytes=1000,
        max_aggregate_image_bytes=1000,
    )
    groups = _group_by_route(
        rows,
        critic=capability,
        reviewer=capability.model_copy(
            update={"model": "google/gemini-2.5-flash", "family": "google"}
        ),
    )
    assert tuple(group.page_ids for group in groups) == (
        ("PAGE-A",),
        ("PAGE-B",),
    )
    assert tuple(
        evidence_id for group in groups for evidence_id in group.evidence_ids
    ) == tuple(item.evidence_id for item in rows)


def test_grouping_rejects_per_image_and_aggregate_limits() -> None:
    capability = ModelCapabilityResolution(
        provider="openrouter",
        model="openai/gpt-4o",
        family="openai",
        capability="multimodal_chat",
        message_format="openai_content_parts",
        max_images=3,
        max_image_bytes=50,
        max_aggregate_image_bytes=100,
    )
    with pytest.raises(ValueError, match="image limit"):
        _group_by_route(
            (_evidence(index=1, byte_count=51),),
            critic=capability,
            reviewer=capability,
        )
    with pytest.raises(ValueError, match="route group"):
        _group_by_route(
            (
                _evidence(index=1, byte_count=50),
                _evidence(index=2, byte_count=50, viewport="mobile"),
                _evidence(index=3, byte_count=50, viewport="tablet"),
            ),
            critic=capability,
            reviewer=capability,
        )


def test_png_decode_dimensions_blank_transparent_and_uniform() -> None:
    root = (
        Path(__file__).parent
        / ".visual-artifacts"
        / uuid.uuid4().hex
    )
    root.mkdir(parents=True)
    try:
        good = root / "good.png"
        image = Image.new("RGB", (390, 844), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 20, 370, 500), fill="#336699")
        draw.text((40, 540), "Business-specific booking proof", fill="black")
        image.save(good)
        inspected = _inspect_png(
            good,
            expected_width=390,
            expected_height=844,
        )
        assert not inspected["blank"]
        assert not inspected["materially_uniform"]

        blank = root / "blank.png"
        Image.new("RGB", (390, 844), "white").save(blank)
        assert _inspect_png(
            blank,
            expected_width=390,
            expected_height=844,
        )["blank"]

        transparent = root / "transparent.png"
        Image.new("RGBA", (390, 844), (0, 0, 0, 0)).save(transparent)
        assert _inspect_png(
            transparent,
            expected_width=390,
            expected_height=844,
        )["transparent"]

        corrupt = root / "corrupt.png"
        corrupt.write_bytes(b"not a png")
        with pytest.raises(OSError):
            _inspect_png(
                corrupt,
                expected_width=390,
                expected_height=844,
            )
        with pytest.raises(ValueError, match="dimensions"):
            _inspect_png(
                good,
                expected_width=391,
                expected_height=844,
            )
    finally:
        shutil.rmtree(root)


def _hard_gate_context(root: Path, bundle: VisualEvidenceBundle):
    source = root / "page.tsx"
    source.write_text(
        "export function Page(){return <main>Clinic booking proof</main>}",
        encoding="utf-8",
    )
    page_rows = []
    for item in bundle.ordered_screenshots:
        if item.page_id in {page.page_id for page in page_rows}:
            continue
        page_rows.append(
            SimpleNamespace(
                page_id=item.page_id,
                route=item.route,
                goal=f"Distinct goal for {item.page_id}",
                requirement_ids=(f"REQ-{item.page_id}",),
                action_ids=(f"ACT-{item.page_id}",),
                evidence_ids=(f"EVD-{item.page_id}",),
            )
        )
    return SimpleNamespace(
        refs=bundle.refs,
        routes=tuple(
            SimpleNamespace(
                page_id=item.page_id,
                viewport=item.viewport,
                primary_action_reachable=True,
                overflow_verified=True,
                clipping_verified=True,
            )
            for item in bundle.ordered_screenshots
        ),
        journeys=(
            SimpleNamespace(
                steps=(SimpleNamespace(step="evidence", passed=True),)
            ),
        ),
        candidate_file_manifest=({"path": "page.tsx"},),
        candidate_workspace=root,
        contracts=SimpleNamespace(
            page_purpose=SimpleNamespace(pages=tuple(page_rows))
        ),
    )


def test_placeholder_and_scaffold_markers_fail_hard_gate() -> None:
    root = Path(__file__).parent / ".visual-artifacts" / uuid.uuid4().hex
    root.mkdir(parents=True)
    try:
        bundle = _bundle((_evidence(index=1),))
        context = _hard_gate_context(root, bundle)
        (root / "page.tsx").write_text(
            "export const Page=()=> <main>Lorem ipsum</main>;"
            "const x='SkeletonComposer';",
            encoding="utf-8",
        )
        report = run_hard_gates(context, bundle)
        assert report.passed is False
        assert {item.code for item in report.findings} >= {
            "visible_placeholder_text",
            "prohibited_scaffold_or_catalogue",
        }
    finally:
        shutil.rmtree(root)


def test_duplicate_shell_rejects_distinct_pages_but_not_shared_chrome() -> None:
    root = Path(__file__).parent / ".visual-artifacts" / uuid.uuid4().hex
    root.mkdir(parents=True)
    try:
        same_shell = _bundle(
            (
                _evidence(
                    index=1,
                    page="PAGE-A",
                    route="/a",
                    structural=SHA_A,
                ),
                _evidence(
                    index=2,
                    page="PAGE-B",
                    route="/b",
                    structural=SHA_A,
                ),
            )
        )
        report = run_hard_gates(
            _hard_gate_context(root, same_shell),
            same_shell,
        )
        assert "distinct_pages_same_structural_shell" in {
            item.code for item in report.findings
        }
        shared_chrome = _bundle(
            (
                _evidence(
                    index=1,
                    page="PAGE-A",
                    route="/a",
                    perceptual=SHA_A,
                    structural=SHA_A,
                ),
                _evidence(
                    index=2,
                    page="PAGE-B",
                    route="/b",
                    perceptual=SHA_A,
                    structural=SHA_B,
                ),
            )
        )
        report = run_hard_gates(
            _hard_gate_context(root, shared_chrome),
            shared_chrome,
        )
        assert report.passed is True
        assert "shared_chrome_similarity" in {
            item.code for item in report.findings
        }
    finally:
        shutil.rmtree(root)


def test_blind_order_is_stable_and_hides_creation_order() -> None:
    first = blind_label_order(SHA_A, SHA_B, attempt_hash="c" * 64)
    second = blind_label_order(SHA_A, SHA_B, attempt_hash="c" * 64)
    assert first == second
    assert set(first) == {SHA_A, SHA_B}


def test_absolute_only_baseline_cannot_claim_improvement() -> None:
    comparison = CandidateBaselineComparison(
        mode="absolute_only",
        reason="No same-policy accepted preview exists.",
        attempt_hash=SHA_A,
    )
    assert comparison.dimensions == ()
    with pytest.raises(ValidationError, match="cannot identify A/B"):
        CandidateBaselineComparison(
            mode="absolute_only",
            reason="No baseline.",
            attempt_hash=SHA_A,
            label_a_identity_sha256=SHA_A,
        )


def test_refinement_output_is_source_only_and_scope_limited() -> None:
    with pytest.raises(ValidationError):
        RefinementOutput.model_validate(
            {
                "schema_version": "1.0",
                "files": [
                    {
                        "path": "package.json",
                        "original_sha256": SHA_A,
                        "source": "{}",
                    }
                ],
            }
        )
    with pytest.raises(ValidationError):
        RefinementOutput.model_validate(
            {
                "schema_version": "1.0",
                "files": [
                    {
                        "path": "src/routes/App.tsx",
                        "original_sha256": SHA_A,
                        "source": "export default 1",
                    }
                ],
            }
        )


def test_cache_key_invalidates_model_prompt_policy_grouping_and_screenshot(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    bundle = _bundle((_evidence(index=1),))
    routing = resolve_visual_routing()
    kwargs = {
        "refs": bundle.refs,
        "bundle": bundle,
        "routing": routing,
        "limits": visual_limits(),
        "score_bands": score_band_policy(),
        "acceptance": acceptance_policy(),
        "baseline_identity": None,
    }
    base = evaluation_cache_key(**kwargs)
    assert evaluation_cache_key(
        **{
            **kwargs,
            "routing": (
                routing[0].model_copy(
                    update={"prompt_revision": "2026-07-24.2"}
                ),
                *routing[1:],
            ),
        }
    ) != base
    assert evaluation_cache_key(
        **{
            **kwargs,
            "score_bands": ScoreBandPolicy.model_construct(
                revision="2026-07-24.2",
                exceptional_min=90,
                strong_min=80,
                usable_min=70,
                weak_min=50,
            ),
        }
    ) != base
    changed = bundle.model_copy(
        update={
            "ordered_screenshot_hashes": (SHA_B,),
            "screenshot_set_sha256": SHA_B,
        }
    )
    assert evaluation_cache_key(**{**kwargs, "bundle": changed}) != base


def test_phase5_source_has_no_promotion_serving_tiers_or_phase6() -> None:
    source = inspect.getsource(phase5_service)
    for prohibited in (
        "PREVIEW_APPS_DIR",
        "promote",
        "serving_pointer",
        "Tier 2",
        "Tier 3",
        "phase6",
        "polish",
        "finalize",
    ):
        assert prohibited not in source


def test_three_flag_boundary_restores_phase4_stop(monkeypatch) -> None:
    phase4 = {
        "preview_contract": {"status": "candidate_runtime_validated"}
    }
    calls = []
    monkeypatch.setattr(
        v2_contract,
        "build_v2_app_spec_contract",
        lambda *_args, **_kwargs: {"preview_contract": {}},
    )
    monkeypatch.setattr(
        v2_contract,
        "build_v2_design_contract",
        lambda *_args, **_kwargs: {"preview_contract": {}},
    )
    monkeypatch.setattr(
        v2_contract,
        "build_v2_composition_contract",
        lambda *_args, **_kwargs: {"preview_contract": {}},
    )
    monkeypatch.setattr(
        v2_contract,
        "build_v2_candidate_revision",
        lambda *_args, **_kwargs: {
            "preview_contract": {"status": "candidate_build_pending"}
        },
    )
    monkeypatch.setattr(
        v2_contract,
        "validate_v2_candidate_runtime",
        lambda *_args, **_kwargs: phase4,
    )
    monkeypatch.setattr(
        v2_contract,
        "evaluate_v2_candidate_visuals",
        lambda *_args, **_kwargs: calls.append("visual") or {
            "preview_contract": {"status": "candidate_visual_accepted"}
        },
    )
    monkeypatch.setattr(settings, "V2_RUNTIME_VALIDATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_VISUAL_EVALUATION_ENABLED", False)
    monkeypatch.setattr(settings, "PREVIEW_GENERATOR_V2", True)
    result = v2_contract.run_v2_contract_boundary(
        None,
        1,
        object(),
        object(),
        req=object(),
        app_spec_revision_id=None,
    )
    assert result is phase4
    assert calls == []
    monkeypatch.setattr(settings, "V2_VISUAL_EVALUATION_ENABLED", True)
    result = v2_contract.run_v2_contract_boundary(
        None,
        1,
        object(),
        object(),
        req=object(),
        app_spec_revision_id=None,
    )
    assert result["preview_contract"]["status"] == "candidate_visual_accepted"
    assert calls == ["visual"]


def test_only_runtime_validated_results_enter_phase5(monkeypatch) -> None:
    monkeypatch.setattr(settings, "PREVIEW_GENERATOR_V2", True)
    monkeypatch.setattr(settings, "V2_RUNTIME_VALIDATION_ENABLED", True)
    monkeypatch.setattr(settings, "V2_VISUAL_EVALUATION_ENABLED", True)
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")

    class NoCalls:
        name = "fixture"

        def ask_chat(self, *_args, **_kwargs):
            raise AssertionError("provider must not be reached")

    with pytest.raises(ValueError, match="candidate_runtime_validated"):
        phase5_service.evaluate_v2_candidate_visuals(
            None,
            1,
            NoCalls(),
            object(),
            req=object(),
            phase4_result={
                "preview_contract": {"status": "candidate_build_pending"}
            },
        )


def test_call_token_cost_and_timeout_limits_are_authoritative() -> None:
    route = VisualCallMetrics(
        stage="critic",
        group_index=0,
        model="openai/gpt-4o",
        provider="fixture",
        family="openai",
        capability="multimodal_chat",
        prompt_revision="2026-07-24.1",
        temperature=0.2,
        max_tokens=12000,
        cache_hit=False,
        provider_call_count=1,
        transport_retry_count=0,
        prompt_tokens=0,
        completion_tokens=42001,
        total_tokens=42001,
        cost_usd=1.51,
        latency_ms=1,
    )
    with pytest.raises(Exception, match="output-token ceiling"):
        phase5_service._budget_guard(
            (route,),
            limits=visual_limits(),
            deadline=time.monotonic() + 10,
        )
    prompt_heavy = route.model_copy(
        update={
            "prompt_tokens": 80000,
            "completion_tokens": 1000,
            "total_tokens": 81000,
            "cost_usd": 0.0,
        }
    )
    phase5_service._budget_guard(
        (prompt_heavy,),
        limits=visual_limits(),
        deadline=time.monotonic() + 10,
    )
    route = route.model_copy(
        update={
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
        }
    )
    with pytest.raises(Exception, match="call ceiling"):
        phase5_service._budget_guard(
            (route,) * 6,
            limits=visual_limits(),
            deadline=time.monotonic() + 10,
            required_additional_calls=1,
        )
    with pytest.raises(Exception, match="wall timeout"):
        phase5_service._budget_guard(
            (),
            limits=visual_limits(),
            deadline=time.monotonic() - 1,
        )


def test_all_ten_phase5_tables_are_additive() -> None:
    expected = {
        "candidate_visual_evaluation_attempts",
        "candidate_visual_evidence_bundles",
        "candidate_visual_hard_gate_results",
        "candidate_visual_scorecards",
        "candidate_visual_findings",
        "candidate_visual_reviewer_decisions",
        "candidate_baseline_comparisons",
        "candidate_refinement_plans",
        "candidate_refinement_generations",
        "candidate_visual_summaries",
    }
    assert expected.issubset(Base.metadata.tables)
