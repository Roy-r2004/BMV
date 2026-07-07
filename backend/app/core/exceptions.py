"""Application-level exception hierarchy.

These are internal, layer-agnostic errors. Routers translate them into the
appropriate `HTTPException` at the API boundary; application/infrastructure
code should raise these instead of generic `Exception`/`ValueError` where a
more specific type is useful.
"""


class AppError(Exception):
    """Base class for all application-raised errors."""


class NotFoundError(AppError):
    """A requested resource does not exist."""


class ValidationError(AppError):
    """Input failed a domain validation rule."""


class AIProviderError(AppError):
    """The configured AI provider (Ollama/OpenRouter) failed or is unavailable."""


class BuildError(AppError):
    """The generated preview app failed to compile."""


class TemplateRenderError(AppError):
    """A Jinja2 template failed to render."""
