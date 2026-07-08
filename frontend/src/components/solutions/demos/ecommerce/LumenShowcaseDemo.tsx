import { lazy, Suspense, useCallback, useState } from 'react';
import '../../../../styles/ecommerce-demo.css';
import type { ShowcaseDemoProps } from '../showcaseRegistry';
import { useOverlayProduct } from '../../../../context/ShowcaseOverlayContext.tsx';
import { LumenLogo } from '../shared/ShowcaseChatIcons.tsx';
import type { PlacedOrder } from './lumenData.ts';
import LumenShopSite from './LumenShopSite.tsx';

const LumenSupportInbox = lazy(() => import('./LumenSupportInbox.tsx'));
const LumenFulfillment = lazy(() => import('./LumenFulfillment.tsx'));
const LumenSellerHub = lazy(() => import('./LumenSellerHub.tsx'));

export type LumenView = 'site' | 'inbox' | 'schedule' | 'admin';

const TABS: { id: LumenView; label: string; short: string; path: string; role: string; icon: string }[] = [
  { id: 'site', label: 'Storefront', short: 'Shop', path: 'lumenstore.app', role: 'Shopper AI — categories, NL + image search, style bundles, chat', icon: '◆' },
  { id: 'inbox', label: 'Support queue', short: 'Support', path: 'lumenstore.app/support', role: 'Order support queue — tracking, returns, AI resolution per ticket', icon: '◎' },
  { id: 'schedule', label: 'Fulfillment', short: 'Ship', path: 'lumenstore.app/ship', role: 'Shipment board — packed / shipped / delivered tracking stages', icon: '▦' },
  { id: 'admin', label: 'Seller hub', short: 'Seller', path: 'lumenstore.app/admin', role: 'Seller OS — overview, inventory, catalog, orders, promos, insights, channels, customers', icon: '◈' },
];

export default function LumenShowcaseDemo({ onRequestClick }: ShowcaseDemoProps) {
  const [view, setView] = useState<LumenView>('site');
  const [placedOrder, setPlacedOrder] = useState<PlacedOrder | null>(null);

  const goToView = useCallback((id: LumenView) => setView(id), []);

  const onOrderPlaced = useCallback((order: PlacedOrder) => {
    setPlacedOrder(order);
    setView('inbox');
  }, []);

  const tab = TABS.find((t) => t.id === view)!;
  const productLabel = useOverlayProduct('Lumen Store');

  return (
    <div className="sol-detail-demo__showcase sol-detail-demo__showcase--ecommerce">
      <div className="lh-frame-toolbar">
        <p className="sol-detail-demo__hint lh-frame-toolbar__hint">
          <span className="sol-detail-demo__hint-dot" aria-hidden />
          <strong>{tab.role}</strong>
        </p>
      </div>

      <div className="sol-detail-demo__experience lh-frame">
        <div className="lh-frame__accent" aria-hidden />
        <header className="lh-frame__head">
          <div className="lh-frame__brand">
            <span className="lh-frame__logo" aria-hidden>
              <LumenLogo className="lh-frame__logo-svg" />
            </span>
            <div>
              <p className="lh-frame__product">{productLabel}</p>
              <p className="lh-frame__tag">Commerce OS</p>
            </div>
          </div>
          <div className="lh-frame__url">
            {tab.path}
          </div>
          <span className="lh-frame__live">Live</span>
        </header>

        <nav className="lh-frame__tabs" aria-label="Demo views">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => goToView(t.id)}
              className={`lh-frame__tab ${view === t.id ? 'lh-frame__tab--on' : ''}`}
              title={t.role}
            >
              <span className="lh-frame__tab-icon" aria-hidden>{t.icon}</span>
              <span className="hidden sm:inline">{t.label}</span>
              <span className="sm:hidden">{t.short}</span>
            </button>
          ))}
        </nav>

        <div className="lh-frame__viewport">
          <div className="lh-frame__view">
            <Suspense fallback={<div className="lh-frame__loading" />}>
              {view === 'site' && <LumenShopSite onOrderPlaced={onOrderPlaced} />}
              {view === 'inbox' && (
                <LumenSupportInbox placedOrder={placedOrder} onClearOrder={() => setPlacedOrder(null)} />
              )}
              {view === 'schedule' && <LumenFulfillment highlightOrder={placedOrder?.orderNum} />}
              {view === 'admin' && <LumenSellerHub />}
            </Suspense>
          </div>
        </div>
      </div>

      <div className="sol-detail-demo__footer">
        <p className="sol-detail-demo__footer-copy">
          <strong>Try it:</strong> Browse categories → search by image or &quot;warm minimalist lamp&quot; → AI bundle → order lands in support → seller hub pages.
        </p>
        <button type="button" onClick={onRequestClick} className="sol-detail-demo__footer-cta">
          Get this for my store
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
