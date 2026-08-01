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
from app.application.preview_app.screenshot import capture_routes_visual
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

# Families whose signal words genuinely overlap, so the two of them disagreeing
# is not evidence of a defect. Read as an unordered pair; the third element is
# the overlap that earns the pair its place, because "these feel related" is not
# a reason and this table is the detector's main way of going quiet.
#
# Deliberately NOT transitively closed. health~beauty and beauty~fitness are
# both real, but chaining them would make health~fitness~education~art and the
# detector would never fire again. Membership is exact-pair only.
_ADJACENT_FAMILY_PAIRS: tuple[tuple[str, str, str], ...] = (
    # `spa` (beauty) and `clinic` (medical) co-occur in one brief: a med-spa.
    ("health", "beauty", "cosmetic/aesthetic/massage; a med-spa is both"),
    # "vet clinic" contains `clinic`, a literal medical signal.
    ("health", "pets", "veterinary clinics score both by construction"),
    # `physiotherapy`/`chiropractic`/`therapy` against `training`/`strength`.
    ("health", "fitness", "rehab and strength work share vocabulary"),
    # `grooming` (pets) against `barber`/`hair` (beauty) — a barbershop scores both.
    ("beauty", "pets", "grooming reads as either a dog or a beard"),
    # `spa`/`massage` against `yoga`/`pilates` — one wellness studio, two families.
    ("beauty", "fitness", "wellness studios sell both"),
    # `catering` (food) is literally inside `catering hall` (events).
    ("food", "events", "catering is a literal shared token"),
    # `venue`/`catering hall` against `hotel`/`resort` — a wedding venue.
    ("events", "travel", "venues and resorts are the same booking"),
    # `print`/`prints` (art) against `boutique`/`shop`/`ecommerce` (retail).
    ("art", "retail", "a gallery that sells prints is a storefront"),
    # `notary`/`tax`/`audit`/`counsel` straddle the professional-services line.
    ("legal", "finance", "professional-services vocabulary is shared"),
    # `course`/`lesson` (education) against `yoga`/`bootcamp` (fitness).
    ("education", "fitness", "a class is a lesson"),
    # `renovation`/`construction` (trades) against `property`/`apartment`.
    ("realestate", "trades", "renovation work is described in property terms"),
)

_ADJACENT_FAMILIES: frozenset[frozenset[str]] = frozenset(
    frozenset((left, right)) for left, right, _why in _ADJACENT_FAMILY_PAIRS
)

# Words that appear in every generated imagery query and carry no industry meaning.
_QUERY_NOISE = (
    "lifestyle", "wide", "atmosphere", "interior", "workspace", "product", "detail",
    "close", "up", "customer", "experience", "team", "service", "moment", "ambient",
    "background", "texture", "professional", "small", "business", "hero",
)

_MIN_SIGNAL_HITS = 2
# A one-hit lead is noise, not a classification. `classify_industry_family` was
# already returning the margin and no threshold read it, so a 3-2 win counted as
# confident: "spa and wellness clinic" (health 2 / beauty 3) BLOCKed against
# imagery the pipeline itself had chosen correctly.
_MIN_CONFIDENT_MARGIN = 2


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
    # How many routes the critic set out to judge. Without it "reviewed 0 pages"
    # cannot be told apart from "there was nothing to review", and a total vision
    # outage reads identically to an app with no routes.
    routes_selected: int = 0

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

    @property
    def review_status(self) -> str:
        """`reviewed` | `partial` | `unmeasured` | `no_routes`.

        The one field a caller can read to find out whether "ok" means anything.
        `unmeasured` is the vision-outage case: the critic ran, had pages to
        judge, and judged none of them.
        """
        if not self.routes_selected and not self.reviewed and not self.unmeasured:
            return "no_routes"
        if not self.reviewed:
            return "unmeasured"
        return "reviewed" if not self.unmeasured else "partial"

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
            "routes_selected": int(self.routes_selected),
            # Derived, but written so a reader of the file on disk cannot miss it.
            "review_status": self.review_status,
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
        reviewed = [str(p) for p in (value.get("reviewed") or [])]
        unmeasured = [str(p) for p in (value.get("unmeasured") or [])]
        try:
            routes_selected = int(value.get("routes_selected") or 0)
        except (TypeError, ValueError):
            routes_selected = 0
        return cls(
            findings=findings,
            reviewed=reviewed,
            unmeasured=unmeasured,
            refined=[str(p) for p in (value.get("refined") or [])],
            scores={str(k): int(v) for k, v in (scores or {}).items() if isinstance(v, int)},
            # Reports written before this field existed still have to classify:
            # fall back to what was actually attempted rather than to 0, which
            # would read a real vision outage as "no routes".
            routes_selected=routes_selected or len(reviewed) + len(unmeasured),
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


def _infer_surface(*parts) -> str:
    """`ops` when any path-ish fragment looks owner-only, else `public`."""
    haystack = " ".join(str(p or "") for p in parts).replace("\\", "/").lower()
    return "ops" if any(m in haystack for m in _OPS_PATH_MARKERS) else "public"


def _route_surface(route: dict) -> str:
    surface = str(route.get("surface") or "").strip().lower()
    if surface:
        return surface
    return _infer_surface(route.get("path"), route.get("component_file"))


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
    # The item page, before generic surface coverage. `/` already claims the
    # public surface, so a detail route only ever reached the list through plan
    # order — and the cap was reached first. Request 48 scored Home, Login,
    # About, Dashboard, Gallery and Contact, called itself `reviewed` with an
    # empty `unmeasured`, and never looked at `ArtworkDetailPage`, which was
    # carrying three of the five defects a person then found by clicking.
    # It is also the page a storefront is judged on: the thing being sold.
    for skeleton in ("public-detail", "public-catalog"):
        _add(
            next(
                (
                    rt
                    for rt in routes
                    if str(rt.get("skeleton_id") or "").lower() == skeleton
                ),
                None,
            )
        )
    for surface in sorted({_route_surface(rt) for rt in routes}):
        _add(next((rt for rt in routes if _route_surface(rt) == surface), None))
    for role in architect.get("roles") or []:
        _add(by_path.get(role.get("defaultPath")))
    for rt in routes:
        _add(rt)

    dropped = [
        str(rt.get("path"))
        for rt in routes
        if rt.get("path") not in {s.get("path") for s in selected}
    ]
    if dropped:
        # Not a blocking state — `review_status` stays honest about the pages it
        # *chose*. But a run that says `reviewed` while N routes were never
        # captured should say so somewhere a person reads.
        log.info(
            "    visual critic: %d route(s) past the %d-page cap, not judged: %s",
            len(dropped),
            cap,
            ", ".join(dropped[:8]),
        )

    return selected[:cap]


def _normalize_words(text: str) -> str:
    return f" {re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).strip()} "


def _family(category: str) -> str:
    return _CATEGORY_FAMILY.get(category, category)


def _families_are_adjacent(left: str, right: str) -> bool:
    """True when two families overlap enough that disagreement proves nothing."""
    return frozenset((left, right)) in _ADJACENT_FAMILIES


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

    "Confidently" is enforced by `_MIN_CONFIDENT_MARGIN` on *both* sides, and
    families listed in `_ADJACENT_FAMILY_PAIRS` are never reported against each
    other. This finding BLOCKs, so every way of being merely-probably-right here
    withholds a preview that is fine.
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
    if business_margin < _MIN_CONFIDENT_MARGIN or imagery_margin < _MIN_CONFIDENT_MARGIN:
        return []
    if _families_are_adjacent(business_family, imagery_family):
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


# Every code `imagery_findings` can emit. These are deterministic and free, so
# they are recomputed rather than carried across a refine pass — a page the model
# just rewrote can introduce a new broken reference, or repair an old one.
# `test_imagery_finding_codes_are_complete` fails if this drifts.
_IMAGERY_FINDING_CODES = frozenset({"imagery_industry_mismatch", "missing_image_asset"})


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


def _forget_pages(report: VisualCritiqueReport, component_files) -> None:
    """Drop every measurement recorded for these pages so they can be re-judged.

    The persisted report is the only BLOCK source the quality gate reads that is
    not re-derived per gate run. It used to be written once, pre-refine, and
    persisted *unchanged* on the refine success path — so a page the pipeline had
    just repaired kept failing the gate forever, and the preview shipped as
    `status="failed"` with a perfectly good `dist/` on disk (P0-3).

    A finding the pipeline has since rewritten is not evidence. It is stale.
    """
    targets = {str(p).replace("\\", "/") for p in component_files if p}
    if not targets:
        return
    report.findings = [
        f for f in report.findings if f.path.replace("\\", "/") not in targets
    ]
    report.reviewed = [p for p in report.reviewed if p.replace("\\", "/") not in targets]
    report.unmeasured = [
        p for p in report.unmeasured if p.replace("\\", "/") not in targets
    ]
    report.scores = {
        k: v for k, v in report.scores.items() if k.replace("\\", "/") not in targets
    }


def visual_review_summary(workspace) -> dict:
    """Measurement facts for the API result — never a verdict, always a count.

    `ok` on this report means "nothing blocking was found", which is not the same
    claim as "the pages were looked at". A vision outage produced the former and
    was reported as `status: "ready"` with zero pages judged, while the progress
    feed said `Visually reviewed 6/6`. Callers get the counts here so "ready" can
    never again be read on its own as "reviewed".

    Returns `{}` when the critic never ran, which is not a measurement failure —
    `PREVIEW_SKIP_VISUAL_CRITIC` is a legitimate configuration.
    """
    path = report_path(workspace)
    try:
        if not path.is_file():
            return {}
    except OSError as e:
        log.warning("visual critique report unreadable: %s", e)
        return {}
    report = load_visual_critique_report(workspace)
    return {
        "visual_review_status": report.review_status,
        "visual_pages_reviewed": len(report.reviewed),
        "visual_pages_unmeasured": len(report.unmeasured),
        "visual_pages_selected": report.routes_selected,
    }


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


def invalidate_visual_verdicts(workspace, component_files) -> list[str]:
    """Retire the persisted verdicts for pages rewritten *after* they were judged.

    `_remeasure_refined_pages` covers the pages the visual critic itself refined.
    The quality gate's own AI repair rewrites pages too, and those verdicts were
    never re-derived — so request 45's contact page was repaired from a checkout
    stub into a proper form, rebuilt clean, and still failed the gate on the score
    of 20 the stub had earned. The gate was reading a measurement of source that no
    longer existed.

    The page becomes `unmeasured`, never a pass: after a rewrite we genuinely do not
    know what it looks like, and `visual_review_summary` reports not-knowing. Returns
    the paths whose verdicts were retired.
    """
    targets = {str(p).replace("\\", "/") for p in component_files if p}
    if not targets:
        return []
    report = load_visual_critique_report(workspace)
    judged = {p.replace("\\", "/") for p in report.reviewed}
    retired = sorted(targets & judged)
    if not retired:
        return []
    _forget_pages(report, retired)
    report.unmeasured = list(dict.fromkeys([*report.unmeasured, *retired]))
    write_visual_critique_report(workspace, report)
    log.info(
        "    visual critic: %s verdict(s) retired after repair — %s",
        len(retired),
        ", ".join(retired),
    )
    return retired


def _issue_severity(score, verdict: str, issues: list[str], surface: str = "public") -> str:
    """How hard a page's own visual verdict should bite.

    Surface-scoped for the same reason `broken_rendered_image` is (P0-4), and
    proven necessary by a live run: an admin *login* page scored 20 and withheld
    the entire public storefront, while the public contact page that had genuinely
    lost its form scored 30 beside it. One of those is a reason not to ship a
    preview; the other is a reason to fix an owner page later.

    Public keeps the BLOCK — it is correct there, and that is the case the
    threshold was chosen for.
    """
    if verdict != "revise":
        return WARN
    if (surface or "public").strip().lower() != "public":
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
    only_components: set[str] | None = None,
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
    fail the quality gate on `report.blocking` without re-running anything —
    except for whatever the refine pass rewrote, which is re-measured here before
    the report is handed on (see `_forget_pages`).

    `only_components` runs a *re-measure* pass: judge exactly these component
    files, fold the results into the persisted report, and refine nothing. The
    quality gate retires the verdict for any page it repairs, and request 46
    ended with one page reviewed and five retired — honest, and no coverage at
    all. Retiring a verdict is only half the job; this is the other half.
    """
    remeasure = bool(only_components)
    report = load_visual_critique_report(workspace) if remeasure else VisualCritiqueReport()
    resolved_industry = _resolve_industry(plan, manifest, industry)
    business_context = _business_context(plan, manifest, full_context)

    def _fresh_imagery_findings() -> list[VisualFinding]:
        return imagery_findings(
            workspace,
            industry=resolved_industry,
            brand_name=brand_name,
            business_context=business_context,
            imagery_queries=plan.get("imagery_roles"),
            template_id=str(plan.get("industry_template_id") or ""),
        )

    if not remeasure:
        report.findings.extend(_fresh_imagery_findings())
        for finding in report.blocking:
            log.error("    visual critic BLOCK %s: %s", finding.code, finding.message)
        # Persist before any screenshot work: a later crash must not lose findings
        # the gate is supposed to fail on.
        write_visual_critique_report(workspace, report)

    routes = _select_visual_critique_routes(architect)
    if remeasure:
        wanted = {str(c).replace("\\", "/") for c in (only_components or set())}
        routes = [
            rt
            for rt in routes
            if str(rt.get("component_file") or "").replace("\\", "/") in wanted
        ]
    else:
        report.routes_selected = len(routes)
    if not routes:
        # Nothing to look at. In a re-measure that means the pages stay
        # `unmeasured` — clearing the list here would turn "we could not judge
        # these" into "there was nothing to judge".
        write_visual_critique_report(workspace, report)
        return report
    if remeasure:
        # Only the pages this pass will actually judge lose their old entry.
        judging = {
            str(rt.get("component_file") or "").replace("\\", "/") for rt in routes
        }
        _forget_pages(report, judging)
        report.unmeasured = [
            p for p in report.unmeasured if p.replace("\\", "/") not in judging
        ]

    design_direction = architect.get("design_direction", "")
    business_identity = _business_identity(brand_name, resolved_industry, business_context)
    screenshot_dir = workspace / "_visual_critique_shots"
    base_url = f"{settings.INTERNAL_BASE_URL}{base_path}/"
    workers = max(1, settings.PREVIEW_PARALLEL_WORKERS)

    captures_by_index: dict[int, object] = {}

    def _capture_batch(items: list[tuple[int, dict]]) -> int:
        """Screenshot every route in one serial browser session.

        Capture used to happen inside the worker thread that then made the vision
        call, so `PREVIEW_PARALLEL_WORKERS` threads entered Playwright's sync API
        at once and raced for its driver spawn. Request 40 lost 5 of 6 pages to
        `RuntimeError: Racing with another loop to spawn a process.` and shipped
        with one page judged. Screenshots are serial now; the vision calls, which
        are what the workers are for, still fan out below.
        """
        wanted = [
            (i, rt) for i, rt in items
            if (rt.get("component_file") or "").strip()
        ]
        if not wanted:
            return 0
        captures = capture_routes_visual(
            base_url,
            [(rt.get("path") or "/", screenshot_dir / f"shot_{i}.png") for i, rt in wanted],
        )
        fresh = {i: cap for (i, _rt), cap in zip(wanted, captures)}
        captures_by_index.update(fresh)
        return sum(1 for cap in fresh.values() if getattr(cap, "ok", False))

    def _review_route(item: tuple[int, dict]) -> tuple[str, dict, dict] | None:
        i, rt = item
        component_file = (rt.get("component_file") or "").replace("\\", "/")
        if not component_file:
            return None
        shot_path = screenshot_dir / f"shot_{i}.png"
        capture = captures_by_index.get(i)
        if capture is None or not getattr(capture, "ok", False):
            log.error(f"    visual critic: skip {component_file} (screenshot failed)")
            return component_file, {"verdict": "unavailable"}, {}
        spec = specs_by_path.get(component_file) or {}
        review = critique_file_visual(
            workspace, component_file, str(shot_path),
            spec.get("instructions", ""), full_context, design_direction,
            ai_provider, template_renderer, architect,
            business_identity=business_identity,
        )
        review = {**review, "broken_images": getattr(capture, "broken_images", [])}
        return component_file, review, spec

    indexed_routes = list(enumerate(routes, 1))
    _emit(db, request_id, "visual_critic",
          f"Screenshotting {len(indexed_routes)} page(s)...", 90,
          detail="one browser session, one page at a time")
    shot_ok = _capture_batch(indexed_routes)
    if shot_ok < len(indexed_routes):
        log.error(
            "    visual critic: %s of %s screenshot(s) failed — those pages cannot be judged",
            len(indexed_routes) - shot_ok, len(indexed_routes),
        )
    _record_render_errors(report, indexed_routes, captures_by_index, db, request_id)
    _emit(db, request_id, "visual_critic",
          f"Visually reviewing {shot_ok} page(s) in parallel...", 90,
          detail=f"workers={workers}")

    flagged: list[tuple[str, str, dict]] = []

    def _make_consumer(total: int, verb: str, collect_flagged: bool):
        """One place both review passes fold a result into the report.

        The progress line used to be emitted *before* the exception check, so a
        total vision outage still told the user `Visually reviewed 6/6` while
        judging nothing. The counter here only advances on a page that was
        actually judged, and a failure gets its own visible line.
        """
        state = {"judged": 0}

        def _consume(item, result, exc) -> None:
            _i, rt = item
            route_path = rt.get("path") or "/"
            fallback_file = rt.get("component_file") or route_path or "?"
            if exc:
                log.error(f"    visual critic route error: {exc}")
                report.unmeasured.append(fallback_file)
                report.add(
                    "visual_critique_unavailable",
                    f"Visual review of {route_path} raised ({exc}) — page was never judged.",
                    path=(rt.get("component_file") or ""),
                    severity=_unmeasured_severity(),
                )
                _emit(db, request_id, "visual_critic",
                      f"Visual review FAILED for {route_path} — page not judged", 90,
                      detail=str(exc)[:200])
                return
            if not result:
                return
            component_file, review, spec = result
            _absorb_review(report, component_file, review, surface=_route_surface(rt))
            if _review_verdict(review) == "unavailable":
                _emit(db, request_id, "visual_critic",
                      f"Visual review unavailable for {route_path} — page not judged", 90,
                      detail=component_file)
            else:
                state["judged"] += 1
                _emit(db, request_id, "visual_critic",
                      f"Visually {verb} {state['judged']}/{total}: "
                      f"{rt.get('title', rt.get('path', ''))}", 90,
                      detail=route_path)
            if not collect_flagged or review.get("verdict") != "revise":
                return
            # Never let vision rewrite utility contact/auth — request 62 replaced
            # InquiryPanel with a WhatsApp clone and /privacy-policy dead link.
            route_path = str(rt.get("path") or "").rstrip("/").lower()
            if re.search(r"(^|/)(contact|contact-us|login|sign-in|signin)(/|$)", route_path):
                return
            notes = review.get("revision_instructions") or "; ".join(review.get("issues", []))
            if notes:
                flagged.append((component_file, notes, spec))

        return _consume

    _consume_first_pass = _make_consumer(
        len(indexed_routes), "re-reviewed" if remeasure else "reviewed", not remeasure
    )
    for _item, result, exc in parallel_map(
        indexed_routes,
        _review_route,
        max_workers=workers,
        on_done=lambda d, tot, item, _res, _exc: None,
    ):
        _consume_first_pass(_item, result, exc)

    if report.review_status == "unmeasured" and not remeasure:
        log.error(
            "    visual critic: 0 of %s page(s) could be judged — this is a "
            "measurement outage, not a pass",
            len(indexed_routes),
        )
        _emit(db, request_id, "visual_critic",
              f"Visual review measured 0 of {len(indexed_routes)} page(s)", 90,
              detail="vision unavailable — the pages were not judged")

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
        _remeasure_refined_pages(
            db, request_id, report, indexed_routes, _review_route, _make_consumer, workers,
            recapture=_capture_batch,
        )
        # Deterministic and free, so there is no reason to carry the pre-refine
        # verdict: a rewritten page can introduce a broken local reference or
        # remove the one that was found.
        report.findings = [
            f for f in report.findings if f.code not in _IMAGERY_FINDING_CODES
        ]
        report.findings.extend(_fresh_imagery_findings())
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


def _record_render_errors(
    report: VisualCritiqueReport,
    indexed_routes: list,
    captures_by_index: dict,
    db,
    request_id: int,
) -> None:
    """A page that rendered the error boundary is a crash, not a low score.

    This is deterministic on purpose. Request 41's home page threw
    `aiFeatures is not defined` and rendered the template's error box; the vision
    model looked at that box and reported *"the hero image is a photograph of an
    artist painting in a studio"*, scoring it 65 — a warning. Asking a model
    whether a page rendered is asking the wrong component: the browser knows.

    Public surfaces BLOCK. Ops surfaces WARN, following `asset_integrity`'s policy
    that an owner-only page must not withhold a working storefront (P0-4) — the
    error is still reported and still reaches the repair loop.
    """
    for i, rt in indexed_routes:
        capture = captures_by_index.get(i)
        message = str(getattr(capture, "render_error", "") or "")
        if not message:
            continue
        component_file = (rt.get("component_file") or "").replace("\\", "/")
        route_path = rt.get("path") or "/"
        surface = _route_surface(rt)
        severity = BLOCK if surface == "public" else WARN
        log.error(
            "    visual critic %s page_failed_to_render %s (%s): %s",
            severity.upper(),
            route_path,
            component_file,
            message[:200],
        )
        report.add(
            "page_failed_to_render",
            f"{route_path} ({component_file}) rendered the preview error boundary "
            f"instead of the page: {message[:300]}",
            path=component_file,
            severity=severity,
        )
        _emit(
            db,
            request_id,
            "visual_critic",
            f"{route_path} failed to render",
            90,
            detail=message[:200],
        )


def _remeasure_refined_pages(
    db,
    request_id: int,
    report: VisualCritiqueReport,
    indexed_routes: list,
    review_route,
    make_consumer,
    workers: int,
    recapture=None,
) -> None:
    """Re-judge the pages the refine pass rewrote, discarding the stale verdict.

    This is P0-3's fix. The report was written once, pre-refine, and persisted
    unchanged here — the only BLOCK source the gate reads that never got a second
    look. A page scored 30, got rewritten, rebuilt clean, and the dead score kept
    the whole preview at `status="failed"`.

    Re-measurement can itself fail. That is recorded as `unmeasured`, not as a
    pass and not as the old BLOCK: after a rewrite we genuinely no longer know,
    and `visual_review_summary` makes not-knowing visible.
    """
    refined = sorted({str(p).replace("\\", "/") for p in report.refined if p})
    if not refined:
        return
    _forget_pages(report, refined)
    # One route per refined component file. Several declared routes routinely share
    # a page (`/artworks/:id`, `/artworks/:slug`, `/artworks/:artworkSlug` are one
    # component), and re-measuring costs a screenshot plus a vision call each.
    wanted = set(refined)
    recheck: list = []
    for i, rt in indexed_routes:
        component_file = (rt.get("component_file") or "").replace("\\", "/")
        if component_file in wanted:
            wanted.discard(component_file)
            recheck.append((i, rt))
    if recheck:
        log.info("    visual critic: re-reviewing %s refined page(s)", len(recheck))
        _emit(db, request_id, "visual_critic",
              f"Re-reviewing {len(recheck)} refined page(s)...", 91,
              detail="a repaired page must not keep its old verdict")
        if callable(recapture):
            # The refine pass rewrote these files and the workspace was rebuilt.
            # Judging the pre-refine screenshot again would re-measure nothing —
            # it would re-read the defect we just repaired.
            recapture(recheck)
        consume = make_consumer(len(recheck), "re-reviewed", False)
        try:
            for item, result, exc in parallel_map(recheck, review_route, max_workers=workers):
                consume(item, result, exc)
        except Exception as e:
            log.error("    visual critic: re-review pass raised (%s)", e)
    else:
        # A refined file with no screenshotted route. Not reachable today — every
        # flagged file came from one — but falling through to the sweep below means
        # the honesty of the counts does not depend on that staying true.
        log.info("    visual critic: %s refined file(s) had no route to re-review", len(refined))
    # Anything that neither produced a review nor an error is still unaccounted
    # for — a silently-dropped page must read as unmeasured, never as repaired.
    judged = {p.replace("\\", "/") for p in report.reviewed + report.unmeasured}
    for component_file in refined:
        if component_file in judged:
            continue
        report.unmeasured.append(component_file)
        report.add(
            "visual_critique_unavailable",
            f"{component_file} was refined but never re-reviewed — the repaired "
            "page was not judged; this is a measurement failure, not a pass.",
            path=component_file,
            severity=_unmeasured_severity(),
        )


def _unmeasured_severity() -> str:
    """Severity for a page the critic could not judge.

    Defaults to WARN: a vision outage is *our* measurement failing, not a defect
    in the generated app, and withholding a working preview because OpenRouter
    429'd is the same pathology as P0-3. Operators who would rather ship nothing
    than ship unreviewed set `PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED=true`.

    Either way the counts reach the API result via `visual_review_summary`, so
    "ready" is never the only thing a caller sees.
    """
    return BLOCK if _env_flag("PREVIEW_VISUAL_CRITIC_BLOCK_ON_UNMEASURED", False) else WARN


def _review_verdict(review: dict) -> str:
    """The one place a raw critic result is turned into a verdict string."""
    return str(review.get("visual_verdict") or review.get("verdict") or "unavailable")


def _absorb_review(
    report: VisualCritiqueReport,
    component_file: str,
    review: dict,
    surface: str = "",
) -> None:
    """Fold one page review into the report. An unavailable verdict never passes.

    `surface` decides whether a rendering defect withholds the preview, mirroring
    `asset_integrity.blocking_missing_assets()`. It is inferred from the
    component path when the caller has no route to hand.
    """
    surface = (surface or "").strip().lower() or _infer_surface(component_file)
    verdict = _review_verdict(review)
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
        # Public only. Route selection deliberately screenshots an ops route, so
        # blocking on every surface let one owner-only thumbnail withhold the
        # whole storefront — the policy `asset_integrity` already rejected for
        # the same defect, and `missing_image_asset` is filtered in the gate for
        # exactly this reason.
        report.add(
            "broken_rendered_image",
            f"{len(local_broken)} local image(s) failed to load in the rendered "
            f"{surface} page: {', '.join(local_broken[:6])}.",
            path=component_file,
            severity=BLOCK if surface == "public" else WARN,
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
    severity = _issue_severity(score, verdict, issues, surface=surface)
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
    "invalidate_visual_verdicts",
    "load_visual_critique_report",
    "visual_critique_gate_issues",
    "visual_review_summary",
    "write_visual_critique_report",
]
