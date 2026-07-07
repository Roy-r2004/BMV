"""
Post-process generated HTML pages:
- Inject theme CSS from the plan's design_system (not hardcoded tokens)
- Inject navigation bridge using the plan's navigation links only
- Repair invented/broken image srcs (only provided Unsplash URLs are valid)
"""
import re

from app.domain.interfaces.template_renderer import TemplateRenderer


def fix_broken_images(html: str, images: dict) -> str:
    """Replace any <img> src that isn't an allowed remote URL with a real image.

    The AI sometimes invents local paths like "lumina-logo.png" which render
    as broken images in the iframe. Text logos are handled in the prompt; here
    we swap any remaining bad src for a provided Unsplash URL (or remove logos).
    """
    if not html:
        return html

    allowed = [u for u in images.values() if u]
    fallback = allowed[0] if allowed else ""

    def _sub(m: re.Match) -> str:
        tag = m.group(0)
        src_m = re.search(r'src\s*=\s*["\']([^"\']*)["\']', tag, re.IGNORECASE)
        if not src_m:
            return tag
        src = src_m.group(1).strip()
        if src.startswith("https://") or src.startswith("http://") or src.startswith("data:"):
            return tag
        # Logo-ish images become invisible (brand should be text) — others get a real photo
        if "logo" in src.lower() or "logo" in tag.lower():
            return ""
        if fallback:
            return tag.replace(src_m.group(0), f'src="{fallback}"')
        return ""

    return re.sub(r"<img\b[^>]*>", _sub, html, flags=re.IGNORECASE)


def build_nav_map(role_spec: dict, pages: list[dict]) -> dict[str, str]:
    """Build label->page_id map ONLY from the planner's navigation + page metadata."""
    page_map: dict[str, str] = {}

    for p in pages:
        pid = p.get("id", "")
        title = (p.get("title") or "").lower().strip()
        if pid:
            page_map[pid] = pid
            page_map[pid.replace("-", " ")] = pid
        if title:
            page_map[title] = pid

    nav = role_spec.get("navigation") or {}
    for link in nav.get("links") or []:
        label = (link.get("label") or "").lower().strip()
        page_id = link.get("page_id") or ""
        if label and page_id:
            page_map[label] = page_id

    return page_map


def build_theme_css(design_system: dict, manifest: dict, template_renderer: TemplateRenderer) -> str:
    """Theme CSS from planner design_system + manifest — nothing hardcoded."""
    ds = design_system or {}
    accent = ds.get("primary_color") or manifest.get("accent") or "#6366f1"
    accent_dark = manifest.get("accent_dark") or ds.get("secondary_color") or accent
    accent_light = manifest.get("accent_light") or ds.get("background_color") or "#f8fafc"
    font = ds.get("font_family") or manifest.get("font") or "Inter"
    text = ds.get("text_color") or "#1e293b"
    muted = ds.get("muted_text_color") or "#64748b"
    bg = ds.get("background_color") or "#ffffff"
    radius = ds.get("border_radius") or "16px"

    font_link = ds.get("font_import_url") or (
        f"https://fonts.googleapis.com/css2?family={font.replace(' ', '+')}:wght@300;400;500;600;700;800;900&display=swap"
    )

    return template_renderer.render(
        "pages/theme_css.html.j2",
        font_link=font_link,
        accent=accent,
        accent_dark=accent_dark,
        accent_light=accent_light,
        font=font,
        text=text,
        muted=muted,
        bg=bg,
        radius=radius,
    )


def build_nav_bridge_script(
    page_map: dict[str, str],
    page_ids: list[str],
    template_renderer: TemplateRenderer,
) -> str:
    """Bridge script — resolves ONLY via data-preview-nav and planner-defined labels."""
    return template_renderer.render(
        "pages/nav_bridge_script.js.j2",
        page_map=page_map,
        page_ids=page_ids,
    )


def inject_page_enhancements(
    html: str,
    role_spec: dict,
    pages_in_role: list[dict],
    design_system: dict,
    manifest: dict,
    template_renderer: TemplateRenderer,
) -> str:
    """Inject plan-driven theme + nav bridge."""
    if not html or "<html" not in html.lower():
        return html

    if "preview-nav-bridge" in html and "preview-theme" in html:
        return html

    page_ids = [p.get("id") for p in pages_in_role if p.get("id")]
    page_map = build_nav_map(role_spec, pages_in_role)
    theme_css = build_theme_css(design_system, manifest, template_renderer)
    nav_script = build_nav_bridge_script(page_map, page_ids, template_renderer)

    lower = html.lower()
    head_close = lower.find("</head>")
    if head_close >= 0:
        html = html[:head_close] + theme_css + "\n" + html[head_close:]
    else:
        html = theme_css + html

    body_close = lower.rfind("</body>")
    if body_close >= 0:
        html = html[:body_close] + nav_script + "\n" + html[body_close:]
    else:
        html = html + nav_script

    return html
