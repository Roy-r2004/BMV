"""Load AI feature catalog for workspace integration (mirrors frontend/src/data/aiFeatureCatalog.ts)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CATALOG_PATH = Path(__file__).resolve().parents[3] / "frontend" / "src" / "data" / "aiFeatureCatalog.json"
_CATALOG_TS_FALLBACK = Path(__file__).resolve().parents[3] / "frontend" / "src" / "data" / "aiFeatureCatalog.ts"


def _build_catalog_from_ts_fallback() -> dict[str, dict[str, Any]]:
    """Minimal fallback if JSON export missing — real-estate samples only."""
    return {
        "real-estate:re-listing-ai": {
            "title": "Listing Q&A AI",
            "patch": {
                "aiChips": ["Listing AI", "HOA answers", "School data"],
                "sections": [{
                    "id": "ai-listing",
                    "title": "Listing AI on every page",
                    "body": "Buyers get instant answers on HOA, schools, and comps — agents get qualified leads.",
                    "style": "highlight",
                }],
            },
        },
    }


@lru_cache(maxsize=1)
def _feature_index() -> dict[str, dict[str, Any]]:
    if _CATALOG_PATH.exists():
        raw = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        index: dict[str, dict[str, Any]] = {}
        for solution_id, items in raw.items():
            for item in items:
                key = f"{solution_id}:{item['id']}"
                index[key] = item
        return index
    return _build_catalog_from_ts_fallback()


def get_catalog_feature(solution_id: str, feature_id: str) -> dict[str, Any] | None:
    return _feature_index().get(f"{solution_id}:{feature_id}")


def list_catalog_for_solution(solution_id: str) -> list[dict[str, Any]]:
    if _CATALOG_PATH.exists():
        raw = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        return list(raw.get(solution_id, []))
    return [v for k, v in _feature_index().items() if k.startswith(f"{solution_id}:")]
