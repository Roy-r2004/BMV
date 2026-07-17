"""AppSpec global ID uniqueness checks."""
from __future__ import annotations

from typing import Dict, Tuple

from app.domain.appspec.validation.collector import _Collector, _all_identified_objects
from app.domain.appspec.validation.models import IssuePath
from app.domain.schemas.app_spec import AppSpec

def _validate_global_ids(spec: AppSpec, collector: _Collector) -> None:
    seen: Dict[str, Tuple[str, IssuePath]] = {}
    for value, path in _all_identified_objects(spec):
        folded = value.casefold()
        previous = seen.get(folded)
        if previous is None:
            seen[folded] = (value, path)
            continue
        previous_value, previous_path = previous
        collector.add(
            "duplicate_global_id",
            (
                f"ID {value!r} duplicates {previous_value!r}; every AppSpec ID must "
                "be globally unique, case-insensitively."
            ),
            path,
            (previous_value, value),
        )
        collector.add(
            "duplicate_global_id",
            f"ID {previous_value!r} is also used at {'.'.join(map(str, path))}.",
            previous_path,
            (previous_value, value),
        )
