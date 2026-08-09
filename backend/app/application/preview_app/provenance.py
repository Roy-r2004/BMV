"""Phase 3 license policy, enforced in code — the provenance manifest.

`docs/PHASE3_LICENSE_POLICY.md` is the policy; this module is its mechanical
half: the manifest loader, the license allowlist, the validators the guard
pytests run, and the `ATTRIBUTIONS.md` generator (MIT notice preservation).
Stage B cannot start unmanifested — the guards run in the default suite.

Rules mechanized here, straight from the policy:

- Every borrowed file is manifested (`PROVENANCE.json`, one row per file,
  append-only) with a per-file license from the allowlist and a full-SHA pin
  ("a claim without a pin is not provenance").
- The allowlist carries exactly one non-plain-MIT entry:
  ``MIT+Commons-Clause`` (React Bits form, end-product embedding only —
  owner ruling 2026-08-09). Any React Bits row claiming plain ``MIT`` is
  rejected: the bright line is that these components ship only inside
  generated end products, never as a standalone kit.
- Aceternity is GATED — no findable license text; no ruling can cure absence.
  The validator fails any row citing it, so re-admission is a conscious edit
  here, after a human finds actual text.
- No ``package.json`` dependency beyond the frozen Stage-A baseline without a
  manifest row of kind ``dependency`` (Lenis / dotLottie each get one when
  their stage lands them).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.core.config import settings

MANIFEST_NAME = "PROVENANCE.json"
ATTRIBUTIONS_NAME = "ATTRIBUTIONS.md"

#: MIT or strictly more permissive, plus the single owner-ruled exception.
LICENSE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "MIT",
        "ISC",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "0BSD",
        "Unlicense",
        "CC0-1.0",
        # React Bits form, end-product embedding only (owner ruling 2026-08-09).
        "MIT+Commons-Clause",
    }
)

#: The template's dependency names at the Stage-A freeze (dependencies +
#: devDependencies). FROZEN — never append here; a new dependency gets a
#: manifest row of kind "dependency" instead, which is the whole point.
STAGE_A_DEPENDENCY_BASELINE: frozenset[str] = frozenset(
    {
        "@radix-ui/react-dialog",
        "@radix-ui/react-select",
        "@radix-ui/react-tabs",
        "@radix-ui/react-tooltip",
        "@tanstack/react-table",
        "animejs",
        "class-variance-authority",
        "clsx",
        "date-fns",
        "lucide-react",
        "motion",
        "react",
        "react-dom",
        "react-router-dom",
        "recharts",
        "sonner",
        "tailwind-merge",
        "@tailwindcss/vite",
        "@types/node",
        "@types/react",
        "@types/react-dom",
        "@vitejs/plugin-react",
        "tailwindcss",
        "tsx",
        "typescript",
        "vite",
    }
)

_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_GATED_SOURCE_RE = re.compile(r"aceternity", re.IGNORECASE)
_COMMONS_CLAUSE_SOURCE_RE = re.compile(r"react-bits", re.IGNORECASE)


def template_dir() -> Path:
    return Path(settings.PREVIEW_TEMPLATE_DIR)


def manifest_path(root: Path | None = None) -> Path:
    return (root or template_dir()) / MANIFEST_NAME


def attributions_path(root: Path | None = None) -> Path:
    return (root or template_dir()) / ATTRIBUTIONS_NAME


def load_manifest(root: Path | None = None) -> list[dict[str, Any]]:
    """The manifest as committed. Raises on unreadable/JSON-invalid content —
    a broken manifest must never read as an empty (passing) one."""
    data = json.loads(manifest_path(root).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{MANIFEST_NAME} must be a JSON array, got {type(data).__name__}")
    return data


def validate_manifest(
    rows: list[Any], root: Path | None = None
) -> list[str]:
    """Every policy violation in the manifest, as human-readable problems."""
    base = root or template_dir()
    problems: list[str] = []
    for index, row in enumerate(rows):
        where = f"row {index}"
        if not isinstance(row, dict):
            problems.append(f"{where}: not an object")
            continue
        kind = str(row.get("kind") or "component")
        if kind not in {"component", "dependency"}:
            problems.append(f"{where}: unknown kind {kind!r}")
            continue

        license_id = str(row.get("license") or "")
        if license_id not in LICENSE_ALLOWLIST:
            problems.append(f"{where}: license {license_id!r} not in the allowlist")
        source_repo = str(row.get("source_repo") or "")
        if not source_repo:
            problems.append(f"{where}: source_repo is empty")
        if not str(row.get("license_url") or ""):
            problems.append(f"{where}: license_url is empty (a claim without a pin is not provenance)")
        if not str(row.get("retrieved") or ""):
            problems.append(f"{where}: retrieved date is empty")
        if _GATED_SOURCE_RE.search(source_repo):
            problems.append(
                f"{where}: {source_repo} is GATED — no findable license text; "
                "re-admit only after a human check finds actual text"
            )
        if _COMMONS_CLAUSE_SOURCE_RE.search(source_repo) and license_id != "MIT+Commons-Clause":
            problems.append(
                f"{where}: React Bits rows carry 'MIT+Commons-Clause', never {license_id!r}"
            )

        if kind == "dependency":
            if not str(row.get("name") or ""):
                problems.append(f"{where}: dependency row without a name")
            continue

        path = str(row.get("path") or "")
        if not path.startswith("src/ui/"):
            problems.append(f"{where}: path {path!r} is not under src/ui/**")
        elif not (base / path).is_file():
            problems.append(f"{where}: manifested file {path} does not exist")
        if not str(row.get("source_path") or ""):
            problems.append(f"{where}: source_path is empty")
        if not _FULL_SHA_RE.fullmatch(str(row.get("source_commit") or "")):
            problems.append(
                f"{where}: source_commit must be the full 40-hex sha at time of copy"
            )
        if "rewritten" not in row:
            problems.append(f"{where}: rewritten flag missing (the rewrite is the point)")
    return problems


def _package_dependency_names(root: Path | None = None) -> set[str]:
    data = json.loads(((root or template_dir()) / "package.json").read_text(encoding="utf-8"))
    names: set[str] = set()
    for key in ("dependencies", "devDependencies"):
        block = data.get(key)
        if isinstance(block, dict):
            names.update(str(name) for name in block)
    return names


def dependency_delta_problems(
    rows: list[Any],
    dependencies: set[str] | None = None,
    root: Path | None = None,
) -> list[str]:
    """Deps beyond the frozen Stage-A baseline that lack a dependency row."""
    current = dependencies if dependencies is not None else _package_dependency_names(root)
    manifested = {
        str(row.get("name") or "")
        for row in rows
        if isinstance(row, dict) and str(row.get("kind") or "") == "dependency"
    }
    return [
        f"dependency {name!r} entered package.json without a manifest row"
        for name in sorted(current - STAGE_A_DEPENDENCY_BASELINE - manifested)
    ]


def generate_attributions(rows: list[dict[str, Any]]) -> str:
    """`ATTRIBUTIONS.md` content derived from the manifest, deterministically."""
    lines = [
        "# Third-party attributions",
        "",
        "Generated from `PROVENANCE.json` by `app/application/preview_app/provenance.py`",
        "— do not hand-edit; regenerate after any manifest change.",
        "",
    ]
    if not rows:
        lines += [
            "No third-party components are vendored in this template yet. Every",
            "borrowed file Stage B mines gets a manifest row, and this file",
            "regenerates from those rows (MIT notice preservation).",
            "",
        ]
        return "\n".join(lines)

    by_repo: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_repo.setdefault(str(row.get("source_repo") or ""), []).append(row)
    for repo in sorted(by_repo):
        entries = by_repo[repo]
        lines.append(f"## {repo}")
        lines.append("")
        for row in sorted(entries, key=lambda r: str(r.get("path") or r.get("name") or "")):
            license_id = str(row.get("license") or "")
            url = str(row.get("license_url") or "")
            if str(row.get("kind") or "component") == "dependency":
                lines.append(
                    f"- dependency `{row.get('name')}` — {license_id} ([license]({url}))"
                )
                continue
            commit = str(row.get("source_commit") or "")[:12]
            lines.append(
                f"- `{row.get('path')}` — {license_id}, adapted from "
                f"`{row.get('source_path')}` @ `{commit}`, retrieved "
                f"{row.get('retrieved')} ([license]({url}))"
            )
        lines.append("")
    lines += [
        "Portions adapted from the sources above; original copyright and",
        "permission notices are preserved via the license links per row.",
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "ATTRIBUTIONS_NAME",
    "LICENSE_ALLOWLIST",
    "MANIFEST_NAME",
    "STAGE_A_DEPENDENCY_BASELINE",
    "attributions_path",
    "dependency_delta_problems",
    "generate_attributions",
    "load_manifest",
    "manifest_path",
    "template_dir",
    "validate_manifest",
]
