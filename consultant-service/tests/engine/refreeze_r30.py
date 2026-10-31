"""Re-record the r30 frozen manifest, deliberately.

Use this only when the owner has changed a frozen file on purpose (app/pipeline,
app/prompts, tools, or a top-level tests/*.py) and the change is committed.
Run it from the service root, then commit the manifest, this script's output and
the two commit constants (test_engine_r30_frozen.py and
test_engine_mutation_manifest.py) in one commit that says why:

    python tests/engine/refreeze_r30.py --commit <short-sha-of-the-last-frozen-change>

It rebuilds `files` with the freeze test's own collect_frozen_files() and
sha256_of(), keeps every other key, sets `commit`, and appends one sentence to
`recorded`. It refuses to run while anything under the frozen roots is
uncommitted, because a manifest recorded from a dirty tree would name a commit
that does not contain the bytes it hashes. Lives under tests/engine, which the
freeze excludes (MF3.6).
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVICE_ROOT = os.path.dirname(os.path.dirname(HERE))
FREEZE_TEST = os.path.join(HERE, "test_engine_r30_frozen.py")
MANIFEST_PATH = os.path.join(HERE, "r30_manifest.json")


def _load_freeze_module():
    spec = importlib.util.spec_from_file_location("test_engine_r30_frozen", FREEZE_TEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=SERVICE_ROOT, capture_output=True, text=True)


def _dirty_frozen_paths(frozen) -> list[str]:
    """Uncommitted or untracked paths under the frozen roots or the top-level
    suite. `:(glob)tests/*.py` keeps the pathspec off tests/engine."""
    specs = [*frozen.FROZEN_ROOTS, ":(glob)tests/*.py"]
    result = _git("status", "--porcelain", "--untracked-files=all", "--", *specs)
    if result.returncode != 0:
        raise SystemExit(f"git status failed: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--commit", required=True,
                        help="short sha of the last commit that touched a frozen path")
    parser.add_argument("--after", default="the honest-failure step",
                        help="what the re-freeze follows, for the `recorded` sentence "
                             "(default: %(default)s)")
    args = parser.parse_args(argv)

    if _git("rev-parse", "--verify", "--quiet", f"{args.commit}^{{commit}}").returncode != 0:
        raise SystemExit(f"{args.commit} is not a commit in this repository")

    frozen = _load_freeze_module()
    dirty = _dirty_frozen_paths(frozen)
    if dirty:
        raise SystemExit("refusing to re-freeze: the frozen tree has uncommitted changes:\n"
                         + "\n".join(dirty))

    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        manifest = json.load(fh)

    old_files: dict[str, str] = manifest["files"]
    new_files = {rel: frozen.sha256_of(rel) for rel in frozen.collect_frozen_files()}

    added = sorted(set(new_files) - set(old_files))
    removed = sorted(set(old_files) - set(new_files))
    changed = sorted(p for p in set(new_files) & set(old_files) if new_files[p] != old_files[p])

    sentence = (f"Re-frozen at {args.commit} after {args.after} "
                f"({datetime.date.today().isoformat()}), same rules, same collector.")
    recorded = manifest["recorded"]
    if sentence not in recorded:
        recorded = f"{recorded}. {sentence}"

    manifest["commit"] = args.commit
    manifest["recorded"] = recorded
    manifest["file_count"] = len(new_files)
    manifest["files"] = dict(sorted(new_files.items()))

    # Same bytes the file already had: indent 2, LF, no trailing newline.
    with open(MANIFEST_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(manifest, indent=2))

    print(f"re-frozen at {args.commit}: {len(old_files)} -> {len(new_files)} files; "
          f"added {len(added)} ({', '.join(added) or '-'}); "
          f"removed {len(removed)} ({', '.join(removed) or '-'}); "
          f"changed {len(changed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
