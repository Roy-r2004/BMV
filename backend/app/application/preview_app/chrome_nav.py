"""Deterministic shared chrome wiring for catalogue preview pages."""
from __future__ import annotations

import re

from app.application.preview_app.catalogue_contract import catalogue_route_for_file
from app.application.preview_app.protected_paths import has_catalogue_routes
from app.application.preview_app.workspace import list_source_files, read_file, write_file

_APP_NAV_IMPORT_RE = re.compile(
    r"^import \{[^}]*\} from ['\"]@/lib/app-nav['\"];\s*\n",
    re.MULTILINE,
)
_NESTED_APP_NAV_RE = re.compile(
    r"import \{\s*\nimport \{[^}]+\} from ['\"]@/lib/app-nav['\"];\s*\n",
)
_ADMIN_NAV_CONST_RE = re.compile(
    r"\nconst ADMIN_NAV\s*=\s*\[[\s\S]*?\];\n",
)
_ADMIN_NAV_ITEMS_ASSIGN_RE = re.compile(
    r"^[ \t]*const adminNavItems\s*=\s*.*?;\s*\n",
    re.MULTILINE,
)
_PUBLIC_NAV_ITEMS_ASSIGN_RE = re.compile(
    r"^[ \t]*const navItems\s*=\s*use(?:Public|Member)NavItems\(\);\s*\n",
    re.MULTILINE,
)
_PUBLIC_NAV_CTA_ASSIGN_RE = re.compile(
    r"^[ \t]*const navCta\s*=\s*(?:public|member)Cta\(\);\s*\n",
    re.MULTILINE,
)


def _end_of_imports(src: str) -> int:
    idx = 0
    pos = 0
    while True:
        match = re.match(
            r"\s*(?:import[\s\S]*?;[ \t]*(?://[^\n]*)?\n?|/\*[\s\S]*?\*/\s*|//[^\n]*\n)",
            src[pos:],
        )
        if not match:
            break
        chunk = match.group(0)
        if chunk.lstrip().startswith("import"):
            idx = pos + len(chunk)
        pos += len(chunk)
        if pos >= len(src):
            break
    return idx


def _ensure_import_line(src: str, line: str) -> str:
    # Remove any existing app-nav imports, including ones glued onto prior lines.
    src = re.sub(
        r"[ \t]*import \{[^}]*\} from ['\"]@/lib/app-nav['\"];[ \t]*",
        "",
        src,
    )
    src = _NESTED_APP_NAV_RE.sub("import {\n", src)
    insert = line if line.endswith("\n") else f"{line}\n"
    if "from '@/lib/app-nav'" in src or 'from "@/lib/app-nav"' in src:
        return src
    at = _end_of_imports(src)
    # Prefer inserting on its own line.
    prefix = "" if (at == 0 or src[at - 1] == "\n") else "\n"
    return src[:at] + prefix + insert + src[at:]


def _inject_in_component(src: str, body: str) -> str:
    return re.sub(
        r"(export default function \w+\(\)\s*\{)\n?",
        r"\1\n" + body + "\n",
        src,
        count=1,
    )


def _ensure_named_ui_import(src: str, name: str) -> str:
    pattern = (
        r"import\s*\{[^}]*\b"
        + re.escape(name)
        + r"\b[^}]*\}\s*from\s*['\"]@/ui['\"]"
    )
    if re.search(rf"\b{re.escape(name)}\b", src) and re.search(pattern, src):
        return src

    def add(match: re.Match[str]) -> str:
        clause = match.group(1)
        if name in clause:
            return match.group(0)
        cleaned = clause.strip().rstrip(",")
        return f"import {{ {cleaned}, {name} }} from '@/ui'"

    if "from '@/ui'" in src or 'from "@/ui"' in src:
        return re.sub(r"import \{([^}]+)\} from ['\"]@/ui['\"]", add, src, count=1)
    return _ensure_import_line(src, f"import {{ {name} }} from '@/ui';")


def _is_member_page(file_path: str, route: dict) -> bool:
    path = str(route.get("path") or "")
    role = str(route.get("role_id") or "").lower()
    norm = file_path.replace("\\", "/")
    if "/pages/member/" in norm or path.startswith("/member"):
        return True
    if role == "member" and ("dashboard" in path or "history" in path or "profile" in path):
        return True
    return False


def _replace_nav_items_prop(src: str) -> str:
    """Replace OpsShell navItems={...} even when the value contains nested braces."""
    out: list[str] = []
    i = 0
    token = "navItems={"
    while i < len(src):
        start = src.find(token, i)
        if start < 0:
            out.append(src[i:])
            break
        out.append(src[i:start])
        depth = 0
        j = start + len(token) - 1  # at '{'
        while j < len(src):
            ch = src[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        out.append("navItems={adminNavItems}")
        i = j
    return "".join(out)


def _rewrite_ops_page(src: str) -> str:
    src = _ADMIN_NAV_CONST_RE.sub("\n", src)
    src = _ADMIN_NAV_ITEMS_ASSIGN_RE.sub("", src)
    src = _ensure_import_line(src, "import { useAdminNavItems } from '@/lib/app-nav';")
    src = _inject_in_component(src, "  const adminNavItems = useAdminNavItems();")
    src = _replace_nav_items_prop(src)
    # OpsShell without navItems yet
    if "<OpsShell" in src and "navItems=" not in src:
        src = re.sub(
            r"(<OpsShell\b[^>]*brandName=\{[^}]+\})",
            r"\1 navItems={adminNavItems}",
            src,
            count=1,
        )
    return src


def _rewrite_public_page(src: str, *, member: bool) -> str:
    hook = "useMemberNavItems" if member else "usePublicNavItems"
    cta = "memberCta" if member else "publicCta"
    src = _PUBLIC_NAV_ITEMS_ASSIGN_RE.sub("", src)
    src = _PUBLIC_NAV_CTA_ASSIGN_RE.sub("", src)
    src = re.sub(r"\n\s*const primaryNavItems\s*=\s*\[[\s\S]*?\];\n", "\n", src)
    src = _ensure_import_line(src, f"import {{ {hook}, {cta} }} from '@/lib/app-nav';")
    src = _ensure_named_ui_import(src, "PublicNav")
    src = _inject_in_component(
        src,
        f"  const navItems = {hook}();\n  const navCta = {cta}();",
    )
    src = re.sub(
        r"brandName=\{([A-Za-z0-9_?.]+)\s+nav=\{",
        r"brandName={\1} nav={",
        src,
    )
    # Always normalize every PublicNav usage to the shared hook outputs.
    src = re.sub(
        r"<PublicNav\b[^>]*/>",
        "<PublicNav items={navItems} cta={navCta} />",
        src,
    )
    src = re.sub(
        r"<PublicNav\b[\s\S]*?</PublicNav>",
        "<PublicNav items={navItems} cta={navCta} />",
        src,
    )
    # Object-form nav={{ items, cta }}
    src = re.sub(
        r"nav=\{\{\s*items\s*:\s*\[[\s\S]*?\}\s*\}\}",
        "nav={<PublicNav items={navItems} cta={navCta} />}",
        src,
        count=1,
    )
    if not re.search(r"<PublicShell\b[\s\S]*?\bnav=", src):
        src = re.sub(
            r"(<PublicShell\b[^>]*brandName=\{[^}]+\})",
            r"\1 nav={<PublicNav items={navItems} cta={navCta} />}",
            src,
            count=1,
        )
        # Multiline PublicShell without brandName on same line
        if not re.search(r"<PublicShell\b[\s\S]*?\bnav=", src):
            src = re.sub(
                r"(<PublicShell\b)(\s|>)",
                r"\1 nav={<PublicNav items={navItems} cta={navCta} />}\2",
                src,
                count=1,
            )
    return src


def rewrite_page_shared_chrome(file_path: str, content: str, route: dict) -> str:
    """Force catalogue pages onto the shared app-nav chrome contract."""
    if "OpsShell" in content:
        if (
            "const adminNavItems = useAdminNavItems()" in content
            and "navItems={adminNavItems}" in content
            and content.count("useAdminNavItems") >= 2  # import + call
            and "ADMIN_NAV" not in content
            and "from '@/lib/app-nav'" in content
        ):
            return content
        return _rewrite_ops_page(content)
    if "PublicShell" in content:
        member = _is_member_page(file_path, route)
        hook = "useMemberNavItems" if member else "usePublicNavItems"
        cta = "memberCta" if member else "publicCta"
        if (
            f"const navItems = {hook}()" in content
            and f"const navCta = {cta}()" in content
            and "items={navItems}" in content
            and "cta={navCta}" in content
            and f"from '@/lib/app-nav'" in content
            and "BrokenOnly" not in content
        ):
            return content
        return _rewrite_public_page(content, member=member)
    return content


def enforce_recipe_component_variants(workspace, architect: dict | None = None) -> list[str]:
    """
    Drop hardcoded MarketingHero/FeatureBento variant props so the active
    design recipe can choose the layout (split vs cinematic, bento vs grid).
    """
    if architect is not None and not has_catalogue_routes(architect):
        return []
    # Avoid [^>]* matching — pages often have JSX comments with `/>` inside the
    # opening tag (e.g. `{/* <UiIcon … /> */}`), which breaks tag-scoped regex.
    variant_prop_re = re.compile(
        r"""\s+variant=\{?['"](?:cinematic|split|editorial|product|service|compact|bento|grid|alternating)['"]\}?"""
    )
    changed: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if "/pages/" not in norm or not norm.endswith((".tsx", ".jsx")):
            continue
        original = read_file(workspace, norm)
        if "MarketingHero" not in original and "FeatureBento" not in original:
            continue
        updated = variant_prop_re.sub("", original)
        if updated != original:
            write_file(workspace, norm, updated)
            changed.append(norm)
    return changed


def enforce_shared_chrome_nav(workspace, architect: dict | None) -> list[str]:
    """
    Make sidebar/navbar consistent across every catalogue page automatically.

    Catalogue pages own their shell, so without this guard each AI page invents
    a different navItems/PublicNav list. This rewrite always points chrome at
    `@/lib/app-nav`, which reads the synced mock navigation.
    """
    if not has_catalogue_routes(architect):
        return []
    changed: list[str] = []
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if "/pages/" not in norm or not norm.endswith((".tsx", ".jsx")):
            continue
        original = read_file(workspace, norm)
        if "OpsShell" not in original and "PublicShell" not in original:
            continue
        route = catalogue_route_for_file(norm, architect) or {}
        updated = rewrite_page_shared_chrome(norm, original, route)
        if updated != original:
            write_file(workspace, norm, updated)
            changed.append(norm)
    changed.extend(enforce_recipe_component_variants(workspace, architect))
    return list(dict.fromkeys(changed))
