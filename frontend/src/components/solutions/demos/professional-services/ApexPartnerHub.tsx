import { useEffect, useState, type CSSProperties } from 'react';
import { ApexLogo, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import { FIRM, TODAY_MATTERS } from './apexData.ts';

type HubPage = 'briefing' | 'dossiers';

const PREP_CARDS = [
  {
    id: 'chen',
    client: 'David Chen',
    matter: 'Chen LLC · Vendor contract',
    partner: 'Rachel Holt',
    consult: 'Thu 10:00 AM',
    conflict: 'Cleared',
    clause: '§4.2 indemnity flagged',
    vault: 75,
    engage: 80,
    priority: true,
  },
  {
    id: 'walsh',
    client: 'James Walsh',
    matter: 'Family trust',
    partner: 'Rachel Holt',
    consult: 'Fri 3:00 PM',
    conflict: 'Cleared',
    clause: 'No risks found',
    vault: 100,
    engage: 92,
    priority: false,
  },
  {
    id: 'priya',
    client: 'Priya N.',
    matter: 'Northwind HR dispute',
    partner: 'Marcus Chen',
    consult: 'Thu 2:00 PM',
    conflict: 'Cleared',
    clause: 'Pending upload',
    vault: 60,
    engage: 45,
    priority: false,
  },
];

const SWIMLANES = [
  {
    id: 'conflict',
    label: 'Conflict scan',
    hint: 'Roster clearance',
    matters: [
      { client: 'Atlas Corp', name: 'Meridian arbitration', ai: 'Scanning 847 matters…', pulse: true },
    ],
  },
  {
    id: 'vault',
    label: 'Vault chase',
    hint: 'Counsel AI reminders',
    matters: [
      { client: 'Priya N.', name: 'Northwind HR', ai: 'W-2 + handbook missing', vault: 60 },
    ],
  },
  {
    id: 'review',
    label: 'Partner review',
    hint: 'Consult scheduled',
    matters: [
      { client: 'David Chen', name: 'Chen LLC · Vendor', ai: 'Clause §4.2 in brief', vault: 75, consult: 'Thu 10am' },
    ],
  },
  {
    id: 'ready',
    label: 'Billable-ready',
    hint: 'Engagement drafted',
    matters: [
      { client: 'James Walsh', name: 'Walsh family trust', ai: 'Engagement 92% · vault complete', vault: 100 },
    ],
  },
] as const;

const SYNC_LOG = [
  'Clio · Chen LLC matter synced',
  'DocuSign · cap table envelope opened',
  'Calendar · Rachel Holt Thu 10am locked',
  'Counsel AI · clause brief attached',
];

const LIVE_FEED = [
  'Conflict cleared · Atlas Corp',
  'Clause §4.2 flagged · Chen LLC',
  'Vault reminder · cap table · Priya N.',
  'Engagement 92% drafted · Walsh trust',
];

export default function ApexPartnerHub() {
  const [page, setPage] = useState<HubPage>('briefing');
  const [feedIdx, setFeedIdx] = useState(0);
  const [syncIdx, setSyncIdx] = useState(0);
  const [vaultPulse, setVaultPulse] = useState(75);

  useEffect(() => {
    const t = window.setInterval(() => setFeedIdx((i) => (i + 1) % LIVE_FEED.length), 2800);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    const t = window.setInterval(() => setSyncIdx((i) => (i + 1) % SYNC_LOG.length), 2200);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    const t = window.setInterval(() => setVaultPulse((v) => (v >= 78 ? 75 : v + 1)), 2000);
    return () => window.clearInterval(t);
  }, []);

  const readyLane = SWIMLANES.find((l) => l.id === 'ready')!;
  const visibleReady = readyLane.matters;

  return (
    <div className="ax-hub-app">
    <div className="ax-desk ax-desk--counsel">
      <aside className="ax-desk__nav">
        <div className="ax-desk__brand">
          <ApexLogo className="ax-desk__logo" />
          <div>
            <strong>Partner desk</strong>
            <span>{FIRM.name}</span>
          </div>
        </div>
        <nav>
          {([
            ['briefing', 'Today\'s briefing', 'Consults + AI prep'],
            ['dossiers', 'Matter dossiers', 'Conflict → billable'],
          ] as const).map(([id, label, sub]) => (
            <button
              key={id}
              type="button"
              className={page === id ? 'ax-desk__nav-btn ax-desk__nav-btn--on' : 'ax-desk__nav-btn'}
              onClick={() => setPage(id)}
            >
              <span>{label}</span>
              <small>{sub}</small>
            </button>
          ))}
        </nav>
        <div className="ax-desk__sync-strip">
          <p>Connected stack</p>
          <ul>
            {['Clio', 'DocuSign', 'Calendar', 'Counsel AI'].map((s) => (
              <li key={s}><span className="ax-desk__sync-dot" aria-hidden />{s}</li>
            ))}
          </ul>
          <small aria-live="polite">{SYNC_LOG[syncIdx]}</small>
        </div>
      </aside>

      <main className={`ax-desk__main ${page === 'dossiers' ? 'ax-desk__main--dossiers' : ''}`}>
        <header className="ax-desk__head">
          <h1>{page === 'briefing' ? 'Thursday briefing' : 'Matter dossiers'}</h1>
          <span className="ax-desk__live">
            <span className="ax-desk__live-dot" aria-hidden />
            Counsel AI
          </span>
        </header>

        <p className="ax-desk__feed ax-desk__feed--slim" aria-live="polite">
          <IconSparkle className="ax-desk__feed-icon" />
          <span>{LIVE_FEED[feedIdx]}</span>
        </p>

        {page === 'briefing' && (
          <>
            <section className="ax-briefing__consults">
              <h2>Today&apos;s consults</h2>
              <ul>
                {TODAY_MATTERS.filter((m) => m.status === 'confirmed' || m.time.includes('10:00') || m.time.includes('2:00')).map((m) => (
                  <li key={m.time + m.client} className={m.status === 'confirmed' ? 'ax-briefing__consult--on' : ''}>
                    <time>{m.time}</time>
                    <div>
                      <strong>{m.client}</strong>
                      <span>{m.matter} · {m.partner}</span>
                    </div>
                    <em>{m.status === 'confirmed' ? 'Brief ready' : 'Prep queued'}</em>
                  </li>
                ))}
              </ul>
            </section>

            <section className="ax-briefing__prep">
              <h2>Counsel AI prep briefs</h2>
              <p className="ax-briefing__prep-sub">Open a brief — conflict, clause flags, vault %, engagement draft in one view.</p>
              <div className="ax-briefing__grid">
                {PREP_CARDS.map((card) => (
                  <article key={card.id} className={card.priority ? 'ax-briefing__card ax-briefing__card--priority' : 'ax-briefing__card'}>
                    <header>
                      <div>
                        <strong>{card.client}</strong>
                        <span>{card.matter}</span>
                      </div>
                      <time>{card.consult}</time>
                    </header>
                    <div className="ax-briefing__chips">
                      <span className="ax-briefing__chip ax-briefing__chip--ok">Conflict {card.conflict.toLowerCase()}</span>
                      <span className={`ax-briefing__chip ${card.clause.includes('flagged') ? 'ax-briefing__chip--warn' : 'ax-briefing__chip--muted'}`}>
                        {card.clause}
                      </span>
                    </div>
                    <div className="ax-briefing__meters">
                      <label>
                        Vault
                        <div className="ax-briefing__bar"><span style={{ width: `${card.id === 'chen' ? vaultPulse : card.vault}%` }} /></div>
                        <small>{card.id === 'chen' ? vaultPulse : card.vault}%</small>
                      </label>
                      <label>
                        Engagement
                        <div className="ax-briefing__bar ax-briefing__bar--gold"><span style={{ width: `${card.engage}%` }} /></div>
                        <small>{card.engage}%</small>
                      </label>
                    </div>
                    <footer>
                      <span>{card.partner}</span>
                      <button type="button">Open brief</button>
                    </footer>
                  </article>
                ))}
              </div>
            </section>
          </>
        )}

        {page === 'dossiers' && (
          <section className="ax-dossiers">
            <p className="ax-dossiers__intro">
              Matters move conflict → vault → partner review → billable. Counsel AI runs each layer — partners never chase attachments.
            </p>
            <div className="ax-dossiers__board">
              {SWIMLANES.map((lane) => (
                <div key={lane.id} className={`ax-dossiers__lane ax-dossiers__lane--${lane.id}`}>
                  <header>
                    <strong>{lane.label}</strong>
                    <span>{lane.hint}</span>
                  </header>
                  <ul>
                    {(lane.id === 'ready' ? visibleReady : lane.matters).map((m) => (
                      <li key={m.client + m.name} className={'pulse' in m && m.pulse ? 'ax-dossiers__card ax-dossiers__card--pulse' : 'ax-dossiers__card'}>
                        <strong>{m.client}</strong>
                        <span>{m.name}</span>
                        {'vault' in m && m.vault !== undefined && (
                          <div className="ax-dossiers__vault-ring" style={{ '--pct': `${m.client === 'David Chen' ? vaultPulse : m.vault}%` } as CSSProperties}>
                            <svg viewBox="0 0 36 36" aria-hidden>
                              <circle className="ax-dossiers__ring-bg" cx="18" cy="18" r="15.5" />
                              <circle className="ax-dossiers__ring-fg" cx="18" cy="18" r="15.5" />
                            </svg>
                            <em>{m.client === 'David Chen' ? vaultPulse : m.vault}%</em>
                          </div>
                        )}
                        <p className="ax-dossiers__ai">
                          <IconSparkle className="ax-dossiers__sparkle" />
                          {m.ai}
                        </p>
                        {'consult' in m && m.consult && <time>{m.consult}</time>}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
            <footer className="ax-dossiers__foot">
              <div className="ax-dossiers__stat">
                <strong>18</strong>
                <span>Active matters</span>
              </div>
              <div className="ax-dossiers__stat">
                <strong>9</strong>
                <span>Billable-ready</span>
              </div>
              <div className="ax-dossiers__stat">
                <strong>23</strong>
                <span>Vault chases today</span>
              </div>
              <div className="ax-dossiers__stat ax-dossiers__stat--live">
                <IconSparkle className="ax-dossiers__sparkle" />
                <span>Counsel AI running</span>
              </div>
            </footer>
          </section>
        )}
      </main>
    </div>
    </div>
  );
}
