"""AI codegen for preview React apps — public API only."""
from app.application.preview_app.codegen.architect import call_architect
from app.application.preview_app.codegen.critic import (
    critique_and_refine,
    critique_file,
    critique_file_visual,
    refine_file,
)
from app.application.preview_app.codegen.fix_agent import fix_build_errors
from app.application.preview_app.codegen.generate import generate_file
from app.application.preview_app.codegen.mock import (
    enrich_mock_if_sparse,
    mock_needs_enrichment,
    synthesize_mock_data,
)
from app.application.preview_app.codegen.shared import (
    _catalogue_retry_context,
    _normalize_critic_result,
    page_plan_for_file,
)
from app.core.config import settings

__all__ = [
    "_catalogue_retry_context",
    "_normalize_critic_result",
    "call_architect",
    "critique_and_refine",
    "critique_file",
    "critique_file_visual",
    "enrich_mock_if_sparse",
    "fix_build_errors",
    "generate_file",
    "mock_needs_enrichment",
    "page_plan_for_file",
    "refine_file",
    "settings",
    "synthesize_mock_data",
]
