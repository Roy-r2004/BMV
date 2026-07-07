"""Guaranteed-valid fallback content for pages that keep failing to build.

After the AI fix-loop exhausts its attempts, any file that is *still*
referenced by a build error gets deterministically replaced with a minimal,
always-valid placeholder page instead of leaving the whole app broken. This
is the final safety net that makes preview-app generation self-healing: a
handful of imperfect pages should never sink the entire live preview.
"""
from __future__ import annotations

import re

from app.core.config import settings
from app.application.preview_app.workspace import write_file

_TITLE_SPLIT_RE = re.compile(r"(?<!^)(?=[A-Z])")

# Nav/Layout/icon-set files are now AI-authored per brand (see codegen.py's
# _CHROME_CONTRACTS), but they have real prop/import contracts that a generic
# placeholder page would violate — dropping a "This section is being
# fine-tuned" block into the site's nav bar or layout shell would break every
# page that depends on them. So these get a dedicated fallback: revert to the
# known-good static template file instead of stubbing.
_CHROME_TEMPLATE_PATHS = {
    "src/components/nav.tsx",
    "src/layouts/publiclayout.tsx",
    "src/layouts/adminlayout.tsx",
    "src/components/uiicons.tsx",
}


def is_chrome_path(path: str) -> bool:
    return path.replace("\\", "/").lower() in _CHROME_TEMPLATE_PATHS


def write_template_fallback(workspace, path: str) -> bool:
    """Revert a shared-chrome file to the static template's known-good version.

    Last resort when an AI-authored Nav/Layout/icon-set file keeps breaking
    the build after every fix attempt — guarantees the site never ships
    broken, at the cost of that one file losing its bespoke styling for this
    request. Returns False (caller should fall back to `write_safe_stub`) if
    no template source exists for the path.
    """
    rel = path.replace("\\", "/")
    source = settings.PREVIEW_TEMPLATE_DIR / rel
    if not source.is_file():
        return False
    write_file(workspace, path, source.read_text(encoding="utf-8"))
    return True


def _component_name(path: str) -> str:
    stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    ident = re.sub(r"[^0-9A-Za-z_]", "", stem)
    if not ident or ident[0].isdigit():
        ident = "Page" + ident
    return ident


def _mock_import_prefix(path: str) -> str:
    """Relative import depth from a `src/pages/...` file back to `src/data/mock`."""
    norm = path.replace("\\", "/")
    if "src/pages/" not in norm:
        return "../"
    tail = norm.split("src/pages/", 1)[1]
    depth = tail.count("/")  # sub-folders between pages/ and the filename
    return "../" * (depth + 1)


def _friendly_title(path: str) -> str:
    stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    stem = stem[:-4] if stem.endswith("Page") else stem
    words = _TITLE_SPLIT_RE.sub(" ", stem).strip()
    return words or "This page"


def find_broken_paths(build_log: str, candidate_paths: list[str]) -> list[str]:
    """Return every candidate source path mentioned in a failed build's log."""
    broken = []
    for path in candidate_paths:
        norm = path.replace("\\", "/")
        rel = norm[4:] if norm.startswith("src/") else norm
        if norm in build_log or rel in build_log:
            broken.append(path)
    return broken


def write_safe_stub(workspace, path: str) -> None:
    """Overwrite `path` with a minimal, guaranteed-compiling placeholder page.

    Uses only the `brand` export from mock data (always guaranteed to exist),
    so this can never fail to build regardless of what broke the original.
    """
    component = _component_name(path)
    mock_prefix = _mock_import_prefix(path)
    title = _friendly_title(path)

    content = f"""import {{ brand }} from '{mock_prefix}data/mock';

export default function {component}() {{
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 py-24 text-center">
      <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-4 py-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </span>
      <h1 className="mt-6 text-3xl font-bold text-slate-900">{{brand.name}}</h1>
      <p className="mt-3 max-w-md text-slate-500">
        This section is being fine-tuned for your business — full detail is on its way.
      </p>
    </div>
  );
}}
"""
    write_file(workspace, path, content)
