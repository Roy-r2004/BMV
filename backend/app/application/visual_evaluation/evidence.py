"""PNG verification, deterministic visual evidence, and provider-aware groups."""
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageOps, ImageStat

from app.application.candidate_generation.cache import canonical_sha256
from app.application.runtime_validation.cache import sha256_file
from app.application.runtime_validation.policy import VIEWPORTS
from app.application.runtime_validation.workspace import validation_root
from app.application.visual_evaluation.context import VisualEvaluationContext
from app.domain.schemas.visual_evaluation import (
    ImageBundleGroup,
    ModelCapabilityResolution,
    ScreenshotVisualEvidence,
    VisualEvidenceBundle,
)


def _image_hash(image: Image.Image, *, structural: bool) -> str:
    grayscale = image.convert("L")
    if structural:
        width, height = grayscale.size
        grayscale = grayscale.crop(
            (0, int(height * 0.18), width, int(height * 0.92))
        )
        grayscale = ImageOps.autocontrast(grayscale)
        size = (32, 32)
    else:
        size = (16, 16)
    sample = grayscale.resize(size, Image.Resampling.LANCZOS)
    return hashlib.sha256(sample.tobytes()).hexdigest()


def _inspect_png(
    path: Path,
    *,
    expected_width: int,
    expected_height: int,
) -> dict:
    try:
        with Image.open(path) as probe:
            probe.verify()
        with Image.open(path) as opened:
            if opened.format != "PNG":
                raise ValueError("Screenshot evidence is not PNG")
            opened.load()
            if opened.size != (expected_width, expected_height):
                raise ValueError(
                    "Screenshot dimensions do not match capture viewport"
                )
            rgba = opened.convert("RGBA")
            alpha = rgba.getchannel("A")
            alpha_stat = ImageStat.Stat(alpha)
            alpha_mean = float(alpha_stat.mean[0])
            opaque_ratio = sum(
                count for count, value in alpha.getcolors(maxcolors=256) or ()
                if value >= 250
            ) / float(expected_width * expected_height)
            grayscale = rgba.convert("L")
            stat = ImageStat.Stat(grayscale)
            mean = float(stat.mean[0])
            stddev = float(stat.stddev[0])
            entropy = float(grayscale.entropy())
            transparent = alpha_mean <= 2.0 or opaque_ratio <= 0.01
            blank = transparent or (
                stddev < 1.0 and (mean <= 2.0 or mean >= 253.0)
            )
            # A valid sparse landing page may have a very low global entropy.
            # Treat it as materially uniform only when both pixel spread and
            # information content are effectively absent.
            uniform = stddev < 0.5 and entropy < 0.05
            return {
                "width": opened.width,
                "height": opened.height,
                "mode": opened.mode,
                "alpha_opaque_ratio": opaque_ratio,
                "luminance_mean": mean,
                "luminance_stddev": stddev,
                "entropy": entropy,
                "perceptual_sha256": _image_hash(rgba, structural=False),
                "structural_sha256": _image_hash(rgba, structural=True),
                "blank": blank,
                "transparent": transparent,
                "materially_uniform": uniform,
            }
    except (OSError, SyntaxError, ValueError):
        raise
    except Exception as exc:
        raise ValueError("PNG evidence could not be decoded") from exc


def _screenshot_path(relative_path: str) -> Path:
    root = validation_root().resolve(strict=False)
    target = (root / relative_path).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Screenshot evidence escapes validation root") from exc
    if not target.is_file():
        raise ValueError("Screenshot evidence file is missing")
    return target


def _group_by_route(
    screenshots: tuple[ScreenshotVisualEvidence, ...],
    *,
    critic: ModelCapabilityResolution,
    reviewer: ModelCapabilityResolution,
) -> tuple[ImageBundleGroup, ...]:
    max_images = min(critic.max_images, reviewer.max_images)
    max_image_bytes = min(
        critic.max_image_bytes,
        reviewer.max_image_bytes,
    )
    max_aggregate = min(
        critic.max_aggregate_image_bytes,
        reviewer.max_aggregate_image_bytes,
    )
    if not max_images or not max_image_bytes or not max_aggregate:
        raise ValueError("Resolved visual models cannot accept image bundles")
    by_page: list[tuple[str, list[ScreenshotVisualEvidence]]] = []
    for item in screenshots:
        if item.byte_count > max_image_bytes:
            raise ValueError(
                f"Screenshot {item.evidence_id} exceeds model image limit"
            )
        if not by_page or by_page[-1][0] != item.page_id:
            by_page.append((item.page_id, [item]))
        else:
            by_page[-1][1].append(item)
    groups: list[ImageBundleGroup] = []
    pending_pages: list[str] = []
    pending: list[ScreenshotVisualEvidence] = []
    pending_bytes = 0

    def flush() -> None:
        nonlocal pending_pages, pending, pending_bytes
        if not pending:
            return
        payload = [
            {
                "evidence_id": item.evidence_id,
                "sha256": item.sha256,
                "byte_count": item.byte_count,
            }
            for item in pending
        ]
        groups.append(
            ImageBundleGroup(
                group_index=len(groups),
                page_ids=tuple(pending_pages),
                evidence_ids=tuple(item.evidence_id for item in pending),
                image_count=len(pending),
                aggregate_image_bytes=pending_bytes,
                group_sha256=canonical_sha256(payload),
            )
        )
        pending_pages = []
        pending = []
        pending_bytes = 0

    for page_id, images in by_page:
        route_bytes = sum(item.byte_count for item in images)
        if len(images) > max_images or route_bytes > max_aggregate:
            raise ValueError(
                f"One route group for {page_id} exceeds model bundle limits"
            )
        if pending and (
            len(pending) + len(images) > max_images
            or pending_bytes + route_bytes > max_aggregate
        ):
            flush()
        pending_pages.append(page_id)
        pending.extend(images)
        pending_bytes += route_bytes
    flush()
    return tuple(groups)


def build_evidence_bundle(
    context: VisualEvaluationContext,
    *,
    critic_capability: ModelCapabilityResolution,
    reviewer_capability: ModelCapabilityResolution,
) -> VisualEvidenceBundle:
    viewport_map = {item.name: item for item in VIEWPORTS}
    inspected = []
    for index, screenshot in enumerate(context.screenshots):
        path = _screenshot_path(screenshot.relative_path)
        if (
            path.stat().st_size != screenshot.byte_count
            or sha256_file(path) != screenshot.sha256
        ):
            raise ValueError("Screenshot byte/hash verification failed")
        viewport = viewport_map[screenshot.viewport]
        details = _inspect_png(
            path,
            expected_width=viewport.width,
            expected_height=viewport.height,
        )
        inspected.append(
            ScreenshotVisualEvidence(
                evidence_id=f"VE-{index + 1:03d}",
                page_id=screenshot.page_id,
                route=screenshot.route,
                viewport=screenshot.viewport,
                relative_path=screenshot.relative_path,
                sha256=screenshot.sha256,
                byte_count=screenshot.byte_count,
                **details,
            )
        )
    ordered = tuple(inspected)
    if canonical_sha256(
        [
            {
                "page_id": item.page_id,
                "route": item.route,
                "viewport": item.viewport,
                "sha256": item.sha256,
            }
            for item in ordered
        ]
    ) != context.refs.screenshot_set_sha256:
        raise ValueError("Screenshot-set hash changed during inspection")
    groups = _group_by_route(
        ordered,
        critic=critic_capability,
        reviewer=reviewer_capability,
    )
    cache_payload = {
        "refs": context.refs.model_dump(mode="json"),
        "ordered": [
            item.model_dump(mode="json") for item in ordered
        ],
        "groups": [item.model_dump(mode="json") for item in groups],
        "capabilities": [
            critic_capability.model_dump(mode="json"),
            reviewer_capability.model_dump(mode="json"),
        ],
    }
    first = context.screenshots[0]
    return VisualEvidenceBundle(
        refs=context.refs,
        capture_policy_revision=first.capture_policy_revision,
        browser_version=first.browser_version,
        ordered_screenshots=ordered,
        grouping_manifest=groups,
        ordered_screenshot_hashes=tuple(item.sha256 for item in ordered),
        screenshot_set_sha256=context.refs.screenshot_set_sha256,
        cache_key=canonical_sha256(cache_payload),
    )


def evidence_absolute_paths(
    bundle: VisualEvidenceBundle,
    evidence_ids: tuple[str, ...],
) -> tuple[Path, ...]:
    wanted = set(evidence_ids)
    rows = tuple(
        item for item in bundle.ordered_screenshots
        if item.evidence_id in wanted
    )
    if len(rows) != len(wanted):
        raise ValueError("Image group references missing evidence")
    return tuple(_screenshot_path(item.relative_path) for item in rows)


__all__ = [
    "build_evidence_bundle",
    "evidence_absolute_paths",
]
