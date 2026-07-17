"""Shared npm install for preview workspaces — install once, link into each build.

Each generation used to run a full `npm install` into `preview-apps/{id}/`.
Dependencies are identical for every request (same package-lock from the
template), so we install into a fingerprint-keyed shared folder and junction
(or symlink) `node_modules` into the workspace before `vite build`.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import threading
from pathlib import Path

from app.core.config import settings
from app.infrastructure.logging import get_logger

log = get_logger("SharedNpm")

_install_lock = threading.Lock()


def _npm_cmd() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _template_lock_fingerprint() -> str:
    """Stable id for the current template dependency set."""
    tpl = settings.PREVIEW_TEMPLATE_DIR
    h = hashlib.sha256()
    for name in ("package-lock.json", "package.json"):
        path = tpl / name
        if path.is_file():
            h.update(name.encode())
            h.update(path.read_bytes())
        else:
            h.update(f"missing:{name}".encode())
    return h.hexdigest()[:16]


def shared_npm_root() -> Path:
    return Path(settings.PREVIEW_APPS_DIR) / "_shared_npm" / _template_lock_fingerprint()


def _vite_ready(node_modules: Path) -> bool:
    return (node_modules / "vite" / "package.json").is_file()


def _remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        # Broken junction/symlink
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
        return
    # Directory junction on Windows reports as is_dir(); rmtree works for junctions
    # that point at real dirs. Fall back to rmdir for empty / junction-only.
    try:
        shutil.rmtree(path)
    except OSError:
        try:
            path.rmdir()
        except OSError:
            if os.name == "nt":
                subprocess.run(
                    ["cmd", "/c", "rmdir", str(path)],
                    capture_output=True,
                    text=True,
                    shell=False,
                )


def _link_node_modules(workspace: Path, shared_nm: Path) -> None:
    """Point workspace/node_modules at the shared install (junction on Windows)."""
    target = workspace / "node_modules"
    if target.exists() or target.is_symlink():
        # Already linked to the right place?
        try:
            if target.resolve() == shared_nm.resolve():
                return
        except OSError:
            pass
        _remove_path(target)

    shared_nm = shared_nm.resolve()
    if os.name == "nt":
        # Directory junction — no admin rights required (unlike symlink).
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(shared_nm)],
            capture_output=True,
            text=True,
            shell=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to junction node_modules: {result.stderr or result.stdout}"
            )
    else:
        target.symlink_to(shared_nm, target_is_directory=True)


def ensure_shared_node_modules(timeout: int = 300) -> tuple[Path, str]:
    """Install template deps into the shared cache if needed. Returns (node_modules, log)."""
    root = shared_npm_root()
    nm = root / "node_modules"
    logs: list[str] = []

    with _install_lock:
        if _vite_ready(nm):
            logs.append(f"=== shared npm: cache hit ({root.name}) ===")
            log.debug("shared npm cache hit at %s", nm)
            return nm, "\n".join(logs)

        logs.append(f"=== shared npm: installing into {root} ===")
        log.info("shared npm cache miss — installing into %s", root)
        root.mkdir(parents=True, exist_ok=True)
        tpl = settings.PREVIEW_TEMPLATE_DIR
        for name in ("package.json", "package-lock.json"):
            src = tpl / name
            if src.is_file():
                shutil.copy2(src, root / name)

        npm = _npm_cmd()
        env = {k: v for k, v in os.environ.items() if k != "NODE_ENV"}
        # Prefer ci when lockfile exists (faster, deterministic).
        lock = root / "package-lock.json"
        cmd = (
            [npm, "ci", "--no-audit", "--no-fund"]
            if lock.is_file()
            else [npm, "install", "--no-audit", "--no-fund"]
        )
        install = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            shell=(os.name == "nt"),
        )
        logs.append("=== shared npm install ===")
        logs.append(install.stdout or "")
        logs.append(install.stderr or "")
        if install.returncode != 0 or not _vite_ready(nm):
            # Fall back to npm install if ci failed (lock drift).
            if cmd[1] == "ci":
                logs.append("=== shared npm: ci failed, retrying npm install ===")
                install = subprocess.run(
                    [npm, "install", "--no-audit", "--no-fund"],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                    shell=(os.name == "nt"),
                )
                logs.append(install.stdout or "")
                logs.append(install.stderr or "")
            if install.returncode != 0 or not _vite_ready(nm):
                log.error(
                    "shared npm install failed (returncode=%s vite_ready=%s) — see .bmv-debug if build ran",
                    install.returncode,
                    _vite_ready(nm),
                )
                raise RuntimeError(
                    "Shared npm install failed — vite missing after install.\n" + "\n".join(logs)
                )
        log.info("shared npm ready at %s", nm)
        logs.append("=== shared npm: ready ===")
        return nm, "\n".join(logs)


def attach_shared_node_modules(workspace: Path, timeout: int = 300) -> str:
    """Ensure shared deps exist and link them into the workspace. Returns log text."""
    shared_nm, log = ensure_shared_node_modules(timeout=timeout)
    _link_node_modules(workspace, shared_nm)
    return log + f"\n=== linked node_modules -> {shared_nm} ===\n"
