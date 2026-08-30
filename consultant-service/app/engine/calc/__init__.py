"""app/engine/calc - the only producer of a numeric value in the engine.

Three modules:

- units.py     parsing and formatting of Quantity, UnitFamily inference and
               comparable(a, b), reusing the r30 number grammar
               (app/pipeline/registry._numbers, _infer_unit, canonical_capacity_unit)
- arith.py     DecimalCalculator: product / total / ratio / convert_period in
               exact Decimal arithmetic, recompute() as equality, and every
               refusal the Calculator protocol names
- reconcile.py reconcile(a, b) over two facts sharing a MEASURE: question,
               distinct, conflict (VALUE / DEFINITION / CLIENT_VS_RECORD) or
               same. Nothing here averages.

The calculator boundary types (Calculator, CalcResult, IncomparableInputs,
Reconciliation, RegistryView) are contracts.py section 8 and have ONE
definition, in app/engine/registry.py. They are imported from there without
a fallback on purpose: a private copy would make arith.py raise an
IncomparableInputs that no consumer's `except` clause catches, and a refusal
nobody catches becomes a crash instead of a CONFLICT. The names are
re-exported here so calc's own modules and its callers share one address.
"""
from __future__ import annotations

from app.engine.registry import CalcResult, Calculator, IncomparableInputs, Reconciliation, RegistryView

from app.engine.calc.units import (  # noqa: E402
    COMPARABLE, INCOMPARABLE, UNKNOWN_DIMENSION, comparable, family_of, format_quantity, parse_quantity,
    required_dimensions,
)
from app.engine.calc.arith import DecimalCalculator, PERIOD_STEPS  # noqa: E402
from app.engine.calc.reconcile import reconcile  # noqa: E402

__all__ = [
    "CalcResult", "Calculator", "IncomparableInputs", "Reconciliation", "RegistryView",
    "COMPARABLE", "INCOMPARABLE", "UNKNOWN_DIMENSION", "comparable", "family_of", "format_quantity",
    "parse_quantity", "required_dimensions", "DecimalCalculator", "PERIOD_STEPS", "reconcile",
]
