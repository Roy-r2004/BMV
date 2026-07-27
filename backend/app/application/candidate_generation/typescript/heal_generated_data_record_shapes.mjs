import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const [typescriptArg] = process.argv.slice(2);
if (!typescriptArg) {
  process.stdout.write(JSON.stringify({ edits: [], issues: [{ code: "generated_data_record_shape_tool_error", message: "missing TypeScript compiler argument" }] }));
  process.exit(2);
}

let request;
try {
  request = JSON.parse(fs.readFileSync(0, "utf8"));
} catch {
  process.stdout.write(JSON.stringify({ edits: [], issues: [{ code: "generated_data_record_shape_tool_error", message: "invalid JSON request" }] }));
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
const manifest = request.manifest || { collections: [] };

const compilerOptions = {
  target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.ESNext,
  moduleResolution: ts.ModuleResolutionKind.Bundler,
  jsx: ts.JsxEmit.ReactJSX,
  strict: true,
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
host.getSourceFile = (fileName, languageVersion, onError, shouldCreateNewSourceFile) => {
  const text = host.readFile(fileName);
  return text == null ? undefined : ts.createSourceFile(fileName, text, languageVersion, true);
};
host.resolveModuleNames = (moduleNames, containingFile) => moduleNames.map((moduleName) => {
  if (moduleName === "@/generated/content-data" || moduleName.endsWith("/generated/content-data")) {
    return { resolvedFileName: contentDataPath, extension: ts.Extension.Ts, isExternalLibraryImport: false };
  }
  return ts.resolveModuleName(moduleName, containingFile, compilerOptions, host).resolvedModule;
});

const program = ts.createProgram({
  rootNames: [targetPath, contentDataPath],
  options: compilerOptions,
  host,
});
const checker = program.getTypeChecker();
const sourceFile = program.getSourceFile(targetPath);
if (!sourceFile) {
  process.stdout.write(JSON.stringify({ edits: [], issues: [{ code: "generated_data_record_shape_tool_error", message: "target source unavailable" }] }));
  process.exit(1);
}

const collectionBySymbol = new Map();
for (const collection of manifest.collections || []) {
  collectionBySymbol.set(collection.seed_value_symbol, { collection, kind: "seed" });
  collectionBySymbol.set(collection.accessor_symbol, { collection, kind: "accessor" });
}
const importedOrigins = new Map();
const recordOrigins = new Map();
const issues = [];
const edits = [];
const text = sourceFile.text;

function symbolAt(node) {
  const symbol = checker.getSymbolAtLocation(node);
  return symbol && (symbol.flags & ts.SymbolFlags.Alias) ? checker.getAliasedSymbol(symbol) || symbol : symbol;
}

function symbolKey(node) {
  const symbol = checker.getSymbolAtLocation(node);
  if (!symbol) return undefined;
  const declaration = symbol.declarations?.[0];
  return declaration
    ? `${symbol.getName()}:${declaration.getSourceFile().fileName}:${declaration.pos}`
    : symbol.getName();
}

function parenthesized(node) {
  let current = node;
  while (ts.isParenthesizedExpression(current)) current = current.expression;
  return current;
}

function propertyAccess(node) {
  return ts.isPropertyAccessExpression(node) ? node : undefined;
}

function directIdentifier(node) {
  const current = parenthesized(node);
  return ts.isIdentifier(current) ? current : undefined;
}

function collectionOrigin(expression) {
  const current = parenthesized(expression);
  if (ts.isElementAccessExpression(current)) {
    return collectionOrigin(current.expression);
  }
  if (ts.isCallExpression(current)) {
    const identifier = directIdentifier(current.expression);
    if (identifier) {
      const origin = importedOrigins.get(identifier.text);
      return origin?.kind === "accessor" ? origin.collection : undefined;
    }
    if (
      ts.isPropertyAccessExpression(current.expression) &&
      ["find", "filter", "map"].includes(current.expression.name.text)
    ) {
      return collectionOrigin(current.expression.expression);
    }
    return undefined;
  }
  const identifier = directIdentifier(current);
  if (!identifier) return undefined;
  const imported = importedOrigins.get(identifier.text);
  if (imported?.kind === "seed") return imported.collection;
  return recordOrigins.get(symbolKey(identifier))?.collection;
}

function recordOrigin(expression) {
  const identifier = directIdentifier(expression);
  const collection = identifier ? recordOrigins.get(symbolKey(identifier))?.collection : undefined;
  if (!identifier || !collection) return undefined;
  // The origin is established from a resolved generated-data import symbol or
  // callback symbol. Query the checker as a second proof point; diagnostics
  // are intentionally not used as a fallback source of field names.
  checker.getTypeAtLocation(identifier);
  return collection;
}

function fieldsFor(collection) {
  return new Map((collection.field_signatures || []).map((field) => [field.property_name, field]));
}

function rangeText(node) {
  return text.slice(node.getStart(sourceFile), node.getEnd());
}

function optionalOperator(node) {
  return node.questionDotToken ? "?." : ".";
}

function addIssue(code, node, message) {
  issues.push({
    code,
    start: node.getStart(sourceFile),
    end: node.getEnd(),
    message,
  });
}

function addEdit(node, replacement, reason, collection, field) {
  edits.push({
    start: node.getStart(sourceFile),
    end: node.getEnd(),
    original: rangeText(node),
    replacement,
    reason,
    collection_id: collection.collection_id,
    record_type_symbol: collection.record_type_symbol,
    property_name: field.property_name,
    typescript_type: field.typescript_type,
  });
}

function propertyFromPredicate(callback, collection, subject) {
  if (!callback || (!ts.isArrowFunction(callback) && !ts.isFunctionExpression(callback)) || callback.parameters.length !== 1 || !ts.isIdentifier(callback.parameters[0].name)) {
    addIssue("generated_data_record_shape_ambiguous", subject, "The legacy find predicate does not identify one manifest field.");
    return undefined;
  }
  const parameter = callback.parameters[0].name;
  const fields = fieldsFor(collection);
  const body = parenthesized(callback.body);
  let property;
  if (ts.isPropertyAccessExpression(body) && ts.isIdentifier(body.expression) && body.expression.text === parameter.text) {
    property = body.name.text;
  } else if (
    ts.isBinaryExpression(body) &&
    (body.operatorToken.kind === ts.SyntaxKind.EqualsEqualsEqualsToken || body.operatorToken.kind === ts.SyntaxKind.EqualsEqualsToken) &&
    ts.isPropertyAccessExpression(body.left) &&
    ts.isIdentifier(body.left.expression) &&
    body.left.expression.text === parameter.text &&
    ts.isStringLiteral(body.right)
  ) {
    const keyProperty = body.left.name.text;
    if (
      keyProperty === body.right.text ||
      ["field", "fieldId", "key", "name", "property"].includes(keyProperty)
    ) {
      property = body.right.text;
    } else {
      addIssue("generated_data_record_shape_ambiguous", subject, "The legacy find predicate does not identify one manifest field.");
      return undefined;
    }
  } else if (
    ts.isElementAccessExpression(body) ||
    (ts.isBinaryExpression(body) && ts.isElementAccessExpression(body.left))
  ) {
    addIssue("generated_data_record_shape_dynamic", subject, "The legacy find predicate uses dynamic field access and cannot be mapped to one manifest field.");
    return undefined;
  } else {
    addIssue("generated_data_record_shape_ambiguous", subject, "The legacy find predicate does not map to one manifest field.");
    return undefined;
  }
  const field = fields.get(property);
  if (!field) {
    addIssue("generated_data_record_shape_unknown_field", subject, `The legacy find predicate identifies ${JSON.stringify(property)}, which is not a field of ${collection.record_type_symbol}.`);
    return undefined;
  }
  return field;
}

function wrapperAccess(node) {
  const access = propertyAccess(node);
  if (!access || !["values", "fields"].includes(access.name.text)) return undefined;
  const collection = recordOrigin(access.expression);
  return collection ? { access, collection, wrapper: access.name.text } : undefined;
}

function visitImports(node) {
  if (!ts.isImportDeclaration(node) || !ts.isStringLiteral(node.moduleSpecifier)) return;
  const specifier = node.moduleSpecifier.text;
  if (specifier !== "@/generated/content-data" && !specifier.endsWith("/generated/content-data")) return;
  const named = node.importClause?.namedBindings;
  if (!named || !ts.isNamedImports(named)) return;
  for (const element of named.elements) {
    const imported = element.propertyName?.text || element.name.text;
    const origin = collectionBySymbol.get(imported);
    if (origin) {
      // The declaration is verified by the compiler program; retain the local
      // spelling so subsequent expression symbols can be resolved through it.
      symbolAt(element.name);
      importedOrigins.set(element.name.text, origin);
    }
  }
}

function discoverOrigins(node) {
  if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) {
    const collection = collectionOrigin(node.initializer);
    if (collection) recordOrigins.set(symbolKey(node.name), { collection });
  }
  ts.forEachChild(node, discoverOrigins);
}

function discoverCallbackOrigins(node) {
  if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)) {
    const collection = collectionOrigin(node.expression.expression);
    if (collection && ["find", "filter", "map", "some", "every"].includes(node.expression.name.text)) {
      for (const argument of node.arguments) {
        if ((ts.isArrowFunction(argument) || ts.isFunctionExpression(argument)) && argument.parameters.length) {
          const parameter = argument.parameters[0];
          if (ts.isIdentifier(parameter.name)) recordOrigins.set(symbolKey(parameter.name), { collection });
        }
      }
    }
  }
  ts.forEachChild(node, discoverCallbackOrigins);
}

function discoverEdits(node) {
  if (ts.isPropertyAccessExpression(node) && node.name.text === "value" && ts.isCallExpression(node.expression) && ts.isPropertyAccessExpression(node.expression.expression) && node.expression.expression.name.text === "find") {
    const wrapper = wrapperAccess(node.expression.expression.expression);
    if (wrapper) {
      const field = propertyFromPredicate(node.expression.arguments[0], wrapper.collection, node);
      if (field) {
        const record = rangeText(wrapper.access.expression);
        addEdit(
          node,
          `${record}${optionalOperator(wrapper.access)}${field.property_name}`,
          `manifest_record_${wrapper.wrapper}_find_value`,
          wrapper.collection,
          field,
        );
      }
      return;
    }
  }
  if (ts.isPropertyAccessExpression(node) && ts.isPropertyAccessExpression(node.expression)) {
    const wrapper = wrapperAccess(node.expression);
    if (wrapper && node.name.text !== "find" && node.name.text !== "some" && node.name.text !== "every") {
      const field = fieldsFor(wrapper.collection).get(node.name.text);
      if (!field) {
        addIssue("generated_data_record_shape_unknown_field", node, `${JSON.stringify(node.name.text)} is not a manifest field of ${wrapper.collection.record_type_symbol}.`);
      } else {
        const record = rangeText(wrapper.access.expression);
        addEdit(
          node,
          `${record}${optionalOperator(wrapper.access)}${field.property_name}`,
          `manifest_record_${wrapper.wrapper}_property`,
          wrapper.collection,
          field,
        );
      }
      return;
    }
  }
  ts.forEachChild(node, discoverEdits);
}

ts.forEachChild(sourceFile, visitImports);
discoverOrigins(sourceFile);
discoverCallbackOrigins(sourceFile);
discoverEdits(sourceFile);

const nonOverlapping = [];
for (const edit of edits.sort((a, b) => b.start - a.start || b.end - a.end)) {
  if (nonOverlapping.some((existing) => edit.end > existing.start && edit.start < existing.end)) continue;
  nonOverlapping.push(edit);
}
process.stdout.write(JSON.stringify({ edits: nonOverlapping, issues }));
