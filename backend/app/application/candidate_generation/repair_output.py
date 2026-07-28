"""Canonical deterministic parser for Phase 3B candidate repair output.

Production request #46 evidence:
- repair model ``z-ai/glm-5.2`` returned no ``choices[0].message.content``
- ``completion_tokens`` landed on the configured repair cap exactly
- the central provider parser reported ``provider_response_shape_invalid``
  because the missing-content branch precedes the truncation branch

Accepted envelopes (documented, structurally equivalent, deterministic):

1. ``canonical``          ``{"schema_version": "1.0", "batch_kind": K, "files": [...]}``
2. ``files_only_object``  ``{"files": [...]}`` — schema version / batch kind injected
3. ``bare_files_array``   ``[ ... ]`` — wrapped with schema version and batch kind

Any other top-level shape is ``candidate_repair_envelope_invalid``. Keys are
never matched by similarity, truncated JSON is never completed by appending
brackets, and model text is never evaluated.

Diagnostics deliberately carry only lengths, hashes, and structural flags:
repair responses contain generated product source, so no excerpt is retained.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from pydantic import ValidationError

from app.domain.schemas.preview_candidate import (
    CANDIDATE_SCHEMA_VERSION,
    GeneratedCandidateBatch,
    GeneratedCandidateFile,
)

REPAIR_RESPONSE_FIELD_MISSING = "candidate_repair_response_field_missing"
REPAIR_NO_JSON_PAYLOAD = "candidate_repair_no_json_payload"
REPAIR_JSON_TRUNCATED = "candidate_repair_json_truncated"
REPAIR_JSON_SYNTAX_INVALID = "candidate_repair_json_syntax_invalid"
REPAIR_ENVELOPE_INVALID = "candidate_repair_envelope_invalid"
REPAIR_CONTRACT_INVALID = "candidate_repair_contract_invalid"

REPAIR_PARSER_REVISION = "2026-07-28.candidate-repair.1"

# Violations that mean the repair tried to leave its approved subset. The
# caller maps these onto the existing ownership-violation failure code.
VIOLATION_UNKNOWN_PATH = "unknown_path"
VIOLATION_OUTSIDE_SUBSET = "outside_repair_subset"
VIOLATION_OWNERSHIP_CHANGED = "ownership_changed"
VIOLATION_FILE_KIND_CHANGED = "file_kind_changed"
VIOLATION_BATCH_KIND_MISMATCH = "batch_kind_mismatch"

OWNERSHIP_VIOLATIONS = frozenset(
    {
        VIOLATION_UNKNOWN_PATH,
        VIOLATION_OUTSIDE_SUBSET,
        VIOLATION_OWNERSHIP_CHANGED,
        VIOLATION_FILE_KIND_CHANGED,
        VIOLATION_BATCH_KIND_MISMATCH,
    }
)

_ENVELOPE_CANONICAL = "canonical"
_ENVELOPE_FILES_ONLY = "files_only_object"
_ENVELOPE_BARE_ARRAY = "bare_files_array"

_ALLOWED_ENVELOPE_KEYS = frozenset({"schema_version", "batch_kind", "files"})

_PUBLIC_REPAIR_ERROR = (
    "The repair step did not return a usable set of repaired files."
)

_FENCE_RE = re.compile(
    r"```(?:json|JSON)?\s*\n(?P<body>[\s\S]*?)\n?```",
    re.MULTILINE,
)

_TRUNCATING_FINISH_REASONS = frozenset({"length", "max_tokens"})


@dataclass(frozen=True)
class CandidateRepairParseResult:
    """Outcome of one deterministic candidate-repair-output parse."""

    ok: bool
    batch: GeneratedCandidateBatch | None = None
    strategy: str = ""
    envelope: str = ""
    error_code: str | None = None
    violation: str | None = None
    public_message: str = _PUBLIC_REPAIR_ERROR
    parser_error: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def typed_error(self) -> str | None:
        return self.error_code if not self.ok else None

    @property
    def is_ownership_violation(self) -> bool:
        return bool(self.violation and self.violation in OWNERSHIP_VIOLATIONS)


def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _first_non_whitespace(text: str) -> str | None:
    for ch in text or "":
        if not ch.isspace():
            return ch
    return None


def _is_truncating_finish_reason(finish_reason: str | None) -> bool:
    return str(finish_reason or "").strip().lower() in _TRUNCATING_FINISH_REASONS


_MAX_BALANCED_STARTS = 50


def _balanced_span_from(text: str, start: int) -> tuple[int, int, str]:
    """Scan one container starting at ``start``.

    ``status`` is ``complete``, ``truncated``, or ``mismatched``. The scan is
    string aware: brackets inside strings, escaped quotes, and escaped
    backslashes never affect depth. No regex and no greedy matching.
    """

    closers: list[str] = []
    in_str = False
    escape = False
    for index in range(start, len(text)):
        ch = text[index]
        if escape:
            escape = False
            continue
        if in_str:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch in "{[":
            closers.append("}" if ch == "{" else "]")
            continue
        if ch in "}]":
            if not closers or closers[-1] != ch:
                return start, index + 1, "mismatched"
            closers.pop()
            if not closers:
                return start, index + 1, "complete"
    # Ran out of text with an open container or an unterminated string.
    return start, len(text), "truncated"


def _balanced_span(text: str) -> tuple[int, int, str] | None:
    """Return ``(start, end_exclusive, status)`` for the payload container.

    Surrounding prose may itself contain a stray brace, so rejected containers
    are skipped. The scan only ever moves forward past a container it already
    examined, so nested content inside a rejected container is never mined as a
    substitute payload.
    """

    body = text or ""
    if not body:
        return None

    first_failure: tuple[int, int, str] | None = None
    cursor = 0
    for _attempt in range(_MAX_BALANCED_STARTS):
        start = -1
        for index in range(cursor, len(body)):
            if body[index] in "{[":
                start = index
                break
        if start < 0:
            return first_failure
        span = _balanced_span_from(body, start)
        if span[2] == "complete":
            loaded, _err = _try_loads(body[span[0] : span[1]])
            if loaded is not None:
                return span
        if first_failure is None:
            first_failure = span
        # Resume after the container just examined, never inside it.
        cursor = max(span[1], start + 1)
    return first_failure


def _try_loads(candidate: str) -> tuple[Any | None, str | None]:
    try:
        return json.loads(candidate), None
    except json.JSONDecodeError as exc:
        return None, f"{exc.msg} (line {exc.lineno} col {exc.colno})"


def _base_diagnostics(
    raw: str,
    *,
    finish_reason: str | None,
) -> dict[str, Any]:
    return {
        "parser_revision": REPAIR_PARSER_REVISION,
        "raw_response_sha256": _sha256_text(raw),
        "raw_response_chars": len(raw or ""),
        "first_non_whitespace": _first_non_whitespace(raw),
        "has_markdown_fence": "```" in (raw or ""),
        "finish_reason": finish_reason,
        "finish_reason_truncating": _is_truncating_finish_reason(finish_reason),
    }


def _fail(
    *,
    code: str,
    strategy: str,
    raw: str,
    finish_reason: str | None,
    parser_error: str | None = None,
    envelope: str = "",
    violation: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> CandidateRepairParseResult:
    diagnostics = _base_diagnostics(raw, finish_reason=finish_reason)
    diagnostics.update(
        {
            "extraction_strategy_attempted": strategy,
            "envelope": envelope,
            "parser_error_code": code,
            "parser_error": parser_error,
            "violation": violation,
        }
    )
    if extra:
        diagnostics.update(dict(extra))
    return CandidateRepairParseResult(
        ok=False,
        strategy=strategy,
        envelope=envelope,
        error_code=code,
        violation=violation,
        public_message=_PUBLIC_REPAIR_ERROR,
        parser_error=parser_error,
        diagnostics=diagnostics,
    )


def _normalize_envelope(
    payload: Any,
    *,
    batch_kind: str,
) -> tuple[dict[str, Any] | None, str, str | None, str | None]:
    """Return ``(normalized, envelope, error_code, violation)``.

    Only the three documented envelopes are accepted. Missing
    ``schema_version`` / ``batch_kind`` are filled from the repair request
    because both are already fixed by the approved attempt.
    """

    if isinstance(payload, list):
        return (
            {
                "schema_version": CANDIDATE_SCHEMA_VERSION,
                "batch_kind": batch_kind,
                "files": payload,
            },
            _ENVELOPE_BARE_ARRAY,
            None,
            None,
        )

    if not isinstance(payload, Mapping):
        return None, "", REPAIR_ENVELOPE_INVALID, None

    if "files" not in payload:
        return None, "", REPAIR_ENVELOPE_INVALID, None

    unknown_keys = set(map(str, payload.keys())) - _ALLOWED_ENVELOPE_KEYS
    if unknown_keys:
        # Never guess which extra key carried the payload.
        return None, "", REPAIR_ENVELOPE_INVALID, None

    declared_kind = payload.get("batch_kind")
    if declared_kind is not None and str(declared_kind) != str(batch_kind):
        return None, "", REPAIR_ENVELOPE_INVALID, VIOLATION_BATCH_KIND_MISMATCH

    normalized = {
        "schema_version": payload.get("schema_version", CANDIDATE_SCHEMA_VERSION),
        "batch_kind": batch_kind,
        "files": payload.get("files"),
    }
    envelope = (
        _ENVELOPE_CANONICAL
        if "schema_version" in payload and declared_kind is not None
        else _ENVELOPE_FILES_ONLY
    )
    return normalized, envelope, None, None


def _validate_repair_subset(
    batch: GeneratedCandidateBatch,
    *,
    approved_files: Sequence[GeneratedCandidateFile],
    original_paths: Sequence[str],
) -> tuple[str | None, str | None]:
    """Return ``(violation, detail)`` for subset and ownership rules."""

    approved_by_path = {item.path: item for item in approved_files}
    known_paths = set(original_paths) or set(approved_by_path)

    for item in batch.files:
        approved = approved_by_path.get(item.path)
        if approved is None:
            if item.path in known_paths:
                return VIOLATION_OUTSIDE_SUBSET, item.path
            return VIOLATION_UNKNOWN_PATH, item.path
        if tuple(item.owner_contract_ids) != tuple(approved.owner_contract_ids):
            return VIOLATION_OWNERSHIP_CHANGED, item.path
        if item.file_kind != approved.file_kind:
            return VIOLATION_FILE_KIND_CHANGED, item.path
    return None, None


def parse_candidate_repair_output(
    raw: str | None,
    *,
    batch_kind: str,
    approved_files: Sequence[GeneratedCandidateFile],
    original_paths: Sequence[str] = (),
    structured_payload: Mapping[str, Any] | list[Any] | None = None,
    finish_reason: str | None = None,
    response_field_present: bool = True,
) -> CandidateRepairParseResult:
    """Parse candidate repair output with a fixed, fail-closed strategy order.

    1. provider-native parsed object, when present
    2. direct strict JSON parse of the response text
    3. JSON-labelled markdown fence extraction
    4. string-aware balanced object/array extraction
    5. strict JSON parse of the extracted payload
    6. repair contract validation, then subset / ownership validation
    """

    text = raw if isinstance(raw, str) else ""

    if not response_field_present:
        return _fail(
            code=REPAIR_RESPONSE_FIELD_MISSING,
            strategy="response_field",
            raw="",
            finish_reason=finish_reason,
            parser_error="provider content field missing",
        )

    # 1) Provider-native structured object.
    if structured_payload is not None:
        return _finalize(
            structured_payload,
            raw=text,
            strategy="provider_structured",
            batch_kind=batch_kind,
            approved_files=approved_files,
            original_paths=original_paths,
            finish_reason=finish_reason,
        )

    if not text.strip():
        code = (
            REPAIR_JSON_TRUNCATED
            if _is_truncating_finish_reason(finish_reason)
            else REPAIR_NO_JSON_PAYLOAD
        )
        return _fail(
            code=code,
            strategy="empty",
            raw=text,
            finish_reason=finish_reason,
            parser_error="empty_output",
        )

    # 2) Direct strict parse.
    direct, direct_err = _try_loads(text.strip())
    if direct is not None:
        return _finalize(
            direct,
            raw=text,
            strategy="direct",
            batch_kind=batch_kind,
            approved_files=approved_files,
            original_paths=original_paths,
            finish_reason=finish_reason,
        )

    # 3) JSON-labelled markdown fence.
    for match in _FENCE_RE.finditer(text):
        body = (match.group("body") or "").strip()
        if not body:
            continue
        loaded, _fence_err = _try_loads(body)
        if loaded is not None:
            return _finalize(
                loaded,
                raw=text,
                strategy="markdown_fence",
                batch_kind=batch_kind,
                approved_files=approved_files,
                original_paths=original_paths,
                finish_reason=finish_reason,
            )

    # 4) String-aware balanced object/array extraction.
    span = _balanced_span(text)
    if span is None:
        code = (
            REPAIR_JSON_TRUNCATED
            if _is_truncating_finish_reason(finish_reason)
            else REPAIR_NO_JSON_PAYLOAD
        )
        return _fail(
            code=code,
            strategy="balanced_scan",
            raw=text,
            finish_reason=finish_reason,
            parser_error=direct_err or "no_json_payload",
        )

    start, end, status = span
    candidate = text[start:end]
    if status == "truncated":
        return _fail(
            code=REPAIR_JSON_TRUNCATED,
            strategy="balanced_scan",
            raw=text,
            finish_reason=finish_reason,
            parser_error="unbalanced_payload",
            extra={"candidate_chars": len(candidate)},
        )
    if status == "mismatched":
        return _fail(
            code=REPAIR_JSON_SYNTAX_INVALID,
            strategy="balanced_scan",
            raw=text,
            finish_reason=finish_reason,
            parser_error="mismatched_bracket",
            extra={"candidate_chars": len(candidate)},
        )

    # 5) Strict parse of the extracted payload.
    loaded, err = _try_loads(candidate)
    if loaded is None:
        return _fail(
            code=REPAIR_JSON_SYNTAX_INVALID,
            strategy="balanced_scan",
            raw=text,
            finish_reason=finish_reason,
            parser_error=err or "invalid_payload",
            extra={"candidate_chars": len(candidate)},
        )
    return _finalize(
        loaded,
        raw=text,
        strategy="balanced_scan",
        batch_kind=batch_kind,
        approved_files=approved_files,
        original_paths=original_paths,
        finish_reason=finish_reason,
        extracted=candidate,
    )


def _finalize(
    payload: Any,
    *,
    raw: str,
    strategy: str,
    batch_kind: str,
    approved_files: Sequence[GeneratedCandidateFile],
    original_paths: Sequence[str],
    finish_reason: str | None,
    extracted: str | None = None,
) -> CandidateRepairParseResult:
    """Normalize the envelope, then validate contract and repair subset."""

    normalized, envelope, envelope_error, envelope_violation = _normalize_envelope(
        payload,
        batch_kind=batch_kind,
    )
    if normalized is None:
        return _fail(
            code=envelope_error or REPAIR_ENVELOPE_INVALID,
            strategy=strategy,
            raw=raw,
            finish_reason=finish_reason,
            parser_error="unsupported_top_level_envelope",
            violation=envelope_violation,
            extra={
                "observed_top_level_type": type(payload).__name__,
                "observed_top_level_keys": (
                    sorted(str(key) for key in payload.keys())
                    if isinstance(payload, Mapping)
                    else []
                ),
            },
        )

    # 6) Existing repair contract validation.
    try:
        batch = GeneratedCandidateBatch.model_validate(normalized)
    except ValidationError as exc:
        return _fail(
            code=REPAIR_CONTRACT_INVALID,
            strategy=strategy,
            raw=raw,
            finish_reason=finish_reason,
            parser_error=f"{exc.error_count()} contract errors",
            envelope=envelope,
            extra={
                "contract_error_locations": [
                    ".".join(str(part) for part in error.get("loc", ()))
                    for error in exc.errors()[:20]
                ],
            },
        )

    violation, detail = _validate_repair_subset(
        batch,
        approved_files=approved_files,
        original_paths=original_paths,
    )
    if violation is not None:
        return _fail(
            code=REPAIR_CONTRACT_INVALID,
            strategy=strategy,
            raw=raw,
            finish_reason=finish_reason,
            parser_error=violation,
            envelope=envelope,
            violation=violation,
            extra={"violation_path": detail},
        )

    diagnostics = _base_diagnostics(raw, finish_reason=finish_reason)
    body = extracted if extracted is not None else ""
    diagnostics.update(
        {
            "extraction_strategy_attempted": strategy,
            "envelope": envelope,
            "parser_error_code": None,
            "parser_error": None,
            "violation": None,
            "repaired_path_count": len(batch.files),
            "approved_path_count": len(tuple(approved_files)),
            "extracted_object_sha256": _sha256_text(body) if body else None,
            "extracted_object_chars": len(body) if body else None,
        }
    )
    return CandidateRepairParseResult(
        ok=True,
        batch=batch,
        strategy=strategy,
        envelope=envelope,
        diagnostics=diagnostics,
    )


__all__ = [
    "OWNERSHIP_VIOLATIONS",
    "REPAIR_CONTRACT_INVALID",
    "REPAIR_ENVELOPE_INVALID",
    "REPAIR_JSON_SYNTAX_INVALID",
    "REPAIR_JSON_TRUNCATED",
    "REPAIR_NO_JSON_PAYLOAD",
    "REPAIR_PARSER_REVISION",
    "REPAIR_RESPONSE_FIELD_MISSING",
    "VIOLATION_BATCH_KIND_MISMATCH",
    "VIOLATION_FILE_KIND_CHANGED",
    "VIOLATION_OUTSIDE_SUBSET",
    "VIOLATION_OWNERSHIP_CHANGED",
    "VIOLATION_UNKNOWN_PATH",
    "CandidateRepairParseResult",
    "parse_candidate_repair_output",
]
