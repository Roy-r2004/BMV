"""Unit tests for the shared model-JSON extractor.

Every fixture under `tests/fixtures/model_json/` is a *verbatim* model response
captured by `dump_unparsed_fix_agent_response` from a real run. All four were
reported in the log as `Provider output was truncated`; none of them is
truncated. On requests 67 and 69 the pipeline spent 161.4 s across three calls
re-asking for output the model had already delivered.

The extractor is a pure function, so it is tested directly. The invariant the
tests defend is: **strict parsing is always tried first**, so a well-formed
response can never be altered by the recovery path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.shared.json_utils import (
    balanced_object_spans,
    extract_json_from_text,
    extract_json_with_meta,
    repair_json_text,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "model_json"


def _payload(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# The captured payloads — what shape each one actually was
# --------------------------------------------------------------------------- #


def test_request68_prose_before_the_fence_hid_valid_json() -> None:
    """Request 68: the JSON was *valid*, fenced, and the extractor never saw it.

    The response opens with an explanation containing
    `(event: { target: { value: string } })`. The old stripper only removed a
    fence at position 0, so the bracket matcher started on the brace in that
    sentence, failed, and gave up on the first failure instead of trying the
    next candidate.
    """
    raw = _payload("request68_fix_agent_primary_prose_before_fence.txt")
    assert not raw.lstrip().startswith("```"), "fixture must keep its leading prose"
    assert raw.index("{ target:") < raw.index("```json"), "prose brace must come first"

    parsed, meta = extract_json_with_meta(raw)

    assert meta["method"] == "fenced-block", "the fence must be what located it"
    assert meta["repaired"] is False, "this payload needed no repair, only finding"
    assert [f["path"] for f in parsed["files"]] == [
        "src/pages/owner/AddPaintingPage.tsx",
        "src/pages/owner/PaintingsPage.tsx",
    ]


def test_request67_shell_style_line_continuations_are_recovered() -> None:
    """Request 67 primary: `\\` + newline used as a line separator inside a string.

    `brace_imbalance=0 likely_truncated=False files_key=True` on 37 KB — the
    document is complete; `\\` followed by a newline is simply not a JSON escape.
    """
    raw = _payload("request67_fix_agent_primary_invalid_escape.txt")
    with pytest.raises(json.JSONDecodeError, match="Invalid .escape"):
        json.loads(raw.strip().removeprefix("```json").removesuffix("```"))

    parsed, meta = extract_json_with_meta(raw)

    assert meta["repaired"] is True
    assert [f["path"] for f in parsed["files"]] == [
        "src/pages/owner/AddPaintingPage.tsx",
        "src/pages/owner/EditPaintingPage.tsx",
        "src/data/mock.ts",
        "src/pages/AiFeaturesPage.tsx",
    ]
    for item in parsed["files"]:
        content = item["content"]
        # `\` before whitespace was the continuation marker; nothing else was.
        # Escaped quotes inside the TypeScript being written are legitimate and
        # must survive, so the assertion is narrow on purpose.
        assert "\\ " not in content and "\\\n" not in content, item["path"]
        assert content.rstrip().endswith(("}", ";")), item["path"]


@pytest.mark.parametrize(
    ("fixture", "paths"),
    [
        (
            "request67_fix_agent_retry_unescaped_quotes.txt",
            [
                "src/pages/owner/AddPaintingPage.tsx",
                "src/pages/owner/EditPaintingPage.tsx",
                "src/data/mock.ts",
            ],
        ),
        (
            "request69_fix_agent_retry_partial_files.txt",
            [
                "src/pages/ArtworkDetailPage.tsx",
                "src/pages/owner/AddPaintingPage.tsx",
                "src/pages/owner/EditPageContentPage.tsx",
                "src/pages/owner/ManagePaintingsPage.tsx",
            ],
        ),
    ],
)
def test_the_model_drifts_out_of_escaping_mid_string(fixture: str, paths: list[str]) -> None:
    """Requests 67 and 69: bare `"` inside a `content` value.

    The model escapes correctly for thousands of characters and then writes raw
    source — `id: "edit-1"`, `"item1": "https://…"` — inside a JSON string. That
    is genuinely invalid JSON, which is why re-asking never helped: it is the
    model's habit, not a provider limit.
    """
    raw = _payload(fixture)
    parsed, meta = extract_json_with_meta(raw)

    assert meta["repaired"] is True
    assert [f["path"] for f in parsed["files"]] == paths


@pytest.mark.parametrize(
    "fixture",
    [
        "request67_fix_agent_primary_invalid_escape.txt",
        "request67_fix_agent_retry_unescaped_quotes.txt",
        "request68_fix_agent_primary_prose_before_fence.txt",
        "request69_fix_agent_retry_partial_files.txt",
    ],
)
def test_recovery_loses_no_payload(fixture: str) -> None:
    """Recovery must not silently swallow one file's body into another's.

    A tolerant parser that guesses a string terminator too late produces *valid*
    JSON with one enormous value. Re-serialising and comparing length against the
    raw response catches exactly that: the round trip has to stay within a few
    percent.
    """
    raw = _payload(fixture)
    parsed = extract_json_from_text(raw)
    ratio = len(json.dumps(parsed)) / len(raw)
    assert 0.90 < ratio < 1.05, f"round trip changed size by {ratio:.3f}x"


# --------------------------------------------------------------------------- #
# Shapes, one at a time
# --------------------------------------------------------------------------- #


def test_plain_json_is_returned_untouched() -> None:
    parsed, meta = extract_json_with_meta('{"strategy": "ops", "ops": []}')
    assert meta == {"method": "direct", "repaired": False}
    assert parsed == {"strategy": "ops", "ops": []}


def test_a_fenced_object_parses_strictly() -> None:
    parsed, meta = extract_json_with_meta('```json\n{"files": [{"path": "src/a.tsx"}]}\n```')
    assert meta["repaired"] is False
    assert parsed["files"][0]["path"] == "src/a.tsx"


def test_prose_on_both_sides_of_a_fence() -> None:
    raw = (
        "Here is what I changed, and why the `{ a: 1 }` shape was wrong:\n\n"
        '```json\n{"files": [{"path": "src/a.tsx", "content": "x"}]}\n```\n\n'
        "Let me know if you want the other page too."
    )
    parsed, meta = extract_json_with_meta(raw)
    assert meta["repaired"] is False
    assert parsed["files"][0]["content"] == "x"


def test_prose_on_both_sides_of_a_bare_object() -> None:
    raw = 'Sure. {"files": [{"path": "src/a.tsx", "content": "x"}]} — done.'
    parsed, meta = extract_json_with_meta(raw)
    assert meta["method"] == "span"
    assert parsed["files"][0]["path"] == "src/a.tsx"


def test_a_decoy_brace_in_the_prose_is_stepped_over() -> None:
    """This is request 68's shape, reduced. The decoy must not end the search."""
    raw = (
        "`onSearchChange` expects `(event: { target: { value: string } }) => void`.\n"
        '```json\n{"ops": [{"op": "replace", "path": "src/a.tsx"}]}\n```'
    )
    assert extract_json_from_text(raw)["ops"][0]["op"] == "replace"


def test_a_valid_decoy_object_in_the_prose_never_wins_over_the_fenced_payload() -> None:
    """Span scanning alone is not enough — it would return the decoy.

    Scanning candidate `{` spans rescues a bare object from prose, but a model
    that quotes its own previous plan back at you emits a *parseable* object
    before the real one. The fence is the stronger signal and has to be tried
    first.
    """
    raw = (
        'Your last plan was {"strategy": "noop"}, which applied nothing. Here is the real one:\n'
        '```json\n{"strategy": "ops", "ops": [{"op": "replace", "path": "src/a.tsx"}]}\n```'
    )
    parsed, meta = extract_json_with_meta(raw)
    assert meta["method"] == "fenced-block"
    assert parsed["strategy"] == "ops"


def test_nested_braces_inside_string_values_survive() -> None:
    payload = {
        "files": [
            {
                "path": "src/pages/Home.tsx",
                "content": (
                    "export default function Home() {\n"
                    '  const style = { color: "red", nested: { deep: "{}" } };\n'
                    "  return <div style={style}>{'}'}</div>;\n"
                    "}\n"
                ),
            }
        ]
    }
    raw = "```json\n" + json.dumps(payload, indent=2) + "\n```"
    assert extract_json_from_text(raw) == payload


def test_an_object_literal_inside_a_content_string_is_not_mistaken_for_the_document() -> None:
    """A `{...}` in the source being written must not win over the real payload.

    Span scanning starts at the *first* brace; the recovery pass has to keep the
    outer document, not return the first inner object that happens to parse.
    """
    content = 'const seed = {"id": "a", "title": "b"};\nexport default seed;\n'
    raw = "```json\n" + json.dumps({"files": [{"path": "src/data/mock.ts", "content": content}]}) + "\n```"
    parsed = extract_json_from_text(raw)
    assert parsed["files"][0]["content"] == content


def test_a_trailing_partial_line_is_reported_not_invented() -> None:
    """Genuine truncation must still fail — and say so without a fabricated tail."""
    raw = '```json\n{"files": [{"path": "src/a.tsx", "content": "export default function A('
    with pytest.raises(ValueError) as excinfo:
        extract_json_from_text(raw)
    assert "No valid JSON object" in str(excinfo.value)
    assert repair_json_text(raw) is None, "an unterminated string must not be closed for the model"


def test_prose_with_no_object_at_all_still_reports_that() -> None:
    with pytest.raises(ValueError, match="No JSON object found"):
        extract_json_from_text("I cannot emit the full AppSpec here. Please refine the brief.")


def test_empty_output_is_named_as_empty() -> None:
    with pytest.raises(ValueError, match="Empty model output"):
        extract_json_from_text("   ")


def test_the_failure_message_carries_the_decoder_reason() -> None:
    """`No valid JSON object found` with no reason is what made this a five-session
    misdiagnosis. The decoder's own complaint has to reach the log."""
    with pytest.raises(ValueError, match="last decode error"):
        extract_json_from_text('{"files": [{"path": "a", }]} trailing')


# --------------------------------------------------------------------------- #
# The repair pass, on its own
# --------------------------------------------------------------------------- #


def test_repair_declines_to_touch_valid_json() -> None:
    assert repair_json_text('{"a": "b", "c": [1, 2, {"d": "e"}]}') is None


def test_repair_re_escapes_a_bare_quote_in_a_value() -> None:
    broken = '{"content": "he said "hi" loudly"}'
    assert json.loads(repair_json_text(broken)) == {"content": 'he said "hi" loudly'}


def test_repair_keeps_a_regex_backslash_it_cannot_interpret() -> None:
    """`\\d` is meaningful in the source being written; dropping it ships a
    silently different regex. Only `\\` before whitespace is a continuation."""
    recovered = json.loads(repair_json_text('{"content": "const re = /\\d+/;"}'))
    assert recovered["content"] == "const re = /\\d+/;"


def test_repair_turns_a_line_continuation_into_a_newline() -> None:
    recovered = json.loads(repair_json_text('{"content": "line one,\\\nline two"}'))
    assert recovered["content"] == "line one,\nline two"


def test_repair_escapes_a_raw_newline_inside_a_string() -> None:
    recovered = json.loads(repair_json_text('{"content": "line one\nline two"}'))
    assert recovered["content"] == "line one\nline two"


def test_span_scanner_offers_more_than_the_first_brace() -> None:
    spans = balanced_object_spans('prefix {bad} middle {"ok": 1} suffix')
    assert "{bad}" in spans and '{"ok": 1}' in spans
