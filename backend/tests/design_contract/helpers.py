from __future__ import annotations

import json
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.application.preview_contract.repository import tier_artifact_ref
from app.application.preview_contract.tier_validation import (
    validate_preview_tiers,
)
from app.application.preview_contract.tiers import build_preview_tiers
from app.application.services.ai_context import observe_ai_usage
from app.domain.models import Request
from tests.preview_contract.test_preview_tiers import (
    _db,
    _persist_contract_inputs,
)


@dataclass(frozen=True)
class PreparedPhase1B:
    db: Session
    req: Request
    phase1_result: dict


def prepare_phase1b(
    *,
    request_id: int = 1101,
    page_count: int = 13,
) -> PreparedPhase1B:
    db = _db()
    repository, spec, strategy, context = _persist_contract_inputs(
        db,
        request_id=request_id,
        page_count=page_count,
    )
    tiers = build_preview_tiers(
        spec=spec,
        strategy=strategy,
        context=context,
    )
    validation = validate_preview_tiers(
        tiers,
        spec=spec,
        strategy=strategy,
        context=context,
    )
    persisted = repository.stage_tiers(
        tiers=tiers,
        validation=validation,
    )
    db.commit()
    req = db.get(Request, request_id)
    summary = {
        "generator_version": "v2",
        "status": "contract_ready",
        "customer_source_ref": {
            "id": context.customer_source_ref.id,
            "schema_version": "2.0",
            "sha256": context.customer_source_ref.sha256,
        },
        "product_strategy_ref": {
            "id": context.product_strategy_ref.id,
            "revision": context.product_strategy_ref.revision,
            "schema_version": "1.0",
            "sha256": context.product_strategy_ref.sha256,
            "source_sha256": context.customer_source_ref.sha256,
        },
        "app_spec_ref": {
            **context.app_spec_ref.model_dump(mode="json"),
            "complete": True,
        },
        "tier_artifact_refs": {
            "tier_1": tier_artifact_ref(persisted.tier_1),
            "tier_2": tier_artifact_ref(persisted.tier_2),
            "tier_3": tier_artifact_ref(persisted.tier_3),
        },
    }
    req.generated_pages = json.dumps({"preview_contract": summary})
    db.commit()
    return PreparedPhase1B(
        db=db,
        req=req,
        phase1_result={"preview_contract": summary},
    )


def _stage_input(prompt: str) -> dict:
    marker = "CONTRACT_REFS_AND_INPUTS:\n"
    start = prompt.index(marker) + len(marker)
    raw = prompt[start:].split("\n\n", 1)[0]
    return json.loads(raw)


def _tier_for_requirement(stage_input: dict, requirement_id: str) -> int:
    tiers = stage_input["tier_artifacts"]
    for number, tier in enumerate(tiers, start=1):
        if requirement_id in tier["references"]["requirement_ids"]:
            return number
    raise AssertionError(f"Requirement {requirement_id} missing from tiers")


def strategy_payload(stage_input: dict) -> dict:
    spec = stage_input["canonical_app_spec"]
    active = stage_input["tier_artifacts"][2]["references"]["requirement_ids"]
    page_surfaces = []
    for page in spec["pages"]:
        if page["surface"] not in page_surfaces:
            page_surfaces.append(page["surface"])
    traces = {
        item["requirement_id"]: item for item in spec["traceability"]
    }
    pages = {page["id"]: page for page in spec["pages"]}
    surfaces = []
    for surface in page_surfaces:
        surface_pages = {
            page["id"] for page in spec["pages"] if page["surface"] == surface
        }
        role_ids = []
        for page_id in surface_pages:
            for role_id in pages[page_id]["role_ids"]:
                if role_id not in role_ids:
                    role_ids.append(role_id)
        outcomes = [
            requirement_id
            for requirement_id in active
            if set(traces[requirement_id]["page_ids"]) & surface_pages
        ]
        surfaces.append(
            {
                "surface": surface,
                "role_ids": role_ids,
                "outcome_requirement_ids": outcomes,
                "purpose": (
                    f"Deliver the canonical {surface} outcomes without "
                    "changing customer intent."
                ),
            }
        )
    primary = stage_input["tier_artifacts"][0][
        "primary_journey_proof"
    ]["requirement_id"]
    return {
        "schema_version": "2.0",
        "contract_refs": stage_input["contract_refs"],
        "positioning": {
            "category": "Outcome-led booking service",
            "audience": "Studio customers who value immediate certainty.",
            "promise": "Move from appointment intent to visible confirmation.",
            "problem_frame": (
                "Manual coordination creates delay and uncertainty for "
                "customers and staff."
            ),
        },
        "primary_outcome_requirement_id": primary,
        "prioritized_outcomes": [
            {
                "requirement_id": requirement_id,
                "tier": _tier_for_requirement(stage_input, requirement_id),
                "rationale": (
                    "Preserve this canonical outcome at its cumulative tier."
                ),
            }
            for requirement_id in active
        ],
        "surfaces": surfaces,
        "differentiators": [
            {
                "id": "DIFF-CONFIRMATION",
                "statement": (
                    "Make successful completion unmistakable and durable."
                ),
                "proof_requirement_ids": [primary],
                "design_implication": (
                    "Success evidence receives clear hierarchy without "
                    "prescribing a fixed layout."
                ),
            }
        ],
        "risks": [
            {
                "id": "RISK-UNCERTAINTY",
                "statement": "A weak confirmation state could feel unfinished.",
                "mitigation": "Keep visible success evidence central.",
                "related_requirement_ids": [primary],
            }
        ],
        "assumptions": [],
        "exclusions": ["No invented workflow beyond the canonical contract"],
    }


def _page_outcomes(spec: dict, active: set[str], page_id: str) -> list[str]:
    trace = {
        item["requirement_id"]: item for item in spec["traceability"]
    }
    return [
        requirement["id"]
        for requirement in spec["requirements"]
        if requirement["id"] in active
        and page_id in trace[requirement["id"]]["page_ids"]
    ]


def _page_journeys(spec: dict, page_id: str) -> list[str]:
    return [
        journey["id"]
        for journey in spec["journeys"]
        if journey["start_page_id"] == page_id
        or any(
            step["expected_page_id"] == page_id
            for step in journey["steps"]
        )
    ]


def information_architecture_payload(stage_input: dict) -> dict:
    spec = stage_input["canonical_app_spec"]
    active = set(
        stage_input["tier_artifacts"][2]["references"]["requirement_ids"]
    )
    strategy_ref = stage_input["upstream_artifacts"][
        "product_strategy_v2"
    ]["ref"]
    groups = []
    for surface in ("public", "ops"):
        pages = [page for page in spec["pages"] if page["surface"] == surface]
        if not pages:
            continue
        roles = []
        for page in pages:
            for role_id in page["role_ids"]:
                if role_id not in roles:
                    roles.append(role_id)
        groups.append(
            {
                "id": f"NAV-{surface.upper()}",
                "label": f"{surface.title()} navigation",
                "surface": surface,
                "role_ids": roles,
                "page_ids": [page["id"] for page in pages],
            }
        )
    return {
        "schema_version": "1.0",
        "contract_refs": stage_input["contract_refs"],
        "product_strategy_ref": strategy_ref,
        "navigation_principle": (
            "Lead each role toward its primary outcome while retaining every "
            "canonical route."
        ),
        "navigation_groups": groups,
        "role_access": [
            {
                "role_id": role["id"],
                "entry_page_id": role["default_page_id"],
                "accessible_page_ids": [
                    page["id"]
                    for page in spec["pages"]
                    if role["id"] in page["role_ids"]
                ],
            }
            for role in spec["roles"]
        ],
        "pages": [
            {
                "page_id": page["id"],
                "route": page["route"],
                "surface": page["surface"],
                "purpose": page["purpose"],
                "role_ids": page["role_ids"],
                "required_outcome_requirement_ids": _page_outcomes(
                    spec,
                    active,
                    page["id"],
                ),
                "required_action_ids": page["action_ids"],
                "required_evidence_ids": page["evidence_ids"],
                "journey_ids": _page_journeys(spec, page["id"]),
                "navigation_visibility": (
                    "primary" if page["primary"] else "secondary"
                ),
                "deep_link_reason": None,
                "mobile": {
                    "navigation": "collapsed_menu",
                    "primary_action": (
                        "sticky" if page["action_ids"] else "none"
                    ),
                    "content_priority": [
                        "Primary outcome",
                        "Visible evidence",
                    ],
                    "data_presentation": "not_applicable",
                    "density_adjustment": "relax",
                },
            }
            for page in spec["pages"]
        ],
        "mobile_global_behavior": (
            "Preserve outcome order, readable touch targets, and clear "
            "navigation on narrow screens."
        ),
        "preserves_canonical_routes": True,
        "preserves_all_tier_3_pages": True,
    }


def design_dna_payload(stage_input: dict) -> dict:
    upstream = stage_input["upstream_artifacts"]
    return {
        "schema_version": "1.0",
        "contract_refs": stage_input["contract_refs"],
        "product_strategy_ref": upstream["product_strategy_v2"]["ref"],
        "information_architecture_ref": upstream[
            "information_architecture"
        ]["ref"],
        "reference_mode": stage_input["reference_mode"],
        "composition": {
            "hierarchy": "Outcome evidence leads, supporting detail recedes.",
            "rhythm": "Measured alternation between calm and focused moments.",
            "emphasis": "Use contrast selectively around decisive actions.",
            "layering": "Quiet surfaces separate context from active work.",
        },
        "navigation": {
            "character": "Assured, concise, and easy to scan.",
            "orientation": "contextual",
            "wayfinding": "Maintain clear location and next-step cues.",
            "active_state_direction": "Confident contrast with restrained motion.",
        },
        "typography": {
            "voice": "Warm precision with editorial confidence.",
            "display_direction": "Distinctive but disciplined display forms.",
            "body_direction": "Highly readable forms with generous spacing.",
            "scale_behavior": "Fluid hierarchy that compresses gracefully.",
            "weight_contrast": "Use weight changes for meaning, not decoration.",
        },
        "density": {
            "public_surface": "airy",
            "operations_surface": "balanced",
            "rationale": "Clarity changes by task without changing identity.",
        },
        "imagery": {
            "subject_direction": "Specific moments of customer confidence.",
            "treatment": "Natural light, tactile detail, restrained grading.",
            "placement": "Use imagery where it advances trust or context.",
            "prohibited_treatments": [
                "Generic corporate stock",
                "Decorative image walls",
            ],
        },
        "geometry": {
            "shape_language": "Soft precision with purposeful contrast.",
            "container_behavior": "Containers follow information boundaries.",
            "radius_direction": "Moderate radii with selective sharper moments.",
            "border_direction": "Fine separators reserved for structure.",
            "elevation_direction": "Shallow depth used only for state changes.",
        },
        "motion": {
            "character": "Calm, responsive, and outcome-oriented.",
            "entrance_behavior": "Short reveal that preserves reading order.",
            "interaction_feedback": "Immediate feedback with visible completion.",
            "duration_band_ms": [120, 280],
            "reduced_motion": "Replace movement with immediate state changes.",
        },
        "color_tokens": [
            {
                "semantic_role": role,
                "direction": f"Business-specific {role} direction.",
                "contrast_intent": "Maintain readable semantic contrast.",
            }
            for role in (
                "background",
                "surface",
                "foreground",
                "muted",
                "accent",
                "success",
                "warning",
                "danger",
            )
        ],
        "avoid_list": [
            "Generic gradient excess",
            "Unmotivated glass effects",
            "Decorative dashboard clutter",
        ],
        "fingerprint": {
            "name": "Visible Certainty",
            "signature_traits": [
                "Quiet confidence",
                "Tactile precision",
                "Outcome-led contrast",
            ],
            "recurring_motif": "A measured confirmation rhythm.",
            "differentiation_guard": (
                "Every visual decision must reinforce this business outcome."
            ),
        },
    }


class DesignFixtureAI:
    name = "fixture-provider"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.invalid_stage_responses: dict[str, list[str]] = {}
        self.stage_mutators: dict[str, list] = {}

    def _respond(self, model: str, prompt: str, *, vision: bool) -> str:
        if "Product Strategy stage" in prompt:
            stage = "product_strategy_v2"
            factory = strategy_payload
            cost = 0.01
        elif "Information Architecture stage" in prompt:
            stage = "information_architecture"
            factory = information_architecture_payload
            cost = 0.02
        elif "DesignDNA stage" in prompt:
            stage = "design_dna"
            factory = design_dna_payload
            cost = 0.03
        else:
            raise AssertionError("Unexpected design fixture prompt")
        self.calls.append((stage, model))
        queued = self.invalid_stage_responses.get(stage) or []
        if queued:
            response = queued.pop(0)
        else:
            payload = factory(_stage_input(prompt))
            mutators = self.stage_mutators.get(stage) or []
            if mutators:
                payload = mutators.pop(0)(payload)
            response = json.dumps(payload)
        observe_ai_usage(
            {
                "provider": self.name,
                "model": model,
                "purpose": f"v2_{stage}",
                "request_id": 1101,
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "cost_usd": cost,
                "success": True,
                "error": None,
                "latency_ms": 2,
            }
        )
        time.sleep(0.001)
        return response

    def ask_chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        return self._respond(model, messages[0]["content"], vision=False)

    def ask_vision(self, model: str, prompt: str, image_path: str) -> str:
        return self._respond(model, prompt, vision=True)

    def is_available(self) -> bool:
        return True
