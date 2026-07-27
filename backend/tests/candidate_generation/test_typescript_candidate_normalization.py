"""Compiler-AST normalization for generated candidate TypeScript handoff."""
from __future__ import annotations

from app.application.candidate_generation.deterministic import (
    build_content_data_module,
)
from app.application.candidate_generation.generated_data_api import (
    normalize_generated_candidate_types,
)
from tests.candidate_generation.request40_fixture import request40_context


def test_normalizes_mixed_generated_data_import_and_jsx_type_reference() -> None:
    module, manifest = build_content_data_module(request40_context())
    source = """import { ServiceRecord, getServiceSeedData } from "@/generated/content-data";

export function Card(): JSX.Element {
  const services: readonly ServiceRecord[] = getServiceSeedData();
  return <p>{services.length}</p>;
}
"""

    normalized, evidence, issues = normalize_generated_candidate_types(
        source,
        path="src/components/business/CompCard.tsx",
        manifest=manifest,
        content_data_module=module,
    )

    assert not issues
    assert (
        'import type { ServiceRecord } from "@/generated/content-data";'
        in normalized
    )
    assert (
        'import { getServiceSeedData } from "@/generated/content-data";'
        in normalized
    )
    assert 'import type { JSX } from "react";' in normalized
    assert evidence
