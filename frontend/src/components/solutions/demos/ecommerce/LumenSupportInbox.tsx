import { useEffect, useState } from 'react';
import { LumenLogo, IconClose, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import { SUPPORT_QUEUE, type PlacedOrder, type SupportTicket } from './lumenData.ts';

const LIVE_TICKER = [
  'Order #LM-48291 · tracking sent · out for delivery today',
  'Return label generated · James Ortiz · Halo lamp',
  'Exchange approved · Priya Shah · fog throw shipped free',
  'Replacement shipped · Alex Kim · vase damage resolved',
];

const THREAD = [
  { role: 'user' as const, text: 'Hi — where is order #LM-48291? It shipped Tuesday.', time: '2:41 PM' },
  { role: 'ai' as const, text: 'Found it ✓ UPS 1Z999…784 — out for delivery today by 6 PM to Portland. Tracking link emailed. Anything else?', time: '2:41 PM' },
  { role: 'user' as const, text: 'Perfect, thanks!', time: '2:42 PM' },
  { role: 'ai' as const, text: 'Marked resolved · CSAT prompt sent. Average handle time: 42 sec.', time: '2:42 PM' },
];

const TOPIC_LABEL: Record<SupportTicket['topic'], string> = {
  tracking: 'Tracking',
  return: 'Return',
  exchange: 'Exchange',
  damage: 'Damage',
  other: 'Other',
};

interface Props {
  placedOrder: PlacedOrder | null;
  onClearOrder: () => void;
}

export default function LumenSupportInbox({ placedOrder, onClearOrder }: Props) {
  const [active, setActive] = useState('0');
  const [filter, setFilter] = useState<'all' | 'open' | 'resolved'>('all');
  const [tickerIdx, setTickerIdx] = useState(0);
  const [aiTyping, setAiTyping] = useState(false);
  const [resolvedCount, setResolvedCount] = useState(12);

  useEffect(() => {
    const t = window.setInterval(() => setTickerIdx((i) => (i + 1) % LIVE_TICKER.length), 2800);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    const t = window.setInterval(() => setResolvedCount((c) => (c >= 14 ? 12 : c + 1)), 3500);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    setAiTyping(true);
    const t = window.setTimeout(() => setAiTyping(false), 900);
    return () => window.clearTimeout(t);
  }, [active]);

  const row = SUPPORT_QUEUE.find((q) => q.id === active)!;
  const filtered = SUPPORT_QUEUE.filter((q) => {
    if (filter === 'open') return q.status === 'open' || q.status === 'escalated';
    if (filter === 'resolved') return q.status === 'ai-resolved' || q.status === 'closed';
    return true;
  });

  return (
    <div className="lh-support">
      <header className="lh-support__head">
        <div className="lh-support__head-brand">
          <LumenLogo className="lh-support__logo" />
          <div>
            <h2>Order support queue</h2>
            <p>Order assistant AI · tracking · returns · exchanges</p>
          </div>
        </div>
        <div className="lh-support__head-stats">
          <article><strong>{SUPPORT_QUEUE.length}</strong><span>Open threads</span></article>
          <article><strong>{resolvedCount}</strong><span>AI resolved today</span></article>
          <article><strong>42s</strong><span>Avg handle time</span></article>
        </div>
        <span className="lh-support__ai-badge">
          <span className="lh-support__live-dot" aria-hidden />
          Order AI
        </span>
      </header>

      <div className="lh-support__ticker" aria-live="polite">
        <IconSparkle className="lh-support__sparkle" />
        <span>{LIVE_TICKER[tickerIdx]}</span>
      </div>

      {placedOrder && (
        <div className="lh-support__alert">
          <div>
            <strong>New order placed</strong>
            <p>{placedOrder.orderNum} · {placedOrder.items.join(', ')} · {placedOrder.total}</p>
          </div>
          <button type="button" onClick={onClearOrder} aria-label="Dismiss"><IconClose /></button>
        </div>
      )}

      <div className="lh-support__filters">
        {(['all', 'open', 'resolved'] as const).map((f) => (
          <button
            key={f}
            type="button"
            className={filter === f ? 'lh-support__filter lh-support__filter--on' : 'lh-support__filter'}
            onClick={() => setFilter(f)}
          >
            {f === 'all' ? 'All tickets' : f === 'open' ? 'Needs review' : 'AI resolved'}
          </button>
        ))}
      </div>

      <div className="lh-support__layout">
        <div className="lh-support__table-wrap">
          <table className="lh-support__table">
            <thead>
              <tr>
                <th>Order</th>
                <th>Customer</th>
                <th>Topic</th>
                <th>Status</th>
                <th>Order AI</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((q) => (
                <tr
                  key={q.id}
                  className={`${active === q.id ? 'lh-support__row--on' : ''} ${q.urgent ? 'lh-support__row--urgent' : ''}`}
                  onClick={() => setActive(q.id)}
                >
                  <td>
                    <strong>{q.orderNum}</strong>
                    <small>{q.time} ago</small>
                  </td>
                  <td>
                    <strong>{q.customer}</strong>
                    <small>{q.email}</small>
                  </td>
                  <td><span className="lh-support__topic">{TOPIC_LABEL[q.topic]}</span></td>
                  <td>
                    <span className={`lh-support__status lh-support__status--${q.status}`}>
                      {q.status === 'ai-resolved' ? 'AI resolved' : q.status === 'open' ? 'Open' : q.status}
                    </span>
                  </td>
                  <td>
                    <span className={`lh-support__pill lh-support__pill--${q.status === 'open' ? 'open' : 'done'}`}>
                      {q.aiResolution ?? q.preview}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <aside className="lh-support__detail">
          <header>
            <h3>{row.orderNum}</h3>
            <span>{row.customer} · {TOPIC_LABEL[row.topic]}</span>
          </header>

          <section className="lh-support__resolution">
            <h4>AI resolution</h4>
            <p>{row.aiResolution ?? 'Order assistant analyzing thread…'}</p>
            <div className="lh-support__resolution-meta">
              <span>Auto-reply enabled</span>
              <span>CSAT pending</span>
            </div>
          </section>

          <section className="lh-support__thread">
            <h4>
              <IconSparkle className="lh-support__sparkle" />
              Order assistant thread
            </h4>
            {active === '0'
              ? THREAD.map((m, i) => (
                  <div key={i} className={`lh-support__msg lh-support__msg--${m.role}`}>
                    <p>{m.text}</p>
                    <time>{m.time}</time>
                  </div>
                ))
              : (
                  <div className={`lh-support__msg lh-support__msg--ai`}>
                    <p>{row.preview}</p>
                    <time>{row.time} ago</time>
                  </div>
                )}
            {aiTyping && active === '0' && (
              <div className="lh-support__msg lh-support__msg--ai lh-support__msg--typing">
                <span className="lh-support__dots"><span /><span /><span /></span>
              </div>
            )}
          </section>

          <div className="lh-support__actions">
            <button type="button">Send tracking link</button>
            <button type="button" className="lh-support__actions--primary">Mark resolved</button>
          </div>
        </aside>
      </div>
    </div>
  );
}
