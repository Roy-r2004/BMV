from __future__ import annotations

import pytest

from app.application.runtime_validation.build import (
    _command_failure_code,
    _first_command_error_location,
)
from app.application.runtime_validation.service import _runtime_failure_code
from app.domain.schemas.runtime_validation import CommandResult


def _command(
    name: str,
    message: str = "",
    *,
    timed_out: bool = False,
) -> CommandResult:
    return CommandResult(
        command_name=name,
        argv=("node", name),
        exit_code=1,
        timed_out=timed_out,
        duration_ms=1,
        stdout_sha256="0" * 64,
        stderr_sha256="0" * 64,
        stderr_summary=message,
    )


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (_command("typescript_build", timed_out=True), "runtime_timeout"),
        (
            _command("typescript_build", "error TS2307: Cannot find module 'x'"),
            "import_resolution_failed",
        ),
        (
            _command("typescript_build", "error TS2305: no exported member 'x'"),
            "export_symbol_missing",
        ),
        (
            _command("typescript_build", "error TS2322: type mismatch"),
            "typescript_compile_failed",
        ),
        (_command("vite_build", "build failed"), "vite_build_failed"),
    ],
)
def test_build_failure_code_is_precise(
    command: CommandResult,
    expected: str,
) -> None:
    assert _command_failure_code(command) == expected


def test_request31_first_typescript_error_location_is_preserved() -> None:
    command = _command(
        "typescript_build",
        "src/App.tsx(1,41): error TS2307: Cannot find module "
        "'react-router-dom'",
    )
    assert _command_failure_code(command) == "import_resolution_failed"
    assert _first_command_error_location(command) == "src/App.tsx:1:41"


@pytest.mark.parametrize(
    ("diagnostic", "expected"),
    [
        ("TimeoutError: exceeded 30 seconds", "runtime_timeout"),
        ("BrowserType.launch: executable doesn't exist", "browser_launch_failed"),
        ("preview server exited before readiness", "preview_server_failed"),
        ("screenshot capture failed", "screenshot_failed"),
        ("accessibility gate failed", "accessibility_failed"),
        ("required interaction action failed", "required_interaction_failed"),
        ("required element marker missing", "required_element_missing"),
        ("requestfailed: net::ERR_CONNECTION_REFUSED", "runtime_network_failure"),
        ("console error: uncaught TypeError", "runtime_console_error"),
        ("page.goto: navigation failed", "browser_navigation_failed"),
        ("unexpected runtime exception", "runtime_unhandled_exception"),
    ],
)
def test_runtime_failure_code_is_precise(
    diagnostic: str,
    expected: str,
) -> None:
    assert _runtime_failure_code((diagnostic,)) == expected
