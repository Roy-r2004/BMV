import { render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup } from '@testing-library/react';

import {
  SkeletonComposer,
  composeSkeletonLayout,
  type SkeletonSlots,
} from '@/ui/compose/SkeletonComposer';

afterEach(cleanup);

/** A slot that identifies itself in the DOM, so order is assertable. */
const slot = (id: string) => <div data-section={id} />;

const slots = (...ids: string[]): SkeletonSlots =>
  Object.fromEntries(ids.map((id) => [id, slot(id)]));

/** Section ids in rendered document order. */
const renderedOrder = (container: HTMLElement) =>
  Array.from(container.querySelectorAll('[data-section]')).map((node) =>
    node.getAttribute('data-section'),
  );

describe('required sections', () => {
  it('throws naming every missing required section', () => {
    // public-home requires shell/hero/cta/footer; `cta` is absent.
    expect(() =>
      SkeletonComposer({ skeletonId: 'public-home', slots: slots('hero', 'footer') }),
    ).toThrow(/missing required sections: cta/);
  });

  it('treats an explicitly null slot as missing, not as present-and-empty', () => {
    expect(() =>
      SkeletonComposer({
        skeletonId: 'public-home',
        slots: { ...slots('hero', 'footer'), cta: null },
      }),
    ).toThrow(/missing required sections: cta/);
  });

  it('does not require a `shell` slot — the shell is the layout, not a section', () => {
    expect(() =>
      SkeletonComposer({ skeletonId: 'public-home', slots: slots('hero', 'cta', 'footer') }),
    ).not.toThrow();
  });
});

describe('section order', () => {
  it('an explicit order owns the page face and drops leftover optional slots', () => {
    // The variety contract: a recipe order must not have unrequested marketing
    // sections appended, or every business collapses into the same long stack.
    const { container } = render(
      <SkeletonComposer
        skeletonId="public-home"
        slots={slots('hero', 'cta', 'footer', 'testimonials')}
        order={['hero', 'cta', 'footer']}
      />,
    );

    expect(renderedOrder(container)).toEqual(['hero', 'cta', 'footer']);
  });

  it('an explicit order still cannot drop a required section that was supplied', () => {
    const { container } = render(
      <SkeletonComposer
        skeletonId="public-home"
        slots={slots('hero', 'cta', 'footer')}
        order={['hero', 'cta']}
      />,
    );

    expect(renderedOrder(container)).toContain('footer');
  });

  it('without an explicit order, unrecognised slots are appended after the recommended ones', () => {
    // `faq` is in neither requiredSections nor recommendedOrder for public-home.
    const { container } = render(
      <SkeletonComposer
        skeletonId="public-home"
        slots={slots('hero', 'faq', 'cta', 'footer')}
      />,
    );

    expect(renderedOrder(container)).toEqual(['hero', 'cta', 'footer', 'faq']);
  });
});

describe('public-utility framing', () => {
  it('frames the body in a content column and leaves the footer full-bleed', () => {
    const { container } = render(
      <SkeletonComposer
        skeletonId="public-utility"
        slots={slots('header', 'workspace', 'footer')}
      />,
    );

    const frame = container.querySelector('[data-utility-frame]');
    expect(frame).not.toBeNull();
    expect(renderedOrder(frame as HTMLElement)).toEqual(['header', 'workspace']);
    // Footer renders, but outside the frame.
    expect(renderedOrder(container)).toEqual(['header', 'workspace', 'footer']);
  });
});

describe('composeSkeletonLayout', () => {
  const opsSlots = slots('header', 'kpis', 'chart', 'filters', 'table', 'activity');

  it('moves `activity` out of the main column and into the rail for ops-dashboard', () => {
    const layout = composeSkeletonLayout('ops-dashboard', opsSlots);

    const main = render(<>{layout.main}</>);
    expect(renderedOrder(main.container)).not.toContain('activity');
    cleanup();

    expect(layout.rail).toBeDefined();
    const rail = render(<>{layout.rail}</>);
    expect(renderedOrder(rail.container)).toEqual(['activity']);
  });

  it('returns a flat main tree with no rail for a public skeleton, order intact', () => {
    const layout = composeSkeletonLayout(
      'public-home',
      slots('hero', 'cta', 'footer'),
      ['footer', 'hero', 'cta'],
    );

    expect(layout.rail).toBeUndefined();
    // The order argument must survive the delegation to SkeletonComposer.
    const { container } = render(<>{layout.main}</>);
    expect(renderedOrder(container)).toEqual(['footer', 'hero', 'cta']);
  });
});
