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
from app.core.config import settings
from app.domain.appspec.sanitize.preparse_normalize import extract_json_object_text
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.schemas.app_spec import AppSpec
from app.shared.json_utils import extract_json_from_text


class AppSpecBuildError(RuntimeError):
    """The authoring model did not return a usable AppSpec candidate."""

    def __init__(
        self,
        message: str,
        *,
        response_excerpt: str = "",
        raw_response_sha256: str = "",
        json_extraction: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.response_excerpt = response_excerpt
        self.raw_response_sha256 = raw_response_sha256
        self.json_extraction = dict(json_extraction or {})


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


def _parse_candidate(raw: str) -> AppSpecCandidate:
    text = raw or ""
    raw_sha = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""
    extracted_text, extraction_meta = extract_json_object_text(text)
    try:
        if extracted_text is not None:
            payload = json.loads(extracted_text)
            extraction_meta = {**extraction_meta, "ok": True}
        else:
            payload = extract_json_from_text(text)
            extraction_meta = {
                **extraction_meta,
                "method": extraction_meta.get("method") or "shared_extract",
                "ok": True,
            }
    except Exception as exc:
        raise AppSpecBuildError(
            f"AppSpec model output was not valid JSON: {exc}",
            response_excerpt=text[:2000],
            raw_response_sha256=raw_sha,
            json_extraction={**extraction_meta, "ok": False, "error": str(exc)},
        ) from exc
    if not isinstance(payload, dict):
        raise AppSpecBuildError(
            "AppSpec model output must be one JSON object.",
            response_excerpt=text[:2000],
            raw_response_sha256=raw_sha,
            json_extraction={**extraction_meta, "ok": False, "error": "not_object"},
        )
    return AppSpecCandidate(
        payload=payload,
        response_excerpt=text[:2000],
        raw_response_sha256=raw_sha,
        raw_char_count=len(text),
        json_extraction=extraction_meta,
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

    prompt = template_renderer.render(
        PromptTemplate.APP_SPEC,
        prompt_revision=settings.APPSPEC_PROMPT_REVISION,
        schema_version=settings.APPSPEC_SCHEMA_VERSION,
        source_snapshot_json=_canonical_json(source_snapshot),
        derived_context_json=_canonical_json(derived_context or {}),
        app_spec_json_schema=_canonical_json(app_spec_json_schema()),
    )
    raw = ai_provider.ask_chat(
        model or settings.APPSPEC_MODEL,
        [{"role": "user", "content": prompt}],
        max_tokens=max_tokens or settings.APPSPEC_MAX_TOKENS,
        temperature=0.1,
    )
    return _parse_candidate(raw)


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
    raw = ai_provider.ask_chat(
        model or settings.APPSPEC_REPAIR_MODEL,
        [{"role": "user", "content": prompt}],
        max_tokens=max_tokens or settings.APPSPEC_REPAIR_MAX_TOKENS,
        temperature=0.05,
    )
    return _parse_candidate(raw)


def repair_app_spec(**kwargs: Any) -> AppSpec:
    """Repair and Pydantic-parse a complete AppSpec replacement."""

    return parse_app_spec_candidate(repair_app_spec_candidate(**kwargs))


__all__ = [
    "AppSpecBuildError",
    "AppSpecCandidate",
    "app_spec_json_schema",
    "build_app_spec",
    "build_app_spec_candidate",
    "parse_app_spec_candidate",
    "repair_app_spec",
    "repair_app_spec_candidate",
]
