"""AppSpec deterministic sanitizer package."""
from __future__ import annotations

from app.domain.appspec.sanitize.empty_trace import (
    EmptyTraceNormalizeResult,
    normalize_optional_empty_traces,
    scan_empty_traces,
)
from app.domain.appspec.sanitize.graph_repair import (
    GraphRepairResult,
    repair_app_spec_graph,
    validation_has_repairable_graph_issues,
)
from app.domain.appspec.sanitize.heal import heal_app_spec_payload
from app.domain.appspec.sanitize.pipeline import sanitize_app_spec_payload
from app.domain.appspec.sanitize.preparse_normalize import (
    PreparseNormalizeResult,
    normalize_app_spec_preparse,
)
from app.domain.appspec.sanitize.schema_diagnostics import (
    build_rejected_candidate_artifact,
    classify_schema_parse_exception,
)
from app.domain.appspec.sanitize.trace_evidence_repair import (
    TraceEvidenceRepairResult,
    repair_trace_evidence_mismatch,
    validation_has_safe_trace_evidence_repair,
)

__all__ = [
    "EmptyTraceNormalizeResult",
    "GraphRepairResult",
    "PreparseNormalizeResult",
    "TraceEvidenceRepairResult",
    "build_rejected_candidate_artifact",
    "classify_schema_parse_exception",
    "heal_app_spec_payload",
    "normalize_app_spec_preparse",
    "normalize_optional_empty_traces",
    "repair_app_spec_graph",
    "repair_trace_evidence_mismatch",
    "sanitize_app_spec_payload",
    "scan_empty_traces",
    "validation_has_repairable_graph_issues",
    "validation_has_safe_trace_evidence_repair",
]
