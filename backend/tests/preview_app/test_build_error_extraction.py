"""The fix agent is only as good as the error text it receives.

`extract_build_errors` used to filter the build log line by line on a keyword
list. Rolldown puts the message and the `file:line:col` *inside* a box-drawing
block whose lines contain none of those keywords, so the entire diagnostic was
dropped and the fix agent received only bundler internals. Request 34 spent all
six fix attempts on a one-line JSX error it was never shown.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.build import extract_build_errors


# Verbatim `npx vite build` output from request 34, ANSI escapes included.
REQ34_JSX_FAILURE = (
    "vite v8.1.3 building client environment for production...\n"
    "\x1b[2Ktransforming...✓ 3268 modules transformed.\n"
    "\x1b[31m✗\x1b[0m Build failed in 202ms\n"
    "error during build:\n"
    "Build failed with 1 error:\n"
    "\n"
    "\x1b[31m[builtin:vite-transform] \x1b[0mAdjacent JSX elements must be "
    "wrapped in an enclosing tag.\n"
    "    \x1b[38;5;246m╭─[\x1b[0m src/pages/owner/LoginPage.tsx:54:5 "
    "\x1b[38;5;246m]\x1b[0m\n"
    "    │\n"
    " 54 │     <PublicShell\n"
    "    │     ┬  \n"
    "    │     ╰── \n"
    "    │ \n"
    "    │ Help: Did you want a JSX fragment `<>...</>`?\n"
    "────╯\n"
    "    at aggregateBindingErrorsIntoJsError "
    "(file:///app/data/preview-apps/_shared_npm/58765f2ed43ba6d8/node_modules/"
    "rolldown/dist/shared/error-BlQ0-ek7.mjs:48:18)\n"
    "    at unwrapBindingResult "
    "(file:///app/data/preview-apps/_shared_npm/58765f2ed43ba6d8/node_modules/"
    "rolldown/dist/shared/error-BlQ0-ek7.mjs:18:128)\n"
    "    at async buildEnvironment "
    "(file:///app/data/preview-apps/_shared_npm/58765f2ed43ba6d8/node_modules/"
    "vite/dist/node/chunks/node.js:32622:66)\n"
    "  errors: [Getter/Setter]\n"
    "}\n"
)


def test_rolldown_diagnostic_survives_extraction() -> None:
    extracted = extract_build_errors(REQ34_JSX_FAILURE)

    # The three things the fix agent cannot work without.
    assert "src/pages/owner/LoginPage.tsx:54:5" in extracted
    assert "Adjacent JSX elements must be wrapped in an enclosing tag." in extracted
    assert "<PublicShell" in extracted
    # The bundler's own hint is worth forwarding too.
    assert "Did you want a JSX fragment" in extracted


def test_bundler_stack_frames_are_dropped() -> None:
    """Stack frames match the keyword filter but are never actionable.

    `error-BlQ0-ek7.mjs` matches "error"; `node.js:32622:66` matches the
    file-location pattern. Both must lose to the stack-frame check, or a dozen
    frames crowd out the real diagnostic.
    """

    extracted = extract_build_errors(REQ34_JSX_FAILURE)

    assert "aggregateBindingErrorsIntoJsError" not in extracted
    assert "unwrapBindingResult" not in extracted
    assert "node_modules/rolldown" not in extracted
    assert "[Getter/Setter]" not in extracted
    assert not any(line.lstrip().startswith("at ") for line in extracted.splitlines())


def test_ansi_escapes_are_stripped() -> None:
    """Colour escapes are pure overhead in a prompt and break substring matching."""

    extracted = extract_build_errors(REQ34_JSX_FAILURE)
    assert "\x1b[" not in extracted


def test_extraction_is_mostly_signal() -> None:
    """The old implementation returned bundler noise; keep the result tight."""

    extracted = extract_build_errors(REQ34_JSX_FAILURE)
    assert len(extracted) < 600, f"extraction bloated to {len(extracted)} chars:\n{extracted}"


def test_tsc_style_errors_still_extracted() -> None:
    """The plain `file(line,col): error TSxxxx` shape must keep working."""

    log = (
        "> tsc -b\n"
        "src/pages/HomePage.tsx(12,7): error TS2322: Type 'number' is not "
        "assignable to type 'string'.\n"
        "src/App.tsx(3,1): error TS2307: Cannot find module './Missing'.\n"
    )
    extracted = extract_build_errors(log)

    assert "src/pages/HomePage.tsx(12,7)" in extracted
    assert "TS2322" in extracted
    assert "Cannot find module './Missing'." in extracted


def test_log_without_recognisable_errors_falls_back_to_tail() -> None:
    log = "\n".join(f"line {i}" for i in range(200))
    extracted = extract_build_errors(log, max_chars=40)

    assert extracted == log[-40:]


def test_output_is_capped_and_keeps_the_first_diagnostic() -> None:
    """When truncating, keep the head — the first error is the one to fix."""

    log = REQ34_JSX_FAILURE + "\n".join(
        f"src/pages/Extra{i}.tsx(1,1): error TS9999: filler" for i in range(400)
    )
    extracted = extract_build_errors(log, max_chars=500)

    assert len(extracted) <= 500 + len("\n… (truncated)")
    assert "src/pages/owner/LoginPage.tsx:54:5" in extracted
    assert extracted.endswith("… (truncated)")
