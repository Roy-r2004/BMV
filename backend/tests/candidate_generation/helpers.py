from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.application.composition_contract.service import (
    build_v2_composition_contract,
)
from app.application.services.ai_context import observe_ai_usage
from app.core.config import settings
from app.domain.models import Request
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.composition_contract.helpers import (
    CompositionFixtureAI,
    prepare_phase2,
)


@dataclass(frozen=True)
class PreparedPhase3A:
    db: Session
    req: Request
    phase3a_result: dict


def prepare_phase3a(
    *,
    request_id: int = 1601,
    page_count: int = 13,
) -> PreparedPhase3A:
    prepared = prepare_phase2(
        request_id=request_id,
        page_count=page_count,
    )
    result = build_v2_composition_contract(
        prepared.db,
        prepared.req.id,
        CompositionFixtureAI(),
        JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        req=prepared.req,
        phase2_result=prepared.phase2_result,
    )
    return PreparedPhase3A(
        db=prepared.db,
        req=prepared.req,
        phase3a_result=result,
    )


def _candidate_inputs(prompt: str) -> dict:
    marker = "CANDIDATE_INPUTS:\n"
    return json.loads(prompt.split(marker, 1)[1].strip())


def _symbol(identifier: str, suffix: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", identifier)
    return "".join(part[:1].upper() + part[1:].lower() for part in parts) + suffix


def component_batch_payload(inputs: dict) -> dict:
    plan = inputs["business_component_plan"]
    interactions = {
        item["trigger_component_id"]: item
        for item in inputs["interaction_contract"]["interactions"]
    }
    files = []
    for component in plan["components"]:
        component_id = component["component_id"]
        symbol = _symbol(component_id, "Component")
        interaction = interactions.get(component_id)
        action_rows = []
        state_declaration = ""
        import_row = ""
        if interaction:
            transition = interaction["transitions"][0]
            import_row = 'import { useState } from "react";\n'
            state_declaration = (
                f'  const [activeState, setActiveState] = useState("'
                f'{transition["from_state_id"]}");\n'
            )
            transition_ids = [
                transition["transition_id"]
                for transition in interaction["transitions"]
            ]
            input_rows = []
            for field_id in interaction["input_field_ids"]:
                input_rows.extend(
                    [
                        f'      <label htmlFor="{field_id}">{field_id}</label>',
                        (
                            f'      <input id="{field_id}" '
                            f'data-bmv-field-id="{field_id}" />'
                        ),
                    ]
                )
            action_rows.append(
                "\n".join(input_rows)
                + ("\n" if input_rows else "")
                + "      <button\n"
                '        type="button"\n'
                f'        data-bmv-action-id="{interaction["action_id"]}"\n'
                f'        data-bmv-transition-id="{transition_ids[0]}"\n'
                f'        onClick={{() => setActiveState("'
                f'{transition["to_state_id"]}")}}\n'
                "      >\n"
                "        Complete booking\n"
                "      </button>"
            )
        state_rows = []
        for state_id in component["state_ids"]:
            if interaction:
                state_rows.append(
                    f'      {{activeState === "{state_id}" ? '
                    f'<span data-bmv-state-id="{state_id}">{state_id}</span> '
                    ": null}"
                )
            else:
                state_rows.append(
                    f'      <span data-bmv-state-id="{state_id}">'
                    f"{state_id}</span>"
                )
        success_evidence = {
            evidence_id
            for transition in (interaction or {}).get("transitions", [])
            for evidence_id in transition["success_evidence_ids"]
        }
        evidence_rows = []
        for evidence_id in component["evidence_ids"]:
            if interaction and evidence_id in success_evidence:
                evidence_rows.append(
                    f'      <p data-bmv-evidence-id="{evidence_id}" '
                    f'hidden={{activeState !== "'
                    f'{interaction["transitions"][0]["to_state_id"]}"}}>'
                    f"{evidence_id}</p>"
                )
            else:
                evidence_rows.append(
                    f'      <p data-bmv-evidence-id="{evidence_id}">'
                    f"{evidence_id}</p>"
                )
        source = (
            import_row
            + 'import { contentDataPlan } from "../../generated/content-data";\n\n'
            f"export function {symbol}() {{\n"
            f"{state_declaration}"
            "  return (\n"
            f'    <section data-bmv-component-id="{component_id}">\n'
            f"      <h2>{component['name']}</h2>\n"
            "      <small>{contentDataPlan.schema_version}</small>\n"
            + "\n".join(state_rows + action_rows + evidence_rows)
            + "\n"
            "    </section>\n"
            "  );\n"
            "}\n"
        )
        files.append(
            {
                "path": f"src/components/business/{symbol}.tsx",
                "file_kind": "business_component",
                "owner_contract_ids": [component_id],
                "source": source,
            }
        )
    return {
        "schema_version": "1.0",
        "batch_kind": "business_components",
        "files": files,
    }


def page_batch_payload(inputs: dict) -> dict:
    component_batch = inputs["generated_business_components"]
    component_by_id = {
        owner_id: item
        for item in component_batch["files"]
        for owner_id in item["owner_contract_ids"]
    }
    composition_by_page = {
        item["page_id"]: item["ordered_component_ids"]
        for item in inputs["business_component_plan"]["page_compositions"]
    }
    files = []
    for page in inputs["page_purpose_contract"]["pages"]:
        page_id = page["page_id"]
        symbol = inputs["required_page_exports"][page_id]
        component_ids = composition_by_page[page_id]
        imports = []
        usages = []
        for component_id in component_ids:
            component_file = component_by_id[component_id]
            component_symbol = _symbol(component_id, "Component")
            relpath = (
                "../"
                + component_file["path"]
                .removeprefix("src/")
                .removesuffix(".tsx")
            )
            imports.append(
                f'import {{ {component_symbol} }} from "{relpath}";'
            )
            usages.append(f"      <{component_symbol} />")
        tests = "\n".join(
            f'      <span data-bmv-acceptance-test-id="{test_id}" hidden />'
            for test_id in page["acceptance_test_ids"]
        )
        source = (
            "\n".join(imports)
            + "\n\n"
            f"export function {symbol}() {{\n"
            "  return (\n"
            f'    <main data-bmv-page-id="{page_id}"\n'
            f'      data-bmv-mobile-navigation="{page["mobile"]["navigation"]}"\n'
            f'      data-bmv-mobile-primary-action="{page["mobile"]["primary_action"]}"\n'
            f'      data-bmv-mobile-data-presentation="{page["mobile"]["data_presentation"]}"\n'
            f'      data-bmv-mobile-density="{page["mobile"]["density_adjustment"]}"\n'
            "    >\n"
            f"{tests}\n"
            + "\n".join(usages)
            + "\n"
            "    </main>\n"
            "  );\n"
            "}\n"
        )
        files.append(
            {
                "path": f"src/pages/{symbol}.tsx",
                "file_kind": "page",
                "owner_contract_ids": [page_id],
                "source": source,
            }
        )
    return {
        "schema_version": "1.0",
        "batch_kind": "pages",
        "files": files,
    }


class CandidateFixtureAI:
    name = "candidate-fixture"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.stage_mutators: dict[str, list] = {}
        self.repair_mutators: dict[str, list] = {}
        self.last_inputs: dict[str, dict] = {}

    def ask_chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        prompt = messages[0]["content"]
        repair = "narrow Phase 3B technical repair stage" in prompt
        if repair:
            stage_match = re.search(r"Repair only batch ([a-z_]+)", prompt)
            assert stage_match
            stage = stage_match.group(1)
            inputs = self.last_inputs[stage]
            factory = (
                component_batch_payload
                if stage == "business_components"
                else page_batch_payload
            )
            payload = factory(inputs)
            mutators = self.repair_mutators.get(stage) or []
        else:
            inputs = _candidate_inputs(prompt)
            if "business-component generation stage" in prompt:
                stage = "business_components"
                factory = component_batch_payload
            elif "page generation stage" in prompt:
                stage = "pages"
                factory = page_batch_payload
            else:
                raise AssertionError("Unexpected Phase 3B fixture prompt")
            self.last_inputs[stage] = inputs
            payload = factory(inputs)
            mutators = self.stage_mutators.get(stage) or []
        if mutators:
            payload = mutators.pop(0)(payload)
        call_stage = f"{stage}_repair" if repair else stage
        self.calls.append((call_stage, model))
        observe_ai_usage(
            {
                "provider": self.name,
                "model": model,
                "purpose": f"v2_candidate_{call_stage}",
                "request_id": inputs["page_purpose_contract"][
                    "contract_refs"
                ]["request_id"],
                "prompt_tokens": 140,
                "completion_tokens": 110,
                "total_tokens": 250,
                "cost_usd": 0.02,
                "success": True,
                "error": None,
                "latency_ms": 2,
            }
        )
        time.sleep(0.001)
        return json.dumps(payload)

    def ask_vision(self, *_args, **_kwargs) -> str:
        raise AssertionError("Phase 3B never uses vision")

    def is_available(self) -> bool:
        return True


__all__ = [
    "CandidateFixtureAI",
    "PreparedPhase3A",
    "component_batch_payload",
    "page_batch_payload",
    "prepare_phase3a",
]
