"""AppSpec contract-hook injection for pages and catalogue scaffolds."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.appspec.hooks import (  # noqa: E402
    ensure_workspace_appspec_hooks,
    inject_appspec_contract_hooks,
    page_hooks_present,
)
from app.application.appspec.projection import (  # noqa: E402
    select_preview_scope,
    to_architecture_seed,
)
from app.application.appspec.workspace_validation import (  # noqa: E402
    validate_app_spec_workspace,
)
from app.application.preview_app.catalogue_contract.scaffold import (  # noqa: E402
    minimal_catalogue_page_scaffold,
)
from app.domain.schemas.app_spec import AppSpec  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "app_spec" / "valid_booking.json"


def _spec() -> AppSpec:
    return AppSpec.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_inject_hooks_into_bare_page() -> None:
    source = """
export default function Page() {
  return (
    <main>
      <h1>Book</h1>
      <button type="button">Confirm</button>
    </main>
  );
}
"""
    out = inject_appspec_contract_hooks(
        source,
        page_id="PAGE-BOOK",
        action_ids=["ACTION-SUBMIT"],
        evidence_ids=["EVIDENCE-FORM", "EVIDENCE-CONFIRMATION"],
    )
    assert 'data-appspec-page="PAGE-BOOK"' in out
    assert 'data-appspec-action="ACTION-SUBMIT"' in out
    assert 'data-appspec-evidence="EVIDENCE-FORM"' in out
    assert 'data-appspec-evidence="EVIDENCE-CONFIRMATION"' in out
    assert page_hooks_present(
        out,
        page_id="PAGE-BOOK",
        action_ids=["ACTION-SUBMIT"],
        evidence_ids=["EVIDENCE-FORM", "EVIDENCE-CONFIRMATION"],
    )
    # Strip must sit inside the first return, not as a second dead return.
    assert out.count("return") == 1
    assert out.index("data-appspec-page") < out.index("</main>")


def test_inject_hooks_into_bare_jsx_return_is_reachable() -> None:
    """Regression: bare `return <jsx>;` must not leave hooks as dead code."""
    source = """
export default function Page() {
  return <main><p>Hi</p></main>;
}
"""
    out = inject_appspec_contract_hooks(
        source,
        page_id="PAGE-A",
        action_ids=["ACTION-1"],
        evidence_ids=["EV-1"],
    )
    assert 'data-appspec-page="PAGE-A"' in out
    assert 'data-appspec-action="ACTION-1"' in out
    assert out.count("return") == 1
    assert "return (" in out
    # Hooks appear before the original JSX root inside the same return.
    assert out.index("data-appspec-page") < out.index("<main>")
    assert page_hooks_present(
        out, page_id="PAGE-A", action_ids=["ACTION-1"], evidence_ids=["EV-1"]
    )


def test_inject_skips_helper_return_above_default_export() -> None:
    source = """
function helper() {
  return (
    <span>helper</span>
  );
}
export default function Page() {
  return (
    <main>{helper()}</main>
  );
}
"""
    out = inject_appspec_contract_hooks(
        source,
        page_id="PAGE-A",
        action_ids=["ACTION-1"],
        evidence_ids=[],
    )
    helper_return = out.index("function helper")
    page_export = out.index("export default function Page")
    hook_at = out.index('data-appspec-page="PAGE-A"')
    assert helper_return < page_export < hook_at


def test_inject_named_export_default_component() -> None:
    source = """
function BookPage() {
  return <main><p>Book</p></main>;
}
export default BookPage;
"""
    out = inject_appspec_contract_hooks(
        source,
        page_id="PAGE-BOOK",
        action_ids=["ACTION-SUBMIT"],
        evidence_ids=["EVIDENCE-FORM"],
    )
    assert out.count("return") == 1
    assert out.index('data-appspec-page="PAGE-BOOK"') < out.index("<main>")
    assert "export default BookPage" in out


def test_page_hooks_present_requires_attr_binding() -> None:
    # Id mentioned in copy must not satisfy the hook check.
    loose = '''
export default function Page() {
  return (
    <main>
      <p>See PAGE-A and ACTION-1 in the docs</p>
      <div data-appspec-page="OTHER" />
    </main>
  );
}
'''
    assert not page_hooks_present(
        loose, page_id="PAGE-A", action_ids=["ACTION-1"], evidence_ids=[]
    )


def test_scaffold_includes_appspec_hooks_from_route() -> None:
    route = {
        "path": "/book",
        "title": "Book",
        "skeleton_id": "public-booking",
        "surface": "public",
        "section_slots": ["hero", "booking", "cta", "footer"],
        "app_spec_page_id": "PAGE-BOOK",
        "page_id": "PAGE-BOOK",
        "action_ids": ["ACTION-SUBMIT"],
        "evidence_ids": ["EVIDENCE-FORM", "EVIDENCE-CONFIRMATION"],
    }
    content = minimal_catalogue_page_scaffold(
        "src/pages/BookPage.tsx",
        route,
        brand_name="Jane Art",
    )
    assert "deterministic catalogue contract scaffold" in content
    assert 'data-appspec-page="PAGE-BOOK"' in content
    assert 'data-appspec-action="ACTION-SUBMIT"' in content
    assert 'data-appspec-evidence="EVIDENCE-FORM"' in content


def test_ensure_workspace_hooks_heals_missing_attrs() -> None:
    spec = _spec()
    scope = select_preview_scope(spec)
    architecture = to_architecture_seed(spec, scope)
    assert architecture["routes"][0].get("evidence_ids"), "seed must carry evidence_ids"
    component = architecture["routes"][0]["component_file"]
    with tempfile.TemporaryDirectory() as raw:
        workspace = Path(raw)
        path = workspace / component
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "export default function Page() { return <main><p>Hi</p></main>; }\n",
            encoding="utf-8",
        )
        assert validate_app_spec_workspace(workspace, spec, scope, architecture)
        rewritten = ensure_workspace_appspec_hooks(
            workspace, spec, scope, architecture
        )
        assert component in rewritten
        assert validate_app_spec_workspace(workspace, spec, scope, architecture) == []


def main() -> None:
    test_inject_hooks_into_bare_page()
    test_inject_hooks_into_bare_jsx_return_is_reachable()
    test_inject_skips_helper_return_above_default_export()
    test_inject_named_export_default_component()
    test_page_hooks_present_requires_attr_binding()
    test_scaffold_includes_appspec_hooks_from_route()
    test_ensure_workspace_hooks_heals_missing_attrs()
    print("AppSpec hooks tests passed (7 tests)")


if __name__ == "__main__":
    main()
