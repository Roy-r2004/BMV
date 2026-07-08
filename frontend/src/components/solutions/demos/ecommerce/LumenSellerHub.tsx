import { useEffect, useState } from 'react';
import { LumenLogo, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import {
  CATEGORIES,
  CHANNELS,
  ORDERS_TO_SHIP,
  PRODUCTS,
  PROMO_RULES,
  REV_SPARK,
  SELLER_ACTIVITY,
  STORE,
  STYLE_BUNDLES,
  TOP_CUSTOMERS,
  TOP_QUERIES,
  categoryCounts,
  filterCatalog,
  getProduct,
  lowStockProducts,
  type Product,
  type ProductCategory,
} from './lumenData.ts';
import { onLumenImageError } from './lumenImageFallback.ts';

type HubPage =
  | 'overview'
  | 'inventory'
  | 'catalog'
  | 'orders'
  | 'pricing'
  | 'insights'
  | 'channels'
  | 'customers';

const NAV: { id: HubPage; label: string; sub: string }[] = [
  { id: 'overview', label: 'Overview', sub: 'Activity & alerts' },
  { id: 'inventory', label: 'Inventory', sub: 'Stock & reorder' },
  { id: 'catalog', label: 'Catalog', sub: 'Categories & bundles' },
  { id: 'orders', label: 'Orders', sub: 'Ship queue' },
  { id: 'pricing', label: 'Pricing & promos', sub: 'Rules & flash sales' },
  { id: 'insights', label: 'Insights', sub: 'Search & conversion' },
  { id: 'channels', label: 'Channels', sub: 'Site · IG · Email' },
  { id: 'customers', label: 'Customers', sub: 'Top buyers & LTV' },
];

const METRICS = [
  { label: 'Revenue today', value: '$4.2k', sub: '+18% vs last Tue', accent: true },
  { label: 'Orders to ship', value: '5', sub: '2 priority' },
  { label: 'Low stock SKUs', value: '3', sub: 'Reorder suggested' },
  { label: 'AI search conv.', value: '68%', sub: 'Find rate' },
];

const PAGE_TITLES: Record<HubPage, { title: string; sub: string }> = {
  overview: { title: 'Seller overview', sub: 'Tuesday · live commerce pulse' },
  inventory: { title: 'Inventory grid', sub: 'Stock alerts live' },
  catalog: { title: 'Catalog structure', sub: 'Categories, SKUs & style bundles' },
  orders: { title: 'Orders to ship', sub: 'Fulfillment priority queue' },
  pricing: { title: 'Pricing & promos', sub: 'Flash sales, shipping & bundles' },
  insights: { title: 'Shopper insights', sub: 'NL queries, vision share & conversion' },
  channels: { title: 'Sales channels', sub: 'Where Lumen shows up' },
  customers: { title: 'Customers', sub: 'Top buyers · lifetime value' },
};

function StockBadge({ product }: { product: Product }) {
  if (product.stock <= 5) {
    return <span className="lh-seller__alert lh-seller__alert--critical">Critical · {product.stock} left</span>;
  }
  if (product.lowStock || product.stock <= 10) {
    return <span className="lh-seller__alert lh-seller__alert--low">Low stock · {product.stock}</span>;
  }
  return <span className="lh-seller__alert lh-seller__alert--ok">{product.stock} in stock</span>;
}

export default function LumenSellerHub() {
  const [page, setPage] = useState<HubPage>('overview');
  const [alertPulse, setAlertPulse] = useState(false);
  const [invCategory, setInvCategory] = useState<ProductCategory | 'all'>('all');
  const [channelState, setChannelState] = useState(() => Object.fromEntries(CHANNELS.map((c) => [c.id, c.enabled])));
  const [promoState, setPromoState] = useState(() =>
    Object.fromEntries(PROMO_RULES.map((p) => [p.id, p.status !== 'paused'])),
  );
  const lowStock = lowStockProducts();
  const counts = categoryCounts();
  const inventoryList = invCategory === 'all' ? PRODUCTS : filterCatalog({ category: invCategory });

  useEffect(() => {
    const t = window.setInterval(() => setAlertPulse((p) => !p), 2000);
    return () => window.clearInterval(t);
  }, []);

  const head = PAGE_TITLES[page];

  return (
    <div className="lh-seller">
      <aside className="lh-seller__nav">
        <div className="lh-seller__brand">
          <LumenLogo className="lh-seller__brand-logo" />
          <div>
            <strong>Lumen Seller</strong>
            <span>Commerce OS</span>
          </div>
        </div>
        <nav aria-label="Seller navigation">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={page === item.id ? 'lh-seller__nav-btn lh-seller__nav-btn--on' : 'lh-seller__nav-btn'}
              onClick={() => setPage(item.id)}
            >
              <span className="lh-seller__nav-label">{item.label}</span>
              <span className="lh-seller__nav-sub">{item.sub}</span>
            </button>
          ))}
        </nav>
        <div className={`lh-seller__alert-strip ${alertPulse ? 'lh-seller__alert-strip--pulse' : ''}`}>
          <IconSparkle className="lh-seller__sparkle" />
          {lowStock.length} SKUs need reorder
        </div>
      </aside>

      <main className="lh-seller__main">
        <header className="lh-seller__head">
          <div>
            <p className="lh-seller__head-eyebrow">{STORE.name}</p>
            <h1>{head.title}</h1>
            <p>{head.sub}</p>
          </div>
          <span className="lh-seller__live">Live</span>
        </header>

        {(page === 'overview' || page === 'inventory' || page === 'orders') && (
          <div className="lh-seller__metrics">
            {METRICS.map((m) => (
              <article key={m.label} className={m.accent ? 'lh-seller__metric lh-seller__metric--accent' : 'lh-seller__metric'}>
                <strong>{m.value}</strong>
                <span>{m.label}</span>
                <small>{m.sub}</small>
              </article>
            ))}
          </div>
        )}

        {page === 'overview' && (
          <div className="lh-seller__overview">
            <div className="lh-seller__ai-banner">
              <div>
                <strong>Shopper AI drove 68% of finds to cart today</strong>
                <p>Vision search is 22% of sessions · Warm bedroom mood converts at 74% · textile flash sale lifting AOV</p>
              </div>
              <span>AI conversion</span>
            </div>

            <div className="lh-seller__overview-grid">
              <section className="lh-seller__panel">
                <div className="lh-seller__panel-head">
                  <h2>Revenue · 7 days</h2>
                  <span>+$840 vs prior</span>
                </div>
                <div className="lh-seller__spark">
                  {REV_SPARK.map((h, i) => (
                    <div key={i} className={`lh-seller__spark-bar ${i === REV_SPARK.length - 1 ? 'lh-seller__spark-bar--today' : ''}`}>
                      <span style={{ height: `${h}%` }} />
                      <em>{['W', 'T', 'F', 'S', 'S', 'M', 'T'][i]}</em>
                    </div>
                  ))}
                </div>
              </section>

              <section className="lh-seller__panel">
                <div className="lh-seller__panel-head">
                  <h2>Open alerts</h2>
                  <span>{lowStock.length} stock</span>
                </div>
                <ul className="lh-seller__alert-list">
                  {lowStock.map((p) => (
                    <li key={p.id}>
                      <img src={p.imageUrl} alt="" onError={(e) => onLumenImageError(e, p.name)} />
                      <div>
                        <strong>{p.name}</strong>
                        <StockBadge product={p} />
                      </div>
                      <button type="button" onClick={() => setPage('inventory')}>
                        Reorder
                      </button>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="lh-seller__panel lh-seller__panel--wide">
                <div className="lh-seller__panel-head">
                  <h2>Live activity</h2>
                  <span>Commerce feed</span>
                </div>
                <ul className="lh-seller__activity">
                  {SELLER_ACTIVITY.map((a) => (
                    <li key={a.text} className={`lh-seller__activity-item lh-seller__activity-item--${a.type}`}>
                      <span />
                      <div>
                        <strong>{a.text}</strong>
                        <p>{a.detail}</p>
                        <time>{a.time}</time>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          </div>
        )}

        {page === 'inventory' && (
          <div className="lh-seller__inventory">
            <header className="lh-seller__section-head">
              <h2>Product inventory</h2>
              <span>
                {inventoryList.length} SKUs · {lowStock.length} alerts
              </span>
            </header>
            <div className="lh-seller__inv-filters">
              <button
                type="button"
                className={invCategory === 'all' ? 'lh-seller__chip lh-seller__chip--on' : 'lh-seller__chip'}
                onClick={() => setInvCategory('all')}
              >
                All
              </button>
              {CATEGORIES.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={invCategory === c.id ? 'lh-seller__chip lh-seller__chip--on' : 'lh-seller__chip'}
                  onClick={() => setInvCategory(c.id)}
                >
                  {c.label}
                </button>
              ))}
            </div>
            <div className="lh-seller__grid">
              {inventoryList.map((p) => (
                <article key={p.id} className={p.lowStock ? 'lh-seller__sku lh-seller__sku--alert' : 'lh-seller__sku'}>
                  <img src={p.imageUrl} alt="" loading="lazy" onError={(e) => onLumenImageError(e, p.name)} />
                  <div className="lh-seller__sku-body">
                    <h3>{p.name}</h3>
                    <p>
                      {p.price} · {p.category} / {p.subcategory}
                    </p>
                    <StockBadge product={p} />
                  </div>
                  <button type="button" className="lh-seller__reorder">
                    Reorder
                  </button>
                </article>
              ))}
            </div>
          </div>
        )}

        {page === 'catalog' && (
          <div className="lh-seller__catalog">
            <section className="lh-seller__panel">
              <div className="lh-seller__panel-head">
                <h2>Category tree</h2>
                <span>{PRODUCTS.length} SKUs</span>
              </div>
              <ul className="lh-seller__cat-tree">
                {counts.map((cat) => (
                  <li key={cat.id}>
                    <div className="lh-seller__cat-tree-head">
                      <strong>{cat.label}</strong>
                      <span>{cat.count}</span>
                    </div>
                    <ul>
                      {cat.subs.map((sub) => (
                        <li key={sub.id}>
                          <span>{sub.label}</span>
                          <em>{sub.count}</em>
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </section>

            <section className="lh-seller__panel lh-seller__panel--wide">
              <div className="lh-seller__panel-head">
                <h2>Style bundles</h2>
                <span>{STYLE_BUNDLES.length} live</span>
              </div>
              <div className="lh-seller__bundle-list">
                {STYLE_BUNDLES.map((b) => (
                  <article key={b.id} className="lh-seller__bundle-card">
                    <img src={b.imageUrl} alt="" onError={onLumenImageError} />
                    <div>
                      <strong>{b.title}</strong>
                      <p>{b.subtitle}</p>
                      <ul>
                        {b.productIds.map((id) => {
                          const p = getProduct(id);
                          return p ? <li key={id}>{p.name}</li> : null;
                        })}
                      </ul>
                      <span className="lh-seller__bundle-save">{b.savings}</span>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </div>
        )}

        {page === 'orders' && (
          <div className="lh-seller__orders">
            <header className="lh-seller__section-head">
              <h2>Ship today</h2>
              <span>{ORDERS_TO_SHIP.filter((o) => o.status === 'to-ship').length} awaiting pack · priority first</span>
            </header>
            <ul className="lh-seller__order-list">
              {[...ORDERS_TO_SHIP]
                .sort((a, b) => Number(!!b.priority) - Number(!!a.priority))
                .map((o) => (
                  <li key={o.id} className={o.priority ? 'lh-seller__order lh-seller__order--priority' : 'lh-seller__order'}>
                    <div className="lh-seller__order-main">
                      <strong>{o.orderNum}</strong>
                      <span>{o.customer}</span>
                      <p>{o.items.join(' · ')}</p>
                    </div>
                    <div className="lh-seller__order-meta">
                      <strong>{o.total}</strong>
                      <span className={`lh-seller__order-status lh-seller__order-status--${o.status}`}>
                        {o.status === 'to-ship' ? 'To ship' : o.status === 'packed' ? 'Packed' : 'Shipped'}
                      </span>
                      {o.priority && <span className="lh-seller__priority">Priority</span>}
                    </div>
                    <button type="button">Print label</button>
                  </li>
                ))}
            </ul>
          </div>
        )}

        {page === 'pricing' && (
          <div className="lh-seller__pricing">
            <header className="lh-seller__section-head">
              <h2>Promotion rules</h2>
              <span>{PROMO_RULES.filter((p) => promoState[p.id]).length} active</span>
            </header>
            <ul className="lh-seller__promo-list">
              {PROMO_RULES.map((rule) => (
                <li key={rule.id} className="lh-seller__promo">
                  <div>
                    <strong>{rule.name}</strong>
                    <p>{rule.detail}</p>
                    <small>{rule.ends}</small>
                  </div>
                  <button
                    type="button"
                    className={`lh-seller__toggle ${promoState[rule.id] ? 'lh-seller__toggle--on' : ''}`}
                    aria-pressed={promoState[rule.id]}
                    onClick={() => setPromoState((s) => ({ ...s, [rule.id]: !s[rule.id] }))}
                  >
                    {promoState[rule.id] ? 'On' : 'Off'}
                  </button>
                </li>
              ))}
            </ul>
            <div className="lh-seller__promo-note">
              <IconSparkle className="lh-seller__sparkle" />
              Bundle discounts auto-apply at checkout when Shopper AI surfaces a style edit.
            </div>
          </div>
        )}

        {page === 'insights' && (
          <div className="lh-seller__insights">
            <div className="lh-seller__insight-cards">
              <article className="lh-seller__insight-card lh-seller__insight-card--accent">
                <strong>22%</strong>
                <span>Sessions via image search</span>
                <small>+6 pts vs last week</small>
              </article>
              <article className="lh-seller__insight-card">
                <strong>68%</strong>
                <span>NL find → cart rate</span>
                <small>Top query converts at 72%</small>
              </article>
              <article className="lh-seller__insight-card">
                <strong>$154</strong>
                <span>Vision-search AOV</span>
                <small>Vs $118 site average</small>
              </article>
            </div>
            <section className="lh-seller__panel">
              <div className="lh-seller__panel-head">
                <h2>Top natural-language queries</h2>
                <span>Last 7 days</span>
              </div>
              <ul className="lh-seller__query-list">
                {TOP_QUERIES.map((q) => (
                  <li key={q.query}>
                    <div>
                      <strong>&ldquo;{q.query}&rdquo;</strong>
                      <span>{q.count} searches</span>
                    </div>
                    <em>{q.conversion} conv.</em>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        )}

        {page === 'channels' && (
          <div className="lh-seller__channels">
            <header className="lh-seller__section-head">
              <h2>Connected channels</h2>
              <span>{Object.values(channelState).filter(Boolean).length} of {CHANNELS.length} live</span>
            </header>
            <ul className="lh-seller__channel-list">
              {CHANNELS.map((ch) => (
                <li key={ch.id} className="lh-seller__channel">
                  <div>
                    <strong>{ch.name}</strong>
                    <p>{ch.detail}</p>
                  </div>
                  <button
                    type="button"
                    className={`lh-seller__toggle ${channelState[ch.id] ? 'lh-seller__toggle--on' : ''}`}
                    aria-pressed={channelState[ch.id]}
                    onClick={() => setChannelState((s) => ({ ...s, [ch.id]: !s[ch.id] }))}
                  >
                    {channelState[ch.id] ? 'On' : 'Off'}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {page === 'customers' && (
          <div className="lh-seller__customers">
            <header className="lh-seller__section-head">
              <h2>Top buyers</h2>
              <span>LTV stubs · demo data</span>
            </header>
            <ul className="lh-seller__customer-list">
              {TOP_CUSTOMERS.map((c) => (
                <li key={c.name}>
                  <span className="lh-seller__customer-avatar">{c.name.charAt(0)}</span>
                  <div>
                    <strong>{c.name}</strong>
                    <small>
                      {c.orders} orders · {c.ltv} LTV
                    </small>
                  </div>
                  <span className={`lh-seller__pill ${c.tag === 'VIP' ? 'lh-seller__pill--vip' : ''}`}>{c.tag}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </main>
    </div>
  );
}
