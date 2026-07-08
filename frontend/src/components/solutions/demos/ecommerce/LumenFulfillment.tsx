import { useEffect, useState } from 'react';
import { LumenLogo, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import { SHIPMENTS, type Shipment } from './lumenData.ts';

const STAGES: { id: Shipment['stage']; label: string }[] = [
  { id: 'packed', label: 'Packed' },
  { id: 'shipped', label: 'Shipped' },
  { id: 'out-for-delivery', label: 'Out for delivery' },
  { id: 'delivered', label: 'Delivered' },
];

const STAGE_INDEX: Record<Shipment['stage'], number> = {
  packed: 0,
  shipped: 1,
  'out-for-delivery': 2,
  delivered: 3,
};

const LIVE_UPDATES = [
  'UPS scan · #LM-48291 · out for delivery · Portland',
  'Label printed · #LM-48156 · warm bedroom bundle',
  'Delivered · #LM-48012 · Denver · signed by customer',
];

interface Props {
  highlightOrder?: string;
}

function StageTrack({ shipment }: { shipment: Shipment }) {
  const current = STAGE_INDEX[shipment.stage];
  return (
    <ol className="lh-fulfill__track" aria-label={`Tracking stages for ${shipment.orderNum}`}>
      {STAGES.map((s, i) => (
        <li
          key={s.id}
          className={
            i < current
              ? 'lh-fulfill__track-step lh-fulfill__track-step--done'
              : i === current
                ? 'lh-fulfill__track-step lh-fulfill__track-step--active'
                : 'lh-fulfill__track-step'
          }
        >
          <span className="lh-fulfill__track-dot" aria-hidden />
          <span className="lh-fulfill__track-label">{s.label}</span>
        </li>
      ))}
    </ol>
  );
}

export default function LumenFulfillment({ highlightOrder }: Props) {
  const [filter, setFilter] = useState<'all' | Shipment['stage']>('all');
  const [tickerIdx, setTickerIdx] = useState(0);
  const [liveCount, setLiveCount] = useState(3);

  useEffect(() => {
    const t = window.setInterval(() => setTickerIdx((i) => (i + 1) % LIVE_UPDATES.length), 2600);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    const t = window.setInterval(() => setLiveCount((c) => (c >= 5 ? 3 : c + 1)), 4000);
    return () => window.clearInterval(t);
  }, []);

  const filtered = SHIPMENTS.filter((s) => filter === 'all' || s.stage === filter);

  return (
    <div className="lh-fulfill">
      <header className="lh-fulfill__head">
        <div className="lh-fulfill__head-brand">
          <LumenLogo className="lh-fulfill__logo" />
          <div>
            <h2>Shipment board</h2>
            <p>Live tracking stages · packed → shipped → delivered</p>
          </div>
        </div>
        <div className="lh-fulfill__head-stats">
          <article><strong>{liveCount}</strong><span>In transit</span></article>
          <article><strong>1</strong><span>Packed today</span></article>
          <article><strong>12</strong><span>Delivered this week</span></article>
        </div>
        <span className="lh-fulfill__live">Live</span>
      </header>

      <div className="lh-fulfill__ticker" aria-live="polite">
        <IconSparkle className="lh-fulfill__sparkle" />
        <span>{LIVE_UPDATES[tickerIdx]}</span>
      </div>

      <div className="lh-fulfill__filters">
        <button
          type="button"
          className={filter === 'all' ? 'lh-fulfill__filter lh-fulfill__filter--on' : 'lh-fulfill__filter'}
          onClick={() => setFilter('all')}
        >
          All shipments
        </button>
        {STAGES.map((s) => (
          <button
            key={s.id}
            type="button"
            className={filter === s.id ? 'lh-fulfill__filter lh-fulfill__filter--on' : 'lh-fulfill__filter'}
            onClick={() => setFilter(s.id)}
          >
            {s.label}
          </button>
        ))}
      </div>

      <div className="lh-fulfill__board">
        {filtered.map((s) => (
          <article
            key={s.id}
            className={`lh-fulfill__card ${highlightOrder && s.orderNum === highlightOrder ? 'lh-fulfill__card--highlight' : ''}`}
          >
            <header className="lh-fulfill__card-head">
              <div>
                <strong>{s.orderNum}</strong>
                <span>{s.customer}</span>
              </div>
              <span className={`lh-fulfill__stage lh-fulfill__stage--${s.stage}`}>
                {STAGES.find((st) => st.id === s.stage)?.label}
              </span>
            </header>

            <StageTrack shipment={s} />

            <ul className="lh-fulfill__items">
              {s.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>

            <footer className="lh-fulfill__card-foot">
              <div>
                <small>{s.carrier}</small>
                <code>{s.tracking}</code>
              </div>
              <div>
                <small>{s.city}</small>
                <strong>{s.eta}</strong>
              </div>
            </footer>
          </article>
        ))}
      </div>
    </div>
  );
}
