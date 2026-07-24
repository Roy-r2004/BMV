"""Fresh isolated Vite preview-server lifecycle and build identity check."""
from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from app.application.runtime_validation.build import (
    loopback_only_environment,
)
from app.application.runtime_validation.cache import sha256_bytes
from app.core.config import settings
from app.domain.schemas.runtime_validation import CommandResult, RuntimeLimits


@dataclass
class PreviewServer:
    process: subprocess.Popen
    base_url: str
    argv: tuple[str, ...]
    started_at: float
    output_limit: int
    _stdout: str = field(default="")
    _stderr: str = field(default="")

    def stop(self) -> CommandResult:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                stdout, stderr = self.process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                stdout, stderr = self.process.communicate(timeout=5)
        else:
            stdout, stderr = self.process.communicate(timeout=5)
        stdout = stdout or self._stdout
        stderr = stderr or self._stderr
        exit_code = self.process.returncode
        duration_ms = int((time.monotonic() - self.started_at) * 1000)
        return CommandResult(
            command_name="vite_preview",
            argv=self.argv,
            exit_code=exit_code,
            timed_out=False,
            duration_ms=duration_ms,
            stdout_summary=stdout[-self.output_limit :],
            stderr_summary=stderr[-self.output_limit :],
            stdout_sha256=sha256_bytes(stdout.encode(errors="replace")),
            stderr_sha256=sha256_bytes(stderr.encode(errors="replace")),
        )


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _fetch_json(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"Preview health returned {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Preview identity payload is invalid")
    return payload


def start_preview_server(
    candidate_path: Path,
    *,
    expected_candidate_manifest_sha256: str,
    expected_build_hash: str,
    limits: RuntimeLimits,
) -> tuple[PreviewServer, dict]:
    port = _reserve_port()
    modules = settings.PREVIEW_TEMPLATE_DIR / "node_modules"
    argv = (
        "node",
        str(modules / "vite" / "bin" / "vite.js"),
        "preview",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--strictPort",
    )
    process = subprocess.Popen(
        list(argv),
        cwd=candidate_path,
        env=loopback_only_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
    )
    server = PreviewServer(
        process=process,
        base_url=f"http://127.0.0.1:{port}",
        argv=argv,
        started_at=time.monotonic(),
        output_limit=limits.max_command_output_bytes,
    )
    deadline = time.monotonic() + limits.server_startup_timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=2)
            server._stdout = stdout or ""
            server._stderr = stderr or ""
            raise RuntimeError(
                "Vite preview server exited before health verification: "
                f"{server._stderr[-2000:]}"
            )
        try:
            identity = _fetch_json(
                f"{server.base_url}/bmv-build-identity.json",
                timeout=1.0,
            )
            if (
                identity.get("candidate_manifest_sha256")
                != expected_candidate_manifest_sha256
                or identity.get("build_hash") != expected_build_hash
            ):
                raise ValueError("Served build identity does not match")
            return server, identity
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last_error = str(exc)
            time.sleep(0.1)
    command = server.stop()
    raise TimeoutError(
        "Preview server startup timeout: "
        f"{last_error}; {command.stderr_summary[-1000:]}"
    )


__all__ = ["PreviewServer", "start_preview_server"]
