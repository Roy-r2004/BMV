"""Helpers for host-app role chrome (taglines + route page maps)."""
from __future__ import annotations

from typing import Any


def role_tagline(role: dict[str, Any] | None, plan_roles: list[dict[str, Any]] | None = None) -> str:
    """Resolve a viewing-as blurb for a role from architect/plan fields."""
    role = role or {}
    direct = str(role.get("tagline") or "").strip()
    if direct:
        return direct
    rid = str(role.get("id") or "")
    for pr in plan_roles or []:
        if str(pr.get("id") or "") == rid:
            return str(pr.get("tagline") or "").strip()
    return ""


def routes_for_role(
    routes: list[dict[str, Any]] | None,
    role_id: str,
    first_role_id: str,
) -> list[dict[str, Any]]:
    """Filter preview routes for the host page strip (mirrors frontend roleRoutes)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rt in routes or []:
        path = str(rt.get("path") or "").strip()
        if not path:
            continue
        if not path.startswith("/"):
            path = f"/{path}"
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]
        if path == "/ai-features" or path.startswith("/ai-features?"):
            continue
        if path in seen:
            continue
        rid = str(rt.get("role_id") or "").strip()
        orphan = not rid
        mine = rid == role_id or (orphan and role_id == first_role_id)
        if not mine:
            continue
        seen.add(path)
        title = str(rt.get("title") or "").strip()
        if not title:
            if path == "/":
                title = "Home"
            else:
                seg = path.rstrip("/").split("/")[-1]
                title = " ".join(p.capitalize() for p in seg.split("-") if p)
        out.append({"path": path, "title": title, "role_id": rid or first_role_id})
    return out
