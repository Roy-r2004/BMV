"""The defects a live generation (request 40) shipped past every green gate.

Request 40 finished `status=ready`, `quality gate PASSED`, 9 type errors, zero
broken image paths — and was not shippable:

* `/owner/paintings` rendered *"Meet the team — Dr. Avery Chen, Family medicine"*
  on a fine-art gallery, wearing the public storefront nav.
* all six `/gallery` cards linked to `/artwork/1…6` and every one of them
  rendered *"We could not find that one."*
* the home page's two primary CTAs pointed at `/collection`, which no route
  serves, so the first click bounced the visitor back where they started.
* `/owner/paintings/1` rendered an empty *"Add New Painting"* form.
* `BRAND_MANIFEST` carried `design_system` twice, the second one a generic
  palette that wins at runtime over the sealed brand.
* the `trust` marquee received `{ label: { label } }` and rendered nothing.
* five of six screenshots died in a Playwright thread race, so the one component
  that looks at pixels judged one page and the four defects above went unseen.

Every one had an accurate measurement somewhere — a TS2339, a TS1117, a TS2322,
a `journey_dead_link_offpath` warning — and no reader that could stop a demo.
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

from app.application.preview_app import screenshot as shot  # noqa: E402
from app.application.preview_app.assemble import write_app_tsx  # noqa: E402
from app.application.preview_app.capabilities.journey import (  # noqa: E402
    repair_dead_internal_links,
    walk_journey,
)
from app.application.preview_app.catalogue_contract.item_source import (  # noqa: E402
    catalogue_detail_base,
    unify_catalogue_item_source,
)
from app.application.preview_app.catalogue_contract.scaffold import (  # noqa: E402
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.safety.brand_contract import ensure_brand_shape  # noqa: E402
from app.application.services.industry_images import (  # noqa: E402
    _ITEM_SLOTS,
    normalize_image_slot_map,
)
from app.infrastructure.templating.renderer import get_template_renderer  # noqa: E402


# --------------------------------------------------------------------------- #
# the owner's listing page is not a doctor directory
# --------------------------------------------------------------------------- #

_OPS_LISTING_ROUTE = {
    "path": "/owner/paintings",
    "component_file": "src/pages/owner/AdminPaintingListPage.tsx",
    "surface": "ops",
    "skeleton_id": "ops-list",
    "title": "Manage Paintings – Canvas Curator",
    "page_intent": "listing",
    "section_slots": ["header", "filters", "table"],
}


def test_an_ops_listing_never_gets_the_public_directory_face() -> None:
    """`page_intent: listing` must not outrank surface.

    The directory scaffold builds PublicShell + PublicNav + CatalogGrid. Handing
    it an ops route produced the owner's page wearing the storefront nav, and the
    contract validator then rejected it three times for the OpsShell/header/
    filters/table it structurally could not contain.
    """
    tsx = minimal_catalogue_page_scaffold(
        _OPS_LISTING_ROUTE["component_file"], _OPS_LISTING_ROUTE, brand_name="Jeanne Kassab Art"
    )

    assert "OpsShell" in tsx, "an owner page must wear the ops shell"
    assert "PublicShell" not in tsx
    assert "Dr. Avery Chen" not in tsx
    assert "Meet the team" not in tsx


def test_no_scaffold_invents_a_medical_practice() -> None:
    """The fake-doctor fallback is gone from every face this scaffold can build."""
    for route in (
        _OPS_LISTING_ROUTE,
        {**_OPS_LISTING_ROUTE, "path": "/gallery", "surface": "public",
         "skeleton_id": "public-catalog", "title": "Latest Works",
         "component_file": "src/pages/GalleryHomePage.tsx",
         "section_slots": ["hero", "showcase", "footer"]},
    ):
        tsx = minimal_catalogue_page_scaffold(
            route["component_file"], route, brand_name="Jeanne Kassab Art"
        )
        assert "Dr. Avery Chen" not in tsx
        assert "Family medicine" not in tsx


def test_the_public_listing_reads_the_catalogue_not_a_manifest_key_that_is_absent() -> None:
    """`BRAND_MANIFEST.services` does not exist at that level.

    `tsc` reported it twice as TS2339 on request 40, and because the read returned
    `undefined` the hardcoded doctors were not a rare fallback — they were the only
    possible outcome on that path.
    """
    route = {
        "path": "/gallery",
        "component_file": "src/pages/GalleryHomePage.tsx",
        "surface": "public",
        "skeleton_id": "public-catalog",
        "title": "Latest Works",
        "page_intent": "listing",
        "section_slots": ["hero", "showcase", "footer"],
    }
    tsx = minimal_catalogue_page_scaffold(
        route["component_file"], route, brand_name="Jeanne Kassab Art"
    )
    code = "\n".join(
        line for line in tsx.splitlines() if not line.lstrip().startswith("//")
    )
    assert "BRAND_MANIFEST" not in code, "the absent manifest key must not be read"
    assert "(seed as any).items" in code


# --------------------------------------------------------------------------- #
# one catalogue for the whole app
# --------------------------------------------------------------------------- #

_INLINED_GRID = """\
import { images, seed } from '@/data/mock';
import { CatalogGrid, PublicShell } from '@/ui';

export default function GalleryHomePage() {
  return (
    <PublicShell brandName={"Jeanne Kassab Art"}>
      <CatalogGrid
        heading={"Latest Works"}
        detailBase="/artwork"
        itemNoun="paintings"
        items={[
          { id: '1', title: 'Whispering Winds', description: 'Movement of air.', imageSrc: images.card1, meta: 'Oil on Canvas', status: 'Available' },
          { id: '2', title: 'Coastal Echoes', description: 'Memory of the sea.', imageSrc: images.card2, meta: 'Oil on Panel', status: 'Available' },
        ]}
      />
    </PublicShell>
  );
}
"""

_ARCHITECT = {
    "routes": [
        {"path": "/", "component_file": "src/pages/HomePage.tsx", "surface": "public"},
        {"path": "/gallery", "component_file": "src/pages/GalleryHomePage.tsx", "surface": "public"},
        {"path": "/gallery/:id", "component_file": "src/pages/ArtworkDetailPage.tsx", "surface": "public"},
        {"path": "/artwork/:slug", "component_file": "src/pages/ArtworkDetailPage.tsx", "surface": "public"},
        {"path": "/owner/paintings/:id", "component_file": "src/pages/owner/AdminEditPaintingPage.tsx", "surface": "ops"},
    ],
}


def test_an_inlined_catalogue_is_repointed_at_the_one_seed_list() -> None:
    out, changed = unify_catalogue_item_source(
        _INLINED_GRID, detail_base=catalogue_detail_base(_ARCHITECT)
    )

    assert changed == ["CatalogGrid"]
    assert "seed.items" in out
    # The invented ids are what dead-ended every card.
    assert "id: '1'" not in out
    assert "Whispering Winds" not in out
    # Layout and copy the model authored are left alone.
    assert 'heading={"Latest Works"}' in out
    assert 'itemNoun="paintings"' in out


def test_the_detail_base_prefers_a_route_whose_listing_also_exists() -> None:
    """`/gallery` is declared; `/artwork` is not, so cards must not link there."""
    assert catalogue_detail_base(_ARCHITECT) == "/gallery"


def test_the_ops_surface_keeps_its_own_records() -> None:
    """An owner table is not the storefront catalogue."""
    from app.application.preview_app.catalogue_contract.repair import _is_ops_surface_file

    assert _is_ops_surface_file("src/pages/owner/AdminPaintingListPage.tsx", {"path": "/owner/paintings"})
    assert not _is_ops_surface_file("src/pages/GalleryHomePage.tsx", {"path": "/gallery"})


def test_the_rewrite_is_idempotent() -> None:
    base = catalogue_detail_base(_ARCHITECT)
    once, _ = unify_catalogue_item_source(_INLINED_GRID, detail_base=base)
    twice, changed = unify_catalogue_item_source(once, detail_base=base)

    assert changed == []
    assert twice == once


def test_a_literal_that_cannot_be_spanned_is_left_alone() -> None:
    """A codemod that is not certain where the array ends does nothing."""
    truncated = _INLINED_GRID.replace("]}\n      />", "")
    out, changed = unify_catalogue_item_source(truncated, detail_base="/gallery")

    assert changed == []
    assert out == truncated


def test_a_non_catalogue_items_prop_is_untouched() -> None:
    """`items` is a common prop name; only listing components are rewritten."""
    source = (
        "import { LogoMarquee } from '@/ui';\n"
        "import { seed } from '@/data/mock';\n"
        "export default function P() {\n"
        "  return <LogoMarquee items={[{ label: 'Featured in Art Monthly' }]} />;\n"
        "}\n"
    )
    out, changed = unify_catalogue_item_source(source, detail_base="/gallery")

    assert changed == []
    assert out == source


def test_the_detail_page_resolves_a_numbered_link() -> None:
    """`/artwork/1` must find the first item even when seed ids are slugs.

    Request 40's grid numbered its cards and its seed used slugs, so all six
    cards resolved to nothing while the journey walk called the hop healthy.
    """
    route = {
        "path": "/artwork/:slug",
        "component_file": "src/pages/ArtworkDetailPage.tsx",
        "surface": "public",
        "skeleton_id": "public-detail",
        "title": "Artwork",
        "section_slots": ["hero", "credentials", "inquire", "footer"],
    }
    tsx = minimal_catalogue_page_scaffold(
        route["component_file"], route, brand_name="Jeanne Kassab Art"
    )

    assert "String(index + 1) === itemKey" in tsx, "a numbered link must resolve"
    assert "itemToken(entry?.slug)" in tsx
    assert "itemToken(entry?.title)" in tsx


# --------------------------------------------------------------------------- #
# a dead primary CTA is not a warning
# --------------------------------------------------------------------------- #

def _storefront(tmp_path: Path, home_body: str) -> dict:
    architect = {
        "product_kind": "storefront",
        "routes": [
            {
                "path": "/",
                "component_file": "src/pages/HomePage.tsx",
                "surface": "public",
                "skeleton_id": "public-home",
                "title": "Home",
                "section_slots": ["hero", "showcase", "footer"],
            },
            {
                "path": "/gallery",
                "component_file": "src/pages/GalleryHomePage.tsx",
                "surface": "public",
                "skeleton_id": "public-catalog",
                "title": "Gallery",
                "page_intent": "listing",
                "section_slots": ["hero", "showcase", "footer"],
            },
            {
                "path": "/gallery/:id",
                "component_file": "src/pages/ArtworkDetailPage.tsx",
                "surface": "public",
                "skeleton_id": "public-detail",
                "title": "Artwork",
                "section_slots": ["hero", "credentials", "inquire", "footer"],
            },
            {
                "path": "/owner/paintings",
                "component_file": "src/pages/owner/AdminPaintingListPage.tsx",
                "surface": "ops",
                "skeleton_id": "ops-list",
                "title": "Paintings",
                "section_slots": ["header", "filters", "table"],
            },
        ],
    }
    for route in architect["routes"]:
        rel = route["component_file"]
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            home_body
            if rel == "src/pages/HomePage.tsx"
            else minimal_catalogue_page_scaffold(rel, route, brand_name="Jeanne Kassab Art"),
            encoding="utf-8",
        )
    return architect


_DEAD_CTA_HOME = """\
import { MarketingHero } from '@/ui';

export default function HomePage() {
  return (
    <MarketingHero
      headline={"Capturing Light and Landscape on Canvas"}
      primaryCta={{ label: "View the Collection", href: "/collection" }}
    />
  );
}
"""


def test_a_dead_link_on_a_public_page_fails_the_gate(tmp_path: Path) -> None:
    architect = _storefront(tmp_path, _DEAD_CTA_HOME)

    report = walk_journey(tmp_path, architect)

    dead = [f for f in report.blocking if f.code == "journey_dead_link_offpath"]
    assert dead, [
        (f.code, f.advisory, f.message) for f in report.findings
    ]
    assert "/collection" in dead[0].message


def test_a_dead_link_on_an_owner_page_stays_advisory(tmp_path: Path) -> None:
    """P0-4's policy: never withhold a working storefront over an ops page."""
    architect = _storefront(tmp_path, _DEAD_CTA_HOME)
    ops = tmp_path / "src/pages/owner/AdminPaintingListPage.tsx"
    ops.write_text(
        ops.read_text(encoding="utf-8").replace(
            "export default", "const OPS_DEAD = '/ai-features';\nexport default"
        ),
        encoding="utf-8",
    )

    report = walk_journey(tmp_path, architect)

    ops_findings = [
        f for f in report.findings
        if f.component_file.endswith("AdminPaintingListPage.tsx")
        and f.code == "journey_dead_link_offpath"
    ]
    assert ops_findings, "the ops dead link must still be reported"
    assert all(f.advisory for f in ops_findings)


def test_the_heal_repoints_a_dead_cta_at_the_route_it_meant(tmp_path: Path) -> None:
    """Blocking is only defensible because this fixes it without a model call."""
    architect = _storefront(tmp_path, _DEAD_CTA_HOME)

    healed = repair_dead_internal_links(tmp_path, architect)

    assert "src/pages/HomePage.tsx" in healed
    home = (tmp_path / "src/pages/HomePage.tsx").read_text(encoding="utf-8")
    assert '"/collection"' not in home
    assert '"/gallery"' in home
    assert walk_journey(tmp_path, architect).blocking == []


def test_the_heal_leaves_a_link_it_cannot_place(tmp_path: Path) -> None:
    """Guessing a target is worse than handing it to the AI repair pass."""
    architect = _storefront(
        tmp_path,
        _DEAD_CTA_HOME.replace("/collection", "/franchise-opportunities"),
    )

    repair_dead_internal_links(tmp_path, architect)

    home = (tmp_path / "src/pages/HomePage.tsx").read_text(encoding="utf-8")
    assert "/franchise-opportunities" in home


# --------------------------------------------------------------------------- #
# `parent/:id` addresses a record, not the create form
# --------------------------------------------------------------------------- #

def _routes_in_app_tsx(architect: dict, tmp_path: Path) -> dict[str, str]:
    import re

    pages = tmp_path / "src" / "pages"
    for route in architect["routes"]:
        rel = route["component_file"]
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        component = route["component"]
        target.write_text(
            f"export default function {component}() {{ return <div />; }}\n",
            encoding="utf-8",
        )
    assert pages.exists()
    write_app_tsx(tmp_path, architect, get_template_renderer())
    app = (tmp_path / "src" / "App.tsx").read_text(encoding="utf-8")
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r'<Route\s+path="([^"]+)"\s+element=\{<(\w+)', app)
    }


_OWNER_PAGES = [
    ("/owner/paintings", "AdminPaintingListPage"),
    ("/owner/paintings/add", "AdminAddPaintingPage"),
    ("/owner/paintings/edit/:id", "AdminEditPaintingPage"),
]


def test_a_param_route_renders_the_record_page_not_the_create_form(tmp_path: Path) -> None:
    """Request 40 aliased `/owner/paintings/:id` onto AdminAddPaintingPage.

    Opening any painting from the owner list showed an empty "Add New Painting"
    form, while the edit page was reachable only at `/owner/paintings/edit/1`.
    """
    architect = {
        "routes": [
            {
                "path": path,
                "component_file": f"src/pages/owner/{component}.tsx",
                "component": component,
                "surface": "ops",
            }
            for path, component in _OWNER_PAGES
        ],
        "files_to_generate": [],
        "roles": [],
    }

    routes = _routes_in_app_tsx(architect, tmp_path)

    assert routes.get("/owner/paintings/:id") != "AdminAddPaintingPage"
    if "/owner/paintings/:id" in routes:
        assert routes["/owner/paintings/:id"] == "AdminEditPaintingPage"


# --------------------------------------------------------------------------- #
# the sealed brand is not silently replaced
# --------------------------------------------------------------------------- #

_SEALED_MOCK = """\
export const brand = {
  name: 'Jeanne Kassab Art',
  design_system: {
    display_font_family: 'Fraunces',
    border_radius: '0.63rem',
    recipe_id: 'editorial',
  },
  services: [{ name: 'Originals' }],
  testimonials: [{ quote: 'Lovely', author: 'A collector' }],
  client_names: ['A collector'],
  social_proof: { count: 40 },
};
"""


def test_a_thin_design_system_is_completed_not_re_declared(tmp_path: Path) -> None:
    """Appending a sibling `design_system` makes the last one win.

    Request 40 shipped `BRAND_MANIFEST` with two of them: the sealed brand (Fraunces,
    0.63rem, recipe tokens) and a generic patch that overrode it at runtime. `tsc`
    reported TS1117 and nothing read it.
    """
    (tmp_path / "src/data").mkdir(parents=True)
    (tmp_path / "src/data/mock.ts").write_text(_SEALED_MOCK, encoding="utf-8")

    changed = ensure_brand_shape(tmp_path, "Jeanne Kassab Art", "#0f172a", "#0369a1", "Fraunces")
    mock = (tmp_path / "src/data/mock.ts").read_text(encoding="utf-8")

    assert changed is True
    assert mock.count("design_system:") == 1, "the sealed design_system was re-declared"
    assert "display_font_family: 'Fraunces'" in mock, "the sealed values must survive"
    assert "primary_color" in mock, "the missing colour must still be filled in"


def test_completing_the_design_system_is_idempotent(tmp_path: Path) -> None:
    (tmp_path / "src/data").mkdir(parents=True)
    (tmp_path / "src/data/mock.ts").write_text(_SEALED_MOCK, encoding="utf-8")

    ensure_brand_shape(tmp_path, "Jeanne Kassab Art", "#0f172a", "#0369a1", "Fraunces")
    once = (tmp_path / "src/data/mock.ts").read_text(encoding="utf-8")
    ensure_brand_shape(tmp_path, "Jeanne Kassab Art", "#0f172a", "#0369a1", "Fraunces")
    twice = (tmp_path / "src/data/mock.ts").read_text(encoding="utf-8")

    assert twice == once
    assert twice.count("primary_color") == 1


# --------------------------------------------------------------------------- #
# every catalogue position has its own photograph
# --------------------------------------------------------------------------- #

def test_item_slots_always_exist_so_a_page_can_index_them() -> None:
    slots = normalize_image_slot_map({"hero": "https://images.pexels.com/photos/1/a.jpeg"})

    for slot in _ITEM_SLOTS:
        assert slots.get(slot), f"{slot} must be present for `images.{slot}` to typecheck"


def test_fetched_item_photos_are_distinct() -> None:
    fetched = {
        "hero": "https://images.pexels.com/photos/1/a.jpeg",
        "hero2": "https://images.pexels.com/photos/2/b.jpeg",
        "card1": "https://images.pexels.com/photos/3/c.jpeg",
        "card2": "https://images.pexels.com/photos/4/d.jpeg",
        "card3": "https://images.pexels.com/photos/5/e.jpeg",
        "ambient": "https://images.pexels.com/photos/6/f.jpeg",
        **{
            slot: f"https://images.pexels.com/photos/{10 + i}/item.jpeg"
            for i, slot in enumerate(_ITEM_SLOTS)
        },
    }

    slots = normalize_image_slot_map(fetched)

    urls = [slots[slot] for slot in _ITEM_SLOTS]
    assert len(set(urls)) == len(urls), "two catalogue items shared a photograph"


# --------------------------------------------------------------------------- #
# the trust marquee is handed labels, not labels wrapped in labels
# --------------------------------------------------------------------------- #

def test_the_trust_slot_accepts_both_seed_shapes() -> None:
    """`trustLabels` is strings in the deterministic seed and objects from the model."""
    route = {
        "path": "/gallery",
        "component_file": "src/pages/GalleryHomePage.tsx",
        "surface": "public",
        "skeleton_id": "public-catalog",
        "title": "Gallery",
        "section_slots": ["hero", "trust", "showcase", "footer"],
    }
    tsx = minimal_catalogue_page_scaffold(
        route["component_file"], route, brand_name="Jeanne Kassab Art"
    )

    assert "map((label) => ({ label }))" not in tsx, "double-wrapping is TS2322"
    assert "entry?.label ?? entry" in tsx


# --------------------------------------------------------------------------- #
# screenshots are serial, so a thread race cannot cost five of six pages
# --------------------------------------------------------------------------- #

class _RacyPlaywright:
    """Fails any session entered while another is open, like the real driver."""

    def __init__(self) -> None:
        self.open = 0
        self.max_open = 0
        self.sessions = 0
        self._lock = threading.Lock()

    def __enter__(self):
        with self._lock:
            self.open += 1
            self.sessions += 1
            self.max_open = max(self.max_open, self.open)
            if self.open > 1:
                raise RuntimeError("Racing with another loop to spawn a process.")
        return object()

    def __exit__(self, *_a):
        with self._lock:
            self.open -= 1
        return False


class _Page:
    def __init__(self) -> None:
        self.closed = False

    def evaluate(self, js):
        return 900 if "scrollHeight" in js else []

    def wait_for_timeout(self, _ms):
        return None

    def wait_for_function(self, _js, **_kw):
        return True

    def goto(self, _url, **_kw):
        return None

    def screenshot(self, **kwargs):
        path = Path(kwargs["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG")

    def close(self):
        self.closed = True


class _Browser:
    def __init__(self) -> None:
        self.pages: list[_Page] = []
        self.closed = False

    def new_page(self, **_kwargs):
        page = _Page()
        self.pages.append(page)
        return page

    def close(self):
        self.closed = True


@pytest.fixture()
def racy_playwright(monkeypatch: pytest.MonkeyPatch) -> _RacyPlaywright:
    racy = _RacyPlaywright()
    browser = _Browser()
    monkeypatch.setattr(shot, "_launch_chromium", lambda _p: browser)
    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        type("_M", (), {"sync_playwright": staticmethod(lambda: racy)}),
    )
    return racy


def test_a_batch_of_routes_opens_one_browser_session(tmp_path: Path, racy_playwright) -> None:
    routes = [(f"/page-{i}", tmp_path / f"shot_{i}.png") for i in range(6)]

    captures = shot.capture_routes_visual("http://api/api/preview-apps/41", routes)

    assert [c.ok for c in captures] == [True] * 6
    assert racy_playwright.sessions == 1, "one session for the batch, not one per route"
    assert racy_playwright.max_open == 1


def test_concurrent_single_route_captures_do_not_race(tmp_path: Path, racy_playwright) -> None:
    """The re-measure path and the QA harness call the single-route helper.

    Without the session lock, four worker threads entering Playwright together
    lost three of four pages to `Racing with another loop to spawn a process.`
    """
    results: list[bool] = []
    lock = threading.Lock()

    def _capture(index: int) -> None:
        capture = shot.capture_route_visual(
            "http://api/api/preview-apps/41", f"/page-{index}", tmp_path / f"t_{index}.png"
        )
        with lock:
            results.append(capture.ok)

    threads = [threading.Thread(target=_capture, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == [True] * 4, "a thread race cost a page its only measurement"
    assert racy_playwright.max_open == 1


def test_one_bad_route_does_not_lose_the_rest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    browser = _Browser()

    class _Ctx:
        def __enter__(self):
            return object()

        def __exit__(self, *_a):
            return False

    def _new_page(**_kwargs):
        page = _Page()
        if len(browser.pages) == 1:
            def _boom(*_a, **_kw):
                raise RuntimeError("net::ERR_ABORTED")

            page.goto = _boom  # type: ignore[method-assign]
        browser.pages.append(page)
        return page

    browser.new_page = _new_page  # type: ignore[method-assign]
    monkeypatch.setattr(shot, "_launch_chromium", lambda _p: browser)
    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        type("_M", (), {"sync_playwright": staticmethod(lambda: _Ctx())}),
    )

    captures = shot.capture_routes_visual(
        "http://api/api/preview-apps/41",
        [(f"/page-{i}", tmp_path / f"s_{i}.png") for i in range(3)],
    )

    assert [c.ok for c in captures] == [True, False, True]


def test_a_session_that_will_not_launch_reports_every_route_unmeasured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Boom:
        def __enter__(self):
            raise RuntimeError("no browser in this image")

        def __exit__(self, *_a):
            return False

    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        type("_M", (), {"sync_playwright": staticmethod(lambda: _Boom())}),
    )

    captures = shot.capture_routes_visual(
        "http://api/api/preview-apps/41",
        [(f"/page-{i}", tmp_path / f"x_{i}.png") for i in range(3)],
    )

    assert [c.ok for c in captures] == [False, False, False]


# --------------------------------------------------------------------------- #
# a skipped refine is not a refine
# --------------------------------------------------------------------------- #

def test_refine_file_reports_the_pages_it_declines_to_touch(tmp_path: Path) -> None:
    """Request 40 logged `refined 2 page(s)` for two pages it left untouched.

    Both had scored 60 `revise`, both were skipped as contract-driven utility
    pages, and both then failed `vite build` with adjacent-JSX syntax errors.
    """
    from app.application.preview_app.codegen.critic import refine_file

    rel = "src/pages/ContactPage.tsx"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "// composed public-utility page\nexport default function P() { return null }\n",
        encoding="utf-8",
    )
    skipped: list[str] = []

    refine_file(
        tmp_path,
        rel,
        "",
        "fix the hero",
        "",
        {},
        {},
        ai_provider=None,
        template_renderer=None,
        architect={"routes": []},
        skipped_out=skipped,
    )

    assert skipped == [rel], "a caller cannot report honestly without this"


def test_the_critic_does_not_count_a_skipped_page_as_refined(tmp_path: Path) -> None:
    import app.application.preview_app.codegen.critic as critic

    rel = "src/pages/ContactPage.tsx"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "// composed public-utility page\nexport default function P() { return null }\n",
        encoding="utf-8",
    )

    calls: list[str] = []

    def _fake_critique(_ws, path, *_a, **_kw):
        calls.append(path)
        return {"verdict": "revise", "score": 60, "revision_instructions": "tighten the hero"}

    original = critic.critique_file
    critic.critique_file = _fake_critique  # type: ignore[assignment]
    try:
        refined = critic.critique_and_refine(
            tmp_path,
            [{"path": rel, "kind": "page", "instructions": ""}],
            "",
            "",
            {},
            {},
            None,
            None,
            architect={"routes": []},
            max_workers=1,
        )
    finally:
        critic.critique_file = original  # type: ignore[assignment]

    assert calls == [rel], "the critic must still have reviewed the page"
    assert refined == [], "a page the refiner declined must not be reported as refined"


def test_json_shape_of_the_visual_summary_is_unchanged() -> None:
    """The honesty fields request 40 proved correct must keep their names."""
    from app.application.preview_app.pipeline.visual_critic import VisualCritiqueReport

    report = VisualCritiqueReport()
    report.reviewed.append("src/pages/HomePage.tsx")
    report.unmeasured.append("src/pages/ContactPage.tsx")

    payload = json.loads(json.dumps(report.to_dict()))

    assert "reviewed" in payload and "unmeasured" in payload


# --------------------------------------------------------------------------- #
# request 41: a repaired page shipped a stack trace under `status=ready`
# --------------------------------------------------------------------------- #

def test_an_injected_ai_panel_brings_its_own_import() -> None:
    """The panel references `aiFeatures`; the page must import it.

    `_ensure_mock_import` ran *before* the reference existed, so its
    `if "aiFeatures" in source` guard was never true on a first injection and
    execution fell through to "this page already imports from @/data/mock —
    nothing to do". Request 41's home page and artwork-management page both
    shipped `aiFeatures is not defined`, and the preview reported `ready`.
    """
    from app.application.preview_app.ai_feature_surfaces import inject_ai_panel_into_page

    page = (
        "import { images, seed } from '@/data/mock';\n"
        "import { MarketingHero, PublicShell } from '@/ui';\n"
        "\n"
        "export default function HomePage() {\n"
        "  return (\n"
        "    <PublicShell brandName={'Jeanne Kassab Art'}>\n"
        "      <MarketingHero headline={seed.hero.headline} imageSrc={images.hero} />\n"
        "    </PublicShell>\n"
        "  );\n"
        "}\n"
    )

    out = inject_ai_panel_into_page(page, feature_id="smart-image-optimization", brand_name="Jeanne Kassab Art")

    assert "aiFeatures" in out, "the panel was injected"
    import re as _re

    mock_import = _re.search(r"import\s*\{([^}]*)\}\s*from\s*'@/data/mock'", out)
    assert mock_import, "the mock import must survive"
    names = {n.strip() for n in mock_import.group(1).split(",")}
    assert "aiFeatures" in names, f"reference without import → runtime crash (got {names})"
    assert {"images", "seed"} <= names, "the page's existing imports must survive"


def test_injecting_a_panel_twice_adds_one_import() -> None:
    from app.application.preview_app.ai_feature_surfaces import inject_ai_panel_into_page

    page = (
        "import { seed } from '@/data/mock';\n"
        "export default function P() { return <div>{seed.hero.headline}</div>; }\n"
    )

    once = inject_ai_panel_into_page(page, feature_id="f1", brand_name="Brand")
    twice = inject_ai_panel_into_page(once, feature_id="f1", brand_name="Brand")

    assert twice == once
    import re as _re

    imports = _re.findall(r"import\s*\{([^}]*)\}\s*from\s*'@/data/mock'", once)
    assert len(imports) == 1, f"one mock import line, got {imports}"
    assert imports[0].count("aiFeatures") == 1, f"one aiFeatures name, got {imports[0]!r}"


def test_the_error_boundary_is_machine_readable() -> None:
    """A crashed page must be detectable without asking a model.

    The vision critic looked at request 41's error box and reported "the hero
    image is a photograph of an artist painting in a studio", scoring it 65.
    """
    main_tsx = (
        Path(__file__).resolve().parents[2] / "preview-template" / "src" / "main.tsx"
    ).read_text(encoding="utf-8")

    assert "data-preview-render-error" in main_tsx


def test_the_probe_reports_a_rendered_error_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _CrashPage(_Page):
        def evaluate(self, js):
            if "scrollHeight" in js:
                return 900
            if "data-preview-render-error" in js:
                return "aiFeatures is not defined"
            return []

    browser = _Browser()
    browser.new_page = lambda **_kw: _CrashPage()  # type: ignore[method-assign]

    class _Ctx:
        def __enter__(self):
            return object()

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(shot, "_launch_chromium", lambda _p: browser)
    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        type("_M", (), {"sync_playwright": staticmethod(lambda: _Ctx())}),
    )

    capture = shot.capture_route_visual(
        "http://api/api/preview-apps/41", "/", tmp_path / "shot.png"
    )

    assert capture.ok is True, "the shot itself succeeded — the page rendered *something*"
    assert capture.render_error == "aiFeatures is not defined"


def test_a_crashed_public_page_is_a_block_and_a_crashed_ops_page_is_a_warning() -> None:
    from app.application.preview_app.pipeline.visual_critic import (
        VisualCritiqueReport,
        _record_render_errors,
    )
    from app.application.preview_app.screenshot import RouteCapture

    report = VisualCritiqueReport()
    routes = [
        (1, {"path": "/", "component_file": "src/pages/HomePage.tsx", "surface": "public"}),
        (2, {"path": "/owner/dashboard", "component_file": "src/pages/owner/DashboardPage.tsx", "surface": "ops"}),
    ]
    captures = {
        1: RouteCapture(ok=True, render_error="aiFeatures is not defined"),
        2: RouteCapture(ok=True, render_error="stats is not defined"),
    }

    _record_render_errors(report, routes, captures, db=None, request_id=0)

    codes = {(f.path, f.severity) for f in report.findings if f.code == "page_failed_to_render"}
    assert ("src/pages/HomePage.tsx", "block") in codes
    assert ("src/pages/owner/DashboardPage.tsx", "warn") in codes
    assert len(report.blocking) == 1, "an owner page must not withhold the storefront"


def test_the_smoke_check_walks_public_routes_first_and_resolves_params() -> None:
    from app.application.preview_app.pipeline.finalize import _smoke_routes

    architect = {
        "routes": [
            {"path": "/owner/dashboard", "component_file": "src/pages/owner/DashboardPage.tsx", "surface": "ops"},
            {"path": "/gallery/:id", "component_file": "src/pages/ArtworkDetailPage.tsx", "surface": "public"},
            {"path": "/", "component_file": "src/pages/HomePage.tsx", "surface": "public"},
            {"path": "*", "component_file": "src/pages/HomePage.tsx", "surface": "public"},
        ]
    }

    routes = _smoke_routes(architect)

    assert [r[0] for r in routes] == ["/gallery/1", "/", "/owner/dashboard"]
    assert [r[2] for r in routes] == ["public", "public", "ops"]


# --------------------------------------------------------------------------- #
# a fix model that failed is not asked again in the same run
# --------------------------------------------------------------------------- #

def test_a_failed_fix_model_is_skipped_for_the_rest_of_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """`FIX_MODEL` failed on every run observed: unparseable JSON (39), truncated
    output after 230s (40), truncated again (42). The fallback then did the work.
    Paying that charge once per process instead of once per round is most of why
    request 40's typecheck repair took 6m10s of a 13m28s run.
    """
    import app.application.preview_app.codegen.fix_agent as fa
    from app.core.config import settings

    monkeypatch.setattr(settings, "FIX_MODEL", "slow/model")
    monkeypatch.setattr(settings, "PREVIEW_APP_MODEL", "fast/model")
    monkeypatch.setattr(settings, "TEXT_MODEL", "fast/model")
    monkeypatch.setattr(fa, "_FAILED_FIX_MODELS", set())

    asked: list[str] = []

    class _AI:
        def ask_chat(self, model, _messages, **_kw):
            asked.append(model)
            if model == "slow/model":
                raise RuntimeError("Provider output was truncated.")
            return '{"files": []}'

    ai = _AI()
    assert fa._ask_fix_model(ai, "round one")
    assert fa._ask_fix_model(ai, "round two")

    assert asked.count("slow/model") == 1, f"the failing model was re-asked: {asked}"
    assert asked.count("fast/model") == 2


def test_every_model_failing_still_falls_back_to_the_full_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skipping must never leave the chain empty — an outage may have ended."""
    import app.application.preview_app.codegen.fix_agent as fa
    from app.core.config import settings

    monkeypatch.setattr(settings, "FIX_MODEL", "a/model")
    monkeypatch.setattr(settings, "PREVIEW_APP_MODEL", "b/model")
    monkeypatch.setattr(settings, "TEXT_MODEL", "c/model")
    monkeypatch.setattr(fa, "_FAILED_FIX_MODELS", {"a/model", "b/model", "c/model"})

    asked: list[str] = []

    class _AI:
        def ask_chat(self, model, _messages, **_kw):
            asked.append(model)
            return '{"files": []}'

    assert fa._ask_fix_model(_AI(), "prompt")
    assert asked == ["a/model"], f"the chain must still be tried, got {asked}"


# --------------------------------------------------------------------------- #
# request 42: a page read a seed key the seed never defined
# --------------------------------------------------------------------------- #

_SEED_MOCK = """\
export const seed = {
  hero: { headline: 'Capturing Light', subcopy: 'Original oils.' },
  items: [{ id: 'whispering-winds', title: 'Whispering Winds' }],
};
"""


def _seed_workspace(tmp_path: Path, page_source: str) -> Path:
    (tmp_path / "src/data").mkdir(parents=True)
    (tmp_path / "src/data/mock.ts").write_text(_SEED_MOCK, encoding="utf-8")
    (tmp_path / "src/pages").mkdir(parents=True)
    (tmp_path / "src/pages/AdminAboutEditPage.tsx").write_text(page_source, encoding="utf-8")
    return tmp_path


def test_a_seed_key_a_page_reads_is_added_with_the_shape_it_is_used_as(tmp_path: Path) -> None:
    """`seed.aboutPage.title` on an absent key is `undefined.title` — a crash.

    Request 42 read `seed.aboutPage` five times. `tsc` reported all five as TS2339
    and the page would have rendered the error boundary.
    """
    from app.application.preview_app.safety.seed_keys import ensure_seed_keys_pages_read

    workspace = _seed_workspace(
        tmp_path,
        "import { seed } from '@/data/mock';\n"
        "export default function P() {\n"
        "  return (\n"
        "    <div>\n"
        "      <h1>{seed.aboutPage.biography}</h1>\n"
        "      <p>{seed.aboutPage.artistStatement}</p>\n"
        "    </div>\n"
        "  );\n"
        "}\n",
    )

    added = ensure_seed_keys_pages_read(workspace, "Jeanne Kassab Art")
    mock = (workspace / "src/data/mock.ts").read_text(encoding="utf-8")

    assert added == ["aboutPage"]
    assert "aboutPage:" in mock
    assert "biography:" in mock and "artistStatement:" in mock
    assert "Jeanne Kassab Art" in mock.split("aboutPage:")[1][:300]


def test_a_seed_key_used_as_a_list_becomes_a_list(tmp_path: Path) -> None:
    from app.application.preview_app.safety.seed_keys import ensure_seed_keys_pages_read

    workspace = _seed_workspace(
        tmp_path,
        "import { seed } from '@/data/mock';\n"
        "export default function P() {\n"
        "  return <ul>{(seed.exhibitions ?? []).map((e) => <li key={e.venue}>{e.venue}</li>)}</ul>;\n"
        "}\n",
    )

    added = ensure_seed_keys_pages_read(workspace, "Jeanne Kassab Art")
    mock = (workspace / "src/data/mock.ts").read_text(encoding="utf-8")

    assert added == ["exhibitions"]
    body = mock.split("exhibitions:")[1]
    assert body.lstrip().startswith("["), f"a mapped key must be an array, got {body[:60]!r}"
    assert "venue" in body[:200], "the field the page reads off each row must exist"


def test_keys_that_already_exist_are_left_alone(tmp_path: Path) -> None:
    from app.application.preview_app.safety.seed_keys import ensure_seed_keys_pages_read

    workspace = _seed_workspace(
        tmp_path,
        "import { seed } from '@/data/mock';\n"
        "export default function P() { return <h1>{seed.hero.headline}</h1>; }\n",
    )
    before = (workspace / "src/data/mock.ts").read_text(encoding="utf-8")

    added = ensure_seed_keys_pages_read(workspace, "Jeanne Kassab Art")

    assert added == []
    assert (workspace / "src/data/mock.ts").read_text(encoding="utf-8") == before


def test_the_seed_key_guard_is_idempotent(tmp_path: Path) -> None:
    from app.application.preview_app.safety.seed_keys import ensure_seed_keys_pages_read

    workspace = _seed_workspace(
        tmp_path,
        "import { seed } from '@/data/mock';\n"
        "export default function P() { return <h1>{seed.aboutPage.biography}</h1>; }\n",
    )

    ensure_seed_keys_pages_read(workspace, "Brand")
    once = (workspace / "src/data/mock.ts").read_text(encoding="utf-8")
    second = ensure_seed_keys_pages_read(workspace, "Brand")
    twice = (workspace / "src/data/mock.ts").read_text(encoding="utf-8")

    assert second == []
    assert twice == once


def test_a_surface_root_does_not_mint_a_catch_all_param_route(tmp_path: Path) -> None:
    """Request 41 declared `/owner/:id` and `/owner/:slug`.

    `/owner/artworks` looked detail-ish, so the alias pass hung a param straight
    off the surface namespace — a route that matches every owner page and belongs
    to none of them.
    """
    architect = {
        "routes": [
            {"path": path, "component_file": f"src/pages/owner/{component}.tsx",
             "component": component, "surface": "ops"}
            for path, component in [
                ("/owner/dashboard", "DashboardPage"),
                ("/owner/artworks", "ArtworkManagementPage"),
                ("/owner/settings", "SettingsPage"),
            ]
        ],
        "files_to_generate": [],
        "roles": [],
    }

    routes = _routes_in_app_tsx(architect, tmp_path)

    assert "/owner/:id" not in routes, f"a catch-all under the surface root: {sorted(routes)}"
    assert "/owner/:slug" not in routes
    assert "/owner/dashboard" in routes


def test_page_header_actions_accept_the_button_vocabulary() -> None:
    """Generated ops pages write `variant: "outline"` for a Cancel button.

    The prop admitted only `'primary' | 'secondary'`, so every such page carried a
    TS2322 — while the renderer already treated anything non-secondary as solid.
    """
    header = (
        Path(__file__).resolve().parents[2]
        / "preview-template" / "src" / "ui" / "ops" / "PageHeader.tsx"
    ).read_text(encoding="utf-8")

    for variant in ("outline", "ghost", "destructive"):
        assert f"'{variant}'" in header, f"{variant} must be an accepted action variant"
    assert "variant === 'outline'" in header, "outline must render as the subtle style"


# --------------------------------------------------------------------------- #
# a contact page is a form, not a grid of links
# --------------------------------------------------------------------------- #

def test_a_contact_route_composes_an_inquiry_form() -> None:
    """The visual critic reported the missing contact form on 39 and 41.

    Both times correctly, both times as a warning nobody acted on: `/contact` fell
    through `infer_utility_workspace_type` to `generic`, whose workspace is a grid
    of link cards.
    """
    from app.application.preview_app.utility_compositor import (
        compose_utility_page_tsx,
        infer_utility_workspace_type,
    )

    assert infer_utility_workspace_type("/contact", "Connect with Jeanne", "") == "contact"

    tsx = compose_utility_page_tsx(
        file_path="src/pages/ContactPage.tsx",
        route={"path": "/contact", "title": "Connect with Jeanne", "skeleton_id": "public-utility"},
        content={},
        brand_name="Jeanne Kassab Art",
    )

    assert "InquiryPanel" in tsx, "the page must render the kit's inquiry form"
    assert 'id="inquire"' in tsx, "hero CTAs anchor at #inquire"
    assert "InquiryPanel" in tsx.split("from '@/ui'")[0], "and import it"


def test_other_utility_faces_are_unchanged() -> None:
    from app.application.preview_app.utility_compositor import infer_utility_workspace_type

    assert infer_utility_workspace_type("/cart", "Your cart", "") == "cart"
    assert infer_utility_workspace_type("/checkout", "Checkout", "") == "checkout"
    assert infer_utility_workspace_type("/account", "Your account", "") == "account"
    assert infer_utility_workspace_type("/thank-you", "Thanks", "") == "confirmation"
    assert infer_utility_workspace_type("/legal", "Legal", "") == "generic"


def test_the_item_pool_query_asks_for_the_product_not_its_environment() -> None:
    """Request 41's grid showed an artist at an easel for three of six pieces.

    The vision critic blocked the page for it: "all of the artwork catalog images
    show people painting rather than the finished artworks". Item photos are the
    thing being sold, so their query drops the brand (noise in a stock index) and
    the category hint, whose environment words are what pulled people in.
    """
    from app.application.services.industry_images import item_pool_query

    item_query = item_pool_query(
        "Fine art gallery · original oil paintings · artist portfolio"
    )

    assert "oil paintings" in item_query, "the brief's own nouns must lead"
    assert "product detail close up" in item_query
    assert "Jeanne Kassab Art" not in item_query, "brand names are stock-search noise"
    assert "studio" not in item_query, "the environment hint is what returned people"


def test_the_item_pool_query_is_not_a_slot() -> None:
    """`_slot_queries` stays exactly slot -> query; several callers assume it."""
    from app.application.services.industry_images import (
        _ITEM_SLOTS,
        _SLOTS,
        _slot_queries,
        normalize_image_slot_map,
    )

    queries = _slot_queries("Brand", "Fine art gallery", {"card1": "product detail"})
    assert set(queries) == set(_SLOTS)

    slots = normalize_image_slot_map({"hero": "https://images.pexels.com/photos/1/a.jpeg"})
    assert set(_ITEM_SLOTS) <= set(slots)
