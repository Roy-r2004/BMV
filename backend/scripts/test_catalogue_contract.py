from __future__ import annotations

import sys
import subprocess
import json
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[2]
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
from app.application.preview_app.codegen import (
    _architect_prompt_context,
    _bounded_json,
    fix_build_errors,
    generate_file,
    page_plan_for_file,
    refine_file,
)
from app.application.preview_app import chat_refinement
from app.application.preview_app.catalogue_contract import (
    minimal_catalogue_page_scaffold,
    validate_catalogue_page_content,
)
from app.application.preview_app.fallback import (
    clear_stubbed_paths,
    consume_stubbed_paths,
    scan_and_repair_double_brace_literals,
    stabilize_all_route_pages,
    write_safe_stub,
)
from app.application.preview_app.pipeline import _attach_plan_sections, _normalize_architect
from app.application.preview_app.protected_paths import (
    canonical_workspace_path,
    is_template_owned_path,
)
from app.application.preview_app.safety import apply_workspace_guards, ensure_mock_exports
from app.application.services.page_experience import _normalize_plan
from app.core.config import settings
from app.infrastructure.templating.renderer import JinjaTemplateRenderer


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


def main() -> None:
    catalogue = load_catalogue()
    assert load_catalogue() is catalogue
    skeleton_ids = {item["id"] for item in catalogue["skeletons"]}
    assert skeleton_ids == {
        "public-home",
        "public-service",
        "public-detail",
        "public-booking",
        "ops-dashboard",
        "ops-list",
        "ops-detail",
        "ops-settings",
    }

    booking = get_skeleton("public-booking")
    assert booking["surface"] == "public"
    assert "BookingPanel" in booking["allowedComponents"]

    contract = compact_skeleton_contract("ops-dashboard")
    assert contract["skeleton"]["id"] == "ops-dashboard"
    assert [component["name"] for component in contract["components"]] == [
        "OpsShell",
        "PageHeader",
        "StatCard",
        "ChartCard",
        "FilterBar",
        "DataTable",
        "ActivityFeed",
    ]
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
    assert "items" in public_components["PublicNav"]["requiredProps"]

    normalized_slots = infer_section_slots(
        {"section_slots": ["cta", "unknown", "hero", "hero"]},
        "public-service",
    )
    assert normalized_slots == ["hero", "features", "process", "cta", "footer"]
    assert infer_section_slots({}, "public-service") == [
        "hero",
        "features",
        "process",
        "cta",
        "footer",
    ]
    assert infer_section_slots({"section_slots": ["shell", "unknown"]}, "ops-list") == [
        "header",
        "filters",
        "table",
    ]
    compact = compact_skeleton_contract("public-service", normalized_slots)
    compact_names = [component["name"] for component in compact["components"]]
    assert compact_names == [
        "PublicShell",
        "PublicNav",
        "MarketingHero",
        "FeatureBento",
        "ProcessSection",
        "CTABand",
        "BrandFooter",
    ]
    assert "allowedComponents" not in compact["skeleton"]
    assert len(json.dumps(compact)) < 5000

    cases = [
        ({"title": "Welcome", "page_type": "landing"}, ("public", "public-home")),
        ({"title": "Our Services", "page_type": "service listing"}, ("public", "public-service")),
        ({"title": "Signature Facial", "page_type": "service detail"}, ("public", "public-detail")),
        ({"title": "Book an Appointment", "page_type": "booking"}, ("public", "public-booking")),
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
    assert home["section_slots"] == [
        "hero",
        "features",
        "showcase",
        "process",
        "testimonials",
        "cta",
        "footer",
    ]
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
    assert len(attached_contract_json) < 4000
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
    assert [item["name"] for item in attached_contract["components"]] == selected_component_names
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
        assert "Import page UI exclusively from `@/ui`" in page_prompt
        assert "const SKELETON_ID = 'public-home' as const" in page_prompt
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
        assert len(ai.prompts) == 2
        assert "UNIQUE_BUSINESS_SENTINEL" in generated
        assert "complete invalid page" not in generated
        assert validate_catalogue_page_content(generated, route) == []
        retry_prompt = ai.prompts[1]
        for error in validate_catalogue_page_content(complete_invalid, route):
            assert error in retry_prompt
        assert '"skeleton_id":"public-home"' in retry_prompt
        assert "complete invalid page" in retry_prompt
        assert consume_stubbed_paths(workspace) == []

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
        assert len(ai.prompts) == 3
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
            "import { PublicShell } from '@/ui/public';\n",
            "import helper from '../utils/helper';\n",
        ):
            assert "forbidden import" in validate_catalogue_page_content(
                forbidden_import + stub_content,
                route,
            )
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
        assert "SkeletonComposer invocation" in validate_catalogue_page_content(
            composer_decoy,
            route,
        )
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
        assert validate_catalogue_page_content(stabilized, route) == []

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

        originals = {
            name: getattr(chat_refinement, name)
            for name in (
                "get_request",
                "get_workspace",
                "get_dist_dir",
                "business_info",
                "get_images_for_industry",
                "apply_workspace_guards",
                "run_build",
                "_emit",
                "MAX_BUILD_FIX_ATTEMPTS",
            )
        }
        try:
            chat_refinement.get_request = lambda _db, _id: req
            chat_refinement.get_workspace = lambda _id: workspace
            chat_refinement.get_dist_dir = lambda _id: dist
            chat_refinement.business_info = lambda _req: "business"
            chat_refinement.get_images_for_industry = lambda *_args, **_kwargs: {}
            chat_refinement.apply_workspace_guards = lambda *_args, **_kwargs: []
            chat_refinement.run_build = lambda *_args, **_kwargs: (False, "build failed")
            chat_refinement._emit = lambda *_args, **_kwargs: None
            chat_refinement.MAX_BUILD_FIX_ATTEMPTS = 0
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
                setattr(chat_refinement, name, value)
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


if __name__ == "__main__":
    main()
