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
import threading
from pathlib import Path

from app.core.config import settings
from app.application.preview_app.catalogue_contract import (
    minimal_catalogue_page_scaffold,
    validate_catalogue_page_content,
)
from app.application.preview_app.protected_paths import (
    has_catalogue_routes,
    is_template_owned_path,
    safe_source_path,
)
from app.application.preview_app.workspace import (
    write_file,
    write_trusted_contained_file,
)

_TITLE_SPLIT_RE = re.compile(r"(?<!^)(?=[A-Z])")

# Nav/Layout/icon-set files are now AI-authored per brand (see codegen/

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

# Paths rewritten by write_safe_stub / stabilize, isolated per workspace.
_stubbed_paths_by_workspace: dict[str, list[str]] = {}
_stubbed_paths_lock = threading.RLock()

# Invalid TS object literals emitted when `{{` was used with %-format (not f-strings).
# Do NOT match valid JSX attribute objects like style={{ color: "red" }}.
_DOUBLE_BRACE_OBJECT_START_RE = re.compile(
    r"\{\{\s*(?:label|detail|status|k|v)\s*:"
)
_DOUBLE_BRACE_ROW_OBJECT_RE = re.compile(
    r"\{\{\s*"
    r"label:\s*(?P<label>(?:\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'))\s*,\s*"
    r"detail:\s*(?P<detail>(?:\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'))\s*,\s*"
    r"status:\s*(?P<status>(?:\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'))\s*"
    r"\}\}"
)
_DOUBLE_BRACE_STAT_OBJECT_RE = re.compile(
    r"\{\{\s*"
    r"k:\s*(?P<k>(?:\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'))\s*,\s*"
    r"v:\s*(?P<v>(?:\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'))\s*"
    r"\}\}"
)


def _is_jsx_attribute_object(content: str, start: int) -> bool:
    """Return True when ``{{`` starts an object-valued JSX attribute."""
    line_start = content.rfind("\n", 0, start) + 1
    line_prefix = content[line_start:start]
    attribute_suffix = r"[A-Za-z_][\w:.-]*\s*=\s*$"
    if re.fullmatch(rf"\s*{attribute_suffix}", line_prefix):
        return True
    return "<" in line_prefix and bool(re.search(rf"\b{attribute_suffix}", line_prefix))


def _workspace_tracking_key(workspace) -> str:
    return str(Path(workspace).resolve(strict=False)).casefold()


def active_fallback_tracker_count() -> int:
    with _stubbed_paths_lock:
        return len(_stubbed_paths_by_workspace)


def consume_stubbed_paths(workspace) -> list[str]:
    """Return and clear paths stubbed for one workspace only."""
    key = _workspace_tracking_key(workspace)
    with _stubbed_paths_lock:
        out = list(dict.fromkeys(_stubbed_paths_by_workspace.pop(key, [])))
    return out


def clear_stubbed_paths(workspace) -> None:
    key = _workspace_tracking_key(workspace)
    with _stubbed_paths_lock:
        _stubbed_paths_by_workspace.pop(key, None)


def record_stubbed_path(workspace, path: str) -> None:
    """Record any deterministic page scaffold, regardless of which path created it."""
    key = _workspace_tracking_key(workspace)
    normalized = path.replace("\\", "/")
    with _stubbed_paths_lock:
        paths = _stubbed_paths_by_workspace.setdefault(key, [])
        if normalized not in paths:
            paths.append(normalized)


def clear_stubbed_path(workspace, path: str) -> None:
    """Remove tracking after a valid AI-authored rewrite replaces a scaffold."""
    key = _workspace_tracking_key(workspace)
    normalized = path.replace("\\", "/")
    with _stubbed_paths_lock:
        paths = _stubbed_paths_by_workspace.get(key, [])
        remaining = [item for item in paths if item != normalized]
        if remaining:
            _stubbed_paths_by_workspace[key] = remaining
        else:
            _stubbed_paths_by_workspace.pop(key, None)


def is_stubbed_path(workspace, path: str) -> bool:
    key = _workspace_tracking_key(workspace)
    normalized = path.replace("\\", "/")
    with _stubbed_paths_lock:
        return normalized in _stubbed_paths_by_workspace.get(key, [])


def is_chrome_path(path: str) -> bool:
    return path.replace("\\", "/").lower() in _CHROME_TEMPLATE_PATHS


def find_double_brace_object_literals(content: str) -> list[str]:
    """Return snippets of invalid `{{ label: ... }}` / `{{ k: ... }}` object literals."""
    source = content or ""
    return [
        m.group(0)
        for m in _DOUBLE_BRACE_OBJECT_START_RE.finditer(source)
        if not _is_jsx_attribute_object(source, m.start())
    ]


def _matching_brace_end(content: str, open_index: int) -> int | None:
    """Return index of `}` matching `{` at open_index, skipping strings."""
    if open_index < 0 or open_index >= len(content) or content[open_index] != "{":
        return None
    depth = 0
    i = open_index
    in_str: str | None = None
    escape = False
    while i < len(content):
        ch = content[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in {'"', "'", "`"}:
            in_str = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _collapse_non_jsx_double_brace_objects(content: str) -> tuple[str, int]:
    """Collapse `{{ … }}` object literals that are not JSX attribute values."""
    if not content or "{{" not in content:
        return content, 0
    repaired = 0
    out: list[str] = []
    i = 0
    while i < len(content):
        if content[i : i + 2] != "{{":
            out.append(content[i])
            i += 1
            continue
        if _is_jsx_attribute_object(content, i):
            out.append(content[i])
            i += 1
            continue
        # Only collapse starts the detector cares about (label/detail/status/k/v).
        if not _DOUBLE_BRACE_OBJECT_START_RE.match(content, i):
            out.append(content[i])
            i += 1
            continue
        inner_end = _matching_brace_end(content, i + 1)
        if inner_end is None or inner_end + 1 >= len(content) or content[inner_end + 1] != "}":
            out.append(content[i])
            i += 1
            continue
        # Strip one outer brace pair: {{ ... }} → { ... }
        out.append(content[i + 1 : inner_end + 1])
        repaired += 1
        i = inner_end + 2
    return "".join(out), repaired


def repair_double_brace_object_literals_in_text(content: str) -> tuple[str, int]:
    """Rewrite invalid double-brace row/stat objects to single-brace TS literals."""
    if not content:
        return content, 0
    repaired = 0

    def _row(m: re.Match[str]) -> str:
        nonlocal repaired
        if _is_jsx_attribute_object(content, m.start()):
            return m.group(0)
        repaired += 1
        return (
            f"{{ label: {m.group('label')}, "
            f"detail: {m.group('detail')}, "
            f"status: {m.group('status')} }}"
        )

    def _stat(m: re.Match[str]) -> str:
        nonlocal repaired
        if _is_jsx_attribute_object(content, m.start()):
            return m.group(0)
        repaired += 1
        return f"{{ k: {m.group('k')}, v: {m.group('v')} }}"

    out = _DOUBLE_BRACE_ROW_OBJECT_RE.sub(_row, content)
    out = _DOUBLE_BRACE_STAT_OBJECT_RE.sub(_stat, out)
    collapsed, n_collapse = _collapse_non_jsx_double_brace_objects(out)
    return collapsed, repaired + n_collapse


def _assert_no_double_brace_object_literals(content: str, path: str = "<memory>") -> None:
    hits = find_double_brace_object_literals(content)
    if hits:
        raise ValueError(
            f"{path}: refusing to write invalid double-brace object literal(s): "
            f"{hits[0][:80]}"
        )


def scan_and_repair_double_brace_literals(workspace, *, architect: dict | None = None) -> list[str]:
    """Scan workspace TS/TSX and repair invalid `{{ label: ... }}` object literals.

    Returns paths that were rewritten. Raises ValueError if suspicious double-brace
    object starts remain after repair (so Vite is not fed known-bad syntax).
    """
    root = workspace if hasattr(workspace, "joinpath") else None
    if root is None:
        return []
    src = root / "src"
    if not src.is_dir():
        return []

    repaired_paths: list[str] = []
    remaining: list[str] = []
    for path in sorted(src.rglob("*")):
        if path.suffix.lower() not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        if not path.is_file():
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if is_template_owned_path(rel, architect, workspace):
            continue
        if path.is_symlink():
            write_trusted_contained_file(
                workspace,
                rel,
                "// replaced unsafe source symlink\nexport {};\n",
            )
            repaired_paths.append(rel)
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not find_double_brace_object_literals(text):
            continue
        fixed, n = repair_double_brace_object_literals_in_text(text)
        if n and fixed != text:
            write_trusted_contained_file(workspace, rel, fixed)
            repaired_paths.append(rel)
            text = fixed
        leftovers = find_double_brace_object_literals(text)
        if leftovers:
            remaining.append(f"{rel}: {leftovers[0][:80]}")

    if remaining:
        raise ValueError(
            "Suspicious double-brace object literals remain after repair:\n  "
            + "\n  ".join(remaining[:12])
        )
    return repaired_paths


def write_template_fallback(workspace, path: str) -> bool:
    """Revert a shared-chrome file to the static template's known-good version.

    Last resort when an AI-authored Nav/Layout/icon-set file keeps breaking
    the build after every fix attempt — guarantees the site never ships
    broken, at the cost of that one file losing its bespoke styling for this
    request. Returns False (caller should fall back to `write_safe_stub`) if
    no template source exists for the path.
    """
    rel = safe_source_path(path, workspace)
    if not rel:
        return False
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
    route: dict | None = None,
    architect: dict | None = None,
) -> None:
    """Overwrite `path` with a minimal, guaranteed-compiling placeholder page.

    Uses only the `brand` export from mock data (always guaranteed to exist),
    so this can never fail to build regardless of what broke the original.
    Copy is lightly industry-aware so stubs don't all look like the same cafe ops board.
    """
    global _last_stubbed_paths
    if (route or {}).get("skeleton_id"):
        content = minimal_catalogue_page_scaffold(
            path,
            route or {},
            brand_name=brand_name,
            architect=architect,
        )
        errors = validate_catalogue_page_content(content, route or {})
        if errors:
            raise ValueError(
                f"{path}: generated catalogue fallback violated contract: "
                + ", ".join(errors)
            )
        write_file(workspace, path, content)
        record_stubbed_path(workspace, path)
        return
    component = _component_name(path)
    mock_prefix = _mock_import_prefix(path)
    title = _friendly_title(path, page_title)
    brand = brand_name or "Brand"
    subtitle, stats, rows = _industry_copy(industry, brand, title)

    # Use f-strings (not %-format) so `{{` / `}}` escape to a single brace in
    # the emitted TS — matching stats_js. %-format left `{{` literal and broke Vite.
    stats_js = ",\n          ".join(
        f"{{ k: {json.dumps(s['k'], ensure_ascii=False)}, v: {json.dumps(s['v'], ensure_ascii=False)} }}"
        for s in stats
    )
    rows_js = ",\n    ".join(
        f"{{ label: {json.dumps(r['label'], ensure_ascii=False)}, "
        f"detail: {json.dumps(r['detail'], ensure_ascii=False)}, "
        f"status: {json.dumps(r['status'], ensure_ascii=False)} }}"
        for r in rows
    )

    content = f"""import {{ brand }} from '{mock_prefix}data/mock';

export default function {component}() {{
  const rows = [
    {rows_js},
  ];

  return (
    <div className="relative mx-auto max-w-5xl overflow-hidden px-6 py-12">
      <div aria-hidden className="ui-mesh opacity-70" />
      <div className="relative">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border-subtle pb-8">
        <div>
          <p className="text-sm font-medium uppercase tracking-wide text-brand">{{brand.name}}</p>
          <h1 className="mt-2 font-display text-3xl font-bold tracking-tight text-foreground">{title}</h1>
          <p className="mt-2 max-w-xl text-muted">
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
          <div key={{stat.k}} className="rounded-[calc(var(--radius-ui)+0.35rem)] border border-border-subtle bg-card p-5 shadow-[var(--shadow-ui)]">
            <p className="text-sm text-muted">{{stat.k}}</p>
            <p className="mt-2 font-display text-2xl font-bold text-foreground">{{stat.v}}</p>
          </div>
        ))}}
      </div>

      <div className="mt-8 overflow-hidden rounded-[calc(var(--radius-ui)+0.35rem)] border border-border-subtle bg-card shadow-[var(--shadow-ui)]">
        <div className="border-b border-border-subtle px-5 py-4">
          <h2 className="font-semibold text-foreground">Today&apos;s activity</h2>
        </div>
        <ul className="divide-y divide-border-subtle">
          {{rows.map((row) => (
            <li key={{row.label}} className="flex items-center justify-between gap-4 px-5 py-4">
              <div>
                <p className="font-medium text-foreground">{{row.label}}</p>
                <p className="text-sm text-muted">{{row.detail}}</p>
              </div>
              <span className="rounded-full bg-brand/10 px-3 py-1 text-xs font-semibold text-brand">
                {{row.status}}
              </span>
            </li>
          ))}}
        </ul>
      </div>
      </div>
    </div>
  );
}}
"""
    _assert_no_double_brace_object_literals(content, path)
    write_file(workspace, path, content)
    record_stubbed_path(workspace, path)


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
        if is_template_owned_path(path, architect):
            continue
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
            route=rt,
        )
        rewritten.append(path)

    # Always ensure a HomePage exists for the catch-all redirect.
    home = "src/pages/HomePage.tsx"
    if not has_catalogue_routes(architect) and home not in rewritten:
        write_safe_stub(workspace, home, brand_name=brand_name, industry=industry, page_title="Home")
        rewritten.append(home)
    return rewritten
