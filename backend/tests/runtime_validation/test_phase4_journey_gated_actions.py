"""Journey acceptance assertions must be scoped to the post-action page."""
from __future__ import annotations

import inspect

from app.application.runtime_validation import browser as browser_module


def test_acceptance_steps_skip_other_route_assertions() -> None:
    source = inspect.getsource(browser_module._acceptance_steps)
    assert "no_runtime_errors" in source
    assert 'assertion_route in {None, ""}' in source or "Unscoped visible" in source



def test_journey_enables_gated_actions_before_click() -> None:
    source = inspect.getsource(browser_module)
    assert "_enable_gated_action(page, action)" in source
    assert "skipped_missing_field_hook" in source
