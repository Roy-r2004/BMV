"""Jinja2 prompt rendering — mirrors the settings used by
backend/app/infrastructure/templating/renderer.py (autoescape off, since
every template holds plain text/JSON-shape prompts, not user-facing HTML;
StrictUndefined so a missing variable raises instead of rendering blank).
"""

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_TEMPLATES_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def render(template_name: str, **context) -> str:
    return _env().get_template(template_name).render(**context)
