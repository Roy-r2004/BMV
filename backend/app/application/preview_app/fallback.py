"""Guaranteed-valid fallback content for pages that keep failing to build.

After the AI fix-loop exhausts its attempts, any file that is *still*
referenced by a build error gets deterministically replaced with a minimal,
always-valid placeholder page instead of leaving the whole app broken. This
is the final safety net that makes preview-app generation self-healing: a
handful of imperfect pages should never sink the entire live preview.

Stubs must produce valid TypeScript (never Python f-string `{{` leaks) and
respect dual surfaces: public stubs use PublicShell/MarketingHero; ops stubs
use OpsShell + StatCard density.
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


def _friendly_title(path: str, page_title: str | None = None) -> str:
    if page_title and page_title.strip():
        return page_title.strip()
    stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    stem = stem[:-4] if stem.endswith("Page") else stem
    words = _TITLE_SPLIT_RE.sub(" ", stem).strip()
    return words or "This page"


def _is_ops_path(path: str, surface: str | None = None) -> bool:
    if surface and surface.strip().lower() == "ops":
        return True
    if surface and surface.strip().lower() == "public":
        return False
    norm = path.replace("\\", "/").lower()
    return any(seg in norm for seg in ("/owner/", "/admin/", "/ops/", "/staff/"))


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
                {"k": "Avg ticket", "v": "42"},
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
    if any(k in ind for k in ("clinic", "health", "dental", "medical", "doctor", "medspa", "aesthetic")):
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
    surface: str | None = None,
) -> None:
    """Overwrite `path` with a minimal, guaranteed-compiling surface-aware page.

    Uses only `brand` from mock + `@/ui` shells. Valid TS only — never emit
    Python f-string double-brace leaks like `{{ label: ... }}`.
    """
    global _last_stubbed_paths
    component = _component_name(path)
    title = _friendly_title(path, page_title)
    brand = brand_name or "Brand"
    subtitle, stats, rows = _industry_copy(industry, brand, title)
    ops = _is_ops_path(path, surface)

    stats_js = ",\n    ".join(
        "{ k: %s, v: %s }"
        % (json.dumps(s["k"], ensure_ascii=False), json.dumps(s["v"], ensure_ascii=False))
        for s in stats
    )
    rows_js = ",\n    ".join(
        "{ label: %s, detail: %s, status: %s }"
        % (
            json.dumps(r["label"], ensure_ascii=False),
            json.dumps(r["detail"], ensure_ascii=False),
            json.dumps(r["status"], ensure_ascii=False),
        )
        for r in rows
    )
    chart_js = ",\n    ".join(
        "{ day: %s, value: %s }"
        % (json.dumps(d), n)
        for d, n in (("Mon", 12), ("Tue", 18), ("Wed", 15), ("Thu", 22), ("Fri", 19))
    )
    title_js = json.dumps(title, ensure_ascii=False)
    subtitle_js = json.dumps(subtitle, ensure_ascii=False)
    brand_js = json.dumps(brand, ensure_ascii=False)

    if ops:
        content = f"""import {{ brand }} from '@/data/mock';
import OpsShell from '@/ui/OpsShell';
import PageHeader from '@/ui/PageHeader';
import StatCard from '@/ui/StatCard';
import ChartCard from '@/ui/ChartCard';
import DataTable from '@/ui/DataTable';
import FilterBar from '@/ui/FilterBar';

const stats = [
    {stats_js},
];

const rows = [
    {rows_js},
];

const chartData = [
    {chart_js},
];

const navItems = [
  {{ id: 'dashboard', label: 'Dashboard', href: '/owner/dashboard', active: true }},
  {{ id: 'clients', label: 'Clients', href: '/owner/clients' }},
  {{ id: 'appointments', label: 'Appointments', href: '/owner/appointments' }},
];

export default function {component}() {{
  return (
    <OpsShell brandName={{brand.name || {brand_js}}} navItems={{navItems}}>
      <PageHeader
        title={{{title_js}}}
        description={{{subtitle_js}}}
      />
      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        {{stats.map((stat) => (
          <StatCard key={{stat.k}} label={{stat.k}} value={{stat.v}} />
        ))}}
      </div>
      <div className="mt-6">
        <FilterBar />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <ChartCard
          title="This week"
          description="Sample operational volume"
          data={{chartData}}
          dataKey="value"
          xKey="day"
          type="area"
        />
        <DataTable
          columns={{[
            {{ key: 'label', header: 'Item' }},
            {{ key: 'detail', header: 'Detail' }},
            {{ key: 'status', header: 'Status' }},
          ]}}
          rows={{rows}}
        />
      </div>
    </OpsShell>
  );
}}
"""
    else:
        content = f"""import {{ Link }} from 'react-router-dom';
import {{ brand }} from '@/data/mock';
import PublicShell from '@/ui/PublicShell';
import MarketingHero from '@/ui/MarketingHero';
import FeatureBento from '@/ui/FeatureBento';
import CTABand from '@/ui/CTABand';

const features = [
  {{
    title: 'Guided next step',
    description: 'Clear path from interest to booking with calm, premium pacing.',
  }},
  {{
    title: 'Personal recommendations',
    description: 'AI-assisted suggestions that still feel human and brand-true.',
  }},
  {{
    title: 'Member continuity',
    description: 'Aftercare and follow-ups stay in one polished experience.',
  }},
];

export default function {component}() {{
  return (
    <PublicShell
      brandName={{brand.name || {brand_js}}}
      nav={{
        <div className="flex items-center gap-4 text-sm text-white/75">
          <Link to="/" className="hover:text-white">Home</Link>
          <Link to="/treatments" className="hover:text-white">Treatments</Link>
          <Link
            to="/ai-consultation"
            className="inline-flex h-9 items-center rounded-xl bg-brand px-3.5 text-sm font-semibold text-white"
          >
            Book
          </Link>
        </div>
      }}
    >
      <MarketingHero
        eyebrow={{brand.name || {brand_js}}}
        headline={{{title_js}}}
        subcopy={{{subtitle_js}}}
        primaryAction={{
          <Link
            to="/ai-consultation"
            className="inline-flex h-10 items-center justify-center rounded-xl bg-brand px-4 text-sm font-semibold text-white"
          >
            Start consultation
          </Link>
        }}
        secondaryAction={{
          <Link
            to="/treatments"
            className="inline-flex h-10 items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-900"
          >
            View treatments
          </Link>
        }}
      />
      <div className="px-6 pb-20 lg:px-10">
        <FeatureBento items={{features}} />
        <div className="mt-16">
          <CTABand
            headline="Ready when you are"
            description="Continue exploring the live product — every screen is clickable."
            primaryAction={{
              <Link
                to="/ai-consultation"
                className="inline-flex h-10 items-center justify-center rounded-xl bg-brand px-4 text-sm font-semibold text-white"
              >
                Continue
              </Link>
            }}
          />
        </div>
      </div>
    </PublicShell>
  );
}}
"""

    write_file(workspace, path, content)
    if "{{" in content:
        # Never ship Python brace-escape leaks into the Vite workspace.
        raise RuntimeError(f"write_safe_stub produced invalid JS braces in {path}")
    _last_stubbed_paths.append(path.replace("\\", "/"))


def stabilize_broken_pages(
    workspace,
    paths: list[str],
    architect: dict | None = None,
    *,
    brand_name: str | None = None,
    industry: str | None = None,
) -> list[str]:
    """Stub only the given broken paths (never wipe healthy critic-passed pages).

    Primary pages (home + owner dashboard) always get rich surface-aware stubs —
    never thin placeholder content.
    """
    rewritten: list[str] = []
    route_meta: dict[str, dict] = {}
    for rt in (architect or {}).get("routes") or []:
        cf = (rt.get("component_file") or "").replace("\\", "/")
        if cf:
            route_meta[cf] = rt

    for path in paths:
        norm = path.replace("\\", "/")
        if is_chrome_path(norm):
            if write_template_fallback(workspace, norm):
                rewritten.append(norm)
            continue
        # Never stub a page that already looks critic-passed/rich unless it is listed
        # as broken (caller already decided). Keep stub quality high for primary surfaces.
        meta = route_meta.get(norm) or {}
        surface = meta.get("surface")
        low = norm.lower()
        if "homepage" in low or low.endswith("/home.tsx"):
            surface = "public"
        if "ownerdashboard" in low.replace("_", "") or (
            "/owner/" in low and "dashboard" in low
        ):
            surface = "ops"
        write_safe_stub(
            workspace,
            norm,
            brand_name=brand_name,
            industry=industry,
            page_title=meta.get("title"),
            surface=surface,
        )
        rewritten.append(norm)
    return rewritten


def stabilize_all_route_pages(
    workspace,
    architect: dict,
    *,
    brand_name: str | None = None,
    industry: str | None = None,
    only_paths: list[str] | None = None,
) -> list[str]:
    """Last-resort stabilize. Prefer `only_paths` so good pages are preserved.

    If `only_paths` is provided, only those files are rewritten (+ chrome
    reverted when listed). Full route wipe is used only when `only_paths` is None.
    """
    rewritten: list[str] = []
    chrome = [
        "src/components/Nav.tsx",
        "src/layouts/PublicLayout.tsx",
        "src/layouts/AdminLayout.tsx",
        "src/components/UiIcons.tsx",
    ]

    if only_paths is not None:
        targets = [p.replace("\\", "/") for p in only_paths]
        # Always restore chrome if any chrome path is broken or build is nuclear-ish
        for path in chrome:
            if path.replace("\\", "/").lower() in {t.lower() for t in targets} or any(
                is_chrome_path(t) for t in targets
            ):
                if write_template_fallback(workspace, path):
                    rewritten.append(path)
        page_targets = [t for t in targets if not is_chrome_path(t)]
        rewritten.extend(
            stabilize_broken_pages(
                workspace,
                page_targets,
                architect,
                brand_name=brand_name,
                industry=industry,
            )
        )
        return list(dict.fromkeys(rewritten))

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
            surface=rt.get("surface"),
        )
        rewritten.append(path)

    home = "src/pages/HomePage.tsx"
    if home not in rewritten:
        write_safe_stub(
            workspace,
            home,
            brand_name=brand_name,
            industry=industry,
            page_title="Home",
            surface="public",
        )
        rewritten.append(home)
    return rewritten
