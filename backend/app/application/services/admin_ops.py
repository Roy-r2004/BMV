"""Admin ops — settings, usage recording, overview aggregates."""
from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.admin_ops import AdminSettings, AiUsageEvent
from app.domain.models.request import Request
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.logging import get_logger

log = get_logger("AdminOps")

_settings_lock = Lock()
_settings_cache: dict | None = None
_settings_cached_at: float = 0.0
_CACHE_TTL_S = 5.0


def _settings_snapshot(row: AdminSettings) -> dict:
    return {
        "ai_enabled": bool(row.ai_enabled),
        "site_chat_enabled": bool(row.site_chat_enabled),
        "daily_budget_usd": row.daily_budget_usd,
    }

# Rough $/1M token fallback when OpenRouter omits usage.cost
_FALLBACK_RATES: dict[str, tuple[float, float]] = {
    "openrouter/free": (0.0, 0.0),
    "google/gemini-2.5-flash": (0.15, 0.60),
    "google/gemini-2.0-flash": (0.10, 0.40),
    "meta-llama/llama-3.1-8b-instruct": (0.06, 0.06),
    "anthropic/claude-haiku": (0.80, 4.00),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4o": (2.50, 10.00),
    "deepseek/deepseek-chat": (0.14, 0.28),
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return 0.0
    rates = _FALLBACK_RATES.get(model)
    if not rates:
        # Family match
        for key, val in _FALLBACK_RATES.items():
            if key in model or model.startswith(key.split("/")[0]):
                rates = val
                break
    if not rates:
        rates = (0.20, 0.60)  # conservative generic
    pin, cout = rates
    return (prompt_tokens / 1_000_000) * pin + (completion_tokens / 1_000_000) * cout


def ensure_settings(db: Session) -> AdminSettings:
    row = db.query(AdminSettings).filter(AdminSettings.id == 1).first()
    if row:
        return row
    row = AdminSettings(
        id=1,
        ai_enabled=True,
        site_chat_enabled=bool(settings.SITE_CHAT_ENABLED),
        daily_budget_usd=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class _SettingsView:
    """Detached settings snapshot safe for closed sessions."""

    __slots__ = ("ai_enabled", "site_chat_enabled", "daily_budget_usd")

    def __init__(self, data: dict) -> None:
        self.ai_enabled = bool(data["ai_enabled"])
        self.site_chat_enabled = bool(data["site_chat_enabled"])
        self.daily_budget_usd = data["daily_budget_usd"]


def get_settings(db: Session | None = None) -> _SettingsView:
    """Cached settings for hot path (AI gate)."""
    import time

    global _settings_cache, _settings_cached_at
    now = time.monotonic()
    with _settings_lock:
        if _settings_cache is not None and (now - _settings_cached_at) < _CACHE_TTL_S:
            return _SettingsView(_settings_cache)

    own = db is None
    session = db or SessionLocal()
    try:
        row = ensure_settings(session)
        snap = _settings_snapshot(row)
        with _settings_lock:
            _settings_cache = snap
            _settings_cached_at = time.monotonic()
        return _SettingsView(snap)
    finally:
        if own:
            session.close()


def invalidate_settings_cache() -> None:
    global _settings_cache, _settings_cached_at
    with _settings_lock:
        _settings_cache = None
        _settings_cached_at = 0.0


def update_settings(
    db: Session,
    *,
    ai_enabled: bool | None = None,
    site_chat_enabled: bool | None = None,
    daily_budget_usd: float | None | object = ...,
) -> AdminSettings:
    row = ensure_settings(db)
    if ai_enabled is not None:
        row.ai_enabled = bool(ai_enabled)
    if site_chat_enabled is not None:
        row.site_chat_enabled = bool(site_chat_enabled)
    if daily_budget_usd is not ...:
        row.daily_budget_usd = daily_budget_usd  # type: ignore[assignment]
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    invalidate_settings_cache()
    return row


def cost_since(db: Session, since: datetime) -> float:
    val = (
        db.query(func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0))
        .filter(AiUsageEvent.created_at >= since, AiUsageEvent.success.is_(True))
        .scalar()
    )
    return float(val or 0.0)


def ai_is_allowed(purpose: str = "pipeline") -> tuple[bool, str]:
    """Return (allowed, reason)."""
    try:
        cfg = get_settings()
    except Exception as exc:
        log.warning("settings read failed: %s", exc)
        return True, ""

    if purpose == "site_chat":
        if not cfg.site_chat_enabled:
            return False, "Site chat is disabled by admin."
        # Site chat also respects master AI switch
        if not cfg.ai_enabled:
            return False, "AI is paused by admin."
        return True, ""

    if not cfg.ai_enabled:
        return False, "AI is paused by admin."

    if cfg.daily_budget_usd is not None and cfg.daily_budget_usd >= 0:
        db = SessionLocal()
        try:
            start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            spent = cost_since(db, start)
            if spent >= float(cfg.daily_budget_usd):
                return False, f"Daily AI budget reached (${spent:.2f} / ${cfg.daily_budget_usd:.2f})."
        finally:
            db.close()
    return True, ""


def record_usage(
    *,
    provider: str,
    model: str,
    purpose: str = "unknown",
    request_id: int | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    cost_usd: float | None = None,
    success: bool = True,
    error: str | None = None,
    latency_ms: int | None = None,
) -> None:
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
    if cost_usd is None and success:
        cost_usd = _estimate_cost(model, prompt_tokens, completion_tokens)

    db = SessionLocal()
    try:
        db.add(
            AiUsageEvent(
                provider=provider,
                model=model,
                purpose=purpose[:80],
                request_id=request_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
                success=success,
                error=(error or "")[:2000] or None,
                latency_ms=latency_ms,
            )
        )
        db.commit()
    except Exception as exc:
        log.warning("failed to record AI usage: %s", exc)
        db.rollback()
    finally:
        db.close()


def parse_openrouter_usage(data: dict) -> tuple[int, int, int, float | None]:
    usage = data.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or (prompt + completion))
    cost = usage.get("cost")
    if cost is None:
        cost = usage.get("total_cost")
    try:
        cost_f = float(cost) if cost is not None else None
    except (TypeError, ValueError):
        cost_f = None
    return prompt, completion, total, cost_f


def build_overview(db: Session) -> dict:
    cfg = ensure_settings(db)
    now = datetime.utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=6)

    total_requests = db.query(func.count(Request.id)).scalar() or 0
    requests_today = (
        db.query(func.count(Request.id)).filter(Request.created_at >= day_start).scalar() or 0
    )

    status_rows = (
        db.query(Request.status, func.count(Request.id)).group_by(Request.status).all()
    )
    by_status = {str(s or "unknown"): int(c) for s, c in status_rows}

    calls_today = (
        db.query(func.count(AiUsageEvent.id))
        .filter(AiUsageEvent.created_at >= day_start)
        .scalar()
        or 0
    )
    failed_today = (
        db.query(func.count(AiUsageEvent.id))
        .filter(AiUsageEvent.created_at >= day_start, AiUsageEvent.success.is_(False))
        .scalar()
        or 0
    )
    tokens_today = (
        db.query(func.coalesce(func.sum(AiUsageEvent.total_tokens), 0))
        .filter(AiUsageEvent.created_at >= day_start)
        .scalar()
        or 0
    )

    model_rows = (
        db.query(
            AiUsageEvent.model,
            func.count(AiUsageEvent.id),
            func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0),
            func.coalesce(func.sum(AiUsageEvent.total_tokens), 0),
        )
        .filter(AiUsageEvent.created_at >= day_start, AiUsageEvent.success.is_(True))
        .group_by(AiUsageEvent.model)
        .order_by(func.sum(AiUsageEvent.cost_usd).desc())
        .limit(8)
        .all()
    )
    top_models = [
        {
            "model": m,
            "calls": int(c),
            "cost_usd": round(float(cost or 0), 4),
            "tokens": int(tok or 0),
        }
        for m, c, cost, tok in model_rows
    ]

    failures = (
        db.query(AiUsageEvent)
        .filter(AiUsageEvent.success.is_(False))
        .order_by(AiUsageEvent.created_at.desc())
        .limit(25)
        .all()
    )

    recent_usage = (
        db.query(AiUsageEvent)
        .order_by(AiUsageEvent.created_at.desc())
        .limit(40)
        .all()
    )

    cost_today = cost_since(db, day_start)
    cost_7d = cost_since(db, week_start)

    return {
        "provider": settings.AI_PROVIDER,
        "ai_enabled": bool(cfg.ai_enabled),
        "site_chat_enabled": bool(cfg.site_chat_enabled),
        "daily_budget_usd": cfg.daily_budget_usd,
        "requests_total": int(total_requests),
        "requests_today": int(requests_today),
        "by_status": by_status,
        "cost_today_usd": round(cost_today, 4),
        "cost_7d_usd": round(cost_7d, 4),
        "tokens_today": int(tokens_today),
        "calls_today": int(calls_today),
        "failed_today": int(failed_today),
        "top_models_today": top_models,
        "recent_failures": [_event_dict(e) for e in failures],
        "recent_usage": [_event_dict(e) for e in recent_usage],
        "budget_remaining_usd": (
            None
            if cfg.daily_budget_usd is None
            else round(max(0.0, float(cfg.daily_budget_usd) - cost_today), 4)
        ),
    }


def _event_dict(e: AiUsageEvent) -> dict:
    return {
        "id": e.id,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "provider": e.provider,
        "model": e.model,
        "purpose": e.purpose,
        "request_id": e.request_id,
        "prompt_tokens": e.prompt_tokens,
        "completion_tokens": e.completion_tokens,
        "total_tokens": e.total_tokens,
        "cost_usd": e.cost_usd,
        "success": e.success,
        "error": e.error,
        "latency_ms": e.latency_ms,
    }


def list_usage(db: Session, *, days: int = 7, limit: int = 200) -> list[dict]:
    since = datetime.utcnow() - timedelta(days=max(1, min(days, 90)))
    rows = (
        db.query(AiUsageEvent)
        .filter(AiUsageEvent.created_at >= since)
        .order_by(AiUsageEvent.created_at.desc())
        .limit(min(limit, 500))
        .all()
    )
    return [_event_dict(r) for r in rows]
