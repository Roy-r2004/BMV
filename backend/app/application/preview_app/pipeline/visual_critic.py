"""Post-build visual critique via screenshots, plus zero-cost imagery detectors.

Two independent mechanisms answer the same question — "is this app showing the
right pictures for this business?":

1. `imagery_findings` — deterministic, no model call. Compares the industry the
   business reads as against the industry the *installed* imagery was sourced
   for (the recorded imagery queries / template id), and checks that every
   local image reference resolves to a file that actually exists.
2. `_run_visual_critique` — screenshots the built app and asks a vision model.

Both write into one `VisualCritiqueReport` that is persisted next to the
workspace, so a later phase can turn findings into hard gate failures without
re-running anything.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.application.preview_app.build import run_build
from app.application.preview_app.codegen.critic import critique_file_visual, refine_file
from app.application.preview_app.parallel import parallel_map
from app.application.preview_app.safety.orchestrator import apply_workspace_guards
from app.application.preview_app.screenshot import capture_route_visual
from app.application.preview_app.workspace import list_source_files, read_file, restore_source, snapshot_source
from app.application.services.progress import emit as _emit
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.infrastructure.logging import get_logger

log = get_logger("PreviewPipeline")

MAX_VISUAL_CRITIQUE_PAGES = 6  # default; override with PREVIEW_VISUAL_CRITIC_MAX_PAGES
VISUAL_CRITIQUE_REPORT_FILE = "_bmv_visual_critique.json"
# Scores at or below this, or an issue the critic marked SEVERE, are treated as
# "do not ship" rather than "polish it".
VISUAL_BLOCK_SCORE = 40

BLOCK = "block"
WARN = "warn"

_SEVERE_ISSUE_RE = re.compile(r"^\s*(?:severe|critical|blocker)\s*[:\-]", re.I)
_OPS_PATH_MARKERS = ("/admin", "/ops", "/owner", "/staff", "/manage", "/dashboard", "/back-office")
_IMAGE_SUFFIXES = ("jpg", "jpeg", "png", "webp", "avif", "gif", "svg")
_REMOTE_IMAGE_RE = re.compile(r"https://[^\s\"'`<>()]+", re.I)
_REMOTE_IMAGE_HOSTS = ("pexels.com", "unsplash.com", "cloudinary.com", "imgix.net")
_LOCAL_IMAGE_REF_RE = re.compile(
    r"""["'`](/[^"'`\s?#]+\.(?:""" + "|".join(_IMAGE_SUFFIXES) + r"""))["'`?#]""",
    re.I,
)

# Independent industry signal table. Deliberately NOT imported from
# services/industry_images.py: this detector must keep screaming if the
# imagery resolver's own keyword table regresses.
_INDUSTRY_SIGNALS: dict[str, tuple[str, ...]] = {
    "art": (
        "art", "arts", "artist", "artists", "artwork", "artworks", "fine art", "gallery",
        "galleries", "painting", "paintings", "painter", "oil painting", "canvas", "canvases",
        "sculpture", "sculptures", "exhibition", "exhibitions", "atelier", "curator", "curated",
        "print", "prints", "portrait", "portraits", "landscape painting",
    ),
    "dental": (
        "dental", "dentist", "dentists", "dentistry", "orthodontic", "orthodontics",
        "orthodontist", "teeth", "tooth", "denture", "dentures", "implant", "implants",
        "oral surgery", "hygienist", "smile makeover",
    ),
    "medical": (
        "clinic", "clinics", "medical", "medicine", "doctor", "doctors", "physician",
        "hospital", "healthcare", "health care", "patient", "patients", "nurse",
        "surgery", "surgeon", "pharmacy", "physiotherapy", "chiropractic", "therapy",
    ),
    "beauty": (
        "beauty", "salon", "spa", "facial", "facials", "skincare", "skin care", "cosmetic",
        "aesthetic", "aesthetics", "hair", "haircut", "barber", "nail", "nails", "lash",
        "brow", "massage", "waxing",
    ),
    "fitness": (
        "fitness", "gym", "gyms", "workout", "training", "trainer", "yoga", "pilates",
        "crossfit", "athlete", "athletic", "strength", "cardio", "bootcamp",
    ),
    "food": (
        "food", "restaurant", "restaurants", "cafe", "coffee", "bakery", "bakeries",
        "catering", "caterer", "kitchen", "chef", "dining", "bistro", "menu", "pizzeria",
        "brewery", "cocktail", "pastry",
    ),
    "legal": (
        "law", "lawyer", "lawyers", "attorney", "attorneys", "legal", "litigation",
        "solicitor", "notary", "paralegal", "counsel",
    ),
    "finance": (
        "accounting", "accountant", "bookkeeping", "tax", "taxes", "audit", "finance",
        "financial", "insurance", "wealth", "investment", "investments", "payroll",
    ),
    "tech": (
        "software", "saas", "startup", "developer", "developers", "engineering",
        "platform", "api", "devops", "cloud", "cybersecurity", "data platform",
    ),
    "realestate": (
        "real estate", "realtor", "realty", "property", "properties", "mortgage",
        "apartment", "apartments", "listing", "listings", "broker", "landlord", "tenant",
    ),
    "education": (
        "school", "schools", "tutor", "tutoring", "classroom", "curriculum", "student",
        "students", "teacher", "academy", "course", "courses", "lesson", "lessons",
        "university", "kindergarten",
    ),
    "retail": (
        "retail", "boutique", "apparel", "clothing", "fashion", "shop", "store",
        "storefront", "ecommerce", "merchandise", "footwear", "jewelry", "jewellery",
    ),
    "automotive": (
        "automotive", "auto repair", "car", "cars", "vehicle", "vehicles", "mechanic",
        "garage", "tyre", "tire", "dealership", "detailing",
    ),
    "pets": (
        "pet", "pets", "veterinary", "veterinarian", "vet clinic", "grooming", "kennel",
        "dog", "dogs", "cat", "cats",
    ),
    "trades": (
        "plumbing", "plumber", "electrician", "hvac", "roofing", "roofer", "carpentry",
        "contractor", "construction", "renovation", "landscaping", "handyman",
    ),
    "events": (
        "wedding", "weddings", "event", "events", "photography", "photographer",
        "videography", "florist", "florals", "venue", "catering hall", "dj",
    ),
    "travel": (
        "hotel", "hotels", "hostel", "resort", "travel", "tour", "tours", "booking",
        "airbnb", "guesthouse", "tourism",
    ),
}

# Categories that must not be reported as mismatched against one another.
_CATEGORY_FAMILY: dict[str, str] = {
    "dental": "health",
    "medical": "health",
}

# Words that appear in every generated imagery query and carry no industry meaning.
_QUERY_NOISE = (
    "lifestyle", "wide", "atmosphere", "interior", "workspace", "product", "detail",
    "close", "up", "customer", "experience", "team", "service", "moment", "ambient",
    "background", "texture", "professional", "small", "business", "hero",
)

_MIN_SIGNAL_HITS = 2


@dataclass(frozen=True)
class VisualFinding:
    """One defect the visual feedback loop is willing to stand behind."""

    code: str
    message: str
    path: str = ""
    severity: str = BLOCK

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "severity": self.severity,
        }


@dataclass
class VisualCritiqueReport:
    findings: list[VisualFinding] = field(default_factory=list)
    reviewed: list[str] = field(default_factory=list)
    unmeasured: list[str] = field(default_factory=list)
    refined: list[str] = field(default_factory=list)
    scores: dict[str, int] = field(default_factory=dict)

    @property
    def blocking(self) -> list[VisualFinding]:
        return [f for f in self.findings if f.severity == BLOCK]

    @property
    def ok(self) -> bool:
        return not self.blocking

    @property
    def measurement_failed(self) -> bool:
        """True when at least one page could not actually be judged.

        An unavailable critic result is a measurement failure, never a pass —
        callers must not read `ok` as "the pages were checked and are fine"
        without also checking this.
        """
        return bool(self.unmeasured)

    @property
    def verified(self) -> bool:
        return bool(self.reviewed) and not self.unmeasured

    def add(self, code: str, message: str, path: str = "", severity: str = BLOCK) -> None:
        self.findings.append(
            VisualFinding(code=code, message=message, path=path, severity=severity)
        )

    def to_dict(self) -> dict:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "reviewed": list(self.reviewed),
            "unmeasured": list(self.unmeasured),
            "refined": list(self.refined),
            "scores": dict(self.scores),
        }

    @classmethod
    def from_dict(cls, value) -> "VisualCritiqueReport":
        if not isinstance(value, dict):
            return cls()
        findings = []
        for raw in value.get("findings") or []:
            if not isinstance(raw, dict) or not raw.get("code"):
                continue
            findings.append(
                VisualFinding(
                    code=str(raw.get("code")),
                    message=str(raw.get("message") or ""),
                    path=str(raw.get("path") or ""),
                    severity=BLOCK if raw.get("severity") != WARN else WARN,
                )
            )
        scores = value.get("scores")
        return cls(
            findings=findings,
            reviewed=[str(p) for p in (value.get("reviewed") or [])],
            unmeasured=[str(p) for p in (value.get("unmeasured") or [])],
            refined=[str(p) for p in (value.get("refined") or [])],
            scores={str(k): int(v) for k, v in (scores or {}).items() if isinstance(v, int)},
        )


def _env_int(name: str, default: int) -> int:
    raw = getattr(settings, name, None)
    if raw is None:
        raw = os.getenv(name)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return default


def _env_flag(name: str, default: bool) -> bool:
    raw = getattr(settings, name, None)
    if raw is None:
        raw = os.getenv(name)
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _max_visual_critique_pages() -> int:
    return _env_int("PREVIEW_VISUAL_CRITIC_MAX_PAGES", MAX_VISUAL_CRITIQUE_PAGES)


def _route_surface(route: dict) -> str:
    surface = str(route.get("surface") or "").strip().lower()
    if surface:
        return surface
    haystack = f"{route.get('path') or ''} {route.get('component_file') or ''}".lower()
    return "ops" if any(m in haystack for m in _OPS_PATH_MARKERS) else "public"


def _select_visual_critique_routes(architect: dict, limit: int | None = None) -> list[dict]:
    """Homepage, then one route per surface, then role landing pages, then plan order.

    Surface coverage outranks plan order on purpose: taking the first N routes
    reviews the public storefront only, so ops/admin pages — where app 36's
    broken imagery lived — were never captured at all.
    """
    cap = _max_visual_critique_pages() if limit is None else max(1, limit)
    routes = [rt for rt in (architect.get("routes") or []) if rt.get("path")]
    by_path = {rt.get("path"): rt for rt in routes}
    selected: list[dict] = []
    seen_paths: set[str] = set()

    def _add(rt: dict | None) -> None:
        if not rt or len(selected) >= cap:
            return
        path = rt.get("path")
        if not path or path in seen_paths:
            return
        seen_paths.add(path)
        selected.append(rt)

    _add(by_path.get("/") or by_path.get("/home"))
    for surface in sorted({_route_surface(rt) for rt in routes}):
        _add(next((rt for rt in routes if _route_surface(rt) == surface), None))
    for role in architect.get("roles") or []:
        _add(by_path.get(role.get("defaultPath")))
    for rt in routes:
        _add(rt)

    return selected[:cap]


def _normalize_words(text: str) -> str:
    return f" {re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).strip()} "


def _family(category: str) -> str:
    return _CATEGORY_FAMILY.get(category, category)


def _family_scores(text: str) -> dict[str, int]:
    blob = _normalize_words(text)
    scores: dict[str, int] = {}
    for category, signals in _INDUSTRY_SIGNALS.items():
        hits = sum(1 for signal in signals if f" {signal} " in blob)
        if hits:
            family = _family(category)
            scores[family] = scores.get(family, 0) + hits
    return scores


def classify_industry_family(text: str) -> tuple[str, int]:
    """Best-guess industry family for a blob of text plus its confidence margin.

    Returns `("", 0)` when the text is ambiguous — no single family clearly
    wins. Ambiguity must never produce a finding.
    """
    scores = _family_scores(text)
    if not scores:
        return "", 0
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top_family, top_hits = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    if top_hits < _MIN_SIGNAL_HITS or top_hits <= runner_up:
        return "", top_hits
    return top_family, top_hits - runner_up


def _imagery_query_text(imagery_queries, template_id: str = "") -> str:
    if isinstance(imagery_queries, dict):
        values = [str(v) for v in imagery_queries.values()]
    elif isinstance(imagery_queries, (list, tuple, set)):
        values = [str(v) for v in imagery_queries]
    elif imagery_queries:
        values = [str(imagery_queries)]
    else:
        values = []
    if template_id:
        values.append(str(template_id))
    blob = _normalize_words(" ".join(values))
    kept = [w for w in blob.split() if w not in _QUERY_NOISE]
    return " ".join(kept)


def check_imagery_industry_consistency(
    *,
    industry: str = "",
    brand_name: str = "",
    business_context: str = "",
    imagery_queries=None,
    template_id: str = "",
    image_urls=None,
) -> list[VisualFinding]:
    """Zero-cost consistency assertion between business industry and imagery.

    The business side is read from the brief's own industry/brand wording; the
    imagery side from the queries and pack id actually used to source the
    photographs. Both must classify confidently before a mismatch is reported —
    an abstract or generic brief is not evidence of a defect.
    """
    business_family, business_margin = classify_industry_family(
        " ".join(part for part in (industry, brand_name, business_context) if part)
    )
    query_text = _imagery_query_text(imagery_queries, template_id)
    imagery_family, imagery_margin = classify_industry_family(query_text)
    if not business_family or not imagery_family:
        return []
    if business_family == imagery_family:
        return []
    urls = sorted({str(u) for u in (image_urls or []) if str(u).strip()})
    evidence = f" Installed imagery: {', '.join(urls[:8])}." if urls else ""
    return [
        VisualFinding(
            code="imagery_industry_mismatch",
            message=(
                f"Imagery was sourced for a '{imagery_family}' business but the brief reads as "
                f"'{business_family}' (industry={industry.strip() or '?'!r}, brand="
                f"{brand_name.strip() or '?'!r}). Imagery query terms: "
                f"{query_text[:200]!r} (template={template_id or '-'}); "
                f"confidence margins business={business_margin} imagery={imagery_margin}."
                f"{evidence}"
            ),
            path="src/data/mock.ts",
        )
    ]


def collect_installed_image_urls(workspace) -> list[str]:
    """Remote image URLs actually present in the generated source."""
    workspace = Path(workspace)
    found: set[str] = set()
    for rel in list_source_files(workspace):
        for url in _REMOTE_IMAGE_RE.findall(read_file(workspace, rel)):
            cleaned = url.rstrip(",;")
            lowered = cleaned.lower()
            if any(host in lowered for host in _REMOTE_IMAGE_HOSTS) or any(
                f".{suffix}" in lowered for suffix in _IMAGE_SUFFIXES
            ):
                found.add(cleaned)
    return sorted(found)


def find_missing_local_image_assets(workspace) -> dict[str, list[str]]:
    """Root-relative image references that resolve to no file in the workspace.

    The preview server SPA-fallbacks unknown paths to `dist/index.html` with
    HTTP 200, so a missing asset is invisible to any status-code check and
    renders as a broken-image icon.
    """
    workspace = Path(workspace)
    public_dir = workspace / "public"
    dist_dir = workspace / "dist"
    missing: dict[str, list[str]] = {}
    for rel in list_source_files(workspace):
        for ref in _LOCAL_IMAGE_REF_RE.findall(read_file(workspace, rel)):
            asset = ref.lstrip("/")
            if not asset or ".." in asset:
                continue
            if (public_dir / asset).is_file() or (dist_dir / asset).is_file():
                continue
            missing.setdefault(ref, []).append(rel)
    return {ref: sorted(set(files)) for ref, files in sorted(missing.items())}


def imagery_findings(
    workspace,
    *,
    industry: str = "",
    brand_name: str = "",
    business_context: str = "",
    imagery_queries=None,
    template_id: str = "",
) -> list[VisualFinding]:
    """Every deterministic imagery finding for a built workspace."""
    findings: list[VisualFinding] = list(
        check_imagery_industry_consistency(
            industry=industry,
            brand_name=brand_name,
            business_context=business_context,
            imagery_queries=imagery_queries,
            template_id=template_id,
            image_urls=collect_installed_image_urls(workspace),
        )
    )
    for ref, files in find_missing_local_image_assets(workspace).items():
        findings.append(
            VisualFinding(
                code="missing_image_asset",
                message=(
                    f"Image reference {ref!r} has no file in public/ or dist/ — the SPA "
                    f"fallback answers it with HTML 200 and the page renders a broken image. "
                    f"Referenced by: {', '.join(files[:5])}."
                ),
                path=files[0] if files else "",
            )
        )
    return findings


def _business_context(plan: dict, manifest: dict, full_context: str) -> str:
    parts = [
        str(plan.get("business_description") or ""),
        str(plan.get("concept_name") or ""),
        str(manifest.get("industry") or ""),
        (full_context or "")[:1200],
    ]
    return " ".join(p for p in parts if p)


def _resolve_industry(plan: dict, manifest: dict, industry: str) -> str:
    for candidate in (industry, plan.get("industry"), manifest.get("industry")):
        if candidate and str(candidate).strip():
            return str(candidate).strip()
    return ""


def _business_identity(brand_name: str, industry: str, business_context: str) -> str:
    lines = [f"Business name: {brand_name or 'Unknown'}", f"Industry: {industry or 'Unknown'}"]
    summary = " ".join((business_context or "").split())[:400]
    if summary:
        lines.append(f"What it sells: {summary}")
    return "\n".join(lines)


def report_path(workspace) -> Path:
    return Path(workspace) / VISUAL_CRITIQUE_REPORT_FILE


def write_visual_critique_report(workspace, report: VisualCritiqueReport) -> None:
    try:
        report_path(workspace).write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        log.warning("    visual critic: could not persist report (%s)", e)


def load_visual_critique_report(workspace) -> VisualCritiqueReport:
    """Read the persisted report; an absent/corrupt file yields an empty one."""
    path = report_path(workspace)
    try:
        if not path.is_file():
            return VisualCritiqueReport()
        return VisualCritiqueReport.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception as e:
        log.warning("    visual critic: could not read report (%s)", e)
        return VisualCritiqueReport()


def visual_critique_gate_issues(workspace) -> list[tuple[str, str, str]]:
    """`(code, message, path)` triples a quality gate can fail on directly."""
    return [
        (f.code, f.message, f.path)
        for f in load_visual_critique_report(workspace).blocking
    ]


def _issue_severity(score, verdict: str, issues: list[str]) -> str:
    if verdict != "revise":
        return WARN
    if any(_SEVERE_ISSUE_RE.match(issue) for issue in issues):
        return BLOCK
    if isinstance(score, int) and score <= VISUAL_BLOCK_SCORE:
        return BLOCK
    return WARN


def _run_visual_critique(
    db: Session,
    request_id: int,
    workspace,
    architect: dict,
    plan: dict,
    specs_by_path: dict,
    full_context: str,
    manifest: dict,
    images: dict,
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
    base_path: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    industry: str = "",
) -> VisualCritiqueReport:
    """Post-build visual critique: screenshot the actually-built app (a real
    rendered page, not raw source) and feed each screenshot to a
    vision-capable critic. Flagged pages get refined and the app rebuilt
    ONCE — a secondary polish pass, not the primary 6-attempt fix-loop. If
    that rebuild fails, the pre-critique snapshot is restored and rebuilt
    again to confirm the previously-working version still serves — visual
    "improvement" must never be able to take a working preview and ship a
    broken one instead. Every failure mode here degrades to "keep whatever
    was already built", never raises.

    Returns the report AND persists it to the workspace, so a later phase can
    fail the quality gate on `report.blocking` without re-running anything.
    """
    report = VisualCritiqueReport()
    resolved_industry = _resolve_industry(plan, manifest, industry)
    business_context = _business_context(plan, manifest, full_context)
    report.findings.extend(
        imagery_findings(
            workspace,
            industry=resolved_industry,
            brand_name=brand_name,
            business_context=business_context,
            imagery_queries=plan.get("imagery_roles"),
            template_id=str(plan.get("industry_template_id") or ""),
        )
    )
    for finding in report.blocking:
        log.error("    visual critic BLOCK %s: %s", finding.code, finding.message)
    # Persist before any screenshot work: a later crash must not lose findings
    # the gate is supposed to fail on.
    write_visual_critique_report(workspace, report)

    routes = _select_visual_critique_routes(architect)
    if not routes:
        write_visual_critique_report(workspace, report)
        return report

    design_direction = architect.get("design_direction", "")
    business_identity = _business_identity(brand_name, resolved_industry, business_context)
    screenshot_dir = workspace / "_visual_critique_shots"
    base_url = f"{settings.INTERNAL_BASE_URL}{base_path}/"
    workers = max(1, settings.PREVIEW_PARALLEL_WORKERS)

    def _review_route(item: tuple[int, dict]) -> tuple[str, dict, dict] | None:
        i, rt = item
        route_path = rt.get("path") or "/"
        component_file = (rt.get("component_file") or "").replace("\\", "/")
        if not component_file:
            return None
        shot_path = screenshot_dir / f"shot_{i}.png"
        capture = capture_route_visual(base_url, route_path, shot_path)
        if not capture.ok:
            log.error(f"    visual critic: skip {component_file} (screenshot failed)")
            return component_file, {"verdict": "unavailable"}, {}
        spec = specs_by_path.get(component_file) or {}
        review = critique_file_visual(
            workspace, component_file, str(shot_path),
            spec.get("instructions", ""), full_context, design_direction,
            ai_provider, template_renderer, architect,
            business_identity=business_identity,
        )
        review = {**review, "broken_images": capture.broken_images}
        return component_file, review, spec

    indexed_routes = list(enumerate(routes, 1))
    _emit(db, request_id, "visual_critic",
          f"Visually reviewing {len(indexed_routes)} page(s) in parallel...", 90,
          detail=f"workers={workers}")

    flagged: list[tuple[str, str, dict]] = []
    done = 0
    for _item, result, exc in parallel_map(
        indexed_routes,
        _review_route,
        max_workers=workers,
        on_done=lambda d, tot, item, _res, _exc: None,
    ):
        done += 1
        i, rt = _item
        _emit(db, request_id, "visual_critic",
              f"Visually reviewed {done}/{len(indexed_routes)}: {rt.get('title', rt.get('path', ''))}", 90,
              detail=rt.get("path") or "/")
        if exc:
            log.error(f"    visual critic route error: {exc}")
            report.unmeasured.append((rt.get("component_file") or rt.get("path") or "?"))
            report.add(
                "visual_critique_unavailable",
                f"Visual review of {rt.get('path') or '/'} raised ({exc}) — page was never judged.",
                path=(rt.get("component_file") or ""),
                severity=_unmeasured_severity(),
            )
            continue
        if not result:
            continue
        component_file, review, spec = result
        _absorb_review(report, component_file, review)
        if review.get("verdict") != "revise":
            continue
        notes = review.get("revision_instructions") or "; ".join(review.get("issues", []))
        if notes:
            flagged.append((component_file, notes, spec))

    try:
        import shutil
        shutil.rmtree(screenshot_dir, ignore_errors=True)
    except Exception:
        pass

    if not flagged:
        log.info("    visual critic: no pages flagged for refine")
        write_visual_critique_report(workspace, report)
        return report

    log.debug(f"    visual critic: refining {len(flagged)} page(s)")
    _emit(db, request_id, "visual_critic",
          f"Applying visual fixes to {len(flagged)} page(s)...", 91)
    snapshot = snapshot_source(workspace)

    def _rebuild_and_guard() -> tuple[bool, str]:
        apply_workspace_guards(
            workspace, architect, plan, images, brand_name, primary, secondary, font, template_renderer,
        )
        return run_build(workspace, base_path, template_renderer)

    try:
        def _refine_flagged(item: tuple[str, str, dict]) -> str:
            component_file, notes, spec = item
            refine_file(
                workspace, component_file, spec.get("instructions", ""), notes,
                full_context, manifest, images, ai_provider, template_renderer,
                architect,
            )
            return component_file

        for _item, result, exc in parallel_map(flagged, _refine_flagged, max_workers=workers):
            if exc:
                log.error(f"    visual critic refine failed: {exc}")
            elif result:
                report.refined.append(result)
        ok2, _ = _rebuild_and_guard()
    except Exception as e:
        log.info(f"    visual critic refine pass raised ({e}) — rolling back")
        ok2 = False

    if ok2:
        log.info("    visual critic: rebuild OK, keeping visually-refined version")
        write_visual_critique_report(workspace, report)
        return report

    log.error("    visual critic: rebuild failed after refinement — rolling back to pre-critique version")
    restore_source(workspace, snapshot)
    ok3, _ = _rebuild_and_guard()
    if ok3:
        log.info("    visual critic: rollback confirmed — restored version still builds")
    else:
        log.error("    visual critic: rollback rebuild ALSO failed — unexpected, workspace may be inconsistent")
    report.refined.clear()
    write_visual_critique_report(workspace, report)
    return report


def _unmeasured_severity() -> str:
    return BLOCK if _env_flag("PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED", False) else WARN


def _absorb_review(report: VisualCritiqueReport, component_file: str, review: dict) -> None:
    """Fold one page review into the report. An unavailable verdict never passes."""
    verdict = str(review.get("visual_verdict") or review.get("verdict") or "unavailable")
    issues = [str(i) for i in (review.get("issues") or [])]
    score = review.get("score")
    broken_images = [str(u) for u in (review.get("broken_images") or [])]

    if verdict == "unavailable":
        report.unmeasured.append(component_file)
        report.add(
            "visual_critique_unavailable",
            f"Visual critic returned no usable verdict for {component_file} — "
            "the page was never actually judged; this is a measurement failure, not a pass.",
            path=component_file,
            severity=_unmeasured_severity(),
        )
        return

    report.reviewed.append(component_file)
    if isinstance(score, int):
        report.scores[component_file] = score
    log.debug(f"    visual critic {component_file}: {score} ({verdict})")

    # A local src that will not decode is a workspace defect. A remote one may
    # only mean the sandbox cannot reach the CDN, which must not block a ship.
    local_broken = [src for src in broken_images if not src.lower().startswith(("http://", "https://", "data:"))]
    remote_broken = [src for src in broken_images if src not in local_broken]
    if local_broken:
        report.add(
            "broken_rendered_image",
            f"{len(local_broken)} local image(s) failed to load in the rendered page: "
            f"{', '.join(local_broken[:6])}.",
            path=component_file,
        )
    if remote_broken:
        report.add(
            "broken_remote_image",
            f"{len(remote_broken)} remote image(s) failed to load in the rendered page "
            f"(may be sandbox network): {', '.join(remote_broken[:6])}.",
            path=component_file,
            severity=WARN,
        )
    if verdict != "revise" or not issues:
        return
    severity = _issue_severity(score, verdict, issues)
    report.add(
        "visual_defect" if severity == WARN else "visual_defect_severe",
        f"{component_file} scored {score}: {'; '.join(issues[:6])}",
        path=component_file,
        severity=severity,
    )


__all__ = [
    "BLOCK",
    "MAX_VISUAL_CRITIQUE_PAGES",
    "VISUAL_BLOCK_SCORE",
    "VISUAL_CRITIQUE_REPORT_FILE",
    "WARN",
    "VisualCritiqueReport",
    "VisualFinding",
    "check_imagery_industry_consistency",
    "classify_industry_family",
    "collect_installed_image_urls",
    "find_missing_local_image_assets",
    "imagery_findings",
    "load_visual_critique_report",
    "visual_critique_gate_issues",
    "write_visual_critique_report",
]
