"""AI authoring and repair primitives for the canonical AppSpec.

This module deliberately does not persist or approve a contract. It renders the
schema directly from :class:`AppSpec`, requests one JSON candidate, and parses it.
Deterministic validation, independent coverage review, retry policy, and storage
belong to ``app_spec_generation``.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.application.prompts import PromptTemplate
from app.application.services.ai_context import ai_call
from app.core.config import settings
from app.domain.appspec.authoring_parser import (
    AUTHORING_JSON_SYNTAX_INVALID,
    AUTHORING_JSON_TRUNCATED,
    AUTHORING_NO_JSON_OBJECT,
    AUTHORING_RESPONSE_FIELD_MISSING,
    authoring_parse_diagnostics,
    parse_appspec_authoring_output,
)
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.schemas.app_spec import AppSpec
from app.infrastructure.ai_providers.model_capabilities import resolve_model_capability
from app.infrastructure.ai_providers.response_parser import ProviderGenerationError

# One compact corrective retry for malformed authoring JSON. Does not raise the
# configured APPSPEC_MAX_CALLS / repair ceilings.
APPSPEC_AUTHORING_MALFORMED_RETRY_MAX = 1

_COMPACT_JSON_RETRY_INSTRUCTION = (
    "Return one complete JSON object that satisfies the supplied AppSpec schema. "
    "No prose. No markdown. No code fences. Do not abbreviate or truncate."
)


class AppSpecBuildError(RuntimeError):
    """The authoring model did not return a usable AppSpec candidate."""

    def __init__(
        self,
        message: str,
        *,
        response_excerpt: str = "",
        raw_response_sha256: str = "",
        json_extraction: Mapping[str, Any] | None = None,
        typed_error: str | None = None,
        authoring_diagnostics: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.response_excerpt = response_excerpt
        self.raw_response_sha256 = raw_response_sha256
        self.json_extraction = dict(json_extraction or {})
        self.typed_error = typed_error
        self.authoring_diagnostics = dict(authoring_diagnostics or {})


@dataclass(frozen=True)
class AppSpecCandidate:
    """A parsed JSON candidate plus a bounded excerpt useful for diagnostics."""

    payload: dict[str, Any]
    response_excerpt: str = ""
    raw_response_sha256: str = ""
    raw_char_count: int = 0
    json_extraction: Mapping[str, Any] | None = None
    parent_payload_sha256: str = ""
    repair_type: str = ""
    authoring_diagnostics: Mapping[str, Any] | None = None


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, BaseException):
        return f"{type(value).__name__}: {value}"
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _provider_completion_meta(ai_provider: AIProvider) -> dict[str, Any]:
    for target in (ai_provider, getattr(ai_provider, "provider", None)):
        if target is None:
            continue
        getter = getattr(target, "last_completion_meta", None)
        if callable(getter):
            meta = getter()
            if isinstance(meta, dict):
                return dict(meta)
        meta = getattr(target, "_last_completion_meta", None)
        if isinstance(meta, dict):
            return dict(meta)
    return {}


def _structured_output_request(model: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    profile = resolve_model_capability(model)
    supported = bool(profile.known and profile.supports_json_object)
    diagnostics = {
        "model": profile.model,
        "known": profile.known,
        "structured_output_mode_supported": supported,
        "supports_json_object": profile.supports_json_object,
        "supports_json_schema": profile.supports_json_schema,
        "supports_strict_json_schema": profile.supports_strict_json_schema,
        "capability_profile_revision": profile.revision,
    }
    if not supported:
        return None, {
            **diagnostics,
            "structured_output_mode_requested": None,
        }
    # JSON-object mode only — never send unsupported json_schema params.
    request = {"type": "json_object"}
    return request, {
        **diagnostics,
        "structured_output_mode_requested": "json_object",
    }


def _ask_appspec_chat(
    ai_provider: AIProvider,
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict[str, Any]]:
    response_format, structured_diag = _structured_output_request(model)
    ask_kwargs: dict[str, Any] = {
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format is not None:
        ask_kwargs["response_format"] = response_format
    try:
        raw = ai_provider.ask_chat(model, messages, **ask_kwargs)
    except TypeError:
        # Older/test doubles may not accept response_format.
        if "response_format" in ask_kwargs:
            ask_kwargs.pop("response_format", None)
            structured_diag = {
                **structured_diag,
                "structured_output_mode_requested": None,
                "structured_output_kwarg_unsupported": True,
            }
            raw = ai_provider.ask_chat(model, messages, **ask_kwargs)
        else:
            raise
    completion = _provider_completion_meta(ai_provider)
    diagnostics = {
        **structured_diag,
        "provider": completion.get("provider")
        or str(getattr(ai_provider, "name", "unknown") or "unknown"),
        "response_field_used": completion.get("response_field")
        or "choices[0].message.content",
        "input_tokens": completion.get("input_tokens"),
        "output_tokens": completion.get("output_tokens"),
        "total_tokens": completion.get("total_tokens"),
        "max_output_tokens": max_tokens,
        "finish_reason": completion.get("finish_reason"),
        "truncated": bool(completion.get("truncated")),
        "provider_text_chars": completion.get("text_chars"),
    }
    return raw, diagnostics


def _parse_candidate(
    raw: str | None,
    *,
    finish_reason: str | None = None,
    provider_diagnostics: Mapping[str, Any] | None = None,
    response_field_present: bool = True,
) -> AppSpecCandidate:
    text = raw if isinstance(raw, str) else ""
    field_present = response_field_present
    if provider_diagnostics and provider_diagnostics.get(
        "response_field_present"
    ) is False:
        field_present = False
    raw_sha = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""
    parsed = parse_appspec_authoring_output(
        text,
        finish_reason=finish_reason
        or (provider_diagnostics or {}).get("finish_reason"),
        response_field_present=field_present,
    )
    extraction_meta = authoring_parse_diagnostics(parsed)
    if provider_diagnostics:
        extraction_meta = {
            **extraction_meta,
            "provider": dict(provider_diagnostics),
        }
    if not parsed.ok or not isinstance(parsed.payload, dict):
        typed = parsed.error_code or AUTHORING_NO_JSON_OBJECT
        raise AppSpecBuildError(
            parsed.public_message,
            response_excerpt=text[:2000],
            raw_response_sha256=raw_sha,
            json_extraction={
                **extraction_meta,
                "ok": False,
                "method": parsed.strategy,
                "error": parsed.parser_error or typed,
            },
            typed_error=typed,
            authoring_diagnostics=extraction_meta,
        )
    return AppSpecCandidate(
        payload=parsed.payload,
        response_excerpt=text[:2000],
        raw_response_sha256=raw_sha,
        raw_char_count=len(text),
        json_extraction={
            **extraction_meta,
            "ok": True,
            "method": parsed.strategy,
        },
        authoring_diagnostics=extraction_meta,
    )


def app_spec_json_schema() -> dict[str, Any]:
    """Return the live schema used by prompts and runtime parsing."""

    return AppSpec.model_json_schema()


def parse_app_spec_candidate(candidate: AppSpecCandidate | Mapping[str, Any]) -> AppSpec:
    payload = candidate.payload if isinstance(candidate, AppSpecCandidate) else dict(candidate)
    try:
        return AppSpec.model_validate(payload)
    except ValidationError:
        raise
    except Exception as exc:
        raise AppSpecBuildError(f"Could not parse AppSpec candidate: {exc}") from exc


#: One bounded re-ask for a stream the PROVIDER cut — never for model-authored
#: malformation, which the authoring loop's wider retryable set owns on
#: purpose. Kept at 1 because every re-ask also spends the request's appspec
#: call budget (APPSPEC_MAX_CALLS) and downstream-runway clock.
_TRANSPORT_REASK_MAX = 1


def _is_transport_cut(error: Exception) -> bool:
    """True only for the transport class — never model-authored malformation.

    The two shapes the pipeline can see: the parser gate's ``provider_error``
    verdict (``finish_reason=error`` with a partial body), and the retryable
    ``ProviderGenerationError`` the provider raises on an empty cut. A
    non-retryable raise is refusal-class and a parse failure on a healthy
    stream is the model's own answer; neither is weather.
    """
    if isinstance(error, ProviderGenerationError):
        return bool(error.retryable)
    if isinstance(error, AppSpecBuildError):
        return dict(error.json_extraction or {}).get("method") == "provider_error"
    return False


def _transport_fallback_candidate(
    ai_provider: AIProvider,
    *,
    writer: str,
    primary_model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    attempt: int,
    transport_error: Exception,
) -> AppSpecCandidate | None:
    """One ask on a different provider's model after the primary's chain died.

    Runs 136/137: both repair chains were double error-cut — a bounded
    same-model re-ask cannot dodge a provider-side storm. This is the last
    rung before failing closed: one ask on
    ``APPSPEC_TRANSPORT_FALLBACK_MODEL`` (cross-provider by configuration),
    attempt-numbered above the primary asks so its ``ai_usage_events`` row
    stays unmistakable. Returns ``None`` when unconfigured or pointed at the
    primary model — a same-model "fallback" would ride the same storm.
    The deterministic validator still gates whatever comes back: a fallback
    spec that is wrong rejects honestly, so this trades a certain dead run for
    a judged candidate. Malformation from the fallback model raises honestly
    and is never re-asked.
    """
    fallback_model = str(settings.APPSPEC_TRANSPORT_FALLBACK_MODEL or "").strip()
    if not fallback_model or fallback_model == primary_model:
        return None
    with ai_call("appspec", writer=writer, attempt=attempt):
        try:
            raw, provider_diag = _ask_appspec_chat(
                ai_provider,
                model=fallback_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except ProviderGenerationError as exc:
            if not exc.retryable:
                raise
            raise AppSpecBuildError(
                f"transport fallback model was also cut: {exc}",
                typed_error=AUTHORING_JSON_TRUNCATED,
                json_extraction={
                    "ok": False,
                    "method": "provider_error",
                    "error": str(exc),
                    "transport_fallback_model": fallback_model,
                    "primary_transport_error": str(transport_error),
                },
            ) from exc
    try:
        candidate = _parse_candidate(
            raw,
            finish_reason=provider_diag.get("finish_reason"),
            provider_diagnostics=provider_diag,
        )
    except AppSpecBuildError as exc:
        exc.json_extraction["transport_fallback_model"] = fallback_model
        exc.json_extraction["primary_transport_error"] = str(transport_error)
        raise
    merged = dict(candidate.authoring_diagnostics or {})
    merged["transport_reask_used"] = True
    merged["transport_fallback_used"] = True
    merged["transport_fallback_model"] = fallback_model
    return dataclasses.replace(candidate, authoring_diagnostics=merged)


def _candidate_ask_with_transport_reask(
    ai_provider: AIProvider,
    *,
    writer: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
) -> AppSpecCandidate:
    """One candidate-shaped ask; an error-cut stream gets exactly one re-ask.

    Run 123: a schema_repair stream error-cut at 349 chars bypassed the
    provider-error gate (its call site never threaded ``finish_reason`` into
    the parser), the extracted fragment consumed the only schema-repair
    attempt, and the run died as a spec rejection. Run 128 proved the
    authoring loop's re-ask handles the same weather. Every candidate-shaped
    ask goes through here now: the gate classifies, the transport class —
    the gate's ``provider_error`` verdict, or the empty-cut shape the provider
    raises as a retryable ``ProviderGenerationError`` — is re-asked once with
    the attempt number bumped so ``ai_usage_events`` rows stay
    distinguishable, and everything else (the model's own malformation)
    raises exactly as before.

    Runs 136/137: a provider-side storm cut the primary ask AND its re-ask on
    both repair chains — the same-model re-ask cannot dodge weather at the
    provider. When the bounded re-ask is also transport-cut, the tail asks the
    cross-provider ``APPSPEC_TRANSPORT_FALLBACK_MODEL`` exactly once before
    failing closed (see ``_transport_fallback_candidate``).
    """
    last_error: Exception | None = None
    for attempt_index in range(1 + _TRANSPORT_REASK_MAX):
        raw: str | None = None
        provider_diag: dict[str, Any] = {}
        with ai_call("appspec", writer=writer, attempt=attempt_index + 1):
            try:
                raw, provider_diag = _ask_appspec_chat(
                    ai_provider,
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except ProviderGenerationError as exc:
                if not _is_transport_cut(exc):
                    raise
                last_error = exc
        if raw is None:
            continue
        try:
            candidate = _parse_candidate(
                raw,
                finish_reason=provider_diag.get("finish_reason"),
                provider_diagnostics=provider_diag,
            )
        except AppSpecBuildError as exc:
            if not _is_transport_cut(exc):
                raise
            # Transport: re-ask while attempts remain; a cut on the FINAL
            # attempt falls through to the tail for the cross-provider rung.
            last_error = exc
            continue
        merged = dict(candidate.authoring_diagnostics or {})
        merged["transport_reask_used"] = attempt_index > 0
        return AppSpecCandidate(
            payload=candidate.payload,
            response_excerpt=candidate.response_excerpt,
            raw_response_sha256=candidate.raw_response_sha256,
            raw_char_count=candidate.raw_char_count,
            json_extraction=candidate.json_extraction,
            parent_payload_sha256=candidate.parent_payload_sha256,
            repair_type=candidate.repair_type,
            authoring_diagnostics=merged,
        )
    assert last_error is not None
    # Both primary attempts were transport-cut (anything else raised above).
    # Last rung: one ask on the cross-provider fallback model, then fail closed.
    fallback = _transport_fallback_candidate(
        ai_provider,
        writer=writer,
        primary_model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        attempt=_TRANSPORT_REASK_MAX + 2,
        transport_error=last_error,
    )
    if fallback is not None:
        return fallback
    if isinstance(last_error, AppSpecBuildError):
        raise last_error
    raise AppSpecBuildError(
        str(last_error),
        typed_error=AUTHORING_JSON_TRUNCATED,
        json_extraction={"ok": False, "method": "provider_error", "error": str(last_error)},
    ) from last_error


def _ops_floor_block(derived_context: Mapping[str, Any]) -> str:
    """R4 rung 2's producer, resolved lazily.

    Lazy import — mirrors `source.py`'s `_product_kind_guidance` and keeps
    `app.application.appspec` free of a package-level dependency on
    `app.application.preview_app`. The block itself derives from the ship
    gate's own floor constant, so prompt and gate cannot drift.
    """

    from app.application.preview_app.product_kind import ops_floor_prompt_block

    return ops_floor_prompt_block(derived_context)


def build_app_spec_candidate(
    *,
    source_snapshot: Mapping[str, Any],
    derived_context: Mapping[str, Any] | None,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    model: str | None = None,
    max_tokens: int | None = None,
) -> AppSpecCandidate:
    """Ask the authoring model for one complete AppSpec JSON candidate."""

    selected_model = model or settings.APPSPEC_MODEL
    token_budget = max_tokens or settings.APPSPEC_MAX_TOKENS
    prompt = template_renderer.render(
        PromptTemplate.APP_SPEC,
        prompt_revision=settings.APPSPEC_PROMPT_REVISION,
        schema_version=settings.APPSPEC_SCHEMA_VERSION,
        source_snapshot_json=_canonical_json(source_snapshot),
        derived_context_json=_canonical_json(derived_context or {}),
        app_spec_json_schema=_canonical_json(app_spec_json_schema()),
        ops_floor_block=_ops_floor_block(derived_context or {}),
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    attempt_diagnostics: list[dict[str, Any]] = []
    last_error: AppSpecBuildError | None = None

    for attempt_index in range(1 + APPSPEC_AUTHORING_MALFORMED_RETRY_MAX):
        # Scope the ask so its row carries a writer and a real attempt number.
        # Without this the row falls back to `purpose` for its stage and hardcodes
        # `writer=None, attempt=1` (`admin_ops.py:330-332`), which is why appspec
        # — the most expensive stage in the pipeline — was the only one whose
        # sub-calls and re-asks could not be told apart in `ai_usage_events`.
        transport_raise: ProviderGenerationError | None = None
        with ai_call("appspec", writer="authoring", attempt=attempt_index + 1):
            try:
                raw, provider_diag = _ask_appspec_chat(
                    ai_provider,
                    model=selected_model,
                    messages=messages,
                    max_tokens=token_budget,
                    temperature=0.1 if attempt_index == 0 else 0.0,
                )
            except ProviderGenerationError as exc:
                # The empty-cut raise is the same weather the parser gate
                # classifies on a partial body; before this catch it escaped
                # the loop entirely and killed authoring with zero retries.
                # Refusal-class (non-retryable) raises still propagate.
                if not _is_transport_cut(exc):
                    raise
                transport_raise = exc
        if transport_raise is not None:
            last_error = AppSpecBuildError(
                str(transport_raise),
                typed_error=AUTHORING_JSON_TRUNCATED,
                json_extraction={
                    "ok": False,
                    "method": "provider_error",
                    "error": str(transport_raise),
                },
            )
            attempt_diagnostics.append(
                {
                    "attempt": attempt_index + 1,
                    "typed_error": AUTHORING_JSON_TRUNCATED,
                    "provider": {},
                    "parse": {"method": "provider_error", "empty_cut_raise": True},
                }
            )
            if attempt_index >= APPSPEC_AUTHORING_MALFORMED_RETRY_MAX:
                break
            # Transport, not malformation: re-ask with the messages unchanged.
            continue
        try:
            candidate = _parse_candidate(
                raw,
                finish_reason=provider_diag.get("finish_reason"),
                provider_diagnostics=provider_diag,
            )
            merged = dict(candidate.authoring_diagnostics or {})
            merged["authoring_attempt"] = attempt_index + 1
            merged["malformed_retry_used"] = attempt_index > 0
            merged["provider"] = provider_diag
            return AppSpecCandidate(
                payload=candidate.payload,
                response_excerpt=candidate.response_excerpt,
                raw_response_sha256=candidate.raw_response_sha256,
                raw_char_count=candidate.raw_char_count,
                json_extraction=candidate.json_extraction,
                parent_payload_sha256=candidate.parent_payload_sha256,
                repair_type=candidate.repair_type,
                authoring_diagnostics=merged,
            )
        except AppSpecBuildError as exc:
            last_error = exc
            attempt_diagnostics.append(
                {
                    "attempt": attempt_index + 1,
                    "typed_error": exc.typed_error,
                    "provider": provider_diag,
                    "parse": dict(exc.authoring_diagnostics or {}),
                }
            )
            retryable = exc.typed_error in {
                AUTHORING_NO_JSON_OBJECT,
                AUTHORING_JSON_SYNTAX_INVALID,
                AUTHORING_JSON_TRUNCATED,
                AUTHORING_RESPONSE_FIELD_MISSING,
                None,
            }
            if attempt_index >= APPSPEC_AUTHORING_MALFORMED_RETRY_MAX or not retryable:
                break
            # Compact corrective retry — never resend the malformed output.
            messages = [
                {"role": "user", "content": prompt},
                {"role": "user", "content": _COMPACT_JSON_RETRY_INSTRUCTION},
            ]

    assert last_error is not None
    if _is_transport_cut(last_error):
        # Every authoring attempt died on weather, not on the model's answer.
        # Last rung before failing closed: one clean ask (the original prompt,
        # no corrective instruction) on the cross-provider fallback model.
        try:
            fallback = _transport_fallback_candidate(
                ai_provider,
                writer="authoring",
                primary_model=selected_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=token_budget,
                temperature=0.0,
                attempt=len(attempt_diagnostics) + 1,
                transport_error=last_error,
            )
        except AppSpecBuildError as exc:
            attempt_diagnostics.append(
                {
                    "attempt": len(attempt_diagnostics) + 1,
                    "typed_error": exc.typed_error,
                    "provider": dict(exc.json_extraction or {}),
                    "parse": dict(exc.authoring_diagnostics or {}),
                    "transport_fallback": True,
                }
            )
            last_error = exc
            fallback = None
        if fallback is not None:
            merged = dict(fallback.authoring_diagnostics or {})
            merged["authoring_attempt"] = len(attempt_diagnostics) + 1
            merged["malformed_retry_used"] = len(attempt_diagnostics) > 1
            merged["authoring_attempts"] = attempt_diagnostics
            return dataclasses.replace(fallback, authoring_diagnostics=merged)
    diagnostics = dict(last_error.authoring_diagnostics or {})
    diagnostics["authoring_attempts"] = attempt_diagnostics
    diagnostics["malformed_retry_used"] = len(attempt_diagnostics) > 1
    raise AppSpecBuildError(
        str(last_error),
        response_excerpt=last_error.response_excerpt,
        raw_response_sha256=last_error.raw_response_sha256,
        json_extraction={
            **dict(last_error.json_extraction or {}),
            "authoring_attempts": attempt_diagnostics,
        },
        typed_error=last_error.typed_error,
        authoring_diagnostics=diagnostics,
    )


def build_app_spec(
    *,
    source_snapshot: Mapping[str, Any],
    derived_context: Mapping[str, Any] | None,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    model: str | None = None,
    max_tokens: int | None = None,
) -> AppSpec:
    """Build and Pydantic-parse an AppSpec without approving or persisting it."""

    candidate = build_app_spec_candidate(
        source_snapshot=source_snapshot,
        derived_context=derived_context,
        ai_provider=ai_provider,
        template_renderer=template_renderer,
        model=model,
        max_tokens=max_tokens,
    )
    return parse_app_spec_candidate(candidate)


def repair_app_spec_candidate(
    *,
    source_snapshot: Mapping[str, Any],
    derived_context: Mapping[str, Any] | None,
    candidate: AppSpecCandidate | AppSpec | Mapping[str, Any] | None,
    deterministic_report: Any,
    coverage_review: Any = None,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    model: str | None = None,
    max_tokens: int | None = None,
) -> AppSpecCandidate:
    """Ask for a complete replacement that addresses supplied validation gaps."""

    if isinstance(candidate, AppSpecCandidate):
        candidate_payload: Any = candidate.payload
    else:
        candidate_payload = candidate or {}
    selected_model = model or settings.APPSPEC_REPAIR_MODEL
    prompt = template_renderer.render(
        PromptTemplate.APP_SPEC_REPAIR,
        prompt_revision=settings.APPSPEC_PROMPT_REVISION,
        schema_version=settings.APPSPEC_SCHEMA_VERSION,
        source_snapshot_json=_canonical_json(source_snapshot),
        derived_context_json=_canonical_json(derived_context or {}),
        candidate_json=_canonical_json(candidate_payload),
        deterministic_report_json=_canonical_json(deterministic_report or {}),
        coverage_review_json=_canonical_json(coverage_review or {}),
        app_spec_json_schema=_canonical_json(app_spec_json_schema()),
    )
    return _candidate_ask_with_transport_reask(
        ai_provider,
        writer="repair",
        model=selected_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens or settings.APPSPEC_REPAIR_MAX_TOKENS,
        temperature=0.05,
    )


def repair_app_spec(**kwargs: Any) -> AppSpec:
    """Repair and Pydantic-parse a complete AppSpec replacement."""

    return parse_app_spec_candidate(repair_app_spec_candidate(**kwargs))


__all__ = [
    "APPSPEC_AUTHORING_MALFORMED_RETRY_MAX",
    "AppSpecBuildError",
    "AppSpecCandidate",
    "app_spec_json_schema",
    "build_app_spec",
    "build_app_spec_candidate",
    "parse_app_spec_candidate",
    "repair_app_spec",
    "repair_app_spec_candidate",
]
