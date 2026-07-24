"""Preview-generator version selection.

Phase 0 deliberately keeps the v2 execution path behaviorally identical to
v1. This module is the narrow boundary that later phases can replace without
changing how legacy previews are selected.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Literal, TypeVar


GENERATOR_V1 = "v1"
GENERATOR_V2 = "v2"
GeneratorVersion = Literal["v1", "v2"]

_T = TypeVar("_T")


@dataclass(frozen=True)
class GeneratorSelection:
    version: GeneratorVersion
    reason: str


def _preview_metadata(generated_pages: object) -> tuple[dict, bool]:
    """Return persisted preview metadata and whether any legacy output exists."""

    if not generated_pages:
        return {}, False
    try:
        payload = (
            json.loads(generated_pages)
            if isinstance(generated_pages, str)
            else generated_pages
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}, True
    if not isinstance(payload, dict):
        return {}, True
    preview_app = payload.get("preview_app")
    return (preview_app if isinstance(preview_app, dict) else {}), True


def select_preview_generator(
    request: object,
    *,
    v2_enabled: bool,
) -> GeneratorSelection:
    """Select a generator without migrating or mutating an existing preview.

    The flag is an emergency rollback switch: when false, every generation
    uses v1. When true, existing unmarked output remains on v1 and only a new
    preview enters v2. A v2 marker keeps that preview on v2 while the flag
    remains enabled.
    """

    if not v2_enabled:
        return GeneratorSelection(GENERATOR_V1, "flag_disabled")

    metadata, has_existing_output = _preview_metadata(
        getattr(request, "generated_pages", None)
    )
    persisted_version = metadata.get("generator_version")
    if persisted_version == GENERATOR_V2:
        return GeneratorSelection(GENERATOR_V2, "existing_v2_preview")
    if has_existing_output:
        return GeneratorSelection(GENERATOR_V1, "existing_v1_preview")
    return GeneratorSelection(GENERATOR_V2, "flag_enabled_new_preview")


def dispatch_preview_generator(
    selection: GeneratorSelection,
    *,
    run_v1: Callable[[], _T],
    run_v2: Callable[[], _T],
) -> _T:
    """Dispatch through the explicit boundary without evaluating both paths."""

    if selection.version == GENERATOR_V2:
        return run_v2()
    return run_v1()


def apply_generator_version_marker(
    preview_app: dict,
    *,
    version: str,
) -> dict:
    """Persist only the opt-in v2 marker; leave legacy v1 payloads untouched."""

    if version == GENERATOR_V2:
        preview_app["generator_version"] = GENERATOR_V2
    return preview_app


__all__ = [
    "apply_generator_version_marker",
    "GENERATOR_V1",
    "GENERATOR_V2",
    "GeneratorSelection",
    "GeneratorVersion",
    "dispatch_preview_generator",
    "select_preview_generator",
]
