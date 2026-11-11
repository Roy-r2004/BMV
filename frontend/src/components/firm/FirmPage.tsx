/**
 * The parts a plain public page is made of: the page itself (the shell
 * around it supplies the bar and the footer), the page's opening as a short
 * section, a section of prose, and the closing section every page can end on.
 */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import Rise from '../../film/Rise';
import Shot from '../../film/Shot';
import { PRICE_LINE } from '../../data/offer';

export function FirmPage({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

export function PageHero({
  kicker,
  title,
  lede,
  actions,
}: {
  kicker: string;
  title: string;
  lede?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <Shot title={kicker} compact wide>
      <p className="film-mark">{kicker}</p>
      <Rise as="h1" className="film-h2">
        {title}
      </Rise>
      {lede ? <p className="film-body">{lede}</p> : null}
      {actions ? <div className="film-actions">{actions}</div> : null}
    </Shot>
  );
}

export function Section({ id, title, intro, children }: { id?: string; title: string; intro?: ReactNode; children?: ReactNode }) {
  return (
    <section id={id} className="film-prose">
      <div>
        <h2>{title}</h2>
        {intro ? <p>{intro}</p> : null}
        {children}
      </div>
    </section>
  );
}

/** The closing shot: the question every page ends on, and the way to act on it. */
export function CloseBand({
  title = 'What would you like to *work out?*',
  body = 'Describe it as you would to an adviser. The consultation starts from your words.',
}: {
  title?: string;
  body?: string;
}) {
  return (
    <Shot title="Start">
      <p className="film-mark">Start</p>
      <Rise className="film-h">{title}</Rise>
      <p className="film-body">{body}</p>
      <div className="film-actions">
        <Link to="/demo" className="film-pill">
          Start a consultation
        </Link>
        <Link to="/contact" className="film-pill film-pill--ghost">
          Contact us
        </Link>
      </div>
      <p className="film-sub">{PRICE_LINE}</p>
    </Shot>
  );
}
