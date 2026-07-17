"""AppSpec validation entrypoint."""
from __future__ import annotations

from app.domain.appspec.validation.acceptance import _validate_acceptance_tests
from app.domain.appspec.validation.collector import _Collector
from app.domain.appspec.validation.ids import _validate_global_ids
from app.domain.appspec.validation.journeys import _validate_journeys
from app.domain.appspec.validation.membership import _validate_references_and_membership
from app.domain.appspec.validation.models import ValidationReport
from app.domain.appspec.validation.traceability import _validate_traceability
from app.domain.appspec.validation.transitions import _validate_transitions
from app.domain.schemas.app_spec import AppSpec

def validate_app_spec(spec: AppSpec) -> ValidationReport:
    """Validate cross-object AppSpec semantics without mutating state or doing I/O."""

    if not isinstance(spec, AppSpec):
        raise TypeError("validate_app_spec expects an AppSpec instance")
    collector = _Collector()
    _validate_global_ids(spec, collector)
    _validate_references_and_membership(spec, collector)
    return collector.report()
