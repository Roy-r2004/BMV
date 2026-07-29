"""The visual feedback loop must be able to fail something.

Covers the four ways it could not, and the deterministic imagery detector that
would have caught the app-36 fine-art-gallery-with-dental-photos failure with
no model call at all.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.codegen import critic as critic_mod  # noqa: E402
from app.application.preview_app.pipeline import visual_critic as vc  # noqa: E402
from app.infrastructure.templating.renderer import JinjaTemplateRenderer  # noqa: E402

TEMPLATES_DIR = BACKEND_DIR / "app" / "templates"

# Real Pexels photo ids installed into preview app 36 (a fine-art gallery).
# Every one of them is a dental-clinic stock photo.
APP36_DENTAL_URLS = [
    "https://images.pexels.com/photos/3845983/pexels-photo-3845983.jpeg?auto=compress&cs=tinysrgb&w=1400",
    "https://images.pexels.com/photos/6627349/pexels-photo-6627349.jpeg?auto=compress&cs=tinysrgb&w=1400",
    "https://images.pexels.com/photos/6627329/pexels-photo-6627329.jpeg?auto=compress&cs=tinysrgb&w=700",
    "https://images.pexels.com/photos/6627350/pexels-photo-6627350.jpeg?auto=compress&cs=tinysrgb&w=700",
    "https://images.pexels.com/photos/4269936/pexels-photo-4269936.jpeg?auto=compress&cs=tinysrgb&w=700",
    "https://images.pexels.com/photos/6627724/pexels-photo-6627724.jpeg?auto=compress&cs=tinysrgb&w=900",
]

# Literal query the dental pack's industry_tags produced for the art brief.
APP36_DENTAL_QUERIES = {
    "hero": "clinic dental dentist medical healthcare doctor orthodontics lifestyle wide atmosphere",
    "hero2": "clinic dental dentist medical healthcare doctor orthodontics interior workspace",
    "card1": "clinic dental dentist medical healthcare doctor orthodontics product detail close-up",
    "card2": "clinic dental dentist medical healthcare doctor orthodontics customer experience",
    "card3": "clinic dental dentist medical healthcare doctor orthodontics team service moment",
    "ambient": "clinic dental dentist medical healthcare doctor orthodontics ambient background texture",
}

ART_QUERIES = {
    "hero": "Jeanne Kassab Art fine art gallery painting studio hero lifestyle wide",
    "hero2": "Jeanne Kassab Art art gallery painting studio interior workspace",
    "card1": "Jeanne Kassab Art oil painting canvas product detail close-up",
}


class _CapturingVisionAI:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def ask_chat(self, _model, messages, **_kwargs):
        self.prompts.append(messages[-1]["content"])
        return self.response

    def ask_vision(self, _model, prompt, _image_path):
        self.prompts.append(prompt)
        return self.response


def _write_page(workspace: Path, rel: str, content: str) -> None:
    target = workspace / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


# --------------------------------------------------------------------------
# (e) "unavailable" is a measurement failure, never a pass
# --------------------------------------------------------------------------

def test_malformed_visual_critic_result_is_not_a_pass(tmp_path: Path) -> None:
    renderer = JinjaTemplateRenderer(TEMPLATES_DIR)
    _write_page(tmp_path, "src/pages/HomePage.tsx", "export default function Home() { return null }")
    ai = _CapturingVisionAI("this is not JSON at all")

    review = critic_mod.critique_file_visual(
        tmp_path,
        "src/pages/HomePage.tsx",
        str(tmp_path / "unused.png"),
        "Public storefront home",
        "Jeanne Kassab Art — fine art gallery",
        "Gallery-quiet, image-led",
        ai,
        renderer,
        {},
    )
    assert review["verdict"] == "unavailable"

    report = vc.VisualCritiqueReport()
    vc._absorb_review(report, "src/pages/HomePage.tsx", review)

    assert report.unmeasured == ["src/pages/HomePage.tsx"]
    assert report.reviewed == []
    assert report.measurement_failed is True
    assert report.verified is False
    codes = [f.code for f in report.findings]
    assert "visual_critique_unavailable" in codes


def test_screenshot_failure_is_recorded_as_unmeasured() -> None:
    report = vc.VisualCritiqueReport()
    vc._absorb_review(report, "src/pages/admin/DashboardPage.tsx", {"verdict": "unavailable"})
    assert report.measurement_failed is True
    assert report.verified is False


# --------------------------------------------------------------------------
# (b) scaffold pages are no longer exempt from visual review
# --------------------------------------------------------------------------

_SCAFFOLD_SOURCE = (
    "// deterministic catalogue contract scaffold\n"
    "export default function GalleryPage() { return null }\n"
)


def test_scaffold_page_is_still_screenshot_reviewed(tmp_path: Path) -> None:
    renderer = JinjaTemplateRenderer(TEMPLATES_DIR)
    _write_page(tmp_path, "src/pages/GalleryPage.tsx", _SCAFFOLD_SOURCE)
    ai = _CapturingVisionAI(
        json.dumps(
            {
                "score": 12,
                "verdict": "revise",
                "issues": [
                    "SEVERE: The hero photograph clearly shows a dental clinic, not a gallery."
                ],
                "revision_instructions": "Replace the imagery.",
            }
        )
    )

    review = critic_mod.critique_file_visual(
        tmp_path,
        "src/pages/GalleryPage.tsx",
        str(tmp_path / "unused.png"),
        "Featured works gallery",
        "Jeanne Kassab Art — fine art gallery",
        "Gallery-quiet, image-led",
        ai,
        renderer,
        {},
        business_identity="Business name: Jeanne Kassab Art\nIndustry: fine art gallery",
    )

    # The vision model was actually called for a scaffold page.
    assert ai.prompts, "scaffold page was exempted from visual review"
    assert "Jeanne Kassab Art" in ai.prompts[0]
    # Refine stays suppressed (freeform rewrite breaks the catalogue contract)...
    assert review["verdict"] == "ok"
    assert review["scaffold_locked"] is True
    # ...but the honest judgement survives and can block.
    assert review["visual_verdict"] == "revise"
    assert review["issues"]

    report = vc.VisualCritiqueReport()
    vc._absorb_review(report, "src/pages/GalleryPage.tsx", review)
    assert [f.code for f in report.blocking] == ["visual_defect_severe"]
    assert report.ok is False


def test_scaffold_page_reaches_the_vision_model(tmp_path: Path) -> None:
    renderer = JinjaTemplateRenderer(TEMPLATES_DIR)
    _write_page(tmp_path, "src/pages/GalleryPage.tsx", _SCAFFOLD_SOURCE)
    ai = _CapturingVisionAI(
        json.dumps({"score": 91, "verdict": "pass", "issues": [], "revision_instructions": ""})
    )

    critic_mod.critique_file_visual(
        tmp_path,
        "src/pages/GalleryPage.tsx",
        str(tmp_path / "unused.png"),
        "Featured works gallery",
        "Jeanne Kassab Art — fine art gallery",
        "Gallery-quiet, image-led",
        ai,
        renderer,
        {},
    )
    assert ai.prompts, "scaffold page short-circuited without a vision call"


def test_text_critic_keeps_its_scaffold_exemption(tmp_path: Path) -> None:
    renderer = JinjaTemplateRenderer(TEMPLATES_DIR)
    _write_page(tmp_path, "src/pages/GalleryPage.tsx", _SCAFFOLD_SOURCE)
    ai = _CapturingVisionAI("not JSON")

    review = critic_mod.critique_file(
        tmp_path,
        "src/pages/GalleryPage.tsx",
        "Featured works gallery",
        "Jeanne Kassab Art — fine art gallery",
        "Gallery-quiet, image-led",
        ai,
        renderer,
        {},
    )
    assert review["verdict"] == "ok"
    assert ai.prompts == []


def test_broken_local_image_blocks_but_unreachable_cdn_only_warns() -> None:
    report = vc.VisualCritiqueReport()
    vc._absorb_review(
        report,
        "src/pages/admin/DashboardPage.tsx",
        {
            "score": 90,
            "verdict": "pass",
            "issues": [],
            "revision_instructions": "",
            "broken_images": [
                "/placeholder-morning-mist.jpg",
                APP36_DENTAL_URLS[0],
            ],
        },
    )
    by_code = {f.code: f for f in report.findings}
    assert by_code["broken_rendered_image"].severity == vc.BLOCK
    assert by_code["broken_remote_image"].severity == vc.WARN
    assert [f.code for f in report.blocking] == ["broken_rendered_image"]


def test_severe_marker_and_low_score_both_block() -> None:
    assert vc._issue_severity(12, "revise", ["SEVERE: wrong industry photo"]) == vc.BLOCK
    assert vc._issue_severity(95, "revise", ["SEVERE: wrong industry photo"]) == vc.BLOCK
    assert vc._issue_severity(30, "revise", ["Cramped spacing"]) == vc.BLOCK
    assert vc._issue_severity(72, "revise", ["Cramped spacing"]) == vc.WARN
    assert vc._issue_severity(92, "pass", []) == vc.WARN


# --------------------------------------------------------------------------
# PART B: the prompt must ask whether the photography depicts THIS business
# --------------------------------------------------------------------------

def _render_visual_prompt(**overrides) -> str:
    renderer = JinjaTemplateRenderer(TEMPLATES_DIR)
    context = {
        "full_context": "Jeanne Kassab Art sells original oil paintings from a Beirut gallery.",
        "design_direction": "Gallery-quiet, image-led",
        "file_instructions": "Featured works gallery",
        "file_path": "src/pages/GalleryPage.tsx",
        "catalogue_page": True,
        "surface": "public",
        "skeleton_id": "public-catalogue",
        "skeleton_contract_json": "{}",
    }
    context.update(overrides)
    from app.application.prompts import PromptTemplate

    return renderer.render(PromptTemplate.PREVIEW_APP_VISUAL_CRITIC, **context)


def test_visual_critic_prompt_demands_subject_relevance() -> None:
    prompt = _render_visual_prompt(
        business_identity="Business name: Jeanne Kassab Art\nIndustry: fine art gallery"
    )
    assert "Jeanne Kassab Art" in prompt
    lowered = prompt.lower()
    for demand in (
        "depict this business",
        "different industry",
        "dental",
        "oil painting",
        "severe: ",
        "caption",
        "ambiguous",
        "confidence",
        "below 40",
        "under 80",
    ):
        assert demand in lowered, f"visual critic prompt never asks about: {demand}"


def test_visual_critic_prompt_renders_without_business_identity() -> None:
    prompt = _render_visual_prompt()
    assert prompt.strip()
    assert "read it from the business context" in prompt.lower()


# --------------------------------------------------------------------------
# (c) route selection must reach the ops/admin surface and honour a budget
# --------------------------------------------------------------------------

def _architect_with_deep_ops() -> dict:
    routes = [
        {"path": "/", "component_file": "src/pages/HomePage.tsx", "surface": "public"},
        {"path": "/gallery", "component_file": "src/pages/GalleryPage.tsx", "surface": "public"},
        {"path": "/artists", "component_file": "src/pages/ArtistsPage.tsx", "surface": "public"},
        {"path": "/about", "component_file": "src/pages/AboutPage.tsx", "surface": "public"},
        {"path": "/contact", "component_file": "src/pages/ContactPage.tsx", "surface": "public"},
        {"path": "/visit", "component_file": "src/pages/VisitPage.tsx", "surface": "public"},
        {"path": "/journal", "component_file": "src/pages/JournalPage.tsx", "surface": "public"},
        {"path": "/admin", "component_file": "src/pages/admin/DashboardPage.tsx", "surface": "ops"},
        {"path": "/admin/inventory", "component_file": "src/pages/admin/InventoryPage.tsx", "surface": "ops"},
    ]
    return {"routes": routes}


def test_route_selection_covers_ops_surface() -> None:
    selected = vc._select_visual_critique_routes(_architect_with_deep_ops())
    paths = [rt["path"] for rt in selected]
    assert len(paths) == vc.MAX_VISUAL_CRITIQUE_PAGES
    assert paths[0] == "/"
    assert "/admin" in paths, f"ops surface never reviewed: {paths}"


def test_route_selection_infers_ops_surface_without_a_surface_field() -> None:
    architect = _architect_with_deep_ops()
    for rt in architect["routes"]:
        rt.pop("surface")
    paths = [rt["path"] for rt in vc._select_visual_critique_routes(architect)]
    assert "/admin" in paths


def test_route_cap_is_configurable(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_VISUAL_CRITIC_MAX_PAGES", "9")
    assert vc._max_visual_critique_pages() == 9
    assert len(vc._select_visual_critique_routes(_architect_with_deep_ops())) == 9
    monkeypatch.setenv("PREVIEW_VISUAL_CRITIC_MAX_PAGES", "not-a-number")
    assert vc._max_visual_critique_pages() == vc.MAX_VISUAL_CRITIQUE_PAGES


def test_explicit_limit_still_respects_a_budget() -> None:
    assert len(vc._select_visual_critique_routes(_architect_with_deep_ops(), limit=2)) == 2


# --------------------------------------------------------------------------
# PART C: deterministic, zero-cost imagery/industry consistency
# --------------------------------------------------------------------------

def test_app36_art_business_with_dental_imagery_is_flagged() -> None:
    findings = vc.check_imagery_industry_consistency(
        industry="fine art gallery — original oil paintings",
        brand_name="Jeanne Kassab Art",
        imagery_queries=APP36_DENTAL_QUERIES,
        template_id="clinic-dental-home",
        image_urls=APP36_DENTAL_URLS,
    )
    assert len(findings) == 1
    finding = findings[0]
    assert finding.code == "imagery_industry_mismatch"
    assert finding.severity == vc.BLOCK
    assert "health" in finding.message and "art" in finding.message
    assert "6627349" in finding.message


def test_consistent_art_imagery_passes() -> None:
    assert (
        vc.check_imagery_industry_consistency(
            industry="fine art gallery — original oil paintings",
            brand_name="Jeanne Kassab Art",
            imagery_queries=ART_QUERIES,
            template_id="gallery-art-home",
            image_urls=APP36_DENTAL_URLS,
        )
        == []
    )


def test_dental_business_with_medical_imagery_is_not_a_mismatch() -> None:
    assert (
        vc.check_imagery_industry_consistency(
            industry="dental clinic",
            brand_name="Bright Smile Dentistry",
            imagery_queries=APP36_DENTAL_QUERIES,
            template_id="clinic-dental-home",
        )
        == []
    )


def test_ambiguous_business_never_produces_a_finding() -> None:
    assert (
        vc.check_imagery_industry_consistency(
            industry="",
            brand_name="Northwind",
            imagery_queries={"hero": "professional small business lifestyle wide"},
        )
        == []
    )
    assert vc.classify_industry_family("professional small business atmosphere") == ("", 0)


def test_imagery_findings_reads_installed_urls_from_the_workspace(tmp_path: Path) -> None:
    mock = "export const images = {\n" + "".join(
        f"  slot{i}: '{url}',\n" for i, url in enumerate(APP36_DENTAL_URLS)
    ) + "};\n"
    _write_page(tmp_path, "src/data/mock.ts", mock)

    assert vc.collect_installed_image_urls(tmp_path)[0].startswith("https://images.pexels.com/")

    findings = vc.imagery_findings(
        tmp_path,
        industry="fine art gallery — original oil paintings",
        brand_name="Jeanne Kassab Art",
        imagery_queries=APP36_DENTAL_QUERIES,
        template_id="clinic-dental-home",
    )
    assert [f.code for f in findings] == ["imagery_industry_mismatch"]
    assert "3845983" in findings[0].message


def test_missing_local_image_asset_is_flagged(tmp_path: Path) -> None:
    _write_page(
        tmp_path,
        "src/pages/admin/DashboardPage.tsx",
        '<img src="/placeholder-morning-mist.jpg" alt="Morning Mist thumbnail" />\n'
        '<img src="/catalogue-hero.jpg" alt="Gallery" />\n',
    )
    (tmp_path / "public").mkdir()
    (tmp_path / "public" / "catalogue-hero.jpg").write_bytes(b"jpeg")

    missing = vc.find_missing_local_image_assets(tmp_path)
    assert list(missing) == ["/placeholder-morning-mist.jpg"]
    assert missing["/placeholder-morning-mist.jpg"] == ["src/pages/admin/DashboardPage.tsx"]

    findings = vc.imagery_findings(tmp_path, industry="fine art gallery", brand_name="Jeanne Kassab Art")
    assert [f.code for f in findings] == ["missing_image_asset"]
    assert findings[0].severity == vc.BLOCK

    (tmp_path / "public" / "placeholder-morning-mist.jpg").write_bytes(b"jpeg")
    assert vc.find_missing_local_image_assets(tmp_path) == {}


# --------------------------------------------------------------------------
# (a) the verdict is now durable state a later phase can gate on
# --------------------------------------------------------------------------

def test_report_persists_and_exposes_gate_issues(tmp_path: Path) -> None:
    report = vc.VisualCritiqueReport()
    report.findings.extend(
        vc.check_imagery_industry_consistency(
            industry="fine art gallery",
            brand_name="Jeanne Kassab Art",
            imagery_queries=APP36_DENTAL_QUERIES,
            template_id="clinic-dental-home",
            image_urls=APP36_DENTAL_URLS,
        )
    )
    report.add("visual_defect", "cramped hero", path="src/pages/HomePage.tsx", severity=vc.WARN)
    assert report.ok is False

    vc.write_visual_critique_report(tmp_path, report)
    assert (tmp_path / vc.VISUAL_CRITIQUE_REPORT_FILE).is_file()

    issues = vc.visual_critique_gate_issues(tmp_path)
    assert [code for code, _msg, _path in issues] == ["imagery_industry_mismatch"]

    reloaded = vc.load_visual_critique_report(tmp_path)
    assert reloaded.ok is False
    assert len(reloaded.findings) == 2


def test_absent_report_is_empty_and_does_not_block(tmp_path: Path) -> None:
    assert vc.load_visual_critique_report(tmp_path).ok is True
    assert vc.visual_critique_gate_issues(tmp_path) == []
    (tmp_path / vc.VISUAL_CRITIQUE_REPORT_FILE).write_text("{not json", encoding="utf-8")
    assert vc.visual_critique_gate_issues(tmp_path) == []


def test_run_visual_critique_returns_a_report_with_no_routes(tmp_path: Path) -> None:
    mock = "export const images = {\n" + "".join(
        f"  slot{i}: '{url}',\n" for i, url in enumerate(APP36_DENTAL_URLS)
    ) + "};\n"
    _write_page(tmp_path, "src/data/mock.ts", mock)

    report = vc._run_visual_critique(
        None, 36, tmp_path, {"routes": []},
        {
            "imagery_roles": APP36_DENTAL_QUERIES,
            "industry_template_id": "clinic-dental-home",
            "industry": "fine art gallery — original oil paintings",
        },
        {}, "Jeanne Kassab Art sells original oil paintings.", {}, {},
        "Jeanne Kassab Art", "#111111", "#222222", "Inter", "/api/preview-apps/36",
        None, None,
    )
    assert report.ok is False
    assert [f.code for f in report.blocking] == ["imagery_industry_mismatch"]
    assert vc.visual_critique_gate_issues(tmp_path)
