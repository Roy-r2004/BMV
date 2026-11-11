import { Children, isValidElement, type ReactNode } from 'react';

/** Blocks that carry a section's substance: on a wide screen they take the right half. */
const BLOCKS = ['film-rows', 'film-grid2', 'film-labels', 'film-svc', 'film-facts', 'film-card', 'film-form', 'film-tests',
  'film-ex-groups', 'film-quote', 'film-docs'];

function isBlock(child: ReactNode): boolean {
  if (!isValidElement<{ className?: string }>(child)) return false;
  const cls = child.props.className ?? '';
  return BLOCKS.some((b) => cls.split(/\s+/).includes(b));
}

/**
 * One section of a public page. `tone` paints it white or black; a white
 * section that follows a black one rises over it as a panel, and the bar
 * above the page takes the colour that reads on the section under it.
 * On a wide screen a section with a list, cards or a form splits in two:
 * its headline and text on the left, that block on the right, so the page
 * uses its width. `stack` keeps everything in one full-width column, for
 * cards that should run across the page. `title` names the section.
 */
export default function Shot({
  tone = 'light',
  title,
  first = false,
  wide = false,
  compact = false,
  stack = false,
  id,
  children,
}: {
  tone?: 'light' | 'dark';
  title: string;
  first?: boolean;
  wide?: boolean;
  /** As tall as its content: the opening of a page that is mostly reading. */
  compact?: boolean;
  /** One full-width column: headline, then the blocks across the page. */
  stack?: boolean;
  id?: string;
  children: ReactNode;
}) {
  const all = Children.toArray(children);
  const right = stack ? [] : all.filter(isBlock);
  const left = right.length ? all.filter((c) => !isBlock(c)) : all;
  const cls = `film-shot film-shot--${tone}${first ? ' film-shot--first' : ''}${compact ? ' film-shot--compact' : ''}`;

  return (
    <section className={cls} data-tone={tone} aria-label={title} id={id}>
      {right.length ? (
        <div className="film-col film-col--split">
          <div className="film-side">{left}</div>
          <div className="film-blocks">{right}</div>
        </div>
      ) : (
        <div className={`film-col${wide || stack ? ' film-col--wide' : ''}${stack ? ' film-col--stack' : ''}`}>{left}</div>
      )}
    </section>
  );
}
