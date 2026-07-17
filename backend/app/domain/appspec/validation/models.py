"""AppSpec validation models."""
from __future__ import annotations

from typing import Any, Literal, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field

PathPart = Union[str, int]

IssuePath = Tuple[PathPart, ...]

class ValidationIssue(BaseModel):
    """One stable, machine-readable semantic validation finding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Literal["error", "warning"]
    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=1000)
    path: IssuePath = ()
    related_ids: Tuple[str, ...] = ()

class ValidationReport(BaseModel):
    """Deterministic validation result.  Warnings do not make a spec invalid."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_valid: bool
    issues: Tuple[ValidationIssue, ...] = ()

    @property
    def passed(self) -> bool:
        """Compatibility alias for integrations that call a valid report passed."""

        return self.is_valid

    @property
    def errors(self) -> Tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> Tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")
