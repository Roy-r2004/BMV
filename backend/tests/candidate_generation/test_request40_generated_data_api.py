"""Request 40: generated-data API contract and strict TypeScript handoff.

Production request #40 reached `candidate_build_pending`'s validation gate and
failed with 13 `typescript_no_emit` diagnostics: three components imported
`getServiceSeedData` from `@/generated/content-data`, which exported no such
member, and every implicit-`any` parameter cascaded from that error-typed
import.

This suite reproduces the full pre-fix diagnostic set against the real
TypeScript gate, then proves the canonical generated-data API removes it.
"""
from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from types import SimpleNamespace
from urllib.request import urlopen
from pathlib import Path

import pytest

from app.application.candidate_generation.content_data_identifiers import (
    collection_seed_records,
    identifier_words,
    pluralize,
    upper_camel,
)
from app.application.candidate_generation.context import (
    load_candidate_context,
)
from app.application.candidate_generation.service import (
    build_v2_candidate_revision,
)
from app.application.candidate_generation.builder import repair_ai_batch
from app.application.candidate_generation.deterministic import (
    build_content_data_module,
    build_data_sources,
    build_foundation_sources,
    generated_data_api_manifest,
)
from app.application.candidate_generation.generated_data_api import (
    build_generated_data_api_manifest,
    exported_symbols,
    heal_generated_data_symbols,
    heal_generated_data_record_shapes,
    manifest_prompt_projection,
    normalize_generated_candidate_types,
    resolve_invented_symbol,
    validate_generated_data_literals,
    validate_generated_data_imports,
)
from app.application.candidate_generation.validation import (
    heal_invented_generated_data_imports,
    heal_generated_data_record_shapes_in_batch,
)
from app.core.config import settings
from app.domain.schemas.generated_data_api import (
    GENERATED_DATA_API_MODULE_SPECIFIER,
    GENERATED_DATA_API_POLICY_REVISION,
    GeneratedDataApiManifest,
)
from app.domain.schemas.preview_candidate import (
    CandidateValidationIssue,
    GeneratedCandidateBatch,
    GeneratedCandidateFile,
)
from app.application.candidate_generation.policy import repair_policy
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from app.application.prompts import PromptTemplate
from tests.candidate_generation.helpers import (
    CandidateFixtureAI,
    prepare_phase3a,
)
from tests.candidate_generation.request40_fixture import (
    APP_STUB,
    CANONICAL_API_COMPONENTS,
    REQUEST_40_COMPONENTS,
    REQUEST_40_EXPECTED_DIAGNOSTICS,
    legacy_content_data_module,
    request40_context,
)


def test_seed_records_force_declared_alias_to_canonical_value() -> None:
    collection = SimpleNamespace(
        entity_id="customer",
        seed_records=(
            SimpleNamespace(
                values=(
                    SimpleNamespace(field_id="customer_id", value="canonical-id"),
                    SimpleNamespace(field_id="id", value="stale-id"),
                )
            ),
        ),
    )

    assert collection_seed_records(collection) == [
        {"customerId": "canonical-id", "id": "canonical-id"}
    ]


@pytest.fixture
def isolated_candidate_paths(monkeypatch):
    root = Path(__file__).resolve().parent / ".runtime" / uuid.uuid4().hex
    monkeypatch.setattr(
        settings,
        "PREVIEW_CANDIDATES_DIR",
        root / "candidates",
    )
    monkeypatch.setattr(settings, "PREVIEW_APPS_DIR", root / "accepted")
    yield root
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


_MISSING_EXPORT_RE = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+):(?P<col>\d+) "
    r"Module '\"(?P<module>[^\"]+)\"' has no exported member "
    r"'(?P<symbol>[^']+)'\."
)
_IMPLICIT_ANY_RE = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+):(?P<col>\d+) "
    r"Parameter '(?P<symbol>[^']+)' implicitly has an 'any' type\."
)


def _classify(diagnostics: list[str]) -> list[tuple[str, int, str, str]]:
    """Reduce raw gate diagnostics to (path, line, class, symbol) tuples."""

    classified: list[tuple[str, int, str, str]] = []
    for item in diagnostics:
        missing = _MISSING_EXPORT_RE.match(item)
        if missing is not None:
            assert missing.group("module") == GENERATED_DATA_API_MODULE_SPECIFIER
            classified.append(
                (
                    missing.group("path"),
                    int(missing.group("line")),
                    "missing_export",
                    missing.group("symbol"),
                )
            )
            continue
        implicit = _IMPLICIT_ANY_RE.match(item)
        if implicit is not None:
            classified.append(
                (
                    implicit.group("path"),
                    int(implicit.group("line")),
                    "implicit_any",
                    implicit.group("symbol"),
                )
            )
            continue
        classified.append((item.split(":", 1)[0], 0, "other", item))
    return classified


def _typescript_gate(workspace: Path) -> list[str]:
    """Run the exact deterministic pre-build TypeScript no-emit gate."""

    node = shutil.which("node")
    typescript = (
        settings.PREVIEW_TEMPLATE_DIR
        / "node_modules"
        / "typescript"
        / "lib"
        / "typescript.js"
    )
    if not node or not typescript.is_file():
        pytest.skip("Checked-in TypeScript compiler runtime is unavailable.")
    script = (
        Path(
            "app/application/candidate_generation/typescript/"
            "validate_candidate.mjs"
        )
        .resolve()
    )
    result = subprocess.run(
        [node, str(script), str(workspace), str(typescript)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    payload = json.loads(result.stdout or "{}")
    assert not result.stderr, result.stderr
    return list(payload.get("diagnostics") or [])


def _vite_build(workspace: Path) -> None:
    node = shutil.which("node")
    vite = settings.PREVIEW_TEMPLATE_DIR / "node_modules/vite/bin/vite.js"
    if not node or not vite.is_file():
        pytest.skip("Checked-in Vite runtime is unavailable.")
    result = subprocess.run(
        [node, str(vite), "build"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _assert_preview_routes(workspace: Path, routes: tuple[str, ...]) -> None:
    node = shutil.which("node")
    vite = settings.PREVIEW_TEMPLATE_DIR / "node_modules/vite/bin/vite.js"
    if not node or not vite.is_file():
        pytest.skip("Checked-in Vite runtime is unavailable.")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = subprocess.Popen(
        [node, str(vite), "--host", "127.0.0.1", "--port", str(port)],
        cwd=workspace,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                with urlopen(f"http://127.0.0.1:{port}/", timeout=1) as response:
                    assert response.status == 200
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    stdout, stderr = server.communicate(timeout=5)
                    pytest.fail(
                        f"Vite preview server did not start:\n{stdout}\n{stderr}"
                    )
                time.sleep(0.1)
        for route in routes:
            with urlopen(
                f"http://127.0.0.1:{port}{route}",
                timeout=5,
            ) as response:
                assert response.status == 200
                assert b'id="root"' in response.read()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)


def _materialize(
    root: Path,
    *,
    content_data_module: str,
    components: dict[str, str],
) -> Path:
    """Reconstruct a request #40 shaped candidate workspace on disk."""

    workspace = root / "staging"
    for item in build_foundation_sources(settings.PREVIEW_TEMPLATE_DIR):
        target = workspace / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.source, encoding="utf-8")
    (workspace / "src" / "App.tsx").write_text(APP_STUB, encoding="utf-8")
    generated = workspace / "src" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / "content-data.ts").write_text(
        content_data_module,
        encoding="utf-8",
    )
    for path, source in components.items():
        target = workspace / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    return workspace


def test_request40_before_pre_fix_module_reproduces_thirteen_diagnostics(
    tmp_path,
) -> None:
    context = request40_context()
    post_fix, _manifest = build_content_data_module(context)
    pre_fix = legacy_content_data_module(post_fix)
    assert "getServiceSeedData" not in pre_fix

    workspace = _materialize(
        tmp_path,
        content_data_module=pre_fix,
        components=REQUEST_40_COMPONENTS,
    )
    diagnostics = _typescript_gate(workspace)

    assert len(diagnostics) == 13
    assert _classify(diagnostics) == list(REQUEST_40_EXPECTED_DIAGNOSTICS)
    missing = [item for item in _classify(diagnostics) if item[2] == "missing_export"]
    implicit = [item for item in _classify(diagnostics) if item[2] == "implicit_any"]
    assert len(missing) == 3
    assert len(implicit) == 10
    assert {item[3] for item in missing} == {"getServiceSeedData"}


def test_request40_after_canonical_api_clears_the_typescript_gate(
    tmp_path,
) -> None:
    context = request40_context()
    post_fix, manifest = build_content_data_module(context)
    assert manifest.api_policy_revision == GENERATED_DATA_API_POLICY_REVISION

    workspace = _materialize(
        tmp_path,
        content_data_module=post_fix,
        components=CANONICAL_API_COMPONENTS,
    )

    assert _typescript_gate(workspace) == []


def test_request40_after_missing_export_and_untyped_import_classes_are_gone(
    tmp_path,
) -> None:
    """The exact pre-fix sources no longer produce either failure class.

    Reading `.values` off a seed record is a separate model misreading of the
    record shape. It now surfaces as a precise property diagnostic against a
    named record type instead of an unnamed cascade, and the manifest states the
    real property names, so components are told the flat shape up front.
    """

    context = request40_context()
    post_fix, manifest = build_content_data_module(context)
    workspace = _materialize(
        tmp_path,
        content_data_module=post_fix,
        components=REQUEST_40_COMPONENTS,
    )

    diagnostics = _typescript_gate(workspace)

    assert not [item for item in _classify(diagnostics) if item[2] == "missing_export"]
    assert all(
        "Property 'values' does not exist on type 'ServiceRecord'." in item
        or "implicitly has an 'any' type" in item
        for item in diagnostics
    )
    assert manifest.collections[0].record_type_symbol == "ServiceRecord"
    assert "never read" in manifest_prompt_projection(manifest)["record_shape"]


def test_request40_canonical_api_exports_record_seed_and_accessor() -> None:
    context = request40_context()
    source, manifest = build_content_data_module(context)

    assert manifest.module_specifier == GENERATED_DATA_API_MODULE_SPECIFIER
    assert manifest.module_path == "src/generated/content-data.ts"
    assert manifest.generated_file_sha256
    collection = manifest.collections[0]
    assert collection.collection_id == "COLLECTION-SERVICES"
    assert collection.entity_id == "ENTITY-SERVICE"
    assert collection.record_type_symbol == "ServiceRecord"
    assert collection.seed_value_symbol == "serviceSeedData"
    assert collection.accessor_symbol == "getServiceSeedData"
    assert collection.seed_record_count == 2

    assert "export interface ServiceRecord {" in source
    assert (
        "export const serviceSeedData: readonly ServiceRecord[] = " in source
    )
    assert (
        "export function getServiceSeedData(): readonly ServiceRecord[] {"
        in source
    )
    assert "  return serviceSeedData;" in source

    types = {
        item.property_name: item.typescript_type
        for item in collection.field_signatures
    }
    assert types["serviceName"] == "string"
    assert types["serviceDuration"] == "number"
    assert types["duration"] == "number"
    aliases = {
        item.property_name: item.alias_of
        for item in collection.field_signatures
    }
    assert aliases["serviceId"] == ""
    assert aliases["id"] == "serviceId"

    kinds = {item.symbol: item.export_kind for item in manifest.exports}
    assert kinds["ServiceRecord"] == "type"
    assert kinds["serviceSeedData"] == "const"
    assert kinds["getServiceSeedData"] == "function"
    signatures = {
        item.symbol: item.typescript_signature for item in manifest.exports
    }
    assert (
        signatures["serviceSeedData"]
        == "const serviceSeedData: readonly ServiceRecord[]"
    )
    assert (
        signatures["getServiceSeedData"]
        == "function getServiceSeedData(): readonly ServiceRecord[]"
    )


def test_request40_manifest_is_byte_stable_and_matches_emitted_module() -> None:
    context = request40_context()
    first_source, first = build_content_data_module(context)
    second_source, second = build_content_data_module(request40_context())

    assert first_source == second_source
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert generated_data_api_manifest(context).model_dump(
        mode="json"
    ) == first.model_dump(mode="json")

    emitted = next(
        item.source
        for item in build_data_sources(context)
        if item.path == "src/generated/content-data.ts"
    )
    assert emitted == first_source
    assert exported_symbols(emitted) >= set(first.symbols())


def test_request40_compat_aliases_still_exist_alongside_canonical_api() -> None:
    source, manifest = build_content_data_module(request40_context())
    symbols = exported_symbols(source)

    assert {"contentDataPlan", "contentDataSha256", "contentData"} <= symbols
    assert "dataCollections" in symbols
    assert "services" in symbols
    assert "service" in symbols
    assert set(manifest.symbols()) <= symbols


def test_request40_invented_export_fails_closed_before_typescript() -> None:
    source, manifest = build_content_data_module(request40_context())
    allowed = exported_symbols(source)
    invented = validate_generated_data_imports(
        path="src/components/business/CompServiceListComponent.tsx",
        source=(
            'import { fetchServiceRows } from "@/generated/content-data";\n'
            "export function CompServiceListComponent() {\n"
            "  return <ul>{fetchServiceRows().length}</ul>;\n"
            "}\n"
        ),
        manifest=manifest,
        allowed_symbols=allowed,
    )

    assert [item["symbol"] for item in invented] == ["fetchServiceRows"]
    assert invented[0]["suggestion"] == "serviceSeedData"


def test_request40_declared_symbols_are_never_reported_as_invented() -> None:
    source, manifest = build_content_data_module(request40_context())
    allowed = exported_symbols(source)

    for symbol in manifest.symbols():
        assert not validate_generated_data_imports(
            path="src/pages/PageServiceListPage.tsx",
            source=(
                f'import {{ {symbol} }} from "@/generated/content-data";\n'
            ),
            manifest=manifest,
            allowed_symbols=allowed,
        )


def test_request40_near_miss_accessor_is_healed_to_the_canonical_symbol() -> None:
    source, manifest = build_content_data_module(request40_context())
    allowed = exported_symbols(source)
    original = (
        'import { getServicesSeedData } from "../../generated/content-data";\n'
        "\n"
        "export function CompServiceListComponent() {\n"
        "  const rows = getServicesSeedData();\n"
        "  return <ul>{rows.length}</ul>;\n"
        "}\n"
    )

    healed, applied = heal_generated_data_symbols(
        original,
        manifest=manifest,
        allowed_symbols=allowed,
    )

    assert applied == (("getServicesSeedData", "serviceSeedData"),)
    assert "getServicesSeedData" not in healed
    assert (
        'import { serviceSeedData } from "../../generated/content-data";'
        in healed
    )
    assert "  const rows = serviceSeedData;" in healed
    assert not validate_generated_data_imports(
        path="src/components/business/CompServiceListComponent.tsx",
        source=healed,
        manifest=manifest,
        allowed_symbols=allowed,
    )


def test_request40_healed_near_miss_component_clears_the_typescript_gate(
    tmp_path,
) -> None:
    source, manifest = build_content_data_module(request40_context())
    allowed = exported_symbols(source)
    healed, applied = heal_generated_data_symbols(
        'import { getServicesSeedData } from "@/generated/content-data";\n'
        "\n"
        "export function CompServiceListComponent() {\n"
        "  const rows = getServicesSeedData();\n"
        "  return (\n"
        '    <ul data-bmv-component-id="COMP-SERVICE-LIST">\n'
        "      {rows.map((row) => (\n"
        "        <li key={row.serviceId}>{row.serviceName}</li>\n"
        "      ))}\n"
        "    </ul>\n"
        "  );\n"
        "}\n",
        manifest=manifest,
        allowed_symbols=allowed,
    )
    assert applied

    workspace = _materialize(
        tmp_path,
        content_data_module=source,
        components={
            "src/components/business/CompServiceListComponent.tsx": healed
        },
    )

    assert _typescript_gate(workspace) == []


def test_request40_heal_adds_the_canonical_symbol_to_exactly_one_clause(
) -> None:
    """A second content-data import must not receive a duplicate binding."""

    source, manifest = build_content_data_module(request40_context())
    allowed = exported_symbols(source)
    original = (
        'import { getServicesSeedData } from "@/generated/content-data";\n'
        'import { useState } from "react";\n'
        'import { contentDataPlan } from "@/generated/content-data";\n'
        "\n"
        "export function CompServiceListComponent() {\n"
        "  const [state] = useState(contentDataPlan.schema_version);\n"
        "  return <ul>{getServicesSeedData().length}{state}</ul>;\n"
        "}\n"
    )

    healed, applied = heal_generated_data_symbols(
        original,
        manifest=manifest,
        allowed_symbols=allowed,
    )

    assert applied == (("getServicesSeedData", "serviceSeedData"),)
    assert healed.count("serviceSeedData }") == 1
    assert healed.count("serviceSeedData") == 2
    assert 'import { contentDataPlan } from "@/generated/content-data";' in healed
    assert 'import { useState } from "react";' in healed


def test_request40_allowed_symbols_are_left_untouched_by_the_heal() -> None:
    source, manifest = build_content_data_module(request40_context())
    allowed = exported_symbols(source)
    original = (
        'import { getServiceSeedData, serviceSeedData, contentDataPlan } '
        'from "@/generated/content-data";\n'
        "export const rows = getServiceSeedData().length + "
        "serviceSeedData.length;\n"
        "export const version = contentDataPlan.schema_version;\n"
    )

    healed, applied = heal_generated_data_symbols(
        original,
        manifest=manifest,
        allowed_symbols=allowed,
    )

    assert applied == ()
    assert healed == original


def test_request40_manifest_reserves_symbols_against_compat_collisions() -> None:
    context = request40_context()
    source, manifest = build_content_data_module(context)
    declared = [item.symbol for item in manifest.exports]

    assert len(declared) == len(set(declared))
    for collection in manifest.collections:
        assert source.count(
            f"export const {collection.seed_value_symbol}"
        ) == 1
        assert source.count(
            f"export function {collection.accessor_symbol}"
        ) == 1
        assert source.count(
            f"export interface {collection.record_type_symbol}"
        ) == 1


def test_request40_manifest_prompt_projection_is_bounded_and_authoritative(
) -> None:
    _source, manifest = build_content_data_module(request40_context())
    projection = manifest_prompt_projection(manifest)

    assert projection["module_specifier"] == GENERATED_DATA_API_MODULE_SPECIFIER
    assert projection["api_policy_revision"] == GENERATED_DATA_API_POLICY_REVISION
    assert "Import only the symbols listed in exports" in projection["import_rule"]
    assert "noImplicitAny" in projection["strict_typescript"]
    assert [item["symbol"] for item in projection["exports"]] == [
        item.symbol for item in manifest.exports
    ]
    assert projection["collections"][0]["accessor_symbol"] == "getServiceSeedData"
    assert "prompt" not in json.dumps(projection).lower()


def test_request40_collections_without_seed_data_emit_no_api_block() -> None:
    context = request40_context()
    context.content_data.data_collections = ()
    context.content_data.model_dump = lambda mode="json": {
        "schema_version": "1.0",
        "content_items": [{"content_id": "CONTENT-HOME-HEADLINE"}],
        "data_collections": [],
    }

    source, manifest = build_content_data_module(context)

    assert manifest.collections == ()
    assert "Canonical generated-data API" not in source
    assert [item.symbol for item in manifest.exports] == [
        "contentDataPlan",
        "contentDataSha256",
        "contentData",
        "dataCollections",
    ]


def test_request40_manifest_is_persisted_with_the_data_exports_checkpoint(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1640)
    result = build_v2_candidate_revision(
        prepared.db,
        prepared.req.id,
        CandidateFixtureAI(),
        JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        req=prepared.req,
        phase3a_result=prepared.phase3a_result,
    )
    preview_contract = result["preview_contract"]
    assert preview_contract["status"] == "candidate_build_pending"

    checkpoints = preview_contract["candidate_stage_checkpoints"]
    data_exports = checkpoints["data_exports"]
    assert data_exports["status"] == "completed"
    persisted = data_exports["artifact_manifest"]["generated_data_api"]
    manifest = GeneratedDataApiManifest.model_validate(persisted)

    context = load_candidate_context(
        prepared.db,
        request_id=prepared.req.id,
        phase3a_result=prepared.phase3a_result,
    )
    expected_source, expected = build_content_data_module(context)
    assert manifest.model_dump(mode="json") == expected.model_dump(mode="json")
    assert manifest.generated_file_sha256 == expected.generated_file_sha256
    assert manifest.content_data_plan_sha256 == (
        context.refs.content_data_plan_ref.sha256
    )
    assert set(manifest.symbols()) <= exported_symbols(expected_source)
    assert "source" not in json.dumps(persisted)

    for substage in ("foundation", "business_components", "pages"):
        assert checkpoints[substage].get("artifact_manifest") is None


def test_request40_component_and_page_prompts_receive_the_data_api(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1641)
    ai = CandidateFixtureAI()
    build_v2_candidate_revision(
        prepared.db,
        prepared.req.id,
        ai,
        JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        req=prepared.req,
        phase3a_result=prepared.phase3a_result,
    )

    context = load_candidate_context(
        prepared.db,
        request_id=prepared.req.id,
        phase3a_result=prepared.phase3a_result,
    )
    expected = manifest_prompt_projection(generated_data_api_manifest(context))

    assert set(ai.last_inputs) == {"business_components", "pages"}
    for inputs in ai.last_inputs.values():
        assert inputs["generated_data_api"] == expected
        assert (
            inputs["generated_data_api"]["module_specifier"]
            == GENERATED_DATA_API_MODULE_SPECIFIER
        )


def _inject_data_import(symbol: str):
    def mutate(payload: dict) -> dict:
        first = payload["files"][0]
        first["source"] = (
            f'import {{ {symbol} }} from "../../generated/content-data";\n'
            + first["source"]
            + f"\nexport const injectedRowCount = {symbol}().length;\n"
        )
        return payload

    return mutate


def test_request40_unresolvable_invented_export_fails_closed_with_its_own_code(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1642)
    ai = CandidateFixtureAI()
    ai.stage_mutators["business_components"] = [
        _inject_data_import("getWidgetSeedData")
    ]
    ai.repair_mutators["business_components"] = [
        _inject_data_import("getWidgetSeedData")
    ]

    result = build_v2_candidate_revision(
        prepared.db,
        prepared.req.id,
        ai,
        JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        req=prepared.req,
        phase3a_result=prepared.phase3a_result,
    )
    failure = result["preview_contract"]["failure"]

    assert result["preview_contract"]["status"] == "candidate_contract_failed"
    assert failure["kind"] == "contract_validation"
    codes = {item["code"] for item in failure["issues"]}
    assert "generated_data_api_unknown_export" in codes
    unknown = next(
        item
        for item in failure["issues"]
        if item["code"] == "generated_data_api_unknown_export"
    )
    assert "getWidgetSeedData" in unknown["message"]
    assert GENERATED_DATA_API_MODULE_SPECIFIER in unknown["message"]
    assert unknown["path"].startswith("src/components/business/")


def test_request40_near_miss_import_is_healed_inside_the_pipeline(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1643)
    context = load_candidate_context(
        prepared.db,
        request_id=prepared.req.id,
        phase3a_result=prepared.phase3a_result,
    )
    manifest = generated_data_api_manifest(context)
    collection = manifest.collections[0]
    plural = upper_camel(pluralize(identifier_words(collection.entity_id)))
    invented = f"get{plural}SeedData"
    assert invented != collection.accessor_symbol
    assert (
        resolve_invented_symbol(invented, manifest=manifest)
        == collection.seed_value_symbol
    )

    ai = CandidateFixtureAI()
    ai.stage_mutators["business_components"] = [_inject_data_import(invented)]

    result = build_v2_candidate_revision(
        prepared.db,
        prepared.req.id,
        ai,
        JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        req=prepared.req,
        phase3a_result=prepared.phase3a_result,
    )
    preview_contract = result["preview_contract"]

    assert preview_contract["status"] == "candidate_build_pending"
    assert [stage for stage, _model in ai.calls] == [
        "business_components",
        "pages",
    ]
    workspace = (
        settings.PREVIEW_CANDIDATES_DIR
        / preview_contract["candidate_revision"]["workspace_relpath"]
    )
    components = sorted((workspace / "src/components/business").glob("*.tsx"))
    sources = {
        path.name: path.read_text(encoding="utf-8") for path in components
    }
    assert not [name for name, text in sources.items() if invented in text]
    rewritten = [
        name for name, text in sources.items() if "injectedRowCount" in text
    ]
    assert len(rewritten) == 1
    source = sources[rewritten[0]]
    seed_symbol = collection.seed_value_symbol
    assert (
        f"export const injectedRowCount = {seed_symbol}.length;" in source
    )
    assert f"import {{ {seed_symbol} }} from" in source


def test_record_shape_heal_runs_once_and_persists_audit_evidence(
    isolated_candidate_paths,
) -> None:
    prepared = prepare_phase3a(request_id=1644)
    context = load_candidate_context(
        prepared.db,
        request_id=prepared.req.id,
        phase3a_result=prepared.phase3a_result,
    )
    collection = generated_data_api_manifest(context).collections[0]
    field = collection.field_signatures[0]

    def inject_legacy_record_shape(payload: dict) -> dict:
        first = payload["files"][0]
        first["source"] = (
            f'import {{ {collection.seed_value_symbol} }} from '
            '"../../generated/content-data";\n'
            + first["source"]
            + "\n"
            + f"const legacyRecord = {collection.seed_value_symbol}[0];\n"
            + "export const legacyRecordField = "
            + f"legacyRecord.values.{field.property_name};\n"
        )
        return payload

    ai = CandidateFixtureAI()
    ai.stage_mutators["business_components"] = [inject_legacy_record_shape]
    result = build_v2_candidate_revision(
        prepared.db,
        prepared.req.id,
        ai,
        JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        req=prepared.req,
        phase3a_result=prepared.phase3a_result,
    )
    preview_contract = result["preview_contract"]

    assert preview_contract["status"] == "candidate_build_pending"
    assert [stage for stage, _model in ai.calls] == [
        "business_components",
        "pages",
    ]
    checkpoint = preview_contract["candidate_stage_checkpoints"][
        "business_components"
    ]
    evidence = checkpoint["artifact_manifest"][
        "generated_data_record_shape_heals"
    ]
    assert len(evidence) == 1
    assert evidence[0]["original_expression"].endswith(field.property_name)
    assert evidence[0]["replacement"].endswith(field.property_name)
    assert evidence[0]["manifest_sha256"]
    assert evidence[0]["file_sha256_before"]
    assert evidence[0]["file_sha256_after"]


def test_request40_manifest_carries_relationship_reference_fields() -> None:
    context = request40_context()
    context.content_data.relationships = (
        type(
            "Relationship",
            (),
            {
                "from_collection_id": "COLLECTION-SERVICES",
                "from_field_id": "FIELD-SERVICE-ID",
                "to_collection_id": "COLLECTION-BOOKINGS",
                "to_field_id": "FIELD-BOOKING-SERVICE-ID",
            },
        )(),
    )

    manifest = build_generated_data_api_manifest(
        content_data=context.content_data,
        content_data_plan_sha256="b" * 64,
    )

    references = {
        item.property_name: (
            item.reference_collection_id,
            item.reference_field_id,
        )
        for item in manifest.collections[0].field_signatures
    }
    assert references["serviceId"] == (
        "COLLECTION-BOOKINGS",
        "FIELD-BOOKING-SERVICE-ID",
    )
    assert references["serviceName"] == (None, None)


def _shape_heal(source: str) -> tuple[str, tuple[dict, ...], tuple[dict, ...]]:
    module, manifest = build_content_data_module(request40_context())
    return heal_generated_data_record_shapes(
        source,
        path="src/components/business/CompServiceDetailComponent.tsx",
        manifest=manifest,
        content_data_module=module,
    )


def test_record_shape_heal_rewrites_values_find_value_with_manifest_field() -> None:
    healed, rewrites, issues = _shape_heal(
        'import { getServiceSeedData } from "@/generated/content-data";\n'
        "const services = getServiceSeedData();\n"
        "const detail = services[0];\n"
        "export const label = detail.values.find((value) => value.serviceName)?.value;\n"
    )

    assert not issues
    assert "detail.serviceName" in healed
    assert "values.find" not in healed
    assert rewrites[0]["reason"] == "manifest_record_values_find_value"
    assert rewrites[0]["manifest_sha256"]
    assert rewrites[0]["file_sha256_before"]
    assert rewrites[0]["file_sha256_after"]


def test_record_shape_heal_rewrites_fields_find_value_with_manifest_field() -> None:
    healed, rewrites, issues = _shape_heal(
        'import { serviceSeedData } from "@/generated/content-data";\n'
        "const detail = serviceSeedData[0];\n"
        "export const duration = detail.fields.find((value) => value.serviceDuration)?.value;\n"
    )

    assert not issues
    assert "detail.serviceDuration" in healed
    assert rewrites[0]["reason"] == "manifest_record_fields_find_value"


def test_record_shape_heal_maps_a_unique_legacy_field_predicate() -> None:
    healed, rewrites, issues = _shape_heal(
        'import { serviceSeedData } from "@/generated/content-data";\n'
        "const detail = serviceSeedData[0];\n"
        'export const label = detail.values.find((value) => value.field === "serviceName")?.value;\n'
    )

    assert not issues
    assert "detail.serviceName" in healed
    assert rewrites[0]["property_name"] == "serviceName"


@pytest.mark.parametrize(
    ("wrapper", "field"),
    [
        ("values", "serviceName"),
        ("fields", "serviceDuration"),
    ],
)
def test_record_shape_heal_rewrites_direct_legacy_wrapper_access(
    wrapper: str,
    field: str,
) -> None:
    healed, rewrites, issues = _shape_heal(
        'import { serviceSeedData } from "@/generated/content-data";\n'
        "const detail = serviceSeedData[0];\n"
        f"export const value = detail.{wrapper}.{field};\n"
    )

    assert not issues
    assert f"detail.{field}" in healed
    assert len(rewrites) == 1


def test_record_shape_heal_preserves_optional_record_receiver() -> None:
    healed, rewrites, issues = _shape_heal(
        'import { serviceSeedData } from "@/generated/content-data";\n'
        "const detail = serviceSeedData[0];\n"
        "export const label = detail?.values.find((value) => value.serviceName)?.value;\n"
    )

    assert not issues
    assert "detail?.serviceName" in healed
    assert len(rewrites) == 1


def test_record_shape_heal_fails_closed_for_ambiguous_field_predicate() -> None:
    original = (
        'import { serviceSeedData } from "@/generated/content-data";\n'
        "const detail = serviceSeedData[0];\n"
        "export const value = detail.values.find((value) => value.serviceName || value.name)?.value;\n"
    )

    healed, rewrites, issues = _shape_heal(original)

    assert healed == original
    assert rewrites == ()
    assert issues[0]["code"] == "generated_data_record_shape_ambiguous"


def test_record_shape_heal_fails_closed_for_dynamic_predicate() -> None:
    original = (
        'import { serviceSeedData } from "@/generated/content-data";\n'
        "const detail = serviceSeedData[0];\n"
        "const field = getRequestedField();\n"
        "export const value = detail.values.find((value) => value[field])?.value;\n"
    )

    healed, rewrites, issues = _shape_heal(original)

    assert healed == original
    assert rewrites == ()
    assert issues[0]["code"] == "generated_data_record_shape_dynamic"


def test_record_shape_heal_leaves_unrelated_values_access_untouched() -> None:
    original = (
        "const detail = { values: { serviceName: 'local' } };\n"
        "export const value = detail.values.serviceName;\n"
    )

    healed, rewrites, issues = _shape_heal(original)

    assert healed == original
    assert rewrites == ()
    assert issues == ()


def test_record_shape_heal_leaves_valid_candidates_byte_stable() -> None:
    original = CANONICAL_API_COMPONENTS[
        "src/components/business/CompServiceListComponent.tsx"
    ]

    healed, rewrites, issues = _shape_heal(original)

    assert healed == original
    assert rewrites == ()
    assert issues == ()


def test_record_shape_heal_preserves_manifest_callback_inference(tmp_path) -> None:
    module, manifest = build_content_data_module(request40_context())
    original = (
        'import { getServiceSeedData } from "@/generated/content-data";\n'
        "const services = getServiceSeedData();\n"
        "export const labels = services.map((service) => "
        "service.values.find((value) => value.serviceName)?.value);\n"
    )

    healed, rewrites, issues = heal_generated_data_record_shapes(
        original,
        path="src/components/business/CompServiceListComponent.tsx",
        manifest=manifest,
        content_data_module=module,
    )
    workspace = _materialize(
        tmp_path,
        content_data_module=module,
        components={
            "src/components/business/CompServiceListComponent.tsx": healed
        },
    )

    assert not issues
    assert rewrites[0]["record_type_symbol"] == "ServiceRecord"
    assert "(service:" not in healed
    assert _typescript_gate(workspace) == []


def test_record_shape_batch_heal_returns_auditable_evidence() -> None:
    batch = GeneratedCandidateBatch(
        batch_kind="business_components",
        files=(
            GeneratedCandidateFile(
                path="src/components/business/CompServiceDetailComponent.tsx",
                file_kind="business_component",
                owner_contract_ids=("COMP-SERVICE-DETAIL",),
                source=(
                    'import { serviceSeedData } from "@/generated/content-data";\n'
                    "const detail = serviceSeedData[0];\n"
                    "export const duration = detail.values.find((value) => value.serviceDuration)?.value;\n"
                ),
            ),
        ),
    )

    healed, evidence, issues = heal_generated_data_record_shapes_in_batch(
        batch,
        context=request40_context(),
    )

    assert not issues
    assert "detail.serviceDuration" in healed.files[0].source
    assert evidence[0]["path"] == healed.files[0].path
    assert evidence[0]["original_expression"].endswith("?.value")
    assert evidence[0]["replacement"] == "detail.serviceDuration"


def test_request40_exact_sources_leave_only_the_unsupported_wrapper_after_ast_heal(
    tmp_path,
) -> None:
    context = request40_context()
    module, _manifest = build_content_data_module(context)
    batch = GeneratedCandidateBatch(
        batch_kind="business_components",
        files=tuple(
            GeneratedCandidateFile(
                path=path,
                file_kind="business_component",
                owner_contract_ids=(f"COMP-FIXTURE-{index}",),
                source=source,
            )
            for index, (path, source) in enumerate(REQUEST_40_COMPONENTS.items())
        ),
    )

    imported, import_rewrites = heal_invented_generated_data_imports(
        batch,
        context=context,
    )
    healed, evidence, issues = heal_generated_data_record_shapes_in_batch(
        imported,
        context=context,
    )
    workspace = _materialize(
        tmp_path,
        content_data_module=module,
        components={item.path: item.source for item in healed.files},
    )
    diagnostics = _typescript_gate(workspace)

    assert import_rewrites == ()
    assert len(evidence) == 6
    assert issues == ()
    assert diagnostics == [
        (
            "src/components/business/CompServiceDetailComponent.tsx:9:41 "
            "Property 'values' does not exist on type 'ServiceRecord'."
        ),
        (
            "src/components/business/CompServiceDetailComponent.tsx:9:54 "
            "Parameter 'v' implicitly has an 'any' type."
        ),
    ]


class _Request40ScopedRepairAI:
    """Provider double that returns only the one scoped repair file."""

    name = "request40-scoped-repair"

    def __init__(self, *, source: str, owner_contract_ids: tuple[str, ...]) -> None:
        self.source = source
        self.owner_contract_ids = owner_contract_ids
        self.calls = 0

    def ask_chat(self, _model, _messages, **_kwargs) -> str:
        self.calls += 1
        return json.dumps(
            {
                "schema_version": "1.0",
                "batch_kind": "business_components",
                "files": [
                    {
                        "path": (
                            "src/components/business/"
                            "CompServiceDetailComponent.tsx"
                        ),
                        "file_kind": "business_component",
                        "owner_contract_ids": list(self.owner_contract_ids),
                        "source": self.source,
                    }
                ],
            }
        )


def test_request40_exact_sources_reach_zero_diagnostics_after_scoped_repair(
    tmp_path,
) -> None:
    context = request40_context()
    module, _manifest = build_content_data_module(context)
    batch = GeneratedCandidateBatch(
        batch_kind="business_components",
        files=tuple(
            GeneratedCandidateFile(
                path=path,
                file_kind="business_component",
                owner_contract_ids=(f"COMP-FIXTURE-{index}",),
                source=source,
            )
            for index, (path, source) in enumerate(REQUEST_40_COMPONENTS.items())
        ),
    )
    imported, _import_rewrites = heal_invented_generated_data_imports(
        batch,
        context=context,
    )
    healed, evidence, issues = heal_generated_data_record_shapes_in_batch(
        imported,
        context=context,
    )
    assert evidence
    assert not issues
    detail = next(
        item
        for item in healed.files
        if item.path.endswith("CompServiceDetailComponent.tsx")
    )
    assert "s.values.some" in detail.source
    repaired_source = detail.source.replace(
        'import { getServiceSeedData } from "@/generated/content-data";',
        (
            'import { getServiceSeedData } from "@/generated/content-data";\n'
            'import type { ServiceRecord } from "@/generated/content-data";'
        ),
    ).replace(
        "const detail = services.find((s) => s.values.some((v) => v.serviceName));",
        (
            "const detail = services.find((s: ServiceRecord) => "
            "Boolean(s.serviceName));"
        ),
    )
    provider = _Request40ScopedRepairAI(
        source=repaired_source,
        owner_contract_ids=detail.owner_contract_ids,
    )
    repair = repair_ai_batch(
        request_id=40,
        batch_stage="business_components",
        policy=repair_policy(),
        batch=healed,
        diagnostics=(
            json.dumps(
                CandidateValidationIssue(
                    code="typescript_no_emit",
                    path=detail.path,
                    message=(
                        "Property 'values' does not exist on type "
                        "'ServiceRecord'."
                    ),
                ).model_dump(mode="json")
            ),
        ),
        canonical_bindings={
            "page_purpose_contract": {},
            "business_component_plan": {},
            "interaction_contract": {},
            "required_business_component_bindings": {},
        },
        ai_provider=provider,
        template_renderer=JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        prompt_template=PromptTemplate.V2_CANDIDATE_REPAIR,
        phase_deadline=time.monotonic() + 60,
    )
    workspace = _materialize(
        tmp_path,
        content_data_module=module,
        components={item.path: item.source for item in repair.batch.files},
    )

    assert provider.calls == 1
    assert _typescript_gate(workspace) == []
    with tempfile.TemporaryDirectory(
        dir=settings.PREVIEW_TEMPLATE_DIR,
        prefix=".request40-acceptance-",
    ) as acceptance_root:
        acceptance = _materialize(
            Path(acceptance_root),
            content_data_module=module,
            components={item.path: item.source for item in repair.batch.files},
        )
        _vite_build(acceptance)
        _assert_preview_routes(
            acceptance,
            ("/", "/services", "/services/first", "/booking", "/confirmation"),
        )


def test_request41_class_equivalent_sources_are_normalized_without_manual_replacement(
    tmp_path,
) -> None:
    """Keep the #41 type-import, JSX, and flat-record regression reproducible."""

    customer_records = (
        {
            "FIELD-CUSTOMER-ID": "customer-1",
            "FIELD-CUSTOMER-NAME": "Ada Lovelace",
            "FIELD-CUSTOMER-EMAIL": "ada@example.test",
        },
    )
    customer_collection = SimpleNamespace(
        collection_id="COLLECTION-CUSTOMERS",
        entity_id="ENTITY-CUSTOMER",
        field_ids=tuple(customer_records[0]),
        seed_records=tuple(
            SimpleNamespace(
                values=tuple(
                    SimpleNamespace(field_id=field_id, value=value)
                    for field_id, value in record.items()
                )
            )
            for record in customer_records
        ),
    )
    content_data = SimpleNamespace(
        content_items=(),
        data_collections=(customer_collection,),
        relationships=(),
        model_dump=lambda mode="json": {
            "schema_version": "1.0",
            "content_items": [],
            "data_collections": [
                {
                    "collection_id": customer_collection.collection_id,
                    "entity_id": customer_collection.entity_id,
                    "field_ids": list(customer_collection.field_ids),
                    "seed_records": [
                        {
                            "record_id": f"RECORD-CUSTOMER-{index}",
                            "values": [
                                {"field_id": field_id, "value": value}
                                for field_id, value in record.items()
                            ],
                        }
                        for index, record in enumerate(customer_records)
                    ],
                }
            ],
        },
    )
    context = SimpleNamespace(
        content_data=content_data,
        refs=SimpleNamespace(content_data_plan_ref=SimpleNamespace(sha256="4" * 64)),
    )
    module, manifest = build_content_data_module(context)
    assert validate_generated_data_literals(
        manifest=manifest,
        content_data=content_data,
    ) == ()

    def candidate_source(index: int, *, legacy_record_access: bool = False) -> str:
        customer_value = (
            "{customer.values.customerName}{customer.fields.customerEmail}"
            if legacy_record_access
            else "{customer.customerName}"
        )
        return (
            'import { CustomerRecord, customerSeedData } from "@/generated/content-data";\n'
            "\n"
            f"export function CompRequest41_{index}(): JSX.Element {{\n"
            "  const customer: CustomerRecord = customerSeedData[0];\n"
            f"  return <p>{customer_value}</p>;\n"
            "}\n"
        )

    initial_sources = {
        f"src/components/business/CompRequest41_{index}.tsx": candidate_source(
            index,
            legacy_record_access=index == 0,
        )
        for index in range(5)
    }
    initial_workspace = _materialize(
        tmp_path / "initial",
        content_data_module=module,
        components=initial_sources,
    )
    initial_diagnostics = _typescript_gate(initial_workspace)
    assert len(initial_diagnostics) == 12
    assert sum(
        "must be imported using a type-only import" in item
        and "verbatimModuleSyntax" in item
        for item in initial_diagnostics
    ) == 5
    assert sum("Cannot find namespace 'JSX'." in item for item in initial_diagnostics) == 5
    assert sum(
        "Property 'values' does not exist on type 'CustomerRecord'." in item
        or "Property 'fields' does not exist on type 'CustomerRecord'." in item
        for item in initial_diagnostics
    ) == 2

    normalized_sources: dict[str, str] = {}
    type_evidence: list[dict] = []
    for path, source in initial_sources.items():
        normalized, evidence, issues = normalize_generated_candidate_types(
            source,
            path=path,
            manifest=manifest,
            content_data_module=module,
        )
        assert issues == ()
        normalized_sources[path] = normalized
        type_evidence.extend(evidence)
    healed, record_evidence, record_issues = heal_generated_data_record_shapes_in_batch(
        GeneratedCandidateBatch(
            batch_kind="business_components",
            files=tuple(
                GeneratedCandidateFile(
                    path=path,
                    file_kind="business_component",
                    owner_contract_ids=(f"COMP-REQUEST-41-{index}",),
                    source=source,
                )
                for index, (path, source) in enumerate(normalized_sources.items())
            ),
        ),
        context=context,
    )
    final_sources = {item.path: item.source for item in healed.files}
    final_workspace = _materialize(
        tmp_path / "normalized",
        content_data_module=module,
        components=final_sources,
    )

    assert len(type_evidence) == 10
    assert len(record_evidence) == 2
    assert record_issues == ()
    assert _typescript_gate(final_workspace) == []
    with tempfile.TemporaryDirectory(
        dir=settings.PREVIEW_TEMPLATE_DIR,
        prefix=".request41-acceptance-",
    ) as acceptance_root:
        acceptance = _materialize(
            Path(acceptance_root),
            content_data_module=module,
            components=final_sources,
        )
        _vite_build(acceptance)
        _assert_preview_routes(
            acceptance,
            ("/", "/services", "/services/first", "/booking", "/confirmation"),
        )
