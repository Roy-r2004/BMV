"""C16 work products: the declaration algebra (P1-P3) and adaptive planning
(design 10.1/10.2). Each test names the law it pins; the mutations the work
breakdown requires are noted where they are caught.

No registry module is imported: a minimal in-memory RegistryView stands in,
because the planner reads only query() and engagement_id - which is itself
part of the law (planning is counts over structural fields, nothing else).
"""
from __future__ import annotations

import ast
import dataclasses
import itertools
import pathlib
import re
from decimal import Decimal

import pytest

from app.engine import types as T
from app.engine.methods.contract import InputSpec
from app.engine.work_products import decl as D
from app.engine.work_products.decl import (
    AllOf,
    Always,
    AnyOf,
    Count,
    Predicate,
    SectionDecl,
    WORK_PRODUCTS,
    WorkProductDecl,
    plan_sections,
)
from app.engine.work_products.plan import plan_work_products

from conftest import sample_entity, sample_payload


# ---------------------------------------------------------------------------
# a stand-in read side: query only, which is all the planner reads
# ---------------------------------------------------------------------------

class View:
    engagement_id = "E-1"

    def __init__(self, *rows: T.Entity):
        self._rows = list(rows)

    def get(self, entity_id):
        return next((e for e in self._rows if e.id == entity_id), None)

    def query(self, kind=None, *, status=None, where=None):
        return [e for e in self._rows if kind is None or e.kind == kind]


_seq = itertools.count(1)


def ent(kind: T.Kind, *, status: T.Status = T.Status.PROPOSED, **overrides) -> T.Entity:
    e = sample_entity(kind, sample_payload(kind, **overrides), status=status)
    return dataclasses.replace(e, id=f"{T.ID_PREFIX[kind]}-{next(_seq)}")


def money(v="100") -> T.Quantity:
    return T.Quantity(Decimal(v), "EUR", T.UnitFamily.MONEY)


def calc_money_fact() -> T.Entity:
    return ent(T.Kind.FACT, basis=T.FactBasis.CALCULATED, formula="FCT-1 * FCT-2",
               inputs=("FCT-1", "FCT-2"), quantity=money())


def planned_ids(plan) -> set[str]:
    return {v.product_id for v in plan.planned}


def unplanned_ids(plan) -> set[str]:
    return {v.product_id for v in plan.unplanned}


# ---------------------------------------------------------------------------
# P3: the mandatory set  (mutation caught: "drop the mandatory set")
# ---------------------------------------------------------------------------

def test_P3_brief_and_integrity_record_always_planned_even_on_an_empty_registry():
    plan = plan_work_products(View())
    assert {"executive_decision_brief", "integrity_record"} <= planned_ids(plan)
    written = {d.entity.payload.product_id for d in plan.deltas}
    assert {"executive_decision_brief", "integrity_record"} <= written
    for v in plan.planned:
        if v.product_id in ("executive_decision_brief", "integrity_record"):
            assert v.because == "mandatory"


def test_every_mandatory_declaration_declares_Always():
    mandatory = [d for d in WORK_PRODUCTS.all() if d.mandatory]
    assert {d.id for d in mandatory} == {"executive_decision_brief", "integrity_record"}
    assert all(isinstance(d.applicability, Always) for d in mandatory)


# ---------------------------------------------------------------------------
# the planned set is a function of the registry
# (mutation caught: "hardcode the planned set")
# ---------------------------------------------------------------------------

def test_registries_with_and_without_calculated_money_facts_plan_different_sets():
    cost = ent(T.Kind.COST)
    with_calc = View(calc_money_fact(), calc_money_fact(), cost)
    without = View(ent(T.Kind.FACT, basis=T.FactBasis.DOCUMENT_EXTRACTED),
                   ent(T.Kind.FACT, basis=T.FactBasis.DOCUMENT_EXTRACTED), cost)
    a, b = plan_work_products(with_calc), plan_work_products(without)
    assert "business_case_financial_model" in planned_ids(a)
    assert "business_case_financial_model" in unplanned_ids(b)
    assert planned_ids(a) != planned_ids(b)


def test_no_workstream_means_no_roadmap_and_no_implementation_plan():
    actions = [ent(T.Kind.ACTION) for _ in range(D._bound("MIN_ACTIONS"))]
    milestone = ent(T.Kind.MILESTONE)
    bare = plan_work_products(View(*actions, milestone))
    assert {"transformation_roadmap", "implementation_plan"} <= unplanned_ids(bare)
    with_ws = plan_work_products(View(*actions, milestone, ent(T.Kind.WORKSTREAM)))
    assert {"transformation_roadmap", "implementation_plan"} <= planned_ids(with_ws)


def test_a_clock_starting_dated_deadline_a_gate_and_day_actions_plan_the_dated_event_plan():
    trio = [ent(T.Kind.DEADLINE, starts_clock=True, date="2026-06-30"),
            ent(T.Kind.MILESTONE, gate=True),
            ent(T.Kind.ACTION, horizon=T.Horizon.DAYS)]
    assert "dated_event_plan" in planned_ids(plan_work_products(View(*trio)))
    trio[0] = ent(T.Kind.DEADLINE, starts_clock=False, date="2026-06-30")
    assert "dated_event_plan" in unplanned_ids(plan_work_products(View(*trio)))


def test_two_data_gaps_an_initiative_and_a_dependency_plan_the_systems_migration_plan():
    rows = [ent(T.Kind.CAPABILITY, capability_class=T.CapabilityClass.DATA_AND_INTEGRATION, gap=T.GapState.MISSING),
            ent(T.Kind.CAPABILITY, capability_class=T.CapabilityClass.DATA_AND_INTEGRATION, gap=T.GapState.PARTIAL),
            ent(T.Kind.INITIATIVE, capability_class=T.CapabilityClass.SOFTWARE_SYSTEM),
            ent(T.Kind.DEPENDENCY)]
    assert "systems_migration_plan" in planned_ids(plan_work_products(View(*rows)))
    assert "systems_migration_plan" in unplanned_ids(plan_work_products(View(*rows[1:])))


def test_customer_process_steps_plan_customer_journeys_and_internal_ones_do_not():
    n = D._bound("MIN_STEPS")
    customer = [ent(T.Kind.PROCESS_STEP, perspective=T.StepPerspective.CUSTOMER, sequence=i) for i in range(n)]
    internal = [ent(T.Kind.PROCESS_STEP, perspective=T.StepPerspective.INTERNAL, sequence=i) for i in range(n)]
    assert "customer_journeys" in planned_ids(plan_work_products(View(*customer)))
    assert "customer_journeys" in unplanned_ids(plan_work_products(View(*internal)))


# ---------------------------------------------------------------------------
# bounds  (mutation caught: "ignore MAX_WORK_PRODUCTS")
# ---------------------------------------------------------------------------

def test_MAX_WORK_PRODUCTS_caps_the_plan_dropping_lowest_count_verdicts_first():
    view = View(ent(T.Kind.RISK), ent(T.Kind.GOVERNANCE),
                *[ent(T.Kind.SUCCESS_CRITERION) for _ in range(3)])
    unbounded = plan_work_products(view)
    assert len(unbounded.planned) > 3
    plan = plan_work_products(view, bounds={"MIN_WORK_PRODUCTS": 2, "MAX_WORK_PRODUCTS": 3})
    assert len(plan.planned) == 3
    # mandatory kept, thickest evidence kept, every drop explained
    assert planned_ids(plan) == {"executive_decision_brief", "integrity_record", "kpi_framework"}
    dropped = {v.product_id: v.because for v in plan.unplanned if "MAX_WORK_PRODUCTS" in v.because}
    assert "risk_register" in dropped and "held" in dropped["risk_register"]


def test_below_MIN_WORK_PRODUCTS_the_planner_refuses_rather_than_inventing():
    with pytest.raises(ValueError, match="MIN_WORK_PRODUCTS"):
        plan_work_products(View(), bounds={"MIN_WORK_PRODUCTS": 5, "MAX_WORK_PRODUCTS": 16})


# ---------------------------------------------------------------------------
# section-level applicability  (mutation caught: "make plan_sections keep empty sections")
# ---------------------------------------------------------------------------

def test_plan_sections_drops_an_empty_non_required_section_and_keeps_required_ones():
    risk = ent(T.Kind.RISK)
    decl = WORK_PRODUCTS.get("risk_register")
    assert plan_sections(decl, View(risk)) == ("risks",)                       # controls empty -> dropped
    assert plan_sections(decl, View(risk, ent(T.Kind.CONTROL))) == ("risks", "controls")
    plan = plan_work_products(View(risk))
    verdict = next(v for v in plan.planned if v.product_id == "risk_register")
    assert verdict.section_ids == ("risks",)


# ---------------------------------------------------------------------------
# P1 / P2 / P3: the algebra is closed
# ---------------------------------------------------------------------------

def test_P1_a_predicate_on_a_text_filter_cannot_be_constructed():
    with pytest.raises(ValueError, match="M2"):
        Count(InputSpec(name="bad", kind=T.Kind.FACT, filter={"statement": "cash"}))
    with pytest.raises(ValueError, match="M2"):
        Count(InputSpec(name="bad", kind=T.Kind.RISK, filter={"text": "churn"}))


def test_P1_a_callable_applicability_is_rejected():
    with pytest.raises(TypeError, match="P1"):
        WorkProductDecl(id="x", title_template="X", applicability=lambda v: (True, "yes"), sections=())


def test_P2_a_section_query_that_is_not_an_inputspec_is_rejected():
    with pytest.raises(TypeError, match="P2"):
        WorkProductDecl(id="x", title_template="X", applicability=Always(),
                        sections=(SectionDecl(id="s", title="S", query=(object(),), renderer="table"),))


def test_P3_a_mandatory_product_without_Always_is_rejected():
    with pytest.raises(ValueError, match="P3"):
        WorkProductDecl(id="x", title_template="X", mandatory=True,
                        applicability=Count(InputSpec(name="risks", kind=T.Kind.RISK)), sections=())


def test_all_21_products_are_registered_with_predicate_applicability():
    decls = WORK_PRODUCTS.all()
    assert len(decls) == 21
    assert all(isinstance(d.applicability, Predicate) for d in decls)
    for d in decls:
        for s in d.sections:
            assert all(isinstance(q, InputSpec) for q in s.query)


# ---------------------------------------------------------------------------
# titles, lineage, preliminary passes
# ---------------------------------------------------------------------------

def test_titles_render_the_central_decision_and_a_hole_stays_unknown():
    central = ent(T.Kind.DECISION, statement="enter the Dutch market", role=T.DecisionRole.CENTRAL)
    plan = plan_work_products(View(central))
    brief = next(d.entity for d in plan.deltas if d.entity.payload.product_id == "executive_decision_brief")
    assert brief.payload.title == "Decision Brief: enter the Dutch market"
    empty = plan_work_products(View())
    brief = next(d.entity for d in empty.deltas if d.entity.payload.product_id == "executive_decision_brief")
    assert brief.payload.title == "Decision Brief: not yet known"


def test_planned_because_carries_counts_and_consumes_carries_matched_ids():
    risk = ent(T.Kind.RISK)
    plan = plan_work_products(View(risk))
    row = next(d.entity for d in plan.deltas if d.entity.payload.product_id == "risk_register")
    assert row.payload.planned_because == "1 risks"
    assert risk.id in row.payload.consumes
    assert risk.id in row.provenance.derived_from


def test_a_preliminary_plan_promises_the_same_verdicts_but_writes_nothing():
    view = View(ent(T.Kind.RISK))
    final, pre = plan_work_products(view), plan_work_products(view, preliminary=True)
    assert pre.deltas == ()
    assert pre.planned == final.planned and pre.unplanned == final.unplanned


def test_a_live_work_product_row_is_not_planned_twice():
    existing = ent(T.Kind.WORK_PRODUCT, product_id="executive_decision_brief")
    plan = plan_work_products(View(existing))
    assert "executive_decision_brief" in planned_ids(plan)
    assert all(d.entity.payload.product_id != "executive_decision_brief" for d in plan.deltas)


def test_unplanned_verdicts_explain_absence_with_counts():
    plan = plan_work_products(View())
    reasons = {v.product_id: v.because for v in plan.unplanned}
    assert "risk_register" in reasons and reasons["risk_register"] == "0 risks"


# ---------------------------------------------------------------------------
# universality: no engagement type, no benchmark vocabulary, no client
# ---------------------------------------------------------------------------

DENIED = ("acquisition", "merger", "turnaround", "market entry", "cost reduction",
          "icarry", "vitalis", "club rally")


def _executable_text(path: pathlib.Path) -> str:
    """Every name and string literal the module can ACT on — docstrings and
    comments excluded.

    The law is that planning never branches on a kind of engagement. Scanning
    raw source instead tests something stricter and wrong: it forbids the
    module from NAMING the thing it refuses to do, so a comment saying "an
    acquisition and a turnaround must plan from counts alone" fails the very
    law it documents. This codebase requires comments that explain why a law
    exists; a scanner that punishes them would be paid for in deleted
    explanations.

    A docstring is unreachable at runtime. A string compared against, stored
    in a table or returned IS reachable, and stays in scope here."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                out.append(node.value)
        elif isinstance(node, ast.Name):
            out.append(node.id)
        elif isinstance(node, ast.Attribute):
            out.append(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append(node.name)
    # identifiers separate words with underscores and slugs with hyphens, so a
    # denied phrase written with spaces would never match `cost_reduction_plan`
    # -- the negative control below caught exactly that hole.
    return re.sub(r"[_\-]+", " ", "\n".join(out)).lower()


@pytest.mark.parametrize("module", ["decl.py", "plan.py"])
def test_work_product_modules_never_act_on_an_engagement_type_or_client(module):
    text = _executable_text(pathlib.Path(D.__file__).parent / module)
    for word in DENIED:
        assert word not in text, f"{module} can act on {word!r}"


def test_the_scanner_still_catches_a_denied_word_in_reachable_code(tmp_path):
    """Negative control: excluding docstrings must not excuse a real branch."""
    good = tmp_path / "good.py"
    good.write_text('"""Plans an acquisition the same as anything else."""\nX = 1\n', encoding="utf-8")
    assert "acquisition" not in _executable_text(good)

    for source in ('if kind == "acquisition":\n    pass\n',
                   'TABLE = {"turnaround": 1}\n',
                   'def cost_reduction_plan():\n    pass\n'):
        bad = tmp_path / "bad.py"
        bad.write_text(source, encoding="utf-8")
        text = _executable_text(bad)
        assert any(w in text for w in DENIED), f"scanner missed: {source!r}"
