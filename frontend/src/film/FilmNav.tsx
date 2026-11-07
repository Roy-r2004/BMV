import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { COMPANY, SECTIONS } from '../data/company';
import { pad2 } from './scenes';

/**
 * The bar over every scene. On a wide screen every section is in it; on a
 * narrow one a single button opens a curtain with the sections as a numbered
 * list, the way in to a consultation, and the firm's address. A signed-in
 * client also sees their engagements.
 */
export default function FilmNav() {
  const { pathname } = useLocation();
  const { user, isAuthenticated, logout, loading } = useAuth();
  const [open, setOpen] = useState(false);
  const [solid, setSolid] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const openRef = useRef<HTMLButtonElement>(null);

  const links = isAuthenticated
    ? [...SECTIONS, { to: '/engagements', label: 'Your engagements', hint: 'Consultations you have started' }]
    : [...SECTIONS];

  useEffect(() => {
    const on = () => setSolid(window.scrollY > 30);
    on();
    window.addEventListener('scroll', on, { passive: true });
    return () => window.removeEventListener('scroll', on);
  }, []);

  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    const opener = openRef.current;
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', onKey);
      opener?.focus();
    };
  }, [open]);

  const current = (to: string) => (pathname === to ? 'page' : undefined);

  return (
    <>
      <header className={`film-bar${solid ? ' is-solid' : ''}`}>
        <Link to="/" className="film-brand">
          <img src="/logo-160.png" alt="" width={36} height={36} />
          <span>{COMPANY.name}</span>
        </Link>
        <nav className="film-links" aria-label="Main">
          {links.map((l) => (
            <Link key={l.to} to={l.to} aria-current={current(l.to)}>
              {l.label}
            </Link>
          ))}
        </nav>
        {!loading &&
          (isAuthenticated ? (
            <button type="button" className="film-signin" onClick={() => logout()} title={user?.email}>
              Sign out
            </button>
          ) : (
            <Link to="/login" state={{ from: pathname }} className="film-signin">
              Sign in
            </Link>
          ))}
        <Link to="/demo" className="film-pill film-bar-cta">
          Start a consultation
        </Link>
        <button
          ref={openRef}
          type="button"
          className="film-menu-btn"
          aria-label="Open menu"
          aria-expanded={open}
          aria-controls="film-curtain"
          onClick={() => setOpen(true)}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M4 8h16M4 16h16" />
          </svg>
        </button>
      </header>

      <div className={`film-curtain${open ? ' is-open' : ''}`} id="film-curtain" role="dialog" aria-modal="true" aria-label="Menu" aria-hidden={!open} inert={!open}>
        <button ref={closeRef} type="button" className="film-curtain-close" aria-label="Close menu" onClick={() => setOpen(false)}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
        <ul>
          <li>
            <Link to="/" aria-current={current('/')}>
              <small>{pad2(1)}</small>Home
            </Link>
          </li>
          {links.map((l, i) => (
            <li key={l.to}>
              <Link to={l.to} aria-current={current(l.to)}>
                <small>{pad2(i + 2)}</small>
                {l.label}
              </Link>
            </li>
          ))}
        </ul>
        <div className="film-curtain-actions">
          <Link to="/demo" className="film-pill film-pill--light">
            Start a consultation
          </Link>
          {!loading &&
            (isAuthenticated ? (
              <button type="button" className="film-pill film-pill--line-dark" onClick={() => { setOpen(false); logout(); }}>
                Sign out{user?.name ? ` (${user.name})` : ''}
              </button>
            ) : (
              <Link to="/login" state={{ from: pathname }} className="film-pill film-pill--line-dark">
                Sign in
              </Link>
            ))}
        </div>
        <p className="film-curtain-meta">
          {COMPANY.email}
          <br />
          {COMPANY.name}. {COMPANY.registered}.
        </p>
      </div>
    </>
  );
}
