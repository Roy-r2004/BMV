"""A declared NAME that contains an AI word is not AI logic the pilot performs.

Production request 16 was refused three times because the pilot spec said
"Multi-Model Inference Gateway" and `_AI_LOGIC` matched "Model Inference"
inside it. That is the name of a thing being procured, not something the pilot
does. In an AI-infrastructure engagement every module name carries those words
by necessity, so the rule could never pass — two runs with explicit prompt
steering failed before this was changed.

The rule keeps its teeth: AI that ACTS is still caught, and naming another
module is still a dependency.
"""
from app.pipeline.registry import _AI_LOGIC, _declared_names, _without_names, pilot_isolation_findings

GATEWAY = {"id": "g", "name": "Multi-Model Inference Gateway",
           "client_facing_name": "Multi-Model Inference Gateway"}


def test_a_name_is_masked_before_the_sentence_is_read_for_behaviour():
    names = _declared_names([GATEWAY])
    sentence = "Multi-Model Inference Gateway records each score."
    assert _AI_LOGIC.search(sentence), "the raw sentence trips the pattern — this is the false positive"
    assert not _AI_LOGIC.search(_without_names(sentence, names)), "the name must be masked out"


def test_a_pilot_whose_own_name_carries_ai_words_is_allowed():
    pilot = {
        "id": "p", "pilot": True, "client_facing_name": "Baseline Measurement Harness",
        "purpose": "Run a fixed prompt set through each candidate and have a clinician score the answers by hand.",
        "spec": {"features": [{"name": "Multi-Model Inference Scorecard",
                               "description": "A written rubric the clinician fills in for each candidate."}]},
    }
    assert pilot_isolation_findings([pilot, GATEWAY]) == []


def test_ai_that_acts_is_still_caught():
    pilot = {"id": "p", "pilot": True, "client_facing_name": "Intake Pilot",
             "purpose": "The AI classifies each reply and decides which centre fits.", "spec": {}}
    out = pilot_isolation_findings([pilot])
    assert out and "AI logic" in out[0]["issue"]


def test_naming_another_module_is_still_a_dependency():
    """Masking applies to the AI-logic read only. The dependency check reads
    the unmasked string, because naming another module IS the dependency this
    rule exists to catch."""
    pilot = {"id": "p", "pilot": True, "client_facing_name": "Intake Pilot",
             "purpose": "Hands the order to the Multi-Model Inference Gateway for processing.", "spec": {}}
    out = pilot_isolation_findings([pilot, GATEWAY])
    assert out and "depends on" in out[0]["issue"]
