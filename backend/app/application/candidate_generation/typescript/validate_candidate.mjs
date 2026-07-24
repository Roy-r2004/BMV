import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const [workspaceArg, typescriptArg] = process.argv.slice(2);
if (!workspaceArg || !typescriptArg) {
  process.stdout.write(
    JSON.stringify({ passed: false, diagnostics: ["missing arguments"] }),
  );
  process.exit(2);
}

const workspace = path.resolve(workspaceArg);
const typescriptPath = path.resolve(typescriptArg);
const templateNodeModules = path.dirname(path.dirname(typescriptPath));
const ts = require(typescriptPath);
const configPath = path.join(workspace, "tsconfig.app.json");
const configRead = ts.readConfigFile(configPath, ts.sys.readFile);
if (configRead.error) {
  process.stdout.write(
    JSON.stringify({
      passed: false,
      diagnostics: [ts.flattenDiagnosticMessageText(configRead.error.messageText, "\n")],
    }),
  );
  process.exit(1);
}

const parsed = ts.parseJsonConfigFileContent(
  configRead.config,
  ts.sys,
  workspace,
  { noEmit: true, incremental: false, tsBuildInfoFile: undefined },
  configPath,
);
const host = ts.createCompilerHost(parsed.options);
const originalResolve = host.resolveModuleNames?.bind(host);
host.resolveModuleNames = (moduleNames, containingFile) =>
  moduleNames.map((moduleName) => {
    const primary = ts.resolveModuleName(
      moduleName,
      containingFile,
      parsed.options,
      host,
    ).resolvedModule;
    if (primary || moduleName.startsWith(".") || moduleName.startsWith("@/")) {
      return primary;
    }
    const synthetic = path.join(templateNodeModules, "__phase3b__.ts");
    return ts.resolveModuleName(
      moduleName,
      synthetic,
      parsed.options,
      host,
    ).resolvedModule;
  });

const program = ts.createProgram({
  rootNames: parsed.fileNames,
  options: parsed.options,
  host,
});
const diagnostics = ts
  .getPreEmitDiagnostics(program)
  .map((diagnostic) => {
    const message = ts.flattenDiagnosticMessageText(diagnostic.messageText, "\n");
    if (!diagnostic.file || diagnostic.start == null) return message;
    const point = diagnostic.file.getLineAndCharacterOfPosition(diagnostic.start);
    const rel = path.relative(workspace, diagnostic.file.fileName).replaceAll("\\", "/");
    return `${rel}:${point.line + 1}:${point.character + 1} ${message}`;
  });

process.stdout.write(
  JSON.stringify({ passed: diagnostics.length === 0, diagnostics }),
);
process.exit(diagnostics.length === 0 ? 0 : 1);
