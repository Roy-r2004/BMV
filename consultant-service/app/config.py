import logging
import os

from dotenv import load_dotenv

load_dotenv()


def _env_or(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _env_int_within(name: str, default: int, low: int, high: int) -> int:
    """An integer setting held inside [low, high]: a value out of range is
    moved to the nearest bound, and one that is not a number reads as unset."""
    try:
        value = int(_env_or(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(high, value))


def _at_most(name: str, value: int, ceiling_name: str, ceiling: int) -> int:
    """`value`, held at or below another setting it may not pass (a shortest
    length above the longest is moved down to it, and the log says so)."""
    if value > ceiling:
        logging.getLogger("consultant.config").warning(
            "%s=%s is above %s=%s; using %s", name, value, ceiling_name, ceiling, ceiling)
        return ceiling
    return value


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


class Settings:
    # Everything routes through OpenRouter — one key, one place cost is tracked.
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "").strip()
    ANALYSIS_MODEL: str = _env_or("ANALYSIS_MODEL", "google/gemini-2.5-flash")
    # The diagnosis stage only. Holding five competing explanations against a
    # claim set and refusing the one the owner already believed is a different
    # job from extracting fields and formatting prose, and ANALYSIS_MODEL is
    # sized for the second. Two calls per engagement carry this; everything
    # else stays on the cheaper model.
    # Deliberately NOT chained to ANALYSIS_MODEL: an env that sets the cheap
    # model everywhere would silently take the diagnosis down with it, and the
    # stage would go on reporting tested conclusions.
    REASONING_MODEL: str = _env_or("REASONING_MODEL", "google/gemini-2.5-pro")
    # The Phase-1 pilot's lightweight tooling and the human role that runs it —
    # generic names applied to every engagement (a pilot module is never a
    # person and never depends on a later-phase module).
    PILOT_TOOLING_NAME: str = _env_or("PILOT_TOOLING_NAME", "Pilot Review Queue")
    PILOT_OPERATOR_ROLE: str = _env_or("PILOT_OPERATOR_ROLE", "Pilot Support Operator")
    # the customer-facing counterpart of the internal queue: what a customer
    # receives during the pilot (a simple confirmation form / reply), never
    # the internal review queue
    PILOT_CUSTOMER_FORM_NAME: str = _env_or("PILOT_CUSTOMER_FORM_NAME", "Pilot Confirmation Form")
    # Soft bounds, not a fixed target — the plan stage decides the actual
    # count per business (see prompts/plan.j2). MIN only guards the fallback
    # path; MAX is a cost/sanity cap on a real model response.
    MIN_ROLES_PER_REQUEST: int = int(_env_or("MIN_ROLES_PER_REQUEST", "2"))
    MAX_ROLES_PER_REQUEST: int = int(_env_or("MAX_ROLES_PER_REQUEST", "4"))
    # Bounds on the decomposition stage's module count — the model decides
    # the actual number per business (same soft-bounds pattern as roles:
    # never a fixed count, a floor against a degenerate answer and a
    # ceiling against a runaway one). Each module costs one extra deep-spec
    # text call, so MAX also caps that stage's spend.
    # Discovery questions are soft-bounded the same way modules are — the
    # model chooses the count this business needs within the bounds.
    # The human review gate: finished runs land as pending until the
    # reviewer (holding REVIEW_TOKEN) approves. Active only when a token
    # is configured — a gate nobody can open must never be armed.
    # The main app owns accounts; sessions are introspected against it.
    MAIN_API_URL: str = _env_or("MAIN_API_URL", "https://buildmyversion.com")
    # Runs listed here are the PUBLIC example engagements — the marketing
    # gallery. Everything else created after the auth gate is private to
    # its owner. Comma-separated ids, set in the deploy environment.
    SHOWCASE_IDS: str = _env_or("SHOWCASE_IDS", "")
    # Transactional mail from the consultancy's own mailbox. Unset
    # password = mail silently disabled; nothing depends on it.
    SMTP_HOST: str = _env_or("SMTP_HOST", "smtp.hostinger.com")
    SMTP_PORT: int = int(_env_or("SMTP_PORT", "465"))
    SMTP_USER: str = _env_or("SMTP_USER", "consulting@buildmyversion.com")
    SMTP_PASSWORD: str = _env_or("SMTP_PASSWORD", "")
    # A provider outage stalls every interview round for every client at once.
    # The team gets one email per kind of stall per this many seconds, not one
    # per round.
    STALL_MAIL_WINDOW_SECONDS: int = int(_env_or("STALL_MAIL_WINDOW_SECONDS", "300"))
    # How many times, in all, a stage asks for ONE reply it must be able to use
    # (JSON of the right shape, a document that is not empty) before the run
    # stops. 2 is one retry. A reply cut off mid-object is a known, occasional
    # fault and a paid run should not end on the first one; the provider's own
    # failures are retried in the provider and never again here. Held to 1..3.
    STAGE_REPLY_ATTEMPTS: int = _env_int_within("STAGE_REPLY_ATTEMPTS", 2, 1, 3)
    # How many figures the case file (app/figures/casefile.py) keeps: from one
    # text (an answer, a field) and from the whole request. A build stops at the
    # bound, in the order the texts are read, so a pasted spreadsheet cannot make
    # the stored case file, or the time to build it, unbounded. Held to 20..1000
    # and 100..5000.
    CASE_FILE_FIGURES_PER_TEXT: int = _env_int_within("CASE_FILE_FIGURES_PER_TEXT", 200, 20, 1000)
    CASE_FILE_FIGURES_PER_REQUEST: int = _env_int_within("CASE_FILE_FIGURES_PER_REQUEST", 1000, 100, 5000)
    # The length of the plan the answer proposes, in weeks (app/pipeline/answer.py),
    # and the bounds the model's length is held to; the roadmap's phases may not run
    # past it. Per business, so bounded: the default 6 within 2..26, the shortest
    # 1..12, the longest 4..104.
    PLAN_WEEKS_DEFAULT: int = _env_int_within("PLAN_WEEKS_DEFAULT", 6, 2, 26)
    PLAN_WEEKS_MAX: int = _env_int_within("PLAN_WEEKS_MAX", 12, 4, 104)
    # the shortest may not pass the longest (both are set from the environment)
    PLAN_WEEKS_MIN: int = _at_most("PLAN_WEEKS_MIN", _env_int_within("PLAN_WEEKS_MIN", 2, 1, 12),
                                   "PLAN_WEEKS_MAX", PLAN_WEEKS_MAX)
    # How many figures a prompt lists under "Figures you may use"
    # (app/figures/known.py prompt_lines). Theirs and derived come first; the rest
    # are counted in one closing line. A prompt cannot grow with a pasted
    # spreadsheet. Held to 10..200.
    PROMPT_FIGURE_LINES: int = _env_int_within("PROMPT_FIGURE_LINES", 60, 10, 200)
    REVIEW_MODE: str = _env_or("REVIEW_MODE", "on")
    # Named on covers and in the closing pages when set ("Roy Rizkallah -
    # Managing Consultant"). A document a person signs reads senior; one
    # nobody signs reads generated. Empty = omitted entirely.
    ENGAGEMENT_LEAD: str = _env_or("ENGAGEMENT_LEAD", "")
    REVIEW_TOKEN: str = _env_or("REVIEW_TOKEN", "")
    MAX_DISCOVERY_QUESTIONS: int = int(_env_or("MAX_DISCOVERY_QUESTIONS", "6"))
    # The fact-finding interview. It works through the brief's fact list and
    # ends when nothing on it is still needed — so the rounds cap is a safety
    # rail, not the product. Two questions a round keeps every follow-up close
    # to the answer before it.
    INTERVIEW_MAX_ROUNDS: int = int(_env_or("INTERVIEW_MAX_ROUNDS", "18"))
    INTERVIEW_MAX_PER_ROUND: int = int(_env_or("INTERVIEW_MAX_PER_ROUND", "2"))
    MIN_MODULES_PER_REQUEST: int = int(_env_or("MIN_MODULES_PER_REQUEST", "3"))
    MAX_MODULES_PER_REQUEST: int = int(_env_or("MAX_MODULES_PER_REQUEST", "7"))

    # The diagnosis stage's challenge round — each leading explanation is
    # attacked from several angles before it is reported (see
    # pipeline/diagnose.py) — runs on this model. Defaults to ANALYSIS_MODEL.
    QA_MODEL: str = _env_or("QA_MODEL", _env_or("ANALYSIS_MODEL", "google/gemini-2.5-flash"))

    # Money-safety valve on the open intake endpoint: how many requests may
    # be generating simultaneously before new submissions get a 429.
    MAX_CONCURRENT_GENERATIONS: int = int(_env_or("MAX_CONCURRENT_GENERATIONS", "3"))

    # INFO, because the pipeline's INFO lines are the run's only narrative:
    # which stage is running, which model answered, and why a stage fell
    # back. Set to WARNING for a quiet console.
    LOG_LEVEL: str = _env_or("LOG_LEVEL", "INFO").upper()

    DATABASE_URL: str = _env_or("DATABASE_URL", "sqlite:///./consultant.db")
    PORT: int = int(_env_or("PORT", "8002"))
    FRONTEND_ORIGIN: str = _env_or("FRONTEND_ORIGIN", "http://localhost:5173")

    UPLOADS_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")

    # -- Universal engine bounds (ENGINE_*) --------------------------------
    # Same rule as the role/module bounds above: never a fixed count of
    # anything per engagement -- a floor against a degenerate answer and a
    # ceiling against a runaway one; the registry decides the actual number.
    # The NAMES and defaults are frozen in app/engine/types.py BOUNDS so that
    # a bound the engine reads cannot exist without a setting an operator can
    # move, and vice versa (tests/engine/test_engine_types.py pins the pair).
    # Each is read from ENGINE_<NAME> and cast to the type of its default.
    ENGINE_MIN_QUESTIONS_PER_TURN: int
    ENGINE_MAX_QUESTIONS_PER_TURN: int
    ENGINE_MIN_QUESTION_VALUE: float
    ENGINE_ASK_FLOOR: float
    ENGINE_MAX_FANOUT: int
    ENGINE_SYMPTOM_MARGIN: float
    ENGINE_CHARTER_MIN_WEIGHT: float
    ENGINE_CHARTER_MIN_MARGIN: float
    ENGINE_MAX_DISCOVERY_TURNS: int
    ENGINE_MAX_ANALYSIS_ROUNDS: int
    ENGINE_MIN_WORK_PRODUCTS: int
    ENGINE_MAX_WORK_PRODUCTS: int
    ENGINE_MAX_SPECIALISTS_PER_ROUND: int
    ENGINE_MAX_METHODS_PER_ISSUE: int
    ENGINE_MIN_REVEALED_CHANGERS: int
    ENGINE_MIN_DISTINCT_DELIVERABLE_SETS: int
    ENGINE_MIN_DISTINCT_SECTION_SIGNATURES: int
    ENGINE_RENDERED_RESTATEMENT_TOLERANCE: float
    ENGINE_MAX_NARRATIVE_REGENERATIONS: int
    ENGINE_MAX_ENTITIES_PER_ANALYSIS_KIND: int

    def engine_bounds(self) -> dict:
        """Every BOUNDS name with its live value -- what MethodContext.settings
        carries, so a method reads bounds only, never a fixed count."""
        from app.engine.types import BOUNDS

        return {name: getattr(self, f"ENGINE_{name}") for name in BOUNDS}

    # The real BMV logo, drawn on the PDF deliverables' cover and side panel
    # (pipeline/export_pdf.py). A missing file means no mark, never a failure.
    BMV_LOGO_PATH: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "frontend", "public", "logo.png",
    )


def _install_engine_bounds() -> None:
    # Populated from the frozen table rather than written out by hand, so the
    # set of settings IS the set of bounds: adding a bound without a setting,
    # or a setting without a bound, is impossible by construction.
    from app.engine.types import BOUNDS

    for name, default in BOUNDS.items():
        cast = float if isinstance(default, float) else int
        setattr(Settings, f"ENGINE_{name}", cast(_env_or(f"ENGINE_{name}", str(default))))


_install_engine_bounds()

settings = Settings()
