import { useEffect, useState } from 'react';
import { BrightFixLogo, IconClose, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import {
  JOB_QUEUE,
  scoreLabel,
  urgencyColor,
  type QuoteSubmission,
  type JobRequest,
} from './brightfixData.ts';

const THREADS: Record<string, { role: 'user' | 'ai'; text: string; time?: string }[]> = {
  j1: [
    { role: 'user', text: 'Water spraying from under the kitchen sink — shutoff valve won\'t turn.', time: '2:14 PM' },
    { role: 'ai', text: 'Emergency flagged. 3 photos received — looks like supply line burst. Dispatch score 98. Routing Mike R. (12 min).', time: '2:14 PM' },
  ],
  j2: [
    { role: 'user', text: 'Kitchen sink backing up — tried plunger, still slow.', time: '2:02 PM' },
    { role: 'ai', text: 'Quoted $165–$220 for drain clear. Sara L. matches skill (88%). Confirm for today 4–6 PM?', time: '2:02 PM' },
  ],
  j3: [
    { role: 'user', text: 'No hot water since this morning. Heater is about 12 years old.', time: '1:48 PM' },
    { role: 'ai', text: 'Likely thermocouple or full unit. Ballpark $350–$1,800. Need photo of model plate for exact quote.', time: '1:48 PM' },
  ],
};

interface Props {
  submittedQuote: QuoteSubmission | null;
  onClearQuote: () => void;
}

function ScoreBar({ label, value, animKey }: { label: string; value: number; animKey: string }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    setDisplay(0);
    let frame = 0;
    const start = performance.now();
    const duration = 800;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - t) ** 3;
      setDisplay(Math.round(value * eased));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, animKey]);

  return (
    <div className="bf-inbox__score">
      <div className="bf-inbox__score-head">
        <span>{label}</span>
        <strong>{display}</strong>
      </div>
      <div className="bf-inbox__score-track">
        <span key={`${animKey}-${label}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

export default function BrightFixJobInbox({ submittedQuote, onClearQuote }: Props) {
  const [active, setActive] = useState('j1');
  const [filter, setFilter] = useState<'all' | 'emergency' | 'today'>('all');
  const [input, setInput] = useState('');
  const [scoreKey, setScoreKey] = useState(0);

  const filtered = JOB_QUEUE.filter((j) => {
    if (filter === 'all') return true;
    if (filter === 'emergency') return j.urgency === 'emergency';
    return j.urgency === 'today';
  });

  const job = JOB_QUEUE.find((j) => j.id === active)!;
  const messages = THREADS[active] || [];

  const selectJob = (id: string) => {
    setActive(id);
    setScoreKey((k) => k + 1);
  };

  const dispatch = () => {
    if (!input.trim()) return;
    setInput('');
  };

  return (
    <div className="bf-inbox">
      <aside className="bf-inbox__queue">
        <header className="bf-inbox__head">
          <div className="bf-inbox__brand">
            <BrightFixLogo className="bf-inbox__logo" />
            <div>
              <h2>Job inbox</h2>
              <span>{JOB_QUEUE.length} requests · AI scored</span>
            </div>
          </div>
          <span className="bf-inbox__ai-pill">
            <IconSparkle className="bf-inbox__sparkle" />
            Dispatch AI
          </span>
        </header>

        <div className="bf-inbox__strip">
          <span>Quote intake</span>
          <span>Skill match</span>
          <span>Auto route</span>
        </div>

        {submittedQuote && (
          <div className="bf-inbox__alert">
            <BrightFixLogo className="bf-inbox__alert-logo" />
            <div>
              <strong>New quote from site</strong>
              <p>
                {submittedQuote.jobTypeId} · {submittedQuote.urgency} · {submittedQuote.zoneId}
              </p>
            </div>
            <button type="button" onClick={onClearQuote} aria-label="Dismiss">
              <IconClose className="bf-inbox__icon" />
            </button>
          </div>
        )}

        <div className="bf-inbox__filters">
          {(['all', 'emergency', 'today'] as const).map((f) => (
            <button
              key={f}
              type="button"
              className={filter === f ? 'bf-inbox__filter bf-inbox__filter--on' : 'bf-inbox__filter'}
              onClick={() => setFilter(f)}
            >
              {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>

        <ul className="bf-inbox__list">
          {filtered.map((j: JobRequest) => (
            <li key={j.id}>
              <button
                type="button"
                className={active === j.id ? 'bf-inbox__item bf-inbox__item--on' : 'bf-inbox__item'}
                onClick={() => selectJob(j.id)}
              >
                <div className="bf-inbox__item-top">
                  <strong>{j.customer}</strong>
                  <span>{j.time}</span>
                </div>
                <p>{j.preview}</p>
                <div className="bf-inbox__item-meta">
                  <span className={`bf-inbox__urgency bf-inbox__urgency--${urgencyColor(j.urgency)}`}>{j.urgency}</span>
                  <span className="bf-inbox__score-pill">
                    {scoreLabel(j.dispatchScore)} · {j.dispatchScore}
                  </span>
                  {j.photos > 0 && <span className="bf-inbox__photos">{j.photos} photos</span>}
                </div>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="bf-inbox__detail">
        <header className="bf-inbox__detail-head">
          <div>
            <h3>{job.customer}</h3>
            <p>
              {job.address} · {job.zone}
            </p>
          </div>
          <span className={`bf-inbox__status bf-inbox__status--${job.status}`}>{job.status}</span>
        </header>

        <div className="bf-inbox__scores">
          <ScoreBar label="Dispatch score" value={job.dispatchScore} animKey={`${active}-${scoreKey}`} />
          <ScoreBar label="Skill match" value={job.skillMatch} animKey={`${active}-${scoreKey}`} />
        </div>

        <div className="bf-inbox__dispatch-card">
          <IconSparkle className="bf-inbox__sparkle" />
          <div>
            <strong>AI recommendation</strong>
            <p>
              {job.dispatchScore >= 90
                ? `Priority dispatch — route nearest ${job.jobType.toLowerCase()} tech immediately.`
                : `Queue for ${job.urgency === 'this-week' ? 'scheduled slot' : 'next available window'} — skill match ${job.skillMatch}%.`}
            </p>
          </div>
          <button type="button" className="bf-inbox__dispatch-btn">
            Auto dispatch
          </button>
        </div>

        <div className="bf-inbox__thread">
          {messages.map((msg, i) => (
            <div key={i} className={`bf-inbox__msg bf-inbox__msg--${msg.role}`}>
              {msg.role === 'ai' && (
                <span className="bf-inbox__ai-label">
                  <IconSparkle className="bf-inbox__sparkle" />
                  Quote AI
                </span>
              )}
              <p>{msg.text}</p>
              {msg.time && <time>{msg.time}</time>}
            </div>
          ))}
        </div>

        <footer className="bf-inbox__composer">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Override routing or add note…"
            onKeyDown={(e) => e.key === 'Enter' && dispatch()}
          />
          <button type="button" onClick={dispatch}>
            Send
          </button>
        </footer>
      </main>
    </div>
  );
}
