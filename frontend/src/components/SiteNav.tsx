import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import Logo from './Logo';
import GlowButton from './GlowButton';
import { useAuth } from '../context/AuthContext';
import { scrollToTop } from '../utils/scroll';

// One client-facing generator, called Demo. The old /demo page listed
// generated preview APPS; the studio generates the image demo, and it is
// the only generation a client is offered. Two entries called "Demo" and
// "Studio" made that a choice the client had to understand.
const LINKS = [
  { to: '/solutions', label: 'Solutions' },
  { to: '/demo', label: 'Demo' },
  { to: '/examples', label: 'Examples' },
  { to: '/about', label: 'About' },
];

export default function SiteNav() {
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const { user, isAuthenticated, logout, loading } = useAuth();

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [menuOpen]);

  return (
    <nav className="fixed top-0 inset-x-0 z-50 border-b border-blue-100/80 bg-white/95 shadow-sm shadow-blue-500/5 supports-[backdrop-filter]:backdrop-blur-md">
      <div className="container-max flex items-center justify-between gap-2 sm:gap-4 px-3 sm:px-6 h-14 sm:h-16 min-h-[3.5rem] pt-[env(safe-area-inset-top)]">
        <div className="shrink-0 min-w-0">
          <div className="sm:hidden">
            <Logo />
          </div>
          <div className="hidden sm:block">
            <Logo showName />
          </div>
        </div>

        <div className="hidden md:flex items-center gap-0.5 lg:gap-1">
          {LINKS.map((link) => {
            const active = pathname === link.to;
            return (
              <Link
                key={link.to}
                to={link.to}
                onClick={() => {
                  if (active) scrollToTop('smooth');
                }}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                  active
                    ? 'text-blue-600 bg-blue-50'
                    : 'text-slate-600 hover:text-blue-600 hover:bg-slate-50'
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </div>

        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          <button
            type="button"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((o) => !o)}
            className="md:hidden flex items-center justify-center w-11 h-11 rounded-xl text-slate-700 hover:bg-slate-100"
          >
            {menuOpen ? (
              <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
              </svg>
            )}
          </button>

          {!loading && isAuthenticated ? (
            <div className="hidden sm:flex items-center gap-2">
              <span className="text-xs text-slate-500 max-w-[120px] truncate" title={user?.email}>
                {user?.name}
              </span>
              <button
                type="button"
                onClick={() => logout()}
                className="text-xs font-medium text-slate-600 hover:text-blue-600 px-2 py-1 rounded-lg hover:bg-slate-50"
              >
                Sign out
              </button>
            </div>
          ) : (
            !loading && (
              <Link
                to="/login"
                state={{ from: pathname }}
                className="hidden sm:inline text-xs font-medium text-slate-600 hover:text-blue-600 px-2 py-1 rounded-lg hover:bg-slate-50"
              >
                Sign in
              </Link>
            )
          )}

          <GlowButton
            to="/demo"
            className="!inline-flex items-center justify-center text-xs sm:text-sm py-2.5 px-3.5 sm:px-4 whitespace-nowrap leading-none min-h-10"
          >
            <span className="sm:hidden">Start</span>
            <span className="hidden sm:inline">Create My Version</span>
          </GlowButton>
        </div>
      </div>

      {menuOpen && (
        <div className="md:hidden border-t border-slate-100 bg-white site-nav-mobile-menu">
          {LINKS.map((link) => {
            const active = pathname === link.to;
            return (
              <Link
                key={link.to}
                to={link.to}
                onClick={() => {
                  setMenuOpen(false);
                  if (active) scrollToTop('smooth');
                }}
                className={`rounded-xl font-semibold ${
                  active ? 'text-blue-600 bg-blue-50' : 'text-slate-800 hover:bg-slate-50'
                }`}
              >
                {link.label}
              </Link>
            );
          })}
          {!loading &&
            (isAuthenticated ? (
              <>
                <span className="px-3 py-2.5 text-sm text-slate-500">{user?.name}</span>
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    logout();
                  }}
                  className="rounded-xl font-semibold text-left text-slate-800 hover:bg-slate-50 w-full"
                >
                  Sign out
                </button>
              </>
            ) : (
              <Link
                to="/login"
                state={{ from: pathname }}
                onClick={() => setMenuOpen(false)}
                className="rounded-xl font-semibold text-blue-600 hover:bg-blue-50"
              >
                Sign in
              </Link>
            ))}
          <Link
            to="/demo"
            onClick={() => setMenuOpen(false)}
            className="mt-2 rounded-xl font-bold text-center text-white bg-gradient-to-r from-blue-600 to-cyan-500 py-3"
          >
            Start free preview
          </Link>
        </div>
      )}
    </nav>
  );
}
