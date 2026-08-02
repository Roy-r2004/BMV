"""Slot-fill rejection must retry with reason-specific guidance and log it."""
from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app import codegen
from app.application.preview_app.catalogue_contract import (
    blocking_contract_errors,
    enforce_catalogue_page_contract,
    minimal_catalogue_page_scaffold,
    validate_catalogue_page_content,
)
from app.application.preview_app.codegen.generate import _MAX_SLOT_FILL_ATTEMPTS
from app.application.preview_app.fallback import clear_stubbed_paths, consume_stubbed_paths
from app.application.services.ai_context import (
    UNUSABLE_REJECTED,
    ai_call,
    current_ai_call,
)
from app.application.services.request_deadline import (
    DEFAULT_ASK_CEILING_SECONDS,
    RESERVE_SECONDS,
    request_deadline_scope,
)
from app.infrastructure.templating.renderer import JinjaTemplateRenderer

TEMPLATES_DIR = REPO_ROOT / "backend" / "app" / "templates"
PAGE = "src/pages/HomePage.tsx"
SCAFFOLD_MARKER = "deterministic catalogue contract scaffold"
CODEGEN_LOGGER = "bmv.Codegen"

_MISMATCHED_TAGS = (
    "import { PublicShell } from '@/ui';\n"
    "export default function HomePage() { return <div><span></div></span>; }\n"
)
_NO_EXPORT = (
    "import { PublicShell } from '@/ui';\n"
    "function HomePage() { return <div>Complete but not exported.</div>; }\n"
)


class _SequenceAI:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.prompts: list[str] = []

    def ask_chat(self, _model, messages, **_kwargs):
        self.calls += 1
        self.prompts.append(messages[-1]["content"])
        return self.responses.pop(0) if self.responses else ""

    def ask_vision(self, _model, prompt, _image_path):
        self.calls += 1
        self.prompts.append(prompt)
        return self.responses.pop(0) if self.responses else ""


def _route() -> dict:
    return {
        "path": "/",
        "page_id": "home",
        "role_id": "customer",
        "component_file": PAGE,
        "surface": "public",
        "skeleton_id": "public-home",
        "section_slots": [
            "hero",
            "features",
            "showcase",
            "process",
            "testimonials",
            "cta",
            "footer",
        ],
    }


def _accepted_fill(sentinel: str) -> str:
    return minimal_catalogue_page_scaffold(PAGE, _route(), brand_name=sentinel).replace(
        f"// {SCAFFOLD_MARKER}", "// AI-authored business page"
    )


def _truncated_fill() -> str:
    full = _accepted_fill("Truncated Sentinel")
    return full[: full.index("  return (")]


def _generate(ai: _SequenceAI, workspace: Path) -> str:
    return codegen.generate_file(
        workspace,
        {"path": PAGE, "kind": "page", "instructions": "home"},
        "business context",
        {"routes": [_route()]},
        {"roles": []},
        {},
        {},
        ai,
        JinjaTemplateRenderer(TEMPLATES_DIR),
    )


def _rejection_logs(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if "slot_fill rejected" in record.getMessage()
    ]


def test_truncated_slot_fill_retries_and_logs_reason(caplog) -> None:
    caplog.set_level(logging.WARNING, logger=CODEGEN_LOGGER)
    ai = _SequenceAI([_truncated_fill(), _accepted_fill("RETRY_ACCEPTED_SENTINEL")])
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        content = _generate(ai, workspace)
        assert ai.calls == 2
        assert "RETRY_ACCEPTED_SENTINEL" in content
        assert SCAFFOLD_MARKER not in content
        assert consume_stubbed_paths(workspace) == []
    logs = _rejection_logs(caplog)
    assert len(logs) == 1
    assert PAGE in logs[0]
    assert "truncated" in logs[0]
    assert "retrying" in logs[0]
    assert "Previous answer failed (truncated)" in ai.prompts[-1]


def test_missing_export_default_slot_fill_retries_with_export_guidance(caplog) -> None:
    caplog.set_level(logging.WARNING, logger=CODEGEN_LOGGER)
    ai = _SequenceAI([_NO_EXPORT, _accepted_fill("EXPORT_RETRY_SENTINEL")])
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        content = _generate(ai, workspace)
        assert ai.calls == 2
        assert "EXPORT_RETRY_SENTINEL" in content
        assert consume_stubbed_paths(workspace) == []
    logs = _rejection_logs(caplog)
    assert len(logs) == 1
    assert PAGE in logs[0]
    assert "missing-export-default" in logs[0]
    retry_prompt = ai.prompts[-1]
    assert "Previous answer failed (missing-export-default)" in retry_prompt
    assert "export default function" in retry_prompt
    assert "truncated" not in retry_prompt.rsplit("IMPORTANT:", 1)[-1]


def test_unparseable_slot_fill_retries_then_keeps_scaffold(caplog) -> None:
    caplog.set_level(logging.WARNING, logger=CODEGEN_LOGGER)
    ai = _SequenceAI(
        [_MISMATCHED_TAGS, _MISMATCHED_TAGS, _accepted_fill("NEVER_REACHED_SENTINEL")]
    )
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        content = _generate(ai, workspace)
        assert ai.calls == _MAX_SLOT_FILL_ATTEMPTS == 2
        assert "NEVER_REACHED_SENTINEL" not in content
        assert SCAFFOLD_MARKER in content
        assert consume_stubbed_paths(workspace) == [PAGE]
    logs = _rejection_logs(caplog)
    assert len(logs) == 2
    assert all("unparseable-tsx" in message for message in logs)
    assert "keeping scaffold" in logs[-1]


def test_empty_slot_fill_answer_is_logged_without_retry(caplog) -> None:
    caplog.set_level(logging.WARNING, logger=CODEGEN_LOGGER)
    ai = _SequenceAI([""])
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        content = _generate(ai, workspace)
        assert ai.calls == 1
        assert SCAFFOLD_MARKER in content
        assert consume_stubbed_paths(workspace) == [PAGE]
    logs = _rejection_logs(caplog)
    assert len(logs) == 1
    assert "empty" in logs[0]
    assert "keeping scaffold" in logs[0]


# --- Contract rejection (roadmap 2.9) ----------------------------------------
#
# Until 2026-08-03 the four cases above were the *whole* rejection vocabulary,
# and none of them fired in practice: across requests 74-79, zero syntactic
# rejections were logged and 26 pages were still discarded — by
# `enforce_catalogue_page_contract`, one call later, with no retry. The retry
# loop existed and had never once run. These tests pin the fifth reason and,
# just as importantly, the two places it must NOT fire.

_CONTRACT_INVALID = (
    "import { PublicShell } from '@/ui';\n"
    "export default function HomePage() { "
    'return <PublicShell brandName="Wrong"><main>complete invalid page</main>'
    "</PublicShell>; }\n"
)


def _architect() -> dict:
    return {"routes": [_route()]}


def _fill_missing_one_slot() -> str:
    """A fill enforce REPAIRS rather than replaces: one slot entry removed.

    Built by cutting a region out of the live scaffold and asserting the cut
    happened, because a decoy built by `.replace()` on a moved anchor is a
    no-op that leaves the "bad" page byte-identical to the good one — the exact
    way three tests in `test_catalogue_contract.py` went quietly vacuous.
    """
    full = _accepted_fill("REPAIRABLE_SENTINEL")
    start = full.index("    process: (")
    end = full.index("    testimonials: (")
    dropped = full[:start] + full[end:]
    assert dropped != full and "    process: (" not in dropped, (
        "the scaffold's slot layout moved — this fixture removes nothing"
    )
    return dropped


def test_the_two_contract_fixtures_still_mean_what_they_say() -> None:
    """Guards the two tests below against their fixtures drifting.

    Both assert on a *difference* between two pages. If the catalogue scaffold
    changes shape and both pages start landing on the same side of enforce, the
    tests keep passing while testing nothing.
    """
    route, architect = _route(), _architect()

    _, replaced = enforce_catalogue_page_contract(
        PAGE, _CONTRACT_INVALID, architect, brand_name="Brand"
    )
    assert replaced, "the contract-invalid fixture is no longer discarded by enforce"

    repairable = _fill_missing_one_slot()
    assert blocking_contract_errors(
        validate_catalogue_page_content(repairable, route)
    ) == ["slot:process"], "the repairable fixture no longer violates the contract"
    _, replaced = enforce_catalogue_page_contract(
        PAGE, repairable, architect, brand_name="Brand"
    )
    assert not replaced, "enforce no longer repairs a single missing slot"


def test_a_contract_invalid_fill_is_re_asked_with_its_validator_errors(caplog) -> None:
    """The 2.9 defect. A page that compiles but lost its face gets one re-ask."""
    caplog.set_level(logging.WARNING, logger=CODEGEN_LOGGER)
    ai = _SequenceAI([_CONTRACT_INVALID, _accepted_fill("CONTRACT_RETRY_SENTINEL")])
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        content = _generate(ai, workspace)
        assert ai.calls == 2, "the contract-invalid page was not re-asked"
        assert "CONTRACT_RETRY_SENTINEL" in content
        assert SCAFFOLD_MARKER not in content
        # The page shipped from the retry, so it is not a stub.
        assert consume_stubbed_paths(workspace) == []

    logs = _rejection_logs(caplog)
    assert len(logs) == 1
    assert "catalogue-contract" in logs[0] and "retrying" in logs[0]
    # Not "try again" — the exact errors, so the second answer can differ from
    # the first for a reason. A generic re-ask reproduces the same violation.
    retry_prompt = ai.prompts[-1]
    assert "CATALOGUE CONTRACT RETRY" in retry_prompt
    for error in ("SkeletonComposer invocation", "slot:hero", "slot:footer"):
        assert error in retry_prompt, f"retry prompt does not name {error}"


def test_a_fill_enforce_can_repair_is_not_re_asked(caplog) -> None:
    """The bound on the fix: re-ask only what would otherwise be thrown away.

    `enforce` back-fills a missing slot deterministically. Re-asking for that
    spends ~50 s of a 540 s budget to arrive at the same file, and doing it on
    every contract error — rather than on enforce's verdict — is how a fix for
    "not enough retries" becomes the reason a run breaches its deadline.
    """
    caplog.set_level(logging.WARNING, logger=CODEGEN_LOGGER)
    ai = _SequenceAI([_fill_missing_one_slot(), _accepted_fill("NEVER_ASKED_SENTINEL")])
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        content = _generate(ai, workspace)
        assert ai.calls == 1, "an ask was spent on something enforce repairs for free"
        assert "NEVER_ASKED_SENTINEL" not in content
        assert "REPAIRABLE_SENTINEL" in content
        assert consume_stubbed_paths(workspace) == []
    assert _rejection_logs(caplog) == []


def test_the_contract_retry_is_skipped_when_the_request_is_out_of_runway(caplog) -> None:
    """Discretionary spend needs runway, and skipping it is on the record.

    A contract retry fires on roughly four pages a run. One ask is bounded by
    the per-ask ceiling and the post-deadline smoke pass needs the reserve, so
    under their sum the re-ask would be taking time from a stage that cannot
    skip. The syntactic retries stay ungated — those fire on already-broken
    files and effectively never happen.
    """
    caplog.set_level(logging.WARNING, logger=CODEGEN_LOGGER)
    ai = _SequenceAI([_CONTRACT_INVALID, _accepted_fill("UNREACHABLE_SENTINEL")])
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        with request_deadline_scope(
            "slotfill-runway",
            total_seconds=DEFAULT_ASK_CEILING_SECONDS + RESERVE_SECONDS - 10.0,
        ) as deadline:
            content = _generate(ai, workspace)
            reasons = [entry["reason"] for entry in deadline.degradations()]
        assert ai.calls == 1, "a re-ask was started with no runway to finish it"
        assert "UNREACHABLE_SENTINEL" not in content
        assert SCAFFOLD_MARKER in content
        assert consume_stubbed_paths(workspace) == [PAGE]

    assert "slot_fill_contract_retry_skipped_low_runway" in reasons, (
        "the skipped retry was silent; a run that could not afford its retries "
        "must not look like a run that had none to make"
    )
    logs = _rejection_logs(caplog)
    assert len(logs) == 1
    assert "catalogue-contract" in logs[0] and "keeping scaffold" in logs[0]


def test_ample_runway_still_allows_the_contract_retry() -> None:
    """The gate reads the clock — it is not 'off whenever a deadline exists'."""
    ai = _SequenceAI([_CONTRACT_INVALID, _accepted_fill("RUNWAY_OK_SENTINEL")])
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        with request_deadline_scope("slotfill-runway-ok", total_seconds=540.0) as deadline:
            content = _generate(ai, workspace)
            reasons = [entry["reason"] for entry in deadline.degradations()]
        assert ai.calls == 2
        assert "RUNWAY_OK_SENTINEL" in content
        assert consume_stubbed_paths(workspace) == []
    assert "slot_fill_contract_retry_skipped_low_runway" not in reasons


class _TelemetrySequenceAI(_SequenceAI):
    """`_SequenceAI` that files a usage row the way a real provider does."""

    def ask_chat(self, model, messages, **kwargs):
        call = current_ai_call()
        if call is not None:
            call.record({"success": True, "usable": True})
        return super().ask_chat(model, messages, **kwargs)


def test_a_contract_rejected_fill_is_filed_as_an_unusable_call() -> None:
    """A rejected ask cost the same wall clock as one that shipped.

    The census is how Phase 1 answers "where did the 540 seconds go", and until
    the contract rejection existed it could only see the four syntactic ones —
    which never fire. A run whose slot-fills were half discarded and a run whose
    slot-fills all landed would have filed identical telemetry.
    """
    captured: list[dict] = []
    ai = _TelemetrySequenceAI(
        [_CONTRACT_INVALID, _accepted_fill("TELEMETRY_SENTINEL")]
    )
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        with ai_call("test-root", flush=captured.extend):
            _generate(ai, workspace)

    slot_fill = [row for row in captured if row.get("writer") == "slot_fill"]
    assert [row["attempt"] for row in slot_fill] == [1, 2]
    assert slot_fill[0]["usable"] is False
    assert slot_fill[0]["unusable_reason"] == UNUSABLE_REJECTED
    assert slot_fill[1]["usable"] is True


def test_both_attempts_contract_invalid_keeps_the_scaffold(caplog) -> None:
    """Two bad answers cost two asks and no more, and the page says it is a stub."""
    caplog.set_level(logging.WARNING, logger=CODEGEN_LOGGER)
    ai = _SequenceAI(
        [_CONTRACT_INVALID, _CONTRACT_INVALID, _accepted_fill("NEVER_REACHED_SENTINEL")]
    )
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        content = _generate(ai, workspace)
        assert ai.calls == _MAX_SLOT_FILL_ATTEMPTS == 2
        assert "NEVER_REACHED_SENTINEL" not in content
        assert SCAFFOLD_MARKER in content
        assert consume_stubbed_paths(workspace) == [PAGE]
    logs = _rejection_logs(caplog)
    assert len(logs) == 2
    assert all("catalogue-contract" in message for message in logs)
    assert "keeping scaffold" in logs[-1]
