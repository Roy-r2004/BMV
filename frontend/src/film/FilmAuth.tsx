import type { ReactNode } from 'react';
import Rise from './Rise';
import Shot from './Shot';

/** Sign in and sign up, on the film stage: one shot with the form, over the key. */
export default function FilmAuth({
  kicker,
  title,
  lead,
  footer,
  children,
}: {
  kicker: string;
  title: string;
  lead: string;
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="film-auth">
      <Shot title={kicker} first>
        <p className="film-mark">{kicker}</p>
        <Rise as="h1" className="film-h2">
          {title}
        </Rise>
        <p className="film-body">{lead}</p>
        {children}
        {footer ? <p className="film-form-foot">{footer}</p> : null}
      </Shot>
    </div>
  );
}
