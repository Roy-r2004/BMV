"""Replay session 11's three unproven fixes against stored production inputs.

Session 11 landed four fixes (`3b63a07`, `8fe8955`). One is production-proven:
requests 101 and 102 ship a derived palette. The other three are not, because
both proof runs died in `codegen` on a provider HTTP 408 before a build, and
`normalize_mock_navigation` and `ensure_seed_scaffold_fields` both run *at* a
build. Session 12 could not run a duo either: the OpenRouter account is
exhausted.

This is the sanctioned substitute — "force it offline if the run does not". It
is **weaker than a run** and stronger than a unit test: it drives the real
functions with the workspaces and route tables production actually produced.

    mkdir -p /tmp/ws && tar -xzf docs/evidence/preview-workspaces.tar.gz -C /tmp/ws
    docker compose exec api python /app/backend/scripts/measure/session11_fix_replay.py \
        --workspaces /ws

What it cannot show: that the pipeline *reaches* these functions with this data
on a live run. Only a generation shows that, and the three fixes stay
production-unproven until one happens.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

_REPO_BACKEND = Path(__file__).resolve().parents[2]
if str(_REPO_BACKEND) not in sys.path:
    sys.path.insert(0, str(_REPO_BACKEND))

SUBCOPY_LITERAL = "warm, specific, and ready when you are"


def _nav_of(mock_text: str) -> dict:
    match = re.search(r"export const navigation\s*=\s*", mock_text)
    if not match:
        return {}
    from app.application.preview_app.safety.mock_data import _mock_export_value_end

    end = _mock_export_value_end(mock_text, match.end())
    try:
        value = json.loads(mock_text[match.end() : end].rstrip().rstrip(";"))
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _routes_for(request_id: int) -> list[dict]:
    from app.domain.models.request import Request
    from app.infrastructure.db.session import SessionLocal

    db = SessionLocal()
    try:
        req = db.query(Request).filter(Request.id == request_id).one_or_none()
        if req is None:
            return []
        pages = req.generated_pages
        if isinstance(pages, str):
            try:
                pages = json.loads(pages)
            except ValueError:
                return []
        if not isinstance(pages, dict):
            return []
        app = pages.get("preview_app") or {}
        return [r for r in (app.get("routes") or []) if isinstance(r, dict)]
    finally:
        db.close()


def replay_navigation(root: Path) -> int:
    """A label collision must rename a route, never delete it.

    The nav is built from the architect route table by `_nav_from_architect` and
    then normalized. Replaying the normalizer over a *shipped* `mock.ts` proves
    nothing about this fix: request 95's `/reservations` was already deleted by
    the old rule before that file was written, and the normalizer only ever
    narrows a list — it cannot restore a route that was dropped upstream of it.
    So this rebuilds the nav the way `write_plumbing_mock` does and normalizes
    that, which is the sequence a live build runs.
    """
    from app.application.preview_app.safety.mock_data import (
        _nav_from_architect,
        _mock_export_value_end,
        normalize_mock_navigation,
    )

    print("=== _nav_from_architect + normalize_mock_navigation, on shipped route tables ===")
    failures = 0
    checked = 0
    for workspace in sorted(root.iterdir(), key=lambda p: p.name):
        if not workspace.is_dir() or not (workspace / "src/data/mock.ts").is_file():
            continue
        try:
            request_id = int(workspace.name)
        except ValueError:
            continue
        routes = _routes_for(request_id)
        paths = {str(r.get("path") or "") for r in routes}
        # The shape the fix exists for: two declared public routes whose short
        # labels collide. `_NAV_LABEL_NOISE_RE` strips a leading `My `.
        collisions = sorted(
            p for p in paths if p.startswith("/my-") and f"/{p[4:]}" in paths
        )
        if not collisions:
            continue
        checked += 1
        architect = {"routes": routes}
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp) / workspace.name
            shutil.copytree(workspace, scratch)
            mock_path = scratch / "src/data/mock.ts"
            mock = mock_path.read_text()
            match = re.search(r"export const navigation\s*=\s*", mock)
            end = _mock_export_value_end(mock, match.end())
            mock_path.write_text(
                mock[: match.end()]
                + json.dumps(_nav_from_architect(architect), indent=2)
                + ";"
                + mock[end:]
            )
            normalize_mock_navigation(scratch, architect, workspace_brand(scratch))
            nav = _nav_of(mock_path.read_text())
        public = nav.get("public") or []
        by_path = {str(i.get("path") or i.get("href") or ""): i for i in public}
        for member in collisions:
            partner = f"/{member[4:]}"
            labels = {
                str(by_path.get(p, {}).get("label") or "") for p in (member, partner)
            }
            ok = member in by_path and partner in by_path and len(labels) == 2
            print(
                f"  request {request_id}: {partner} + {member} -> "
                f"{sorted(labels)}  {'OK' if ok else 'FAIL'}"
            )
            failures += 0 if ok else 1
    if not checked:
        print("  no archived workspace declares a colliding pair — nothing replayed")
        return 1
    return failures


def workspace_brand(workspace: Path) -> str:
    mock = (workspace / "src/data/mock.ts").read_text()
    match = re.search(r'"?(?:brand_name|brandName|name)"?\s*:\s*"([^"]{2,60})"', mock)
    return match.group(1) if match else "Brand"


def replay_subcopy(root: Path) -> int:
    """The scaffold's hero subcopy must not be the literal it used to be."""
    from app.application.preview_app.safety.mock_data import ensure_seed_scaffold_fields

    print("\n=== ensure_seed_scaffold_fields, on the workspaces that shipped the literal ===")
    failures = 0
    checked = 0
    for workspace in sorted(root.iterdir(), key=lambda p: p.name):
        mock_path = workspace / "src/data/mock.ts"
        if not workspace.is_dir() or not mock_path.is_file():
            continue
        try:
            request_id = int(workspace.name)
        except ValueError:
            continue
        mock = mock_path.read_text()
        if SUBCOPY_LITERAL not in mock:
            continue
        checked += 1
        # Reproduce the condition the scaffold fires under: the AI's synthesis
        # dropped `hero`, so the whole block is written from scratch.
        stripped = re.sub(
            r"\n\s*hero:\s*\{.*?\n\s*\},", "\n", mock, count=1, flags=re.S
        )
        rebuilt = ensure_seed_scaffold_fields(
            stripped, workspace_brand(workspace), {"routes": _routes_for(request_id)}
        )
        ok = SUBCOPY_LITERAL not in rebuilt
        print(
            f"  request {request_id}: shipped the literal; rebuilt "
            f"{'without it  OK' if ok else 'WITH IT  FAIL'}"
        )
        failures += 0 if ok else 1
    if not checked:
        print("  no archived workspace carries the literal — nothing replayed")
        return 1
    return failures


def replay_font() -> int:
    """`design_system.font_family` must be the font's name, not a squashed slug."""
    from app.application.preview_app.safety.mock_data import _design_system_dict

    print("\n=== _design_system_dict, on the font names the corpus actually used ===")
    failures = 0
    for font in ("Source Sans 3", "Nunito Sans", "Libre Baskerville", "Fraunces", "Inter"):
        design = _design_system_dict("#1d7b4c", "#124b3a", font)
        family = design["font_family"]
        url = design["font_import_url"]
        ok = family == font and "+" in url or family == font
        print(f"  {font!r:24} -> font_family={family!r:24} {'OK' if ok else 'FAIL'}")
        failures += 0 if ok else 1
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workspaces",
        default="/ws",
        help="extracted docs/evidence/preview-workspaces.tar.gz",
    )
    args = parser.parse_args()
    root = Path(args.workspaces)
    if not root.is_dir():
        print(f"no such directory: {root}")
        return 2

    failures = replay_navigation(root) + replay_subcopy(root) + replay_font()
    print()
    if failures:
        print(f"{failures} REPLAYED CHECKS FAILED — the fix is not landed")
        return 1
    print("all replayed checks hold. NOT a production proof — see the module docstring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
