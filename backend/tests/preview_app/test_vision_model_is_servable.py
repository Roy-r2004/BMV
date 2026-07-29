"""The configured vision model must be one the provider actually serves.

The visual critic is the only component in the pipeline that renders pixels, and
it was calling `meta-llama/llama-3.2-11b-vision-instruct`, for which OpenRouter
returns "No endpoints found". Every route failed, the critic reviewed nothing, and
because an unavailable verdict is not a failure the run still reported a pass. So
the one check able to notice dental photographs in an art gallery was inert.

These are offline guards — no network. They pin the default away from the known-dead
model and keep the deploy templates agreeing with the code.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.core.config import _DEFAULT_MODELS

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Models confirmed to return no endpoints on OpenRouter. Add to this list rather
# than deleting it — a regression here is silent at runtime.
_UNSERVABLE = ("meta-llama/llama-3.2-11b-vision-instruct",)


def test_openrouter_vision_default_is_not_a_dead_model() -> None:
    vision = _DEFAULT_MODELS["openrouter"]["vision"]
    assert vision not in _UNSERVABLE, (
        f"the OpenRouter vision default is {vision!r}, which serves no endpoints — "
        "the visual critic will fail on every route and review nothing"
    )
    assert vision.strip(), "a blank vision default falls through to CRITIC_MODEL, which may not be multimodal"


def test_vision_default_is_a_multimodal_family() -> None:
    """Guard against pointing `vision` at a text-only model, which fails per-route."""
    vision = _DEFAULT_MODELS["openrouter"]["vision"].lower()
    multimodal_families = ("gemini", "gpt-4o", "gpt-4.1", "claude", "vision", "pixtral", "qwen-vl")
    assert any(family in vision for family in multimodal_families), (
        f"{vision!r} does not look like a multimodal model; ask_vision would fail"
    )


def _env_value(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if name.strip() == key:
            return value.strip()
    return None


def test_deploy_templates_do_not_pin_a_dead_vision_model() -> None:
    """An uncommented dead value in a template is worse than no value at all."""
    offenders = []
    for rel in (".env.prod.example", "backend/.env.example", ".env.example"):
        value = _env_value(_REPO_ROOT / rel, "VISION_MODEL")
        if value and value in _UNSERVABLE:
            offenders.append(f"{rel}={value}")
    assert not offenders, f"deploy templates pin an unservable vision model: {offenders}"


def test_docs_do_not_advertise_a_dead_vision_model() -> None:
    docs = _REPO_ROOT / "docs"
    if not docs.is_dir():
        return  # container mounts only ./backend
    hits = []
    for path in docs.rglob("*.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for dead in _UNSERVABLE:
            if dead in text:
                hits.append(str(path.relative_to(_REPO_ROOT)))
    assert not hits, (
        f"docs still tell operators to configure an unservable vision model: {sorted(set(hits))}"
    )
