"""Persist structured failure artifacts under preview workspace `.bmv-debug/`."""
from __future__ import annotations

import hashlib
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.infrastructure.logging import get_logger

log = get_logger("Diagnostics")

DEBUG_ROOT = ".bmv-debug"


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def dump_text(
    workspace: Path,
    category: str,
    label: str,
    body: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Write a text artifact; returns the path written."""
    safe_label = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in label)[:80]
    dump_dir = workspace / DEBUG_ROOT / category
    dump_dir.mkdir(parents=True, exist_ok=True)
    path = dump_dir / f"{safe_label}-{_stamp()}-{_digest(body)}.txt"
    header_lines = [f"category={category}", f"label={label}"]
    if metadata:
        for key, value in metadata.items():
            header_lines.append(f"{key}={value}")
    header_lines.append("--- body ---")
    path.write_text("\n".join(header_lines) + "\n" + body, encoding="utf-8", errors="replace")
    return path


def dump_json(
    workspace: Path,
    category: str,
    label: str,
    payload: Any,
    *,
    extra: dict[str, Any] | None = None,
) -> Path:
    body = json.dumps(
        {"extra": extra or {}, "payload": payload},
        indent=2,
        ensure_ascii=False,
        default=str,
    )
    return dump_text(workspace, category, label, body, metadata={"format": "json"})


def dump_catalogue_rejection(
    workspace: Path,
    *,
    file_path: str,
    errors: list[str],
    source: str,
    route: dict | None = None,
    attempt: int | None = None,
) -> Path:
    meta = {
        "path": file_path,
        "errors": errors,
        "attempt": attempt,
        "skeleton_id": (route or {}).get("skeleton_id"),
        "route_path": (route or {}).get("path"),
    }
    path = dump_text(
        workspace,
        "catalogue-contract",
        file_path.replace("/", "_"),
        source,
        metadata={k: str(v) for k, v in meta.items() if v is not None},
    )
    log.warning(
        "catalogue contract rejected path=%s errors=%s — source dumped to %s",
        file_path,
        errors,
        path,
    )
    return path


def dump_build_failure(
    workspace: Path,
    *,
    label: str,
    build_log: str,
    extracted_errors: str | None = None,
    attempt: int | None = None,
) -> Path:
    meta: dict[str, Any] = {"attempt": attempt}
    if extracted_errors:
        meta["extracted_errors"] = extracted_errors
    path = dump_text(
        workspace,
        "vite-build",
        label,
        build_log,
        metadata={k: str(v) for k, v in meta.items() if v is not None},
    )
    tail = (build_log or "")[-1500:]
    log.error("vite build failed (%s) — full log dumped to %s\n%s", label, path, tail)
    return path


def dump_unparsed_fix_agent_response(
    workspace: Path,
    *,
    label: str,
    raw: str,
    error: Exception | str,
    build_errors: str | None = None,
) -> Path:
    meta = {
        "error": str(error),
        "length": len(raw),
        "sha256": _digest(raw),
    }
    if build_errors:
        meta["build_errors_excerpt"] = build_errors[:2000]
    path = dump_text(
        workspace,
        "fix-agent",
        label,
        raw,
        metadata={k: str(v) for k, v in meta.items()},
    )
    log.error(
        "fix agent %s JSON parse failed: %s — full response dumped to %s",
        label,
        error,
        path,
    )
    if raw:
        log.debug("fix agent %s response head (2k):\n%s", label, raw[:2000])
        log.debug("fix agent %s response tail (2k):\n%s", label, raw[-2000:])
    return path


def dump_exception(
    workspace: Path | None,
    category: str,
    label: str,
    exc: BaseException,
    *,
    context: dict[str, Any] | None = None,
) -> None:
    """Log exception with traceback; optionally persist to workspace."""
    log.exception("%s failed: %s", label, exc)
    if workspace is None:
        return
    body = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    if context:
        body = f"context={json.dumps(context, default=str)}\n\n{body}"
    path = dump_text(workspace, category, label, body)
    log.error("exception artifact written to %s", path)


def dump_pipeline_summary(
    workspace: Path,
    *,
    request_id: int,
    ok: bool,
    build_log: str,
    notes: list[str] | None = None,
) -> Path:
    payload = {
        "request_id": request_id,
        "ok": ok,
        "notes": notes or [],
        "build_log_tail": (build_log or "")[-4000:],
    }
    return dump_json(workspace, "pipeline", f"request-{request_id}-summary", payload)


def analyze_json_response(raw: str) -> dict[str, Any]:
    """Heuristic diagnostics for unparsable model JSON (fix-agent, codegen, etc.)."""
    text = raw or ""
    stripped = text.strip()
    fenced = "```" in stripped
    has_open_brace = "{" in stripped
    has_close_brace = "}" in stripped
    open_count = stripped.count("{")
    close_count = stripped.count("}")
    depth_imbalance = open_count - close_count
    starts_with_fence = stripped.startswith("```")
    starts_with_brace = stripped.startswith("{")
    has_files_key = '"files"' in stripped or "'files'" in stripped
    truncated_hint = (
        depth_imbalance > 0
        or (has_open_brace and not has_close_brace)
        or (stripped.endswith(",") or stripped.endswith('":'))
    )
    return {
        "length": len(text),
        "lines": text.count("\n") + (1 if text else 0),
        "fenced": fenced,
        "starts_with_fence": starts_with_fence,
        "starts_with_brace": starts_with_brace,
        "has_files_key": has_files_key,
        "open_braces": open_count,
        "close_braces": close_count,
        "depth_imbalance": depth_imbalance,
        "likely_truncated": truncated_hint,
        "head": stripped[:400],
        "tail": stripped[-400:] if len(stripped) > 400 else stripped,
    }


def _read_dump_header(path: Path) -> dict[str, str]:
    meta: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:30]:
            if line.strip() == "--- body ---":
                break
            if "=" in line:
                key, _, value = line.partition("=")
                meta[key.strip()] = value.strip()
    except Exception:
        pass
    return meta


def _extract_vite_errors(build_log: str, limit: int = 12) -> list[str]:
    errors: list[str] = []
    for line in (build_log or "").splitlines():
        s = line.strip()
        if not s:
            continue
        if any(
            token in s
            for token in ("error TS", "ERROR", "✘", "Failed to", "Could not resolve", "is not exported")
        ):
            errors.append(s)
        if len(errors) >= limit:
            break
    return errors


def summarize_workspace_debug(workspace: Path) -> dict[str, Any]:
    """Scan ``.bmv-debug/`` and return a structured failure report."""
    root = workspace / DEBUG_ROOT
    summary: dict[str, Any] = {
        "workspace": str(workspace),
        "exists": workspace.exists(),
        "categories": {},
        "top_issues": [],
    }
    if not root.is_dir():
        summary["top_issues"].append("no .bmv-debug directory — run may not have reached codegen/build")
        return summary

    for category_dir in sorted(root.iterdir()):
        if not category_dir.is_dir():
            continue
        files = sorted(category_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        cat: dict[str, Any] = {"count": len(files), "artifacts": []}
        for path in files[:20]:
            meta = _read_dump_header(path)
            entry: dict[str, Any] = {"file": path.name, "meta": meta}
            if category_dir.name == "fix-agent":
                try:
                    body = path.read_text(encoding="utf-8", errors="replace")
                    body_start = body.find("--- body ---")
                    raw = body[body_start + len("--- body ---") :].lstrip("\n") if body_start >= 0 else body
                    analysis = analyze_json_response(raw)
                    entry["json_analysis"] = {
                        k: v for k, v in analysis.items() if k not in ("head", "tail")
                    }
                    if analysis.get("likely_truncated"):
                        summary["top_issues"].append(
                            f"fix-agent {path.name}: likely truncated JSON "
                            f"(len={analysis['length']}, brace imbalance={analysis['depth_imbalance']})"
                        )
                    else:
                        summary["top_issues"].append(
                            f"fix-agent {path.name}: JSON parse failed "
                            f"(len={analysis['length']}, error={meta.get('error', '?')})"
                        )
                except Exception as exc:
                    entry["read_error"] = str(exc)
            elif category_dir.name == "catalogue-contract":
                errs = meta.get("errors", "")
                if errs:
                    summary["top_issues"].append(f"catalogue {meta.get('path', path.name)}: {errs[:200]}")
                entry["path"] = meta.get("path")
                entry["errors"] = errs
            elif category_dir.name == "vite-build":
                try:
                    body = path.read_text(encoding="utf-8", errors="replace")
                    body_start = body.find("--- body ---")
                    log_body = body[body_start + len("--- body ---") :].lstrip("\n") if body_start >= 0 else body
                    entry["vite_errors"] = _extract_vite_errors(log_body)
                    if entry["vite_errors"]:
                        summary["top_issues"].append(
                            f"vite-build {path.name}: {entry['vite_errors'][0][:180]}"
                        )
                except Exception as exc:
                    entry["read_error"] = str(exc)
            elif category_dir.name == "pipeline":
                try:
                    body = path.read_text(encoding="utf-8", errors="replace")
                    payload = json.loads(body[body.find("{") :])
                    entry["payload"] = payload.get("payload") or payload
                    notes = (entry.get("payload") or {}).get("notes") or []
                    for note in notes:
                        summary["top_issues"].append(f"pipeline: {note}")
                except Exception as exc:
                    entry["read_error"] = str(exc)
            cat["artifacts"].append(entry)
        summary["categories"][category_dir.name] = cat

    # De-duplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for issue in summary["top_issues"]:
        if issue not in seen:
            seen.add(issue)
            deduped.append(issue)
    summary["top_issues"] = deduped[:25]
    return summary


def dump_appspec_failure(
    workspace: Path | None,
    *,
    request_id: int,
    exc: BaseException,
    phase: str,
) -> None:
    """Persist AppSpec failure context when a workspace exists."""
    dump_exception(
        workspace,
        "appspec",
        f"request-{request_id}-{phase}",
        exc,
        context={"request_id": request_id, "phase": phase},
    )
