import { useCallback, useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { clearAdminSession, getAdminOverview, hasAdminSession, type AdminOverview } from '../api/admin';
import Logo from './Logo';
import '../styles/admin-console.css';

function IconOps() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M4 13h6V4H4v9Zm10 7h6V11h-6v9ZM4 20h6v-5H4v5Zm10-11h6V4h-6v5Z" strokeLinejoin="round" />
    </svg>
  );
}

function IconRequests() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" strokeLinecap="round" />
    </svg>
  );
}

function IconUsage() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M4 19V5M4 19h16M8 15l3-4 3 2 4-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconOut() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M10 5H5v14h5M14 12H5M16 8l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function money(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return '—';
  return `$${n.toFixed(n >= 1 ? 2 : 4)}`;
}

export default function AdminLayout() {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<AdminOverview | null>(null);

  const links = [
    { to: '/admin', end: true, icon: <IconOps />, label: 'Overview', short: 'Home' },
    { to: '/admin/requests', end: false, icon: <IconRequests />, label: 'Requests', short: 'Requests' },
    { to: '/admin/usage', end: false, icon: <IconUsage />, label: 'Usage', short: 'Usage' },
  ];

  const loadStatus = useCallback(async () => {
    if (!hasAdminSession()) return;
    try {
      const data = await getAdminOverview();
      setOverview(data);
    } catch {
      /* ignore — pages handle auth redirects */
    }
  }, []);

  useEffect(() => {
    loadStatus();
    const t = window.setInterval(loadStatus, 30000);
    return () => window.clearInterval(t);
  }, [loadStatus]);

  const logout = () => {
    clearAdminSession();
    navigate('/admin/login');
  };

  const email = sessionStorage.getItem('admin_email');

  return (
    <div className="ac">
      <aside className="ac-rail">
        <div className="ac-rail__brand">
          <Logo to="/admin" size="sm" theme="dark" />
          <NavLink to="/admin" className="ac-rail__brand-text" end style={{ textDecoration: 'none', color: 'inherit' }}>
            <strong>BMV Ops</strong>
            <span>Command center</span>
          </NavLink>
        </div>

        <nav className="ac-rail__nav">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) => `ac-nav${isActive ? ' is-active' : ''}`}
            >
              {l.icon}
              {l.label}
            </NavLink>
          ))}
        </nav>

        <div className="ac-rail__status">
          <div className="ac-chip">
            <span className="ac-chip__label">AI</span>
            <span className={`ac-chip__val ${overview?.ai_enabled ? 'ac-chip__val--good' : 'ac-chip__val--bad'}`}>
              {overview ? (overview.ai_enabled ? 'Live' : 'Paused') : '…'}
            </span>
          </div>
          <div className="ac-chip">
            <span className="ac-chip__label">Chat</span>
            <span className={`ac-chip__val ${overview?.site_chat_enabled ? 'ac-chip__val--good' : 'ac-chip__val--muted'}`}>
              {overview ? (overview.site_chat_enabled ? 'On' : 'Off') : '…'}
            </span>
          </div>
          <div className="ac-chip">
            <span className="ac-chip__label">Today</span>
            <span className="ac-chip__val">{overview ? money(overview.cost_today_usd) : '…'}</span>
          </div>
          {email ? (
            <div className="ac-chip">
              <span className="ac-chip__label">Signed in</span>
              <span className="ac-chip__val ac-chip__val--muted" title={email}>
                {email.split('@')[0]}
              </span>
            </div>
          ) : null}
          <button type="button" className="ac-rail__logout" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>

      <div className="ac-shell">
        <header className="ac-topbar">
          <div className="ac-topbar__brand">
            <Logo to="/admin" size="sm" theme="dark" />
            <div className="ac-topbar__titles">
              <NavLink to="/admin" end style={{ color: 'inherit', textDecoration: 'none' }}>
                BMV Ops
              </NavLink>
              <span className="ac-topbar__live">
                <span className={overview?.ai_enabled ? 'ac-ok' : 'ac-fail'}>
                  {overview ? (overview.ai_enabled ? 'AI live' : 'AI paused') : '…'}
                </span>
                <span aria-hidden="true">·</span>
                <span>{overview ? money(overview.cost_today_usd) : '…'}</span>
              </span>
            </div>
          </div>
          <button type="button" className="ac-topbar__out" onClick={logout} aria-label="Sign out">
            <IconOut />
          </button>
        </header>

        <main className="ac-main">
          <Outlet context={{ overview, refreshOverview: loadStatus }} />
        </main>

        <nav className="ac-dock" aria-label="Admin sections">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) => `ac-dock__item${isActive ? ' is-active' : ''}`}
            >
              {l.icon}
              <span>{l.short}</span>
            </NavLink>
          ))}
          <button type="button" className="ac-dock__item ac-dock__item--out" onClick={logout}>
            <IconOut />
            <span>Out</span>
          </button>
        </nav>
      </div>
    </div>
  );
}
