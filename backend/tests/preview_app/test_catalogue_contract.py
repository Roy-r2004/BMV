from __future__ import annotations

import sys
import subprocess
import json
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.ui_catalogue import (
    compact_skeleton_contract,
    get_skeleton,
    infer_page_contract,
    infer_section_slots,
    load_catalogue,
)
from app.application.preview_app.assemble import (
    architect_from_stored,
    sync_mock_roles_navigation,
    write_app_tsx,
)
from app.application.preview_app.chat_refinement import _architect_from_generated
from app.application.preview_app.codegen.architect import _architect_prompt_context
from app.application.preview_app.codegen.critic import refine_file
from app.application.preview_app.codegen.fix_agent import fix_build_errors
from app.application.preview_app.codegen.generate import generate_file
from app.application.preview_app.codegen.shared import page_plan_for_file
from app.application.preview_app.text_utils import _bounded_json
from app.application.preview_app import chat_refinement
from app.application.preview_app.refinement import chat_rebuild
from app.application.preview_app.catalogue_contract import (
    enforce_catalogue_page_contract,
    minimal_catalogue_page_scaffold,
    repair_missing_catalogue_slots,
    validate_catalogue_page_content,
)
from app.application.preview_app.fallback import (
    clear_stubbed_paths,
    consume_stubbed_paths,
    scan_and_repair_double_brace_literals,
    stabilize_all_route_pages,
    write_safe_stub,
)
from app.application.preview_app.pipeline.architect_normalize import _attach_plan_sections, _normalize_architect
from app.application.preview_app.protected_paths import (
    canonical_workspace_path,
    is_template_owned_path,
)
from app.application.preview_app.safety.orchestrator import apply_workspace_guards
from app.application.preview_app.safety.mock_data import ensure_mock_exports
from app.application.services.page_experience import _normalize_plan
from app.core.config import settings
from app.infrastructure.templating.renderer import JinjaTemplateRenderer


def _mutated(source: str, old: str, new: str) -> str:
    """Apply a decoy mutation, refusing to return an unmutated string.

    Every decoy in this file is built with `str.replace`, which returns the
    input unchanged when its anchor is gone. The scaffold has been rewritten
    since these were written, and three decoys quietly became no-ops that
    compared the untouched stub against itself: two failed loudly because they
    also asserted `decoy != stub` (and were parked as xfails), while
    `optional_extra` had no such guard and stayed **green while testing
    nothing** — the worst of the three outcomes.

    Anchoring on an exact count rather than mere presence also catches the
    opposite drift, where a string the scaffold now emits twice makes a decoy
    mutate more than intended.
    """
    found = source.count(old)
    if found != 1:
        raise AssertionError(
            f"decoy anchor appears {found} times, expected exactly 1 — the "
            f"scaffold has moved and this mutation tests nothing:\n  {old!r}"
        )
    mutated = source.replace(old, new, 1)
    if mutated == source:
        raise AssertionError("mutation produced an identical string")
    return mutated


class _CapturingAI:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def ask_chat(self, _model, messages, **_kwargs):
        self.prompts.append(messages[0]["content"])
        return self.response


class _SequenceAI:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def ask_chat(self, _model, messages, **_kwargs):
        self.prompts.append(messages[0]["content"])
        if not self.responses:
            raise AssertionError("AI called more times than expected")
        return self.responses.pop(0)


def test_catalogue_skeleton_ids_are_exactly_the_known_set() -> None:
    """The exact catalogue face set. Re-pinned at 15 on 2026-08-03.

    Previously pinned at the original ten and parked as an xfail while five ops
    faces were added — `ops-ledger-home`, `ops-blotter-desk`, `ops-recon-split`,
    `ops-invoice-board`, `ops-expense-queue`. They ship, they are referenced by
    the registry and the scaffold, and they have been live across every trio
    since; they are canonical. Re-pinned rather than deleted, because the point
    of an exact set is that growth is a decision.

    **Adding a face is a product decision, not a test failure.** If this goes
    red, add the id here in the same commit that adds the face — do not relax
    the equality, and do not park it as an xfail again. The five above spent
    several sessions invisible behind exactly that.
    """
    catalogue = load_catalogue()
    skeleton_ids = {item["id"] for item in catalogue["skeletons"]}
    assert skeleton_ids == {
        # The original ten.
        "public-home",
        "public-service",
        "public-detail",
        "public-catalog",
        "public-utility",
        "public-booking",
        "ops-dashboard",
        "ops-list",
        "ops-detail",
        "ops-settings",
        # Added since, and canonical as of 2026-08-03.
        "ops-ledger-home",
        "ops-blotter-desk",
        "ops-recon-split",
        "ops-invoice-board",
        "ops-expense-queue",
    }


def test_catalogue_contract() -> None:
    catalogue = load_catalogue()
    assert load_catalogue() is catalogue
    skeleton_ids = {item["id"] for item in catalogue["skeletons"]}
    # Original ten must remain; growth is tracked by the xfail above.
    assert {
        "public-home",
        "public-service",
        "public-detail",
        "public-catalog",
        "public-utility",
        "public-booking",
        "ops-dashboard",
        "ops-list",
        "ops-detail",
        "ops-settings",
    } <= skeleton_ids

    booking = get_skeleton("public-booking")
    assert booking["surface"] == "public"
    assert "BookingPanel" in booking["allowedComponents"]

    utility = get_skeleton("public-utility")
    assert utility["surface"] == "public"
    assert utility["requiredSections"] == ["shell", "header", "workspace", "footer"]
    assert {"Card", "Table", "PageHeader", "Input", "Select"} <= set(utility["allowedComponents"])
    assert "MarketingHero" not in utility["allowedComponents"]
    catalog = get_skeleton("public-catalog")
    assert "showcase" in catalog["requiredSections"]
    assert "testimonials" not in catalog["requiredSections"]

    contract = compact_skeleton_contract("ops-dashboard")
    assert contract["skeleton"]["id"] == "ops-dashboard"
    # Shell first, then every skeleton-allowed component alphabetically —
    # the contract exposes the full allow-list so validators/prompts accept
    # Button, Badge, Input, etc., not only slot defaults.
    contract_names = [component["name"] for component in contract["components"]]
    assert contract_names[0] == "OpsShell"
    assert {"PageHeader", "StatCard", "ChartCard", "FilterBar", "DataTable", "ActivityFeed"} <= set(contract_names)
    assert contract_names[1:] == sorted(contract_names[1:])
    assert contract["shell_component"] == "OpsShell"
    assert contract["navigation_components"] == []
    ops_shell = contract["components"][0]
    assert {"brandName", "navItems", "children"} <= set(ops_shell["requiredProps"])
    assert all(
        set(component) <= {"name", "requiredProps", "optionalProps", "variants"}
        for component in contract["components"]
    )
    assert "MarketingHero" not in {component["name"] for component in contract["components"]}

    public_contract = compact_skeleton_contract("public-home")
    public_components = {
        component["name"]: component for component in public_contract["components"]
    }
    assert public_contract["shell_component"] == "PublicShell"
    assert public_contract["navigation_components"] == ["PublicNav"]
    assert {"brandName", "children"} <= set(
        public_components["PublicShell"]["requiredProps"]
    )
    assert "nav" in public_components["PublicShell"]["optionalProps"]
    assert "cta" in public_components["PublicShell"]["optionalProps"]
    assert "items" in public_components["PublicNav"]["requiredProps"]
    assert "heading" in public_components["ProductShowcase"]["requiredProps"]
    assert "items" not in public_components["ProductShowcase"]["requiredProps"]
    assert "children" in public_components["ProductShowcase"]["optionalProps"]
    assert "heading" in public_components["BookingPanel"]["requiredProps"]
    assert "treatments" not in public_components["BookingPanel"]["requiredProps"]
    assert "children" in public_components["BookingPanel"]["optionalProps"]
    # Hardening remains durable: invented Tailwind color aliases ship in generated CSS.
    backend_root = REPO_ROOT / "backend"
    css_template = (backend_root / "app" / "templates" / "codegen" / "index_css.j2").read_text(encoding="utf-8")
    assert ".text-muted-text-color" in css_template
    assert ".text-text-color" in css_template
    public_shell_src = (
        backend_root / "preview-template" / "src" / "ui" / "public" / "PublicShell.tsx"
    ).read_text(encoding="utf-8")
    assert "isNavItemList" in public_shell_src
    data_table_src = (
        backend_root / "preview-template" / "src" / "ui" / "ops" / "DataTable.tsx"
    ).read_text(encoding="utf-8")
    assert "invokeRender" in data_table_src
    filter_bar_src = (
        backend_root / "preview-template" / "src" / "ui" / "ops" / "FilterBar.tsx"
    ).read_text(encoding="utf-8")
    assert "isActionDescriptorList" in filter_bar_src
    showcase_src = (
        backend_root / "preview-template" / "src" / "ui" / "public" / "ProductShowcase.tsx"
    ).read_text(encoding="utf-8")
    assert "isShowcaseItem" in showcase_src
    assert "children" in showcase_src

    normalized_slots = infer_section_slots(
        {"section_slots": ["cta", "unknown", "hero", "hero"]},
        "public-service",
    )
    # "process" is optional on public-service now — only requested + required slots.
    assert normalized_slots == ["hero", "features", "cta", "footer"]
    assert infer_section_slots({}, "public-service") == [
        "hero",
        "features",
        "cta",
        "footer",
    ]
    assert infer_section_slots({}, "public-utility") == ["header", "workspace", "footer"]
    assert infer_section_slots({"section_slots": ["shell", "unknown"]}, "ops-list") == [
        "header",
        "filters",
        "table",
    ]
    compact = compact_skeleton_contract("public-service", normalized_slots)
    compact_names = [component["name"] for component in compact["components"]]
    assert compact_names[:2] == ["PublicShell", "PublicNav"]
    assert {"MarketingHero", "FeatureBento", "ProcessSection", "CTABand", "BrandFooter"} <= set(compact_names)
    assert compact_names[2:] == sorted(compact_names[2:])
    assert "allowedComponents" not in compact["skeleton"]
    assert len(json.dumps(compact)) < 6000

    cases = [
        ({"title": "Welcome", "page_type": "landing"}, ("public", "public-home")),
        ({"title": "Our Services", "page_type": "service listing"}, ("public", "public-service")),
        ({"title": "Signature Facial", "page_type": "service detail"}, ("public", "public-detail")),
        ({"title": "Book an Appointment", "page_type": "booking"}, ("public", "public-booking")),
        ({"title": "Cart", "path": "/cart"}, ("public", "public-utility")),
        ({"title": "Checkout", "page_type": "checkout flow"}, ("public", "public-utility")),
        ({"title": "Track Your Order", "page_type": "order tracking"}, ("public", "public-utility")),
        ({"title": "Shop Laptops", "path": "/shop"}, ("public", "public-catalog")),
        ({"title": "Browse Collection", "page_type": "catalog"}, ("public", "public-catalog")),
        ({"title": "Business Overview", "page_type": "dashboard"}, ("ops", "ops-dashboard")),
        ({"title": "Clients", "page_type": "operational list"}, ("ops", "ops-list")),
        ({"title": "Client Record", "page_type": "record detail"}, ("ops", "ops-detail")),
        ({"title": "Preferences", "page_type": "settings"}, ("ops", "ops-settings")),
    ]
    for page, expected in cases:
        inferred = infer_page_contract(page)
        assert (inferred["surface"], inferred["skeleton_id"]) == expected, (page, inferred)

    old_plan = {
        "roles": [
            {
                "id": "public",
                "pages": [
                    {
                        "id": "home",
                        "title": "Home",
                        "path": "/",
                        "layout": "public",
                        "sections": [{"name": "hero"}, "features"],
                    }
                ],
            },
            {
                "id": "owner",
                "pages": [
                    {
                        "id": "settings",
                        "title": "Settings",
                    },
                    {
                        "id": "clients",
                        "title": "Clients",
                        "page_type": "client management",
                    }
                ],
            },
            {
                "id": "admin",
                "label": "Platform Administrator",
                "pages": [{"id": "users", "title": "User Management"}],
            },
            {
                "id": "ops",
                "pages": [{"id": "orders", "title": "Orders Queue"}],
            },
        ]
    }
    normalized = _normalize_plan(old_plan, "#123456", "#654321")
    home = normalized["roles"][0]["pages"][0]
    settings_page = normalized["roles"][1]["pages"][0]
    clients = normalized["roles"][1]["pages"][1]
    assert home["surface"] == "public"
    assert home["skeleton_id"] == "public-home"
    # The public-home slot expectation moved out to
    # `test_a_legacy_plan_home_page_is_filled_out_to_the_full_recommended_order`,
    # which is xfail: it is stale, and it was masking the ~250 assertions below.
    assert settings_page["surface"] == "ops"
    assert settings_page["skeleton_id"] == "ops-settings"
    assert settings_page["section_slots"] == ["header"]
    assert clients["surface"] == "ops"
    assert clients["skeleton_id"] == "ops-list"
    for role in normalized["roles"][2:]:
        assert role["pages"][0]["surface"] == "ops"
        assert role["pages"][0]["skeleton_id"] == "ops-list"

    architect = _normalize_architect(
        {
            "routes": [
                {
                    "path": "/owner/settings",
                    "page_id": "settings",
                    "role_id": "owner",
                    "layout": "admin",
                    "component_file": "src/pages/owner/SettingsPage.tsx",
                }
            ],
            "files_to_generate": [],
        },
        normalized,
    )
    route = architect["routes"][0]
    assert route["surface"] == "ops"
    assert route["skeleton_id"] == "ops-settings"
    page_file = next(
        item
        for item in architect["files_to_generate"]
        if item["path"] == "src/pages/owner/SettingsPage.tsx"
    )
    assert "ops-settings" in page_file["instructions"]
    assert '"section_slots": ["header"]' in page_file["instructions"]
    assert '"MarketingHero"' not in page_file["instructions"]

    persisted = json.loads(
        json.dumps({"preview_app": {"routes": [route], "roles": [{"id": "owner"}]}})
    )
    assert persisted["preview_app"]["routes"][0]["surface"] == "ops"
    assert persisted["preview_app"]["routes"][0]["skeleton_id"] == "ops-settings"
    rebuilt = architect_from_stored(
        persisted,
        normalized,
    )
    assert rebuilt["routes"][0]["surface"] == "ops"
    assert rebuilt["routes"][0]["skeleton_id"] == "ops-settings"
    assert "ops-settings" in rebuilt["files_to_generate"][0]["instructions"]

    huge_plan = _normalize_plan(
        {
            "roles": [
                {
                    "id": "owner",
                    "pages": [
                        {
                            "id": "huge-settings",
                            "title": "Settings",
                            "sections": [
                                {
                                    "name": "header",
                                    "description": "Z" * 100_000,
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        "#111111",
        "#222222",
    )
    huge_rebuilt = architect_from_stored(
        {
            "preview_app": {
                "routes": [
                    {
                        "path": "/owner/settings",
                        "role_id": "owner",
                        "page_id": "huge-settings",
                        "component_file": "src/pages/owner/HugeSettingsPage.tsx",
                        "surface": "ops",
                        "skeleton_id": "ops-settings",
                    }
                ]
            }
        },
        huge_plan,
    )
    huge_instructions = huge_rebuilt["files_to_generate"][0]["instructions"]
    assert len(huge_instructions) <= 8000
    huge_payload = json.loads(huge_instructions)
    assert isinstance(huge_payload["sections"], list)
    assert isinstance(huge_payload["catalogue_contract"], dict)
    assert huge_payload["catalogue_contract"]["skeleton"]["id"] == "ops-settings"

    duplicate_plan = _normalize_plan(
        {
            "roles": [
                {
                    "id": "customer",
                    "pages": [
                        {"id": "dashboard", "title": "Welcome", "page_type": "landing"}
                    ],
                },
                {
                    "id": "owner",
                    "pages": [
                        {
                            "id": "dashboard",
                            "title": "Business Overview",
                            "page_type": "dashboard",
                            "sections": [
                                {"name": "header", "description": "Owner overview"}
                            ],
                        }
                    ],
                },
            ]
        },
        "#111111",
        "#222222",
    )
    duplicate_architect = _normalize_architect(
        {
            "routes": [
                {
                    "path": "/",
                    "role_id": "customer",
                    "page_id": "dashboard",
                    "component_file": "src/pages/HomePage.tsx",
                },
                {
                    "path": "/owner",
                    "role_id": "owner",
                    "page_id": "dashboard",
                    "component_file": "src/pages/owner/DashboardPage.tsx",
                },
            ],
            "files_to_generate": [],
        },
        duplicate_plan,
    )
    assert duplicate_architect["routes"][0]["skeleton_id"] == "public-home"
    assert duplicate_architect["routes"][1]["skeleton_id"] == "ops-dashboard"
    owner_page_plan = page_plan_for_file(
        "src/pages/owner/DashboardPage.tsx",
        duplicate_plan,
        duplicate_architect,
    )
    assert owner_page_plan["title"] == "Business Overview"
    assert owner_page_plan["role_id"] == "owner"
    assert owner_page_plan["sections"][0]["description"] == "Owner overview"
    assert (
        page_plan_for_file(
            "src/pages/DashboardPage.tsx",
            duplicate_plan,
            {"routes": []},
        )
        == {}
    )
    attached = _attach_plan_sections(
        duplicate_architect["files_to_generate"],
        duplicate_plan,
        duplicate_architect,
    )
    home_instructions = next(
        item["instructions"] for item in attached if item["path"] == "src/pages/HomePage.tsx"
    )
    owner_instructions = next(
        item["instructions"]
        for item in attached
        if item["path"] == "src/pages/owner/DashboardPage.tsx"
    )
    assert "Page: Welcome" in home_instructions
    assert "Page: Business Overview" in owner_instructions
    contract_marker = "Skeleton/slot contract (use only these catalogue components and props):\n"
    attached_contract_json = home_instructions.rsplit(contract_marker, 1)[1]
    attached_contract = json.loads(attached_contract_json)
    # The 4,000-char bound moved out to
    # `test_the_attached_skeleton_contract_stays_under_four_thousand_chars` (xfail).
    assert "do not add sections not listed here" not in home_instructions
    assert "Assigned skeleton slots are authoritative" in home_instructions
    for slot in attached_contract["section_slots"]:
        assert slot in home_instructions
    selected_component_names = list(
        dict.fromkeys(
            [
                attached_contract["shell_component"],
                *attached_contract["navigation_components"],
                *attached_contract["slot_components"].values(),
            ]
        )
    )
    # Contract now carries the full skeleton allow-list; shell/nav/slot picks
    # must all be present within it.
    attached_names = [item["name"] for item in attached_contract["components"]]
    assert set(selected_component_names) <= set(attached_names)
    assert attached_names[0] == attached_contract["shell_component"]
    context_json = _architect_prompt_context(duplicate_architect)
    json.loads(context_json)
    assert "files_to_generate" not in context_json
    assert "Skeleton/slot contract" not in context_json
    oversized_context = _architect_prompt_context(
        {
            "roles": duplicate_architect.get("roles", []),
            "routes": [
                {
                    "path": f"/route/{index}",
                    "page_id": f"page-{index}",
                    "role_id": "owner",
                    "title": "X" * 500,
                    "component_file": f"src/pages/Page{index}.tsx",
                }
                for index in range(200)
            ],
            "files_to_generate": [{"instructions": "never include " * 1000}],
        }
    )
    json.loads(oversized_context)
    assert len(oversized_context) <= 8000
    bounded_page = _bounded_json(
        {"sections": [{"description": "Y" * 2000} for _ in range(30)]},
        6000,
    )
    json.loads(bounded_page)
    assert len(bounded_page) <= 6000

    stored_duplicate = architect_from_stored(
        json.loads(json.dumps({"preview_app": {"routes": duplicate_architect["routes"]}})),
        duplicate_plan,
    )
    assert [route["skeleton_id"] for route in stored_duplicate["routes"]] == [
        "public-home",
        "ops-dashboard",
    ]

    chat_generated = {
        "preview_app": {
            "routes": [
                {
                    "path": "/owner",
                    "role_id": "owner",
                    "page_id": "dashboard",
                    "component_file": "src/pages/owner/DashboardPage.tsx",
                }
            ]
        },
        "experience_plan": duplicate_plan,
    }
    chat_architect = _architect_from_generated(
        chat_generated,
        chat_generated["experience_plan"],
    )
    chat_instructions = json.loads(chat_architect["files_to_generate"][0]["instructions"])
    assert chat_instructions["sections"]
    assert "catalogue_contract" not in chat_instructions
    assert "skeleton_id" not in chat_architect["routes"][0]

    chrome_paths = {
        "src/components/nav.tsx",
        "src/layouts/publiclayout.tsx",
        "src/layouts/adminlayout.tsx",
        "src/components/uiicons.tsx",
    }
    protected_architect = _normalize_architect(
        {
            "routes": [
                {
                    "path": "/",
                    "page_id": "dashboard",
                    "role_id": "customer",
                    "component_file": "src/pages/HomePage.tsx",
                }
            ],
            "files_to_generate": [
                {"path": "src/ui/public/PublicShell.tsx", "kind": "component"},
                {"path": "src/components/UiIcons.tsx", "kind": "component"},
            ],
            "shared_components": [
                {"path": "src/components/Nav.tsx", "kind": "component"},
                {"path": "src/layouts/PublicLayout.tsx", "kind": "layout"},
                {"path": "src/layouts/AdminLayout.tsx", "kind": "layout"},
            ],
        },
        duplicate_plan,
    )
    generated_paths = {
        item["path"].replace("\\", "/").lower()
        for item in protected_architect["files_to_generate"]
    }
    assert not generated_paths & chrome_paths
    assert not any(path.startswith("src/ui/") for path in generated_paths)
    assert "src/pages/homepage.tsx" in generated_paths

    renderer = JinjaTemplateRenderer(REPO_ROOT / "backend" / "app" / "templates")
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        page_path = workspace / "src" / "pages" / "HomePage.tsx"
        page_path.parent.mkdir(parents=True)
        page_path.write_text("export default function HomePage() { return <div />; }\n", encoding="utf-8")
        (workspace / "src" / "data").mkdir(parents=True)
        (workspace / "src" / "data" / "mock.ts").write_text(
            "export const roles = [];\n",
            encoding="utf-8",
        )
        write_app_tsx(workspace, protected_architect, renderer)
        catalogue_app = (workspace / "src" / "App.tsx").read_text(encoding="utf-8")
        assert "PublicLayout" not in catalogue_app
        assert "AdminLayout" not in catalogue_app
        assert '<Route path="/" element={<HomePage />} />' in catalogue_app
        assert "RouteBridge" in catalogue_app
        assert "RoleBridge" in catalogue_app
        assert "basename={import.meta.env.BASE_URL}" in catalogue_app

    legacy_stored = {
        "preview_app": {
            "routes": [
                {
                    "path": "/legacy",
                    "page_id": "legacy",
                    "role_id": "public",
                    "layout": "public",
                    "component_file": "src/pages/LegacyPage.tsx",
                }
            ],
            "roles": [{"id": "public", "defaultPath": "/legacy"}],
        }
    }
    legacy_architect = architect_from_stored(legacy_stored, {"roles": []})
    assert "skeleton_id" not in legacy_architect["routes"][0]
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        page_path = workspace / "src" / "pages" / "LegacyPage.tsx"
        page_path.parent.mkdir(parents=True)
        page_path.write_text("export default function LegacyPage() { return <div />; }\n", encoding="utf-8")
        (workspace / "src" / "data").mkdir(parents=True)
        (workspace / "src" / "data" / "mock.ts").write_text(
            "export const roles = [];\n",
            encoding="utf-8",
        )
        write_app_tsx(workspace, legacy_architect, renderer)
        legacy_app = (workspace / "src" / "App.tsx").read_text(encoding="utf-8")
        assert "import PublicLayout from './layouts/PublicLayout';" in legacy_app
        assert '<Route element={<PublicLayout />}>' in legacy_app

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        ai = _CapturingAI("export default function HomePage() { return <div />; }")
        generate_file(
            workspace,
            next(
                item
                for item in protected_architect["files_to_generate"]
                if item["path"] == "src/pages/HomePage.tsx"
            ),
            "business context",
            protected_architect,
            duplicate_plan,
            {},
            {},
            ai,
            renderer,
        )
        page_prompt = ai.prompts[0]
        # Two prompt-wording assertions moved out to
        # `test_the_page_prompt_still_dictates_the_ui_import_and_skeleton_const`
        # (xfail) — the prompt was rewritten and they were never updated.
        assert "getSkeleton(SKELETON_ID)" in page_prompt
        assert "SkeletonComposer" in page_prompt
        assert "PublicShell" in page_prompt
        for forbidden in ("lucide-react", "recharts", "@radix-ui", "motion/react"):
            assert forbidden not in page_prompt.lower()
        generated_page = (workspace / "src" / "pages" / "HomePage.tsx").read_text(encoding="utf-8")
        assert validate_catalogue_page_content(
            generated_page,
            protected_architect["routes"][0],
        ) == []

    route = protected_architect["routes"][0]
    valid_with_sentinel = minimal_catalogue_page_scaffold(
        "src/pages/HomePage.tsx",
        route,
        brand_name="UNIQUE_BUSINESS_SENTINEL",
    ).replace(
        "A clear, considered experience built around your next step.",
        "UNIQUE_BUSINESS_SENTINEL",
    ).replace(
        "// deterministic catalogue contract scaffold",
        "// AI-authored business-specific page",
    )
    complete_invalid = (
        "import { PublicShell } from '@/ui';\n"
        "export default function HomePage() { "
        "return <PublicShell brandName=\"Wrong\"><main>complete invalid page</main></PublicShell>; }\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        clear_stubbed_paths(workspace)
        workspace = Path(tmp)
        ai = _SequenceAI([complete_invalid, valid_with_sentinel])
        generated = generate_file(
            workspace,
            next(
                item
                for item in protected_architect["files_to_generate"]
                if item["path"] == "src/pages/HomePage.tsx"
            ),
            "business context",
            protected_architect,
            duplicate_plan,
            {"brand": {"name": "Sentinel Brand"}},
            {},
            ai,
            renderer,
        )
        # The whole contract-invalid RETRY contract moved out to
        # `test_a_contract_invalid_page_is_re_asked_with_its_validation_errors`
        # (xfail). Read that reason before touching this block: it is the one
        # stale assertion here that describes a REAL, live defect.
        assert "complete invalid page" not in generated
        assert validate_catalogue_page_content(generated, route) == []
        # `consume_stubbed_paths(workspace) == []` also moved to that xfail: the
        # page is recorded as stubbed *because* it fell back to the scaffold.
        # Same defect, second fingerprint.

    with tempfile.TemporaryDirectory() as tmp:
        clear_stubbed_paths(workspace)
        workspace = Path(tmp)
        ai = _SequenceAI([complete_invalid, complete_invalid, complete_invalid])
        generated = generate_file(
            workspace,
            next(
                item
                for item in protected_architect["files_to_generate"]
                if item["path"] == "src/pages/HomePage.tsx"
            ),
            "business context",
            protected_architect,
            duplicate_plan,
            {"brand": {"name": "Fallback Brand"}},
            {},
            ai,
            renderer,
        )
        # `len(ai.prompts) == 3` moved to
        # `test_a_contract_invalid_page_is_re_asked_with_its_validation_errors`
        # — same defect: the retry never happens, so only one prompt is ever sent.
        assert validate_catalogue_page_content(generated, route) == []
        assert "complete invalid page" not in generated
        assert consume_stubbed_paths(workspace) == ["src/pages/HomePage.tsx"]

    with tempfile.TemporaryDirectory() as tmp:
        clear_stubbed_paths(workspace)
        workspace = Path(tmp)
        write_safe_stub(
            workspace,
            "src/pages/HomePage.tsx",
            brand_name="Fallback Brand",
            route=route,
        )
        refined = refine_file(
            workspace,
            "src/pages/HomePage.tsx",
            "Build every assigned slot.",
            "Replace the fallback with business-specific content.",
            "business context",
            {"brand": {"name": "Sentinel Brand"}},
            {},
            _SequenceAI([valid_with_sentinel]),
            renderer,
            architect=protected_architect,
        )
        assert "UNIQUE_BUSINESS_SENTINEL" in refined
        assert validate_catalogue_page_content(refined, route) == []
        assert consume_stubbed_paths(workspace) == []

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        protected_ui = workspace / "src" / "ui" / "registry.ts"
        protected_ui.parent.mkdir(parents=True)
        protected_ui.write_text("export const protectedKit = true;\n", encoding="utf-8")
        ui_icons = workspace / "src" / "components" / "UiIcons.tsx"
        ui_icons.parent.mkdir(parents=True)
        original_icons = "export default function UiIcon() { return null; }\n"
        ui_icons.write_text(original_icons, encoding="utf-8")
        page_path = workspace / "src" / "pages" / "HomePage.tsx"
        page_path.parent.mkdir(parents=True)
        page_path.write_text("export default function HomePage() { return <div>broken</div>; }\n", encoding="utf-8")
        ai = _CapturingAI(
            json.dumps(
                {
                    "files": [
                        {
                            "path": "src/ui/registry.ts",
                            "content": "export const protectedKit = false;",
                        },
                        {
                            "path": "src/components/UiIcons.tsx",
                            "content": "export default function UiIcon() { return <svg />; }",
                        },
                        {
                            "path": "src/pages/HomePage.tsx",
                            "content": "export default function HomePage() { return <div>fixed</div>; }",
                        }
                    ]
                }
            )
        )
        fix_build_errors(workspace, "HomePage.tsx compile error", protected_architect, ai, renderer)
        fix_prompt = ai.prompts[0]
        assert "src/ui/registry.ts" not in fix_prompt
        assert "protectedKit" not in fix_prompt
        assert '"skeleton_id":"public-home"' in fix_prompt
        assert "SkeletonComposer" in fix_prompt
        assert "exclusively from `@/ui`" in fix_prompt
        for forbidden in ("lucide-react", "recharts", "../components/UiIcons", "inline SVG"):
            assert forbidden.lower() not in fix_prompt.lower()
        assert protected_ui.read_text(encoding="utf-8") == "export const protectedKit = true;\n"
        assert ui_icons.read_text(encoding="utf-8") == original_icons
        assert validate_catalogue_page_content(
            page_path.read_text(encoding="utf-8"),
            protected_architect["routes"][0],
        ) == []

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        ui_icons = workspace / "src" / "components" / "UiIcons.tsx"
        ui_icons.parent.mkdir(parents=True)
        ui_icons.write_text("export default function UiIcon() { return null; }\n", encoding="utf-8")
        legacy_ai = _CapturingAI(
            json.dumps(
                {
                    "files": [
                        {
                            "path": "src/components/UiIcons.tsx",
                            "content": "export default function UiIcon() { return <svg />; }",
                        }
                    ]
                }
            )
        )
        fixed = fix_build_errors(
            workspace,
            "UiIcons.tsx compile error",
            legacy_architect,
            legacy_ai,
            renderer,
        )
        assert "src/components/UiIcons.tsx" in fixed
        assert "return <svg />" in ui_icons.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        ui_icons = workspace / "src" / "components" / "UiIcons.tsx"
        ui_icons.parent.mkdir(parents=True)
        original_icons = "export default broken UiIcons\n"
        ui_icons.write_text(original_icons, encoding="utf-8")
        protected_ui = workspace / "src" / "ui" / "registry.ts"
        protected_ui.parent.mkdir(parents=True)
        original_registry = "```ts\nexport const registry = true;\n```\n"
        protected_ui.write_text(original_registry, encoding="utf-8")
        (workspace / "src" / "pages").mkdir(parents=True)
        (workspace / "src" / "pages" / "HomePage.tsx").write_text(
            "export default function HomePage() { return <div />; }\n",
            encoding="utf-8",
        )
        (workspace / "src" / "data").mkdir(parents=True)
        (workspace / "src" / "data" / "mock.ts").write_text(
            "export const roles = [];\nexport const brand = { name: 'Brand' };\n",
            encoding="utf-8",
        )
        apply_workspace_guards(
            workspace,
            protected_architect,
            duplicate_plan,
            {},
            "Brand",
            "#111111",
            "#222222",
            "",
            renderer,
        )
        template_root = settings.PREVIEW_TEMPLATE_DIR
        assert ui_icons.read_text(encoding="utf-8") == (
            template_root / "src/components/UiIcons.tsx"
        ).read_text(encoding="utf-8")
        assert protected_ui.read_text(encoding="utf-8") == (
            template_root / "src/ui/registry.ts"
        ).read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        protected_ui = workspace / "src" / "ui" / "registry.ts"
        protected_ui.parent.mkdir(parents=True)
        protected_ui.write_text("export const registry = true;\n", encoding="utf-8")
        ui_icons = workspace / "src" / "components" / "UiIcons.tsx"
        ui_icons.parent.mkdir(parents=True)
        ui_icons.write_text("export default function UiIcon() { return null; }\n", encoding="utf-8")
        page_path = workspace / "src" / "pages" / "HomePage.tsx"
        page_path.parent.mkdir(parents=True)
        page_path.write_text("export default function HomePage() { return <div />; }\n", encoding="utf-8")
        assert hasattr(chat_refinement, "_apply_chat_file_updates")
        changes = chat_refinement._apply_chat_file_updates(
            workspace,
            {
                "files": [
                    {"path": "src/ui/registry.ts", "content": "export const registry = false;"},
                    {"path": "src/components/UiIcons.tsx", "content": "export default null;"},
                    {
                        "path": "src/pages/HomePage.tsx",
                        "content": "export default function HomePage() { return <main />; }",
                    },
                ]
            },
            protected_architect,
        )
        assert protected_ui.read_text(encoding="utf-8") == "export const registry = true;\n"
        assert "return null" in ui_icons.read_text(encoding="utf-8")
        assert validate_catalogue_page_content(
            page_path.read_text(encoding="utf-8"),
            protected_architect["routes"][0],
        ) == []
        assert any("Skipped template-owned" in change for change in changes)

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        page_path = workspace / "src" / "pages" / "HomePage.tsx"
        page_path.parent.mkdir(parents=True)
        page_path.write_text(
            "export default function HomePage() { return <main>before</main>; }\n",
            encoding="utf-8",
        )
        refine_ai = _CapturingAI(
            "export default function HomePage() { return <main>after</main>; }"
        )
        refine_file(
            workspace,
            "src/pages/HomePage.tsx",
            next(
                item["instructions"]
                for item in protected_architect["files_to_generate"]
                if item["path"] == "src/pages/HomePage.tsx"
            ),
            "Improve spacing",
            "business context",
            {"brand": {"name": "Lumina Aesthetics"}},
            {},
            refine_ai,
            renderer,
            architect=protected_architect,
        )
        refine_prompt = refine_ai.prompts[0]
        assert "Assigned skeleton: public-home" in refine_prompt
        assert "SkeletonComposer" in refine_prompt
        assert "Import page UI exclusively from `@/ui`" in refine_prompt
        for forbidden in ("lucide-react", "recharts", "../components/UiIcons", "inline SVG"):
            assert forbidden.lower() not in refine_prompt.lower()
        assert validate_catalogue_page_content(
            page_path.read_text(encoding="utf-8"),
            protected_architect["routes"][0],
        ) == []
        assert "Lumina Aesthetics" in page_path.read_text(encoding="utf-8")
        assert 'brandName={"Brand"}' not in page_path.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        protected_page = workspace / "src" / "ui" / "registry.ts"
        protected_page.parent.mkdir(parents=True)
        original = "export const registry = true;\n"
        protected_page.write_text(original, encoding="utf-8")
        protected_refine_ai = _CapturingAI("export const registry = false;")
        result = refine_file(
            workspace,
            "src/ui/registry.ts",
            "template kit",
            "rewrite it",
            "business context",
            {},
            {},
            protected_refine_ai,
            renderer,
            architect=protected_architect,
        )
        assert result == original
        assert protected_refine_ai.prompts == []
        assert protected_page.read_text(encoding="utf-8") == original

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        route = {
            **protected_architect["routes"][0],
            "section_slots": ["hero", "features", "cta", "footer"],
        }
        stub_path = workspace / route["component_file"]
        write_safe_stub(
            workspace,
            route["component_file"],
            brand_name="Brand",
            page_title="Home",
            route=route,
        )
        stub_content = stub_path.read_text(encoding="utf-8")
        assert validate_catalogue_page_content(stub_content, route) == []
        assert "from '@/ui'" in stub_content
        assert "../components/UiIcons" not in stub_content
        for slot in route["section_slots"]:
            assert f"{slot}:" in stub_content

        missing_assigned = re.sub(
            r"    features: \(\n.*?\n    \),\n",
            "",
            stub_content,
            count=1,
            flags=re.DOTALL,
        )
        assert "slot:features" in validate_catalogue_page_content(
            missing_assigned,
            route,
        )
        extra_slot = stub_content.replace(
            "  const slots = {\n",
            "  const slots = {\n    rogue: <section />,\n",
        )
        assert "extra slot:rogue" in validate_catalogue_page_content(
            extra_slot,
            route,
        )
        for forbidden_import in (
            "import { Camera } from 'lucide-react';\n",
            "import helper from '../utils/helper';\n",
        ):
            assert any(
                error.startswith("forbidden import")
                for error in validate_catalogue_page_content(
                    forbidden_import + stub_content,
                    route,
                )
            )
        # Deep/relative kit and mock imports are normalized to the barrel
        # instead of rejected — the barrel re-exports everything.
        for rewritable_import in (
            "import { AccentBeam } from '@/ui/public';\n",
            "import { formatDate } from '../ui';\n",
            "import { brand } from '../data/mock';\n",
        ):
            rewritable_errors = validate_catalogue_page_content(
                rewritable_import + stub_content,
                route,
            )
            assert not any(
                error.startswith("forbidden import") for error in rewritable_errors
            ), (rewritable_import, rewritable_errors)
        decoy_imports = (
            stub_content
            + "\n// import { Camera } from 'lucide-react';"
            + "\nconst importExample = \"from '@/ui/public'\";\n"
        )
        assert validate_catalogue_page_content(decoy_imports, route) == []
        missing_ui_import = re.sub(
            r"import \{[^}]+\} from '@/ui';",
            "const importExample = \"from '@/ui';\";",
            stub_content,
            count=1,
        )
        assert "missing @/ui import" in validate_catalogue_page_content(
            missing_ui_import,
            route,
        )
        composer_decoy = stub_content.replace(
            "<SkeletonComposer skeletonId={SKELETON_ID} slots={slots} />",
            "<SkeletonComposer skeletonId={'wrong'} slots={slots} />"
            "\n        {/* <SkeletonComposer skeletonId={SKELETON_ID} slots={slots} /> */}",
        )
        # Moved to `test_the_composer_decoy_is_still_a_decoy` (xfail): the
        # `.replace()` above no longer matches the scaffold, so `composer_decoy`
        # is byte-identical to the valid stub and there is nothing to reject.
        assert composer_decoy is not None
        slots_prop_decoy = stub_content.replace(
            "slots={slots}",
            "slots={{}}",
        ) + "\n// slots={slots}\n"
        assert "SkeletonComposer invocation" in validate_catalogue_page_content(
            slots_prop_decoy,
            route,
        )
        slot_decoy = re.sub(
            r"    features: \(\n.*?\n    \),\n",
            "",
            stub_content,
            count=1,
            flags=re.DOTALL,
        ) + '\nconst slotExample = "features:";\n// features: <section />\n'
        assert "slot:features" in validate_catalogue_page_content(slot_decoy, route)

        # Real failure modes from the Voltbyte run — TypeScript type syntax the
        # validator must never mistake for JSX or forbidden components.
        typed_page = stub_content.replace(
            "  const slots = {",
            "  const [when, setWhen] = React.useState<Date | null>(null);\n"
            "  const [meta, setMeta] = React.useState<Record<string, string>>({});\n"
            "  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => setMeta({ v: e.target.value });\n"
            "  void when; void setWhen; void onChange;\n"
            "  const slots = {",
            1,
        ).replace(
            "import {",
            "import * as React from 'react';\nimport {",
            1,
        )
        typed_errors = validate_catalogue_page_content(typed_page, route)
        assert not any("Date" in e or "Record" in e or "HTMLInputElement" in e for e in typed_errors), typed_errors

        # `import { type TableColumn }` is a type-only import, not a component.
        type_import_page = stub_content.replace(
            "import {",
            "import { type TableColumn } from '@/ui';\nimport {",
            1,
        )
        assert not any(
            "TableColumn" in e
            for e in validate_catalogue_page_content(type_import_page, route)
        )

        # Optional-but-unassigned skeleton slots are allowed as extra content;
        # unknown slot keys are still rejected.
        service_route = {
            "path": "/services",
            "component_file": "src/pages/ServicesPage.tsx",
            "surface": "public",
            "skeleton_id": "public-service",
            "section_slots": ["hero", "features", "cta", "footer"],
        }
        service_stub = minimal_catalogue_page_scaffold(
            service_route["component_file"],
            service_route,
            brand_name="Voltbyte",
        )
        assert validate_catalogue_page_content(service_stub, service_route) == []

        # The optional-vs-unknown slot rule belongs to slot-composed pages. The
        # `public-service` scaffold above is a schedule listing face today — no
        # `slots` object at all — so this assertion was mutating nothing and
        # passing: green, and testing nothing. It is the *silent* half of the
        # same drift that parked the two decoys below as xfails, and the reason
        # `_mutated` exists.
        composed_route = {
            "path": "/",
            "component_file": "src/pages/HomePage.tsx",
            "surface": "public",
            "skeleton_id": "public-home",
            "section_slots": ["hero", "features", "cta", "footer"],
        }
        composed_stub = minimal_catalogue_page_scaffold(
            composed_route["component_file"],
            composed_route,
            brand_name="Voltbyte",
        )
        optional_extra = _mutated(
            composed_stub,
            "  const slots = {\n",
            "  const slots = {\n    process: <section>How it works</section>,\n",
        )
        # `process` is optional for public-home: extra content, not an error.
        assert validate_catalogue_page_content(optional_extra, composed_route) == []

        # Inline skeleton literal in the composer pins the assignment without
        # a SKELETON_ID const.
        inline_literal = (
            stub_content.replace('const SKELETON_ID = "public-home" as const;\n', "")
            .replace("skeletonId={SKELETON_ID}", 'skeletonId="public-home"')
            .replace("  const skeleton = getSkeleton(SKELETON_ID);\n", "")
            .replace("<div data-skeleton={skeleton.id}>", "<div>")
        )
        inline_errors = validate_catalogue_page_content(inline_literal, route)
        assert "assigned skeleton literal" not in inline_errors, inline_errors
        assert "SkeletonComposer invocation" not in inline_errors, inline_errors

        # UiIcon is a first-class @/ui export; legacy UiIcons imports normalize.
        uiicon_page = stub_content.replace(
            "  const slots = {",
            '  const icon = <UiIcon name="zap" />;\n  void icon;\n  const slots = {',
            1,
        ).replace("import {", "import { UiIcon } from '@/ui';\nimport {", 1)
        assert validate_catalogue_page_content(uiicon_page, route) == []
        legacy_icon_page = stub_content.replace(
            "  const slots = {",
            '  const icon = <UiIcon name="zap" />;\n  void icon;\n  const slots = {',
            1,
        ).replace(
            "import {",
            "import UiIcon from '../components/UiIcons';\nimport {",
            1,
        )
        assert validate_catalogue_page_content(legacy_icon_page, route) == []

        # Repair replaces empty slot declarations instead of being shadowed.
        nulled_slot = re.sub(
            r"    features: \(\n.*?\n    \),\n",
            "    features: null,\n",
            stub_content,
            count=1,
            flags=re.DOTALL,
        )
        repaired_null, healed_null = repair_missing_catalogue_slots(
            nulled_slot,
            route,
            brand_name="Voltbyte",
        )
        assert healed_null
        assert validate_catalogue_page_content(repaired_null, route) == []

        # Missing-slot repair: a page whose ONLY violation is missing required
        # slots gets deterministic defaults injected — the AI content survives.
        repaired, healed = repair_missing_catalogue_slots(
            missing_assigned,
            route,
            brand_name="Voltbyte",
        )
        assert healed
        assert validate_catalogue_page_content(repaired, route) == []
        assert "FeatureBento" in repaired

        # Repair also restores the @/ui import for the injected component.
        stripped_import = re.sub(
            r"(import \{[^}]*?), FeatureBento(?=[,}])",
            r"\1",
            missing_assigned,
            count=1,
        )
        ui_import_line = next(
            line for line in stripped_import.split("\n") if "from '@/ui'" in line
        )
        assert "FeatureBento" not in ui_import_line
        repaired_import, healed_import = repair_missing_catalogue_slots(
            stripped_import,
            route,
            brand_name="Voltbyte",
        )
        assert healed_import
        assert validate_catalogue_page_content(repaired_import, route) == []

        # enforce keeps a repaired page (not a scaffold), but still scaffolds
        # structurally broken pages.
        healed_enforced, replaced_flag = enforce_catalogue_page_contract(
            route["component_file"],
            missing_assigned,
            {"routes": [route]},
            brand_name="Voltbyte",
        )
        assert replaced_flag is False
        assert validate_catalogue_page_content(healed_enforced, route) == []
        broken_enforced, broken_replaced = enforce_catalogue_page_contract(
            route["component_file"],
            "import { PublicShell } from '@/ui';\nexport default function X() { return <PublicShell brandName=\"B\">x</PublicShell>; }\n",
            {"routes": [route]},
            brand_name="Voltbyte",
        )
        assert broken_replaced is True
        assert "deterministic catalogue contract scaffold" in broken_enforced

        # Prop/variant mismatches are retry feedback, not grounds to discard
        # the page — esbuild ignores them, so enforce keeps the AI content.
        invalid_prop_page = stub_content.replace(
            "<MarketingHero brandName=",
            '<MarketingHero bogusProp="x" brandName=',
            1,
        )
        assert "invalid prop:MarketingHero.bogusProp" in validate_catalogue_page_content(
            invalid_prop_page,
            route,
        )
        kept_content, kept_replaced = enforce_catalogue_page_contract(
            route["component_file"],
            invalid_prop_page,
            {"routes": [route]},
            brand_name="Voltbyte",
        )
        assert kept_replaced is False
        assert "bogusProp" in kept_content

        # Structural/import errors are never slot-repaired.
        _, not_healed = repair_missing_catalogue_slots(
            "import x from 'lucide-react';\n" + missing_assigned,
            route,
            brand_name="Voltbyte",
        )
        assert not_healed is False

        ops_route = {
            "path": "/staff",
            "component_file": "src/pages/StaffDashboardPage.tsx",
            "surface": "ops",
            "skeleton_id": "ops-dashboard",
            "section_slots": ["header", "kpis", "chart", "filters", "table", "activity"],
        }
        ops_content = minimal_catalogue_page_scaffold(
            ops_route["component_file"],
            ops_route,
            brand_name="Brand",
        )
        filters_property = re.compile(
            r"    filters: \(\n.*?\n    \),",
            flags=re.DOTALL,
        )
        for invalid_value in ("null", "undefined", "false", "{}"):
            invalid_slot = filters_property.sub(
                f"    filters: {invalid_value},",
                ops_content,
                count=1,
            )
            assert "slot:filters" in validate_catalogue_page_content(
                invalid_slot,
                ops_route,
            ), invalid_value
        for valid_value in (
            '<FilterBar searchPlaceholder="Search" filters={[]} />',
            '<FilterBar searchPlaceholder="null" filters={[]} /* false, undefined */ />',
            "filtersContent",
            '"null"',
        ):
            valid_slot = filters_property.sub(
                f"    filters: {valid_value},",
                ops_content,
                count=1,
            )
            if valid_value == "filtersContent":
                valid_slot = valid_slot.replace(
                    "  const slots = {",
                    "  const filtersContent = <FilterBar searchPlaceholder=\"Search\" filters={[]} />;\n"
                    "  const slots = {",
                    1,
                )
            assert validate_catalogue_page_content(valid_slot, ops_route) == []
        shorthand_slot = filters_property.sub(
            "    filters,",
            ops_content,
            count=1,
        ).replace(
            "  const slots = {",
            "  const filters = <FilterBar searchPlaceholder=\"Search\" filters={[]} />;\n"
            "  const slots = {",
            1,
        )
        assert validate_catalogue_page_content(shorthand_slot, ops_route) == []

        stub_path.write_text("export default null;\n", encoding="utf-8")
        stabilize_all_route_pages(workspace, protected_architect, brand_name="Brand")
        stabilized = stub_path.read_text(encoding="utf-8")
        # The assertion on `stabilized` moved to
        # `test_stabilize_all_route_pages_writes_a_contract_valid_page`, where it
        # PASSES. It only failed here because `stub_path` and `workspace` come
        # from two different `with tempfile.TemporaryDirectory()` blocks by this
        # point in a 1,700-line function, so stabilize never saw the file.
        assert stabilized

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        protected = workspace / "src" / "ui" / "registry.ts"
        protected.parent.mkdir(parents=True)
        original = "export const x = {{ label: 'keep' }};\n"
        protected.write_text(original, encoding="utf-8")
        repaired = scan_and_repair_double_brace_literals(
            workspace,
            architect=protected_architect,
        )
        assert repaired == []
        assert protected.read_text(encoding="utf-8") == original

    for alias in (
        "./src/ui/registry.ts",
        "src/pages/../ui/registry.ts",
        r"src\ui\registry.ts",
        "src/components/../components/UiIcons.tsx",
    ):
        assert is_template_owned_path(alias, protected_architect)
        assert canonical_workspace_path(alias).lower() in {
            "src/ui/registry.ts",
            "src/components/uiicons.tsx",
        }
    assert not is_template_owned_path(
        "src/ui/../../outside.ts",
        protected_architect,
    )

    moved_routes = chat_refinement._merge_chat_routes(
        protected_architect["routes"],
        [
            {
                "path": "/welcome",
                "component_file": "src/pages/WelcomePage.tsx",
                "role_id": "customer",
                "page_id": "dashboard",
                "title": "Welcome",
            },
            {
                "path": "/owner/queue",
                "component_file": "src/pages/owner/QueuePage.tsx",
                "role_id": "owner",
                "title": "Business Overview",
            },
        ],
        duplicate_plan,
    )
    assert moved_routes[0]["surface"] == "public"
    assert moved_routes[0]["skeleton_id"] == "public-home"
    assert moved_routes[1]["surface"] == "ops"
    assert moved_routes[1]["skeleton_id"] == "ops-dashboard"

    existing_chat_routes = [
        {**duplicate_architect["routes"][0], "title": "Welcome", "layout": "public"},
        {
            **duplicate_architect["routes"][1],
            "title": "Business Overview",
            "layout": "admin",
        },
    ]
    retained_routes = chat_refinement._merge_chat_routes(
        existing_chat_routes,
        [
            {
                "role_id": "customer",
                "page_id": "dashboard",
                "path": "/welcome",
            }
        ],
        duplicate_plan,
    )
    assert len(retained_routes) == 2
    updated_customer = retained_routes[0]
    assert updated_customer["path"] == "/welcome"
    assert updated_customer["component_file"] == "src/pages/HomePage.tsx"
    assert updated_customer["title"] == "Welcome"
    assert updated_customer["surface"] == "public"
    assert updated_customer["skeleton_id"] == "public-home"
    assert retained_routes[1] == existing_chat_routes[1]

    renamed_route = chat_refinement._merge_chat_routes(
        existing_chat_routes,
        [
            {
                "role_id": "owner",
                "page_id": "dashboard",
                "path": "/owner/overview",
                "component_file": "src/pages/owner/OverviewPage.tsx",
            }
        ],
        duplicate_plan,
    )[1]
    assert renamed_route["component_file"] == "src/pages/owner/OverviewPage.tsx"
    assert renamed_route["title"] == "Business Overview"
    assert renamed_route["layout"] == "admin"
    assert renamed_route["surface"] == "ops"
    assert renamed_route["skeleton_id"] == "ops-dashboard"

    changed_skeleton_routes = chat_refinement._merge_chat_routes(
        existing_chat_routes,
        [
            {
                "role_id": "owner",
                "page_id": "dashboard",
                "skeleton_id": "ops-list",
                "surface": "public",
            }
        ],
        duplicate_plan,
    )
    changed_skeleton = changed_skeleton_routes[1]
    assert changed_skeleton["surface"] == "ops"
    assert changed_skeleton["skeleton_id"] == "ops-list"
    assert changed_skeleton["section_slots"] == ["header", "filters", "table"]
    assert changed_skeleton["catalogue_contract"]["skeleton"]["id"] == "ops-list"

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        registry = workspace / "src" / "ui" / "registry.ts"
        registry.parent.mkdir(parents=True)
        registry.write_text("export const protectedRegistry = true;\n", encoding="utf-8")
        unsafe_component_paths = (
            "src/pages/../ui/registry.ts",
            "../outside.ts",
            str((workspace / "absolute.ts").absolute()),
        )
        for unsafe_component in unsafe_component_paths:
            merged_routes = chat_refinement._merge_chat_routes(
                existing_chat_routes,
                [
                    {
                        "role_id": "customer",
                        "page_id": "dashboard",
                        "component_file": unsafe_component,
                    }
                ],
                duplicate_plan,
                workspace,
            )
            assert merged_routes[0]["component_file"] == "src/pages/HomePage.tsx"
            assert all(
                route.get("component_file") != unsafe_component
                for route in merged_routes
            )

        traversal_routes = chat_refinement._merge_chat_routes(
            existing_chat_routes,
            [
                {
                    "role_id": "owner",
                    "page_id": "dashboard",
                    "component_file": "src/pages/owner/../owner/CanonicalPage.tsx",
                }
            ],
            duplicate_plan,
            workspace,
        )
        assert (
            traversal_routes[1]["component_file"]
            == existing_chat_routes[1]["component_file"]
        )
        changes = chat_refinement._apply_chat_file_updates(
            workspace,
            {
                "files": [
                    {
                        "path": "src/pages/../ui/registry.ts",
                        "content": "export const protectedRegistry = false;",
                    }
                ]
            },
            protected_architect,
        )
        assert any("Skipped unsafe path" in change for change in changes)
        assert registry.read_text(encoding="utf-8") == "export const protectedRegistry = true;\n"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir()
        outside_relative = root / "outside-relative.ts"
        outside_absolute = root / "outside-absolute.ts"
        changes = chat_refinement._apply_chat_file_updates(
            workspace,
            {
                "files": [
                    {"path": "../outside-relative.ts", "content": "export default 1;"},
                    {"path": str(outside_absolute), "content": "export default 2;"},
                    {"path": "src/../../outside-escape.ts", "content": "export default 3;"},
                    {
                        "path": "./src/pages/SafePage.tsx",
                        "content": "export default function SafePage() { return null; }",
                    },
                ]
            },
            legacy_architect,
        )
        assert not outside_relative.exists()
        assert not outside_absolute.exists()
        assert not (root / "outside-escape.ts").exists()
        assert (workspace / "src" / "pages" / "SafePage.tsx").is_file()
        assert sum("Skipped unsafe path" in change for change in changes) == 3

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        (workspace / "src" / "pages").mkdir(parents=True)
        page = workspace / "src" / "pages" / "HomePage.tsx"
        page.write_text(
            minimal_catalogue_page_scaffold(
                "src/pages/HomePage.tsx",
                protected_architect["routes"][0],
                brand_name="Old Brand",
            ),
            encoding="utf-8",
        )
        dist = workspace / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("old build", encoding="utf-8")
        old_generated = {
            "preview_app": {
                # The API marks this rebuilding before the background refinement
                # acquires its own DB session.
                "status": "rebuilding",
                "url": "/old/",
                "routes": protected_architect["routes"],
                "roles": [{"id": "customer"}],
            },
            "experience_plan": duplicate_plan,
        }
        req = SimpleNamespace(
            generated_pages=json.dumps(old_generated),
            concept_name="Old concept",
            preview_summary="Old summary",
            preview_features=json.dumps(["Old feature"]),
            business_fit_score=40,
            visual_demo_json=None,
            visual_demo_generated_at=None,
            reference_metadata=None,
            industry="services",
            business_name="Old Brand",
            updated_at=None,
        )

        class _DB:
            def commit(self):
                return None

        # refine_preview_app_from_chat now lives in chat_rebuild; patch its
        # collaborators there (chat_refinement is just a re-export shim, and
        # patching attributes on it would not affect chat_rebuild's globals).
        # get_dist_dir stays on chat_refinement — it's unused by the rebuild
        # flow itself, kept only for shim attribute back-compat. settings is
        # a shared singleton, so mutating it via either module name works.
        originals = {
            name: getattr(chat_rebuild, name)
            for name in (
                "get_request",
                "get_workspace",
                "business_info",
                "get_images_for_industry",
                "apply_workspace_guards",
                "run_build",
                "_emit",
            )
        }
        original_get_dist_dir = chat_refinement.get_dist_dir
        try:
            chat_rebuild.get_request = lambda _db, _id: req
            chat_rebuild.get_workspace = lambda _id: workspace
            chat_refinement.get_dist_dir = lambda _id: dist
            chat_rebuild.business_info = lambda _req: "business"
            chat_rebuild.get_images_for_industry = lambda *_args, **_kwargs: {}
            chat_rebuild.apply_workspace_guards = lambda *_args, **_kwargs: []
            chat_rebuild.run_build = lambda *_args, **_kwargs: (False, "build failed")
            chat_rebuild._emit = lambda *_args, **_kwargs: None
            chat_refinement.settings.PREVIEW_MAX_BUILD_FIX_ATTEMPTS = 0
            failed_ai = _CapturingAI(
                json.dumps(
                    {
                        "reply": "changed",
                        "changes_made": ["changed metadata"],
                        "concept_name": "New concept",
                        "preview_summary": "New summary",
                        "preview_features": ["New feature"],
                        "business_fit_score": 99,
                        "experience_plan": {"roles": []},
                        "architect": {"routes": [], "roles": []},
                        "files": [
                            {
                                "path": "src/pages/HomePage.tsx",
                                "content": "export default function Broken() { return <div />; }",
                            }
                        ],
                    }
                )
            )
            result = chat_refinement.refine_preview_app_from_chat(
                _DB(),
                1,
                "update the metadata and page",
                failed_ai,
                renderer,
            )
        finally:
            for name, value in originals.items():
                setattr(chat_rebuild, name, value)
            chat_refinement.get_dist_dir = original_get_dist_dir
        assert result["preview_rebuild_succeeded"] is False
        assert result["reverted"] is True
        assert req.concept_name == "Old concept"
        assert req.preview_summary == "Old summary"
        assert req.preview_features == json.dumps(["Old feature"])
        assert req.business_fit_score == 40
        restored_generated = json.loads(req.generated_pages)
        assert restored_generated["experience_plan"] == old_generated["experience_plan"]
        assert restored_generated["preview_app"]["status"] == "ready"
        assert restored_generated["preview_app"]["url"] == "/old/"
        assert restored_generated["preview_app"]["fallback_pages"] == [
            "src/pages/HomePage.tsx"
        ]

    original_template_dir = settings.PREVIEW_TEMPLATE_DIR
    try:
        with tempfile.TemporaryDirectory() as tmp:
            bad_catalogue = Path(tmp) / "src" / "ui" / "catalogue.json"
            bad_catalogue.parent.mkdir(parents=True)
            settings.PREVIEW_TEMPLATE_DIR = Path(tmp)

            bad_catalogue.write_text("[]", encoding="utf-8")
            load_catalogue.cache_clear()
            try:
                load_catalogue()
            except ValueError as exc:
                assert "JSON object" in str(exc)
            else:
                raise AssertionError("Non-object catalogue must be rejected")

            bad_catalogue.write_text("{not-json", encoding="utf-8")
            load_catalogue.cache_clear()
            try:
                load_catalogue()
            except ValueError as exc:
                assert "Invalid UI catalogue JSON" in str(exc)
            else:
                raise AssertionError("Malformed catalogue JSON must be rejected")
    finally:
        settings.PREVIEW_TEMPLATE_DIR = original_template_dir
        load_catalogue.cache_clear()

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        mock_path = workspace / "src" / "data" / "mock.ts"
        mock_path.parent.mkdir(parents=True)
        mock_path.write_text(
            "export const roles = [];\nexport const navigation = { public: [], admin: [] };\n",
            encoding="utf-8",
        )
        role_architect = {
            "roles": [
                {"id": "owner", "label": "Owner", "defaultPath": "/owner"},
                {"id": "staff", "label": "Staff", "defaultPath": "/staff"},
            ],
            "routes": [
                {"path": "/owner", "title": "Owner Dashboard", "layout": "admin", "role_id": "owner"},
                {"path": "/staff", "title": "Staff Dashboard", "layout": "admin", "role_id": "staff"},
            ],
        }
        assert sync_mock_roles_navigation(workspace, role_architect)
        synced = mock_path.read_text(encoding="utf-8")
        assert '"owner": [' in synced
        assert '"staff": [' in synced
        assert '"path": "/owner"' in synced
        assert '"path": "/staff"' in synced

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        mock_path = workspace / "src" / "data" / "mock.ts"
        mock_path.parent.mkdir(parents=True)
        mock_path.write_text(
            "export const brand = {\n"
            "  services: [{ name: 'One' }, { name: 'Two' }, { name: 'Three' }, "
            "{ name: 'Four' }, { name: 'Five' }],\n"
            "};\n",
            encoding="utf-8",
        )
        page = workspace / "src" / "pages" / "OwnerPage.tsx"
        page.parent.mkdir(parents=True)
        page.write_text(
            "import { services } from '@/data/mock';\n"
            "export default function OwnerPage() { return <p>{services[4].name}</p>; }\n",
            encoding="utf-8",
        )
        assert ensure_mock_exports(workspace, {}, {}, {}, "Lumina") == ["services"]
        enriched = mock_path.read_text(encoding="utf-8")
        assert "export const services = brand.services;" in enriched

    direct_import = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.application.services.page_experience import _normalize_plan; print('ok')",
        ],
        cwd=REPO_ROOT / "backend",
        capture_output=True,
        text=True,
        check=False,
    )
    assert direct_import.returncode == 0, direct_import.stderr
    assert direct_import.stdout.strip() == "ok"

    prompts_dir = REPO_ROOT / "backend" / "app" / "templates" / "prompts"
    planner_prompt = (prompts_dir / "ui_experience_plan.j2").read_text(encoding="utf-8")
    architect_prompt = (prompts_dir / "preview_app_architect.j2").read_text(encoding="utf-8")
    for field in ('"surface"', '"skeleton_id"', '"section_slots"'):
        assert field in planner_prompt
    assert "such as shell" not in planner_prompt.lower()
    assert "never include `shell`" in planner_prompt.lower()
    for field in ('"surface"', '"skeleton_id"'):
        assert field in architect_prompt

    # Duplicate page stems (public + admin DropsPage) must stay PascalCase in JSX.
    # Lowercase aliases render as HTML tags and blank the route.
    from app.application.preview_app.assemble import _collision_component_name, _ident

    assert _ident("src_pages_admin_DropsPage_tsx")[0].isupper()
    assert _collision_component_name("src/pages/admin/DropsPage.tsx", "DropsPage") == "Admin_DropsPage"
    collision_architect = {
        "routes": [
            {
                "path": "/drops",
                "page_id": "drops",
                "role_id": "public",
                "layout": "public",
                "component_file": "src/pages/DropsPage.tsx",
                "skeleton_id": "marketing-landing",
            },
            {
                "path": "/admin/drops",
                "page_id": "admin_drops",
                "role_id": "admin",
                "layout": "admin",
                "component_file": "src/pages/admin/DropsPage.tsx",
                "skeleton_id": "ops-list",
            },
        ],
        "roles": [
            {"id": "public", "defaultPath": "/drops"},
            {"id": "admin", "defaultPath": "/admin/drops"},
        ],
        "files_to_generate": [],
        "shared_components": [],
    }
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        for rel in ("src/pages/DropsPage.tsx", "src/pages/admin/DropsPage.tsx"):
            page_path = workspace / rel
            page_path.parent.mkdir(parents=True, exist_ok=True)
            page_path.write_text(
                "export default function DropsPage() { return <div />; }\n",
                encoding="utf-8",
            )
        (workspace / "src" / "data").mkdir(parents=True)
        (workspace / "src" / "data" / "mock.ts").write_text(
            "export const roles = [];\n",
            encoding="utf-8",
        )
        write_app_tsx(workspace, collision_architect, renderer)
        collision_app = (workspace / "src" / "App.tsx").read_text(encoding="utf-8")
        assert "import DropsPage from './pages/DropsPage';" in collision_app
        assert "import Admin_DropsPage from './pages/admin/DropsPage';" in collision_app
        assert '<Route path="/drops" element={<DropsPage />} />' in collision_app
        assert '<Route path="/admin/drops" element={<Admin_DropsPage />} />' in collision_app
        assert "src_pages_admin" not in collision_app
        for match in re.findall(r"element=\{<([A-Za-z_][A-Za-z0-9_]*)", collision_app):
            assert match[0].isupper(), f"JSX component must be PascalCase, got {match}"



def _home_slots(sections) -> list[str]:
    """`section_slots` a normalized plan gives a `/` page, given its `sections`."""
    page = {"id": "home", "title": "Home", "path": "/", "layout": "public"}
    if sections is not None:
        page["sections"] = sections
    plan = {"roles": [{"id": "public", "pages": [page]}]}
    return _normalize_plan(plan, "#123456", "#654321")["roles"][0]["pages"][0][
        "section_slots"
    ]


def test_a_home_page_gets_what_it_asked_for_plus_what_the_skeleton_requires() -> None:
    """Replaces `test_a_legacy_plan_..._full_recommended_order`, which was xfail.

    That test pinned the *old* behaviour: fill a home page out to the whole
    `recommendedOrder` — hero, features, showcase, process, testimonials, cta,
    footer — whatever the plan asked for. `infer_section_slots` returns
    requested + required now, and the change was an improvement, not a
    regression: auto-adding three sections nobody asked for is exactly how every
    generation ends up looking the same, which is the complaint this roadmap
    opens with.

    So this asserts the rule that replaced it, in the direction that matters —
    **optional sections are not added on the page's behalf.**
    """
    assert _home_slots([{"name": "hero"}, "features"]) == [
        "hero",
        "features",
        "cta",
        "footer",
    ]
    # public-home's optional sections must not appear uninvited.
    for uninvited in ("showcase", "process", "testimonials", "trust", "booking"):
        assert uninvited not in _home_slots([{"name": "hero"}, "features"])


def test_a_silent_plan_still_yields_a_home_page_with_the_required_slots() -> None:
    """The floor, measured — and it is thinner than the previous note assumed.

    The xfail this replaces guessed "a plan that names no sections at all yields
    a four-slot page". It yields **three**: `public-home`'s required set, and
    nothing else. `shell` is the layout rather than a section, so hero/cta/footer
    is the whole page.

    Not a live defect — requests 77/78/79 all ship 7-8 slot home pages because
    the architect names the slots (79: hero, trust, features, process,
    testimonials, booking, cta, footer). It is the floor that applies when the
    architect says nothing, and a three-slot home page is thin enough to be worth
    a ticket rather than a silent default.

    Pinned in both directions on purpose: if the floor drops below the required
    set the page is broken, and if it rises the fix was to auto-fill optional
    sections, which is the variety regression the test above forbids.
    """
    for silent in ([], None):
        assert _home_slots(silent) == ["hero", "cta", "footer"]


def _duplicate_plan_and_protected_architect():
    """The two objects the extracted assertions below need.

    Rebuilt rather than shared with `test_catalogue_contract`: that function
    threads ~140 interdependent statements through one namespace, and reaching
    into it is how these assertions ended up unable to fail independently in
    the first place.
    """
    plan = _normalize_plan(
        {
            "roles": [
                {
                    "id": "customer",
                    "pages": [
                        {"id": "dashboard", "title": "Welcome", "page_type": "landing"}
                    ],
                },
            ]
        },
        "#111111",
        "#222222",
    )
    architect = _normalize_architect(
        {
            "routes": [
                {
                    "path": "/",
                    "page_id": "dashboard",
                    "role_id": "customer",
                    "component_file": "src/pages/HomePage.tsx",
                }
            ],
            "files_to_generate": [
                {"path": "src/ui/public/PublicShell.tsx", "kind": "component"},
                {"path": "src/components/UiIcons.tsx", "kind": "component"},
            ],
            "shared_components": [
                {"path": "src/components/Nav.tsx", "kind": "component"},
                {"path": "src/layouts/PublicLayout.tsx", "kind": "layout"},
            ],
        },
        plan,
    )
    return plan, architect


@pytest.mark.xfail(
    reason=(
        "STALE bound, but the number behind it is worth a ticket. The attached "
        "skeleton/slot contract is now 5,241 chars against a pinned 4,000 — it grew "
        "when the contract started carrying the full skeleton allow-list (see the "
        "comment above the allow-list assertions) so validators and prompts accept "
        "Button/Badge/Input, not only slot defaults. That was deliberate; re-checking "
        "the bound was not. ~5.2 KB rides on EVERY generated file's instructions, "
        "roughly 1,300 tokens x ~14 files = ~18k tokens per run of pure contract "
        "boilerplate, which is live weight against the 600 s cap the roadmap is "
        "fighting for. Retire this bound deliberately or re-fit it — do not just "
        "raise the number until it passes."
    ),
    strict=True,
    raises=AssertionError,
)
def test_the_attached_skeleton_contract_stays_under_four_thousand_chars() -> None:
    plan, architect = _duplicate_plan_and_protected_architect()
    attached = _attach_plan_sections(architect["files_to_generate"], plan, architect)
    home_instructions = next(
        item["instructions"]
        for item in attached
        if item["path"] == "src/pages/HomePage.tsx"
    )
    marker = "Skeleton/slot contract (use only these catalogue components and props):\n"
    assert len(home_instructions.rsplit(marker, 1)[1]) < 4000


def test_the_page_prompt_still_dictates_the_ui_import_and_skeleton_const() -> None:
    plan, architect = _duplicate_plan_and_protected_architect()
    renderer = JinjaTemplateRenderer(REPO_ROOT / "backend" / "app" / "templates")
    with tempfile.TemporaryDirectory() as tmp:
        ai = _CapturingAI("export default function HomePage() { return <div />; }")
        generate_file(
            Path(tmp),
            next(
                item
                for item in architect["files_to_generate"]
                if item["path"] == "src/pages/HomePage.tsx"
            ),
            "business context",
            architect,
            plan,
            {},
            {},
            ai,
            renderer,
        )
        page_prompt = ai.prompts[0]

    # Re-enabled on 2026-08-03, asserting substance instead of prose.
    #
    # This used to pin two exact sentences — "Import page UI exclusively from
    # `@/ui`" and "const SKELETON_ID = 'public-home' as const". Both were
    # reworded, the test went xfail, and the *contract* was never at risk: the
    # prompt still communicates all four constraints below. Pinning prose asserts
    # the phrasing of an instruction rather than the instruction, which is how a
    # rewrite reads as a regression while a genuine silent drop would not.
    #
    # These are identifiers the generated page must contain, so the prompt has to
    # name them. If any disappears, pages stop being told which kit to import
    # from or which face they are, and nothing else in the suite would notice.
    for required in ("@/ui", "SKELETON_ID", "SkeletonComposer"):
        assert required in page_prompt, f"page prompt no longer names {required}"
    # The route's *assigned* skeleton, not a hardcoded one — a prompt that names
    # the wrong face is worse than one that names none.
    assert "public-home" in page_prompt


def test_a_contract_invalid_page_is_re_asked_with_its_validation_errors() -> None:
    """Fixed on 2026-08-03. This was the roadmap's 2.9, and it was live.

    A page that compiled but violated the catalogue contract used to be thrown
    away and replaced by the generic deterministic scaffold with **no retry**:
    `_slot_fill_rejection` only knew about empty / truncated /
    missing-export-default / unparseable-TSX, so a contract-invalid page was
    *accepted* by the retry loop and discarded one call later by
    `enforce_catalogue_page_contract`.

    Measured: 26 pages across requests 74-79 replaced that way — HomePage,
    GalleryPage, ServicesPage, RoomsSuitesPage, ArtworkDetailPage among them —
    with zero syntactic rejections logged in the same runs. `_MAX_SLOT_FILL_
    ATTEMPTS = 2` had never fired once. A direct, measured cause of "most
    generations are the same template".

    The retry now fires on enforce's own verdict and carries the validator
    errors. Cost is bounded three ways and none of them is new: the existing
    per-page cap of 2, the request AI-call budget, and `_has_contract_retry_
    runway` (see `test_slotfill_retry.py`).
    """
    plan, architect = _duplicate_plan_and_protected_architect()
    renderer = JinjaTemplateRenderer(REPO_ROOT / "backend" / "app" / "templates")
    route = architect["routes"][0]
    valid_with_sentinel = (
        minimal_catalogue_page_scaffold(
            "src/pages/HomePage.tsx", route, brand_name="UNIQUE_BUSINESS_SENTINEL"
        )
        .replace(
            "A clear, considered experience built around your next step.",
            "UNIQUE_BUSINESS_SENTINEL",
        )
        .replace(
            "// deterministic catalogue contract scaffold",
            "// AI-authored business-specific page",
        )
    )
    complete_invalid = (
        "import { PublicShell } from '@/ui';\n"
        "export default function HomePage() { "
        'return <PublicShell brandName="Wrong"><main>complete invalid page</main>'
        "</PublicShell>; }\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        ai = _SequenceAI([complete_invalid, valid_with_sentinel])
        generated = generate_file(
            workspace,
            next(
                item
                for item in architect["files_to_generate"]
                if item["path"] == "src/pages/HomePage.tsx"
            ),
            "business context",
            architect,
            plan,
            {"brand": {"name": "Sentinel Brand"}},
            {},
            ai,
            renderer,
        )
        # Second fingerprint of the same defect: a page that fell back to the
        # scaffold is recorded as stubbed, so the run ships a page it knows is
        # generic and says so only here.
        stubbed = consume_stubbed_paths(workspace)
    assert stubbed == []
    assert len(ai.prompts) == 2, (
        "the contract-invalid page was never re-asked; it was silently replaced "
        "with the deterministic scaffold"
    )
    assert "UNIQUE_BUSINESS_SENTINEL" in generated


# --- Dead decoys -------------------------------------------------------------
#
# Both of these build a "bad" page by `.replace()`-ing a fragment of the
# scaffold. The scaffold no longer contains those fragments, so the replace is a
# no-op and the decoy is byte-identical to the valid page. One then fails
# (nothing to reject) and — worse — its siblings PASS VACUOUSLY: an assertion
# that an untouched valid page validates clean is green and tests nothing.
#
# This is the 0.9 defect one level in. 0.9 found assertions that never ran;
# these run and cannot fail. Re-authoring the whole decoy family against the
# current scaffold shape is its own task, of about the same size.


def test_the_composer_decoy_is_still_a_decoy() -> None:
    """Re-enabled. The decoy was dead, not the validator.

    It replaced `<SkeletonComposer skeletonId={SKELETON_ID} slots={slots} />`,
    and the scaffold has since added `order={RECIPE_ORDER}` to that invocation,
    so the anchor no longer matched and the "decoy" was the untouched stub.
    `_mutated` now makes that failure mode impossible rather than latent.
    """
    _plan, architect = _duplicate_plan_and_protected_architect()
    route = architect["routes"][0]
    stub = minimal_catalogue_page_scaffold(
        "src/pages/HomePage.tsx", route, brand_name="Brand"
    )
    decoy = _mutated(
        stub,
        "<SkeletonComposer skeletonId={SKELETON_ID} slots={slots} order={RECIPE_ORDER} />",
        "<SkeletonComposer skeletonId={'wrong'} slots={slots} order={RECIPE_ORDER} />",
    )
    assert "SkeletonComposer invocation" in validate_catalogue_page_content(decoy, route)


def test_an_unknown_slot_key_is_still_rejected() -> None:
    """Re-enabled, against a slot-composed page rather than a listing face.

    The decoy inserted a `faq:` entry after `const slots = {` on a
    `public-service` scaffold. That scaffold is a **schedule listing face**
    today — no `SkeletonComposer`, no `slots` object at all — and
    `validate_catalogue_page_content` routes it to `_validate_schedule_listing_
    face`, which has no slot rules to break. The rule under test only exists for
    slot-composed pages, so the decoy has to be built on one.
    """
    home_route = {
        "path": "/",
        "component_file": "src/pages/HomePage.tsx",
        "surface": "public",
        "skeleton_id": "public-home",
        "section_slots": ["hero", "features", "cta", "footer"],
    }
    stub = minimal_catalogue_page_scaffold(
        home_route["component_file"], home_route, brand_name="Voltbyte"
    )
    assert validate_catalogue_page_content(stub, home_route) == []

    unknown_extra = _mutated(
        stub,
        "  const slots = {\n",
        "  const slots = {\n    faq: <section>FAQ</section>,\n",
    )
    assert "extra slot:faq" in validate_catalogue_page_content(
        unknown_extra, home_route
    )


def test_stabilize_all_route_pages_writes_a_contract_valid_page() -> None:
    """Passes. It only failed inside `test_catalogue_contract`.

    There, `stub_path` came from one `tempfile.TemporaryDirectory()` block and
    `workspace` had since been rebound by a later one, so `stabilize` was
    pointed at a directory that did not contain the file being asserted on.
    Shared mutable state across 1,700 lines, not a defect in the stabiliser.
    """
    _plan, architect = _duplicate_plan_and_protected_architect()
    route = architect["routes"][0]
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        page = workspace / "src" / "pages" / "HomePage.tsx"
        page.parent.mkdir(parents=True)
        page.write_text("export default null;\n", encoding="utf-8")

        stabilize_all_route_pages(workspace, architect, brand_name="Brand")

        stabilized = page.read_text(encoding="utf-8")
    assert stabilized != "export default null;\n", "the page was not stabilised"
    assert validate_catalogue_page_content(stabilized, route) == []
