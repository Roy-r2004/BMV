/**
 * The parts every plain public page is made of: the shell (navigation, page,
 * footer), the page's opening, a section, and the closing band. Pages with a
 * 3D story (home, about, private AI) keep their own layout and share only the
 * navigation, the footer and the closing band.
 */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import SiteNav from '../SiteNav';
import SiteFooter from '../SiteFooter';
import { PRICE_LINE } from '../../data/offer';

export function FirmPage({ children }: { children: ReactNode }) {
  return (
    <div className="fm-page min-h-screen">
      <SiteNav />
      <main>{children}</main>
      <SiteFooter />
    </div>
  );
}

export function PageHero({
  kicker,
  title,
  lede,
  actions,
  aside,
}: {
  kicker: string;
  title: string;
  lede?: ReactNode;
  actions?: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <header className="fm-hero">
      <div className={`fm-wrap fm-hero-grid${aside ? ' fm-hero-grid--aside' : ''}`}>
        <div>
          <p className="fm-kicker">{kicker}</p>
          <h1 className="fm-h1">{title}</h1>
          {lede ? <p className="fm-lede">{lede}</p> : null}
          {actions ? <div className="fm-actions">{actions}</div> : null}
        </div>
        {aside ? <div>{aside}</div> : null}
      </div>
    </header>
  );
}

export function Section({
  id,
  title,
  intro,
  mist = false,
  split = false,
  children,
}: {
  id?: string;
  title: string;
  intro?: ReactNode;
  mist?: boolean;
  split?: boolean;
  children?: ReactNode;
}) {
  return (
    <section id={id} className={`fm-section${mist ? ' fm-section--mist' : ''}`}>
      <div className="fm-wrap">
        <div className={`fm-section-head${split ? ' fm-section-head--split' : ''}`}>
          <h2 className="fm-h2">{title}</h2>
          {intro ? <p className="fm-intro">{intro}</p> : null}
        </div>
        {children}
      </div>
    </section>
  );
}

/** The closing band: the question every page ends on, and the way to act on it. */
export function CloseBand({
  title = 'What would you like to work out?',
  body = 'Describe it as you would to an adviser. The consultation starts from your words.',
}: {
  title?: string;
  body?: string;
}) {
  return (
    <section className="fm-close">
      <div className="fm-wrap">
        <h2 className="fm-serif">{title}</h2>
        <p>{body}</p>
        <div className="fm-actions">
          <Link to="/demo" className="fm-btn fm-btn--on-dark">
            Start a consultation
          </Link>
          <Link to="/contact" className="fm-btn-line fm-btn-line--on-dark">
            Contact us
          </Link>
        </div>
        <p className="fm-note">{PRICE_LINE}</p>
      </div>
    </section>
  );
}
