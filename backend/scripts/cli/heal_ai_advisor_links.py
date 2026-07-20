"""Fix dead /ai-advisor/* card links and keep subpaths on the advisor page."""
from __future__ import annotations

import re
import sys

from app.application.preview_app.ai_feature_surfaces import rewrite_invented_ai_step_links
from app.application.preview_app.build import run_build
from app.application.preview_app.workspace import get_workspace, list_source_files, read_file, write_file
from app.infrastructure.templating.renderer import get_template_renderer


def _heal_app_routes(app_tsx: str) -> str:
    """Ensure /ai-advisor/* maps to the same component as /ai-advisor."""
    if not app_tsx or 'path="/ai-advisor/*"' in app_tsx:
        return app_tsx
    pattern = re.compile(
        r'(<Route path="/ai-advisor" element=\{<(\w+) />\} />)'
    )
    match = pattern.search(app_tsx)
    if not match:
        return app_tsx
    comp = match.group(2)
    injection = (
        f'{match.group(1)}\n'
        f'          <Route path="/ai-advisor/*" element={{<{comp} />}} />'
    )
    return app_tsx.replace(match.group(1), injection, 1)


def main(request_id: int) -> int:
    ws = get_workspace(request_id)
    changed: list[str] = []
    for rel in list_source_files(ws):
        if not rel.endswith(".tsx"):
            continue
        text = read_file(ws, rel) or ""
        if "ai-advisor/" not in text and "ai-stylist/" not in text:
            continue
        # Ensure panel has an id for hash targeting.
        text2 = re.sub(
            r'<div data-ai-feature-panel="([^"]+)">',
            r'<div id="\1" data-ai-feature-panel="\1">',
            text,
        )
        text2 = rewrite_invented_ai_step_links(text2)
        if text2 != text:
            write_file(ws, rel, text2)
            changed.append(rel)
            print("healed", rel)

    app = read_file(ws, "src/App.tsx") or ""
    app2 = _heal_app_routes(app)
    if app2 != app:
        write_file(ws, "src/App.tsx", app2)
        changed.append("src/App.tsx")
        print("healed src/App.tsx wildcard")

    if not changed:
        print("nothing to heal")
        return 0

    ok, _ = run_build(ws, f"/api/preview-apps/{request_id}", get_template_renderer())
    print("build_ok", ok)
    return 0 if ok else 2


if __name__ == "__main__":
    rid = int(sys.argv[1]) if len(sys.argv) > 1 else 11
    raise SystemExit(main(rid))
