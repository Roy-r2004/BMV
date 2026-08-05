import { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import { navigation } from '@/data/mock';

export type AppNavLink = {
  id: string;
  label: string;
  href: string;
  active?: boolean;
};

type RawNav = {
  id?: string;
  label?: string;
  name?: string;
  path?: string;
  href?: string;
};

function tidy(label: string, href: string): string {
  const text = String(label ?? '')
    .replace(/\s+/g, ' ')
    .trim();
  if (text && text.length <= 22) return text;
  const seg = href.split('/').filter(Boolean).pop() || 'Home';
  return seg
    .replace(/[-_]/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

const labelKey = (text: string) => text.toLowerCase().replace(/[^a-z0-9]+/g, '');

/**
 * Shortened labels for one nav section — shortened only while they stay unique.
 *
 * Stripping a leading `My ` turns "My Reservations" into "Reservations", which
 * is the label a sibling `/reservations` entry already carries, so the header
 * named a member page with the public page's name. `/my-orders` and `/orders`,
 * `/my-bookings` and `/bookings` are the same shape — which is why the rule is
 * about the **list** and never about a route name.
 *
 * It has to see the whole section at once: deciding per item in order would
 * shorten whichever entry happened to come first and collide anyway.
 */
function shortLabels(raw: { label: string; href: string }[]): string[] {
  const full = raw.map((item) => tidy(item.label, item.href));
  const short = raw.map((item) =>
    tidy(String(item.label ?? '').replace(/^(Welcome(\s+to)?|Manage|My)\s+/i, ''), item.href)
  );
  const shortCount = new Map<string, number>();
  for (const text of short) shortCount.set(labelKey(text), (shortCount.get(labelKey(text)) ?? 0) + 1);

  return raw.map((_, index) => {
    const s = short[index];
    const f = full[index];
    if (!s || labelKey(s) === labelKey(f)) return f;
    if ((shortCount.get(labelKey(s)) ?? 0) > 1) return f;
    if (full.some((other, j) => j !== index && labelKey(other) === labelKey(s))) return f;
    return s;
  });
}

/**
 * Terminal pages: where a form sends you, never where a link takes you.
 * Request 66 listed `/inquiry-confirm` in the public nav, so it became the
 * target of every "Contact" control on the site — a page reading "Inquiry Sent"
 * with no form on it. The old `confirmation\b` test did not match it.
 */
const TERMINAL_LEAF_RE =
  /^(inquiry|enquiry|order|booking|payment|checkout|contact)?[-_]?(confirm|confirmed|confirmation|thank[-_]?you|thanks|success|receipt|complete|completed|sent)$/i;

export function isTerminalHref(href: string): boolean {
  const leaf = String(href || '').split('?')[0].replace(/\/+$/, '').split('/').pop() || '';
  return TERMINAL_LEAF_RE.test(leaf);
}

function isNavWorthy(href: string): boolean {
  if (!href || !href.startsWith('/')) return false;
  if (href.includes(':')) return false;
  // Skip transactional flow steps from persistent chrome
  if (/^\/(book|payment|confirmation)\b/i.test(href)) return false;
  if (isTerminalHref(href)) return false;
  return true;
}

/**
 * The AI hub's route, but only when this app actually serves one.
 *
 * `/ai-features` is a conditional route: the pipeline builds the hub for some
 * briefs and not others (`capabilities/journey._CONDITIONAL_ROUTES`), and
 * `assemble._pin_ai_features_nav` adds the nav entry if and only if a hub route
 * exists. So the shipped `navigation` is the app's own answer to "is there a
 * hub", and the answer is available at runtime.
 *
 * `AiFeaturePanel` used to hardcode `href="/ai-features"`, which was dead in 5
 * of the 41 archived workspaces that render the panel (requests 32, 36, 45, 47,
 * 77) — the catch-all route silently redirected it to `/` rather than 404ing,
 * which is why it survived so long. Same rule as `MarketingHero`'s CTA default:
 * a template cannot assume a route it did not create.
 *
 * Returns the *declared* path rather than a literal, so the panel links only
 * where the app's own navigation already points.
 */
export function aiHubHref(): string | undefined {
  const nav = navigation as Record<string, RawNav[]> | undefined;
  if (!nav) return undefined;
  for (const section of Object.values(nav)) {
    for (const item of section || []) {
      const href = String(item?.href || item?.path || '').trim();
      if (/^\/ai-features(\/|$)/i.test(href)) return href;
    }
  }
  return undefined;
}

/** Storefront chrome only — never admin, owner login, or AI hub. */
function isPublicMarketingHref(href: string): boolean {
  if (!isNavWorthy(href)) return false;
  if (/^\/(admin|owner|ops|staff|desk|member|account)(\/|$)/i.test(href)) return false;
  if (/^\/ai-features(\/|$)/i.test(href) || /^\/ai-/i.test(href)) return false;
  return true;
}

function normalizeList(raw: RawNav[] | undefined, pathname: string): AppNavLink[] {
  const seen = new Set<string>();
  const kept: { id: string; href: string; label: string }[] = [];
  for (const [index, item] of (raw || []).entries()) {
    const href = String(item.href || item.path || '').trim();
    if (!isNavWorthy(href) || seen.has(href)) continue;
    seen.add(href);
    kept.push({
      id: String(item.id || href || index),
      href,
      label: String(item.label || item.name || href),
    });
  }
  // Labels are decided across the whole section, never one entry at a time.
  const labels = shortLabels(kept);
  return kept.map((item, index) => ({
    id: item.id,
    label: labels[index],
    href: item.href,
    active:
      pathname === item.href || (item.href !== '/' && pathname.startsWith(`${item.href}/`)),
  }));
}

function sectionLinks(section: 'admin' | 'public' | 'member'): RawNav[] {
  const nav = navigation as Record<string, RawNav[]>;
  if (section === 'admin') return nav.admin || [];
  if (section === 'member') return nav.member || nav.public || [];
  return nav.public || [];
}

function withActive(links: AppNavLink[], pathname: string): AppNavLink[] {
  return links.map((item) => ({
    ...item,
    active: pathname === item.href || (item.href !== '/' && pathname.startsWith(`${item.href}/`)),
  }));
}

/** Stable admin sidebar links — same list on every ops page. */
export function useAdminNavItems(): AppNavLink[] {
  const { pathname } = useLocation();
  return useMemo(
    () => withActive(normalizeList(sectionLinks('admin'), pathname), pathname),
    [pathname]
  );
}

/** Stable public marketing navbar links — derived from synced mock navigation. */
export function usePublicNavItems(): AppNavLink[] {
  const { pathname } = useLocation();
  return useMemo(() => {
    const links = normalizeList(sectionLinks('public'), pathname).filter((item) =>
      isPublicMarketingHref(item.href)
    );
    return withActive(links.slice(0, 5), pathname);
  }, [pathname]);
}

/** Stable member hub navbar links — member routes plus a couple public destinations. */
export function useMemberNavItems(): AppNavLink[] {
  const { pathname } = useLocation();
  return useMemo(() => {
    const memberLinks = normalizeList(sectionLinks('member'), pathname).filter((item) =>
      item.href.startsWith('/member')
    );
    const publicExtras = normalizeList(sectionLinks('public'), pathname)
      .filter((item) => isPublicMarketingHref(item.href) && item.href !== '/')
      .slice(0, 2);
    const seen = new Set<string>();
    const merged: AppNavLink[] = [];
    for (const item of [...publicExtras, ...memberLinks]) {
      if (seen.has(item.href)) continue;
      seen.add(item.href);
      merged.push(item);
    }
    return withActive(merged.slice(0, 6), pathname);
  }, [pathname]);
}

function firstHref(raw: RawNav[] | undefined, fallback: string): string {
  for (const item of raw || []) {
    const href = String(item.href || item.path || '').trim();
    if (isPublicMarketingHref(href)) return href;
  }
  return fallback;
}

export function publicCta() {
  const publicLinks = sectionLinks('public').filter((item) =>
    isPublicMarketingHref(String(item.href || item.path || ''))
  );
  // Book / class CTAs only — never owner login ("Get started" → /owner/login).
  const bookish =
    publicLinks.find((item) =>
      /book|class|schedule|workshop|join|start/i.test(
        `${item.label || ''} ${item.path || ''} ${item.href || ''}`
      )
    ) || null;
  if (bookish) {
    const href = String(bookish.href || bookish.path || '/');
    const bookLabel = /book|class|schedule|workshop/i.test(
      `${bookish.label || ''} ${bookish.path || ''} ${bookish.href || ''}`
    );
    return { label: bookLabel ? 'Book' : 'Get started', href };
  }
  // Storefronts: prefer collection/gallery/about over inventing a Book CTA.
  const browse =
    publicLinks.find((item) =>
      /gallery|collection|shop|menu|work|about|catalog/i.test(
        `${item.label || ''} ${item.path || ''} ${item.href || ''}`
      )
    ) || null;
  const href = String(browse?.href || browse?.path || firstHref(publicLinks, '/'));
  const label = /gallery|collection|work|catalog/i.test(
    `${browse?.label || ''} ${browse?.path || ''} ${browse?.href || ''}`
  )
    ? 'View collection'
    : /about/i.test(`${browse?.label || ''} ${browse?.path || ''} ${browse?.href || ''}`)
      ? 'About'
      : 'Explore';
  return { label, href };
}

export function memberCta() {
  const publicLinks = sectionLinks('public').filter((item) =>
    isPublicMarketingHref(String(item.href || item.path || ''))
  );
  const bookish =
    publicLinks.find((item) =>
      /book|class|schedule/i.test(`${item.label || ''} ${item.path || ''} ${item.href || ''}`)
    ) || null;
  const href = String(bookish?.href || bookish?.path || firstHref(publicLinks, '/'));
  return { label: 'Book', href };
}
