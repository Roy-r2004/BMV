from app.core.config import settings
from app.infrastructure.ai_providers.ollama_provider import OllamaAIProvider

REQUIRED_MODELS = [
    {"id": "text", "name": settings.TEXT_MODEL, "label": "Text model", "purpose": "Blueprint & chat refinements"},
    {"id": "vision", "name": settings.VISION_MODEL, "label": "Vision model", "purpose": "Screenshot analysis"},
    {"id": "coder", "name": settings.CODER_MODEL, "label": "Coder model", "purpose": "Technical plan"},
]


def _model_matches(required: str, available: str) -> bool:
    return available == required or available.startswith(f"{required}:")


def get_ai_status() -> dict:
    if settings.AI_PROVIDER == "openrouter":
        return _openrouter_status()
    return _ollama_status()


def _ollama_status() -> dict:
    provider = OllamaAIProvider()
    try:
        available = provider.installed_models()
        ollama_reachable = True
    except Exception as exc:
        return {
            "ready": False,
            "provider": "ollama",
            "ollama_reachable": False,
            "message": "Ollama is not running yet. Start Ollama, then pull the required models.",
            "error": str(exc),
            "required_models": REQUIRED_MODELS,
            "installed_models": [],
            "missing_models": [m["name"] for m in REQUIRED_MODELS],
            "models_ready_count": 0,
            "models_required_count": len(REQUIRED_MODELS),
        }

    model_status = []
    missing = []

    for spec in REQUIRED_MODELS:
        present = any(_model_matches(spec["name"], name) for name in available)
        model_status.append({**spec, "present": present})
        if not present:
            missing.append(spec["name"])

    ready = len(missing) == 0
    if ready:
        message = "All AI models are ready."
    elif missing:
        message = (
            "AI models are still downloading. This is a one-time setup (~10 GB total). "
            "Preview generation and chat refinements will work once all models finish pulling."
        )
    else:
        message = "Checking AI models..."

    return {
        "ready": ready,
        "provider": "ollama",
        "ollama_reachable": ollama_reachable,
        "message": message,
        "required_models": model_status,
        "installed_models": available,
        "missing_models": missing,
        "models_ready_count": len(REQUIRED_MODELS) - len(missing),
        "models_required_count": len(REQUIRED_MODELS),
    }


def _openrouter_status() -> dict:
    if not settings.OPENROUTER_API_KEY:
        return {
            "ready": False,
            "provider": "openrouter",
            "ollama_reachable": False,
            "message": "Set OPENROUTER_API_KEY in backend/.env to enable AI.",
            "error": "Missing OPENROUTER_API_KEY",
            "required_models": [{**m, "present": False} for m in REQUIRED_MODELS],
            "installed_models": [],
            "missing_models": [m["name"] for m in REQUIRED_MODELS],
            "models_ready_count": 0,
            "models_required_count": len(REQUIRED_MODELS),
        }

    model_status = [{**spec, "present": True} for spec in REQUIRED_MODELS]

    return {
        "ready": True,
        "provider": "openrouter",
        "ollama_reachable": True,
        "message": "OpenRouter is connected. Models are served on demand — no local download needed.",
        "required_models": model_status,
        "installed_models": [m["name"] for m in REQUIRED_MODELS],
        "missing_models": [],
        "models_ready_count": len(REQUIRED_MODELS),
        "models_required_count": len(REQUIRED_MODELS),
    }
