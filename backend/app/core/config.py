"""Application settings.

All environment-driven configuration lives here as a single typed `Settings`
object, instead of scattered module-level constants. Import the `settings`
singleton anywhere it's needed:

    from app.core.config import settings
    settings.DATABASE_URL
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_APP_DIR = Path(__file__).resolve().parent.parent  # backend/app
_PROJECT_ROOT = _APP_DIR.parent.parent  # repo root


def _normalize_database_url(url: str) -> str:
    """Render/Heroku often give postgres://; SQLAlchemy expects postgresql://."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


class Settings:
    """Environment-driven settings, resolved once at import time."""

    BASE_DIR: Path = _APP_DIR
    PROJECT_ROOT: Path = _PROJECT_ROOT

    # Database (Render may provide postgres:// — normalize for SQLAlchemy)
    DATABASE_URL: str = _normalize_database_url(
        os.getenv("DATABASE_URL", "sqlite:///./buildmyversion.db")
    )

    # Admin auth
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "change_this_password")

    # Uploads
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", str(_APP_DIR / "uploads"))

    # Misc
    ROY_WHATSAPP_NUMBER: str = os.getenv("ROY_WHATSAPP_NUMBER", "")

    # AI provider selection
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "ollama").strip().lower()

    # Ollama
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")

    # OpenRouter
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    OPENROUTER_APP_NAME: str = os.getenv("OPENROUTER_APP_NAME", "Build My Version")

    # Preview app build paths
    PREVIEW_TEMPLATE_DIR: Path
    PREVIEW_APPS_DIR: Path

    # Model names (resolved below, provider-dependent)
    TEXT_MODEL: str
    VISION_MODEL: str
    CODER_MODEL: str
    HTML_MODEL: str
    PREVIEW_APP_MODEL: str
    ARCHITECT_MODEL: str
    CRITIC_MODEL: str
    FIX_MODEL: str
    PREVIEW_SKIP_CRITIC: bool
    PREVIEW_PARALLEL_WORKERS: int
    PREVIEW_SKIP_VISUAL_CRITIC: bool
    INTERNAL_BASE_URL: str

    def __init__(self) -> None:
        self.PREVIEW_TEMPLATE_DIR = Path(
            os.getenv("PREVIEW_TEMPLATE_DIR", str(self.PROJECT_ROOT / "preview-template"))
        )
        self.PREVIEW_APPS_DIR = Path(
            os.getenv("PREVIEW_APPS_DIR", str(Path(self.UPLOAD_DIR) / "preview-apps"))
        )

        provider_key = "openrouter" if self.AI_PROVIDER == "openrouter" else "ollama"
        defaults = _DEFAULT_MODELS[provider_key]

        self.TEXT_MODEL = os.getenv("TEXT_MODEL", defaults["text"])
        self.VISION_MODEL = os.getenv("VISION_MODEL", defaults["vision"])
        self.CODER_MODEL = os.getenv("CODER_MODEL", defaults["coder"])
        self.HTML_MODEL = os.getenv("HTML_MODEL", defaults["html"])
        self.PREVIEW_APP_MODEL = os.getenv("PREVIEW_APP_MODEL", self.HTML_MODEL)

        # Architecture and design-critique are where model "taste" actually shows
        # up (layout, hierarchy, visual judgment) — bulk file codegen can stay on
        # a cheap coder model, but these two calls get a stronger default.
        taste_default = "anthropic/claude-haiku-4.5" if provider_key == "openrouter" else defaults["text"]
        self.ARCHITECT_MODEL = os.getenv("ARCHITECT_MODEL", taste_default)
        self.CRITIC_MODEL = os.getenv("CRITIC_MODEL", taste_default)
        # Fix loop uses the codegen model by default — Flash often returns empty JSON.
        self.FIX_MODEL = os.getenv("FIX_MODEL", self.PREVIEW_APP_MODEL)
        self.PREVIEW_SKIP_CRITIC = os.getenv("PREVIEW_SKIP_CRITIC", "true").strip().lower() in (
            "1", "true", "yes", "on",
        )
        try:
            self.PREVIEW_PARALLEL_WORKERS = max(1, int(os.getenv("PREVIEW_PARALLEL_WORKERS", "4")))
        except ValueError:
            self.PREVIEW_PARALLEL_WORKERS = 4

        # Post-build visual critique (screenshot + vision critic) is the most
        # expensive/slowest stage in the pipeline (headless Chromium launch +
        # render wait + a vision model call per page) — default OFF so it
        # never turns on unannounced; toggle in .env without a redeploy.
        self.PREVIEW_SKIP_VISUAL_CRITIC = os.getenv(
            "PREVIEW_SKIP_VISUAL_CRITIC", "true"
        ).strip().lower() in ("1", "true", "yes", "on")
        # Internal-only address Playwright uses to reach this same server's
        # already-running preview-app route — never exposed to end users,
        # unrelated to any public base URL / CORS setting.
        self.INTERNAL_BASE_URL = os.getenv("INTERNAL_BASE_URL", "http://localhost:8000").rstrip("/")

    @property
    def TEMPLATES_DIR(self) -> Path:
        return self.BASE_DIR / "templates"

    @property
    def cors_origins(self) -> list[str]:
        raw = os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://localhost:5175,http://127.0.0.1:5175",
        )
        return [o.strip() for o in raw.split(",") if o.strip()]


_DEFAULT_MODELS: dict[str, dict[str, str]] = {
    "ollama": {
        "text": "llama3.1:8b",
        "vision": "llama3.2-vision",
        "coder": "qwen2.5-coder:7b",
        "html": "qwen2.5-coder:7b",
    },
    "openrouter": {
        "text": "meta-llama/llama-3.1-8b-instruct",
        "vision": "meta-llama/llama-3.2-11b-vision-instruct",
        "coder": "qwen/qwen-2.5-coder-32b-instruct",
        "html": "openai/gpt-4o",
    },
}


settings = Settings()
