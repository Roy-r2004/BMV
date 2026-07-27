"""Regression: content-data.ts must export CONTENT_*/DATA_* ids models import."""
from __future__ import annotations

from types import SimpleNamespace

from app.application.candidate_generation.deterministic import (
    _contract_id_export_names,
    ensure_content_data_compat_aliases,
)


def test_contract_id_export_names_cover_case_variants() -> None:
    names = _contract_id_export_names("CONTENT-E-7a788ace5adf9bad")
    assert "CONTENT_E_7A788ACE5ADF9BAD" in names
    assert "CONTENT_E_7a788ace5adf9bad" in names


def test_ensure_content_data_compat_aliases_exports_content_and_data_ids() -> None:
    content_item = SimpleNamespace(
        content_id="CONTENT-E-07ffae6e3d298bd8",
        value="Booking confirmed.",
    )
    collection = SimpleNamespace(
        collection_id="DATA-a16370bce8cb84e4",
        entity_id="ENTITY-SERVICE",
        seed_records=(
            SimpleNamespace(
                values=(
                    SimpleNamespace(
                        field_id="FIELD-SERVICE-ID",
                        value="svc-1",
                    ),
                    SimpleNamespace(
                        field_id="FIELD-SERVICE-NAME",
                        value="Cut",
                    ),
                )
            ),
        ),
    )
    context = SimpleNamespace(
        content_data=SimpleNamespace(
            content_items=(content_item,),
            data_collections=(collection,),
        )
    )
    source = (
        "export const contentDataPlan = {"
        '"content_items":[{"content_id":"CONTENT-E-07ffae6e3d298bd8","value":"Booking confirmed."}],'
        '"data_collections":[]'
        "} as const;\n"
    )
    aliased = ensure_content_data_compat_aliases(source, context=context)
    assert "export const CONTENT_E_07FFAE6E3D298BD8 = " in aliased
    assert "contentDataPlan.content_items[0].value" in aliased
    assert "export const DATA_A16370BCE8CB84E4 = Object.assign(" in aliased
    assert "contentDataPlan.data_collections[0]" in aliased
    assert "FIELD_SERVICE_ID" in aliased
