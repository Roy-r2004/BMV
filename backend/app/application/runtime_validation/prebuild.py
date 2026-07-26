"""Bounded, fail-fast Phase 4 checks that do not emulate TypeScript."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.domain.schemas.runtime_validation import Phase4FailureCode


@dataclass(frozen=True)
class PrebuildValidationError(ValueError):
    code: Phase4FailureCode
    evidence: str
    location: str | None = None

    def __str__(self) -> str:
        return self.evidence


_REQUIRED_FILES = (
    "package.json",
    "package-lock.json",
    "index.html",
    "tsconfig.json",
    "tsconfig.app.json",
    "tsconfig.node.json",
    "vite.config.ts",
    "src/main.tsx",
    "src/App.tsx",
    "src/generated/route-manifest.ts",
)


def _load_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PrebuildValidationError(
            "package_manifest_invalid",
            f"Invalid JSON: {path.name}: {type(exc).__name__}",
            path.name,
        ) from exc
    if not isinstance(value, dict):
        raise PrebuildValidationError(
            "package_manifest_invalid",
            f"Expected JSON object: {path.name}",
            path.name,
        )
    return value


def validate_prebuild(candidate_path: Path) -> tuple[str, ...]:
    """Validate only deterministic file/manifest invariants before execution."""
    for relpath in _REQUIRED_FILES:
        if not (candidate_path / relpath).is_file():
            code: Phase4FailureCode = (
                "package_manifest_invalid"
                if relpath.startswith(("package", "tsconfig"))
                else "route_missing"
            )
            raise PrebuildValidationError(
                code,
                f"Required candidate file is missing: {relpath}",
                relpath,
            )

    package = _load_object(candidate_path / "package.json")
    _load_object(candidate_path / "package-lock.json")

    scripts = package.get("scripts")
    if not isinstance(scripts, dict):
        raise PrebuildValidationError(
            "package_manifest_invalid",
            "package.json scripts must be an object",
            "package.json",
        )
    for name in ("typecheck", "build"):
        if not isinstance(scripts.get(name), str) or not scripts[name].strip():
            raise PrebuildValidationError(
                "package_manifest_invalid",
                f"package.json is missing required script: {name}",
                "package.json",
            )

    for field in ("dependencies", "devDependencies"):
        value = package.get(field)
        if value is not None and not isinstance(value, dict):
            raise PrebuildValidationError(
                "package_manifest_invalid",
                f"package.json {field} must be an object",
                "package.json",
            )

    forbidden_markers = (
        "file:///",
        "/Users/",
        "/app/data/",
        "/app/backend/",
        "C:\\Users\\",
        "C:\\\\Users\\\\",
    )
    skip_parts = {"node_modules", ".phase4-cache", "dist"}
    for path in sorted(candidate_path.rglob("*")):
        if any(part in skip_parts for part in path.parts):
            continue
        if path.suffix.lower() not in {".ts", ".tsx", ".js", ".jsx", ".css", ".html"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        marker = next((item for item in forbidden_markers if item in text), None)
        if marker is not None:
            relpath = str(path.relative_to(candidate_path)).replace("\\", "/")
            raise PrebuildValidationError(
                "import_resolution_failed",
                f"Forbidden absolute filesystem path in {relpath}: {marker}",
                relpath,
            )

    return tuple(_REQUIRED_FILES)


__all__ = ["PrebuildValidationError", "validate_prebuild"]
