"""Preview safety — Pages."""
from __future__ import annotations

import json
import re

from app.application.preview_app.patterns import _NAV_IMPORT_RE, _NAV_JSX_RE
from app.application.preview_app.workspace import list_source_files, read_file, write_file
from app.infrastructure.logging import get_logger

guard_log = get_logger("SafetyGuards")

def unwrap_route_layout_wrappers(workspace, brand_name: str = "Brand") -> list[str]:
    """Replace page-local legacy layout wrappers with their matching kit shell."""
    fixed: list[str] = []
    wrapper_specs = {
        "PublicLayout": ("PublicShell", f'brandName={{{json.dumps(brand_name or "Brand")}}}'),
        "AdminLayout": (
            "OpsShell",
            f'brandName={{{json.dumps(brand_name or "Brand")}}} navItems={{[]}}',
        ),
    }
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if "/pages/" not in norm or not norm.endswith(".tsx"):
            continue
        content = read_file(workspace, norm)
        updated = content
        added_shells: list[str] = []
        for wrapper, (shell, props) in wrapper_specs.items():
            if not re.search(rf"<{wrapper}\b", updated):
                continue
            updated = re.sub(
                rf"^\s*import\s+{wrapper}\s+from\s+['\"][^'\"]+['\"]\s*;?\s*\n",
                "",
                updated,
                flags=re.MULTILINE,
            )
            updated = re.sub(rf"<{wrapper}(?:\s[^>]*)?>", f"<{shell} {props}>", updated)
            updated = updated.replace(f"</{wrapper}>", f"</{shell}>")
            added_shells.append(shell)
        if added_shells:
            existing = re.search(
                r"import\s*\{([^}]*)\}\s*from\s*['\"]@/ui['\"]\s*;?",
                updated,
            )
            if existing:
                names = [part.strip() for part in existing.group(1).split(",") if part.strip()]
                for shell in added_shells:
                    if shell not in names:
                        names.append(shell)
                replacement = "import { " + ", ".join(names) + " } from '@/ui';"
                updated = updated[:existing.start()] + replacement + updated[existing.end():]
            else:
                updated = (
                    "import { " + ", ".join(added_shells) + " } from '@/ui';\n" + updated
                )
        if updated != content:
            write_file(workspace, norm, updated)
            fixed.append(norm)
    return fixed

def cleanup_page_shells(workspace) -> list[str]:
    """Remove duplicate Nav from pages — PublicLayout already renders it."""
    cleaned: list[str] = []
    for rel in list_source_files(workspace):
        if "/pages/" not in rel.replace("\\", "/"):
            continue
        content = read_file(workspace, rel)
        updated = _NAV_IMPORT_RE.sub("", content)
        updated = _NAV_JSX_RE.sub("", updated)
        if updated != content:
            write_file(workspace, rel, updated)
            cleaned.append(rel)
    return cleaned
