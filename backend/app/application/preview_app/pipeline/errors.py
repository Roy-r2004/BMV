"""Pipeline error types."""
from __future__ import annotations


class PreviewAppContractError(RuntimeError):
    """A required AppSpec preview could not meet its non-fallback contract."""
