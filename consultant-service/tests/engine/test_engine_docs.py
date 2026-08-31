"""C26 - the documentation gate (design 2, spec sequence step 12).

A document is not a deliverable if nothing can make it fail. These tests turn
`docs/engine/*.md` into a registry query: the tables in ARCHITECTURE.md must
list exactly what the code registers, in BOTH directions, so a method added
without a line in the table is a red suite rather than a silent lie, and a
method deleted from the code leaves a stale row that is also caught.

The reverse direction matters as much as the forward one. Forward only, a
document can be padded with rows for methods that do not exist and still pass;
that is how a "complete" architecture document ends up describing a system
nobody built.

The named mutations for this component and the test that kills each:

  register a new method without documenting it
      -> test_every_registered_method_is_documented
  document a method that is not registered (stale row)
      -> test_no_documented_method_is_unregistered
  drop a law / product / admission rule / bound from the docs
      -> test_every_law_is_documented, test_every_work_product_is_documented,
         test_every_admission_rule_is_documented, test_every_bound_is_documented
  change a bound's value in code but not in the table
      -> test_every_bound_is_documented

The docs are read as bytes and decoded as ASCII on purpose: these files are
read in terminals and diffed in PRs, and the export faces this service ships
cover a ~233-glyph subset, so a smart quote pasted from a chat window is a
defect here for the same reason it is a defect in a rendered page.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import app.engine.methods.builtin  # noqa: F401  registration is by import
from app.engine.gates.laws import LAWS, LawId
from app.engine.methods.contract import METHODS
from app.engine.specialists.assignment import ADMISSION_RULES
from app.engine.types import BOUNDS
from app.engine.work_products.decl import WORK_PRODUCTS

_ROOT = Path(__file__).resolve().parents[2]
_DOCS = _ROOT / "docs" / "engine"
_BENCHMARKS = Path(__file__).resolve().parent / "benchmarks"

ARCHITECTURE = "ARCHITECTURE.md"
EXTENSION_CONTRACTS = "EXTENSION_CONTRACTS.md"
LIMITATIONS = "LIMITATIONS.md"
DOC_NAMES = (ARCHITECTURE, EXTENSION_CONTRACTS, LIMITATIONS)


def _read(name: str) -> str:
    """Bytes, then a strict ASCII decode: a non-ASCII character is a failure
    here, not a silently replaced character."""
    return (_DOCS / name).read_bytes().decode("ascii")


def _rows(doc: str, block: str) -> list[list[str]]:
    """The rows of one marked table. The markers are what make the pinning
    exact: a table found by heading text would move with any rewording, and a
    test that cannot find its table passes vacuously."""
    start = f"<!-- registry:{block} -->"
    end = f"<!-- /registry:{block} -->"
    assert start in doc and end in doc, f"{ARCHITECTURE} lost the {block} markers"
    body = doc.split(start, 1)[1].split(end, 1)[0]
    out: list[list[str]] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or set(cells[0]) <= {"-", ":"}:      # the header separator
            continue
        out.append(cells)
    return out


def _documented(block: str) -> dict[str, list[str]]:
    """id -> the rest of its row, for every row whose first cell is a backticked
    identifier. The header row has no backticks, so it drops out without the
    test needing to know how many header rows a table has."""
    doc = _read(ARCHITECTURE)
    found: dict[str, list[str]] = {}
    for cells in _rows(doc, block):
        m = re.match(r"^`([A-Za-z0-9_]+)`$", cells[0])
        if m is None:
            continue
        assert m.group(1) not in found, f"{block}: {m.group(1)} documented twice"
        found[m.group(1)] = cells[1:]
    assert found, f"{block}: the table documents nothing"
    return found


# =============================================================================
# The files themselves
# =============================================================================

@pytest.mark.parametrize("name", DOC_NAMES)
def test_docs_exist_and_are_ascii(name: str) -> None:
    path = _DOCS / name
    assert path.is_file(), f"docs/engine/{name} is missing"
    text = _read(name)                                    # raises on non-ASCII
    assert len(text.split()) > 200, f"{name} is a stub, not a document"


def test_architecture_points_at_the_other_two() -> None:
    """One entry point. A limitation nobody is routed to is a limitation nobody
    reads."""
    doc = _read(ARCHITECTURE)
    assert EXTENSION_CONTRACTS in doc
    assert LIMITATIONS in doc


# =============================================================================
# The five registries, pinned in both directions
# =============================================================================

def test_every_registered_method_is_documented() -> None:
    registered = {m.spec.id for m in METHODS.all()}
    documented = set(_documented("methods"))
    missing = sorted(registered - documented)
    assert not missing, f"methods registered but undocumented: {missing}"


def test_no_documented_method_is_unregistered() -> None:
    registered = {m.spec.id for m in METHODS.all()}
    documented = set(_documented("methods"))
    stale = sorted(documented - registered)
    assert not stale, f"methods documented but not registered: {stale}"


def test_documented_methods_carry_their_execution_type() -> None:
    """The execution type is what decides whether a method may spend money and
    whether it needs an assignment, so a row that omits it documents a name and
    nothing else."""
    documented = _documented("methods")
    for method in METHODS.all():
        # An undocumented method is the neighbouring test's finding, not this
        # one's: reporting it here too would say nothing new and hide what this
        # test is actually for.
        row = " ".join(documented.get(method.spec.id, ("",)))
        if not row.strip():
            continue
        assert method.spec.execution.value in row, (
            f"{method.spec.id}: the table does not state its execution type")


def test_every_work_product_is_documented() -> None:
    registered = {p.id for p in WORK_PRODUCTS.all()}
    documented = set(_documented("work_products"))
    assert not sorted(registered - documented), (
        f"products registered but undocumented: {sorted(registered - documented)}")
    assert not sorted(documented - registered), (
        f"products documented but not registered: {sorted(documented - registered)}")


def test_every_law_is_documented() -> None:
    """Both the member name (L7) and its full id (L7.calculation_does_not_
    recompute): the name alone would survive a law being repurposed under the
    same number, which is precisely the change a reader must be told about."""
    registered = {law.id for law in LAWS.all()}
    assert registered == set(LawId), "a LawId member is not registered in LAWS"
    documented = _documented("laws")
    assert set(documented) == {law.name for law in LawId}, (
        f"documented laws {sorted(documented)} != {sorted(l.name for l in LawId)}")
    for law in LawId:
        row = " ".join(documented[law.name])
        assert law.value in row, f"{law.name}: the table does not carry its id {law.value}"


def test_every_admission_rule_is_documented() -> None:
    documented = _documented("admission_rules")
    assert set(documented) == set(ADMISSION_RULES), (
        f"documented admission rules {sorted(documented)} != {sorted(ADMISSION_RULES)}")


def test_every_bound_is_documented() -> None:
    """Name, default and settings field. The default is compared literally: a
    ceiling that moves in code and not in the table is exactly the drift that
    makes an operator trust the wrong number."""
    documented = _documented("bounds")
    assert set(documented) == set(BOUNDS), (
        f"documented bounds {sorted(documented)} != {sorted(BOUNDS)}")
    for name, value in BOUNDS.items():
        default, setting = documented[name][0], documented[name][1]
        assert default == str(value), (
            f"{name}: documented default {default!r}, code says {str(value)!r}")
        assert f"`ENGINE_{name}`" == setting, (
            f"{name}: the table does not name its ENGINE_ settings field")


def test_no_bound_is_documented_as_a_fixed_count() -> None:
    """Dynamic, not hardcoded (owner constraint). The bounds section has to say
    so, because a reader who thinks a bound is a target will hardcode to it."""
    doc = _read(ARCHITECTURE)
    assert "No count is fixed per engagement." in doc


# =============================================================================
# Extension contracts
# =============================================================================

# extension point -> the symbols a reader needs to find to actually do it. A
# section that names the extension but not the registration symbol sends the
# reader looking through the orchestrator, which is the edit this file exists
# to prevent.
_EXTENSION_POINTS = {
    "method": ("@register", "MethodSpec", "app/engine/methods/builtin/", "QuestionShape"),
    "work product": ("register_product", "WorkProductDecl", "Predicate", "SectionDecl"),
    "law": ("LAWS.register", "LawId", "blocks_final"),
    "regulated domain": ("RegulatedDomain", "ADVISER_CLASS", "app/engine/synthesis/regulated.py"),
    "benchmark case": ("tests/engine/benchmarks/", ".keys.json", "topic_map", "FILTERABLE_FIELDS"),
}

# The orchestrator files an extension must not need. Naming them is the whole
# claim of the document; if the list goes missing the promise is unfalsifiable.
_CLOSED_FILES = (
    "app/engine/partner/loop.py",
    "app/engine/methods/contract.py",
    "app/engine/specialists/runner.py",
    "app/engine/work_products/plan.py",
    "app/engine/gates/release.py",
)


@pytest.mark.parametrize("point,symbols", sorted(_EXTENSION_POINTS.items()))
def test_extension_contracts_cover_every_extension_point(point: str, symbols: tuple) -> None:
    doc = _read(EXTENSION_CONTRACTS)
    assert f"Add a {point}" in doc, f"no section on adding a {point}"
    missing = [s for s in symbols if s not in doc]
    assert not missing, f"the '{point}' contract never names {missing}"


def test_extension_contracts_name_the_files_that_stay_closed() -> None:
    doc = _read(EXTENSION_CONTRACTS)
    missing = [f for f in _CLOSED_FILES if f not in doc]
    assert not missing, f"the closed-file list omits {missing}"


def test_extension_contracts_name_the_frozen_r30_tree() -> None:
    """The r30 baseline must stay byte-identical (owner constraint); a
    contributor who does not know that will reach for app/pipeline first."""
    doc = _read(EXTENSION_CONTRACTS)
    for frozen in ("app/pipeline/**", "app/prompts/**", "tools/**"):
        assert frozen in doc, f"the frozen manifest does not mention {frozen}"


def test_extension_contracts_demand_a_test_per_extension() -> None:
    """Mutation-proof every law (owner constraint): each contract has to end in
    the tests it obliges, or the next method arrives untested."""
    doc = _read(EXTENSION_CONTRACTS)
    assert doc.count("Tests to add:") >= len(_EXTENSION_POINTS)


# =============================================================================
# Limitations
# =============================================================================

# Each limitation the design settled, with a token that only its own paragraph
# would contain. Deleting an inconvenient limitation is the mutation here.
_LIMITATIONS = {
    "the fake proves structure, not quality": ("FakeProvider", "structural oracle"),
    "real runs cost money": ("ENGINE_BENCHMARK_REAL", "--max-usd", "uploads/benchmarks/"),
    "classifier bounded one way": ("RegulatedDomain", "QUALIFIED_PROFESSIONAL"),
    "xlsx deferred": ("openpyxl", ".xlsx", "CSV"),
    "legacy rows stay listed": ("/api/requests/mine",),
    "clipping is spans, not pixels": ("Clipping",),
    "reconciliation follows measure attachment": ("measure_id",),
    "absence is not a defect": ("is False",),
}


@pytest.mark.parametrize("topic,tokens", sorted(_LIMITATIONS.items()))
def test_limitations_records_every_deferral(topic: str, tokens: tuple) -> None:
    doc = _read(LIMITATIONS)
    missing = [t for t in tokens if t not in doc]
    assert not missing, f"LIMITATIONS.md no longer records '{topic}' ({missing})"


# =============================================================================
# The docs are part of the universality claim
# =============================================================================

_TOKEN = re.compile(r"[A-Za-z]{5,}")


def _case_names() -> set[str]:
    """Persona and company names from the benchmark data. The engine is scanned
    for these by the universality guard; the docs are scanned here for the same
    reason - an architecture explained through one client's engagement is an
    architecture that quietly learned that client.

    A name is a token of five or more letters that one case's identity fields
    use and that no OTHER case uses anywhere. That second filter is what keeps
    ordinary business English out: a company called something-Systems does not
    make the word "systems" a client, because every other case says it too."""
    identity: dict[str, set[str]] = {}
    used_by: dict[str, int] = {}
    if not _BENCHMARKS.is_dir():                          # data is untracked
        return set()
    for path in sorted(_BENCHMARKS.glob("*.json")):
        if path.name.endswith(".keys.json"):
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            case = json.loads(raw)
        except (OSError, ValueError):
            continue
        persona = case.get("client_persona") or {}
        identity[path.name] = {
            t.lower() for field in ("name", "company")
            for t in _TOKEN.findall(str(persona.get(field) or ""))}
        for token in {t.lower() for t in _TOKEN.findall(raw)}:
            used_by[token] = used_by.get(token, 0) + 1
    return {token for tokens in identity.values() for token in tokens
            if used_by.get(token, 0) <= 1}


@pytest.mark.parametrize("name", DOC_NAMES)
def test_docs_name_no_client(name: str) -> None:
    cases = _case_names()
    if not cases:
        pytest.skip("benchmark case data is not present")
    text = _read(name).lower()
    hits = sorted(n for n in cases if n in text)
    assert not hits, f"{name} names benchmark clients: {hits}"


def test_architecture_states_the_no_branching_law() -> None:
    """The one claim the whole engine rests on. A reader who misses it will
    write the first engagement-type branch in good faith."""
    doc = _read(ARCHITECTURE)
    assert "There is no engagement-type switch anywhere in `app/engine`" in doc
    assert "FILTERABLE_FIELDS" in doc
