"""Roadmap DoD 8 — no module outside a named allowlist may write pages.

*No module outside a named allowlist may write `src/pages/**.tsx` or
`src/render/**`, enforced at runtime inside `workspace.write_file`, allowlist
pinned by test.*

This is a hard guarantee rather than a measurement, which is why it was the
highest-value offline item: Phase 2's thesis is that one writer owns pages, and
26 modules can write them today. The list can now only grow by decision.
"""
from __future__ import annotations


import types
from pathlib import Path

import pytest

from app.application.preview_app import workspace as ws
from app.application.preview_app.workspace import (
    UnauthorizedPageWrite,
    _GUARDED_WRITE_RE,
    _PAGE_WRITERS,
    write_file,
)


def _write_from_module(module_name: str, workspace: Path, rel_path: str) -> str:
    """Call `write_file` from a synthetic module, so the guard sees that name.

    The guard identifies its caller by walking frames to the first module that
    is not `workspace` itself, so a test cannot exercise a foreign origin by
    calling directly — it would see `tests.…`, which is allowed.
    """
    module = types.ModuleType(module_name)
    code = compile(
        "def go(write_file, workspace, rel_path):\n"
        "    return write_file(workspace, rel_path, 'export default function P() {}\\n')\n",
        f"<{module_name}>",
        "exec",
    )
    # Deliberately NOT registered in `sys.modules`. The guard reads
    # `frame.f_globals["__name__"]`, which `exec` into the module dict already
    # sets — and registering shadows the real module, so writing as
    # `…preview_app.protected_paths` broke `write_file`'s own import of it.
    exec(code, module.__dict__)  # noqa: S102 - the point is a controlled __name__
    return module.go(write_file, workspace, rel_path)


GUARDED = [
    "src/pages/HomePage.tsx",
    "src/pages/owner/DashboardPage.tsx",
    "src/pages/HomePage.jsx",
    "src/render/HomePage.tsx",
    "src/render/spec/home.json",
]
UNGUARDED = [
    "src/data/mock.ts",
    "src/App.tsx",
    "src/components/Nav.tsx",
    "src/ui/public/PublicShell.tsx",
    "src/pages/README.md",  # not a component
]


@pytest.mark.parametrize("rel_path", GUARDED)
def test_an_unlisted_module_cannot_write_a_guarded_path(
    tmp_path: Path, rel_path: str
) -> None:
    with pytest.raises(UnauthorizedPageWrite) as excinfo:
        _write_from_module("app.some.new.writer", tmp_path, rel_path)

    assert "app.some.new.writer" in str(excinfo.value)
    assert rel_path in str(excinfo.value)
    assert not (tmp_path / rel_path).exists(), "the write happened anyway"


@pytest.mark.parametrize("rel_path", UNGUARDED)
def test_an_unlisted_module_may_still_write_everything_else(
    tmp_path: Path, rel_path: str
) -> None:
    """The guard covers pages and render artifacts, not the workspace."""
    written = _write_from_module("app.some.new.writer", tmp_path, rel_path)
    assert (tmp_path / written).is_file()


@pytest.mark.parametrize("module_name", sorted(_PAGE_WRITERS))
def test_every_allowlisted_module_can_write_a_page(
    tmp_path: Path, module_name: str
) -> None:
    """Every name on the list works, so a typo cannot sit there unnoticed.

    A misspelled entry is silently useless: the module it was meant to cover
    keeps raising and the list keeps looking complete.
    """
    written = _write_from_module(module_name, tmp_path / module_name, "src/pages/HomePage.tsx")
    assert written == "src/pages/HomePage.tsx"


def test_the_allowlist_is_pinned() -> None:
    """DoD 8 says *pinned by test*. This is the pin.

    The number is the point. 26 modules can write pages; Phase 2's 2.4-2.5 is
    measured by how far it falls. Changing it should require editing this
    assertion and saying why in the commit.
    """
    assert len(_PAGE_WRITERS) == 27  # 26 writers + `workspace` itself
    assert "app.application.preview_app.codegen.generate" in _PAGE_WRITERS
    # Nothing outside the application package, and no test module baked in.
    for name in _PAGE_WRITERS:
        assert name.startswith("app."), name


def test_the_guarded_pattern_covers_what_the_dod_names() -> None:
    for rel_path in GUARDED:
        assert _GUARDED_WRITE_RE.match(rel_path), rel_path
    for rel_path in UNGUARDED:
        assert not _GUARDED_WRITE_RE.match(rel_path), rel_path


def test_the_guard_judges_the_canonical_path_not_the_requested_one(
    tmp_path: Path,
) -> None:
    """`write_file` renames `Dashboard.tsx` -> `DashboardPage.tsx`.

    Checking before canonicalization would let a caller past the guard with a
    name that becomes a page only after the rename.
    """
    with pytest.raises(UnauthorizedPageWrite) as excinfo:
        _write_from_module("app.some.new.writer", tmp_path, "src/pages/Dashboard.tsx")

    assert "src/pages/DashboardPage.tsx" in str(excinfo.value)


def test_audit_mode_records_instead_of_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """The mode the allowlist was derived with, so it stays usable.

    A census tool that rots is how the list stops being derived and starts being
    guessed.
    """
    monkeypatch.setenv("BMV_AUDIT_PAGE_WRITES", "1")
    written = _write_from_module("app.some.new.writer", tmp_path, "src/pages/HomePage.tsx")

    assert (tmp_path / written).is_file()
    out = capsys.readouterr().out
    assert "PAGE_WRITE_ORIGIN\tapp.some.new.writer\tsrc/pages/HomePage.tsx" in out


def test_the_origin_is_the_caller_not_an_intermediate_in_workspace(
    tmp_path: Path,
) -> None:
    """`write_file` delegates to `write_trusted_contained_file` in this module.

    A frame walk that stopped at the first frame would blame `workspace` for
    every write and the guard would allow everything.
    """
    assert ws._page_write_origin().startswith("tests.")