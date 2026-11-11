import type { ReactNode } from 'react';

const STEPS = ['Your words', 'The test', 'The answer', 'The plan'] as const;

/**
 * Sign in and sign up: the form on the left, on white; on the right, the data
 * hall in a frame with the firm's line and the consultation's steps. On a
 * phone the picture is dropped and the form has the screen.
 */
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
    <section className="film-auth" data-tone="light" aria-label={kicker}>
      <div className="film-auth-form">
        <div className="film-auth-in">
          <p className="film-mark">{kicker}</p>
          <h1 className="film-auth-h">{title}</h1>
          <p className="film-body">{lead}</p>
          {children}
          {footer ? <p className="film-form-foot">{footer}</p> : null}
        </div>
      </div>
      <div className="film-auth-art" aria-hidden="true">
        <div className="film-auth-photo" />
        <div className="film-auth-say">
          <p className="film-mark">Build My Version · Dubai</p>
          <p className="film-auth-line">AI consultants and engineers, based in Dubai.</p>
          <p className="film-auth-steps">
            {STEPS.map((s, i) => (
              <span key={s}>
                {String(i + 1).padStart(2, '0')} {s}
              </span>
            ))}
          </p>
        </div>
      </div>
    </section>
  );
}
