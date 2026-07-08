"""AI code agent — per-user overlay + virtual generated files from chat."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.application.services.solution_sanitize import sanitize_file_entry
from app.application.services.user_auth import add_message, get_or_create_workspace, list_messages, parse_overlay, save_overlay
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.infrastructure.ai_providers.factory import get_ai_provider

_AGENT_SCHEMA = """
You are a solution customization agent. Each user gets a PRIVATE workspace on top of a shared industry template.
Return ONLY valid JSON with keys: reply (string), overlay_patch (object), changes_made (string[]).

overlay_patch may include:

OVERLAY (live UI bindings):
- businessName, productName, tagline, heroHeadline, heroSub (strings)
- primaryColor, secondaryColor, backgroundColor, accentColor (hex #RRGGBB)
- ctaPrimary, ctaSecondary (hero button labels)
- aiChips (string[]), heroStats ({label, value}[])
- sections (array) — {id, title, subtitle?, body?, bullets?, style?: highlight|cards|banner|stats, ctaLabel?}
- removeSectionIds (string[])
- elementEdits (array) — direct edits from click-to-edit preview selection:
  {id, selector, text?, placeholder?, value?, ariaLabel?}
  Use this for selected titles, text, buttons, labels, and input placeholders.
- removeElementEditIds (string[])

CODE FILES (virtual per-user files — NOT the shared repo):
- files (array) — write or update by path. Each:
  {id, path, kind: "css"|"markup", content}
  - css: scoped styles. Prefix selectors with .user-codegen-{solution_id} to avoid breaking the template.
  - catalog AI feature tools render with .overlay-feature-widget and children such as
    .overlay-feature-widget__head, __badge, __form, __inline, __result, __cards, __timeline, __primary.
    Each catalog tool root also has a stable feature class: .{feature_id}-widget
    (examples: .lum-size-finder-widget, .lum-bundles-widget, .re-lead-scoring-widget).
    Target the root feature class first, e.g.
    .user-codegen-ecommerce .lum-size-finder-widget { ... }
    Do not invent internal classes that are not listed here.
    Use these selectors when the user asks to enhance an integrated catalog feature UI.
  - markup: safe HTML fragment injected into the demo (no script/form/iframe). Use for custom blocks the overlay cannot express.
- removeFileIds (string[])

Use files when the user wants layout/code-level changes: custom pricing tables, unique section HTML, advanced styling.
Prefer overlay fields for simple copy/color/button changes.
Do not invent pricing. Keep changes faithful to the request.
"""

_INDUSTRY_HINTS: dict[str, str] = {
    "real-estate": "Northline listings site with hero, listings grid, viewing booking.",
    "healthcare": "Harbor patient site with intake AI, scheduling, clinic admin.",
    "food": "Ember restaurant guest site with menu, reservations, kitchen ops.",
    "fitness": "Peak Form gym member site with classes and coach AI.",
    "ecommerce": "Lumen lifestyle shop with search and product discovery.",
    "education": "Summit tutoring student site with subject matching.",
    "hospitality": "Row Hotel guest site with booking and concierge.",
    "automotive": "Metro auto service booking and bay status.",
    "home-services": "BrightFix plumbing quote wizard and dispatch.",
    "professional-services": "Apex legal counsel portal with conflict checks.",
    "personal-care": "Studio Nine barbershop booking and DM inbox.",
    "nonprofit": "Harbor Give donor site with campaigns and volunteer.",
}


def _clean_requested_change(raw: str) -> str:
    text = (raw or "").strip()
    text = re.sub(r"^(requested\s+change\s*:)\s*", "", text, flags=re.I).strip()
    for pattern in (
        r"\b(?:word|text|title|placeholder|value)\s+['\"]?([^'\".\n]+)['\"]?\s*$",
        r"\b(?:to|as|inside it)\s+['\"]?([^'\".\n]+)['\"]?\s*$",
        r"['\"]([^'\"]+)['\"]",
    ):
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).strip()
    return text.strip(' "\'')


def _selected_element_patch(message: str) -> tuple[dict[str, Any], list[str]]:
    selector_match = re.search(r"Element selector:\s*(.+)", message, re.I)
    request_match = re.search(r"Requested change:\s*([\s\S]+)", message, re.I)
    if not selector_match or not request_match:
        return {}, []

    selector = selector_match.group(1).strip()
    requested = _clean_requested_change(request_match.group(1))
    if not selector or not requested:
        return {}, []

    type_match = re.search(r"Change this selected ([^\n.]+)", message, re.I)
    element_type = (type_match.group(1) if type_match else "").lower()
    field = "placeholder" if "form field" in element_type else "text"
    edit_id = re.sub(r"[^a-z0-9]+", "-", selector.lower()).strip("-")[:80] or uuid.uuid4().hex[:8]
    edit: dict[str, Any] = {
        "id": f"selected-{edit_id}",
        "selector": selector,
        field: requested,
    }
    return {"elementEdits": [edit]}, [f"Updated selected {element_type or 'element'}"]


def _merge_overlay(base: dict[str, Any], patch: dict[str, Any], *, solution_id: str) -> dict[str, Any]:
    out = dict(base)

    for key, val in patch.items():
        if val is None:
            continue

        if key == "sections" and isinstance(val, list):
            by_id = {
                str(s["id"]): s
                for s in (out.get("sections") or [])
                if isinstance(s, dict) and s.get("id")
            }
            for s in val:
                if isinstance(s, dict) and s.get("id"):
                    by_id[str(s["id"])] = s
            out["sections"] = list(by_id.values())
            continue

        if key == "removeSectionIds" and isinstance(val, list):
            remove = {str(x) for x in val}
            out["sections"] = [
                s for s in (out.get("sections") or [])
                if isinstance(s, dict) and str(s.get("id")) not in remove
            ]
            continue

        if key == "files" and isinstance(val, list):
            by_path: dict[str, dict] = {
                str(f["path"]): f
                for f in (out.get("files") or [])
                if isinstance(f, dict) and f.get("path")
            }
            for raw in val:
                clean = sanitize_file_entry(raw)
                if clean:
                    if clean["kind"] == "css" and ".user-codegen-" not in clean["content"]:
                        clean["content"] = f".user-codegen-{solution_id} {{\n{clean['content']}\n}}"
                    by_path[clean["path"]] = clean
            out["files"] = list(by_path.values())
            continue

        if key == "removeFileIds" and isinstance(val, list):
            remove = {str(x) for x in val}
            out["files"] = [
                f for f in (out.get("files") or [])
                if isinstance(f, dict) and str(f.get("id")) not in remove
            ]
            continue

        if key == "elementEdits" and isinstance(val, list):
            by_id: dict[str, dict] = {
                str(e["id"]): e
                for e in (out.get("elementEdits") or [])
                if isinstance(e, dict) and e.get("id")
            }
            for raw in val:
                if not isinstance(raw, dict):
                    continue
                selector = str(raw.get("selector") or "").strip()
                if not selector:
                    continue
                edit_id = str(raw.get("id") or selector).strip()
                clean = {"id": edit_id, "selector": selector}
                for field in ("text", "placeholder", "value", "ariaLabel"):
                    if raw.get(field) is not None:
                        clean[field] = str(raw[field]).strip()[:500]
                by_id[edit_id] = clean
            out["elementEdits"] = list(by_id.values())
            continue

        if key == "removeElementEditIds" and isinstance(val, list):
            remove = {str(x) for x in val}
            out["elementEdits"] = [
                e for e in (out.get("elementEdits") or [])
                if isinstance(e, dict) and str(e.get("id")) not in remove
            ]
            continue

        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = {**out[key], **val}
        else:
            out[key] = val

    return out


def _fallback_patch(message: str, solution_id: str) -> tuple[dict[str, Any], list[str], str]:
    changes: list[str] = []
    patch: dict[str, Any] = {}
    lower = message.lower()

    brand_match = re.search(
        r"(?:brand|business|company|name)(?:\s+to|\s+is|\s*:\s*)\s*['\"]?([^'\".\n]+)",
        message,
        re.I,
    )
    if brand_match:
        patch["businessName"] = brand_match.group(1).strip()
        changes.append(f"Business name → {patch['businessName']}")

    for color_key, patterns in [
        ("primaryColor", [r"primary\s*(?:color)?\s*#([0-9a-fA-F]{6})", r"#([0-9a-fA-F]{6})"]),
        ("secondaryColor", [r"secondary\s*(?:color)?\s*#([0-9a-fA-F]{6})"]),
        ("backgroundColor", [r"background\s*(?:color)?\s*#([0-9a-fA-F]{6})"]),
        ("accentColor", [r"accent\s*(?:color)?\s*#([0-9a-fA-F]{6})"]),
    ]:
        for pat in patterns:
            m = re.search(pat, message, re.I)
            if m:
                patch[color_key] = f"#{m.group(1)}"
                changes.append(f"{color_key} → {patch[color_key]}")
                break

    hero_match = re.search(r"hero(?:\s+headline)?\s*(?:to|:)\s*['\"]([^'\"]+)['\"]", message, re.I)
    if hero_match:
        patch["heroHeadline"] = hero_match.group(1).strip()
        changes.append("Updated hero headline")

    if "tagline" in lower:
        quote = re.search(r"['\"]([^'\"]+)['\"]", message)
        if quote:
            patch["tagline"] = quote.group(1).strip()
            changes.append("Updated tagline")

    if any(kw in lower for kw in ("add section", "new section", "add a section")):
        title_m = re.search(r"section(?:\s+(?:called|named|titled))?\s*['\"]?([^'\".\n]+)", message, re.I)
        title = title_m.group(1).strip() if title_m else "Why work with us"
        section_id = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or uuid.uuid4().hex[:8]
        body_m = re.search(r"(?:about|saying|content)\s*['\"]([^'\"]+)['\"]", message, re.I)
        section: dict[str, Any] = {"id": section_id, "title": title, "style": "highlight"}
        if body_m:
            section["body"] = body_m.group(1).strip()
        patch["sections"] = [section]
        changes.append(f"Added section “{title}”")

    if any(kw in lower for kw in ("custom css", "write css", "add css", "style file")):
        css_m = re.search(r"```(?:css)?\s*([\s\S]+?)```", message)
        css_body = css_m.group(1).strip() if css_m else "border-radius: 1rem; padding: 1rem;"
        file_id = "custom-styles"
        try:
            patch["files"] = [
                sanitize_file_entry({
                    "id": file_id,
                    "path": "styles/custom.css",
                    "kind": "css",
                    "content": f".user-codegen-{solution_id} .hero {{ {css_body} }}",
                })
            ]
            changes.append("Added custom CSS file")
        except ValueError:
            pass

    if any(kw in lower for kw in ("html block", "custom html", "add html", "markup file")):
        html_m = re.search(r"```(?:html)?\s*([\s\S]+?)```", message)
        if html_m:
            try:
                patch["files"] = [
                    sanitize_file_entry({
                        "id": "custom-block",
                        "path": "blocks/custom.html",
                        "kind": "markup",
                        "content": html_m.group(1).strip(),
                    })
                ]
                changes.append("Added custom HTML block")
            except ValueError:
                pass

    if changes:
        reply = f"Applied {len(changes)} change(s) to your {solution_id} workspace."
    else:
        reply = (
            "I'm your customization agent — I can change copy/colors via overlay, or write virtual CSS/HTML files "
            "for deeper layout changes. Describe what you want or paste a CSS/HTML block."
        )
    return patch, changes, reply


def _ai_patch(
    ai: AIProvider,
    *,
    solution_id: str,
    message: str,
    overlay: dict[str, Any],
    history: list[dict[str, str]],
) -> tuple[dict[str, Any], list[str], str]:
    industry = _INDUSTRY_HINTS.get(solution_id, "Industry software showcase demo.")
    system = (
        _AGENT_SCHEMA
        + f"\nSolution: {solution_id}. Template context: {industry}"
        + f"\nScope CSS with .user-codegen-{solution_id} when targeting page areas."
    )
    user_payload = {
        "solution_id": solution_id,
        "current_overlay": overlay,
        "recent_messages": history[-8:],
        "user_message": message,
    }
    raw = ai.ask_chat(
        settings.TEXT_MODEL,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
        max_tokens=4000,
    )
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    patch = data.get("overlay_patch") or {}
    changes = data.get("changes_made") or []
    reply = data.get("reply") or "Updated your workspace."
    if not isinstance(patch, dict):
        patch = {}
    if not isinstance(changes, list):
        changes = []
    return patch, [str(c) for c in changes], str(reply)


def refine_solution_from_chat(
    db: Session,
    *,
    user_id: int,
    solution_id: str,
    message: str,
    attachment_name: str | None = None,
    attachment_path: str | None = None,
) -> tuple[dict[str, Any], str, list[str]]:
    ws = get_or_create_workspace(db, user_id, solution_id)
    overlay = parse_overlay(ws)
    add_message(
        db,
        ws.id,
        role="user",
        content=message,
        attachment_name=attachment_name,
        attachment_path=attachment_path,
    )

    history = [{"role": m.role, "content": m.content} for m in list_messages(db, ws.id)]

    try:
        ai = get_ai_provider()
        patch, changes, reply = _ai_patch(
            ai,
            solution_id=solution_id,
            message=message,
            overlay=overlay,
            history=history,
        )
    except Exception:
        patch, changes, reply = _fallback_patch(message, solution_id)

    selected_patch, selected_changes = _selected_element_patch(message)
    if selected_patch:
        patch = _merge_overlay(patch, selected_patch, solution_id=solution_id)
        for change in selected_changes:
            if change not in changes:
                changes.append(change)
        if not reply or "updated" not in reply.lower():
            reply = "Updated the selected preview element."

    if attachment_name:
        notes = list(overlay.get("notes") or [])
        notes.append(f"Attachment: {attachment_name}")
        patch = _merge_overlay(patch, {"notes": notes}, solution_id=solution_id)
        if f"Stored attachment {attachment_name}" not in changes:
            changes.append(f"Stored attachment {attachment_name}")

    if patch:
        overlay = _merge_overlay(overlay, patch, solution_id=solution_id)
        save_overlay(db, ws, overlay)

    add_message(db, ws.id, role="assistant", content=reply)
    return overlay, reply, changes
