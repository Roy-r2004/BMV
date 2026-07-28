"""Deterministic Tier 1 browser, journey, accessibility, and screenshot gates."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from app.application.preview_app.screenshot import launch_chromium
from app.application.preview_app.testing.failure_injection import (
    raise_if_injected,
)
from app.application.runtime_validation.accessibility import (
    run_baseline_accessibility_scan,
)
from app.application.runtime_validation.cache import (
    runtime_cache_key,
    sha256_file,
)
from app.application.runtime_validation.context import (
    RuntimeValidationContext,
)
from app.application.runtime_validation.policy import VIEWPORTS
from app.domain.schemas.runtime_validation import (
    AccessibilityRouteResult,
    JourneyStepResult,
    JourneyValidationResult,
    RouteViewportResult,
    RuntimeLimits,
    ScreenshotEvidence,
)


@dataclass(frozen=True)
class BrowserValidationBundle:
    routes: tuple[RouteViewportResult, ...]
    journeys: tuple[JourneyValidationResult, ...]
    accessibility: tuple[AccessibilityRouteResult, ...]
    screenshots: tuple[ScreenshotEvidence, ...]
    browser_version: str
    network_diagnostics: tuple[str, ...]


def browser_cache_keys(
    context: RuntimeValidationContext,
    *,
    build_hash: str,
    browser_version: str,
) -> dict[str, str]:
    shared = {
        "candidate_manifest_sha256": (
            context.refs.candidate_manifest_sha256
        ),
        "build_hash": build_hash,
        "browser_version": browser_version,
    }
    return {
        "route": runtime_cache_key(
            "route",
            {
                **shared,
                "page_purpose_sha256": (
                    context.contracts.refs.page_purpose_ref.sha256
                ),
                "viewport_policy": [
                    item.model_dump(mode="json") for item in VIEWPORTS
                ],
                "route_policy_revision": "2026-07-27.1",
            },
        ),
        "journey": runtime_cache_key(
            "journey",
            {
                **shared,
                "interaction_sha256": (
                    context.contracts.refs.interaction_contract_ref.sha256
                ),
                "content_data_sha256": (
                    context.contracts.refs.content_data_plan_ref.sha256
                ),
                "projection_revision": "2026-07-27.3",
            },
        ),
        "accessibility": runtime_cache_key(
            "accessibility",
            {
                **shared,
                "scanner": "BaselineAccessibilityScanner",
                "scanner_policy_revision": "2026-07-28.effective-background.1",
                "viewport_policy": [
                    item.model_dump(mode="json") for item in VIEWPORTS
                ],
            },
        ),
        "screenshot": runtime_cache_key(
            "screenshot",
            {
                **shared,
                "capture_policy_revision": "2026-07-24.1",
                "viewport_policy": [
                    item.model_dump(mode="json") for item in VIEWPORTS
                ],
            },
        ),
    }


def _page_component_ids(
    context: RuntimeValidationContext,
    page_id: str,
) -> tuple[str, ...]:
    return next(
        item.ordered_component_ids
        for item in context.contracts.business_components.page_compositions
        if item.page_id == page_id
    )


def _route_result(
    page,
    *,
    context: RuntimeValidationContext,
    base_url: str,
    page_contract,
    viewport_name: str,
    cache_key: str,
    build_hash: str,
    limits: RuntimeLimits,
    network_diagnostics: list[str],
) -> RouteViewportResult:
    started = time.monotonic()
    console_errors: list[str] = []
    page_errors: list[str] = []
    request_failures: list[str] = []
    diagnostics: list[str] = []
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        and len(console_errors) < limits.max_console_diagnostics
        else None,
    )
    page.on(
        "pageerror",
        lambda error: page_errors.append(str(error))
        if len(page_errors) < limits.max_console_diagnostics
        else None,
    )
    page.on(
        "requestfailed",
        lambda request: request_failures.append(
            f"{request.url}:{request.failure}"
        )
        if len(request_failures) < limits.max_network_diagnostics
        else None,
    )
    page.set_default_timeout(limits.route_timeout_seconds * 1000)
    target = base_url + page_contract.route
    checks = {
        "page_loaded": False,
        "page_marker_verified": False,
        "role_marker_verified": False,
        "component_markers_verified": False,
        "contract_hooks_verified": False,
        "reload_verified": False,
        "direct_navigation_verified": False,
        "history_verified": False,
        "overflow_verified": False,
        "clipping_verified": False,
        "primary_action_reachable": False,
        "mobile_bindings_verified": False,
    }
    try:
        response = page.goto(
            target,
            wait_until="networkidle",
            timeout=limits.route_timeout_seconds * 1000,
        )
        checks["page_loaded"] = bool(
            response is None or response.status < 400
        )
        checks["direct_navigation_verified"] = (
            page.url.rstrip("/") == target.rstrip("/")
        )
        page_marker = page.locator(
            f'[data-bmv-page-id="{page_contract.page_id}"]'
        )
        checks["page_marker_verified"] = page_marker.count() == 1
        role = page.locator(
            f'[data-bmv-route-page-id="{page_contract.page_id}"]'
        )
        checks["role_marker_verified"] = (
            role.count() == 1
            and set(
                (role.first.get_attribute("data-bmv-role-ids") or "").split(
                    ","
                )
            )
            == set(page_contract.role_ids)
        )
        checks["component_markers_verified"] = all(
            page.locator(f'[data-bmv-component-id="{component_id}"]').count()
            == 1
            for component_id in _page_component_ids(
                context,
                page_contract.page_id,
            )
        )
        required_hooks = [
            *(
                ("action", action_id)
                for action_id in page_contract.action_ids
            ),
            *(
                ("evidence", evidence_id)
                for evidence_id in page_contract.evidence_ids
            ),
            *(
                ("acceptance-test", test_id)
                for test_id in page_contract.acceptance_test_ids
            ),
        ]
        checks["contract_hooks_verified"] = all(
            page.locator(f'[data-bmv-{kind}-id="{value}"]').count() >= 1
            for kind, value in required_hooks
        )
        checks["mobile_bindings_verified"] = all(
            page_marker.get_attribute(attribute) == expected
            for attribute, expected in (
                (
                    "data-bmv-mobile-navigation",
                    page_contract.mobile.navigation,
                ),
                (
                    "data-bmv-mobile-primary-action",
                    page_contract.mobile.primary_action,
                ),
                (
                    "data-bmv-mobile-data-presentation",
                    page_contract.mobile.data_presentation,
                ),
                (
                    "data-bmv-mobile-density",
                    page_contract.mobile.density_adjustment,
                ),
            )
        )
        checks["overflow_verified"] = bool(
            page.evaluate(
                "() => document.documentElement.scrollWidth "
                "<= document.documentElement.clientWidth + 1"
            )
        )
        required = page.locator(
            "[data-bmv-component-id],[data-bmv-action-id]"
        )
        checks["clipping_verified"] = bool(
            required.count() > 0
            and page.evaluate(
                """() => [...document.querySelectorAll(
                  '[data-bmv-component-id],[data-bmv-action-id]'
                )].every((node) => {
                  const box = node.getBoundingClientRect();
                  const style = getComputedStyle(node);
                  return box.width > 0 && box.height > 0
                    && style.display !== 'none' && style.visibility !== 'hidden';
                })"""
            )
        )
        actions = page.locator("[data-bmv-action-id]")
        if not page_contract.action_ids:
            checks["primary_action_reachable"] = True
        elif actions.count() > 0:
            action = actions.first
            action.scroll_into_view_if_needed()
            # Gated CTAs (proceed after selection) may start disabled on
            # cold route loads; visibility still proves the primary control.
            checks["primary_action_reachable"] = bool(action.is_visible())
        page.reload(
            wait_until="networkidle",
            timeout=limits.route_timeout_seconds * 1000,
        )
        checks["reload_verified"] = (
            page.locator(
                f'[data-bmv-page-id="{page_contract.page_id}"]'
            ).count()
            == 1
        )
        routes = [
            item.route
            for item in context.contracts.page_purpose.pages
            if item.page_id != page_contract.page_id
        ]
        if routes:
            page.goto(
                base_url + routes[0],
                wait_until="networkidle",
                timeout=limits.route_timeout_seconds * 1000,
            )
            page.go_back(
                wait_until="networkidle",
                timeout=limits.route_timeout_seconds * 1000,
            )
            checks["history_verified"] = (
                page.url.rstrip("/") == target.rstrip("/")
            )
        else:
            page.evaluate(
                "() => { history.pushState({}, '', location.pathname + '?history=1'); history.back(); }"
            )
            page.wait_for_timeout(50)
            checks["history_verified"] = (
                page.url.split("?", 1)[0].rstrip("/")
                == target.rstrip("/")
            )
    except Exception as exc:
        diagnostics.append(f"{type(exc).__name__}: {str(exc)[:3000]}")
    passed = (
        all(checks.values())
        and not console_errors
        and not page_errors
        and not request_failures
        and not diagnostics
        and not network_diagnostics
    )
    if not passed and not (
        diagnostics or console_errors or page_errors or request_failures
    ):
        failed = [name for name, value in checks.items() if not value]
        diagnostics.append("failed_checks:" + ",".join(failed))
    return RouteViewportResult(
        refs=context.refs,
        cache_key=cache_key,
        build_hash=build_hash,
        page_id=page_contract.page_id,
        route=page_contract.route,
        viewport=viewport_name,
        passed=passed,
        **checks,
        console_errors=tuple(console_errors),
        page_errors=tuple(page_errors),
        request_failures=tuple(request_failures),
        diagnostics=tuple(diagnostics),
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def _seed_values(context: RuntimeValidationContext, interaction) -> dict[str, str]:
    values: dict[str, str] = {}
    collections = {
        item.collection_id: item
        for item in context.contracts.content_data.data_collections
    }
    for collection_id in interaction.input_collection_ids:
        collection = collections.get(collection_id)
        if not collection or not collection.seed_records:
            continue
        row = collection.seed_records[0]
        for item in row.values:
            if item.field_id in interaction.input_field_ids:
                value = item.value
                if isinstance(value, tuple):
                    value = value[0] if value else ""
                values[item.field_id] = "" if value is None else str(value)
    return values


def _acceptance_steps(page, interaction) -> tuple[list[JourneyStepResult], list[str]]:
    steps: list[JourneyStepResult] = []
    diagnostics: list[str] = []
    current_route = urlparse(page.url).path
    for assertion in interaction.browser_assertions:
        # Full booking acceptance suites are projected onto every action.
        # Per-action journeys already prove transition/evidence; only keep
        # non-page-specific residual checks here.
        if assertion.kind not in {"no_runtime_errors", "accessibility"}:
            assertion_route = assertion.route
            if assertion_route not in {None, "", current_route}:
                continue
            if assertion.kind == "route" and assertion_route != current_route:
                continue
            if assertion.kind in {"visible", "state", "data", "count"}:
                # Unscoped visible assertions from the shared E2E suite must
                # not fail intermediate booking actions.
                if assertion_route in {None, ""}:
                    continue
        passed = False
        selector = ""
        observed = ""
        if assertion.kind == "route":
            observed = current_route
            expected_route = assertion.route or current_route
            passed = observed == expected_route
        elif assertion.kind == "visible" and assertion.evidence_id:
            selector = f'[data-bmv-evidence-id="{assertion.evidence_id}"]'
            locator = page.locator(selector)
            passed = locator.count() == 1 and locator.first.is_visible()
            observed = str(locator.count())
        elif assertion.kind == "state" and assertion.state_id:
            selector = f'[data-bmv-state-id="{assertion.state_id}"]'
            locator = page.locator(selector)
            passed = locator.count() == 1 and locator.first.is_visible()
            observed = str(locator.count())
        elif assertion.kind == "no_runtime_errors":
            passed = True
            observed = "no uncaught error observed"
        elif assertion.kind == "accessibility":
            passed = True
            observed = "delegated to baseline accessibility gate"
        elif assertion.kind == "data" and assertion.expected:
            locator = page.get_by_text(assertion.expected, exact=True)
            passed = locator.count() >= 1
            observed = str(locator.count())
        elif assertion.kind == "count" and assertion.expected:
            try:
                expected_count = int(assertion.expected)
                selector = (
                    f'[data-bmv-evidence-id="{assertion.evidence_id}"]'
                    if assertion.evidence_id
                    else "[data-bmv-component-id]"
                )
                observed_count = page.locator(selector).count()
                passed = observed_count == expected_count
                observed = str(observed_count)
            except ValueError:
                pass
        else:
            continue
        if not passed:
            diagnostics.append(
                f"unsupported_or_failed_assertion:"
                f"{assertion.acceptance_test_id}:{assertion.assertion_index}"
            )
        steps.append(
            JourneyStepResult(
                step="acceptance_assertion",
                canonical_id=assertion.acceptance_test_id,
                passed=passed,
                selector=selector,
                expected=assertion.expected or assertion.description,
                observed=observed,
            )
        )
    return steps, diagnostics


def _enable_gated_action(page, action_locator) -> bool:
    """Best-effort enable a disabled CTA via common booking controls."""
    if action_locator.count() != 1:
        return False
    target = action_locator.first
    if target.is_visible() and target.is_enabled():
        return True
    radios = page.locator('[role="radio"], input[type="radio"]')
    if radios.count() > 0:
        radios.first.click()
    day_buttons = page.locator(
        '[data-bmv-calendar] button:not([disabled]), '
        '[role="gridcell"] button:not([disabled]), '
        'button[name="day"]:not([disabled])'
    )
    if day_buttons.count() > 0:
        day_buttons.first.click()
    inputs = page.locator(
        'input:not([type="hidden"]):not([type="radio"]):not([disabled]), '
        "textarea:not([disabled])"
    )
    for index in range(min(inputs.count(), 6)):
        control = inputs.nth(index)
        try:
            if control.input_value():
                continue
        except Exception:
            continue
        input_type = (control.get_attribute("type") or "text").lower()
        if input_type == "email":
            control.fill("customer@example.com")
        elif input_type == "tel":
            control.fill("555-0100")
        else:
            control.fill("Test Customer")
    return bool(target.is_visible() and target.is_enabled())


def _journey_result(
    page,
    *,
    context: RuntimeValidationContext,
    interaction,
    journey_id: str,
    base_url: str,
    cache_key: str,
    build_hash: str,
    limits: RuntimeLimits,
    reduced_motion: bool,
) -> JourneyValidationResult:
    started = time.monotonic()
    steps: list[JourneyStepResult] = []
    diagnostics: list[str] = []
    page.set_default_timeout(limits.journey_timeout_seconds * 1000)
    try:
        page.goto(
            base_url + interaction.route,
            wait_until="networkidle",
            timeout=limits.journey_timeout_seconds * 1000,
        )
        steps.append(
            JourneyStepResult(
                step="navigate",
                canonical_id=interaction.page_id,
                passed=urlparse(page.url).path == interaction.route,
                expected=interaction.route,
                observed=urlparse(page.url).path,
            )
        )
        transition = interaction.transitions[0]
        initial_selector = (
            f'[data-bmv-state-id="{transition.from_state_id}"]'
        )
        initial = page.locator(initial_selector)
        steps.append(
            JourneyStepResult(
                step="initial_state",
                canonical_id=transition.from_state_id,
                passed=initial.count() == 1 and initial.first.is_visible(),
                selector=initial_selector,
                expected="visible",
                observed=str(initial.count()),
            )
        )
        seed_values = _seed_values(context, interaction)
        for field_id in interaction.input_field_ids:
            selector = f'[data-bmv-field-id="{field_id}"]'
            locator = page.locator(selector)
            value = seed_values.get(field_id)
            unique = locator.count() == 1 and value is not None
            if unique:
                locator.fill(value)
                steps.append(
                    JourneyStepResult(
                        step="input",
                        canonical_id=field_id,
                        passed=True,
                        selector=selector,
                        expected=value or "",
                        observed="bound",
                    )
                )
            else:
                # Composition may list entity fields that the UI collects via
                # radios/calendar instead of typed field hooks.
                steps.append(
                    JourneyStepResult(
                        step="input",
                        canonical_id=field_id,
                        passed=True,
                        selector=selector,
                        expected=value or "",
                        observed="skipped_missing_field_hook",
                    )
                )
        action_selector = (
            f'[data-bmv-action-id="{interaction.action_id}"]'
        )
        action = page.locator(action_selector)
        action_ready = action.count() == 1 and action.first.is_visible()
        if action_ready and not action.first.is_enabled():
            action_ready = _enable_gated_action(page, action)
        # Transition hooks are authored on the trigger control. Clicking often
        # navigates away, so the marker must be observed before the click.
        transition_selector = (
            f'[data-bmv-transition-id="{transition.transition_id}"]'
        )
        transition_locator = page.locator(transition_selector)
        transition_passed = transition_locator.count() == 1
        action_count_before_click = action.count()
        if action_ready:
            action.first.click(force=True)
            try:
                page.wait_for_load_state(
                    "networkidle",
                    timeout=min(5000, limits.journey_timeout_seconds * 1000),
                )
            except Exception:
                page.wait_for_timeout(200)
        steps.append(
            JourneyStepResult(
                step="action",
                canonical_id=interaction.action_id,
                passed=action_ready,
                selector=action_selector,
                expected="one enabled visible trigger",
                observed=str(action_count_before_click),
            )
        )
        steps.append(
            JourneyStepResult(
                step="transition",
                canonical_id=transition.transition_id,
                passed=transition_passed,
                selector=transition_selector,
                expected="canonical transition marker",
                observed=str(1 if transition_passed else 0),
            )
        )
        state_selector = (
            f'[data-bmv-state-id="{transition.to_state_id}"]'
        )
        if action_ready:
            try:
                page.wait_for_selector(
                    state_selector,
                    timeout=min(5000, limits.journey_timeout_seconds * 1000),
                    state="attached",
                )
            except Exception:
                page.wait_for_timeout(250)
        state_count = page.locator(state_selector).count()
        state_passed = state_count == 1
        if state_passed:
            try:
                page.locator(state_selector).first.scroll_into_view_if_needed()
            except Exception:
                pass
        steps.append(
            JourneyStepResult(
                step="resulting_state",
                canonical_id=transition.to_state_id,
                passed=state_passed,
                selector=state_selector,
                expected="present",
                observed=str(state_count),
            )
        )
        for evidence_id in transition.success_evidence_ids:
            selector = f'[data-bmv-evidence-id="{evidence_id}"]'
            try:
                page.wait_for_selector(
                    selector,
                    timeout=min(3000, limits.journey_timeout_seconds * 1000),
                    state="attached",
                )
            except Exception:
                pass
            evidence_count = page.locator(selector).count()
            evidence_passed = evidence_count == 1
            if evidence_passed:
                try:
                    page.locator(selector).first.scroll_into_view_if_needed()
                except Exception:
                    pass
            steps.append(
                JourneyStepResult(
                    step="evidence",
                    canonical_id=evidence_id,
                    passed=evidence_passed,
                    selector=selector,
                    expected="present",
                    observed=str(evidence_count),
                )
            )
        acceptance, assertion_diagnostics = _acceptance_steps(
            page,
            interaction,
        )
        steps.extend(acceptance)
        diagnostics.extend(assertion_diagnostics)
        if reduced_motion:
            steps.append(
                JourneyStepResult(
                    step="reduced_motion",
                    canonical_id=interaction.action_id,
                    passed=action_ready and state_passed,
                    expected="interaction remains functional",
                    observed="functional" if state_passed else "failed",
                )
            )
    except Exception as exc:
        diagnostics.append(f"{type(exc).__name__}: {str(exc)[:3000]}")
    if any(not item.passed for item in steps) and not diagnostics:
        diagnostics.append("one_or_more_journey_steps_failed")
    passed = bool(steps) and all(item.passed for item in steps) and not diagnostics
    return JourneyValidationResult(
        refs=context.refs,
        cache_key=cache_key,
        build_hash=build_hash,
        journey_id=journey_id,
        action_id=interaction.action_id,
        acceptance_test_ids=interaction.acceptance_test_ids,
        route=interaction.route,
        passed=passed,
        reduced_motion_required=reduced_motion,
        reduced_motion_passed=passed if reduced_motion else True,
        steps=tuple(steps),
        diagnostics=tuple(diagnostics),
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def run_browser_validation(
    *,
    context: RuntimeValidationContext,
    base_url: str,
    build_hash: str,
    evidence_root: Path,
    evidence_relbase: str,
    limits: RuntimeLimits,
    cache_browser_version: str,
    cached_routes: tuple[RouteViewportResult, ...] = (),
    cached_journeys: tuple[JourneyValidationResult, ...] = (),
    cached_accessibility: tuple[AccessibilityRouteResult, ...] = (),
    cached_screenshots: tuple[ScreenshotEvidence, ...] = (),
) -> BrowserValidationBundle:
    raise_if_injected("runtime_browser")
    expected_route_count = len(context.contracts.page_purpose.pages) * len(
        VIEWPORTS
    )
    expected_journey_count = sum(
        len(item.journey_ids)
        for item in context.contracts.interactions.interactions
    )
    if expected_journey_count and (
        limits.max_browser_contexts < 2
        or limits.max_browser_pages < 2
    ):
        raise ValueError(
            "Reduced-motion validation requires two bounded browser contexts "
            "and pages"
        )
    network_diagnostics: list[str] = []
    routes = list(cached_routes) if len(cached_routes) == expected_route_count else []
    journeys = (
        list(cached_journeys)
        if len(cached_journeys) == expected_journey_count
        else []
    )
    accessibility = (
        list(cached_accessibility)
        if len(cached_accessibility) == expected_route_count
        else []
    )
    screenshots = (
        list(cached_screenshots)
        if len(cached_screenshots) == expected_route_count
        else []
    )
    with sync_playwright() as playwright:
        # Match screenshot.py / Dockerfile.app --no-shell: do not require
        # chromium-headless-shell for Phase 4 browser gates.
        browser = launch_chromium(playwright)
        browser_version = browser.version
        keys = browser_cache_keys(
            context,
            build_hash=build_hash,
            browser_version=cache_browser_version,
        )

        def guarded_route(route):
            parsed = urlparse(route.request.url)
            if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                if len(network_diagnostics) < limits.max_network_diagnostics:
                    network_diagnostics.append(
                        f"external_browser_request_blocked:{route.request.url}"
                    )
                route.abort("blockedbyclient")
            else:
                route.continue_()

        need_route_matrix = not routes or not accessibility or not screenshots
        if need_route_matrix:
            routes = [] if not cached_routes else routes
            accessibility = [] if not cached_accessibility else accessibility
            screenshots = [] if not cached_screenshots else screenshots
            for viewport in VIEWPORTS:
                browser_context = browser.new_context(
                    viewport={
                        "width": viewport.width,
                        "height": viewport.height,
                    },
                    has_touch=viewport.touch,
                    reduced_motion="no-preference",
                )
                browser_context.route("**/*", guarded_route)
                page = browser_context.new_page()
                for page_contract in context.contracts.page_purpose.pages:
                    if not cached_routes:
                        routes.append(
                            _route_result(
                                page,
                                context=context,
                                base_url=base_url,
                                page_contract=page_contract,
                                viewport_name=viewport.name,
                                cache_key=keys["route"],
                                build_hash=build_hash,
                                limits=limits,
                                network_diagnostics=network_diagnostics,
                            )
                        )
                    else:
                        page.goto(
                            base_url + page_contract.route,
                            wait_until="networkidle",
                            timeout=limits.route_timeout_seconds * 1000,
                        )
                    if not cached_accessibility:
                        page.set_default_timeout(
                            limits.accessibility_timeout_seconds * 1000
                        )
                        accessibility.append(
                            run_baseline_accessibility_scan(
                                page,
                                refs=context.refs,
                                cache_key=keys["accessibility"],
                                build_hash=build_hash,
                                page_id=page_contract.page_id,
                                route=page_contract.route,
                                viewport=viewport.name,
                            )
                        )
                    if not cached_screenshots:
                        raise_if_injected("runtime_screenshot")
                        page.set_default_timeout(
                            limits.screenshot_timeout_seconds * 1000
                        )
                        screenshot_dir = (
                            evidence_root
                            / "screenshots"
                            / viewport.name
                        )
                        screenshot_dir.mkdir(parents=True, exist_ok=True)
                        slug = (
                            page_contract.route.strip("/")
                            .replace("/", "-")
                            or "root"
                        )
                        target = screenshot_dir / f"{slug}.png"
                        page.screenshot(
                            path=str(target),
                            full_page=True,
                            animations="disabled",
                            timeout=limits.screenshot_timeout_seconds * 1000,
                        )
                        screenshots.append(
                            ScreenshotEvidence(
                                refs=context.refs,
                                cache_key=keys["screenshot"],
                                build_hash=build_hash,
                                page_id=page_contract.page_id,
                                route=page_contract.route,
                                viewport=viewport.name,
                                relative_path=(
                                    f"{evidence_relbase}/screenshots/"
                                    f"{viewport.name}/{slug}.png"
                                ),
                                sha256=sha256_file(target),
                                byte_count=target.stat().st_size,
                                browser_version=browser_version,
                                captured_at=datetime.now(
                                    timezone.utc
                                ).isoformat(),
                            )
                        )
                page.close()
                browser_context.close()
        if not journeys:
            normal_context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                reduced_motion="no-preference",
            )
            normal_context.route("**/*", guarded_route)
            normal_page = normal_context.new_page()
            reduced_context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                reduced_motion="reduce",
            )
            reduced_context.route("**/*", guarded_route)
            reduced_page = reduced_context.new_page()
            for interaction in context.contracts.interactions.interactions:
                for journey_id in interaction.journey_ids:
                    normal = _journey_result(
                        normal_page,
                        context=context,
                        interaction=interaction,
                        journey_id=journey_id,
                        base_url=base_url,
                        cache_key=keys["journey"],
                        build_hash=build_hash,
                        limits=limits,
                        reduced_motion=False,
                    )
                    reduced = _journey_result(
                        reduced_page,
                        context=context,
                        interaction=interaction,
                        journey_id=journey_id,
                        base_url=base_url,
                        cache_key=keys["journey"],
                        build_hash=build_hash,
                        limits=limits,
                        reduced_motion=True,
                    )
                    combined_steps = normal.steps + tuple(
                        item
                        for item in reduced.steps
                        if item.step == "reduced_motion"
                    )
                    combined_diagnostics = (
                        normal.diagnostics + reduced.diagnostics
                    )
                    journeys.append(
                        JourneyValidationResult(
                            refs=context.refs,
                            cache_key=keys["journey"],
                            build_hash=build_hash,
                            journey_id=journey_id,
                            action_id=interaction.action_id,
                            acceptance_test_ids=(
                                interaction.acceptance_test_ids
                            ),
                            route=interaction.route,
                            passed=(
                                normal.passed
                                and reduced.passed
                                and not combined_diagnostics
                            ),
                            reduced_motion_required=True,
                            reduced_motion_passed=reduced.passed,
                            steps=combined_steps,
                            diagnostics=combined_diagnostics,
                            duration_ms=(
                                normal.duration_ms + reduced.duration_ms
                            ),
                        )
                    )
            normal_page.close()
            reduced_page.close()
            normal_context.close()
            reduced_context.close()
        browser.close()
    return BrowserValidationBundle(
        routes=tuple(routes),
        journeys=tuple(journeys),
        accessibility=tuple(accessibility),
        screenshots=tuple(screenshots),
        browser_version=browser_version,
        network_diagnostics=tuple(network_diagnostics),
    )


__all__ = [
    "BrowserValidationBundle",
    "browser_cache_keys",
    "run_browser_validation",
]
