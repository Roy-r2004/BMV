import os

from dotenv import load_dotenv

load_dotenv()


def _env_or(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


class Settings:
    # Everything routes through OpenRouter — one key, one place cost is tracked.
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "").strip()
    ANALYSIS_MODEL: str = _env_or("ANALYSIS_MODEL", "google/gemini-2.5-flash")
    IMAGE_MODEL: str = _env_or("IMAGE_MODEL", "openai/gpt-5-image")

    # Soft bounds, not a fixed target — the plan stage decides the actual
    # count per business (see prompts/plan.j2). MIN only guards the fallback
    # path; MAX is a cost/sanity cap on a real model response.
    MIN_ROLES_PER_REQUEST: int = int(_env_or("MIN_ROLES_PER_REQUEST", "2"))
    MAX_ROLES_PER_REQUEST: int = int(_env_or("MAX_ROLES_PER_REQUEST", "4"))
    VARIANTS_PER_ROLE: int = int(_env_or("VARIANTS_PER_ROLE", "2"))

    DATABASE_URL: str = _env_or("DATABASE_URL", "sqlite:///./consultant.db")
    PORT: int = int(_env_or("PORT", "8002"))
    FRONTEND_ORIGIN: str = _env_or("FRONTEND_ORIGIN", "http://localhost:5173")

    UPLOADS_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")


settings = Settings()
