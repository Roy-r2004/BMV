import { useCallback, useEffect, useState } from 'react';
import { cancelRequestGeneration, getRequestRunLog, type RequestRunLog } from '../api/admin';

function money(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return '—';
  return `$${n.toFixed(n >= 1 ? 2 : 4)}`;
}

function fmtAt(ts: number | null | undefined) {
  if (ts == null) return '—';
  try {
    return new Date(ts * 1000).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return String(ts);
  }
}

export default function RequestRunLogPanel({
  requestId,
  refreshKey = 0,
}: {
  requestId: number;
  refreshKey?: number;
}) {
  const [log, setLog] = useState<RequestRunLog | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'timeline' | 'ai' | 'progress'>('timeline');
  const [error, setError] = useState('');
  const [cancelling, setCancelling] = useState(false);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setError('');
    try {
      const data = await getRequestRunLog(requestId);
      setLog(data);
    } catch {
      setError('Could not load run log');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [requestId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  // Live console while generating
  useEffect(() => {
    if (!log?.is_generating) return;
    const t = window.setInterval(() => load(true), 3000);
    return () => window.clearInterval(t);
  }, [log?.is_generating, load]);

  if (loading && !log) {
    return (
      <section className="ac-panel" style={{ marginBottom: '0.9rem' }}>
        <p className="ac-muted">Loading cost & run log…</p>
      </section>
    );
  }

  if (error || !log) {
    return (
      <section className="ac-panel" style={{ marginBottom: '0.9rem' }}>
        <p className="ac-fail">{error || 'No run data'}</p>
      </section>
    );
  }

  return (
    <section className="ac-panel" style={{ marginBottom: '0.9rem' }}>
      <div className="ac-panel__head">
        <h2 className="ac-panel__title">
          Cost & run log
          {log.is_generating ? <span className="ac-pill ac-pill--live" style={{ marginLeft: '0.6rem' }}>Live</span> : null}
        </h2>
        <div className="ac-actions">
          {log.is_generating ? (
            <button
              type="button"
              className="ac-btn ac-btn--danger"
              style={{ width: 'auto', minHeight: '2.2rem' }}
              disabled={cancelling || log.cancel_requested}
              onClick={async () => {
                setCancelling(true);
                try {
                  await cancelRequestGeneration(requestId);
                  await load(true);
                } finally {
                  setCancelling(false);
                }
              }}
            >
              {log.cancel_requested ? 'Cancel pending…' : cancelling ? 'Cancelling…' : 'Cancel run'}
            </button>
          ) : null}
          <button type="button" className="ac-btn" onClick={() => load()} style={{ width: 'auto', minHeight: '2.2rem' }}>
            Refresh
          </button>
        </div>
      </div>

      {log.is_generating ? (
        <div className="ac-control ac-control--live" style={{ marginBottom: '0.9rem' }}>
          <div className="ac-control__top">
            <h3 className="ac-control__title">{log.progress.label || 'Generating…'}</h3>
            <span className="ac-pill ac-pill--live">{log.progress.pct ?? 0}%</span>
          </div>
          <p className="ac-control__desc" style={{ marginBottom: 0 }}>
            Stage <strong>{log.progress.stage || '—'}</strong>
            {' · '}spend so far <strong>{money(log.cost_usd)}</strong>
            {' · '}
            {log.progress.detail || 'Polling every 3s'}
            {log.cancel_requested ? ' · cancel requested — next AI call will stop' : ''}
          </p>
        </div>
      ) : null}

      <div className="ac-kpis" style={{ marginBottom: '0.9rem' }}>
        <article className="ac-kpi">
          <p className="ac-kpi__label">Total cost</p>
          <p className="ac-kpi__value">{money(log.cost_usd)}</p>
          <p className="ac-kpi__hint">{log.calls} AI calls</p>
        </article>
        <article className={`ac-kpi${log.failed_calls > 0 ? ' ac-kpi--warn' : ''}`}>
          <p className="ac-kpi__label">Failures</p>
          <p className="ac-kpi__value">{log.failed_calls}</p>
          <p className="ac-kpi__hint">Of {log.calls} calls</p>
        </article>
        <article className="ac-kpi">
          <p className="ac-kpi__label">Tokens</p>
          <p className="ac-kpi__value">{log.tokens.toLocaleString()}</p>
          <p className="ac-kpi__hint">{log.progress.stage || 'no stage'}</p>
        </article>
        <article className="ac-kpi ac-kpi--good">
          <p className="ac-kpi__label">Progress</p>
          <p className="ac-kpi__value">{log.progress.pct ?? 0}%</p>
          <p className="ac-kpi__hint">{log.progress.label || '—'}</p>
        </article>
      </div>

      {(log.by_purpose.length > 0 || log.by_model.length > 0) && (
        <div className="ac-grid-2" style={{ marginBottom: '0.9rem' }}>
          <div>
            <h3 className="ac-control__title" style={{ marginBottom: '0.5rem' }}>By stage / purpose</h3>
            <div className="ac-table-wrap">
              <table className="ac-table">
                <thead>
                  <tr>
                    <th>Purpose</th>
                    <th>Calls</th>
                    <th>Tokens</th>
                    <th>Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {log.by_purpose.map((r) => (
                    <tr key={r.key}>
                      <td className="ac-strong">{r.key}</td>
                      <td className="ac-num">{r.calls}</td>
                      <td className="ac-num">{r.tokens.toLocaleString()}</td>
                      <td className="ac-num">{money(r.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div>
            <h3 className="ac-control__title" style={{ marginBottom: '0.5rem' }}>By model</h3>
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
                  {log.by_model.map((r) => (
                    <tr key={r.key}>
                      <td className="ac-mono">{r.key}</td>
                      <td className="ac-num">{r.calls}</td>
                      <td className="ac-num">{r.tokens.toLocaleString()}</td>
                      <td className="ac-num">{money(r.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      <div className="ac-filters" style={{ marginBottom: '0.75rem' }}>
        {(
          [
            ['timeline', 'Full timeline'],
            ['ai', 'AI calls'],
            ['progress', 'Pipeline log'],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`ac-filter${tab === key ? ' is-active' : ''}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'timeline' && (
        <div className="ac-table-wrap">
          <table className="ac-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Type</th>
                <th>Message</th>
                <th>Cost</th>
                <th>Tokens</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {log.timeline.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <div className="ac-empty">No log events yet for this request.</div>
                  </td>
                </tr>
              ) : (
                log.timeline.map((row, i) => (
                  <tr key={`${row.kind}-${row.at}-${i}`}>
                    <td>{fmtAt(row.at)}</td>
                    <td>
                      <span className={row.kind === 'ai' ? (row.success === false ? 'ac-fail' : 'ac-ok') : 'ac-muted'}>
                        {row.kind === 'ai' ? 'AI' : 'STEP'}
                      </span>
                    </td>
                    <td className="ac-strong">{row.message}</td>
                    <td className="ac-num">{row.kind === 'ai' ? money(row.cost_usd) : '—'}</td>
                    <td className="ac-num">{row.kind === 'ai' ? (row.tokens ?? '—') : '—'}</td>
                    <td style={{ maxWidth: 280, wordBreak: 'break-word' }}>{row.detail || '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'ai' && (
        <div className="ac-table-wrap">
          <table className="ac-table">
            <thead>
              <tr>
                <th>When</th>
                <th>OK</th>
                <th>Purpose</th>
                <th>Model</th>
                <th>In</th>
                <th>Out</th>
                <th>Cost</th>
                <th>ms</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {log.usage_events.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <div className="ac-empty">
                      No AI calls attributed yet. New runs tag cost to this request automatically.
                    </div>
                  </td>
                </tr>
              ) : (
                log.usage_events.map((e) => (
                  <tr key={e.id}>
                    <td>
                      {e.created_at
                        ? new Date(e.created_at).toLocaleString(undefined, {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                            second: '2-digit',
                          })
                        : '—'}
                    </td>
                    <td>
                      <span className={e.success ? 'ac-ok' : 'ac-fail'}>{e.success ? 'OK' : 'FAIL'}</span>
                    </td>
                    <td>{e.purpose}</td>
                    <td className="ac-mono">{e.model}</td>
                    <td className="ac-num">{e.prompt_tokens}</td>
                    <td className="ac-num">{e.completion_tokens}</td>
                    <td className="ac-num">{money(e.cost_usd)}</td>
                    <td className="ac-num">{e.latency_ms ?? '—'}</td>
                    <td style={{ maxWidth: 220, wordBreak: 'break-word' }}>{e.error || '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'progress' && (
        <div className="ac-table-wrap">
          <table className="ac-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Stage</th>
                <th>%</th>
                <th>Message</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {(log.progress.log || []).length === 0 ? (
                <tr>
                  <td colSpan={5}>
                    <div className="ac-empty">No pipeline progress log stored yet.</div>
                  </td>
                </tr>
              ) : (
                (log.progress.log || []).map((row, i) => (
                  <tr key={`${row.t}-${i}`}>
                    <td>{fmtAt(row.t)}</td>
                    <td className="ac-strong">{row.stage || '—'}</td>
                    <td className="ac-num">{row.pct ?? '—'}</td>
                    <td>{row.msg || '—'}</td>
                    <td style={{ maxWidth: 280, wordBreak: 'break-word' }}>{row.detail || '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
