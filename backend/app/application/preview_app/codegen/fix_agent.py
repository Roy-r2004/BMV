"""AI fix agent for Vite build errors and TypeScript contract violations."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from app.application.prompts import PromptTemplate
from app.application.preview_app.catalogue_contract import blocking_contract_errors, enforce_catalogue_page_contract
from app.application.preview_app.codegen.architect import (
    _architect_prompt_context,
    _catalogue_routes_context,
    _route_for_file,
)
from app.application.preview_app.codegen.shared import (
    _catalogue_contract_errors,
    _catalogue_retry_context,
)
from app.application.preview_app.text_utils import (
    _bounded_json,
    _strip_fences,
    parse_json_with_meta,
)
from app.application.preview_app.typecheck import (
    TypecheckReport,
    collect_type_declarations,
    format_diagnostics,
)
from app.application.preview_app.fallback import record_stubbed_path, clear_stubbed_path
from app.application.preview_app.protected_paths import (
    has_catalogue_routes,
    is_generator_owned_path,
    is_template_owned_path,
    safe_source_path,
)
from app.application.preview_app.source_quality import (
    looks_truncated_source,
    tsx_parse_error,
)
from app.application.preview_app.workspace import list_source_files, read_file, write_file
from app.application.services.ai_context import UNUSABLE_UNPARSEABLE, ai_call
from app.application.ui_catalogue import infer_section_slots, skeleton_contract_for_prompt
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.infrastructure.logging import get_logger
from app.infrastructure.logging.diagnostics import analyze_json_response, dump_unparsed_fix_agent_response

fix_log = get_logger("FixAgent")

# Kept as one shared rule with `quality_repair.RepairAPI._safe`. These two
# writers disagreeing about `App.tsx` is what let request 67's repair delete a
# route declaration — see `protected_paths._GENERATOR_OWNED_BASENAMES`.

# A "fix" that satisfies the compiler by removing the feature trades a visible
# defect for an invisible one. These patterns are the three ways that happens.
_JSX_COMPONENT_RE = re.compile(r"<\s*([A-Z][A-Za-z0-9_]*)")
_ANY_CAST_RE = re.compile(
    r"\bas\s+any\b|\bas\s+unknown\b|:\s*any\b|<any>|@ts-ignore|@ts-expect-error|@ts-nocheck"
)
_EMPTY_PROP_RE = re.compile(r"([A-Za-z_$][\w$]*)\s*=\s*\{\s*\[\s*\]\s*\}")
_EMPTY_ENTRY_RE = re.compile(r"([A-Za-z_$][\w$]*)\s*:\s*\[\s*\]")
_FILLED_PROP_RE = re.compile(r"([A-Za-z_$][\w$]*)\s*=\s*\{\s*\[\s*[^\]\s]")
_FILLED_ENTRY_RE = re.compile(r"([A-Za-z_$][\w$]*)\s*:\s*\[\s*[^\]\s]")

# Guard callable: (path, before, after) -> rejection reason ("" accepts).
FixGuard = Callable[[str, str, str], str]


def _component_usages(source: str) -> set[str]:
    return set(_JSX_COMPONENT_RE.findall(source or ""))


def _emptied_collections(before: str, after: str) -> list[str]:
    emptied = {
        name
        for pattern in (_EMPTY_PROP_RE, _EMPTY_ENTRY_RE)
        for name in pattern.findall(after or "")
    }
    filled = {
        name
        for pattern in (_FILLED_PROP_RE, _FILLED_ENTRY_RE)
        for name in pattern.findall(before or "")
    }
    already_empty = {
        name
        for pattern in (_EMPTY_PROP_RE, _EMPTY_ENTRY_RE)
        for name in pattern.findall(before or "")
    }
    return sorted((emptied & filled) - already_empty)


def regressive_fix_reason(path: str, before: str, after: str) -> str:
    """Reject a patch that satisfies the compiler by removing content.

    Deleting a component usage, replacing real data with `[]`, or casting to
    `any` all silence `tsc` while making the rendered page emptier — the exact
    defect this loop exists to remove.
    """
    if not (before or "").strip() or not (after or "").strip():
        return ""
    dropped = sorted(_component_usages(before) - _component_usages(after))
    if dropped:
        return f"{path}: deletes component usage(s) {', '.join(dropped[:6])}"
    emptied = _emptied_collections(before, after)
    if emptied:
        return f"{path}: empties data collection(s) {', '.join(emptied[:6])}"
    added_casts = len(_ANY_CAST_RE.findall(after)) - len(_ANY_CAST_RE.findall(before))
    if added_casts > 0:
        return f"{path}: adds {added_casts} `any`/ts-ignore escape hatch(es)"
    return ""


def _fix_prompt_inputs(
    workspace: Path,
    architect: dict,
    error_text: str,
    max_files: int,
) -> tuple[str, str]:
    paths = [
        path
        for path in list_source_files(workspace)
        if not is_template_owned_path(path, architect)
    ]
    # Prioritise files explicitly named in the errors, then App/pages/mock.
    errored = [p for p in paths if p.split("/")[-1] in error_text or p in error_text]

    def _rank(p: str) -> tuple:
        return (
            0 if p in errored else 1,
            0 if "App.tsx" in p else 1 if "/pages/" in p else 2 if "mock.ts" in p else 3,
            p,
        )

    priority = sorted(paths, key=_rank)[:max_files]

    files_content = "\n\n".join(
        f"=== {p} ===\n{read_file(workspace, p)[:6000]}" for p in priority
    )
    file_tree = "\n".join(sorted(paths))
    return files_content, file_tree


#: Models that failed on this worker, so a repair loop stops re-paying for them.
#: Not persisted: a provider outage is per-run, and a fresh request should try the
#: configured model again.
_FAILED_FIX_MODELS: set[str] = set()


def fix_model_candidates(chain) -> tuple[list[str], bool]:
    """Resolve a model chain to the ids actually worth asking, in order.

    Two settings resolving to the same id is the default, not an edge case:
    `FIX_MODEL` defaults to `PREVIEW_APP_MODEL` and `QUALITY_FIX_MODEL` defaults
    to `FIX_MODEL` (`config.py:300-312`), so the gate repair's four-name chain
    resolved to two distinct models, each asked twice in a row. A model that just
    failed does not succeed when asked again one millisecond later; it costs
    another timeout.

    Returns `(candidates, exhausted)`. `exhausted` is True when every model in the
    chain has already failed this process — the caller then tries them anyway,
    because a provider outage can end and an empty chain would disable repair for
    the life of the worker.
    """
    ordered = list(dict.fromkeys(m for m in chain if m))
    fresh = [m for m in ordered if m not in _FAILED_FIX_MODELS]
    if fresh:
        return fresh, False
    return ordered, True


def _ask_fix_model(ai_provider: AIProvider, prompt_text: str) -> str:
    """Ask the fix chain, skipping models that already failed this process.

    `FIX_MODEL` failed on every observed run: request 39 returned unparseable
    JSON, request 40 spent 230s and came back `Provider output was truncated`, and
    request 42 did it again a round later. Each failure is a wall-clock charge
    before the fallback does the actual work — the typecheck repair took 6m10s of
    request 40's 13m28s and landed nothing. Remembering the failure inside a run
    turns three of those into one.
    """
    chain = [settings.FIX_MODEL, settings.PREVIEW_APP_MODEL, settings.TEXT_MODEL]
    ordered, exhausted = fix_model_candidates(chain)
    for model in ordered:
        # Re-checked per iteration, not just when the list was built: a failure
        # recorded by a concurrent run mid-loop is still a failure.
        if not exhausted and model in _FAILED_FIX_MODELS:
            fix_log.info("fix agent skipping %s — already failed this process", model)
            continue
        try:
            raw = ai_provider.ask_chat(
                model, [{"role": "user", "content": prompt_text}], max_tokens=16000,
            )
        except Exception as e:
            fix_log.warning("fix agent model %s failed: %s", model, e)
            _FAILED_FIX_MODELS.add(model)
            continue
        if raw and str(raw).strip():
            return str(raw)
        fix_log.warning("fix agent model %s returned nothing", model)
        _FAILED_FIX_MODELS.add(model)
    return ""


def _parse_fix_payload(
    workspace: Path,
    raw: str,
    label: str,
    error_text: str,
) -> dict | None:
    if not raw or not raw.strip():
        fix_log.warning("fix agent %s: empty response", label)
        return None
    try:
        parsed, meta = parse_json_with_meta(raw)
        if isinstance(parsed, dict):
            if meta.get("method") not in ("direct", "fence"):
                # Says out loud that the response arrived intact and needed
                # salvage — the failure mode that was logged as truncation.
                fix_log.info(
                    "fix agent %s: recovered via %s (len=%s)", label, meta.get("method"), len(raw)
                )
            return parsed
        fix_log.warning(
            "fix agent %s: JSON was %s, expected object", label, type(parsed).__name__
        )
        return None
    except Exception as e:
        analysis = analyze_json_response(raw)
        dump_unparsed_fix_agent_response(
            workspace,
            label=label,
            raw=raw,
            error=e,
            build_errors=error_text[:3000] if error_text else None,
        )
        fix_log.error(
            "fix agent %s parse diagnostics: len=%s lines=%s fenced=%s "
            "brace_imbalance=%s likely_truncated=%s files_key=%s",
            label,
            analysis["length"],
            analysis["lines"],
            analysis["fenced"],
            analysis["depth_imbalance"],
            analysis["likely_truncated"],
            analysis["has_files_key"],
        )
        return None


def _run_fix_agent(
    workspace: Path,
    architect: dict,
    ai_provider: AIProvider,
    *,
    prompt: str,
    error_text: str,
    guard: FixGuard | None = None,
    rejections_out: list[str] | None = None,
) -> list[str]:
    """Ask the fix chain and apply what it returns. Census-instrumented.

    The outer `ai_call` exists only so `ops_applied` — known once the paths have
    been written, several branches below — lands on the rows the inner scopes
    already adjudicated. Request 67 spent three fix-agent calls, two of them
    recorded `success = true`, for zero applied files; that pair of numbers on
    one row is the whole point.
    """

    with ai_call("fix_agent") as fix_scope:
        paths = _run_fix_agent_inner(
            workspace,
            architect,
            ai_provider,
            prompt=prompt,
            error_text=error_text,
            guard=guard,
            rejections_out=rejections_out,
        )
        fix_scope.applied_ops(len(paths))
        return paths


def _run_fix_agent_inner(
    workspace: Path,
    architect: dict,
    ai_provider: AIProvider,
    *,
    prompt: str,
    error_text: str,
    guard: FixGuard | None = None,
    rejections_out: list[str] | None = None,
) -> list[str]:
    def _ask(prompt_text: str) -> str:
        return _ask_fix_model(ai_provider, prompt_text)

    def _try_parse(raw: str, label: str) -> dict | None:
        return _parse_fix_payload(workspace, raw, label, error_text)

    def _ask_and_parse(prompt_text: str, label: str, attempt: int) -> dict | None:
        """One logical ask, with the verdict the parse hands down attached to it.

        A 200 whose body no extractor can read is not a success. Recording it as
        one is what let three dead calls per run hide behind a healthy-looking
        transport column.
        """

        with ai_call("fix_agent", writer=label, attempt=attempt) as call:
            parsed = _try_parse(_ask(prompt_text), label)
            call.adjudicate(parsed is not None, reason=UNUSABLE_UNPARSEABLE)
            return parsed

    data = _ask_and_parse(prompt, "primary", 1)

    if data is None:
        strict_prompt = (
            prompt
            + "\n\nSTRICT SCHEMA RETRY: Respond with ONLY a JSON object of shape "
            '{"files":[{"path":"src/pages/Example.tsx","content":"...full file..."}]}. '
            "No markdown fences, no prose, no empty body."
        )
        data = _ask_and_parse(strict_prompt, "strict-retry", 2)

    def _deterministic_local_repair() -> list[str]:
        from app.application.preview_app.deterministic_repairs import (
            run_deterministic_local_repairs,
        )

        return run_deterministic_local_repairs(workspace, architect)

    def _enforce_all_catalogue_pages(paths: list[str]) -> list[str]:
        enforced = list(paths)
        for route in architect.get("routes") or []:
            path = safe_source_path(route.get("component_file") or "", workspace)
            if not path or not route.get("skeleton_id"):
                continue
            current = read_file(workspace, path)
            guarded, replaced = enforce_catalogue_page_contract(path, current, architect)
            if replaced:
                write_file(workspace, path, guarded)
                record_stubbed_path(workspace, path)
                if path not in enforced:
                    enforced.append(path)
            elif "deterministic catalogue contract scaffold" in guarded:
                record_stubbed_path(workspace, path)
            else:
                clear_stubbed_path(workspace, path)
        return enforced

    if data is None:
        repaired = _enforce_all_catalogue_pages(_deterministic_local_repair())
        fix_log.info(
            "fix agent fell back to deterministic local repair: %s",
            ", ".join(repaired) or "none",
        )
        return repaired

    fixed_paths: list[str] = []
    for item in data.get("files", []):
        path = safe_source_path(item.get("path", ""), workspace)
        content = item.get("content", "")
        if not path or not content:
            continue
        if (
            is_generator_owned_path(path, workspace)
            or is_template_owned_path(path, architect, workspace)
        ):
            continue
        route = _route_for_file(path, architect)
        candidate = _strip_fences(content)
        errors = blocking_contract_errors(
            _catalogue_contract_errors(path, candidate, route, workspace=workspace)
        )
        if errors:
            contract_json = _bounded_json(
                skeleton_contract_for_prompt(
                    str(route.get("skeleton_id") or ""),
                    infer_section_slots(route, str(route.get("skeleton_id") or "")),
                ),
                5000,
            )
            for retry_number in range(1, 3):
                contract_retry_prompt = (
                    _catalogue_retry_context(
                        errors=errors,
                        contract_json=contract_json,
                        rejected_source=candidate,
                        build_context=error_text,
                    )
                    + "\nRespond as JSON only with shape "
                    '{"files":[{"path":'
                    + json.dumps(path)
                    + ',"content":"...complete corrected file..."}]}.'
                )
                retry_data = _ask_and_parse(
                    contract_retry_prompt,
                    f"catalogue-contract-retry-{retry_number}",
                    retry_number,
                )
                if not retry_data:
                    continue
                replacement = next(
                    (
                        value.get("content", "")
                        for value in retry_data.get("files", [])
                        if safe_source_path(value.get("path", ""), workspace) == path
                    ),
                    "",
                )
                if not replacement:
                    continue
                candidate = _strip_fences(replacement)
                errors = blocking_contract_errors(
                    _catalogue_contract_errors(path, candidate, route, workspace=workspace)
                )
                if not errors:
                    break
        if guard is not None:
            rejection = guard(path, read_file(workspace, path), candidate)
            if rejection:
                fix_log.warning("fix agent patch REJECTED — %s", rejection)
                # The reason has to reach the next round's prompt. Logging it and
                # dropping it is why the model reoffered the same forbidden patch.
                if rejections_out is not None:
                    rejections_out.append(rejection)
                continue
        # A patch that does not parse must not replace source that did. Request 47's
        # artwork detail page was cut off mid-attribute — `<section className="py-16`
        # — so the source shipped unparseable while `dist/` kept an older build, and
        # `/artwork/1` quietly served the home page instead.
        previous = read_file(workspace, path)
        truncated = looks_truncated_source(candidate)
        parse_error = "" if truncated else tsx_parse_error(candidate)
        if (truncated or parse_error) and not tsx_parse_error(previous):
            reason = "truncated" if truncated else f"does not parse ({parse_error})"
            fix_log.warning("fix agent patch REJECTED — %s is %s", path, reason)
            if rejections_out is not None:
                rejections_out.append(f"{path}: patch was {reason}; return the COMPLETE file")
            continue
        fixed_content, replaced = enforce_catalogue_page_contract(
            path,
            candidate,
            architect,
        )
        write_file(workspace, path, fixed_content)
        if replaced:
            record_stubbed_path(workspace, path)
        elif route.get("skeleton_id"):
            if "deterministic catalogue contract scaffold" in fixed_content:
                record_stubbed_path(workspace, path)
            else:
                clear_stubbed_path(workspace, path)
        fixed_paths.append(path)

    # Always scrub known corruption / missing icon exports after AI patches.
    for path in _deterministic_local_repair():
        if path not in fixed_paths:
            fixed_paths.append(path)

    return _enforce_all_catalogue_pages(fixed_paths)


def fix_build_errors(
    workspace: Path,
    build_log: str,
    architect: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    max_files: int = 16,
) -> list[str]:
    files_content, file_tree = _fix_prompt_inputs(
        workspace, architect, build_log, max_files
    )
    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_FIX,
        build_errors=build_log[:7000],
        file_tree=file_tree[:4000],
        architect_json=_architect_prompt_context(architect),
        files_content=files_content[:40000],
        catalogue_mode=has_catalogue_routes(architect),
        catalogue_routes_json=_catalogue_routes_context(architect),
    )
    return _run_fix_agent(
        workspace,
        architect,
        ai_provider,
        prompt=prompt,
        error_text=build_log,
    )


def fix_type_errors(
    workspace: Path,
    report: TypecheckReport,
    architect: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    max_files: int = 12,
    prior_rejections: list[str] | None = None,
    rejections_out: list[str] | None = None,
) -> list[str]:
    """Repair TypeScript contract violations in a workspace that already builds.

    The compiler says which prop/item contract was broken; the kit's exported
    declarations say what the right shape is. Both go to the model, together
    with a hard prohibition on "fixing" the error by removing the feature.

    `prior_rejections` carries why the previous round's patches were thrown
    away, so a rejected approach is not simply reoffered; `rejections_out`
    collects this round's for the next one.
    """
    diagnostics_text = format_diagnostics(report)
    if not diagnostics_text:
        return []
    declarations = collect_type_declarations(workspace, report.diagnostics)
    files_content, file_tree = _fix_prompt_inputs(
        workspace, architect, diagnostics_text, max_files
    )
    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_FIX,
        typecheck_mode=True,
        type_errors=diagnostics_text,
        type_declarations=declarations,
        build_errors="",
        file_tree=file_tree[:4000],
        architect_json=_architect_prompt_context(architect),
        files_content=files_content[:40000],
        catalogue_mode=has_catalogue_routes(architect),
        catalogue_routes_json=_catalogue_routes_context(architect),
        prior_rejections=list(prior_rejections or [])[:12],
    )
    return _run_fix_agent(
        workspace,
        architect,
        ai_provider,
        prompt=prompt,
        error_text=diagnostics_text,
        guard=regressive_fix_reason,
        rejections_out=rejections_out,
    )
