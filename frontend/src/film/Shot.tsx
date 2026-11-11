import type { ReactNode } from 'react';

/**
 * One section of a public page. `tone` paints it white or black; a white
 * section that follows a black one rises over it as a panel, and the bar
 * above the page takes the colour that reads on the section under it.
 * `title` names the section for screen readers' landmarks.
 */
export default function Shot({
  tone = 'light',
  title,
  first = false,
  wide = false,
  compact = false,
  id,
  children,
}: {
  tone?: 'light' | 'dark';
  title: string;
  first?: boolean;
  wide?: boolean;
  /** As tall as its content: the opening of a page that is mostly reading. */
  compact?: boolean;
  id?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={`film-shot film-shot--${tone}${first ? ' film-shot--first' : ''}${compact ? ' film-shot--compact' : ''}`}
      data-tone={tone}
      aria-label={title}
      id={id}
    >
      <div className={`film-col${wide ? ' film-col--wide' : ''}`}>{children}</div>
    </section>
  );
}
