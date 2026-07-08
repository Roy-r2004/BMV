import { useEffect, useState } from 'react';
import { DOC_CHECKLIST, FIRM } from './apexData.ts';

const PHASES = [
  { id: 'open', label: 'Matter opened', date: 'Wed 2:14 PM', done: true, detail: 'Conflict cleared · Chen LLC corporate' },
  { id: 'vault', label: 'Vault collection', date: 'Live · 75%', done: false, active: true, detail: 'Cap table chasing — Counsel AI reminder tomorrow 9am' },
  { id: 'clause', label: 'Clause review', date: 'In progress', done: false, detail: 'Indemnity cap flagged in vendor agreement §4.2' },
  { id: 'consult', label: 'Partner consult', date: 'Thu 10am', done: false, detail: 'Rachel Holt · discovery call' },
  { id: 'engage', label: 'Engagement letter', date: '80% drafted', done: false, detail: 'Auto-generated from matter brief — partner review after consult' },
];

interface Props {
  highlightClient?: string;
}

export default function ApexMatterTracker({ highlightClient = 'David Chen' }: Props) {
  const [vaultPct, setVaultPct] = useState(75);
  const [engagePct, setEngagePct] = useState(80);

  useEffect(() => {
    const t = window.setInterval(() => {
      setVaultPct((p) => (p >= 80 ? 75 : p + 1));
      setEngagePct((p) => (p >= 85 ? 80 : p + 1));
    }, 2200);
    return () => window.clearInterval(t);
  }, []);

  return (
    <div className="ax-matter ax-matter--counsel">
      <header className="ax-matter__head">
        <div>
          <p className="ax-matter__eyebrow">Client portal · live matter</p>
          <h2>{highlightClient} · Chen LLC</h2>
          <span>Corporate · Ref #AX-2841 · conflict cleared</span>
        </div>
        <div className="ax-matter__head-badges">
          <span className="ax-matter__head-badge ax-matter__head-badge--live">
            <span className="ax-matter__live-dot" aria-hidden />
            Counsel AI active
          </span>
          <span className="ax-matter__head-badge">Vault {vaultPct}%</span>
        </div>
      </header>

      <div className="ax-matter__layout">
        <section className="ax-matter__timeline">
          <h3>Matter timeline</h3>
          <ol>
            {PHASES.map((phase) => (
              <li
                key={phase.id}
                className={[
                  phase.done ? 'ax-matter__phase--done' : '',
                  phase.active ? 'ax-matter__phase--active' : '',
                ].filter(Boolean).join(' ')}
              >
                <span className="ax-matter__phase-dot" aria-hidden />
                <div>
                  <div className="ax-matter__phase-top">
                    <strong>{phase.label}</strong>
                    <time>{phase.date}</time>
                  </div>
                  <p>{phase.detail}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <aside className="ax-matter__vault">
          <h3>Secure vault</h3>
          <p className="ax-matter__vault-sub">Vault chaser AI · encrypted · partner-only</p>
          <div className="ax-matter__vault-bar">
            <span style={{ width: `${vaultPct}%` }} />
          </div>
          <ul>
            {DOC_CHECKLIST.map((d) => (
              <li key={d.name} className={d.done ? 'ax-matter__file--done' : 'ax-matter__file--pending'}>
                <span aria-hidden>{d.done ? '✓' : '◎'}</span>
                <div>
                  <strong>{d.name}</strong>
                  <small>{d.done ? 'Verified' : 'Chasing'}</small>
                </div>
                {!d.done && <button type="button">Upload</button>}
              </li>
            ))}
          </ul>
          <div className="ax-matter__vault-ai">
            <strong>Clause review live</strong>
            <p>Indemnity cap flagged §4.2 — partner brief attached to Thu consult</p>
          </div>
        </aside>

        <aside className="ax-matter__next">
          <h3>Next step</h3>
          <article className="ax-matter__consult">
            <p>Discovery consult</p>
            <strong>Thursday · 10:00 AM</strong>
            <span>Rachel Holt · Park Ave conference</span>
            <button type="button">Add to calendar</button>
          </article>
          <div className="ax-matter__engage">
            <p>Engagement letter</p>
            <div className="ax-matter__engage-bar">
              <span style={{ width: `${engagePct}%` }} />
            </div>
            <span>{engagePct}% drafted by Counsel AI</span>
          </div>
          <div className="ax-matter__contact">
            <p>Questions?</p>
            <span>Counsel AI answers conflict, vault, and clause questions 24/7</span>
            <button type="button">Open chat</button>
          </div>
          <p className="ax-matter__firm">{FIRM.name} · {FIRM.phone}</p>
        </aside>
      </div>
    </div>
  );
}
