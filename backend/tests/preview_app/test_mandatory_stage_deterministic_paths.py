"""1.12 — a MANDATORY stage takes its deterministic path instead of shipping NULL.

Five runs have shipped nothing at all on this class: **74, 92, 94** (`architect`
raising after an expensive `appspec`) and **101, 102** (a provider outage across
`build_experience_plan`'s whole chain, then `synthesize_mock_data` raising the
same way). `MANDATORY_STAGES`' contract is that such a stage *"takes its
deterministic path"*, and outside the AppSpec branch there was none — so the
designed outcome, *a degraded preview that ships*, was unreachable and the
pipeline shipped `NULL` instead.

Four pieces, each pinned here:

a. **`architect`.** `plan_phase` rescued only under `enforce_app_spec`, which is
   never true in shadow — the standing mode. `{}` is not a substantive route
   table, so `apply_product_kind_to_architect` injects the kind's whole
   blueprint eleven lines later. The enforced path must not move a byte.
b. **`synthesize_mock_data`.** `write_plumbing_mock` has already written a
   complete `mock.ts` in the plan phase. A provider failure should keep it.
c. **A run that built a workspace stores a `preview_app`.** 101 and 102 built
   workspaces and stored nothing, leaving the only evidence in a docker volume.
d. **`build_experience_plan`.** With the caller's kind contract there is an
   honest minimal plan; without one the raise stands as an explicit bound.

The healthy-path tests here are not decoration. Every one of these fixes is a
widened `except`, and the failure mode of a widened `except` is that it starts
catching the normal case — so each piece is paired with a fixture proving an
untroubled run is bit-for-bit what it was.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.application.preview_app.pipeline import plan_phase as plan_phase_mod
from app.application.preview_app.pipeline.context import PipelineContext
from app.application.services import request_deadline as rd


# --------------------------------------------------------------------------
# (a) the architect's deterministic path
# --------------------------------------------------------------------------


class _Renderer:
    def render(self, *_args, **_kwargs) -> str:
        return "prompt"


class _AI:
    def ask_chat(self, *_args, **_kwargs) -> str:
        return "{}"


def _plan_ctx(tmp_path: Path, *, enforce: bool = False) -> PipelineContext:
    ctx = PipelineContext(
        db=SimpleNamespace(commit=lambda: None, rollback=lambda: None),
        request_id=101,
        ai_provider=_AI(),
        template_renderer=_Renderer(),
        app_spec_revision_id=None,
        req=SimpleNamespace(
            business_name="Osteria Vinci",
            business_description="A twelve-table trattoria serving regional Italian food.",
            description="A twelve-table trattoria serving regional Italian food.",
            concept_name="Osteria Vinci",
            main_problem="",
            desired_outcome="",
            target_customers="",
            preview_features=None,
            mvp_blueprint="blueprint",
            generated_pages=None,
            updated_at=None,
        ),
    )
    ctx.industry = "restaurant"
    ctx.enforce_app_spec = enforce
    return ctx


def _run_plan_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    architect_result,
    plan: dict | None = None,
    enforce: bool = False,
) -> PipelineContext:
    """Drive the real `run_plan_phase`, stubbing only I/O and model calls.

    Everything that decides the outcome — `resolve_product_kind_contract`,
    `apply_product_kind_to_architect`, `_normalize_architect` — is the
    production function. A test that re-implemented the blueprint injection
    would be measuring its own copy of it.
    """
    from app.application.preview_app import ai_feature_surfaces as surfaces_mod

    def _architect(*_args, **_kwargs):
        if isinstance(architect_result, Exception):
            raise architect_result
        return architect_result

    monkeypatch.setattr(plan_phase_mod, "_emit", lambda *a, **k: None)
    monkeypatch.setattr(plan_phase_mod, "gather_full_context", lambda *a, **k: "context")
    monkeypatch.setattr(
        plan_phase_mod,
        "build_experience_plan",
        lambda *a, **k: json.loads(json.dumps(plan or {"roles": []})),
    )
    monkeypatch.setattr(plan_phase_mod, "build_design_manifest", lambda *a, **k: {})
    monkeypatch.setattr(plan_phase_mod, "call_architect", _architect)
    monkeypatch.setattr(plan_phase_mod, "prepare_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(plan_phase_mod, "write_plumbing_mock", lambda *a, **k: None)
    monkeypatch.setattr(plan_phase_mod, "clear_stubbed_paths", lambda *a, **k: None)
    monkeypatch.setattr(surfaces_mod, "ensure_ai_feature_route", lambda *a, **k: None)
    monkeypatch.setattr(surfaces_mod, "ensure_ai_feature_surfaces", lambda *a, **k: None)

    ctx = _plan_ctx(tmp_path, enforce=enforce)
    plan_phase_mod.run_plan_phase(ctx)
    return ctx


def test_a_failed_architect_ships_the_blueprint_instead_of_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Requests 74, 92 and 94, in shadow mode — the mode every run uses."""

    with rd.request_deadline_scope(101, total_seconds=600) as deadline:
        ctx = _run_plan_phase(
            tmp_path,
            monkeypatch,
            architect_result=ValueError("Architect agent failed to produce valid JSON"),
        )

    paths = [r.get("path") for r in ctx.architect.get("routes") or []]
    assert paths, "the architect failed and the run still has no routes at all"
    assert "/" in paths, (
        "no root route — assemble.py routes the catch-all to `/`, so an app "
        "without one redirects to nothing"
    )
    assert len(ctx.architect.get("files_to_generate") or []) >= 2

    assert ("architect", "call_failed_deterministic_blueprint") in {
        (d["stage"], d["reason"]) for d in deadline.degradations()
    }, "the run degraded silently — a blueprint preview must not look like a planned one"


def test_the_blueprint_fallback_is_not_hardcoded_to_one_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dentist must not be rescued with an art gallery.

    The fallback route table is the *resolved contract's*, and `booking_service`
    is gap-filled `_booking_pages()` — home, `/services`, `/book`. Session 12
    published two wrong numbers by assuming every brief resolves to
    `storefront`; this is the fixture that would have caught it.
    """

    ctx = _plan_ctx(tmp_path)
    ctx.industry = "dentist"
    ctx.req.business_description = "A dental clinic taking patient appointments and bookings."
    ctx.req.description = ctx.req.business_description

    from app.application.preview_app import ai_feature_surfaces as surfaces_mod

    monkeypatch.setattr(plan_phase_mod, "_emit", lambda *a, **k: None)
    monkeypatch.setattr(plan_phase_mod, "gather_full_context", lambda *a, **k: "context")
    monkeypatch.setattr(plan_phase_mod, "build_experience_plan", lambda *a, **k: {"roles": []})
    monkeypatch.setattr(plan_phase_mod, "build_design_manifest", lambda *a, **k: {})
    monkeypatch.setattr(
        plan_phase_mod,
        "call_architect",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("provider HTTP 408")),
    )
    monkeypatch.setattr(plan_phase_mod, "prepare_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(plan_phase_mod, "write_plumbing_mock", lambda *a, **k: None)
    monkeypatch.setattr(plan_phase_mod, "clear_stubbed_paths", lambda *a, **k: None)
    monkeypatch.setattr(surfaces_mod, "ensure_ai_feature_route", lambda *a, **k: None)
    monkeypatch.setattr(surfaces_mod, "ensure_ai_feature_surfaces", lambda *a, **k: None)

    plan_phase_mod.run_plan_phase(ctx)

    paths = {r.get("path") for r in ctx.architect.get("routes") or []}
    assert "/book" in paths, f"a booking brief was rescued with {sorted(paths)}"
    assert "/gallery" not in paths, (
        "the booking clinic was handed the storefront blueprint — the fallback "
        "is reading a default instead of the resolved contract"
    )


def test_a_healthy_architect_is_untouched_by_the_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The normal case: the model answered, and its answer is what ships.

    A widened `except` that also swallows success would pass every test above
    and destroy every real run.
    """

    declared = {
        "routes": [
            {"path": "/", "title": "Home", "component_file": "src/pages/HomePage.tsx"},
            {"path": "/menu", "title": "Menu", "component_file": "src/pages/MenuPage.tsx"},
            {
                "path": "/reservations",
                "title": "Reservations",
                "component_file": "src/pages/ReservationsPage.tsx",
            },
        ],
        "files_to_generate": [
            {"path": "src/pages/HomePage.tsx", "kind": "page"},
            {"path": "src/pages/MenuPage.tsx", "kind": "page"},
            {"path": "src/pages/ReservationsPage.tsx", "kind": "page"},
        ],
    }

    with rd.request_deadline_scope(103, total_seconds=600) as deadline:
        ctx = _run_plan_phase(tmp_path, monkeypatch, architect_result=declared)

    paths = [r.get("path") for r in ctx.architect.get("routes") or []]
    for declared_path in ("/", "/menu", "/reservations"):
        assert declared_path in paths, (
            f"{declared_path} was declared by the architect and is not in the "
            f"shipped table {paths}"
        )
    assert not [
        d for d in deadline.degradations() if d["stage"] == "architect"
    ], "a run whose architect answered recorded an architect degradation"


def test_the_enforced_path_still_rescues_from_the_appspec_and_not_the_blueprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one path that must stay byte-identical.

    Under enforcement the rescue is the AppSpec projection, which is the whole
    point of an enforced contract: routes traceable to the approved spec. The
    shadow fallback must not reach into this branch, and the enforced branch
    must not start recording a degradation it never recorded before.
    """

    seed_routes = [
        {"path": "/", "title": "Home", "component_file": "src/pages/HomePage.tsx"},
        {"path": "/menu", "title": "Menu", "component_file": "src/pages/MenuPage.tsx"},
    ]

    monkeypatch.setattr(
        plan_phase_mod,
        "to_architecture_seed",
        lambda *a, **k: {"routes": [dict(r) for r in seed_routes], "files_to_generate": []},
    )
    monkeypatch.setattr(
        plan_phase_mod, "merge_architecture_enrichment", lambda seed, arch: seed
    )
    monkeypatch.setattr(plan_phase_mod, "to_experience_plan_seed", lambda *a, **k: {"roles": []})

    ctx = _plan_ctx(tmp_path, enforce=True)
    ctx.app_spec_result = SimpleNamespace(spec={}, revision_record=None)
    ctx.app_spec_scope = SimpleNamespace()

    from app.application.preview_app import ai_feature_surfaces as surfaces_mod

    monkeypatch.setattr(plan_phase_mod, "_emit", lambda *a, **k: None)
    monkeypatch.setattr(plan_phase_mod, "gather_full_context", lambda *a, **k: "context")
    monkeypatch.setattr(plan_phase_mod, "build_experience_plan", lambda *a, **k: {"roles": []})
    monkeypatch.setattr(plan_phase_mod, "build_design_manifest", lambda *a, **k: {})
    monkeypatch.setattr(
        plan_phase_mod,
        "call_architect",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("provider HTTP 408")),
    )
    monkeypatch.setattr(plan_phase_mod, "prepare_workspace", lambda *a, **k: tmp_path)
    monkeypatch.setattr(plan_phase_mod, "write_plumbing_mock", lambda *a, **k: None)
    monkeypatch.setattr(plan_phase_mod, "clear_stubbed_paths", lambda *a, **k: None)
    monkeypatch.setattr(surfaces_mod, "ensure_ai_feature_route", lambda *a, **k: None)
    monkeypatch.setattr(surfaces_mod, "ensure_ai_feature_surfaces", lambda *a, **k: None)

    with rd.request_deadline_scope(99, total_seconds=600) as deadline:
        plan_phase_mod.run_plan_phase(ctx)

    paths = [r.get("path") for r in ctx.architect.get("routes") or []]
    assert "/menu" in paths, (
        "the enforced rescue lost the AppSpec's own route — the shadow fallback "
        "has reached into the enforced branch"
    )
    assert not [
        d for d in deadline.degradations() if d["stage"] == "architect"
    ], "the enforced rescue started recording a degradation it never recorded before"


# --------------------------------------------------------------------------
# (b) synthesize_mock_data keeps the plumbing mock
# --------------------------------------------------------------------------


def _workspace_with_a_page(tmp_path: Path, plumbing: str) -> Path:
    src = tmp_path / "src"
    (src / "pages").mkdir(parents=True)
    (src / "data").mkdir(parents=True)
    (src / "pages" / "HomePage.tsx").write_text(
        "import { seed } from '../data/mock';\nexport default function HomePage() { return null }\n",
        encoding="utf-8",
    )
    (src / "data" / "mock.ts").write_text(plumbing, encoding="utf-8")
    return tmp_path


_PLUMBING = "export const seed = { hero: { title: 'Osteria Vinci' } };\n"


class _DeadProvider:
    def ask_chat(self, *_args, **_kwargs) -> str:
        raise RuntimeError("HTTP 408 upstream request timeout")


def test_a_dead_provider_keeps_the_plumbing_mock_instead_of_killing_the_run(
    tmp_path: Path,
) -> None:
    """Requests 101 and 102. Both had this exact file and stored nothing."""

    from app.application.preview_app.codegen import mock as mock_mod

    workspace = _workspace_with_a_page(tmp_path, _PLUMBING)

    with rd.request_deadline_scope(101, total_seconds=600) as deadline:
        result = mock_mod.synthesize_mock_data(
            workspace, "context", {}, {}, {}, {}, _DeadProvider(), _Renderer(),
        )

    assert result is False
    assert (workspace / "src" / "data" / "mock.ts").read_text(encoding="utf-8") == _PLUMBING, (
        "the plumbing mock was damaged by a synthesis that never produced anything"
    )
    assert ("codegen", "mock_synthesis_failed_plumbing_mock_kept") in {
        (d["stage"], d["reason"]) for d in deadline.degradations()
    }, "the mock was not synthesized and nothing says so"


def test_the_codegen_phase_survives_a_dead_mock_synthesis(tmp_path: Path) -> None:
    """The seam that actually killed 101 and 102 — `run_codegen_phase` line 325.

    Asserting only on `synthesize_mock_data` proves the function returns False
    and proves nothing about whether the phase still raises around it.
    """

    from app.application.preview_app.codegen import mock as mock_mod

    workspace = _workspace_with_a_page(tmp_path, _PLUMBING)
    assert (
        mock_mod.synthesize_mock_data(
            workspace, "context", {}, {}, {}, {}, _DeadProvider(), _Renderer(),
        )
        is False
    )
    # `if synthesize_mock_data(...)` — the call site's whole contract is that a
    # falsey answer is survivable. It cannot be, if the call raises.


def test_a_healthy_mock_synthesis_still_rewrites_the_file(tmp_path: Path) -> None:
    """The normal case: the model answered and its mock is what ships."""

    from app.application.preview_app.codegen import mock as mock_mod

    workspace = _workspace_with_a_page(tmp_path, _PLUMBING)
    synthesized = "export const seed = { hero: { title: 'Synthesized' } };\n"

    class _GoodProvider:
        def ask_chat(self, *_args, **_kwargs) -> str:
            return synthesized

    with rd.request_deadline_scope(97, total_seconds=600) as deadline:
        result = mock_mod.synthesize_mock_data(
            workspace, "context", {}, {}, {}, {}, _GoodProvider(), _Renderer(),
        )

    assert result is True
    assert "Synthesized" in (workspace / "src" / "data" / "mock.ts").read_text(encoding="utf-8")
    assert not deadline.degradations(), (
        "a healthy synthesis recorded a degradation — the catch is firing on the "
        "normal path"
    )


def test_a_rejected_mock_is_still_a_rejection_and_not_a_degradation(
    tmp_path: Path,
) -> None:
    """The pre-existing `return False` must keep its own meaning.

    An unusable *answer* is not a provider outage: the model was reached, the
    ask was adjudicated, and turning that into a degradation would make the two
    indistinguishable in the record.
    """

    from app.application.preview_app.codegen import mock as mock_mod

    workspace = _workspace_with_a_page(tmp_path, _PLUMBING)

    class _JunkProvider:
        def ask_chat(self, *_args, **_kwargs) -> str:
            return "not typescript at all"

    with rd.request_deadline_scope(98, total_seconds=600) as deadline:
        result = mock_mod.synthesize_mock_data(
            workspace, "context", {}, {}, {}, {}, _JunkProvider(), _Renderer(),
        )

    assert result is False
    assert (workspace / "src" / "data" / "mock.ts").read_text(encoding="utf-8") == _PLUMBING
    assert not [
        d for d in deadline.degradations() if d["reason"].startswith("mock_synthesis_failed")
    ], "a rejected answer was recorded as a provider failure"


# --------------------------------------------------------------------------
# (c) a run that built a workspace stores a preview_app
# --------------------------------------------------------------------------


def _crash_ctx(tmp_path: Path | None, *, generated_pages: str | None = None):
    committed: list[str] = []
    req = SimpleNamespace(generated_pages=generated_pages, updated_at=None)

    def _commit() -> None:
        committed.append(req.generated_pages)

    ctx = PipelineContext(
        db=SimpleNamespace(commit=_commit, rollback=lambda: None),
        request_id=102,
        ai_provider=None,
        template_renderer=None,
        app_spec_revision_id=None,
        req=req,
    )
    ctx.workspace = tmp_path
    ctx.architect = {
        "routes": [{"path": "/", "component_file": "src/pages/HomePage.tsx"}],
        "design_direction": "warm",
    }
    return ctx, committed


def test_a_crashed_run_that_built_a_workspace_leaves_a_record(tmp_path: Path) -> None:
    """Requests 101 and 102 built workspaces and stored nothing at all."""

    from app.application.preview_app.pipeline.finalize import store_crash_record

    ctx, committed = _crash_ctx(tmp_path)

    with rd.request_deadline_scope(102, total_seconds=600):
        assert store_crash_record(ctx, RuntimeError("HTTP 408 upstream request timeout")) is True

    assert committed, "nothing was committed — the record exists only in memory"
    stored = json.loads(committed[-1])["preview_app"]
    assert stored["status"] == "failed"
    assert stored["url"] is None
    assert stored["withheld_reason"] == "pipeline_crashed"
    assert "HTTP 408" in stored["crash_error"], (
        "the record says the run failed and not what killed it"
    )
    assert stored["routes"], "the routes the run had built were thrown away"


def test_the_crash_record_is_never_a_fake_ready(tmp_path: Path) -> None:
    """`status` keeps its three-value vocabulary and this run is not servable."""

    from app.application.preview_app.pipeline.finalize import crash_record

    record = crash_record(exc=RuntimeError("boom"), architect={"routes": []})
    assert record["status"] != "ready"
    assert record["url"] is None
    assert record["withheld_reason"] is not None


def test_a_crash_before_any_workspace_stores_nothing(tmp_path: Path) -> None:
    """The bound, stated: with no workspace there is no run to describe."""

    from app.application.preview_app.pipeline.finalize import store_crash_record

    ctx, committed = _crash_ctx(None)
    assert store_crash_record(ctx, RuntimeError("boom")) is False
    assert not committed


def test_a_served_preview_is_not_overwritten_by_a_failed_rebuild(tmp_path: Path) -> None:
    """A chat rebuild that crashes must not mark the user's working site failed."""

    from app.application.preview_app.pipeline.finalize import store_crash_record

    previous = json.dumps(
        {"preview_app": {"status": "ready", "url": "/api/preview-apps/102/"}}
    )
    ctx, committed = _crash_ctx(tmp_path, generated_pages=previous)

    assert store_crash_record(ctx, RuntimeError("boom")) is False
    assert not committed, "a ready record was overwritten by a crashed rebuild"


def test_the_bookkeeping_never_replaces_the_real_exception(tmp_path: Path) -> None:
    """It runs inside an `except` whose exception is about to be re-raised."""

    from app.application.preview_app.pipeline.finalize import store_crash_record

    ctx, _ = _crash_ctx(tmp_path)

    def _explode() -> None:
        raise RuntimeError("the database is gone too")

    ctx.db = SimpleNamespace(commit=_explode, rollback=lambda: None)
    assert store_crash_record(ctx, RuntimeError("the real failure")) is False


def test_the_orchestrator_records_then_re_raises(tmp_path: Path, monkeypatch) -> None:
    """The caller's retry-once path depends on the exception still arriving."""

    from app.application.preview_app.pipeline import orchestrator as orch

    seen: list[BaseException] = []
    monkeypatch.setattr(
        orch, "run_appspec_gate", lambda ctx: (_ for _ in ()).throw(RuntimeError("nope"))
    )
    monkeypatch.setattr(orch, "store_crash_record", lambda ctx, exc: seen.append(exc) or True)

    with pytest.raises(RuntimeError, match="nope"):
        orch._run_v1_pipeline(
            SimpleNamespace(commit=lambda: None, rollback=lambda: None),
            102,
            None,
            None,
            app_spec_revision_id=None,
            req=SimpleNamespace(generated_pages=None, updated_at=None),
            generator_version="v1",
        )

    assert seen, "the run crashed and nothing was asked to record it"


# --------------------------------------------------------------------------
# (d) build_experience_plan's deterministic path
# --------------------------------------------------------------------------


def _planner_req(business_name: str, context: str):
    """A request the planner can actually read — the real model, unpersisted.

    A hand-rolled `SimpleNamespace` is the wrong fake here: every column it
    forgets raises `AttributeError` *inside* the planner loop, which the new
    fallback then catches, so the **healthy** fixture takes the degraded path
    and still looks green. This file did exactly that twice — first on
    `concept_name`, then on `needs_ai` — which is blind spot 5 (a test that
    adapts until it passes) arriving through the fixture instead of the
    assertion. `Request()` cannot drift from the columns the code reads.
    """
    from app.domain.models.request import Request

    return Request(
        business_name=business_name,
        concept_name=business_name,
        industry="general business",
        business_description=context,
        email="owner@example.com",
        mvp_blueprint="blueprint",
    )


def _dead_planner_plan(context: str, *, contract=None):
    from app.application.preview_app.product_kind import resolve_product_kind_contract
    from app.application.services.page_experience import build_experience_plan

    req = _planner_req("Northgate Dental", context)
    return build_experience_plan(
        req,
        {},
        "#0f766e",
        "#134e4a",
        _DeadProvider(),
        _Renderer(),
        fallback_contract=(
            contract if contract is not None else resolve_product_kind_contract(context)
        ),
    )


def test_a_dead_planner_returns_the_kinds_blueprint_rather_than_raising() -> None:
    """Requests 101 and 102 — the raise that ended both."""

    from app.application.services.page_experience import _plan_meets_minimums

    with rd.request_deadline_scope(101, total_seconds=600) as deadline:
        plan = _dead_planner_plan("boutique art gallery selling original paintings")

    pages = [p for r in plan.get("roles") or [] for p in (r.get("pages") or [])]
    assert pages, "the deterministic plan has no pages, so nothing downstream can build"
    ok, issues = _plan_meets_minimums(plan, [])
    assert ok, f"the deterministic plan fails the pipeline's own minimums: {issues}"
    assert plan.get("design_system", {}).get("primary_color") == "#0f766e", (
        "the caller's resolved brand colour was dropped by the fallback"
    )
    assert ("planning", "planner_failed_deterministic_blueprint") in {
        (d["stage"], d["reason"]) for d in deadline.degradations()
    }


def test_the_deterministic_plan_follows_the_contract_not_a_default() -> None:
    from app.application.preview_app.product_kind import resolve_product_kind_contract

    contract = resolve_product_kind_contract(
        "accounting practice ledger, invoices and reconciliation software"
    )
    with rd.request_deadline_scope(102, total_seconds=600):
        plan = _dead_planner_plan("accounting ledger and invoices", contract=contract)

    ids = {p.get("id") for r in plan.get("roles") or [] for p in (r.get("pages") or [])}
    assert "invoices" in ids, f"an accounting brief was given {sorted(ids)}"


def test_an_accepted_appspec_still_outranks_the_blueprint() -> None:
    """Order is load-bearing, and this is the pair the ordering protects.

    Under enforcement the accepted spec *is* the product contract, and a design
    outage must reduce visual specificity rather than replace the inventory with
    a blueprint. The 1.12 fallback is deliberately placed **after** the
    canonical-seed rescue for that reason.
    """

    from app.application.preview_app.product_kind import resolve_product_kind_contract
    from app.application.services import page_experience as pe

    seed = {
        "roles": [
            {
                "id": "ROLE-GUEST",
                "label": "Guest",
                "pages": [
                    {"id": "home", "title": "Home"},
                    {"id": "private-events", "title": "Private Events"},
                ],
            }
        ]
    }

    with rd.request_deadline_scope(99, total_seconds=600):
        plan = pe.build_experience_plan(
            _planner_req("Osteria Vinci", "a trattoria"),
            {},
            "#0f766e",
            "#134e4a",
            _DeadProvider(),
            _Renderer(),
            canonical_seed=seed,
            fallback_contract=resolve_product_kind_contract("trattoria restaurant"),
        )

    titles = {p.get("title") for r in plan.get("roles") or [] for p in (r.get("pages") or [])}
    assert "Private Events" in titles, (
        f"the approved spec's own pages were replaced by the blueprint: {sorted(titles)}"
    )


def test_a_caller_with_no_contract_still_gets_the_explicit_bound() -> None:
    """`role_pages` and the chat rebuild pass no contract; nothing changes there.

    The alternative — inventing a kind for a caller that never resolved one —
    would ship a gallery to whoever asked last.
    """

    from app.application.services.page_experience import build_experience_plan

    req = _planner_req("Northgate Dental", "a dental clinic")
    with pytest.raises(ValueError, match="Experience planner failed"):
        build_experience_plan(req, {}, "#0f766e", "#134e4a", _DeadProvider(), _Renderer())


def test_a_healthy_planner_is_not_replaced_by_the_blueprint() -> None:
    """The normal case: the planner answered, and its plan is what is used."""

    from app.application.preview_app.product_kind import resolve_product_kind_contract
    from app.application.services import page_experience as pe

    authored = {
        "roles": [
            {
                "id": "ROLE-GUEST",
                "label": "Guest",
                "pages": [
                    {"id": "home", "title": "Home"},
                    {"id": "menu", "title": "Our Menu"},
                ],
            }
        ],
        "design_system": {"primary_color": "#b62bb6"},
    }

    class _GoodProvider:
        def ask_chat(self, *_args, **_kwargs) -> str:
            return json.dumps(authored)

    req = _planner_req("Osteria Vinci", "a trattoria")

    with rd.request_deadline_scope(95, total_seconds=600) as deadline:
        plan = pe.build_experience_plan(
            req,
            {},
            "#0f766e",
            "#134e4a",
            _GoodProvider(),
            _Renderer(),
            fallback_contract=resolve_product_kind_contract("trattoria restaurant"),
        )

    titles = {p.get("title") for r in plan.get("roles") or [] for p in (r.get("pages") or [])}
    assert "Our Menu" in titles, (
        f"the planner's own page inventory was replaced by the blueprint: {sorted(titles)}"
    )
    assert not [
        d for d in deadline.degradations() if d["stage"] == "planning"
    ], "a run whose planner answered recorded a planning degradation"
