"""AppSpec sanitize — evidence, assertions, effects."""
from __future__ import annotations

from typing import Any, Mapping

from app.domain.appspec.sanitize.kinds import (
    _ASSERTION_KIND_ALIASES,
    _EVIDENCE_KIND_ALIASES,
    _VALID_ASSERTION_KINDS,
    _VALID_EVIDENCE_KINDS,
    _normalize_kind,
)
from app.domain.appspec.sanitize.structure import _sanitize_route

# Mirrors AcceptanceAssertion fields in app.domain.schemas.app_spec.
_ALLOWED_ASSERTION_KEYS = frozenset(
    {
        "kind",
        "description",
        "page_id",
        "state_id",
        "evidence_id",
        "expected",
    }
)


def _fold_assertion_extra_into_expected(assertion: dict[str, Any]) -> None:
    """Preserve useful model extras inside ``expected`` before stripping them."""

    if assertion.get("expected"):
        return
    parts: list[str] = []
    for key in ("entity_id", "field_id", "action_id", "value"):
        raw = assertion.get(key)
        if raw is None or raw == "":
            continue
        parts.append(f"{key}={raw}")
    if parts:
        assertion["expected"] = ", ".join(parts)[:240]


def _sanitize_assertion_schema_fields(assertion: dict[str, Any]) -> None:
    """Drop forbidden keys models often invent (e.g. entity_id on assertions)."""

    _fold_assertion_extra_into_expected(assertion)
    for key in list(assertion.keys()):
        if key not in _ALLOWED_ASSERTION_KEYS:
            assertion.pop(key, None)


def _sanitize_page_evidence_ids(
    page: dict[str, Any],
    evidence_by_page: dict[str, list[str]],
    synthetic_evidence: list[dict[str, Any]],
) -> None:
    evidence_ids = list(page.get("evidence_ids") or [])
    if evidence_ids:
        return
    page_id = str(page.get("id") or "")
    linked = evidence_by_page.get(page_id, [])
    if linked:
        page["evidence_ids"] = [linked[0]]
        return

    capability_ids = [
        str(value)
        for value in (page.get("capability_ids") or [])
        if str(value).strip()
    ]
    if not capability_ids:
        capability_ids = ["CAP-UNSPECIFIED"]
    evidence_id = f"EVIDENCE-{page_id.replace('PAGE-', '')}-SURFACE"
    suffix = 2
    existing_ids = {
        str(item.get("id"))
        for item in synthetic_evidence
        if isinstance(item, dict) and item.get("id")
    }
    while evidence_id in existing_ids:
        evidence_id = f"EVIDENCE-{page_id.replace('PAGE-', '')}-SURFACE-{suffix}"
        suffix += 1
    synthetic_evidence.append(
        {
            "id": evidence_id,
            "page_id": page_id,
            "name": f"{page.get('name', 'Page')} surface",
            "description": (
                "Observable page surface used to satisfy schema traceability for "
                f"{page.get('name', 'this page')}."
            ),
            "kind": "navigation",
            "capability_ids": capability_ids[:1],
        }
    )
    page["evidence_ids"] = [evidence_id]
    evidence_by_page.setdefault(page_id, []).append(evidence_id)

def _sanitize_evidence_and_assertions(payload: dict[str, Any]) -> None:
    for item in payload.get("evidence") or []:
        if isinstance(item, dict):
            item["kind"] = _normalize_kind(
                item.get("kind"),
                valid=_VALID_EVIDENCE_KINDS,
                aliases=_EVIDENCE_KIND_ALIASES,
                default="text",
            )

    evidence = _evidence_by_id(payload)
    states_by_page: dict[str, list[str]] = {}
    for state in payload.get("states") or []:
        if not isinstance(state, dict):
            continue
        page_id = str(state.get("page_id") or "")
        state_id = str(state.get("id") or "")
        if page_id and state_id:
            states_by_page.setdefault(page_id, []).append(state_id)

    for test in payload.get("acceptance_tests") or []:
        if not isinstance(test, dict):
            continue
        for assertion in test.get("assertions") or []:
            if not isinstance(assertion, dict):
                continue
            assertion["kind"] = _normalize_kind(
                assertion.get("kind"),
                valid=_VALID_ASSERTION_KINDS,
                aliases=_ASSERTION_KIND_ALIASES,
                default="visible",
            )
            _sanitize_assertion_schema_fields(assertion)
            # Models often emit kind=state for visual checks without state_id.
            if str(assertion.get("kind")) != "state" or assertion.get("state_id"):
                continue
            page_id = str(assertion.get("page_id") or "")
            if not page_id:
                evidence_id = str(assertion.get("evidence_id") or "")
                page_id = str((evidence.get(evidence_id) or {}).get("page_id") or "")
            candidates = states_by_page.get(page_id) or []
            if candidates:
                assertion["state_id"] = candidates[0]
                if page_id and not assertion.get("page_id"):
                    assertion["page_id"] = page_id
            elif assertion.get("evidence_id"):
                assertion["kind"] = "visible"
            else:
                assertion["kind"] = "visible"

def _sanitize_visible_assertion_evidence(payload: dict[str, Any]) -> None:
    evidence_by_page: dict[str, list[str]] = {}
    for item in payload.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        page_id = str(item.get("page_id") or "")
        evidence_id = str(item.get("id") or "")
        if page_id and evidence_id:
            evidence_by_page.setdefault(page_id, []).append(evidence_id)

    for test in payload.get("acceptance_tests") or []:
        if not isinstance(test, dict):
            continue
        for assertion in test.get("assertions") or []:
            if not isinstance(assertion, dict):
                continue
            if str(assertion.get("kind")) != "visible":
                continue
            if assertion.get("evidence_id"):
                continue
            page_id = str(assertion.get("page_id") or "")
            candidates = evidence_by_page.get(page_id) or []
            if candidates:
                assertion["evidence_id"] = candidates[0]

def _sanitize_transition_effects(payload: dict[str, Any]) -> None:
    field_types: dict[tuple[str, str], str] = {}
    field_enums: dict[tuple[str, str], list[Any]] = {}
    for entity in payload.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        entity_id = str(entity.get("id") or "")
        for field in entity.get("fields") or []:
            if not isinstance(field, dict):
                continue
            field_id = str(field.get("id") or "")
            if entity_id and field_id:
                field_types[(entity_id, field_id)] = str(field.get("type") or "string")
                if field.get("enum_values"):
                    field_enums[(entity_id, field_id)] = list(field["enum_values"])

    for transition in payload.get("transitions") or []:
        if not isinstance(transition, dict):
            continue
        for effect in transition.get("effects") or []:
            if not isinstance(effect, dict):
                continue
            operation = str(effect.get("operation") or "")
            key = (str(effect.get("entity_id") or ""), str(effect.get("field_id") or ""))
            field_type = field_types.get(key, "string")
            # append/remove are only valid on list fields; demote to set otherwise.
            if operation in {"append", "remove"} and field_type != "list":
                effect["operation"] = "set"
                operation = "set"
            if effect.get("value") is not None:
                continue
            if operation not in {"set", "append"}:
                continue
            if field_type == "boolean":
                effect["value"] = True
            elif field_type in {"integer", "number"}:
                effect["value"] = 0
            elif field_type == "enum":
                enum_values = field_enums.get(key) or []
                effect["value"] = enum_values[0] if enum_values else "updated"
            else:
                effect["value"] = "updated"

def _sanitize_evidence_capability_page_alignment(payload: dict[str, Any]) -> None:
    """Keep evidence.capability_ids within the page that hosts the evidence."""

    pages = {
        str(item.get("id")): item
        for item in (payload.get("pages") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for item in payload.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        page = pages.get(str(item.get("page_id") or ""))
        if page is None:
            continue
        page_caps = [str(value) for value in (page.get("capability_ids") or [])]
        evidence_caps = [str(value) for value in (item.get("capability_ids") or [])]
        aligned = [cap for cap in evidence_caps if cap in page_caps]
        if aligned:
            item["capability_ids"] = aligned
            continue
        if page_caps:
            item["capability_ids"] = page_caps[:1]
            continue
        if not evidence_caps:
            item["capability_ids"] = ["CAP-UNSPECIFIED"]

def _evidence_by_id(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in (payload.get("evidence") or [])
        if isinstance(item, dict) and item.get("id")
    }

def _sanitize_state_and_journey_evidence(payload: dict[str, Any]) -> None:
    evidence = _evidence_by_id(payload)
    for state in payload.get("states") or []:
        if not isinstance(state, dict):
            continue
        page_id = str(state.get("page_id") or "")
        state["evidence_ids"] = [
            evidence_id
            for evidence_id in (state.get("evidence_ids") or [])
            if str(evidence.get(str(evidence_id), {}).get("page_id") or "") == page_id
        ]

    for journey in payload.get("journeys") or []:
        if not isinstance(journey, dict):
            continue
        for step in journey.get("steps") or []:
            if not isinstance(step, dict):
                continue
            page_id = str(step.get("expected_page_id") or "")
            step["evidence_ids"] = [
                evidence_id
                for evidence_id in (step.get("evidence_ids") or [])
                if str(evidence.get(str(evidence_id), {}).get("page_id") or "") == page_id
            ]

def _sanitize_route_assertions(payload: dict[str, Any]) -> None:
    pages = [
        item for item in (payload.get("pages") or []) if isinstance(item, dict) and item.get("id")
    ]
    route_to_page = {
        _sanitize_route(page.get("route")): str(page.get("id")) for page in pages
    }
    for test in payload.get("acceptance_tests") or []:
        if not isinstance(test, dict):
            continue
        for assertion in test.get("assertions") or []:
            if not isinstance(assertion, dict):
                continue
            if str(assertion.get("kind")) != "route":
                continue
            if assertion.get("page_id"):
                continue
            expected = _sanitize_route(assertion.get("expected") or "/")
            page_id = route_to_page.get(expected)
            if page_id is None:
                # Longest matching prefix among known routes.
                matches = [
                    (route, pid)
                    for route, pid in route_to_page.items()
                    if expected.startswith(route.rstrip("/") + "/") or expected == route
                ]
                matches.sort(key=lambda item: len(item[0]), reverse=True)
                page_id = matches[0][1] if matches else (str(pages[0].get("id")) if pages else None)
            if page_id:
                assertion["page_id"] = page_id

def _sanitize_page_evidence_membership(payload: dict[str, Any]) -> None:
    evidence_by_page: dict[str, list[str]] = {}
    for item in payload.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        page_id = str(item.get("page_id") or "")
        evidence_id = str(item.get("id") or "")
        if page_id and evidence_id:
            evidence_by_page.setdefault(page_id, []).append(evidence_id)
    for page in payload.get("pages") or []:
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("id") or "")
        known = evidence_by_page.get(page_id, [])
        known_set = set(known)
        merged: list[str] = []
        seen: set[str] = set()
        for evidence_id in list(page.get("evidence_ids") or []) + known:
            text = str(evidence_id)
            if text in known_set and text not in seen:
                merged.append(text)
                seen.add(text)
        page["evidence_ids"] = merged
