"""No-package-manager TypeScript and Vite build execution for Phase 4."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from app.application.candidate_generation.cache import canonical_sha256
from app.application.runtime_validation.cache import (
    runtime_cache_key,
    sha256_bytes,
    sha256_file,
)
from app.application.runtime_validation.dist import (
    dist_manifest,
    dist_manifest_sha256,
    validate_dist,
    write_build_identity,
)
from app.application.runtime_validation.workspace import (
    source_manifest_sha256,
)
from app.core.config import settings
from app.domain.schemas.runtime_validation import (
    BuildValidationResult,
    CommandResult,
    RuntimeLimits,
    RuntimeToolVersions,
    RuntimeValidationRefs,
)


def _bounded(value: str, limit: int) -> str:
    payload = value.encode("utf-8", errors="replace")
    if len(payload) <= limit:
        return value
    marker = b"\n...[truncated by Phase 4]..."
    return (payload[: max(0, limit - len(marker))] + marker).decode(
        "utf-8",
        errors="replace",
    )


def network_guard_path() -> Path:
    return Path(__file__).with_name("network_guard.cjs")


def loopback_only_environment() -> dict[str, str]:
    keep = {
        "PATH",
        "Path",
        "SYSTEMROOT",
        "SystemRoot",
        "WINDIR",
        "TEMP",
        "TMP",
        "PATHEXT",
        "COMSPEC",
        "USERPROFILE",
        "LOCALAPPDATA",
    }
    env = {key: value for key, value in os.environ.items() if key in keep}
    guard = str(network_guard_path().resolve()).replace("\\", "/")
    env.update(
        {
            "CI": "1",
            "NO_UPDATE_NOTIFIER": "1",
            "npm_config_offline": "true",
            "npm_config_audit": "false",
            "npm_config_fund": "false",
            "NODE_OPTIONS": f'--require="{guard}"',
        }
    )
    return env


def _command(
    name: str,
    argv: list[str],
    *,
    cwd: Path,
    timeout: int,
    output_limit: int,
    env: dict[str, str],
) -> CommandResult:
    started = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        exit_code = result.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = (
            exc.stdout.decode(errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        stderr = (
            exc.stderr.decode(errors="replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )
        exit_code = 124
    return CommandResult(
        command_name=name,
        argv=tuple(argv),
        exit_code=exit_code,
        timed_out=timed_out,
        duration_ms=int((time.monotonic() - started) * 1000),
        stdout_summary=_bounded(stdout, output_limit),
        stderr_summary=_bounded(stderr, output_limit),
        stdout_sha256=sha256_bytes(stdout.encode("utf-8", errors="replace")),
        stderr_sha256=sha256_bytes(stderr.encode("utf-8", errors="replace")),
    )


def _dependency_tree_sha256(root: Path) -> str:
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        stat = path.stat()
        relpath = str(path.relative_to(root)).replace("\\", "/")
        content_sha = None
        if (
            path.name == "package.json"
            or relpath == ".package-lock.json"
            or relpath in {
                "typescript/bin/tsc",
                "typescript/lib/typescript.js",
                "vite/bin/vite.js",
            }
        ):
            content_sha = sha256_file(path)
        rows.append(
            {
                "path": relpath,
                "byte_count": stat.st_size,
                "modified_ns": stat.st_mtime_ns,
                "content_sha256": content_sha,
            }
        )
    return canonical_sha256(rows)


def verify_dependency_runtime(
    candidate_path: Path,
) -> tuple[dict[str, str], str]:
    lock_path = candidate_path / "package-lock.json"
    if sha256_file(lock_path) == "":
        raise ValueError("Candidate dependency lock is unreadable")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    package = json.loads(
        (candidate_path / "package.json").read_text(encoding="utf-8")
    )
    root_lock = (lock.get("packages") or {}).get("") or {}
    declared = {
        **dict(package.get("dependencies") or {}),
        **dict(package.get("devDependencies") or {}),
    }
    locked_declared = {
        **dict(root_lock.get("dependencies") or {}),
        **dict(root_lock.get("devDependencies") or {}),
    }
    if declared != locked_declared:
        raise ValueError("Candidate package and lock declarations differ")
    modules = settings.PREVIEW_TEMPLATE_DIR / "node_modules"
    versions: dict[str, str] = {}
    locked_packages = lock.get("packages") or {}
    for lock_path, locked in sorted(locked_packages.items()):
        if not lock_path.startswith("node_modules/") or not locked.get(
            "version"
        ):
            continue
        package_name = lock_path.removeprefix("node_modules/")
        installed_path = (
            modules.joinpath(*package_name.split("/")) / "package.json"
        )
        if not installed_path.is_file():
            if locked.get("optional") is True:
                continue
            raise ValueError(
                f"Checked dependency is missing: {package_name}"
            )
        installed = json.loads(installed_path.read_text(encoding="utf-8"))
        if str(installed.get("version")) != str(locked.get("version")):
            raise ValueError(
                f"Checked dependency version mismatch: {package_name}"
            )
        versions[package_name] = str(installed["version"])
    return versions, _dependency_tree_sha256(modules)


def verify_network_guard(
    *,
    cwd: Path,
    limits: RuntimeLimits,
    env: dict[str, str],
) -> CommandResult:
    script = (
        "if (!globalThis.__BMV_NETWORK_GUARD__?.loopbackOnly) process.exit(9);"
        "const attempts=["
        "()=>require('dns').lookup('example.com',()=>{}),"
        "()=>require('http').get('http://example.com'),"
        "()=>require('https').get('https://example.com'),"
        "()=>require('net').connect(80,'8.8.8.8'),"
        "()=>require('tls').connect(443,'8.8.8.8')"
        "];"
        "let blocked=0;"
        "for(const attempt of attempts){try{attempt();}"
        "catch(error){if(error.code==='BMV_EXTERNAL_NETWORK_BLOCKED')"
        "{blocked+=1;}else{process.exit(7);}}}"
        "process.exit(blocked===attempts.length?0:8);"
    )
    return _command(
        "network_guard_verification",
        ["node", "-e", script],
        cwd=cwd,
        timeout=10,
        output_limit=limits.max_command_output_bytes,
        env=env,
    )


def build_cache_keys(
    *,
    refs: RuntimeValidationRefs,
    limits: RuntimeLimits,
    tools: RuntimeToolVersions,
) -> tuple[str, str]:
    build_key = runtime_cache_key(
        "build",
        {
            "candidate_manifest_sha256": refs.candidate_manifest_sha256,
            "dependency_lock_sha256": refs.dependency_lock_sha256,
            "runtime_policy_revision": refs.runtime_policy_revision,
            "node": tools.node,
            "typescript": tools.typescript,
            "vite": tools.vite,
            "network_guard_revision": tools.network_guard_revision,
        },
    )
    dist_key = runtime_cache_key(
        "dist",
        {
            "build_cache_key": build_key,
            "limits": limits.model_dump(mode="json"),
            "dist_policy_revision": "2026-07-24.1",
        },
    )
    return build_key, dist_key


def restore_cached_build(
    *,
    cached: BuildValidationResult,
    cached_dist: Path,
    candidate_path: Path,
    frozen_source_path: Path,
    expected_manifest: tuple[dict[str, Any], ...],
    source_sha_before: str,
) -> BuildValidationResult:
    started = time.monotonic()
    if not cached.passed or not cached.dist_validation_passed:
        raise ValueError("Only a passing build may be restored")
    if not cached_dist.is_dir():
        raise ValueError("Cached dist is missing")
    actual_cached = dist_manifest(cached_dist)
    if (
        dist_manifest_sha256(actual_cached)
        != cached.dist_manifest_sha256
        or actual_cached != cached.dist_files
    ):
        raise ValueError("Cached dist manifest is corrupt")
    target = candidate_path / "dist"
    if cached_dist.resolve(strict=False) != target.resolve(strict=False):
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(cached_dist, target, copy_function=shutil.copy2)
    restored = dist_manifest(target)
    if (
        restored != actual_cached
        or dist_manifest_sha256(restored)
        != cached.dist_manifest_sha256
    ):
        raise ValueError("Restored dist differs from cache")
    _versions, dependency_before = verify_dependency_runtime(candidate_path)
    dependency_after = _dependency_tree_sha256(
        settings.PREVIEW_TEMPLATE_DIR / "node_modules"
    )
    source_after = source_manifest_sha256(
        frozen_source_path,
        expected_manifest,
    )
    diagnostics = []
    if dependency_before != dependency_after:
        diagnostics.append("dependency_runtime_mutated")
    if source_sha_before != source_after:
        diagnostics.append("frozen_candidate_mutated")
    return BuildValidationResult(
        refs=cached.refs,
        build_cache_key=cached.build_cache_key,
        dist_cache_key=cached.dist_cache_key,
        passed=not diagnostics,
        dist_validation_passed=not diagnostics,
        cache_hit=True,
        deterministic_repair_count=0,
        source_candidate_sha256_before=source_sha_before,
        source_candidate_sha256_after=source_after,
        dependency_runtime_sha256_before=dependency_before,
        dependency_runtime_sha256_after=dependency_after,
        network_guard_verified=True,
        build_hash=cached.build_hash,
        dist_manifest_sha256=cached.dist_manifest_sha256,
        dist_files=restored,
        commands=(),
        diagnostics=tuple(diagnostics),
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def run_build_validation(
    *,
    refs: RuntimeValidationRefs,
    candidate_path: Path,
    frozen_source_path: Path,
    expected_manifest: tuple[dict[str, Any], ...],
    source_sha_before: str,
    limits: RuntimeLimits,
    tools: RuntimeToolVersions,
    cache_hit: bool = False,
    deterministic_repair_count: int = 0,
    derived_from_build_attempt_id: int | None = None,
) -> BuildValidationResult:
    started = time.monotonic()
    commands: list[CommandResult] = []
    diagnostics: list[str] = []
    zero = "0" * 64
    build_cache_key, dist_cache_key = build_cache_keys(
        refs=refs,
        limits=limits,
        tools=tools,
    )
    dependency_before = zero
    dependency_after = zero
    source_after = source_sha_before
    try:
        template_lock = settings.PREVIEW_TEMPLATE_DIR / "package-lock.json"
        if sha256_file(template_lock) != refs.dependency_lock_sha256:
            raise ValueError("Approved dependency-lock hash changed")
        if json.loads(
            (candidate_path / "package-lock.json").read_text(
                encoding="utf-8"
            )
        ) != json.loads(template_lock.read_text(encoding="utf-8")):
            raise ValueError("Candidate dependency-lock content changed")
        _versions, dependency_before = verify_dependency_runtime(
            candidate_path
        )
        env = loopback_only_environment()
        guard = verify_network_guard(cwd=candidate_path, limits=limits, env=env)
        commands.append(guard)
        if guard.exit_code != 0 or guard.timed_out:
            raise RuntimeError("Network guard could not be verified")
        modules = settings.PREVIEW_TEMPLATE_DIR / "node_modules"
        tsc = _command(
            "typescript_build",
            [
                "node",
                str(modules / "typescript" / "bin" / "tsc"),
                "-b",
                "--pretty",
                "false",
            ],
            cwd=candidate_path,
            timeout=limits.typescript_timeout_seconds,
            output_limit=limits.max_command_output_bytes,
            env=env,
        )
        commands.append(tsc)
        if tsc.exit_code != 0 or tsc.timed_out:
            raise RuntimeError("TypeScript project build failed")
        elapsed = time.monotonic() - started
        remaining = limits.build_stage_timeout_seconds - elapsed
        if remaining <= 0:
            raise TimeoutError("Combined build-stage timeout exceeded")
        dist = candidate_path / "dist"
        if dist.exists():
            shutil.rmtree(dist)
        vite = _command(
            "vite_build",
            [
                "node",
                str(modules / "vite" / "bin" / "vite.js"),
                "build",
                "--mode",
                "production",
                "--outDir",
                "dist",
                "--emptyOutDir",
            ],
            cwd=candidate_path,
            timeout=min(
                limits.vite_build_timeout_seconds,
                max(1, int(remaining)),
            ),
            output_limit=limits.max_command_output_bytes,
            env=env,
        )
        commands.append(vite)
        if vite.exit_code != 0 or vite.timed_out:
            raise RuntimeError("Vite production build failed")
        pre_identity_rows, dist_issues = validate_dist(
            dist,
            limits=limits,
            forbidden_absolute_roots=(
                str(settings.PROJECT_ROOT),
                str(frozen_source_path),
                str(candidate_path),
            ),
        )
        if dist_issues:
            diagnostics.extend(dist_issues)
            raise RuntimeError("Production output validation failed")
        pre_identity_sha = dist_manifest_sha256(pre_identity_rows)
        build_hash = canonical_sha256(
            {
                "candidate_manifest_sha256": refs.candidate_manifest_sha256,
                "dependency_lock_sha256": refs.dependency_lock_sha256,
                "build_cache_key": build_cache_key,
                "dist_content_sha256": pre_identity_sha,
            }
        )
        write_build_identity(
            dist,
            candidate_manifest_sha256=refs.candidate_manifest_sha256,
            build_hash=build_hash,
            dist_content_sha256=pre_identity_sha,
        )
        final_rows, final_issues = validate_dist(
            dist,
            limits=limits,
            forbidden_absolute_roots=(
                str(settings.PROJECT_ROOT),
                str(frozen_source_path),
                str(candidate_path),
            ),
        )
        if final_issues:
            diagnostics.extend(final_issues)
            raise RuntimeError("Final dist manifest validation failed")
        final_sha = dist_manifest_sha256(final_rows)
        dependency_after = _dependency_tree_sha256(modules)
        source_after = source_manifest_sha256(
            frozen_source_path,
            expected_manifest,
        )
        if dependency_before != dependency_after:
            diagnostics.append("dependency_runtime_mutated")
        if source_sha_before != source_after:
            diagnostics.append("frozen_candidate_mutated")
        passed = not diagnostics
        return BuildValidationResult(
            refs=refs,
            build_cache_key=build_cache_key,
            dist_cache_key=dist_cache_key,
            passed=passed,
            dist_validation_passed=passed,
            cache_hit=cache_hit,
            deterministic_repair_count=deterministic_repair_count,
            derived_from_build_attempt_id=derived_from_build_attempt_id,
            source_candidate_sha256_before=source_sha_before,
            source_candidate_sha256_after=source_after,
            dependency_runtime_sha256_before=dependency_before,
            dependency_runtime_sha256_after=dependency_after,
            network_guard_verified=guard.exit_code == 0,
            build_hash=build_hash,
            dist_manifest_sha256=final_sha,
            dist_files=final_rows,
            commands=tuple(commands),
            diagnostics=tuple(diagnostics),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as exc:
        if not diagnostics:
            diagnostics.append(
                f"{type(exc).__name__}: {str(exc)[:1000]}"
            )
        try:
            dependency_after = _dependency_tree_sha256(
                settings.PREVIEW_TEMPLATE_DIR / "node_modules"
            )
        except Exception as dependency_exc:
            diagnostics.append(
                f"dependency_rehash_failed:{str(dependency_exc)[:1000]}"
            )
        try:
            source_after = source_manifest_sha256(
                frozen_source_path,
                expected_manifest,
            )
        except Exception as source_exc:
            source_after = zero
            diagnostics.append(
                f"candidate_rehash_failed:{str(source_exc)[:1000]}"
            )
        if dependency_before != zero and dependency_before != dependency_after:
            diagnostics.append("dependency_runtime_mutated")
        if source_sha_before != source_after:
            diagnostics.append("frozen_candidate_mutated")
        return BuildValidationResult(
            refs=refs,
            build_cache_key=build_cache_key,
            dist_cache_key=dist_cache_key,
            passed=False,
            dist_validation_passed=False,
            cache_hit=cache_hit,
            deterministic_repair_count=deterministic_repair_count,
            derived_from_build_attempt_id=derived_from_build_attempt_id,
            source_candidate_sha256_before=source_sha_before,
            source_candidate_sha256_after=source_after,
            dependency_runtime_sha256_before=dependency_before,
            dependency_runtime_sha256_after=dependency_after,
            network_guard_verified=bool(
                commands and commands[0].exit_code == 0
            ),
            build_hash=zero,
            dist_manifest_sha256=zero,
            dist_files=(),
            commands=tuple(commands),
            diagnostics=tuple(dict.fromkeys(diagnostics)),
            duration_ms=int((time.monotonic() - started) * 1000),
        )


__all__ = [
    "build_cache_keys",
    "loopback_only_environment",
    "network_guard_path",
    "restore_cached_build",
    "run_build_validation",
    "verify_dependency_runtime",
    "verify_network_guard",
]
