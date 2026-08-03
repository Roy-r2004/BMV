"""Suite-wide guards.

Roadmap DoD 9 — *total collected test count never drops below 1,107, asserted in
CI.* Enforced here rather than as a test, because a test cannot see how many
tests were collected alongside it, and the failure being guarded against is
tests *disappearing*: a file that stops being collected takes its assertions with
it and the summary line still says `passed`.

0.9 found this the expensive way — eight files in the repo had never been
collected at all, two of them containing zero test functions and a print probe.
Nothing was red. The suite simply did not include them.
"""
from __future__ import annotations

import pytest

#: The DoD's contractual minimum. Do not lower it.
DOD_9_FLOOR = 1_107

#: The ratchet, and the number that actually does the work.
#:
#: A floor 500 below the real count catches nothing — the whole point is to
#: notice a *drop*, and between 1,107 and today there is room to silently lose a
#: third of the suite. Set to the count at the time of the last deliberate
#: change, so removing tests requires editing this line and saying why.
#:
#: Raise it when the suite grows. Lower it only with a reason in the commit
#: message; "CI was red" is not one.
COLLECTED_FLOOR = 1_669  # 1,668 passed + 1 skipped, 2026-08-03 (session 8)


def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    # Only judge a full-suite run. `-k`, `-m` and a narrower path all collect a
    # subset by design — the mutation drivers each run two or three files — and
    # failing those would train everyone to ignore this.
    if config.option.keyword or config.option.markexpr:
        return
    if any(str(arg).rstrip("/") not in ("", ".", "tests") for arg in config.args):
        return
    if len(items) >= COLLECTED_FLOOR:
        return
    raise pytest.UsageError(
        f"DoD 9: collected {len(items)} tests, floor is {COLLECTED_FLOOR} "
        f"(contractual minimum {DOD_9_FLOOR}). Tests have stopped being "
        "collected, or were deleted. A file that silently drops out of "
        "collection still reports `passed`. If the removal was deliberate, "
        "lower COLLECTED_FLOOR in tests/conftest.py and say why."
    )
