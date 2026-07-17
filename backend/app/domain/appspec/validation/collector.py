"""AppSpec validation issue collector helpers."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Tuple

from app.domain.appspec.validation.models import IssuePath, PathPart, ValidationIssue, ValidationReport
from app.domain.schemas.app_spec import AppSpec

class _Collector:
    def __init__(self) -> None:
        self.issues: List[ValidationIssue] = []

    def add(
        self,
        code: str,
        message: str,
        path: Sequence[PathPart] = (),
        related_ids: Sequence[str] = (),
        *,
        severity: Literal["error", "warning"] = "error",
    ) -> None:
        self.issues.append(
            ValidationIssue(
                severity=severity,
                code=code,
                message=message,
                path=tuple(path),
                related_ids=tuple(related_ids),
            )
        )

    def report(self) -> ValidationReport:
        severity_rank = {"error": 0, "warning": 1}
        ordered = tuple(
            sorted(
                self.issues,
                key=lambda issue: (
                    tuple(f"{type(part).__name__}:{part}" for part in issue.path),
                    severity_rank[issue.severity],
                    issue.code,
                    issue.message,
                    tuple(value.casefold() for value in issue.related_ids),
                ),
            )
        )
        return ValidationReport(
            is_valid=not any(issue.severity == "error" for issue in ordered),
            issues=ordered,
        )

def _objects_by_id(items: Iterable[Any]) -> Dict[str, Any]:
    return {str(item.id): item for item in items}

def _require_reference(
    collector: _Collector,
    value: str,
    objects: Dict[str, Any],
    path: IssuePath,
    target: str,
) -> Optional[Any]:
    obj = objects.get(value)
    if obj is not None:
        return obj
    folded = value.casefold()
    case_matches = sorted(key for key in objects if key.casefold() == folded)
    if case_matches:
        collector.add(
            "reference_case_mismatch",
            f"{target} reference {value!r} must use canonical ID {case_matches[0]!r}.",
            path,
            (value, case_matches[0]),
        )
    else:
        collector.add(
            "missing_reference",
            f"{target} reference {value!r} does not exist.",
            path,
            (value,),
        )
    return None

def _reject_duplicate_references(
    collector: _Collector,
    values: Sequence[str],
    path: IssuePath,
) -> None:
    seen: Dict[str, str] = {}
    for index, value in enumerate(values):
        folded = value.casefold()
        if folded in seen:
            collector.add(
                "duplicate_reference",
                f"Reference {value!r} duplicates {seen[folded]!r} (IDs are case-insensitive).",
                path + (index,),
                (seen[folded], value),
            )
        else:
            seen[folded] = value

def _all_identified_objects(spec: AppSpec) -> Iterable[Tuple[str, IssuePath]]:
    collection_names = (
        "requirements",
        "assumptions",
        "open_questions",
        "roles",
        "entities",
        "capabilities",
        "pages",
        "states",
        "actions",
        "transitions",
        "evidence",
        "journeys",
        "acceptance_tests",
        "deferred_scope",
    )
    for name in collection_names:
        for index, item in enumerate(getattr(spec, name)):
            yield item.id, (name, index, "id")
    for entity_index, entity in enumerate(spec.entities):
        for field_index, field in enumerate(entity.fields):
            yield field.id, ("entities", entity_index, "fields", field_index, "id")
    for journey_index, journey in enumerate(spec.journeys):
        for step_index, step in enumerate(journey.steps):
            yield step.id, ("journeys", journey_index, "steps", step_index, "id")
