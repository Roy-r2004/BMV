"""Request 138: visible assertions with no evidence to cite are a dead end.

Revision 1 and revision 2 carried the same four issues, byte-identical:

    A visible assertion requires evidence_id.
        TEST-AI-DESCRIPTIONS / TEST-WINE-PAIRINGS /
        TEST-SOCIAL-CAPTIONS / TEST-EVENT-INQUIRY-SCORING

The repair prompt taught no legal move for the code, the claimed surfaces had
no evidence object to bind, and the run died with repair budget remaining. Two
fixes, tested here and in the prompt test:

1. The repair prompt now teaches the legal moves (bind existing evidence on the
   page, or declare the evidence the page already renders).
2. The last-resort salvage drops the unprovable claim instead of losing the
   run, exactly as fix B does for `state_assertion_state_required`.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import app.application.appspec  # noqa: F401  isort:skip  (import cycle: application first)
from app.domain.appspec.sanitize.heal import (  # noqa: E402
    drop_unbindable_state_assertions,
    heal_app_spec_payload,
)


def _request138_shape() -> tuple[dict, dict]:
    tests = []
    for index, name in enumerate(
        ["AI-DESCRIPTIONS", "WINE-PAIRINGS", "SOCIAL-CAPTIONS", "EVENT-INQUIRY-SCORING"]
    ):
        tests.append(
            {
                "id": f"TEST-{name}",
                "name": name,
                "assertions": [
                    {"kind": "route", "page_id": "PAGE-MENU", "description": "route"},
                    {
                        "kind": "visible",
                        "evidence_id": None,
                        "description": f"{name} output is visible",
                    },
                ],
            }
        )
    spec = {"acceptance_tests": tests}
    validation = {
        "issues": [
            {
                "code": "visible_assertion_evidence_required",
                "path": ["acceptance_tests", i, "assertions", 1, "evidence_id"],
                "message": "A visible assertion requires evidence_id.",
                "related_ids": [tests[i]["id"]],
            }
            for i in range(4)
        ]
    }
    return spec, validation


def test_request138_all_four_unprovable_claims_are_dropped() -> None:
    spec, validation = _request138_shape()
    salvaged, actions = drop_unbindable_state_assertions(spec, validation)
    assert len(actions) == 4
    assert all(a.startswith("drop_unprovable_visible_assertion:") for a in actions)
    for test in salvaged["acceptance_tests"]:
        kinds = [a["kind"] for a in test["assertions"]]
        assert kinds == ["route"], f"{test['id']} kept {kinds}"


def test_the_last_assertion_survives_and_fails_closed() -> None:
    spec = {
        "acceptance_tests": [
            {
                "id": "TEST-ONLY",
                "assertions": [
                    {"kind": "visible", "evidence_id": None, "description": "only claim"}
                ],
            }
        ]
    }
    validation = {
        "issues": [
            {
                "code": "visible_assertion_evidence_required",
                "path": ["acceptance_tests", 0, "assertions", 0, "evidence_id"],
            }
        ]
    }
    salvaged, actions = drop_unbindable_state_assertions(spec, validation)
    assert actions == []
    assert salvaged == spec


def test_the_heal_pass_never_touches_the_code() -> None:
    """Ordering: the salvage must stay behind the model's repair chance."""
    spec, validation = _request138_shape()
    healed, actions = heal_app_spec_payload(spec, validation)
    assert not any("visible" in a for a in actions)
    assert healed.get("acceptance_tests") == spec["acceptance_tests"]


def test_the_repair_prompt_teaches_the_legal_move() -> None:
    template = (
        REPO_ROOT / "backend/app/templates/prompts/app_spec_repair.j2"
    ).read_text(encoding="utf-8")
    assert "visible_assertion_evidence_required" in template
    # Both legal moves and the dead-end warning are spelled out.
    assert "DECLARE" in template
    assert "it is proof, not new product behavior" in template
    assert "evidence_id: null" in template
