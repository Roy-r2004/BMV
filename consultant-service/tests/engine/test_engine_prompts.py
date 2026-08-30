"""C3-prompts: app/engine/templating.py and app/engine/prompts/*.j2.

Pins (work_breakdown C3-prompts): every template renders with a full
context; a missing variable raises; the marker sentences are present in each
JSON template's SOURCE; no denylist stem and no client name in any .j2
(design 18.3 / 18.4 - the scanner here is the local twin of C24's); the
catalogue rendered by issue_tree.j2 carries every Interrogative and
CapabilityClass value; the verifier clears only with the literal
not_licensed.

Named mutations: remove the "empty list is a real answer" sentence; write
"acquisition" into a template; drop "not_licensed" from the verifier.
"""
from __future__ import annotations

import json
import os
import re

import pytest
from jinja2 import UndefinedError

from app.engine import templating as TP
from app.engine import types as T

_SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PROMPTS_DIR = os.path.join(_SERVICE_ROOT, "app", "engine", "prompts")
_CASES_DIR = os.path.join(_SERVICE_ROOT, "tests", "engine", "benchmarks")

# Design 18.1 / 18.4 - the vocabulary that would make a prompt know what kind
# of engagement it is in. Matched as a case-insensitive substring of the .j2
# SOURCE; rendered output legitimately carries enum values (kinds are
# injected as variables, which is the whole point).
DENYLIST_STEMS = (
    "acquisition", "merger", "m&a", "integration", "market entry", "market_entry",
    "cost reduction", "cost_reduction", "cost-cutting", "restructur", "turnaround",
    "bottleneck", "product launch", "new product", "transformation",
    "customer experience", "customer-experience", "cx", "governance and risk",
    "risk improvement", "ai transformation", "technology transformation",
)

# Ordinary words that happen to sit inside a case's company/document name
# ("... Controls Ltd", "Heads of Terms summary"). The client-name scan
# (design 18.3) is about identity leaking into the engine, not about the
# English language; C24's scanner keeps its own list.
_GENERIC_NAME_WORDS = {
    "process", "controls", "services", "service", "summary", "terms", "heads", "board",
    "group", "report", "notes", "notice", "letter", "email", "draft", "internal", "memo",
    "minutes", "meeting", "schedule", "forecast", "invoice", "contract", "agreement",
    "update", "thread", "extract", "export", "snapshot", "spreadsheet", "analysis",
    "management", "finance", "sales", "marketing", "operations", "logistics", "digital",
    "platform", "systems", "precision", "castings", "foods", "bakery", "marine", "coatings",
    "capital", "partners", "limited", "holdings", "clinic", "controller", "director",
    "founder", "administrator", "committee", "division", "customer", "customers", "business",
    "consulting", "advisory", "industry", "production", "supply", "fleet", "workforce",
    "employment", "investment", "investor", "growth", "pilot", "project", "proposal",
    "one-page", "one-pager", "two-pager", "follow-up", "before", "after", "about",
    "monthly", "count", "usage", "cover", "second", "three", "times", "getting", "wants",
    "prepared", "translated", "ended", "coming", "nearly", "everyone", "himself", "cannot",
    "decide", "hiding", "hiring", "double", "build", "custom", "amber", "coach", "crest",
    "maple", "spiral", "matrix", "kairos", "mandate", "incident", "complaint", "complaining",
    "independent", "provisional", "abridged", "authorisation", "allocation", "commission",
    "insolvency", "fulfilment", "delivery", "payment", "purchasing", "reduction", "rollout",
    "benchmarks", "breakdown", "countdown", "currencies", "headcounts", "messages", "minute",
    "percent", "priorities", "question", "telematics", "undertakings", "vendor", "facility",
    "freezer", "fifteen", "fiscal", "centre", "clause", "churn", "capex", "absorbs",
    "accounts", "invitation", "post-closing", "end-of-support", "z-report", "informe",
    "resumo", "notas", "relat", "reuni", "gesti", "preparado", "conformidade",
    "responsabilidades", "financeiras", "organograma", "junho", "julho", "segunda-feira",
    "march", "april", "august", "september", "pipeline", "estonia", "ireland", "dubai",
    "emirates", "genoa", "liguria", "roubaix",
}


def client_name_tokens() -> set[str]:
    """Every token >= 5 chars of every company, persona, product and document
    name in the 15 case files (design 18.3), minus ordinary words."""
    toks: set[str] = set()

    def walk(o, key=None):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, k)
        elif isinstance(o, list):
            for v in o:
                walk(v, key)
        elif isinstance(o, str) and key in ("name", "company", "product", "products", "title"):
            for t in re.findall(r"[A-Za-z][A-Za-z\-']+", o):
                t = re.sub(r"'s?$", "", t.lower())
                if len(t) >= 5 and t not in _GENERIC_NAME_WORDS:
                    toks.add(t)

    for fn in os.listdir(_CASES_DIR):
        if fn.endswith(".json") and not fn.endswith(".keys.json"):
            with open(os.path.join(_CASES_DIR, fn), encoding="utf-8") as fh:
                walk(json.load(fh))
    return toks


# --- full contexts ---------------------------------------------------------

_ENTITIES = [
    {"id": "E-1", "kind": T.Kind.FACT.value, "text": "orders per week 120", "quantity": "120 per week"},
    {"id": "E-2", "kind": T.Kind.OBJECTIVE.value, "text": "ship on time", "quantity": None},
]

CONTEXTS: dict[str, dict] = {
    "extract_turn.j2": dict(
        turn_id="T-1", turn_number=1, message="We take 120 orders a week and lose a third to delay.",
        open_questions=[{"id": "Q-1", "text": "How many orders per week?"}],
        registered_measures=[{"id": "M-1", "name": "orders per week", "unit_family": T.UnitFamily.CAPACITY.value}],
        candidate_kinds=[T.Kind.BUSINESS_CONTEXT, T.Kind.DECISION, T.Kind.OBJECTIVE, T.Kind.CONSTRAINT,
                         T.Kind.DEADLINE, T.Kind.DECISION_OWNER, T.Kind.STAKEHOLDER, T.Kind.MEASURE, T.Kind.FACT],
    ),
    "extract_document.j2": dict(
        document_id="D-1", document_name="ledger.csv", document_kind="dataset",
        extracted_text="week,orders\n1,118\n2,122",
        registered_measures=[{"id": "M-1", "name": "orders per week", "unit_family": T.UnitFamily.CAPACITY.value}],
    ),
    "revise_hypothesis.j2": dict(
        candidates=[{"id": "DEC-1", "role": T.DecisionRole.STATED_REQUEST.value, "text": "fix the delays"}],
        entities=_ENTITIES,
    ),
    "issue_tree.j2": dict(
        decisions=[{"id": "DEC-1", "role": T.DecisionRole.CENTRAL.value, "text": "fix the delays"}],
        objectives=[{"id": "O-1", "text": "ship on time"}],
        entities=_ENTITIES,
        existing_nodes=[{"id": "I-1", "parent_id": None, "text": "why are orders late?"}],
        max_fanout=T.BOUNDS["MAX_FANOUT"],
    ),
    "phrase_questions.j2": dict(
        entities=_ENTITIES,
        gaps=[{"gap_id": "G-1", "asks_for_kind": T.Kind.FACT.value, "asks_for_filter": {"has_quantity": True},
               "effort": T.EffortClass.OFFHAND.value, "issue_id": "I-1", "issue_text": "why late?",
               "decision_id": "DEC-1", "decision_text": "fix the delays", "why_needed": "baseline"}],
        min_questions=T.BOUNDS["MIN_QUESTIONS_PER_TURN"], max_questions=T.BOUNDS["MAX_QUESTIONS_PER_TURN"],
    ),
    "narrative_section.j2": dict(
        section_title="Situation", section_purpose="what is happening today", audience="the decision owner",
        claims=[{"entity_id": "E-1", "token": "{{S-1}}", "label": "order volume"}],
        findings=[],
    ),
    "regulated_classifier.j2": dict(
        candidates=[{"id": "R-1", "kind": T.Kind.RECOMMENDATION.value, "text": "shorten notice periods"}],
    ),
    "regulated_verifier.j2": dict(
        claim={"entity_id": "R-1", "kind": T.Kind.RECOMMENDATION.value, "text": "shorten notice periods",
               "domain": T.RegulatedDomain.EMPLOYMENT_LAW.value, "trigger": "notice periods", "reason": "statutory"},
        entities=_ENTITIES,
    ),
    "simulated_client.j2": dict(
        persona={"name": "P", "role": "owner", "company": "C", "sector": "s", "country": "c", "size": "n",
                 "temperament": "brisk"},
        unrevealed=[{"topic": "volume", "fact": "120 a week"}], revealed=["we are late"],
        documents=[{"name": "ledger", "kind": "dataset"}], consultant_message="How many orders a week?",
    ),
    "method_generic.j2": dict(
        method_id="capability_gap", method_purpose="find the gaps",
        issue={"id": "I-1", "text": "which capabilities are missing?", "interrogative": T.Interrogative.WHAT.value,
               "target_kind": T.Kind.CAPABILITY.value},
        inputs=_ENTITIES, assumption_grants=[{"id": "A-1", "text": "demand is flat"}],
        output_kinds=[T.Kind.CAPABILITY], instructions="",
    ),
}


def _source(name: str) -> str:
    return TP.template_source(name)


# --- pins ------------------------------------------------------------------

def test_template_set_on_disk_matches_declaration():
    on_disk = sorted(f for f in os.listdir(_PROMPTS_DIR) if f.endswith(".j2"))
    assert on_disk == sorted(TP.TEMPLATE_NAMES)
    assert set(CONTEXTS) == set(TP.TEMPLATE_NAMES)


@pytest.mark.parametrize("name", TP.TEMPLATE_NAMES)
def test_every_template_renders_with_full_context(name):
    out = TP.render(name, **CONTEXTS[name])
    assert out.strip()
    assert "{{" not in out and "{%" not in out or name == "narrative_section.j2"


@pytest.mark.parametrize("name", TP.TEMPLATE_NAMES)
def test_missing_variable_raises(name):
    ctx = dict(CONTEXTS[name])
    ctx.pop(next(iter(ctx)))
    with pytest.raises(UndefinedError):
        TP.render(name, **ctx)


def test_environment_is_strict_and_own_directory():
    # A lenient environment renders blanks where a variable is missing and the
    # model fills the blank with an invention; the r30 prompt dir is frozen.
    from jinja2 import StrictUndefined
    assert TP._env().undefined is StrictUndefined
    assert TP._TEMPLATES_DIR.name == "prompts" and TP._TEMPLATES_DIR.parent.name == "engine"


@pytest.mark.parametrize("name", TP.JSON_TEMPLATE_NAMES)
@pytest.mark.parametrize("marker", [TP.ANGLE_BRACKET_MARKER, TP.EMPTY_LIST_MARKER,
                                    TP.NO_INVENTED_NUMBER_MARKER, TP.CITE_IDS_MARKER])
def test_json_templates_carry_marker_sentences_in_source(name, marker):
    assert marker in _source(name), f"{name} lacks: {marker}"
    assert marker in TP.render(name, **CONTEXTS[name])


def test_json_templates_ask_for_json_only():
    for name in TP.JSON_TEMPLATE_NAMES:
        assert "Return ONLY this JSON" in _source(name), name


def test_narrative_receives_ids_and_tokens_only():
    src = _source("narrative_section.j2")
    assert "Reference claims by token only" in src
    out = TP.render("narrative_section.j2", **CONTEXTS["narrative_section.j2"])
    assert "{{S-1}}" in out and "E-1" in out
    # the statement text itself is never a template variable
    assert "statement_text" not in src and "c.text" not in src


def test_simulated_client_reveals_only_what_is_asked():
    src = _source("simulated_client.j2")
    assert TP.REVEAL_ONLY_MARKER in src and "temperament" in src
    assert TP.NO_INVENTED_NUMBER_MARKER.rstrip(".").lower() in src.lower()


def test_verifier_clears_only_with_literal_not_licensed():
    src = _source("regulated_verifier.j2")
    assert TP.CLEAR_VERDICT == "not_licensed"
    assert TP.CLEAR_VERDICT in src and TP.KEEP_VERDICT in src
    assert "Uncertainty is not a refutation" in src
    out = TP.render("regulated_verifier.j2", **CONTEXTS["regulated_verifier.j2"])
    assert TP.CLEAR_VERDICT in out


def test_issue_tree_catalogue_carries_every_shape_value():
    out = TP.render("issue_tree.j2", **CONTEXTS["issue_tree.j2"])
    for enum_cls in (T.Interrogative, T.CapabilityClass, T.Kind):
        for member in enum_cls:
            assert member.value in out, f"{enum_cls.__name__}.{member.name} missing from catalogue"
    for flag in TP.SHAPE_BOOLEANS:
        assert flag in out
    assert "method" not in out.split("RULES")[0].lower()


def test_closed_vocabularies_are_rendered_not_written():
    # The enum values reach the model at render time; the source spells none
    # of the multi-word ones (a written value would drift from the enum).
    src_all = "".join(_source(n) for n in TP.TEMPLATE_NAMES)
    for enum_cls in (T.Kind, T.CapabilityClass, T.RegulatedDomain):
        for member in enum_cls:
            if "_" in member.value:
                assert member.value not in src_all, member.value
    out = TP.render("regulated_classifier.j2", **CONTEXTS["regulated_classifier.j2"])
    assert all(d.value in out for d in T.RegulatedDomain)
    out = TP.render("extract_document.j2", **CONTEXTS["extract_document.j2"])
    assert all(r.value in out for r in T.RecordClass) and T.FactBasis.DOCUMENT_EXTRACTED.value in out
    out = TP.render("extract_turn.j2", **CONTEXTS["extract_turn.j2"])
    assert T.FactBasis.CLIENT_STATED.value in out and T.DecisionRole.STATED_REQUEST.value in out


def test_values_filter_accepts_enum_class_and_subset():
    assert TP._values_filter(T.Interrogative) == " | ".join(m.value for m in T.Interrogative)
    assert TP._values_filter([T.Kind.FACT, "objective"]) == "fact | objective"


@pytest.mark.parametrize("name", TP.TEMPLATE_NAMES)
def test_no_denylist_stem_in_template_source(name):
    src = _source(name).lower()
    hits = [s for s in DENYLIST_STEMS if s in src]
    assert not hits, f"{name} carries engagement vocabulary: {hits}"


def test_denylist_scanner_negative_control():
    assert [s for s in DENYLIST_STEMS if s in "plan the acquisition"] == ["acquisition"]


@pytest.mark.parametrize("name", TP.TEMPLATE_NAMES)
def test_no_client_name_in_template_source(name):
    src = _source(name).lower()
    tokens = client_name_tokens()
    assert tokens, "case files must yield name tokens"
    hits = sorted(t for t in tokens if re.search(r"\b" + re.escape(t) + r"\b", src))
    assert not hits, f"{name} names a benchmark client: {hits}"


@pytest.mark.parametrize("name", TP.TEMPLATE_NAMES)
def test_template_source_is_ascii(name):
    _source(name).encode("ascii")
