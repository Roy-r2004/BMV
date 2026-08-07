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
_INITIAL_ENV_KEYS = frozenset(os.environ)
# Prefer backend/.env (compose env_file + local).
load_dotenv(_APP_DIR.parent / ".env")
load_dotenv()

_TRUE_BOOLEAN_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_BOOLEAN_VALUES = frozenset({"0", "false", "no", "off"})


def _parse_strict_bool(
    raw: str | None,
    *,
    default: bool = False,
) -> tuple[bool, bool]:
    """Parse a boolean without treating arbitrary non-empty strings as true.

    Returns ``(value, valid)``. Unset and blank values use the supplied
    fail-closed default. Malformed values resolve false and are marked invalid
    so startup/readiness can surface the configuration error.
    """

    if raw is None or not raw.strip():
        return default, True
    normalized = raw.strip().lower()
    if normalized in _TRUE_BOOLEAN_VALUES:
        return True, True
    if normalized in _FALSE_BOOLEAN_VALUES:
        return False, True
    return False, False


def _dotenv_defines(path: Path, name: str) -> bool:
    """Return whether a dotenv file defines a key without reading its value."""

    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            if stripped.split("=", 1)[0].strip() == name:
                return True
    except OSError:
        return False
    return False


def _configuration_source(name: str) -> str:
    """Describe the winning configuration layer without exposing values."""

    if name in _INITIAL_ENV_KEYS:
        return "process_environment"
    backend_dotenv = _APP_DIR.parent / ".env"
    if _dotenv_defines(backend_dotenv, name):
        return "backend_dotenv"
    cwd_dotenv = Path.cwd() / ".env"
    if cwd_dotenv != backend_dotenv and _dotenv_defines(cwd_dotenv, name):
        return "cwd_dotenv"
    return "source_default"


def _environment_classification() -> str:
    raw = (
        os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or os.getenv("ENV") or ""
    ).strip().lower()
    if raw in {"production", "prod"}:
        return "production"
    if raw in {"staging", "stage"}:
        return "staging"
    if raw in {"test", "testing"}:
        return "test"
    if raw in {"development", "dev", "local", ""}:
        return "development"
    return "other"


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
    PREVIEW_APP_MODEL: str
    PREVIEW_APP_TRANSPORT_FALLBACK_MODEL: str
    ARCHITECT_MODEL: str
    CRITIC_MODEL: str
    FIX_MODEL: str
    QUALITY_FIX_MODEL: str
    APPSPEC_MODEL: str
    APPSPEC_REPAIR_MODEL: str
    APPSPEC_TRANSPORT_FALLBACK_MODEL: str
    APPSPEC_COVERAGE_MODEL: str
    APPSPEC_V2_COVERAGE_MODEL: str
    APPSPEC_MODE: str
    APPSPEC_SCHEMA_VERSION: str
    APPSPEC_PROMPT_REVISION: str
    APPSPEC_MAX_CALLS: int
    APPSPEC_DOWNSTREAM_RESERVE_SECONDS: float
    APPSPEC_MAX_REPAIR_ATTEMPTS: int
    APPSPEC_MAX_SCHEMA_REPAIR_ATTEMPTS: int
    APPSPEC_MAX_DETERMINISTIC_HEALS: int
    APPSPEC_FALLBACK_ENABLED: bool
    APPSPEC_FALLBACK_CONFIG_SOURCE: str
    APPSPEC_FALLBACK_CONFIG_VALID: bool
    APPSPEC_FALLBACK_SAFETY_CODE: str
    APP_ENVIRONMENT_CLASSIFICATION: str
    APPSPEC_MAX_TOKENS: int
    APPSPEC_REPAIR_MAX_TOKENS: int
    APPSPEC_COVERAGE_MAX_TOKENS: int
    APPSPEC_MIN_COVERAGE_SCORE: int
    APPSPEC_PREVIEW_TARGET_PAGES: int
    APPSPEC_PREVIEW_MAX_PAGES: int
    V2_PHASE7_ROLLOUT_ENABLED: bool
    V2_PHASE7_SHADOW_ENABLED: bool
    V2_PHASE7_PROMOTE_ENABLED: bool
    V2_PHASE7_ROLLOUT_PERCENT: int
    V2_PHASE7_REQUEST_ALLOWLIST: tuple[int, ...]
    V2_PHASE7_CIRCUIT_BREAKER_ENABLED: bool
    V2_PHASE7_AUTO_ROLLBACK_ENABLED: bool
    V2_PHASE7_AUTO_ROLLBACK_LOOKBACK_SECONDS: int
    V2_PHASE7_BREAKER_EVAL_MAX_REQUESTS: int
    V2_PHASE7_OPS_DASHBOARD_ENABLED: bool
    V2_PHASE7_OPS_ALERTS_ENABLED: bool
    V2_PHASE7_OPS_ALERT_LOOKBACK_SECONDS: int
    V2_PHASE7_POLICY_REVISION: str
    V2_PHASE7_ROLLOUT_SALT: str
    V2_PHASE7_ALLOW_ADMIN_DUAL_ROLE: bool
    V2_PHASE7_CONFIG_VALID: bool
    V2_PHASE7_SHADOW_MODE: str
    V2_PHASE7_SHADOW_COMPARE_ENABLED: bool
    V2_PHASE7_SHADOW_LIVE_PROVIDERS_ENABLED: bool
    V2_PHASE7_SHADOW_MAX_CONCURRENCY: int
    V2_PHASE7_SHADOW_MAX_WALL_SECONDS: int
    V2_PHASE7_PERCENT_SERVE_ENABLED: bool
    V2_PHASE7_PERCENT_REQUIRES_CANARY: bool
    V2_PHASE7_LIVE_CANARY_ENABLED: bool
    V2_PHASE7_LIVE_CANARY_PROVIDERS_ENABLED: bool
    V2_PHASE7_CANARY_SIMULATION_ENABLED: bool
    V2_PHASE7_CANARY_MAX_CALLS: int
    V2_PHASE7_CANARY_MAX_INPUT_TOKENS: int
    V2_PHASE7_CANARY_MAX_OUTPUT_TOKENS: int
    V2_PHASE7_CANARY_MAX_COST_USD: float
    V2_PHASE7_CANARY_MAX_WALL_SECONDS: int
    V2_PHASE7_CANARY_MAX_RETRIES: int
    V2_PHASE7_CANARY_PER_CALL_TIMEOUT_SECONDS: int
    V2_PHASE7_CANARY_APPROVAL_TTL_SECONDS: int
    PREVIEW_SKIP_CRITIC: bool
    PREVIEW_PARALLEL_WORKERS: int
    PREVIEW_MAX_FILES: int
    PREVIEW_MAX_BUILD_FIX_ATTEMPTS: int
    PREVIEW_MAX_FIX_LOOP_SECONDS: int
    PREVIEW_MAX_AI_CALLS: int
    PREVIEW_QUALITY_AI_REPAIR: bool
    PREVIEW_MAX_QUALITY_FIX_ATTEMPTS: int
    PREVIEW_SKIP_VISUAL_CRITIC: bool
    PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED: bool
    PREVIEW_SCAFFOLD_FIRST: bool
    PREVIEW_SCAFFOLD_SLOT_FILL: bool
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
        self.PREVIEW_APP_MODEL = _env_or("PREVIEW_APP_MODEL", defaults["preview_app"])
        # The last rung before a slot_fill ask settles for its scaffold on
        # transport (R1 at the highest-volume ask site — 1.12(b): an unroutable
        # page writer shipped bare scaffolds to the gate). ONE ask on a
        # DIFFERENT provider's model; same-provider rides the same storm. When
        # equal to PREVIEW_APP_MODEL the rung is skipped and the page fails
        # closed to its scaffold as before.
        self.PREVIEW_APP_TRANSPORT_FALLBACK_MODEL = _env_or(
            "PREVIEW_APP_TRANSPORT_FALLBACK_MODEL", "anthropic/claude-haiku-4.5"
        )

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
        # 2026-08-07.1: sessions 18-19's reject shapes taught — exactly-one
        # initial state, per-kind assertion references, declare-before-cite,
        # the minItems floor outside traceability, trace-or-defer.
        # 2026-08-07.2: R4 rung 2 — the ops-kind page floor (8b), rendered for
        # ops faces only and derived from the ship gate's own constant.
        # 2026-08-07.3: request 143's empty-tuple reject class — 9a (no
        # stateless pages, no placeholder objects, mined Page1 shape), the
        # repair prompt's anti-collapse line (rev 1 returned one acceptance
        # test in place of a 6-page spec), and the schema-repair prompt's
        # constructive stateless-page fix (7a).
        self.APPSPEC_PROMPT_REVISION = (
            os.getenv("APPSPEC_PROMPT_REVISION", "2026-08-07.3").strip()
            or "2026-07-15.1"
        )
        self.APPSPEC_MODEL = _env_or("APPSPEC_MODEL", self.ARCHITECT_MODEL)
        self.APPSPEC_REPAIR_MODEL = _env_or("APPSPEC_REPAIR_MODEL", self.APPSPEC_MODEL)
        # The last rung before an appspec ask fails closed on transport: one ask
        # on a DIFFERENT provider's model (runs 136/137 — a provider-side storm
        # cuts the primary and its bounded re-ask alike; a same-provider
        # fallback would ride the same storm). Keep this cross-provider from
        # APPSPEC_MODEL / APPSPEC_REPAIR_MODEL; when they are equal the
        # fallback is skipped and the ask fails closed as before.
        self.APPSPEC_TRANSPORT_FALLBACK_MODEL = _env_or(
            "APPSPEC_TRANSPORT_FALLBACK_MODEL", "anthropic/claude-haiku-4.5"
        )
        # Keep the coverage review separately configurable so production can use
        # a different model from the authoring pass instead of self-grading.
        self.APPSPEC_COVERAGE_MODEL = _env_or(
            "APPSPEC_COVERAGE_MODEL", self.CRITIC_MODEL
        )
        # v2 validates that this reviewer belongs to a different model family
        # before it makes any provider call. v1 continues using the legacy
        # APPSPEC_COVERAGE_MODEL setting above.
        # Prefer an explicit v2 override; otherwise inherit APPSPEC_COVERAGE_MODEL
        # so production does not silently self-review with CRITIC_MODEL/Gemini.
        self.APPSPEC_V2_COVERAGE_MODEL = _env_or(
            "APPSPEC_V2_COVERAGE_MODEL", self.APPSPEC_COVERAGE_MODEL
        )
        # Per REQUEST, not per entry into the stage. `appspec` is entered twice
        # a generation, so while this was enforced per entry the effective
        # ceiling was double the configured one: requests 92, 93 and 94 made 7,
        # 6 and 10 calls against a configured 6, and none of them logged a
        # budget-exhausted line. 8 rather than 6 because the largest *accepted*
        # AppSpec in the corpus took 7 calls (request 87), and a request-wide 6
        # would have refused the call that produced it.
        try:
            self.APPSPEC_MAX_CALLS = max(2, int(os.getenv("APPSPEC_MAX_CALLS", "8")))
        except ValueError:
            self.APPSPEC_MAX_CALLS = 8
        # `appspec` may not start an AI call that leaves the rest of the pipeline
        # less than this. Sized to the corpus, not to a guess: across requests
        # 77-94 the five runs that reached `ready` needed 284.6, 382.1, 457.5,
        # 458.7 and 504.9 s after their last appspec call, so 280 s is under
        # every one of them and no shipped run would have lost a call. The two
        # runs that stored *nothing* — 92 and 94 — left 91 s and 136 s, and each
        # would have had roughly 120 s returned to the stages that had to
        # follow. Fitted to a minimum over n=5: when it is wrong the cost is a
        # degraded AppSpec, which is the designed outcome, and the alternative
        # it replaces is an empty record.
        try:
            self.APPSPEC_DOWNSTREAM_RESERVE_SECONDS = max(
                0.0, float(os.getenv("APPSPEC_DOWNSTREAM_RESERVE_SECONDS", "280"))
            )
        except ValueError:
            self.APPSPEC_DOWNSTREAM_RESERVE_SECONDS = 280.0
        try:
            self.APPSPEC_MAX_REPAIR_ATTEMPTS = max(
                0, int(os.getenv("APPSPEC_MAX_REPAIR_ATTEMPTS", "3"))
            )
        except ValueError:
            self.APPSPEC_MAX_REPAIR_ATTEMPTS = 3
        try:
            # Schema-only repair attempts. Deliberately SEPARATE from
            # APPSPEC_MAX_REPAIR_ATTEMPTS: one schema repair is guaranteed even
            # when the general repair budget is 0, so the floor here is 1 and the
            # default preserves the historical single-attempt behavior exactly.
            # Raise it when the author intermittently emits empty required tuples
            # (invalid_trace_shape) or duplicate IDs — those cannot be healed
            # deterministically without inventing traceability, so AI repair is
            # the only legitimate path. Total calls stay bounded by
            # APPSPEC_MAX_CALLS via _StageLimitedAIProvider.
            self.APPSPEC_MAX_SCHEMA_REPAIR_ATTEMPTS = min(
                3, max(1, int(os.getenv("APPSPEC_MAX_SCHEMA_REPAIR_ATTEMPTS", "1")))
            )
        except ValueError:
            self.APPSPEC_MAX_SCHEMA_REPAIR_ATTEMPTS = 1
        try:
            self.APPSPEC_MAX_DETERMINISTIC_HEALS = max(
                0, int(os.getenv("APPSPEC_MAX_DETERMINISTIC_HEALS", "4"))
            )
        except ValueError:
            self.APPSPEC_MAX_DETERMINISTIC_HEALS = 4
        # AppSpec fallback is fail-closed by default. It may be enabled only by
        # an explicit, valid non-production override.
        self.APP_ENVIRONMENT_CLASSIFICATION = _environment_classification()
        (
            self.APPSPEC_FALLBACK_ENABLED,
            self.APPSPEC_FALLBACK_CONFIG_VALID,
        ) = _parse_strict_bool(
            os.getenv("APPSPEC_FALLBACK_ENABLED"),
            default=False,
        )
        self.APPSPEC_FALLBACK_CONFIG_SOURCE = _configuration_source(
            "APPSPEC_FALLBACK_ENABLED"
        )
        if not self.APPSPEC_FALLBACK_CONFIG_VALID:
            self.APPSPEC_FALLBACK_SAFETY_CODE = (
                "invalid_appspec_fallback_boolean"
            )
        elif (
            self.APP_ENVIRONMENT_CLASSIFICATION == "production"
            and self.APPSPEC_FALLBACK_ENABLED
        ):
            self.APPSPEC_FALLBACK_SAFETY_CODE = (
                "unsafe_appspec_fallback_enabled"
            )
        else:
            self.APPSPEC_FALLBACK_SAFETY_CODE = "ok"
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

        # Phase 7A rollout control plane — fail closed; never serves candidates.
        self.V2_PHASE7_ROLLOUT_ENABLED = os.getenv(
            "V2_PHASE7_ROLLOUT_ENABLED",
            "false",
        ).strip().lower() in ("1", "true", "yes", "on")
        self.V2_PHASE7_SHADOW_ENABLED = os.getenv(
            "V2_PHASE7_SHADOW_ENABLED",
            "false",
        ).strip().lower() in ("1", "true", "yes", "on")
        self.V2_PHASE7_PROMOTE_ENABLED = os.getenv(
            "V2_PHASE7_PROMOTE_ENABLED",
            "false",
        ).strip().lower() in ("1", "true", "yes", "on")
        self.V2_PHASE7_CIRCUIT_BREAKER_ENABLED = os.getenv(
            "V2_PHASE7_CIRCUIT_BREAKER_ENABLED",
            "false",
        ).strip().lower() in ("1", "true", "yes", "on")
        self.V2_PHASE7_AUTO_ROLLBACK_ENABLED = os.getenv(
            "V2_PHASE7_AUTO_ROLLBACK_ENABLED",
            "false",
        ).strip().lower() in ("1", "true", "yes", "on")
        _breaker_cfg_invalid = False
        try:
            self.V2_PHASE7_AUTO_ROLLBACK_LOOKBACK_SECONDS = max(
                1,
                int(os.getenv("V2_PHASE7_AUTO_ROLLBACK_LOOKBACK_SECONDS", "3600")),
            )
        except ValueError:
            self.V2_PHASE7_AUTO_ROLLBACK_LOOKBACK_SECONDS = 3600
            _breaker_cfg_invalid = True
        try:
            self.V2_PHASE7_BREAKER_EVAL_MAX_REQUESTS = max(
                1,
                min(500, int(os.getenv("V2_PHASE7_BREAKER_EVAL_MAX_REQUESTS", "50"))),
            )
        except ValueError:
            self.V2_PHASE7_BREAKER_EVAL_MAX_REQUESTS = 50
            _breaker_cfg_invalid = True
        self.V2_PHASE7_OPS_DASHBOARD_ENABLED = os.getenv(
            "V2_PHASE7_OPS_DASHBOARD_ENABLED",
            "false",
        ).strip().lower() in ("1", "true", "yes", "on")
        self.V2_PHASE7_OPS_ALERTS_ENABLED = os.getenv(
            "V2_PHASE7_OPS_ALERTS_ENABLED",
            "false",
        ).strip().lower() in ("1", "true", "yes", "on")
        try:
            self.V2_PHASE7_OPS_ALERT_LOOKBACK_SECONDS = max(
                1,
                int(os.getenv("V2_PHASE7_OPS_ALERT_LOOKBACK_SECONDS", "3600")),
            )
        except ValueError:
            self.V2_PHASE7_OPS_ALERT_LOOKBACK_SECONDS = 3600
            _breaker_cfg_invalid = True
        self.V2_PHASE7_ALLOW_ADMIN_DUAL_ROLE = os.getenv(
            "V2_PHASE7_ALLOW_ADMIN_DUAL_ROLE",
            "false",
        ).strip().lower() in ("1", "true", "yes", "on")
        self.V2_PHASE7_POLICY_REVISION = _env_or(
            "V2_PHASE7_POLICY_REVISION",
            "2026-07-25.1",
        )
        self.V2_PHASE7_ROLLOUT_SALT = _env_or(
            "V2_PHASE7_ROLLOUT_SALT",
            self.V2_PHASE7_POLICY_REVISION,
        )
        self.V2_PHASE7_CONFIG_VALID = True
        if _breaker_cfg_invalid:
            self.V2_PHASE7_CONFIG_VALID = False
            self.V2_PHASE7_CIRCUIT_BREAKER_ENABLED = False
            self.V2_PHASE7_AUTO_ROLLBACK_ENABLED = False
            self.V2_PHASE7_OPS_DASHBOARD_ENABLED = False
            self.V2_PHASE7_OPS_ALERTS_ENABLED = False
        percent_raw = (os.getenv("V2_PHASE7_ROLLOUT_PERCENT") or "0").strip()
        try:
            percent = int(percent_raw)
            if percent < 0 or percent > 100:
                raise ValueError("percent out of range")
            self.V2_PHASE7_ROLLOUT_PERCENT = percent
        except ValueError:
            # Fail closed: invalid percent disables Phase 7 master semantics.
            self.V2_PHASE7_ROLLOUT_PERCENT = 0
            self.V2_PHASE7_CONFIG_VALID = False
            self.V2_PHASE7_ROLLOUT_ENABLED = False
            self.V2_PHASE7_SHADOW_ENABLED = False
            self.V2_PHASE7_PROMOTE_ENABLED = False
        allowlist_raw = (os.getenv("V2_PHASE7_REQUEST_ALLOWLIST") or "").strip()
        if not allowlist_raw:
            self.V2_PHASE7_REQUEST_ALLOWLIST = ()
        else:
            tokens = [t.strip() for t in allowlist_raw.split(",") if t.strip()]
            try:
                values = []
                for token in tokens:
                    if not token.isdigit() or int(token) < 1:
                        raise ValueError(f"bad allowlist token {token!r}")
                    values.append(int(token))
                self.V2_PHASE7_REQUEST_ALLOWLIST = tuple(sorted(set(values)))
            except ValueError:
                self.V2_PHASE7_REQUEST_ALLOWLIST = ()
                self.V2_PHASE7_CONFIG_VALID = False
                self.V2_PHASE7_ROLLOUT_ENABLED = False
                self.V2_PHASE7_SHADOW_ENABLED = False
                self.V2_PHASE7_PROMOTE_ENABLED = False
        if not self.V2_PHASE7_ROLLOUT_SALT.strip():
            self.V2_PHASE7_CONFIG_VALID = False
            self.V2_PHASE7_ROLLOUT_ENABLED = False
        # Phase 7B shadow execution — fail closed; never serves candidates.
        mode_raw = _env_or("V2_PHASE7_SHADOW_MODE", "reuse_accepted").strip()
        allowed_modes = {"reuse_accepted", "regenerate_fixture", "regenerate_live"}
        if mode_raw not in allowed_modes:
            self.V2_PHASE7_SHADOW_MODE = "reuse_accepted"
            self.V2_PHASE7_CONFIG_VALID = False
            self.V2_PHASE7_ROLLOUT_ENABLED = False
            self.V2_PHASE7_SHADOW_ENABLED = False
        else:
            self.V2_PHASE7_SHADOW_MODE = mode_raw
        self.V2_PHASE7_SHADOW_COMPARE_ENABLED = os.getenv(
            "V2_PHASE7_SHADOW_COMPARE_ENABLED",
            "true",
        ).strip().lower() in ("1", "true", "yes", "on")
        self.V2_PHASE7_SHADOW_LIVE_PROVIDERS_ENABLED = os.getenv(
            "V2_PHASE7_SHADOW_LIVE_PROVIDERS_ENABLED",
            "false",
        ).strip().lower() in ("1", "true", "yes", "on")
        # Live providers remain unsupported in Phase 7B operational modes.
        if self.V2_PHASE7_SHADOW_LIVE_PROVIDERS_ENABLED:
            # Fail closed: never silently allow live regenerate.
            self.V2_PHASE7_CONFIG_VALID = False
            self.V2_PHASE7_SHADOW_ENABLED = False
        try:
            self.V2_PHASE7_SHADOW_MAX_CONCURRENCY = min(
                1,
                max(1, int(os.getenv("V2_PHASE7_SHADOW_MAX_CONCURRENCY", "1"))),
            )
        except ValueError:
            self.V2_PHASE7_SHADOW_MAX_CONCURRENCY = 1
            self.V2_PHASE7_CONFIG_VALID = False
            self.V2_PHASE7_SHADOW_ENABLED = False
        try:
            self.V2_PHASE7_SHADOW_MAX_WALL_SECONDS = min(
                3600,
                max(1, int(os.getenv("V2_PHASE7_SHADOW_MAX_WALL_SECONDS", "3600"))),
            )
        except ValueError:
            self.V2_PHASE7_SHADOW_MAX_WALL_SECONDS = 3600
            self.V2_PHASE7_CONFIG_VALID = False
            self.V2_PHASE7_SHADOW_ENABLED = False
        # Phase 7F percent serve + live canary — defaults fail closed.
        self.V2_PHASE7_PERCENT_SERVE_ENABLED = os.getenv(
            "V2_PHASE7_PERCENT_SERVE_ENABLED",
            "false",
        ).strip().lower() in ("1", "true", "yes", "on")
        self.V2_PHASE7_PERCENT_REQUIRES_CANARY = os.getenv(
            "V2_PHASE7_PERCENT_REQUIRES_CANARY",
            "true",
        ).strip().lower() in ("1", "true", "yes", "on")
        self.V2_PHASE7_LIVE_CANARY_ENABLED = os.getenv(
            "V2_PHASE7_LIVE_CANARY_ENABLED",
            "false",
        ).strip().lower() in ("1", "true", "yes", "on")
        self.V2_PHASE7_LIVE_CANARY_PROVIDERS_ENABLED = os.getenv(
            "V2_PHASE7_LIVE_CANARY_PROVIDERS_ENABLED",
            "false",
        ).strip().lower() in ("1", "true", "yes", "on")
        # Live paid providers stay off unless explicitly enabled (still canary-only).
        if self.V2_PHASE7_LIVE_CANARY_PROVIDERS_ENABLED and not (
            self.V2_PHASE7_LIVE_CANARY_ENABLED and self.V2_PHASE7_CONFIG_VALID
        ):
            self.V2_PHASE7_LIVE_CANARY_PROVIDERS_ENABLED = False
        # Fixture simulation is never available in production configuration.
        _app_env = (
            os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or os.getenv("ENV") or ""
        ).strip().lower()
        _is_production = _app_env in ("production", "prod")
        _sim_requested = os.getenv(
            "V2_PHASE7_CANARY_SIMULATION_ENABLED",
            "false",
        ).strip().lower() in ("1", "true", "yes", "on")
        if _is_production:
            self.V2_PHASE7_CANARY_SIMULATION_ENABLED = False
            if _sim_requested:
                self.V2_PHASE7_CONFIG_VALID = False
                self.V2_PHASE7_LIVE_CANARY_ENABLED = False
        else:
            self.V2_PHASE7_CANARY_SIMULATION_ENABLED = _sim_requested
        _canary_cfg_invalid = False
        try:
            self.V2_PHASE7_CANARY_MAX_CALLS = min(
                12, max(1, int(os.getenv("V2_PHASE7_CANARY_MAX_CALLS", "12")))
            )
            self.V2_PHASE7_CANARY_MAX_INPUT_TOKENS = max(
                1, int(os.getenv("V2_PHASE7_CANARY_MAX_INPUT_TOKENS", "50000"))
            )
            self.V2_PHASE7_CANARY_MAX_OUTPUT_TOKENS = max(
                1, int(os.getenv("V2_PHASE7_CANARY_MAX_OUTPUT_TOKENS", "20000"))
            )
            self.V2_PHASE7_CANARY_MAX_COST_USD = float(
                os.getenv("V2_PHASE7_CANARY_MAX_COST_USD", "5.0")
            )
            if self.V2_PHASE7_CANARY_MAX_COST_USD <= 0:
                raise ValueError("cost ceiling must be positive")
            self.V2_PHASE7_CANARY_MAX_WALL_SECONDS = min(
                1200,
                max(1, int(os.getenv("V2_PHASE7_CANARY_MAX_WALL_SECONDS", "1200"))),
            )
            self.V2_PHASE7_CANARY_MAX_RETRIES = min(
                1, max(0, int(os.getenv("V2_PHASE7_CANARY_MAX_RETRIES", "1")))
            )
            self.V2_PHASE7_CANARY_PER_CALL_TIMEOUT_SECONDS = min(
                600,
                max(
                    1,
                    int(os.getenv("V2_PHASE7_CANARY_PER_CALL_TIMEOUT_SECONDS", "120")),
                ),
            )
            self.V2_PHASE7_CANARY_APPROVAL_TTL_SECONDS = max(
                60,
                int(os.getenv("V2_PHASE7_CANARY_APPROVAL_TTL_SECONDS", "3600")),
            )
        except ValueError:
            _canary_cfg_invalid = True
            self.V2_PHASE7_CANARY_MAX_CALLS = 12
            self.V2_PHASE7_CANARY_MAX_INPUT_TOKENS = 50000
            self.V2_PHASE7_CANARY_MAX_OUTPUT_TOKENS = 20000
            self.V2_PHASE7_CANARY_MAX_COST_USD = 5.0
            self.V2_PHASE7_CANARY_MAX_WALL_SECONDS = 1200
            self.V2_PHASE7_CANARY_MAX_RETRIES = 1
            self.V2_PHASE7_CANARY_PER_CALL_TIMEOUT_SECONDS = 120
            self.V2_PHASE7_CANARY_APPROVAL_TTL_SECONDS = 3600
        if _canary_cfg_invalid:
            self.V2_PHASE7_CONFIG_VALID = False
            self.V2_PHASE7_LIVE_CANARY_ENABLED = False
            self.V2_PHASE7_PERCENT_SERVE_ENABLED = False
        # Percent-serve activation while master/promote disabled → fail closed.
        # Note: ROLLOUT_PERCENT may still be >0 for shadow targeting (7A/7B)
        # while PERCENT_SERVE_ENABLED remains false — that must not invalidate
        # the whole Phase 7 plane.
        if self.V2_PHASE7_PERCENT_SERVE_ENABLED and not (
            self.V2_PHASE7_ROLLOUT_ENABLED and self.V2_PHASE7_PROMOTE_ENABLED
        ):
            self.V2_PHASE7_CONFIG_VALID = False
            self.V2_PHASE7_PERCENT_SERVE_ENABLED = False
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
        # Should a page the vision critic could not judge withhold the preview?
        # OFF: a vision outage (model unservable, 429, missing key, budget spent)
        # is our measurement failing, not a defect in the generated app, and
        # withholding a working preview for it is the same pathology as shipping
        # a stale BLOCK. The counts always reach the API result as
        # `visual_review_status` / `visual_pages_reviewed` regardless, so nothing
        # downstream can read "ready" as "reviewed". Turn ON to refuse to ship
        # anything a human or model has not actually looked at.
        #
        # This read used to be the flag's ONLY appearance in the repo — no
        # Settings field, no .env template, no doc, no test — so it was off
        # everywhere by accident rather than by decision.
        self.PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED = os.getenv(
            "PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED", "false"
        ).strip().lower() in ("1", "true", "yes", "on")
        # `vite build` never typechecks, so prop-contract violations ship as
        # empty components. tsc costs ~2s per run — ON by default.
        self.PREVIEW_TYPECHECK = os.getenv(
            "PREVIEW_TYPECHECK", "true"
        ).strip().lower() in ("1", "true", "yes", "on")
        try:
            self.PREVIEW_MAX_TYPECHECK_FIX_ROUNDS = max(
                0, int(os.getenv("PREVIEW_MAX_TYPECHECK_FIX_ROUNDS", "2"))
            )
        except ValueError:
            self.PREVIEW_MAX_TYPECHECK_FIX_ROUNDS = 2
        try:
            self.PREVIEW_TYPECHECK_TIMEOUT_SECONDS = max(
                30, int(os.getenv("PREVIEW_TYPECHECK_TIMEOUT_SECONDS", "180"))
            )
        except ValueError:
            self.PREVIEW_TYPECHECK_TIMEOUT_SECONDS = 180
        # Catalogue pages: emit deterministic scaffold first (reliable compile +
        # AppSpec hooks), optionally AI-fill slot copy once. Default ON.
        self.PREVIEW_SCAFFOLD_FIRST = os.getenv(
            "PREVIEW_SCAFFOLD_FIRST", "true"
        ).strip().lower() in ("1", "true", "yes", "on")
        self.PREVIEW_SCAFFOLD_SLOT_FILL = os.getenv(
            "PREVIEW_SCAFFOLD_SLOT_FILL", "true"
        ).strip().lower() in ("1", "true", "yes", "on")
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
        "preview_app": "qwen2.5-coder:7b",
    },
    "openrouter": {
        "text": "meta-llama/llama-3.1-8b-instruct",
        # OpenRouter serves no endpoints for llama-3.2-11b-vision-instruct, so the
        # visual critic failed on every route and silently reviewed nothing. This
        # is the multimodal model the pipeline already uses for codegen.
        "vision": "google/gemini-2.5-flash",
        "coder": "qwen/qwen-2.5-coder-32b-instruct",
        # Matches the value backend/.env pins today, so deleting the env line
        # does not silently change the page-writer model.
        "preview_app": "deepseek/deepseek-v4-pro",
    },
}


class RuntimeConfigurationError(RuntimeError):
    """Typed fail-closed runtime configuration error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def appspec_fallback_configuration(
    config: Settings,
) -> dict[str, str | bool]:
    """Return redacted AppSpec fallback safety diagnostics."""

    code = config.APPSPEC_FALLBACK_SAFETY_CODE
    return {
        "appspec_fallback_enabled": config.APPSPEC_FALLBACK_ENABLED,
        "configuration_source": config.APPSPEC_FALLBACK_CONFIG_SOURCE,
        "environment_classification": (
            config.APP_ENVIRONMENT_CLASSIFICATION
        ),
        "configuration_valid": config.APPSPEC_FALLBACK_CONFIG_VALID,
        "safety_assertion": "passed" if code == "ok" else "failed",
        "safety_code": code,
    }


def _model_provider_prefix(model: str) -> str | None:
    """The OpenRouter provider segment of ``provider/model``, or None.

    A model id without a ``/`` names no provider — it cannot be classified,
    so callers must not treat it as matching anything.
    """

    head, sep, _ = (model or "").strip().partition("/")
    if not sep or not head:
        return None
    return head.lower()


def warn_same_provider_transport_fallback(config: Settings) -> list[str]:
    """Warn when the transport fallback cannot be independent of the primary.

    The transport fallback's whole value is provider independence: a
    provider-side storm cuts the primary and its bounded same-model re-ask
    alike (runs 136/137), so a fallback on the SAME provider rides the same
    storm and R1 silently defeats itself. That invariant lived in a `.env`
    comment; this asserts it at startup. WARN, never crash — a same-provider
    fallback still fails closed exactly as before the fallback existed.

    Returns the offending primary slot names so the check is testable without
    capturing log output.
    """

    fallback_prefix = _model_provider_prefix(config.APPSPEC_TRANSPORT_FALLBACK_MODEL)
    if fallback_prefix is None:
        return []
    offenders = [
        slot
        for slot in ("APPSPEC_MODEL", "APPSPEC_REPAIR_MODEL", "APPSPEC_COVERAGE_MODEL")
        if _model_provider_prefix(getattr(config, slot)) == fallback_prefix
    ]
    if offenders:
        from app.infrastructure.logging import get_logger

        get_logger("Config").warning(
            "APPSPEC_TRANSPORT_FALLBACK_MODEL=%s shares provider %r with %s — "
            "a provider-side storm will cut the fallback with the primary, so "
            "the transport rung buys nothing. Point it at a different provider.",
            config.APPSPEC_TRANSPORT_FALLBACK_MODEL,
            fallback_prefix,
            " and ".join(offenders),
        )
    return offenders


def warn_same_provider_preview_app_fallback(config: Settings) -> list[str]:
    """The slot_fill twin of `warn_same_provider_transport_fallback`.

    Same invariant, R1's newest rung: `PREVIEW_APP_TRANSPORT_FALLBACK_MODEL`
    must not share a provider with `PREVIEW_APP_MODEL` or the storm that cut
    the page writer cuts its fallback too. Kept as a sibling rather than a
    parameter because the appspec check's source is anchored by a landed
    mutation sweep. WARN, never crash.
    """

    fallback_prefix = _model_provider_prefix(
        config.PREVIEW_APP_TRANSPORT_FALLBACK_MODEL
    )
    if fallback_prefix is None:
        return []
    offenders = [
        slot
        for slot in ("PREVIEW_APP_MODEL",)
        if _model_provider_prefix(getattr(config, slot)) == fallback_prefix
    ]
    if offenders:
        from app.infrastructure.logging import get_logger

        get_logger("Config").warning(
            "PREVIEW_APP_TRANSPORT_FALLBACK_MODEL=%s shares provider %r with %s — "
            "a provider-side storm will cut the fallback with the primary, so "
            "the transport rung buys nothing. Point it at a different provider.",
            config.PREVIEW_APP_TRANSPORT_FALLBACK_MODEL,
            fallback_prefix,
            " and ".join(offenders),
        )
    return offenders


def assert_safe_runtime_configuration(config: Settings) -> None:
    """Fail startup for malformed or production-unsafe fallback settings."""

    code = config.APPSPEC_FALLBACK_SAFETY_CODE
    if code != "ok":
        raise RuntimeConfigurationError(code)
    warn_same_provider_transport_fallback(config)
    warn_same_provider_preview_app_fallback(config)


settings = Settings()
