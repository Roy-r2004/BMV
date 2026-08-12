"""Where each class of request lands, and what that pins.

The archetype is chosen by the ui_spec LLM reading the consulting
analysis, so no test in this file can assert what the live classifier will
do next — asserting that would need a model call, and a test that spends
money is a test nobody runs. What CAN be pinned is the measurement: real
probes of the real stages (scripts/classify_probe.py), frozen into
docs/evidence, and the conclusions this project has built on top of them.

Re-measure with:

    python scripts/classify_probe.py       # ~$0.06, writes scripts/out/

then copy the result over the evidence file. If a class starts landing
somewhere else, that is a finding to write up, not a line to edit quietly.

Measured 2026-08-12 (session 38), ten probes, intakes written the way
customers write them. Every row records the `catalog` it ran against, so a
"chatbot -> operations-dashboard" row stays readable later: it says the
console did not exist yet, not that it lost.

THE HEADLINE, and it is not the one the session expected: **archetype
selection is not deterministic for a given intake.** The investment brief
landed on analytics-dashboard, then crm-dashboard, on identical text. What
is stable is the two ends of the range — a brief with an obvious home, and
a brief whose product IS the assistant — and it is only those that are
pinned as equalities below. Pinning a coin flip would produce a test that
fails for the wrong reason on a Tuesday.
"""

import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app import archetypes

PROBE_FILE = (
    pathlib.Path(__file__).resolve().parents[2]
    / "docs" / "evidence" / "session38" / "classification-probe.json"
)


def _rows(probe: str, *, console: bool | None = None) -> list[dict]:
    """Every recorded run of one probe, oldest first. `console` filters to
    the runs taken before or after the assistant console existed."""
    out = []
    for row in json.loads(PROBE_FILE.read_text()):
        if row["probe"] != probe:
            continue
        if console is not None and (archetypes.ASSISTANT_ARCHETYPE in row.get("catalog", [])) != console:
            continue
        out.append(row)
    return out


def test_the_probe_record_exists_and_covers_every_class_the_session_asked_about():
    assert PROBE_FILE.exists(), f"missing {PROBE_FILE} — re-run scripts/classify_probe.py"
    probes = {row["probe"] for row in json.loads(PROBE_FILE.read_text())}
    assert probes == {"investment", "chatbot", "portfolio", "courses", "salon"}


def test_the_control_brief_has_not_moved_in_any_run():
    """A salon is the class this catalogue was built for. If it ever lands
    somewhere else, the probe is measuring the weather and every other row
    in this file is suspect. Two runs, including one taken after a sixth
    archetype was added to the catalogue."""
    landings = [row["archetype"] for row in _rows("salon")]
    assert landings and set(landings) == {"operations-dashboard"}, landings


def test_the_chatbot_class_was_coerced_before_the_console_existed():
    """The recorded failure the assistant-console archetype answers: a
    customer asking for a chatbot got a service dashboard whose anchor was
    a "Select Service" flow, with the product they came to see reduced to
    the fourth item in the navigation."""
    before = _rows("chatbot", console=False)
    assert before, "the pre-console measurement is the reason the shape exists — keep the receipt"
    for row in before:
        assert row["archetype"] == "operations-dashboard"
        assert "Chatbot" in row["navigation"]
        assert row["anchor_kind"] != "assistant"


def test_an_assistant_first_brief_lands_on_the_console_with_a_conversation_anchor():
    """Two different intakes, both assistant-first, both after the shape
    existed. This is the equality worth pinning: the class had no home and
    now has exactly one."""
    after = [row for probe in ("chatbot", "courses") for row in _rows(probe, console=True)]
    assert len(after) >= 2
    for row in after:
        assert row["archetype"] == archetypes.ASSISTANT_ARCHETYPE, row
        assert row["anchor_kind"] == "assistant", row
        assert row["screens"][0] == "conversations", row


def test_adding_the_console_did_not_pull_ordinary_businesses_into_it():
    """The blast-radius check on a new catalogue entry. Nearly every brief
    this pipeline sees is sold an AI front-desk in its consulting summary,
    so the console is a shape any of them could have drifted to."""
    for probe in ("investment", "portfolio", "salon"):
        for row in _rows(probe, console=True):
            assert row["archetype"] != archetypes.ASSISTANT_ARCHETYPE, row


def test_the_investment_class_needs_no_new_shape_but_does_not_pick_one_twice_running():
    """The session-38 brief said this class "already lands on
    analytics-dashboard". Measured three times it landed on
    analytics-dashboard, then on the fallback (a chart bug, since fixed),
    then on crm-dashboard. The brief's conclusion holds — nothing needs
    building, every landing is a credible numbers-or-clients shape — but
    the premise that it lands somewhere specific does not."""
    landings = {row["archetype"] for row in _rows("investment")}
    assert landings <= {"analytics-dashboard", "crm-dashboard", "operations-dashboard"}
    assert len(landings) > 1, (
        "if this ever becomes stable, the instability finding is stale and the "
        "next session should re-measure rather than trust this file"
    )


def test_the_portfolio_class_has_its_navigation_honoured_in_every_run():
    """Step 1 is not an image-stage fix — it lands in the spec, which is
    where the text-truth gate reads its ground truth. True in text-only
    runs, on both archetypes this class has landed on."""
    rows = _rows("portfolio")
    assert rows
    for row in rows:
        assert row["navigation"] == ["Home", "Gallery", "About", "Contact"], row


@pytest.mark.parametrize("probe", ["investment", "chatbot", "portfolio", "courses", "salon"])
def test_every_recorded_archetype_is_one_this_service_can_actually_render(probe):
    for row in _rows(probe):
        assert row["archetype"] in archetypes.ARCHETYPES, row
