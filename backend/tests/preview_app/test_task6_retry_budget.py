from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app import chat_refinement, codegen, pipeline
from app.application.preview_app.refinement import chat_rebuild
from app.application.preview_app.catalogue_contract import (
    minimal_catalogue_page_scaffold,
    validate_catalogue_page_content,
)
from app.application.preview_app.fallback import (
    clear_stubbed_paths,
    consume_stubbed_paths,
    record_stubbed_path,
)
from app.application.preview_app import fallback as fallback_module
from app.infrastructure.templating.renderer import JinjaTemplateRenderer

try:
    from app.application.preview_app import ai_budget as ai_budget_module
except ImportError:
    ai_budget_module = None

budget_ai_provider = getattr(ai_budget_module, "budget_ai_provider", None)
active_budget_registry_size = getattr(ai_budget_module, "active_budget_registry_size", None)
active_operation_registry_size = getattr(ai_budget_module, "active_operation_registry_size", None)
request_operation_lock = getattr(ai_budget_module, "request_operation_lock", None)


TEMPLATES_DIR = REPO_ROOT / "backend" / "app" / "templates"


class _SequenceAI:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.prompts: list[str] = []

    def ask_chat(self, _model, messages, **_kwargs):
        self.calls += 1
        self.prompts.append(messages[-1]["content"])
        return self.responses.pop(0) if self.responses else ""

    def ask_vision(self, _model, prompt, _image_path):
        self.calls += 1
        self.prompts.append(prompt)
        return self.responses.pop(0) if self.responses else ""


def _route() -> dict:
    return {
        "path": "/",
        "page_id": "home",
        "role_id": "customer",
        "component_file": "src/pages/HomePage.tsx",
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


def _valid_page(sentinel: str) -> str:
    return minimal_catalogue_page_scaffold(
        "src/pages/HomePage.tsx",
        _route(),
        brand_name=sentinel,
    ).replace(
        "// deterministic catalogue contract scaffold",
        "// AI-authored business page",
    )


def _mock_synthesis_workspace(
    workspace: Path,
    existing: str,
    needed: tuple[str, ...] = ("brand",),
) -> Path:
    page = workspace / "src/pages/HomePage.tsx"
    page.parent.mkdir(parents=True)
    page.write_text(
        f"import {{ {', '.join(needed)} }} from '@/data/mock';\n"
        "export default function HomePage() { return <div />; }\n",
        encoding="utf-8",
    )
    mock = workspace / "src/data/mock.ts"
    mock.parent.mkdir(parents=True)
    mock.write_text(existing, encoding="utf-8")
    return mock


def test_mock_synthesis_budget_exhaustion_preserves_existing_source() -> None:
    existing = "export const brand = { name: 'KEEP_EXISTING' };\n"
    underlying = _SequenceAI(["consume budget", "export const brand = { name: 'REPLACE' };\n"])
    wrapped = budget_ai_provider(
        underlying,
        request_key="mock-synthesis-exhausted",
        max_calls=1,
    )
    try:
        assert wrapped.ask_chat("model", [{"role": "user", "content": "consume"}]) == "consume budget"
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            mock = _mock_synthesis_workspace(workspace, existing)
            changed = codegen.synthesize_mock_data(
                workspace,
                "",
                {},
                {},
                {},
                {"routes": []},
                wrapped,
                JinjaTemplateRenderer(TEMPLATES_DIR),
            )
            assert changed is False
            assert mock.read_text(encoding="utf-8") == existing
            assert underlying.calls == 1
    finally:
        wrapped.close()


def test_mock_synthesis_malformed_responses_preserve_existing_source() -> None:
    existing = "export const brand = { name: 'KEEP_EXISTING' };\n"
    malformed_responses = (
        "```ts\nthis is fenced junk\n```",
        "export const brand = { name: 'cut off'",
        "const brand = { name: 'no export' };\n",
        "export const brand = ;\n",
        "import value from 'https://evil.invalid/data.ts';\nexport const brand = value;\n",
        "const source = 'x';\nexport const brand = import(source);\n",
    )
    for response in malformed_responses:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            mock = _mock_synthesis_workspace(workspace, existing)
            changed = codegen.synthesize_mock_data(
                workspace,
                "",
                {},
                {},
                {},
                {"routes": []},
                _SequenceAI([response]),
                JinjaTemplateRenderer(TEMPLATES_DIR),
            )
            assert changed is False, response
            assert mock.read_text(encoding="utf-8") == existing, response


def test_mock_synthesis_parser_rejects_balanced_malformed_typescript() -> None:
    existing = b"export const brand = { name: 'KEEP_EXISTING' };\r\n"
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        mock = _mock_synthesis_workspace(workspace, existing.decode("utf-8"))
        mock.write_bytes(existing)
        changed = codegen.synthesize_mock_data(
            workspace,
            "",
            {},
            {},
            {},
            {"routes": []},
            _SequenceAI(["export const brand = { name: };"]),
            JinjaTemplateRenderer(TEMPLATES_DIR),
        )
        assert changed is False
        assert mock.read_bytes() == existing


def test_mock_synthesis_rejects_valid_candidate_missing_needed_exports() -> None:
    existing = b"export const brand = { name: 'KEEP_EXISTING' };\n"
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        mock = _mock_synthesis_workspace(workspace, existing.decode("utf-8"))
        mock.write_bytes(existing)
        changed = codegen.synthesize_mock_data(
            workspace,
            "",
            {},
            {},
            {},
            {"routes": []},
            _SequenceAI(["export const unrelated = { value: 1 };"]),
            JinjaTemplateRenderer(TEMPLATES_DIR),
        )
        assert changed is False
        assert mock.read_bytes() == existing


def test_mock_synthesis_valid_candidate_with_all_needed_exports_overwrites() -> None:
    existing = b"export const brand = { name: 'KEEP_EXISTING' };\n"
    candidate = (
        "export const brand = { name: 'REPLACED' };\n"
        "export const roles = [{ id: 'owner' }];"
    )
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        mock = _mock_synthesis_workspace(
            workspace,
            existing.decode("utf-8"),
            needed=("brand", "roles"),
        )
        changed = codegen.synthesize_mock_data(
            workspace,
            "",
            {},
            {},
            {},
            {"routes": []},
            _SequenceAI([candidate]),
            JinjaTemplateRenderer(TEMPLATES_DIR),
        )
        assert changed is True
        assert mock.read_text(encoding="utf-8") == candidate


def test_mock_synthesis_fails_closed_without_typescript_tooling() -> None:
    existing = b"export const brand = { name: 'KEEP_EXISTING' };\n"
    candidate = "export const brand = { name: 'REPLACED' };"
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as missing:
        workspace = Path(tmp)
        mock = _mock_synthesis_workspace(workspace, existing.decode("utf-8"))
        mock.write_bytes(existing)
        original_template = codegen.settings.PREVIEW_TEMPLATE_DIR
        codegen.settings.PREVIEW_TEMPLATE_DIR = Path(missing)
        try:
            changed = codegen.synthesize_mock_data(
                workspace,
                "",
                {},
                {},
                {},
                {"routes": []},
                _SequenceAI([candidate]),
                JinjaTemplateRenderer(TEMPLATES_DIR),
            )
        finally:
            codegen.settings.PREVIEW_TEMPLATE_DIR = original_template
        assert changed is False
        assert mock.read_bytes() == existing


def test_aggregate_budget_stops_underlying_calls() -> None:
    assert callable(budget_ai_provider), "request-scoped aggregate AI budget is required"
    underlying = _SequenceAI(["one", "two", "three"])
    wrapped = budget_ai_provider(underlying, request_key="request-7", max_calls=2)
    assert wrapped.ask_chat("model", [{"role": "user", "content": "a"}]) == "one"
    assert wrapped.ask_chat("model", [{"role": "user", "content": "b"}]) == "two"
    assert wrapped.ask_chat("model", [{"role": "user", "content": "c"}]) == ""
    assert wrapped.ask_vision("model", "d", "unused.png") == ""
    assert underlying.calls == 2
    assert wrapped.budget.used == 2
    assert wrapped.budget.exhausted is True
    reentered = budget_ai_provider(wrapped, request_key="request-7", max_calls=99)
    assert reentered is not wrapped
    assert reentered.budget is wrapped.budget
    other_request = budget_ai_provider(wrapped, request_key="request-8", max_calls=1)
    assert other_request is not wrapped
    assert other_request.budget.request_key == "request-8"
    reentered.close()
    wrapped.close()
    other_request.close()
    assert active_budget_registry_size() == 0


def test_concurrent_budget_wrappers_share_one_request_cap() -> None:
    assert callable(active_budget_registry_size)
    underlying = _SequenceAI(["only", "must-not-run"])
    barrier = threading.Barrier(2)

    def _call() -> str:
        wrapped = budget_ai_provider(underlying, request_key="concurrent-budget", max_calls=1)
        barrier.wait()
        try:
            return wrapped.ask_chat("model", [{"role": "user", "content": "go"}])
        finally:
            wrapped.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in [pool.submit(_call), pool.submit(_call)]]
    assert underlying.calls == 1
    assert sorted(results) == ["", "only"]
    assert active_budget_registry_size() == 0


def test_same_request_operations_serialize_and_cleanup() -> None:
    assert callable(request_operation_lock)
    assert callable(active_operation_registry_size)
    barrier = threading.Barrier(2)
    state_lock = threading.Lock()
    active = 0
    peak = 0

    def _mutate() -> None:
        nonlocal active, peak
        barrier.wait()
        with request_operation_lock("serialized-request"):
            with state_lock:
                active += 1
                peak = max(peak, active)
            threading.Event().wait(0.03)
            with state_lock:
                active -= 1

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_mutate), pool.submit(_mutate)]
        for future in futures:
            future.result()
    assert peak == 1
    assert active_operation_registry_size() == 0


def test_one_budget_is_shared_across_codegen_and_critic() -> None:
    renderer = JinjaTemplateRenderer(TEMPLATES_DIR)
    route = _route()
    underlying = _SequenceAI(
        [
            _valid_page("SHARED_BUDGET_SENTINEL"),
            json.dumps(
                {"score": 95, "verdict": "pass", "issues": [], "revision_instructions": ""}
            ),
        ]
    )
    wrapped = budget_ai_provider(underlying, request_key="shared-request", max_calls=1)
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        codegen.generate_file(
            workspace,
            {"path": route["component_file"], "kind": "page", "instructions": "assigned"},
            "business",
            {"routes": [route]},
            {"roles": []},
            {},
            {},
            wrapped,
            renderer,
        )
        review = codegen.critique_file(
            workspace,
            route["component_file"],
            "assigned",
            "business",
            "direction",
            wrapped,
            renderer,
            {"routes": [route]},
        )
        assert review["verdict"] == "unavailable"
        assert review["preserve"] is True
        assert underlying.calls == 1
    wrapped.close()


def test_workspace_scaffold_tracking_is_isolated() -> None:
    with tempfile.TemporaryDirectory() as left_tmp, tempfile.TemporaryDirectory() as right_tmp:
        left = Path(left_tmp)
        right = Path(right_tmp)
        clear_stubbed_paths(left)
        clear_stubbed_paths(right)
        barrier = threading.Barrier(2)

        def _track(workspace: Path, path: str) -> list[str]:
            record_stubbed_path(workspace, path)
            barrier.wait()
            return consume_stubbed_paths(workspace)

        with ThreadPoolExecutor(max_workers=2) as pool:
            left_future = pool.submit(_track, left, "src/pages/Left.tsx")
            right_future = pool.submit(_track, right, "src/pages/Right.tsx")
            assert left_future.result() == ["src/pages/Left.tsx"]
            assert right_future.result() == ["src/pages/Right.tsx"]
        assert consume_stubbed_paths(left) == []
        assert consume_stubbed_paths(right) == []


def test_contract_retry_excerpt_keeps_later_slot_context() -> None:
    source = (
        "HEAD_SENTINEL\n"
        + ("const early = 'safe';\n" * 300)
        + "const slots = { hero: <Hero />, features: <Features /> };\n"
        + ("const later = 'safe';\n" * 300)
        + "TAIL_SENTINEL\n"
    )
    context = codegen._catalogue_retry_context(
        errors=["slot:footer"],
        contract_json='{"section_slots":["hero","footer"]}',
        rejected_source=source,
        build_context="TS2322 near footer assignment",
    )
    assert "HEAD_SENTINEL" in context
    assert "slot:footer" in context
    assert "TAIL_SENTINEL" in context
    assert "TS2322 near footer assignment" in context
    assert len(context) < 7000


def test_malformed_critic_retries_once_then_preserves() -> None:
    renderer = JinjaTemplateRenderer(TEMPLATES_DIR)
    route = _route()
    valid_pass = json.dumps(
        {"score": 95, "verdict": "pass", "issues": [], "revision_instructions": ""}
    )
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        page = workspace / route["component_file"]
        page.parent.mkdir(parents=True)
        page.write_text(_valid_page("Critic Sentinel"), encoding="utf-8")
        recovered_ai = _SequenceAI(["not json", valid_pass])
        recovered = codegen.critique_file(
            workspace,
            route["component_file"],
            "assigned slots",
            "business",
            "direction",
            recovered_ai,
            renderer,
            {"routes": [route]},
        )
        assert recovered["verdict"] == "pass"
        assert recovered_ai.calls == 2

        unavailable_ai = _SequenceAI(["not json", "still not json"])
        unavailable = codegen.critique_file(
            workspace,
            route["component_file"],
            "assigned slots",
            "business",
            "direction",
            unavailable_ai,
            renderer,
            {"routes": [route]},
        )
        assert unavailable["verdict"] == "unavailable"
        assert unavailable["preserve"] is True
        assert unavailable_ai.calls == 2


def test_parallel_critic_refine_accepts_tuple_work_items() -> None:
    route = _route()
    files = [
        {
            "path": route["component_file"],
            "kind": "page",
            "instructions": "home",
        },
        {
            "path": "src/pages/SecondPage.tsx",
            "kind": "page",
            "instructions": "second",
        },
    ]
    originals = codegen.critique_file, codegen.refine_file
    refined: list[str] = []
    import app.application.preview_app.codegen.critic as critic_mod

    try:
        def _critique(*_args, **_kwargs):
            return {
                "score": 80,
                "verdict": "revise",
                "issues": ["improve"],
                "revision_instructions": "improve",
            }

        def _refine(_workspace, path, *_args, **_kwargs):
            refined.append(path)
            return "updated"

        codegen.critique_file = critic_mod.critique_file = _critique
        codegen.refine_file = critic_mod.refine_file = _refine
        with tempfile.TemporaryDirectory() as tmp:
            result = codegen.critique_and_refine(
                Path(tmp),
                files,
                "business",
                "direction",
                {},
                {},
                _SequenceAI([]),
                JinjaTemplateRenderer(TEMPLATES_DIR),
                max_workers=2,
                architect={"routes": [route]},
            )
    finally:
        codegen.critique_file = critic_mod.critique_file = originals[0]
        codegen.refine_file = critic_mod.refine_file = originals[1]
    assert sorted(refined) == sorted(item["path"] for item in files)
    assert sorted(result) == sorted(refined)


def test_malformed_chat_payload_retries_once() -> None:
    ai = _SequenceAI(
        [
            "not valid json",
            json.dumps({"reply": "updated", "files": []}),
        ]
    )
    payload = chat_refinement._request_chat_refinement_payload(
        ai,
        "original focused update",
    )
    assert payload["reply"] == "updated"
    assert ai.calls == 2
    assert "Return one valid JSON object" in ai.prompts[-1]


def test_chat_contract_retry_and_exhausted_tracking() -> None:
    route = _route()
    architect = {"routes": [route]}
    invalid = "import React from 'react';\nexport default function HomePage(){return <main>bad</main>}\n"
    valid = _valid_page("CHAT_RETRY_SENTINEL")
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        ai = _SequenceAI(
            [json.dumps({"files": [{"path": route["component_file"], "content": valid}]})]
        )
        changes = chat_refinement._apply_chat_file_updates(
            workspace,
            {"files": [{"path": route["component_file"], "content": invalid}]},
            architect,
            ai_provider=ai,
            chat_prompt="original chat update",
        )
        written = (workspace / route["component_file"]).read_text(encoding="utf-8")
        assert ai.calls == 1
        assert "CHAT_RETRY_SENTINEL" in written
        assert validate_catalogue_page_content(written, route) == []
        assert consume_stubbed_paths(workspace) == []
        assert any("Updated" in change for change in changes)

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        ai = _SequenceAI(
            [
                json.dumps({"files": [{"path": route["component_file"], "content": invalid}]}),
                json.dumps({"files": [{"path": route["component_file"], "content": invalid}]}),
            ]
        )
        chat_refinement._apply_chat_file_updates(
            workspace,
            {"files": [{"path": route["component_file"], "content": invalid}]},
            architect,
            ai_provider=ai,
            chat_prompt="original chat update",
        )
        written = (workspace / route["component_file"]).read_text(encoding="utf-8")
        assert ai.calls == 2
        assert "deterministic catalogue contract scaffold" in written
        assert consume_stubbed_paths(workspace) == [route["component_file"]]


def test_malformed_fix_logs_metadata_not_customer_source() -> None:
    renderer = JinjaTemplateRenderer(TEMPLATES_DIR)
    secret = "PRIVATE_CUSTOMER_COPY_DO_NOT_LOG"
    ai = _SequenceAI([secret, secret])
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        page = workspace / "src/pages/HomePage.tsx"
        page.parent.mkdir(parents=True)
        page.write_text("export default function HomePage(){return null}\n", encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            codegen.fix_build_errors(
                workspace,
                "HomePage.tsx compile error",
                {"routes": []},
                ai,
                renderer,
            )
        logged = output.getvalue()
        assert secret not in logged
        dump_dir = workspace / ".bmv-debug" / "fix-agent"
        assert dump_dir.is_dir()
        dumps = list(dump_dir.glob("*.txt")) + list(dump_dir.glob("*.json"))
        assert dumps, "expected fix-agent diagnostics dump"
        dump_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in dumps)
        assert secret in dump_text  # full response is dumped to disk for ops
        # Customer source must not leak via stdout/stderr stream capture
        assert secret not in logged


def test_chat_scaffold_is_persisted_in_fallback_metadata() -> None:
    assert hasattr(chat_refinement.refine_preview_app_from_chat, "__wrapped__")
    assert hasattr(pipeline.generate_preview_app, "__wrapped__")
    # Global registry can retain entries from earlier tests in the same process.
    with fallback_module._stubbed_paths_lock:
        fallback_module._stubbed_paths_by_workspace.clear()
    route = _route()
    invalid = "export default function HomePage(){return <main>invalid</main>}\n"
    generated = {
        "preview_app": {
            "status": "ready",
            "url": "/old/",
            "routes": [route],
            "roles": [{"id": "customer", "defaultPath": "/"}],
        },
        "experience_plan": {
            "roles": [
                {
                    "id": "customer",
                    "label": "Customer",
                    "pages": [
                        {
                            "id": "home",
                            "title": "Home",
                            "skeleton_id": "public-home",
                            "section_slots": route["section_slots"],
                        }
                    ],
                }
            ]
        },
    }
    req = SimpleNamespace(
        generated_pages=json.dumps(generated),
        concept_name="Concept",
        preview_summary="Summary",
        preview_features="[]",
        business_fit_score=80,
        visual_demo_json=None,
        visual_demo_generated_at=None,
        reference_metadata=None,
        industry="services",
        business_name="Metadata Brand",
        updated_at=None,
    )

    class _DB:
        def commit(self):
            return None

    response = json.dumps(
        {
            "reply": "updated",
            "changes_made": [],
            "files": [{"path": route["component_file"], "content": invalid}],
        }
    )
    retry_response = json.dumps(
        {"files": [{"path": route["component_file"], "content": invalid}]}
    )
    ai = _SequenceAI([response, retry_response, retry_response])
    renderer = JinjaTemplateRenderer(TEMPLATES_DIR)
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        page = workspace / route["component_file"]
        page.parent.mkdir(parents=True)
        page.write_text(_valid_page("Before"), encoding="utf-8")
        (workspace / "dist").mkdir()
        (workspace / "dist/index.html").write_text("old", encoding="utf-8")
        # refine_preview_app_from_chat now lives in chat_rebuild; patch its
        # collaborators there (chat_refinement is just a re-export shim, and
        # patching attributes on it would not affect chat_rebuild's globals).
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
        try:
            chat_rebuild.get_request = lambda *_args: req
            chat_rebuild.get_workspace = lambda *_args: workspace
            chat_rebuild.business_info = lambda *_args: "business"
            chat_rebuild.get_images_for_industry = lambda *_args, **_kwargs: {}
            chat_rebuild.apply_workspace_guards = lambda *_args, **_kwargs: []
            chat_rebuild.run_build = lambda *_args, **_kwargs: (True, "ok")
            chat_rebuild._emit = lambda *_args, **_kwargs: None
            result = chat_refinement.refine_preview_app_from_chat(
                _DB(),
                42,
                "update page",
                ai,
                renderer,
            )
        finally:
            for name, value in originals.items():
                setattr(chat_rebuild, name, value)
        assert result["preview_rebuild_succeeded"] is True
        persisted = json.loads(req.generated_pages)
        assert persisted["preview_app"]["fallback_pages"] == [route["component_file"]]
        tracker_count = getattr(fallback_module, "active_fallback_tracker_count", None)
        assert callable(tracker_count), "fallback tracker lifecycle metric is required"
        assert tracker_count() == 0
        assert active_budget_registry_size() == 0
        assert active_operation_registry_size() == 0


def main() -> None:
    test_mock_synthesis_budget_exhaustion_preserves_existing_source()
    test_mock_synthesis_malformed_responses_preserve_existing_source()
    test_mock_synthesis_parser_rejects_balanced_malformed_typescript()
    test_mock_synthesis_rejects_valid_candidate_missing_needed_exports()
    test_mock_synthesis_valid_candidate_with_all_needed_exports_overwrites()
    test_mock_synthesis_fails_closed_without_typescript_tooling()
    test_aggregate_budget_stops_underlying_calls()
    test_concurrent_budget_wrappers_share_one_request_cap()
    test_same_request_operations_serialize_and_cleanup()
    test_one_budget_is_shared_across_codegen_and_critic()
    test_workspace_scaffold_tracking_is_isolated()
    test_contract_retry_excerpt_keeps_later_slot_context()
    test_malformed_critic_retries_once_then_preserves()
    test_parallel_critic_refine_accepts_tuple_work_items()
    test_malformed_chat_payload_retries_once()
    test_chat_contract_retry_and_exhausted_tracking()
    test_malformed_fix_logs_metadata_not_customer_source()
    test_chat_scaffold_is_persisted_in_fallback_metadata()
    print("task6 retry/budget tests passed")


if __name__ == "__main__":
    main()
