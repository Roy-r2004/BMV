"""Deterministic Phase 4 production-output validation."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.application.appspec.source import canonical_json
from app.application.candidate_generation.cache import canonical_sha256
from app.application.runtime_validation.cache import sha256_file
from app.domain.schemas.runtime_validation import DistFileRecord, RuntimeLimits


_REMOTE_IMPORT = re.compile(
    r"""(?:import\s*(?:\(|[^'"]*from\s*)|url\s*\()\s*['"]?https?://""",
    re.IGNORECASE,
)
_SOURCE_MAP = re.compile(r"sourceMappingURL\s*=", re.IGNORECASE)
_ABSOLUTE_LOCAL = re.compile(
    r"(?:[A-Za-z]:[\\/](?:Users|home|tmp|Your Business Version)[\\/]|"
    r"/(?:Users|home|tmp)/)",
    re.IGNORECASE,
)
_UNEXPECTED_ENV = re.compile(
    r"(?:OPENROUTER_API_KEY|DATABASE_URL|PEXELS_API_KEY|"
    r"SECRET_KEY|ADMIN_PASSWORD)",
)


def _media_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in {".js", ".mjs", ".cjs"}:
        return "javascript"
    if suffix == ".css":
        return "css"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"}:
        return "image"
    if suffix in {".woff", ".woff2", ".ttf", ".otf"}:
        return "font"
    if suffix == ".json":
        return "json"
    return "other"


def dist_manifest(dist: Path) -> tuple[DistFileRecord, ...]:
    rows = []
    for path in sorted(item for item in dist.rglob("*") if item.is_file()):
        if path.is_symlink():
            raise ValueError("Dist output contains a symbolic link")
        rows.append(
            DistFileRecord(
                path=str(path.relative_to(dist)).replace("\\", "/"),
                sha256=sha256_file(path),
                byte_count=path.stat().st_size,
                media_kind=_media_kind(path),
            )
        )
    return tuple(rows)


def dist_manifest_sha256(rows: tuple[DistFileRecord, ...]) -> str:
    return canonical_sha256([item.model_dump(mode="json") for item in rows])


def _local_asset_path(dist: Path, raw: str) -> Path | None:
    value = raw.strip()
    parsed = urlparse(value)
    if parsed.scheme or value.startswith("//") or value.startswith("data:"):
        return None
    clean = parsed.path
    if not clean or clean.startswith("#"):
        return None
    if clean.startswith("/"):
        return dist / clean.lstrip("/")
    return dist / clean.removeprefix("./")


def validate_dist(
    dist: Path,
    *,
    limits: RuntimeLimits,
    forbidden_absolute_roots: tuple[str, ...],
) -> tuple[tuple[DistFileRecord, ...], tuple[str, ...]]:
    issues: list[str] = []
    index = dist / "index.html"
    if not index.is_file():
        return (), ("index_html_missing",)
    rows = dist_manifest(dist)
    if len(rows) > limits.max_dist_files:
        issues.append("dist_file_count_budget_exceeded")
    total = sum(item.byte_count for item in rows)
    if total > limits.max_dist_bytes:
        issues.append("dist_total_bytes_budget_exceeded")
    javascript = [item for item in rows if item.media_kind == "javascript"]
    if any(item.byte_count > limits.max_javascript_bytes for item in javascript):
        issues.append("javascript_asset_budget_exceeded")
    css_total = sum(
        item.byte_count for item in rows if item.media_kind == "css"
    )
    if css_total > limits.max_css_bytes:
        issues.append("css_budget_exceeded")
    source_map_count = sum(item.path.endswith(".map") for item in rows)
    if source_map_count > limits.max_source_maps:
        issues.append("source_map_file_budget_exceeded")

    index_text = index.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(index_text, "html.parser")
    for element, attribute in (
        ("script", "src"),
        ("link", "href"),
        ("img", "src"),
        ("source", "src"),
    ):
        for node in soup.find_all(element):
            raw = str(node.get(attribute) or "")
            if not raw:
                continue
            parsed = urlparse(raw)
            if parsed.scheme in {"http", "https"} or raw.startswith("//"):
                issues.append(f"remote_runtime_asset:{raw[:200]}")
                continue
            local = _local_asset_path(dist, raw)
            if local is not None and not local.is_file():
                issues.append(f"missing_local_asset:{raw[:200]}")

    text_extensions = {".html", ".js", ".mjs", ".cjs", ".css", ".json"}
    forbidden_roots = tuple(
        value.replace("\\", "/") for value in forbidden_absolute_roots if value
    )
    for row in rows:
        path = dist / row.path
        if path.suffix.lower() not in text_extensions:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if _REMOTE_IMPORT.search(text):
            issues.append(f"remote_import_or_asset:{row.path}")
        if _SOURCE_MAP.search(text):
            issues.append(f"source_map_reference:{row.path}")
        normalized = text.replace("\\", "/")
        if _ABSOLUTE_LOCAL.search(text) or any(
            root in normalized for root in forbidden_roots
        ):
            issues.append(f"absolute_local_path:{row.path}")
        if _UNEXPECTED_ENV.search(text):
            issues.append(f"unexpected_environment_value:{row.path}")
    return rows, tuple(sorted(set(issues)))


def write_build_identity(
    dist: Path,
    *,
    candidate_manifest_sha256: str,
    build_hash: str,
    dist_content_sha256: str,
) -> Path:
    target = dist / "bmv-build-identity.json"
    target.write_text(
        canonical_json(
            {
                "candidate_manifest_sha256": candidate_manifest_sha256,
                "build_hash": build_hash,
                "dist_content_sha256": dist_content_sha256,
            }
        ),
        encoding="utf-8",
        newline="\n",
    )
    return target


def read_build_identity(dist: Path) -> dict:
    payload = json.loads(
        (dist / "bmv-build-identity.json").read_text(encoding="utf-8")
    )
    if not isinstance(payload, dict):
        raise ValueError("Build identity is invalid")
    return payload


__all__ = [
    "dist_manifest",
    "dist_manifest_sha256",
    "read_build_identity",
    "validate_dist",
    "write_build_identity",
]
