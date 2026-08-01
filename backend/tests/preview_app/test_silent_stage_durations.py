"""Two stages used to finish without ever saying how long they took.

`typecheck.py` built a `TypecheckReport` carrying `duration_ms` on every branch
and logged none of it, so the only branch that matters — the one with errors,
which is also the one that hands the fix agent its work — was invisible in the
run log. `build.py` timed nothing at all, which is how `build_phase.py:183`'s
"~20 s" comment survived being 40× stale.

The wall-clock ledger had to be reconstructed from timestamps around these
stages. These tests pin that it no longer has to be.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

from app.application.preview_app import build as build_mod  # noqa: E402
from app.application.preview_app import typecheck as typecheck_mod  # noqa: E402


class _Completed:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


_TSC_ERRORS = (
    "src/pages/HomePage.tsx(12,5): error TS2353: Object literal may only "
    "specify known properties.\n"
)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    return tmp_path


def _run_typecheck(monkeypatch, workspace: Path, output: str, returncode: int):
    monkeypatch.setattr(typecheck_mod, "_compiler_command", lambda _ws: ["tsc"])
    monkeypatch.setattr(typecheck_mod, "_project_args", lambda _ws: ())
    monkeypatch.setattr(
        typecheck_mod.subprocess,
        "run",
        lambda *_a, **_k: _Completed(returncode=returncode, stdout=output),
    )
    return typecheck_mod.typecheck_workspace(workspace, use_cache=False)


def test_a_typecheck_that_found_errors_says_how_long_it_took(
    monkeypatch, workspace, caplog
) -> None:
    """`typecheck.py:494-499` — the branch the roadmap names."""

    with caplog.at_level(logging.INFO):
        report = _run_typecheck(monkeypatch, workspace, _TSC_ERRORS, 2)

    assert report.status == "errors"
    lines = [r.getMessage() for r in caplog.records if "typecheck finished" in r.getMessage()]
    assert lines, "the errors branch must record its duration"
    assert "status=errors" in lines[0]
    assert "errors=1" in lines[0]


def test_a_clean_typecheck_says_how_long_it_took(monkeypatch, workspace, caplog) -> None:
    with caplog.at_level(logging.INFO):
        report = _run_typecheck(monkeypatch, workspace, "", 0)

    assert report.status == "clean"
    assert any(
        "typecheck finished" in r.getMessage() and "status=clean" in r.getMessage()
        for r in caplog.records
    )


def test_a_broken_compiler_run_is_reported_as_unavailable_with_its_duration(
    monkeypatch, workspace, caplog
) -> None:
    """Non-zero exit with nothing parseable must never read as `clean`, and the
    time it burned is still time the deadline has to account for."""

    with caplog.at_level(logging.WARNING):
        report = _run_typecheck(monkeypatch, workspace, "tsconfig.json not found", 1)

    assert report.status == "unavailable"
    assert any(
        "typecheck finished" in r.getMessage() and "status=unavailable" in r.getMessage()
        for r in caplog.records
    )


class _Renderer:
    def render(self, _template: str, **_kwargs) -> str:
        return "base: '/preview/1/'"


def test_the_build_records_both_the_npm_attach_and_the_vite_build(
    monkeypatch, tmp_path, caplog
) -> None:
    """`build.py:83` — npm attach and vite each finish silently today."""

    workspace = tmp_path / "ws"
    (workspace / "node_modules" / "vite").mkdir(parents=True)
    (workspace / "node_modules" / "vite" / "package.json").write_text("{}")
    (workspace / "dist").mkdir()
    (workspace / "dist" / "index.html").write_text("<html></html>")

    monkeypatch.setattr(
        build_mod, "attach_shared_node_modules", lambda _ws, timeout=0: "attached"
    )
    monkeypatch.setattr(
        build_mod.subprocess, "run", lambda *_a, **_k: _Completed(returncode=0)
    )

    with caplog.at_level(logging.INFO):
        ok, _log = build_mod.run_build(workspace, "/preview/1/", _Renderer())

    messages = [record.getMessage() for record in caplog.records]
    assert ok is True
    assert any("npm attach finished in" in m for m in messages)
    assert any("vite build finished in" in m for m in messages)


def test_a_failed_vite_build_still_records_its_duration(
    monkeypatch, tmp_path, caplog
) -> None:
    """The expensive case. A build that fails is the one whose cost the
    deadline most needs to know about."""

    workspace = tmp_path / "ws"
    (workspace / "node_modules" / "vite").mkdir(parents=True)
    (workspace / "node_modules" / "vite" / "package.json").write_text("{}")

    monkeypatch.setattr(
        build_mod, "attach_shared_node_modules", lambda _ws, timeout=0: "attached"
    )
    monkeypatch.setattr(
        build_mod.subprocess,
        "run",
        lambda *_a, **_k: _Completed(returncode=1, stderr="error during build:"),
    )
    monkeypatch.setattr(build_mod, "dump_build_failure", lambda *_a, **_k: None)

    with caplog.at_level(logging.INFO):
        ok, _log = build_mod.run_build(workspace, "/preview/1/", _Renderer())

    assert ok is False
    assert any(
        "vite build finished in" in record.getMessage() and "exit=1" in record.getMessage()
        for record in caplog.records
    )


def test_the_local_npm_fallback_records_its_duration(
    monkeypatch, tmp_path, caplog
) -> None:
    workspace = tmp_path / "ws"
    (workspace / "node_modules" / "vite").mkdir(parents=True)
    (workspace / "node_modules" / "vite" / "package.json").write_text("{}")
    (workspace / "dist").mkdir()
    (workspace / "dist" / "index.html").write_text("<html></html>")

    def _attach_fails(_ws, timeout=0):
        raise RuntimeError("shared npm unavailable")

    monkeypatch.setattr(build_mod, "attach_shared_node_modules", _attach_fails)
    monkeypatch.setattr(
        build_mod.subprocess, "run", lambda *_a, **_k: _Completed(returncode=0)
    )

    with caplog.at_level(logging.INFO):
        build_mod.run_build(workspace, "/preview/1/", _Renderer())

    assert any(
        "npm install (local fallback) finished in" in record.getMessage()
        for record in caplog.records
    )


def test_a_typecheck_that_times_out_reports_a_duration_on_the_report(
    monkeypatch, workspace
) -> None:
    """The timeout branch already carried the number; nothing here regresses it."""

    monkeypatch.setattr(typecheck_mod, "_compiler_command", lambda _ws: ["tsc"])
    monkeypatch.setattr(typecheck_mod, "_project_args", lambda _ws: ())

    def _times_out(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="tsc", timeout=1)

    monkeypatch.setattr(typecheck_mod.subprocess, "run", _times_out)

    report = typecheck_mod.typecheck_workspace(workspace, use_cache=False)

    assert report.status == "unavailable"
    assert report.duration_ms is not None
