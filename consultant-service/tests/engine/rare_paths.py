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
# EMPTY, and that is a measurement rather than an omission. The trace of all
# fifteen engagements walks 282 scoped functions and every one of them is walked
# by at least two core cases, so the single-path law currently needs no
# exception at all.
#
# Four claims stood here and have been withdrawn, each because the run stopped
# reaching the function it named - never because the law was relaxed:
#
#   app/engine/gates/laws.py:_finding        and
#   app/engine/gates/release.py:_reason
#     Both exist only to describe a FAILURE, and the fifteen fake engagements no
#     longer have one: every material question the engine raises is answered or
#     recorded unknown before the gate, so `run_laws` returns no finding in any
#     case and neither function is entered. The unit tests named by the two
#     withdrawn entries still walk them deliberately, which is now their only
#     cover; a benchmark case that walks them again would have to be an
#     engagement that really does reach the gate dirty, not one arranged to.
#
#   app/engine/synthesis/regulated.py:_flag_recommendation      and
#   app/engine/synthesis/recommend.py:withdraw_licensed_advice.<locals>.<genexpr>
#     The licensed-advice path. Under the fake the screen claims no regulated
#     domain at all (oracle.py says so in its own docstring), so no live
#     RECOMMENDATION is ever flagged and neither half is reached. Both were
#     entered here on the expectation that a RECOMMENDATION producer would make
#     them reachable; it made the ROWS exist, not the classification.
#
# A path walked by NO case is not what this law is about: `single_path_findings`
# iterates the trace, so a function nothing reaches is never judged by it. The
# entry would have to be re-added, with evidence, the day a case walks it once.
# Empty, and that is a claim rather than an oversight: the two entries this
# table held (gates/laws.py:_finding, gates/release.py:_reason) name functions
# that no longer exist under those names, and the guard below refuses an entry
# whose function the run never executed -- it fails on each of them if restored.
# Nothing in the engine currently claims an exemption from the single-path law.
RARE_PATHS: dict[str, str] = {}
