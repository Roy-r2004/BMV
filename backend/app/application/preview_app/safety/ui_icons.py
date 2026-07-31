"""Preview safety — Ui Icons."""
from __future__ import annotations

import re

from app.application.preview_app.patterns import (
    _ICON_MAP_DECL_RE,
    _ICON_MAP_KEY_RE,
    _NAMED_ICONS_IMPORT_RE,
    _NAMED_UIICON_IMPORT_RE,
    _UI_ICON_USAGE_RE,
)
from app.application.preview_app.workspace import list_source_files, read_file, write_file
from app.core.config import settings
from app.infrastructure.logging import get_logger

guard_log = get_logger("SafetyGuards")

def _collect_ui_icon_usages(workspace) -> set[str]:
    """Every literal icon name referenced via `<UiIcon name="...">` across the
    app (excluding the icon-set file itself, which defines names rather than
    using them). Dynamic names (`name={item.icon}`) can't be resolved
    statically and are intentionally skipped — this only catches the common
    case of a page hardcoding an icon key that the icon set never defines.
    """
    names: set[str] = set()
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if norm.endswith("components/uiicons.tsx") or not norm.endswith((".tsx", ".ts")):
            continue
        for m in _UI_ICON_USAGE_RE.finditer(read_file(workspace, rel)):
            names.add(m.group(1).strip().lower())
    return names

def _find_icon_map(content: str) -> tuple[int, int] | None:
    """Locate the icon-name -> JSX map inside a generated UiIcons.tsx.

    Doesn't assume the AI kept the static template's `icons` variable name —
    scans every top-level `const X = { ... }` object literal (brace/string
    aware, since JSX values contain their own braces) and returns the body
    span of the first one that actually contains SVG markup, which
    disambiguates it from unrelated objects like a shared `stroke` props
    object. Returns None if no such map can be found.
    """
    for m in _ICON_MAP_DECL_RE.finditer(content):
        start = m.end()
        depth = 1
        i = start
        in_str: str | None = None
        while i < len(content) and depth > 0:
            ch = content[i]
            if in_str:
                if ch == "\\":
                    i += 1
                elif ch == in_str:
                    in_str = None
            elif ch in ("'", '"', "`"):
                in_str = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            i += 1
        end = i - 1
        if end <= start:
            continue
        if "<svg" in content[start:end]:
            return start, end
    return None

def _icon_map_keys(body: str) -> set[str]:
    keys: set[str] = set()
    for km in _ICON_MAP_KEY_RE.finditer(body):
        key = km.group(1) or km.group(2) or km.group(3)
        if key:
            keys.add(key.strip().lower())
    return keys

def ensure_ui_icon_coverage(workspace) -> list[str]:
    """Guarantee every `<UiIcon name="...">` usage has a matching entry in the
    generated UiIcons.tsx icon map.

    AI-authored icon sets sometimes omit keys that pages actually reference
    (e.g. a page uses `name="dashboard"` but the generated set only defines
    `gauge`) — the lookup then silently renders nothing for that slot: the
    build still passes, the icon is just blank space. This appends a generic
    fallback shape for any missing key (reusing the file's own stroke-prop
    styling when detectable) so every reference renders SOMETHING instead of
    empty space. Purely additive — never touches or removes existing icons.
    """
    target = "src/components/UiIcons.tsx"
    content = read_file(workspace, target)
    if not content.strip():
        return []

    used = _collect_ui_icon_usages(workspace)
    if not used:
        return []

    found = _find_icon_map(content)
    if not found:
        return []
    body_start, body_end = found
    defined = _icon_map_keys(content[body_start:body_end])

    missing = sorted(n for n in used if n and n not in defined and n != "default")
    if not missing:
        return []

    stroke_match = re.search(r"\{\.\.\.(\w+)\}", content)
    stroke_attrs = (
        f"{{...{stroke_match.group(1)}}}" if stroke_match else
        'fill="none" stroke="currentColor" strokeWidth={1.75} '
        'strokeLinecap="round" strokeLinejoin="round"'
    )
    additions = "".join(
        f"  '{key}': (\n"
        f"    <svg viewBox=\"0 0 24 24\" {stroke_attrs}>\n"
        f"      <circle cx=\"12\" cy=\"12\" r=\"8\" />\n"
        f"    </svg>\n"
        f"  ),\n"
        for key in missing
    )
    # `content[:body_end]` ends wherever the last existing entry's value ends
    # — if the AI didn't write a trailing comma after it (valid JS either
    # way, but ours needs one before splicing in more entries), gluing
    # `additions` on directly would concatenate two expressions with no
    # separator (`)\n  'x': (` — invalid object-literal syntax). Detect that
    # and insert the missing comma ourselves rather than assuming it's there.
    head = content[:body_end]
    head_trimmed = head.rstrip()
    if head_trimmed and not head_trimmed.endswith((",", "{")):
        head = head_trimmed + ",\n"
    updated = head + additions + content[body_end:]
    write_file(workspace, target, updated)
    return [f"UiIcons.tsx (+{len(missing)} icon key{'s' if len(missing) != 1 else ''}: {', '.join(missing)})"]

def ensure_ui_icons(workspace) -> bool:
    """Ensure UiIcons exists and exports a default (pages use `import UiIcon from ...`)."""
    target = "src/components/UiIcons.tsx"
    content = read_file(workspace, target).strip()
    changed = False
    if not content:
        source = settings.PREVIEW_TEMPLATE_DIR / "src" / "components" / "UiIcons.tsx"
        if not source.is_file():
            return False
        content = source.read_text(encoding="utf-8")
        changed = True
    if "export default UiIcon" not in content and "export function UiIcon" in content:
        content = content.rstrip() + "\n\nexport default UiIcon;\n"
        changed = True
    # Pages sometimes do `import { UiIcon }` — expose a named export too.
    if "export default UiIcon" in content and "export { UiIcon }" not in content:
        content = content.rstrip() + "\nexport { UiIcon };\n"
        changed = True
    if changed:
        write_file(workspace, target, content)
    return changed

def _icon_export_to_key(name: str) -> str:
    base = re.sub(r"Icon$", "", name.strip())
    if not base:
        return "default"
    return re.sub(r"(?<!^)(?=[A-Z])", "-", base).lower().replace("_", "-")

def _collect_named_ui_icon_imports(workspace) -> set[str]:
    names: set[str] = set()
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts", ".jsx", ".js")):
            continue
        if norm.endswith("components/UiIcons.tsx"):
            continue
        for m in _NAMED_ICONS_IMPORT_RE.finditer(read_file(workspace, rel)):
            for part in m.group(1).split(","):
                token = part.strip()
                if not token or token.startswith("type ") or token.startswith("typeof "):
                    continue
                ident = token.split()[0]
                if " as " in f" {token} ":
                    # `Foo as Bar` — export name used in file is the alias (Bar)
                    bits = re.split(r"\s+as\s+", token, maxsplit=1)
                    ident = bits[-1].strip().split()[0] if bits else ident
                if ident == "UiIcon":
                    continue
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", ident):
                    names.add(ident)
    return names

def ensure_named_ui_icon_exports(workspace) -> list[str]:
    """Add missing named `*Icon` re-exports wrapping default `UiIcon`.

    Prevents Vite MISSING_EXPORT when pages import `{ CalendarIcon }` etc.
    """
    needed = sorted(_collect_named_ui_icon_imports(workspace))
    if not needed:
        return []

    target = "src/components/UiIcons.tsx"
    content = read_file(workspace, target)
    if not content.strip():
        if not ensure_ui_icons(workspace):
            return []
        content = read_file(workspace, target)

    missing = [
        n for n in needed
        if not re.search(rf"export\s+(?:function|const)\s+{re.escape(n)}\b", content)
        and f"export {{ {n}" not in content
        and f"export {{{n}" not in content
    ]
    if not missing:
        return []

    if "function UiIcon" not in content and "UiIcon =" not in content:
        ensure_ui_icons(workspace)
        content = read_file(workspace, target)

    additions = []
    for name in missing:
        key = _icon_export_to_key(name)
        additions.append(
            f"\nexport function {name}({{ className = 'w-5 h-5' }}: {{ className?: string }}) {{\n"
            f"  return <UiIcon name={{'{key}'}} className={{className}} />;\n"
            f"}}\n"
        )
    write_file(workspace, target, content.rstrip() + "\n" + "".join(additions))
    try:
        ensure_ui_icon_coverage(workspace)
    except Exception:
        pass
    return [f"UiIcons.tsx (named exports: {', '.join(missing)})"]

#: Any relative import of the icon component, singular or plural, default or named.
_ICON_MODULE_IMPORT_RE = re.compile(
    r"import\s+(?:UiIcon|\{\s*UiIcon\s*\})\s+from\s+"
    r"['\"][^'\"]*components/UiIcons?['\"]\s*;?"
)


def normalize_kit_icon_imports(workspace) -> list[str]:
    """Point every `UiIcon` import at `@/ui`, whatever path the model invented.

    Request 47's artwork page wrote `from '../components/UiIcon'` — singular, and
    no such module — for a TS2307 that failed the page. The kit re-exports `UiIcon`,
    the prompt already says to import page UI exclusively from `@/ui`, and this is
    the one module name the model gets wrong often enough to be worth a codemod.
    Runs for catalogue workspaces too, where the standalone-component repairs do not.
    """
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")) or not norm.startswith("src/pages/"):
            continue
        content = read_file(workspace, rel)
        if "UiIcon" not in content:
            continue
        updated, n = _ICON_MODULE_IMPORT_RE.subn("import { UiIcon } from '@/ui';", content)
        if n:
            write_file(workspace, rel, updated)
            fixed.append(norm)
    return fixed


def normalize_ui_icon_imports(workspace) -> list[str]:
    """Rewrite `import { UiIcon } from '...UiIcons'` → default import."""
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts")):
            continue
        content = read_file(workspace, rel)
        new_content, n = _NAMED_UIICON_IMPORT_RE.subn(
            r"import UiIcon from \1;",
            content,
        )
        if n:
            write_file(workspace, rel, new_content)
            fixed.append(norm)
    return fixed
