from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.application.design_contract.service import build_v2_design_contract
from app.application.services.ai_context import observe_ai_usage
from app.core.config import settings
from app.domain.models import Request
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.design_contract.helpers import DesignFixtureAI, prepare_phase1b


@dataclass(frozen=True)
class PreparedPhase2:
    db: Session
    req: Request
    phase2_result: dict


def prepare_phase2(
    *,
    request_id: int = 1301,
    page_count: int = 13,
    spec_mutator: Callable[[dict], None] | None = None,
) -> PreparedPhase2:
    prepared = prepare_phase1b(
        request_id=request_id,
        page_count=page_count,
        spec_mutator=spec_mutator,
    )
    result = build_v2_design_contract(
        prepared.db,
        prepared.req.id,
        DesignFixtureAI(),
        JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        req=prepared.req,
        phase1_result=prepared.phase1_result,
    )
    return PreparedPhase2(
        db=prepared.db,
        req=prepared.req,
        phase2_result=result,
    )


def _shorten_three_page_payload(payload: dict) -> None:
    for requirement in payload["requirements"]:
        if requirement["id"] != "REQ-BOOK":
            requirement["description"] = "Short support info."
    for page in payload["pages"]:
        if page["id"] != "PAGE-BOOK":
            page["purpose"] = "Short support surface."
    for evidence in payload["evidence"]:
        if evidence["page_id"] != "PAGE-BOOK":
            evidence["name"] = f"{evidence['id']} brief"
            evidence["description"] = "Short support evidence."
    for test in payload["acceptance_tests"]:
        if test["id"] != "TEST-BOOK":
            test["description"] = "Short support proof."
            for assertion in test["assertions"]:
                assertion["description"] = "Short support visible."
                assertion["expected"] = "brief"


def _append_service_catalog_entities(payload: dict, *, entity_count: int) -> None:
    booking_page = next(page for page in payload["pages"] if page["id"] == "PAGE-BOOK")
    booking_state_id = booking_page["state_ids"][0]
    for index in range(1, entity_count + 1):
        suffix = f"CATALOG-{index:02d}"
        requirement_id = f"REQ-{suffix}"
        capability_id = f"CAP-{suffix}"
        entity_id = f"ENTITY-{suffix}"
        evidence_id = f"EVIDENCE-{suffix}"
        test_id = f"TEST-{suffix}"
        payload["requirements"].append(
            {
                "id": requirement_id,
                "title": f"Compare service option {index}",
                "description": (
                    "Customers can compare package names, durations, prices, and "
                    f"benefits for service option {index}."
                ),
                "priority": "must",
                "verification_mode": "content",
                "source_refs": ["customer_input.preview_features"],
            }
        )
        payload["entities"].append(
            {
                "id": entity_id,
                "name": f"Service Catalog {index}",
                "description": (
                    f"A safe seeded service-catalog record {index} for booking comparisons."
                ),
                "fields": [
                    {
                        "id": f"FIELD-{suffix}-NAME",
                        "name": "Service Name",
                        "description": "Customer-visible service name.",
                        "type": "string",
                        "required": True,
                        "enum_values": [],
                        "reference_entity_id": None,
                    },
                    {
                        "id": f"FIELD-{suffix}-DURATION",
                        "name": "Duration Minutes",
                        "description": "Expected appointment duration in minutes.",
                        "type": "integer",
                        "required": True,
                        "enum_values": [],
                        "reference_entity_id": None,
                    },
                    {
                        "id": f"FIELD-{suffix}-PRICE",
                        "name": "Price",
                        "description": "Displayed package price.",
                        "type": "number",
                        "required": True,
                        "enum_values": [],
                        "reference_entity_id": None,
                    },
                ],
            }
        )
        payload["capabilities"].append(
            {
                "id": capability_id,
                "name": f"Service catalog option {index}",
                "description": (
                    f"Present service option {index} with duration and pricing detail."
                ),
                "requirement_ids": [requirement_id],
                "role_ids": ["ROLE-CUSTOMER"],
                "entity_ids": [entity_id],
            }
        )
        booking_page["capability_ids"].append(capability_id)
        booking_page["evidence_ids"].append(evidence_id)
        payload["evidence"].append(
            {
                "id": evidence_id,
                "page_id": "PAGE-BOOK",
                "name": f"Service catalog option {index}",
                "description": (
                    f"Service option {index} shows package name, price, duration, and compareable benefits."
                ),
                "kind": "text",
                "capability_ids": [capability_id],
            }
        )
        payload["acceptance_tests"].append(
            {
                "id": test_id,
                "name": f"Service option {index} is visible",
                "description": f"Prove service option {index} content is present.",
                "requirement_ids": [requirement_id],
                "journey_id": None,
                "assertions": [
                    {
                        "kind": "visible",
                        "description": f"The service option {index} content is visible.",
                        "page_id": "PAGE-BOOK",
                        "state_id": booking_state_id,
                        "evidence_id": evidence_id,
                        "expected": f"option {index}",
                    }
                ],
            }
        )
        payload["traceability"].append(
            {
                "requirement_id": requirement_id,
                "capability_ids": [capability_id],
                "page_ids": ["PAGE-BOOK"],
                "evidence_ids": [evidence_id],
                "journey_ids": [],
                "acceptance_test_ids": [test_id],
            }
        )


def prompt_variant_prepare_kwargs(variant_id: str) -> dict[str, Any]:
    if variant_id == "small_three_page":
        return {"spec_mutator": _shorten_three_page_payload}
    if variant_id in {"exact_five_page_booking", "long_description_booking"}:
        return {
            "spec_mutator": lambda payload: _append_service_catalog_entities(
                payload, entity_count=1
            )
        }
    if variant_id == "larger_service_catalog_booking":
        return {
            "spec_mutator": lambda payload: _append_service_catalog_entities(
                payload, entity_count=2
            )
        }
    if variant_id == "maximum_supported_tier1":
        return {
            "spec_mutator": lambda payload: _append_service_catalog_entities(
                payload, entity_count=4
            )
        }
    return {}


def _stage_input(prompt: str) -> dict:
    marker = "COMPOSITION_INPUTS:\n"
    return json.loads(prompt.split(marker, 1)[1].strip())


def _words(value: str) -> list[str]:
    blocked = {
        "action",
        "business",
        "component",
        "content",
        "data",
        "display",
        "information",
        "page",
        "show",
        "user",
    }
    return [
        word
        for word in re.findall(r"[a-z0-9]+", value.casefold())
        if len(word) >= 4 and word not in blocked
    ]


def business_component_payload(stage_input: dict) -> dict:
    spec = stage_input["canonical_app_spec"]
    page_contract = stage_input["page_purpose_contract"]
    capabilities = {item["id"]: item for item in spec["capabilities"]}
    actions = {item["id"]: item for item in spec["actions"]}
    components = []
    compositions = []
    component_by_page: dict[str, str] = {}
    for page in page_contract["pages"]:
        component_id = f"COMP-{page['page_id'].removeprefix('PAGE-')}"
        component_by_page[page["page_id"]] = component_id
        linked_caps = [
            capabilities[item] for item in page["capability_ids"]
        ]
        entity_ids: list[str] = []
        for capability in linked_caps:
            for entity_id in capability["entity_ids"]:
                if entity_id not in entity_ids:
                    entity_ids.append(entity_id)
        for action_id in page["action_ids"]:
            entity_id = actions[action_id]["entity_id"]
            if entity_id and entity_id not in entity_ids:
                entity_ids.append(entity_id)
        language = []
        for source in (
            " ".join(item["name"] for item in linked_caps),
            " ".join(
                actions[item]["name"] for item in page["action_ids"]
            ),
            page["goal"],
        ):
            for word in _words(source):
                if word not in language:
                    language.append(word)
        language = language[:4] or ["appointment"]
        purpose_terms = " and ".join(language[:2])
        components.append(
            {
                "component_id": component_id,
                "name": "AppointmentDashboard",
                "purpose": (
                    f"Coordinate the {purpose_terms} workflow and make its "
                    "canonical outcome visibly complete."
                ),
                "component_kind": (
                    "business_action"
                    if page["action_ids"]
                    else "business_content"
                ),
                "domain_language": language,
                "page_ids": [page["page_id"]],
                "role_ids": page["role_ids"],
                "requirement_ids": page["requirement_ids"],
                "entity_ids": entity_ids,
                "capability_ids": page["capability_ids"],
                "state_ids": page["state_ids"],
                "action_ids": page["action_ids"],
                "evidence_ids": page["evidence_ids"],
                "content_responsibilities": [
                    "Explain the next appointment decision clearly."
                ],
                "data_responsibilities": [
                    "Show the current booking status and details."
                ],
                "interaction_responsibilities": [
                    "Submit the canonical booking action."
                ]
                if page["action_ids"]
                else [],
                "requires_component_ids": [],
                "shared_across_pages": False,
            }
        )
        compositions.append(
            {
                "page_id": page["page_id"],
                "ordered_component_ids": [component_id],
            }
        )
    state_map = {item["id"]: item for item in spec["states"]}
    state_bindings = []
    for page in page_contract["pages"]:
        component_id = component_by_page[page["page_id"]]
        for state_id in page["state_ids"]:
            evidence_ids = [
                item
                for item in state_map[state_id]["evidence_ids"]
                if item in page["evidence_ids"]
            ]
            if evidence_ids:
                state_bindings.append(
                    {
                        "component_id": component_id,
                        "state_id": state_id,
                        "visible_evidence_ids": evidence_ids,
                    }
                )
    return {
        "schema_version": "1.0",
        "contract_refs": stage_input["composition_contract_refs"],
        "page_purpose_ref": stage_input["page_purpose_ref"],
        "components": components,
        "page_compositions": compositions,
        "action_trigger_bindings": [
            {
                "action_id": action_id,
                "component_id": component_by_page[
                    actions[action_id]["page_id"]
                ],
                "trigger_label": actions[action_id]["name"],
            }
            for page in page_contract["pages"]
            for action_id in page["action_ids"]
        ],
        "component_state_bindings": state_bindings,
    }


def _seed_value(field: dict):
    if field["type"] == "enum":
        return field["enum_values"][0]
    if field["type"] == "boolean":
        return True
    if field["type"] == "integer":
        return 1
    if field["type"] == "number":
        return 125.0
    if field["type"] == "date":
        return "2026-08-15"
    if field["type"] == "datetime":
        return "2026-08-15T10:00:00Z"
    if field["type"] == "reference":
        return "BOOKING-REFERENCE-01"
    if field["type"] == "list":
        return ["consultation", "follow-up"]
    return f"Realistic {field['name'].casefold()} value"


def content_data_payload(stage_input: dict) -> dict:
    spec = stage_input["canonical_app_spec"]
    pages = stage_input["page_purpose_contract"]["pages"]
    component_plan = stage_input["business_component_plan"]
    components = {
        item["component_id"]: item
        for item in component_plan["components"]
    }
    component_for_page = {
        page_id: item["component_id"]
        for item in component_plan["components"]
        for page_id in item["page_ids"]
    }
    page_contract = {item["page_id"]: item for item in pages}
    evidence = {
        item["id"]: item
        for item in spec["evidence"]
        if any(item["id"] in page["evidence_ids"] for page in pages)
    }
    content_items = [
        {
            "content_id": f"CONTENT-{evidence_id.removeprefix('EVIDENCE-')}",
            "semantic_kind": (
                "success"
                if "confirmation" in item["name"].casefold()
                else "instruction"
            ),
            "value": item["description"],
            "provenance": "canonical_contract",
            "page_ids": [item["page_id"]],
            "component_ids": [component_for_page[item["page_id"]]],
            "requirement_ids": page_contract[item["page_id"]][
                "requirement_ids"
            ],
        }
        for evidence_id, item in evidence.items()
    ]
    entity_ids = []
    for component in components.values():
        for entity_id in component["entity_ids"]:
            if entity_id not in entity_ids:
                entity_ids.append(entity_id)
    collections = []
    collection_by_entity = {}
    entities = {item["id"]: item for item in spec["entities"]}
    for entity_id in entity_ids:
        entity = entities[entity_id]
        collection_id = f"DATA-{entity_id.removeprefix('ENTITY-')}"
        collection_by_entity[entity_id] = collection_id
        component_ids = [
            component["component_id"]
            for component in components.values()
            if entity_id in component["entity_ids"]
        ]
        page_ids = [
            page_id
            for component_id in component_ids
            for page_id in components[component_id]["page_ids"]
        ]
        fields = [field["id"] for field in entity["fields"]]
        collections.append(
            {
                "collection_id": collection_id,
                "entity_id": entity_id,
                "purpose": (
                    f"Provide realistic {entity['name'].casefold()} records "
                    "for the accepted Tier 1 workflow."
                ),
                "page_ids": list(dict.fromkeys(page_ids)),
                "component_ids": component_ids,
                "field_ids": fields,
                "seed_records": [
                    {
                        "record_id": (
                            f"RECORD-{entity_id.removeprefix('ENTITY-')}-01"
                        ),
                        "values": [
                            {
                                "field_id": field["id"],
                                "value": _seed_value(field),
                            }
                            for field in entity["fields"]
                        ],
                    }
                ],
            }
        )
    content_ids_by_page = {
        page["page_id"]: [
            item["content_id"]
            for item in content_items
            if page["page_id"] in item["page_ids"]
        ]
        for page in pages
    }
    state_map = {item["id"]: item for item in spec["states"]}
    component_state = {
        (binding["component_id"], binding["state_id"], evidence_id)
        for binding in component_plan["component_state_bindings"]
        for evidence_id in binding["visible_evidence_ids"]
    }
    evidence_bindings = []
    for evidence_id, item in evidence.items():
        component_id = component_for_page[item["page_id"]]
        state_id = next(
            (
                state["id"]
                for state in spec["states"]
                if (
                    state["page_id"] == item["page_id"]
                    and (
                        component_id,
                        state["id"],
                        evidence_id,
                    )
                    in component_state
                )
            ),
            None,
        )
        if state_id:
            evidence_bindings.append(
                {
                    "evidence_id": evidence_id,
                    "binding_kind": "component_state",
                    "content_ids": [],
                    "collection_ids": [],
                    "component_id": component_id,
                    "state_id": state_id,
                }
            )
        else:
            content_id = next(
                item["content_id"]
                for item in content_items
                if evidence_id in item["content_id"]
            )
            evidence_bindings.append(
                {
                    "evidence_id": evidence_id,
                    "binding_kind": "content",
                    "content_ids": [content_id],
                    "collection_ids": [],
                    "component_id": None,
                    "state_id": None,
                }
            )
    action_map = {item["id"]: item for item in spec["actions"]}
    action_bindings = []
    for page in pages:
        for action_id in page["action_ids"]:
            action = action_map[action_id]
            if action["entity_id"] or action["kind"] in {
                "fill",
                "select",
                "submit",
            }:
                collection_id = collection_by_entity[action["entity_id"]]
                collection = next(
                    item
                    for item in collections
                    if item["collection_id"] == collection_id
                )
                action_bindings.append(
                    {
                        "action_id": action_id,
                        "collection_ids": [collection_id],
                        "field_ids": collection["field_ids"],
                    }
                )
    return {
        "schema_version": "1.0",
        "contract_refs": stage_input["composition_contract_refs"],
        "page_purpose_ref": stage_input["page_purpose_ref"],
        "business_component_plan_ref": (
            stage_input["business_component_plan_ref"]
        ),
        "content_items": content_items,
        "data_collections": collections,
        "relationships": [],
        "state_payloads": [
            {
                "state_id": state_id,
                "page_id": page["page_id"],
                "content_ids": content_ids_by_page[page["page_id"]],
                "collection_ids": [
                    item["collection_id"]
                    for item in collections
                    if page["page_id"] in item["page_ids"]
                ],
                "component_ids": [
                    component_for_page[page["page_id"]]
                ],
                "evidence_ids": state_map[state_id]["evidence_ids"],
            }
            for page in pages
            for state_id in page["state_ids"]
        ],
        "evidence_bindings": evidence_bindings,
        "action_input_bindings": action_bindings,
    }


class CompositionFixtureAI:
    name = "composition-fixture"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.invalid_stage_responses: dict[str, list[str]] = {}
        self.stage_mutators: dict[str, list] = {}

    def ask_chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float | None = None,
        **_kwargs,
    ) -> str:
        prompt = messages[0]["content"]
        if "BusinessComponentPlan stage" in prompt:
            stage = "business_component_plan"
            factory = business_component_payload
            cost = 0.02
        elif "ContentDataPlan stage" in prompt:
            stage = "content_data_plan"
            factory = content_data_payload
            cost = 0.01
        else:
            raise AssertionError("Unexpected composition fixture prompt")
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
        request_id = _stage_input(prompt)[
            "composition_contract_refs"
        ]["request_id"]
        observe_ai_usage(
            {
                "provider": self.name,
                "model": model,
                "purpose": f"v2_{stage}",
                "request_id": request_id,
                "prompt_tokens": 120,
                "completion_tokens": 80,
                "total_tokens": 200,
                "cost_usd": cost,
                "success": True,
                "error": None,
                "latency_ms": 2,
            }
        )
        time.sleep(0.001)
        return response

    def ask_vision(self, *_args, **_kwargs) -> str:
        raise AssertionError("Phase 3A fixture must not call vision")

    def is_available(self) -> bool:
        return True


__all__ = [
    "CompositionFixtureAI",
    "PreparedPhase2",
    "business_component_payload",
    "content_data_payload",
    "prepare_phase2",
    "prompt_variant_prepare_kwargs",
]
