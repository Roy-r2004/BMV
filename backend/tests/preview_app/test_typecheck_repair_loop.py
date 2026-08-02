"""Type errors are a quality signal, never a reason to ship nothing.

The repair loop is bounded (rounds + the fix-loop wall clock), it records what
is left over so the count can be surfaced, and it refuses to trade a working
build for a typechecked one: any round whose rebuild fails is rolled back
wholesale and the previous dist is put back.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.pipeline import build_phase
from app.application.preview_app.typecheck import (
    TypecheckReport,
    parse_tsc_output,
    read_typecheck_record,
)

TS_ERRORS = (
    "src/pages/HomePage.tsx(15,85): error TS2322: Type '{ label: string; value: string; }[]' is not "
    "assignable to type 'CredentialStripItem[]'.\n"
)
ORIGINAL_PAGE = "export default function HomePage() { return <main>original</main> }\n"


def _errors_report() -> TypecheckReport:
    return TypecheckReport(status="errors", diagnostics=tuple(parse_tsc_output(TS_ERRORS)))


def _report_for(counts: dict[str, int], *, unparseable: tuple[str, ...] = ()) -> TypecheckReport:
    """A report with `counts[path]` errors per file.

    `unparseable` files get a parse-failure message instead of a type mismatch,
    which is how a broken patch looks to `tsc` — and it is why an error-count
    comparison alone is not enough: `tsc` abandons the file, so it reports FEWER
    errors than the working version did.
    """
    lines = []
    for path, count in counts.items():
        for index in range(count):
            if path in unparseable:
                lines.append(f"{path}({index + 1},1): error TS1005: '}}' expected.")
            else:
                lines.append(
                    f"{path}({index + 1},9): error TS2322: Type 'string' is not "
                    "assignable to type 'CredentialStripItem[]'."
                )
    return TypecheckReport(status="errors", diagnostics=tuple(parse_tsc_output("\n".join(lines))))


def _ctx(workspace: Path) -> SimpleNamespace:
    return SimpleNamespace(
        db=None,
        request_id=36,
        workspace=workspace,
        architect={},
        ai_provider=object(),
        template_renderer=object(),
        base_path="/api/preview-apps/36",
        max_fix_seconds=900.0,
        build_log="",
    )


def _workspace(tmp_path: Path) -> Path:
    pages = tmp_path / "src" / "pages"
    pages.mkdir(parents=True)
    (pages / "HomePage.tsx").write_text(ORIGINAL_PAGE, encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>shipping</html>", encoding="utf-8")
    return tmp_path


def _stub_pipeline(
    monkeypatch, *, reports, build_ok=True, on_fix=None, patched=None, reject=None
) -> dict:
    """Stub the three expensive steps. `calls["prior_rejections"]` records what
    each round was told about the previous round's rejections; `reject` is a
    per-round rejection reason the fix agent reports back."""
    calls: dict[str, Any] = {"fix": 0, "build": 0, "typecheck": 0, "prior_rejections": []}
    queue = list(reports)

    def _typecheck(_workspace, **_kwargs):
        calls["typecheck"] += 1
        return queue.pop(0) if queue else reports[-1]

    def _fix(workspace, _report, *_args, **kwargs):
        calls["fix"] += 1
        calls["prior_rejections"].append(list(kwargs.get("prior_rejections") or []))
        out = kwargs.get("rejections_out")
        if reject and out is not None and calls["fix"] == 1:
            out.append(reject)
        if on_fix is not None:
            on_fix(workspace)
        return list(patched) if patched is not None else ["src/pages/HomePage.tsx"]

    def _build(workspace, *_args, **_kwargs):
        calls["build"] += 1
        dist = Path(workspace) / "dist"
        if build_ok:
            dist.mkdir(exist_ok=True)
            (dist / "index.html").write_text("<html>rebuilt</html>", encoding="utf-8")
            return True, "ok"
        # vite empties outDir before it fails.
        for child in dist.glob("*"):
            child.unlink()
        return False, "build failed"

    monkeypatch.setattr(build_phase, "typecheck_workspace", _typecheck)
    monkeypatch.setattr(build_phase, "fix_type_errors", _fix)
    monkeypatch.setattr(build_phase, "run_build", _build)
    monkeypatch.setattr(build_phase, "_pre_build_fixups", lambda _ctx: None)
    monkeypatch.setattr(build_phase, "_emit", lambda *a, **k: None)
    return calls


def test_rounds_are_bounded_and_leftover_errors_are_recorded(tmp_path: Path, monkeypatch) -> None:
    """The round cap is what stops a loop that is still making progress.

    Each round must reduce the error count, or the no-net-progress guard exits
    first (see `test_a_round_that_makes_no_net_progress_stops_the_loop`) and this
    would be measuring that instead of the cap.
    """
    workspace = _workspace(tmp_path)
    page = "src/pages/HomePage.tsx"
    monkeypatch.setattr(build_phase.settings, "PREVIEW_MAX_TYPECHECK_FIX_ROUNDS", 2)
    calls = _stub_pipeline(
        monkeypatch,
        reports=[
            _report_for({page: 3}),
            _report_for({page: 2}),
            _report_for({page: 1}),
        ],
    )

    report = build_phase._run_typecheck_repair(_ctx(workspace))

    assert calls["fix"] == 2
    assert report.status == "errors"
    # Still shipping: the dist the customer opens is intact.
    assert (workspace / "dist" / "index.html").is_file()
    recorded = read_typecheck_record(workspace)
    assert recorded["status"] == "errors"
    assert recorded["error_count"] == 1
    assert recorded["repair_rounds"] == 2


def test_zero_rounds_still_measures_and_records(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setattr(build_phase.settings, "PREVIEW_MAX_TYPECHECK_FIX_ROUNDS", 0)
    calls = _stub_pipeline(monkeypatch, reports=[_errors_report()])

    build_phase._run_typecheck_repair(_ctx(workspace))

    assert calls["fix"] == 0
    assert read_typecheck_record(workspace)["error_count"] == 1


def test_loop_stops_as_soon_as_the_workspace_is_clean(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setattr(build_phase.settings, "PREVIEW_MAX_TYPECHECK_FIX_ROUNDS", 3)
    calls = _stub_pipeline(
        monkeypatch, reports=[_errors_report(), TypecheckReport(status="clean")]
    )

    report = build_phase._run_typecheck_repair(_ctx(workspace))

    assert calls["fix"] == 1
    assert report.status == "clean"
    assert read_typecheck_record(workspace)["error_count"] == 0


def test_unavailable_typecheck_never_triggers_repairs(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setattr(build_phase.settings, "PREVIEW_MAX_TYPECHECK_FIX_ROUNDS", 2)
    calls = _stub_pipeline(
        monkeypatch, reports=[TypecheckReport(status="unavailable", reason="no node")]
    )

    build_phase._run_typecheck_repair(_ctx(workspace))

    assert calls["fix"] == 0
    assert calls["build"] == 0
    recorded = read_typecheck_record(workspace)
    assert recorded["status"] == "unavailable"
    assert recorded["reason"] == "no node"


def test_one_bad_patch_does_not_cost_the_whole_batch(tmp_path: Path, monkeypatch) -> None:
    """The defect this loop never recovered from.

    In two live generations the model patched 8 files, the rebuild failed, and all
    8 were rolled back — so a round that fixed 7 files landed nothing. Only the
    file the model made worse may be given back.
    """
    workspace = _workspace(tmp_path)
    pages = workspace / "src" / "pages"
    # Canonical `*Page.tsx` names: `write_file` renames anything else under
    # src/pages/ and unlinks the pre-canonical file, so a fixture using
    # `Good.tsx` would measure that rename rather than the revert.
    good_one, good_two, bad = "GoodOnePage.tsx", "GoodTwoPage.tsx", "BadPage.tsx"
    for name in (good_one, good_two, bad):
        (pages / name).write_text(f"// original {name}\n", encoding="utf-8")
    rel = [f"src/pages/{name}" for name in (good_one, good_two, bad)]

    def _patch_all(ws: Path) -> None:
        for name in (good_one, good_two, bad):
            (Path(ws) / "src" / "pages" / name).write_text(f"// patched {name}\n", encoding="utf-8")

    monkeypatch.setattr(build_phase.settings, "PREVIEW_MAX_TYPECHECK_FIX_ROUNDS", 1)
    _stub_pipeline(
        monkeypatch,
        # Before: 2 errors each. After: the two good files are clean, Bad.tsx
        # gained one.
        reports=[
            _report_for({rel[0]: 2, rel[1]: 2, rel[2]: 2}),
            _report_for({rel[2]: 3}),
            _report_for({rel[2]: 3}),
        ],
        patched=rel,
        on_fix=_patch_all,
    )

    build_phase._run_typecheck_repair(_ctx(workspace))

    assert (pages / good_one).read_text(encoding="utf-8") == f"// patched {good_one}\n"
    assert (pages / good_two).read_text(encoding="utf-8") == f"// patched {good_two}\n"
    assert (pages / bad).read_text(encoding="utf-8") == f"// original {bad}\n"


def test_a_patch_that_stops_parsing_is_reverted_even_though_it_scores_better(
    tmp_path: Path, monkeypatch
) -> None:
    """`tsc` abandons a file it cannot parse, so a broken patch reports FEWER
    errors than the working file did. An error-count comparison alone would keep
    it and hand a build failure to the next stage."""
    workspace = _workspace(tmp_path)
    pages = workspace / "src" / "pages"
    (pages / "BrokenPage.tsx").write_text("// original BrokenPage.tsx\n", encoding="utf-8")
    rel = "src/pages/BrokenPage.tsx"

    monkeypatch.setattr(build_phase.settings, "PREVIEW_MAX_TYPECHECK_FIX_ROUNDS", 1)
    _stub_pipeline(
        monkeypatch,
        reports=[
            _report_for({rel: 6}),
            _report_for({rel: 1}, unparseable=(rel,)),
            _report_for({rel: 6}),
        ],
        patched=[rel],
        on_fix=lambda ws: (Path(ws) / "src" / "pages" / "BrokenPage.tsx").write_text(
            "export default function Broken() { return <main>", encoding="utf-8"
        ),
    )

    build_phase._run_typecheck_repair(_ctx(workspace))

    assert (pages / "BrokenPage.tsx").read_text(encoding="utf-8") == "// original BrokenPage.tsx\n"


def test_a_round_that_makes_no_net_progress_stops_the_loop(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    page = "src/pages/HomePage.tsx"
    monkeypatch.setattr(build_phase.settings, "PREVIEW_MAX_TYPECHECK_FIX_ROUNDS", 4)
    calls = _stub_pipeline(monkeypatch, reports=[_report_for({page: 2})])

    build_phase._run_typecheck_repair(_ctx(workspace))

    assert calls["fix"] == 1, "a lateral round must not be repeated three more times"


def test_a_round_that_leaves_more_errors_than_it_found_is_given_back(
    tmp_path: Path, monkeypatch
) -> None:
    """Damage in files the model was not asked about cannot be reverted per-file,
    so the whole round goes back — and no build is spent on it."""
    workspace = _workspace(tmp_path)
    page, elsewhere = "src/pages/HomePage.tsx", "src/pages/OtherPage.tsx"
    (workspace / "src" / "pages" / "OtherPage.tsx").write_text("// other\n", encoding="utf-8")
    monkeypatch.setattr(build_phase.settings, "PREVIEW_MAX_TYPECHECK_FIX_ROUNDS", 2)
    calls = _stub_pipeline(
        monkeypatch,
        reports=[_report_for({page: 2}), _report_for({page: 1, elsewhere: 4})],
        patched=[page],
        on_fix=lambda ws: (Path(ws) / "src" / "pages" / "HomePage.tsx").write_text(
            "// patched\n", encoding="utf-8"
        ),
    )

    build_phase._run_typecheck_repair(_ctx(workspace))

    assert (workspace / "src" / "pages" / "HomePage.tsx").read_text(
        encoding="utf-8"
    ) == ORIGINAL_PAGE
    assert calls["build"] == 0, "a round known to be worse must not consume a build"


def test_rejection_reasons_reach_the_next_round(tmp_path: Path, monkeypatch) -> None:
    """`regressive_fix_reason` used to log why a patch was thrown away and drop
    it, so the model reoffered the same forbidden patch every round."""
    workspace = _workspace(tmp_path)
    page = "src/pages/HomePage.tsx"
    reason = f"{page}: empties data collection(s) items"
    monkeypatch.setattr(build_phase.settings, "PREVIEW_MAX_TYPECHECK_FIX_ROUNDS", 2)
    calls = _stub_pipeline(
        monkeypatch,
        reports=[_report_for({page: 3}), _report_for({page: 2}), _report_for({page: 1})],
        reject=reason,
    )

    build_phase._run_typecheck_repair(_ctx(workspace))

    assert calls["fix"] == 2
    assert calls["prior_rejections"][0] == []
    assert calls["prior_rejections"][1] == [reason], (
        "round 2 must be told why round 1's patch was rejected"
    )


def test_a_repair_that_breaks_the_build_is_rolled_back(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setattr(build_phase.settings, "PREVIEW_MAX_TYPECHECK_FIX_ROUNDS", 2)

    def _break_page(ws: Path) -> None:
        (Path(ws) / "src" / "pages" / "HomePage.tsx").write_text(
            "export default function HomePage() { return <main>broken", encoding="utf-8"
        )

    calls = _stub_pipeline(
        monkeypatch, reports=[_errors_report()], build_ok=False, on_fix=_break_page
    )

    build_phase._run_typecheck_repair(_ctx(workspace))

    assert calls["fix"] == 1
    assert (workspace / "src" / "pages" / "HomePage.tsx").read_text(encoding="utf-8") == ORIGINAL_PAGE
    # A failed rebuild wiped dist; the pre-typecheck build is restored so the
    # preview still serves.
    assert (workspace / "dist" / "index.html").read_text(encoding="utf-8") == "<html>shipping</html>"


def test_dist_backup_temp_is_removed_even_when_repair_raises(
    tmp_path: Path, monkeypatch
) -> None:
    """`_backup_dist` mkdtemps a full dist copy — an exception must not leak it."""
    import tempfile

    workspace = _workspace(tmp_path)
    monkeypatch.setattr(build_phase.settings, "PREVIEW_MAX_TYPECHECK_FIX_ROUNDS", 1)
    created: list[Path] = []
    real_mkdtemp = tempfile.mkdtemp

    def _tracking_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created.append(Path(path))
        return path

    monkeypatch.setattr(build_phase.tempfile, "mkdtemp", _tracking_mkdtemp)

    def _raise_mid_repair(*_a, **_k):
        raise RuntimeError("simulated mid-repair crash")

    monkeypatch.setattr(build_phase, "typecheck_workspace", lambda *_a, **_k: _errors_report())
    monkeypatch.setattr(build_phase, "fix_type_errors", _raise_mid_repair)
    monkeypatch.setattr(build_phase, "_pre_build_fixups", lambda _ctx: None)
    monkeypatch.setattr(build_phase, "_emit", lambda *a, **k: None)
    # dump_exception writes diagnostics — keep it quiet and local.
    monkeypatch.setattr(build_phase, "dump_exception", lambda *a, **k: None)

    build_phase._run_typecheck_repair(_ctx(workspace))

    assert created, "expected _backup_dist to create a temp dir"
    for path in created:
        assert not path.exists(), f"leaked dist backup temp: {path}"
