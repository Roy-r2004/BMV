"""app/engine/synthesis - what the engagement makes of everything it holds.

Three modules, one law each round:

- conflicts.py  the four detection queries (facts on one MEASURE, two live
                conclusions on one subject, an objective the arithmetic
                refutes, an assumption a confirmed fact contradicts) and the
                per-round re-evaluation of materiality
- resolve.py    what declared precedence recommends, the automatic-but-visible
                resolution the engine may perform alone, the authority-checked
                resolution a human performs, and the DECISION_REQUIRED rows
                that put an open material conflict in front of its owner
- recommend.py  what a recommendation must rest on, and the open material
                questions that make it conditional

Nothing here averages, blends or silently drops a conclusion: two PROPOSED
conclusions on one subject become a CONFLICT, a resolution keeps the loser
queryable, and a conflict that is material and open blocks release (L1). The
regulated screen (regulated.py, C15) is deliberately NOT re-exported here:
it carries the model boundary, and every reader of a conflict would otherwise
pay for the LLM stack to ask what two facts are to each other.
"""
from __future__ import annotations

from app.engine.synthesis.conflicts import (
    SYNTHESIS_ACTOR_REF, UNTESTED_VERDICT, detect_conflicts, reevaluate_materiality,
)
from app.engine.synthesis.recommend import (
    UNSUPPORTED_RECOMMENDATION_LAW, UnsupportedRecommendation, approve_recommendation, conditional_on,
    refresh_conditional_on, support_findings,
)
# `resolve` is re-exported as the FUNCTION, which shadows the submodule of the
# same name on this package: `from app.engine.synthesis import resolve` gives
# the act, not the module. That is what every caller wants; a reader who wants
# the module imports `app.engine.synthesis.resolve` symbols by name.
from app.engine.synthesis.resolve import (
    ResolutionAdvice, ResolutionRefused, advise, auto_resolve, emit_decisions_required, resolve,
)

__all__ = [
    "SYNTHESIS_ACTOR_REF", "UNTESTED_VERDICT", "detect_conflicts", "reevaluate_materiality",
    "ResolutionAdvice", "ResolutionRefused", "advise", "auto_resolve", "emit_decisions_required", "resolve",
    "UNSUPPORTED_RECOMMENDATION_LAW", "UnsupportedRecommendation", "approve_recommendation",
    "conditional_on", "refresh_conditional_on", "support_findings",
]
