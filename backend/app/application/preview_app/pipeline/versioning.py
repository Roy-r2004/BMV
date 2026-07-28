"""Preview-generator version label.

Preview generator v2 was removed; v1 is the only generation path. This module
retains only the label persisted alongside generated previews, so existing rows
and log lines keep a stable meaning.
"""
from __future__ import annotations

from typing import Literal

GENERATOR_V1 = "v1"
GeneratorVersion = Literal["v1"]

__all__ = ["GENERATOR_V1", "GeneratorVersion"]
