"""tests/engine/rare_paths.py - the named exceptions to the single-path law
(design 18.7, MF1.5).

`test_engine_universality.py` profiles all fifteen benchmark engagements and
asks of every function in TRACE_SCOPE: did at least two of the ten core cases
walk it? A function only one engagement reaches is the shape a per-case script
takes - one branch, one client, one path - so the trace reports it.

The honest exception is a path that is rare because the SITUATION is rare, not
because a case name unlocked it. Such a path is listed here with the unit test
that walks it deliberately; the universality test refuses an entry whose test
does not exist, and refuses an entry naming a function the run never executed,
so this table can hold neither a ghost nor an unproven claim.

Adding an entry is therefore a claim with evidence attached. Removing the
function's test, or renaming it, breaks the claim and the guard says so.
"""
from __future__ import annotations

# The scope of the law (design 18.7): the modules where a per-case branch would
# actually change what a client is told - the partner loop, the method
# selector, the planner, synthesis and the gates. Rendering and persistence are
# out of scope because they are downstream of decisions already made, and the
# benchmark harness is out because it is the thing doing the driving.
TRACE_SCOPE_DIRS: tuple[str, ...] = (
    "app/engine/partner",
    "app/engine/synthesis",
    "app/engine/gates",
)
TRACE_SCOPE_FILES: tuple[str, ...] = (
    "app/engine/methods/contract.py",
    "app/engine/work_products/plan.py",
)

# "<path>:<qualname>" -> the name of the unit test that walks it on purpose.
#
# Both entries are the same rare situation: a fifteen-engagement fake run is
# mostly CLEAN, so the two functions that only exist to describe a FAILURE are
# reached by whichever engagements happen to hold a finding. That is rareness
# of the situation, not of a client: the gates run in full on every case, and
# the tests named here construct the failing registry directly, which is a
# stronger walk of the path than any benchmark case gives.
RARE_PATHS: dict[str, str] = {
    # Every Finding the law list emits is built here; fifteen fake runs produce
    # findings in only two of them.
    "app/engine/gates/laws.py:_finding":
        "test_l1_blocks_an_open_conflict_a_recommendation_rests_on",
    # The release record's reason line, written only when a blocking finding is
    # open and the door is therefore shut.
    "app/engine/gates/release.py:_reason":
        "test_a_blocking_finding_reaches_the_record_as_a_reason",
}
