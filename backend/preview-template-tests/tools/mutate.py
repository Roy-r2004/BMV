"""Mutation-test the vitest suite against preview-template source.

    python3 tools/mutate.py

The repo's standing rule is *mutation-test every guard*: a guard whose success
looks like its failure is this codebase's recurring defect, and a green suite is
not evidence until each test has been shown to go red when the behaviour it
claims to pin is removed.

For each mutation below: apply an exact-string edit to the template source, run
vitest, record which test names failed, then restore from an in-memory backup —
never from `git checkout`, which has discarded uncommitted work here before.
A mutation that leaves the suite green names a test that pins nothing.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent.parent
TEMPLATE = TESTS.parent / "preview-template"
COMPOSER = TEMPLATE / "src/ui/compose/SkeletonComposer.tsx"
PANEL = TEMPLATE / "src/ui/public/AiFeaturePanel.tsx"
APP_NAV = TEMPLATE / "src/lib/app-nav.ts"
SCROLL = TEMPLATE / "src/components/ScrollToTop.tsx"

#: (label, file, exact source to replace, replacement)
MUTATIONS: list[tuple[str, Path, str, str]] = [
    (
        "throw removed from assertRequiredSections",
        COMPOSER,
        """  if (missingRequired.length > 0) {
    throw new Error(`Skeleton "${skeletonId}" missing required sections: ${missingRequired.join(', ')}`);
  }""",
        "",
    ),
    (
        "shell no longer exempt from required check",
        COMPOSER,
        "    if (section === 'shell') return false;\n",
        "",
    ),
    (
        "null slot treated as present",
        COMPOSER,
        "    return slots[section] == null;",
        "    return !(section in slots);",
    ),
    (
        "explicit order no longer owns the page face (leftovers appended)",
        COMPOSER,
        """  if (order && order.length > 0) {
    const requiredMissing = skeleton.requiredSections.filter(
      (section) =>
        section !== 'shell' &&
        slots[section] != null &&
        !sequence.includes(section),
    );
    return [...sequence, ...requiredMissing];
  }""",
        "",
    ),
    (
        "required-but-unordered sections no longer restored",
        COMPOSER,
        "    return [...sequence, ...requiredMissing];",
        "    return sequence;",
    ),
    (
        "unrecognised slots no longer appended",
        COMPOSER,
        """  for (const section of Object.keys(slots)) {
    if (section !== 'shell' && slots[section] != null && !sequence.includes(section)) {
      sequence.push(section);
    }
  }""",
        "",
    ),
    (
        "public-utility frame removed",
        COMPOSER,
        "  if (skeletonId === 'public-utility') {",
        "  if (false) {",
    ),
    (
        "ops rail split removed",
        COMPOSER,
        "  if (railSkeletons.includes(skeletonId) && slots.activity != null) {",
        "  if (false) {",
    ),
    (
        "non-rail fallback drops the recipe order",
        COMPOSER,
        "    main: <SkeletonComposer skeletonId={skeletonId} slots={slots} order={order} />,",
        "    main: <SkeletonComposer skeletonId={skeletonId} slots={slots} />,",
    ),
    # --- AiFeaturePanel's hub link (was a hardcoded /ai-features) -----------
    (
        "hub link hardcoded again (the original defect)",
        PANEL,
        "          {hubHref ? (\n            <AppLink\n              href={hubHref}",
        "          {true ? (\n            <AppLink\n              href=\"/ai-features\"",
    ),
    (
        "link rendered unconditionally, whatever the app declares",
        PANEL,
        "          {hubHref ? (",
        "          {true ? (",
    ),
    (
        "caller can no longer suppress the link with null",
        PANEL,
        "  const hubHref = indexHref === null ? undefined : indexHref || aiHubHref();",
        "  const hubHref = indexHref || aiHubHref();",
    ),
    (
        "caller override ignored in favour of the app's nav",
        PANEL,
        "  const hubHref = indexHref === null ? undefined : indexHref || aiHubHref();",
        "  const hubHref = indexHref === null ? undefined : aiHubHref();",
    ),
    # --- aiHubHref -----------------------------------------------------------
    (
        "aiHubHref always claims a hub exists",
        APP_NAV,
        "      if (/^\\/ai-features(\\/|$)/i.test(href)) return href;",
        "      return '/ai-features';",
    ),
    (
        "aiHubHref matches any /ai- route, not just the hub",
        APP_NAV,
        "      if (/^\\/ai-features(\\/|$)/i.test(href)) return href;",
        "      if (/^\\/ai-/i.test(href)) return href;",
    ),
    (
        "aiHubHref returns a literal instead of the declared path",
        APP_NAV,
        "      if (/^\\/ai-features(\\/|$)/i.test(href)) return href;",
        "      if (/^\\/ai-features(\\/|$)/i.test(href)) return '/ai-features';",
    ),
    (
        "malformed navigation is no longer tolerated",
        APP_NAV,
        "      const href = String(item?.href || item?.path || '').trim();",
        "      const href = String(item.href || item.path).trim();",
    ),
    # --- ScrollToTop: scroll reset and anchor landing ------------------------
    # jsdom cannot measure a pixel, so none of these mutate a rendered position.
    # They mutate *which element is chosen and how the offset is computed*, which
    # is where request 67's deep-link defect actually lived.
    (
        "route change no longer resets scroll",
        SCROLL,
        "    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });\n    return undefined;",
        "    return undefined;",
    ),
    (
        "scroll reset animates instead of jumping",
        SCROLL,
        "    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });\n    return undefined;",
        "    window.scrollTo({ top: 0, left: 0, behavior: 'smooth' });\n    return undefined;",
    ),
    (
        "the effect stops re-running on navigation",
        SCROLL,
        "  }, [pathname, hash]);",
        "  }, []);",
    ),
    (
        "a hash no longer re-runs the effect (only the path does)",
        SCROLL,
        "  }, [pathname, hash]);",
        "  }, [pathname]);",
    ),
    (
        "a hashed route lands at the top like any other",
        SCROLL,
        "      if (scrollToHash()) return;",
        "      window.scrollTo({ top: 0, left: 0, behavior: 'instant' });\n      return;",
    ),
    (
        "header measured from the CSS variable fallback, not the DOM (request 67)",
        SCROLL,
        "        const offset = (header ? header.getBoundingClientRect().height : 112) + 24;",
        "        const offset = 112 + 24;",
    ),
    (
        "the 24px of air above the anchor is dropped",
        SCROLL,
        "        const offset = (header ? header.getBoundingClientRect().height : 112) + 24;",
        "        const offset = header ? header.getBoundingClientRect().height : 112;",
    ),
    (
        "no header fallback at all",
        SCROLL,
        "        const offset = (header ? header.getBoundingClientRect().height : 112) + 24;",
        "        const offset = (header ? header.getBoundingClientRect().height : 0) + 24;",
    ),
    (
        "current scroll position ignored (viewport-relative treated as absolute)",
        SCROLL,
        "        const top = el.getBoundingClientRect().top + window.scrollY - offset;",
        "        const top = el.getBoundingClientRect().top - offset;",
    ),
    (
        "an anchor near the top scrolls to a negative position",
        SCROLL,
        "        window.scrollTo({ top: Math.max(0, top), left: 0, behavior: 'instant' });",
        "        window.scrollTo({ top, left: 0, behavior: 'instant' });",
    ),
    (
        "hash aliases dropped (#contact stops finding the inquire panel)",
        SCROLL,
        "      const id = HASH_ALIASES[raw] || raw;",
        "      const id = raw;",
    ),
    (
        "every hash is forced through the alias map",
        SCROLL,
        "      const id = HASH_ALIASES[raw] || raw;",
        "      const id = HASH_ALIASES[raw] || 'inquire';",
    ),
    (
        "no retry for a target that has not mounted yet",
        SCROLL,
        "      const t = window.setTimeout(() => {",
        "      return undefined;\n      const t = window.setTimeout(() => {",
    ),
    (
        "the retry timer is never cleared (a stale landing after navigating away)",
        SCROLL,
        "      return () => window.clearTimeout(t);",
        "      return undefined;",
    ),
    (
        "a hash that never resolves leaves the page mid-document",
        SCROLL,
        "        if (!scrollToHash()) window.scrollTo({ top: 0, left: 0, behavior: 'instant' });",
        "        scrollToHash();",
    ),
    # --- nav labels: shorten only while the shortened form stays unique -------
    # The template half of request 95's menu defect. Session 10 wrote this fix,
    # measured that it changes nothing without the generator half, and reverted
    # it; it is testable here because the fixture supplies both entries directly.
    (
        "the `My ` strip is unconditional again (a member page takes the public name)",
        APP_NAV,
        "    if ((shortCount.get(labelKey(s)) ?? 0) > 1) return f;\n"
        "    if (full.some((other, j) => j !== index && labelKey(other) === labelKey(s))) return f;\n"
        "    return s;",
        "    return s;",
    ),
    (
        "collisions against a sibling's FULL label stop counting",
        APP_NAV,
        "    if (full.some((other, j) => j !== index && labelKey(other) === labelKey(s))) return f;",
        "",
    ),
    (
        "collisions between two shortened labels stop counting",
        APP_NAV,
        "    if ((shortCount.get(labelKey(s)) ?? 0) > 1) return f;",
        "",
    ),
    (
        "labels are decided one entry at a time instead of across the section",
        APP_NAV,
        "  const labels = shortLabels(kept);",
        "  const labels = kept.map((item) => shortLabels([item])[0]);",
    ),
    (
        "the label key stops normalising, so 'My Orders' never matches 'my orders'",
        APP_NAV,
        "const labelKey = (text: string) => text.toLowerCase().replace(/[^a-z0-9]+/g, '');",
        "const labelKey = (text: string) => text;",
    ),
]


def run_suite(report: Path) -> tuple[int, list[str]]:
    """Run vitest; return (exit code, names of failed tests)."""
    proc = subprocess.run(
        ["npm", "test", "--", "--reporter=json", f"--outputFile={report}"],
        cwd=TESTS,
        capture_output=True,
        text=True,
        timeout=600,
    )
    try:
        data = json.loads(report.read_text())
    except Exception:
        return proc.returncode, ["<no json report>"]
    failed = [
        test["fullName"]
        for result in data.get("testResults", [])
        for test in result.get("assertionResults", [])
        if test.get("status") == "failed"
    ]
    return proc.returncode, failed


def main() -> int:
    originals = {path: path.read_text() for path in {m[1] for m in MUTATIONS}}
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "vitest.json"

        code, failed = run_suite(report)
        print(f"baseline: exit={code} failed={failed}")
        if code != 0:
            print("BASELINE IS RED — fix that before mutating anything")
            return 1

        survivors: list[str] = []
        try:
            for label, src, old, new in MUTATIONS:
                original = originals[src]
                found = original.count(old)
                if found != 1:
                    # The source moved out from under the mutation. Silence here
                    # would report a passing sweep that tested nothing.
                    print(
                        f"!! {label}: anchor matched {found} times in "
                        f"{src.name} — NOT APPLIED"
                    )
                    survivors.append(f"{label} (anchor drift)")
                    continue
                src.write_text(original.replace(old, new, 1))
                code, failed = run_suite(report)
                caught = code != 0
                print(f"\n[{'RED' if caught else 'STILL GREEN <-- pins nothing'}] {label}")
                for name in failed:
                    print(f"    caught by: {name}")
                if not caught:
                    survivors.append(label)
                src.write_text(original)
        finally:
            for path, source in originals.items():
                path.write_text(source)
                if path.read_text() != source:
                    print(f"RESTORE FAILED for {path} — check git diff now")
                    return 2
            print("\nsources restored and verified byte-identical")

    print(f"\nsurvivors (mutations no test caught): {survivors or 'none'}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
