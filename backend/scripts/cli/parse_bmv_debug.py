#!/usr/bin/env python3
"""Parse `.bmv-debug/` artifacts for a preview request and print a failure report.

Usage:
  python scripts/parse_bmv_debug.py 6
  python scripts/parse_bmv_debug.py /app/data/preview-apps/6
  docker compose exec api python /app/backend/scripts/parse_bmv_debug.py 6
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root or backend/
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import settings  # noqa: E402
from app.infrastructure.logging.diagnostics import summarize_workspace_debug  # noqa: E402


def _resolve_workspace(arg: str) -> Path:
    p = Path(arg)
    if p.is_dir():
        return p
    return settings.PREVIEW_APPS_DIR / arg


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize BMV preview debug artifacts")
    parser.add_argument(
        "target",
        help="Request id (e.g. 6) or absolute path to preview workspace",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full JSON report instead of human summary",
    )
    args = parser.parse_args()

    workspace = _resolve_workspace(args.target)
    report = summarize_workspace_debug(workspace)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0 if report.get("categories") else 1

    print(f"Workspace: {workspace}")
    if not workspace.exists():
        print("ERROR: workspace does not exist")
        return 1

    debug_root = workspace / ".bmv-debug"
    if not debug_root.is_dir():
        print("No .bmv-debug/ directory found.")
        print("Tip: re-run generation with LOG_LEVEL=debug and inspect api logs.")
        return 1

    cats = report.get("categories") or {}
    print(f"\nArtifacts ({sum(c.get('count', 0) for c in cats.values())} files):")
    for name, cat in cats.items():
        print(f"  {name}: {cat.get('count', 0)}")

    issues = report.get("top_issues") or []
    print(f"\nTop issues ({len(issues)}):")
    if not issues:
        print("  (none parsed — check raw files under .bmv-debug/)")
    for issue in issues:
        print(f"  • {issue}")

    # Category detail
    for name, cat in cats.items():
        artifacts = cat.get("artifacts") or []
        if not artifacts:
            continue
        print(f"\n--- {name} (latest) ---")
        latest = artifacts[0]
        meta = latest.get("meta") or {}
        if meta:
            for k, v in meta.items():
                if k != "errors" or len(str(v)) < 300:
                    print(f"  {k}: {v}")
        if name == "fix-agent":
            ja = latest.get("json_analysis") or {}
            if ja:
                print(
                    f"  analysis: len={ja.get('length')} truncated={ja.get('likely_truncated')} "
                    f"brace_imbalance={ja.get('depth_imbalance')} files_key={ja.get('has_files_key')}"
                )
        if name == "vite-build":
            for err in (latest.get("vite_errors") or [])[:5]:
                print(f"  vite: {err}")
        if name == "pipeline":
            payload = latest.get("payload") or {}
            if payload.get("build_log_tail"):
                tail = payload["build_log_tail"].splitlines()[-6:]
                print("  build_log_tail:")
                for line in tail:
                    print(f"    {line}")

    print(f"\nRaw dumps: {debug_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
