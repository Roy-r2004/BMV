"""Thin FastAPI application factory.

All actual behavior (routes, business logic, models) lives in the layered
`app/{api,application,domain,infrastructure}` packages. This module only
wires the pieces together: DB bootstrap, CORS, router mounting, and optional
SPA static file serving.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.api_router import api_router
from app.application.bootstrap.startup import (
    StartupMigrationError,
    StartupMigrationResult,
    bootstrap_database,
    redact_database_url,
)
from app.application.services.admin_bootstrap import bootstrap_admin
from app.application.services.demo_seed import seed_demo_if_empty
from app.core.config import settings
from app.domain.models import (  # noqa: F401
    AdminAlert,
    AdminSettings,
    AiUsageEvent,
    AppSpecRevision,
    CandidateArtifactRecord,
    CandidateRevisionRecord,
    CandidateAccessibilityFindingRecord,
    CandidateBuildAttemptRecord,
    CandidateJourneyResultRecord,
    CandidateRouteResultRecord,
    CandidateRuntimeValidationAttemptRecord,
    CandidateScreenshotRecord,
    CandidateValidationSummaryRecord,
    CandidateBaselineComparisonRecord,
    CandidateRefinementGenerationRecord,
    CandidateRefinementPlanRecord,
    CandidateVisualEvaluationAttemptRecord,
    CandidateVisualEvidenceBundleRecord,
    CandidateVisualFindingRecord,
    CandidateVisualHardGateResultRecord,
    CandidateVisualReviewerDecisionRecord,
    CandidateVisualScorecardRecord,
    CandidateVisualSummaryRecord,
    CandidateEffectiveTierSummaryRecord,
    CandidateLowerTierPreservationAuditRecord,
    CandidateTierExtensionManifestRecord,
    CandidateTierGenerationResultRecord,
    CandidateTierOrchestrationAttemptRecord,
    CandidateTierValidationResultRecord,
    CandidateTierVisualOutcomeRecord,
    PreviewCircuitBreakerPolicyRecord,
    PreviewCircuitBreakerStateRecord,
    PreviewLiveCanaryApprovalRecord,
    PreviewLiveCanaryApprovalStatusEventRecord,
    PreviewLiveCanaryExecutionClaimRecord,
    PreviewLiveCanaryExecutionRecord,
    PreviewLiveCanaryExecutionStatusEventRecord,
    PreviewLiveCanaryLifecycleEventRecord,
    PreviewPromotionDecisionRecord,
    PreviewPromotionDecisionStatusEventRecord,
    PreviewRolloutAuditEventRecord,
    PreviewRolloutPolicyRecord,
    PreviewServingPointerVersionRecord,
    PreviewShadowEvaluationRecord,
    CompositionContractArtifactRecord,
    CustomerSourceArtifact,
    DesignContractArtifactRecord,
    PreviewChatMessage,
    PreviewTierArtifactRecord,
    ProductStrategyRevision,
    Request,
    SolutionEditMessage,
    SolutionWorkspace,
    User,
    UserSession,
)
from app.domain.models.expanded_preview import (  # noqa: F401
    ExpandedPreviewGenerationClaimRecord,
    ExpandedPreviewPublicationRecord,
    ExpandedPreviewRequestRecord,
    ExpandedPreviewStatusEventRecord,
)
from app.infrastructure.db.base import Base
from app.infrastructure.db.migrations import run_legacy_column_migrations
from app.infrastructure.db.session import engine
from app.infrastructure.logging import configure_logging, get_logger
from app.infrastructure.storage.file_service import ensure_upload_dir

configure_logging(settings.LOG_LEVEL)
boot_log = get_logger("Boot")

STARTUP_MIGRATION_RESULT: StartupMigrationResult | None = None

# Fail closed: incomplete schema must not serve traffic.
try:
    STARTUP_MIGRATION_RESULT = bootstrap_database(
        engine=engine,
        create_all=Base.metadata.create_all,
        run_legacy_column_migrations=run_legacy_column_migrations,
        database_url=settings.DATABASE_URL,
    )
    ensure_upload_dir()
    bootstrap_admin()
    if settings.SEED_DEMO:
        seed_demo_if_empty()
    else:
        boot_log.info("SEED_DEMO=false — skipping PlateSync demo seed")
except StartupMigrationError as exc:
    STARTUP_MIGRATION_RESULT = exc.result
    boot_log.error(
        "DB bootstrap failed (db=%s) — refusing to start",
        redact_database_url(settings.DATABASE_URL),
    )
    raise SystemExit(f"Startup aborted: {exc.result.failure_reason}") from exc

boot_log.info(
    "PREVIEW_TEMPLATE_DIR=%s exists=%s",
    settings.PREVIEW_TEMPLATE_DIR,
    settings.PREVIEW_TEMPLATE_DIR.is_dir(),
)


def _log_runtime_tooling() -> None:
    import shutil
    import subprocess

    boot_log.info("AI_PROVIDER=%s LOG_LEVEL=%s", settings.AI_PROVIDER, settings.LOG_LEVEL)
    node = shutil.which("node")
    npm = shutil.which("npm")
    if node:
        try:
            node_ver = subprocess.run(
                [node, "-v"], capture_output=True, text=True, timeout=5, check=False,
            ).stdout.strip()
        except Exception:
            node_ver = "?"
    else:
        node_ver = "missing"
    if npm:
        try:
            npm_ver = subprocess.run(
                [npm, "-v"], capture_output=True, text=True, timeout=5, check=False,
            ).stdout.strip()
        except Exception:
            npm_ver = "?"
    else:
        npm_ver = "missing"
    boot_log.info("node=%s npm=%s", node_ver, npm_ver)
    boot_log.info("INTERNAL_BASE_URL=%s", settings.INTERNAL_BASE_URL)
    if settings.UVICORN_RELOAD:
        boot_log.info("uvicorn auto-reload ON (app + preview-template)")


_log_runtime_tooling()

app = FastAPI(title="BuildMyVersion AI", version="1.0.0")


@app.on_event("startup")
def _on_startup() -> None:
    # Uvicorn attaches access-log handlers after import; re-apply filters here.
    configure_logging(settings.LOG_LEVEL)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


if settings.STATIC_DIR and settings.STATIC_DIR.is_dir():
    _static_path = settings.STATIC_DIR
    _assets_dir = _static_path / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="Not found")

        if full_path in ("", "favicon.ico"):
            return FileResponse(_static_path / "index.html")

        target = _static_path / full_path
        if target.is_file():
            return FileResponse(target)

        return FileResponse(_static_path / "index.html")
