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
    # Auto-create / promote this user on boot (no manual SQL). Empty = skip.
    ADMIN_EMAIL: str = (os.getenv("ADMIN_EMAIL") or "roy.rizkallah@hotmail.com").strip()
    ADMIN_NAME: str = (os.getenv("ADMIN_NAME") or "Roy").strip()
    # Account password for ADMIN_EMAIL. Falls back to ADMIN_PASSWORD when blank.
    ADMIN_USER_PASSWORD: str = (os.getenv("ADMIN_USER_PASSWORD") or "").strip()
    # Keep bootstrap account password in sync with env on every boot.
    ADMIN_SYNC_PASSWORD: bool = os.getenv("ADMIN_SYNC_PASSWORD", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    # Optional Discord/Slack/generic webhook for admin alerts (POST JSON).
    ADMIN_ALERT_WEBHOOK_URL: str = (os.getenv("ADMIN_ALERT_WEBHOOK_URL") or "").strip()

    # PlateSync demo seed on boot. Default OFF so Coolify/prod redeploys never
    # wipe or replace real customer builds. Opt in explicitly for local demos.
    SEED_DEMO: bool = os.getenv("SEED_DEMO", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

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
    OPENROUTER_SITE_URL: str

    # Pexels — per-business preview stock photos (optional; curated fallback if empty)
    PEXELS_API_KEY: str = (os.getenv("PEXELS_API_KEY") or "").strip()

    # Preview app build paths
    PREVIEW_TEMPLATE_DIR: Path
    PREVIEW_APPS_DIR: Path
    PREVIEW_CANDIDATES_DIR: Path
    PREVIEW_VALIDATIONS_DIR: Path

    # Model names (resolved below, provider-dependent)
    TEXT_MODEL: str
    VISION_MODEL: str
    CODER_MODEL: str
    HTML_MODEL: str
    PREVIEW_APP_MODEL: str
    ARCHITECT_MODEL: str
    CRITIC_MODEL: str
    FIX_MODEL: str
    QUALITY_FIX_MODEL: str
    APPSPEC_MODEL: str
    APPSPEC_REPAIR_MODEL: str
    APPSPEC_COVERAGE_MODEL: str
    APPSPEC_V2_COVERAGE_MODEL: str
    APPSPEC_MODE: str
    APPSPEC_SCHEMA_VERSION: str
    APPSPEC_PROMPT_REVISION: str
    APPSPEC_MAX_CALLS: int
    APPSPEC_MAX_REPAIR_ATTEMPTS: int
    APPSPEC_MAX_DETERMINISTIC_HEALS: int
    APPSPEC_FALLBACK_ENABLED: bool
    APPSPEC_MAX_TOKENS: int
    APPSPEC_REPAIR_MAX_TOKENS: int
    APPSPEC_COVERAGE_MAX_TOKENS: int
    APPSPEC_MIN_COVERAGE_SCORE: int
    APPSPEC_PREVIEW_TARGET_PAGES: int
    APPSPEC_PREVIEW_MAX_PAGES: int
    V2_PRODUCT_STRATEGY_MODEL: str
    V2_INFORMATION_ARCHITECTURE_MODEL: str
    V2_DESIGN_DNA_MODEL: str
    V2_DESIGN_DNA_VISION_MODEL: str
    V2_PRODUCT_STRATEGY_PROMPT_REVISION: str
    V2_INFORMATION_ARCHITECTURE_PROMPT_REVISION: str
    V2_DESIGN_DNA_PROMPT_REVISION: str
    V2_PRODUCT_STRATEGY_MAX_TOKENS: int
    V2_INFORMATION_ARCHITECTURE_MAX_TOKENS: int
    V2_DESIGN_DNA_MAX_TOKENS: int
    V2_DESIGN_STAGE_MAX_ATTEMPTS: int
    V2_PRODUCT_STRATEGY_TIMEOUT_SECONDS: int
    V2_INFORMATION_ARCHITECTURE_TIMEOUT_SECONDS: int
    V2_DESIGN_DNA_TIMEOUT_SECONDS: int
    V2_DESIGN_CONTRACT_TIMEOUT_SECONDS: int
    V2_DESIGN_CONTRACT_MAX_COST_USD: float
    V2_BUSINESS_COMPONENT_MODEL: str
    V2_CONTENT_DATA_MODEL: str
    V2_BUSINESS_COMPONENT_PROMPT_REVISION: str
    V2_CONTENT_DATA_PROMPT_REVISION: str
    V2_BUSINESS_COMPONENT_MAX_TOKENS: int
    V2_CONTENT_DATA_MAX_TOKENS: int
    V2_COMPOSITION_AI_STAGE_MAX_ATTEMPTS: int
    V2_BUSINESS_COMPONENT_TIMEOUT_SECONDS: int
    V2_CONTENT_DATA_TIMEOUT_SECONDS: int
    V2_COMPOSITION_CONTRACT_TIMEOUT_SECONDS: int
    V2_COMPOSITION_CONTRACT_MAX_CALLS: int
    V2_COMPOSITION_CONTRACT_MAX_COST_USD: float
    V2_CANDIDATE_POLICY_REVISION: str
    V2_CANDIDATE_COMPONENT_MODEL: str
    V2_CANDIDATE_PAGE_MODEL: str
    V2_CANDIDATE_REPAIR_MODEL: str
    V2_CANDIDATE_COMPONENT_PROMPT_REVISION: str
    V2_CANDIDATE_PAGE_PROMPT_REVISION: str
    V2_CANDIDATE_REPAIR_PROMPT_REVISION: str
    V2_CANDIDATE_COMPONENT_MAX_TOKENS: int
    V2_CANDIDATE_PAGE_MAX_TOKENS: int
    V2_CANDIDATE_REPAIR_MAX_TOKENS: int
    V2_CANDIDATE_COMPONENT_TIMEOUT_SECONDS: int
    V2_CANDIDATE_PAGE_TIMEOUT_SECONDS: int
    V2_CANDIDATE_REPAIR_TIMEOUT_SECONDS: int
    V2_CANDIDATE_TIMEOUT_SECONDS: int
    V2_CANDIDATE_MAX_CALLS: int
    V2_CANDIDATE_MAX_COST_USD: float
    V2_RUNTIME_VALIDATION_ENABLED: bool
    V2_RUNTIME_POLICY_REVISION: str
    V2_RUNTIME_TYPESCRIPT_TIMEOUT_SECONDS: int
    V2_RUNTIME_VITE_BUILD_TIMEOUT_SECONDS: int
    V2_RUNTIME_BUILD_TIMEOUT_SECONDS: int
    V2_RUNTIME_SERVER_TIMEOUT_SECONDS: int
    V2_RUNTIME_ROUTE_TIMEOUT_SECONDS: int
    V2_RUNTIME_JOURNEY_TIMEOUT_SECONDS: int
    V2_RUNTIME_ACCESSIBILITY_TIMEOUT_SECONDS: int
    V2_RUNTIME_SCREENSHOT_TIMEOUT_SECONDS: int
    V2_RUNTIME_PHASE_TIMEOUT_SECONDS: int
    V2_RUNTIME_MAX_BROWSER_CONTEXTS: int
    V2_RUNTIME_MAX_BROWSER_PAGES: int
    V2_RUNTIME_MAX_CONSOLE_DIAGNOSTICS: int
    V2_RUNTIME_MAX_NETWORK_DIAGNOSTICS: int
    V2_RUNTIME_MAX_COMMAND_OUTPUT_BYTES: int
    V2_RUNTIME_MAX_DETERMINISTIC_REPAIRS: int
    V2_RUNTIME_MAX_DIST_BYTES: int
    V2_RUNTIME_MAX_JAVASCRIPT_BYTES: int
    V2_RUNTIME_MAX_CSS_BYTES: int
    V2_RUNTIME_MAX_DIST_FILES: int
    V2_RUNTIME_MAX_SOURCE_MAPS: int
    V2_VISUAL_EVALUATION_ENABLED: bool
    V2_VISUAL_POLICY_REVISION: str
    V2_VISUAL_CRITIC_MODEL: str
    V2_VISUAL_REVIEWER_MODEL: str
    V2_VISUAL_REFINEMENT_MODEL: str
    V2_VISUAL_TECHNICAL_REPAIR_MODEL: str
    V2_VISUAL_ECONOMY_FALLBACK_MODEL: str
    V2_VISUAL_ECONOMY_FALLBACK_ENABLED: bool
    V2_VISUAL_CRITIC_PROMPT_REVISION: str
    V2_VISUAL_REVIEWER_PROMPT_REVISION: str
    V2_VISUAL_REFINEMENT_PROMPT_REVISION: str
    V2_VISUAL_TECHNICAL_REPAIR_PROMPT_REVISION: str
    V2_VISUAL_CRITIC_MAX_TOKENS: int
    V2_VISUAL_REVIEWER_MAX_TOKENS: int
    V2_VISUAL_REFINEMENT_MAX_TOKENS: int
    V2_VISUAL_TECHNICAL_REPAIR_MAX_TOKENS: int
    V2_VISUAL_CRITIC_TIMEOUT_SECONDS: int
    V2_VISUAL_REVIEWER_TIMEOUT_SECONDS: int
    V2_VISUAL_REFINEMENT_TIMEOUT_SECONDS: int
    V2_VISUAL_TECHNICAL_REPAIR_TIMEOUT_SECONDS: int
    V2_VISUAL_PHASE_TIMEOUT_SECONDS: int
    V2_VISUAL_MAX_OUTPUT_TOKENS: int
    V2_VISUAL_MAX_CALLS: int
    V2_VISUAL_MAX_COST_USD: float
    PREVIEW_SKIP_CRITIC: bool
    PREVIEW_PARALLEL_WORKERS: int
    PREVIEW_MAX_FILES: int
    PREVIEW_MAX_BUILD_FIX_ATTEMPTS: int
    PREVIEW_MAX_FIX_LOOP_SECONDS: int
    PREVIEW_MAX_AI_CALLS: int
    PREVIEW_QUALITY_AI_REPAIR: bool
    PREVIEW_MAX_QUALITY_FIX_ATTEMPTS: int
    PREVIEW_SKIP_VISUAL_CRITIC: bool
    PREVIEW_SCAFFOLD_FIRST: bool
    PREVIEW_SCAFFOLD_SLOT_FILL: bool
    PREVIEW_GENERATOR_V2: bool
    INTERNAL_BASE_URL: str
    STATIC_DIR: Path | None
    CORS_ORIGINS: str
    UVICORN_RELOAD: bool
    LOG_LEVEL: str
    SITE_CHAT_ENABLED: bool
    SITE_CHAT_MODEL: str

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
        self.PREVIEW_CANDIDATES_DIR = Path(
            os.getenv(
                "PREVIEW_CANDIDATES_DIR",
                str(Path(self.UPLOAD_DIR) / "preview-candidates"),
            )
        )
        self.PREVIEW_VALIDATIONS_DIR = Path(
            os.getenv(
                "PREVIEW_VALIDATIONS_DIR",
                str(self.PREVIEW_TEMPLATE_DIR / ".runtime-validation"),
            )
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
        # Quality-gate dynamic repair (agentic coding). Prefer a strong coder;
        # default follows FIX_MODEL (set QUALITY_FIX_MODEL=z-ai/glm-5.2 to try GLM).
        self.QUALITY_FIX_MODEL = _env_or("QUALITY_FIX_MODEL", self.FIX_MODEL)

        # Canonical product contract toggle:
        # - off: skip AppSpec
        # - shadow: author/validate but do not block preview on failure
        # - on: enforce AppSpec (legacy aliases map here)
        requested_appspec_mode = os.getenv("APPSPEC_MODE", "off").strip().lower()
        if requested_appspec_mode == "shadow":
            self.APPSPEC_MODE = "shadow"
        elif requested_appspec_mode in {
            "on",
            "required_new",
            "required",
            "true",
            "1",
            "yes",
            "enabled",
        }:
            self.APPSPEC_MODE = "on"
        else:
            self.APPSPEC_MODE = "off"
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
        # v2 validates that this reviewer belongs to a different model family
        # before it makes any provider call. v1 continues using the legacy
        # APPSPEC_COVERAGE_MODEL setting above.
        self.APPSPEC_V2_COVERAGE_MODEL = _env_or(
            "APPSPEC_V2_COVERAGE_MODEL", self.CRITIC_MODEL
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
            self.APPSPEC_MAX_DETERMINISTIC_HEALS = max(
                0, int(os.getenv("APPSPEC_MAX_DETERMINISTIC_HEALS", "4"))
            )
        except ValueError:
            self.APPSPEC_MAX_DETERMINISTIC_HEALS = 4
        # When AI author/repair cannot clear gates, accept a minimal valid
        # fallback AppSpec so preview generation stays unblocked.
        self.APPSPEC_FALLBACK_ENABLED = os.getenv(
            "APPSPEC_FALLBACK_ENABLED", "true"
        ).strip().lower() in {"1", "true", "yes", "on"}
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
        self.V2_PRODUCT_STRATEGY_MODEL = _env_or(
            "V2_PRODUCT_STRATEGY_MODEL",
            self.PREVIEW_APP_MODEL,
        )
        self.V2_INFORMATION_ARCHITECTURE_MODEL = _env_or(
            "V2_INFORMATION_ARCHITECTURE_MODEL",
            self.APPSPEC_MODEL,
        )
        self.V2_DESIGN_DNA_MODEL = _env_or(
            "V2_DESIGN_DNA_MODEL",
            self.QUALITY_FIX_MODEL,
        )
        self.V2_DESIGN_DNA_VISION_MODEL = _env_or(
            "V2_DESIGN_DNA_VISION_MODEL",
            self.VISION_MODEL,
        )
        self.V2_PRODUCT_STRATEGY_PROMPT_REVISION = (
            os.getenv(
                "V2_PRODUCT_STRATEGY_PROMPT_REVISION",
                "2026-07-24.1",
            ).strip()
            or "2026-07-24.1"
        )
        self.V2_INFORMATION_ARCHITECTURE_PROMPT_REVISION = (
            os.getenv(
                "V2_INFORMATION_ARCHITECTURE_PROMPT_REVISION",
                "2026-07-24.1",
            ).strip()
            or "2026-07-24.1"
        )
        self.V2_DESIGN_DNA_PROMPT_REVISION = (
            os.getenv(
                "V2_DESIGN_DNA_PROMPT_REVISION",
                "2026-07-24.1",
            ).strip()
            or "2026-07-24.1"
        )
        try:
            self.V2_PRODUCT_STRATEGY_MAX_TOKENS = max(
                1000,
                int(os.getenv("V2_PRODUCT_STRATEGY_MAX_TOKENS", "4500")),
            )
        except ValueError:
            self.V2_PRODUCT_STRATEGY_MAX_TOKENS = 4500
        try:
            self.V2_INFORMATION_ARCHITECTURE_MAX_TOKENS = max(
                2000,
                int(
                    os.getenv(
                        "V2_INFORMATION_ARCHITECTURE_MAX_TOKENS",
                        "9000",
                    )
                ),
            )
        except ValueError:
            self.V2_INFORMATION_ARCHITECTURE_MAX_TOKENS = 9000
        try:
            self.V2_DESIGN_DNA_MAX_TOKENS = max(
                1000,
                int(os.getenv("V2_DESIGN_DNA_MAX_TOKENS", "5000")),
            )
        except ValueError:
            self.V2_DESIGN_DNA_MAX_TOKENS = 5000
        try:
            self.V2_DESIGN_STAGE_MAX_ATTEMPTS = min(
                2,
                max(
                    1,
                    int(os.getenv("V2_DESIGN_STAGE_MAX_ATTEMPTS", "2")),
                ),
            )
        except ValueError:
            self.V2_DESIGN_STAGE_MAX_ATTEMPTS = 2
        for field_name, default in (
            ("V2_PRODUCT_STRATEGY_TIMEOUT_SECONDS", 90),
            ("V2_INFORMATION_ARCHITECTURE_TIMEOUT_SECONDS", 120),
            ("V2_DESIGN_DNA_TIMEOUT_SECONDS", 120),
            ("V2_DESIGN_CONTRACT_TIMEOUT_SECONDS", 300),
        ):
            try:
                value = max(10, int(os.getenv(field_name, str(default))))
            except ValueError:
                value = default
            setattr(self, field_name, value)
        try:
            self.V2_DESIGN_CONTRACT_MAX_COST_USD = max(
                0.01,
                float(os.getenv("V2_DESIGN_CONTRACT_MAX_COST_USD", "0.25")),
            )
        except ValueError:
            self.V2_DESIGN_CONTRACT_MAX_COST_USD = 0.25
        self.V2_BUSINESS_COMPONENT_MODEL = _env_or(
            "V2_BUSINESS_COMPONENT_MODEL",
            self.PREVIEW_APP_MODEL,
        )
        self.V2_CONTENT_DATA_MODEL = _env_or(
            "V2_CONTENT_DATA_MODEL",
            self.CODER_MODEL,
        )
        self.V2_BUSINESS_COMPONENT_PROMPT_REVISION = (
            os.getenv(
                "V2_BUSINESS_COMPONENT_PROMPT_REVISION",
                "2026-07-24.1",
            ).strip()
            or "2026-07-24.1"
        )
        self.V2_CONTENT_DATA_PROMPT_REVISION = (
            os.getenv(
                "V2_CONTENT_DATA_PROMPT_REVISION",
                "2026-07-24.1",
            ).strip()
            or "2026-07-24.1"
        )
        try:
            self.V2_BUSINESS_COMPONENT_MAX_TOKENS = max(
                2000,
                int(
                    os.getenv(
                        "V2_BUSINESS_COMPONENT_MAX_TOKENS",
                        "8000",
                    )
                ),
            )
        except ValueError:
            self.V2_BUSINESS_COMPONENT_MAX_TOKENS = 8000
        try:
            self.V2_CONTENT_DATA_MAX_TOKENS = max(
                2000,
                int(os.getenv("V2_CONTENT_DATA_MAX_TOKENS", "10000")),
            )
        except ValueError:
            self.V2_CONTENT_DATA_MAX_TOKENS = 10000
        try:
            self.V2_COMPOSITION_AI_STAGE_MAX_ATTEMPTS = min(
                2,
                max(
                    1,
                    int(
                        os.getenv(
                            "V2_COMPOSITION_AI_STAGE_MAX_ATTEMPTS",
                            "2",
                        )
                    ),
                ),
            )
        except ValueError:
            self.V2_COMPOSITION_AI_STAGE_MAX_ATTEMPTS = 2
        for field_name, default in (
            ("V2_BUSINESS_COMPONENT_TIMEOUT_SECONDS", 120),
            ("V2_CONTENT_DATA_TIMEOUT_SECONDS", 120),
            ("V2_COMPOSITION_CONTRACT_TIMEOUT_SECONDS", 240),
        ):
            try:
                value = max(10, int(os.getenv(field_name, str(default))))
            except ValueError:
                value = default
            setattr(self, field_name, value)
        try:
            self.V2_COMPOSITION_CONTRACT_MAX_CALLS = min(
                4,
                max(
                    2,
                    int(
                        os.getenv(
                            "V2_COMPOSITION_CONTRACT_MAX_CALLS",
                            "4",
                        )
                    ),
                ),
            )
        except ValueError:
            self.V2_COMPOSITION_CONTRACT_MAX_CALLS = 4
        try:
            self.V2_COMPOSITION_CONTRACT_MAX_COST_USD = max(
                0.01,
                float(
                    os.getenv(
                        "V2_COMPOSITION_CONTRACT_MAX_COST_USD",
                        "0.20",
                    )
                ),
            )
        except ValueError:
            self.V2_COMPOSITION_CONTRACT_MAX_COST_USD = 0.20
        self.V2_CANDIDATE_POLICY_REVISION = (
            os.getenv(
                "V2_CANDIDATE_POLICY_REVISION",
                "2026-07-24.1",
            ).strip()
            or "2026-07-24.1"
        )
        self.V2_CANDIDATE_COMPONENT_MODEL = _env_or(
            "V2_CANDIDATE_COMPONENT_MODEL",
            self.PREVIEW_APP_MODEL,
        )
        self.V2_CANDIDATE_PAGE_MODEL = _env_or(
            "V2_CANDIDATE_PAGE_MODEL",
            self.PREVIEW_APP_MODEL,
        )
        self.V2_CANDIDATE_REPAIR_MODEL = _env_or(
            "V2_CANDIDATE_REPAIR_MODEL",
            self.FIX_MODEL,
        )
        self.V2_CANDIDATE_COMPONENT_PROMPT_REVISION = (
            os.getenv(
                "V2_CANDIDATE_COMPONENT_PROMPT_REVISION",
                "2026-07-24.1",
            ).strip()
            or "2026-07-24.1"
        )
        self.V2_CANDIDATE_PAGE_PROMPT_REVISION = (
            os.getenv(
                "V2_CANDIDATE_PAGE_PROMPT_REVISION",
                "2026-07-24.1",
            ).strip()
            or "2026-07-24.1"
        )
        self.V2_CANDIDATE_REPAIR_PROMPT_REVISION = (
            os.getenv(
                "V2_CANDIDATE_REPAIR_PROMPT_REVISION",
                "2026-07-24.1",
            ).strip()
            or "2026-07-24.1"
        )
        for field_name, default, minimum, maximum in (
            ("V2_CANDIDATE_COMPONENT_MAX_TOKENS", 24000, 4000, 32000),
            ("V2_CANDIDATE_PAGE_MAX_TOKENS", 32000, 4000, 48000),
            ("V2_CANDIDATE_REPAIR_MAX_TOKENS", 10000, 2000, 12000),
        ):
            try:
                value = min(
                    maximum,
                    max(minimum, int(os.getenv(field_name, str(default)))),
                )
            except ValueError:
                value = default
            setattr(self, field_name, value)
        for field_name, default, maximum in (
            ("V2_CANDIDATE_COMPONENT_TIMEOUT_SECONDS", 240, 240),
            ("V2_CANDIDATE_PAGE_TIMEOUT_SECONDS", 300, 300),
            ("V2_CANDIDATE_REPAIR_TIMEOUT_SECONDS", 150, 150),
            ("V2_CANDIDATE_TIMEOUT_SECONDS", 600, 600),
        ):
            try:
                value = min(
                    maximum,
                    max(10, int(os.getenv(field_name, str(default)))),
                )
            except ValueError:
                value = default
            setattr(self, field_name, value)
        try:
            self.V2_CANDIDATE_MAX_CALLS = min(
                4,
                max(
                    2,
                    int(os.getenv("V2_CANDIDATE_MAX_CALLS", "4")),
                ),
            )
        except ValueError:
            self.V2_CANDIDATE_MAX_CALLS = 4
        try:
            self.V2_CANDIDATE_MAX_COST_USD = max(
                0.01,
                float(os.getenv("V2_CANDIDATE_MAX_COST_USD", "0.25")),
            )
        except ValueError:
            self.V2_CANDIDATE_MAX_COST_USD = 0.25
        self.V2_RUNTIME_VALIDATION_ENABLED = os.getenv(
            "V2_RUNTIME_VALIDATION_ENABLED",
            "false",
        ).strip().lower() in ("1", "true", "yes", "on")
        self.V2_RUNTIME_POLICY_REVISION = (
            os.getenv(
                "V2_RUNTIME_POLICY_REVISION",
                "2026-07-24.1",
            ).strip()
            or "2026-07-24.1"
        )
        runtime_integer_settings = (
            ("V2_RUNTIME_TYPESCRIPT_TIMEOUT_SECONDS", 90, 1, 600),
            ("V2_RUNTIME_VITE_BUILD_TIMEOUT_SECONDS", 120, 1, 600),
            ("V2_RUNTIME_BUILD_TIMEOUT_SECONDS", 180, 1, 1200),
            ("V2_RUNTIME_SERVER_TIMEOUT_SECONDS", 20, 1, 120),
            ("V2_RUNTIME_ROUTE_TIMEOUT_SECONDS", 15, 1, 120),
            ("V2_RUNTIME_JOURNEY_TIMEOUT_SECONDS", 30, 1, 180),
            ("V2_RUNTIME_ACCESSIBILITY_TIMEOUT_SECONDS", 15, 1, 120),
            ("V2_RUNTIME_SCREENSHOT_TIMEOUT_SECONDS", 10, 1, 120),
            ("V2_RUNTIME_PHASE_TIMEOUT_SECONDS", 600, 1, 3600),
            ("V2_RUNTIME_MAX_BROWSER_CONTEXTS", 2, 1, 8),
            ("V2_RUNTIME_MAX_BROWSER_PAGES", 2, 1, 8),
            ("V2_RUNTIME_MAX_CONSOLE_DIAGNOSTICS", 100, 1, 1000),
            ("V2_RUNTIME_MAX_NETWORK_DIAGNOSTICS", 100, 1, 1000),
            ("V2_RUNTIME_MAX_COMMAND_OUTPUT_BYTES", 65536, 1024, 1048576),
            ("V2_RUNTIME_MAX_DETERMINISTIC_REPAIRS", 1, 0, 1),
            ("V2_RUNTIME_MAX_DIST_BYTES", 5242880, 1, 104857600),
            ("V2_RUNTIME_MAX_JAVASCRIPT_BYTES", 2097152, 1, 52428800),
            ("V2_RUNTIME_MAX_CSS_BYTES", 524288, 1, 10485760),
            ("V2_RUNTIME_MAX_DIST_FILES", 200, 1, 2000),
            ("V2_RUNTIME_MAX_SOURCE_MAPS", 0, 0, 100),
        )
        for field_name, default, minimum, maximum in runtime_integer_settings:
            try:
                value = min(
                    maximum,
                    max(minimum, int(os.getenv(field_name, str(default)))),
                )
            except ValueError:
                value = default
            setattr(self, field_name, value)
        self.V2_VISUAL_EVALUATION_ENABLED = os.getenv(
            "V2_VISUAL_EVALUATION_ENABLED",
            "false",
        ).strip().lower() in ("1", "true", "yes", "on")
        self.V2_VISUAL_POLICY_REVISION = (
            os.getenv("V2_VISUAL_POLICY_REVISION", "2026-07-24.1").strip()
            or "2026-07-24.1"
        )
        self.V2_VISUAL_CRITIC_MODEL = _env_or(
            "V2_VISUAL_CRITIC_MODEL",
            "openai/gpt-4o",
        )
        self.V2_VISUAL_REVIEWER_MODEL = _env_or(
            "V2_VISUAL_REVIEWER_MODEL",
            "google/gemini-2.5-flash",
        )
        self.V2_VISUAL_REFINEMENT_MODEL = _env_or(
            "V2_VISUAL_REFINEMENT_MODEL",
            "openai/gpt-4o",
        )
        self.V2_VISUAL_TECHNICAL_REPAIR_MODEL = _env_or(
            "V2_VISUAL_TECHNICAL_REPAIR_MODEL",
            "deepseek/deepseek-v4-pro",
        )
        self.V2_VISUAL_ECONOMY_FALLBACK_MODEL = _env_or(
            "V2_VISUAL_ECONOMY_FALLBACK_MODEL",
            "meta-llama/llama-3.2-11b-vision-instruct",
        )
        self.V2_VISUAL_ECONOMY_FALLBACK_ENABLED = os.getenv(
            "V2_VISUAL_ECONOMY_FALLBACK_ENABLED",
            "false",
        ).strip().lower() in ("1", "true", "yes", "on")
        for field_name in (
            "V2_VISUAL_CRITIC_PROMPT_REVISION",
            "V2_VISUAL_REVIEWER_PROMPT_REVISION",
            "V2_VISUAL_REFINEMENT_PROMPT_REVISION",
            "V2_VISUAL_TECHNICAL_REPAIR_PROMPT_REVISION",
        ):
            setattr(
                self,
                field_name,
                os.getenv(field_name, "2026-07-24.1").strip()
                or "2026-07-24.1",
            )
        visual_integer_settings = (
            ("V2_VISUAL_CRITIC_MAX_TOKENS", 12000, 1000, 20000),
            ("V2_VISUAL_REVIEWER_MAX_TOKENS", 10000, 1000, 18000),
            ("V2_VISUAL_REFINEMENT_MAX_TOKENS", 12000, 1000, 20000),
            ("V2_VISUAL_TECHNICAL_REPAIR_MAX_TOKENS", 8000, 1000, 12000),
            ("V2_VISUAL_CRITIC_TIMEOUT_SECONDS", 150, 1, 150),
            ("V2_VISUAL_REVIEWER_TIMEOUT_SECONDS", 120, 1, 120),
            ("V2_VISUAL_REFINEMENT_TIMEOUT_SECONDS", 240, 1, 240),
            ("V2_VISUAL_TECHNICAL_REPAIR_TIMEOUT_SECONDS", 150, 1, 150),
            ("V2_VISUAL_PHASE_TIMEOUT_SECONDS", 1200, 1, 1200),
            ("V2_VISUAL_MAX_OUTPUT_TOKENS", 42000, 1000, 42000),
            ("V2_VISUAL_MAX_CALLS", 6, 2, 6),
        )
        for field_name, default, minimum, maximum in visual_integer_settings:
            try:
                value = min(
                    maximum,
                    max(minimum, int(os.getenv(field_name, str(default)))),
                )
            except ValueError:
                value = default
            setattr(self, field_name, value)
        try:
            self.V2_VISUAL_MAX_COST_USD = min(
                1.50,
                max(
                    0.01,
                    float(os.getenv("V2_VISUAL_MAX_COST_USD", "1.50")),
                ),
            )
        except ValueError:
            self.V2_VISUAL_MAX_COST_USD = 1.50
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
        # After deterministic quality heals fail, let a sandboxed AI repair try.
        self.PREVIEW_QUALITY_AI_REPAIR = os.getenv(
            "PREVIEW_QUALITY_AI_REPAIR", "true"
        ).strip().lower() in ("1", "true", "yes", "on")
        try:
            self.PREVIEW_MAX_QUALITY_FIX_ATTEMPTS = max(
                0, int(os.getenv("PREVIEW_MAX_QUALITY_FIX_ATTEMPTS", "2"))
            )
        except ValueError:
            self.PREVIEW_MAX_QUALITY_FIX_ATTEMPTS = 2

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
        # Phase-gated preview-generator boundary. The legacy v1 path remains
        # the default until a later phase is explicitly enabled.
        self.PREVIEW_GENERATOR_V2 = os.getenv(
            "PREVIEW_GENERATOR_V2", "false"
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
        # OpenRouter HTTP-Referer — use live https://DOMAIN on Hostinger
        site = (os.getenv("OPENROUTER_SITE_URL") or "").strip()
        if not site:
            site = (self.CORS_ORIGINS.split(",")[0] if self.CORS_ORIGINS else "").strip()
        if not site.startswith("http"):
            site = "https://buildmyversion.ai"
        self.OPENROUTER_SITE_URL = site
        self.UVICORN_RELOAD = os.getenv("UVICORN_RELOAD", "false").strip().lower() in (
            "1", "true", "yes", "on",
        )
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "debug").strip().lower()
        # Public site guide bot — default cheapest OpenRouter free router
        self.SITE_CHAT_ENABLED = os.getenv("SITE_CHAT_ENABLED", "true").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        chat_default = (
            "openrouter/free"
            if self.AI_PROVIDER == "openrouter"
            else defaults["text"]
        )
        self.SITE_CHAT_MODEL = _env_or("SITE_CHAT_MODEL", chat_default)

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
