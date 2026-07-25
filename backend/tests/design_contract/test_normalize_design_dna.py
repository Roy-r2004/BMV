"""Deterministic heal for Design DNA mechanical gaps."""
from __future__ import annotations

from app.application.design_contract.normalize import normalize_design_dna
from app.application.design_contract.service import _load_phase1b_contract
from app.application.design_contract.validation import validate_design_dna
from app.domain.schemas.design_contract import DesignArtifactRef
from app.domain.schemas.design_dna import DesignDNA
from tests.design_contract.helpers import design_dna_payload, prepare_phase1b


def test_normalize_repairs_color_roles_and_forbidden_markers() -> None:
    prepared = prepare_phase1b(request_id=3601, page_count=6)
    try:
        contract = _load_phase1b_contract(
            prepared.db,
            request_id=prepared.req.id,
            phase1_summary=prepared.phase1_result["preview_contract"],
        )
        strategy_ref = DesignArtifactRef(
            id=91,
            artifact_kind="product_strategy_v2",
            schema_version="2.0",
            sha256="a" * 64,
        )
        ia_ref = DesignArtifactRef(
            id=92,
            artifact_kind="information_architecture",
            schema_version="2.0",
            sha256="b" * 64,
        )
        stage_input = {
            "contract_refs": contract.refs.model_dump(mode="json"),
            "reference_mode": "none",
            "upstream_artifacts": {
                "product_strategy_v2": {
                    "ref": strategy_ref.model_dump(mode="json")
                },
                "information_architecture": {
                    "ref": ia_ref.model_dump(mode="json")
                },
            },
        }
        payload = design_dna_payload(stage_input)
        payload["composition"]["hierarchy"] = (
            "Lead with outcome using a shadcn card and tailwind class accents."
        )
        payload["reference_mode"] = "vision"
        # Drop two roles after schema parse via construct so normalize must refill.
        valid = DesignDNA.model_validate(payload)
        incomplete = valid.model_dump(mode="json")
        incomplete["color_tokens"] = incomplete["color_tokens"][:6]
        messy = DesignDNA.model_construct(**{
            **{
                key: getattr(valid, key)
                for key in DesignDNA.model_fields
                if key != "color_tokens"
            },
            "color_tokens": tuple(
                type(valid.color_tokens[0]).model_validate(item)
                for item in incomplete["color_tokens"]
            ),
            "reference_mode": "vision",
        })

        healed = normalize_design_dna(
            messy,
            context=contract.validation_context,
            product_strategy_ref=strategy_ref,
            information_architecture_ref=ia_ref,
            expected_reference_mode="none",
        )
        report = validate_design_dna(
            healed,
            context=contract.validation_context,
            product_strategy_ref=strategy_ref,
            information_architecture_ref=ia_ref,
            expected_reference_mode="none",
        )
        assert report.passed, report.model_dump()
        assert healed.reference_mode == "none"
        assert len(healed.color_tokens) == 8
        assert "shadcn" not in healed.composition.hierarchy.casefold()
        assert "tailwind class" not in healed.composition.hierarchy.casefold()
    finally:
        prepared.db.close()
