"""AppSpec sanitize — cross-cutting alignment repairs."""
from __future__ import annotations

from typing import Any

from app.domain.appspec.sanitize.evidence import _evidence_by_id

def _sanitize_trace_journeys_and_tests(payload: dict[str, Any]) -> None:
    journeys = {
        str(item.get("id")): item
        for item in (payload.get("journeys") or [])
        if isinstance(item, dict) and item.get("id")
    }
    tests = {
        str(item.get("id")): item
        for item in (payload.get("acceptance_tests") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for link in payload.get("traceability") or []:
        if not isinstance(link, dict):
            continue
        requirement_id = str(link.get("requirement_id") or "")
        if not requirement_id:
            continue
        journey_ids = [str(value) for value in (link.get("journey_ids") or [])]
        kept_journeys: list[str] = []
        for journey_id in journey_ids:
            journey = journeys.get(journey_id)
            if journey is None:
                continue
            reqs = [str(value) for value in (journey.get("requirement_ids") or [])]
            if requirement_id not in reqs:
                reqs.append(requirement_id)
                journey["requirement_ids"] = reqs
            kept_journeys.append(journey_id)
        link["journey_ids"] = kept_journeys

        test_ids = [str(value) for value in (link.get("acceptance_test_ids") or [])]
        for test_id in test_ids:
            test = tests.get(test_id)
            if test is None:
                continue
            reqs = [str(value) for value in (test.get("requirement_ids") or [])]
            if requirement_id not in reqs:
                reqs.append(requirement_id)
                test["requirement_ids"] = reqs
            if kept_journeys and not test.get("journey_id"):
                test["journey_id"] = kept_journeys[0]
            elif kept_journeys and str(test.get("journey_id")) not in kept_journeys:
                test["journey_id"] = kept_journeys[0]
            # Keep the test's journey in sync when traceability forces a requirement
            # onto an acceptance test that already points at a different journey.
            journey = journeys.get(str(test.get("journey_id") or ""))
            if journey is not None:
                journey_reqs = [
                    str(value) for value in (journey.get("requirement_ids") or [])
                ]
                if requirement_id not in journey_reqs:
                    journey_reqs.append(requirement_id)
                    journey["requirement_ids"] = journey_reqs

def _sanitize_action_capability_page_alignment(payload: dict[str, Any]) -> None:
    pages = {
        str(item.get("id")): item
        for item in (payload.get("pages") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for action in payload.get("actions") or []:
        if not isinstance(action, dict):
            continue
        page = pages.get(str(action.get("page_id") or ""))
        if page is None:
            continue
        page_caps = [str(value) for value in (page.get("capability_ids") or [])]
        action_caps = [str(value) for value in (action.get("capability_ids") or [])]
        aligned = [cap for cap in action_caps if cap in page_caps]
        if aligned:
            action["capability_ids"] = aligned
            continue
        if page_caps:
            action["capability_ids"] = page_caps[:1]
            continue
        # Keep at least one capability id for schema; page will be repaired later.
        if not action_caps:
            action["capability_ids"] = ["CAP-UNSPECIFIED"]


def _sanitize_action_capability_role_alignment(payload: dict[str, Any]) -> None:
    """Grant each action's role on every capability the action cites."""

    capabilities = {
        str(item.get("id")): item
        for item in (payload.get("capabilities") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for action in payload.get("actions") or []:
        if not isinstance(action, dict):
            continue
        role_id = str(action.get("role_id") or "")
        if not role_id:
            continue
        for capability_id in action.get("capability_ids") or []:
            capability = capabilities.get(str(capability_id))
            if capability is None:
                continue
            roles = [str(value) for value in (capability.get("role_ids") or [])]
            if role_id not in roles:
                roles.append(role_id)
                capability["role_ids"] = roles


def _sanitize_action_entity_capability_alignment(payload: dict[str, Any]) -> None:
    """Ensure action.entity_id is declared on every capability the action cites."""

    capabilities = {
        str(item.get("id")): item
        for item in (payload.get("capabilities") or [])
        if isinstance(item, dict) and item.get("id")
    }
    entities = {
        str(item.get("id"))
        for item in (payload.get("entities") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for action in payload.get("actions") or []:
        if not isinstance(action, dict):
            continue
        entity_id = str(action.get("entity_id") or "")
        if not entity_id or entity_id not in entities:
            continue
        for capability_id in action.get("capability_ids") or []:
            capability = capabilities.get(str(capability_id))
            if capability is None:
                continue
            entity_ids = [str(value) for value in (capability.get("entity_ids") or [])]
            if entity_id not in entity_ids:
                entity_ids.append(entity_id)
                capability["entity_ids"] = entity_ids

def _sanitize_page_state_membership(payload: dict[str, Any]) -> None:
    states_by_page: dict[str, list[str]] = {}
    for state in payload.get("states") or []:
        if not isinstance(state, dict):
            continue
        page_id = str(state.get("page_id") or "")
        state_id = str(state.get("id") or "")
        if page_id and state_id:
            states_by_page.setdefault(page_id, []).append(state_id)
    for page in payload.get("pages") or []:
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("id") or "")
        merged: list[str] = []
        seen: set[str] = set()
        for state_id in list(page.get("state_ids") or []) + states_by_page.get(page_id, []):
            text = str(state_id)
            if text and text not in seen:
                merged.append(text)
                seen.add(text)
        page["state_ids"] = merged

def _sanitize_traceability_alignment(payload: dict[str, Any]) -> None:
    pages = {
        str(item.get("id")): item
        for item in (payload.get("pages") or [])
        if isinstance(item, dict) and item.get("id")
    }
    evidence = _evidence_by_id(payload)
    capabilities = {
        str(item.get("id")): item
        for item in (payload.get("capabilities") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for link in payload.get("traceability") or []:
        if not isinstance(link, dict):
            continue
        requirement_id = str(link.get("requirement_id") or "")
        capability_ids = [
            str(value)
            for value in (link.get("capability_ids") or [])
            if str(value) in capabilities
        ]
        if not capability_ids:
            continue
        if requirement_id:
            for capability_id in capability_ids:
                capability = capabilities[capability_id]
                reqs = [str(value) for value in (capability.get("requirement_ids") or [])]
                if requirement_id not in reqs:
                    reqs.append(requirement_id)
                    capability["requirement_ids"] = reqs
        capability_set = set(capability_ids)
        page_ids = [
            page_id
            for page_id in (link.get("page_ids") or [])
            if page_id in pages
            and capability_set.intersection(
                {str(value) for value in (pages[page_id].get("capability_ids") or [])}
            )
        ]
        if not page_ids:
            # Prefer pages that expose any traced capability.
            page_ids = [
                page_id
                for page_id, page in pages.items()
                if capability_set.intersection(
                    {str(value) for value in (page.get("capability_ids") or [])}
                )
            ][:3]
        page_set = set(page_ids)
        evidence_ids = [
            evidence_id
            for evidence_id in (link.get("evidence_ids") or [])
            if evidence_id in evidence
            and str(evidence[evidence_id].get("page_id") or "") in page_set
            and capability_set.intersection(
                {str(value) for value in (evidence[evidence_id].get("capability_ids") or [])}
            )
        ]
        if not evidence_ids:
            evidence_ids = [
                evidence_id
                for evidence_id, item in evidence.items()
                if str(item.get("page_id") or "") in page_set
                and capability_set.intersection(
                    {str(value) for value in (item.get("capability_ids") or [])}
                )
            ][:5]
        link["capability_ids"] = capability_ids
        if page_ids:
            link["page_ids"] = page_ids
        if evidence_ids:
            link["evidence_ids"] = evidence_ids

def _sanitize_traceability_acceptance_tests(payload: dict[str, Any]) -> None:
    """Schema requires every traceability link to cite at least one acceptance test."""

    tests = {
        str(item.get("id")): item
        for item in (payload.get("acceptance_tests") or [])
        if isinstance(item, dict) and item.get("id")
    }
    if not tests:
        # Cannot satisfy min_length without inventing a whole test graph; drop links.
        payload["traceability"] = []
        return

    tests_by_requirement: dict[str, list[str]] = {}
    for test_id, test in tests.items():
        for requirement_id in test.get("requirement_ids") or []:
            tests_by_requirement.setdefault(str(requirement_id), []).append(test_id)

    tests_by_journey: dict[str, list[str]] = {}
    for test_id, test in tests.items():
        journey_id = str(test.get("journey_id") or "")
        if journey_id:
            tests_by_journey.setdefault(journey_id, []).append(test_id)

    kept_links: list[dict[str, Any]] = []
    for link in payload.get("traceability") or []:
        if not isinstance(link, dict):
            continue
        requirement_id = str(link.get("requirement_id") or "")
        existing = [
            test_id
            for test_id in (link.get("acceptance_test_ids") or [])
            if str(test_id) in tests
        ]
        if existing:
            link["acceptance_test_ids"] = existing
            kept_links.append(link)
            continue

        matched = list(tests_by_requirement.get(requirement_id) or [])
        if not matched:
            for journey_id in link.get("journey_ids") or []:
                matched.extend(tests_by_journey.get(str(journey_id)) or [])
        if not matched:
            matched = [next(iter(tests))]

        # Deduplicate while preserving order.
        seen: set[str] = set()
        acceptance_test_ids: list[str] = []
        for test_id in matched:
            text = str(test_id)
            if text and text not in seen:
                acceptance_test_ids.append(text)
                seen.add(text)
        link["acceptance_test_ids"] = acceptance_test_ids[:5]
        for test_id in link["acceptance_test_ids"]:
            test = tests[test_id]
            reqs = [str(value) for value in (test.get("requirement_ids") or [])]
            if requirement_id and requirement_id not in reqs:
                reqs.append(requirement_id)
                test["requirement_ids"] = reqs
        kept_links.append(link)
    payload["traceability"] = kept_links
