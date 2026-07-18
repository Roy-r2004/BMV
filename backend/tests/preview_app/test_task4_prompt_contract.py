from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.prompts import PromptTemplate
from app.application.preview_app import codegen
from app.application.preview_app.pipeline import architect_normalize as _arch_norm
from app.application.preview_app.text_utils import _bounded_json as _text_bounded_json
from app.application.preview_app.catalogue_contract import minimal_catalogue_page_scaffold
from app.application.services import page_experience
from app.application.ui_catalogue import compact_skeleton_contract, load_catalogue
from app.infrastructure.templating.renderer import JinjaTemplateRenderer


TEMPLATES_DIR = REPO_ROOT / "backend" / "app" / "templates"


class _CapturingAI:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def ask_chat(self, _model, messages, **_kwargs):
        self.prompts.append(messages[-1]["content"])
        return self.response

    def ask_vision(self, _model, prompt, _image_path):
        self.prompts.append(prompt)
        return self.response


def _planning_contract() -> str:
    skeletons = []
    for skeleton in load_catalogue()["skeletons"]:
        skeletons.append(
            {
                key: skeleton.get(key)
                for key in (
                    "id",
                    "surface",
                    "shell",
                    "purpose",
                    "requiredSections",
                    "optionalSections",
                    "recommendedOrder",
                )
            }
        )
    return json.dumps({"skeletons": skeletons}, ensure_ascii=False)


def _route(surface: str) -> dict:
    if surface == "ops":
        return {
            "path": "/owner",
            "page_id": "owner-dashboard",
            "role_id": "owner",
            "component_file": "src/pages/owner/OwnerDashboardPage.tsx",
            "surface": "ops",
            "skeleton_id": "ops-dashboard",
            "section_slots": ["header", "kpis", "chart", "table", "activity"],
        }
    return {
        "path": "/",
        "page_id": "home",
        "role_id": "customer",
        "component_file": "src/pages/HomePage.tsx",
        "surface": "public",
        "skeleton_id": "public-home",
        "section_slots": ["hero", "features", "showcase", "testimonials", "cta", "footer"],
    }


def _route_contract(route: dict) -> str:
    return json.dumps(
        compact_skeleton_contract(route["skeleton_id"], route["section_slots"]),
        ensure_ascii=False,
    )


def _render_all(renderer: JinjaTemplateRenderer, surface: str) -> dict[str, str]:
    route = _route(surface)
    route_contract = _route_contract(route)
    routes_contract = json.dumps(
        [
            {
                "path": route["path"],
                "component_file": route["component_file"],
                "surface": route["surface"],
                "skeleton_id": route["skeleton_id"],
                "section_slots": route["section_slots"],
                "contract": json.loads(route_contract),
            }
        ],
        ensure_ascii=False,
    )
    common = {
        "full_context": "Copper & Pine is a neighborhood restaurant with reservations and dinner service.",
        "plan_json": json.dumps({"public_direction": "Warm editorial dining", "ops_direction": "Fast service control"}),
        "preview_features": "- reservations\n- service dashboard",
        "mvp_blueprint": "Customers book tables; owners manage covers and service.",
        "catalogue_contract_json": _planning_contract(),
    }
    return {
        "plan": renderer.render(
            PromptTemplate.UI_EXPERIENCE_PLAN,
            **common,
            visual_demo_summary="Seasonal neighborhood dining",
            primary_color="#7c2d12",
            secondary_color="#365314",
            concept_name="Copper & Pine",
            industry="restaurant",
        ),
        "validate": renderer.render(PromptTemplate.PLAN_VALIDATION, **common),
        "expand": renderer.render(
            PromptTemplate.PLAN_EXPANSION,
            **common,
            issues="- owner dashboard lacks a chart",
        ),
        "architect": renderer.render(
            PromptTemplate.PREVIEW_APP_ARCHITECT,
            **common,
            manifest_json="{}",
            images_json="{}",
        ),
        "file": renderer.render(
            PromptTemplate.PREVIEW_APP_FILE,
            full_context=common["full_context"],
            architect_json=json.dumps({"routes": [route]}),
            design_system_json="{}",
            manifest_json="{}",
            images_json="{}",
            file_path=route["component_file"],
            file_kind="page",
            file_instructions="Build the assigned live product page.",
            page_plan_json="{}",
            catalogue_page=True,
            skeleton_id=route["skeleton_id"],
            skeleton_contract_json=route_contract,
            shell_component="OpsShell" if surface == "ops" else "PublicShell",
            existing_files_summary="src/data/mock.ts",
        ),
        "fix": renderer.render(
            PromptTemplate.PREVIEW_APP_FIX,
            build_errors="TypeScript error",
            file_tree=route["component_file"],
            architect_json=json.dumps({"routes": [route]}),
            catalogue_mode=True,
            catalogue_routes_json=routes_contract,
            files_content="export default function Page() { return null }",
        ),
        "refine": renderer.render(
            PromptTemplate.PREVIEW_APP_REFINE,
            full_context=common["full_context"],
            manifest_json="{}",
            images_json="{}",
            file_instructions="Build all assigned sections.",
            critic_notes="Increase density.",
            catalogue_page=True,
            skeleton_id=route["skeleton_id"],
            shell_component="OpsShell" if surface == "ops" else "PublicShell",
            catalogue_contract_json=route_contract,
            file_path=route["component_file"],
            current_content="export default function Page() { return null }",
        ),
        "chat": renderer.render(
            PromptTemplate.PREVIEW_APP_CHAT_REFINEMENT,
            business_context=common["full_context"],
            user_message="Make the page denser.",
            experience_plan_json=common["plan_json"],
            architect_json=json.dumps({"routes": [route]}),
            catalogue_mode=True,
            catalogue_routes_json=routes_contract,
            file_tree=route["component_file"],
            files_content="export default function Page() { return null }",
            app_spec_enforced=False,
            app_spec_ref_json="{}",
            app_spec_contracts_json="{}",
        ),
        "mock": renderer.render(
            PromptTemplate.PREVIEW_APP_MOCK_SYNTHESIZE,
            full_context=common["full_context"],
            plan_json=common["plan_json"],
            routes_json=json.dumps([route]),
            manifest_json="{}",
            images_json="{}",
            required_exports="chartData, reservations, proofResults",
            import_context="ChartCard DataTable BookingPanel ResultRail",
            current_content="export const roles = [];",
        ),
        "critic": renderer.render(
            PromptTemplate.PREVIEW_APP_CRITIC,
            full_context=common["full_context"],
            design_direction="Warm public, efficient operations.",
            file_instructions="Build all assigned sections.",
            file_path=route["component_file"],
            current_content="export default function Page() { return null }",
            catalogue_page=True,
            surface=surface,
            skeleton_id=route["skeleton_id"],
            skeleton_contract_json=route_contract,
        ),
        "visual_critic": renderer.render(
            PromptTemplate.PREVIEW_APP_VISUAL_CRITIC,
            full_context=common["full_context"],
            design_direction="Warm public, efficient operations.",
            file_instructions="Build all assigned sections.",
            file_path=route["component_file"],
            catalogue_page=True,
            surface=surface,
            skeleton_id=route["skeleton_id"],
            skeleton_contract_json=route_contract,
        ),
    }


def test_prompt_render_contracts() -> None:
    renderer = JinjaTemplateRenderer(TEMPLATES_DIR)
    rendered_by_surface = {
        surface: _render_all(renderer, surface) for surface in ("public", "ops")
    }

    for rendered in rendered_by_surface.values():
        for name, prompt in rendered.items():
            assert prompt.strip(), f"{name} rendered empty"

        for stage in ("plan", "validate", "expand"):
            prompt = rendered[stage]
            assert "requiredSections" in prompt and "optionalSections" in prompt
            assert "public_direction" in prompt and "ops_direction" in prompt
            assert "only" in prompt.lower() and "shell" in prompt.lower()

        architect = rendered["architect"]
        assert "template-owned" in architect.lower() and "immutable" in architect.lower()
        assert '"surface"' in architect and '"skeleton_id"' in architect
        for legacy in ("Nav", "PublicLayout", "AdminLayout", "UiIcons"):
            assert f"generate {legacy}".lower() not in architect.lower()
        for assembler_owned in ("src/data/mock.ts", "src/App.tsx", "src/index.css"):
            assert assembler_owned not in architect

        page = rendered["file"]
        for invariant in ("@/ui", "SkeletonComposer", "page owns its chrome", "section_slots"):
            assert invariant.lower() in page.lower()
        assert "direct package" in page.lower()
        assert "emoji" in page.lower() and "hardcode hex" in page.lower()

        for stage in ("fix", "refine", "chat"):
            prompt = rendered[stage].lower()
            for invariant in ("@/ui", "skeleton", "slot", "template-owned"):
                assert invariant in prompt
            assert "publiclayout" in prompt and "adminlayout" in prompt
            assert "keep the same imports/exports contract" not in prompt
            assert "build only the sections described in the page plan" not in prompt
            assert "preserve invalid legacy imports" not in prompt
        refine = rendered["refine"].lower()
        assert "assigned skeleton" in refine
        assert "assigned section slot" in refine
        assert "replace invalid legacy imports" in refine

        mock = rendered["mock"]
        for shape in ("ChartCard", "DataTable", "BookingPanel", "ResultRail"):
            assert shape in mock

        critic = rendered["critic"].lower()
        assert "under 88" in critic
        visual = rendered["visual_critic"].lower()
        assert "under 80" in visual
        for failure in (
            "missing skeleton",
            "missing assigned slot",
            "non-@/ui",
            "duplicate chrome",
            "emoji",
            "flat public home",
            "kpis",
            "chart",
            "table",
            "placeholder",
            "hardcoded color",
            "wrong surface",
        ):
            assert failure in critic
            assert failure in visual


def test_prompt_call_sites_supply_compact_contracts() -> None:
    page_experience = (
        REPO_ROOT / "backend" / "app" / "application" / "services" / "page_experience.py"
    ).read_text(encoding="utf-8")
    # Package split: former monolith codegen.py lives under codegen/
    generate = (
        REPO_ROOT
        / "backend"
        / "app"
        / "application"
        / "preview_app"
        / "codegen"
        / "generate.py"
    ).read_text(encoding="utf-8")
    architect = (
        REPO_ROOT
        / "backend"
        / "app"
        / "application"
        / "preview_app"
        / "codegen"
        / "architect.py"
    ).read_text(encoding="utf-8")

    assert page_experience.count("catalogue_contract_json=") >= 3
    assert "compact_catalogue_plan_contract" in page_experience
    assert "catalogue_contract_json=" in generate or "catalogue_contract_json=" in architect
    assert "skeleton_contract_json=" in generate
    critic = (
        REPO_ROOT
        / "backend"
        / "app"
        / "application"
        / "preview_app"
        / "codegen"
        / "critic.py"
    ).read_text(encoding="utf-8")
    assert 'surface=route.get("surface")' in critic


def test_compact_contract_includes_shell_and_navigation_metadata() -> None:
    public = compact_skeleton_contract(
        "public-home",
        ["hero", "features", "showcase", "process", "testimonials", "cta", "footer"],
    )
    ops = compact_skeleton_contract(
        "ops-dashboard",
        ["header", "kpis", "chart", "filters", "table", "activity"],
    )

    public_components = {item["name"]: item for item in public["components"]}
    assert public["shell_component"] == "PublicShell"
    assert {"brandName", "children"} <= set(public_components["PublicShell"]["requiredProps"])
    assert "nav" in public_components["PublicShell"]["optionalProps"]
    assert public["navigation_components"] == ["PublicNav"]
    assert "items" in public_components["PublicNav"]["requiredProps"]

    ops_components = {item["name"]: item for item in ops["components"]}
    assert ops["shell_component"] == "OpsShell"
    assert {"brandName", "navItems", "children"} <= set(
        ops_components["OpsShell"]["requiredProps"]
    )
    assert ops["navigation_components"] == []

    assert len(json.dumps(public, separators=(",", ":"))) < 10000
    assert len(json.dumps(ops, separators=(",", ":"))) < 10000
    for contract, shell in ((public, "PublicShell"), (ops, "OpsShell")):
        bounded = _text_bounded_json(contract, 5000)
        assert len(bounded) <= 5000
        bounded_contract = json.loads(bounded)
        assert bounded_contract["shell_component"] == shell
        assert any(item["name"] == shell for item in bounded_contract["components"])


def test_fallback_file_worklist_excludes_pipeline_owned_files() -> None:
    files = _arch_norm._files_from_plan(
        {
            "routes": [_route("public"), _route("ops")],
            "shared_components": [],
        }
    )
    assert {(item["path"], item["kind"]) for item in files} == {
        ("src/pages/HomePage.tsx", "page"),
        ("src/pages/owner/OwnerDashboardPage.tsx", "page"),
    }


def test_critic_results_fail_closed() -> None:
    normalize = getattr(codegen, "_normalize_critic_result", None)
    assert callable(normalize), "critic result normalizer is required"

    for raw in (None, {}, [], {"score": 99}, {"verdict": "pass"}):
        result = normalize(raw, threshold=88)
        assert result["verdict"] == "unavailable"
        assert result["score"] is None
        assert result["preserve"] is True
        assert result["issues"]

    low_pass = normalize(
        {"score": 40, "verdict": "pass", "issues": [], "revision_instructions": ""},
        threshold=88,
    )
    assert low_pass["verdict"] == "revise"
    assert low_pass["score"] == 40

    high_revise = normalize(
        {
            "score": 95,
            "verdict": "revise",
            "issues": ["Duplicate chrome"],
            "revision_instructions": "Remove the duplicate header.",
        },
        threshold=88,
    )
    assert high_revise["verdict"] == "revise"
    assert high_revise["score"] == 87

    valid_pass = normalize(
        {"score": 92, "verdict": "pass", "issues": [], "revision_instructions": ""},
        threshold=88,
    )
    assert valid_pass == {
        "score": 92,
        "verdict": "pass",
        "issues": [],
        "revision_instructions": "",
    }


def test_production_callsites_render_with_strict_undefined() -> None:
    renderer = JinjaTemplateRenderer(TEMPLATES_DIR)
    request = SimpleNamespace(
        business_name="Copper & Pine",
        concept_name="Copper & Pine",
        industry="restaurant",
        business_description="Neighborhood dining and reservations.",
        target_customers="Local diners",
        main_problem="Busy service coordination",
        desired_outcome="Smooth bookings and dinner service",
        what_you_like="Warm editorial design",
        reference_url=None,
        needs_ai=False,
        preview_summary="Reservation and service tools",
        mvp_blueprint="Customers reserve; owners manage service.",
        preview_features=json.dumps(["Reservations", "Service dashboard"]),
        screenshot_analysis=None,
        reference_metadata=None,
    )
    plan_response = json.dumps(
        {
            "design_system": {},
            "public_direction": "Warm neighborhood dining storefront.",
            "ops_direction": "Dense dinner-service control room.",
            "roles": [
                {
                    "id": "customer",
                    "label": "Guest",
                    "pages": [
                        {
                            "id": "home",
                            "title": "Home",
                            "surface": "public",
                            "skeleton_id": "public-home",
                            "section_slots": [
                                "hero",
                                "features",
                                "showcase",
                                "process",
                                "testimonials",
                                "cta",
                                "footer",
                            ],
                        }
                    ],
                }
            ],
        }
    )
    planner_ai = _CapturingAI(plan_response)
    planned = page_experience._call_planner(
        request,
        {},
        "#7c2d12",
        "#365314",
        "test-model",
        planner_ai,
        renderer,
    )
    assert planned and planner_ai.prompts
    validation_ai = _CapturingAI(plan_response)
    validated = page_experience.validate_and_expand_plan(
        request,
        planned,
        validation_ai,
        renderer,
        {},
    )
    assert validated and validation_ai.prompts
    expansion_ai = _CapturingAI(plan_response)
    expanded = page_experience._expand_plan(
        request,
        {},
        planned,
        ["owner dashboard lacks chart data"],
        "#7c2d12",
        "#365314",
        expansion_ai,
        renderer,
    )
    assert expanded and len(expansion_ai.prompts) >= 2

    architect_response = json.dumps(
        {
            "app_name": "copper-pine",
            "roles": [{"id": "customer", "label": "Guest", "defaultPath": "/"}],
            "routes": [_route("public")],
            "files_to_generate": [
                {
                    "path": "src/pages/HomePage.tsx",
                    "kind": "page",
                    "instructions": "Build the planned home page.",
                }
            ],
        }
    )
    architect_ai = _CapturingAI(architect_response)
    architect = codegen.call_architect(
        "restaurant context",
        planned,
        {},
        {},
        architect_ai,
        renderer,
    )
    assert architect["routes"] and architect_ai.prompts

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        for surface in ("public", "ops"):
            route = _route(surface)
            page_path = workspace / route["component_file"]
            page_path.parent.mkdir(parents=True, exist_ok=True)
            scaffold = minimal_catalogue_page_scaffold(
                route["component_file"],
                route,
                brand_name="Copper & Pine",
            )
            page_path.write_text(scaffold, encoding="utf-8")
            route_architect = {"routes": [route]}

            page_ai = _CapturingAI(scaffold)
            codegen.generate_file(
                workspace,
                {
                    "path": route["component_file"],
                    "kind": "page",
                    "instructions": "Build every assigned section.",
                },
                "restaurant context",
                route_architect,
                {
                    "roles": [
                        {
                            "id": route["role_id"],
                            "pages": [
                                {
                                    "id": route["page_id"],
                                    "surface": route["surface"],
                                    "skeleton_id": route["skeleton_id"],
                                    "section_slots": route["section_slots"],
                                }
                            ],
                        }
                    ]
                },
                {},
                {},
                page_ai,
                renderer,
            )
            assert page_ai.prompts

            pass_json = json.dumps(
                {
                    "score": 92,
                    "verdict": "pass",
                    "issues": [],
                    "revision_instructions": "",
                }
            )
            text_ai = _CapturingAI(pass_json)
            scaffold_review = codegen.critique_file(
                workspace,
                route["component_file"],
                "Build every assigned section.",
                "restaurant context",
                "Warm public, efficient ops",
                text_ai,
                renderer,
                route_architect,
            )
            # Scaffold-first pages are intentionally locked — critic must not thrash refine.
            assert scaffold_review["verdict"] == "ok"
            assert "scaffold" in scaffold_review["issues"][0].lower()
            visual_ai = _CapturingAI(pass_json)
            assert codegen.critique_file_visual(
                workspace,
                route["component_file"],
                str(workspace / "unused.png"),
                "Build every assigned section.",
                "restaurant context",
                "Warm public, efficient ops",
                visual_ai,
                renderer,
                route_architect,
            )["verdict"] == "ok"

            # Scaffold pages short-circuit before AI critic parsing — locked as ok.
            malformed_ai = _CapturingAI("not JSON")
            malformed = codegen.critique_file(
                workspace,
                route["component_file"],
                "Build every assigned section.",
                "restaurant context",
                "Warm public, efficient ops",
                malformed_ai,
                renderer,
                route_architect,
            )
            assert malformed["verdict"] == "ok"
            assert malformed_ai.prompts == []

            inconsistent_ai = _CapturingAI(
                json.dumps(
                    {
                        "score": 20,
                        "verdict": "pass",
                        "issues": [],
                        "revision_instructions": "",
                    }
                )
            )
            inconsistent = codegen.critique_file_visual(
                workspace,
                route["component_file"],
                str(workspace / "unused.png"),
                "Build every assigned section.",
                "restaurant context",
                "Warm public, efficient ops",
                inconsistent_ai,
                renderer,
                route_architect,
            )
            assert inconsistent["verdict"] == "ok"
            assert inconsistent_ai.prompts == []

            refine_ai = _CapturingAI(scaffold)
            codegen.refine_file(
                workspace,
                route["component_file"],
                "Build every assigned section.",
                "Increase realistic density.",
                "restaurant context",
                {},
                {},
                refine_ai,
                renderer,
                route_architect,
            )
            assert refine_ai.prompts

        fix_ai = _CapturingAI('{"files":[]}')
        codegen.fix_build_errors(
            workspace,
            "TypeScript compile error",
            {"routes": [_route("public"), _route("ops")]},
            fix_ai,
            renderer,
        )
        assert fix_ai.prompts

        data_page = workspace / "src" / "pages" / "DataPage.tsx"
        data_page.write_text(
            "import { reservations } from '@/data/mock';\n"
            "export default function DataPage() { return <div>{reservations.length}</div>; }\n",
            encoding="utf-8",
        )
        mock_path = workspace / "src" / "data" / "mock.ts"
        mock_path.parent.mkdir(parents=True, exist_ok=True)
        mock_path.write_text("export const roles = [];\n", encoding="utf-8")
        mock_ai = _CapturingAI(
            "export const reservations = [];\n"
            "export const images = { hero: '', card1: '', card2: '', card3: '' };\n"
        )
        assert codegen.synthesize_mock_data(
            workspace,
            "restaurant context",
            planned,
            {},
            {},
            {"routes": [_route("public"), _route("ops")]},
            mock_ai,
            renderer,
        )
        assert mock_ai.prompts


if __name__ == "__main__":
    test_prompt_render_contracts()
    test_prompt_call_sites_supply_compact_contracts()
    test_compact_contract_includes_shell_and_navigation_metadata()
    test_fallback_file_worklist_excludes_pipeline_owned_files()
    test_critic_results_fail_closed()
    test_production_callsites_render_with_strict_undefined()
    print("task4 prompt contract tests passed")
