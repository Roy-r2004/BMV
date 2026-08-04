"""Admin ops — settings, usage recording, overview aggregates."""
from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock

from sqlalchemy import case, func
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
        "request_budget_usd": getattr(row, "request_budget_usd", None),
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
        request_budget_usd=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class _SettingsView:
    """Detached settings snapshot safe for closed sessions."""

    __slots__ = ("ai_enabled", "site_chat_enabled", "daily_budget_usd", "request_budget_usd")

    def __init__(self, data: dict) -> None:
        self.ai_enabled = bool(data["ai_enabled"])
        self.site_chat_enabled = bool(data["site_chat_enabled"])
        self.daily_budget_usd = data["daily_budget_usd"]
        self.request_budget_usd = data.get("request_budget_usd")


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
    request_budget_usd: float | None | object = ...,
) -> AdminSettings:
    row = ensure_settings(db)
    if ai_enabled is not None:
        row.ai_enabled = bool(ai_enabled)
    if site_chat_enabled is not None:
        row.site_chat_enabled = bool(site_chat_enabled)
    if daily_budget_usd is not ...:
        row.daily_budget_usd = daily_budget_usd  # type: ignore[assignment]
    if request_budget_usd is not ...:
        row.request_budget_usd = request_budget_usd  # type: ignore[assignment]
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    invalidate_settings_cache()
    return row


def request_cost(db: Session, request_id: int) -> float:
    val = (
        db.query(func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0))
        .filter(AiUsageEvent.request_id == request_id, AiUsageEvent.success.is_(True))
        .scalar()
    )
    return float(val or 0.0)


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
                try:
                    from app.application.services.admin_alerts import emit_alert

                    emit_alert(
                        kind="daily_budget",
                        severity="critical",
                        title="Daily AI budget reached",
                        body=f"${spent:.2f} / ${cfg.daily_budget_usd:.2f}",
                        dedupe_minutes=60,
                    )
                except Exception:
                    pass
                return False, f"Daily AI budget reached (${spent:.2f} / ${cfg.daily_budget_usd:.2f})."
        finally:
            db.close()

    # Per-request hard cap (pipeline / vision only)
    if cfg.request_budget_usd is not None and cfg.request_budget_usd >= 0:
        from app.application.services.ai_context import get_ai_request_id

        rid = get_ai_request_id()
        if rid:
            db = SessionLocal()
            try:
                spent = request_cost(db, rid)
                if spent >= float(cfg.request_budget_usd):
                    try:
                        from app.application.services.admin_alerts import emit_alert

                        emit_alert(
                            kind="request_budget",
                            severity="critical",
                            title=f"Request #{rid} hit cost cap",
                            body=f"${spent:.4f} / ${cfg.request_budget_usd:.2f}",
                            request_id=rid,
                            dedupe_minutes=30,
                        )
                    except Exception:
                        pass
                    return False, (
                        f"Request AI budget reached (${spent:.4f} / ${cfg.request_budget_usd:.2f})."
                    )
                req = db.query(Request).filter(Request.id == rid).first()
                if req and getattr(req, "generation_cancel", False):
                    return False, "Generation cancelled by admin."
            finally:
                db.close()

    return True, ""


#: Purposes that are a provider default rather than a statement about the call,
#: so a stage name from the request context is strictly better information.
_GENERIC_PURPOSES = ("unknown", "pipeline", "vision")


def presumed_usable(
    *,
    success: bool,
    output_chars: int | None,
    finish_reason: str | None,
    completion_tokens: int | None = 0,
) -> tuple[bool, str | None]:
    """The provider-side half of the usable verdict.

    Three shapes are unusable on their face and need no caller to say so: the
    model was cut off mid-answer, the transport failed, or the body was empty.
    Anything else is presumed usable until whoever had to read it disagrees —
    `AICall.unusable()` is that disagreement.

    Truncation is checked *before* transport, and that ordering is load-bearing.
    Eighteen of the nineteen failed calls across requests 66–71 carry
    `provider_truncated_output`: the socket was fine and the model simply ran
    out of tokens. Filing all of them under "transport" would point the next
    engineer at the network, which is not where the 2,105 s went.

    **`finish_reason: error` is a 200 that failed mid-stream**, and only when it
    billed no output tokens. The provider returns HTTP 200 with a partial body,
    so `call_with_retry` never sees a failure and the application re-asks
    instead — 14 of `slot_fill`'s 28 rejected calls on duo 1 are this, read by
    the caller as "the model wrote a truncated file". Across the corpus: 55
    calls and 474.4 s, of which 15 were presumed **usable** because nothing
    looked at `finish_reason` beyond `length`. The billed-tokens condition is
    the whole guard — 24 other `error` rows carry real completion tokens and
    514.3 s of work the pipeline used, and condemning those would trade one
    wrong number for another.
    """

    from app.application.services.ai_context import (
        UNUSABLE_EMPTY,
        UNUSABLE_TRANSPORT,
        UNUSABLE_TRUNCATED,
    )

    if finish_reason and str(finish_reason).lower() in ("length", "max_tokens"):
        return False, UNUSABLE_TRUNCATED
    if not success:
        return False, UNUSABLE_TRANSPORT
    if str(finish_reason or "").lower() == "error" and int(completion_tokens or 0) <= 0:
        return False, UNUSABLE_TRANSPORT
    if output_chars is not None and int(output_chars) <= 0:
        return False, UNUSABLE_EMPTY
    return True, None


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
    finish_reason: str | None = None,
    output_chars: int | None = None,
) -> None:
    from app.application.services.ai_context import (
        current_ai_call,
        get_ai_purpose,
        get_ai_request_id,
        observe_ai_usage,
    )

    if request_id is None:
        request_id = get_ai_request_id()
    ctx_purpose = get_ai_purpose()
    if ctx_purpose and purpose in _GENERIC_PURPOSES:
        purpose = ctx_purpose

    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
    if cost_usd is None and success:
        cost_usd = _estimate_cost(model, prompt_tokens, completion_tokens)

    usable, unusable_reason = presumed_usable(
        success=success,
        output_chars=output_chars,
        finish_reason=finish_reason,
        completion_tokens=completion_tokens,
    )

    call = current_ai_call()
    row = {
        "provider": provider,
        "model": model,
        "purpose": purpose,
        "request_id": request_id,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": float(cost_usd or 0.0),
        "success": success,
        "error": error,
        "latency_ms": int(latency_ms or 0),
        "stage": (call.stage if call and call.stage else None) or purpose,
        "writer": call.writer if call else None,
        "attempt": call.attempt if call else 1,
        "finish_reason": finish_reason or None,
        "output_chars": None if output_chars is None else int(output_chars),
        "usable": usable,
        "unusable_reason": unusable_reason,
        "ops_applied": None,
    }

    observe_ai_usage(dict(row))

    if call is not None:
        # Buffered, not skipped: the scope writes it once, at exit, with the
        # usability verdict already on it. No second round trip to adjudicate.
        call.record(row)
        return
    flush_usage_rows([row])


def flush_usage_rows(rows: list[dict]) -> None:
    """Write buffered usage rows. One session, one commit, never raises.

    Batching matters: an `ai_call` scope covering a four-model failover chain
    writes four rows in one transaction instead of four.
    """

    if not rows:
        return
    db = SessionLocal()
    try:
        for row in rows:
            db.add(
                AiUsageEvent(
                    provider=row.get("provider") or "unknown",
                    model=row.get("model") or "unknown",
                    purpose=str(row.get("purpose") or "unknown")[:80],
                    request_id=row.get("request_id"),
                    prompt_tokens=int(row.get("prompt_tokens") or 0),
                    completion_tokens=int(row.get("completion_tokens") or 0),
                    total_tokens=int(row.get("total_tokens") or 0),
                    cost_usd=row.get("cost_usd"),
                    success=bool(row.get("success")),
                    error=(row.get("error") or "")[:2000] or None,
                    latency_ms=row.get("latency_ms"),
                    stage=(str(row.get("stage"))[:64] if row.get("stage") else None),
                    writer=(str(row.get("writer"))[:80] if row.get("writer") else None),
                    attempt=row.get("attempt"),
                    finish_reason=(
                        str(row.get("finish_reason"))[:40] if row.get("finish_reason") else None
                    ),
                    output_chars=row.get("output_chars"),
                    usable=row.get("usable"),
                    unusable_reason=(
                        str(row.get("unusable_reason"))[:80]
                        if row.get("unusable_reason")
                        else None
                    ),
                    ops_applied=row.get("ops_applied"),
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

    from app.application.services.admin_alerts import list_alerts
    from app.domain.models.admin_ops import AdminAlert

    unread_alerts = (
        db.query(func.count(AdminAlert.id)).filter(AdminAlert.acknowledged.is_(False)).scalar() or 0
    )

    return {
        "provider": settings.AI_PROVIDER,
        "ai_enabled": bool(cfg.ai_enabled),
        "site_chat_enabled": bool(cfg.site_chat_enabled),
        "daily_budget_usd": cfg.daily_budget_usd,
        "request_budget_usd": getattr(cfg, "request_budget_usd", None),
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
        "action_queue": build_action_queue(db),
        "alerts": list_alerts(db, unread_only=True, limit=20),
        "unread_alerts": int(unread_alerts),
        "budget_remaining_usd": (
            None
            if cfg.daily_budget_usd is None
            else round(max(0.0, float(cfg.daily_budget_usd) - cost_today), 4)
        ),
    }


def build_action_queue(db: Session, *, limit: int = 40) -> list[dict]:
    """Prioritized work items for the admin home screen."""
    from app.application.services.progress import FAILED_STAGES, is_request_generating, parse_progress_snapshot

    items: list[dict] = []
    recent = db.query(Request).order_by(Request.updated_at.desc()).limit(120).all()
    costs = costs_for_request_ids(db, [r.id for r in recent])
    now = datetime.utcnow()

    for req in recent:
        snap = parse_progress_snapshot(getattr(req, "generation_log", None))
        stage = str(snap.get("stage") or "")
        generating = is_request_generating(req)
        cost = (costs.get(req.id) or {}).get("cost_usd", 0.0)
        base = {
            "request_id": req.id,
            "business_name": req.business_name,
            "status": req.status,
            "stage": stage or None,
            "pct": snap.get("pct"),
            "label": snap.get("label"),
            "cost_usd": cost,
            "email": req.email,
            "updated_at": req.updated_at.isoformat() if req.updated_at else None,
        }

        if req.build_requested and req.status in ("new", "reviewing", "proposal sent", None, ""):
            items.append({**base, "kind": "build_requested", "priority": 10, "reason": "Customer requested a build"})

        if stage in FAILED_STAGES or req.status == "failed":
            items.append({**base, "kind": "failed", "priority": 20, "reason": snap.get("label") or "Generation failed"})

        if generating:
            # Stuck if no update for 20+ minutes
            stuck = False
            try:
                updated = req.updated_at or req.created_at
                if updated and (now - updated).total_seconds() > 20 * 60:
                    stuck = True
            except Exception:
                pass
            if stuck:
                items.append({**base, "kind": "stuck", "priority": 15, "reason": "No progress for 20+ minutes"})
            else:
                items.append({**base, "kind": "running", "priority": 40, "reason": snap.get("label") or "Generating"})

        if req.status == "new" and not generating and stage not in FAILED_STAGES:
            age_h = 0.0
            try:
                if req.created_at:
                    age_h = (now - req.created_at).total_seconds() / 3600
            except Exception:
                pass
            items.append(
                {
                    **base,
                    "kind": "new",
                    "priority": 30,
                    "reason": f"New submission ({age_h:.1f}h ago)" if age_h else "New submission",
                }
            )

        cfg = get_settings()
        if cfg.request_budget_usd is not None and cost >= float(cfg.request_budget_usd) * 0.85:
            items.append(
                {
                    **base,
                    "kind": "cost_warn",
                    "priority": 25,
                    "reason": f"Near/over request cap (${cost:.4f})",
                }
            )

    # Deduplicate by (request_id, kind), keep highest priority (lowest number)
    best: dict[tuple[int, str], dict] = {}
    for it in items:
        key = (it["request_id"], it["kind"])
        prev = best.get(key)
        if prev is None or it["priority"] < prev["priority"]:
            best[key] = it

    ordered = sorted(best.values(), key=lambda x: (x["priority"], -(x.get("cost_usd") or 0)))
    return ordered[:limit]


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


def costs_for_request_ids(db: Session, request_ids: list[int]) -> dict[int, dict]:
    """Aggregate AI spend per request id."""
    if not request_ids:
        return {}
    rows = (
        db.query(
            AiUsageEvent.request_id,
            func.count(AiUsageEvent.id),
            func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0),
            func.coalesce(func.sum(AiUsageEvent.total_tokens), 0),
            func.coalesce(
                func.sum(case((AiUsageEvent.success.is_(False), 1), else_=0)),
                0,
            ),
        )
        .filter(AiUsageEvent.request_id.in_(request_ids))
        .group_by(AiUsageEvent.request_id)
        .all()
    )
    out: dict[int, dict] = {}
    for rid, calls, cost, tokens, fails in rows:
        if rid is None:
            continue
        out[int(rid)] = {
            "calls": int(calls or 0),
            "cost_usd": round(float(cost or 0), 6),
            "tokens": int(tokens or 0),
            "failed_calls": int(fails or 0),
        }
    return out


def build_request_run_log(db: Session, request_id: int) -> dict | None:
    """Cost totals + AI events + generation progress log for one request."""
    from app.application.services.progress import parse_progress_snapshot

    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        return None

    events = (
        db.query(AiUsageEvent)
        .filter(AiUsageEvent.request_id == request_id)
        .order_by(AiUsageEvent.created_at.asc(), AiUsageEvent.id.asc())
        .all()
    )
    event_dicts = [_event_dict(e) for e in events]

    cost_total = sum(float(e.cost_usd or 0) for e in events if e.success)
    tokens_total = sum(int(e.total_tokens or 0) for e in events)
    failed = sum(1 for e in events if not e.success)

    by_purpose: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    for e in events:
        for bucket, key in ((by_purpose, e.purpose or "unknown"), (by_model, e.model or "unknown")):
            row = bucket.setdefault(key, {"calls": 0, "cost_usd": 0.0, "tokens": 0, "failed": 0})
            row["calls"] += 1
            row["tokens"] += int(e.total_tokens or 0)
            if e.success:
                row["cost_usd"] += float(e.cost_usd or 0)
            else:
                row["failed"] += 1

    def _sorted(bucket: dict[str, dict]) -> list[dict]:
        return [
            {"key": k, **{**v, "cost_usd": round(v["cost_usd"], 6)}}
            for k, v in sorted(bucket.items(), key=lambda kv: kv[1]["cost_usd"], reverse=True)
        ]

    progress = parse_progress_snapshot(getattr(req, "generation_log", None))
    progress_log = progress.get("log") if isinstance(progress.get("log"), list) else []

    # Unified timeline for the admin UI
    timeline: list[dict] = []
    for item in progress_log:
        if not isinstance(item, dict):
            continue
        timeline.append(
            {
                "kind": "progress",
                "at": item.get("t"),
                "message": item.get("msg") or "",
                "detail": item.get("detail") or "",
            }
        )
    for e in event_dicts:
        ts = None
        if e.get("created_at"):
            try:
                ts = int(datetime.fromisoformat(e["created_at"]).timestamp())
            except Exception:
                ts = None
        timeline.append(
            {
                "kind": "ai",
                "at": ts,
                "message": f"{'OK' if e.get('success') else 'FAIL'} · {e.get('purpose')} · {e.get('model')}",
                "detail": e.get("error") or "",
                "cost_usd": e.get("cost_usd"),
                "tokens": e.get("total_tokens"),
                "latency_ms": e.get("latency_ms"),
                "success": e.get("success"),
                "event_id": e.get("id"),
            }
        )
    timeline.sort(key=lambda x: (x.get("at") is None, x.get("at") or 0))

    from app.application.services.progress import is_request_generating

    return {
        "request_id": request_id,
        "business_name": req.business_name,
        "status": req.status,
        "cost_usd": round(cost_total, 6),
        "tokens": tokens_total,
        "calls": len(events),
        "failed_calls": failed,
        "is_generating": is_request_generating(req),
        "cancel_requested": bool(getattr(req, "generation_cancel", False)),
        "by_purpose": _sorted(by_purpose),
        "by_model": _sorted(by_model),
        "usage_events": event_dicts,
        "progress": {
            "stage": progress.get("stage"),
            "label": progress.get("label"),
            "pct": progress.get("pct"),
            "detail": progress.get("detail"),
            "files_done": progress.get("files_done"),
            "files_total": progress.get("files_total"),
            "updated_at": progress.get("updated_at"),
            "log": progress_log,
        },
        "timeline": timeline,
    }
