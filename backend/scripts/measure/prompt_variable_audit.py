"""Every prompt variable a template declares, diffed against every render site.

    docker run --rm -v "$REPO:/repo" -w /repo/backend --entrypoint sh bmv-local-api \
      -c 'python3 scripts/measure/prompt_variable_audit.py'

No database, no network, no model. The renderer uses StrictUndefined, so a
truly-missing variable raises — but a variable guarded with `is defined` that
no call site passes is a SILENTLY DEAD PROMPT SECTION: authored, tested at the
render level, and never sent to a model. That exact gap shipped in
`preview_app_mock_synthesize.j2` (CATALOGUE ITEM SHAPES, wired in session 16
after this audit found it).

Reports, per render site:
  MISSING  — template variables the call site does not pass (dead-if-guarded,
             crash-if-not; either way, look)
  unused   — kwargs the template never references (dead payload)

Call sites that spread `**kwargs` cannot be checked statically and are listed
as UNVERIFIABLE so silence is never read as coverage.

Exit code 1 when any MISSING row exists, so this can gate a commit.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

from jinja2 import Environment, meta

BACKEND = Path(__file__).resolve().parents[2]


def main() -> int:
    env = Environment()
    tpl_vars: dict[str, tuple[str, set[str]]] = {}
    for tpl in (BACKEND / "app/templates/prompts").glob("*.j2"):
        tpl_vars[tpl.stem] = (
            tpl.name,
            set(meta.find_undeclared_variables(env.parse(tpl.read_text()))),
        )

    enum_map: dict[str, str] = {}
    enum_src = (BACKEND / "app/application/prompts.py").read_text()
    for m in re.finditer(r"(\w+)\s*=\s*\"prompts/([\w.]+)\.j2\"", enum_src):
        enum_map[m.group(1)] = m.group(2)

    missing_rows: list[str] = []
    info_rows: list[str] = []
    for py in (BACKEND / "app").rglob("*.py"):
        src = py.read_text()
        if "PromptTemplate." not in src or ".render(" not in src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        rel = py.relative_to(BACKEND)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if not (isinstance(f, ast.Attribute) and f.attr == "render" and node.args):
                continue
            a0 = node.args[0]
            if not (
                isinstance(a0, ast.Attribute)
                and isinstance(a0.value, ast.Name)
                and a0.value.id == "PromptTemplate"
            ):
                continue
            tpl_file = enum_map.get(a0.attr)
            if not tpl_file or tpl_file not in tpl_vars:
                missing_rows.append(f"{rel}:{node.lineno} unknown template {a0.attr}")
                continue
            fname, needed = tpl_vars[tpl_file]
            passed = {kw.arg for kw in node.keywords if kw.arg}
            if any(kw.arg is None for kw in node.keywords):
                info_rows.append(f"{rel}:{node.lineno} {fname} UNVERIFIABLE (**kwargs)")
                continue
            missing = needed - passed
            extra = passed - needed
            if missing:
                missing_rows.append(f"{rel}:{node.lineno} {fname} MISSING: {sorted(missing)}")
            if extra:
                info_rows.append(f"{rel}:{node.lineno} {fname} unused kwargs: {sorted(extra)}")

    for row in info_rows:
        print(row)
    for row in missing_rows:
        print(row)
    if missing_rows:
        print(f"{len(missing_rows)} render site(s) with MISSING template variables")
        return 1
    print("all render sites pass every declared template variable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
