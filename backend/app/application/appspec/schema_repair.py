"""Bounded AI repair for AppSpec schema/shape failures only."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.application.appspec.builder import (
    AppSpecCandidate,
    _candidate_ask_with_transport_reask,
    app_spec_json_schema,
)
from app.application.prompts import PromptTemplate
from app.core.config import settings
from app.domain.appspec.sanitize.empty_trace import schema_repair_trace_context
from app.domain.appspec.sanitize.preparse_normalize import schema_fragments_for_paths
from app.domain.appspec.sanitize.schema_diagnostics import (
    classify_schema_parse_exception,
    payload_sha256,
)
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.schemas.app_spec import AppSpec
from pydantic import ValidationError


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        # Sorted by repr so canonical output stays deterministic.
        return sorted((_jsonable(item) for item in value), key=repr)
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    # Pydantic v2 attaches the raw exception object under ``ctx.error`` for
    # custom validators — the AppSpec ``duplicate_id`` check raises ValueError,
    # so the issue payload carried a ValueError straight into json.dumps and
    # raised "Object of type ValueError is not JSON serializable". That aborted
    # the single allowed AI schema-repair attempt before it ever ran, turning a
    # repairable spec into a hard AppSpec failure. Degrade to the string form so
    # the repair prompt can still describe the defect.
    return str(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def repair_app_spec_schema_candidate(
    *,
    candidate: AppSpecCandidate | Mapping[str, Any],
    schema_issue: Mapping[str, Any],
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    model: str | None = None,
    max_tokens: int | None = None,
) -> AppSpecCandidate:
    """Ask for one schema-only repair. Does not resend the authoring source brief."""

    if isinstance(candidate, AppSpecCandidate):
        payload = candidate.payload
        parent_sha = payload_sha256(payload)
        excerpt = candidate.response_excerpt
    else:
        payload = dict(candidate)
        parent_sha = payload_sha256(payload)
        excerpt = ""

    child_issues = list(schema_issue.get("issues") or [])
    paths = [str(item.get("path") or "") for item in child_issues if isinstance(item, Mapping)]
    fragments = schema_fragments_for_paths(paths)
    trace_context = schema_repair_trace_context(payload, schema_issue=schema_issue)

    prompt = template_renderer.render(
        PromptTemplate.APP_SPEC_SCHEMA_REPAIR,
        prompt_revision=settings.APPSPEC_PROMPT_REVISION,
        schema_version=settings.APPSPEC_SCHEMA_VERSION,
        candidate_json=_canonical_json(payload),
        schema_issues_json=_canonical_json(
            {
                "wrapper": {
                    "code": schema_issue.get("code"),
                    "message": schema_issue.get("message"),
                },
                "issues": child_issues,
            }
        ),
        schema_fragments_json=_canonical_json(fragments),
        app_spec_json_schema=_canonical_json(app_spec_json_schema()),
        empty_trace_context_json=_canonical_json(trace_context),
    )
    # Through the shared candidate ask: run 123's schema_repair stream was
    # error-cut at 349 chars, and because this site called ask_chat raw and
    # parsed with NO finish_reason, the provider-error gate never fired — the
    # extracted fragment consumed the only schema-repair attempt and the run
    # died as a spec rejection. The helper threads the provider diagnostics
    # (so the gate classifies) and re-asks the transport class once.
    repaired = _candidate_ask_with_transport_reask(
        ai_provider,
        writer="schema_repair",
        model=model or settings.APPSPEC_REPAIR_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens or settings.APPSPEC_REPAIR_MAX_TOKENS,
        temperature=0.0,
    )
    return AppSpecCandidate(
        payload=repaired.payload,
        response_excerpt=repaired.response_excerpt or excerpt[:2000],
        raw_response_sha256=repaired.raw_response_sha256,
        raw_char_count=repaired.raw_char_count,
        json_extraction=repaired.json_extraction,
        parent_payload_sha256=parent_sha,
        repair_type="ai_schema_repair",
    )


def validate_schema_repaired_candidate(
    candidate: AppSpecCandidate | Mapping[str, Any],
) -> tuple[AppSpec | None, dict[str, Any] | None]:
    """Re-validate a schema-repaired candidate from scratch."""

    payload = (
        candidate.payload if isinstance(candidate, AppSpecCandidate) else dict(candidate)
    )
    try:
        return AppSpec.model_validate(payload), None
    except ValidationError as exc:
        return None, classify_schema_parse_exception(
            exc,
            candidate_payload=payload,
        )
    except Exception as exc:
        return None, classify_schema_parse_exception(
            exc,
            candidate_payload=payload,
        )


__all__ = [
    "repair_app_spec_schema_candidate",
    "validate_schema_repaired_candidate",
]
