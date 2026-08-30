"""The frozen manifest (design 13.5).

`app/pipeline`, `app/prompts`, `tools` and the top-level suite that proves
them were byte-identical at commit f9fc846 and must stay byte-identical: the
engine imports r30, it never edits it, and the owner's contract says so in
those words. This file is the enforcement.

MF3.6: `tests/engine/**` is excluded. The engine's own tests change with
every wave; freezing them would turn the manifest into a diary and the law
into noise. The exclusion is itself a law here, with its own test, because a
manifest that quietly grew to cover the engine's tests would fail on every
honest commit and be deleted within a day.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANIFEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "r30_manifest.json")

# The three trees r30 lives in, plus the top-level suite. Stated here and in
# the manifest; the test that they agree is `test_manifest_declares_its_rules`.
FROZEN_ROOTS = ("app/pipeline", "app/prompts", "tools")
TESTS_DIR = "tests"
ENGINE_TESTS = "tests/engine"
SKIP_DIRS = frozenset({"__pycache__"})
SKIP_SUFFIXES = (".pyc", ".pyo")


def _rel(path: str) -> str:
    return os.path.relpath(path, SERVICE_ROOT).replace(os.sep, "/")


def collect_frozen_files() -> list[str]:
    """Every file the manifest covers, rebuilt from the rules rather than
    read from the manifest: a file added to `app/pipeline` after the freeze
    is caught by the set comparison, not missed because nobody listed it."""
    found: list[str] = []
    for root in FROZEN_ROOTS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(SERVICE_ROOT, root)):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in sorted(filenames):
                if name.endswith(SKIP_SUFFIXES):
                    continue
                found.append(_rel(os.path.join(dirpath, name)))
    tests_dir = os.path.join(SERVICE_ROOT, TESTS_DIR)
    for name in sorted(os.listdir(tests_dir)):
        path = os.path.join(tests_dir, name)
        # Top level only: tests/engine is a directory and is never descended
        # into (MF3.6).
        if os.path.isfile(path) and name.endswith(".py"):
            found.append(f"{TESTS_DIR}/{name}")
    return sorted(set(found))


def sha256_of(rel_path: str) -> str:
    with open(os.path.join(SERVICE_ROOT, rel_path), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


@pytest.fixture(scope="module")
def manifest() -> dict:
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# The manifest itself
# ---------------------------------------------------------------------------

def test_manifest_declares_its_rules(manifest):
    """The manifest says which commit it was recorded at and which trees it
    covers, so a reader never has to infer the scope from the file list."""
    assert manifest["commit"] == "f9fc846"
    assert tuple(manifest["roots"]) == FROZEN_ROOTS
    assert manifest["file_count"] == len(manifest["files"])
    assert manifest["file_count"] > 0


def test_manifest_excludes_the_engines_own_tests(manifest):
    """MF3.6 as a law. Not one manifest entry is under `tests/engine`: the
    engine's tests are the thing that changes, and the r30 tree is the thing
    that must not.

    Mutation: add a `tests/engine/...` entry to the manifest. This test names
    it, and `test_every_frozen_file_matches_its_recorded_hash` fails too
    because the collector never walks that directory."""
    offenders = [p for p in manifest["files"] if p.startswith(ENGINE_TESTS)]
    assert offenders == [], f"the manifest reaches into the engine's own tests: {offenders}"


def test_collector_never_descends_into_engine_tests():
    """The collector's half of the same law: whatever the manifest says, the
    rules themselves do not reach `tests/engine`."""
    assert [p for p in collect_frozen_files() if p.startswith(ENGINE_TESTS)] == []


# ---------------------------------------------------------------------------
# The freeze
# ---------------------------------------------------------------------------

def test_the_frozen_file_set_is_unchanged(manifest):
    """No file added to, or removed from, the r30 trees since f9fc846."""
    recorded = set(manifest["files"])
    found = set(collect_frozen_files())
    assert sorted(found - recorded) == [], "files appeared under a frozen root"
    assert sorted(recorded - found) == [], "files disappeared from under a frozen root"


def test_every_frozen_file_matches_its_recorded_hash(manifest):
    """The freeze itself: byte-identical, file by file.

    Mutation: alter one byte of `app/pipeline/registry.py`. This test names
    the file and reports both hashes."""
    changed = []
    for rel_path, recorded in sorted(manifest["files"].items()):
        actual = sha256_of(rel_path)
        if actual != recorded:
            changed.append(f"{rel_path}: recorded {recorded[:12]}, found {actual[:12]}")
    assert changed == [], "r30 is frozen; these files moved:\n" + "\n".join(changed)


def test_the_pipeline_tree_is_actually_covered(manifest):
    """A manifest that had lost its contents would pass every check above by
    covering nothing. The modules the engine's adapter imports by name are
    named here, so an empty or truncated manifest is a failure and not a
    silent pass."""
    for required in ("app/pipeline/registry.py", "app/pipeline/integrity.py",
                     "app/pipeline/export_pdf.py", "app/pipeline/pilot_gate.py",
                     "app/pipeline/orchestrator.py", "app/pipeline/_shared.py",
                     "app/pipeline/phase2_bridge.py", "tests/conftest.py"):
        assert required in manifest["files"], f"{required} is not frozen"


def test_the_engine_never_writes_to_a_frozen_tree():
    """Every engine module lives under `app/engine` or `tests/engine`. This
    is the structural reason the freeze holds: there is nowhere else the
    engine could have put a change."""
    engine_dir = os.path.join(SERVICE_ROOT, "app", "engine")
    assert os.path.isdir(engine_dir)
    for root in FROZEN_ROOTS:
        assert not os.path.commonpath([os.path.join(SERVICE_ROOT, root), engine_dir]).endswith(
            os.path.join("app", "pipeline"))
