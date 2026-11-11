/**
 * Roy's outreach list: businesses found, why they were picked, the message ready
 * to copy, and a status he sets once he has messaged them on Instagram by hand.
 * Nothing here sends anything.
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { hasAdminSession } from '../api/admin';
import {
  downloadOutreachSlides,
  fillOutreach,
  getOutreachList,
  isForbidden,
  setOutreachStatus,
  type OutreachList,
  type OutreachRow,
  type OutreachStatus,
} from '../api/outreach';

const LISTS: { id: OutreachStatus; label: string }[] = [
  { id: 'queued', label: 'To send' },
  { id: 'sent', label: 'Sent' },
  { id: 'replied', label: 'Replied' },
  { id: 'call_booked', label: 'Call booked' },
  { id: 'not_interested', label: 'Not interested' },
  { id: 'skip', label: 'Skipped' },
];

const MARKS: { id: OutreachStatus; label: string }[] = [
  { id: 'sent', label: 'Sent' },
  { id: 'replied', label: 'Replied' },
  { id: 'call_booked', label: 'Call booked' },
  { id: 'not_interested', label: 'Not interested' },
  { id: 'skip', label: 'Skip' },
];

function when(iso: string | null) {
  return iso ? new Date(iso).toLocaleString() : '';
}

function CopyBox({ label, text }: { label: string; text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };
  return (
    <div style={{ marginTop: 10 }}>
      <p className="ac-kpi__label" style={{ margin: '0 0 6px' }}>{label}</p>
      <textarea className="ac-input" readOnly value={text} rows={3} style={{ width: '100%', resize: 'vertical' }} />
      <button type="button" className="ac-btn" onClick={copy} style={{ marginTop: 6 }}>
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  );
}

function Row({ row, onMark }: { row: OutreachRow; onMark: (s: OutreachStatus) => void }) {
  const [saving, setSaving] = useState<'idle' | 'busy' | 'failed'>('idle');
  const saveSlides = async () => {
    setSaving('busy');
    try {
      await downloadOutreachSlides(row);
      setSaving('idle');
    } catch {
      setSaving('failed');
    }
  };
  const findHandle = row.website || `https://www.google.com/search?q=${encodeURIComponent(`${row.name} ${row.city} instagram`)}`;
  return (
    <article className="ac-panel" style={{ padding: 18 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 650 }}>{row.name}</h2>
          <p className="ac-hero__sub" style={{ margin: '4px 0 0' }}>
            {row.kind}, {row.city}
            {row.phone ? `, ${row.phone}` : ''}
            {row.opens ? `, opened ${row.opens}× (first ${when(row.opened_first_at)})` : ''}
            {row.sent_at ? `, sent ${when(row.sent_at)}` : ''}
          </p>
        </div>
        <div className="ac-actions">
          {row.instagram_url ? (
            <a className="ac-btn ac-btn--primary" href={row.instagram_url} target="_blank" rel="noopener noreferrer">
              Open @{row.instagram}
            </a>
          ) : (
            <a className="ac-btn" href={findHandle} target="_blank" rel="noopener noreferrer">
              Find the handle
            </a>
          )}
          <a className="ac-btn" href={`${row.report_url}?preview=1`} target="_blank" rel="noopener noreferrer">
            Open report
          </a>
        </div>
      </div>

      {row.reasons.length ? (
        <ul style={{ margin: '12px 0 0', paddingLeft: 18, fontSize: 14 }}>
          {row.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      ) : null}

      {row.dm ? <CopyBox label="1. First message (no link)" text={row.dm} /> : null}
      {row.messages.length ? (
        <div style={{ marginTop: 14 }}>
          <p className="ac-kpi__label" style={{ margin: 0 }}>2. When they reply yes: send these messages, then the slides, then the link</p>
          {row.messages.map((m, i) => (
            <CopyBox key={i} label={`Message ${i + 1} of ${row.messages.length}`} text={m} />
          ))}
          {row.slides ? (
            <div style={{ marginTop: 10 }}>
              <p className="ac-kpi__label" style={{ margin: '0 0 6px' }}>Slides ({row.slides}), sent together as one set</p>
              <button type="button" className="ac-btn ac-btn--primary" onClick={saveSlides} disabled={saving === 'busy'}>
                {saving === 'busy' ? 'Drawing the slides…' : 'Download slides'}
              </button>
              {saving === 'failed' ? (
                <span className="ac-hero__sub" style={{ marginLeft: 10 }}>The slides could not be made; the messages and the link are enough.</span>
              ) : null}
            </div>
          ) : null}
          {row.followup ? <CopyBox label="Last: the link" text={row.followup} /> : null}
        </div>
      ) : null}

      <div className="ac-actions" style={{ marginTop: 12, flexWrap: 'wrap' }}>
        {MARKS.filter((m) => m.id !== row.status).map((m) => (
          <button key={m.id} type="button" className="ac-btn" onClick={() => onMark(m.id)}>
            {m.label}
          </button>
        ))}
        {row.status !== 'queued' && row.dm ? (
          <button type="button" className="ac-btn" onClick={() => onMark('queued')}>
            Back to send
          </button>
        ) : null}
      </div>
    </article>
  );
}

export default function AdminOutreachPage() {
  const navigate = useNavigate();
  const [list, setList] = useState<OutreachStatus>('queued');
  const [data, setData] = useState<OutreachList | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!hasAdminSession()) navigate('/admin/login');
  }, [navigate]);

  const load = useCallback(async () => {
    try {
      setData(await getOutreachList(list));
      setError(null);
    } catch (err) {
      if (isForbidden(err)) {
        navigate('/admin/login');
      } else {
        setError('The outreach service could not be reached.');
      }
    }
  }, [list, navigate]);

  useEffect(() => {
    void load();
  }, [load]);

  // While a run is going, look again every few seconds.
  useEffect(() => {
    if (!data?.running) return;
    const t = setInterval(() => void load(), 4000);
    return () => clearInterval(t);
  }, [data?.running, load]);

  const fill = async () => {
    try {
      await fillOutreach();
      setData((d) => (d ? { ...d, running: true } : d));
      setTimeout(() => void load(), 1500);
    } catch {
      setError('A run could not be started. One may already be going.');
    }
  };

  const mark = async (row: OutreachRow, status: OutreachStatus) => {
    try {
      await setOutreachStatus(row.id, status);
      await load();
    } catch {
      setError(`${row.name} could not be marked.`);
    }
  };

  return (
    <div className="ac-page">
      <header className="ac-hero">
        <div>
          <p className="ac-hero__eyebrow">Outreach</p>
          <h1 className="ac-hero__title">Businesses to message</h1>
          <p className="ac-hero__sub">
            {data ? `$${data.spent.toFixed(2)} of $${data.cap.toFixed(0)} spent this month` : 'Loading…'}
            {data?.last_run
              ? `. Last run ${data.last_run.day}: ${data.last_run.queued} added${data.last_run.stopped_because ? `, ${data.last_run.stopped_because.toLowerCase()}` : ''}.`
              : ''}
          </p>
        </div>
        <div className="ac-actions">
          <button type="button" className="ac-btn ac-btn--primary" onClick={fill} disabled={!data || data.running}>
            {data?.running ? 'Finding businesses…' : `Find up to ${data?.daily ?? 30} more`}
          </button>
        </div>
      </header>

      <nav className="ac-actions" style={{ flexWrap: 'wrap', marginBottom: 16 }} aria-label="Lists">
        {LISTS.map((l) => (
          <button
            key={l.id}
            type="button"
            className={`ac-btn${list === l.id ? ' ac-btn--primary' : ''}`}
            onClick={() => setList(l.id)}
          >
            {l.label} {data?.counts?.[l.id] != null ? `(${data.counts[l.id]})` : ''}
          </button>
        ))}
      </nav>

      {error ? <p className="ac-empty">{error}</p> : null}
      {data && !data.rows.length ? (
        <p className="ac-empty">
          {list === 'queued' ? 'Nothing waiting. Press "Find" to look for new businesses.' : 'Nothing in this list yet.'}
        </p>
      ) : null}
      <div style={{ display: 'grid', gap: 14 }}>
        {data?.rows.map((row) => (
          <Row key={row.id} row={row} onMark={(s) => void mark(row, s)} />
        ))}
      </div>
    </div>
  );
}
