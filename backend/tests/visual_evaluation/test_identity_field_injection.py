"""Inject service-known Phase 5 identity fields before schema validate."""
from __future__ import annotations

from app.application.visual_evaluation.builder import invoke_structured
from app.domain.schemas.visual_evaluation import VisualReviewerDecision


def test_identity_fields_fill_missing_reviewer_subject(monkeypatch) -> None:
    captured: dict = {}

    class _Provider:
        name = "fixture"

        def ask_chat(self, *_args, **_kwargs):
            return (
                '{"recommendation":"accept","confidence":0.8,'
                '"dimensions":[],"blocking_findings":[],'
                '"score_band_concerns":[],"disagreements":[]}'
            )

    class _Renderer:
        def render(self, *_args, **_kwargs):
            return "prompt"

    def _fake_validate(payload):  # noqa: ANN001
        captured["payload"] = payload
        raise AssertionError("stop-after-identity")

    monkeypatch.setattr(
        VisualReviewerDecision,
        "model_validate",
        staticmethod(_fake_validate),
    )
    try:
        invoke_structured(
            request_id=1,
            stage="reviewer",
            group_index=0,
            routing=type(
                "R",
                (),
                {
                    "timeout_seconds": 30,
                    "prompt_revision": "2026-07-24.1",
                    "max_tokens": 100,
                    "temperature": 0.1,
                    "capability": type(
                        "C",
                        (),
                        {
                            "model": "m",
                            "family": "f",
                            "capability": "multimodal_chat",
                        },
                    )(),
                },
            )(),
            template_name="prompts/v2_visual_reviewer.j2",
            template_values={},
            output_schema=VisualReviewerDecision,
            ai_provider=_Provider(),
            template_renderer=_Renderer(),
            phase_deadline=__import__("time").monotonic() + 30,
            identity_fields={"subject": "original"},
        )
    except Exception as exc:
        assert "stop-after-identity" in str(exc)
    assert captured["payload"]["subject"] == "original"
