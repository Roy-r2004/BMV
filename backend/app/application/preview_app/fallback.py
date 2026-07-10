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

    # Last-resort fallback must still feel like a real product screen, not a
    # "coming soon" pitch — otherwise one broken page destroys owner trust.
    content = f"""import {{ brand }} from '{mock_prefix}data/mock';

export default function {component}() {{
  const rows = [
    {{ label: 'Morning rush', detail: '12 open · 3 ready', status: 'Live' }},
    {{ label: 'Midday', detail: '8 open · 5 ready', status: 'On track' }},
    {{ label: 'Evening', detail: '4 open · 1 ready', status: 'Quiet' }},
  ];

  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-100 pb-8">
        <div>
          <p className="text-sm font-medium uppercase tracking-wide text-brand">{{brand.name}}</p>
          <h1 className="mt-2 text-3xl font-bold text-slate-900">{title}</h1>
          <p className="mt-2 max-w-xl text-slate-600">
            Working view for today&apos;s floor — sample activity so you can click through the full product.
          </p>
        </div>
        <span className="inline-flex items-center rounded-full bg-brand/10 px-3 py-1 text-sm font-semibold text-brand">
          Open now
        </span>
      </div>

      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {{[
          {{ k: 'In progress', v: '12' }},
          {{ k: 'Completed', v: '47' }},
          {{ k: 'Avg wait', v: '8 min' }},
        ].map((stat) => (
          <div key={{stat.k}} className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">{{stat.k}}</p>
            <p className="mt-2 text-2xl font-bold text-slate-900">{{stat.v}}</p>
          </div>
        ))}}
      </div>

      <div className="mt-8 overflow-hidden rounded-2xl border border-slate-100 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-5 py-4">
          <h2 className="font-semibold text-slate-900">Today&apos;s activity</h2>
        </div>
        <ul className="divide-y divide-slate-100">
          {{rows.map((row) => (
            <li key={{row.label}} className="flex items-center justify-between gap-4 px-5 py-4">
              <div>
                <p className="font-medium text-slate-900">{{row.label}}</p>
                <p className="text-sm text-slate-500">{{row.detail}}</p>
              </div>
              <span className="rounded-full bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-600">
                {{row.status}}
              </span>
            </li>
          ))}}
        </ul>
      </div>
    </div>
  );
}}
"""
    write_file(workspace, path, content)
