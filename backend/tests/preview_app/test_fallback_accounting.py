"""fallback_pages must be measured from source alone; policy only gates failure."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.catalogue_contract import minimal_catalogue_page_scaffold
from app.application.preview_app.fallback import clear_stubbed_paths, consume_stubbed_paths
from app.application.preview_app.pipeline import finalize as finalize_module
from app.application.preview_app.pipeline.context import PipelineContext
from app.application.preview_app.source_quality import (
    catalogue_page_is_thin,
    substantive_slot_count,
)

DENSE_PAGE = "src/pages/HomePage.tsx"
THIN_PAGE = "src/pages/ThinPage.tsx"
SCAFFOLD_MARKER = "deterministic catalogue contract scaffold"

_THIN_SOURCE = f"""// {SCAFFOLD_MARKER}
import {{ PublicShell, getSkeleton, SkeletonComposer, PublicNav, EmptyState }} from '@/ui';

const SKELETON_ID = "public-detail" as const;
const RECIPE_ORDER = ["body", "aside"] as const;

export default function ThinPage() {{
  const skeleton = getSkeleton(SKELETON_ID);
  const slots = {{
    body: (
      <EmptyState title="Nothing here yet" description="New records will appear here." />
    ),
    aside: (
      <EmptyState title="Nothing here yet" description="New records will appear here." />
    ),
  }};

  return (
    <PublicShell brandName={{"Jeanne Kassab Art"}} nav={{<PublicNav items={{[]}} />}}>
      <div data-skeleton={{skeleton.id}} data-appspec-page="thin">
        <SkeletonComposer skeletonId={{SKELETON_ID}} slots={{slots}} order={{RECIPE_ORDER}} />
      </div>
    </PublicShell>
  );
}}
"""


class _DB:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


def _dense_route() -> dict:
    return {
        "path": "/",
        "page_id": "home",
        "app_spec_page_id": "home",
        "role_id": "customer",
        "component_file": DENSE_PAGE,
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


def _thin_route() -> dict:
    return {
        "path": "/thin",
        "page_id": "thin",
        "app_spec_page_id": "thin",
        "role_id": "customer",
        "component_file": THIN_PAGE,
        "surface": "public",
        "skeleton_id": "public-detail",
        "section_slots": ["body", "aside"],
    }


def _write_workspace(workspace: Path, routes: list[dict]) -> None:
    (workspace / "dist").mkdir(parents=True, exist_ok=True)
    (workspace / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    pages = workspace / "src" / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    for route in routes:
        component = route["component_file"]
        if component == THIN_PAGE:
            source = _THIN_SOURCE
        else:
            source = minimal_catalogue_page_scaffold(
                component, route, brand_name="Jeanne Kassab Art"
            )
        (workspace / component).write_text(source, encoding="utf-8")


def _run(workspace: Path, routes: list[dict], *, enforce: bool) -> tuple[dict, list[tuple]]:
    events: list[tuple] = []
    ctx = PipelineContext(
        db=_DB(),
        request_id=7,
        ai_provider=None,
        template_renderer=None,
        app_spec_revision_id=None,
        req=SimpleNamespace(
            generated_pages=None,
            business_name="Jeanne Kassab Art",
            concept_name="Jeanne Kassab Art",
            updated_at=None,
        ),
    )
    ctx.workspace = workspace
    ctx.architect = {"routes": routes, "roles": []}
    ctx.plan = {"roles": []}
    ctx.manifest = {}
    ctx.design_system = {}
    ctx.enforce_app_spec = enforce
    ctx.ok = True
    ctx.base_path = "/api/preview-apps/7"

    originals = {
        name: getattr(finalize_module, name)
        for name in ("_emit", "run_quality_gate_with_heal", "ai_features_from_request")
    }
    try:
        finalize_module._emit = lambda *args, **kwargs: events.append(args[2:])
        finalize_module.run_quality_gate_with_heal = lambda *args, **kwargs: SimpleNamespace(
            ok=True, healed=[], issues=[]
        )
        finalize_module.ai_features_from_request = lambda *_args, **_kwargs: []
        result = finalize_module.run_finalize(ctx)
    finally:
        for name, value in originals.items():
            setattr(finalize_module, name, value)
    return result, events


def _codes(events: list[tuple]) -> list[str]:
    return [event[0] for event in events]


def test_thin_scaffold_density_is_the_discriminator() -> None:
    dense = minimal_catalogue_page_scaffold(
        DENSE_PAGE, _dense_route(), brand_name="Jeanne Kassab Art"
    )
    assert substantive_slot_count(dense) >= 2
    assert catalogue_page_is_thin(dense) is False
    assert substantive_slot_count(_THIN_SOURCE) == 0
    assert catalogue_page_is_thin(_THIN_SOURCE) is True


def test_scaffold_acceptance_requires_hooks_when_page_id_is_known() -> None:
    dense = minimal_catalogue_page_scaffold(
        DENSE_PAGE, _dense_route(), brand_name="Jeanne Kassab Art"
    )
    assert finalize_module._scaffold_page_is_acceptable(
        dense, page_id="home", action_ids=[], evidence_ids=[]
    )
    assert not finalize_module._scaffold_page_is_acceptable(
        dense, page_id="home", action_ids=["submit-inquiry"], evidence_ids=[]
    )
    assert finalize_module._scaffold_page_is_acceptable(
        dense, page_id="", action_ids=[], evidence_ids=[]
    )


def test_enforcement_off_records_only_thin_scaffolds() -> None:
    routes = [_dense_route(), _thin_route()]
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        _write_workspace(workspace, routes)
        result, events = _run(workspace, routes, enforce=False)
        assert result["preview_app"]["fallback_pages"] == [THIN_PAGE]
        assert result["preview_app"]["status"] == "ready"
        assert "contract_failed" not in _codes(events)
        assert consume_stubbed_paths(workspace) == []


def test_enforcement_off_never_fails_on_fallback_pages() -> None:
    routes = [_thin_route()]
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        _write_workspace(workspace, routes)
        result, events = _run(workspace, routes, enforce=False)
        assert result["preview_app"]["fallback_pages"] == [THIN_PAGE]
        assert result["preview_app"]["status"] == "ready"
        assert "contract_failed" not in _codes(events)
        assert "ready" in _codes(events)
        assert consume_stubbed_paths(workspace) == []


def test_enforcement_on_still_fails_on_thin_scaffold_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        _write_workspace(workspace, [_dense_route()])
        result, events = _run(workspace, [_dense_route()], enforce=True)
        assert result["preview_app"]["fallback_pages"] == []
        assert "contract_failed" not in _codes(events)
        assert consume_stubbed_paths(workspace) == []

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        clear_stubbed_paths(workspace)
        _write_workspace(workspace, [_thin_route()])
        result, events = _run(workspace, [_thin_route()], enforce=True)
        assert result["preview_app"]["fallback_pages"] == [THIN_PAGE]
        assert "contract_failed" in _codes(events)
        assert consume_stubbed_paths(workspace) == []
