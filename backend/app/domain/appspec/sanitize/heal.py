"""Deterministic AppSpec heals driven by validation / schema issue codes."""
from __future__ import annotations

import copy
from typing import Any, Mapping

from app.domain.appspec.sanitize.reference_integrity import (
    reconcile_reference_integrity,
)


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


def _heal_tier1_primary_journey(payload: dict[str, Any]) -> list[str]:
    """Close the common gap between AppSpec validation and Tier 1 proof selection.

    Tier building needs an interaction requirement whose journey ends in a
    terminal state with visible success evidence and a journey-backed test.
    Authors often omit ``terminal`` / visible assertions even when the graph
    is otherwise valid.
    """

    applied: list[str] = []
    requirements = [
        item for item in (payload.get("requirements") or []) if isinstance(item, dict)
    ]
    journeys = [
        item for item in (payload.get("journeys") or []) if isinstance(item, dict)
    ]
    states = [
        item for item in (payload.get("states") or []) if isinstance(item, dict)
    ]
    evidence = [
        item for item in (payload.get("evidence") or []) if isinstance(item, dict)
    ]
    tests = [
        item
        for item in (payload.get("acceptance_tests") or [])
        if isinstance(item, dict)
    ]
    traces = [
        item for item in (payload.get("traceability") or []) if isinstance(item, dict)
    ]
    deferred = {
        str(req_id)
        for item in (payload.get("deferred_scope") or [])
        if isinstance(item, dict)
        for req_id in (item.get("requirement_ids") or [])
    }
    state_by_id = {str(item.get("id")): item for item in states if item.get("id")}
    evidence_by_page: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        page_id = str(item.get("page_id") or "")
        if page_id:
            evidence_by_page.setdefault(page_id, []).append(item)

    interaction_ids = [
        str(item.get("id"))
        for item in requirements
        if item.get("verification_mode") == "interaction"
        and item.get("id")
        and str(item.get("id")) not in deferred
    ]
    if not interaction_ids or not journeys:
        return applied

    for requirement_id in interaction_ids:
        trace = next(
            (
                item
                for item in traces
                if str(item.get("requirement_id")) == requirement_id
            ),
            None,
        )
        if trace is None:
            continue
        traced_journeys = {
            str(value) for value in (trace.get("journey_ids") or [])
        }
        traced_tests = {
            str(value) for value in (trace.get("acceptance_test_ids") or [])
        }
        for journey in journeys:
            journey_id = str(journey.get("id") or "")
            if (
                not journey_id
                or journey_id not in traced_journeys
                or requirement_id
                not in {
                    str(value) for value in (journey.get("requirement_ids") or [])
                }
            ):
                continue
            steps = [
                step
                for step in (journey.get("steps") or [])
                if isinstance(step, dict)
            ]
            if not steps:
                continue
            last_step = steps[-1]
            state_id = str(last_step.get("expected_state_id") or "")
            page_id = str(last_step.get("expected_page_id") or "")
            state = state_by_id.get(state_id)
            if state is None:
                continue
            if not state.get("terminal"):
                state["terminal"] = True
                applied.append(f"mark_terminal:{state_id}")

            step_evidence = [
                str(value) for value in (last_step.get("evidence_ids") or []) if value
            ]
            state_evidence = [
                str(value) for value in (state.get("evidence_ids") or []) if value
            ]
            success_ids = list(dict.fromkeys([*step_evidence, *state_evidence]))
            if not success_ids:
                page_evidence = evidence_by_page.get(page_id) or []
                if page_evidence:
                    success_ids = [str(page_evidence[0].get("id"))]
                elif evidence:
                    success_ids = [str(evidence[0].get("id"))]
                else:
                    continue
                last_step["evidence_ids"] = success_ids
                state["evidence_ids"] = success_ids
                applied.append(f"attach_success_evidence:{success_ids[0]}")
            else:
                if not step_evidence:
                    last_step["evidence_ids"] = success_ids[:1]
                    applied.append("copy_success_evidence_to_step")
                if not state_evidence:
                    state["evidence_ids"] = success_ids[:1]
                    applied.append("copy_success_evidence_to_state")

            success_id = success_ids[0]
            test = next(
                (
                    item
                    for item in tests
                    if str(item.get("id") or "") in traced_tests
                    and str(item.get("journey_id") or "") == journey_id
                    and requirement_id
                    in {
                        str(value)
                        for value in (item.get("requirement_ids") or [])
                    }
                ),
                None,
            )
            if test is None:
                continue
            assertions = [
                assertion
                for assertion in (test.get("assertions") or [])
                if isinstance(assertion, dict)
            ]
            has_visible = any(
                assertion.get("kind") == "visible"
                and str(assertion.get("evidence_id") or "") == success_id
                for assertion in assertions
            )
            if not has_visible:
                assertions.append(
                    {
                        "kind": "visible",
                        "description": (
                            "Terminal success evidence is visible after the "
                            "primary journey."
                        ),
                        "page_id": page_id or None,
                        "state_id": state_id or None,
                        "evidence_id": success_id,
                        "expected": "visible",
                    }
                )
                test["assertions"] = assertions
                applied.append(f"add_visible_assertion:{test.get('id')}")
            if applied:
                return applied
    return applied


def drop_unbindable_state_assertions(
    payload: Mapping[str, Any],
    validation_payload: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Last-resort salvage for unbindable assertions. Returns (payload, actions).

    A `kind: "state"` assertion with `state_id: null` is the model saying "I want
    to assert a state here and I did not declare one". Requests 154 and 155 both
    died on it and 149 before them — *"the hire booking is confirmed"* against a
    page whose only state is *"hire booking form displayed"*, *"the bike gallery
    is in a filtered state"* against a page that declares only *"loaded"*. The
    state is missing, not the field, so nothing can be bound.

    `visible_assertion_evidence_required` is the same dead end one field over:
    request 138's repair reproduced all four *"A visible assertion requires
    evidence_id"* issues byte-identically, because the claimed surface had no
    evidence object to bind and the prompt taught no legal move. Both codes
    anchor `("acceptance_tests", i, "assertions", j, <field>)`, and the salvage
    for both is the one always-safe action: remove the claim the spec cannot
    prove.

    **This is deliberately not a heal.** It must never run before the model's
    repair pass: declaring the missing state is the right fix and only the model
    can write it coherently (the state needs a page listing, a non-initial flag,
    an outgoing transition and reachability from an initial state — mint any of
    those wrong and one blocking code becomes three). The repair prompt now says
    so explicitly. This runs only at the point the pipeline would otherwise throw
    the whole paid run away, and it does the one thing that is always safe:
    removes the claim the spec cannot express. `assertions` has `min_length=1`,
    so a test's last assertion is never dropped — such a spec is genuinely
    unrepairable and still fails closed.
    """
    salvageable = {
        "state_assertion_state_required": "drop_unbindable_state_assertion",
        "visible_assertion_evidence_required": "drop_unprovable_visible_assertion",
    }
    targets: dict[tuple[int, int], str] = {}
    for issue in validation_payload.get("issues") or []:
        if not isinstance(issue, Mapping):
            continue
        label = salvageable.get(str(issue.get("code") or ""))
        if label is None:
            continue
        parts = _path_parts(issue.get("path"))
        # ("acceptance_tests", i, "assertions", j, "state_id"|"evidence_id")
        if len(parts) < 4 or str(parts[0]) != "acceptance_tests":
            continue
        if str(parts[2]) != "assertions":
            continue
        try:
            targets.setdefault((int(parts[1]), int(parts[3])), label)
        except (TypeError, ValueError):
            continue
    if not targets:
        return dict(payload), []

    healed = copy.deepcopy(dict(payload))
    tests = healed.get("acceptance_tests")
    if not isinstance(tests, list):
        return dict(payload), []
    applied: list[str] = []
    # Descending, so an earlier drop cannot shift a later index.
    for test_index, assertion_index in sorted(targets, reverse=True):
        if test_index < 0 or test_index >= len(tests):
            continue
        test = tests[test_index]
        if not isinstance(test, dict):
            continue
        assertions = test.get("assertions")
        if not isinstance(assertions, list) or len(assertions) <= 1:
            continue
        if assertion_index < 0 or assertion_index >= len(assertions):
            continue
        dropped = assertions.pop(assertion_index)
        description = ""
        if isinstance(dropped, Mapping):
            description = str(dropped.get("description") or "")
        applied.append(
            f"{targets[(test_index, assertion_index)]}:{test.get('id')}:{description[:60]}"
        )
    if not applied:
        return dict(payload), []
    return healed, applied


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

    issue_codes = {
        str(issue.get("code") or "")
        for issue in (validation_payload.get("issues") or [])
        if isinstance(issue, Mapping)
    }

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
        elif code == "tier1_primary_journey_incomplete":
            applied.extend(_heal_tier1_primary_journey(healed))

    if "missing_reference" in issue_codes:
        healed, integrity = reconcile_reference_integrity(healed)
        applied.extend(list(integrity.applied))
        if integrity.integrity_hash:
            applied.append(
                f"reference_integrity:hash:{integrity.integrity_hash[:16]}"
            )
        for item in integrity.diagnostics[:40]:
            applied.append(
                "reference_integrity:diag:"
                f"{item.get('referencing_field')}:"
                f"{item.get('missing_reference_id')}:"
                f"{item.get('repair_result')}"
            )

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


__all__ = ["drop_unbindable_state_assertions", "heal_app_spec_payload"]
