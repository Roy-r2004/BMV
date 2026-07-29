"""Slot-fill rejection must retry with reason-specific guidance and log it."""
from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app import codegen
from app.application.preview_app.catalogue_contract import minimal_catalogue_page_scaffold
from app.application.preview_app.codegen.generate import _MAX_SLOT_FILL_ATTEMPTS
from app.application.preview_app.fallback import clear_stubbed_paths, consume_stubbed_paths
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
