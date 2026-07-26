"""Deterministic baseline accessibility gate (not Axe or WCAG certification)."""
from __future__ import annotations

import time

from app.application.preview_app.testing.failure_injection import (
    raise_if_injected,
)
from app.domain.schemas.runtime_validation import (
    AccessibilityFinding,
    AccessibilityRouteResult,
    RuntimeValidationRefs,
)


_BASELINE_SCRIPT = r"""
() => {
  const findings = [];
  const selector = (node) => {
    if (node.id) return `#${CSS.escape(node.id)}`;
    const bmv = [...node.attributes].find((a) => a.name.startsWith("data-bmv-"));
    if (bmv) return `[${bmv.name}="${CSS.escape(bmv.value)}"]`;
    const tag = node.tagName.toLowerCase();
    const siblings = node.parentElement
      ? [...node.parentElement.children].filter((x) => x.tagName === node.tagName)
      : [];
    return siblings.length > 1 ? `${tag}:nth-of-type(${siblings.indexOf(node) + 1})` : tag;
  };
  const add = (rule, severity, node, evidence) =>
    findings.push({
      rule_id: rule,
      severity,
      selector: selector(node),
      diagnostic_evidence: evidence,
    });
  const visible = (node) => {
    const style = getComputedStyle(node);
    const box = node.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden"
      && Number(style.opacity || 1) > 0 && box.width > 0 && box.height > 0;
  };
  const name = (node) => {
    const labelled = node.getAttribute("aria-labelledby");
    if (labelled) {
      return labelled.split(/\s+/).map((id) => document.getElementById(id)?.textContent || "").join(" ").trim();
    }
    if (node.labels?.length) {
      return [...node.labels].map((label) => label.textContent || "").join(" ").trim();
    }
    return (node.getAttribute("aria-label") || node.getAttribute("alt")
      || node.getAttribute("title") || node.textContent || "").trim();
  };
  for (const node of document.querySelectorAll(
    'button, a[href], input:not([type="hidden"]), select, textarea, [role="button"]'
  )) {
    if (visible(node) && !name(node)) add("required-control-name", "serious", node, "Visible control has no accessible name.");
  }
  for (const node of document.querySelectorAll('input:not([type="hidden"]), select, textarea')) {
    const labelled = node.labels?.length || node.hasAttribute("aria-label") || node.hasAttribute("aria-labelledby");
    if (visible(node) && !labelled) add("form-control-label", "serious", node, "Visible form control has no programmatic label.");
  }
  for (const node of document.querySelectorAll("img")) {
    if (!node.hasAttribute("alt") && node.getAttribute("role") !== "presentation") {
      add("image-alt", "serious", node, "Image lacks alt text or presentation role.");
    }
  }
  const headings = [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")].filter(visible);
  let previous = 0;
  for (const heading of headings) {
    const level = Number(heading.tagName.slice(1));
    if (previous && level > previous + 1) add("heading-hierarchy", "moderate", heading, `Heading level jumps from h${previous} to h${level}.`);
    previous = level;
  }
  if (!document.querySelector("main,[role=main]")) {
    add("main-landmark", "serious", document.body, "Page has no main landmark.");
  }
  for (const node of document.querySelectorAll("[data-bmv-action-id]")) {
    if (visible(node) && (node.tabIndex < 0 || node.hasAttribute("disabled"))) {
      add("required-action-keyboard", "serious", node, "Required action is not keyboard reachable.");
    }
    if (visible(node) && typeof node.focus === "function") {
      node.focus();
      const style = getComputedStyle(node);
      if (
        document.activeElement === node
        && style.outlineStyle === "none"
        && style.boxShadow === "none"
      ) {
        add("visible-focus", "serious", node, "Focused required action has no visible outline or shadow.");
      }
    }
  }
  for (const dialog of document.querySelectorAll('[role="dialog"],dialog[open]')) {
    if (visible(dialog) && !dialog.contains(document.activeElement)) {
      add("dialog-focus-containment", "critical", dialog, "Open dialog does not contain focus.");
    }
  }
  const parse = (value) => {
    const match = value.match(
      /rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([0-9.]+))?/
    );
    if (!match || (match[4] !== undefined && Number(match[4]) === 0)) {
      return null;
    }
    return match.slice(1, 4).map(Number);
  };
  const luminance = (rgb) => {
    const values = rgb.map((v) => {
      const x = v / 255;
      return x <= .03928 ? x / 12.92 : Math.pow((x + .055) / 1.055, 2.4);
    });
    return .2126 * values[0] + .7152 * values[1] + .0722 * values[2];
  };
  for (const node of document.querySelectorAll("[data-bmv-action-id],p,h1,h2,h3")) {
    if (!visible(node)) continue;
    const style = getComputedStyle(node);
    const fg = parse(style.color);
    const bg = parse(style.backgroundColor) || [255, 255, 255];
    if (!fg) continue;
    const ratio = (Math.max(luminance(fg), luminance(bg)) + .05)
      / (Math.min(luminance(fg), luminance(bg)) + .05);
    if (ratio < 3) add("obvious-computed-contrast", "serious", node, `Computed contrast ratio ${ratio.toFixed(2)} is below 3:1.`);
  }
  return findings;
}
"""


def run_baseline_accessibility_scan(
    page,
    *,
    refs: RuntimeValidationRefs,
    cache_key: str,
    build_hash: str,
    page_id: str,
    route: str,
    viewport: str,
) -> AccessibilityRouteResult:
    raise_if_injected("runtime_accessibility")
    started = time.monotonic()
    raw = page.evaluate(_BASELINE_SCRIPT)
    findings = tuple(AccessibilityFinding.model_validate(item) for item in raw)
    blocking = any(
        item.severity in {"serious", "critical"} for item in findings
    )
    return AccessibilityRouteResult(
        refs=refs,
        cache_key=cache_key,
        build_hash=build_hash,
        page_id=page_id,
        route=route,
        viewport=viewport,
        passed=not blocking,
        findings=findings,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


__all__ = ["run_baseline_accessibility_scan"]
