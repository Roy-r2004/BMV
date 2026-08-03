/**
 * `ScrollToTop` — the scroll-reset and anchor-landing half of the nav guarantees.
 *
 * **What this file can and cannot say, because it matters more than the tests.**
 * jsdom has no layout engine: every `getBoundingClientRect()` is zeros and
 * nothing has a height. So the roadmap's nav guarantees as *stated* — "a cold
 * load of `/<detail>/1#inquire` lands the target's `top` in [16, 48]", "hero
 * content clears the measured header on every public route" — cannot be asserted
 * here at all. Those are pixel measurements and they belong to
 * `tests/preview_app/test_nav_contract.py`, which drives a real browser.
 *
 * What is assertable here is the layer underneath them: **which element is
 * scrolled to, and the arithmetic that positions it.** Request 67's defect was
 * not a wrong pixel, it was reading `--public-header-h` before `PublicShell` had
 * written it, so a deep link landed 18px *under* a 114px header while the same
 * anchor clicked in-page landed correctly. That is a logic bug with a fixed
 * header height stubbed in, and it is exactly what these tests hold.
 *
 * **Which copy this tests.** `src/components/ScrollToTop.tsx`, the template's.
 * A generated app runs an inlined copy in `app/templates/codegen/app_tsx.j2`,
 * because `assemble.write_app_tsx` rewrites `App.tsx` from scratch and an import
 * would not survive the workspace copy. Behaviour proved here reaches the shipped
 * app only through `test_the_scroll_reset_ships_one_behaviour_from_two_files` in
 * pytest — which compares the two effect bodies *normalized*, not just their
 * alias maps, precisely because an alias-only version stayed green for two rounds
 * while the j2 moved to `behavior: 'instant'` and the template sat on
 * `scrollIntoView`. Those tests are load-bearing for these ones: if that
 * comparison ever weakens to the alias table again, everything below stops saying
 * anything about a generated app.
 */
import { fireEvent, render } from '@testing-library/react';
import { Link, MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ScrollToTop } from '@/components/ScrollToTop';

/** jsdom's `scrollTo` is a stub that warns; every test wants to read the call. */
let scrollTo: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  scrollTo = vi.fn();
  Object.defineProperty(window, 'scrollTo', { writable: true, value: scrollTo });
  Object.defineProperty(window, 'scrollY', { writable: true, value: 0 });
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = '';
});

/** jsdom gives every element a zero rect; give this one a position. */
function placeAt(el: Element, top: number): void {
  el.getBoundingClientRect = () => ({ top, height: 0 }) as DOMRect;
}

function mountAnchor(id: string, top: number): HTMLElement {
  const el = document.createElement('section');
  el.id = id;
  placeAt(el, top);
  document.body.appendChild(el);
  return el;
}

function mountHeader(height: number): HTMLElement {
  const header = document.createElement('header');
  header.setAttribute('data-public-header', '');
  header.getBoundingClientRect = () => ({ top: 0, height }) as DOMRect;
  document.body.appendChild(header);
  return header;
}

function renderAt(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <ScrollToTop />
    </MemoryRouter>,
  );
}

describe('scroll reset', () => {
  it('lands a plain route at the top', () => {
    renderAt('/gallery');

    expect(scrollTo).toHaveBeenCalledWith({ top: 0, left: 0, behavior: 'instant' });
  });

  it('is instant, never smooth', () => {
    // A landing that animates from 3000px while the incoming page is still
    // mounting reads as broken. In-page `<a href="#x">` keeps the smooth glide
    // because react-router never sees it.
    renderAt('/about');

    expect(scrollTo.mock.calls[0][0].behavior).toBe('instant');
  });

  it('runs again on a real in-app navigation', () => {
    // Not a rerender with different `initialEntries` — react-router reads those
    // once, on mount, so that version of this test passes with the effect's
    // dependency array emptied. The navigation has to be a navigation.
    const { getByText } = render(
      <MemoryRouter initialEntries={['/gallery']}>
        <ScrollToTop />
        <Link to="/about">go</Link>
      </MemoryRouter>,
    );
    scrollTo.mockClear();

    fireEvent.click(getByText('go'));

    expect(scrollTo).toHaveBeenCalledWith({ top: 0, left: 0, behavior: 'instant' });
  });

  it('runs again when only the hash changes', () => {
    mountAnchor('inquire', 500);
    const { getByText } = render(
      <MemoryRouter initialEntries={['/gallery']}>
        <ScrollToTop />
        <Link to="/gallery#inquire">go</Link>
      </MemoryRouter>,
    );
    scrollTo.mockClear();

    fireEvent.click(getByText('go'));

    expect(scrollTo).toHaveBeenCalledWith({ top: 500 - 136, left: 0, behavior: 'instant' });
  });
});

describe('anchor landing', () => {
  it('scrolls to the hashed section instead of the top', () => {
    mountAnchor('inquire', 500);

    renderAt('/painting/1#inquire');

    expect(scrollTo).toHaveBeenCalledTimes(1);
    expect(scrollTo.mock.calls[0][0].top).not.toBe(0);
  });

  it('clears the header it measured, plus 24px of air', () => {
    // The whole of request 67's defect, in the only form jsdom can express it.
    mountHeader(114);
    mountAnchor('inquire', 500);

    renderAt('/painting/1#inquire');

    expect(scrollTo).toHaveBeenCalledWith({
      top: 500 - (114 + 24),
      left: 0,
      behavior: 'instant',
    });
  });

  it('measures the rendered header rather than trusting a CSS variable', () => {
    // `--public-header-h` is written by PublicShell *after* this effect runs on a
    // cold load, so a run that read the variable would use the stylesheet
    // fallback and land 18px under a 114px header. Two headers, two offsets: if
    // the offset were a constant, both of these would be the same number.
    mountHeader(60);
    mountAnchor('inquire', 500);
    renderAt('/a#inquire');
    const shortHeader = scrollTo.mock.calls[0][0].top;

    document.body.innerHTML = '';
    scrollTo.mockClear();
    mountHeader(160);
    mountAnchor('inquire', 500);
    renderAt('/a#inquire');

    expect(shortHeader - scrollTo.mock.calls[0][0].top).toBe(100);
  });

  it('falls back to 112px of header when the page has none', () => {
    mountAnchor('inquire', 500);

    renderAt('/a#inquire');

    expect(scrollTo.mock.calls[0][0].top).toBe(500 - (112 + 24));
  });

  it('accounts for how far the page is already scrolled', () => {
    // `getBoundingClientRect().top` is viewport-relative; the destination is not.
    Object.defineProperty(window, 'scrollY', { writable: true, value: 800 });
    mountHeader(100);
    mountAnchor('inquire', 500);

    renderAt('/a#inquire');

    expect(scrollTo.mock.calls[0][0].top).toBe(500 + 800 - 124);
  });

  it('never scrolls above the top of the document', () => {
    mountHeader(114);
    mountAnchor('inquire', 20);

    renderAt('/a#inquire');

    expect(scrollTo.mock.calls[0][0].top).toBe(0);
  });

  it('resolves the contact aliases onto the inquire panel', () => {
    // `/contact#contact`, `#purchase`, `#enquiry` all mean the one form the
    // template actually renders. The alias map is the thing the two copies of
    // this component are pinned on.
    for (const alias of ['contact', 'contact-form', 'purchase', 'inquire-form', 'enquiry', 'enquiries']) {
      document.body.innerHTML = '';
      scrollTo.mockClear();
      mountAnchor('inquire', 400);

      renderAt(`/x#${alias}`);

      expect(scrollTo.mock.calls[0][0].top, alias).toBe(400 - 136);
    }
  });

  it('leaves an unaliased hash alone', () => {
    mountAnchor('rooms', 300);

    renderAt('/x#rooms');

    expect(scrollTo.mock.calls[0][0].top).toBe(300 - 136);
  });
});

describe('a hash whose target has not mounted yet', () => {
  it('retries, and lands the section once it appears', () => {
    renderAt('/painting/1#inquire');
    expect(scrollTo).not.toHaveBeenCalled();

    mountAnchor('inquire', 500);
    vi.advanceTimersByTime(50);

    expect(scrollTo).toHaveBeenCalledWith({
      top: 500 - 136,
      left: 0,
      behavior: 'instant',
    });
  });

  it('gives up to the top rather than leaving the page mid-document', () => {
    renderAt('/painting/1#nowhere');

    vi.advanceTimersByTime(50);

    expect(scrollTo).toHaveBeenCalledWith({ top: 0, left: 0, behavior: 'instant' });
  });

  it('does not fire a stale retry after the route changes', () => {
    const { unmount } = renderAt('/painting/1#inquire');

    unmount();
    mountAnchor('inquire', 500);
    vi.advanceTimersByTime(50);

    expect(scrollTo).not.toHaveBeenCalled();
  });
});
