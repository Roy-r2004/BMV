import { useEffect, useState } from 'react';
import { IconSparkle } from '../shared/ShowcaseChatIcons.tsx';

const AI_EVENTS = [
  { kind: 'conflict', label: 'Conflict scan', text: 'Chen LLC cleared — no conflicts with 847 active matters' },
  { kind: 'clause', label: 'Clause review', text: 'Indemnity cap flagged in vendor agreement §4.2 — partner brief queued' },
  { kind: 'vault', label: 'Vault chaser', text: 'Cap table reminder sent · 2 of 4 files secured' },
  { kind: 'engage', label: 'Engagement draft', text: 'Letter 80% drafted from questionnaire — Rachel Holt review Thu' },
] as const;

const DOC_ITEMS = [
  { name: 'Entity charter', done: true },
  { name: 'Vendor agreement', done: true },
  { name: 'Cap table summary', done: false },
  { name: 'Signer ID', done: false },
];

export default function ApexCounselLive({ compact = false }: { compact?: boolean }) {
  const [eventIdx, setEventIdx] = useState(0);
  const [typing, setTyping] = useState(false);
  const [docPct, setDocPct] = useState(50);

  useEffect(() => {
    const tick = window.setInterval(() => {
      setTyping(true);
      window.setTimeout(() => {
        setEventIdx((i) => (i + 1) % AI_EVENTS.length);
        setTyping(false);
      }, 680);
    }, 3200);
    return () => window.clearInterval(tick);
  }, []);

  useEffect(() => {
    const docTick = window.setInterval(() => {
      setDocPct((p) => (p >= 75 ? 50 : p + 5));
    }, 2400);
    return () => window.clearInterval(docTick);
  }, []);

  const event = AI_EVENTS[eventIdx];
  const doneCount = DOC_ITEMS.filter((d) => d.done).length;

  return (
    <aside className={`ax-counsel-live ${compact ? 'ax-counsel-live--compact' : ''}`} aria-live="polite">
      <header className="ax-counsel-live__head">
        <span className="ax-counsel-live__pulse" aria-hidden />
        <div>
          <strong>Counsel AI</strong>
          <span>Live on Chen LLC matter</span>
        </div>
        <em className="ax-counsel-live__secure">SOC2</em>
      </header>

      <div className="ax-counsel-live__feed">
        <p className="ax-counsel-live__feed-label">
          <IconSparkle className="ax-counsel-live__sparkle" />
          {typing ? 'Analyzing…' : event.label}
        </p>
        {typing ? (
          <span className="ax-counsel-live__dots" aria-hidden>
            <span /><span /><span />
          </span>
        ) : (
          <p className="ax-counsel-live__feed-text">{event.text}</p>
        )}
      </div>

      {!compact && (
        <>
          <div className="ax-counsel-live__vault">
            <div className="ax-counsel-live__vault-top">
              <span>Secure vault</span>
              <strong>{docPct}%</strong>
            </div>
            <div className="ax-counsel-live__bar">
              <span style={{ width: `${docPct}%` }} />
            </div>
            <ul>
              {DOC_ITEMS.map((d) => (
                <li key={d.name} className={d.done ? 'ax-counsel-live__doc--done' : ''}>
                  <span aria-hidden>{d.done ? '✓' : '○'}</span>
                  {d.name}
                  {!d.done && <em>chasing</em>}
                </li>
              ))}
            </ul>
          </div>

          <footer className="ax-counsel-live__foot">
            <span>{doneCount} of {DOC_ITEMS.length} verified</span>
            <span className="ax-counsel-live__foot-live">Live</span>
          </footer>
        </>
      )}
    </aside>
  );
}
