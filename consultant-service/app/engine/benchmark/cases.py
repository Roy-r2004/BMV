"""app/engine/benchmark/cases.py - the strict benchmark case loader (design 17.1,
17.2).

Two files describe one case. `<id>.json` is the case data that already existed
before the engine did: an opening statement, a persona, a dossier of facts the
client will reveal only when asked, documents, and the regulated matters a good
engine should refuse to answer itself. `<id>.keys.json` is the harness's own
annotation layer (MF1.4 / MF3.5), and it exists because the first version of the
deterministic client matched a question to a dossier item by prose overlap.
Prose overlap cannot fail: every question overlaps every topic a little, so
every case "revealed" something and the benchmark proved nothing. The annotation
replaces that with types - a topic maps to `AsksFor(kind, filter)` rows, and a
question reveals an item only when the kinds are the same and the filters do not
contradict.

Loading is strict, and every refusal below is a raise, never a default:

  * a dossier topic with no `topic_map` entry and no per-item override. A silent
    fallback here is exactly the vacuous match the annotation exists to remove:
    the item would be revealed by any question, or by none, and nothing would
    say which.
  * a `regulated_matters` line with no `{text, domain}` annotation. The
    adversarial regulated case asserts that every annotated domain was routed;
    an unannotated matter would quietly shrink what the assertion checks.
  * an enum value that is not a member of `Kind`, `RegulatedDomain` or
    `Interrogative`, or a filter field outside `FILTERABLE_FIELDS`. An
    annotation that filtered on a text field would be prose deciding a reveal
    again, one layer down.
  * an unknown field anywhere (`extra="forbid"`), so a typo in an annotation is
    a load error rather than a key nothing reads.

The engine never imports this module.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from app.engine.types import FILTERABLE_FIELDS, AsksFor, Interrogative, Kind, RegulatedDomain

__all__ = [
    "ADVERSARIAL_CHECKS",
    "BENCHMARK_DIR",
    "AskForSpec",
    "CandidateShape",
    "Case",
    "CaseDocument",
    "CaseError",
    "CaseKeys",
    "DossierItem",
    "LoadedCase",
    "Persona",
    "RegulatedAnnotation",
    "adversarial_cases",
    "benchmark_dir",
    "case_ids",
    "core_cases",
    "documents_as_attachments",
    "load_all",
    "load_case",
]

# The case data lives with the tests, not with the package: it is test data,
# and the frozen manifest (design 13.5) excludes tests/engine/**.
_SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
BENCHMARK_DIR = os.path.join(_SERVICE_ROOT, "tests", "engine", "benchmarks")

KEYS_SUFFIX = ".keys.json"
CASE_SUFFIX = ".json"

# The closed set of adversarial checks a keys file may name. It lives here
# rather than in assertions.py so a case file can be validated without
# importing the assertion bodies, and assertions.py asserts at import time that
# its registry covers exactly this tuple - a name here with no implementation,
# or an implementation nothing names, fails on both sides rather than becoming
# a check that quietly never ran.
ADVERSARIAL_CHECKS: tuple[str, ...] = (
    "missing_evidence",
    "contradictory_documents",
    "impossible_objective",
    "specialist_disagreement",
    "regulated",
    "symptom_not_problem",
)


class CaseError(ValueError):
    """A case or its annotations could not be loaded. Carries the path and the
    field, because a benchmark that fails to load must say which file to fix."""


# =============================================================================
# 1. The case file (existing data, design 17.1)
# =============================================================================

class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Persona(_Strict):
    name: str
    role: str
    company: str
    sector: str
    country: str
    size: str
    temperament: str


class DossierItem(_Strict):
    topic: str
    fact: str
    # Prose, kept for model mode only: the deterministic client matches on the
    # annotation's types and never reads this field.
    reveals_when: str = ""
    changes_recommendation: bool = False


class CaseDocument(_Strict):
    name: str
    kind: str
    content: str
    # The case files carry the contradiction as prose describing it; its
    # presence, not its wording, is what the adversarial assertion counts.
    contains_contradiction: str | None = None


class Case(_Strict):
    id: str
    title: str
    opening_statement: str
    client_persona: Persona
    dossier: tuple[DossierItem, ...]
    documents: tuple[CaseDocument, ...]
    what_a_good_engine_should_notice: tuple[str, ...] = ()
    regulated_matters: tuple[str, ...] = ()
    realistic_central_decision_candidates: tuple[str, ...] = ()


# =============================================================================
# 2. The annotations (harness-owned, design 17.2)
# =============================================================================

class AskForSpec(_Strict):
    """One typed thing a dossier item answers. `filter` reads FILTERABLE_FIELDS
    only - the same closed vocabulary an InputSpec and a registry query read, so
    an annotation cannot select on prose any more than a method can (M2/P1)."""
    kind: Kind
    filter: Mapping[str, Any] = {}

    @field_validator("filter")
    @classmethod
    def _structural_only(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        bad = sorted(set(value or {}) - FILTERABLE_FIELDS)
        if bad:
            raise ValueError(f"filter reads non-structural field(s) {bad}")
        return dict(value or {})

    def as_asks_for(self) -> AsksFor:
        return AsksFor(self.kind, dict(self.filter))


class RegulatedAnnotation(_Strict):
    """A `regulated_matters` line with the licensed domain it belongs to. The
    text is matched to the case file's line verbatim: a paraphrase would let an
    annotation drift away from the matter it claims to type."""
    text: str
    domain: RegulatedDomain


class CandidateShape(_Strict):
    """The shape of an issue one of the case's realistic central decisions would
    decompose into. No run reads it; one assertion does, and what that assertion
    states is about the METHOD LIBRARY rather than about this case: every
    annotated shape must be a shape some registered method declares it can take
    on. A case whose real decision no method answers is a hole in the library
    that no amount of oracle output would reveal."""
    interrogative: Interrogative
    target_kind: Kind
    quantified: bool = False
    comparative: bool = False
    causal: bool = False
    temporal: bool = False


class CaseKeys(_Strict):
    """`<id>.keys.json`. `adversarial` is a boolean rather than an enum on
    purpose: the harness must branch on it, and a branch on an enum this package
    defined would be exactly the private vocabulary the universality whitelist
    law (design 18.2) forbids under app/engine."""
    adversarial: bool = False
    checks: tuple[str, ...] = ()
    topic_map: Mapping[str, tuple[AskForSpec, ...]] = {}
    overrides: Mapping[int, tuple[AskForSpec, ...]] = {}
    regulated_domains: tuple[RegulatedAnnotation, ...] = ()
    candidate_shapes: tuple[CandidateShape, ...] = ()


# =============================================================================
# 3. One loaded case
# =============================================================================

@dataclass(frozen=True)
class LoadedCase:
    """A case and its annotations, already checked against each other."""
    case: Case
    keys: CaseKeys
    path: str

    @property
    def id(self) -> str:
        return self.case.id

    @property
    def adversarial(self) -> bool:
        return self.keys.adversarial

    def asks_for(self, index: int) -> tuple[AsksFor, ...]:
        """What dossier item `index` answers, typed. An override wins over the
        topic map: one item on a shared topic can answer something the rest of
        the topic does not, and the override is where that is said out loud."""
        override = self.keys.overrides.get(index)
        if override is not None:
            return tuple(a.as_asks_for() for a in override)
        topic = self.case.dossier[index].topic
        return tuple(a.as_asks_for() for a in self.keys.topic_map[topic])

    def changing_indexes(self) -> tuple[int, ...]:
        """The dossier items that change the recommendation. These are what a
        core case must actually surface (MIN_REVEALED_CHANGERS): a run that
        revealed only the harmless items has diverged about nothing."""
        return tuple(i for i, item in enumerate(self.case.dossier)
                     if item.changes_recommendation is True)

    def regulated_domains(self) -> tuple[RegulatedDomain, ...]:
        return tuple(dict.fromkeys(a.domain for a in self.keys.regulated_domains))

    def contradicting_documents(self) -> tuple[CaseDocument, ...]:
        return tuple(d for d in self.case.documents if d.contains_contradiction)


# =============================================================================
# 4. Loading
# =============================================================================

def benchmark_dir(directory: str | None = None) -> str:
    return directory or BENCHMARK_DIR


def case_ids(directory: str | None = None) -> tuple[str, ...]:
    """Every case id in the directory, sorted. A `.keys.json` is an annotation
    of a case, never a case: it is excluded by name, not by inspecting it."""
    root = benchmark_dir(directory)
    names: list[str] = []
    for name in sorted(os.listdir(root)):
        if name.endswith(KEYS_SUFFIX) or not name.endswith(CASE_SUFFIX):
            continue
        names.append(name[: -len(CASE_SUFFIX)])
    return tuple(names)


def _read_json(path: str) -> Any:
    if not os.path.exists(path):
        raise CaseError(f"{path}: missing")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise CaseError(f"{path}: not JSON: {exc}") from exc


def _model(cls: type, data: Any, path: str) -> Any:
    try:
        return cls.model_validate(data)
    except Exception as exc:  # pydantic.ValidationError and TypeError alike
        raise CaseError(f"{path}: {exc}") from exc


def _check_topics(case: Case, keys: CaseKeys, path: str) -> None:
    """Every dossier item must be typed by the topic map or by its own override.
    Absence is the error: an unmapped topic would be revealed by nothing (a
    silently weaker benchmark) or by everything (a vacuous one)."""
    missing: list[tuple[int, str]] = []
    for i, item in enumerate(case.dossier):
        if i in keys.overrides:
            continue
        if item.topic not in keys.topic_map:
            missing.append((i, item.topic))
    if missing:
        listed = ", ".join(f"[{i}] {topic!r}" for i, topic in missing)
        raise CaseError(f"{path}: dossier topic(s) with no topic_map entry or override: {listed}")


def _check_overrides(case: Case, keys: CaseKeys, path: str) -> None:
    outside = sorted(i for i in keys.overrides if not 0 <= i < len(case.dossier))
    if outside:
        raise CaseError(f"{path}: override index(es) outside the dossier: {outside}")


def _check_regulated(case: Case, keys: CaseKeys, path: str) -> None:
    """Every regulated matter the case states must carry a domain. The
    adversarial assertion checks routed domains against these; an unannotated
    matter would narrow the assertion without anyone noticing."""
    annotated = {a.text for a in keys.regulated_domains}
    missing = [m for m in case.regulated_matters if m not in annotated]
    if missing:
        raise CaseError(f"{path}: {len(missing)} regulated matter(s) with no domain, "
                        f"first: {missing[0][:120]!r}")
    stated = set(case.regulated_matters)
    unknown = [a.text for a in keys.regulated_domains if a.text not in stated]
    if unknown:
        raise CaseError(f"{path}: regulated_domains annotates text no case line states: "
                        f"{unknown[0][:120]!r}")


def _check_checks(keys: CaseKeys, path: str) -> None:
    unknown = sorted(set(keys.checks) - set(ADVERSARIAL_CHECKS))
    if unknown:
        raise CaseError(f"{path}: unknown adversarial check(s) {unknown}")
    if keys.checks and not keys.adversarial:
        raise CaseError(f"{path}: a core case names adversarial checks {list(keys.checks)}")
    if keys.adversarial and not keys.checks:
        raise CaseError(f"{path}: an adversarial case must name the checks it exists to prove")


def load_case(case_id: str, directory: str | None = None) -> LoadedCase:
    """One case with its annotations, or CaseError. Nothing here falls back."""
    root = benchmark_dir(directory)
    case_path = os.path.join(root, case_id + CASE_SUFFIX)
    keys_path = os.path.join(root, case_id + KEYS_SUFFIX)
    case = _model(Case, _read_json(case_path), case_path)
    keys = _model(CaseKeys, _read_json(keys_path), keys_path)
    if case.id != case_id:
        raise CaseError(f"{case_path}: id {case.id!r} does not match its filename")
    _check_topics(case, keys, keys_path)
    _check_overrides(case, keys, keys_path)
    _check_regulated(case, keys, keys_path)
    _check_checks(keys, keys_path)
    return LoadedCase(case=case, keys=keys, path=case_path)


def load_all(directory: str | None = None) -> tuple[LoadedCase, ...]:
    return tuple(load_case(cid, directory) for cid in case_ids(directory))


def core_cases(loaded: Iterable[LoadedCase] | None = None,
               directory: str | None = None) -> tuple[LoadedCase, ...]:
    pool = loaded if loaded is not None else load_all(directory)
    return tuple(c for c in pool if not c.adversarial)


def adversarial_cases(loaded: Iterable[LoadedCase] | None = None,
                      directory: str | None = None) -> tuple[LoadedCase, ...]:
    pool = loaded if loaded is not None else load_all(directory)
    return tuple(c for c in pool if c.adversarial)


def documents_as_attachments(case: Case) -> Sequence[tuple[str, bytes]]:
    """The case documents as (filename, bytes), the way an attachment arrives.
    The suffix decides the SourceKind the ingester records, so it is set here
    once rather than guessed per call site."""
    return [(f"{d.name}.txt", d.content.encode("utf-8")) for d in case.documents]
