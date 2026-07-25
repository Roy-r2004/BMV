"""Focused tests for Tier 1 business-component usage contract (#25 class)."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from app.application.candidate_generation.cache import sha256_text
from app.application.candidate_generation.component_registry import (
    bindings_prompt_block,
    build_business_component_registry,
    build_required_business_component_bindings,
)
from app.application.candidate_generation.deterministic import (
    component_export_symbol,
    page_export_symbol,
)
from app.application.candidate_generation.page_skeleton import (
    BMV_REQUIRED_BC_END,
    BMV_REQUIRED_BC_START,
    build_page_skeleton_source,
    ensure_protected_business_component_region,
)
from app.application.candidate_generation.service import (
    build_v2_candidate_revision,
)
from app.application.candidate_generation.usage_validation import (
    heal_missing_business_component_usage,
    validate_binding_against_source,
    validate_business_component_usage,
)
from app.core.config import settings
from app.domain.schemas.business_component_usage import (
    RequiredBusinessComponentBinding,
)
from app.domain.schemas.preview_candidate import (
    GeneratedCandidateBatch,
    GeneratedCandidateFile,
)
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.candidate_generation.helpers import (
    CandidateFixtureAI,
    component_batch_payload,
    prepare_phase3a,
)


PLAN_HASH = "a" * 64


@pytest.fixture
def isolated_candidate_paths(monkeypatch):
    root = (
        Path(__file__).resolve().parent
        / ".runtime"
        / uuid.uuid4().hex
    )
    candidates = root / "candidates"
    accepted = root / "accepted"
    monkeypatch.setattr(settings, "PREVIEW_CANDIDATES_DIR", candidates)
    monkeypatch.setattr(settings, "PREVIEW_APPS_DIR", accepted)
    yield root
    if root.exists():
        shutil.rmtree(root)


def _binding(
    *,
    page_id: str = "PAGE-HOME",
    component_id: str = "COMP-HOME",
    required_props: tuple[str, ...] = (),
) -> RequiredBusinessComponentBinding:
    symbol = component_export_symbol(component_id)
    return RequiredBusinessComponentBinding(
        page_id=page_id,
        business_component_id=component_id,
        component_symbol=symbol,
        component_module_path=f"src/components/business/{symbol}.tsx",
        required_usage_count=1,
        required_props=required_props,
        action_ids=("ACTION-1",),
        state_ids=("STATE-1",),
        evidence_ids=("EVIDENCE-1",),
        source_plan_revision="1.0",
        source_plan_hash=PLAN_HASH,
    )


def _valid_page_source(binding: RequiredBusinessComponentBinding) -> str:
    symbol = page_export_symbol(binding.page_id)
    rel = "../components/business/" + binding.component_symbol
    return (
        f'import {{ {binding.component_symbol} }} from "{rel}";\n\n'
        f"export function {symbol}() {{\n"
        "  return (\n"
        f'    <main data-bmv-page-id="{binding.page_id}">\n'
        f"      <{binding.component_symbol} />\n"
        "    </main>\n"
        "  );\n"
        "}\n"
    )


def test_component_file_alone_is_insufficient() -> None:
    binding = _binding()
    item = validate_binding_against_source(
        source=(
            f'export function {page_export_symbol(binding.page_id)}() {{\n'
            f'  return <main data-bmv-page-id="{binding.page_id}" />;\n'
            "}\n"
        ),
        binding=binding,
        component_file_exists=True,
    )
    assert item.result == "missing_import"
    assert item.component_file_exists is True
    assert item.mount_found is False


def test_metadata_reference_alone_is_insufficient() -> None:
    binding = _binding()
    item = validate_binding_against_source(
        source=(
            f'export function {page_export_symbol(binding.page_id)}() {{\n'
            "  return (\n"
            f'    <main data-bmv-page-id="{binding.page_id}" '
            f'data-bmv-component-ref="{binding.business_component_id}" />\n'
            "  );\n"
            "}\n"
        ),
        binding=binding,
        component_file_exists=True,
    )
    assert item.result == "missing_import"


def test_missing_import_and_mount_and_wrong_symbol_detected() -> None:
    binding = _binding()
    source = _valid_page_source(binding).replace(
        binding.component_symbol, "WrongSymbol"
    )
    item = validate_binding_against_source(
        source=source,
        binding=binding,
        component_file_exists=True,
    )
    assert item.result == "missing_import"

    mounted_without_import = (
        f'export function {page_export_symbol(binding.page_id)}() {{\n'
        "  return (\n"
        f'    <main data-bmv-page-id="{binding.page_id}">\n'
        f"      <{binding.component_symbol} />\n"
        "    </main>\n"
        "  );\n"
        "}\n"
    )
    item = validate_binding_against_source(
        source=mounted_without_import,
        binding=binding,
        component_file_exists=True,
    )
    assert item.result == "missing_import"

    imported_without_mount = (
        f'import {{ {binding.component_symbol} }} from '
        f'"../components/business/{binding.component_symbol}";\n'
        f'export function {page_export_symbol(binding.page_id)}() {{\n'
        f'  return <main data-bmv-page-id="{binding.page_id}" />;\n'
        "}\n"
    )
    item = validate_binding_against_source(
        source=imported_without_mount,
        binding=binding,
        component_file_exists=True,
    )
    assert item.result == "missing_mount"


def test_wrong_module_path_and_missing_props_detected() -> None:
    binding = _binding(required_props=("services",))
    source = (
        f'import {{ {binding.component_symbol} }} from '
        f'"../components/business/OtherThing";\n'
        f'export function {page_export_symbol(binding.page_id)}() {{\n'
        "  return (\n"
        f'    <main data-bmv-page-id="{binding.page_id}">\n'
        f"      <{binding.component_symbol} />\n"
        "    </main>\n"
        "  );\n"
        "}\n"
    )
    item = validate_binding_against_source(
        source=source,
        binding=binding,
        component_file_exists=True,
    )
    assert item.result == "missing_import"

    source = _valid_page_source(binding).replace(
        f"<{binding.component_symbol} />",
        f"<{binding.component_symbol} />",
    )
    item = validate_binding_against_source(
        source=source,
        binding=binding,
        component_file_exists=True,
    )
    assert item.result == "missing_props"


def test_deterministic_skeleton_includes_required_mounts() -> None:
    prepared = prepare_phase3a(request_id=2501, page_count=4)
    try:
        from app.application.candidate_generation.context import (
            load_candidate_context,
        )

        context = load_candidate_context(
            prepared.db,
            request_id=prepared.req.id,
            phase3a_result=prepared.phase3a_result,
        )
        component_payload = component_batch_payload(
            {
                "business_component_plan": context.business_components.model_dump(
                    mode="json"
                ),
                "interaction_contract": context.interactions.model_dump(
                    mode="json"
                ),
                "page_purpose_contract": context.page_purpose.model_dump(
                    mode="json"
                ),
            }
        )
        batch = GeneratedCandidateBatch.model_validate(component_payload)
        registry, issues = build_business_component_registry(
            context=context,
            component_batch=batch,
        )
        assert not issues and registry is not None
        bindings, binding_issues = build_required_business_component_bindings(
            context=context,
            registry=registry,
        )
        assert not binding_issues
        page = context.page_purpose.pages[0]
        page_bindings = tuple(
            item for item in bindings if item.page_id == page.page_id
        )
        skeleton = build_page_skeleton_source(
            page=page,
            bindings=page_bindings,
        )
        assert BMV_REQUIRED_BC_START in skeleton
        assert BMV_REQUIRED_BC_END in skeleton
        for binding in page_bindings:
            assert binding.component_symbol in skeleton
            assert f"<{binding.component_symbol}" in skeleton
        block = bindings_prompt_block(bindings)
        assert page.page_id in block
        assert block[page.page_id][0]["must_mount"] is True
    finally:
        prepared.db.close()


def test_model_cannot_remove_protected_required_mounts() -> None:
    binding = _binding()
    skeleton = (
        f'import {{ {binding.component_symbol} }} from '
        f'"../components/business/{binding.component_symbol}";\n'
        f"export function {page_export_symbol(binding.page_id)}() {{\n"
        "  return (\n"
        f'    <main data-bmv-page-id="{binding.page_id}">\n'
        f"      {BMV_REQUIRED_BC_START}\n"
        f"      <{binding.component_symbol} />\n"
        f"      {BMV_REQUIRED_BC_END}\n"
        "    </main>\n"
        "  );\n"
        "}\n"
    )
    stripped = skeleton.replace(
        f"      {BMV_REQUIRED_BC_START}\n"
        f"      <{binding.component_symbol} />\n"
        f"      {BMV_REQUIRED_BC_END}\n",
        "      <div>generic</div>\n",
    )
    restored = ensure_protected_business_component_region(
        source=stripped,
        bindings=(binding,),
    )
    assert f"<{binding.component_symbol}" in restored
    assert BMV_REQUIRED_BC_START in restored


def test_bounded_heal_inserts_import_and_mount_once() -> None:
    binding = _binding()
    generic = (
        f"export function {page_export_symbol(binding.page_id)}() {{\n"
        "  return (\n"
        f'    <main data-bmv-page-id="{binding.page_id}">\n'
        "      <section>generic primitives only</section>\n"
        "    </main>\n"
        "  );\n"
        "}\n"
    )
    batch = GeneratedCandidateBatch(
        batch_kind="pages",
        files=(
            GeneratedCandidateFile(
                path=f"src/pages/{page_export_symbol(binding.page_id)}.tsx",
                file_kind="page",
                owner_contract_ids=(binding.page_id,),
                source=generic,
            ),
        ),
    )
    evidence, issues = validate_business_component_usage(
        batch=batch,
        bindings=(binding,),
        component_paths={binding.component_module_path},
    )
    assert issues
    assert evidence[0].result in {"missing_import", "missing_mount"}
    healed, before, used = heal_missing_business_component_usage(
        batch=batch,
        bindings=(binding,),
        evidence=evidence,
    )
    assert used is True
    assert before
    evidence2, issues2 = validate_business_component_usage(
        batch=healed,
        bindings=(binding,),
        component_paths={binding.component_module_path},
        repair_attempt=1,
        previous_hashes=before,
    )
    assert not issues2
    assert evidence2[0].result == "satisfied"
    # Second heal is a no-op.
    healed2, _before2, used2 = heal_missing_business_component_usage(
        batch=healed,
        bindings=(binding,),
        evidence=evidence2,
    )
    assert used2 is False
    assert healed2.files[0].source == healed.files[0].source


def test_ambiguous_and_missing_wiring_fail_closed() -> None:
    binding = _binding(required_props=("services",))
    batch = GeneratedCandidateBatch(
        batch_kind="pages",
        files=(
            GeneratedCandidateFile(
                path="src/pages/PageHomePage.tsx",
                file_kind="page",
                owner_contract_ids=("PAGE-HOME", "PAGE-OTHER"),
                source=_valid_page_source(binding),
            ),
        ),
    )
    evidence, _issues = validate_business_component_usage(
        batch=batch,
        bindings=(binding,),
        component_paths={binding.component_module_path},
    )
    healed, _before, used = heal_missing_business_component_usage(
        batch=batch,
        bindings=(binding,),
        evidence=evidence,
    )
    # Valid usage already present; heal should not invent props.
    assert used is False
    item = validate_binding_against_source(
        source=healed.files[0].source,
        binding=binding,
        component_file_exists=True,
    )
    assert item.result == "missing_props"


def test_valid_usage_is_byte_stable() -> None:
    binding = _binding()
    source = _valid_page_source(binding)
    before = sha256_text(source)
    restored = ensure_protected_business_component_region(
        source=source,
        bindings=(binding,),
    )
    # Existing valid mounts without markers stay unchanged.
    assert sha256_text(restored) == before


def test_request_25_class_fixture_heals_to_build_pending(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=2525, page_count=4)
    ai = CandidateFixtureAI()

    def strip_business_component_usage(payload):
        for item in payload["files"]:
            page_id = item["owner_contract_ids"][0]
            symbol = page_export_symbol(page_id)
            # Recreate #25: generic page primitives, no business mounts.
            item["source"] = (
                'import { contentDataPlan } from "../generated/content-data";\n\n'
                f"export function {symbol}() {{\n"
                "  return (\n"
                f'    <main data-bmv-page-id="{page_id}"\n'
                '      data-bmv-mobile-navigation="stack"\n'
                '      data-bmv-mobile-primary-action="book"\n'
                '      data-bmv-mobile-data-presentation="cards"\n'
                '      data-bmv-mobile-density="comfortable"\n'
                "    >\n"
                '      <span data-bmv-acceptance-test-id="AT-PLACEHOLDER" hidden />\n'
                "      <section><h1>Welcome</h1><button>Go</button></section>\n"
                "      <small>{contentDataPlan.schema_version}</small>\n"
                "    </main>\n"
                "  );\n"
                "}\n"
            )
        return payload

    ai.stage_mutators["pages"] = [strip_business_component_usage]
    try:
        # Replace acceptance placeholder with real IDs after first prompt parse
        # by wrapping factory through mutator that uses last inputs.
        original = strip_business_component_usage

        def strip_with_real_acceptance(payload):
            payload = original(payload)
            pages = ai.last_inputs["pages"]["page_purpose_contract"]["pages"]
            mobile_by_page = {page["page_id"]: page["mobile"] for page in pages}
            tests_by_page = {
                page["page_id"]: page["acceptance_test_ids"] for page in pages
            }
            for item in payload["files"]:
                page_id = item["owner_contract_ids"][0]
                mobile = mobile_by_page[page_id]
                tests = "\n".join(
                    f'      <span data-bmv-acceptance-test-id="{test_id}" hidden />'
                    for test_id in tests_by_page[page_id]
                )
                symbol = page_export_symbol(page_id)
                item["source"] = (
                    'import { contentDataPlan } from "../generated/content-data";\n\n'
                    f"export function {symbol}() {{\n"
                    "  return (\n"
                    f'    <main data-bmv-page-id="{page_id}"\n'
                    f'      data-bmv-mobile-navigation="{mobile["navigation"]}"\n'
                    f'      data-bmv-mobile-primary-action="{mobile["primary_action"]}"\n'
                    f'      data-bmv-mobile-data-presentation="{mobile["data_presentation"]}"\n'
                    f'      data-bmv-mobile-density="{mobile["density_adjustment"]}"\n'
                    "    >\n"
                    f"{tests}\n"
                    "      <section><h1>Welcome</h1><button>Go</button></section>\n"
                    "      <small>{contentDataPlan.schema_version}</small>\n"
                    "    </main>\n"
                    "  );\n"
                    "}\n"
                )
            return payload

        ai.stage_mutators["pages"] = [strip_with_real_acceptance]
        result = build_v2_candidate_revision(
            prepared.db,
            prepared.req.id,
            ai,
            JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            req=prepared.req,
            phase3a_result=prepared.phase3a_result,
        )
        preview = result["preview_contract"]
        assert preview["status"] == "candidate_build_pending"
        evidence = preview["business_component_usage_evidence"]
        assert evidence["deterministic_heal_used"] is True
        assert all(item["result"] == "satisfied" for item in evidence["items"])
        assert "pages_repair" not in [call[0] for call in ai.calls]
        # Prompt included explicit binding block.
        assert "required_business_component_bindings" in ai.last_inputs["pages"]
        assert "page_skeletons" in ai.last_inputs["pages"]
    finally:
        prepared.db.close()


def test_no_generic_substitute_invented_on_missing_file() -> None:
    binding = _binding()
    item = validate_binding_against_source(
        source=_valid_page_source(binding),
        binding=binding,
        component_file_exists=False,
    )
    assert item.result == "missing_file"
    batch = GeneratedCandidateBatch(
        batch_kind="pages",
        files=(
            GeneratedCandidateFile(
                path="src/pages/PageHomePage.tsx",
                file_kind="page",
                owner_contract_ids=(binding.page_id,),
                source=(
                    f"export function {page_export_symbol(binding.page_id)}()"
                    " { return <main />;\n}\n"
                ),
            ),
        ),
    )
    evidence, _issues = validate_business_component_usage(
        batch=batch,
        bindings=(binding,),
        component_paths=set(),
    )
    healed, _before, used = heal_missing_business_component_usage(
        batch=batch,
        bindings=(binding,),
        evidence=evidence,
    )
    assert used is False
    assert "Generic" not in healed.files[0].source
    assert "Substitute" not in healed.files[0].source
