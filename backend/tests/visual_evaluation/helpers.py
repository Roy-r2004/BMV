from __future__ import annotations

import json
import re
import base64
import io
from dataclasses import dataclass
from typing import Any

import pytest
from PIL import Image

from app.application.visual_evaluation.service import (
    evaluate_v2_candidate_visuals,
)
from app.core.config import settings
from app.domain.schemas.visual_evaluation import VISUAL_DIMENSIONS
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from tests.runtime_validation.helpers import (
    PreparedRuntimeCandidate,
    prepare_runtime_candidate,
    run_phase4,
)


def _prompt(messages: list[dict]) -> str:
    content = messages[0]["content"]
    if isinstance(content, str):
        return content
    return next(item["text"] for item in content if item["type"] == "text")


def _section(prompt: str, header: str, next_header: str) -> Any:
    raw = prompt.split(header, 1)[1].split(next_header, 1)[0].strip()
    return json.loads(raw)


def _evidence(prompt: str) -> list[dict]:
    return _section(prompt, "EVIDENCE:", "TYPED CONTRACTS:")


def _dimension_rows(
    evidence: list[dict],
    *,
    score: int,
) -> list[dict]:
    evidence_ids = [item["evidence_id"] for item in evidence]
    routes = list(dict.fromkeys(item["route"] for item in evidence))
    viewports = list(dict.fromkeys(item["viewport"] for item in evidence))
    band = (
        "exceptional client-ready differentiated"
        if score >= 90
        else "strong professional with only minor weaknesses"
        if score >= 80
        else "usable but ordinary and inconsistent"
        if score >= 70
        else "weak generic and materially unclear"
        if score >= 50
        else "broken and commercially unconvincing"
    )
    cited = f"{evidence_ids[0]} route {routes[0]}"
    return [
        {
            "dimension": dimension,
            "score": score,
            "confidence": 0.9,
            "evidence_ids": evidence_ids,
            "affected_routes": routes,
            "affected_viewports": viewports,
            "rationale": (
                f"{cited} is {band} for the {dimension} score band."
            ),
            "failure_severity": "none" if score >= 80 else "major",
            "deterministic_support": False,
        }
        for dimension in VISUAL_DIMENSIONS
    ]


class VisualFixtureAI:
    name = "fixture-openrouter"

    def __init__(
        self,
        *,
        score: int = 85,
        repairable: bool = False,
        reviewer_disagrees: bool = False,
        technical_repair: bool = False,
    ) -> None:
        self.score = score
        self.repairable = repairable
        self.reviewer_disagrees = reviewer_disagrees
        self.technical_repair = technical_repair
        self.calls: list[tuple[str, str]] = []
        self.critic_count = 0
        self.reviewer_count = 0

    def ask_chat(
        self,
        model: str,
        messages: list[dict],
        max_tokens=None,
        temperature=None,
    ) -> str:
        prompt = _prompt(messages)
        self.calls.append((model, prompt))
        if "primary BMV Phase 5 visual critic" in prompt:
            self.critic_count += 1
            evidence = _evidence(prompt)
            subject = re.search(r"SUBJECT: (\w+)", prompt).group(1)
            group = int(re.search(r"GROUP INDEX: (\d+)", prompt).group(1))
            score = 85 if subject == "refined" else self.score
            findings = []
            if self.repairable and subject == "original":
                contracts = _section(
                    prompt,
                    "TYPED CONTRACTS:",
                    "DETERMINISTIC HARD GATES:",
                )
                page = contracts["page_purpose"]["pages"][0]
                findings.append(
                    {
                        "finding_id": "FIND-001",
                        "source": "critic",
                        "issue_type": "visual_hierarchy",
                        "severity": "major",
                        "dimension_ids": ["hierarchy_and_composition"],
                        "evidence_ids": [
                            item["evidence_id"] for item in evidence
                        ],
                        "routes": [page["route"]],
                        "viewports": list(
                            dict.fromkeys(
                                item["viewport"] for item in evidence
                            )
                        ),
                        "page_ids": [page["page_id"]],
                        "component_ids": [],
                        "rationale": (
                            f"{evidence[0]['evidence_id']} route "
                            f"{page['route']} has weak hierarchy."
                        ),
                        "deterministic_support": False,
                    }
                )
            return json.dumps(
                {
                    "schema_version": "1.0",
                    "actor": "critic",
                    "subject": subject,
                    "group_index": group,
                    "dimensions": _dimension_rows(
                        evidence,
                        score=score,
                    ),
                    "findings": findings,
                }
            )
        if "independent BMV Phase 5 visual reviewer" in prompt:
            self.reviewer_count += 1
            evidence = _evidence(prompt)
            subject = re.search(r"SUBJECT: (\w+)", prompt).group(1)
            score = (
                85
                if subject == "refined"
                else 65
                if self.repairable
                else 70
                if self.reviewer_disagrees
                else self.score
            )
            blind = _section(
                prompt,
                "BLIND COMPARISON MANIFEST:",
                "OUTPUT SCHEMA:",
            )
            comparative_result = "not_applicable"
            comparisons = []
            if blind:
                image_parts = [
                    item
                    for item in messages[0]["content"]
                    if item["type"] == "image_url"
                ]
                half = len(image_parts) // 2

                def quality(parts):
                    values = []
                    for part in parts:
                        encoded = part["image_url"]["url"].split(",", 1)[1]
                        with Image.open(
                            io.BytesIO(base64.b64decode(encoded))
                        ) as image:
                            values.append(image.convert("L").entropy())
                    return sum(values)

                label = (
                    "a"
                    if quality(image_parts[:half])
                    >= quality(image_parts[half:])
                    else "b"
                )
                comparative_result = f"{label}_preferred"
                blind_id = blind["labels"][label][0]["blind_evidence_id"]
                comparisons = [
                    {
                        "dimension": dimension,
                        "preferred": label,
                        "confidence": 0.9,
                        "evidence_ids": [blind_id],
                        "rationale": (
                            f"{blind_id} is stronger for {dimension}."
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
            disagreements = []
            if self.reviewer_disagrees:
                disagreements.append(
                    {
                        "disagreement_id": "DIS-001",
                        "dimension": "business_specificity",
                        "critic_score": self.score,
                        "reviewer_score": score,
                        "evidence_ids": [evidence[0]["evidence_id"]],
                        "rationale": (
                            f"{evidence[0]['evidence_id']} supports a lower "
                            "reviewer band."
                        ),
                    }
                )
            return json.dumps(
                {
                    "schema_version": "1.0",
                    "subject": subject,
                    "recommendation": "accept" if score >= 80 else "reject",
                    "confidence": 0.9,
                    "dimensions": _dimension_rows(evidence, score=score),
                    "disagreements": disagreements,
                    "blocking_findings": [],
                    "score_band_concerns": (
                        [] if score >= 80 else ["below acceptance band"]
                    ),
                    "comparative_result": comparative_result,
                    "comparative_dimensions": comparisons,
                }
            )
        if "screenshot-aware source refiner" in prompt:
            sources = _section(
                prompt,
                "ALLOWED SOURCE FILES:",
                "DESIGN DNA AND RELEVANT CONTRACTS:",
            )
            files = []
            for item in sources:
                source = item["source"]
                if 'className="' in source:
                    source = source.replace(
                        'className="',
                        'className="ring-1 ring-slate-200 ',
                        1,
                    )
                else:
                    source += "\n/* phase5 bounded visual refinement */\n"
                if self.technical_repair and not files:
                    source += "\n<broken-phase5-syntax"
                files.append(
                    {
                        "path": item["path"],
                        "original_sha256": item["sha256"],
                        "source": source,
                    }
                )
            return json.dumps({"schema_version": "1.0", "files": files})
        if "narrow source-only technical repair" in prompt:
            sources = _section(
                prompt,
                "ALLOWED SOURCE FILES:",
                "IMMUTABLE CONTRACTS:",
            )
            return json.dumps(
                {
                    "schema_version": "1.0",
                    "files": [
                        {
                            "path": item["path"],
                            "original_sha256": item["sha256"],
                            "source": item["source"].replace(
                                "\n<broken-phase5-syntax",
                                "",
                            ),
                        }
                        for item in sources
                    ],
                }
            )
        raise AssertionError("Unexpected fixture provider invocation")

    def ask_vision(self, *_args, **_kwargs):
        raise AssertionError("Phase 5 uses registered multimodal chat")

    def is_available(self) -> bool:
        return True


@dataclass
class PreparedVisual:
    runtime: PreparedRuntimeCandidate
    phase4_result: dict

    @property
    def db(self):
        return self.runtime.prepared.db

    @property
    def req(self):
        return self.runtime.prepared.req


@pytest.fixture
def prepared_visual(isolated_runtime_paths, monkeypatch) -> PreparedVisual:
    monkeypatch.setattr(settings, "V2_VISUAL_EVALUATION_ENABLED", True)
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    runtime = prepare_runtime_candidate()
    phase4 = run_phase4(runtime)
    assert (
        phase4["preview_contract"]["status"]
        == "candidate_runtime_validated"
    )
    return PreparedVisual(runtime=runtime, phase4_result=phase4)


def run_phase5(prepared: PreparedVisual, ai: VisualFixtureAI) -> dict:
    return evaluate_v2_candidate_visuals(
        prepared.db,
        prepared.req.id,
        ai,
        JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        req=prepared.req,
        phase4_result=prepared.phase4_result,
    )


__all__ = [
    "PreparedVisual",
    "VisualFixtureAI",
    "prepared_visual",
    "run_phase5",
]
