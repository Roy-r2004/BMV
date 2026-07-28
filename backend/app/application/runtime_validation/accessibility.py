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
    // Disabled is a valid gated CTA state on route-entry scans (e.g. proceed
    // after selection). Only fail permanently non-tabbable actions.
    if (visible(node) && node.tabIndex < 0 && !node.hasAttribute("disabled")) {
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
    const raw = String(value == null ? "" : value).trim();
    if (!raw || raw === "transparent") return null;
    if (raw.startsWith("#")) {
      const hex = raw.slice(1);
      const expand = hex.length === 3 || hex.length === 4
        ? hex.split("").map((ch) => ch + ch).join("")
        : hex;
      if (expand.length < 6) return null;
      return {
        rgb: [
          parseInt(expand.slice(0, 2), 16),
          parseInt(expand.slice(2, 4), 16),
          parseInt(expand.slice(4, 6), 16),
        ],
        alpha: expand.length === 8
          ? parseInt(expand.slice(6, 8), 16) / 255
          : 1,
      };
    }
    const match = raw.match(
      /rgba?\(\s*([0-9.]+)[,\s]+([0-9.]+)[,\s]+([0-9.]+)(?:\s*[,/]\s*([0-9.%]+))?/
    );
    if (!match) return null;
    let alpha = 1;
    if (match[4] !== undefined) {
      alpha = match[4].endsWith("%")
        ? Number(match[4].slice(0, -1)) / 100
        : Number(match[4]);
    }
    if (!Number.isFinite(alpha) || alpha <= 0) return null;
    return { rgb: match.slice(1, 4).map(Number), alpha };
  };
  const blend = (top, bottom) =>
    top.rgb.map((channel, index) =>
      channel * top.alpha + bottom[index] * (1 - top.alpha)
    );
  const gradientStops = (image) => {
    const stops = [];
    const pattern = /#([0-9a-fA-F]{3,8})\b|rgba?\([^)]*\)/g;
    let match;
    while ((match = pattern.exec(String(image))) !== null) {
      const parsed = parse(match[0]);
      if (parsed && parsed.alpha > 0) stops.push(parsed);
    }
    return stops;
  };
  const declaredFallback = (node, style) => {
    const declared = [
      node.getAttribute ? node.getAttribute("data-bmv-contrast-background") : "",
      style.getPropertyValue("--bmv-contrast-background"),
      style.getPropertyValue("--bmv-overlay-background"),
    ];
    for (const value of declared) {
      const parsed = parse(value);
      if (parsed && parsed.alpha > 0) return parsed;
    }
    return null;
  };
  // Effective background resolution order:
  // 1. element's first non-transparent computed backgroundColor
  // 2. nearest ancestor's first non-transparent computed backgroundColor
  // 3. explicit solid fallback / overlay token (attribute or CSS variable)
  // 4. measurable gradient color stops
  // Background images without a solid fallback occlude ancestors and remain
  // unresolved. Transparent is never treated as white.
  const resolveBackgrounds = (node) => {
    if (!node || node.nodeType !== 1) return null;
    const style = getComputedStyle(node);
    const image = style.backgroundImage;
    const hasImage = Boolean(image && image !== "none");
    const own = parse(style.backgroundColor);
    const declared = declaredFallback(node, style);
    if (hasImage) {
      if (own && own.alpha >= 1) return [own.rgb];
      if (declared && declared.alpha >= 1) return [declared.rgb];
      const stops = gradientStops(image).filter((stop) => stop.alpha >= 1);
      if (stops.length) return stops.map((stop) => stop.rgb);
      // url(...) or translucent gradient with no solid fallback: occludes.
      return null;
    }
    if (own && own.alpha >= 1) return [own.rgb];
    if (declared && declared.alpha >= 1) return [declared.rgb];
    const behind = resolveBackgrounds(node.parentElement);
    if (!behind) return null;
    if (own && own.alpha > 0) {
      return behind.map((layer) => blend(own, layer));
    }
    if (declared && declared.alpha > 0) {
      return behind.map((layer) => blend(declared, layer));
    }
    return behind;
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
    const foreground = parse(style.color);
    if (!foreground) continue;
    const backgrounds = resolveBackgrounds(node);
    if (!backgrounds || !backgrounds.length) {
      add(
        "contrast-background-unresolved",
        "serious",
        node,
        "Effective background color is unresolved, so contrast is unverifiable."
      );
      continue;
    }
    let worst = Infinity;
    for (const background of backgrounds) {
      const fg = foreground.alpha >= 1
        ? foreground.rgb
        : blend(foreground, background);
      const ratio = (Math.max(luminance(fg), luminance(background)) + .05)
        / (Math.min(luminance(fg), luminance(background)) + .05);
      if (ratio < worst) worst = ratio;
    }
    if (worst < 3) add("obvious-computed-contrast", "serious", node, `Computed contrast ratio ${worst.toFixed(2)} is below 3:1.`);
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
