import { useEffect, useState } from 'react';
import { ApexLogo, IconClose, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import { type ConsultSlot } from './apexData.ts';

const QUEUE = [
  { id: '0', client: 'David Chen', matter: 'Chen LLC · Vendor contract', practice: 'Corporate', docs: 75, status: 'Vault chasing', channel: 'portal', urgent: true, partner: 'Rachel Holt', ai: 'Clause §4.2 flagged' },
  { id: '1', client: 'Priya N.', matter: 'Northwind HR dispute', practice: 'Employment', docs: 60, status: 'Conflict cleared', channel: 'email', urgent: false, partner: 'Marcus Chen', ai: 'Handbook reminder sent' },
  { id: '2', client: 'Atlas Corp', matter: 'Meridian arbitration', practice: 'Litigation', docs: 40, status: 'Conflict scan', channel: 'portal', urgent: false, partner: 'Elena Vasquez', ai: 'Scanning 847 matters' },
  { id: '3', client: 'James Walsh', matter: 'Family trust', practice: 'Estate', docs: 100, status: 'Billable-ready', channel: 'web', urgent: false, partner: 'Rachel Holt', ai: 'Engagement drafted' },
];

const THREAD = [
  { role: 'user' as const, text: 'We need counsel on a vendor SaaS agreement — any conflicts?', time: '2:14 PM' },
  { role: 'ai' as const, text: 'Conflict scan: Chen LLC cleared against 847 matters. Clause review queued on upload. Vault checklist sent — Rachel Holt Thu 10am held.', time: '2:14 PM' },
  { role: 'user' as const, text: 'Thu 10 works.', time: '2:15 PM' },
  { role: 'ai' as const, text: 'Locked ✓ Thu 10:00 AM · Rachel Holt. Vault 2/4 — cap table chaser live. Engagement letter drafting at 80%.', time: '2:15 PM' },
];

const DOC_ROWS = [
  { name: 'Entity charter', done: true },
  { name: 'Vendor agreement draft', done: true },
  { name: 'Cap table summary', done: false },
  { name: 'Signer ID', done: true },
];

const LIVE_TICKER = [
  'Vault chaser sent cap table reminder · Chen LLC',
  'Clause AI flagged indemnity cap · vendor agreement',
  'Engagement letter 80% drafted · Walsh trust',
  'Conflict cleared · Atlas Corp arbitration',
];

interface Props {
  bookedSlot: ConsultSlot | null;
  onClearBooking: () => void;
}

export default function ApexClientInbox({ bookedSlot, onClearBooking }: Props) {
  const [active, setActive] = useState('0');
  const [filter, setFilter] = useState<'all' | 'chasing' | 'ready'>('all');
  const [tickerIdx, setTickerIdx] = useState(0);
  const [liveDocs, setLiveDocs] = useState(75);
  const [aiTyping, setAiTyping] = useState(false);

  useEffect(() => {
    const t = window.setInterval(() => setTickerIdx((i) => (i + 1) % LIVE_TICKER.length), 2800);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    if (active !== '0') return;
    const t = window.setInterval(() => setLiveDocs((d) => (d >= 80 ? 75 : d + 1)), 2000);
    return () => window.clearInterval(t);
  }, [active]);

  useEffect(() => {
    setAiTyping(true);
    const t = window.setTimeout(() => setAiTyping(false), 900);
    return () => window.clearTimeout(t);
  }, [active]);

  const row = QUEUE.find((q) => q.id === active)!;
  const filtered = QUEUE.filter((q) => {
    if (filter === 'chasing') return q.docs < 100;
    if (filter === 'ready') return q.docs >= 100;
    return true;
  });
  const displayDocs = active === '0' ? liveDocs : row.docs;

  return (
    <div className="ax-queue ax-queue--counsel">
      <header className="ax-queue__head">
        <div className="ax-queue__head-brand">
          <ApexLogo className="ax-queue__logo" />
          <div>
            <h2>Doc vault queue</h2>
            <p>Counsel AI · conflict · clauses · vault chase</p>
          </div>
        </div>
        <div className="ax-queue__head-stats">
          <article><strong>18</strong><span>Matters</span></article>
          <article><strong>9</strong><span>Vault chasing</span></article>
          <article><strong>6</strong><span>Billable-ready</span></article>
        </div>
        <span className="ax-queue__ai-badge ax-queue__ai-badge--live">
          <span className="ax-queue__live-dot" aria-hidden />
          Counsel AI
        </span>
      </header>

      <div className="ax-queue__ticker" aria-live="polite">
        <IconSparkle className="ax-queue__sparkle" />
        <span>{LIVE_TICKER[tickerIdx]}</span>
      </div>

      {bookedSlot && (
        <div className="ax-queue__alert">
          <div>
            <strong>New matter opened</strong>
            <p>{bookedSlot.label} · conflict cleared · vault active</p>
          </div>
          <button type="button" onClick={onClearBooking} aria-label="Dismiss"><IconClose /></button>
        </div>
      )}

      <div className="ax-queue__filters">
        {(['all', 'chasing', 'ready'] as const).map((f) => (
          <button key={f} type="button" className={filter === f ? 'ax-queue__filter ax-queue__filter--on' : 'ax-queue__filter'} onClick={() => setFilter(f)}>
            {f === 'all' ? 'All matters' : f === 'chasing' ? 'Vault chasing' : 'Billable-ready'}
          </button>
        ))}
      </div>

      <div className="ax-queue__layout">
        <div className="ax-queue__table-wrap">
          <table className="ax-queue__table">
            <thead>
              <tr>
                <th>Client</th>
                <th>Matter</th>
                <th>Vault</th>
                <th>Counsel AI</th>
                <th>Partner</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((q) => (
                <tr
                  key={q.id}
                  className={`${active === q.id ? 'ax-queue__row--on' : ''} ${q.urgent ? 'ax-queue__row--urgent' : ''}`}
                  onClick={() => setActive(q.id)}
                >
                  <td>
                    <strong>{q.client}</strong>
                    <small>{q.channel}</small>
                  </td>
                  <td>{q.matter}</td>
                  <td>
                    <div className="ax-queue__bar">
                      <span style={{ width: `${active === q.id ? displayDocs : q.docs}%` }} />
                    </div>
                    <small>{active === q.id ? displayDocs : q.docs}%</small>
                  </td>
                  <td>
                    <span className={`ax-queue__pill ax-queue__pill--${q.docs >= 100 ? 'ready' : 'chase'}`}>{q.ai}</span>
                  </td>
                  <td>{q.partner}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <aside className="ax-queue__detail">
          <header>
            <h3>{row.client}</h3>
            <span>{row.matter}</span>
          </header>

          <section className="ax-queue__docs">
            <h4>Vault checklist</h4>
            <ul>
              {DOC_ROWS.map((d) => (
                <li key={d.name} className={d.done ? 'ax-queue__doc--done' : 'ax-queue__doc--chase'}>
                  <span>{d.done ? '✓' : '◎'}</span>
                  {d.name}
                </li>
              ))}
            </ul>
          </section>

          <section className="ax-queue__thread">
            <h4>
              <IconSparkle className="ax-queue__sparkle" />
              Counsel AI thread
            </h4>
            {THREAD.map((m, i) => (
              <div key={i} className={`ax-queue__msg ax-queue__msg--${m.role}`}>
                <p>{m.text}</p>
                <time>{m.time}</time>
              </div>
            ))}
            {aiTyping && (
              <div className="ax-queue__msg ax-queue__msg--ai ax-queue__msg--typing">
                <span className="ax-queue__dots"><span /><span /><span /></span>
              </div>
            )}
          </section>

          <div className="ax-queue__actions">
            <button type="button">Run clause review</button>
            <button type="button" className="ax-queue__actions--primary">Assign {row.partner}</button>
          </div>
        </aside>
      </div>
    </div>
  );
}
