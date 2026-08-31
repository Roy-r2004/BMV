"""C23 benchmark, fake mode: app/engine/benchmark/{cases,oracle,harness,assertions}.py.

Fifteen engagements run end to end against one engine and one case-blind
provider. What the run proves is not that the answers are good - the structural
oracle cannot judge prose - but that nothing in the deterministic core is a
per-case script: the oracle cannot tell one case from another, so every
difference between two bundles came out of the registry.

Pinned mutations (work breakdown C23):
- a fixed deliverable set     -> test_core_cases_diverge (D8)
- a fixed question script     -> test_core_cases_diverge (D1/D2)
- averaging in calc           -> test_adversarial_cases_hold_their_law[contradictory]
- disabled regulated routing  -> test_adversarial_cases_hold_their_law[regulated]
- disabled symptom detection  -> test_adversarial_cases_hold_their_law[symptom]
- remove the SPAWN branch     -> test_core_cases_diverge (D7)
- silence the reveal counter  -> test_every_core_case_surfaces_what_changes_the_recommendation
"""
from __future__ import annotations

import json
import os

import pytest

from app.engine.benchmark import assertions as A
from app.engine.benchmark import cases as C
from app.engine.benchmark import harness as H
from app.engine.benchmark.oracle import structural_oracle
from app.engine.partner import charter as CH
from app.engine.llm import FakeProvider
from app.engine.methods.contract import METHODS, QuestionShape, shape_matches
from app.engine import types as T
from app.engine.types import Kind

import app.engine.methods.builtin  # noqa: F401  - registration by import


def _provider():
    return FakeProvider(oracle=structural_oracle)


@pytest.fixture(scope="module")
def loaded():
    return C.load_all()


@pytest.fixture(scope="module")
def bundles(loaded):
    """Every case run once. Module-scoped because fifteen engagements are the
    unit under test here, not one - and because running them again per test
    would say nothing new: the runs are deterministic (proved below)."""
    return {case.id: H.run_case(case, _provider()) for case in loaded}


def _core(loaded, bundles):
    return [bundles[c.id] for c in C.core_cases(loaded)]


# ===========================================================================
# 1. The loader refuses; it never falls back
# ===========================================================================

def _write_case(tmp_path, case_id: str, case: dict, keys: dict) -> str:
    (tmp_path / f"{case_id}.json").write_text(json.dumps(case), encoding="utf-8")
    (tmp_path / f"{case_id}.keys.json").write_text(json.dumps(keys), encoding="utf-8")
    return str(tmp_path)


def _minimal_case(case_id: str = "c1") -> dict:
    return {
        "id": case_id, "title": "t", "opening_statement": "we have a problem",
        "client_persona": {"name": "n", "role": "r", "company": "c", "sector": "s",
                           "country": "k", "size": "z", "temperament": "p"},
        "dossier": [{"topic": "money", "fact": "we turn over 4m", "reveals_when": "",
                     "changes_recommendation": True}],
        "documents": [{"name": "d", "kind": "report", "content": "we turn over 4m",
                       "contains_contradiction": None}],
        "regulated_matters": ["whether the contract binds us"],
    }


def _minimal_keys() -> dict:
    return {"adversarial": False, "checks": [],
            "topic_map": {"money": [{"kind": "fact", "filter": {"basis": "client_stated"}}]},
            "overrides": {},
            "regulated_domains": [{"text": "whether the contract binds us", "domain": "legal_contract"}],
            "candidate_shapes": []}


def test_a_case_loads_only_with_every_topic_typed(tmp_path):
    keys = _minimal_keys()
    keys["topic_map"] = {}
    root = _write_case(tmp_path, "c1", _minimal_case(), keys)
    with pytest.raises(C.CaseError) as exc:
        C.load_case("c1", root)
    assert "topic_map" in str(exc.value) and "money" in str(exc.value)


def test_a_per_item_override_stands_in_for_the_topic_map(tmp_path):
    keys = _minimal_keys()
    keys["topic_map"] = {}
    keys["overrides"] = {"0": [{"kind": "measure", "filter": {}}]}
    root = _write_case(tmp_path, "c1", _minimal_case(), keys)
    case = C.load_case("c1", root)
    assert case.asks_for(0)[0].kind is Kind.MEASURE


def test_a_regulated_matter_without_a_domain_refuses_to_load(tmp_path):
    keys = _minimal_keys()
    keys["regulated_domains"] = []
    root = _write_case(tmp_path, "c1", _minimal_case(), keys)
    with pytest.raises(C.CaseError) as exc:
        C.load_case("c1", root)
    assert "regulated matter" in str(exc.value)


def test_an_unknown_enum_value_refuses_to_load(tmp_path):
    keys = _minimal_keys()
    keys["regulated_domains"] = [{"text": "whether the contract binds us", "domain": "vibes"}]
    root = _write_case(tmp_path, "c1", _minimal_case(), keys)
    with pytest.raises(C.CaseError):
        C.load_case("c1", root)


def test_an_annotation_cannot_filter_on_prose(tmp_path):
    """M2/P1 one layer down: an annotation reads FILTERABLE_FIELDS only, or the
    reveal is decided by wording again."""
    keys = _minimal_keys()
    keys["topic_map"] = {"money": [{"kind": "fact", "filter": {"statement": "turnover"}}]}
    root = _write_case(tmp_path, "c1", _minimal_case(), keys)
    with pytest.raises(C.CaseError) as exc:
        C.load_case("c1", root)
    assert "non-structural" in str(exc.value)


def test_an_unknown_field_refuses_to_load(tmp_path):
    keys = dict(_minimal_keys(), notes="a key nothing reads")
    root = _write_case(tmp_path, "c1", _minimal_case(), keys)
    with pytest.raises(C.CaseError):
        C.load_case("c1", root)


def test_an_adversarial_case_must_name_implemented_checks(tmp_path):
    keys = dict(_minimal_keys(), adversarial=True, checks=["reads_minds"])
    root = _write_case(tmp_path, "c1", _minimal_case(), keys)
    with pytest.raises(C.CaseError) as exc:
        C.load_case("c1", root)
    assert "unknown adversarial check" in str(exc.value)


def test_every_named_check_has_an_implementation():
    """The two-way pin: a name a keys file may use with no code behind it, and
    code nothing names, are both failures rather than a check that never ran."""
    assert set(A.ADVERSARIAL) == set(C.ADVERSARIAL_CHECKS)


def test_the_fifteen_shipped_cases_all_load(loaded):
    assert len(loaded) == len(C.case_ids())
    assert len(C.core_cases(loaded)) >= 2 and len(C.adversarial_cases(loaded)) >= 1
    for case in loaded:
        for i in range(len(case.case.dossier)):
            assert case.asks_for(i), f"{case.id}[{i}] types nothing"


# ===========================================================================
# 2. Every case runs, and runs the same way twice
# ===========================================================================

def test_every_case_runs_end_to_end(loaded, bundles):
    for case in loaded:
        bundle = bundles[case.id]
        assert bundle.turns > 0, f"{case.id} never took a turn"
        assert bundle.central_decision, f"{case.id} named no central decision"
        assert bundle.issue_shapes, f"{case.id} built no issue tree"
        assert bundle.work_products, f"{case.id} planned no work products"
        assert bundle.registry_hash


def test_the_same_case_twice_is_the_same_bundle(loaded):
    """Determinism (design 17.4): fixed clock, seeded ids, one case-blind
    provider. A bundle that moved between runs would make every divergence
    comparison below meaningless."""
    for case in loaded:
        first = H.run_case(case, _provider())
        second = H.run_case(case, _provider())
        assert first.digest() == second.digest(), f"{case.id} is not deterministic"


def test_the_tree_root_is_the_engines_and_every_bundle_says_so(bundles, loaded):
    """The tree's first node is engine work, and the bundle proves it.

    This test read `seeded_root is True` while the harness owned the bootstrap.
    It was wrong the moment `partner.charter.seed_root_issue` landed: the
    charter now opens the root itself, the harness's fallback never fires, and
    asserting True would have pinned a workaround instead of the engine. The
    law is the same one either way - nothing downstream may credit the engine
    for structure the benchmark supplied - so it is asserted from the other
    side: the harness contributed no issue node to any of the fifteen, and each
    root carries the charter's own actor_ref. If the engine ever stops seeding,
    the fallback keeps the run measurable and this fails loudly rather than
    fifteen empty trees passing quietly.
    """
    for case in loaded:
        bundle = bundles[case.id]
        assert bundle.seeded_root is False, f"{case.id}: the harness had to seed the root"
        roots = [i for i in bundle.registry.live(Kind.ISSUE) if i.payload.parent_id is None]
        assert roots, f"{case.id}: no root issue at all"
        for root in roots:
            assert root.provenance.actor_ref == CH.ROOT_ISSUE_ACTOR_REF
            assert CH.ROOT_ISSUE_LABEL in root.labels


def test_the_fallback_root_declares_itself_when_it_fires(loaded):
    """The other half: the fallback is not dead code that could quietly lie.
    Seeded on a registry with a central decision and no tree, it writes a node,
    and `seeded_root` reads that node back off provenance as the harness's."""
    case = loaded[0]
    registry = H.EngagementRegistry(case.id, clock=H._clock)
    registry.apply(T.Add(T.make_entity(
        kind=Kind.DECISION, engagement_id=case.id,
        payload=T.DecisionPayload(statement="which way to go", role=T.DecisionRole.CENTRAL),
        provenance=T.Provenance(actor=T.Actor.PARTNER, actor_ref="test"),
        confidence=T.Confidence(None), relevance=None,
        relation=T.RelationToCentralDecision.DEFINES, status=T.Status.CONFIRMED)))
    assert H._harness_seeded_root(registry) is False
    assert H._seed_root_issue(registry, 5) is True
    assert H._harness_seeded_root(registry) is True
    # Idempotent: a tree that exists is never given a second root.
    assert H._seed_root_issue(registry, 5) is False


# ===========================================================================
# 3. Divergence over the ten core cases
# ===========================================================================

def test_core_cases_diverge(loaded, bundles):
    failures = A.divergence_failures(_core(loaded, bundles))
    assert failures == [], "\n".join(failures)


def test_every_core_case_surfaces_what_changes_the_recommendation(loaded, bundles):
    core = C.core_cases(loaded)
    failures = A.revealed_failures([bundles[c.id] for c in core], core)
    assert failures == [], "\n".join(failures)


def test_divergence_needs_more_than_one_bundle(loaded, bundles):
    """The negative control on the comparison itself: one bundle is not a
    divergence result, and saying so is not the same as passing."""
    one = _core(loaded, bundles)[:1]
    assert A.divergence_failures(one)


def test_identical_bundles_are_reported_as_identical(loaded, bundles):
    """The other negative control: the checks fire when the bundles really are
    the same. Without this, a check that always returned [] would pass."""
    from dataclasses import replace
    one = _core(loaded, bundles)[0]
    twin = replace(one, case_id=one.case_id + "-twin")
    failures = A.divergence_failures([one, twin])
    assert any(f.startswith("D3") for f in failures)
    assert any(f.startswith("D4") for f in failures)


# ===========================================================================
# 4. The adversarial cases
# ===========================================================================

@pytest.mark.parametrize("case_id", [c.id for c in C.adversarial_cases()])
def test_adversarial_cases_hold_their_law(case_id, loaded, bundles):
    case = next(c for c in loaded if c.id == case_id)
    failures = A.adversarial_failures(bundles[case_id], case)
    assert failures == [], "\n".join(failures)


def test_every_adversarial_check_is_exercised_by_some_case(loaded):
    named = {name for case in loaded for name in case.keys.checks}
    assert named == set(C.ADVERSARIAL_CHECKS), f"never run: {sorted(set(C.ADVERSARIAL_CHECKS) - named)}"


# ===========================================================================
# 5. What the case data claims about the method library
# ===========================================================================

def test_every_annotated_candidate_shape_is_one_some_method_answers(loaded):
    """`candidate_shapes` types what a case's realistic central decisions would
    decompose into. The claim is about the LIBRARY: a real decision that no
    method can take on is a hole nothing else in this suite would show."""
    unanswered: list[str] = []
    for case in loaded:
        for shape in case.keys.candidate_shapes:
            node = QuestionShape(shape.interrogative, shape.target_kind, shape.quantified,
                                 shape.comparative, shape.causal, shape.temporal)
            if not any(shape_matches(d, node) for m in METHODS.all() for d in m.spec.applicability):
                unanswered.append(f"{case.id}: no method takes on {node}")
    assert unanswered == [], "\n".join(unanswered)


# ===========================================================================
# 6. What this build cannot yet claim
# ===========================================================================

def test_the_claims_this_build_cannot_make_are_named_and_explained():
    """A gap that is written down is a gap somebody can close; a gap that is
    silently skipped is a law nothing tests. When the engine gains what these
    need, this test fails and the claim moves into `divergence_failures`."""
    expected = {
        "deliverable_sets_reach_the_bound",
        "section_signatures_reach_the_bound",
        "recommendations_are_distinct",
        "workstreams_are_distinct",
        "central_decision_is_not_the_opening_statement",
    }
    assert set(A.BLOCKED_CLAIMS) == expected
    for name, reason in A.BLOCKED_CLAIMS.items():
        assert len(reason) > 80, f"{name} does not say what is missing"


def test_the_engine_never_reads_a_case_file():
    """The separation the whole benchmark rests on: if any module outside
    app/engine/benchmark imported the loader, a case file could teach the
    engine something and the divergence results would be worthless."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(H.__file__)))
    offenders: list[str] = []
    for dirpath, _dirs, files in os.walk(root):
        if os.path.basename(dirpath) in ("benchmark", "__pycache__"):
            continue
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
            if "benchmark" in body and "import" in body:
                for line in body.splitlines():
                    stripped = line.strip()
                    if stripped.startswith(("import ", "from ")) and "benchmark" in stripped:
                        offenders.append(f"{path}: {stripped}")
    assert offenders == [], "\n".join(offenders)


def test_the_oracle_answers_from_the_call_and_nothing_else(loaded):
    """Case blindness, stated as a property of the oracle rather than of its
    author: no company, persona, product or document name from any case file
    appears in the benchmark package's source."""
    import app.engine.benchmark as pkg

    # Proper nouns only: a capitalised word from the person or the company that
    # belongs to exactly ONE case and is not a word the engine's own closed
    # vocabularies use. Counting and deriving the exclusions - rather than
    # keeping a stop-list - means the filter cannot rot as the cases change.
    vocabulary = {word for enum in (T.Kind, T.Interrogative, T.CapabilityClass, T.RegulatedDomain,
                                    T.UnitFamily, T.SourceKind, T.RecordClass, T.Authority,
                                    T.InfoType, T.Actor, T.Status, T.Phase)
                  for member in enum for word in member.value.split("_")}
    seen: dict[str, set[str]] = {}
    for case in loaded:
        persona = case.case.client_persona
        for value in (persona.name, persona.company):
            for word in value.replace(",", " ").replace("-", " ").split():
                if len(word) >= 6 and word.isalpha() and word[0].isupper():
                    seen.setdefault(word.lower(), set()).add(case.id)
    tokens = {word for word, owners in seen.items()
              if len(owners) == 1 and word not in vocabulary}
    assert len(tokens) >= 10, "the client-name scan found almost no names to look for"
    root = os.path.dirname(os.path.abspath(pkg.__file__))
    hits: list[str] = []
    for name in sorted(os.listdir(root)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(root, name), encoding="utf-8") as fh:
            body = fh.read().lower()
        for token in sorted(tokens):
            if token in body:
                hits.append(f"{name}: {token}")
    assert hits == [], "\n".join(hits)
