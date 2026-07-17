"""Preview safety — Imports."""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path, PurePosixPath

from app.application.preview_app.patterns import (
    _ALLOWED_NPM_IMPORTS,
    _CURATED_UI_NPM_IMPORTS,
    _FORBIDDEN_RUNTIME_IMPORT_LINE_RE,
    _HEADLESS_SYMBOLS,
    _IMPORT_FROM_RE,
    _ROUTER_SYMBOLS,
    _SIDE_EFFECT_IMPORT_RE,
    _STATIC_UI_IMPORT_RE,
    _STUBBED_NPM_IMPORTS,
    strip_ts_comments_and_strings as _strip_ts_comments_and_strings,
)
from app.application.preview_app.workspace import (
    list_source_files,
    read_file,
    write_file,
    write_trusted_contained_file,
)
from app.application.ui_catalogue import load_catalogue
from app.core.config import settings
from app.infrastructure.logging import get_logger

guard_log = get_logger("SafetyGuards")

def _npm_package_name(spec: str) -> str:
    if spec.startswith("@"):
        parts = spec.split("/")
        return "/".join(parts[:2]) if len(parts) >= 2 else spec
    return spec.split("/")[0]

def _rel_to_stub(from_file: str, stub_abs: str = "src/components/UiHeadless") -> str:
    """Relative import path from a source file to the UiHeadless stub (no extension)."""
    start = PurePosixPath(from_file.replace("\\", "/")).parent
    target = PurePosixPath(stub_abs)
    rel = PurePosixPath(os.path.relpath(str(target), str(start))).as_posix()
    if not rel.startswith("."):
        rel = "./" + rel
    return rel

def ensure_ui_headless_file(workspace) -> bool:
    """Copy UiHeadless.tsx from the preview template into the workspace."""
    source = settings.PREVIEW_TEMPLATE_DIR / "src" / "components" / "UiHeadless.tsx"
    dest = Path(workspace) / "src" / "components" / "UiHeadless.tsx"
    if not source.is_file():
        return False
    text = source.read_text(encoding="utf-8")
    if (
        dest.is_file()
        and not dest.is_symlink()
        and dest.read_text(encoding="utf-8") == text
    ):
        return False
    write_trusted_contained_file(
        workspace,
        "src/components/UiHeadless.tsx",
        text,
    )
    return True

def _safe_workspace_destination(workspace, rel: str) -> Path:
    """Resolve an approved source destination without following escapes/symlink parents."""
    root = Path(workspace).resolve()
    normalized = rel.replace("\\", "/")
    if not (
        normalized.startswith("src/ui/")
        or normalized == "src/components/UiIcons.tsx"
        or normalized == "src/lib/preview-bridge.ts"
        or normalized == "src/lib/app-nav.ts"
        or normalized == "src/lib/recipe-id.ts"
        or normalized == "src/lib/recipe.ts"
    ):
        raise ValueError(f"Refusing non-kit restore path: {rel}")
    target = root.joinpath(*normalized.split("/"))
    parent = target.parent
    existing = parent
    while not existing.exists() and existing != root:
        existing = existing.parent
    if existing.is_symlink():
        raise ValueError(f"Refusing kit restore through symlink: {rel}")
    resolved_parent = existing.resolve()
    try:
        resolved_parent.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Refusing kit restore outside workspace: {rel}") from exc
    return target

def restore_curated_ui_kit(workspace) -> list[str]:
    """Restore the canonical template UI barrel and icon set into a workspace."""
    template_root = settings.PREVIEW_TEMPLATE_DIR.resolve()
    source_ui = template_root / "src" / "ui"
    source_icons = template_root / "src" / "components" / "UiIcons.tsx"
    required_files = (
        source_ui / "catalogue.json",
        source_ui / "registry.ts",
        source_ui / "index.ts",
        source_ui / "compose" / "SkeletonComposer.tsx",
        source_ui / "lib" / "AppLink.tsx",
        source_icons,
    )
    required_dirs = tuple(
        source_ui / name for name in ("core", "public", "ops", "motion", "lib")
    )
    missing = [
        str(path)
        for path in required_files
        if not path.is_file()
    ] + [
        str(path)
        for path in required_dirs
        if not path.is_dir()
    ]
    if missing:
        raise FileNotFoundError(
            "Canonical curated UI kit is incomplete; missing: "
            + ", ".join(missing)
        )

    root = Path(workspace).resolve()
    destination_ui = _safe_workspace_destination(root, "src/ui/index.ts").parent
    destination_icons = _safe_workspace_destination(root, "src/components/UiIcons.tsx")
    changed: list[str] = []

    canonical: dict[str, Path] = {}
    for source in sorted(path for path in source_ui.rglob("*") if path.is_file()):
        rel = "src/ui/" + source.relative_to(source_ui).as_posix()
        canonical[rel] = source

    if destination_ui.exists():
        for current in sorted(
            (path for path in destination_ui.rglob("*") if path.is_file() or path.is_symlink()),
            reverse=True,
        ):
            rel = "src/ui/" + current.relative_to(destination_ui).as_posix()
            if rel not in canonical:
                try:
                    if current.is_dir() and not current.is_symlink():
                        shutil.rmtree(current)
                    else:
                        current.unlink()
                except OSError as exc:
                    raise RuntimeError(
                        f"Failed to remove drifted curated UI path {rel}"
                    ) from exc
                changed.append(rel)

    for rel, source in canonical.items():
        try:
            destination = _safe_workspace_destination(root, rel)
            payload = source.read_bytes()
            if (
                destination.is_symlink()
                or not destination.is_file()
                or destination.read_bytes() != payload
            ):
                write_trusted_contained_file(root, rel, payload)
                changed.append(rel)
        except OSError as exc:
            raise RuntimeError(f"Failed to restore curated UI path {rel}") from exc

    try:
        icon_text = source_icons.read_text(encoding="utf-8")
        if (
            destination_icons.is_symlink()
            or not destination_icons.is_file()
            or destination_icons.read_text(encoding="utf-8") != icon_text
        ):
            write_trusted_contained_file(
                root,
                "src/components/UiIcons.tsx",
                icon_text,
            )
            changed.append("src/components/UiIcons.tsx")
    except OSError as exc:
        raise RuntimeError("Failed to restore curated UI icon set") from exc

    source_bridge = template_root / "src" / "lib" / "preview-bridge.ts"
    if not source_bridge.is_file():
        raise FileNotFoundError(
            f"Canonical preview bridge missing: {source_bridge}"
        )
    try:
        bridge_text = source_bridge.read_text(encoding="utf-8")
        destination_bridge = _safe_workspace_destination(
            root, "src/lib/preview-bridge.ts"
        )
        if (
            destination_bridge.is_symlink()
            or not destination_bridge.is_file()
            or destination_bridge.read_text(encoding="utf-8") != bridge_text
        ):
            write_trusted_contained_file(
                root,
                "src/lib/preview-bridge.ts",
                bridge_text,
            )
            changed.append("src/lib/preview-bridge.ts")
    except OSError as exc:
        raise RuntimeError("Failed to restore preview bridge") from exc

    source_app_nav = template_root / "src" / "lib" / "app-nav.ts"
    if source_app_nav.is_file():
        try:
            app_nav_text = source_app_nav.read_text(encoding="utf-8")
            destination_app_nav = _safe_workspace_destination(
                root, "src/lib/app-nav.ts"
            )
            if (
                destination_app_nav.is_symlink()
                or not destination_app_nav.is_file()
                or destination_app_nav.read_text(encoding="utf-8") != app_nav_text
            ):
                write_trusted_contained_file(
                    root,
                    "src/lib/app-nav.ts",
                    app_nav_text,
                )
                changed.append("src/lib/app-nav.ts")
        except OSError as exc:
            raise RuntimeError("Failed to restore shared app-nav helpers") from exc

    source_recipe_id = template_root / "src" / "lib" / "recipe-id.ts"
    if source_recipe_id.is_file():
        try:
            destination_recipe = _safe_workspace_destination(root, "src/lib/recipe-id.ts")
            if destination_recipe.is_symlink() or not destination_recipe.is_file():
                write_trusted_contained_file(
                    root,
                    "src/lib/recipe-id.ts",
                    source_recipe_id.read_text(encoding="utf-8"),
                )
                changed.append("src/lib/recipe-id.ts")
        except OSError as exc:
            raise RuntimeError("Failed to restore recipe-id bootstrap") from exc

    source_recipe = template_root / "src" / "lib" / "recipe.ts"
    if source_recipe.is_file():
        try:
            recipe_text = source_recipe.read_text(encoding="utf-8")
            destination_recipe_helpers = _safe_workspace_destination(root, "src/lib/recipe.ts")
            if (
                destination_recipe_helpers.is_symlink()
                or not destination_recipe_helpers.is_file()
                or destination_recipe_helpers.read_text(encoding="utf-8") != recipe_text
            ):
                write_trusted_contained_file(root, "src/lib/recipe.ts", recipe_text)
                changed.append("src/lib/recipe.ts")
        except OSError as exc:
            raise RuntimeError("Failed to restore recipe helpers") from exc

    return list(dict.fromkeys(changed))

def _is_ui_kit_source(source: str, from_file: str) -> bool:
    if source == "@/ui" or source.startswith("@/ui/"):
        return True
    component_names = {
        str(item.get("name") or "").lower()
        for item in load_catalogue().get("components") or []
    }
    source_stem = PurePosixPath(source).name.lower()
    if (
        source_stem in component_names
        and (
            source.startswith("@/components/ui/")
            or source.startswith("@/components/")
            or source.startswith("@/ui-components/")
        )
    ):
        return True
    if not source.startswith("."):
        return False
    base = PurePosixPath(from_file.replace("\\", "/")).parent
    joined = PurePosixPath(os.path.normpath(str(base / source)).replace("\\", "/")).as_posix()
    return (
        joined == "src/ui"
        or joined.startswith("src/ui/")
        or (
            source_stem in component_names
            and (
                joined.startswith("src/components/ui/")
                or joined.startswith("src/ui-components/")
            )
        )
    )

def _is_ui_barrel_source(source: str, from_file: str) -> bool:
    if source in {"@/ui", "@/ui/index"}:
        return True
    if not source.startswith("."):
        return False
    base = PurePosixPath(from_file.replace("\\", "/")).parent
    joined = PurePosixPath(os.path.normpath(str(base / source)).replace("\\", "/")).as_posix()
    return joined in {"src/ui", "src/ui/index"}

def _ui_barrel_exports() -> set[str]:
    """Read the canonical barrel's named exports for safe deep-import conversion."""
    source = settings.PREVIEW_TEMPLATE_DIR / "src" / "ui" / "index.ts"
    content = source.read_text(encoding="utf-8") if source.is_file() else ""
    exported: set[str] = {
        str(item.get("name") or "")
        for item in load_catalogue().get("components") or []
        if item.get("name")
    }
    for match in re.finditer(r"export\s*\{([\s\S]*?)\}\s*from\s*['\"]", content):
        for item in match.group(1).split(","):
            token = re.sub(r"^\s*type\s+", "", item.strip())
            if not token:
                continue
            exported_name = re.split(r"\s+as\s+", token)[-1].strip()
            if re.match(r"^[A-Za-z_$][\w$]*$", exported_name):
                exported.add(exported_name)
    return exported

def _split_ui_import_clause(
    clause: str,
    source: str,
    exports: set[str],
    *,
    barrel_source: bool,
) -> tuple[list[str], list[str], bool, bool, str]:
    """Return value/type specs, unsupported/preserve flags, and namespace alias."""
    raw = clause.strip()
    whole_type = raw.startswith("type ")
    if whole_type:
        raw = raw[5:].strip()

    namespace = re.fullmatch(r"\*\s+as\s+([A-Za-z_$][\w$]*)", raw)
    if namespace:
        if barrel_source and not whole_type:
            preserve = source == "@/ui"
            return [], [], False, preserve, "" if preserve else namespace.group(1)
        return [], [], True, False, ""

    default_name = ""
    named_body = ""
    if "{" in raw and "}" in raw:
        before, remainder = raw.split("{", 1)
        named_body = remainder.rsplit("}", 1)[0]
        default_name = before.strip().rstrip(",").strip()
    else:
        default_name = raw

    values: list[str] = []
    types: list[str] = []
    unsupported = False

    if default_name:
        if (
            whole_type
            or not re.match(r"^[A-Za-z_$][\w$]*$", default_name)
        ):
            unsupported = True
        else:
            exported_name = PurePosixPath(source).name.rsplit(".", 1)[0]
            if exported_name in exports:
                spec = (
                    exported_name
                    if default_name == exported_name
                    else f"{exported_name} as {default_name}"
                )
                values.append(spec)
            else:
                unsupported = True

    if named_body:
        for raw_item in named_body.split(","):
            item = raw_item.strip()
            if not item:
                continue
            item_type = whole_type or item.startswith("type ")
            if item.startswith("type "):
                item = item[5:].strip()
            parts = re.split(r"\s+as\s+", item, maxsplit=1)
            imported = parts[0].strip()
            local = parts[1].strip() if len(parts) == 2 else imported
            if (
                imported not in exports
                or not re.match(r"^[A-Za-z_$][\w$]*$", local)
            ):
                unsupported = True
                continue
            spec = imported if imported == local else f"{imported} as {local}"
            (types if item_type else values).append(spec)
    return values, types, unsupported, False, ""

def normalize_ui_kit_imports(workspace) -> list[str]:
    """Collapse representable UI imports to the barrel and remove unsafe deep forms."""
    touched: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")) or norm.startswith("src/ui/"):
            continue
        content = read_file(workspace, norm)
        matches = [
            match
            for match in _STATIC_UI_IMPORT_RE.finditer(content)
            if _is_ui_kit_source(match.group("source"), norm)
        ]
        if not matches:
            continue

        exports = _ui_barrel_exports()
        mergeable: list[tuple[re.Match, list[str], list[str], bool, str]] = []
        for match in matches:
            values, types, unsupported, root_namespace, namespace_alias = _split_ui_import_clause(
                match.group("clause"),
                match.group("source"),
                exports,
                barrel_source=_is_ui_barrel_source(match.group("source"), norm),
            )
            if root_namespace:
                continue
            mergeable.append((match, values, types, unsupported, namespace_alias))
        if not mergeable:
            continue

        value_names: list[str] = []
        type_names: list[str] = []
        namespace_names: list[str] = []
        unsupported = False
        for _match, values, types, invalid, namespace_alias in mergeable:
            unsupported = unsupported or invalid
            if namespace_alias and namespace_alias not in namespace_names:
                namespace_names.append(namespace_alias)
            for name in values:
                if name not in value_names:
                    value_names.append(name)
            for name in types:
                if name not in type_names:
                    type_names.append(name)

        if (
            len(mergeable) == 1
            and mergeable[0][0].group("source") == "@/ui"
            and not unsupported
        ):
            continue

        replacement_lines: list[str] = []
        replacement_lines.extend(
            f"import * as {name} from '@/ui';" for name in namespace_names
        )
        if value_names:
            replacement_lines.append(f"import {{ {', '.join(value_names)} }} from '@/ui';")
        if type_names:
            replacement_lines.append(f"import type {{ {', '.join(type_names)} }} from '@/ui';")
        if unsupported:
            replacement_lines.append("/* removed unsupported deep UI import */")
        replacement = "\n".join(replacement_lines)
        if replacement:
            replacement += "\n"

        pieces: list[str] = []
        cursor = 0
        for index, (match, _values, _types, _invalid, _namespace) in enumerate(mergeable):
            pieces.append(content[cursor:match.start()])
            if index == 0:
                pieces.append(replacement)
            cursor = match.end()
        pieces.append(content[cursor:])
        updated = "".join(pieces)
        write_file(workspace, norm, updated)
        touched.append(norm)
    return touched

def strip_forbidden_npm_imports(workspace) -> list[str]:
    """Rewrite stubbable illegal imports; strip the rest.

    Models often import @headlessui/react / framer-motion. Deleting those lines
    used to leave `<Transition>` / `<Dialog>` unbound → runtime white screen
    even though `vite build` succeeded. Stubbable packages are rewritten to
    `src/components/UiHeadless`; unknown packages are still stripped.

    Also strips side-effect CSS/JS imports (`import 'pkg/dist/x.css'`) which
    `_IMPORT_FROM_RE` does not match and which otherwise fail Vite resolve.
    """
    ensure_ui_headless_file(workspace)
    touched: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        if norm.endswith("UiHeadless.tsx"):
            continue
        content = read_file(workspace, rel)
        updated = content
        changed = False

        template_ui = (
            norm.startswith("src/ui/")
            or norm.lower() == "src/components/uiicons.tsx"
        )

        def _should_keep(src: str) -> bool:
            if (
                src.startswith(".")
                or src.startswith("/")
                or src.startswith("@/")
                or src.startswith("~/")
            ):
                return True
            if src.startswith(("http://", "https://")):
                return False
            pkg = _npm_package_name(src)
            if template_ui:
                return pkg in _CURATED_UI_NPM_IMPORTS
            return pkg in _ALLOWED_NPM_IMPORTS or src in _ALLOWED_NPM_IMPORTS

        for m in list(_IMPORT_FROM_RE.finditer(content)):
            src = m.group(1)
            if _should_keep(src):
                continue
            pkg = _npm_package_name(src)
            stub_target = _STUBBED_NPM_IMPORTS.get(src) or _STUBBED_NPM_IMPORTS.get(pkg)
            if stub_target:
                rel_imp = _rel_to_stub(norm, stub_target)
                old = m.group(0)
                new = re.sub(
                    r"""from\s+['"][^'"]+['"]""",
                    f"from '{rel_imp}'",
                    old,
                )
                if new != old and old in updated:
                    updated = updated.replace(old, new, 1)
                    changed = True
                continue
            old = m.group(0)
            if old in updated:
                updated = updated.replace(old, "/* removed forbidden import */\n", 1)
                changed = True

        for m in list(_SIDE_EFFECT_IMPORT_RE.finditer(updated)):
            src = m.group(1)
            if _should_keep(src):
                continue
            old = m.group(0)
            if old in updated:
                updated = updated.replace(old, "/* removed forbidden side-effect import */\n", 1)
                changed = True

        if not template_ui:
            scrubbed = _strip_ts_comments_and_strings(updated)
            spans = [
                (match.start(), match.end())
                for match in _FORBIDDEN_RUNTIME_IMPORT_LINE_RE.finditer(scrubbed)
            ]
            for start, end in reversed(spans):
                newline = "\n" if updated[start:end].endswith(("\n", "\r\n")) else ""
                updated = (
                    updated[:start]
                    + "/* removed forbidden runtime import */"
                    + newline
                    + updated[end:]
                )
                changed = True

        if changed and updated != content:
            write_file(workspace, norm, updated)
            guard_log.debug("npm imports rewritten/stripped in %s", norm)
            touched.append(norm)
    return touched

def ensure_headless_stub_imports(workspace) -> list[str]:
    """Inject UiHeadless imports when Transition/Dialog/motion are used unbound.

    Covers the case where a prior build already stripped the headless import
    (comment left behind) and the page still references the symbols.
    """
    ensure_ui_headless_file(workspace)
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        if (
            norm.startswith("src/data/")
            or norm.startswith("src/ui/")
            or norm.endswith("UiHeadless.tsx")
            or norm.lower() == "src/components/uiicons.tsx"
        ):
            continue
        content = read_file(workspace, rel)
        needed: list[str] = []
        for sym in _HEADLESS_SYMBOLS:
            # JSX tag or compound API (Dialog.Panel) — not prose like "Member Portal."
            used = bool(
                re.search(rf"<{sym}\b", content)
                or re.search(rf"\b{sym}\.[A-Za-z]", content)
                or (sym == "motion" and re.search(r"\bmotion\.[a-z]", content))
                or (sym == "useAnimation" and re.search(r"\buseAnimation\s*\(", content))
            )
            if not used:
                continue
            imported = bool(
                re.search(
                    rf"import\s+[^;]*\b{sym}\b[^;]*from\s+['\"][^'\"]+['\"]",
                    content,
                )
            )
            if not imported:
                needed.append(sym)
        if not needed:
            continue
        # Deduplicate while preserving order
        ordered: list[str] = []
        for s in needed:
            if s not in ordered:
                ordered.append(s)
        rel_imp = _rel_to_stub(norm)
        inject = f"import {{ {', '.join(ordered)} }} from '{rel_imp}';\n"
        # Prefer after the last import; else top of file
        last_imp = None
        for m in re.finditer(r"^(?:import\s.+?;|/\* removed forbidden import \*/)\s*$", content, re.MULTILINE):
            last_imp = m
        if last_imp:
            at = last_imp.end()
            if not content[at:].startswith("\n"):
                inject = "\n" + inject
            updated = content[:at] + "\n" + inject + content[at:].lstrip("\n")
        else:
            updated = inject + content
        write_file(workspace, norm, updated)
        fixed.append(norm)
        guard_log.debug("injected UiHeadless imports in %s: %s", norm, ", ".join(ordered))
    return fixed

def ensure_react_default_import(workspace) -> list[str]:
    """Add `import React` when files use runtime `React.*` (e.g. cloneElement).

    Vite's automatic JSX runtime does not inject a React binding, so
    `React.cloneElement` / `React.FC` value usage crashes with a blank page
    (`React is not defined`) even though `vite build` succeeds.
    """
    fixed: list[str] = []
    react_use = re.compile(r"\bReact\.")
    has_default = re.compile(r"import\s+React\b|import\s*\*\s*as\s+React\b")
    named_only = re.compile(r"import\s*\{([^}]*)\}\s*from\s*['\"]react['\"]\s*;?")
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        content = read_file(workspace, rel)
        if not react_use.search(content) or has_default.search(content):
            continue
        m = named_only.search(content)
        if m:
            new_imp = f"import React, {{ {m.group(1).strip()} }} from 'react';"
            content = content[: m.start()] + new_imp + content[m.end() :]
        else:
            content = "import React from 'react';\n" + content
        write_file(workspace, rel, content)
        fixed.append(norm)
        guard_log.debug("added React import in %s", norm)
    return fixed

def ensure_react_router_imports(workspace) -> list[str]:
    """Add missing react-router-dom named imports when JSX/hooks use them.

    Models often use `<Link>` in layouts/footers without importing it — that
    builds fine under Vite (no typecheck in `vite build`) then crashes at
    runtime with a blank white screen (`Link is not defined`).
    """
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        content = read_file(workspace, rel)
        needed: list[str] = []
        for sym in _ROUTER_SYMBOLS:
            used = bool(re.search(rf"<\s*{sym}[\s/>]", content)) or bool(
                re.search(rf"\b{sym}\s*\(", content)
            )
            if not used:
                continue
            if re.search(
                rf"import\s*{{[^}}]*\b{sym}\b[^}}]*}}\s*from\s*['\"]react-router-dom['\"]",
                content,
            ):
                continue
            needed.append(sym)
        if not needed:
            continue
        m = re.search(
            r"import\s*\{([^}]*)\}\s*from\s*['\"]react-router-dom['\"]\s*;?",
            content,
        )
        if m:
            existing = {p.strip() for p in m.group(1).split(",") if p.strip()}
            merged = sorted(existing | set(needed))
            new_imp = "import { " + ", ".join(merged) + " } from 'react-router-dom';"
            content = content[: m.start()] + new_imp + content[m.end() :]
        else:
            content = "import { " + ", ".join(needed) + " } from 'react-router-dom';\n" + content
        write_file(workspace, rel, content)
        fixed.append(norm)
        guard_log.debug("added react-router imports in %s: %s", norm, ", ".join(needed))
    return fixed

def rewrite_invented_component_imports(workspace) -> list[str]:
    """Route generated deep UI imports through the curated public barrel."""
    return normalize_ui_kit_imports(workspace)

def sanitize_ui_component_apis(workspace) -> list[str]:
    """Remove a small set of known invented props without reshaping page content."""
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith(".tsx") or norm.startswith("src/ui/"):
            continue
        content = read_file(workspace, norm)
        updated = re.sub(r"\s+Icon=\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", "", content)
        updated = re.sub(r'\bsize=(["\'])(?:xs|md|xl)\1', 'size="default"', updated)
        if updated != content:
            write_file(workspace, norm, updated)
            fixed.append(norm)
    return fixed
