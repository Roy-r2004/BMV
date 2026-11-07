import type { ReactNode } from 'react';
import type { ShapeName } from './shapes';

/**
 * One shot of a scene: a screen-high section whose shape the light field
 * takes while the section is in the middle of the screen. `title` names the
 * shot in the rail and the slate; `words` is the sentence for the words shape.
 */
export default function Shot({
  shape,
  title,
  words,
  first = false,
  wide = false,
  compact = false,
  id,
  children,
}: {
  shape: ShapeName;
  title: string;
  words?: string;
  first?: boolean;
  wide?: boolean;
  /** As tall as its content: the opening of a page that is mostly reading. */
  compact?: boolean;
  id?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={`film-shot${first ? ' film-shot--first' : ''}${compact ? ' film-shot--compact' : ''}`}
      data-shape={shape}
      data-shot={title}
      data-words={words}
      id={id}
    >
      <div className={`film-col${wide ? ' film-col--wide' : ''}`}>{children}</div>
    </section>
  );
}
