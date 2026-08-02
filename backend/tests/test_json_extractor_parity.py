"""Every JSON extractor in the repo must recover every captured payload.

1.6 fixed `app/shared/json_utils.py` and measured it against the four verbatim
model responses in `tests/fixtures/model_json/`. The other extractors were never
measured. Replaying the same payloads through them scored:

    shared/json_utils (1.6, fixed)       ok      ok      ok      ok
    appspec/sanitize/preparse_normalize  FAIL    FAIL    FAIL    FAIL
    services/page_experience   [LIVE]    FAIL    PARTIAL FAIL    FAIL
    appspec/authoring_parser   [LIVE]    FAIL    FAIL    ok      FAIL

Two of those four payloads are *structurally complete* — brace-balanced, fence
closed — and simply under-escaped, so nothing in the failing column looked like
a parse bug in the log. It looked like truncation, and the pipeline re-asked.

`PARTIAL` is the worst cell and the reason this file exists: it is not a
failure, it is a **success that lost data**. See
`test_partial_recovery_is_not_reported_as_a_clean_parse`.

These tests are the parity contract. They are deliberately written against the
public entry point of each extractor rather than its internals, so that routing
an extractor through the shared one keeps them green while reverting the routing
turns them red.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# Import order: `app.domain.appspec` pulls `app.application.appspec` back
# through `reference_integrity`, so the application package must land first.
import app.application.appspec  # noqa: F401
from app.application.services.page_experience import _parse_json_from_response
from app.domain.appspec.authoring_parser import parse_appspec_authoring_output
from app.domain.appspec.sanitize.preparse_normalize import extract_json_object_text
from app.shared.json_utils import extract_json_from_text

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "model_json"

PAYLOADS = sorted(path.name for path in FIXTURES.glob("*.txt"))


def _raw(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _via_shared(raw: str) -> dict:
    return extract_json_from_text(raw)


def _via_preparse(raw: str) -> dict:
    text, meta = extract_json_object_text(raw)
    assert meta.get("ok") is True, f"extraction not ok: {meta}"
    assert text is not None
    return json.loads(text)


def _via_page_experience(raw: str) -> dict:
    result = _parse_json_from_response(raw)
    assert result is not None, "returned None"
    return result


def _via_authoring(raw: str) -> dict:
    result = parse_appspec_authoring_output(raw, finish_reason="stop")
    assert result.ok, f"{result.error_code}: {result.parser_error}"
    assert result.payload is not None
    return result.payload


EXTRACTORS = {
    "shared/json_utils": _via_shared,
    "appspec/preparse_normalize": _via_preparse,
    "services/page_experience": _via_page_experience,
    "appspec/authoring_parser": _via_authoring,
}


def test_the_captured_payloads_are_still_present() -> None:
    """A parity suite over zero fixtures passes and proves nothing."""
    assert len(PAYLOADS) == 4, PAYLOADS


@pytest.mark.parametrize("extractor", sorted(EXTRACTORS))
@pytest.mark.parametrize("payload", PAYLOADS)
def test_every_extractor_recovers_every_captured_payload(extractor: str, payload: str) -> None:
    raw = _raw(payload)
    value = EXTRACTORS[extractor](raw)
    assert isinstance(value, dict) and value, f"{extractor} produced {type(value).__name__}"


@pytest.mark.parametrize("extractor", sorted(EXTRACTORS))
@pytest.mark.parametrize("payload", PAYLOADS)
def test_recovery_is_whole_not_partial(extractor: str, payload: str) -> None:
    """Recovering *a* document is not enough; it must be the same document.

    Without this, `services/page_experience` passes the test above while
    returning `src/data/mock.ts` with its 15,143 characters of content replaced
    by an empty string.
    """
    raw = _raw(payload)
    assert EXTRACTORS[extractor](raw) == _via_shared(raw), (
        f"{extractor} recovered a DIFFERENT document from {payload}"
    )


def test_partial_recovery_is_not_reported_as_a_clean_parse() -> None:
    """The measured silent-data-loss case, pinned by its exact shape.

    `request67_fix_agent_retry_unescaped_quotes` is not truncated — the model
    drifted out of escaping mid-string. The old code sent it straight to the
    truncation closer, which trimmed the document back until something parsed
    and returned three files with the right paths, the first two byte-identical,
    and the third emptied. No exception, no log, no None.
    """
    raw = _raw("request67_fix_agent_retry_unescaped_quotes.txt")

    parsed = _parse_json_from_response(raw)
    assert parsed is not None

    files = parsed["files"]
    reference = _via_shared(raw)["files"]
    assert len(files) == len(reference) == 3

    for got, want in zip(files, reference):
        assert got["path"] == want["path"]
        assert len(got["content"]) == len(want["content"]), (
            f"{got['path']}: {len(want['content']) - len(got['content'])} characters "
            "of content silently dropped"
        )


def test_authoring_parser_reports_that_it_repaired() -> None:
    """A salvaged AppSpec must be labelled as salvaged.

    The strategy and the `repaired` flag are what separate "the model sent us
    unparseable JSON" (a prompt problem) from "the transport truncated it" (a
    token-budget problem). Requests 67 and 69 were misdiagnosed as the latter
    for several sessions.
    """
    result = parse_appspec_authoring_output(
        _raw("request67_fix_agent_primary_invalid_escape.txt"), finish_reason="stop"
    )

    assert result.ok
    assert result.strategy == "repaired"
    assert result.diagnostics["repaired"] is True
    assert result.diagnostics["truncated"] is False
    assert result.diagnostics["strict_parser_error"]


def test_repair_never_preempts_strict_parsing() -> None:
    """The invariant the whole design rests on: strict first, always.

    Recovery is only reachable after every non-destructive path has failed, so a
    well-formed response cannot be altered — or even re-serialized — by it.
    """
    clean = json.dumps({"roles": [{"id": "owner", "pages": []}]}, indent=2)

    authoring = parse_appspec_authoring_output(clean, finish_reason="stop")
    assert authoring.ok
    assert authoring.strategy == "direct"
    assert authoring.diagnostics.get("repaired") is not True
    assert authoring.extracted_text == clean  # byte-identical, not re-serialized

    text, meta = extract_json_object_text(clean)
    assert meta["method"] == "direct"
    assert text == clean

    assert _parse_json_from_response(clean) == json.loads(clean)


def test_a_genuinely_truncated_response_still_fails_closed() -> None:
    """Repair must not launder a real `max_tokens` cut into a success.

    `repair_json_text` returns None on an unterminated document rather than
    inventing a closing brace, so the truncated verdict has to survive.
    """
    cut = '{"roles": [{"id": "owner", "pages": [{"name": "Dash'

    result = parse_appspec_authoring_output(cut, finish_reason="length")

    assert result.ok is False
    assert result.error_code == "app_spec_authoring_json_truncated"
    assert result.diagnostics["truncated"] is True
