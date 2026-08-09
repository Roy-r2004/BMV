"""Canonical deterministic parser for AppSpec authoring model output."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping


AUTHORING_NO_JSON_OBJECT = "app_spec_authoring_no_json_object"
AUTHORING_JSON_TRUNCATED = "app_spec_authoring_json_truncated"
AUTHORING_JSON_SYNTAX_INVALID = "app_spec_authoring_json_syntax_invalid"
AUTHORING_RESPONSE_FIELD_MISSING = "app_spec_authoring_response_field_missing"

_PUBLIC_AUTHORING_ERROR = (
    "AppSpec model output was not valid JSON: no usable JSON object was found."
)

_FENCE_RE = re.compile(
    r"```(?:json|JSON)?\s*\n(?P<body>[\s\S]*?)\n?```",
    re.MULTILINE,
)

# A recovered object dwarfed by the response it came from is a nested fragment,
# not the document. Request 143: an unescaped quote desynchronised the outer
# object of a 31,303-char authoring response, the span fallback surfaced one
# balanced 414-char acceptance-test object, and the run spent every repair on a
# candidate that was 1.3 % of what the model wrote — five revisions, dead.
# Failing closed re-asks the writer, which is a legal move; repairing a
# fragment has none. The raw floor keeps the guard out of small documents,
# where legitimate extractions (prose-wrapped objects, first-object policy)
# can sit near the ratio boundary.
_FRAGMENT_GUARD_MIN_RAW_CHARS = 2000
_FRAGMENT_GUARD_MIN_RATIO = 0.5


def _is_fragment_extraction(raw_chars: int, extracted_chars: int) -> bool:
    if raw_chars < _FRAGMENT_GUARD_MIN_RAW_CHARS:
        return False
    return extracted_chars < raw_chars * _FRAGMENT_GUARD_MIN_RATIO


@dataclass
class AppSpecAuthoringParseResult:
    """Outcome of one deterministic authoring-output parse."""

    ok: bool
    payload: dict[str, Any] | None = None
    extracted_text: str | None = None
    strategy: str | None = None
    error_code: str | None = None
    public_message: str = _PUBLIC_AUTHORING_ERROR
    parser_error: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def typed_error(self) -> str | None:
        return self.error_code if not self.ok else None


def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _sanitized_edges(text: str, *, limit: int = 80) -> dict[str, str]:
    cleaned = (text or "").replace("\r\n", "\n")
    prefix = cleaned[:limit]
    suffix = cleaned[-limit:] if len(cleaned) > limit else cleaned
    # Avoid leaking large prose; keep length + hash elsewhere.
    return {
        "prefix": prefix if _looks_safe_edge(prefix) else "",
        "suffix": suffix if _looks_safe_edge(suffix) else "",
    }


def _looks_safe_edge(fragment: str) -> bool:
    if not fragment:
        return True
    # Prefer edges that are structural JSON/markdown markers.
    stripped = fragment.strip()
    if not stripped:
        return True
    return stripped[0] in "{[`\"'\\n " or stripped[-1] in "}`]\"'\\n "


def _first_non_whitespace(text: str) -> str | None:
    for ch in text or "":
        if not ch.isspace():
            return ch
    return None


def _balanced_object_span(text: str) -> tuple[int, int, str] | None:
    """Return (start, end_exclusive, status) for the first top-level `{...}`.

    status is ``complete``, ``truncated``, or ``none``.
    """

    start = (text or "").find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for index, ch in enumerate(text[start:], start):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, index + 1, "complete"
    if depth > 0:
        return start, len(text), "truncated"
    return None


def _try_loads(candidate: str) -> tuple[Any | None, str | None]:
    try:
        return json.loads(candidate), None
    except json.JSONDecodeError as exc:
        return None, f"{exc.msg} (line {exc.lineno} col {exc.colno})"
    except Exception as exc:  # pragma: no cover - unexpected parser failures
        return None, str(exc)


def _try_repair(text: str) -> tuple[dict[str, Any], str, str] | None:
    """Last non-destructive attempt: the shared extractor's repair pass.

    Returns ``(payload, extracted_text, method)`` or None.

    Two of the shapes the authoring model actually produces are *structurally
    complete* — brace-balanced, fence closed, `finish_reason: stop` — and still
    not valid JSON: it drifts out of escaping mid-string (bare `"` where `\\"`
    was required), and it writes shell-style `\\`+newline line continuations
    inside strings. Nothing above this line can read either one, so the parser
    used to return `app_spec_authoring_json_syntax_invalid` and the caller
    re-asked a 28k-token authoring call for output the model had already sent.

    This runs only after every strict path has failed, so a well-formed
    response can never reach it, and `json.loads` still adjudicates the result
    — a bad repair fails closed rather than inventing a document.
    """
    try:
        from app.shared.json_utils import extract_json_with_meta

        value, meta = extract_json_with_meta(text)
    except Exception:
        return None
    if not isinstance(value, dict):
        return None
    return value, json.dumps(value, ensure_ascii=False), str(meta.get("method") or "repaired")


def _repaired_result(
    text: str,
    *,
    finish_reason: str | None,
    strict_error: str | None,
) -> AppSpecAuthoringParseResult | None:
    recovered = _try_repair(text)
    if recovered is None:
        return None
    payload, extracted, method = recovered
    if _is_fragment_extraction(len(text), len(extracted)):
        return None
    return AppSpecAuthoringParseResult(
        ok=True,
        payload=payload,
        extracted_text=extracted,
        strategy="repaired",
        diagnostics={
            "raw_response_sha256": _sha256_text(text),
            "raw_response_chars": len(text),
            "extracted_object_sha256": _sha256_text(extracted),
            "extracted_object_chars": len(extracted),
            "finish_reason": finish_reason,
            "truncated": False,
            # Loud on purpose: the model sent unparseable JSON and we salvaged
            # it. That is a prompt problem, not a transport one.
            "repaired": True,
            "repair_method": method,
            "strict_parser_error": strict_error,
        },
    )


def _fail(
    *,
    code: str,
    strategy: str | None,
    raw: str,
    parser_error: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> AppSpecAuthoringParseResult:
    edges = _sanitized_edges(raw)
    diagnostics = {
        "raw_response_sha256": _sha256_text(raw),
        "raw_response_chars": len(raw or ""),
        "first_non_whitespace": _first_non_whitespace(raw),
        "has_markdown_fence": "```" in (raw or ""),
        "extraction_strategy_attempted": strategy,
        "parser_error_code": code,
        "parser_error": parser_error,
        "sanitized_prefix": edges["prefix"],
        "sanitized_suffix": edges["suffix"],
    }
    if extra:
        diagnostics.update(dict(extra))
    return AppSpecAuthoringParseResult(
        ok=False,
        strategy=strategy,
        error_code=code,
        public_message=_PUBLIC_AUTHORING_ERROR,
        parser_error=parser_error,
        diagnostics=diagnostics,
    )


def parse_appspec_authoring_output(
    raw: str | None,
    *,
    finish_reason: str | None = None,
    response_field_present: bool = True,
) -> AppSpecAuthoringParseResult:
    """Parse AppSpec authoring output with a fixed, fail-closed strategy order.

    Order:
    1. Direct JSON parse of the complete response
    2. Explicit JSON markdown fence extraction
    3. String-aware balanced-brace scan for the first complete top-level object
    4. Strict ``json.loads`` of the extracted object
    5. Re-escaping repair via the shared extractor — only after 1-4 have all
       failed, so a well-formed response is never touched by it. See
       ``_try_repair``: without this step a structurally complete but
       under-escaped response is reported as invalid and re-asked in full.
    """

    if not response_field_present:
        return _fail(
            code=AUTHORING_RESPONSE_FIELD_MISSING,
            strategy="response_field",
            raw="",
            parser_error="provider content field missing",
        )

    text = raw if isinstance(raw, str) else ""
    if not text.strip():
        return _fail(
            code=AUTHORING_NO_JSON_OBJECT,
            strategy="empty",
            raw=text,
            parser_error="empty_output",
            extra={"finish_reason": finish_reason},
        )

    # 1) Direct parse
    direct, direct_err = _try_loads(text.strip())
    if isinstance(direct, dict):
        return AppSpecAuthoringParseResult(
            ok=True,
            payload=direct,
            extracted_text=text.strip(),
            strategy="direct",
            diagnostics={
                "raw_response_sha256": _sha256_text(text),
                "raw_response_chars": len(text),
                "extracted_object_sha256": _sha256_text(text.strip()),
                "extracted_object_chars": len(text.strip()),
                "finish_reason": finish_reason,
                "truncated": False,
            },
        )
    if direct is not None:
        return _fail(
            code=AUTHORING_JSON_SYNTAX_INVALID,
            strategy="direct",
            raw=text,
            parser_error="top_level_not_object",
            extra={"finish_reason": finish_reason},
        )

    # A stream the provider cut with an error is not the model's answer. Only
    # the complete direct parse above may pass; every extraction strategy below
    # exists to find a fragment, and a fragment of an error-cut body is a
    # different document than the one the model was writing. Request 118: a
    # 15,939-char partial stream (finish_reason=error, 0 output tokens) was
    # "repaired" into a 973-char candidate, minted five revisions, and failed
    # the request as a spec rejection. Truncated is the honest class — the
    # authoring retry loop re-asks the provider instead of judging the cut.
    if str(finish_reason or "").lower() == "error":
        return _fail(
            code=AUTHORING_JSON_TRUNCATED,
            strategy="provider_error",
            raw=text,
            parser_error="provider_error_cut_stream",
            extra={"finish_reason": finish_reason, "truncated": True},
        )

    # 2) Explicit labelled JSON fence (or plain ``` fence)
    for match in _FENCE_RE.finditer(text):
        body = (match.group("body") or "").strip()
        if not body:
            continue
        loaded, err = _try_loads(body)
        if isinstance(loaded, dict):
            return AppSpecAuthoringParseResult(
                ok=True,
                payload=loaded,
                extracted_text=body,
                strategy="markdown_fence",
                diagnostics={
                    "raw_response_sha256": _sha256_text(text),
                    "raw_response_chars": len(text),
                    "extracted_object_sha256": _sha256_text(body),
                    "extracted_object_chars": len(body),
                    "finish_reason": finish_reason,
                    "truncated": False,
                },
            )
        if loaded is not None:
            return _fail(
                code=AUTHORING_JSON_SYNTAX_INVALID,
                strategy="markdown_fence",
                raw=text,
                parser_error="fenced_top_level_not_object",
                extra={"finish_reason": finish_reason},
            )
        # Fenced body present but invalid JSON — classify below after scan too.
        fence_err = err

    # 3) Balanced brace scan (string/escape aware)
    span = _balanced_object_span(text)
    if span is None:
        truncated = str(finish_reason or "").lower() in {"length", "max_tokens"}
        code = AUTHORING_JSON_TRUNCATED if truncated else AUTHORING_NO_JSON_OBJECT
        return _fail(
            code=code,
            strategy="balanced_scan",
            raw=text,
            parser_error=direct_err or "no_object",
            extra={
                "finish_reason": finish_reason,
                "truncated": truncated,
            },
        )

    start, end, status = span
    candidate = text[start:end]
    if status == "truncated":
        # An unescaped `"` desynchronises the brace matcher above, so a complete
        # document can present as unbalanced. Try the repair pass before
        # declaring truncation; it fails closed, so a real cut still lands here.
        recovered = _repaired_result(
            text, finish_reason=finish_reason, strict_error="unbalanced_object"
        )
        if recovered is not None:
            return recovered
        return _fail(
            code=AUTHORING_JSON_TRUNCATED,
            strategy="balanced_scan",
            raw=text,
            parser_error="unbalanced_object",
            extra={
                "finish_reason": finish_reason,
                "truncated": True,
                "candidate_chars": len(candidate),
            },
        )

    loaded, err = _try_loads(candidate)
    if isinstance(loaded, dict) and _is_fragment_extraction(len(text), len(candidate)):
        return _fail(
            code=AUTHORING_JSON_SYNTAX_INVALID,
            strategy="balanced_scan",
            raw=text,
            parser_error="fragment_extracted",
            extra={
                "finish_reason": finish_reason,
                "truncated": False,
                "candidate_chars": len(candidate),
            },
        )
    if isinstance(loaded, dict):
        return AppSpecAuthoringParseResult(
            ok=True,
            payload=loaded,
            extracted_text=candidate,
            strategy="balanced_scan",
            diagnostics={
                "raw_response_sha256": _sha256_text(text),
                "raw_response_chars": len(text),
                "extracted_object_sha256": _sha256_text(candidate),
                "extracted_object_chars": len(candidate),
                "finish_reason": finish_reason,
                "truncated": False,
            },
        )
    if loaded is not None:
        return _fail(
            code=AUTHORING_JSON_SYNTAX_INVALID,
            strategy="balanced_scan",
            raw=text,
            parser_error="extracted_top_level_not_object",
            extra={"finish_reason": finish_reason},
        )

    strict_error = err or locals().get("fence_err") or "invalid_object"
    # 4) Every strict path has failed. Re-escaping repair, then fail closed.
    recovered = _repaired_result(text, finish_reason=finish_reason, strict_error=strict_error)
    if recovered is not None:
        return recovered

    return _fail(
        code=AUTHORING_JSON_SYNTAX_INVALID,
        strategy="balanced_scan",
        raw=text,
        parser_error=strict_error,
        extra={"finish_reason": finish_reason, "truncated": False},
    )


def authoring_parse_diagnostics(
    result: AppSpecAuthoringParseResult,
) -> dict[str, Any]:
    """Admin-safe diagnostic fragment for one authoring parse."""

    out = {
        "ok": result.ok,
        "strategy": result.strategy,
        "error_code": result.error_code,
        "public_message": result.public_message if not result.ok else None,
        **dict(result.diagnostics),
    }
    return out


__all__ = [
    "AUTHORING_JSON_SYNTAX_INVALID",
    "AUTHORING_JSON_TRUNCATED",
    "AUTHORING_NO_JSON_OBJECT",
    "AUTHORING_RESPONSE_FIELD_MISSING",
    "AppSpecAuthoringParseResult",
    "authoring_parse_diagnostics",
    "parse_appspec_authoring_output",
]
