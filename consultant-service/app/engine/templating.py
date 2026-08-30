"""Prompt rendering for the universal engine (design 2, `app/engine/templating.py`).

Mirrors app/templating.py:10-26 - autoescape off (the templates are plain
text and JSON-shape prompts, never HTML), StrictUndefined so a missing
variable raises instead of rendering blank - over the engine's OWN template
directory. The r30 prompt directory is frozen (design 13.5) and must never
be reached from here, so `_TEMPLATES_DIR` is this package's `prompts/`.

Two things are deliberately settled at this layer rather than in each
template:

* Closed vocabularies are rendered from the enums in `app.engine.types`,
  never written as words. A template that spelled out a kind or a domain
  would carry engagement vocabulary in its source (the universality scan of
  design 18.4 forbids that) and would drift from the enum the validators
  check against. So every enum a prompt needs is a template global and the
  `values` filter renders it as `a | b | c`.
* The marker sentences every JSON prompt must carry are constants here so
  the pinning test (tests/engine/test_engine_prompts.py) checks the exact
  wording the model sees. They are still written verbatim into every
  template - the mutation that deletes a sentence from one template must be
  caught on that template's source, not masked by a shared include.
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.engine import types as T

_TEMPLATES_DIR = Path(__file__).parent / "prompts"

# --- marker sentences ---------------------------------------------------
# Angle brackets in a JSON shape are schema, never output. r30 learned this
# the hard way (app/prompts/checklists.j2:23): without the sentence the
# model returns "<the figure>" as a value and the page prints it.
ANGLE_BRACKET_MARKER = ("The <angle-bracket> notation in the JSON shape below is schema "
                        "documentation, NEVER output format - no value in your output is "
                        "wrapped in < >.")
# Absence is a first-class state (design 1, consequence 1). A model that
# believes it must return something fills the list with inventions; a model
# told an empty list is a real answer leaves the hole for the registry to
# turn into a QUESTION.
EMPTY_LIST_MARKER = "An empty list is a real answer."
# Every quantity is a client fact, a verified record or a Calculator result
# (spec 7: unknown information remains unknown). The model words things; it
# never coins a number.
NO_INVENTED_NUMBER_MARKER = "Never invent a number."
# Every proposal must trace to registered entities by id (spec 7: every
# recommendation traces to evidence). Ids, not paraphrases - a paraphrase
# cannot be looked up and the validators drop uncited output.
CITE_IDS_MARKER = "Cite entity ids."

# The one literal that clears a regulated claim (design 9.6). Anything
# else - a synonym, a hedge, a provider error - keeps the matter regulated,
# because under-routing is the dangerous direction and is closed.
CLEAR_VERDICT = "not_licensed"
KEEP_VERDICT = "licensed"

# Persona rule for the benchmark's model-mode client (design 17.3).
REVEAL_ONLY_MARKER = "Reveal only what is asked"

# The enums a prompt may render as a closed vocabulary. Exposed as template
# globals under their class names so a template reads `{{ Kind | values }}`
# and can never spell a value itself.
VOCABULARIES: dict[str, type[Enum]] = {
    "Kind": T.Kind,
    "Interrogative": T.Interrogative,
    "CapabilityClass": T.CapabilityClass,
    "RegulatedDomain": T.RegulatedDomain,
    "FactBasis": T.FactBasis,
    "RecordClass": T.RecordClass,
    "EffortClass": T.EffortClass,
    "DecisionRole": T.DecisionRole,
    "RelationToCentralDecision": T.RelationToCentralDecision,
    "UnitFamily": T.UnitFamily,
    "GapState": T.GapState,
}

# The four boolean dimensions of a QuestionShape (design 6.3). Listed here,
# not in the template, so the catalogue the model chooses from is the same
# list `shape_matches` (methods/contract.py) filters on.
SHAPE_BOOLEANS: tuple[str, ...] = ("quantified", "comparative", "causal", "temporal")

TEMPLATE_NAMES: tuple[str, ...] = (
    "extract_turn.j2",
    "extract_document.j2",
    "revise_hypothesis.j2",
    "issue_tree.j2",
    "phrase_questions.j2",
    "narrative_section.j2",
    "regulated_classifier.j2",
    "regulated_verifier.j2",
    "simulated_client.j2",
    "method_generic.j2",
)

# The prompts that ask for JSON and therefore must carry all four markers.
JSON_TEMPLATE_NAMES: tuple[str, ...] = tuple(
    n for n in TEMPLATE_NAMES if n not in ("narrative_section.j2", "simulated_client.j2"))


def enum_values(enum_cls: type[Enum]) -> list[str]:
    """The closed vocabulary of an enum, in declaration order."""
    return [m.value for m in enum_cls]


def _values_filter(enum_cls) -> str:
    """`{{ Kind | values }}` -> "business_context | decision | ...".

    Accepts an Enum class or an iterable of members/strings so a caller can
    pass a SUBSET (e.g. the kinds an extraction may propose) as a variable
    and render it the same way."""
    if isinstance(enum_cls, type) and issubclass(enum_cls, Enum):
        items = enum_values(enum_cls)
    else:
        items = [m.value if isinstance(m, Enum) else str(m) for m in enum_cls]
    return " | ".join(items)


@lru_cache(maxsize=1)
def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )
    env.filters["values"] = _values_filter
    env.globals.update(VOCABULARIES)
    env.globals["SHAPE_BOOLEANS"] = SHAPE_BOOLEANS
    env.globals["CLEAR_VERDICT"] = CLEAR_VERDICT
    env.globals["KEEP_VERDICT"] = KEEP_VERDICT
    return env


def render(template_name: str, **context) -> str:
    """Render `app/engine/prompts/<template_name>`; a missing variable raises."""
    return _env().get_template(template_name).render(**context)


def template_source(template_name: str) -> str:
    """The raw .j2 text (for scans that must run on the source, not the render)."""
    return (_TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
