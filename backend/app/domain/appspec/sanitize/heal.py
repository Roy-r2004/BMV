"""Deterministic AppSpec heals driven by validation / schema issue codes."""
from __future__ import annotations

import copy
from typing import Any, Mapping


def _path_parts(raw: Any) -> list[Any]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, tuple)):
        return list(raw)
    text = str(raw).strip()
    if not text:
        return []
    return text.split(".")


def _delete_at_path(root: Any, parts: list[Any]) -> bool:
    if not parts or not isinstance(root, (dict, list)):
        return False
    current: Any = root
    for part in parts[:-1]:
        key: Any = int(part) if isinstance(current, list) and str(part).isdigit() else part
        if isinstance(current, dict):
            if key not in current:
                return False
            current = current[key]
        elif isinstance(current, list) and isinstance(key, int):
            if key < 0 or key >= len(current):
                return False
            current = current[key]
        else:
            return False
    last = parts[-1]
    key = int(last) if isinstance(current, list) and str(last).isdigit() else last
    if isinstance(current, dict) and key in current:
        current.pop(key, None)
        return True
    if isinstance(current, list) and isinstance(key, int) and 0 <= key < len(current):
        current.pop(key)
        return True
    return False


def _set_at_path(root: Any, parts: list[Any], value: Any) -> bool:
    if not parts or not isinstance(root, (dict, list)):
        return False
    current: Any = root
    for part in parts[:-1]:
        key: Any = int(part) if isinstance(current, list) and str(part).isdigit() else part
        if isinstance(current, dict):
            if key not in current:
                return False
            current = current[key]
        elif isinstance(current, list) and isinstance(key, int):
            if key < 0 or key >= len(current):
                return False
            current = current[key]
        else:
            return False
    last = parts[-1]
    key = int(last) if isinstance(current, list) and str(last).isdigit() else last
    if isinstance(current, dict):
        current[key] = value
        return True
    if isinstance(current, list) and isinstance(key, int) and 0 <= key < len(current):
        current[key] = value
        return True
    return False


def _heal_schema_parse_extras(payload: dict[str, Any], issue: Mapping[str, Any]) -> list[str]:
    """Remove keys pydantic rejected as extra_forbidden."""

    applied: list[str] = []
    detail = issue.get("detail")
    if not isinstance(detail, list):
        return applied
    for err in detail:
        if not isinstance(err, Mapping):
            continue
        if str(err.get("type") or "") != "extra_forbidden":
            continue
        loc = list(err.get("loc") or [])
        if not loc:
            continue
        if _delete_at_path(payload, loc):
            applied.append("strip_extra:" + ".".join(str(p) for p in loc))
    return applied


def _heal_reference_entity_not_allowed(
    payload: dict[str, Any],
    issue: Mapping[str, Any],
) -> list[str]:
    parts = _path_parts(issue.get("path"))
    # path like entities.N.fields.M.reference_entity_id → set sibling type=reference
    if len(parts) < 2 or parts[-1] != "reference_entity_id":
        return []
    type_path = parts[:-1] + ["type"]
    if _set_at_path(payload, type_path, "reference"):
        return ["coerce_reference_type:" + ".".join(str(p) for p in parts[:-1])]
    return []


def _heal_unresolved_source_refs(payload: dict[str, Any]) -> list[str]:
    applied: list[str] = []
    for requirement in payload.get("requirements") or []:
        if not isinstance(requirement, dict):
            continue
        refs = [str(r) for r in (requirement.get("source_refs") or []) if str(r).strip()]
        if not refs:
            requirement["source_refs"] = ["customer_input.desired_outcome"]
            applied.append(f"default_source_ref:{requirement.get('id')}")
            continue
        # Keep only refs that look authoritative; always ensure one valid fallback.
        kept = [r for r in refs if r.startswith(("customer_input.", "reference_evidence."))]
        if not kept:
            requirement["source_refs"] = ["customer_input.desired_outcome"]
            applied.append(f"reset_source_ref:{requirement.get('id')}")
        elif kept != refs:
            requirement["source_refs"] = kept
            applied.append(f"filter_source_ref:{requirement.get('id')}")
    return applied


def _heal_schema_version(payload: dict[str, Any]) -> list[str]:
    if payload.get("schema_version") != "1.0":
        payload["schema_version"] = "1.0"
        return ["force_schema_version_1.0"]
    return []


def heal_app_spec_payload(
    payload: Mapping[str, Any],
    validation_payload: Mapping[str, Any],
    source_snapshot: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Apply code-driven heals for known validation / schema failures.

    Returns ``(healed_payload, applied_actions)``. ``applied_actions`` empty means
    no deterministic heal was possible from the report.
    """

    del source_snapshot  # reserved for future source-aware heals
    healed = copy.deepcopy(dict(payload))
    applied: list[str] = []
    applied.extend(_heal_schema_version(healed))

    for issue in list(validation_payload.get("issues") or []):
        if not isinstance(issue, Mapping):
            continue
        code = str(issue.get("code") or "")
        if code == "app_spec_schema_parse_failed":
            applied.extend(_heal_schema_parse_extras(healed, issue))
        elif code == "reference_entity_not_allowed":
            applied.extend(_heal_reference_entity_not_allowed(healed, issue))
        elif code in {
            "unresolved_requirement_source_ref",
            "duplicate_requirement_source_ref",
        }:
            applied.extend(_heal_unresolved_source_refs(healed))
        elif code == "app_spec_schema_version_mismatch":
            applied.extend(_heal_schema_version(healed))

    # Always re-normalize source refs when any source-ref issue appeared.
    if any(
        str(i.get("code") or "").endswith("source_ref")
        for i in (validation_payload.get("issues") or [])
        if isinstance(i, Mapping)
    ):
        # Deduplicate refs case-insensitively.
        for requirement in healed.get("requirements") or []:
            if not isinstance(requirement, dict):
                continue
            seen: set[str] = set()
            deduped: list[str] = []
            for ref in requirement.get("source_refs") or []:
                folded = str(ref).casefold()
                if folded in seen:
                    continue
                seen.add(folded)
                deduped.append(str(ref))
            if not deduped:
                deduped = ["customer_input.desired_outcome"]
            requirement["source_refs"] = deduped

    return healed, applied


__all__ = ["heal_app_spec_payload"]
