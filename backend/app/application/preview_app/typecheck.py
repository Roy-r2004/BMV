"""Run the TypeScript compiler against a generated workspace.

`vite build` bundles with rolldown/esbuild and never typechecks, so a generated
page can violate every prop contract in `src/ui/` and still ship a green build.
Those violations are not cosmetic: a component handed `{label, value}` where it
declares `{title, detail}` renders empty cards. The kit's exported interfaces
are a complete machine-checkable spec, and `tsc` verifies it in ~2s with no
model call — so it runs on every generation and its diagnostics drive repairs.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.core.config import settings
from app.infrastructure.logging import get_logger
from app.infrastructure.logging.diagnostics import DEBUG_ROOT

tc_log = get_logger("Typecheck")

TypecheckStatus = Literal["clean", "errors", "unavailable"]

# Project mode on tsconfig.app.json (not `tsc -b`) checks the identical file set
# and emits byte-identical diagnostics, but writes no .tsbuildinfo: workspaces
# symlink a SHARED node_modules, and tsconfig.app.json points tsBuildInfoFile
# inside it, so build mode would make concurrent generations race on one cache.
_APP_PROJECT = "tsconfig.app.json"
_PROJECT_ARGS = ("--noEmit", "--incremental", "false", "--pretty", "false")
_BUILD_ARGS = ("-b", "--force", "--pretty", "false")
_DEFAULT_TIMEOUT = 180
_MAX_CACHED_REPORTS = 8
_RECORD_CATEGORY = "typecheck"
RECORD_FILENAME = "summary.json"

# src/pages/HomePage.tsx(15,85): error TS2322: Type '...' is not assignable ...
_DIAGNOSTIC_RE = re.compile(
    r"^(?P<file>[^(\s][^(]*?)\((?P<line>\d+),(?P<column>\d+)\):\s+error\s+(?P<code>TS\d+):\s+(?P<message>.*)$"
)
# error TS5083: Cannot read file '/app/tsconfig.app.json'. — no source location.
_GLOBAL_DIAGNOSTIC_RE = re.compile(r"^error\s+(?P<code>TS\d+):\s+(?P<message>.*)$")

# Shape/contract violations first: they are what render blank components. Then
# everything else, with implicit-any and unused-symbol noise last.
_CODE_PRIORITY = {
    "TS1117": 0,  # duplicate object key — silently drops data
    "TS2322": 1,  # not assignable (wrong item/prop shape)
    "TS2741": 1,  # missing required prop
    "TS2739": 1,
    "TS2740": 1,
    "TS2345": 1,
    "TS2353": 2,  # unknown property in object literal
    "TS2339": 2,  # property does not exist (mock.ts image keys)
    "TS2551": 2,
    "TS7006": 8,  # implicit any parameter
    "TS6133": 9,  # declared but never read
}
_DEFAULT_CODE_PRIORITY = 4

_FILE_PRIORITY = (
    ("src/pages/", 0),
    ("src/App.tsx", 1),
    ("src/data/", 2),
    ("src/components/", 3),
)
_DEFAULT_FILE_PRIORITY = 5

_TYPE_NAME_RE = re.compile(r"\b([A-Z][A-Za-z0-9]*(?:Props|Item|Items|Entry|Row|Option|Link|Column|Action|Config))\b")
_DECLARATION_RE = "export (?:interface|type) {name}\\b"
_DECLARATION_SEARCH_DIRS = ("src/ui", "src/components", "src/data")
_MAX_DECLARATIONS = 14
_MAX_DECLARATION_CHARS = 6000


@dataclass(frozen=True)
class TypeDiagnostic:
    """One `tsc` error, with its indented continuation lines attached."""

    file: str
    line: int
    column: int
    code: str
    message: str
    detail: tuple[str, ...] = ()

    @property
    def location(self) -> str:
        if not self.file:
            return "(project)"
        return f"{self.file}({self.line},{self.column})"

    def as_text(self) -> str:
        head = f"{self.location}: error {self.code}: {self.message}"
        if not self.detail:
            return head
        return "\n".join((head, *(f"  {line}" for line in self.detail)))


@dataclass(frozen=True)
class TypecheckReport:
    """Outcome of one typecheck run.

    ``status`` separates the three states that must never be conflated:
    ``clean`` (compiler ran, no errors), ``errors`` (compiler ran, found these),
    ``unavailable`` (compiler could not be run or produced nothing parseable —
    we know nothing about this workspace's type health).
    """

    status: TypecheckStatus
    diagnostics: tuple[TypeDiagnostic, ...] = ()
    reason: str = ""
    duration_ms: int = 0
    command: tuple[str, ...] = field(default=())

    @property
    def available(self) -> bool:
        return self.status != "unavailable"

    @property
    def clean(self) -> bool:
        return self.status == "clean"

    @property
    def error_count(self) -> int:
        return len(self.diagnostics)

    @property
    def files(self) -> tuple[str, ...]:
        seen: list[str] = []
        for diagnostic in self.diagnostics:
            if diagnostic.file and diagnostic.file not in seen:
                seen.append(diagnostic.file)
        return tuple(seen)

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "error_count": self.error_count,
            "reason": self.reason,
            "duration_ms": self.duration_ms,
            "files": {
                path: sum(1 for d in self.diagnostics if d.file == path)
                for path in self.files
            },
            "codes": _code_histogram(self.diagnostics),
        }


def _code_histogram(diagnostics: tuple[TypeDiagnostic, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for diagnostic in diagnostics:
        counts[diagnostic.code] = counts.get(diagnostic.code, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def parse_tsc_output(output: str) -> list[TypeDiagnostic]:
    """Parse `tsc --pretty false` output into structured diagnostics."""
    parsed: list[TypeDiagnostic] = []
    pending: dict[str, Any] | None = None
    detail: list[str] = []

    def _flush() -> None:
        nonlocal pending, detail
        if pending is not None:
            parsed.append(TypeDiagnostic(**pending, detail=tuple(detail)))
        pending = None
        detail = []

    for raw_line in (output or "").splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        match = _DIAGNOSTIC_RE.match(line)
        if match:
            _flush()
            pending = {
                "file": match.group("file").replace("\\", "/").strip(),
                "line": int(match.group("line")),
                "column": int(match.group("column")),
                "code": match.group("code"),
                "message": match.group("message").strip(),
            }
            continue
        global_match = _GLOBAL_DIAGNOSTIC_RE.match(line)
        if global_match:
            _flush()
            pending = {
                "file": "",
                "line": 0,
                "column": 0,
                "code": global_match.group("code"),
                "message": global_match.group("message").strip(),
            }
            continue
        if pending is not None and raw_line.startswith("  "):
            detail.append(line.strip())
    _flush()
    return parsed


def rank_diagnostics(diagnostics: list[TypeDiagnostic]) -> list[TypeDiagnostic]:
    """Most actionable first, keeping every diagnostic for one file together."""
    file_rank = {
        path: index
        for index, path in enumerate(
            sorted(
                {d.file for d in diagnostics if d.file},
                key=lambda path: (_file_priority(path), path),
            )
        )
    }

    def _key(diagnostic: TypeDiagnostic) -> tuple:
        if not diagnostic.file:
            # A project-level error means the whole check is suspect — first.
            return (-1, 0, 0)
        return (
            file_rank.get(diagnostic.file, len(file_rank)),
            _CODE_PRIORITY.get(diagnostic.code, _DEFAULT_CODE_PRIORITY),
            diagnostic.line,
        )

    return sorted(diagnostics, key=_key)


def _file_priority(path: str) -> int:
    for prefix, rank in _FILE_PRIORITY:
        if path.startswith(prefix):
            return rank
    return _DEFAULT_FILE_PRIORITY


def group_by_file(diagnostics: tuple[TypeDiagnostic, ...]) -> dict[str, list[TypeDiagnostic]]:
    grouped: dict[str, list[TypeDiagnostic]] = {}
    for diagnostic in diagnostics:
        grouped.setdefault(diagnostic.file, []).append(diagnostic)
    return grouped


def format_diagnostics(
    report: TypecheckReport,
    *,
    max_per_file: int = 8,
    max_total: int = 40,
    max_chars: int = 7000,
) -> str:
    """Render diagnostics for a prompt: grouped by file, ranked, bounded."""
    if not report.diagnostics:
        return ""
    blocks: list[str] = []
    emitted = 0
    for path, items in group_by_file(report.diagnostics).items():
        if emitted >= max_total:
            break
        head = f"--- {path or '(project)'} ---"
        kept = items[: max(1, max_per_file)]
        emitted += len(kept)
        lines = [diagnostic.as_text() for diagnostic in kept]
        if len(items) > len(kept):
            lines.append(f"  … {len(items) - len(kept)} more error(s) in this file")
        blocks.append("\n".join((head, *lines)))
    text = "\n\n".join(blocks)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n… (truncated)"


def referenced_type_names(diagnostics: tuple[TypeDiagnostic, ...]) -> list[str]:
    """Type names named by the diagnostics — the contracts that were violated."""
    names: list[str] = []
    for diagnostic in diagnostics:
        for text in (diagnostic.message, *diagnostic.detail):
            for name in _TYPE_NAME_RE.findall(text):
                if name not in names:
                    names.append(name)
    return names


def _extract_declaration(source: str, name: str) -> str:
    match = re.search(_DECLARATION_RE.format(name=re.escape(name)), source)
    if not match:
        return ""
    start = match.start()
    tail = source[start:]
    depth = 0
    for index, char in enumerate(tail):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return tail[: index + 1]
        elif char == ";" and depth == 0 and index > 0:
            return tail[: index + 1]
    return tail.split("\n\n", 1)[0]


def collect_type_declarations(
    workspace: Path,
    diagnostics: tuple[TypeDiagnostic, ...],
    *,
    max_declarations: int = _MAX_DECLARATIONS,
    max_chars: int = _MAX_DECLARATION_CHARS,
) -> str:
    """Quote the exported declarations the diagnostics reference, verbatim.

    A bare TS2322 is guesswork; the same error next to
    ``CredentialStripItem = { title: string; detail: string }`` is mechanical.
    Kit shapes come from ``ui_catalogue.ui_type_shape``; the workspace lookup
    then covers names that helper does not resolve (mock seed types, page-local
    interfaces).
    """
    names = referenced_type_names(diagnostics)
    if not names:
        return ""
    blocks: list[str] = []
    seen: set[str] = set()
    for name, snippet in _kit_type_shapes(names).items():
        if snippet.strip():
            seen.add(name)
            blocks.append(snippet.strip())
    sources = _declaration_sources(Path(workspace))
    for name in names:
        if name in seen or len(blocks) >= max_declarations:
            continue
        for rel, source in sources:
            declaration = _extract_declaration(source, name)
            if declaration:
                seen.add(name)
                blocks.append(f"// {rel}\n{declaration}")
                break
    text = "\n\n".join(blocks)
    return text[:max_chars]


def _render_type_shape(shape: Any) -> str:
    if not isinstance(shape, dict):
        return ""
    alias = str(shape.get("alias") or "")
    if alias:
        return alias
    members = shape.get("members") or {}
    if not isinstance(members, dict) or not members:
        return ""
    optional = set(shape.get("optional") or ())
    body = "; ".join(
        f"{name}{'?' if name in optional else ''}: {type_text}"
        for name, type_text in members.items()
    )
    return f"{{ {body} }}"


def _kit_type_shapes(names: list[str]) -> dict[str, str]:
    """Resolve kit type names through the ui_catalogue declaration seam.

    Seam: ``ui_catalogue.ui_type_shape(name)`` -> ``{"members", "optional",
    "alias"}``. A missing helper (or any failure inside it) degrades to the
    workspace source lookup below, never to an empty prompt section.
    """
    try:
        from app.application import ui_catalogue

        resolve = getattr(ui_catalogue, "ui_type_shape", None)
        if not callable(resolve):
            return {}
    except Exception as exc:
        tc_log.debug("ui type declarations unavailable: %s", exc)
        return {}
    shapes: dict[str, str] = {}
    for name in names:
        try:
            rendered = _render_type_shape(resolve(name))
        except Exception as exc:
            tc_log.debug("ui type shape %s unavailable: %s", name, exc)
            continue
        if rendered:
            shapes[name] = f"type {name} = {rendered};"
    return shapes


def _declaration_sources(workspace: Path) -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    for folder in _DECLARATION_SEARCH_DIRS:
        root = workspace / folder
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.ts*")):
            try:
                sources.append((str(path.relative_to(workspace)).replace("\\", "/"), path.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
    return sources


def _compiler_command(workspace: Path) -> list[str] | None:
    """Locate a compiler the same way the mock validator locates typescript."""
    node = shutil.which("node")
    for root in (workspace, Path(settings.PREVIEW_TEMPLATE_DIR)):
        entry = root / "node_modules" / "typescript" / "bin" / "tsc"
        if node and entry.is_file():
            return [node, str(entry)]
        binary = root / "node_modules" / ".bin" / "tsc"
        if binary.is_file():
            return [str(binary)]
    return None


def _project_args(workspace: Path) -> tuple[str, ...]:
    if (workspace / _APP_PROJECT).is_file():
        return ("-p", _APP_PROJECT, *_PROJECT_ARGS)
    return _BUILD_ARGS


_report_cache: dict[str, tuple[str, TypecheckReport]] = {}


def _source_fingerprint(workspace: Path) -> str:
    parts: list[str] = []
    src = workspace / "src"
    if src.is_dir():
        for path in sorted(src.rglob("*")):
            if path.is_file():
                try:
                    stat = path.stat()
                except OSError:
                    continue
                parts.append(f"{path}:{stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(parts)


def typecheck_workspace(
    workspace: Path,
    *,
    timeout: int = _DEFAULT_TIMEOUT,
    use_cache: bool = True,
) -> TypecheckReport:
    """Typecheck a generated workspace. Never raises.

    Infrastructure failure returns ``status="unavailable"`` — never ``"clean"``.
    Repeat calls with untouched sources reuse the previous report.
    """
    workspace = Path(workspace)
    key = str(workspace)
    fingerprint = _source_fingerprint(workspace) if use_cache else ""
    if use_cache and fingerprint:
        cached = _report_cache.get(key)
        if cached and cached[0] == fingerprint:
            return cached[1]

    command = _compiler_command(workspace)
    if command is None:
        return TypecheckReport(status="unavailable", reason="TypeScript compiler not found")
    args = tuple(command) + _project_args(workspace)

    started = time.monotonic()
    try:
        result = subprocess.run(
            list(args),
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return TypecheckReport(
            status="unavailable",
            reason=f"typecheck timed out after {timeout}s",
            duration_ms=int((time.monotonic() - started) * 1000),
            command=args,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        return TypecheckReport(
            status="unavailable",
            reason=f"typecheck could not run: {exc}",
            duration_ms=int((time.monotonic() - started) * 1000),
            command=args,
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    output = f"{result.stdout or ''}\n{result.stderr or ''}"
    parsed = parse_tsc_output(output)
    # A diagnostic with no source location is a config/CLI failure (TS5083,
    # TS6053, bad flag). It says nothing about the generated code and the fix
    # agent cannot act on it, so on its own it means "unavailable".
    diagnostics = tuple(rank_diagnostics(parsed)) if any(d.file for d in parsed) else ()
    if diagnostics:
        report = TypecheckReport(
            status="errors",
            diagnostics=diagnostics,
            duration_ms=duration_ms,
            command=args,
        )
    elif result.returncode == 0:
        report = TypecheckReport(status="clean", duration_ms=duration_ms, command=args)
    else:
        # Non-zero exit with nothing parseable is a broken compiler run, not a
        # healthy workspace — saying "clean" here is how bad apps ship.
        report = TypecheckReport(
            status="unavailable",
            reason=f"typecheck exited {result.returncode} with no source diagnostics: "
            + output.strip()[-400:],
            duration_ms=duration_ms,
            command=args,
        )
    if use_cache and fingerprint:
        if len(_report_cache) >= _MAX_CACHED_REPORTS:
            _report_cache.clear()
        _report_cache[key] = (fingerprint, report)
    return report


def record_typecheck_report(
    workspace: Path,
    report: TypecheckReport,
    *,
    rounds: int = 0,
) -> Path | None:
    """Persist the final type-health verdict at a stable workspace path.

    Type errors never block serving, so this file is where the count lives for
    anything that wants to surface it (finalize, metadata, admin QA).
    """
    payload = {
        **report.summary(),
        "repair_rounds": rounds,
        "recorded_at": int(time.time()),
        "diagnostics": [
            {
                "file": diagnostic.file,
                "line": diagnostic.line,
                "column": diagnostic.column,
                "code": diagnostic.code,
                "message": diagnostic.message,
            }
            for diagnostic in report.diagnostics[:200]
        ],
    }
    path = Path(workspace) / DEBUG_ROOT / _RECORD_CATEGORY / RECORD_FILENAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    except OSError as exc:
        tc_log.warning("could not record typecheck summary: %s", exc)
        return None
    return path


def read_typecheck_record(workspace: Path) -> dict[str, Any]:
    """Read back the recorded verdict; empty dict when nothing was recorded."""
    path = Path(workspace) / DEBUG_ROOT / _RECORD_CATEGORY / RECORD_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
