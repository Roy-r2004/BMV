"""Jinja2-backed implementation of `TemplateRenderer`.

One shared `Environment` is used for every template category (LLM prompts,
generated browser HTML/JS, generated React/CSS code). Autoescaping is off
everywhere: every use case inserts already-correct content (plain text,
pre-built HTML fragments, source code) rather than user-facing text that
needs HTML-escaping.
"""
from __future__ import annotations

from functools import lru_cache

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.core.config import settings
from app.core.exceptions import TemplateRenderError
from app.domain.interfaces.template_renderer import TemplateRenderer


class JinjaTemplateRenderer(TemplateRenderer):
    def __init__(self, templates_dir=None) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(templates_dir or settings.TEMPLATES_DIR)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
        )

    def render(self, template_name: str, **context) -> str:
        try:
            template = self._env.get_template(template_name)
            return template.render(**context)
        except Exception as exc:
            raise TemplateRenderError(f"Failed to render template '{template_name}': {exc}") from exc


@lru_cache(maxsize=1)
def get_template_renderer() -> TemplateRenderer:
    return JinjaTemplateRenderer()
