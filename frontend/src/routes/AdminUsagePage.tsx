import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { hasAdminSession, listAdminUsage, type AiUsageEvent } from '../api/admin';

function money(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return '—';
  return `$${n.toFixed(n >= 1 ? 2 : 4)}`;
}

export default function AdminUsagePage() {
  const navigate = useNavigate();
  const [days, setDays] = useState(7);
  const [events, setEvents] = useState<AiUsageEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!hasAdminSession()) {
      navigate('/admin/login');
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const data = await listAdminUsage(days, 400);
        if (!cancelled) setEvents(data.events);
      } catch {
        navigate('/admin/login');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [days, navigate]);

  const totalCost = events
    .filter((e) => e.success && e.cost_usd != null)
    .reduce((s, e) => s + (e.cost_usd || 0), 0);
  const fails = events.filter((e) => !e.success).length;
  const tokens = events.reduce((s, e) => s + (e.total_tokens || 0), 0);

  return (
    <div className="ac-page">
      <header className="ac-hero">
        <div>
          <p className="ac-hero__eyebrow">Telemetry</p>
          <h1 className="ac-hero__title">AI usage</h1>
          <p className="ac-hero__sub">
            {events.length} events · {money(totalCost)} · {tokens.toLocaleString()} tokens · {fails} failures
          </p>
        </div>
        <div className="ac-actions">
          <select
            className="ac-input"
            style={{ width: 'auto' }}
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            <option value={1}>Last 24h</option>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <Link to="/admin" className="ac-btn">
            ← Command
          </Link>
        </div>
      </header>

      <section className="ac-kpis">
        <article className="ac-kpi">
          <p className="ac-kpi__label">Spend</p>
          <p className="ac-kpi__value">{money(totalCost)}</p>
          <p className="ac-kpi__hint">Selected window</p>
        </article>
        <article className="ac-kpi">
          <p className="ac-kpi__label">Events</p>
          <p className="ac-kpi__value">{events.length}</p>
          <p className="ac-kpi__hint">Success + failure</p>
        </article>
        <article className={`ac-kpi${fails > 0 ? ' ac-kpi--warn' : ''}`}>
          <p className="ac-kpi__label">Failures</p>
          <p className="ac-kpi__value">{fails}</p>
          <p className="ac-kpi__hint">
            {events.length ? `${Math.round((fails / events.length) * 100)}% fail rate` : '—'}
          </p>
        </article>
        <article className="ac-kpi">
          <p className="ac-kpi__label">Tokens</p>
          <p className="ac-kpi__value">{tokens.toLocaleString()}</p>
          <p className="ac-kpi__hint">All calls in window</p>
        </article>
      </section>

      <section className="ac-panel">
        {loading ? (
          <p className="ac-empty">Loading usage…</p>
        ) : (
          <div className="ac-table-wrap">
            <table className="ac-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>OK</th>
                  <th>Provider</th>
                  <th>Model</th>
                  <th>Purpose</th>
                  <th>Req</th>
                  <th>In</th>
                  <th>Out</th>
                  <th>Cost</th>
                  <th>ms</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id}>
                    <td>
                      {e.created_at
                        ? new Date(e.created_at).toLocaleString(undefined, {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })
                        : '—'}
                    </td>
                    <td>
                      <span className={e.success ? 'ac-ok' : 'ac-fail'}>{e.success ? 'OK' : 'FAIL'}</span>
                    </td>
                    <td>{e.provider}</td>
                    <td className="ac-mono">{e.model}</td>
                    <td>{e.purpose}</td>
                    <td>
                      {e.request_id ? (
                        <Link to={`/admin/requests/${e.request_id}`} className="ac-row-link">
                          #{e.request_id}
                        </Link>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="ac-num">{e.prompt_tokens || 0}</td>
                    <td className="ac-num">{e.completion_tokens || 0}</td>
                    <td className="ac-num">{money(e.cost_usd)}</td>
                    <td className="ac-num">{e.latency_ms ?? '—'}</td>
                    <td style={{ maxWidth: 240, wordBreak: 'break-word' }}>{e.error || '—'}</td>
                  </tr>
                ))}
                {events.length === 0 ? (
                  <tr>
                    <td colSpan={11}>
                      <div className="ac-empty">No events in this window.</div>
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
