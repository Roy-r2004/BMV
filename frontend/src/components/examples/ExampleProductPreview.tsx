import type { ExampleOutput } from '../../data/examples';

type AppMeta = {
  brand: string;
  nav: { label: string; icon: string }[];
  active: string;
  user: string;
  role: string;
};

const APPS: Record<string, AppMeta> = {
  'business-xray': {
    brand: 'X-Ray',
    nav: [
      { label: 'Analyze', icon: '◎' },
      { label: 'Reports', icon: '▣' },
      { label: 'Compare', icon: '⇄' },
      { label: 'Share', icon: '↗' },
    ],
    active: 'Analyze',
    user: 'Alex Rivera',
    role: 'Strategy',
  },
  hirewise: {
    brand: 'HireWise',
    nav: [
      { label: 'Jobs', icon: '◎' },
      { label: 'Candidates', icon: '▣' },
      { label: 'Shortlist', icon: '★' },
      { label: 'Settings', icon: '⚙' },
    ],
    active: 'Candidates',
    user: 'Sam Okoye',
    role: 'Talent',
  },
  cashpath: {
    brand: 'CashPath',
    nav: [
      { label: 'Overview', icon: '◎' },
      { label: 'Expenses', icon: '▣' },
      { label: 'Insights', icon: '◈' },
      { label: 'Export', icon: '↓' },
    ],
    active: 'Overview',
    user: 'Jordan Lee',
    role: 'Finance',
  },
  clinic: {
    brand: 'ClinicAI',
    nav: [
      { label: 'Inbox', icon: '◎' },
      { label: 'Calendar', icon: '▣' },
      { label: 'Patients', icon: '◇' },
      { label: 'Settings', icon: '⚙' },
    ],
    active: 'Inbox',
    user: 'Dr. Lee',
    role: 'Clinic',
  },
  scaleyou: {
    brand: 'ScaleYou',
    nav: [
      { label: 'Pipeline', icon: '◎' },
      { label: 'Outreach', icon: '↗' },
      { label: 'Meetings', icon: '▣' },
      { label: 'Analytics', icon: '◈' },
    ],
    active: 'Pipeline',
    user: 'Riley Chen',
    role: 'Growth',
  },
  visioncommerce: {
    brand: 'Vision',
    nav: [
      { label: 'Search', icon: '◎' },
      { label: 'Catalog', icon: '▣' },
      { label: 'Orders', icon: '◇' },
      { label: 'Merchants', icon: '⚙' },
    ],
    active: 'Search',
    user: 'Casey Park',
    role: 'Merch',
  },
};

/** Logged-in product UI — dense, real SaaS workspace. */
export default function ExampleProductPreview({
  example,
  size = 'md',
}: {
  example: ExampleOutput;
  size?: 'sm' | 'md' | 'lg';
}) {
  const app = APPS[example.id] ?? {
    brand: example.inspiredBy.slice(0, 10),
    nav: example.screens.slice(0, 4).map((label) => ({ label, icon: '·' })),
    active: example.screens[0] ?? 'Home',
    user: 'You',
    role: 'Owner',
  };

  if (size === 'sm') {
    return (
      <div className="ex-preview ex-preview--sm" data-example={example.id}>
        <div className="ex-preview__canvas">
          <ThumbUI example={example} />
        </div>
      </div>
    );
  }

  const dense = size === 'md';

  return (
    <div className={`ex-preview ex-preview--${size} ex-preview--app`} data-example={example.id}>
      <div className="ex-app">
        <aside className="ex-app__side" aria-hidden>
          <div className="ex-app__brand">
            <span className="ex-app__mark" data-brand={example.id} />
            <div>
              <b>{app.brand}</b>
              <i>Pro</i>
            </div>
          </div>
          <nav className="ex-app__nav">
            {app.nav.map((item) => (
              <span
                key={item.label}
                className={
                  item.label === app.active ? 'ex-app__nav-item ex-app__nav-item--on' : 'ex-app__nav-item'
                }
              >
                <em>{item.icon}</em>
                {item.label}
              </span>
            ))}
          </nav>
          <div className="ex-app__user">
            <span className="ex-app__av" data-brand={example.id} />
            <div>
              <em>{app.user.split(' ')[0]}</em>
              <i>{app.role}</i>
            </div>
          </div>
        </aside>

        <div className="ex-app__main">
          <header className="ex-app__top">
            <div className="ex-app__crumbs">
              <span>{app.brand}</span>
              <i>/</i>
              <strong>{app.active}</strong>
            </div>
            <div className="ex-app__top-actions">
              <span className="ex-app__search" aria-hidden>
                Search…
              </span>
              <button type="button" className="ex-app__btn" tabIndex={-1}>
                {primaryAction(example.id)}
              </button>
            </div>
          </header>
          <div className={`ex-app__body ${dense ? 'ex-app__body--dense' : ''}`}>
            <AppScreen example={example} dense={dense} />
          </div>
        </div>
      </div>
    </div>
  );
}

function primaryAction(id: string): string {
  switch (id) {
    case 'business-xray':
      return 'New analysis';
    case 'hirewise':
      return 'Invite';
    case 'cashpath':
      return 'Add expense';
    case 'clinic':
      return 'Book slot';
    case 'scaleyou':
      return 'Launch';
    case 'visioncommerce':
      return 'New search';
    default:
      return 'New';
  }
}

function AppScreen({ example, dense }: { example: ExampleOutput; dense?: boolean }) {
  switch (example.id) {
    case 'business-xray':
      return <XrayApp dense={dense} />;
    case 'hirewise':
      return <HireApp dense={dense} />;
    case 'cashpath':
      return <CashApp dense={dense} />;
    case 'clinic':
      return <ClinicApp dense={dense} />;
    case 'scaleyou':
      return <SalesApp dense={dense} />;
    case 'visioncommerce':
      return <MarketApp dense={dense} />;
    default:
      return (
        <div className="ex-work">
          <p className="ex-work__muted">{example.tagline}</p>
        </div>
      );
  }
}

function ThumbUI({ example }: { example: ExampleOutput }) {
  return (
    <div className="ex-thumb">
      <span className="ex-thumb__pill">{example.industry.split(/[&/]/)[0].trim()}</span>
      <strong>{example.score}%</strong>
      <div className="ex-thumb__bars">
        <i style={{ width: '82%' }} />
        <i style={{ width: '58%' }} />
      </div>
    </div>
  );
}

function XrayApp({ dense }: { dense?: boolean }) {
  return (
    <div className="ex-work">
      <div className="ex-work__insight">
        <span className="ex-work__insight-mark">AI</span>
        <p>Best wedge: transparent SMB pricing — they hide cost on /pricing.</p>
      </div>

      <div className="ex-work__toolbar">
        <label className="ex-work__field ex-work__field--grow">
          <span>Company URL</span>
          <div className="ex-work__input">
            <i>https://</i>
            <em>acme.co</em>
            <b>Analyze</b>
          </div>
        </label>
        <div className="ex-work__status">
          <span className="ex-work__dot" />
          Ready · 2.4s
        </div>
      </div>

      <div className="ex-work__stats">
        <div>
          <span>Fit</span>
          <strong>88%</strong>
        </div>
        <div>
          <span>Gaps</span>
          <strong>4</strong>
        </div>
        <div>
          <span>Moves</span>
          <strong>{dense ? '2' : '3'}</strong>
        </div>
      </div>

      <div className="ex-work__split">
        <section className="ex-work__panel">
          <header>
            <strong>acme.co</strong>
            <span className="ex-work__badge">B2B SaaS</span>
          </header>
          <ul className="ex-work__kv">
            <li>
              <span>Positioning</span>
              <b>Mid-market ops</b>
            </li>
            <li>
              <span>Signal</span>
              <b className="ex-work__warn">Pricing opaque</b>
            </li>
            {!dense && (
              <li>
                <span>Traffic</span>
                <b>~42k / mo</b>
              </li>
            )}
          </ul>
        </section>

        <section className="ex-work__panel">
          <header>
            <strong>Attack plan</strong>
            <span className="ex-work__muted">Priority</span>
          </header>
          <ol className="ex-work__steps">
            <li>
              <b>1</b>
              <div>
                <strong>Own the URL → plan</strong>
                {!dense && <p>Instant brief vs their PDF cycle</p>}
              </div>
            </li>
            <li>
              <b>2</b>
              <div>
                <strong>SMB pricing wedge</strong>
                {!dense && <p>Transparent tiers where they hide cost</p>}
              </div>
            </li>
            {!dense && (
              <li>
                <b>3</b>
                <div>
                  <strong>Share loop</strong>
                  <p>One-click PDF for sales calls</p>
                </div>
              </li>
            )}
          </ol>
        </section>
      </div>

      {!dense && (
        <div className="ex-work__grid">
          <article>
            <h4>Strengths</h4>
            <p>Brand trust · Fast support</p>
          </article>
          <article>
            <h4>Gaps</h4>
            <p>Weak self-serve · Opaque pricing</p>
          </article>
        </div>
      )}
    </div>
  );
}

function HireApp({ dense }: { dense?: boolean }) {
  const rows = [
    { name: 'Maya Chen', role: 'Ops lead', yrs: '6 yrs', score: 94, tag: 'Top', tone: 'hi' as const },
    { name: 'Jordan Lee', role: 'Recruiter', yrs: '4 yrs', score: 87, tag: 'Strong', tone: 'mid' as const },
    ...(!dense
      ? [{ name: 'Sam Ortiz', role: 'Coordinator', yrs: '3 yrs', score: 81, tag: 'Review', tone: 'lo' as const }]
      : []),
  ];

  return (
    <div className="ex-work">
      <div className="ex-work__insight">
        <span className="ex-work__insight-mark">AI</span>
        <p>Maya leads on ops systems + stakeholder comms — interview first.</p>
      </div>

      <div className="ex-work__toolbar">
        <div>
          <strong className="ex-work__title">Senior operations</strong>
          <p className="ex-work__muted">42 CVs scored · AI ranked</p>
        </div>
        <div className="ex-work__filters">
          <span className="ex-work__chip ex-work__chip--on">All</span>
          <span className="ex-work__chip">90+</span>
          <span className="ex-work__chip">Shortlist</span>
        </div>
      </div>

      <div className="ex-work__table">
        <div className="ex-work__thead">
          <span>Candidate</span>
          <span>Role</span>
          <span>Match</span>
          <span />
        </div>
        {rows.map((r) => (
          <div key={r.name} className="ex-work__row">
            <div className="ex-work__person">
              <span className={`ex-app__av ex-app__av--sm ex-app__av--${r.tone}`} />
              <div>
                <b>{r.name}</b>
                <i>{r.yrs}</i>
              </div>
            </div>
            <span className="ex-work__cell">{r.role}</span>
            <div className="ex-work__match">
              <strong className={r.score >= 90 ? 'ex-work__score--hi' : ''}>{r.score}</strong>
              <span className="ex-work__bar" style={{ ['--p' as string]: `${r.score}%` }} />
            </div>
            <span className={`ex-work__chip ${r.tone === 'hi' ? 'ex-work__chip--on' : ''}`}>{r.tag}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function CashApp({ dense }: { dense?: boolean }) {
  const days = dense
    ? [
        { d: 'Mon', h: 42 },
        { d: 'Tue', h: 68 },
        { d: 'Wed', h: 50 },
        { d: 'Thu', h: 82 },
        { d: 'Fri', h: 58 },
        { d: 'Sat', h: 74 },
        { d: 'Sun', h: 46 },
      ]
    : [
        { d: 'Mon', h: 42 },
        { d: 'Tue', h: 68 },
        { d: 'Wed', h: 50 },
        { d: 'Thu', h: 82 },
        { d: 'Fri', h: 58 },
        { d: 'Sat', h: 74 },
        { d: 'Sun', h: 92 },
        { d: 'Mon', h: 64 },
      ];

  const txns = [
    { name: 'Notion · Team', cat: 'Software', amt: '−$96', when: 'Today' },
    { name: 'Delta · NYC', cat: 'Travel', amt: '−$418', when: 'Yesterday' },
    ...(!dense ? [{ name: 'AWS · Compute', cat: 'Ops', amt: '−$1,240', when: 'Mar 12' }] : []),
  ];

  return (
    <div className="ex-work">
      <div className="ex-work__insight">
        <span className="ex-work__insight-mark">AI</span>
        <p>Software is 39% of spend — 3 unused seats flagged for cancel.</p>
      </div>

      <div className="ex-work__toolbar">
        <div>
          <p className="ex-work__muted">This month · Operating spend</p>
          <strong className="ex-work__money">$12,420</strong>
        </div>
        <div className="ex-work__chip ex-work__chip--ok">↓ 8% vs last month</div>
      </div>

      <div className="ex-work__chart">
        <div className="ex-work__bars" aria-hidden>
          {days.map((b, i) => (
            <span key={`${b.d}-${i}`} style={{ height: `${b.h}%` }} className={b.h >= 80 ? 'is-peak' : undefined} />
          ))}
        </div>
        <div className="ex-work__axis" aria-hidden>
          {days.map((b, i) => (
            <em key={`${b.d}-l-${i}`}>{b.d}</em>
          ))}
        </div>
      </div>

      <ul className="ex-work__txns">
        {txns.map((t) => (
          <li key={t.name}>
            <span className="ex-work__txn-ico" />
            <div>
              <b>{t.name}</b>
              <i>
                {t.cat} · {t.when}
              </i>
            </div>
            <strong>{t.amt}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ClinicApp({ dense }: { dense?: boolean }) {
  return (
    <div className="ex-work">
      <div className="ex-work__toolbar">
        <div>
          <strong className="ex-work__title">WhatsApp inbox</strong>
          <p className="ex-work__muted">3 open · AI drafting</p>
        </div>
        <div className="ex-work__chip">Tue · 3:30 open</div>
      </div>
      <div className="ex-work__chat">
        <div className="ex-work__bubble ex-work__bubble--bot">Hi — I can book your consult.</div>
        <div className="ex-work__bubble ex-work__bubble--user">Tuesday afternoon?</div>
        {!dense && <div className="ex-work__bubble ex-work__bubble--bot">Tue 3:30 is open. Confirm?</div>}
      </div>
      <div className="ex-work__actions">
        <span className="ex-app__btn ex-app__btn--ghost">Suggest times</span>
        <span className="ex-app__btn">Hold slot</span>
      </div>
    </div>
  );
}

function SalesApp({ dense }: { dense?: boolean }) {
  const stages = [
    { label: 'Leads', n: 128 },
    { label: 'Sent', n: 86 },
    { label: 'Replied', n: 24 },
    { label: 'Booked', n: dense ? 7 : 9 },
  ];
  return (
    <div className="ex-work">
      <div className="ex-work__toolbar">
        <div>
          <strong className="ex-work__title">Outbound · Mid-market</strong>
          <p className="ex-work__muted">Campaign live</p>
        </div>
        <div className="ex-work__chip ex-work__chip--ok">+12 booked</div>
      </div>
      <div className="ex-work__pipeline">
        {stages.map((s) => (
          <div key={s.label}>
            <em>{s.label}</em>
            <b>{s.n}</b>
          </div>
        ))}
      </div>
      {!dense && (
        <ul className="ex-work__kv">
          <li>
            <span>Next send</span>
            <b>14 leads · 11:00</b>
          </li>
          <li>
            <span>Reply rate</span>
            <b>28%</b>
          </li>
        </ul>
      )}
    </div>
  );
}

function MarketApp({ dense }: { dense?: boolean }) {
  const items = [
    { name: 'Coastal linen', price: '$98', match: '96%' },
    { name: 'Studio blazer', price: '$114', match: '91%' },
    ...(!dense ? [{ name: 'Weekend tote', price: '$64', match: '84%' }] : []),
  ];
  return (
    <div className="ex-work">
      <div className="ex-work__toolbar">
        <label className="ex-work__field ex-work__field--grow">
          <span>Search</span>
          <div className="ex-work__input">
            <em>“linen jacket under $120”</em>
            <b>Go</b>
          </div>
        </label>
      </div>
      <div className={`ex-work__shop ${dense ? '' : 'ex-work__shop--3'}`}>
        {items.map((p) => (
          <article key={p.name}>
            <span className="ex-work__swatch" />
            <b>{p.name}</b>
            <div>
              <i>{p.price}</i>
              <em>{p.match}</em>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
