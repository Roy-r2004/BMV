import { cleanup, render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { AiFeatureItem } from '@/ui/public/AiFeatureStage';

/**
 * `AiFeaturePanel.tsx:44` hardcoded `href="/ai-features"`.
 *
 * `/ai-features` is a *conditional* route — the pipeline builds the AI hub for
 * some briefs and not others, which is why the dead-link gate lists it in
 * `_CONDITIONAL_ROUTES` and reports a link to it without blocking. Over the 58
 * archived workspaces, 41 render this panel and **5 of them declare no hub
 * route at all** (requests 32, 36, 45, 47, 77). The template's catch-all route
 * redirects unknown paths to `/` instead of 404ing, so the dead link looked
 * like a working one.
 *
 * There is no safe deletion: `AppLink` requires `href`, and the dead-link guard
 * skips template-owned files (`restore_template_owned_files` reverts the edit),
 * so the fix has to be in the template. `MarketingHero`'s `DEFAULT_PRIMARY_CTA`
 * was the same defect with the same rule — a template cannot assume a route it
 * did not create.
 *
 * The panel now asks the app's own shipped `navigation`, which
 * `assemble._pin_ai_features_nav` populates if and only if a hub route exists.
 * Checked against the archive: in all 5 dead cases `navigation` correctly says
 * there is no hub.
 */

/** Mutable so each test can ship a different `navigation`, as a generated app does. */
const mockData: { navigation: unknown } = { navigation: {} };

vi.mock('@/data/mock', () => ({
  get navigation() {
    return mockData.navigation;
  },
}));

const feature: AiFeatureItem = {
  id: 'auto-quote',
  name: 'Automatic quoting',
  description: 'Drafts a quote from the enquiry.',
};

const renderPanel = async (props: Record<string, unknown> = {}) => {
  const { AiFeaturePanel } = await import('@/ui/public/AiFeaturePanel');
  return render(
    <MemoryRouter>
      <AiFeaturePanel feature={feature} {...props} />
    </MemoryRouter>,
  );
};

/**
 * The affordance, found by its label rather than its href.
 *
 * Selecting on `a[href*="ai-features"]` was not enough: rendering the link
 * unconditionally with `href={undefined}` produces `<a>All AI features →</a>`
 * with no href attribute at all, which no href selector matches and which is
 * *worse* than a dead link — a visible control that does nothing. That mutation
 * survived the first sweep.
 */
const hubLink = (container: HTMLElement) =>
  Array.from(container.querySelectorAll('a')).find((anchor) =>
    (anchor.textContent || '').includes('All AI features'),
  ) ?? null;

/** No anchor in the panel may be missing an href. */
const hrefless = (container: HTMLElement) =>
  Array.from(container.querySelectorAll('a')).filter((anchor) => !anchor.getAttribute('href'));

beforeEach(() => {
  mockData.navigation = {};
  vi.resetModules();
});

afterEach(cleanup);

describe('the hub link follows the app, not a literal', () => {
  it('renders no hub link when the app declares no hub route', async () => {
    // Requests 32, 36, 45, 47 and 77. Before the fix this shipped a link to a
    // route that did not exist, and the catch-all quietly redirected it to `/`.
    mockData.navigation = {
      public: [{ path: '/', label: 'Home' }],
      admin: [{ path: '/admin', label: 'Overview' }],
    };
    const { container } = await renderPanel();

    expect(hubLink(container)).toBeNull();
    expect(container.innerHTML).not.toContain('/ai-features');
    expect(container.textContent).not.toContain('All AI features');
    // Not replaced by an hrefless anchor, which renders as a control that
    // looks clickable and is not.
    expect(hrefless(container)).toHaveLength(0);
    // The panel itself still renders — this is a suppressed link, not a
    // suppressed component.
    expect(container.querySelector('[data-ai-feature="auto-quote"]')).not.toBeNull();
    expect(container.textContent).toContain('Automatic quoting');
  });

  it('renders the hub link when the app declares the hub route', async () => {
    mockData.navigation = {
      public: [{ path: '/', label: 'Home' }],
      admin: [
        { path: '/admin', label: 'Overview' },
        // Exactly the entry `_pin_ai_features_nav` inserts.
        { id: 'ai-features', path: '/ai-features', href: '/ai-features', label: 'AI features' },
      ],
    };
    const { container } = await renderPanel();

    const link = hubLink(container);
    expect(link).not.toBeNull();
    expect(link?.getAttribute('href')).toBe('/ai-features');
    expect(link?.textContent).toContain('All AI features');
  });

  it('links to the declared path, so it cannot invent a route of its own', async () => {
    // The point of reading nav rather than hardcoding: if the app mounts the hub
    // somewhere else, the link follows it. A literal cannot.
    mockData.navigation = {
      admin: [{ path: '/ai-features/all', label: 'AI features' }],
    };
    const { container } = await renderPanel();

    expect(hubLink(container)?.getAttribute('href')).toBe('/ai-features/all');
  });

  it('lets a caller suppress the link with null, for the hub page itself', async () => {
    mockData.navigation = { admin: [{ path: '/ai-features', label: 'AI features' }] };
    const { container } = await renderPanel({ indexHref: null });

    expect(hubLink(container)).toBeNull();
    expect(hrefless(container)).toHaveLength(0);
  });

  it('lets a caller override the target', async () => {
    mockData.navigation = { admin: [{ path: '/ai-features', label: 'AI features' }] };
    const { container } = await renderPanel({ indexHref: '/owner/ai' });

    expect(container.querySelector('a[href="/owner/ai"]')).not.toBeNull();
  });

  it('survives a degraded app whose navigation is missing or malformed', async () => {
    // Degraded previews are the designed outcome past the deadline, so mock.ts
    // is not guaranteed well-formed. A thrown render is worse than no link.
    for (const nav of [undefined, null, {}, { admin: null }, { admin: [null] }, []]) {
      cleanup();
      vi.resetModules();
      mockData.navigation = nav;
      const { container } = await renderPanel();
      expect(hubLink(container)).toBeNull();
      expect(hrefless(container)).toHaveLength(0);
      expect(container.querySelector('[data-ai-feature="auto-quote"]')).not.toBeNull();
    }
  });
});

describe('aiHubHref', () => {
  it('ignores nav entries that merely start with /ai-', async () => {
    // `isPublicMarketingHref` filters `/^\/ai-/` as a class; the hub check must
    // be narrower or an `/ai-assistant` page would masquerade as the hub.
    mockData.navigation = { admin: [{ path: '/ai-assistant', label: 'Assistant' }] };
    const { aiHubHref } = await import('@/lib/app-nav');

    expect(aiHubHref()).toBeUndefined();
  });

  it('finds the hub in whichever section declares it', async () => {
    mockData.navigation = { member: [{ href: '/ai-features', label: 'AI features' }] };
    const { aiHubHref } = await import('@/lib/app-nav');

    expect(aiHubHref()).toBe('/ai-features');
  });
});
