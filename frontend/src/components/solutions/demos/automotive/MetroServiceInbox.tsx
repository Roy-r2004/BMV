import { useState } from 'react';
import { IconClose, IconSparkle, MetroLogo } from '../shared/ShowcaseChatIcons.tsx';
import {
  SERVICE_QUEUE,
  bayScoreLabel,
  preferredBayForService,
  type BookingSubmission,
  type ServiceRequest,
} from './metroData.ts';

const THREADS: Record<string, { role: 'user' | 'ai'; text: string; time?: string }[]> = {
  r1: [
    { role: 'user', text: 'Need synthetic oil change — waiting in the lounge if possible.', time: '2:11 PM' },
    { role: 'ai', text: 'Bay score 96 → Bay 2 (quick-service lift). Elena V. free after current drain. ETA 28 min. Status Bot will push each stage.', time: '2:11 PM' },
  ],
  r2: [
    { role: 'user', text: 'Check-engine on — code P0302 if that helps.', time: '1:58 PM' },
    { role: 'ai', text: 'Assigned Bay 4 diag station. Nina K. running live scan. Coil weakness flagged — upsell alert queued for staff.', time: '1:59 PM' },
  ],
  r3: [
    { role: 'user', text: 'Tire rotation + can you check wear?', time: '1:40 PM' },
    { role: 'ai', text: 'On Bay 1 alignment rack (55%). Uneven FL tread detected — Maintenance AI recommends 4-wheel alignment (+$129). Staff notified.', time: '2:05 PM' },
  ],
};

interface Props {
  submittedBooking: BookingSubmission | null;
  onClearBooking: () => void;
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="mt-inbox__score">
      <div className="mt-inbox__score-head">
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <div className="mt-inbox__score-track">
        <span style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

export default function MetroServiceInbox({ submittedBooking, onClearBooking }: Props) {
  const [active, setActive] = useState('r1');
  const [filter, setFilter] = useState<'all' | 'new' | 'in-bay'>('all');
  const [input, setInput] = useState('');

  const filtered = SERVICE_QUEUE.filter((r) => {
    if (filter === 'all') return true;
    if (filter === 'new') return r.status === 'new';
    return r.status === 'in-bay';
  });

  const req = SERVICE_QUEUE.find((r) => r.id === active)!;
  const messages = THREADS[active] || [];

  const sendNote = () => {
    if (!input.trim()) return;
    setInput('');
  };

  return (
    <div className="mt-inbox">
      <aside className="mt-inbox__queue">
        <header className="mt-inbox__head">
          <div className="mt-inbox__brand">
            <MetroLogo className="mt-inbox__logo" />
            <div>
              <h2>Service inbox</h2>
              <span>{SERVICE_QUEUE.length} requests · bay AI</span>
            </div>
          </div>
          <span className="mt-inbox__ai-pill">
            <IconSparkle className="mt-inbox__sparkle" />
            Bay scheduler
          </span>
        </header>

        <div className="mt-inbox__strip">
          <span>Job type → lift</span>
          <span>Parts check</span>
          <span>Customer SMS</span>
        </div>

        {submittedBooking && (
          <div className="mt-inbox__alert">
            <MetroLogo className="mt-inbox__alert-logo" />
            <div>
              <strong>New booking from site</strong>
              <p>
                {submittedBooking.serviceId} · {submittedBooking.vehicle} · suggested Bay{' '}
                {preferredBayForService(submittedBooking.serviceId)}
              </p>
            </div>
            <button type="button" onClick={onClearBooking} aria-label="Dismiss">
              <IconClose className="mt-inbox__icon" />
            </button>
          </div>
        )}

        <div className="mt-inbox__filters">
          {(['all', 'new', 'in-bay'] as const).map((f) => (
            <button
              key={f}
              type="button"
              className={filter === f ? 'mt-inbox__filter mt-inbox__filter--on' : 'mt-inbox__filter'}
              onClick={() => setFilter(f)}
            >
              {f === 'all' ? 'All' : f === 'new' ? 'New' : 'In bay'}
            </button>
          ))}
        </div>

        <ul className="mt-inbox__list">
          {filtered.map((r: ServiceRequest) => (
            <li key={r.id}>
              <button
                type="button"
                className={active === r.id ? 'mt-inbox__item mt-inbox__item--on' : 'mt-inbox__item'}
                onClick={() => setActive(r.id)}
              >
                <div className="mt-inbox__item-top">
                  <strong>{r.customer}</strong>
                  <span>{r.time}</span>
                </div>
                <p>{r.preview}</p>
                <div className="mt-inbox__item-meta">
                  <span className="mt-inbox__svc-pill">{r.service}</span>
                  <span className="mt-inbox__score-pill">{bayScoreLabel(r.bayScore)} · Bay {r.suggestedBay}</span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="mt-inbox__detail">
        <header className="mt-inbox__detail-head">
          <div>
            <h3>{req.customer}</h3>
            <p>{req.vehicle} · {req.plate} · {req.mileage}</p>
          </div>
          <span className={`mt-inbox__status mt-inbox__status--${req.status}`}>{req.status.replace('-', ' ')}</span>
        </header>

        <div className="mt-inbox__scores">
          <ScoreBar label="Bay fit score" value={req.bayScore} />
          <div className="mt-inbox__bay-rec">
            <span>Suggested lift</span>
            <strong>Bay {req.suggestedBay}</strong>
          </div>
        </div>

        <div className="mt-inbox__dispatch-card">
          <IconSparkle className="mt-inbox__sparkle" />
          <div>
            <strong>Bay assignment AI</strong>
            <p>
              {req.bayScore >= 90
                ? `Assign Bay ${req.suggestedBay} now — best lift match for ${req.service.toLowerCase()}.`
                : `Queue for Bay ${req.suggestedBay} when current job clears — score ${req.bayScore}.`}
            </p>
          </div>
          <button type="button" className="mt-inbox__dispatch-btn">Assign bay</button>
        </div>

        <div className="mt-inbox__thread">
          {messages.map((msg, i) => (
            <div key={i} className={`mt-inbox__msg mt-inbox__msg--${msg.role}`}>
              {msg.role === 'ai' && (
                <span className="mt-inbox__ai-label">
                  <IconSparkle className="mt-inbox__sparkle" />
                  Bay AI
                </span>
              )}
              <p>{msg.text}</p>
              {msg.time && <time>{msg.time}</time>}
            </div>
          ))}
        </div>

        <footer className="mt-inbox__composer">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Override bay or add tech note…"
            onKeyDown={(e) => e.key === 'Enter' && sendNote()}
          />
          <button type="button" onClick={sendNote}>Send</button>
        </footer>
      </main>
    </div>
  );
}
