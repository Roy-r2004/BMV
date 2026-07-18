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

_APP_DIR = Path(__file__).resolve().parent.parent  # backend/app
_PROJECT_ROOT = _APP_DIR.parent.parent  # repo root
# Prefer backend/.env (compose + local), then cwd
load_dotenv(_APP_DIR.parent / ".env")
load_dotenv()


def _normalize_database_url(url: str | None) -> str:
    """Render/Heroku often give postgres://; SQLAlchemy expects postgresql://.

    Empty env values (common with Blueprint sync:false) must fall back to SQLite
    so the web process can still bind a port on Render.
    """
    raw = (url or "").strip()
    if not raw:
        return "sqlite:///./buildmyversion.db"
    if raw.startswith("postgres://"):
        return "postgresql://" + raw[len("postgres://") :]
    return raw


def _env_or(name: str, default: str) -> str:
    """Read an env var, treating blank/whitespace as unset so Compose defaults work."""

    raw = (os.getenv(name) or "").strip()
    return raw or default


class Settings:
    """Environment-driven settings, resolved once at import time."""

    BASE_DIR: Path = _APP_DIR
    PROJECT_ROOT: Path = _PROJECT_ROOT

    # Database (Render may provide postgres:// — normalize for SQLAlchemy)
    DATABASE_URL: str = _normalize_database_url(os.getenv("DATABASE_URL"))

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

    # OpenRouter (strip — Render/dashboard pastes often include trailing newlines)
    OPENROUTER_API_KEY: str = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    OPENROUTER_BASE_URL: str = (os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").strip()
    OPENROUTER_APP_NAME: str = os.getenv("OPENROUTER_APP_NAME", "Build My Version")

    # Pexels — per-business preview stock photos (optional; curated fallback if empty)
    PEXELS_API_KEY: str = (os.getenv("PEXELS_API_KEY") or "").strip()

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
    APPSPEC_MODEL: str
    APPSPEC_REPAIR_MODEL: str
    APPSPEC_COVERAGE_MODEL: str
    APPSPEC_MODE: str
    APPSPEC_SCHEMA_VERSION: str
    APPSPEC_PROMPT_REVISION: str
    APPSPEC_MAX_CALLS: int
    APPSPEC_MAX_REPAIR_ATTEMPTS: int
    APPSPEC_MAX_TOKENS: int
    APPSPEC_REPAIR_MAX_TOKENS: int
    APPSPEC_COVERAGE_MAX_TOKENS: int
    APPSPEC_MIN_COVERAGE_SCORE: int
    APPSPEC_PREVIEW_TARGET_PAGES: int
    APPSPEC_PREVIEW_MAX_PAGES: int
    PREVIEW_SKIP_CRITIC: bool
    PREVIEW_PARALLEL_WORKERS: int
    PREVIEW_MAX_FILES: int
    PREVIEW_MAX_BUILD_FIX_ATTEMPTS: int
    PREVIEW_MAX_FIX_LOOP_SECONDS: int
    PREVIEW_MAX_AI_CALLS: int
    PREVIEW_SKIP_VISUAL_CRITIC: bool
    PREVIEW_SCAFFOLD_FIRST: bool
    PREVIEW_SCAFFOLD_SLOT_FILL: bool
    INTERNAL_BASE_URL: str
    STATIC_DIR: Path | None
    CORS_ORIGINS: str
    UVICORN_RELOAD: bool
    LOG_LEVEL: str

    def __init__(self) -> None:
        # Resolve preview-template from env, repo root, or next to backend/
        # (Render used to deploy rootDir=backend only — template was missing).
        env_tpl = (os.getenv("PREVIEW_TEMPLATE_DIR") or "").strip()
        candidates = []
        if env_tpl:
            candidates.append(Path(env_tpl))
        candidates.extend(
            [
                self.PROJECT_ROOT / "preview-template",
                self.BASE_DIR.parent / "preview-template",
                Path.cwd() / "preview-template",
                Path.cwd().parent / "preview-template",
            ]
        )
        self.PREVIEW_TEMPLATE_DIR = next((p for p in candidates if p.is_dir()), candidates[0])
        self.PREVIEW_APPS_DIR = Path(
            os.getenv("PREVIEW_APPS_DIR", str(Path(self.UPLOAD_DIR) / "preview-apps"))
        )

        provider_key = "openrouter" if self.AI_PROVIDER == "openrouter" else "ollama"
        defaults = _DEFAULT_MODELS[provider_key]

        self.TEXT_MODEL = _env_or("TEXT_MODEL", defaults["text"])
        self.VISION_MODEL = _env_or("VISION_MODEL", defaults["vision"])
        self.CODER_MODEL = _env_or("CODER_MODEL", defaults["coder"])
        self.HTML_MODEL = _env_or("HTML_MODEL", defaults["html"])
        self.PREVIEW_APP_MODEL = _env_or("PREVIEW_APP_MODEL", self.HTML_MODEL)

        # Architecture and design-critique are where model "taste" actually shows
        # up (layout, hierarchy, visual judgment) — bulk file codegen can stay on
        # a cheap coder model, but these two calls get a stronger default.
        taste_default = "anthropic/claude-haiku-4.5" if provider_key == "openrouter" else defaults["text"]
        self.ARCHITECT_MODEL = _env_or("ARCHITECT_MODEL", taste_default)
        self.CRITIC_MODEL = _env_or("CRITIC_MODEL", taste_default)
        # Fix loop uses the codegen model by default — Flash often returns empty JSON.
        self.FIX_MODEL = _env_or("FIX_MODEL", self.PREVIEW_APP_MODEL)

        # Canonical product contract toggle. `off` keeps the legacy pipeline
        # untouched; `on` authors, enforces, and drives the UI from the AppSpec
        # for every preview. Legacy rollout values (shadow/required_new/required)
        # are accepted and treated as `on` so old configs keep working.
        requested_appspec_mode = os.getenv("APPSPEC_MODE", "off").strip().lower()
        _appspec_on = {"on", "shadow", "required_new", "required", "true", "1", "yes", "enabled"}
        self.APPSPEC_MODE = "on" if requested_appspec_mode in _appspec_on else "off"
        self.APPSPEC_SCHEMA_VERSION = (
            os.getenv("APPSPEC_SCHEMA_VERSION", "1.0").strip() or "1.0"
        )
        self.APPSPEC_PROMPT_REVISION = (
            os.getenv("APPSPEC_PROMPT_REVISION", "2026-07-18.1").strip()
            or "2026-07-15.1"
        )
        self.APPSPEC_MODEL = _env_or("APPSPEC_MODEL", self.ARCHITECT_MODEL)
        self.APPSPEC_REPAIR_MODEL = _env_or("APPSPEC_REPAIR_MODEL", self.APPSPEC_MODEL)
        # Keep the coverage review separately configurable so production can use
        # a different model from the authoring pass instead of self-grading.
        self.APPSPEC_COVERAGE_MODEL = _env_or(
            "APPSPEC_COVERAGE_MODEL", self.CRITIC_MODEL
        )
        try:
            self.APPSPEC_MAX_CALLS = max(2, int(os.getenv("APPSPEC_MAX_CALLS", "6")))
        except ValueError:
            self.APPSPEC_MAX_CALLS = 6
        try:
            self.APPSPEC_MAX_REPAIR_ATTEMPTS = max(
                0, int(os.getenv("APPSPEC_MAX_REPAIR_ATTEMPTS", "3"))
            )
        except ValueError:
            self.APPSPEC_MAX_REPAIR_ATTEMPTS = 3
        try:
            self.APPSPEC_MAX_TOKENS = max(
                4000, int(os.getenv("APPSPEC_MAX_TOKENS", "24000"))
            )
        except ValueError:
            self.APPSPEC_MAX_TOKENS = 24000
        try:
            self.APPSPEC_REPAIR_MAX_TOKENS = max(
                4000, int(os.getenv("APPSPEC_REPAIR_MAX_TOKENS", "24000"))
            )
        except ValueError:
            self.APPSPEC_REPAIR_MAX_TOKENS = 24000
        try:
            self.APPSPEC_COVERAGE_MAX_TOKENS = max(
                2000, int(os.getenv("APPSPEC_COVERAGE_MAX_TOKENS", "6000"))
            )
        except ValueError:
            self.APPSPEC_COVERAGE_MAX_TOKENS = 6000
        try:
            self.APPSPEC_MIN_COVERAGE_SCORE = min(
                100, max(0, int(os.getenv("APPSPEC_MIN_COVERAGE_SCORE", "95")))
            )
        except ValueError:
            self.APPSPEC_MIN_COVERAGE_SCORE = 95
        try:
            self.APPSPEC_PREVIEW_TARGET_PAGES = max(
                1, int(os.getenv("APPSPEC_PREVIEW_TARGET_PAGES", "6"))
            )
        except ValueError:
            self.APPSPEC_PREVIEW_TARGET_PAGES = 6
        try:
            self.APPSPEC_PREVIEW_MAX_PAGES = max(
                self.APPSPEC_PREVIEW_TARGET_PAGES,
                int(os.getenv("APPSPEC_PREVIEW_MAX_PAGES", "10")),
            )
        except ValueError:
            self.APPSPEC_PREVIEW_MAX_PAGES = max(
                self.APPSPEC_PREVIEW_TARGET_PAGES, 10
            )
        # Quality bar: critics ON by default so thin/placeholder pages get refined.
        # Set PREVIEW_SKIP_CRITIC=true only for fast local iteration.
        self.PREVIEW_SKIP_CRITIC = os.getenv("PREVIEW_SKIP_CRITIC", "false").strip().lower() in (
            "1", "true", "yes", "on",
        )
        try:
            self.PREVIEW_PARALLEL_WORKERS = max(1, int(os.getenv("PREVIEW_PARALLEL_WORKERS", "4")))
        except ValueError:
            self.PREVIEW_PARALLEL_WORKERS = 4
        try:
            # Cap how many AI-authored files we generate (keeps live demos under ~10–15 min).
            self.PREVIEW_MAX_FILES = max(6, int(os.getenv("PREVIEW_MAX_FILES", "40")))
        except ValueError:
            self.PREVIEW_MAX_FILES = 40
        try:
            self.PREVIEW_MAX_BUILD_FIX_ATTEMPTS = max(1, int(os.getenv("PREVIEW_MAX_BUILD_FIX_ATTEMPTS", "6")))
        except ValueError:
            self.PREVIEW_MAX_BUILD_FIX_ATTEMPTS = 6
        try:
            self.PREVIEW_MAX_FIX_LOOP_SECONDS = max(60, int(os.getenv("PREVIEW_MAX_FIX_LOOP_SECONDS", "900")))
        except ValueError:
            self.PREVIEW_MAX_FIX_LOOP_SECONDS = 900
        try:
            self.PREVIEW_MAX_AI_CALLS = max(1, int(os.getenv("PREVIEW_MAX_AI_CALLS", "96")))
        except ValueError:
            self.PREVIEW_MAX_AI_CALLS = 96

        # Post-build visual critique (screenshot + vision) — ON by default for
        # demo quality. Skip with PREVIEW_SKIP_VISUAL_CRITIC=true for speed.
        self.PREVIEW_SKIP_VISUAL_CRITIC = os.getenv(
            "PREVIEW_SKIP_VISUAL_CRITIC", "false"
        ).strip().lower() in ("1", "true", "yes", "on")
        # Catalogue pages: emit deterministic scaffold first (reliable compile +
        # AppSpec hooks), optionally AI-fill slot copy once. Default ON.
        self.PREVIEW_SCAFFOLD_FIRST = os.getenv(
            "PREVIEW_SCAFFOLD_FIRST", "true"
        ).strip().lower() in ("1", "true", "yes", "on")
        self.PREVIEW_SCAFFOLD_SLOT_FILL = os.getenv(
            "PREVIEW_SCAFFOLD_SLOT_FILL", "true"
        ).strip().lower() in ("1", "true", "yes", "on")
        # Internal-only address Playwright uses to reach this same server's
        # already-running preview-app route — never exposed to end users,
        # unrelated to any public base URL / CORS setting.
        self.INTERNAL_BASE_URL = os.getenv("INTERNAL_BASE_URL", "http://localhost:8000").rstrip("/")
        static_dir = (os.getenv("STATIC_DIR") or "").strip()
        self.STATIC_DIR = Path(static_dir) if static_dir else None
        self.CORS_ORIGINS = os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://localhost:5175,http://127.0.0.1:5175",
        )
        self.UVICORN_RELOAD = os.getenv("UVICORN_RELOAD", "false").strip().lower() in (
            "1", "true", "yes", "on",
        )
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "debug").strip().lower()

    @property
    def TEMPLATES_DIR(self) -> Path:
        return self.BASE_DIR / "templates"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


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
