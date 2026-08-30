"""app/engine/specialists - dynamic internal specialist work (spec section 4).

A specialist is a temporary analytical role, never a fixed public agent: an
Assignment (assignment.py) freezes the question, the permitted evidence, the
method, the grants, the forbidden decisions and the budget; the runner
(runner.py) executes the method behind a ScopedView as Actor.SPECIALIST and
admits the result all-or-nothing under S1-S6. Every RESEARCH / MODEL_ASSISTED
method and every tied selection runs only through runner.run(); run_free() is
the loop's only direct-execution door and refuses both (MF1.2).
"""
from app.engine.specialists.assignment import ADMISSION_RULES, Assignment
from app.engine.specialists.runner import (
    AssignmentRequired,
    BudgetedProvider,
    BudgetExceeded,
    RunOutcome,
    run,
    run_free,
)

__all__ = [
    "ADMISSION_RULES", "Assignment", "AssignmentRequired", "BudgetedProvider",
    "BudgetExceeded", "RunOutcome", "run", "run_free",
]
