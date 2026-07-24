from __future__ import annotations

import json
import re

from app.application.services.ai_context import observe_ai_usage
from tests.candidate_generation.helpers import (
    component_batch_payload,
    page_batch_payload,
)
from tests.visual_evaluation.helpers import VisualFixtureAI


def _tier_inputs(prompt: str) -> dict:
    return json.loads(
        prompt.split("Tier 2 inputs:\n", 1)[1]
        .split("\n\nOutput schema:", 1)[0]
    )


def _tier_3_inputs(prompt: str) -> dict:
    return json.loads(
        prompt.split("Tier 3 inputs:\n", 1)[1]
        .split("\n\nOutput schema:", 1)[0]
    )


def _symbol(identifier: str) -> str:
    return "".join(
        part[:1].upper() + part[1:].lower()
        for part in re.findall(r"[A-Za-z0-9]+", identifier)
    ) + "Page"


class Tier2FixtureAI(VisualFixtureAI):
    """Two generation calls plus the normal two Phase 5 calls."""

    def ask_chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens=None,
        temperature=None,
    ) -> str:
        content = messages[0]["content"]
        prompt = (
            content
            if isinstance(content, str)
            else next(item["text"] for item in content if item["type"] == "text")
        )
        if "FAILED_BATCH:" in prompt:
            payload = json.loads(
                prompt.split("FAILED_BATCH:", 1)[1]
                .split("DIAGNOSTICS:", 1)[0]
                .strip()
            )
            stage = f"tier_2_{payload['batch_kind']}_static_repair"
            self.calls.append((stage, model))
            observe_ai_usage(
                {
                    "provider": self.name,
                    "model": model,
                    "purpose": stage,
                    "prompt_tokens": 100,
                    "completion_tokens": 100,
                    "total_tokens": 200,
                    "cost_usd": 0.01,
                    "success": True,
                    "error": None,
                    "latency_ms": 1,
                }
            )
            return json.dumps(payload)
        if "Tier 2 inputs:" not in prompt:
            raw = super().ask_chat(
                model,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if "independent BMV Phase 5 visual reviewer" not in prompt:
                return raw
            payload = json.loads(raw)
            blind = json.loads(
                prompt.split("BLIND COMPARISON MANIFEST:", 1)[1]
                .split("OUTPUT SCHEMA:", 1)[0]
                .strip()
            )
            if blind:
                evidence_id = blind["labels"]["a"][0][
                    "blind_evidence_id"
                ]
                payload["comparative_result"] = "inconclusive"
                payload["comparative_dimensions"] = [
                    {
                        "dimension": dimension,
                        "preferred": "equal",
                        "confidence": 0.9,
                        "evidence_ids": [evidence_id],
                        "rationale": (
                            f"{evidence_id} confirms no material regression "
                            f"for {dimension}."
                        ),
                    }
                    for dimension in (
                        "clarity",
                        "business_specificity",
                        "visual_quality",
                        "trust",
                        "conversion_strength",
                        "mobile_quality",
                    )
                ]
            return json.dumps(payload)
        inputs = _tier_inputs(prompt)
        if 'batch_kind must be "business_components"' in prompt:
            stage = "tier_2_components"
            filtered = dict(inputs)
            filtered["business_component_plan"] = dict(
                inputs["business_component_plan"]
            )
            filtered["business_component_plan"]["components"] = [
                item
                for item in filtered["business_component_plan"]["components"]
                if item["component_id"].startswith("COMP-T2-")
            ]
            payload = component_batch_payload(filtered)
            for file in payload["files"]:
                file["source"] = file["source"].replace(
                    '<section data-bmv-component-id="',
                    (
                        '<section style={{background:"#dbeafe",'
                        'border:"8px solid #1d4ed8",padding:"48px",'
                        'display:"grid",gridTemplateColumns:"1fr 2fr",'
                        'gap:"32px"}} data-bmv-component-id="'
                    ),
                ).replace(
                    "    </section>",
                    (
                        "      <aside>\n"
                        "        <h3>Clinic cancellation policy timeline</h3>\n"
                        "        <ol>\n"
                        "          <li>48 hours: reschedule without fee</li>\n"
                        "          <li>24 hours: confirm practitioner notice</li>\n"
                        "          <li>Same day: contact the clinic desk</li>\n"
                        "        </ol>\n"
                        "      </aside>\n"
                        "    </section>"
                    ),
                )
        else:
            stage = "tier_2_pages"
            wanted = set(inputs["tier_2_projection"]["delta"]["page_ids"])
            filtered = dict(inputs)
            filtered["page_purpose_contract"] = dict(
                inputs["page_purpose_contract"]
            )
            filtered["page_purpose_contract"]["pages"] = [
                item
                for item in filtered["page_purpose_contract"]["pages"]
                if item["page_id"] in wanted
            ]
            filtered["business_component_plan"] = dict(
                inputs["business_component_plan"]
            )
            filtered["business_component_plan"]["page_compositions"] = [
                item
                for item in filtered["business_component_plan"][
                    "page_compositions"
                ]
                if item["page_id"] in wanted
            ]
            filtered["generated_business_components"] = inputs[
                "generated_tier_2_components"
            ]
            filtered["required_page_exports"] = {
                page_id: _symbol(page_id) for page_id in wanted
            }
            payload = page_batch_payload(filtered)
        self.calls.append((stage, model))
        observe_ai_usage(
            {
                "provider": self.name,
                "model": model,
                "purpose": stage,
                "request_id": inputs["tier_2_projection"]["request_id"],
                "prompt_tokens": 100,
                "completion_tokens": 100,
                "total_tokens": 200,
                "cost_usd": 0.01,
                "success": True,
                "error": None,
                "latency_ms": 1,
            }
        )
        return json.dumps(payload)


class Tier3FixtureAI(Tier2FixtureAI):
    """Two Tier 3 generation calls plus grouped Phase 5 calls."""

    def ask_chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens=None,
        temperature=None,
    ) -> str:
        content = messages[0]["content"]
        prompt = (
            content
            if isinstance(content, str)
            else next(
                item["text"]
                for item in content
                if item["type"] == "text"
            )
        )
        if "Tier 3 inputs:" not in prompt:
            return super().ask_chat(
                model,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        inputs = _tier_3_inputs(prompt)
        projection = inputs["tier_projection"]
        if 'batch_kind must be "business_components"' in prompt:
            stage = "tier_3_components"
            filtered = dict(inputs)
            filtered["business_component_plan"] = dict(
                inputs["business_component_plan"]
            )
            filtered["business_component_plan"]["components"] = [
                item
                for item in filtered["business_component_plan"]["components"]
                if item["component_id"].startswith("COMP-T3-")
            ]
            payload = component_batch_payload(filtered)
            for index, file in enumerate(payload["files"]):
                stripe_width = 22 + ((index * 7) % 61)
                stripe_height = 18 + ((index * 11) % 47)
                left_pad = 24 + ((index * 13) % 72)
                file["source"] = file["source"].replace(
                    '<section data-bmv-component-id="',
                    (
                        '<section style={{background:"#ecfdf5",'
                        'border:"8px solid #047857",'
                        f'padding:"48px 48px 48px {left_pad}px",'
                        'display:"grid",gridTemplateColumns:"1fr 2fr",'
                        'gap:"32px"}} data-bmv-component-id="'
                    ),
                ).replace(
                    "    </section>",
                    (
                        "      <div aria-hidden=\"true\" "
                        f"style={{{{width:\"{stripe_width}%\","
                        f"height:\"{stripe_height}px\","
                        "background:\"#065f46\",borderRadius:\"999px\"}} />\n"
                        "    </section>"
                    ),
                )
        else:
            stage = "tier_3_pages"
            wanted = set(projection["delta"]["page_ids"])
            filtered = dict(inputs)
            filtered["page_purpose_contract"] = dict(
                inputs["page_purpose_contract"]
            )
            filtered["page_purpose_contract"]["pages"] = [
                item
                for item in filtered["page_purpose_contract"]["pages"]
                if item["page_id"] in wanted
            ]
            filtered["business_component_plan"] = dict(
                inputs["business_component_plan"]
            )
            filtered["business_component_plan"]["page_compositions"] = [
                item
                for item in filtered["business_component_plan"][
                    "page_compositions"
                ]
                if item["page_id"] in wanted
            ]
            filtered["generated_business_components"] = inputs[
                "generated_tier_components"
            ]
            filtered["required_page_exports"] = {
                page_id: _symbol(page_id) for page_id in wanted
            }
            payload = page_batch_payload(filtered)
        self.calls.append((stage, model))
        observe_ai_usage(
            {
                "provider": self.name,
                "model": model,
                "purpose": stage,
                "request_id": projection["request_id"],
                "prompt_tokens": 100,
                "completion_tokens": 100,
                "total_tokens": 200,
                "cost_usd": 0.01,
                "success": True,
                "error": None,
                "latency_ms": 1,
            }
        )
        return json.dumps(payload)


__all__ = ["Tier2FixtureAI", "Tier3FixtureAI"]
