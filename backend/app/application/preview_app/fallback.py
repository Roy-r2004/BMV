"""Guaranteed-valid fallback content for pages that keep failing to build.

After the AI fix-loop exhausts its attempts, any file that is *still*
referenced by a build error gets deterministically replaced with a minimal,
always-valid placeholder page instead of leaving the whole app broken. This
is the final safety net that makes preview-app generation self-healing: a
handful of imperfect pages should never sink the entire live preview.
"""
from __future__ import annotations

import json
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

# Paths rewritten by write_safe_stub / stabilize — cleared by callers each run.
_last_stubbed_paths: list[str] = []


def consume_stubbed_paths() -> list[str]:
    """Return and clear paths stubbed since the last consume."""
    global _last_stubbed_paths
    out = list(dict.fromkeys(_last_stubbed_paths))
    _last_stubbed_paths = []
    return out


def clear_stubbed_paths() -> None:
    global _last_stubbed_paths
    _last_stubbed_paths = []


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


def _friendly_title(path: str, page_title: str | None = None) -> str:
    if page_title and page_title.strip():
        return page_title.strip()
    stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    stem = stem[:-4] if stem.endswith("Page") else stem
    words = _TITLE_SPLIT_RE.sub(" ", stem).strip()
    return words or "This page"


def _industry_copy(industry: str | None, brand: str, title: str) -> tuple[str, list[dict], list[dict]]:
    """Return (subtitle, stats, rows) tailored lightly by industry."""
    ind = (industry or "").lower()
    brand = brand or "Business"
    if any(k in ind for k in ("restaurant", "cafe", "food", "bakery", "bar")):
        return (
            f"Today at {brand} — sample covers and kitchen flow so you can click every screen.",
            [
                {"k": "Open tickets", "v": "12"},
                {"k": "Covers tonight", "v": "64"},
                {"k": "Avg ticket", "v": "$42"},
            ],
            [
                {"label": "Table 4 · tasting menu", "detail": "2 guests · seated", "status": "Live"},
                {"label": "Online · pickup #184", "detail": "Ready in 8 min", "status": "Prep"},
                {"label": "Reservation · 7:30", "detail": "Party of 6 · patio", "status": "Booked"},
            ],
        )
    if any(k in ind for k in ("gym", "fitness", "yoga", "studio")):
        return (
            f"{title} for {brand} — sample classes and members so the product feels live.",
            [
                {"k": "Check-ins today", "v": "48"},
                {"k": "Classes left", "v": "6"},
                {"k": "Renewals due", "v": "3"},
            ],
            [
                {"label": "Strength Lab · 6:00", "detail": "12 / 16 booked", "status": "Open"},
                {"label": "HIIT · 7:15", "detail": "Waitlist 2", "status": "Full"},
                {"label": "Mobility · 8:00", "detail": "Coach: Maya", "status": "Live"},
            ],
        )
    if any(k in ind for k in ("clinic", "health", "dental", "medical", "doctor")):
        return (
            f"{title} at {brand} — sample schedule so patients and staff can explore the flow.",
            [
                {"k": "Today", "v": "18"},
                {"k": "Checked in", "v": "7"},
                {"k": "Avg wait", "v": "9 min"},
            ],
            [
                {"label": "9:15 · New patient", "detail": "Room 2 · intake done", "status": "Ready"},
                {"label": "10:00 · Follow-up", "detail": "Dr. Chen", "status": "Live"},
                {"label": "11:30 · Procedure", "detail": "Consent signed", "status": "Prep"},
            ],
        )
    if any(k in ind for k in ("salon", "spa", "barber", "beauty")):
        return (
            f"{title} for {brand} — sample bookings and chairs so the demo feels real.",
            [
                {"k": "Booked today", "v": "22"},
                {"k": "Walk-ins", "v": "4"},
                {"k": "No-shows", "v": "1"},
            ],
            [
                {"label": "Cut + color · Maya", "detail": "Chair 1 · 90 min", "status": "Live"},
                {"label": "Beard trim · Leo", "detail": "Chair 3 · 30 min", "status": "Next"},
                {"label": "Blowout · Sam", "detail": "Online booking", "status": "Booked"},
            ],
        )
    return (
        f"{title} for {brand} — sample activity so you can click through the full product.",
        [
            {"k": "In progress", "v": "12"},
            {"k": "Completed", "v": "47"},
            {"k": "This week", "v": "128"},
        ],
        [
            {"label": "Priority queue", "detail": "3 waiting · 1 assigned", "status": "Live"},
            {"label": "Follow-ups", "detail": "5 due today", "status": "On track"},
            {"label": "New requests", "detail": "2 just in", "status": "New"},
        ],
    )


def find_broken_paths(build_log: str, candidate_paths: list[str]) -> list[str]:
    """Return every candidate source path mentioned in a failed build's log."""
    broken = []
    for path in candidate_paths:
        norm = path.replace("\\", "/")
        rel = norm[4:] if norm.startswith("src/") else norm
        if norm in build_log or rel in build_log:
            broken.append(path)
    return broken


def write_safe_stub(
    workspace,
    path: str,
    *,
    brand_name: str | None = None,
    industry: str | None = None,
    page_title: str | None = None,
) -> None:
    """Overwrite `path` with a minimal, guaranteed-compiling placeholder page.

    Uses only the `brand` export from mock data (always guaranteed to exist),
    so this can never fail to build regardless of what broke the original.
    Copy is lightly industry-aware so stubs don't all look like the same cafe ops board.
    """
    global _last_stubbed_paths
    component = _component_name(path)
    mock_prefix = _mock_import_prefix(path)
    title = _friendly_title(path, page_title)
    brand = brand_name or "Brand"
    subtitle, stats, rows = _industry_copy(industry, brand, title)

    stats_js = ",\n          ".join(
        f"{{ k: {json.dumps(s['k'], ensure_ascii=False)}, v: {json.dumps(s['v'], ensure_ascii=False)} }}"
        for s in stats
    )
    rows_js = ",\n    ".join(
        "{{ label: %s, detail: %s, status: %s }}"
        % (
            json.dumps(r["label"], ensure_ascii=False),
            json.dumps(r["detail"], ensure_ascii=False),
            json.dumps(r["status"], ensure_ascii=False),
        )
        for r in rows
    )

    content = f"""import {{ brand }} from '{mock_prefix}data/mock';

export default function {component}() {{
  const rows = [
    {rows_js},
  ];

  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-100 pb-8">
        <div>
          <p className="text-sm font-medium uppercase tracking-wide text-brand">{{brand.name}}</p>
          <h1 className="mt-2 text-3xl font-bold text-slate-900">{title}</h1>
          <p className="mt-2 max-w-xl text-slate-600">
            {subtitle}
          </p>
        </div>
        <span className="inline-flex items-center rounded-full bg-brand/10 px-3 py-1 text-sm font-semibold text-brand">
          Open now
        </span>
      </div>

      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {{[
          {stats_js},
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
    _last_stubbed_paths.append(path.replace("\\", "/"))


def stabilize_all_route_pages(
    workspace,
    architect: dict,
    *,
    brand_name: str | None = None,
    industry: str | None = None,
) -> list[str]:
    """Last-resort: stub every planned page + revert chrome so Vite can always ship.

    Used when targeted stubbing still leaves the build broken (e.g. cascading
    import errors). Returns the list of paths rewritten.
    """
    rewritten: list[str] = []
    chrome = [
        "src/components/Nav.tsx",
        "src/layouts/PublicLayout.tsx",
        "src/layouts/AdminLayout.tsx",
        "src/components/UiIcons.tsx",
    ]
    for path in chrome:
        if write_template_fallback(workspace, path):
            rewritten.append(path)

    for rt in architect.get("routes") or []:
        path = (rt.get("component_file") or "").replace("\\", "/")
        if not path or not path.startswith("src/"):
            continue
        if is_chrome_path(path):
            continue
        write_safe_stub(
            workspace,
            path,
            brand_name=brand_name,
            industry=industry,
            page_title=rt.get("title"),
        )
        rewritten.append(path)

    # Always ensure a HomePage exists for the catch-all redirect.
    home = "src/pages/HomePage.tsx"
    if home not in rewritten:
        write_safe_stub(workspace, home, brand_name=brand_name, industry=industry, page_title="Home")
        rewritten.append(home)
    return rewritten
