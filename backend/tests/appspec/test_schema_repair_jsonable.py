"""Schema-repair issue payloads must always be JSON serializable.

Request 26 regression: the AppSpec ``duplicate_id`` validator raises a
ValueError, and pydantic v2 attaches the raw exception under ``ctx.error``.
``_jsonable`` passed unknown scalars through untouched, so json.dumps raised
"Object of type ValueError is not JSON serializable". That exception aborted the
single allowed AI schema-repair attempt *before it ran*, so a repairable spec
became a hard ``deterministic_validation_failed`` with fallback disabled.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.appspec.schema_repair import (  # noqa: E402
    _canonical_json,
    _jsonable,
)


def test_pydantic_ctx_error_exception_is_serializable() -> None:
    """The exact request 26 shape: a ValueError nested in ctx.error."""

    issue = {
        "code": "duplicate_id",
        "path": "pages",
        "ctx": {"error": ValueError("IDs must be unique within each AppSpec collection")},
    }
    encoded = _canonical_json({"issues": [issue]})
    decoded = json.loads(encoded)

    assert decoded["issues"][0]["code"] == "duplicate_id"
    assert "unique" in decoded["issues"][0]["ctx"]["error"]


def test_primitives_are_preserved_exactly() -> None:
    payload = {"s": "x", "i": 3, "f": 1.5, "b": True, "n": None, "l": [1, "two"]}
    assert json.loads(_canonical_json(payload)) == payload


def test_arbitrary_objects_degrade_to_strings_not_crashes() -> None:
    class Opaque:
        def __repr__(self) -> str:
            return "<opaque>"

    assert _jsonable(Opaque()) == "<opaque>"
    json.loads(_canonical_json({"o": Opaque()}))


def test_sets_are_deterministic() -> None:
    first = _canonical_json({"tags": {"b", "a", "c"}})
    second = _canonical_json({"tags": {"c", "a", "b"}})
    assert first == second
    assert json.loads(first)["tags"] == ["a", "b", "c"]
