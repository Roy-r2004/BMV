import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  getAdminOverview,
  hasAdminSession,
  updateAdminSettings,
  type AdminOverview,
  type AiUsageEvent,
} from '../api/admin';

function money(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return '—';
  return `$${n.toFixed(n >= 1 ? 2 : 4)}`;
}

function fmtTime(iso: string | null) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function UsageRow({ e }: { e: AiUsageEvent }) {
  return (
    <tr>
      <td>{fmtTime(e.created_at)}</td>
      <td>
        <span className={e.success ? 'ac-ok' : 'ac-fail'}>{e.success ? 'OK' : 'FAIL'}</span>
      </td>
      <td className="ac-mono">{e.model}</td>
      <td>{e.purpose}</td>
      <td className="ac-num">{e.total_tokens || '—'}</td>
      <td className="ac-num">{money(e.cost_usd)}</td>
      <td className="ac-num">{e.latency_ms != null ? `${e.latency_ms}` : '—'}</td>
      <td title={e.error || ''} style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {e.error || (e.request_id ? (
          <Link className="ac-row-link" to={`/admin/requests/${e.request_id}`}>#{e.request_id}</Link>
        ) : '—')}
      </td>
    </tr>
  );
}

export default function AdminOpsPage() {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [budgetInput, setBudgetInput] = useState('');
  const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAdminOverview();
      setOverview(data);
      setBudgetInput(data.daily_budget_usd != null ? String(data.daily_budget_usd) : '');
    } catch {
      navigate('/admin/login');
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    if (!hasAdminSession()) {
      navigate('/admin/login');
      return;
    }
    load();
    const t = window.setInterval(load, 30000);
    return () => window.clearInterval(t);
  }, [load, navigate]);

  const patch = async (body: Parameters<typeof updateAdminSettings>[0], okMsg: string) => {
    setSaving(true);
    setMessage('');
    try {
      await updateAdminSettings(body);
      setMessage(okMsg);
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Update failed');
    } finally {
      setSaving(false);
    }
  };

  if (loading && !overview) {
    return (
      <div className="ac-page">
        <p className="ac-empty">Booting command center…</p>
      </div>
    );
  }
  if (!overview) return null;

  const aiOn = overview.ai_enabled;
  const chatOn = overview.site_chat_enabled;
  const statusEntries = Object.entries(overview.by_status).sort((a, b) => b[1] - a[1]);
  const statusMax = Math.max(1, ...statusEntries.map(([, c]) => c));
  const budgetPct =
    overview.daily_budget_usd != null && overview.daily_budget_usd > 0
      ? Math.min(100, (overview.cost_today_usd / overview.daily_budget_usd) * 100)
      : null;

  return (
    <div className="ac-page">
      <header className="ac-hero">
        <div>
          <p className="ac-hero__eyebrow">Command center</p>
          <h1 className="ac-hero__title">Operations</h1>
          <p className="ac-hero__sub">
            Provider <strong style={{ color: 'var(--ac-text)' }}>{overview.provider}</strong>
            {' · '}live status refresh every 30s
          </p>
        </div>
        <div className="ac-actions">
          <button type="button" className="ac-btn" onClick={() => load()} disabled={loading}>
            Refresh
          </button>
          <Link to="/admin/requests" className="ac-btn ac-btn--primary">
            Open requests
          </Link>
        </div>
      </header>

      {message ? <div className="ac-toast">{message}</div> : null}

      <section className="ac-kpis">
        <article className="ac-kpi">
          <p className="ac-kpi__label">Cost today</p>
          <p className="ac-kpi__value">{money(overview.cost_today_usd)}</p>
          <p className="ac-kpi__hint">7d {money(overview.cost_7d_usd)}</p>
        </article>
        <article className={`ac-kpi${overview.failed_today > 0 ? ' ac-kpi--warn' : ''}`}>
          <p className="ac-kpi__label">AI calls</p>
          <p className="ac-kpi__value">{overview.calls_today}</p>
          <p className="ac-kpi__hint">{overview.failed_today} failed today</p>
        </article>
        <article className="ac-kpi">
          <p className="ac-kpi__label">Tokens</p>
          <p className="ac-kpi__value">{overview.tokens_today.toLocaleString()}</p>
          <p className="ac-kpi__hint">Prompt + completion</p>
        </article>
        <article className="ac-kpi ac-kpi--good">
          <p className="ac-kpi__label">Requests</p>
          <p className="ac-kpi__value">{overview.requests_today}</p>
          <p className="ac-kpi__hint">{overview.requests_total} all-time</p>
        </article>
      </section>

      <section className="ac-panel" style={{ marginBottom: '0.9rem' }}>
        <div className="ac-panel__head">
          <h2 className="ac-panel__title">Control plane</h2>
          <span className="ac-muted">Instant kill switches</span>
        </div>
        <div className="ac-grid-3" style={{ marginBottom: 0 }}>
          <div className={`ac-control ${aiOn ? 'ac-control--live' : 'ac-control--off'}`}>
            <div className="ac-control__top">
              <h3 className="ac-control__title">Master AI</h3>
              <span className={`ac-pill ${aiOn ? 'ac-pill--live' : 'ac-pill--off'}`}>
                {aiOn ? 'Live' : 'Paused'}
              </span>
            </div>
            <p className="ac-control__desc">
              Hard stop for pipeline, vision, regenerate actions, and site chat.
            </p>
            <button
              type="button"
              disabled={saving}
              className={`ac-btn ${aiOn ? 'ac-btn--danger' : 'ac-btn--good'}`}
              onClick={() => patch({ ai_enabled: !aiOn }, aiOn ? 'AI paused' : 'AI enabled')}
            >
              {aiOn ? 'Pause all AI' : 'Enable AI'}
            </button>
          </div>

          <div className={`ac-control ${chatOn && aiOn ? 'ac-control--live' : ''}`}>
            <div className="ac-control__top">
              <h3 className="ac-control__title">Site chat</h3>
              <span className={`ac-pill ${chatOn && aiOn ? 'ac-pill--live' : 'ac-pill--muted'}`}>
                {chatOn && aiOn ? 'On' : 'Off'}
              </span>
            </div>
            <p className="ac-control__desc">
              Marketing guide only. Pipeline can stay live while chat is disabled.
            </p>
            <button
              type="button"
              disabled={saving || !aiOn}
              className="ac-btn"
              onClick={() =>
                patch({ site_chat_enabled: !chatOn }, chatOn ? 'Site chat disabled' : 'Site chat enabled')
              }
            >
              {chatOn ? 'Disable chat' : 'Enable chat'}
            </button>
          </div>

          <div className="ac-control">
            <div className="ac-control__top">
              <h3 className="ac-control__title">Daily budget</h3>
              <span className="ac-pill ac-pill--muted">
                {overview.daily_budget_usd == null ? 'No cap' : 'Capped'}
              </span>
            </div>
            <p className="ac-control__desc">
              Soft USD cap. When hit, new AI calls block until tomorrow (UTC).
            </p>
            <div style={{ display: 'flex', gap: '0.45rem', marginBottom: '0.45rem' }}>
              <input
                type="number"
                min={0}
                step={0.5}
                placeholder="No cap"
                value={budgetInput}
                onChange={(e) => setBudgetInput(e.target.value)}
                className="ac-input"
              />
              <button
                type="button"
                disabled={saving}
                className="ac-btn ac-btn--primary"
                onClick={() => {
                  const v = budgetInput.trim();
                  if (!v) {
                    patch({ clear_daily_budget: true }, 'Budget cleared');
                    return;
                  }
                  const n = Number(v);
                  if (Number.isNaN(n) || n < 0) {
                    setMessage('Enter a valid budget');
                    return;
                  }
                  patch({ daily_budget_usd: n }, `Budget set to $${n}`);
                }}
              >
                Save
              </button>
            </div>
            <button
              type="button"
              disabled={saving}
              className="ac-btn"
              style={{ alignSelf: 'flex-start' }}
              onClick={() => {
                setBudgetInput('');
                patch({ clear_daily_budget: true }, 'Budget cleared');
              }}
            >
              Clear cap
            </button>
            {budgetPct != null ? (
              <div className="ac-budget-bar">
                <div className="ac-budget-bar__meta">
                  <span>Used today</span>
                  <span>
                    {money(overview.cost_today_usd)} / {money(overview.daily_budget_usd)}
                  </span>
                </div>
                <div className="ac-budget-bar__track">
                  <div
                    className={`ac-budget-bar__fill${budgetPct >= 90 ? ' is-bad' : budgetPct >= 70 ? ' is-warn' : ''}`}
                    style={{ width: `${budgetPct}%` }}
                  />
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </section>

      <div className="ac-grid-2">
        <section className="ac-panel">
          <div className="ac-panel__head">
            <h2 className="ac-panel__title">Pipeline status</h2>
            <Link to="/admin/requests" className="ac-panel__link">
              Manage →
            </Link>
          </div>
          {statusEntries.length === 0 ? (
            <p className="ac-muted">No requests yet.</p>
          ) : (
            <ul className="ac-status-list">
              {statusEntries.map(([status, count]) => (
                <li key={status}>
                  <span className="ac-status-list__name">{status}</span>
                  <span className="ac-status-list__bar">
                    <span
                      className="ac-status-list__fill"
                      style={{ width: `${(count / statusMax) * 100}%` }}
                    />
                  </span>
                  <span className="ac-status-list__count">{count}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="ac-panel">
          <div className="ac-panel__head">
            <h2 className="ac-panel__title">Top models today</h2>
          </div>
          {overview.top_models_today.length === 0 ? (
            <p className="ac-muted">No successful AI calls today.</p>
          ) : (
            <div className="ac-table-wrap">
              <table className="ac-table">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Calls</th>
                    <th>Tokens</th>
                    <th>Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.top_models_today.map((m) => (
                    <tr key={m.model}>
                      <td className="ac-mono">{m.model}</td>
                      <td className="ac-num">{m.calls}</td>
                      <td className="ac-num">{m.tokens.toLocaleString()}</td>
                      <td className="ac-num">{money(m.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      <section className="ac-panel" style={{ marginBottom: '0.9rem' }}>
        <div className="ac-panel__head">
          <h2 className="ac-panel__title">Failure feed</h2>
          <Link to="/admin/usage" className="ac-panel__link">
            Full log →
          </Link>
        </div>
        {overview.recent_failures.length === 0 ? (
          <p className="ac-ok">No failures recorded. Systems look clean.</p>
        ) : (
          <div className="ac-table-wrap">
            <table className="ac-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Status</th>
                  <th>Model</th>
                  <th>Purpose</th>
                  <th>Tokens</th>
                  <th>Cost</th>
                  <th>ms</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {overview.recent_failures.map((e) => (
                  <UsageRow key={e.id} e={e} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="ac-panel">
        <div className="ac-panel__head">
          <h2 className="ac-panel__title">Live AI traffic</h2>
          <span className="ac-muted">Latest {overview.recent_usage.length} calls</span>
        </div>
        <div className="ac-table-wrap">
          <table className="ac-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Status</th>
                <th>Model</th>
                <th>Purpose</th>
                <th>Tokens</th>
                <th>Cost</th>
                <th>ms</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {overview.recent_usage.length === 0 ? (
                <tr>
                  <td colSpan={8}>
                    <div className="ac-empty">No usage events yet — appear after the next AI call.</div>
                  </td>
                </tr>
              ) : (
                overview.recent_usage.map((e) => <UsageRow key={e.id} e={e} />)
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
