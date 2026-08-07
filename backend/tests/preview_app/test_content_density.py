"""Phase 0's 0.8: the spec-level content-density record, pinned.

Three things are worth pinning and a fourth is pinned elsewhere:

1. The prose discriminators — a detector that quietly returns zero reads as
   "Phase 2 already landed" (the census's own warning).
2. The module and `scripts/measure/content_census.py` may never disagree: the
   archived DoD-2 baseline and the live metric are the same ruler or they are
   two numbers wearing one name.
3. Finalize stores the record, measured, beside `fallback_pages` — and a
   failed measurement is a recorded fact (`status: unmeasured`), never an
   absent key. Absent, "not measured" and "nobody recorded why" must stay
   three different readings.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.application.preview_app.content_density import (
    density_record,
    measure_content_density,
    prose_chars,
)
from app.application.preview_app.pipeline import finalize as finalize_module
from app.application.preview_app.pipeline.context import PipelineContext
from app.application.preview_app.quality_gate import GateReport

_SPEC = importlib.util.spec_from_file_location(
    "content_census_for_density_pin",
    Path(__file__).resolve().parents[2] / "scripts" / "measure" / "content_census.py",
)
assert _SPEC and _SPEC.loader
content_census = importlib.util.module_from_spec(_SPEC)
sys.modules["content_census_for_density_pin"] = content_census
_SPEC.loader.exec_module(content_census)


# ---------------------------------------------------------------- discriminators

def test_jsx_text_counts_and_class_lists_do_not() -> None:
    source = '<p className="flex items-center gap-4 md:grid-cols-2">A calm, premium feel for collectors.</p>'
    assert prose_chars(source) == len("A calm, premium feel for collectors.")


def test_hyphenated_lowercase_prose_is_not_tailwind() -> None:
    # The census's sweep-found case: one hyphenated token must not condemn it.
    assert prose_chars("<span>self-catering apartments available</span>") > 0


def test_paths_urls_and_import_lines_are_not_prose() -> None:
    source = (
        "import { Panel } from '@/ui';\n"
        "const a = '/gallery/collection';\n"
        "const b = 'https://example.com/some page';\n"
    )
    assert prose_chars(source) == 0


def test_prose_inside_classname_is_still_excluded() -> None:
    # The span exclusion, not the class-list heuristic, is what rejects this.
    assert prose_chars('<div className="Deliberately Prose Words">x</div>') == 0


# Deliberately no import-specifier exclusion test: the census's `_IMPORT_LINE`
# sub strips the clause only up to `from`, so a (contrived) multi-word module
# specifier counts under BOTH rulers — the battery below pins that agreement
# rather than "fixing" the archived DoD-2 method out from under its baseline.


def test_string_literal_prose_counts_outside_classname() -> None:
    source = "const tagline = 'Original oil paintings, layered by hand';"
    assert prose_chars(source) == len("Original oil paintings, layered by hand")


def test_module_and_census_script_agree() -> None:
    """The drift pin: same ruler, or red."""
    battery = [
        "<div>Plain words between tags</div>",
        '<p className="px-6 py-28 lg:px-12">Copy beside a class list</p>',
        "const t = `A template literal with real prose in it`;",
        "import { X } from 'lucide-react';\nconst path = './assets/img.png';",
        "<span>self-catering apartments available</span>",
        'className="flex gap-2" title="Two words"',
        '<div className="Deliberately Prose Words">x</div>',
        "import { Gallery } from 'the gallery of modern art';",
        "<div>{item.name}</div><p>Short.</p>",
    ]
    for source in battery:
        assert prose_chars(source) == content_census.prose_chars(source), source


# ---------------------------------------------------------------- measurement

def _workspace_with(pages: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="bmv-density-test-"))
    for rel, body in pages.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return root


_RICH = "<main><h1>Osteria Vinci</h1><p>" + "Wood-fired pizza and house-made pasta, served nightly. " * 8 + "</p></main>"
_THIN = "<div><p>Nothing here yet today.</p></div>"


def test_measure_reads_routed_pages_only_and_dedupes() -> None:
    workspace = _workspace_with({
        "src/pages/HomePage.tsx": _RICH,
        "src/pages/ThinPage.tsx": _THIN,
        "src/pages/UnroutedPage.tsx": _RICH,
    })
    routes = [
        {"path": "/", "component_file": "src/pages/HomePage.tsx"},
        {"path": "/alias", "component_file": "src/pages/HomePage.tsx"},
        {"path": "/thin", "component_file": "src/pages/ThinPage.tsx"},
        {"path": "/ghost", "component_file": "src/pages/MissingPage.tsx"},
    ]
    record = measure_content_density(workspace, routes)
    assert record["status"] == "measured"
    assert record["pages_measured"] == 2  # dedupe + missing file skipped + unrouted unread
    assert "src/pages/UnroutedPage.tsx" not in record["per_page"]
    assert record["pages_under_200_chars"] == ["src/pages/ThinPage.tsx"]
    assert record["prose_chars_total"] == sum(record["per_page"].values())
    assert record["prose_chars_median"] > 0


def test_measure_with_no_routes_is_measured_and_empty() -> None:
    record = measure_content_density(_workspace_with({}), [])
    assert record["status"] == "measured"
    assert record["pages_measured"] == 0
    assert record["prose_chars_total"] == 0
    assert record["prose_chars_median"] == 0


def test_density_record_failure_is_a_recorded_fact() -> None:
    record = density_record(None, [{"component_file": "src/pages/X.tsx"}])
    assert record["status"] == "unmeasured"
    assert record["reason"]


# ---------------------------------------------------------------- finalize wiring

class _DB:
    def commit(self) -> None:  # pragma: no cover - trivial
        pass


def _run_finalize(workspace: Path, routes: list[dict]) -> dict:
    ctx = PipelineContext(
        db=_DB(),
        request_id=7,
        ai_provider=None,
        template_renderer=None,
        app_spec_revision_id=None,
        req=SimpleNamespace(
            generated_pages=None,
            business_name="Osteria Vinci",
            concept_name="Osteria Vinci",
            updated_at=None,
        ),
    )
    ctx.workspace = workspace
    ctx.architect = {"routes": routes, "roles": []}
    ctx.plan = {"roles": []}
    ctx.manifest = {}
    ctx.design_system = {}
    ctx.enforce_app_spec = False
    ctx.ok = True
    ctx.base_path = "/api/preview-apps/7"

    originals = {
        name: getattr(finalize_module, name)
        for name in ("_emit", "run_quality_gate_with_heal", "ai_features_from_request")
    }
    try:
        finalize_module._emit = lambda *args, **kwargs: None
        finalize_module.run_quality_gate_with_heal = lambda *args, **kwargs: GateReport()
        finalize_module.ai_features_from_request = lambda *_a, **_k: []
        return finalize_module.run_finalize(ctx)
    finally:
        for name, value in originals.items():
            setattr(finalize_module, name, value)


def test_finalize_stores_a_measured_density_record() -> None:
    workspace = _workspace_with({"src/pages/HomePage.tsx": _RICH})
    (workspace / "dist").mkdir(parents=True, exist_ok=True)
    (workspace / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    result = _run_finalize(
        workspace,
        [{
            "path": "/",
            "page_id": "home",
            "role_id": "customer",
            "component_file": "src/pages/HomePage.tsx",
            "surface": "public",
            "skeleton_id": "public-home",
        }],
    )
    record = (result.get("preview_app") or {}).get("content_density")
    assert record is not None, "finalize stopped storing content_density"
    assert record["status"] == "measured"
    assert record["pages_measured"] == 1
    assert record["prose_chars_total"] > 200
