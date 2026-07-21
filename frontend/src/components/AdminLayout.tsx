import { useCallback, useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { clearAdminSession, getAdminOverview, hasAdminSession, type AdminOverview } from '../api/admin';
import Logo from './Logo';
import '../styles/admin-console.css';

function IconOps() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M4 13h6V4H4v9Zm10 7h6V11h-6v9ZM4 20h6v-5H4v5Zm10-11h6V4h-6v5Z" strokeLinejoin="round" />
    </svg>
  );
}

function IconRequests() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" strokeLinecap="round" />
    </svg>
  );
}

function IconUsage() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M4 19V5M4 19h16M8 15l3-4 3 2 4-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const links = [
  { to: '/admin', end: true, label: 'Command', icon: <IconOps /> },
  { to: '/admin/requests', end: false, label: 'Requests', icon: <IconRequests /> },
  { to: '/admin/usage', end: false, label: 'Usage', icon: <IconUsage /> },
];

function money(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return '—';
  return `$${n.toFixed(n >= 1 ? 2 : 4)}`;
}

export default function AdminLayout() {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<AdminOverview | null>(null);

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

      <div>
        <header className="ac-topbar">
          <div className="ac-topbar__brand">
            <Logo to="/admin" size="sm" theme="dark" />
            <NavLink to="/admin" end style={{ color: 'inherit', textDecoration: 'none' }}>
              BMV Ops
            </NavLink>
          </div>
          <nav className="ac-topbar__menu">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                className={({ isActive }) => (isActive ? 'is-active' : undefined)}
              >
                {l.label}
              </NavLink>
            ))}
            <button type="button" className="ac-btn" style={{ padding: '0.35rem 0.7rem' }} onClick={logout}>
              Out
            </button>
          </nav>
        </header>

        <main className="ac-main">
          <Outlet context={{ overview, refreshOverview: loadStatus }} />
        </main>
      </div>
    </div>
  );
}
