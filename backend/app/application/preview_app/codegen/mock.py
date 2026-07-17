"""Mock data synthesis for preview workspaces."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from app.application.prompts import PromptTemplate
from app.application.preview_app.catalogue_contract import _source_tokens
from app.application.preview_app.mock_imports import _collect_mock_imports
from app.application.preview_app.source_quality import (
    fix_unescaped_apostrophes,
    looks_truncated_source,
)
from app.application.preview_app.text_utils import _bounded_json, _parse_json, _strip_fences
from app.application.preview_app.workspace import list_source_files, read_file, write_file
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.infrastructure.logging import get_logger

cg_log = get_logger("Codegen")

def mock_needs_enrichment(content: str) -> bool:
    if not content or len(content) < 1800:
        return True
    if re.search(r"//\s*(Additional|more items|etc)", content, re.I):
        return True
    if "export const brand" not in content or "export const roles" not in content:
        return True
    return False

_MAX_SYNTHESIZED_MOCK_BYTES = 256_000

_TYPESCRIPT_MOCK_VALIDATOR = r"""
const ts = require(process.argv[1]);
const needed = new Set(JSON.parse(process.argv[2]));
let source = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => { source += chunk; });
process.stdin.on("end", () => {
  const file = ts.createSourceFile(
    "mock.ts",
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  if (file.parseDiagnostics.length) process.exit(2);

  const locals = new Set();
  const exported = new Set();
  const bindingNames = (name, target) => {
    if (ts.isIdentifier(name)) {
      target.add(name.text);
      return;
    }
    for (const element of name.elements || []) {
      if (element && element.name) bindingNames(element.name, target);
    }
  };
  const declarationNames = (statement, target) => {
    if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        bindingNames(declaration.name, target);
      }
    } else if (
      (ts.isFunctionDeclaration(statement)
        || ts.isClassDeclaration(statement)
        || ts.isInterfaceDeclaration(statement)
        || ts.isTypeAliasDeclaration(statement)
        || ts.isEnumDeclaration(statement)
        || ts.isModuleDeclaration(statement))
      && statement.name
      && ts.isIdentifier(statement.name)
    ) {
      target.add(statement.name.text);
    }
  };
  const hasExport = statement =>
    (ts.getCombinedModifierFlags(statement) & ts.ModifierFlags.Export) !== 0;

  for (const statement of file.statements) declarationNames(statement, locals);
  for (const statement of file.statements) {
    if (hasExport(statement)) declarationNames(statement, exported);
    if (
      ts.isExportDeclaration(statement)
      && !statement.moduleSpecifier
      && statement.exportClause
      && ts.isNamedExports(statement.exportClause)
    ) {
      for (const element of statement.exportClause.elements) {
        const localName = (element.propertyName || element.name).text;
        if (locals.has(localName)) exported.add(element.name.text);
      }
    }
  }
  for (const name of needed) {
    if (!exported.has(name)) process.exit(3);
  }
  process.stdout.write("ok");
});
"""

def _typescript_candidate_defines(
    content: str,
    needed: list[str],
) -> bool:
    """Parse candidate TypeScript and verify its locally-defined named exports."""
    encoded = content.encode("utf-8", errors="strict")
    if len(encoded) > _MAX_SYNTHESIZED_MOCK_BYTES:
        return False
    node = shutil.which("node")
    compiler = (
        Path(settings.PREVIEW_TEMPLATE_DIR)
        / "node_modules"
        / "typescript"
        / "lib"
        / "typescript.js"
    )
    if not node or not compiler.is_file():
        return False
    try:
        result = subprocess.run(
            [
                node,
                "-e",
                _TYPESCRIPT_MOCK_VALIDATOR,
                str(compiler.resolve()),
                json.dumps(needed),
            ],
            input=content,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            cwd=Path(settings.PREVIEW_TEMPLATE_DIR),
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return False
    return result.returncode == 0 and result.stdout == "ok"

def _valid_synthesized_mock_source(content: str, needed: list[str]) -> bool:
    """Fail closed unless a safe candidate parses and defines every needed export."""
    if not content.strip() or looks_truncated_source(content):
        return False
    tokens = _source_tokens(content)
    if not tokens:
        return False
    for index, token in enumerate(tokens):
        if token == "require":
            return False
        if token == "import" and index + 1 < len(tokens):
            if tokens[index + 1] == "(":
                return False
            if (
                index + 2 < len(tokens)
                and re.match(r"^[A-Za-z_$][\w$]*$", tokens[index + 1])
                and tokens[index + 2] == "="
            ):
                return False
            if (
                tokens[index + 1].startswith("\0http://")
                or tokens[index + 1].startswith("\0https://")
            ):
                return False
        if (
            token == "from"
            and index + 1 < len(tokens)
            and tokens[index + 1].startswith(("\0http://", "\0https://"))
        ):
            return False
    return _typescript_candidate_defines(content, needed)

def synthesize_mock_data(
    workspace: Path,
    full_context: str,
    plan: dict,
    manifest: dict,
    images: dict,
    architect: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> bool:
    """After pages exist: AI writes mock.ts exporting ONLY what pages import."""
    mock_path = "src/data/mock.ts"
    needed = sorted(_collect_mock_imports(workspace))
    if not needed:
        return False

    snippets: list[str] = []
    for rel in list_source_files(workspace):
        if rel.endswith((".tsx", ".ts")) and "data/mock" not in rel:
            body = read_file(workspace, rel)
            if "data/mock" in body or "from '../data/mock" in body or 'from "../data/mock' in body:
                snippets.append(f"=== {rel} ===\n{body[:4000]}")
    import_context = "\n\n".join(snippets[:12])[:24000]

    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_MOCK_SYNTHESIZE,
        full_context=full_context[:10000],
        plan_json=json.dumps(plan, ensure_ascii=False, indent=2)[:12000],
        routes_json=json.dumps(architect.get("routes", []), ensure_ascii=False, indent=2)[:4000],
        manifest_json=json.dumps(manifest, ensure_ascii=False, indent=2),
        images_json=json.dumps(images, ensure_ascii=False, indent=2),
        required_exports=", ".join(needed),
        import_context=import_context,
        current_content=read_file(workspace, mock_path)[:4000],
    )
    raw = ai_provider.ask_chat(settings.PREVIEW_APP_MODEL, [{"role": "user", "content": prompt}], max_tokens=14000)
    content, _ = fix_unescaped_apostrophes(_strip_fences(raw))
    if not _valid_synthesized_mock_source(content, needed):
        return False
    write_file(workspace, mock_path, content)
    return True

def enrich_mock_if_sparse(
    workspace: Path,
    full_context: str,
    manifest: dict,
    images: dict,
    architect: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    plan: dict | None = None,
) -> bool:
    """Backward-compatible alias — always synthesize from page imports after codegen."""
    return synthesize_mock_data(
        workspace, full_context, plan or {}, manifest, images, architect, ai_provider, template_renderer,
    )
