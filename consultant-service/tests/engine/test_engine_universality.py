"""C24 universality guard: the engine has no idea what KIND of engagement it is
running, and this file is the only one that tries to refute that (design 18).

Every other test in this directory takes universality as a premise. Here it is
attacked in seven layers, each with a negative control proving the layer can
still fail:

  1. denylist  - no engagement-type word decides anything (18.1)
  2. whitelist - no branch test compares against prose at all, and an enum
                 branch is on an enum the two contract modules own (S5, 18.2)
  3. names     - no benchmark client's name appears in the engine (18.3)
  4. prompts   - no engagement-type word is written into a prompt (18.4)
  5. imports   - no fuzzy matcher, no provider import outside llm.py, no regex
                 rewrite outside the three modules allowed one (18.5)
  6. scramble  - selection, planning and section planning are identical when
                 every text field of every registry is replaced (18.6)
  7. trace     - every path the fifteen engagements walk is walked by two of
                 them or is named in RARE_PATHS with the test that walks it on
                 purpose (MF1.5, 18.7)

Layers 1-5 read the source; 6 and 7 run the engine. Seven layers because each
is evadable alone: a denylist is a word list (rename the word), a whitelist is
about syntax (branch on an int instead), a scramble only proves what the
selectors it can reach do not read, and a trace only sees what fifteen cases
execute. What none of them is talked past is the intersection.

Pinned mutations (work breakdown C24):
- `if 'acquisition' in issue.payload.text:` in select_methods -> layers 1, 2, 6
- `import difflib` in work_products/render_md.py              -> layer 5
- `re.sub(...)` in work_products/render_md.py                 -> layer 5
- a locally defined enum branched on in partner/loop.py       -> layer 2
"""
from __future__ import annotations

import ast
import collections
import dataclasses
import enum
import functools
import hashlib
import importlib
import importlib.util
import os
import re
import sys

import pytest

from app.engine import types as T
from app.engine.benchmark import cases as C
from app.engine.benchmark import harness as H
from app.engine.benchmark.oracle import structural_oracle
from app.engine.llm import FakeProvider
from app.engine.methods import contract as MC
from app.engine.methods.contract import (
    EvidenceRequirement, InputSpec, MethodRegistry, MethodResult, MethodSpec, QuestionShape,
    select_methods,
)
from app.engine.registry import EngagementRegistry
from app.engine.types import ExecutionType, Interrogative, Kind
from app.engine.work_products.decl import (
    WORK_PRODUCTS, Count, SectionDecl, WorkProductDecl, plan_sections,
)
from app.engine.work_products.plan import plan_work_products

import app.engine.methods.builtin  # noqa: F401  - registration by import

# tests/engine is not a package (design 2.1), so the sibling law table is
# reached the way pytest reaches this module: by its own directory.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from rare_paths import RARE_PATHS, TRACE_SCOPE_DIRS, TRACE_SCOPE_FILES  # noqa: E402

SERVICE_ROOT = os.path.dirname(os.path.dirname(_HERE))
ENGINE_DIR = os.path.join(SERVICE_ROOT, "app", "engine")


# ===========================================================================
# 0. The tree under scan
# ===========================================================================

def _rel(path: str) -> str:
    """The path a finding names. Control files written to a temp directory are
    reported by basename: a finding is about the code, not about where pytest
    put it."""
    rel = os.path.relpath(path, SERVICE_ROOT).replace(os.sep, "/")
    return os.path.basename(path) if rel.startswith("..") else rel


def engine_files(suffix: str = ".py") -> list[str]:
    """Every file of one kind under app/engine, absolute and sorted. The scan
    walks the tree rather than a list, so a module added next week is scanned
    without anyone remembering to add it here."""
    out: list[str] = []
    for dirpath, _dirs, names in os.walk(ENGINE_DIR):
        if "__pycache__" in dirpath:
            continue
        for name in sorted(names):
            if name.endswith(suffix):
                out.append(os.path.join(dirpath, name))
    return sorted(out)


@functools.lru_cache(maxsize=None)
def _parse(path: str) -> ast.Module:
    with open(path, encoding="utf-8") as fh:
        return ast.parse(fh.read(), filename=path)


def _tree_of(path: str) -> ast.Module:
    """Parsed once per path per session for the tree; never cached for the
    temporary files the negative controls write, whose whole point is that
    each is different."""
    if path.startswith(ENGINE_DIR):
        return _parse(path)
    with open(path, encoding="utf-8") as fh:
        return ast.parse(fh.read(), filename=path)


def _branch_tests(tree: ast.AST):
    """Every expression that decides what happens next: the test of an if, a
    conditional expression, a while and an assert, and the condition of a
    comprehension. A `match` is handled with its patterns, below - a case
    pattern IS the test."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.IfExp, ast.While, ast.Assert)):
            yield node.test
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for gen in node.generators:
                for cond in gen.ifs:
                    yield cond


def _match_pattern_constants(tree: ast.AST):
    """String constants inside `match` patterns."""
    for node in ast.walk(tree):
        if isinstance(node, ast.match_case):
            for sub in ast.walk(node.pattern):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    yield sub


def _dict_key_constants(tree: ast.AST):
    """String keys of dict literals: a lookup table keyed by an engagement type
    is a branch with the `if` spelled differently."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    yield key


def _compare_string_operands(test: ast.AST):
    """The string constants a comparison in a branch test puts either side of
    the operator, including the elements of a literal tuple/list/set on the
    right - `x in ("a", "b")` is the same branch written wider."""
    for node in ast.walk(test):
        if not isinstance(node, ast.Compare):
            continue
        operands: list[ast.expr] = [node.left, *node.comparators]
        flat: list[ast.expr] = []
        for operand in operands:
            if isinstance(operand, (ast.Tuple, ast.List, ast.Set)):
                flat.extend(operand.elts)
            else:
                flat.append(operand)
        for operand in flat:
            if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                yield operand


# ===========================================================================
# 1. Denylist: no engagement-type word decides anything (design 18.1)
# ===========================================================================

# The stems of design 18.1: the vocabulary a consultancy uses to name a KIND of
# engagement. None of them may reach a decision point - not as a branch test,
# not as a match pattern, not as the key of a dispatch table.
DENY_STEMS: tuple[str, ...] = (
    "acquisition", "merger", "m&a", "integration", "market entry", "market_entry",
    "cost reduction", "cost_reduction", "cost-cutting", "restructur", "turnaround",
    "bottleneck", "product launch", "new product", "transformation", "customer experience",
    "customer-experience", "cx", "governance and risk", "risk improvement",
    "ai transformation", "technology transformation",
)


def _words(text: str) -> str:
    """Punctuation-blind form: `cost_reduction`, `cost-cutting` and
    `Cost Reduction` are the same word to the scan, because they are the same
    word to whoever would write them."""
    return " ".join(re.findall(r"[a-z0-9&]+", text.lower()))


_STEM_PATTERNS = tuple(
    (stem, re.compile(r"(?<![a-z0-9])" + re.escape(_words(stem)).replace(r"\ ", r"[ ]")))
    for stem in DENY_STEMS
)


def deny_stems_in(text: str) -> list[str]:
    """The stems this string carries. A stem matches at a word start and runs
    on: `restructur` is meant to catch `restructuring`, which is the point of
    stating stems rather than words."""
    flat = _words(text)
    return [stem for stem, pattern in _STEM_PATTERNS if pattern.search(flat)]


def denylist_findings(path: str) -> list[str]:
    """Every place in one file where an engagement-type word decides."""
    tree = _tree_of(path)
    rel = _rel(path)
    out: list[str] = []

    def report(node: ast.AST, where: str, value: str) -> None:
        stems = deny_stems_in(value)
        if stems:
            out.append(f"{rel}:{node.lineno} {where} {value!r} carries {stems}")

    for test in _branch_tests(tree):
        for node in ast.walk(test):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                report(node, "branch test", node.value)
    for node in _match_pattern_constants(tree):
        report(node, "match pattern", node.value)
    for node in _dict_key_constants(tree):
        report(node, "dict key", node.value)
    return sorted(out)


def _write(tmp_path, name: str, source: str) -> str:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return str(path)


def test_no_engagement_type_word_decides_anything_in_the_engine():
    """Layer 1. The single fact this whole component exists to keep true."""
    findings = [f for path in engine_files(".py") for f in denylist_findings(path)]
    assert findings == [], "an engagement type reached a decision point:\n" + "\n".join(findings)


def test_the_denylist_scan_reads_the_whole_tree():
    """A scan that read three files would pass for the wrong reason."""
    scanned = engine_files(".py")
    assert len(scanned) > 60
    packages = {_rel(p).split("/")[2] for p in scanned if _rel(p).count("/") > 2}
    for expected in ("partner", "methods", "synthesis", "gates", "work_products", "benchmark"):
        assert expected in packages, f"{expected} was never scanned"


def test_the_scan_catches_a_branch_on_an_engagement_type(tmp_path):
    """Negative control (design 18.1): `if kind == "acquisition":`."""
    path = _write(tmp_path, "control_branch.py", "def f(kind):\n"
                                                 "    if kind == \"acquisition\":\n"
                                                 "        return 1\n"
                                                 "    return 0\n")
    findings = denylist_findings(path)
    assert len(findings) == 1 and "acquisition" in findings[0]


def test_the_scan_catches_a_match_on_an_engagement_type(tmp_path):
    """Negative control: `match t: case "cost_reduction":`."""
    path = _write(tmp_path, "control_match.py", "def f(t):\n"
                                                "    match t:\n"
                                                "        case \"cost_reduction\":\n"
                                                "            return 1\n"
                                                "        case _:\n"
                                                "            return 0\n")
    findings = denylist_findings(path)
    assert len(findings) == 1 and "cost reduction" in str(findings[0]).lower()


def test_the_scan_catches_a_dispatch_table_keyed_by_engagement_type(tmp_path):
    """A dict is a branch with the `if` spelled differently."""
    path = _write(tmp_path, "control_dict.py",
                  "PLAYBOOKS = {\"market entry\": 1, \"turnaround\": 2}\n")
    findings = denylist_findings(path)
    assert len(findings) == 2


def test_a_stem_matches_the_word_it_is_the_stem_of():
    assert deny_stems_in("restructuring plan") == ["restructur"]
    assert deny_stems_in("a CX programme") == ["cx"]
    assert deny_stems_in("Cost-Cutting") == ["cost-cutting"]
    assert deny_stems_in("cost_reduction") == ["cost reduction", "cost_reduction"]
    assert deny_stems_in("the client wants fewer stockouts") == []


# ===========================================================================
# 2. Whitelist (S5, design 18.2): a branch test compares against a closed
#    vocabulary or against nothing at all
# ===========================================================================
#
# The denylist is a word list, and a word list is evadable by renaming the
# word. The whitelist closes that door from the other side: a branch may
# compare against a member of a vocabulary the two contract modules OWN, and
# against nothing else. A private vocabulary - a string this package invented,
# or an enum this package defined for itself - is exactly how per-engagement
# behaviour would come back under a new name, so both are refused.

CONTRACT_MODULES: tuple[str, ...] = ("app.engine.types", "app.engine.methods.contract")

# The literals a branch may still compare against, with the reason each is not
# vocabulary. Every entry is either not a word at all, or a token the engine
# receives from OUTSIDE its own domain - a unit, a file format, a provider's
# protocol, a name in its own law list. None of them can say what kind of
# engagement this is, which is the only thing this layer defends.
ADMITTED_LITERALS: frozenset[str] = frozenset({
    # (a) not words: operators, separators and the empty string
    "", " ", "%", "/", "*", "+", "-", "(", ")", "._-",
    # (b) unit and period tokens the calculator parses out of client wording
    #     (the capacity units it inherits from app/pipeline/registry.py)
    "fte", "heads", "items", "people", "staff", "units", "percent", "pp", "point_in_time",
    # (c) artifact formats
    "csv", "md", "pdf", "pptx",
    # (d) protocol tokens from outside the engine: a provider's finish reason,
    #     JSON's null, the Decimal tag in this package's own encoding
    "length", "null", "$decimal",
    # (e) verdicts these functions return in their own words
    "comparable", "correct",
    # (f) named things this package owns: one law id, two prompt templates
    "M.raci_governance.multiple_accountable", "narrative_section.j2", "simulated_client.j2",
})


@functools.lru_cache(maxsize=1)
def closed_vocabulary() -> frozenset[str]:
    """Every string a branch test may compare against: the values of every Enum
    the two contract modules define, plus the structural field names, the
    dimension names and the bound names. Read off the imported modules rather
    than parsed, so adding a vocabulary to types.py widens this by itself and
    inventing one anywhere else does not."""
    words: set[str] = set()
    for module in (T, MC):
        for obj in vars(module).values():
            if isinstance(obj, type) and issubclass(obj, enum.Enum) and obj.__module__ == module.__name__:
                words.update(m.value for m in obj if isinstance(m.value, str))
    words.update(T.FILTERABLE_FIELDS)
    words.update(T.TEXT_FIELDS)
    words.update(T.Dimensions.DIMENSION_NAMES)
    words.update(T.BOUNDS)
    return frozenset(words)


def _module_for(path: str):
    """The imported module a source file belongs to. Enum ownership is settled
    on the OBJECT (`type(member).__module__`), never on the import line that
    named it: re-exporting a private enum cannot launder it, and importing
    Kind under an alias is not mistaken for inventing one."""
    rel = _rel(path)
    if rel.startswith("app/engine/"):
        name = rel[:-3].replace("/", ".")
        if name.endswith(".__init__"):
            name = name[: -len(".__init__")]
        return importlib.import_module(name)
    spec = importlib.util.spec_from_file_location("_universality_control_" + os.path.basename(path)[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _attribute_chain(node: ast.AST) -> list[str] | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return list(reversed(parts))
    return None


def _resolve(module, chain: list[str]):
    obj = module
    for part in chain:
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def whitelist_findings(path: str) -> list[str]:
    """Every branch test in one file that compares against prose, or against an
    enum the contract modules do not own."""
    tree = _tree_of(path)
    rel = _rel(path)
    module = _module_for(path)
    admitted = closed_vocabulary() | ADMITTED_LITERALS
    out: list[str] = []

    for test in _branch_tests(tree):
        if isinstance(test, ast.Constant) and isinstance(test.value, str):
            out.append(f"{rel}:{test.lineno} branches on the string {test.value!r} itself")
        for node in _compare_string_operands(test):
            if node.value not in admitted:
                out.append(f"{rel}:{node.lineno} compares against {node.value!r}, "
                           "which no contract vocabulary contains")
        for node in ast.walk(test):
            if not isinstance(node, ast.Compare):
                continue
            for operand in [node.left, *node.comparators]:
                chain = _attribute_chain(operand)
                if chain is None or len(chain) < 2:
                    continue
                value = _resolve(module, chain)
                owner = None
                if isinstance(value, enum.Enum):
                    owner = type(value).__module__
                elif isinstance(value, type) and issubclass(value, enum.Enum):
                    owner = value.__module__
                if owner is not None and owner not in CONTRACT_MODULES:
                    out.append(f"{rel}:{node.lineno} branches on {'.'.join(chain)}, an enum "
                               f"{owner} defined for itself")
    for node in _match_pattern_constants(tree):
        if node.value not in admitted:
            out.append(f"{rel}:{node.lineno} matches the pattern {node.value!r}, "
                       "which no contract vocabulary contains")
    return sorted(set(out))


def test_no_branch_in_the_engine_compares_against_prose():
    """Layer 2 (S5). Every string a decision rests on is a member of a
    vocabulary types.py or methods/contract.py owns - or one of the handful of
    admitted non-words above, each of which is named and reasoned."""
    findings = [f for path in engine_files(".py") for f in whitelist_findings(path)]
    assert findings == [], "a branch rests on prose or on a private vocabulary:\n" + "\n".join(findings)


def test_the_closed_vocabulary_is_read_off_the_contracts():
    """It is the contracts' vocabulary, not a copy of it: every Kind and every
    Status is in it, and a word no contract declares is not."""
    vocabulary = closed_vocabulary()
    assert {k.value for k in Kind} <= vocabulary
    assert {s.value for s in T.Status} <= vocabulary
    assert "acquisition" not in vocabulary and "phase_b" not in vocabulary


def test_the_whitelist_catches_an_off_denylist_string_branch(tmp_path):
    """Negative control (design 18.2): `if mode == "phase_b":` names no
    engagement type, so layer 1 lets it through - and layer 2 does not."""
    path = _write(tmp_path, "control_phase.py", 'def f(mode):\n'
                                                '    if mode == "phase_b":\n'
                                                '        return 1\n'
                                                '    return 0\n')
    assert denylist_findings(path) == []
    findings = whitelist_findings(path)
    assert len(findings) == 1 and "phase_b" in findings[0]


def test_the_whitelist_catches_a_branch_on_a_privately_defined_enum(tmp_path):
    """Negative control (design 18.2): a module that defines its own enum and
    branches on it has invented a vocabulary. Spelling a string as an enum
    member is the obvious way past the string rule; ownership closes it."""
    path = _write(tmp_path, "control_enum.py",
                  'from enum import Enum\n'
                  '\n'
                  'class EngType(str, Enum):\n'
                  '    ACQ = "a"\n'
                  '    RED = "r"\n'
                  '\n'
                  'def f(t):\n'
                  '    if t is EngType.ACQ:\n'
                  '        return 1\n'
                  '    return 0\n')
    assert denylist_findings(path) == []
    findings = whitelist_findings(path)
    assert len(findings) == 1 and "EngType.ACQ" in findings[0]


def test_a_branch_on_a_contract_enum_passes(tmp_path):
    """The passing fixture: the same shape of branch, on an enum types.py owns."""
    path = _write(tmp_path, "control_contract_enum.py",
                  'from app.engine.types import Kind\n'
                  '\n'
                  'def f(kind):\n'
                  '    if kind is Kind.RISK:\n'
                  '        return 1\n'
                  '    return 0\n')
    assert whitelist_findings(path) == []


def test_the_whitelist_catches_a_string_match_pattern(tmp_path):
    path = _write(tmp_path, "control_match_pattern.py",
                  'def f(t):\n'
                  '    match t:\n'
                  '        case "phase_b":\n'
                  '            return 1\n'
                  '        case _:\n'
                  '            return 0\n')
    findings = whitelist_findings(path)
    assert len(findings) == 1 and "phase_b" in findings[0]


# ===========================================================================
# 3. Names (design 18.3): the engine has never heard of these clients
# ===========================================================================
#
# A denylist catches the words a consultant would use to name an engagement
# type; this layer catches the words that would tie the engine to one of the
# fifteen benchmark clients. A name in app/engine is per-case tailoring even
# when it sits in a comment, because it means someone read a case while
# writing the engine.
#
# What counts as a name is derived, not typed out: a token of five or more
# letters that a case's own identity fields use, that no OTHER case's file
# uses anywhere, and that the product's pre-engine vocabulary (app/ outside
# app/engine, and tools/) does not contain. The last two filters are what stop
# ordinary English from being mistaken for a client.

_TOKEN = re.compile(r"[^\W\d_]{5,}", re.UNICODE)

# Three ordinary words that fall inside one case's own title or company name.
# Each is used in the engine in its ordinary sense - a non-blocking finding,
# the calculator's cross-currency refusal, the count of benchmark cases - and
# `test_an_exempt_word_is_a_word_and_not_a_name` proves the engine holds the
# word without holding the name it came from.
NOT_A_NAME: frozenset[str] = frozenset({"advisory", "currencies", "fifteen"})


@functools.lru_cache(maxsize=1)
def prior_vocabulary() -> frozenset[str]:
    """Every word the product already used before the engine existed: the r30
    pipeline, its prompts and tools. Independent of app/engine by
    construction, so a name that leaked INTO the engine can never excuse
    itself by appearing there."""
    words: set[str] = set()
    for top in ("app", "tools"):
        for dirpath, _dirs, names in os.walk(os.path.join(SERVICE_ROOT, top)):
            if "__pycache__" in dirpath or os.path.join("app", "engine") in dirpath:
                continue
            for name in names:
                if name.rsplit(".", 1)[-1] not in ("py", "j2", "md", "txt", "json", "html"):
                    continue
                try:
                    with open(os.path.join(dirpath, name), encoding="utf-8") as fh:
                        words.update(t.lower() for t in _TOKEN.findall(fh.read()))
                except (OSError, UnicodeDecodeError):
                    continue
    return frozenset(words)


@functools.lru_cache(maxsize=1)
def _name_fields() -> tuple[tuple[str, str, str], ...]:
    """(case id, which field, the text) for every company, persona, document
    and title the fifteen case files carry."""
    out: list[tuple[str, str, str]] = []
    for loaded in C.load_all():
        case = loaded.case
        out.append((loaded.id, "persona", case.client_persona.name))
        out.append((loaded.id, "company", case.client_persona.company))
        out.append((loaded.id, "title", case.title))
        for document in case.documents:
            out.append((loaded.id, "document", document.name))
    return tuple(out)


@functools.lru_cache(maxsize=1)
def _cases_using() -> collections.Counter:
    """How many of the fifteen case files use each token anywhere at all. A
    token two cases share is the language of business, not the name of one
    client."""
    counter: collections.Counter = collections.Counter()
    for loaded in C.load_all():
        for token in {t.lower() for t in _TOKEN.findall(loaded.case.model_dump_json())}:
            counter[token] += 1
    return counter


def _distinctive(token: str) -> bool:
    return (_cases_using()[token] <= 1
            and token not in closed_vocabulary()
            and token not in prior_vocabulary())


@functools.lru_cache(maxsize=1)
def client_name_tokens() -> dict[str, str]:
    """token -> the case it identifies."""
    out: dict[str, str] = {}
    for case_id, _where, text in _name_fields():
        for raw in _TOKEN.findall(text):
            token = raw.lower()
            if token in NOT_A_NAME or not _distinctive(token):
                continue
            out.setdefault(token, case_id)
    return out


def _mentions(text: str, token: str) -> bool:
    return re.search(r"(?<![^\W\d_])" + re.escape(token) + r"(?![^\W\d_])", text) is not None


def name_findings(path: str) -> list[str]:
    """Every client name one file mentions."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read().lower()
    rel = _rel(path)
    return sorted(f"{rel} names {token!r}, which identifies {case_id}"
                  for token, case_id in client_name_tokens().items() if _mentions(text, token))


def test_no_client_name_appears_anywhere_in_the_engine():
    """Layer 3. Source and prompts alike: a name in a comment is still a name
    that was read off a case."""
    findings = [f for path in engine_files(".py") + engine_files(".j2") for f in name_findings(path)]
    assert findings == [], "the engine names a benchmark client:\n" + "\n".join(findings)


def test_every_case_contributes_a_name_to_the_scan():
    """A scan with nothing to look for passes for free. Every one of the
    fifteen engagements must put at least one name into the pool."""
    tokens = client_name_tokens()
    per_case = collections.Counter(tokens.values())
    missing = sorted({case.id for case in C.load_all()} - set(per_case))
    assert missing == [], f"no name was derived for {missing}"
    assert len(tokens) >= 60


def test_an_exempt_word_is_a_word_and_not_a_name():
    """The three exemptions cannot become a licence. For each, every OTHER
    distinctive token of the name it came from must be absent from the engine:
    the engine holds the word, never the client it belongs to."""
    engine_text = "\n".join(text for _path, text in _engine_text())
    stale = sorted(word for word in NOT_A_NAME if not _distinctive(word) or not _mentions(engine_text, word))
    assert stale == [], f"the engine no longer needs these exemptions; drop them: {stale}"
    for word in sorted(NOT_A_NAME):
        for case_id, where, text in _name_fields():
            tokens = {t.lower() for t in _TOKEN.findall(text)}
            if word not in tokens:
                continue
            leaked = sorted(t for t in tokens - {word} if _distinctive(t) and _mentions(engine_text, t))
            assert leaked == [], (f"{word!r} is exempt, but the engine also holds {leaked} from the "
                                  f"same {where} of {case_id}: that is the name, not the word")


@functools.lru_cache(maxsize=1)
def _engine_text() -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    for path in engine_files(".py") + engine_files(".j2"):
        with open(path, encoding="utf-8") as fh:
            out.append((_rel(path), fh.read().lower()))
    return tuple(out)


def test_the_name_scan_catches_a_client_name(tmp_path):
    """Negative control: a module that mentions one company by name."""
    company = next(token for token, case_id in client_name_tokens().items()
                   if case_id == "acquisition-integration-nordvik-baltic")
    path = _write(tmp_path, "control_name.py", f'# tuned for the {company} engagement\n'
                                               'VALUE = 1\n')
    findings = name_findings(path)
    assert len(findings) == 1 and company in findings[0]


def test_the_name_scan_lets_ordinary_language_through(tmp_path):
    """The passing fixture: prose about consulting is not a client."""
    path = _write(tmp_path, "control_prose.py",
                  '"""A recommendation rests on facts the client confirmed."""\n'
                  'VALUE = 1\n')
    assert name_findings(path) == []


# ===========================================================================
# 4. Prompts (design 18.4): the model is told the shape, never the type
# ===========================================================================

def prompt_findings(path: str) -> list[str]:
    """An engagement type written into a prompt is a branch the model takes
    for us: it would answer a market-entry question differently because the
    template said so. Kinds reach a template as variables, never as words."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    rel = _rel(path)
    out: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stems = deny_stems_in(line)
        if stems:
            out.append(f"{rel}:{number} names {stems}")
    return out


def test_no_prompt_names_an_engagement_type():
    """Layer 4."""
    prompts = engine_files(".j2")
    assert len(prompts) >= 9, "the prompt directory was not found"
    findings = [f for path in prompts for f in prompt_findings(path)]
    assert findings == [], "a prompt names an engagement type:\n" + "\n".join(findings)


def test_the_prompt_scan_catches_a_typed_template(tmp_path):
    """Negative control."""
    path = _write(tmp_path, "control_prompt.j2", "You are advising on a market entry.\n")
    findings = prompt_findings(path)
    assert len(findings) == 1 and "market entry" in findings[0]


# ===========================================================================
# 5. Imports and calls (design 18.5): nothing in the engine guesses at text
# ===========================================================================
#
# Three imports and one call are how prose would quietly become a decision
# again: a fuzzy matcher (two strings "close enough" to be the same thing), a
# second door to the model provider, and a regular-expression rewrite of
# rendered words. The engine reconciles on ids (MF1.6), calls one provider
# (design 15) and rewrites text in exactly one module (S15).

FORBIDDEN_IMPORTS: dict[str, str] = {
    "difflib": "similarity is not identity; facts reconcile on measure_id (MF1.6)",
    "rapidfuzz": "similarity is not identity; facts reconcile on measure_id (MF1.6)",
    "app.ai.provider": "one provider boundary; llm.py wraps it (design 15)",
}
PROVIDER_MODULE = "app/engine/llm.py"

# Where a regular-expression rewrite is permitted, and for what (design 18.5):
# unit spelling, page furniture, and the one correction module.
RE_SUB_MODULES: frozenset[str] = frozenset({
    "app/engine/calc/units.py",
    "app/engine/gates/presentation.py",
    "app/engine/work_products/corrections.py",
})
# One call in the tree sits outside those three: the persistence layer's
# filesystem-name sanitiser, which rewrites a FILENAME and never a rendered
# word. It is pinned by its exact pattern and replacement so the carve-out
# cannot grow into a text rewrite, and it is on the list to be replaced with a
# stdlib character filter.
PINNED_SUBSTITUTIONS: frozenset[tuple[str, str, str]] = frozenset({
    ("app/engine/persistence/store.py", r"[^A-Za-z0-9._-]+", "_"),
})


def _literal(node: ast.AST):
    return node.value if isinstance(node, ast.Constant) else None


def import_findings(path: str, rel: str | None = None) -> list[str]:
    """Every forbidden import and every unpinned text substitution in one file.
    `rel` lets a control file be scanned as if it were a module the tree holds,
    so the pin can be tested where the pin applies."""
    tree = _tree_of(path)
    rel = rel or _rel(path)
    out: list[str] = []

    def check_import(node: ast.AST, name: str) -> None:
        for forbidden, why in FORBIDDEN_IMPORTS.items():
            if name == forbidden or name.startswith(forbidden + "."):
                if forbidden == "app.ai.provider" and rel == PROVIDER_MODULE:
                    return
                out.append(f"{rel}:{node.lineno} imports {forbidden}: {why}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                check_import(node, alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            check_import(node, module)
            for alias in node.names:
                check_import(node, f"{module}.{alias.name}")
                if module == "re" and alias.name in ("sub", "subn"):
                    out.append(f"{rel}:{node.lineno} imports re.{alias.name} by name")
        elif isinstance(node, ast.Call):
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr in ("sub", "subn")):
                continue
            if not (isinstance(func.value, ast.Name) and func.value.id == "re"):
                continue
            if rel in RE_SUB_MODULES:
                continue
            args = list(node.args)
            pinned = (rel, _literal(args[0]) if args else None, _literal(args[1]) if len(args) > 1 else None)
            if pinned in PINNED_SUBSTITUTIONS:
                continue
            out.append(f"{rel}:{node.lineno} rewrites text with re.{func.attr}, "
                       "which only units, presentation and corrections may do")
    # `from app.ai.provider import chat` reports the module once, not once for
    # the module and once for every name taken out of it.
    return sorted(set(out))


def test_the_engine_never_imports_a_fuzzy_matcher_or_a_second_provider():
    """Layer 5."""
    findings = [f for path in engine_files(".py") for f in import_findings(path)]
    assert findings == [], "\n".join(findings)


def test_the_one_provider_import_is_in_llm_py():
    """The rule is not that nobody imports the provider - it is that one
    module does, and the test would notice if that module stopped."""
    provider = os.path.join(SERVICE_ROOT, PROVIDER_MODULE.replace("/", os.sep))
    source = _tree_of(provider)
    imported = {f"{n.module}.{a.name}" for n in ast.walk(source)
                if isinstance(n, ast.ImportFrom) and n.module for a in n.names}
    imported |= {n.module for n in ast.walk(source) if isinstance(n, ast.ImportFrom) and n.module}
    imported |= {a.name for n in ast.walk(source) if isinstance(n, ast.Import) for a in n.names}
    assert "app.ai.provider" in imported


def test_a_pinned_substitution_is_pinned_to_its_exact_call(tmp_path):
    """A carve-out that admitted `re.sub` in a module would be a licence. Each
    pinned entry names the pattern and the replacement, so the same module
    rewriting anything else is still a finding."""
    module_rel, pattern, repl = sorted(PINNED_SUBSTITUTIONS)[0]
    assert module_rel not in RE_SUB_MODULES
    pinned = _write(tmp_path, "control_pinned.py", "import re\n"
                                                   "def name(base):\n"
                                                   f'    return re.sub(r"{pattern}", "{repl}", base)\n')
    assert import_findings(pinned, rel=module_rel) == []
    widened = _write(tmp_path, "control_widened.py", "import re\n"
                                                     "def name(base):\n"
                                                     '    return re.sub(r"[a-z]+", "x", base)\n')
    assert len(import_findings(widened, rel=module_rel)) == 1


def test_the_pinned_substitution_is_still_the_call_that_module_makes(tmp_path):
    """And the pin is not a fiction: the module it names holds exactly that
    call today, so no finding is being suppressed for a call that moved."""
    module_rel = sorted(PINNED_SUBSTITUTIONS)[0][0]
    path = os.path.join(SERVICE_ROOT, module_rel.replace("/", os.sep))
    assert import_findings(path) == []
    calls = [n for n in ast.walk(_tree_of(path))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr in ("sub", "subn")]
    assert len(calls) == 1, "the pinned module's substitutions changed; re-pin or remove the entry"


def test_the_import_scan_catches_a_fuzzy_matcher(tmp_path):
    """Negative control (and the pinned mutation for render_md.py)."""
    path = _write(tmp_path, "control_difflib.py", 'import difflib\n'
                                                  'def f(a, b):\n'
                                                  '    return difflib.SequenceMatcher(None, a, b).ratio()\n')
    findings = import_findings(path)
    assert len(findings) == 1 and "difflib" in findings[0]


def test_the_import_scan_catches_a_text_rewrite(tmp_path):
    """Negative control: re.sub outside the three modules allowed one."""
    path = _write(tmp_path, "control_resub.py", 'import re\n'
                                                'def f(text):\n'
                                                '    return re.sub(r"[a-z]+", "x", text)\n')
    findings = import_findings(path)
    assert len(findings) == 1 and "re.sub" in findings[0]


def test_the_import_scan_catches_a_second_provider_door(tmp_path):
    path = _write(tmp_path, "control_provider.py", 'from app.ai.provider import chat\n'
                                                   'VALUE = chat\n')
    findings = import_findings(path)
    assert len(findings) == 1 and "app.ai.provider" in findings[0]


# ===========================================================================
# 6. Vocabulary-blind behaviour (design 18.6): the same engagement in words
#    nobody can read
# ===========================================================================
#
# Layers 1-5 read the source. This one runs the engine twice on the same
# fifteen registries - once as they are, once with every text field replaced by
# a token that carries no meaning at all - and demands the same method
# selections, the same work products and the same sections. It is the layer a
# clever rename cannot survive: if any selector reads prose, the prose it read
# is gone.

def _mask(value: str) -> str:
    """A stable, collision-free replacement. Same input, same token (so a
    comparison of two scrambles is a comparison of the same registry), and
    the tokens are hex, which means no English word survives inside one."""
    return "t" + hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def _loud(value: str) -> str:
    """The masked value with every engagement-type word appended. A selector
    that reads prose for a word no case happens to use is invisible to the
    mask and cannot hide from this."""
    return _mask(value) + " " + " ".join(DENY_STEMS)


def _scramble_payload(payload, mask):
    changes = {}
    for field in dataclasses.fields(payload):
        if field.name not in T.TEXT_FIELDS:
            continue
        value = getattr(payload, field.name)
        if isinstance(value, str) and value:
            changes[field.name] = mask(value)
        elif isinstance(value, tuple) and value and all(isinstance(v, str) and v for v in value):
            changes[field.name] = tuple(mask(v) for v in value)
    return dataclasses.replace(payload, **changes) if changes else payload


def scrambled(registry: EngagementRegistry, mask=_mask) -> EngagementRegistry:
    """The same engagement with every TEXT_FIELDS value replaced. An EMPTY
    text stays empty: absence is a state of its own (design 1.1), and turning
    a hole into a word would be a different registry, not the same one in
    other words."""
    rows = []
    for row in registry.rows():
        payload = _scramble_payload(row.payload, mask)
        rows.append(row if payload is row.payload else dataclasses.replace(row, payload=payload))
    return EngagementRegistry.from_rows(registry.engagement_id, rows, clock=lambda: H.FIXED_CLOCK)


def selection_signature(view, methods=MC.METHODS) -> tuple:
    """What the selector decided, in the terms it decided them: which method
    took on which node, how much of its input it had, and whether it was tied."""
    selections = select_methods(view.live(Kind.ISSUE), view, methods=methods)
    return tuple(sorted((s.issue_id, s.method_id, s.tied, round(s.inputs.ratio, 12),
                         tuple(s.rank_key[1:])) for s in selections))


def plan_signature(view) -> tuple:
    """What the planner decided. The rendered TITLE is deliberately left out:
    titles are rendered from entity fields on purpose (MF1.1), so they are the
    one thing that SHOULD move when the words move."""
    plan = plan_work_products(view)
    return (tuple(sorted((v.product_id, v.section_ids, v.because) for v in plan.planned)),
            tuple(sorted((v.product_id, v.because) for v in plan.unplanned)))


def section_signature(view) -> tuple:
    return tuple((decl.id, plan_sections(decl, view)) for decl in WORK_PRODUCTS.all())


@pytest.fixture(scope="module")
def loaded():
    return C.load_all()


@pytest.fixture(scope="module")
def traced(loaded):
    """Every case run once, under a profiler that records which functions in
    TRACE_SCOPE it walked. Module-scoped because fifteen engagements are what
    both remaining layers are about, and because the runs are deterministic:
    running them again would say the same thing more slowly."""
    return _run_every_case(loaded)


def rewordings(view) -> list[tuple[str, EngagementRegistry]]:
    """The same engagement said twice over. `silent` takes every word away;
    `loud` gives every text field EVERY engagement-type word at once. Silence
    alone is not enough: a selector that reads a word no case happens to use
    reads nothing under a mask and still reads it in the field. Between the two
    variants, a text-reading selector either loses what it read or finds what
    it was looking for, and either way its answer moves."""
    return [("silent", scrambled(view, _mask)), ("loud", scrambled(view, _loud))]


def test_selection_is_the_same_whatever_the_words_say(traced):
    """Layer 6, selection (M2/P1). Method selection reads QuestionShapes and
    FILTERABLE_FIELDS; the scramble proves it, rather than the InputSpec
    constructor's refusal being taken on trust."""
    mismatched = []
    for case_id, bundle in sorted(traced.bundles.items()):
        view = bundle.registry
        before = selection_signature(view)
        assert before, f"{case_id} selected no method at all; the check would be vacuous"
        for name, other in rewordings(view):
            if before != selection_signature(other):
                mismatched.append(f"{case_id} ({name})")
    assert mismatched == [], f"selection moved when the words moved: {mismatched}"


def test_the_planned_products_and_their_sections_survive_a_rewording(traced):
    """Layer 6, planning (P1/P2, MF1.1). Which products an engagement gets and
    which sections they carry is a fact about the registry's structure."""
    moved = []
    for case_id, bundle in sorted(traced.bundles.items()):
        view = bundle.registry
        plan, sections = plan_signature(view), section_signature(view)
        for name, other in rewordings(view):
            if plan != plan_signature(other):
                moved.append(f"{case_id} ({name}) products")
            if sections != section_signature(other):
                moved.append(f"{case_id} ({name}) sections")
    assert moved == [], f"planning read prose: {moved}"


def test_the_rewordings_really_did_reword(traced):
    """The control on the control: a scramble that changed nothing, or a loud
    variant that did not actually say the words, would make the two tests above
    pass for free."""
    view = traced.bundles[sorted(traced.bundles)[0]].registry
    texts = {e.payload.text for e in view.live(Kind.ISSUE)}
    assert texts
    for name, other in rewordings(view):
        assert view.content_hash() != other.content_hash()
        assert len(other.rows()) == len(view.rows())
        reworded = {e.payload.text for e in other.live(Kind.ISSUE)}
        assert not (texts & reworded), f"the {name} variant left a text untouched"
    silent = {e.payload.text for e in scrambled(view, _mask).live(Kind.ISSUE)}
    assert all(t.startswith("t") and len(t) == 17 for t in silent)
    loud = {e.payload.text for e in scrambled(view, _loud).live(Kind.ISSUE)}
    assert all(deny_stems_in(t) == list(DENY_STEMS) for t in loud)


class _ProseReadingInput(InputSpec):
    """An input that reads prose. M2 refuses a text FILTER at construction, so
    a declaration cannot express this; overriding the matcher in code is the
    only way prose reaches selection at all, and this control does it to prove
    the scramble detector sees it when it happens."""

    def matches(self, entity) -> bool:
        return entity.kind == self.kind and "the" in str(getattr(entity.payload, "text", "")).lower()


def _prose_reading_method(kind: Kind) -> MethodRegistry:
    """A method whose input is satisfied by prose, in a registry of its own -
    the global METHODS is never touched by a control."""
    spec = MethodSpec(
        id="control_prose_reader", version=1,
        applicability=(QuestionShape(interrogative=Interrogative.WHY, target_kind=Kind.FACT, causal=True),
                       QuestionShape(interrogative=Interrogative.HOW_MUCH, target_kind=Kind.COST),
                       QuestionShape(interrogative=Interrogative.WHAT, target_kind=Kind.FACT)),
        answers=(Interrogative.WHY, Interrogative.HOW_MUCH, Interrogative.WHAT),
        required_inputs=(_ProseReadingInput(name="prose", kind=kind),),
        optional_inputs=(), execution=ExecutionType.DETERMINISTIC, output_kinds=(Kind.HYPOTHESIS,),
        output_schema=None, evidence=EvidenceRequirement(), limitations=(), validators=())

    class _Control:
        def __init__(self):
            self.spec = spec

        def run(self, ctx):
            return MethodResult()

    registry = MethodRegistry()
    registry.register(_Control())
    return registry


def test_the_scramble_detector_fires_on_a_method_that_reads_prose(traced):
    """Negative control (design 18.6). The detector must be able to fail."""
    view = next(bundle.registry for _case, bundle in sorted(traced.bundles.items())
                if bundle.registry.live(Kind.ISSUE))
    methods = _prose_reading_method(Kind.ISSUE)
    control = _ProseReadingInput(name="prose", kind=Kind.ISSUE)
    assert any(control.matches(e) for e in view.live(Kind.ISSUE)), \
        "no live issue carries ordinary prose; the control would pass vacuously"
    other = scrambled(view)
    assert not any(control.matches(e) for e in other.live(Kind.ISSUE))
    assert selection_signature(view, methods=methods) != selection_signature(other, methods=methods)


def test_the_scramble_detector_fires_on_a_section_that_reads_prose(traced):
    """Negative control (design 18.6), section-level (MF1.1): a section whose
    query reads prose is dropped once the prose is gone."""
    view = next(bundle.registry for _case, bundle in sorted(traced.bundles.items())
                if bundle.registry.live(Kind.ISSUE))
    decl = WorkProductDecl(
        id="control_prose_product", title_template="control",
        applicability=Count(InputSpec(name="issues", kind=Kind.ISSUE), min_count=1),
        sections=(SectionDecl(id="s_prose", title="prose", renderer="statement_list",
                              query=(_ProseReadingInput(name="prose", kind=Kind.ISSUE),)),
                  SectionDecl(id="s_always", title="always", renderer="statement_list",
                              query=(), required=True)))
    assert plan_sections(decl, view) == ("s_prose", "s_always")
    assert plan_sections(decl, scrambled(view)) == ("s_always",)


# ===========================================================================
# 7. One path, scoped (MF1.5, design 18.7)
# ===========================================================================
#
# A per-case script leaves a footprint no source scan sees: a function only one
# engagement ever walks. The profiler records every call the fifteen runs make
# inside TRACE_SCOPE, and the law is that a path is walked by at least two of
# the ten core cases - or is named in RARE_PATHS with the unit test that walks
# it deliberately. Scoped, because MF1.5 is precisely that an unscoped
# single-path trace fails on paths that are rare for honest reasons.

@dataclasses.dataclass(frozen=True)
class _Traced:
    bundles: dict
    walked: dict                 # (path, qualname) -> set of case ids
    core: frozenset


def _scope_of(filename: str) -> str:
    """The path a traced code object belongs to, or "" when it is out of scope."""
    try:
        rel = os.path.relpath(filename, SERVICE_ROOT).replace(os.sep, "/")
    except ValueError:                                   # another drive: not ours
        return ""
    if rel in TRACE_SCOPE_FILES or any(rel.startswith(d + "/") for d in TRACE_SCOPE_DIRS):
        return rel
    return ""


def _run_every_case(loaded) -> _Traced:
    bundles, walked = {}, collections.defaultdict(set)
    for case in loaded:
        hit: set[tuple[str, str]] = set()
        scope: dict[str, str] = {}

        def profile(frame, event, arg, hit=hit, scope=scope):
            if event != "call":
                return
            code = frame.f_code
            rel = scope.get(code.co_filename)
            if rel is None:
                rel = scope[code.co_filename] = _scope_of(code.co_filename)
            if rel:
                hit.add((rel, code.co_qualname))

        previous = sys.getprofile()
        sys.setprofile(profile)
        try:
            bundles[case.id] = H.run_case(case, FakeProvider(oracle=structural_oracle))
        finally:
            sys.setprofile(previous)
        for key in hit:
            walked[key].add(case.id)
    return _Traced(bundles=bundles, walked=dict(walked),
                   core=frozenset(c.id for c in C.core_cases(loaded)))


def single_path_findings(walked, core, rare_paths) -> list[str]:
    """The law itself, as a function of a trace: every scoped function two core
    engagements did not both walk, minus the ones named in RARE_PATHS."""
    out = []
    for (rel, qualname), case_ids in sorted(walked.items()):
        if len(case_ids & core) >= 2 or f"{rel}:{qualname}" in rare_paths:
            continue
        out.append(f"{rel}:{qualname} walked only by {sorted(case_ids)}")
    return out


def test_every_path_is_walked_by_two_engagements_or_named(traced):
    """Layer 7."""
    findings = single_path_findings(traced.walked, traced.core, RARE_PATHS)
    assert findings == [], ("a path belongs to one engagement; walk it from a second case or "
                            "name it in rare_paths.py with the test that walks it:\n" + "\n".join(findings))


def test_the_trace_saw_the_scope_it_claims_to_cover(traced):
    """A trace that recorded nothing would make the law vacuous."""
    covered = {rel for rel, _q in traced.walked}
    for scoped in TRACE_SCOPE_FILES:
        assert scoped in covered, f"{scoped} was never executed by any case"
    for directory in TRACE_SCOPE_DIRS:
        assert any(rel.startswith(directory + "/") for rel in covered), f"{directory} was never executed"
    assert len(traced.walked) >= 150
    assert len(traced.core) >= 2 and len(traced.bundles) == len(C.case_ids())


@functools.lru_cache(maxsize=1)
def _test_function_names() -> frozenset[str]:
    """Every test function this directory defines, by name."""
    names: set[str] = set()
    for entry in sorted(os.listdir(_HERE)):
        if not (entry.startswith("test_") and entry.endswith(".py")):
            continue
        for node in ast.walk(_parse(os.path.join(_HERE, entry))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                names.add(node.name)
    return frozenset(names)


def missing_rare_tests(rare_paths) -> list[str]:
    known = _test_function_names()
    return sorted(f"{path} names {name}, which no test in tests/engine defines"
                  for path, name in rare_paths.items() if name not in known)


def test_every_named_rare_path_has_the_test_it_names():
    """Layer 7's other half: an exception is a claim with evidence attached.
    Delete or rename the test and the claim fails here rather than quietly
    excusing a path nothing walks on purpose."""
    assert missing_rare_tests(RARE_PATHS) == []


def test_a_rare_path_entry_is_in_scope_and_was_actually_walked(traced):
    """The table holds no ghosts: every entry names a function inside
    TRACE_SCOPE that the fifteen runs really did execute."""
    walked = {f"{rel}:{qualname}" for rel, qualname in traced.walked}
    for path in sorted(RARE_PATHS):
        module_rel = path.rsplit(":", 1)[0]
        assert module_rel in TRACE_SCOPE_FILES or any(
            module_rel.startswith(d + "/") for d in TRACE_SCOPE_DIRS), f"{path} is outside the traced scope"
        assert path in walked, f"{path} was never executed; drop it from RARE_PATHS"


def test_the_trace_reports_a_path_only_one_engagement_walks():
    """Negative control (design 18.7). The law is a function of a trace, so the
    control feeds it a trace: one function walked by a single core case and
    named nowhere is reported, and naming it silences exactly that one."""
    walked = {
        ("app/engine/partner/loop.py", "Partner.turn"): {"case-a", "case-b"},
        ("app/engine/partner/loop.py", "_only_for_one_client"): {"case-a"},
    }
    core = frozenset({"case-a", "case-b"})
    findings = single_path_findings(walked, core, {})
    assert len(findings) == 1 and "_only_for_one_client" in findings[0]
    assert single_path_findings(walked, core, {"app/engine/partner/loop.py:_only_for_one_client": "test_x"}) == []


def test_an_adversarial_case_alone_does_not_make_a_path_common():
    """Two core cases, not two cases: the five adversarial files exist to break
    the engine, and a path only they reach is still a path one situation owns."""
    walked = {("app/engine/gates/laws.py", "_l99"): {"core-1", "adv-1", "adv-2"}}
    findings = single_path_findings(walked, frozenset({"core-1", "core-2"}), {})
    assert len(findings) == 1


def test_a_rare_path_naming_a_test_that_does_not_exist_is_reported():
    """Negative control: the named test must exist."""
    missing = missing_rare_tests({"app/engine/gates/laws.py:_finding": "test_that_was_never_written"})
    assert len(missing) == 1 and "test_that_was_never_written" in missing[0]
    assert missing_rare_tests({"app/engine/gates/laws.py:_finding":
                               "test_every_named_rare_path_has_the_test_it_names"}) == []
