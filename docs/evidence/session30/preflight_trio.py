#!/usr/bin/env python3
"""Trio pre-flight — every runbook precondition as one GO/NO-GO command.

Automates the CHECKS before `TRIO_LAUNCH_RUNBOOK.md` (session 29); it does
not launch anything and it spends nothing (the balance probe is a free read,
bracketed per the shared-key policy). Run FROM THE REPO ROOT:

    python3 docs/evidence/session30/preflight_trio.py

After `git checkout main` this file is no longer in the working tree (it is
committed on `phase3-stage-a`); run it from the branch's blob instead:

    git show phase3-stage-a:docs/evidence/session30/preflight_trio.py | python3 -

GO means: launch per the runbook. Any FAIL names the fix.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path.cwd()
MIN_BALANCE = 5.0


def sh(cmd: list[str]) -> tuple[int, str]:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    return result.returncode, (result.stdout + result.stderr).strip()


def check(label: str, ok: bool, detail: str, failures: list[str]) -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label} — {detail}")
    if not ok:
        failures.append(label)


def main() -> int:
    failures: list[str] = []
    print("trio pre-flight\n")

    code, branch = sh(["git", "branch", "--show-current"])
    check(
        "on main (frozen build)",
        code == 0 and branch == "main",
        f"current branch: {branch or '?'} — the trio must run main; `git checkout main` first"
        if branch != "main"
        else "main checked out",
        failures,
    )

    code, dirty = sh(["git", "status", "--porcelain"])
    check(
        "tree clean",
        code == 0 and not dirty,
        "clean" if not dirty else f"{len(dirty.splitlines())} dirty/untracked tracked-path entries",
        failures,
    )

    code, behind = sh(["git", "rev-list", "--count", "phase3-stage-a..main"])
    check(
        "branch merge stays fast-forward",
        code == 0 and behind.strip() == "0",
        "main has not moved under the branch" if behind.strip() == "0" else f"main is {behind} ahead — rebase before merging",
        failures,
    )

    code, out = sh(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"])
    rows = dict(line.split("\t", 1) for line in out.splitlines() if "\t" in line) if code == 0 else {}
    api_up = "healthy" in rows.get("bmv-api", "")
    check("bmv-api healthy", api_up, rows.get("bmv-api", "not running"), failures)
    check("bmv-db healthy", "healthy" in rows.get("bmv-db", ""), rows.get("bmv-db", "not running"), failures)

    noisy = [name for name in rows if "rag" in name.lower()]
    check(
        "quiet host (no rag-mvp containers)",
        not noisy,
        "quiet" if not noisy else f"stop first: {', '.join(noisy)}",
        failures,
    )

    code, env = sh(["docker", "exec", "bmv-api", "printenv", "PREVIEW_TEMPLATE_DIR"])
    check(
        "container template dir sane",
        code == 0 and env.strip().endswith("preview-template"),
        env.strip() or "unreadable",
        failures,
    )

    probe = (
        "import json, os, urllib.request\n"
        "key = os.environ.get('OPENROUTER_API_KEY', '')\n"
        "req = urllib.request.Request('https://openrouter.ai/api/v1/credits',"
        " headers={'Authorization': f'Bearer {key}'})\n"
        "data = json.load(urllib.request.urlopen(req, timeout=15))['data']\n"
        "print(json.dumps(data['total_credits'] - data['total_usage']))\n"
    )
    code, out = sh(["docker", "exec", "bmv-api", "python", "-c", probe])
    balance = None
    if code == 0:
        try:
            balance = float(json.loads(out.splitlines()[-1]))
        except (ValueError, IndexError):
            balance = None
    check(
        f"balance >= ${MIN_BALANCE:.0f} (shared key — attribute only the delta)",
        balance is not None and balance >= MIN_BALANCE,
        f"${balance:.3f}" if balance is not None else f"probe failed: {out[:120]}",
        failures,
    )

    print()
    if failures:
        print(f"NO-GO — fix: {', '.join(failures)}")
        return 1
    print("GO — launch per docs/evidence/session29/TRIO_LAUNCH_RUNBOOK.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
