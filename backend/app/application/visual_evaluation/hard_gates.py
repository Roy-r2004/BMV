"""Zero-AI Phase 5 gates over verified screenshots, source, and Phase 4."""
from __future__ import annotations

import json
import re

from app.application.candidate_generation.cache import canonical_sha256
from app.application.visual_evaluation.context import VisualEvaluationContext
from app.domain.schemas.visual_evaluation import (
    VisualEvidenceBundle,
    VisualHardGateFinding,
    VisualHardGateReport,
)


HARD_GATE_CHECKS = (
    "phase4_terminal_integrity",
    "candidate_manifest_integrity",
    "build_hash_integrity",
    "route_viewport_matrix",
    "journey_and_evidence_reachability",
    "png_decode_and_dimensions",
    "screenshot_hashes",
    "blank_transparent_uniform_images",
    "overflow_and_clipping",
    "visible_placeholder_absence",
    "scaffold_catalogue_absence",
    "generic_duplicate_shells",
    "cross_request_and_stale_references",
)
_PLACEHOLDER = re.compile(
    r"\b(?:lorem ipsum|coming soon|todo content|sample content|"
    r"replace me|placeholder text|your (?:business|company) here)\b",
    re.IGNORECASE,
)
_VISIBLE_JSX = re.compile(r">\s*([^<{][^<]{2,300})\s*<")
_PROHIBITED = (
    "@/ui",
    "SkeletonComposer",
    "MarketingHero",
    "FeatureBento",
    "ProductShowcase",
    "OpsShell",
    "StatCard",
    "DataTable",
    "ChartCard",
)


def _route_evidence(bundle: VisualEvidenceBundle, page_id: str):
    return tuple(
        item for item in bundle.ordered_screenshots if item.page_id == page_id
    )


def run_hard_gates(
    context: VisualEvaluationContext,
    bundle: VisualEvidenceBundle,
) -> VisualHardGateReport:
    findings: list[VisualHardGateFinding] = []

    def add(
        *,
        code: str,
        severity: str,
        rows,
        rationale: str,
    ) -> None:
        selected = tuple(rows)
        findings.append(
            VisualHardGateFinding(
                finding_id=f"HG-{len(findings) + 1:03d}",
                code=code,
                severity=severity,
                evidence_ids=tuple(
                    dict.fromkeys(item.evidence_id for item in selected)
                ),
                routes=tuple(dict.fromkeys(item.route for item in selected)),
                viewports=tuple(
                    dict.fromkeys(item.viewport for item in selected)
                ),
                rationale=rationale,
                deterministic_support=True,
            )
        )

    for item in bundle.ordered_screenshots:
        if item.blank:
            add(
                code="blank_screenshot",
                severity="blocking",
                rows=(item,),
                rationale=(
                    f"{item.route} at {item.viewport} decodes as an empty "
                    "black/white or transparent screenshot."
                ),
            )
        elif item.transparent:
            add(
                code="transparent_screenshot",
                severity="blocking",
                rows=(item,),
                rationale=(
                    f"{item.route} at {item.viewport} has no materially "
                    "opaque rendered content."
                ),
            )
        elif item.materially_uniform:
            add(
                code="materially_uniform_screenshot",
                severity="blocking",
                rows=(item,),
                rationale=(
                    f"{item.route} at {item.viewport} lacks sufficient "
                    "rendered visual variation."
                ),
            )

    route_map = {
        (item.page_id, item.viewport): item for item in context.routes
    }
    journey_has_evidence = all(
        any(step.step == "evidence" and step.passed for step in item.steps)
        for item in context.journeys
    )
    for evidence in bundle.ordered_screenshots:
        route = route_map[(evidence.page_id, evidence.viewport)]
        if (
            not route.primary_action_reachable
            or not route.overflow_verified
            or not route.clipping_verified
            or not journey_has_evidence
        ):
            add(
                code="required_interaction_visually_unreachable",
                severity="blocking",
                rows=(evidence,),
                rationale=(
                    f"Phase 4 did not prove reachable action/evidence and "
                    f"unclipped content for {evidence.route} "
                    f"at {evidence.viewport}."
                ),
            )

    visible_text: list[str] = []
    all_source: list[str] = []
    for manifest in context.candidate_file_manifest:
        path = context.candidate_workspace / manifest["path"]
        if path.suffix not in {".tsx", ".ts", ".json", ".css"}:
            continue
        text = path.read_text(encoding="utf-8")
        all_source.append(text)
        if path.suffix == ".tsx":
            visible_text.extend(_VISIBLE_JSX.findall(text))
        elif path.name == "content-data.json":
            try:
                visible_text.append(
                    json.dumps(json.loads(text), ensure_ascii=False)
                )
            except Exception:
                visible_text.append(text)
    placeholder_match = _PLACEHOLDER.search("\n".join(visible_text))
    if placeholder_match:
        add(
            code="visible_placeholder_text",
            severity="blocking",
            rows=bundle.ordered_screenshots,
            rationale=(
                "Visible candidate content contains deterministic "
                f"placeholder marker {placeholder_match.group(0)!r}."
            ),
        )
    joined_source = "\n".join(all_source).casefold()
    markers = tuple(
        marker for marker in _PROHIBITED
        if marker.casefold() in joined_source
    )
    if markers:
        add(
            code="prohibited_scaffold_or_catalogue",
            severity="blocking",
            rows=bundle.ordered_screenshots,
            rationale=(
                "Candidate source contains prohibited high-level markers: "
                + ", ".join(markers)
            ),
        )

    pages = {item.page_id: item for item in context.contracts.page_purpose.pages}
    by_viewport: dict[str, list] = {}
    for item in bundle.ordered_screenshots:
        by_viewport.setdefault(item.viewport, []).append(item)
    for viewport, rows in by_viewport.items():
        structural: dict[str, list] = {}
        perceptual: dict[str, list] = {}
        for row in rows:
            structural.setdefault(row.structural_sha256, []).append(row)
            perceptual.setdefault(row.perceptual_sha256, []).append(row)
        for duplicates in structural.values():
            page_ids = tuple(dict.fromkeys(item.page_id for item in duplicates))
            if len(page_ids) < 2:
                continue
            signatures = {
                (
                    pages[page_id].goal,
                    pages[page_id].requirement_ids,
                    pages[page_id].action_ids,
                    pages[page_id].evidence_ids,
                )
                for page_id in page_ids
            }
            if len(signatures) > 1:
                add(
                    code="distinct_pages_same_structural_shell",
                    severity="blocking",
                    rows=duplicates,
                    rationale=(
                        "Canonical page-purpose contracts are distinct, but "
                        f"their {viewport} content-region render is identical."
                    ),
                )
        # Full-image equality without content-region equality is only advisory;
        # shared navigation, typography, and product chrome are legitimate.
        for duplicates in perceptual.values():
            if (
                len({item.page_id for item in duplicates}) > 1
                and len({item.structural_sha256 for item in duplicates}) > 1
            ):
                add(
                    code="shared_chrome_similarity",
                    severity="advisory",
                    rows=duplicates,
                    rationale=(
                        "Routes share strong chrome-level consistency while "
                        "their canonical content regions remain distinct."
                    ),
                )
    cache_key = canonical_sha256(
        {
            "refs": context.refs.model_dump(mode="json"),
            "evidence_cache_key": bundle.cache_key,
            "checks": HARD_GATE_CHECKS,
            "findings": [item.model_dump(mode="json") for item in findings],
            "policy_revision": "2026-07-24.1",
        }
    )
    return VisualHardGateReport(
        refs=context.refs,
        cache_key=cache_key,
        checks=HARD_GATE_CHECKS,
        findings=tuple(findings),
        passed=not any(item.severity == "blocking" for item in findings),
    )


__all__ = ["HARD_GATE_CHECKS", "run_hard_gates"]
