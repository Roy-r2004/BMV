import { renderHook } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * `shortLabel` stripped a leading `My ` from every nav label on its own.
 *
 * Request 95 shipped a public nav whose "Reservations" entry pointed at
 * `/my-reservations`, while the declared public `/reservations` — served by
 * `ReservationsPage.tsx` — was absent from the menu entirely. Two halves, and
 * session 10 measured that the template half alone changes nothing on screen:
 * the collision only becomes visible once the generator stops *deleting* the
 * public route (`safety/mock_data._nav_labels_for_section`). They land together.
 *
 * The rule has to be about the **list**: drop a prefix only while the shortened
 * label stays unique among its siblings. `/my-orders` and `/orders`,
 * `/my-bookings` and `/bookings` are the same shape, so nothing here may test a
 * route name.
 *
 * Deciding entry-by-entry is not enough and that is what the ordering test
 * below exists to catch: whichever entry came first would take the short label
 * and the other would still collide.
 */

const mockData: { navigation: unknown } = { navigation: {} };

vi.mock('@/data/mock', () => ({
  get navigation() {
    return mockData.navigation;
  },
}));

const publicNav = async () => {
  const { usePublicNavItems } = await import('@/lib/app-nav');
  const { result } = renderHook(() => usePublicNavItems(), {
    wrapper: ({ children }) => <MemoryRouter>{children}</MemoryRouter>,
  });
  return result.current;
};

beforeEach(() => {
  mockData.navigation = {};
  vi.resetModules();
});

describe('a shortened nav label may not collide with a sibling', () => {
  it('keeps both entries and tells them apart', async () => {
    mockData.navigation = {
      public: [
        { id: 'home', href: '/', label: 'Home' },
        { id: 'my-reservations', href: '/my-reservations', label: 'My Reservations' },
        { id: 'reservations', href: '/reservations', label: 'Reservations' },
      ],
    };
    const links = await publicNav();
    expect(links.map((l) => l.href)).toEqual(['/', '/my-reservations', '/reservations']);
    expect(new Set(links.map((l) => l.label)).size).toBe(3);
  });

  it('does not depend on which of the two comes first', async () => {
    mockData.navigation = {
      public: [
        { id: 'reservations', href: '/reservations', label: 'Reservations' },
        { id: 'my-reservations', href: '/my-reservations', label: 'My Reservations' },
      ],
    };
    const links = await publicNav();
    expect(new Set(links.map((l) => l.label)).size).toBe(2);
    // The public page keeps the plain name; the member page is the one that has
    // a longer form to fall back on.
    expect(links.find((l) => l.href === '/reservations')?.label).toBe('Reservations');
    expect(links.find((l) => l.href === '/my-reservations')?.label).toBe('My Reservations');
  });

  it('still shortens when nothing collides', async () => {
    mockData.navigation = {
      public: [
        { id: 'home', href: '/', label: 'Home' },
        { id: 'my-profile', href: '/my-profile', label: 'My Profile' },
      ],
    };
    const links = await publicNav();
    expect(links.find((l) => l.href === '/my-profile')?.label).toBe('Profile');
  });

  /**
   * Two entries whose *shortened* forms collide but whose full labels do not.
   * The first sweep's fixtures could not reach this: both of their full labels
   * also collided, so the shortened-label guard alone explained every failure
   * and deleting it left the suite green.
   */
  it('refuses to shorten when two different prefixes reduce to one word', async () => {
    mockData.navigation = {
      public: [
        { id: 'mine', href: '/my-orders', label: 'My Orders' },
        { id: 'manage', href: '/orders', label: 'Manage Orders' },
      ],
    };
    const links = await publicNav();
    expect(links.map((l) => l.label)).toEqual(['My Orders', 'Manage Orders']);
  });

  /**
   * One entry's shortened form equal to another entry's *full* label. This is
   * the case the second guard exists for, and the shortened-label counter
   * cannot see it because the two shortened forms differ.
   */
  it('refuses to shorten onto a label a sibling already carries in full', async () => {
    mockData.navigation = {
      public: [
        { id: 'manage-mine', href: '/manage-my-orders', label: 'Manage My Orders' },
        { id: 'mine', href: '/my-orders', label: 'My Orders' },
      ],
    };
    const links = await publicNav();
    expect(new Set(links.map((l) => l.label)).size).toBe(2);
    expect(links.find((l) => l.href === '/my-orders')?.label).toBe('Orders');
    expect(links.find((l) => l.href === '/manage-my-orders')?.label).toBe('Manage My Orders');
  });

  it('compares labels case- and punctuation-insensitively', async () => {
    mockData.navigation = {
      public: [
        { id: 'mine', href: '/my-reservations', label: 'My Reservations' },
        { id: 'public', href: '/reservations', label: 'reservations' },
      ],
    };
    const links = await publicNav();
    expect(links.find((l) => l.href === '/my-reservations')?.label).toBe('My Reservations');
  });

  it('applies to every stripped prefix, not to one route name', async () => {
    // `Manage ` is stripped by the same rule as `My `, so an admin section can
    // collide the same way. Nothing in the fix may key on "reservations".
    mockData.navigation = {
      public: [
        { id: 'manage-bookings', href: '/manage-bookings', label: 'Manage Bookings' },
        { id: 'bookings', href: '/bookings', label: 'Bookings' },
      ],
    };
    const links = await publicNav();
    expect(links.map((l) => l.href)).toEqual(['/manage-bookings', '/bookings']);
    expect(new Set(links.map((l) => l.label)).size).toBe(2);
  });
});
