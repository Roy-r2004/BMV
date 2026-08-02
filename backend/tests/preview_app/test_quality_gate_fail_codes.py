"""Positive coverage for every quality-gate fail code that evaluates alone.

Twelve of nineteen `.fail("…")` literals under `preview_app/` had no test that
named them. A gate that fires in production and is silent in CI is scenery.

Each test below constructs the minimal workspace that triggers one code and
asserts that code appears in the report. The collection-time guard at the
bottom refuses to let a new literal land without its own test.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from app.application.preview_app.quality_gate import evaluate_quality_gate
from app.application.preview_app.workspace import write_file

BACKEND_DIR = Path(__file__).resolve().parents[2]
PREVIEW_APP = BACKEND_DIR / "app" / "application" / "preview_app"
TESTS_DIR = BACKEND_DIR / "tests"

_GOOD_HUB = """\
// plan AI feature hub
import { AiFeatureDeck } from '@/ui';
import { aiFeatures } from '@/data/mock';
export default function AiFeaturesPage() {
  return <AiFeatureDeck features={aiFeatures} brandName="Brand" />;
}
"""

_CLEAN_MOCK = (
    'export const navigation = { public: [{ path: "/", label: "Home" }] };\n'
    "export const aiFeatures = [] as const;\n"
)


def _ws(tmp_path: Path, *, with_dist: bool = True) -> Path:
    (tmp_path / "src" / "pages").mkdir(parents=True)
    (tmp_path / "src" / "data").mkdir(parents=True)
    if with_dist:
        (tmp_path / "dist").mkdir(parents=True)
        (tmp_path / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    return tmp_path


def _baseline(ws: Path, *, hub: bool = True) -> None:
    if hub:
        write_file(ws, "src/pages/AiFeaturesPage.tsx", _GOOD_HUB)
    write_file(ws, "src/pages/HomePage.tsx", "export default function HomePage(){return null}")
    write_file(ws, "src/App.tsx", "export default function App(){return null}")
    write_file(ws, "src/data/mock.ts", _CLEAN_MOCK)


def _codes(report) -> set[str]:
    return {i.code for i in report.issues}


# --------------------------------------------------------------------------- #
# the twelve that had no name in any test — plus no_pages, which the
# collection-time guard also requires
# --------------------------------------------------------------------------- #


def test_a_preview_without_dist_cannot_pass_the_gate(tmp_path: Path) -> None:
    """`dist/index.html` is what the customer opens. No file → no site."""
    ws = _ws(tmp_path, with_dist=False)
    _baseline(ws)
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert "no_dist" in _codes(report)


def test_a_workspace_with_no_pages_fails_the_gate(tmp_path: Path) -> None:
    """An empty `src/pages/` is not a preview — the gate must refuse it."""
    ws = _ws(tmp_path)
    write_file(ws, "src/App.tsx", "export default function App(){return null}")
    write_file(ws, "src/data/mock.ts", _CLEAN_MOCK)
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert "no_pages" in _codes(report)


def test_a_missing_ai_hub_fails_the_gate(tmp_path: Path) -> None:
    """When AI features are required, AiFeaturesPage.tsx must exist."""
    ws = _ws(tmp_path)
    _baseline(ws, hub=False)
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert "ai_hub_missing" in _codes(report)


def test_a_page_linking_to_an_invented_ai_advisor_step_fails_the_gate(
    tmp_path: Path,
) -> None:
    """href=/ai-advisor/skill-assessment is a dead route the hub never serves."""
    ws = _ws(tmp_path)
    _baseline(ws)
    write_file(
        ws,
        "src/pages/MysteryPage.tsx",
        'export default function MysteryPage(){ return <a href={"/ai-advisor/skill-assessment"}>x</a> }',
    )
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert "dead_ai_step_link" in _codes(report)


def test_a_schedule_listing_without_schedule_rail_fails_the_gate(tmp_path: Path) -> None:
    """Classes/services listings that render as a home clone fail the gate."""
    ws = _ws(tmp_path)
    _baseline(ws)
    rel = "src/pages/ClassesPage.tsx"
    write_file(
        ws,
        rel,
        "export default function ClassesPage(){ return <div>Class schedule</div> }",
    )
    architect = {
        "routes": [
            {
                "path": "/classes",
                "component_file": rel,
                "title": "Classes & Workshops",
                "skeleton_id": "public-service",
                "surface": "public",
            }
        ]
    }
    report = evaluate_quality_gate(ws, architect, require_ai_hub=True)
    assert "listing_not_schedule_rail" in _codes(report)


def test_a_directory_listing_without_directory_face_fails_the_gate(
    tmp_path: Path,
) -> None:
    """A /doctors page that looks like a homepage is not a directory face."""
    ws = _ws(tmp_path)
    _baseline(ws)
    rel = "src/pages/DoctorsPage.tsx"
    write_file(
        ws,
        rel,
        # Has content so the gate reads it, but no CatalogGrid/ProductShowcase
        # and no directory-listing scaffold marker — so the face check fails.
        "export default function DoctorsPage(){ return <div>Our team</div> }",
    )
    architect = {
        "routes": [
            {
                "path": "/doctors",
                "component_file": rel,
                "title": "Our Doctors",
                "skeleton_id": "public-service",
                "surface": "public",
            }
        ]
    }
    report = evaluate_quality_gate(ws, architect, require_ai_hub=True)
    assert "listing_not_directory_face" in _codes(report)


def test_a_confirmation_page_without_confirm_stage_fails_the_gate(
    tmp_path: Path,
) -> None:
    """A utility confirmation stub is not ConfirmStage — the demo journey ends."""
    ws = _ws(tmp_path)
    _baseline(ws)
    rel = "src/pages/BookingConfirmationPage.tsx"
    write_file(
        ws,
        rel,
        """
export default function BookingConfirmationPage() {
  return (
    <div className="public-utility">
      <PageHeader title="Confirmed" />
      <p>Signature package · Ready to confirm</p>
    </div>
  );
}
""",
    )
    architect = {
        "routes": [
            {
                "path": "/booking/confirmation",
                "component_file": rel,
                "title": "Booking Confirmed",
                "skeleton_id": "public-utility",
                "surface": "public",
            }
        ]
    }
    report = evaluate_quality_gate(ws, architect, require_ai_hub=True)
    assert "confirm_not_stage" in _codes(report)


def test_an_ai_advisor_route_without_wildcard_fails_the_gate(tmp_path: Path) -> None:
    """`/ai-advisor` alone leaves `/ai-advisor/anything` falling through to `*`."""
    ws = _ws(tmp_path)
    _baseline(ws)
    write_file(
        ws,
        "src/App.tsx",
        'import AiAdvisorChatPage from "./pages/AiAdvisorChatPage";\n'
        '          <Route path="/ai-advisor" element={<AiAdvisorChatPage />} />\n',
    )
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert "ai_advisor_no_wildcard" in _codes(report)


def test_an_ops_home_with_marketing_hero_fails_the_gate(tmp_path: Path) -> None:
    """SaaS/ops home must not ship the storefront MarketingHero."""
    ws = _ws(tmp_path)
    _baseline(ws)
    rel = "src/pages/DashboardPage.tsx"
    write_file(
        ws,
        rel,
        """
export default function DashboardPage() {
  return (
    <OpsShell>
      <MarketingHero title="Welcome" />
      <StatCard label="MRR" value="$1" />
    </OpsShell>
  );
}
""",
    )
    architect = {
        "routes": [
            {
                "path": "/",
                "component_file": rel,
                "surface": "ops",
                "skeleton_id": "ops-dashboard",
                "title": "Dashboard",
            }
        ]
    }
    report = evaluate_quality_gate(ws, architect, require_ai_hub=True)
    assert "ops_home_marketing_hero" in _codes(report)


def test_an_ops_home_without_ops_shell_fails_the_gate(tmp_path: Path) -> None:
    """An ops home that never mounts OpsShell is wearing the wrong chrome."""
    ws = _ws(tmp_path)
    _baseline(ws)
    rel = "src/pages/DashboardPage.tsx"
    write_file(
        ws,
        rel,
        """
export default function DashboardPage() {
  return (
    <div>
      <StatCard label="MRR" value="$1" />
    </div>
  );
}
""",
    )
    architect = {
        "routes": [
            {
                "path": "/",
                "component_file": rel,
                "surface": "ops",
                "skeleton_id": "ops-dashboard",
                "title": "Dashboard",
            }
        ]
    }
    report = evaluate_quality_gate(ws, architect, require_ai_hub=True)
    assert "ops_home_missing_shell" in _codes(report)


def test_an_ops_home_without_kpi_density_fails_the_gate(tmp_path: Path) -> None:
    """Ops home without StatCard/DataTable is a thin marketing landing."""
    ws = _ws(tmp_path)
    _baseline(ws)
    rel = "src/pages/DashboardPage.tsx"
    write_file(
        ws,
        rel,
        """
export default function DashboardPage() {
  return (
    <OpsShell>
      <p>Welcome back</p>
    </OpsShell>
  );
}
""",
    )
    architect = {
        "routes": [
            {
                "path": "/",
                "component_file": rel,
                "surface": "ops",
                "skeleton_id": "ops-dashboard",
                "title": "Dashboard",
            }
        ]
    }
    report = evaluate_quality_gate(ws, architect, require_ai_hub=True)
    assert "ops_home_thin" in _codes(report)


def test_a_cluttered_public_nav_fails_the_gate(tmp_path: Path) -> None:
    """Public nav with too many items (or deep paths) is unusable chrome."""
    ws = _ws(tmp_path)
    _baseline(ws)
    items = ",\n".join(
        f'  {{ "path": "/page-{i}", "label": "Page {i}" }}' for i in range(10)
    )
    write_file(
        ws,
        "src/data/mock.ts",
        # Gate regex anchors on quoted `"public"` — the JSON shape sync_mock writes.
        f'export const navigation = {{ "public": [\n{items}\n] }};\n'
        "export const aiFeatures = [] as const;\n",
    )
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert "nav_clutter" in _codes(report)


def test_an_unfilled_placeholder_in_mock_fails_the_gate(tmp_path: Path) -> None:
    """`[Artist Name]` in mock.ts ships as visible copy — no vision call needed."""
    ws = _ws(tmp_path)
    _baseline(ws)
    write_file(
        ws,
        "src/data/mock.ts",
        'export const navigation = { public: [{ path: "/", label: "Home" }] };\n'
        'export const brand = { tagline: "Discover fine art by [Artist Name]" };\n'
        "export const aiFeatures = [] as const;\n",
    )
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert "placeholder_content_shipped" in _codes(report)


# --------------------------------------------------------------------------- #
# collection-time guard — every .fail("literal") must be named by a test
# --------------------------------------------------------------------------- #


def _fail_code_literals() -> set[str]:
    codes: set[str] = set()
    for path in PREVIEW_APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "fail"):
                continue
            if not node.args:
                continue
            arg0 = node.args[0]
            if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                codes.add(arg0.value)
    return codes


def test_every_quality_gate_fail_code_is_named_by_a_test() -> None:
    """A new `report.fail("code", …)` under preview_app must land with a test.

    Scans every `.fail(` call whose first argument is a string literal, then
    requires that literal to appear as a quoted string somewhere under
    `backend/tests/`. Dynamic `report.fail(code, …)` sites are out of scope —
    those codes are owned by their own emitters' tests.
    """
    codes = _fail_code_literals()
    assert codes, "expected fail-code literals under preview_app/"

    corpus = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in TESTS_DIR.rglob("*.py")
    )
    missing = sorted(
        code
        for code in codes
        if not re.search(rf'["\']{re.escape(code)}["\']', corpus)
    )
    assert not missing, (
        "quality-gate fail codes with no test naming them: "
        + ", ".join(missing)
    )
