"""`vite build` does not typecheck, so prop-contract violations shipped silently.

Preview app 36 was marked "ready" with 50+ TypeScript errors: CredentialStrip
was handed `{label, value}` where it declares `{title, detail}`, so four empty
white cards rendered under a real heading. The compiler had that answer the
whole time and nobody asked it.

Coverage split:
  - `parse_tsc_output` / ranking / formatting / declaration lookup are tested
    against VERBATIM `tsc -b --pretty false` output captured from app 36.
  - `typecheck_workspace` is tested with a stubbed `subprocess.run` (no node in
    the test image), including the compiler-failure -> "unavailable" path.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app import typecheck as typecheck_module
from app.application.preview_app.typecheck import (
    TypecheckReport,
    collect_type_declarations,
    format_diagnostics,
    parse_tsc_output,
    rank_diagnostics,
    read_typecheck_record,
    record_typecheck_report,
    referenced_type_names,
    typecheck_workspace,
)


# Verbatim output of `./node_modules/.bin/tsc -b --pretty false` inside
# /app/data/preview-apps/36 (74 lines total; this is the head of it).
APP36_TSC_OUTPUT = (
    "src/data/mock.ts(212,3): error TS1117: An object literal cannot have multiple properties with the same name.\n"
    "src/data/mock.ts(384,24): error TS2339: Property 'artwork1' does not exist on type "
    "'{ hero: string; hero2: string; card1: string; card2: string; card3: string; ambient: string; }'.\n"
    "src/pages/AboutPage.tsx(16,85): error TS2322: Type '{ label: string; value: string; }[]' is not "
    "assignable to type 'CredentialStripItem[]'.\n"
    "  Type '{ label: string; value: string; }' is missing the following properties from type "
    "'CredentialStripItem': title, detail\n"
    "src/pages/AboutPage.tsx(76,106): error TS2322: Type '{ children: (string | Element)[]; variant: "
    '"outline"; size: "default"; href: string; target: string; rel: string; className: string; }\' is not '
    "assignable to type 'IntrinsicAttributes & ButtonProps'.\n"
    "  Property 'target' does not exist on type 'IntrinsicAttributes & ButtonProps'.\n"
    "src/pages/admin/AdminDashboardPage.tsx(9,21): error TS7006: Parameter 's' implicitly has an 'any' type.\n"
)


def test_parses_file_line_column_code_and_message() -> None:
    diagnostics = parse_tsc_output(APP36_TSC_OUTPUT)

    assert len(diagnostics) == 5
    credential = next(d for d in diagnostics if d.line == 16)
    assert credential.file == "src/pages/AboutPage.tsx"
    assert credential.column == 85
    assert credential.code == "TS2322"
    assert credential.message.startswith("Type '{ label: string; value: string; }[]' is not assignable")
    # The continuation line names the fields the model must supply.
    assert credential.detail and "title, detail" in credential.detail[0]
    assert "src/pages/AboutPage.tsx(16,85): error TS2322" in credential.as_text()


def test_duplicate_key_and_missing_property_are_kept_separately() -> None:
    diagnostics = parse_tsc_output(APP36_TSC_OUTPUT)

    codes = {(d.file, d.line): d.code for d in diagnostics}
    assert codes[("src/data/mock.ts", 212)] == "TS1117"
    assert codes[("src/data/mock.ts", 384)] == "TS2339"
    assert codes[("src/pages/admin/AdminDashboardPage.tsx", 9)] == "TS7006"


def test_ranking_puts_pages_first_and_keeps_each_file_together() -> None:
    ranked = rank_diagnostics(parse_tsc_output(APP36_TSC_OUTPUT))

    files = [d.file for d in ranked]
    # Pages are what the customer looks at; the fix agent rewrites whole files,
    # so each file's diagnostics stay contiguous.
    assert files[0].startswith("src/pages/")
    assert files[-1] == "src/data/mock.ts"
    assert files == sorted(files, key=files.index)
    # mock.ts duplicate key beats its own cascade of missing-property errors.
    mock_codes = [d.code for d in ranked if d.file == "src/data/mock.ts"]
    assert mock_codes[0] == "TS1117"


def test_shape_errors_outrank_implicit_any_within_a_file() -> None:
    output = (
        "src/pages/HomePage.tsx(9,21): error TS7006: Parameter 's' implicitly has an 'any' type.\n"
        "src/pages/HomePage.tsx(15,85): error TS2322: Type '{ label: string; }[]' is not assignable "
        "to type 'CredentialStripItem[]'.\n"
    )

    ranked = rank_diagnostics(parse_tsc_output(output))

    assert [d.code for d in ranked] == ["TS2322", "TS7006"]


def test_format_groups_by_file_and_keeps_continuation_lines() -> None:
    report = TypecheckReport(
        status="errors", diagnostics=tuple(rank_diagnostics(parse_tsc_output(APP36_TSC_OUTPUT)))
    )
    text = format_diagnostics(report)

    assert "--- src/pages/AboutPage.tsx ---" in text
    assert "--- src/data/mock.ts ---" in text
    assert "missing the following properties from type 'CredentialStripItem': title, detail" in text


def test_referenced_type_names_finds_the_violated_contracts() -> None:
    names = referenced_type_names(tuple(parse_tsc_output(APP36_TSC_OUTPUT)))

    assert "CredentialStripItem" in names
    assert "ButtonProps" in names


def test_collect_type_declarations_gives_the_violated_contract(tmp_path: Path) -> None:
    ui = tmp_path / "src" / "ui" / "public"
    ui.mkdir(parents=True)
    (ui / "CredentialStrip.tsx").write_text(
        "export interface CredentialStripItem {\n"
        "  title: string;\n"
        "  detail: string;\n"
        "}\n\n"
        "export function CredentialStrip() { return null }\n",
        encoding="utf-8",
    )
    diagnostics = tuple(parse_tsc_output(APP36_TSC_OUTPUT))

    declarations = collect_type_declarations(tmp_path, diagnostics)

    # The model invents {label, value} because it is never shown the contract.
    assert "CredentialStripItem" in declarations
    assert "title: string" in declarations
    assert "detail: string" in declarations


def test_collect_type_declarations_falls_back_to_workspace_sources(tmp_path: Path) -> None:
    data = tmp_path / "src" / "data"
    data.mkdir(parents=True)
    (data / "mock.ts").write_text(
        "export interface GalleryRowItem {\n  slug: string;\n  price: number;\n}\n",
        encoding="utf-8",
    )
    diagnostics = tuple(
        parse_tsc_output(
            "src/pages/WorksPage.tsx(20,7): error TS2322: Type '{ id: string; }[]' is not "
            "assignable to type 'GalleryRowItem[]'.\n"
        )
    )

    declarations = collect_type_declarations(tmp_path, diagnostics)

    # No such type in the template kit — the workspace source is the only source.
    assert "src/data/mock.ts" in declarations
    assert "export interface GalleryRowItem {" in declarations


def test_kit_shapes_degrade_when_the_catalogue_seam_is_absent(tmp_path: Path, monkeypatch) -> None:
    from app.application import ui_catalogue

    monkeypatch.delattr(ui_catalogue, "ui_type_shape", raising=True)
    ui = tmp_path / "src" / "ui" / "public"
    ui.mkdir(parents=True)
    (ui / "CredentialStrip.tsx").write_text(
        "export interface CredentialStripItem { title: string; detail: string; }\n", encoding="utf-8"
    )

    declarations = collect_type_declarations(tmp_path, tuple(parse_tsc_output(APP36_TSC_OUTPUT)))

    assert "export interface CredentialStripItem { title: string; detail: string; }" in declarations


class _StubCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _workspace_with_project(tmp_path: Path) -> Path:
    (tmp_path / "tsconfig.app.json").write_text("{}", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text("export default function App() { return null }", encoding="utf-8")
    binary = tmp_path / "node_modules" / ".bin"
    binary.mkdir(parents=True)
    (binary / "tsc").write_text("#!/bin/sh\n", encoding="utf-8")
    return tmp_path


def test_workspace_errors_are_structured(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace_with_project(tmp_path)
    monkeypatch.setattr(
        typecheck_module.subprocess,
        "run",
        lambda *a, **k: _StubCompletedProcess(2, stdout=APP36_TSC_OUTPUT),
    )

    report = typecheck_workspace(workspace, use_cache=False)

    assert report.status == "errors"
    assert report.error_count == 5
    assert report.available and not report.clean
    assert "src/pages/AboutPage.tsx" in report.files


def test_clean_workspace_is_clean_not_unavailable(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace_with_project(tmp_path)
    monkeypatch.setattr(
        typecheck_module.subprocess, "run", lambda *a, **k: _StubCompletedProcess(0)
    )

    report = typecheck_workspace(workspace, use_cache=False)

    assert report.status == "clean"
    assert report.error_count == 0


def test_compiler_crash_is_unavailable_not_clean(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace_with_project(tmp_path)

    def _boom(*_args, **_kwargs):
        raise OSError("Exec format error")

    monkeypatch.setattr(typecheck_module.subprocess, "run", _boom)

    report = typecheck_workspace(workspace, use_cache=False)

    assert report.status == "unavailable"
    assert not report.available
    assert not report.clean
    assert "Exec format error" in report.reason


def test_nonzero_exit_without_diagnostics_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace_with_project(tmp_path)
    monkeypatch.setattr(
        typecheck_module.subprocess,
        "run",
        lambda *a, **k: _StubCompletedProcess(1, stderr="node: bad option: --incremental"),
    )

    report = typecheck_workspace(workspace, use_cache=False)

    assert report.status == "unavailable"
    assert "bad option" in report.reason


def test_timeout_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace_with_project(tmp_path)

    def _timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="tsc", timeout=5)

    monkeypatch.setattr(typecheck_module.subprocess, "run", _timeout)

    report = typecheck_workspace(workspace, timeout=5, use_cache=False)

    assert report.status == "unavailable"
    assert "timed out" in report.reason


def test_missing_compiler_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "src").mkdir()
    monkeypatch.setattr(typecheck_module, "_compiler_command", lambda _workspace: None)

    report = typecheck_workspace(tmp_path, use_cache=False)

    assert report.status == "unavailable"
    assert "compiler not found" in report.reason


def test_config_only_diagnostics_are_unavailable_not_errors(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace_with_project(tmp_path)
    monkeypatch.setattr(
        typecheck_module.subprocess,
        "run",
        lambda *a, **k: _StubCompletedProcess(
            2, stdout="error TS5083: Cannot read file '/app/tsconfig.app.json'.\n"
        ),
    )

    # A tsconfig that cannot be read says nothing about the generated code and
    # the fix agent cannot act on it — that is a broken check, not a clean app.
    report = typecheck_workspace(workspace, use_cache=False)

    assert report.status == "unavailable"
    assert "TS5083" in report.reason


def test_repeat_call_reuses_report_for_untouched_sources(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace_with_project(tmp_path)
    calls: list[int] = []

    def _run(*_args, **_kwargs):
        calls.append(1)
        return _StubCompletedProcess(2, stdout=APP36_TSC_OUTPUT)

    monkeypatch.setattr(typecheck_module.subprocess, "run", _run)
    typecheck_module._report_cache.clear()

    first = typecheck_workspace(workspace)
    second = typecheck_workspace(workspace)
    assert len(calls) == 1
    assert second is first

    (workspace / "src" / "App.tsx").write_text("export default function App() { return <div /> }", encoding="utf-8")
    typecheck_workspace(workspace)
    assert len(calls) == 2


def test_uses_project_mode_so_no_shared_buildinfo_race(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace_with_project(tmp_path)
    seen: dict[str, list[str]] = {}

    def _run(args, **_kwargs):
        seen["args"] = list(args)
        return _StubCompletedProcess(0)

    monkeypatch.setattr(typecheck_module.subprocess, "run", _run)

    typecheck_workspace(workspace, use_cache=False)

    assert "tsconfig.app.json" in seen["args"]
    assert "--noEmit" in seen["args"]
    # node_modules is a symlink into a SHARED install whose tsBuildInfoFile lives
    # inside it — build mode would make concurrent generations race on one cache.
    assert "-b" not in seen["args"]
    assert seen["args"][seen["args"].index("--incremental") + 1] == "false"


_FIXTURE_TSCONFIG = """{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true
  },
  "include": ["src"]
}
"""

_FIXTURE_MOCK = """export interface CredentialStripItem {
  title: string;
  detail: string;
}

export const credentials: CredentialStripItem[] = [
  { label: 'Since 2009', value: '15 years' },
];
"""


def test_real_compiler_reports_the_wrong_item_shape(tmp_path: Path) -> None:
    """End-to-end against the actual tsc binary (skipped where none exists)."""
    if typecheck_module._compiler_command(tmp_path) is None:
        import pytest

        pytest.skip("no TypeScript compiler available in this environment")
    (tmp_path / "tsconfig.app.json").write_text(_FIXTURE_TSCONFIG, encoding="utf-8")
    src = tmp_path / "src" / "data"
    src.mkdir(parents=True)
    (src / "mock.ts").write_text(_FIXTURE_MOCK, encoding="utf-8")

    report = typecheck_workspace(tmp_path, use_cache=False)

    assert report.status == "errors"
    diagnostic = report.diagnostics[0]
    assert diagnostic.file == "src/data/mock.ts"
    assert diagnostic.line == 7
    assert diagnostic.code in {"TS2322", "TS2353", "TS2739", "TS2740"}
    assert "label" in diagnostic.message or "title" in diagnostic.message
    # Same run, no re-invocation, no .tsbuildinfo left behind in the workspace.
    assert not list(tmp_path.rglob("*.tsbuildinfo"))


def test_real_compiler_reports_clean_when_shapes_match(tmp_path: Path) -> None:
    if typecheck_module._compiler_command(tmp_path) is None:
        import pytest

        pytest.skip("no TypeScript compiler available in this environment")
    (tmp_path / "tsconfig.app.json").write_text(_FIXTURE_TSCONFIG, encoding="utf-8")
    src = tmp_path / "src" / "data"
    src.mkdir(parents=True)
    (src / "mock.ts").write_text(
        _FIXTURE_MOCK.replace("label: 'Since 2009', value: '15 years'", "title: 'Since 2009', detail: '15 years'"),
        encoding="utf-8",
    )

    report = typecheck_workspace(tmp_path, use_cache=False)

    assert report.status == "clean"
    assert report.diagnostics == ()


def test_record_is_readable_and_separates_unavailable_from_clean(tmp_path: Path) -> None:
    errors = TypecheckReport(
        status="errors", diagnostics=tuple(parse_tsc_output(APP36_TSC_OUTPUT))
    )
    record_typecheck_report(tmp_path, errors, rounds=2)
    recorded = read_typecheck_record(tmp_path)

    assert recorded["status"] == "errors"
    assert recorded["error_count"] == 5
    assert recorded["repair_rounds"] == 2
    assert recorded["files"]["src/pages/AboutPage.tsx"] == 2

    record_typecheck_report(tmp_path, TypecheckReport(status="unavailable", reason="no node"))
    assert read_typecheck_record(tmp_path)["status"] == "unavailable"
    assert read_typecheck_record(tmp_path)["error_count"] == 0
