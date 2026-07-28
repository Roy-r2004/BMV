"""Canonical provider-payload extraction for Phase 3B candidate repair.

Production request #48 evidence:
- repair model ``z-ai/glm-5.2`` returned HTTP 200 with ~3100 completion tokens
- ``choices[0].message.content`` was not a string, so the central parser hit
  ``provider_response_shape_invalid`` ("Provider choice message content was
  missing") before any repair parsing could run
- ``finish_reason`` was not a truncating reason, so the #46 truncation branch
  did not apply

The response therefore carried no repair payload in the one field the adapter
read. The fix is twofold: read every field a payload can legitimately arrive
in, and ask supported models for the payload as a required tool call so the
transport cannot be an unstructured text field at all.

Extraction order is fixed and deterministic:

1. provider-native parsed object, when the capability profile proves support
2. exactly one approved repair tool call's function arguments
3. ``message.content`` string
4. ``message.content`` text parts joined in order
5. the existing strict candidate-repair text parser

Never used: hidden reasoning, arbitrary message fields, similarity matching,
merged tool calls, ``eval``, JSON5, or ``ast.literal_eval``.

Diagnostics carry only lengths, hashes, and structural flags. Repair payloads
contain generated product source, so no excerpt is ever retained.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.domain.schemas.preview_candidate import (
    CANDIDATE_SCHEMA_VERSION,
    GeneratedCandidateFile,
)
from app.infrastructure.ai_providers.response_parser import (
    ChatMessageEnvelope,
    ProviderToolCall,
)

REPAIR_TOOL_NAME = "submit_candidate_repair"
REPAIR_PAYLOAD_EXTRACTOR_REVISION = "2026-07-28.candidate-repair-payload.1"

REPAIR_PAYLOAD_MISSING = "candidate_repair_payload_missing"
REPAIR_MULTIPLE_TOOL_CALLS = "candidate_repair_multiple_tool_calls"
REPAIR_TOOL_NAME_INVALID = "candidate_repair_tool_name_invalid"
REPAIR_TOOL_ARGUMENTS_MISSING = "candidate_repair_tool_arguments_missing"
REPAIR_CONTENT_PARTS_INVALID = "candidate_repair_content_parts_invalid"
REPAIR_REFUSED = "candidate_repair_refused"

EXTRACTION_ERROR_CODES = frozenset(
    {
        REPAIR_PAYLOAD_MISSING,
        REPAIR_MULTIPLE_TOOL_CALLS,
        REPAIR_TOOL_NAME_INVALID,
        REPAIR_TOOL_ARGUMENTS_MISSING,
        REPAIR_CONTENT_PARTS_INVALID,
        REPAIR_REFUSED,
    }
)

SOURCE_PROVIDER_PARSED = "provider_parsed"
SOURCE_TOOL_CALL = "tool_call_arguments"
SOURCE_CONTENT_STRING = "content_string"
SOURCE_CONTENT_PARTS = "content_parts"

_PUBLIC_MESSAGE = (
    "The repair step did not return a usable set of repaired files."
)

# Exact tool contract requested from models that support tool calling.
REPAIR_TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["files"],
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["path", "owner", "source"],
                "properties": {
                    "path": {"type": "string"},
                    "owner": {"type": "string"},
                    "source": {"type": "string"},
                },
                "additionalProperties": False,
            },
        }
    },
    "additionalProperties": False,
}

_REPAIR_TOOL_DESCRIPTION = (
    "Return the corrected source for every file that failed validation. "
    "Return only the files you were asked to repair, each exactly once, "
    "keeping its original path and owner."
)

# ``file_kind`` is not part of the tool contract: it is already fixed by the
# approved attempt, so it is resolved from the approved file rather than asked
# for. Unknown paths fall back to the kind implied by the batch so the subset
# validator can report them precisely instead of as a contract error.
_BATCH_DEFAULT_FILE_KIND = {
    "business_components": "business_component",
    "pages": "page",
}


def build_repair_tool_spec() -> dict[str, Any]:
    """The single tool offered on a candidate-repair call."""

    return {
        "type": "function",
        "function": {
            "name": REPAIR_TOOL_NAME,
            "description": _REPAIR_TOOL_DESCRIPTION,
            "parameters": dict(REPAIR_TOOL_SCHEMA),
        },
    }


def build_repair_tool_choice() -> dict[str, Any]:
    """Require the repair tool rather than leaving the transport to the model."""

    return {"type": "function", "function": {"name": REPAIR_TOOL_NAME}}


@dataclass(frozen=True)
class RepairPayloadExtraction:
    """One deterministic extraction attempt over a provider response."""

    ok: bool
    source: str = ""
    structured_payload: Any | None = None
    text: str = ""
    response_field_present: bool = True
    error_code: str = ""
    public_message: str = _PUBLIC_MESSAGE
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _base_diagnostics(envelope: ChatMessageEnvelope) -> dict[str, Any]:
    return {
        "extractor_revision": REPAIR_PAYLOAD_EXTRACTOR_REVISION,
        "envelope": envelope.to_diagnostics(),
    }


def _fail(
    *,
    code: str,
    envelope: ChatMessageEnvelope,
    source: str = "",
    response_field_present: bool = True,
    extra: Mapping[str, Any] | None = None,
) -> RepairPayloadExtraction:
    diagnostics = _base_diagnostics(envelope)
    diagnostics.update(
        {
            "extraction_source_attempted": source,
            "extraction_error_code": code,
        }
    )
    if extra:
        diagnostics.update(dict(extra))
    return RepairPayloadExtraction(
        ok=False,
        source=source,
        response_field_present=response_field_present,
        error_code=code,
        public_message=_PUBLIC_MESSAGE,
        diagnostics=diagnostics,
    )


def _succeed(
    *,
    source: str,
    envelope: ChatMessageEnvelope,
    structured_payload: Any | None = None,
    text: str = "",
    extra: Mapping[str, Any] | None = None,
) -> RepairPayloadExtraction:
    diagnostics = _base_diagnostics(envelope)
    diagnostics.update(
        {
            "extraction_source": source,
            "extraction_error_code": None,
            "payload_text_chars": len(text or ""),
            "payload_text_sha256": _sha256_text(text) if text else None,
        }
    )
    if extra:
        diagnostics.update(dict(extra))
    return RepairPayloadExtraction(
        ok=True,
        source=source,
        structured_payload=structured_payload,
        text=text,
        response_field_present=True,
        diagnostics=diagnostics,
    )


def _normalize_owner(owner: Any) -> list[str] | None:
    """Accept the declared string form, or a list the model echoed back."""

    if isinstance(owner, str):
        value = owner.strip()
        return [value] if value else None
    if isinstance(owner, Sequence) and not isinstance(owner, (str, bytes)):
        values = [str(item).strip() for item in owner]
        cleaned = [item for item in values if item]
        return cleaned or None
    return None


def _tool_arguments_to_envelope(
    arguments: Mapping[str, Any],
    *,
    batch_kind: str,
    approved_files: Sequence[GeneratedCandidateFile],
) -> dict[str, Any] | None:
    """Map the tool's ``{path, owner, source}`` rows onto the batch contract.

    Returns ``None`` when the arguments do not carry a ``files`` array; the
    caller then reports a contract failure rather than guessing at the shape.
    """

    rows = arguments.get("files")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return None
    approved_kind = {item.path: item.file_kind for item in approved_files}
    default_kind = _BATCH_DEFAULT_FILE_KIND.get(str(batch_kind), "business_component")
    files: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            # Preserve the invalid row so contract validation reports it.
            files.append({})
            continue
        path = row.get("path")
        entry: dict[str, Any] = {
            "path": path,
            "file_kind": approved_kind.get(str(path), default_kind),
            "source": row.get("source"),
        }
        owners = _normalize_owner(row.get("owner"))
        if owners is not None:
            entry["owner_contract_ids"] = owners
        files.append(entry)
    return {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "batch_kind": batch_kind,
        "files": files,
    }


def _extract_from_tool_call(
    call: ProviderToolCall,
    *,
    envelope: ChatMessageEnvelope,
    batch_kind: str,
    approved_files: Sequence[GeneratedCandidateFile],
) -> RepairPayloadExtraction:
    if call.name != REPAIR_TOOL_NAME:
        return _fail(
            code=REPAIR_TOOL_NAME_INVALID,
            envelope=envelope,
            source=SOURCE_TOOL_CALL,
            extra={"observed_tool_name": call.name},
        )
    raw_arguments = call.arguments or ""
    if not raw_arguments.strip():
        return _fail(
            code=REPAIR_TOOL_ARGUMENTS_MISSING,
            envelope=envelope,
            source=SOURCE_TOOL_CALL,
            extra={"tool_arguments_chars": 0},
        )
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        # No usable arguments were delivered; never repair the JSON by hand.
        return _fail(
            code=REPAIR_TOOL_ARGUMENTS_MISSING,
            envelope=envelope,
            source=SOURCE_TOOL_CALL,
            extra={
                "tool_arguments_chars": len(raw_arguments),
                "tool_arguments_sha256": call.arguments_sha256,
                "tool_arguments_error": f"{exc.msg} (line {exc.lineno} col {exc.colno})",
            },
        )
    if not isinstance(arguments, Mapping):
        return _fail(
            code=REPAIR_TOOL_ARGUMENTS_MISSING,
            envelope=envelope,
            source=SOURCE_TOOL_CALL,
            extra={
                "tool_arguments_chars": len(raw_arguments),
                "tool_arguments_type": type(arguments).__name__,
            },
        )
    mapped = _tool_arguments_to_envelope(
        arguments,
        batch_kind=batch_kind,
        approved_files=approved_files,
    )
    if mapped is None:
        # Arguments parsed but carried no ``files`` array. Hand the raw object
        # to the repair contract so it reports the precise envelope failure.
        mapped = dict(arguments)
    return _succeed(
        source=SOURCE_TOOL_CALL,
        envelope=envelope,
        structured_payload=mapped,
        extra={
            "tool_name": call.name,
            "tool_call_id": call.call_id,
            "tool_arguments_chars": len(raw_arguments),
            "tool_arguments_sha256": call.arguments_sha256,
        },
    )


def extract_candidate_repair_payload(
    *,
    envelope: ChatMessageEnvelope,
    batch_kind: str,
    approved_files: Sequence[GeneratedCandidateFile],
    text: str | None = None,
    supports_provider_parsed: bool = False,
) -> RepairPayloadExtraction:
    """Locate the repair payload in the one field the provider actually used.

    ``text`` is the adapter's already-extracted assistant text and is used only
    as a consistency fallback when the envelope itself is unavailable.
    """

    if envelope.refusal_text:
        return _fail(
            code=REPAIR_REFUSED,
            envelope=envelope,
            source="refusal",
        )

    # 1) Provider-native parsed object, only where the profile proves support.
    if supports_provider_parsed and envelope.has_parsed:
        parsed = envelope.parsed_payload
        if isinstance(parsed, (Mapping, list)):
            return _succeed(
                source=SOURCE_PROVIDER_PARSED,
                envelope=envelope,
                structured_payload=parsed,
            )

    # 2) Exactly one approved repair tool call.
    if len(envelope.tool_calls) > 1:
        return _fail(
            code=REPAIR_MULTIPLE_TOOL_CALLS,
            envelope=envelope,
            source=SOURCE_TOOL_CALL,
            extra={
                "tool_call_names": [item.name for item in envelope.tool_calls],
            },
        )
    if len(envelope.tool_calls) == 1:
        return _extract_from_tool_call(
            envelope.tool_calls[0],
            envelope=envelope,
            batch_kind=batch_kind,
            approved_files=approved_files,
        )

    # 3) / 4) Assistant content, as a string or as ordered text parts.
    content = envelope.content_text
    if content is None and isinstance(text, str):
        content = text
    if envelope.content_kind == "parts" and envelope.content_parts_invalid:
        return _fail(
            code=REPAIR_CONTENT_PARTS_INVALID,
            envelope=envelope,
            source=SOURCE_CONTENT_PARTS,
            extra={"content_part_types": list(envelope.content_part_types)},
        )
    if isinstance(content, str) and content.strip():
        source = (
            SOURCE_CONTENT_PARTS
            if envelope.content_kind == "parts"
            else SOURCE_CONTENT_STRING
        )
        # 5) The strict text parser runs downstream on this text.
        return _succeed(source=source, envelope=envelope, text=content)

    # Nothing supported carried a payload. Reasoning-only responses land here:
    # hidden reasoning is never promoted to repaired output.
    return _fail(
        code=REPAIR_PAYLOAD_MISSING,
        envelope=envelope,
        response_field_present=False,
        extra={"reasoning_only": envelope.has_reasoning},
    )


__all__ = [
    "EXTRACTION_ERROR_CODES",
    "REPAIR_CONTENT_PARTS_INVALID",
    "REPAIR_MULTIPLE_TOOL_CALLS",
    "REPAIR_PAYLOAD_EXTRACTOR_REVISION",
    "REPAIR_PAYLOAD_MISSING",
    "REPAIR_REFUSED",
    "REPAIR_TOOL_ARGUMENTS_MISSING",
    "REPAIR_TOOL_NAME",
    "REPAIR_TOOL_NAME_INVALID",
    "REPAIR_TOOL_SCHEMA",
    "SOURCE_CONTENT_PARTS",
    "SOURCE_CONTENT_STRING",
    "SOURCE_PROVIDER_PARSED",
    "SOURCE_TOOL_CALL",
    "RepairPayloadExtraction",
    "build_repair_tool_choice",
    "build_repair_tool_spec",
    "extract_candidate_repair_payload",
]
