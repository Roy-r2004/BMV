"""Runtime asset integrity for generated preview apps.

The browser requests the asset paths written into generated source verbatim, so a
path that exists in neither ``public/`` nor the built ``dist/`` renders as a
broken-image icon. Build-time specifiers (``@/…`` aliases, ``./index.css``,
bare modules) are resolved by the bundler and never reach the network, so they
are deliberately out of scope. False positives are worse than misses here: a
reference is only reported when the browser would certainly 404 it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from app.application.preview_app.workspace import list_source_files, read_file, write_file

_RUNTIME_ASSET_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".avif",
        ".ico",
        ".bmp",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        ".mp4",
        ".webm",
        ".ogv",
        ".ogg",
        ".mp3",
        ".wav",
        ".m4a",
        ".pdf",
    }
)
# Vite copies public/ into dist/, so either root satisfies a runtime request.
_ASSET_ROOTS = ("public", "dist")
_INTERNAL_SURFACE_MARKERS = (
    "admin",
    "owner",
    "staff",
    "internal",
    "manage",
    "console",
    "dashboard",
    "/ops",
)
_IGNORED_PREFIXES = (
    "http://",
    "https://",
    "//",
    "data:",
    "blob:",
    "file:",
    "mailto:",
    "tel:",
    "@",
    "#",
    "?",
)
_STRING_LITERAL_RE = re.compile(r"""(['"])([^'"\n]{1,400})\1""")
_CSS_URL_RE = re.compile(r"""url\(\s*['"]?([^'")\s]{1,400})['"]?\s*\)""")
_HTML_REF_RE = re.compile(r"""(?:src|href|content)\s*=\s*['"]([^'"\s]{1,400})['"]""", re.I)
_MODULE_SPECIFIER_RE = re.compile(
    r"""\bfrom\s*['"]|^\s*import\s*['"]|\brequire\s*\(\s*['"]|\bimport\s*\(\s*['"]"""
)
_MOCK_IMAGES_BLOCK_RE = re.compile(r"export\s+const\s+images\s*=\s*\{(.*?)\n\};", re.S)
_REMOTE_URL_RE = re.compile(r"""['"](https?://[^'"\s]+)['"]""")


@dataclass(frozen=True)
class MissingAssetReference:
    path: str
    referenced_by: tuple[str, ...]
    public_surface: bool


@dataclass
class AssetIntegrityReport:
    missing: list[MissingAssetReference] = field(default_factory=list)
    scanned: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing


def _normalize(ref: str) -> str:
    parts: list[str] = []
    for part in ref.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _candidate_ref(raw: str) -> str | None:
    """Reduce a source literal to a browser-requested asset path, else None."""
    ref = raw.strip()
    if not ref or ref.startswith(_IGNORED_PREFIXES):
        return None
    if "://" in ref or "${" in ref or "*" in ref or any(ch.isspace() for ch in ref):
        return None
    path_part = ref.split("?", 1)[0].split("#", 1)[0]
    if not path_part.startswith(("/", "./", "../")):
        return None
    if PurePosixPath(path_part).suffix.lower() not in _RUNTIME_ASSET_SUFFIXES:
        return None
    normalized = _normalize(path_part)
    if not normalized or normalized.startswith("src/") or normalized.startswith("node_modules/"):
        return None
    return path_part


def _refs_in_source(rel: str, source: str) -> set[str]:
    if rel.endswith(".css"):
        return set(_CSS_URL_RE.findall(source))
    if rel.endswith(".html"):
        return set(_HTML_REF_RE.findall(source))
    refs: set[str] = set()
    for line in source.splitlines():
        if _MODULE_SPECIFIER_RE.search(line):
            continue
        refs.update(value for _quote, value in _STRING_LITERAL_RE.findall(line))
    return refs


def _served_file(workspace: Path, rel: str) -> bool:
    if not rel:
        return False
    return any(
        (workspace / root).joinpath(*rel.split("/")).is_file() for root in _ASSET_ROOTS
    )


def _served_basename(workspace: Path, name: str) -> bool:
    for root in _ASSET_ROOTS:
        base = workspace / root
        if base.is_dir() and any(p.name == name for p in base.rglob("*")):
            return True
    return False


def _resolves(workspace: Path, rel: str, path_part: str) -> bool:
    normalized = _normalize(path_part)
    if _served_file(workspace, normalized):
        return True
    if path_part.startswith("/"):
        return False
    # A relative reference resolves against whatever URL the route happens to
    # have, so accept a co-located file or any same-named served asset.
    sibling = _normalize(str(PurePosixPath(rel).parent / path_part))
    if (workspace / sibling).is_file():
        return True
    return _served_basename(workspace, PurePosixPath(normalized).name)


def _is_internal_surface(rel: str) -> bool:
    low = rel.lower()
    return any(marker in low for marker in _INTERNAL_SURFACE_MARKERS)


def _scan_targets(workspace: Path) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    for rel in list_source_files(workspace):
        source = read_file(workspace, rel)
        if source:
            targets.append((rel, source))
    index = workspace / "index.html"
    if index.is_file():
        targets.append(("index.html", index.read_text(encoding="utf-8", errors="replace")))
    return targets


def scan_asset_integrity(workspace: Path) -> AssetIntegrityReport:
    """Report locally-referenced asset paths that no served root can satisfy."""
    workspace = Path(workspace)
    report = AssetIntegrityReport()
    found: dict[str, set[str]] = {}
    for rel, source in _scan_targets(workspace):
        report.scanned.append(rel)
        for raw in _refs_in_source(rel, source):
            path_part = _candidate_ref(raw)
            if path_part is None or _resolves(workspace, rel, path_part):
                continue
            found.setdefault(path_part, set()).add(rel)
    for path_part in sorted(found):
        sources = tuple(sorted(found[path_part]))
        report.missing.append(
            MissingAssetReference(
                path=path_part,
                referenced_by=sources,
                public_surface=not all(_is_internal_surface(s) for s in sources),
            )
        )
    return report


def blocking_missing_assets(
    report: AssetIntegrityReport,
) -> list[MissingAssetReference]:
    """Missing assets bad enough to withhold the preview: public-surface imagery.

    Owner/admin-only breakage is recorded but still worth shipping; a broken
    public hero or card is not.
    """
    return [ref for ref in report.missing if ref.public_surface]


def _quoted_ref_re(path: str) -> re.Pattern[str]:
    return re.compile(r"(['\"])" + re.escape(path) + r"((?:\?[^'\"\s]*)?)\1")


def _replacement_pool(workspace: Path) -> list[str]:
    """Imagery known to load: the app's own slot map, else scaffolded public files."""
    block = _MOCK_IMAGES_BLOCK_RE.search(read_file(workspace, "src/data/mock.ts"))
    urls = _REMOTE_URL_RE.findall(block.group(1)) if block else []
    if urls:
        return urls
    public = workspace / "public"
    if not public.is_dir():
        return []
    return sorted(
        "/" + str(p.relative_to(public)).replace("\\", "/")
        for p in public.rglob("*")
        if p.is_file() and p.suffix.lower() in _RUNTIME_ASSET_SUFFIXES
    )


def repair_missing_asset_references(workspace: Path) -> list[str]:
    """Repoint broken local asset references at imagery the browser can fetch."""
    workspace = Path(workspace)
    report = scan_asset_integrity(workspace)
    if report.ok:
        return []
    pool = _replacement_pool(workspace)
    if not pool:
        return []
    touched: list[str] = []
    for index, ref in enumerate(report.missing):
        replacement = pool[index % len(pool)]
        pattern = _quoted_ref_re(ref.path)
        for rel in ref.referenced_by:
            if not rel.startswith("src/"):
                continue
            source = read_file(workspace, rel)
            fixed = pattern.sub(lambda m: f"{m.group(1)}{replacement}{m.group(1)}", source)
            if fixed != source:
                write_file(workspace, rel, fixed)
                touched.append(rel)
    return list(dict.fromkeys(touched))
