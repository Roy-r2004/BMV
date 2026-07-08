import { useMemo, useState } from 'react';
import { EmberLogo } from '../shared/ShowcaseChatIcons.tsx';
import { KITCHEN_QUEUE, MENU_SECTIONS, RESTAURANT, type KitchenOrder } from './emberData.ts';
import { onEmberImageError } from './emberImageFallback.ts';

type HubPage = 'orders' | 'menu' | 'covers' | 'connect';

const METRICS = [
  { label: 'Direct revenue', value: '$2.4k', sub: 'Today — no platform fees', accent: true },
  { label: 'Orders in queue', value: '12', sub: '3 firing now' },
  { label: 'Covers tonight', value: '34', sub: '6 arriving next hour' },
  { label: 'Avg ticket', value: '$38', sub: '+$6 vs last week' },
];

const NAV: { id: HubPage; label: string; sub: string }[] = [
  { id: 'orders', label: 'Live orders', sub: 'Kitchen queue' },
  { id: 'menu', label: 'Menu', sub: '86 & pricing' },
  { id: 'covers', label: 'Covers', sub: 'Tonight\'s flow' },
  { id: 'connect', label: 'Connect', sub: 'Integrations' },
];

const PAGE_TITLE: Record<HubPage, string> = {
  orders: 'Kitchen dashboard',
  menu: 'Menu manager',
  covers: 'Tonight\'s covers',
  connect: 'Connections',
};

const KANBAN: { status: KitchenOrder['status']; label: string; hint: string }[] = [
  { status: 'new', label: 'New', hint: 'Fire to line' },
  { status: 'cooking', label: 'Cooking', hint: 'On the pass' },
  { status: 'ready', label: 'Ready', hint: 'Pickup / run' },
  { status: 'served', label: 'Served', hint: 'Closed' },
];

const UPCOMING = [
  { time: '7:00 PM', party: 'Anderson · 6', zone: 'Main' },
  { time: '7:30 PM', party: 'Lee · 2', zone: 'Bar' },
  { time: '7:45 PM', party: 'Birthday · 8', zone: 'Patio', hot: true },
];

const CONNECT = [
  { name: 'POS sync', detail: 'Toast · tickets auto-fire', on: true },
  { name: 'Delivery zones', detail: '2.5 mi radius live', on: true },
  { name: 'Instagram orders', detail: 'DM → kitchen queue', on: true },
  { name: 'Reminder SMS', detail: 'Reservation nudges', on: true },
];

const TYPE_LABEL: Record<KitchenOrder['type'], string> = {
  'dine-in': 'Dine-in',
  pickup: 'Pickup',
  delivery: 'Delivery',
};

export default function EmberKitchenOps() {
  const [page, setPage] = useState<HubPage>('orders');

  const queueByStatus = useMemo(() => {
    const map: Record<KitchenOrder['status'], KitchenOrder[]> = {
      new: [],
      cooking: [],
      ready: [],
      served: [],
    };
    KITCHEN_QUEUE.forEach((order) => map[order.status].push(order));
    return map;
  }, []);

  return (
    <div className="eo-kitchen">
      <aside className="eo-kitchen__nav">
        <div className="eo-kitchen__brand">
          <EmberLogo className="eo-kitchen__brand-logo" />
          <div>
            <strong>Ember Ops</strong>
            <span>Kitchen & floor</span>
          </div>
        </div>
        <nav aria-label="Ops navigation">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={page === item.id ? 'eo-kitchen__nav-btn eo-kitchen__nav-btn--on' : 'eo-kitchen__nav-btn'}
              onClick={() => setPage(item.id)}
            >
              <span className="eo-kitchen__nav-label">{item.label}</span>
              <span className="eo-kitchen__nav-sub">{item.sub}</span>
            </button>
          ))}
        </nav>
        <div className="eo-kitchen__nav-foot">
          <span className="eo-kitchen__nav-live" />
          Saturday service live
        </div>
      </aside>

      <main className="eo-kitchen__main">
        <div className="eo-kitchen__hero-strip">
          <img src={RESTAURANT.kitchenImage} alt="" onError={onEmberImageError} />
          <div className="eo-kitchen__hero-shade" aria-hidden />
          <div className="eo-kitchen__hero-grain" aria-hidden />
          <div className="eo-kitchen__hero-copy">
            <p>Saturday service</p>
            <strong>Pass is hot — 3 tickets firing</strong>
          </div>
        </div>

        <header className="eo-kitchen__head">
          <div>
            <p className="eo-kitchen__head-eyebrow">{RESTAURANT.name}</p>
            <h1>{PAGE_TITLE[page]}</h1>
            <p>Saturday · 6:52 PM · 34 covers booked</p>
          </div>
          <span className="eo-kitchen__live">Live</span>
        </header>

        <div className="eo-kitchen__metrics">
          {METRICS.map((m) => (
            <article key={m.label} className={m.accent ? 'eo-kitchen__metric eo-kitchen__metric--accent' : 'eo-kitchen__metric'}>
              <p>{m.label}</p>
              <strong>{m.value}</strong>
              <span>{m.sub}</span>
            </article>
          ))}
        </div>

        {page === 'orders' && (
          <div className="eo-kitchen__ai-banner">
            <div>
              <strong>Menu AI converted 2 allergy questions into $480 covers</strong>
              <p>GF flagged · patio party synced · guests feel cared for → tip + return</p>
            </div>
            <span className="eo-kitchen__ai-banner-tag">Guest magnet</span>
          </div>
        )}

        <div key={page} className={`eo-kitchen__page eo-kitchen__page--${page}`}>
          {page === 'orders' && (
            <section className="eo-kitchen__queue">
              <header className="eo-kitchen__queue-head">
                <div>
                  <h2>Order queue</h2>
                  <p>Kitchen line · new → cooking → ready → served</p>
                </div>
                <button type="button" className="eo-kitchen__queue-add">+ Manual ticket</button>
              </header>
              <div className="eo-kitchen__kanban">
                {KANBAN.map((col) => (
                  <div key={col.status} className={`eo-kitchen__column eo-kitchen__column--${col.status}`}>
                    <header>
                      <strong>{col.label}</strong>
                      <span>{queueByStatus[col.status].length}</span>
                      <small>{col.hint}</small>
                    </header>
                    <div className="eo-kitchen__column-body">
                      {queueByStatus[col.status].map((order) => (
                        <article key={order.id} className={`eo-kitchen__ticket eo-kitchen__ticket--${order.status}`}>
                          <header>
                            <strong>#{order.id}</strong>
                            <span className={`eo-kitchen__ticket-type eo-kitchen__ticket-type--${order.type}`}>
                              {TYPE_LABEL[order.type]}
                            </span>
                            <time>{order.time}</time>
                          </header>
                          <p className="eo-kitchen__ticket-table">{order.table}</p>
                          <ul>
                            {order.items.map((item) => <li key={item}>{item}</li>)}
                          </ul>
                          <footer>
                            <span className={`eo-kitchen__status eo-kitchen__status--${order.status}`}>{order.status}</span>
                            {order.status === 'new' && <button type="button">Fire</button>}
                            {order.status === 'cooking' && <button type="button">Ready</button>}
                            {order.status === 'ready' && <button type="button">Picked up</button>}
                          </footer>
                        </article>
                      ))}
                      {queueByStatus[col.status].length === 0 && (
                        <p className="eo-kitchen__column-empty">Clear</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {page === 'menu' && (
            <section className="eo-kitchen__menu-mgr">
              <header className="eo-kitchen__menu-head">
                <h2>Live menu board</h2>
                <p>86 items in one tap — pricing syncs to guest site</p>
              </header>
              {MENU_SECTIONS.map((section) => (
                <div key={section.id} className="eo-kitchen__menu-group">
                  <h3>{section.title}</h3>
                  <div className="eo-kitchen__menu-grid">
                    {section.items.map((item) => (
                      <article key={item.id} className="eo-kitchen__menu-card">
                        <div className="eo-kitchen__menu-card-media">
                          <img src={item.imageUrl} alt={item.name} onError={(e) => onEmberImageError(e, item.name)} />
                          {item.tag && <span className="eo-kitchen__menu-tag">{item.tag}</span>}
                        </div>
                        <div className="eo-kitchen__menu-card-body">
                          <strong>{item.name}</strong>
                          <span>{item.price}</span>
                          <p>{item.desc}</p>
                          <button type="button">86&apos;d</button>
                        </div>
                      </article>
                    ))}
                  </div>
                </div>
              ))}
            </section>
          )}

          {page === 'covers' && (
            <section className="eo-kitchen__covers">
              <div className="eo-kitchen__covers-layout">
                <div className="eo-kitchen__covers-panel">
                  <h3>Covers by hour</h3>
                  <div className="eo-kitchen__covers-chart">
                    <div className="eo-kitchen__bar" style={{ height: '72%' }}><span>6 PM</span><strong>22</strong></div>
                    <div className="eo-kitchen__bar eo-kitchen__bar--peak" style={{ height: '100%' }}><span>7 PM</span><strong>34</strong></div>
                    <div className="eo-kitchen__bar" style={{ height: '88%' }}><span>8 PM</span><strong>30</strong></div>
                    <div className="eo-kitchen__bar" style={{ height: '65%' }}><span>9 PM</span><strong>18</strong></div>
                  </div>
                  <p className="eo-kitchen__covers-note">Peak at 7:45 — patio party of 8 lands then.</p>
                </div>
                <aside className="eo-kitchen__covers-aside">
                  <h3>Arriving soon</h3>
                  <ul>
                    {UPCOMING.map((row) => (
                      <li key={row.time} className={row.hot ? 'eo-kitchen__covers-hot' : ''}>
                        <time>{row.time}</time>
                        <div>
                          <strong>{row.party}</strong>
                          <span>{row.zone}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </aside>
              </div>
            </section>
          )}

          {page === 'connect' && (
            <section className="eo-kitchen__connect">
              {CONNECT.map((item) => (
                <article key={item.name} className="eo-kitchen__connect-card">
                  <div>
                    <strong>{item.name}</strong>
                    <p>{item.detail}</p>
                  </div>
                  <span className="eo-kitchen__connect-on">{item.on ? 'Connected' : 'Setup'}</span>
                </article>
              ))}
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
