"""Build preview React apps with npm + vite."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from app.domain.interfaces.template_renderer import TemplateRenderer
from app.application.preview_app.npm_shared import attach_shared_node_modules


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

    try:
        logs.append(attach_shared_node_modules(workspace, timeout=timeout))
    except Exception as exc:
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
        if install.returncode != 0:
            return False, "\n".join(logs)

    vite_pkg = workspace / "node_modules" / "vite" / "package.json"
    if not vite_pkg.is_file():
        logs.append("=== ERROR: vite not installed after shared/local npm setup ===")
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

    build = subprocess.run(
        [npm, "exec", "--", "vite", "build"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=install_env,
        shell=(os.name == "nt"),
    )
    logs.append("=== vite build ===")
    logs.append(build.stdout or "")
    logs.append(build.stderr or "")
    if build.returncode != 0:
        # Surface the real failure in pipeline logs (AI fix can't patch missing native bindings).
        err_tail = (build.stderr or build.stdout or "")[-1200:]
        print(f"    vite build failed:\n{err_tail}", flush=True)

    dist = workspace / "dist" / "index.html"
    ok = build.returncode == 0 and dist.is_file()
    return ok, "\n".join(logs)


def extract_build_errors(log: str, max_chars: int = 8000) -> str:
    """Pull error lines from build log for the fix agent."""
    lines = log.splitlines()
    error_lines = [
        ln for ln in lines
        if any(k in ln.lower() for k in ("error", "failed", "cannot", "unexpected", "✗"))
    ]
    if not error_lines:
        return log[-max_chars:]
    text = "\n".join(error_lines)
    return text[-max_chars:] if len(text) > max_chars else text
