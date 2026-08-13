"""Pins the surface mechanism — the routing key that decides both how a
screen is drawn and which rubric scores it (app/surfaces.py).

The load-bearing property is that the refactor is ADDITIVE. Every screen
shape that existed before session 39 must resolve to the same prompt and
the same judge template it did before, byte for byte, because the judge is
held fixed across sessions and a rubric that quietly moved would
invalidate every score in every evidence document. New surfaces get new
rubrics; old surfaces get exactly what they had.

The second property is that the generator and the judge cannot disagree.
Routing is deterministic from the archetype, so the shape that DREW a
screen and the rubric that SCORES it read one answer. A per-image
classifier would be a second model re-deciding what the generator already
knew, and every disagreement would be a screen judged by the wrong rubric.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app import archetypes, surfaces
from app.ui_spec import UIDemoSpec


# ── the additive rule ────────────────────────────────────────────────────

def test_no_pre_existing_archetype_gained_a_public_screen():
    """Every archetype but the new one answers "what software does this
    business RUN", so none of them may carry a surface that changes which
    rubric scores it. If one ever does, its scores stop being comparable to
    the corpus and this test should be the thing that says so.

    `conversation` is allowed here: the assistant console's anchor genuinely
    is one, and it routes to the same rubric as back_office, so nothing it
    has ever scored moved when it was labelled honestly."""
    internal = {surfaces.BACK_OFFICE, surfaces.CONVERSATION}
    for aid, arch in archetypes.ARCHETYPES.items():
        if aid == archetypes.PUBLIC_SITE_ARCHETYPE:
            continue
        found = {surfaces.resolve(s.get("surface")) for s in arch["screens"]}
        assert found <= internal, f"{aid} declares {found}"
        assert not any(surfaces.is_public(s) for s in found), aid


def test_labelling_the_console_conversation_changed_nothing_it_draws():
    """The conversation surface was dead config until this: declared,
    tested for judge routing, never assigned by any archetype. Assigning it
    makes the data model honest, and must not move a single character of
    the prompt — the console still chooses its shape on concept.kind, which
    is a distinction WITHIN a surface."""
    from app.pipeline import prompt_builder

    payload = {
        "business": {"name": "Halden & Co", "industry": "Professional Services"},
        "product": {"name": "Halden Assistant", "screen_type": "conversations"},
        "navigation": ["Inbox", "Conversations", "Clients"],
        "kpis": [{"label": "Handled", "value": "42"}],
        "concept": {
            "kind": "assistant",
            "turns": [
                {"speaker": "customer", "text": "Can I move my Thursday appointment?"},
                {"speaker": "assistant", "text": "Yes — I have Friday at 10:00 free."},
            ],
        },
    }
    unlabelled = prompt_builder.build_dashboard_image_prompt(UIDemoSpec.model_validate(payload))
    labelled = prompt_builder.build_dashboard_image_prompt(
        UIDemoSpec.model_validate({**payload, "surface": surfaces.CONVERSATION})
    )
    assert unlabelled == labelled
    assert surfaces.judge_template(surfaces.CONVERSATION) == surfaces.judge_template(surfaces.BACK_OFFICE)


def test_the_console_anchor_declares_the_conversation_surface():
    assert archetypes.screen_surfaces(archetypes.ASSISTANT_ARCHETYPE, 3) == [
        surfaces.CONVERSATION, surfaces.BACK_OFFICE, surfaces.BACK_OFFICE,
    ]


def test_the_surfaces_that_predate_this_keep_the_original_judge():
    """The whole reason no before/after is owed for the refactor."""
    assert surfaces.judge_template(surfaces.BACK_OFFICE) == "image_quality_judge.j2"
    assert surfaces.judge_template(surfaces.CONVERSATION) == "image_quality_judge.j2"
    assert surfaces.judge_template(None) == "image_quality_judge.j2"
    assert surfaces.judge_template("") == "image_quality_judge.j2"


def test_an_unknown_surface_falls_back_rather_than_raising():
    """This value can arrive from a golden bundle frozen before the field
    existed. A demo rendering as a dashboard is a far smaller failure than
    a request that dies."""
    assert surfaces.resolve("something-invented-later") == surfaces.BACK_OFFICE
    assert surfaces.get("something-invented-later")["judge_template"] == "image_quality_judge.j2"


def test_only_genuinely_new_surfaces_get_a_new_rubric():
    assert surfaces.judge_template(surfaces.MARKETING) == "image_quality_judge_public.j2"
    assert surfaces.judge_template(surfaces.CATALOG) == "image_quality_judge_public.j2"


def test_both_judge_templates_exist_on_disk():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for record in surfaces.SURFACES.values():
        path = os.path.join(root, "app", "prompts", record["judge_template"])
        assert os.path.exists(path), path


def test_every_surface_record_is_complete():
    """A surface missing a key would fail at judge time, on a funded run,
    after the image had already been paid for."""
    required = {"label", "description", "judge_template", "audience"}
    for sid, record in surfaces.SURFACES.items():
        assert required <= set(record), f"{sid} missing {required - set(record)}"


def test_no_surface_field_is_dead_config():
    """The meta-test, and the one that would have caught the real bug.

    The first draft of this registry carried `prompt_kind`, `expects_chart`
    and `allows_marketing_composition`, and an architecture review found
    all three had ZERO readers anywhere in the codebase: the module looked
    data-driven while every decision it claimed to make sat in an `if`
    statement somewhere else. That is worse than having no config, because
    the next person to add a surface fills the fields in and expects
    behaviour.

    So: every key in every surface record must be read by something outside
    surfaces.py. If you add a field, wire it."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sources = []
    for folder, _dirs, files in os.walk(os.path.join(root, "app")):
        for name in files:
            if not name.endswith((".py", ".j2")):
                continue
            path = os.path.join(folder, name)
            if os.path.basename(path) == "surfaces.py":
                continue
            with open(path, encoding="utf-8") as handle:
                sources.append(handle.read())
    corpus = "\n".join(sources)

    fields = {key for record in surfaces.SURFACES.values() for key in record}
    dead = sorted(f for f in fields if f not in corpus)
    assert not dead, f"surface fields nothing reads: {dead} — wire them or delete them"


def test_every_surface_has_an_explicit_rendering_decision():
    """A surface with no entry would fall through to the dashboard branches
    and render as a dashboard — silently, and only visible on a funded run.
    `None` is a legitimate entry meaning "the concept.kind branches decide";
    absence is not."""
    from app.pipeline.prompt_builder import SURFACE_RENDERERS

    missing = set(surfaces.SURFACES) - set(SURFACE_RENDERERS)
    assert not missing, f"surfaces with no rendering decision: {sorted(missing)}"
    extra = set(SURFACE_RENDERERS) - set(surfaces.SURFACES)
    assert not extra, f"renderers for surfaces that do not exist: {sorted(extra)}"


def test_every_surface_resolves_an_art_pack_or_deliberately_none():
    """Public surfaces inherit the public-site pack so a future
    restaurant-site or shop-site does not have to paste a copy of it."""
    from app.pipeline import art_packs

    for sid in surfaces.PUBLIC_SURFACES:
        assert art_packs.pack_for("some-future-public-archetype", sid) is not None, sid


def test_an_archetype_with_its_own_pack_still_wins():
    """The additive half: nothing that shipped before inherits anything."""
    from app.pipeline import art_packs

    own = art_packs.pack_for("operations-dashboard", surfaces.MARKETING)
    assert own is not None and own["label"] == "Operations"


# ── the drawing path is unchanged for old surfaces ───────────────────────

def _dashboard_spec(**over) -> UIDemoSpec:
    payload = {
        "business": {"name": "SmileBright Dental", "industry": "Dentistry"},
        "product": {"name": "SmileBright Operations", "screen_type": "dashboard"},
        "navigation": ["Dashboard", "Schedule", "Patients"],
        "greeting": "Good morning, Dana",
        "subheading": "Today at a glance",
        "kpis": [{"label": "Appointments", "value": "18"}],
        "primary_panel": {"title": "Today", "rows": [{"Patient": "R. Diaz", "Time": "09:00"}]},
        "chart": {"title": "Visits", "labels": ["Mon", "Tue"], "values": [4, 7]},
    }
    payload.update(over)
    return UIDemoSpec.model_validate(payload)


def test_a_spec_with_no_surface_draws_exactly_what_it_drew_before():
    """The frozen-bundle case: adding the field must not change one
    character of the prompt for a spec that predates it."""
    from app.pipeline import prompt_builder

    before = prompt_builder.build_dashboard_image_prompt(_dashboard_spec())
    after = prompt_builder.build_dashboard_image_prompt(
        _dashboard_spec(surface=surfaces.BACK_OFFICE)
    )
    assert before == after


def test_a_back_office_prompt_still_carries_its_dashboard_furniture():
    from app.pipeline import prompt_builder

    prompt = prompt_builder.build_dashboard_image_prompt(_dashboard_spec())
    assert "Appointments" in prompt
    assert "LANDING PAGE" not in prompt
    assert "CATALOGUE PAGE" not in prompt


# ── the new surfaces draw something genuinely different ──────────────────

def _public_spec(surface: str, **over) -> UIDemoSpec:
    payload = {
        "business": {"name": "Jeanne Art", "industry": "Art - Artists - paintings"},
        "product": {"name": "Jeanne Art", "screen_type": "home"},
        "surface": surface,
        "navigation": ["Home", "Gallery", "About", "Contact"],
        "active_nav": "Home",
        "greeting": "Paintings by Jeanne",
        "subheading": "Original oil on canvas, from the studio",
        "kpis": [{"label": "Works", "value": "78"}, {"label": "Collectors", "value": "124"}],
        "primary_panel": {"rows": [
            {"Title": "Morning Mist", "Price": "$1,800"},
            {"Title": "Coastal Dawn", "Price": "$2,400"},
        ]},
        "hero": {"subject": "an abstract oil painting in gallery light", "caption": "Morning Mist"},
        "concept": {
            "kind": "explorer",
            "primary_action": "View the Gallery",
            "secondary_action": "Commission a Piece",
            "steps": [{"label": "Theme", "options": ["Landscapes", "Portraits"], "selected": "Landscapes"}],
        },
    }
    payload.update(over)
    return UIDemoSpec.model_validate(payload)


def test_a_marketing_screen_is_drawn_as_a_landing_page_not_a_dashboard():
    from app.pipeline import prompt_builder

    prompt = prompt_builder.build_dashboard_image_prompt(_public_spec(surfaces.MARKETING))
    assert "PUBLIC LANDING PAGE" in prompt
    assert "View the Gallery" in prompt          # the one call to action, named
    assert "Paintings by Jeanne" in prompt       # the headline, named
    # None of the back-office furniture may survive the branch.
    assert "Main list panel:" not in prompt
    assert "Recent activity" not in prompt


def test_a_catalog_screen_is_drawn_as_a_grid_of_the_things_on_offer():
    from app.pipeline import prompt_builder

    prompt = prompt_builder.build_dashboard_image_prompt(
        _public_spec(surfaces.CATALOG, product={"name": "Jeanne Art", "screen_type": "gallery"})
    )
    assert "PUBLIC CATALOGUE PAGE" in prompt
    assert "Morning Mist · $1,800" in prompt     # an item caption, named
    assert "Landscapes" in prompt                # the filter chips, named
    assert "Main list panel:" not in prompt


def test_a_public_screen_never_asks_for_a_chart():
    """The rubric that scores these has no chart criterion, and a chart on
    a landing page is the dashboard leaking through."""
    from app.pipeline import prompt_builder

    for surface in (surfaces.MARKETING, surfaces.CATALOG):
        spec = _public_spec(surface, chart={"title": "Views", "labels": ["Jan"], "values": [3]})
        prompt = prompt_builder.build_dashboard_image_prompt(spec)
        assert "Views" not in prompt, surface


# ── the archetype that answers a public brief ────────────────────────────

def test_the_public_site_archetype_shows_the_visitor_and_the_owner():
    """Two screens the visitor sees, one the owner works in. All public
    would be a website mock-up with no software in it; all back-office is
    what the pipeline already got wrong on request 138."""
    ordered = archetypes.screen_surfaces(archetypes.PUBLIC_SITE_ARCHETYPE, 3)
    assert ordered == [surfaces.MARKETING, surfaces.CATALOG, surfaces.BACK_OFFICE]


def test_the_public_site_anchor_is_the_page_a_visitor_lands_on():
    """The anchor is generated first and every other screen is drawn
    against it as a style reference, so it sets the brand look."""
    _, arch = archetypes.get_archetype(archetypes.PUBLIC_SITE_ARCHETYPE)
    assert arch["screens"][0]["screen_type"] == "home"
    assert arch["screens"][0]["surface"] == surfaces.MARKETING


def test_the_archetype_catalogue_offers_the_public_option_to_the_classifier():
    """The ui_spec stage can only pick what the catalogue describes."""
    catalog = archetypes.catalog_for_prompt()
    assert archetypes.PUBLIC_SITE_ARCHETYPE in catalog
    assert "home -> gallery -> manage" in catalog


@pytest.mark.parametrize("count", [2, 3])
def test_surface_routing_matches_the_screens_actually_produced(count):
    """DEMO_SCREEN_COUNT can be 2; the routing table must not hand back
    surfaces for screens that were never drawn."""
    for aid in archetypes.ARCHETYPES:
        assert len(archetypes.screen_surfaces(aid, count)) == count


# ── the prompt must not contradict itself ────────────────────────────────

def test_a_public_prompt_never_asks_for_the_sidebar_it_also_forbids():
    """The first draft of this branch asked for "Navigation items (left
    sidebar...)" and put "no sidebar" two lines below it, and named the
    sidebar again in the branding block. A prompt that contradicts itself
    in one breath is the same defect class as the duplicated navigation and
    the double CTA — the model is not disobeying, it is obeying twice."""
    from app.pipeline import prompt_builder

    for surface in (surfaces.MARKETING, surfaces.CATALOG):
        prompt = prompt_builder.build_dashboard_image_prompt(_public_spec(surface))
        asks = [
            line for line in prompt.splitlines()
            if "sidebar" in line.lower() and "no sidebar" not in line.lower()
        ]
        assert not asks, f"{surface} still asks for a sidebar: {asks}"


def test_a_public_prompt_puts_the_wordmark_in_the_top_bar():
    from app.pipeline import prompt_builder

    prompt = prompt_builder.build_dashboard_image_prompt(_public_spec(surfaces.MARKETING))
    assert "at the far left of the top navigation bar" in prompt
    assert "at the top of the sidebar" not in prompt


def test_a_public_prompt_does_not_open_by_calling_the_page_an_application():
    """The opening sentence sets the whole frame; calling a landing page a
    "production software application" is the strongest single pull back
    toward the dashboard this branch exists to avoid."""
    from app.pipeline import prompt_builder

    prompt = prompt_builder.build_dashboard_image_prompt(_public_spec(surfaces.MARKETING))
    opening = prompt.split("BUSINESS")[0]
    assert "PUBLIC WEBSITE" in opening
    for phrase in ("SaaS application", "software application", "software tool"):
        assert phrase not in opening, phrase


def test_a_back_office_prompt_keeps_its_sidebar_and_its_opening_line():
    """The other half of the additive rule: the branch above must not have
    changed anything for the screens that were already working."""
    from app.pipeline import prompt_builder

    prompt = prompt_builder.build_dashboard_image_prompt(_dashboard_spec())
    assert "left sidebar" in prompt
    assert "at the top of the sidebar" in prompt
    assert "PUBLIC WEBSITE" not in prompt


# ── the scalability claim, made falsifiable ──────────────────────────────

def test_a_whole_new_business_shape_needs_no_new_code():
    """The claim this architecture is making, written as a test.

    Adding a business shape that REUSES existing surfaces must cost one
    dictionary entry and nothing else — no prompt-builder branch, no art
    pack, no judge template, no test. Before session 39's review that was
    false three times over: the renderer was an if/elif on specific surface
    ids, and the art pack was keyed per archetype so every public archetype
    would have pasted a copy of the same visual language.

    A restaurant is the case that will actually turn up: a home page, a
    menu the visitor browses, and a back office the owner works in.
    """
    from app.pipeline import art_packs, prompt_builder

    restaurant = {
        "label": "Restaurant Site + Back Office",
        "when": "restaurants and cafés: a visitor reads the menu before they book",
        "screens": [
            {"screen_type": "home", "surface": surfaces.MARKETING, "layout": "hero", "chart": None},
            {"screen_type": "menu", "surface": surfaces.CATALOG, "layout": "grid", "chart": None},
            {"screen_type": "manage", "surface": surfaces.BACK_OFFICE, "layout": "kpis", "chart": "bar"},
        ],
    }
    patched = {**archetypes.ARCHETYPES, "restaurant-site": restaurant}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(archetypes, "ARCHETYPES", patched)

        ordered = archetypes.screen_surfaces("restaurant-site", 3)
        assert ordered == [surfaces.MARKETING, surfaces.CATALOG, surfaces.BACK_OFFICE]

        for surface_id in ordered:
            # a rubric, without writing one
            assert surfaces.judge_template(surface_id)
            # a rendering decision, without writing one
            assert surface_id in prompt_builder.SURFACE_RENDERERS

        # Public screens inherit their visual language, because every public
        # page shares one. Back-office screens deliberately do NOT: the
        # operations, crm, analytics and pipeline packs are meant to differ
        # (test_packs_differ_between_archetypes), so a new shape supplies one
        # pack for its owner-facing screen and inherits the rest. Two
        # dictionary entries, no code.
        for surface_id in (surfaces.MARKETING, surfaces.CATALOG):
            assert art_packs.pack_for("restaurant-site", surface_id) is not None
        assert art_packs.pack_for("restaurant-site", surfaces.BACK_OFFICE) is None

        # and it actually draws, as a menu rather than as a dashboard
        spec = _public_spec(
            surfaces.CATALOG,
            product={"name": "Trattoria Sole", "screen_type": "menu"},
            style={"archetype": "restaurant-site"},
        )
        prompt = prompt_builder.build_dashboard_image_prompt(spec, archetype_id="restaurant-site")
        assert "PUBLIC CATALOGUE PAGE" in prompt

        # ENABLE_ART_PACKS is False in production — the W2 pack experiment
        # never shipped as the default — so art direction only reaches a
        # prompt when it is switched on. Patched here rather than asserted
        # against the live setting, so this test measures the inheritance
        # and not the flag.
        mp.setattr(prompt_builder.settings, "ENABLE_ART_PACKS", True)
        packed = prompt_builder.build_dashboard_image_prompt(spec, archetype_id="restaurant-site")
        assert "Public Site pack" in packed, "inherited the surface's art pack"
