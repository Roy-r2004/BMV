import os

from dotenv import load_dotenv

load_dotenv()


def _env_or(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


class Settings:
    # Everything routes through OpenRouter — one key, one place cost is tracked.
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "").strip()
    ANALYSIS_MODEL: str = _env_or("ANALYSIS_MODEL", "google/gemini-2.5-flash")
    # Bake-off (2026-08-10, dashboard-image-v1 prompt, same input): gemini-3-pro
    # rendered a crisp true-16:9 desktop screenshot at $0.14; gpt-5.4-image-2 was
    # close but square/softer at $0.25; gpt-5-image bled content off both edges
    # with typos at $0.29. Gemini also accepts image input, which the
    # screen-continuation step needs.
    IMAGE_MODEL: str = _env_or("IMAGE_MODEL", "google/gemini-3-pro-image")

    # ── Per-role, per-archetype image models (W1) ─────────────────────────
    # The anchor screen and the follow-up screens are different jobs: the
    # anchor invents a design, the follow-ups copy one they're handed as a
    # reference image. So the model is chosen per ROLE, and per archetype —
    # a kanban pipeline and a chart-led analytics screen don't have to be
    # best served by the same model. Entries are written here ONLY from a
    # measured bake-off (see docs/evidence/session31/images-bakeoff.md);
    # anything absent falls back to IMAGE_MODEL, so an archetype nobody has
    # measured behaves exactly as before.
    #
    # Measured 2026-08-11, W1 bake-off (docs/evidence/session31/images-bakeoff.md).
    # Same answer on all three archetypes measured, so the entries are
    # identical — kept per-archetype anyway because that is the axis a
    # future measurement will disagree on, and a shared constant would
    # quietly hide the disagreement:
    #   anchor   = gemini-3-pro-image. Won the swap-tested pairwise on crm
    #              and analytics, tied on operations, and matched or beat
    #              flash's anchor QA everywhere (8.7 / 8.7 / 8.7 vs
    #              8.7 / 7.9 / 8.7). gpt-5.4-image-2 was eliminated: it
    #              renders SQUARE, took 354s, and scored lowest.
    #   followup = gemini-3.1-flash-image. Follow-ups copy a design they
    #              are handed as a reference image rather than inventing
    #              one, which is the cheaper job — and all-pro costs $0.72
    #              for a 3-screen request, over the $0.60 DoD line, while
    #              this tiering measured $0.583 at 175s.
    # HONEST LIMIT: the pro-anchor + flash-follow-up combination was
    # measured end-to-end on operations-dashboard only. crm and analytics
    # inherit it by extrapolation from their all-flash follow-up scores
    # (8.7 and 7.0), not from a tiering run of their own.
    ARCHETYPE_IMAGE_MODELS: dict[str, dict[str, str]] = {
        "operations-dashboard": {"anchor": "google/gemini-3-pro-image", "followup": "google/gemini-3.1-flash-image"},
        "crm-dashboard": {"anchor": "google/gemini-3-pro-image", "followup": "google/gemini-3.1-flash-image"},
        "analytics-dashboard": {"anchor": "google/gemini-3-pro-image", "followup": "google/gemini-3.1-flash-image"},
        # scheduling-dashboard and pipeline-dashboard are unmeasured — no
        # golden brief landed on them — so they fall back to IMAGE_MODEL.
    }
    # Operator-level escape hatches (env), used by bake-off runs and by
    # incident response — they outrank the measured table on purpose.
    IMAGE_MODEL_ANCHOR: str = _env_or("IMAGE_MODEL_ANCHOR", "")
    IMAGE_MODEL_FOLLOWUP: str = _env_or("IMAGE_MODEL_FOLLOWUP", "")

    def anchor_model_for(self, archetype_id: str | None) -> str:
        return (
            self.IMAGE_MODEL_ANCHOR
            or self.ARCHETYPE_IMAGE_MODELS.get(archetype_id or "", {}).get("anchor")
            or self.IMAGE_MODEL
        )

    def followup_model_for(self, archetype_id: str | None) -> str:
        return (
            self.IMAGE_MODEL_FOLLOWUP
            or self.ARCHETYPE_IMAGE_MODELS.get(archetype_id or "", {}).get("followup")
            or self.IMAGE_MODEL
        )

    # Soft bounds, not a fixed target — the plan stage decides the actual
    # count per business (see prompts/plan.j2). MIN only guards the fallback
    # path; MAX is a cost/sanity cap on a real model response.
    MIN_ROLES_PER_REQUEST: int = int(_env_or("MIN_ROLES_PER_REQUEST", "2"))
    MAX_ROLES_PER_REQUEST: int = int(_env_or("MAX_ROLES_PER_REQUEST", "4"))
    VARIANTS_PER_ROLE: int = int(_env_or("VARIANTS_PER_ROLE", "2"))

    # ── Demo-screenshot pipeline (cost knobs — this is lead gen) ──────────
    # Screens per request (anchor dashboard + follow-ups, 2-3).
    DEMO_SCREEN_COUNT: int = int(_env_or("DEMO_SCREEN_COUNT", "3"))
    # Candidates generated for the anchor screen; the vision judge picks the
    # best. More candidates = better anchor = better whole set, since every
    # follow-up screen inherits the anchor's look via reference image.
    DASHBOARD_CANDIDATES: int = int(_env_or("DASHBOARD_CANDIDATES", "3"))
    SECONDARY_CANDIDATES: int = int(_env_or("SECONDARY_CANDIDATES", "1"))
    # Vision-model QA over every candidate (cheap flash call per image).
    ENABLE_VISION_QA: bool = _env_bool("ENABLE_VISION_QA", True)
    QA_MODEL: str = _env_or("QA_MODEL", _env_or("ANALYSIS_MODEL", "google/gemini-2.5-flash"))
    QA_MIN_SCORE: float = float(_env_or("QA_MIN_SCORE", "7"))
    # The pairwise judge ("which of these two is better") is a separate
    # instrument from the per-image scorer and may need more capability:
    # comparing two dense screenshots is harder than scoring one. Kept as
    # its own setting so it can be strengthened WITHOUT ever varying the
    # per-image judge — the rule is that judge and generator never change
    # together, not that one model must do both jobs.
    PAIRWISE_JUDGE_MODEL: str = _env_or("PAIRWISE_JUDGE_MODEL", _env_or("QA_MODEL", "google/gemini-2.5-flash"))
    # At most ONE extra attempt per screen when no candidate is approved —
    # never an open-ended regeneration loop.
    MAX_REGENERATIONS: int = int(_env_or("MAX_REGENERATIONS", "1"))
    # Attach the selected anchor screenshot to follow-up screen calls so all
    # screens look like the same product (needs an image-input-capable model).
    USE_REFERENCE_IMAGES: bool = _env_bool("USE_REFERENCE_IMAGES", True)
    # Money-safety valve on the open intake endpoint: how many requests may
    # be generating simultaneously before new submissions get a 429.
    MAX_CONCURRENT_GENERATIONS: int = int(_env_or("MAX_CONCURRENT_GENERATIONS", "3"))

    DATABASE_URL: str = _env_or("DATABASE_URL", "sqlite:///./consultant.db")
    PORT: int = int(_env_or("PORT", "8002"))
    FRONTEND_ORIGIN: str = _env_or("FRONTEND_ORIGIN", "http://localhost:5173")

    UPLOADS_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")

    # The real BMV logo, composited onto every generated image as a corner
    # credit mark — more reliable than asking the image model to draw
    # legible "BMV" text (we've seen it garble small text like URLs/labels).
    BMV_LOGO_PATH: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "frontend", "public", "logo.png",
    )


settings = Settings()
