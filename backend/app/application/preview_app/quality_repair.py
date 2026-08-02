"""Dynamic quality repair — AI proposes ops/script/rewrites; we apply in a sandbox.

Safety model:
- Checks stay fixed (quality_gate). Only *fixes* are dynamic.
- All writes must pass safe_source_path (src/ only, no traversal).
- Template-owned UI files are never rewritten.
- Scripts cannot import/open/exec; they only call injected read/write/replace.
- Attempt-capped; never marks ready without re-passing the gate.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.application.preview_app.protected_paths import (
    is_generator_owned_path,
    is_template_owned_path,
    safe_source_path,
)
from app.application.preview_app.source_quality import tsx_parse_error
from app.application.preview_app.text_utils import _strip_fences, parse_json_with_meta
from app.application.preview_app.workspace import (
    list_source_files,
    read_file,
    restore_source,
    snapshot_source,
    write_file,
)
from app.application.services.ai_context import UNUSABLE_UNPARSEABLE, ai_call
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.infrastructure.logging import get_logger
from app.infrastructure.logging.diagnostics import (
    analyze_json_response,
    dump_unparsed_fix_agent_response,
)

log = get_logger("QualityRepair")

_FORBIDDEN_SCRIPT = re.compile(
    r"\b(__import__|import|open|exec|eval|compile|subprocess|socket|ctypes|"
    r"os\.|sys\.|pathlib|Path\s*\(|globals|locals|getattr|setattr|delattr|"
    r"__builtins__|breakpoint)\b",
    re.I,
)

_SAFE_BUILTINS: dict[str, Any] = {
    "True": True,
    "False": False,
    "None": None,
    "len": len,
    "str": str,
    "int": int,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "min": min,
    "max": max,
    "sum": sum,
    "any": any,
    "all": all,
    "print": print,
    "re": re,
}


class RepairAPI:
    """Injected API for sandboxed repair scripts."""

    def __init__(self, workspace: Path, architect: dict[str, Any] | None = None) -> None:
        self.workspace = Path(workspace)
        self.architect = architect or {}
        self.touched: list[str] = []

    def _safe(self, path: str) -> str:
        canonical = safe_source_path(path, self.workspace)
        if not canonical:
            raise ValueError(f"unsafe path: {path!r}")
        if is_template_owned_path(canonical, self.architect, self.workspace):
            raise ValueError(f"template-owned path blocked: {canonical}")
        if is_generator_owned_path(canonical, self.workspace):
            raise ValueError(f"generator-owned path blocked: {canonical}")
        return canonical

    def list_files(self) -> list[str]:
        return [
            p
            for p in list_source_files(self.workspace)
            if not is_template_owned_path(p, self.architect, self.workspace)
            and not is_generator_owned_path(p, self.workspace)
        ]

    def read(self, path: str) -> str:
        return read_file(self.workspace, self._safe(path)) or ""

    def _write_if_parseable(self, rel: str, updated: str, previous: str) -> bool:
        """Write `updated`, unless it breaks source that parsed before.

        Request 45's gate lost both of its AI repair attempts to
        `rebuild after AI repair failed` — a repair that cannot compile costs a
        full `vite build` to discover and takes its whole batch down with it. Only
        `.tsx`/`.ts` are checked, and only when the previous content parsed: a file
        that was already broken is exactly what a repair is for.
        """
        if not rel.endswith((".ts", ".tsx")):
            write_file(self.workspace, rel, updated)
            return True
        error = tsx_parse_error(updated)
        if error and not tsx_parse_error(previous):
            log.warning("repair rejected — %s would not parse (%s)", rel, error)
            return False
        write_file(self.workspace, rel, updated)
        return True

    def write(self, path: str, content: str) -> None:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("write requires non-empty string content")
        rel = self._safe(path)
        if not self._write_if_parseable(rel, content, read_file(self.workspace, rel) or ""):
            return
        if rel not in self.touched:
            self.touched.append(rel)

    def replace(self, path: str, old: str, new: str, count: int = 0) -> int:
        if not isinstance(old, str) or old == "":
            raise ValueError("replace requires non-empty old string")
        if not isinstance(new, str):
            raise ValueError("replace requires string new")
        rel = self._safe(path)
        src = read_file(self.workspace, rel) or ""
        if old not in src:
            return 0
        if count and count > 0:
            updated = src.replace(old, new, count)
        else:
            updated = src.replace(old, new)
        if updated != src:
            if not self._write_if_parseable(rel, updated, src):
                return 0
            if rel not in self.touched:
                self.touched.append(rel)
        return src.count(old) if not count else min(count, src.count(old))


def apply_repair_ops(
    workspace: Path,
    ops: list[dict[str, Any]],
    architect: dict[str, Any] | None = None,
) -> list[str]:
    """Apply structured ops: replace | write. Returns touched paths.

    All or nothing. A plan's ops are written against each other: request 47's tried
    to create `src/ui/QuantityAdjuster.tsx`, which is correctly refused as
    template-owned — and the *other* ops in that plan had already imported it, so a
    half-applied plan left a page referencing a component that does not exist and
    cost a full `vite build` to find out. If any op is refused, the workspace goes
    back to how the plan found it.
    """
    api = RepairAPI(workspace, architect)

    # Check every path before touching anything. All-or-nothing is right — the
    # ops are written against each other — but combining it with a
    # *discovered-on-the-way* refusal is how request 68 lost eight good ops to
    # one bad path: the plan arrived at t=1,581 s, op seven named `src/App.tsx`,
    # and the rollback threw away a fix for the catalogue that had nothing to do
    # with it. The run then shipped nothing at all.
    #
    # Refusing up front costs one pass over a list and turns "the plan was
    # discarded" into "the plan named a path it may not write", which is a
    # sentence a re-ask can act on.
    blocked: list[str] = []
    for raw in ops or []:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("op") or "").strip().lower() not in {"replace", "write"}:
            continue
        try:
            api._safe(str(raw.get("path") or ""))
        except Exception as exc:  # noqa: BLE001 — the message is the payload
            blocked.append(f"{raw.get('path')!r} ({exc})")
    if blocked:
        log.warning(
            "quality repair plan REFUSED before any write — %s of %s op(s) name a "
            "path the plan may not touch: %s",
            len(blocked),
            len(ops or []),
            "; ".join(blocked[:4]),
        )
        return []

    before = snapshot_source(Path(workspace))
    for raw in ops or []:
        if not isinstance(raw, dict):
            continue
        op = str(raw.get("op") or "").strip().lower()
        path = str(raw.get("path") or "")
        try:
            if op == "replace":
                api.replace(
                    path,
                    str(raw.get("old") or ""),
                    str(raw.get("new") or ""),
                    int(raw.get("count") or 0),
                )
            elif op == "write":
                api.write(path, str(raw.get("content") or ""))
            else:
                log.warning("quality repair: unknown op %s", op)
        except Exception as e:
            log.warning(
                "quality repair op failed (%s %s): %s — abandoning the whole plan, "
                "its other %s op(s) were written against this one",
                op,
                path,
                e,
                max(0, len(ops or []) - 1),
            )
            restore_source(Path(workspace), before)
            return []
    return api.touched


def run_repair_script(
    workspace: Path,
    script: str,
    architect: dict[str, Any] | None = None,
) -> list[str]:
    """Execute a short Python repair script with only RepairAPI injected."""
    body = (script or "").strip()
    if not body:
        return []
    if _FORBIDDEN_SCRIPT.search(body):
        raise ValueError("repair script uses forbidden constructs")
    if len(body) > 40_000:
        raise ValueError("repair script too large")

    api = RepairAPI(workspace, architect)
    globals_dict: dict[str, Any] = {
        "__builtins__": _SAFE_BUILTINS,
        "read": api.read,
        "write": api.write,
        "replace": api.replace,
        "list_files": api.list_files,
    }
    exec(compile(body, "<quality_repair>", "exec"), globals_dict, {})  # noqa: S102
    return api.touched


def apply_file_rewrites(
    workspace: Path,
    files: list[dict[str, Any]],
    architect: dict[str, Any] | None = None,
) -> list[str]:
    """Full-file rewrites under src/ (same safety as ops)."""
    api = RepairAPI(workspace, architect)
    for item in files or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        content = _strip_fences(str(item.get("content") or ""))
        if not path or not content.strip():
            continue
        try:
            api.write(path, content)
        except Exception as e:
            log.warning("quality repair rewrite failed %s: %s", path, e)
    return api.touched


def apply_quality_repair_plan(
    workspace: Path,
    plan: dict[str, Any],
    architect: dict[str, Any] | None = None,
) -> list[str]:
    """Apply plan in order: ops → script → file rewrites."""
    touched: list[str] = []
    ops = plan.get("ops") if isinstance(plan.get("ops"), list) else []
    if ops:
        touched.extend(apply_repair_ops(workspace, ops, architect))
    script = plan.get("script")
    if isinstance(script, str) and script.strip():
        try:
            touched.extend(run_repair_script(workspace, script, architect))
        except Exception as e:
            log.warning("quality repair script failed: %s", e)
    files = plan.get("files") if isinstance(plan.get("files"), list) else []
    if files:
        touched.extend(apply_file_rewrites(workspace, files, architect))
    return list(dict.fromkeys(touched))


def _issue_context(issues: list[Any], workspace: Path, max_files: int = 8) -> str:
    chunks: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        code = getattr(issue, "code", "") or ""
        message = getattr(issue, "message", "") or ""
        path = getattr(issue, "path", "") or ""
        chunks.append(f"- {code}: {message}" + (f" ({path})" if path else ""))
        if path and path not in seen and len(seen) < max_files:
            seen.add(path)
            src = read_file(workspace, path) or ""
            if src:
                chunks.append(f"=== {path} ===\n{src[:8000]}")
    # Always include App + mock when present
    for extra in ("src/App.tsx", "src/data/mock.ts", "src/pages/AiFeaturesPage.tsx"):
        if extra in seen:
            continue
        src = read_file(workspace, extra) or ""
        if src:
            chunks.append(f"=== {extra} ===\n{src[:6000]}")
            seen.add(extra)
    return "\n".join(chunks)[:45000]


def request_quality_repair_plan(
    workspace: Path,
    architect: dict[str, Any],
    issues: list[Any],
    ai_provider: AIProvider,
) -> dict[str, Any] | None:
    """Ask the fix model for a sandboxed repair plan."""
    if not issues:
        return None

    issue_blob = _issue_context(issues, workspace)
    tree = "\n".join(
        p
        for p in list_source_files(workspace)
        if not is_template_owned_path(p, architect, workspace)
    )[:4000]

    prompt = f"""You are repairing a generated React/Vite preview app so it passes a fixed quality gate.

QUALITY ISSUES (must fix):
{issue_blob}

FILE TREE (editable under src/ only):
{tree}

Return ONLY a JSON object (no markdown) with this shape:
{{
  "strategy": "ops" | "script" | "rewrite",
  "ops": [
    {{"op": "replace", "path": "src/pages/Foo.tsx", "old": "...", "new": "..."}},
    {{"op": "write", "path": "src/pages/Foo.tsx", "content": "...full file..."}}
  ],
  "script": "optional short Python using ONLY read/write/replace/list_files + re",
  "files": [{{"path": "src/pages/Foo.tsx", "content": "...full file..."}}],
  "rationale": "one sentence"
}}

Rules:
- Prefer "ops" (surgical replace) over full rewrite.
- Script may ONLY call read/write/replace/list_files and use the `re` module. No imports.
- Paths must start with src/. Never touch package.json, node_modules, or src/ui/*.
- AI hub page must use AiFeatureDeck (not checkout/utility stubs).
- Invented AI step routes like /ai-advisor/foo must become hash panel links (#panel-id).
- Keep TypeScript/TSX valid.
"""

    models = (
        settings.QUALITY_FIX_MODEL,
        settings.FIX_MODEL,
        settings.PREVIEW_APP_MODEL,
        settings.TEXT_MODEL,
    )

    def _ask(text: str) -> str:
        # Same rule as the build fix agent: a model that already failed in this
        # process is not asked again. The configured primary has taken minutes per
        # attempt to return truncated output on every run observed so far, and the
        # gate repair gets two attempts, so the charge was paid twice per request.
        # These four settings resolve to two distinct ids by default, which is why
        # the chain has to be deduplicated by *resolved id*, not by setting name.
        from app.application.preview_app.codegen.fix_agent import (
            _FAILED_FIX_MODELS,
            fix_model_candidates,
        )

        candidates, exhausted = fix_model_candidates(models)
        for model in candidates:
            if not exhausted and model in _FAILED_FIX_MODELS:
                log.info("quality repair skipping %s — already failed this process", model)
                continue
            try:
                raw = ai_provider.ask_chat(
                    model,
                    [{"role": "user", "content": text}],
                    max_tokens=12000,
                )
            except Exception as e:
                log.warning("quality repair model %s failed: %s", model, e)
                _FAILED_FIX_MODELS.add(model)
                continue
            if raw and str(raw).strip():
                return str(raw)
            log.warning("quality repair model %s returned nothing", model)
            _FAILED_FIX_MODELS.add(model)
        return ""

    def _ask_and_parse(text: str, label: str, attempt: int) -> dict[str, Any] | None:
        # A plan that does not parse — or parses to an object with no ops, no
        # script and no files — bought nothing. Request 68 spent 882.2 s here
        # for zero applied operations while every row said `success = true`.
        with ai_call("quality_repair", writer=label, attempt=attempt) as call:
            parsed = _try_parse_plan(_ask(text), label, workspace)
            call.adjudicate(parsed is not None, reason=UNUSABLE_UNPARSEABLE)
            return parsed

    data = _ask_and_parse(prompt, "primary", 1)
    if data is None:
        data = _ask_and_parse(
            prompt
            + "\n\nSTRICT: JSON only. Prefer ops. Shape "
            '{"strategy":"ops","ops":[{"op":"replace","path":"...","old":"...","new":"..."}]}',
            "strict-retry",
            2,
        )
    return data


def _try_parse_plan(
    raw: str,
    label: str,
    workspace: Path | None = None,
) -> dict[str, Any] | None:
    if not raw or not str(raw).strip():
        log.warning("quality repair %s: empty response", label)
        return None
    try:
        parsed, meta = parse_json_with_meta(raw)
    except Exception as e:
        # The fix agent dumps its unparsed responses; this path did not, so
        # request 67's `12:08:48 quality repair primary: parse failed` left no
        # artifact and the diagnosis had to be reconstructed from the fix agent's.
        log.warning("quality repair %s: parse failed: %s", label, e)
        if workspace is not None:
            analysis = analyze_json_response(raw)
            dump_unparsed_fix_agent_response(
                Path(workspace), label=f"quality-repair-{label}", raw=raw, error=e
            )
            log.error(
                "quality repair %s parse diagnostics: len=%s lines=%s fenced=%s "
                "brace_imbalance=%s likely_truncated=%s",
                label,
                analysis["length"],
                analysis["lines"],
                analysis["fenced"],
                analysis["depth_imbalance"],
                analysis["likely_truncated"],
            )
        return None
    if meta.get("method") not in ("direct", "fence"):
        log.info(
            "quality repair %s: recovered via %s (len=%s)", label, meta.get("method"), len(raw)
        )
    if not isinstance(parsed, dict):
        log.warning("quality repair %s: expected object", label)
        return None
    if not (parsed.get("ops") or parsed.get("script") or parsed.get("files")):
        log.warning("quality repair %s: no ops/script/files", label)
        return None
    return parsed


def run_ai_quality_repair(
    workspace: Path,
    architect: dict[str, Any],
    issues: list[Any],
    ai_provider: AIProvider | None = None,
) -> list[str]:
    """One AI repair attempt. Returns touched paths."""
    with ai_call("quality_repair") as repair_scope:
        paths = _run_ai_quality_repair_inner(workspace, architect, issues, ai_provider)
        # The number the ledger was missing. A repair round that costs minutes
        # and applies nothing is indistinguishable, in the old schema, from one
        # that fixed the site.
        repair_scope.applied_ops(len(paths))
        return paths


def _run_ai_quality_repair_inner(
    workspace: Path,
    architect: dict[str, Any],
    issues: list[Any],
    ai_provider: AIProvider | None = None,
) -> list[str]:
    if ai_provider is None:
        from app.infrastructure.ai_providers.factory import get_ai_provider

        ai_provider = get_ai_provider()
    plan = request_quality_repair_plan(workspace, architect, issues, ai_provider)
    if not plan:
        return []
    log.info(
        "quality repair plan strategy=%s ops=%s files=%s script=%s",
        plan.get("strategy"),
        len(plan.get("ops") or []) if isinstance(plan.get("ops"), list) else 0,
        len(plan.get("files") or []) if isinstance(plan.get("files"), list) else 0,
        bool(plan.get("script")),
    )
    # Persist plan for debugging, one file per attempt. A single filename meant
    # round 2 overwrote round 1, and on request 67 that turned "which op minted
    # the duplicate `/gallery`?" from a reading into a reconstruction QA could
    # not finish. The unsuffixed name stays as the latest plan so existing
    # tooling keeps working.
    try:
        debug = Path(workspace) / ".bmv-debug"
        debug.mkdir(parents=True, exist_ok=True)
        body = json.dumps(plan, indent=2)[:200_000]
        attempt = 1 + sum(
            1 for _ in debug.glob("quality_repair_plan.[0-9]*.json")
        )
        (debug / f"quality_repair_plan.{attempt}.json").write_text(body, encoding="utf-8")
        (debug / "quality_repair_plan.json").write_text(body, encoding="utf-8")
    except OSError:
        pass
    return apply_quality_repair_plan(workspace, plan, architect)
