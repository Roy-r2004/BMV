"""
Bundle all pages in a role into ONE website with in-browser client-side routing.
Navigation happens inside the iframe — like a real multi-page site, not parent tab switching.
"""
import re

from app.domain.interfaces.template_renderer import TemplateRenderer


def _extract_head_assets(html: str) -> str:
    """Pull styles/links from a page head."""
    parts: list[str] = []
    for m in re.finditer(r"<link[^>]+>", html, re.IGNORECASE):
        if "preview-theme" not in m.group(0):
            parts.append(m.group(0))
    for m in re.finditer(r"<style[^>]*>.*?</style>", html, re.IGNORECASE | re.DOTALL):
        if "preview-theme" not in m.group(0) and "preview-router" not in m.group(0):
            parts.append(m.group(0))
    return "\n".join(parts)


def _extract_body(html: str) -> str:
    lower = html.lower()
    body_start = lower.find("<body")
    if body_start < 0:
        return html
    tag_end = html.find(">", body_start) + 1
    body_end = lower.rfind("</body>")
    if body_end < 0:
        return html[tag_end:].strip()
    inner = html[tag_end:body_end].strip()
    # Remove per-page nav bridge — bundle router handles navigation
    inner = re.sub(r'<script id="preview-nav-bridge">.*?</script>', "", inner, flags=re.DOTALL)
    return inner


def build_role_site_bundle(
    pages: list[dict],
    design_system: dict,
    manifest: dict,
    concept_slug: str,
    template_renderer: TemplateRenderer,
) -> str:
    """
    Merge role pages into a single navigable website HTML document.
    pages: [{id, title, html}, ...]
    """
    if not pages:
        return ""

    page_ids = [p["id"] for p in pages if p.get("id")]
    default_page = page_ids[0]

    ds = design_system or {}
    accent = ds.get("primary_color") or manifest.get("accent") or "#6366f1"
    accent_dark = manifest.get("accent_dark") or ds.get("secondary_color") or accent
    font = ds.get("font_family") or "Inter"
    font_url = ds.get("font_import_url") or (
        f"https://fonts.googleapis.com/css2?family={font.replace(' ', '+')}:wght@400;500;600;700;800&display=swap"
    )

    head_assets: list[str] = []
    page_contexts: list[dict] = []

    for p in pages:
        pid = p.get("id", "")
        html = p.get("html") or ""
        if not pid or not html:
            continue
        head_assets.append(_extract_head_assets(html))
        body = _extract_body(html)
        page_contexts.append({"id": pid, "body": body, "is_default": pid == default_page})

    return template_renderer.render(
        "pages/role_site_bundle.html.j2",
        brand_name=manifest.get("brand_name"),
        concept_slug=concept_slug,
        font_url=font_url,
        accent=accent,
        accent_dark=accent_dark,
        font=font,
        head_assets=head_assets,
        pages=page_contexts,
        page_ids=page_ids,
        default_page=default_page,
        slug=concept_slug,
    )
