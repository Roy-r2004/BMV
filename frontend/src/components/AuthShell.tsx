import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import Logo from './Logo';
import '../styles/auth-shell.css';

type AuthShellProps = {
  eyebrow: string;
  title: string;
  lead: string;
  children: ReactNode;
  footer?: ReactNode;
  visualTitle?: string;
  visualCopy?: string;
};

export default function AuthShell({
  eyebrow,
  title,
  lead,
  children,
  footer,
  visualTitle = 'BuildMyVersion',
  visualCopy = 'Diagnose what to automate, prove it with a free clickable preview, then ship the real product with our team.',
}: AuthShellProps) {
  return (
    <div className="auth-shell">
      <aside className="auth-shell__visual" aria-hidden="true">
        <div className="auth-shell__brand">
          <Logo to="/" size="md" />
          <h2 className="auth-shell__brand-name">{visualTitle}</h2>
          <p className="auth-shell__brand-copy">{visualCopy}</p>
        </div>
        <div className="auth-shell__meta">
          <span>AI consultancy</span>
          <span>Free preview</span>
          <span>Custom build</span>
        </div>
      </aside>

      <main className="auth-shell__panel">
        <div className="auth-shell__card">
          <div className="auth-shell__mobile-brand">
            <Logo to="/" size="sm" />
            <Link
              to="/"
              className="font-bold text-navy tracking-tight"
              style={{ fontFamily: 'var(--font-display)' }}
            >
              BuildMyVersion
            </Link>
          </div>
          <p className="auth-shell__eyebrow">{eyebrow}</p>
          <h1 className="auth-shell__title">{title}</h1>
          <p className="auth-shell__lead">{lead}</p>
          {children}
          {footer ? <div className="auth-shell__footer">{footer}</div> : null}
        </div>
      </main>
    </div>
  );
}
