import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { COMPANY, SECTIONS } from '../data/company';
import { scrollToTop } from '../utils/scroll';

/**
 * The firm's navigation. On a wide screen every section is in the bar; below
 * that, one button opens a full-screen list that also carries the contact
 * line, so a visitor on a phone can reach the firm without scrolling to the
 * footer. A signed-in client also sees their engagements.
 */
export default function SiteNav() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const { user, isAuthenticated, logout, loading } = useAuth();

  const links = isAuthenticated
    ? [...SECTIONS, { to: '/engagements', label: 'Your engagements', hint: 'Consultations you have started' }]
    : [...SECTIONS];

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const current = (to: string) => (pathname === to ? 'page' : undefined);
  const onSame = (to: string) => () => {
    if (pathname === to) scrollToTop('smooth');
  };

  return (
    <>
      <nav className="fm-nav" aria-label="Main">
        <div className="fm-wrap fm-nav-bar">
          <Link to="/" className="fm-brand" onClick={onSame('/')}>
            <img src="/logo-160.png" alt="" width={36} height={36} />
            <span>{COMPANY.name}</span>
          </Link>

          <div className="fm-links">
            {links.map((l) => (
              <Link key={l.to} to={l.to} aria-current={current(l.to)} onClick={onSame(l.to)}>
                {l.label}
              </Link>
            ))}
          </div>

          <div className="fm-side">
            {!loading &&
              (isAuthenticated ? (
                <button type="button" className="fm-signin" onClick={() => logout()} title={user?.email}>
                  Sign out
                </button>
              ) : (
                <Link to="/login" state={{ from: pathname }} className="fm-signin">
                  Sign in
                </Link>
              ))}
            <Link to="/demo" className="fm-btn">
              Start a consultation
            </Link>
            <button
              type="button"
              className="fm-menu-btn"
              aria-label={open ? 'Close menu' : 'Open menu'}
              aria-expanded={open}
              aria-controls="fm-sheet"
              onClick={() => setOpen((o) => !o)}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                {open ? <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" /> : <path d="M3 7h18M3 12h18M3 17h18" strokeLinecap="round" />}
              </svg>
            </button>
          </div>
        </div>
      </nav>

      {open && (
        <div className="fm-sheet" id="fm-sheet" role="dialog" aria-modal="true" aria-label="Menu">
          <ul className="fm-sheet-links">
            {links.map((l) => (
              <li key={l.to}>
                <Link to={l.to} aria-current={current(l.to)} onClick={() => setOpen(false)}>
                  {l.label}
                  <small>{l.hint}</small>
                </Link>
              </li>
            ))}
          </ul>
          <div className="fm-sheet-actions">
            <Link to="/demo" className="fm-btn" onClick={() => setOpen(false)}>
              Start a consultation
            </Link>
            {!loading &&
              (isAuthenticated ? (
                <button
                  type="button"
                  className="fm-btn-line"
                  onClick={() => {
                    setOpen(false);
                    logout();
                  }}
                >
                  Sign out {user?.name ? `(${user.name})` : ''}
                </button>
              ) : (
                <Link to="/login" state={{ from: pathname }} className="fm-btn-line" onClick={() => setOpen(false)}>
                  Sign in
                </Link>
              ))}
          </div>
          <div className="fm-sheet-meta">
            <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a>
            <br />
            {COMPANY.name}. {COMPANY.registered}.
          </div>
        </div>
      )}
    </>
  );
}
