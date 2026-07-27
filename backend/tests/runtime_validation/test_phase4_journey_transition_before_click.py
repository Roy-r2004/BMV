"""Transition hooks live on the trigger; observe them before navigation."""
from __future__ import annotations

import inspect

from app.application.runtime_validation import browser as browser_module


def test_journey_observes_transition_marker_before_action_click() -> None:
    source = inspect.getsource(browser_module._journey_result)
    action_idx = source.find("action.first.click(")
    transition_count_idx = source.find("transition_locator.count()")
    assert action_idx > 0
    assert 0 < transition_count_idx < action_idx
