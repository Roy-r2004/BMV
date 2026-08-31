"""The mutation manifest and the driver's contract (design 19; C25).

Every law in this engine is supposed to have a mutation that kills a test. The
list of those mutations lives in `work_breakdown.json`, and the thing that
applies them lives in `scratchpad/mutate_engine.py`. Nothing so far makes the
two agree: a clause could be written in the breakdown and never implemented, a
mutation could be implemented against a test that does not exist, and either
way the regime would still report green. This file is what makes the manifest
answerable.

Four groups of laws:

  M1  coverage      -- every clause the breakdown names has an entry, and no
                       entry invents a clause the breakdown does not name.
  M2  pinning       -- every entry names at least one pinning test, and that
                       test exists. This is the component's own named mutation:
                       an entry without a test id must fail this file.
  M3  applicability -- every declared anchor still matches its source exactly
                       once, and every generated family still reaches its
                       floor. A mutation that cannot be applied proves nothing.
  M4  the contract  -- in-memory restore (never `git checkout`), one sweep at a
                       time, no sweep while a generation is in flight, and r30
                       byte-identical after a sweep that deliberately touched
                       it.

The r30 half of C25 -- "the suite count and results are unchanged from
f9fc846" -- is proven structurally rather than by re-counting: the top-level
suite is byte-frozen by `tests/engine/r30_manifest.json`, and this file checks
that the freeze actually covers all of it (`test_the_r30_suite_...`). Identical
bytes cannot produce a different count.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sqlite3
import sys

import pytest

SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DRIVER_PATH = os.path.join(SERVICE_ROOT, "scratchpad", "mutate_engine.py")
R30_MANIFEST = os.path.join(SERVICE_ROOT, "tests", "engine", "r30_manifest.json")


def _load_driver():
    """Imported by path, not by package: the driver lives in `scratchpad/`
    because it is a tool and not part of the service, and a tool nobody can
    import is a tool nobody can test."""
    spec = importlib.util.spec_from_file_location("engine_mutate_driver", DRIVER_PATH)
    assert spec and spec.loader, f"the mutation driver is missing at {DRIVER_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


driver = _load_driver()


# ---------------------------------------------------------------------------
# M1 - coverage
# ---------------------------------------------------------------------------

def test_the_manifest_covers_every_clause_the_breakdown_names():
    """Every (component, clause) pair in the breakdown has exactly one entry,
    and no entry answers to a clause nobody wrote down. Both directions
    matter: the first catches a law nobody implemented a mutation for, the
    second catches a mutation nobody agreed to."""
    declared = [(c, t) for c, t in driver.BREAKDOWN_CLAUSES]
    covered = [(m.component, m.clause) for m in driver.MUTATIONS]
    assert sorted(set(declared) - set(covered)) == [], "clauses with no mutation entry"
    assert sorted(set(covered) - set(declared)) == [], "entries for clauses the breakdown does not name"
    assert len(covered) == len(set(covered)), "two entries answer to the same clause"
    assert len(declared) == len(covered)


def test_mutation_ids_are_unique():
    ids = [m.mid for m in driver.MUTATIONS]
    assert len(ids) == len(set(ids)), "two mutations share an id; the sweep report would be ambiguous"


def test_the_local_clause_list_still_matches_the_breakdown_when_it_is_reachable():
    """`BREAKDOWN_CLAUSES` is a verbatim copy, because the breakdown is a
    planning artefact outside the repository and a law that evaporates when a
    file is missing is not a law. When the source IS reachable
    (ENGINE_WORK_BREAKDOWN), the copy is checked against it, so the copy can
    never quietly drift into being the only opinion."""
    source = driver.BREAKDOWN_SOURCE
    if not source or not os.path.exists(source):
        pytest.skip("work_breakdown.json is not reachable from here")
    with open(source, encoding="utf-8") as fh:
        breakdown = json.load(fh)
    fresh = []
    for entry in breakdown:
        found = re.search(r"Mutations(?: that must be caught)?:\s*(.*)$", entry.get("tests", ""), re.S)
        if not found:
            continue
        for clause in found.group(1).strip().rstrip(".").split(";"):
            if clause.strip():
                fresh.append((entry["id"], clause.strip()))
    assert fresh == list(driver.BREAKDOWN_CLAUSES)


# ---------------------------------------------------------------------------
# M2 - pinning. The component's own named mutation lands here.
# ---------------------------------------------------------------------------

def test_every_mutation_entry_names_a_pinning_test():
    """THE law of this file. A mutation with no pinning test can never fail
    anybody: it is applied, nothing runs, and the sweep reports a green that
    means nothing.

    Named mutation: blank a pin tuple in the driver (`P_TYPES = ()`). Every
    entry that shares it loses its pins and this test names them."""
    unpinned = [m.mid for m in driver.MUTATIONS if not m.pins]
    assert unpinned == [], f"mutations with no pinning test: {unpinned}"


def test_every_pinning_test_id_resolves_to_a_test_that_exists():
    """A pin is a pytest node id: a file, or a file and a test function. The
    file must exist and, when a function is named, it must be defined there.
    A pin naming a test nobody wrote is the same failure as no pin at all,
    one indirection later."""
    import ast

    missing = []
    for m in driver.MUTATIONS:
        if m.component in driver.NOT_YET_BUILT:
            continue
        for pin in m.pins:
            rel, _, func = pin.partition("::")
            path = os.path.join(SERVICE_ROOT, rel.replace("/", os.sep))
            if not os.path.isfile(path):
                missing.append(f"{m.mid}: {pin} (no such file)")
                continue
            if not func:
                continue
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), path)
            names = {n.name for n in ast.walk(tree)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            if func not in names:
                missing.append(f"{m.mid}: {pin} (no such test)")
    assert missing == [], "pins that resolve to nothing:\n  " + "\n  ".join(missing)


def test_pending_components_really_are_missing():
    """`NOT_YET_BUILT` is the one escape from the pinning law, so it is not
    allowed to become a parking space: a component listed there whose test
    file has since landed must be taken off the list, and this fails until it
    is."""
    for component in driver.NOT_YET_BUILT:
        pins = [p for m in driver.MUTATIONS if m.component == component for p in m.pins]
        assert pins, f"{component} is pending but names no pin to become true"
        landed = [p for p in pins
                  if os.path.isfile(os.path.join(SERVICE_ROOT, p.split("::")[0].replace("/", os.sep)))]
        assert landed == [], f"{component} is marked pending but its tests exist: {landed}"


def test_check_reports_an_entry_that_names_no_pinning_test(monkeypatch):
    """The negative control for the law above: the driver's own `--check` must
    say so too, so a sweep run by hand refuses for the same reason the suite
    goes red."""
    orphan = driver.Mutation(mid="X.m1", component="C0-contracts", clause="fabricated",
                             pins=(), variants=())
    monkeypatch.setattr(driver, "MUTATIONS", (orphan,))
    problems = driver.check()
    assert any("names no pinning test" in p for p in problems), problems


def test_check_is_clean_on_the_manifest_as_it_stands():
    """And the positive fixture: the driver's own report agrees with this
    file. Two mechanisms, one verdict."""
    assert driver.check() == []


# ---------------------------------------------------------------------------
# M3 - applicability. A mutation that cannot be applied proves nothing.
# ---------------------------------------------------------------------------

def test_every_declared_anchor_matches_its_source_exactly_once():
    """The difference between a mutation regime and a decorative list of
    intentions. An anchor that matches nothing was silently retired by a
    refactor; an anchor that matches twice mutates a site nobody reasoned
    about. Either way the clause it answers to is no longer proven, and the
    fix is to re-anchor it -- not to delete the entry."""
    problems = []
    for m in driver.MUTATIONS:
        if m.component in driver.NOT_YET_BUILT:
            continue
        for variant in driver.variants_of(m):
            for edit in variant.edits:
                path = os.path.join(SERVICE_ROOT, edit.path.replace("/", os.sep))
                if not os.path.isfile(path):
                    problems.append(f"{m.mid} [{variant.label}]: {edit.path} does not exist")
                    continue
                with open(path, encoding="utf-8", newline="") as fh:
                    text = fh.read()
                count = text.count(edit.old)
                if count != 1:
                    problems.append(
                        f"{m.mid} [{variant.label}]: anchor occurs {count}x in {edit.path}: "
                        f"{edit.old.strip()[:70]!r}")
    assert problems == [], "unapplicable mutations:\n  " + "\n  ".join(problems)


def test_every_entry_declares_a_way_to_break_its_law():
    """Edits or a family; a pending component may have neither, and nothing
    else may."""
    for m in driver.MUTATIONS:
        if m.component in driver.NOT_YET_BUILT:
            continue
        assert m.variants or m.family, f"{m.mid} declares no edits and no family"


def test_generated_families_still_reach_their_floor():
    """The two families are enumerated from the source at sweep time, so their
    size is a property of the code and never a number frozen here. What is
    fixed is a FLOOR: fewer registered laws than the breakdown named means
    laws were removed, not that the driver shrank."""
    for m in driver.MUTATIONS:
        if not m.family:
            continue
        variants = driver.variants_of(m)
        assert len(variants) >= m.min_variants, (
            f"{m.mid}: family {m.family} produced {len(variants)} variants, "
            f"below the floor of {m.min_variants}")
        labels = [v.label for v in variants]
        assert len(labels) == len(set(labels)), f"{m.mid}: two family variants share a label"


def test_the_registry_family_finds_every_invariant():
    """I1-I8 are enforced at more sites than there are invariants, and each
    site is its own law. The family must reach every invariant id, not just
    eight sites of one."""
    ids = {v.label.split()[2] for v in driver.family_registry_invariants()}
    assert {"I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8"} <= ids, ids


# ---------------------------------------------------------------------------
# M4 - the owner's contract for the driver itself
# ---------------------------------------------------------------------------

def test_the_driver_never_restores_with_git():
    """"From an in-memory backup, never `git checkout`" is an owner rule
    written in blood: the sweep runs in a live checkout beside uncommitted
    work, and `git checkout` would restore the committed bytes over it. The
    word may appear in prose explaining the rule; it may not appear in a
    string the code can execute."""
    import ast

    with open(DRIVER_PATH, encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source, DRIVER_PATH)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    offenders = [n.value for n in ast.walk(tree)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)
                 and id(n) not in docstrings and re.search(r"\bgit\b", n.value, re.IGNORECASE)]
    assert offenders == [], f"the driver holds an executable git reference: {offenders[:3]}"


@pytest.fixture()
def probe():
    """A throwaway file inside the repository for the driver to mutate. It
    lives under `scratchpad/`, which no scanner and no manifest covers, and it
    is removed however the test ends."""
    rel = "scratchpad/_mutation_probe.py"
    path = os.path.join(SERVICE_ROOT, rel.replace("/", os.sep))
    original = b"LAW = 1\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(original)
    try:
        yield rel, path, original
    finally:
        if os.path.exists(path):
            os.remove(path)


def _probe_mutation(rel, pins=("tests/engine/test_engine_mutation_manifest.py",)):
    return driver.Mutation(
        mid="probe.m1", component="C25-mutation-driver-and-r30-regression",
        clause="probe", pins=pins,
        variants=(driver.Variant("LAW becomes 2", (driver.Edit(rel, "LAW = 1\n", "LAW = 2\n"),)),))


def test_the_driver_restores_the_original_bytes_after_a_run(probe):
    """The mutant is really written (the runner sees it) and the original
    bytes really come back."""
    rel, path, original = probe
    seen = {}

    def runner(pins):
        with open(path, "rb") as fh:
            seen["during"] = fh.read()
        return 1, "1 failed"

    mutation = _probe_mutation(rel)
    outcome = driver.run_variant(mutation, mutation.variants[0], runner=runner)
    assert outcome.verdict == "killed"
    assert seen["during"] == b"LAW = 2\n", "the mutant never reached disk"
    with open(path, "rb") as fh:
        assert fh.read() == original


def test_the_driver_restores_the_original_bytes_when_the_run_raises(probe):
    """The restore is in a `finally`, so a crashing runner - or a bug in the
    driver - never leaves a mutant behind. Without this the next sweep backs
    up the mutant and 'restores' it forever."""
    rel, path, original = probe

    def runner(pins):
        raise RuntimeError("pytest fell over")

    mutation = _probe_mutation(rel)
    with pytest.raises(RuntimeError):
        driver.run_variant(mutation, mutation.variants[0], runner=runner)
    with open(path, "rb") as fh:
        assert fh.read() == original


def test_a_surviving_mutant_is_a_failing_build(probe, monkeypatch):
    """The sentence "a survivor is a failing build" as an exit code."""
    rel, _, _ = probe
    monkeypatch.setattr(driver, "MUTATIONS", (_probe_mutation(rel),))
    code, outcomes = driver.sweep(runner=lambda pins: (0, "all passed"),
                                  lock=False, check_in_flight=False)
    assert [o.verdict for o in outcomes] == ["survived"]
    assert code == 1

    code, outcomes = driver.sweep(runner=lambda pins: (1, "1 failed"),
                                  lock=False, check_in_flight=False)
    assert [o.verdict for o in outcomes] == ["killed"]
    assert code == 0


def test_an_anchor_that_does_not_match_is_never_reported_as_killed(probe, monkeypatch):
    """An unresolved anchor is the quiet failure this regime dies of: the
    mutation is skipped, nothing is written, the pins pass, and the report
    would say green. It is a failing build, and nothing is written to disk."""
    rel, path, original = probe
    mutation = driver.Mutation(
        mid="probe.m2", component="C25-mutation-driver-and-r30-regression", clause="probe",
        pins=("tests/engine/test_engine_mutation_manifest.py",),
        variants=(driver.Variant("gone", (driver.Edit(rel, "LAW = 99\n", "LAW = 2\n"),)),))
    monkeypatch.setattr(driver, "MUTATIONS", (mutation,))
    code, outcomes = driver.sweep(runner=lambda pins: (0, ""), lock=False, check_in_flight=False)
    assert [o.verdict for o in outcomes] == ["unresolved"]
    assert code == 1
    with open(path, "rb") as fh:
        assert fh.read() == original


def test_an_edit_that_changes_nothing_is_unresolved(probe):
    """`old` present and `new` identical is a no-op mutation: the pins pass
    because nothing was broken, and the report would call the law proven."""
    rel, path, original = probe
    mutation = driver.Mutation(
        mid="probe.m3", component="C25-mutation-driver-and-r30-regression", clause="probe",
        pins=("tests/engine/test_engine_mutation_manifest.py",),
        variants=(driver.Variant("no-op", (driver.Edit(rel, "LAW = 1\n", "LAW = 1\n"),)),))
    outcome = driver.run_variant(mutation, mutation.variants[0], runner=lambda pins: (0, ""))
    assert outcome.verdict == "unresolved"
    with open(path, "rb") as fh:
        assert fh.read() == original


def test_one_sweep_at_a_time(tmp_path, monkeypatch):
    """Two sweeps in one working tree: the second would back up the first
    one's mutant. O_EXCL makes the claim and the check one operation, so the
    second refuses rather than racing."""
    monkeypatch.setattr(driver, "LOCK_PATH", str(tmp_path / "sweep.lock"))
    driver.acquire_lock()
    try:
        with pytest.raises(driver.SweepRefused):
            driver.acquire_lock()
    finally:
        driver.release_lock()
    driver.acquire_lock()          # released, so it is claimable again
    driver.release_lock()


def _db_with(tmp_path, table, column, value):
    path = tmp_path / "probe.db"
    con = sqlite3.connect(str(path))
    con.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, {column} INTEGER)")
    con.execute(f"INSERT INTO {table} ({column}) VALUES (?)", (value,))
    con.commit()
    con.close()
    return str(path)


@pytest.mark.parametrize("table,column", [("engagements", "is_working"),
                                          ("requests", "is_generating")])
def test_the_driver_refuses_while_a_generation_is_in_flight(tmp_path, table, column, monkeypatch):
    """The owner's rule: no code edits while a generation is in flight. The
    running process imports these modules from this tree, so a sweep beside
    one corrupts a real client's run. Both engines count - an engagement turn
    and an r30 generation."""
    path = _db_with(tmp_path, table, column, 1)
    assert driver.in_flight(path), "a live row must stop the sweep"
    monkeypatch.setattr(driver, "ENGINE_DB", path)
    # The manifest is emptied first: the refusal must come from the flag, and
    # a driver that had lost the check must not go on to rewrite the whole
    # tree just because a test asked it to.
    monkeypatch.setattr(driver, "MUTATIONS", ())
    with pytest.raises(driver.SweepRefused):
        driver.sweep(runner=lambda pins: (1, ""), lock=False)


@pytest.mark.parametrize("stored", [0, None])
def test_an_idle_or_unset_flag_is_not_a_generation_in_flight(tmp_path, stored):
    """Absent evidence is not evidence of a defect (owner constraint). A row
    written by an older normaliser carries NULL, and reading it truthily would
    lock the driver out of a repository where nothing is running at all."""
    path = _db_with(tmp_path, "engagements", "is_working", stored)
    assert driver.in_flight(path) == []


def test_a_missing_database_is_not_a_generation_in_flight(tmp_path):
    assert driver.in_flight(str(tmp_path / "nothing.db")) == []


def test_a_database_without_the_tables_is_not_a_generation_in_flight(tmp_path):
    """A fresh checkout has a database with r30 tables and no engine tables.
    A missing table means nothing is running there, not that everything is."""
    path = _db_with(tmp_path, "unrelated", "flag", 1)
    assert driver.in_flight(path) == []


# ---------------------------------------------------------------------------
# M4b - r30 stays byte-identical through a sweep that deliberately touches it
# ---------------------------------------------------------------------------

def test_the_frozen_roots_are_recognised_as_frozen():
    for rel in ("app/pipeline/registry.py", "app/prompts/anything.j2", "tools/inspect_pdf.py",
                "tests/conftest.py", "tests/test_integrity_layer.py"):
        assert driver.is_frozen(rel), rel
    for rel in ("app/engine/registry.py", "tests/engine/conftest.py", "scratchpad/mutate_engine.py",
                "main.py"):
        assert not driver.is_frozen(rel), rel


def test_every_frozen_target_is_pinned_to_the_freeze_itself():
    """Two named mutations must touch r30 on purpose ("alter one byte of
    app/pipeline/registry.py"). Each has to be pinned to the frozen-manifest
    test, because that is the test the mutation is meant to kill; pinning it
    only to an engine test would prove the wrong thing."""
    frozen_test = "tests/engine/test_engine_r30_frozen.py"
    for m in driver.MUTATIONS:
        for variant in driver.variants_of(m):
            for edit in variant.edits:
                if driver.is_frozen(edit.path):
                    assert any(p.split("::")[0] == frozen_test for p in m.pins), (
                        f"{m.mid} touches the frozen {edit.path} without pinning {frozen_test}")


def test_the_frozen_guard_passes_on_the_tree_as_it_stands():
    driver.assert_frozen_intact(["app/pipeline/registry.py", "app/engine/registry.py"])


def test_the_frozen_guard_fails_when_a_frozen_file_did_not_come_back(monkeypatch):
    """The second, independent check after restoration. Byte equality with the
    in-memory backup is already asserted; this one compares with the hash
    recorded at f9fc846, because the whole r30 guarantee rests on it and one
    check is one bug away from nothing."""
    monkeypatch.setattr(driver, "sha256_of", lambda rel: "0" * 64)
    with pytest.raises(driver.FrozenTreeViolation):
        driver.assert_frozen_intact(["app/pipeline/registry.py"])


def test_a_frozen_file_the_manifest_never_recorded_is_a_violation(monkeypatch):
    monkeypatch.setattr(driver, "frozen_manifest", lambda: {"files": {}})
    with pytest.raises(driver.FrozenTreeViolation):
        driver.assert_frozen_intact(["app/pipeline/registry.py"])


def test_the_r30_suite_the_driver_must_not_change_is_covered_by_the_freeze():
    """C25's r30 half: "the suite count and results are unchanged from
    f9fc846". Re-counting would only say what the count is today. What makes
    the count unchangeable is that every file of the top-level suite is
    byte-frozen, and that is checked here: a new top-level test file, or one
    dropped from the manifest, breaks this before anybody has to notice a
    number moved."""
    with open(R30_MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)
    on_disk = {f"tests/{name}" for name in os.listdir(os.path.join(SERVICE_ROOT, "tests"))
               if name.endswith(".py")}
    recorded = {p for p in manifest["files"] if p.startswith("tests/")}
    assert on_disk - recorded == set(), "a top-level r30 test file is not frozen"
    assert recorded - on_disk == set(), "the manifest freezes a top-level test file that is gone"
    assert manifest["commit"] == "f9fc846"
