"""Mock data synthesis for preview workspaces."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from app.application.prompts import PromptTemplate
from app.application.preview_app.catalogue_contract import _source_tokens
from app.application.ui_catalogue import catalogue_prop_shape_block
from app.application.preview_app.mock_imports import _collect_mock_imports
from app.application.preview_app.source_quality import (
    fix_unescaped_apostrophes,
    looks_truncated_source,
)
from app.application.preview_app.text_utils import _bounded_json, _parse_json, _strip_fences
from app.application.preview_app.workspace import list_source_files, read_file, write_file
from app.application.services.ai_context import UNUSABLE_REJECTED, ai_call
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

#: Wall clock a failover link needs before it is worth starting. The one seed
#: ask that succeeded across requests 146-161 took **63.9 s**, so a link handed
#: less than this cannot finish the work even if the model is healthy — starting
#: it would spend the run's remaining time to arrive at the same plumbing mock,
#: later. Deliberately measured rather than round.
_SEED_FAILOVER_FLOOR_SECONDS = 70.0


def _seed_model_chain() -> list[str]:
    """Which models the seed may ask, primary first, each id only once.

    Deduped for the reason `call_architect` documents: when two settings resolve
    to the same id, "fail over" means asking the identical model twice and
    paying twice for the same answer.
    """
    return list(
        dict.fromkeys(
            m
            for m in (
                settings.PREVIEW_APP_MODEL,
                settings.TEXT_MODEL,
                settings.ARCHITECT_MODEL,
            )
            if m
        )
    )


def _synthesize_mock_source(
    ai_provider: AIProvider, prompt: str, needed: list[str]
) -> str | None:
    """Ask each model in turn for a `mock.ts`; `None` when none of them delivers.

    **The seed was the one content-critical stage with no failover, and it was
    failing 87 % of the time.** Measured over the 57 stored `seed` asks: under
    `google/gemini-2.5-flash` (requests 72-98) it returned usable output on 19 of
    23 asks at a 27.0 s mean; under `deepseek/deepseek-v4-pro` (101 onward) it
    returned usable output on **4 of 31**, mean 66.1 s. In the two most recent
    trios it is **1 of 11** — the other ten are `provider_timeout` with
    `output_chars = 0`, six of them riding the 120 s ask cap to the millisecond.

    Nothing broke visibly, because the failure is silent by design: the caller
    keeps the plumbing mock. That is why a hardware store shipped *"Member
    aftercare"*, *"Follow-up visit"*, *"the owner hub's no-show risk view"* and
    `client_names: [… "Client 7", "Client 8"]` — the Brand-default seed with the
    business name pasted through it. Every catalogue defect filed against the
    writers since request 101 has been read off runs where **the writer never
    answered at all**.

    Each link is its own logical ask, numbered, for the reason the architect
    chain states: collapsing them into one row is how a model that reliably
    fails keeps looking free. A link is only started when `ask_budget_seconds()`
    leaves room to finish it, so the chain cannot spend a deadline it has
    already lost — past the deadline the budget is 0.0 and the loop stops
    without making a call.

    Model *order* is deliberately left to settings and is not decided here. On
    the measured numbers the primary is the weakest link in the chain, which is
    a configuration question for the owner, not something to bury in a retry.
    """
    from app.application.services.request_deadline import (
        ask_budget_seconds,
        record_degradation,
    )

    chain = _seed_model_chain()
    provider_failed = False
    for attempt, model in enumerate(chain, start=1):
        if attempt > 1 and ask_budget_seconds() < _SEED_FAILOVER_FLOOR_SECONDS:
            cg_log.warning(
                "    mock synthesis: no time for %s — keeping the plumbing mock", model
            )
            record_degradation("codegen", "mock_synthesis_failover_out_of_time")
            return None
        try:
            with ai_call("seed", writer="mock_synthesize", attempt=attempt) as call:
                raw = ai_provider.ask_chat(
                    model, [{"role": "user", "content": prompt}], max_tokens=14000
                )
                content, _ = fix_unescaped_apostrophes(_strip_fences(raw))
                if _valid_synthesized_mock_source(content, needed):
                    call.mark_usable()
                    return content
                call.unusable(UNUSABLE_REJECTED)
        except Exception as exc:
            provider_failed = True
            cg_log.warning(
                "    mock synthesis failed on %s (%s: %s)",
                model,
                type(exc).__name__,
                exc,
            )

    # An unusable *answer* is not an outage. Every model was reached, every ask
    # was adjudicated, and the rejection is already on those rows; recording a
    # degradation as well would make "the provider never answered" and "the
    # provider answered badly" indistinguishable in the one field that exists to
    # tell them apart. Only a link that raised earns the marker.
    if provider_failed:
        record_degradation("codegen", "mock_synthesis_failed_plumbing_mock_kept")
    cg_log.warning(
        "    mock synthesis produced nothing on %d model(s) — keeping the plumbing mock",
        len(chain),
    )
    return None


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
        # The template's CATALOGUE ITEM SHAPES section was authored for this
        # call and guarded with `is defined` — without this kwarg it never
        # renders and the model invents member names the components don't read.
        catalogue_prop_shapes=catalogue_prop_shape_block(),
        current_content=read_file(workspace, mock_path)[:4000],
    )
    # 1.12. A provider failure here used to leave the function by raising, out of
    # `run_codegen_phase` and out of `generate_preview_app` — requests 101 and 102
    # died exactly this way and stored nothing, having already built a complete
    # workspace. `write_plumbing_mock` wrote a full `mock.ts` back in the plan
    # phase (both of those workspaces have one; the derived palette was proven
    # *from* it), so the deterministic path is simply to keep that file.
    #
    # The scope is settled in `ai_call`'s `finally`, so the usage row is written
    # either way and the catch belongs outside the `with`, not inside it. The
    # function's own contract already says False means "mock.ts was not
    # rewritten" — this is that answer, with a record beside it.
    content = _synthesize_mock_source(ai_provider, prompt, needed)
    if content is None:
        return False
    # The model is handed the whole slot map and tends to restate part of it
    # alongside its own named keys. Request 66 emitted `item4`…`item8` twice and
    # `tsc` reported five TS1117s. Rejecting the file over it would cost the
    # whole synthesis; last-wins is what the engine does anyway.
    from app.application.preview_app.safety.mock_data import dedupe_object_literal_keys

    for export_name in ("images", "seed", "navigation"):
        content = dedupe_object_literal_keys(content, export_name)
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
