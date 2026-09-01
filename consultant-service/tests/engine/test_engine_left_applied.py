"""C26 - the LEFT-APPLIED GUARD: the file that reads the TREE, not the laws.

Every other law file in tests/engine asks whether the engine behaves. This one
asks a question none of them can: *is one of their own named mutations standing
in production source right now?*

The regime already says a mutation must be applied to an in-memory copy of the
original bytes, written, tested, and restored in a `finally` with the bytes
re-read and compared. That protocol has one silent failure mode, and it has
already happened here: an agent applies a mutation, the restore does not run or
does not cover the edit, the mutant ships in `app/engine`, and NOTHING notices -
because the mutation was invented precisely so that the suite stays green under
it. A dead-coded guard reached production this way and survived a full freeze
review. Every test passed. That was the point of the mutation.

So the check cannot be another behavioural law. It has to read the source and
ask whether the mutant is there, and it has to be derived from what the law
files themselves say rather than from a list somebody remembers to update.

Five laws, and the controls that keep them from being decorative:

  LA0  the scanner still reads the corpus. Everything below is DERIVED from the
       law files, so a pattern that quietly stopped matching would leave four
       laws asserting nothing in the most convincing way available: by passing.

  LA1  no named mutation's own code is standing in production source. The pins
       are DERIVED from the law files: every mutation clause in every
       `tests/engine/test_engine_*.py`, every code fragment it quotes in
       backticks, and a direction taken from its own verb. "drop X" says X must
       still be there; "`return wording(option)`" says that must not be. A pin
       nobody wrote is a pin nobody can forget.

  LA2  no check in `app/engine` has been made INERT. Unreachable statements, a
       condition a constant decides, a marker comment left behind. This is the
       shape the shipped guard had, and it is caught without knowing which
       mutation it was - which is what makes it hold for the mutations nobody
       has invented yet.

  LA3  no guard a law NAMES has been emptied to a constant. `synthesis_blockers
       returns () always`, `return an empty frozenset from saturated_kinds`,
       `return {} from _field_rules`: the mutant is valid code with no
       unreachable line in it, so LA2 cannot see it. The functions are read off
       the clauses, so this covers every guard the suite has ever named.

  LA4  the bound the analysis laws measure with is not standing raised at its
       declaration, is still DERIVED there rather than written as a number, and
       the three bounds it is derived FROM have not been raised instead - which
       is the same mutation one level down, and is how it survived the first
       sweep of this file.

  CONTROLS. Every detector above is run against an in-memory MUTANT of real
       production source and must FIRE, and against the shapes it must NOT flag
       and stay silent. A guard asserting only that it found nothing is
       indistinguishable from a guard that cannot find anything - the very
       defect this file exists to close, one level up. Two of the controls are
       here because a sweep found the detector blind and a reading did not:
       `return frozenset()` is a Call and was not read as a constant, and a
       PRESENT pin was satisfied by the `def` line of the very call that had
       been deleted. Nothing is ever written to disk: the mutant is a string.

WHAT THIS FILE CANNOT DO, stated so nobody reads more into a green run than is
there: a mutation that leaves ordinary, reachable, plausible code behind - a
comparison reversed, a threshold nudged, a branch reordered - is invisible to a
source scan and is caught only by the law that names it. LA1 covers exactly
those clauses that quote their mutant or their target; LA2/LA3 cover the
"make the check inert" class completely, for named and unnamed mutations alike.

No production module is read for anything but text, and none is written.
"""
from __future__ import annotations

import ast
import builtins
import os
import re
from dataclasses import dataclass

import pytest

from app.engine.types import BOUNDS

SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP_ROOT = os.path.join(SERVICE_ROOT, "app", "engine")
LAW_ROOT = os.path.join(SERVICE_ROOT, "tests", "engine")


# ===========================================================================
# 1. Reading the tree
# ===========================================================================

def production_files() -> dict[str, str]:
    """Every module under `app/engine`, by repo-relative path.

    `app/pipeline` is deliberately not read: it is byte-frozen by
    `tests/engine/r30_manifest.json`, and identical bytes cannot hold a mutant.
    """
    out: dict[str, str] = {}
    for dirpath, _dirs, files in os.walk(APP_ROOT):
        if "__pycache__" in dirpath:
            continue
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, SERVICE_ROOT).replace(os.sep, "/")
            with open(path, encoding="utf-8", newline="") as fh:
                # Line endings are NOT uniform under app/engine, and a pin whose
                # fragment spans a line break would match in the LF half of the
                # tree and silently never match in the CRLF half - a detector
                # that cannot detect, which is the defect this file is about.
                out[rel] = fh.read().replace("\r\n", "\n")
    return out


def law_files() -> list[str]:
    return sorted(os.path.join(LAW_ROOT, f) for f in os.listdir(LAW_ROOT)
                  if f.startswith("test_engine_") and f.endswith(".py"))


SOURCES = production_files()


# ===========================================================================
# 2. Reading the laws: every named mutation, mechanically
# ===========================================================================

CLAUSE_START = re.compile(
    r"^\s*(?:mutation caught|Mutation(?: '[^']*')?|MUTATION THIS MUST CATCH|mutation)\s*[:(]",
    re.IGNORECASE)


@dataclass(frozen=True)
class Clause:
    """One named mutation, as its own law file states it."""
    law_file: str
    line: int
    text: str

    @property
    def where(self) -> str:
        return f"tests/engine/{self.law_file}:{self.line}"


def clauses() -> tuple[Clause, ...]:
    """Every named mutation in every law file.

    A clause runs from its introducing line to the end of its paragraph, so a
    mutation stated across four lines is one clause and not four fragments.
    """
    out: list[Clause] = []
    for path in law_files():
        name = os.path.basename(path)
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        i = 0
        while i < len(lines):
            if not CLAUSE_START.match(lines[i]):
                i += 1
                continue
            buf = [lines[i].strip()]
            j = i + 1
            while j < len(lines) and lines[j].strip() and not CLAUSE_START.match(lines[j]):
                stripped = lines[j].strip()
                if stripped.startswith('"""') or stripped.startswith("#"):
                    break
                buf.append(stripped)
                j += 1
            out.append(Clause(name, i + 1, " ".join(buf)))
            i = j
    return tuple(out)


BACKTICKED = re.compile(r"`([^`\n]+)`")
CODE_SHAPED = re.compile(r"[()\[\]=]|->")
REMOVAL_VERB = re.compile(r"\b(drop|delete|remove|stop|strip|omit|without)\b", re.IGNORECASE)
DEFINITION_LINE = re.compile(r"^\s*(?:async\s+def|def|class)\s")
MIN_FRAGMENT = 6


@dataclass(frozen=True)
class Pin:
    """One derived source pin: a fragment of code a clause quotes, and which
    way round the clause means it.

    PRESENT - the clause's mutation REMOVES this, so it must still be there.
    ABSENT  - the clause's mutation IS this, so it must not be.
    """
    clause: Clause
    direction: str
    fragment: str
    segments: tuple[str, ...]

    def standing_in(self, sources: dict[str, str]) -> list[str]:
        """The production files in which this fragment is present. A fragment
        elided with `...` is present only where EVERY part of it is: half a
        quoted mutant is not the mutant.

        A PRESENT pin does not read `def` and `class` lines. `drop
        `_decision_owned(spec)` from the free-run condition` deletes a CALL, and
        the definition `def _decision_owned(spec) -> bool:` contains those same
        characters - so the pin reported the code present in a tree where every
        use of it had gone. An ABSENT pin reads the whole file, because a
        planted mutant may sit on a signature.
        """
        return sorted(rel for rel, text in sources.items()
                      if all(seg in self._searchable(text) for seg in self.segments))

    def _searchable(self, text: str) -> str:
        if self.direction != "PRESENT":
            return text
        return "\n".join("" if DEFINITION_LINE.match(line) else line
                          for line in text.splitlines())


def _segments(fragment: str) -> tuple[str, ...]:
    parts = [p.strip() for p in fragment.split("...")]
    return tuple(p for p in parts if len(p) >= MIN_FRAGMENT)


def derived_pins() -> tuple[Pin, ...]:
    """Every clause's quoted code, turned into a pin on production source.

    Nothing is listed by hand. A law added tomorrow that quotes its mutant is
    pinned tomorrow, and a law whose mutant is prose contributes nothing here
    and is left to the law itself - which is honest, and is why LA2 and LA3
    exist beside this.
    """
    out: list[Pin] = []
    for clause in clauses():
        for raw in BACKTICKED.findall(clause.text):
            fragment = raw.strip().rstrip(".")
            if "/" in fragment:          # a path names a target, not a mutant
                continue
            if len(fragment) < MIN_FRAGMENT or not CODE_SHAPED.search(fragment):
                continue
            segments = _segments(fragment)
            if not segments:
                continue
            head = clause.text.split("`" + raw)[0][-70:]
            direction = "PRESENT" if REMOVAL_VERB.search(head) else "ABSENT"
            out.append(Pin(clause, direction, fragment, segments))
    return tuple(out)


def named_guards() -> dict[str, list[str]]:
    """Every production function a mutation clause names, by name -> the files
    defining it. Builtin names are dropped: a clause reading "`any` -> `all`"
    names an operator, not a guard."""
    wanted: set[str] = set()
    for clause in clauses():
        for raw in BACKTICKED.findall(clause.text):
            name = raw.strip().rstrip(".")
            if name.isidentifier() and not hasattr(builtins, name):
                wanted.add(name)
    out: dict[str, list[str]] = {}
    for rel, text in SOURCES.items():
        for node in ast.walk(ast.parse(text, rel)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted:
                out.setdefault(node.name, []).append(rel)
    return out


# ===========================================================================
# 3. The detectors. Each is a pure function of source text, so the control
#    below can run the SAME function over a mutant that was never written.
# ===========================================================================

def _forced(test: ast.AST) -> str:
    """Whether a condition is decided before it is evaluated."""
    if isinstance(test, ast.Constant) and isinstance(test.value, (bool, int)):
        return f"the condition is the constant {test.value!r}"
    if isinstance(test, ast.BoolOp):
        for value in test.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, (bool, int, type(None))):
                if isinstance(test.op, ast.Or) and bool(value.value):
                    return f"`or {value.value!r}` decides the condition"
                if isinstance(test.op, ast.And) and not bool(value.value):
                    return f"`and {value.value!r}` decides the condition"
    if isinstance(test, ast.Compare) and isinstance(test.left, ast.Name):
        for op, other in zip(test.ops, test.comparators):
            if isinstance(op, (ast.Is, ast.Eq)) and isinstance(other, ast.Name) \
                    and other.id == test.left.id:
                return f"`{test.left.id}` is compared with itself"
    return ""


MARKERS = ("# mutation", "#mutation", "# mutant", "# mut:", "# left applied", "# mutate")


def inert_code(rel: str, text: str) -> list[str]:
    """LA2's detector: code that cannot affect the outcome.

    Three shapes, and they are shapes rather than a list of known mutants
    because a mutation nobody has invented yet still has to take one of them to
    silence a check without deleting it:

      - a statement after an unconditional `return` / `raise` / `break` /
        `continue` in the same block;
      - an `if` or `while` whose condition a constant decides;
      - a marker comment a sweep left behind.

    `while True:` is not one of them. It is the idiom for a loop with its exit
    inside, and the tree uses it correctly in three places.
    """
    found: list[str] = []
    tree = ast.parse(text, rel)
    for node in ast.walk(tree):
        block = getattr(node, "body", None)
        if isinstance(block, list):
            for i, stmt in enumerate(block[:-1]):
                if isinstance(stmt, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
                    found.append(f"{rel}:{block[i + 1].lineno}: unreachable - the block already "
                                 f"{type(stmt).__name__.lower()}s at line {stmt.lineno}")
                    break
        if isinstance(node, ast.If):
            why = _forced(node.test)
            if why:
                found.append(f"{rel}:{node.lineno}: {why}")
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) \
                and not node.test.value:
            found.append(f"{rel}:{node.lineno}: `while {node.test.value!r}` never runs")
    for n, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        for marker in MARKERS:
            if marker in low:
                found.append(f"{rel}:{n}: a sweep marker was left behind: {line.strip()[:70]}")
    return found


def _body_after_docstring(fn) -> list[ast.stmt]:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return body


EMPTY_CONTAINERS = ("tuple", "list", "dict", "set", "frozenset")


def _is_flat_constant(node) -> bool:
    """A value nothing computes: None, a literal, an empty container, or an
    empty container spelled as a call.

    The call spelling is not a detail. One of the clauses this file reads states
    its mutation as "return an empty frozenset from `saturated_kinds`", and
    `frozenset()` is an `ast.Call` - so a reader that recognised only literals
    let the mutation named in those exact words walk past it, while reporting
    that it had checked.

    A `tuple(...)` with arguments, or a `()` built from a comprehension, is not
    a constant: something computed it.
    """
    if node is None:
        return True
    if isinstance(node, ast.Call):
        return (isinstance(node.func, ast.Name) and node.func.id in EMPTY_CONTAINERS
                and not node.args and not node.keywords)
    if not isinstance(node, (ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.Set)):
        return False
    return not any(isinstance(inner, (ast.Name, ast.Call, ast.Attribute, ast.comprehension))
                   for inner in ast.walk(node))


def emptied_guards(rel: str, text: str, wanted: set[str]) -> list[str]:
    """LA3's detector: a function a law NAMES whose whole body is one
    unconditional return of a constant.

    This is the mutant LA2 cannot see. `def synthesis_blockers(...): return ()`
    has no unreachable line and no constant condition - it is valid, tidy code
    that answers "nothing is blocking" to every question anyone asks it.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(text, rel)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in wanted:
            continue
        body = _body_after_docstring(node)
        if len(body) == 1 and isinstance(body[0], ast.Return) and _is_flat_constant(body[0].value):
            rendered = ast.unparse(body[0]) if hasattr(ast, "unparse") else "return <constant>"
            found.append(f"{rel}:{node.lineno}: `{node.name}` answers every question with "
                         f"`{rendered}`; a law names it as a guard")
    return found


# ===========================================================================
# LA0 - the scanner still sees the corpus
# ===========================================================================

def test_the_scanner_still_reads_the_named_mutations_out_of_the_law_files():
    """Everything below is derived, so everything below is worth exactly what
    the derivation is worth. A regex that quietly stopped matching would leave
    four laws asserting nothing at all, in the most convincing way available: by
    passing.

    So the corpus is checked first - clauses exist, across several law files,
    and both directions of pin are represented - and every number here is a
    floor of one or two rather than a count of today's tree, because the law
    files are not this file's to freeze.
    """
    found = clauses()
    assert found, ("no named mutation was found in any law file; the clause pattern no longer "
                   "matches how the laws are written, and LA1-LA3 are pinning nothing")
    files = {c.law_file for c in found}
    assert len(files) >= 3, f"only {sorted(files)} name a mutation; the scan has narrowed"

    pins = derived_pins()
    assert pins, "no clause quotes any code; LA1 is pinning nothing"
    directions = {p.direction for p in pins}
    assert directions == {"PRESENT", "ABSENT"}, (
        f"only {sorted(directions)} pins were derived; a direction that stops being derived is a "
        f"half of LA1 that stops being asserted")

    guards = named_guards()
    assert guards, "no clause names a production function; LA3 is pinning nothing"


# ===========================================================================
# LA1 - no named mutation's own code is standing in production source
# ===========================================================================

def test_no_named_mutation_is_standing_in_production_source():
    """LA1. For every mutation a law file states in its own words: if it quotes
    the mutant, the mutant is not in `app/engine`; if it quotes what it removes,
    that is still there.

    This is the check the regime was missing. The protocol says restore the
    original bytes; nothing read the bytes afterwards from outside the agent
    that wrote them, and a mutation is chosen precisely so that no test fails
    while it stands.

    A PRESENT pin failing has two readings and the message gives both: the
    mutation is applied, or the clause is stale and names code that has since
    been rewritten. Both need a person - and a clause naming code that no longer
    exists is a law nobody can be failed by, which is the same defect one
    indirection away.
    """
    standing: list[str] = []
    for pin in derived_pins():
        where = pin.standing_in(SOURCES)
        if pin.direction == "ABSENT" and where:
            standing.append(
                f"{pin.clause.where}: the mutant `{pin.fragment}` is STANDING in {where[0]}"
                + (f" (and {len(where) - 1} more)" if len(where) > 1 else ""))
        elif pin.direction == "PRESENT" and not where:
            standing.append(
                f"{pin.clause.where}: `{pin.fragment}` is what this mutation REMOVES and it is "
                f"gone from app/engine - either the mutation is applied, or the clause names code "
                f"that no longer exists")
    assert standing == [], (
        "a named mutation is standing in the tree:\n  " + "\n  ".join(standing))


# ===========================================================================
# LA2 - no check has been made inert
# ===========================================================================

def test_no_check_in_production_source_has_been_made_inert():
    """LA2. Nothing in `app/engine` is unreachable, decided by a constant, or
    carrying a sweep's marker comment.

    The mutation that shipped was of this class: a guard dead-coded in place, so
    the function still existed, still had its docstring, still appeared in every
    call graph, and answered nothing. No behavioural law saw it, because the
    mutation had been chosen for exactly that property.

    Stated over the whole tree rather than over a list of guards, so it holds
    for the mutations nobody has thought of yet: to silence a check without
    deleting it you have to leave one of these shapes behind.
    """
    found: list[str] = []
    for rel, text in sorted(SOURCES.items()):
        found.extend(inert_code(rel, text))
    assert found == [], (
        "production source carries code that cannot affect the outcome:\n  " + "\n  ".join(found))


# ===========================================================================
# LA3 - no named guard has been emptied to a constant
# ===========================================================================

def test_no_guard_a_law_names_has_been_emptied_to_a_constant():
    """LA3. Every production function a mutation clause names still computes
    its answer.

    `synthesis_blockers returns () always`, `return an empty frozenset from
    saturated_kinds`, `return {} from _field_rules`, `outstanding_inputs
    returns []` - four clauses in three law files, all the same mutant, and all
    of them valid code with nothing unreachable in it. LA2 is blind to them by
    construction. The list of functions is read off the clauses, so a guard
    named by a law written next week is covered without anyone adding it here.
    """
    wanted = set(named_guards())
    found: list[str] = []
    for rel, text in sorted(SOURCES.items()):
        found.extend(emptied_guards(rel, text, wanted))
    assert found == [], (
        "a guard a law names answers every question with a constant:\n  " + "\n  ".join(found))


# ===========================================================================
# LA4 - the bound the analysis laws measure with, at its declaration
# ===========================================================================

def test_the_ceiling_the_analysis_laws_read_is_not_standing_raised():
    """LA4. `MAX_ENTITIES_PER_ANALYSIS_KIND` is read by I9, by
    `saturated_kinds`, by S1 in test_engine_structural_laws and by law D in
    test_engine_analysis_quality. Raising it is a mutation both of those laws
    NAME - and, until the pins beside them landed, a mutation both of them were
    satisfied by, because each measured the engine with the value the mutation
    moved.

    Here it is read at its declaration instead, where the two questions can be
    asked separately: is the value inside what the rest of the table defends,
    and is it still DERIVED from the table rather than written as a number. The
    second is what a source scan adds - a literal `= 100_000` sitting where the
    product used to be passes every value check the moment the three factors are
    read from it.
    """
    factors = ("MAX_ANALYSIS_ROUNDS", "MAX_SPECIALISTS_PER_ROUND", "MAX_FANOUT")
    default = 1
    for name in factors:
        default *= int(BOUNDS[name])
    declared = int(BOUNDS["MAX_ENTITIES_PER_ANALYSIS_KIND"])
    assert declared <= default, (
        f"the declared ceiling is {declared}, above the {default} that "
        f"{' x '.join(factors)} can defend")

    # And the FACTORS are not free either, which a sweep had to find: with the
    # ceiling pinned to the product, `MAX_FANOUT: 6 -> 250` raised the product
    # from 144 to 6000 and every law that measures with it passed, because the
    # goalposts and the measuring stick had simply moved together one level
    # down. So the product carries an anchor, and the anchor is a literal -
    # deliberately, and it is the ONLY literal in this regime's bounds.
    #
    # It has to be immovable or it is not an anchor: any expression written
    # here would be read off the same table the mutation edits. It is
    # one-directional, so it forbids nothing an operator would want - argue
    # any factor DOWN, in any combination, and this passes. Raising the product
    # is a change to what the engine means by "an analysis", and it belongs in
    # a diff a reviewer reads rather than in a table entry nobody re-derives.
    ARGUED_CEILING = 144
    assert default <= ARGUED_CEILING, (
        f"{' x '.join(factors)} now comes to {default}, above the {ARGUED_CEILING} this regime "
        f"measures analyses against. Every law that reads the derived default just moved with it: "
        f"raising a factor is how the ceiling gets raised once the ceiling itself is pinned to the "
        f"factors. Argue it down freely; raising it is a decision, and it is made on this line")

    types_rel = "app/engine/types.py"
    source = SOURCES[types_rel]
    assert 'BOUNDS["MAX_ENTITIES_PER_ANALYSIS_KIND"] = (' in source, (
        f"{types_rel} no longer assigns the ceiling as a derived expression")
    declaration = source.split('BOUNDS["MAX_ENTITIES_PER_ANALYSIS_KIND"] = (', 1)[1].split(")", 1)[0]
    for name in factors:
        assert name in declaration, (
            f"the ceiling in {types_rel} is no longer derived from {name}; it reads "
            f"{declaration.strip()!r}, which is a number wearing the name of a bound")


# ===========================================================================
# THE CONTROL. Every detector above, run on a mutant that was never written.
# ===========================================================================

MUTANTS = (
    ("an early return dead-codes the guard",
     "def synthesis_blockers(view):\n"
     "    '''the real one computes three terms.'''\n"
     "    return ()\n"
     "    left = runnable_selections(view)\n"
     "    return tuple(left)\n",
     "unreachable"),
    ("the guard is kept and its condition decided",
     "def synthesis_blockers(view):\n"
     "    if False:\n"
     "        return ('blocked',)\n"
     "    return ()\n",
     "the constant"),
    ("the condition is widened until nothing can fail it",
     "def synthesis_blockers(view):\n"
     "    if not view.runnable() or True:\n"
     "        return ()\n"
     "    return ('blocked',)\n",
     "decides the condition"),
    ("a sweep left its marker behind",
     "def synthesis_blockers(view):\n"
     "    # MUTATION: silence the second term\n"
     "    return tuple(view.waiting())\n",
     "marker"),
)


@pytest.mark.parametrize("label,mutant,expected", MUTANTS, ids=[m[0][:40] for m in MUTANTS])
def test_the_inert_code_detector_fires_on_a_mutant(label, mutant, expected):
    """CONTROL for LA2. A detector that finds nothing on a clean tree and
    nothing on a mutant is not a guard, it is a green light with a docstring -
    and that is the failure this whole file is about, one level up.

    The mutants are strings. Nothing is written to `app/engine`, so there is
    nothing to restore and nothing that can be left behind by this file itself.
    """
    found = inert_code("app/engine/probe.py", mutant)
    assert found, f"the detector saw nothing in a mutant that {label}"
    assert any(expected in line for line in found), f"{found} does not name {expected!r}"


def test_the_inert_code_detector_passes_the_shapes_it_must_not_flag():
    """The other half of the control. A detector that flagged `while True:` or
    an `or ()` default would be turned off within a week, and a law nobody can
    keep on is a law nobody has."""
    innocent = (
        "def read(text):\n"
        "    out = []\n"
        "    start = 0\n"
        "    while True:\n"
        "        at = text.find('x', start)\n"
        "        if at < 0:\n"
        "            break\n"
        "        out.append(at)\n"
        "        start = at + 1\n"
        "    return tuple(out)\n"
        "\n"
        "def ids(row):\n"
        "    if row.derived_from or ():\n"
        "        return tuple(row.derived_from or ())\n"
        "    return ()\n")
    assert inert_code("app/engine/probe.py", innocent) == []


def test_the_emptied_guard_detector_fires_on_a_mutant_and_not_on_the_real_thing():
    """CONTROL for LA3, taken from the real `synthesis_blockers`: the mutant is
    the module's own source with that function's body replaced, in memory. If
    the detector cannot tell the two apart it is asserting nothing about the
    tree it just passed."""
    rel = "app/engine/partner/state.py"
    real = SOURCES[rel]
    assert emptied_guards(rel, real, {"synthesis_blockers"}) == [], \
        "the real guard already answers with a constant"

    mutant = real + (
        "\n\ndef synthesis_blockers(view, *, rounds_used=0, bounds=None, methods=None):\n"
        '    """SYNTHESIS is reachable when nothing is left to run."""\n'
        "    return ()\n")
    found = emptied_guards(rel, mutant, {"synthesis_blockers"})
    assert found and "synthesis_blockers" in found[0], (
        "the detector cannot see a guard emptied to `return ()`, which is the mutation four law "
        "files name and the shape that shipped")

    # ... and it does not fire on a function that computes an empty answer.
    computed = (
        "def synthesis_blockers(view):\n"
        "    return tuple(sorted(view.waiting()))\n")
    assert emptied_guards(rel, computed, {"synthesis_blockers"}) == []


@pytest.mark.parametrize("spelling", ["()", "frozenset()", "tuple()", "[]", "{}", "None", "set()"])
def test_the_emptied_guard_detector_reads_every_spelling_of_nothing(spelling):
    """CONTROL, and a defect this file shipped with for one sweep. The clauses
    say "returns () always", "an empty frozenset", "return {}" - three spellings
    of one mutant, and a detector that recognised only literals passed the
    frozenset one while reporting that it had checked.

    The negative half is in the same test: an empty answer somebody COMPUTED is
    not this mutation, and a detector that could not tell them apart would fail
    the tree honestly and be removed.
    """
    mutant = f"def saturated_kinds(view):\n    return {spelling}\n"
    assert emptied_guards("app/engine/probe.py", mutant, {"saturated_kinds"}), \
        f"`return {spelling}` is a guard that answers nothing, and was not seen"

    container = spelling[:-2] if spelling.endswith("()") and len(spelling) > 2 else "frozenset"
    computed = f"def saturated_kinds(view):\n    return {container}(k for k in view.full())\n"
    assert emptied_guards("app/engine/probe.py", computed, {"saturated_kinds"}) == [], \
        "an answer the function computed is not an emptied guard"


def test_a_present_pin_is_not_satisfied_by_the_definition_of_what_was_removed():
    """CONTROL, and the second defect a sweep found here. `drop
    `_decision_owned(spec)` from the loop's free-run condition` is a PRESENT
    pin: the call must still be there. Deleting every call left the DEFINITION
    standing - `def _decision_owned(spec) -> bool:` - and the pin read those
    characters and reported the code present.

    A pin satisfied by the declaration of the thing it protects is a pin that
    passes whatever the tree does.
    """
    call = "def _decision_owned(spec) -> bool:\n    return True\n\n\nUSE = _decision_owned(spec)\n"
    pin = Pin(Clause("probe.py", 1, "drop `_decision_owned(spec)`"), "PRESENT",
              "_decision_owned(spec)", ("_decision_owned(spec)",))
    assert pin.standing_in({"app/engine/probe.py": call}), "the call is there and must read present"

    definition_only = "def _decision_owned(spec) -> bool:\n    return True\n"
    assert pin.standing_in({"app/engine/probe.py": definition_only}) == [], (
        "every call was removed and the pin still reads the code as present, off its own "
        "definition line")


def test_the_derived_pins_detect_their_own_mutants():
    """CONTROL for LA1. Every derived pin is exercised against a mutant built
    from its own fragment: an ABSENT pin must fire when its mutant is inserted,
    a PRESENT pin must fire when the code it protects is removed.

    Without this, a pin whose fragment can never be found - a typo, an ellipsis
    that swallowed the whole quotation, a rename - reads as a clean pass
    forever. That is the same defect as a law reading the bound its mutation
    moves: the measuring instrument agreeing with itself.
    """
    dead: list[str] = []
    for pin in derived_pins():
        if pin.direction == "ABSENT":
            planted = {"app/engine/probe.py": "\n".join(pin.segments)}
            if not pin.standing_in(planted):
                dead.append(f"{pin.clause.where}: ABSENT pin `{pin.fragment}` does not match even "
                            f"a file that is nothing but the fragment")
        else:
            stripped = {rel: text for rel, text in SOURCES.items()}
            for rel in list(stripped):
                for seg in pin.segments:
                    stripped[rel] = stripped[rel].replace(seg, "")
            if pin.standing_in(stripped):
                dead.append(f"{pin.clause.where}: PRESENT pin `{pin.fragment}` still reports "
                            f"itself present after every occurrence was removed")
    assert dead == [], "pins that cannot detect their own mutation:\n  " + "\n  ".join(dead)
