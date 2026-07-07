"""Contract for rendering named templates with a context.

Used for LLM prompts, generated browser HTML/JS, and generated React/CSS
code — every string-built artifact in the system goes through this
interface instead of ad-hoc f-strings.
"""
from typing import Any, Protocol


class TemplateRenderer(Protocol):
    def render(self, template_name: str, **context: Any) -> str:
        """Render the named template (relative to the templates root) with context."""
        ...
