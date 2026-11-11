import type { ReactNode } from 'react';

/**
 * A black band with two panels: a picture of the data hall, and one sentence
 * set large on deep blue. The sentence's second half is quieter, so the eye
 * reads the first. It counts as a black section for the bar and for the
 * white panel that follows it.
 */
export default function StatementBand({
  caption,
  lead,
  rest,
  action,
}: {
  caption: string;
  lead: string;
  rest: string;
  action?: ReactNode;
}) {
  return (
    <section className="film-band film-shot--dark" data-tone="dark" aria-label={lead}>
      <figure className="film-band-pic">
        <div className="film-band-photo" aria-hidden="true" />
        <figcaption>{caption}</figcaption>
      </figure>
      <div className="film-band-say">
        <p className="film-band-line">
          {lead} <span>{rest}</span>
        </p>
        {action ? <div className="film-actions">{action}</div> : null}
      </div>
    </section>
  );
}
