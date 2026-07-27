import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const [typescriptArg] = process.argv.slice(2);
if (!typescriptArg) {
  process.stdout.write(JSON.stringify({
    edits: [],
    issues: [{ code: "generated_candidate_type_normalizer_error", message: "missing TypeScript compiler argument" }],
  }));
  process.exit(2);
}

let request;
try {
  request = JSON.parse(fs.readFileSync(0, "utf8"));
} catch {
  process.stdout.write(JSON.stringify({
    edits: [],
    issues: [{ code: "generated_candidate_type_normalizer_error", message: "invalid JSON request" }],
  }));
  process.exit(2);
}

const ts = require(path.resolve(typescriptArg));
const workspace = path.resolve(request.workspace_root || process.cwd());
const targetPath = path.join(workspace, request.path);
const contentDataPath = path.join(workspace, "src/generated/content-data.ts");
const files = new Map([
  [targetPath, String(request.source || "")],
  [contentDataPath, String(request.content_data_module || "")],
]);
const compilerOptions = {
  target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.ESNext,
  moduleResolution: ts.ModuleResolutionKind.Bundler,
  jsx: ts.JsxEmit.ReactJSX,
  strict: true,
  verbatimModuleSyntax: true,
  baseUrl: workspace,
  paths: { "@/*": ["src/*"] },
  skipLibCheck: true,
  noEmit: true,
};
const host = ts.createCompilerHost(compilerOptions, true);
const originalReadFile = host.readFile.bind(host);
const originalFileExists = host.fileExists.bind(host);
host.readFile = (fileName) => files.get(path.resolve(fileName)) ?? originalReadFile(fileName);
host.fileExists = (fileName) => files.has(path.resolve(fileName)) || originalFileExists(fileName);
host.getSourceFile = (fileName, languageVersion) => {
  const text = host.readFile(fileName);
  return text == null ? undefined : ts.createSourceFile(fileName, text, languageVersion, true);
};
host.resolveModuleNames = (moduleNames, containingFile) => moduleNames.map((moduleName) => {
  if (moduleName === "@/generated/content-data" || moduleName.endsWith("/generated/content-data")) {
    return { resolvedFileName: contentDataPath, extension: ts.Extension.Ts, isExternalLibraryImport: false };
  }
  return ts.resolveModuleName(moduleName, containingFile, compilerOptions, host).resolvedModule;
});

const program = ts.createProgram({ rootNames: [targetPath, contentDataPath], options: compilerOptions, host });
const checker = program.getTypeChecker();
const sourceFile = program.getSourceFile(targetPath);
if (!sourceFile) {
  process.stdout.write(JSON.stringify({
    edits: [],
    issues: [{ code: "generated_candidate_type_normalizer_error", message: "target source unavailable" }],
  }));
  process.exit(1);
}

const source = sourceFile.text;
const edits = [];
const issues = [];

function aliasedSymbol(node) {
  const symbol = checker.getSymbolAtLocation(node);
  return symbol && (symbol.flags & ts.SymbolFlags.Alias)
    ? checker.getAliasedSymbol(symbol) || symbol
    : symbol;
}

function symbolKey(node) {
  const symbol = aliasedSymbol(node);
  const declaration = symbol?.declarations?.[0];
  return declaration
    ? `${symbol.getName()}:${declaration.getSourceFile().fileName}:${declaration.pos}`
    : symbol?.getName();
}

function isTypePosition(node) {
  let current = node;
  while (current.parent) {
    const parent = current.parent;
    if (ts.isTypeQueryNode(parent)) return false;
    if (ts.isImportDeclaration(parent) || ts.isImportSpecifier(parent)) return false;
    if (ts.isTypeNode(parent)) return true;
    current = parent;
  }
  return false;
}

function importedUsage(local) {
  const declarationKey = symbolKey(local);
  let typeOnly = false;
  let value = false;
  function visit(node) {
    if (ts.isIdentifier(node) && node.text === local.text && node !== local) {
      if (symbolKey(node) === declarationKey) {
        if (isTypePosition(node)) typeOnly = true;
        else value = true;
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
  return { typeOnly, value };
}

function sourceText(node) {
  return source.slice(node.getStart(sourceFile), node.getEnd());
}

function addImportEdit(declaration, replacement, typeSymbols, valueSymbols, reason) {
  const original = sourceText(declaration);
  if (original === replacement) return;
  edits.push({
    start: declaration.getStart(sourceFile),
    end: declaration.getEnd(),
    original,
    replacement,
    type_symbols: typeSymbols,
    value_symbols: valueSymbols,
    reason,
  });
}

function normalizeNamedImport(declaration, clause, bindings) {
  const typeElements = [];
  const valueElements = [];
  let changed = false;
  for (const element of bindings.elements) {
    const usage = importedUsage(element.name);
    if (!usage.typeOnly && !usage.value) {
      valueElements.push(sourceText(element));
      continue;
    }
    if (usage.value) valueElements.push(sourceText(element));
    else typeElements.push(sourceText(element));
    changed = changed || (!usage.value && !clause.isTypeOnly) || (usage.value && clause.isTypeOnly);
  }
  if (!changed) return;
  const moduleText = sourceText(declaration.moduleSpecifier);
  const defaultText = clause.name ? sourceText(clause.name) : "";
  const typePrefix = defaultText && !valueElements.length
    ? `import type ${defaultText}, { ${typeElements.join(", ")} } from ${moduleText};`
    : typeElements.length
      ? `import type { ${typeElements.join(", ")} } from ${moduleText};`
      : "";
  const valuePrefix = defaultText
    ? valueElements.length
      ? `import ${defaultText}, { ${valueElements.join(", ")} } from ${moduleText};`
      : `import ${defaultText} from ${moduleText};`
    : valueElements.length
      ? `import { ${valueElements.join(", ")} } from ${moduleText};`
      : "";
  const replacement = [typePrefix, valuePrefix].filter(Boolean).join("\n");
  addImportEdit(
    declaration,
    replacement,
    typeElements,
    valueElements,
    "normalize_type_only_imports",
  );
}

function normalizeNamespaceOrDefaultImport(declaration, clause) {
  const binding = clause.name || clause.namedBindings?.name;
  if (!binding) return;
  const usage = importedUsage(binding);
  if (!usage.typeOnly || usage.value || clause.isTypeOnly) return;
  const moduleText = sourceText(declaration.moduleSpecifier);
  const bindingText = sourceText(binding);
  const replacement = clause.namedBindings && ts.isNamespaceImport(clause.namedBindings)
    ? `import type * as ${bindingText} from ${moduleText};`
    : `import type ${bindingText} from ${moduleText};`;
  addImportEdit(
    declaration,
    replacement,
    [bindingText],
    [],
    "normalize_type_only_imports",
  );
}

function normalizeImports(node) {
  if (ts.isImportDeclaration(node) && node.importClause) {
    const clause = node.importClause;
    if (clause.namedBindings && ts.isNamedImports(clause.namedBindings)) {
      normalizeNamedImport(node, clause, clause.namedBindings);
    } else {
      normalizeNamespaceOrDefaultImport(node, clause);
    }
  }
  ts.forEachChild(node, normalizeImports);
}

function jsxTypeReferences(node) {
  const references = [];
  function visit(current) {
    if (
      ts.isIdentifier(current)
      && current.text === "JSX"
      && ts.isQualifiedName(current.parent)
      && current.parent.left === current
      && isTypePosition(current)
    ) {
      references.push(current);
    }
    ts.forEachChild(current, visit);
  }
  visit(node);
  return references;
}

function hasReactJsxTypeImport() {
  let found = false;
  function visit(node) {
    if (
      ts.isImportDeclaration(node)
      && ts.isStringLiteral(node.moduleSpecifier)
      && node.moduleSpecifier.text === "react"
      && node.importClause?.namedBindings
      && ts.isNamedImports(node.importClause.namedBindings)
      && node.importClause.namedBindings.elements.some((element) => (
        (element.propertyName?.text || element.name.text) === "JSX"
      ))
    ) found = true;
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
  return found;
}

function hasUnrelatedJsxBinding() {
  let found = false;
  function visit(node) {
    if (
      (ts.isVariableDeclaration(node) || ts.isFunctionDeclaration(node) || ts.isClassDeclaration(node))
      && node.name
      && ts.isIdentifier(node.name)
      && node.name.text === "JSX"
    ) found = true;
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
  return found;
}

normalizeImports(sourceFile);
const jsxReferences = jsxTypeReferences(sourceFile);
if (jsxReferences.length && !hasReactJsxTypeImport()) {
  if (hasUnrelatedJsxBinding()) {
    issues.push({
      code: "generated_candidate_jsx_ambiguous",
      message: "JSX type references collide with a non-import JSX binding and cannot be normalized safely.",
    });
  } else {
    const imports = sourceFile.statements.filter(ts.isImportDeclaration);
    const insertion = imports.length
      ? imports[imports.length - 1].getEnd() + (source.slice(imports[imports.length - 1].getEnd()).startsWith("\r\n") ? 2 : 1)
      : 0;
    edits.push({
      start: insertion,
      end: insertion,
      original: "",
      replacement: 'import type { JSX } from "react";\n',
      type_symbols: ["JSX"],
      value_symbols: [],
      reason: "normalize_react_jsx_type_namespace",
    });
  }
}

const ordered = [...edits].sort((left, right) => left.start - right.start || left.end - right.end);
for (let index = 1; index < ordered.length; index += 1) {
  if (ordered[index].start < ordered[index - 1].end) {
    issues.push({
      code: "generated_candidate_type_normalizer_conflict",
      message: "TypeScript normalization produced overlapping compiler-AST edits.",
    });
    break;
  }
}
process.stdout.write(JSON.stringify({ edits: issues.length ? [] : ordered, issues }));
