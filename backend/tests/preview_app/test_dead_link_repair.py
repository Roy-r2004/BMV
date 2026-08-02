"""A preview must not be withheld over a link the pipeline can repair itself.

Dead links were 37 of the 49 blocking gate issues across requests 77-85, and 5
of those 9 gate failures were dead links and nothing else. None of them needed a
model: the route table is on disk in `src/App.tsx`, and every case is either a
link with a real destination one level up or a link with no destination at all.

The cases here are the real hrefs those nine runs produced, not invented ones.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

from app.application.preview_app.safety.dead_links import (  # noqa: E402
    repair_dead_links,
    repair_file_dead_links,
    resolve_dead_href,
)

# Request 81's router, trimmed to the paths its dead links argue with.
SERVED_81 = {
    "/",
    "/services",
    "/book",
    "/patient/dashboard",
    "/patient/library",
    "/patient/messages",
    "/patient/treatment-plan",
    "/patient/ai-assistant",
}
SERVED_82 = {"/", "/book", "/rooms", "/sauna", "/canoe-trips", "/dining"}


@pytest.mark.parametrize(
    "href, served, expected",
    [
        # Parent: the detail page was never built, the listing was. Six of the
        # 31 real dead hrefs resolve this way.
        ("/patient/messages/new", SERVED_81, "/patient/messages"),
        ("/patient/messages/active", SERVED_81, "/patient/messages"),
        ("/patient/library/:_", SERVED_81, "/patient/library"),
        ("/patient/treatment-plan/clear-aligners-123", SERVED_81, "/patient/treatment-plan"),
        # Dash: `/book-canoe-trip` -> `/book-canoe` -> `/book`. Three more.
        ("/book-canoe-trip", SERVED_82, "/book"),
        ("/book-room", SERVED_82, "/book"),
        # No destination. 22 of 31 are these, and `/` must NOT be invented here —
        # "nothing matched" and "send them home" are different answers.
        ("/about", SERVED_81, None),
        ("/patient/notifications", SERVED_81, None),
        ("/my-bookings/CPL-198305", SERVED_82, None),
        ("/lodge-experience", SERVED_82, None),
    ],
)
def test_resolve_only_answers_when_there_is_somewhere_real_to_go(
    href: str, served: set[str], expected: str | None
) -> None:
    assert resolve_dead_href(href, served) == expected


def test_a_link_with_a_real_parent_is_retargeted_not_removed() -> None:
    source = '<Button href={"/patient/messages/new"} className="mt-auto w-fit">Open</Button>'
    out, counts = repair_file_dead_links(source, SERVED_81)

    assert '"/patient/messages"' in out
    assert "/patient/messages/new" not in out
    assert counts == {"retargeted": 1, "unlinked": 0, "dropped": 0, "homed": 0}
    assert "Open" in out and "<Button" in out, "the affordance and its text survive"


def test_a_link_with_nowhere_to_go_loses_its_href_and_keeps_its_text() -> None:
    """`Button` declares `href?: string` and only renders an anchor `if (href)`.

    Dropping the attribute leaves the same button in the same place, no longer
    claiming to lead somewhere. Deleting the element would change the layout.
    """
    source = '<Button href={"/patient/notifications"} className="mt-auto w-fit">Alerts</Button>'
    out, counts = repair_file_dead_links(source, SERVED_81)

    assert "/patient/notifications" not in out
    assert "href" not in out
    assert counts == {"retargeted": 0, "unlinked": 1, "dropped": 0, "homed": 0}
    assert 'className="mt-auto w-fit"' in out and ">Alerts<" in out


def test_an_href_on_an_unknown_component_is_grounded_not_stripped() -> None:
    """`href` may be *required* on `<FancyCard>`, so removing it can turn a dead
    link into a red build — the one outcome worse than the dead link. Replacing
    the value keeps the prop's type intact, so grounding is safe everywhere and
    stripping is safe only on the tags we own."""
    source = '<FancyCard href="/about" title="About" />'
    out, counts = repair_file_dead_links(source, SERVED_81)

    assert out == '<FancyCard href="/" title="About" />'
    assert counts == {"retargeted": 0, "unlinked": 0, "dropped": 0, "homed": 1}


def test_a_footer_entry_whose_page_was_never_built_is_removed_entirely() -> None:
    """Request 88 shipped a footer with Activities, Contact and Privacy Policy
    all pointing at `/`. Three differently-labelled links landing on the home
    page reads as navigable and is not — worse for a demo than the dead link,
    and it is what grounding every object-literal href produced.

    Deleting one element cannot change the array's type.
    """
    source = (
        'const links = [\n'
        '  { label: "Services", href: "/services" },\n'
        '  { label: "Contact", href: "/contact" },\n'
        '  { label: "Book", href: "/book" },\n'
        '];'
    )
    out, counts = repair_file_dead_links(source, SERVED_81)

    assert "Contact" not in out
    assert '"/services"' in out and '"/book"' in out
    assert counts == {"retargeted": 0, "unlinked": 0, "dropped": 1, "homed": 0}
    assert out.count("{") == 2, out


def test_the_last_entry_is_grounded_rather_than_leaving_an_empty_list() -> None:
    """An empty footer is a different defect, not a fix for this one."""
    source = 'const nextSteps = [{"title": "About us", "href": "/about"}];'
    out, counts = repair_file_dead_links(source, SERVED_81)

    assert '"href": "/"' in out
    assert '"About us"' in out
    assert counts == {"retargeted": 0, "unlinked": 0, "dropped": 0, "homed": 1}


def test_the_final_entry_is_grounded_so_two_deletions_cannot_collide() -> None:
    """The last entry's only comma is the one in front of it, which the previous
    entry's deletion already claimed. Two edits over one character, and the
    collision resolver drops one silently — request 82's `nextSteps` had four
    dead entries and shipped with the fourth still pointing at
    `/plan-your-stay`, repaired by nothing.
    """
    source = (
        'const links = [\n'
        '  { label: "About", href: "/about" },\n'
        '  { label: "Contact", href: "/contact" }\n'
        '];'
    )
    out, counts = repair_file_dead_links(source, SERVED_81)

    assert counts == {"retargeted": 0, "unlinked": 0, "dropped": 1, "homed": 1}
    assert "About" not in out, "a non-final dead entry is deleted"
    assert '"Contact"' in out and 'href: "/"' in out, "the final one is grounded"
    assert "/contact" not in out
    assert ",\n]" not in out.replace(" ", ""), f"dangling comma: {out!r}"


def test_every_entry_in_an_all_dead_list_but_one_is_removed() -> None:
    source = (
        'const links = [\n'
        '  { label: "About", href: "/about" },\n'
        '  { label: "Gallery", href: "/gallery" },\n'
        '  { label: "Contact", href: "/contact" }\n'
        '];'
    )
    out, counts = repair_file_dead_links(source, SERVED_81)

    assert counts["dropped"] == 2 and counts["homed"] == 1
    assert out.count("{") == 1, f"exactly one entry survives: {out!r}"


def test_a_live_link_is_never_touched() -> None:
    source = (
        '<Button href="/services">Services</Button>\n'
        '<a href="/patient/library">Library</a>\n'
        '<a href="https://example.com">Out</a>\n'
        '<a href="#book">Anchor</a>'
    )
    out, counts = repair_file_dead_links(source, SERVED_81)

    assert out == source
    assert counts == {"retargeted": 0, "unlinked": 0, "dropped": 0, "homed": 0}


def test_a_param_route_still_serves_its_template_link() -> None:
    """Request 44 was withheld on three links that all worked. `/gallery/${id}`
    resolves to `/gallery/:_`, and a declared `/gallery/:id` serves it."""
    source = "<a href={`/gallery/${item.id}`}>View</a>"
    out, counts = repair_file_dead_links(source, {"/", "/gallery", "/gallery/:id"})

    assert out == source
    assert counts == {"retargeted": 0, "unlinked": 0, "dropped": 0, "homed": 0}


def test_the_owner_ellipsis_in_template_prose_is_not_a_route() -> None:
    """`/owner/...` appears in all nine runs and is documentation, not a link."""
    source = "// role landing paths look like href: '/owner/...'"
    out, _ = repair_file_dead_links(source, SERVED_81)

    assert out == source


def test_no_router_on_disk_means_no_repairs(tmp_path: Path) -> None:
    """Fail open. With no route table there is nothing to judge against, and
    treating an empty set as truth would neutralise every link in the app."""
    (tmp_path / "src").mkdir()
    page = tmp_path / "src" / "HomePage.tsx"
    page.write_text('<Button href="/about">About</Button>', encoding="utf-8")

    assert repair_dead_links(tmp_path, {"routes": []}) == []
    assert page.read_text(encoding="utf-8") == '<Button href="/about">About</Button>'


def test_the_guard_walks_the_workspace_and_reports_what_it_changed(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src"
    (src / "pages").mkdir(parents=True)
    (src / "App.tsx").write_text(
        '<Routes><Route path="/" element={<Home />} />'
        '<Route path="/patient/messages" element={<M />} /></Routes>',
        encoding="utf-8",
    )
    page = src / "pages" / "DashboardPage.tsx"
    page.write_text(
        '<Button href={"/patient/messages/new"}>New</Button>\n'
        '<Button href={"/patient/notifications"}>Alerts</Button>',
        encoding="utf-8",
    )

    actions = repair_dead_links(tmp_path, {"routes": []})
    out = page.read_text(encoding="utf-8")

    assert '"/patient/messages"' in out
    assert "/patient/notifications" not in out
    assert len(actions) == 1
    assert "retargeted=1" in actions[0] and "unlinked=1" in actions[0]


def test_the_guard_is_wired_into_the_pre_build_pass() -> None:
    """A guard nobody calls is not a guard. `apply_workspace_guards` runs before
    every build attempt, which is the only place this can run without paying for
    a second `vite build`."""
    source = (
        BACKEND_DIR
        / "app" / "application" / "preview_app" / "safety" / "orchestrator.py"
    ).read_text(encoding="utf-8")

    assert "repair_dead_links(workspace, architect)" in source


def test_the_nav_is_judged_against_the_router_not_the_planner(tmp_path: Path) -> None:
    """`normalize_mock_navigation` dropped nav entries whose path was not in the
    *architect's* route list. The architect's list and the shipped router
    diverge — `served_route_paths` exists because of exactly that — so an entry
    the planner declared and assembly never routed survived into the navbar.
    Requests 78 and 81 shipped `/contact` and `/gallery` nav items that no
    `<Route>` served.

    The architect here declares `/contact`; `App.tsx` does not serve it.
    """
    from app.application.preview_app.safety.mock_data import normalize_mock_navigation

    src = tmp_path / "src" / "data"
    src.mkdir(parents=True)
    (tmp_path / "src" / "App.tsx").write_text(
        '<Routes>'
        '<Route path="/" element={<Home />} />'
        '<Route path="/services" element={<Services />} />'
        "</Routes>",
        encoding="utf-8",
    )
    mock = src / "mock.ts"
    mock.write_text(
        'export const navigation = {"public": ['
        '{"label": "Services", "href": "/services"}, '
        '{"label": "Contact", "href": "/contact"}'
        "]};",
        encoding="utf-8",
    )
    architect = {
        "routes": [
            {"path": "/", "component_file": "src/pages/HomePage.tsx"},
            {"path": "/services", "component_file": "src/pages/ServicesPage.tsx"},
            {"path": "/contact", "component_file": "src/pages/ContactPage.tsx"},
        ]
    }

    changed = normalize_mock_navigation(tmp_path, architect, "Acme")
    out = mock.read_text(encoding="utf-8")

    assert changed, "the dead nav entry should have been removed"
    assert "/contact" not in out, "the router never served /contact"
    assert "/services" in out, "a live entry must survive"


def test_the_template_hero_default_cta_points_at_a_route_that_always_exists() -> None:
    """`DEFAULT_PRIMARY_CTA` was `/gallery`, so every app the architect built
    without a gallery shipped a dead hero CTA — 78, 81 and 84."""
    from app.core.config import settings

    hero = (
        Path(settings.PREVIEW_TEMPLATE_DIR) / "src" / "ui" / "public" / "MarketingHero.tsx"
    ).read_text(encoding="utf-8")

    default_line = next(
        line for line in hero.splitlines() if "DEFAULT_PRIMARY_CTA" in line and "=" in line
    )
    assert "href: '/'" in default_line, default_line
