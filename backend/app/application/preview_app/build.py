"""Build preview React apps with npm + vite."""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

from app.domain.interfaces.template_renderer import TemplateRenderer
from app.application.preview_app.npm_shared import attach_shared_node_modules
from app.infrastructure.logging import get_logger
from app.infrastructure.logging.diagnostics import dump_build_failure

log = get_logger("ViteBuild")


def _npm_cmd() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def run_build(
    workspace: Path,
    base_path: str,
    template_renderer: TemplateRenderer,
    timeout: int = 300,
) -> tuple[bool, str]:
    """Link shared node_modules + vite build. Returns (success, combined output).

    Dependencies are installed once into PREVIEW_APPS_DIR/_shared_npm/<lock-hash>/
    and junctioned/symlinked into each workspace — so generation time goes to AI
    quality, not repeated npm downloads.
    """
    npm = _npm_cmd()
    env = os.environ.copy()
    # Must install/use devDependencies (vite, tailwind) — do not set NODE_ENV=production
    install_env = {k: v for k, v in env.items() if k != "NODE_ENV"}

    logs: list[str] = []

    # Every phase of the build is timed. `build_phase.py:183` still carries a
    # "~20 s" comment that measurement puts 40× out; the only way that comment
    # survived is that nothing here ever said how long it took.
    attach_started = time.monotonic()
    try:
        logs.append(attach_shared_node_modules(workspace, timeout=timeout))
        log.info(
            "npm attach finished in %.2fs workspace=%s",
            time.monotonic() - attach_started,
            workspace.name,
        )
    except Exception as exc:
        log.error("shared npm attach failed: %s", exc)
        logs.append(f"=== shared npm failed ({exc}) — falling back to local npm install ===")
        install = subprocess.run(
            [npm, "install", "--no-audit", "--no-fund"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=install_env,
            shell=(os.name == "nt"),
        )
        logs.append("=== npm install (local fallback) ===")
        logs.append(install.stdout or "")
        logs.append(install.stderr or "")
        log.info(
            "npm install (local fallback) finished in %.2fs exit=%s workspace=%s",
            time.monotonic() - attach_started,
            install.returncode,
            workspace.name,
        )
        if install.returncode != 0:
            return False, "\n".join(logs)

    vite_pkg = workspace / "node_modules" / "vite" / "package.json"
    if not vite_pkg.is_file():
        msg = "vite not installed after shared/local npm setup"
        log.error(msg)
        logs.append(f"=== ERROR: {msg} ===")
        dump_build_failure(
            workspace,
            label="npm-setup",
            build_log="\n".join(logs),
            extracted_errors=msg,
        )
        return False, "\n".join(logs)

    # Patch vite base for subdirectory hosting
    vite_config = workspace / "vite.config.ts"
    if vite_config.is_file():
        content = vite_config.read_text(encoding="utf-8")
        base = base_path if base_path.endswith("/") else f"{base_path}/"
        base_decl = template_renderer.render("codegen/vite_base_patch.j2", base=base)
        if "base:" in content:
            content = re.sub(r"base:\s*['\"][^'\"]*['\"]", base_decl, content)
        else:
            content = content.replace(
                "export default defineConfig({",
                f"export default defineConfig({{\n  {base_decl},",
            )
        vite_config.write_text(content, encoding="utf-8")

    build_started = time.monotonic()
    build = subprocess.run(
        [npm, "exec", "--", "vite", "build"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=install_env,
        shell=(os.name == "nt"),
    )
    build_seconds = time.monotonic() - build_started
    logs.append("=== vite build ===")
    logs.append(build.stdout or "")
    logs.append(build.stderr or "")
    log.info(
        "vite build finished in %.2fs exit=%s total_run_build %.2fs workspace=%s",
        build_seconds,
        build.returncode,
        time.monotonic() - attach_started,
        workspace.name,
    )
    if build.returncode != 0:
        err_tail = (build.stderr or build.stdout or "")[-1200:]
        log.error("vite build failed (see dump in .bmv-debug/vite-build/):\n%s", err_tail)

    dist = workspace / "dist" / "index.html"
    ok = build.returncode == 0 and dist.is_file()
    combined = "\n".join(logs)
    if not ok:
        dump_build_failure(
            workspace,
            label="vite-build",
            build_log=combined,
            extracted_errors=extract_build_errors(combined),
        )
    return ok, combined


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# src/pages/Foo.tsx:54:5 — the location rolldown/tsc put in the diagnostic body.
_LOCATION_RE = re.compile(r"[\w./-]+\.(?:tsx?|jsx?|css|json):\d+(?::\d+)?")
_KEYWORDS = ("error", "failed", "cannot", "unexpected", "✗")
# A JS stack frame. Never actionable for a codegen fix, and the bundler emits a
# dozen of them per failure — they match on "error" in a chunk filename and on
# ".js:line:col" as a location, so they must be dropped explicitly.
_STACK_FRAME_RE = re.compile(r"^\s*at\s+\S")
# Matches a keyword only because of a bundler internal.
_NOISE = ("errors: [getter/setter]",)
_CONTEXT_AFTER = 12


def extract_build_errors(log: str, max_chars: int = 8000) -> str:
    """Pull the actionable part of a build log out for the fix agent.

    This used to filter line by line on ``_KEYWORDS``, which silently dropped
    every rolldown diagnostic: the lines that carry the message and the
    ``file:line:col`` live *inside* a box-drawing block and contain none of the
    keywords. A JSX syntax error therefore reached the fix agent as::

        ✗ Build failed in 312ms
        error during build:
        Build failed with 1 error:
            at aggregateBindingErrorsIntoJsError (.../rolldown/dist/...)
          errors: [Getter/Setter]

    — no file, no line, no message, so all six fix attempts were unfixable.
    Keeping a window of following lines preserves the whole block, and ANSI
    stripping keeps the colour escapes from eating the character budget.
    """

    lines = _ANSI_RE.sub("", log).splitlines()

    def _is_noise(line: str) -> bool:
        lowered = line.lower()
        return _STACK_FRAME_RE.match(line) is not None or any(
            noise in lowered for noise in _NOISE
        )

    keep: set[int] = set()
    for i, line in enumerate(lines):
        if _is_noise(line):
            continue
        lowered = line.lower()
        if any(k in lowered for k in _KEYWORDS) or _LOCATION_RE.search(line):
            # A diagnostic header is followed by the block that explains it.
            keep.update(range(i, min(len(lines), i + _CONTEXT_AFTER + 1)))

    if not keep:
        return log[-max_chars:]

    # Noise pulled in by a context window is still noise.
    selected = [lines[i] for i in sorted(keep) if not _is_noise(lines[i])]
    # Drop the trailing blank/box-drawing filler the context window pulls in.
    while selected and not selected[-1].strip(" │╭╰─┬"):
        selected.pop()

    text = "\n".join(selected).strip()
    if len(text) <= max_chars:
        return text
    # Truncate the tail, not the head: the first diagnostic is the one to fix,
    # and later output is usually cascade noise or a bundler stack.
    return text[:max_chars].rstrip() + "\n… (truncated)"
