import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import Logo from './Logo';
import GlowButton from './GlowButton';
import { scrollToTop } from '../utils/scroll';

const LINKS = [
  { to: '/demo', label: 'Demo' },
  { to: '/examples', label: 'Examples' },
  { to: '/about', label: 'About' },
];

export default function SiteNav() {
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <nav className="fixed top-0 inset-x-0 z-50 border-b border-blue-100/80 bg-white/90 backdrop-blur-xl shadow-sm shadow-blue-500/5">
      <div className="container-max flex items-center justify-between gap-2 sm:gap-4 px-3 sm:px-6 h-14 sm:h-16 min-h-[3.5rem]">
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
            className="md:hidden flex items-center justify-center w-9 h-9 rounded-lg text-slate-600 hover:bg-slate-100"
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

          <GlowButton to="/submit" className="!inline-flex items-center justify-center text-xs sm:text-sm py-2 px-3 sm:px-4 whitespace-nowrap leading-none max-h-10">
            <span className="sm:hidden">Create</span>
            <span className="hidden sm:inline">Create My Version</span>
          </GlowButton>
        </div>
      </div>

      {menuOpen && (
        <div className="md:hidden border-t border-slate-100 bg-white/98 px-3 py-2 flex flex-col gap-0.5">
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
                className={`px-3 py-2.5 rounded-lg text-sm font-medium ${
                  active ? 'text-blue-600 bg-blue-50' : 'text-slate-700 hover:bg-slate-50'
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      )}
    </nav>
  );
}
