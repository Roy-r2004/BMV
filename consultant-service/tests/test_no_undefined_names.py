"""No module may reference a name it never defines or imports.

Engagement 57 failed 120 seconds into a PAID generation with
`NameError: name 'build_engagement_register' is not defined` — plan.py used
the helper without importing it. The bug had been latent for weeks: every run
in between re-rendered stored content, so the plan stage never executed. A
NameError is free to find and expensive to hit, so it is found here.
"""
import ast
import builtins
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
# module-level dunders the interpreter supplies
SUPPLIED = {"__file__", "__name__", "__doc__", "__package__", "__spec__", "__loader__", "__builtins__"}


def _bound_names(tree: ast.AST) -> set[str]:
    """Every name a module binds: imports, defs, classes, assignments,
    arguments, comprehension targets, except-handlers, globals."""
    bound: set[str] = set(dir(builtins)) | SUPPLIED
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)
    return bound


def _undefined(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    bound = _bound_names(tree)
    try:
        where = path.relative_to(ROOT)
    except ValueError:                       # a file outside the tree (the negative control)
        where = path
    return [f"{where}:{n.lineno} {n.id}"
            for n in ast.walk(tree)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in bound]


def test_no_module_uses_a_name_it_never_binds():
    files = sorted(ROOT.joinpath("app").rglob("*.py")) + sorted(ROOT.joinpath("tools").rglob("*.py"))
    assert files, "no source files found — the sweep would pass vacuously"
    problems = [p for f in files for p in _undefined(f)]
    assert problems == [], "undefined names would raise NameError at run time:\n  " + "\n  ".join(problems)


def test_the_sweep_actually_catches_one(tmp_path):
    """The negative control: a file that uses an unimported helper is caught."""
    bad = tmp_path / "bad.py"
    bad.write_text("def go():\n    return build_engagement_register(1)\n", encoding="utf-8")
    assert any("build_engagement_register" in p for p in _undefined(bad))
