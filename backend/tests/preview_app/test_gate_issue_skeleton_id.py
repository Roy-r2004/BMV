"""Gate failures name the skeleton the failing page resolved to.

Pre-flight question 5 could not be settled offline for exactly one reason:
`listing_not_schedule_rail` fired four times across trios 2-5, all on
`ServicesPage.tsx` (x3) and `TreatmentsPage.tsx` (x1), and a page with that title
resolves to `public-catalog` **or** `public-service` depending on its purpose
text. Only `public-catalog` ever overflowed the contract budget that `0082f5f`
fixed, so whether that fix could have moved this code turns entirely on which
skeleton each fire was — and nothing recorded it. One gate code was being counted
as one number when it is two different defects.

Two halves, and this file drives both, because the previous round of telemetry
tests all asked "given a reason, does the field say so" and none asked whether
anything set a reason:

  - `GateIssue.skeleton_id`, resolved centrally in `GateReport` so a new gate code
    gets it without its author remembering to;
  - `preview_app["gate_issues"]`, which `scripts/measure/analyse.py` has read
    since it was written and which **no run has ever stored**.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.application.preview_app.quality_gate import GateReport, evaluate_quality_gate

_SERVICES_PAGE = """
import { composeSkeletonLayout } from '@/ui/SkeletonComposer';

export default function ServicesPage() {
  return <div>Our treatments</div>;
}
"""


def _workspace(tmp_path: Path, page_source: str) -> Path:
    (tmp_path / "dist").mkdir(parents=True)
    (tmp_path / "dist" / "index.html").write_text("<html></html>")
    pages = tmp_path / "src" / "pages"
    pages.mkdir(parents=True)
    (pages / "ServicesPage.tsx").write_text(page_source)
    (pages / "AiFeaturesPage.tsx").write_text("export default function P(){return null;}\n")
    (tmp_path / "src" / "data").mkdir(parents=True)
    (tmp_path / "src" / "data" / "mock.ts").write_text("export const brand = {};\n")
    return tmp_path


def _route(skeleton_id: str) -> dict:
    return {
        "path": "/services",
        "component_file": "src/pages/ServicesPage.tsx",
        "skeleton_id": skeleton_id,
        "surface": "public",
        "title": "Services",
        "purpose": "Browse our full schedule of classes and sessions",
    }


def _fires(tmp_path: Path, skeleton_id: str) -> list:
    ws = _workspace(tmp_path, _SERVICES_PAGE)
    report = evaluate_quality_gate(
        ws, {"routes": [_route(skeleton_id)]}, require_ai_hub=False
    )
    return [i for i in report.issues if i.code == "listing_not_schedule_rail"]


def test_a_catalog_services_page_fire_names_public_catalog(tmp_path: Path) -> None:
    fires = _fires(tmp_path, "public-catalog")

    assert len(fires) == 1
    assert fires[0].path == "src/pages/ServicesPage.tsx"
    assert fires[0].skeleton_id == "public-catalog"


def test_a_service_services_page_fire_names_public_service(tmp_path: Path) -> None:
    """Same code, same file name, same message — a different defect.

    This one is writer judgment and the contract-clipping fix cannot have moved it.
    Without the skeleton on the issue these two rows are identical.
    """
    fires = _fires(tmp_path, "public-service")

    assert len(fires) == 1
    assert fires[0].skeleton_id == "public-service"
    assert fires[0].path == _fires(tmp_path / "b", "public-catalog")[0].path, (
        "the two fires are indistinguishable on every other field"
    )


def test_an_issue_with_no_page_carries_no_skeleton() -> None:
    report = GateReport(architect={"routes": [_route("public-catalog")]})

    report.fail("no_dist", "Preview dist/index.html missing")
    report.fail("ai_advisor_no_wildcard", "missing catch-all", "src/App.tsx")

    assert [i.skeleton_id for i in report.issues] == ["", ""]


def test_a_report_built_without_an_architect_still_records_issues() -> None:
    """Fail open on the skeleton, never on the issue.

    A gate that raised because it could not resolve a skeleton would trade a
    reported defect for an unreported crash.
    """
    report = GateReport()

    report.fail("no_pages", "No pages generated under src/pages/", "src/pages/X.tsx")
    report.warn("thin_page", "short", "src/pages/X.tsx")

    assert report.issues[0].skeleton_id == ""
    assert report.warnings[0].skeleton_id == ""
    assert not report.ok


def test_warnings_carry_the_skeleton_too(tmp_path: Path) -> None:
    report = GateReport(architect={"routes": [_route("public-catalog")]})

    report.warn("thin_page", "short", "src/pages/ServicesPage.tsx")

    assert report.warnings[0].skeleton_id == "public-catalog"


def test_the_persisted_record_carries_every_code_with_its_skeleton() -> None:
    """The consumer half, driven through the function `finalize` actually calls.

    An earlier draft of this test built the record dict itself and asserted on its
    own copy — green with the publication deleted. That is the shape session 7's
    sweep caught six times and it is worth naming here rather than in a commit
    message.
    """
    from app.application.preview_app.pipeline.finalize import gate_issue_summary
    from app.application.preview_app.quality_gate import GateIssue

    gate = GateReport(
        issues=[
            GateIssue(
                "listing_not_schedule_rail",
                "Listing page missing ScheduleRail",
                "src/pages/ServicesPage.tsx",
                "public-catalog",
            ),
            GateIssue("no_dist", "Preview dist/index.html missing"),
        ],
        warnings=[GateIssue("thin_page", "short", "src/pages/X.tsx", "public-home")],
    )

    # It has to survive the JSON round trip `generated_pages` puts it through.
    revived = json.loads(json.dumps(gate_issue_summary(gate)))

    by_code = {i["code"]: i for i in revived["gate_issues"]}
    assert set(by_code) == {"listing_not_schedule_rail", "no_dist"}
    assert by_code["listing_not_schedule_rail"]["skeleton_id"] == "public-catalog"
    assert by_code["listing_not_schedule_rail"]["path"] == "src/pages/ServicesPage.tsx"
    assert by_code["no_dist"]["skeleton_id"] == ""
    assert revived["gate_warnings"] == [
        {"code": "thin_page", "path": "src/pages/X.tsx", "skeleton_id": "public-home"}
    ]


def test_a_long_gate_message_is_bounded_in_the_record() -> None:
    """`generated_pages` is one JSON column and a repair log has landed in it
    before. 200 chars is enough to identify the defect and not enough to bloat."""
    from app.application.preview_app.pipeline.finalize import gate_issue_summary
    from app.application.preview_app.quality_gate import GateIssue

    gate = GateReport(issues=[GateIssue("x", "y" * 5_000, "src/pages/X.tsx")])

    assert len(gate_issue_summary(gate)["gate_issues"][0]["message"]) == 200
