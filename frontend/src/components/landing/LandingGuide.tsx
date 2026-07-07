import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { scrollToId } from '../../utils/scroll';

const SECTIONS = [
  { id: 'hero', label: 'Top', tip: 'Welcome — scroll to see how our consultancy works.' },
  { id: 'consultancy', label: 'Consultancy', tip: 'Your free AI consultancy preview starts here.' },
  { id: 'how-it-works', label: 'Process', tip: 'Four steps from idea to build-ready concept.' },
  { id: 'examples', label: 'Examples', tip: 'Real outputs our AI generates for businesses.' },
  { id: 'use-cases', label: 'Use cases', tip: 'Booking apps, dashboards, portals — and more.' },
  { id: 'packages', label: 'Packages', tip: 'Start free. We build when you are ready.' },
  { id: 'faq', label: 'FAQ', tip: 'Common questions — tap any section to jump back.' },
  { id: 'get-started', label: 'Start', tip: 'Ready? Create your free preview now.' },
] as const;

function GuideBot({ active }: { active: boolean }) {
  return (
    <svg viewBox="0 0 64 72" className={`landing-guide__bot ${active ? 'landing-guide__bot--bounce' : ''}`} aria-hidden>
      <defs>
        <linearGradient id="guide-bot-body" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#1e3a8a" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>
        <linearGradient id="guide-bot-face" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="100%" stopColor="#22d3ee" />
        </linearGradient>
      </defs>
      <ellipse cx="32" cy="68" rx="14" ry="3" fill="#2563eb" opacity="0.2" />
      <rect x="14" y="18" width="36" height="38" rx="12" fill="url(#guide-bot-body)" stroke="#38bdf8" strokeWidth="1.5" opacity="0.9" />
      <rect x="22" y="26" width="20" height="16" rx="6" fill="url(#guide-bot-face)" />
      <circle cx="28" cy="34" r="2.5" fill="#0f172a" />
      <circle cx="36" cy="34" r="2.5" fill="#0f172a" />
      <path d="M27 40 Q32 43 37 40" stroke="#0f172a" strokeWidth="1.5" fill="none" strokeLinecap="round" />
      <rect x="8" y="30" width="6" height="16" rx="3" fill="#2563eb" />
      <rect x="50" y="30" width="6" height="16" rx="3" fill="#2563eb" />
      <circle cx="32" cy="12" r="5" fill="#22d3ee" className="landing-guide__antenna" />
      <line x1="32" y1="17" x2="32" y2="20" stroke="#67e8f9" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export default function LandingGuide() {
  const [activeId, setActiveId] = useState<string>('hero');
  const [menuOpen, setMenuOpen] = useState(false);
  const [bounce, setBounce] = useState(false);
  const [hidden, setHidden] = useState(false);

  const activeSection = useMemo(
    () => SECTIONS.find((s) => s.id === activeId) ?? SECTIONS[0],
    [activeId],
  );

  useEffect(() => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const narrow = window.matchMedia('(max-width: 1023px)').matches;
    setHidden(narrow);
    if (narrow) return;

    const elements = SECTIONS.map((s) => document.getElementById(s.id)).filter(Boolean) as HTMLElement[];
    if (!elements.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible[0]?.target.id) {
          setActiveId(visible[0].target.id);
          if (!reduced) {
            setBounce(true);
            window.setTimeout(() => setBounce(false), 600);
          }
        }
      },
      { rootMargin: '-20% 0px -55% 0px', threshold: [0.12, 0.35, 0.55] },
    );

    elements.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  if (hidden) return null;

  const jump = (id: string) => {
    scrollToId(id, 'smooth');
    setMenuOpen(false);
  };

  return (
    <aside className="landing-guide" aria-label="Page guide">
      <div
        className={`landing-guide__bubble ${
          menuOpen || activeId === 'hero' ? 'landing-guide__bubble--hidden' : ''
        }`}
      >
        <p className="landing-guide__bubble-label">{activeSection.label}</p>
        <p className="landing-guide__bubble-text">{activeSection.tip}</p>
      </div>

      <div className="landing-guide__panel">
        <button
          type="button"
          className="landing-guide__bot-btn"
          onClick={() => setMenuOpen((o) => !o)}
          aria-expanded={menuOpen}
          aria-label={menuOpen ? 'Close section menu' : 'Open section menu'}
        >
          <GuideBot active={bounce} />
        </button>

        <div className="landing-guide__dots" aria-hidden>
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              aria-label={`Go to ${s.label}`}
              onClick={() => jump(s.id)}
              className={`landing-guide__dot ${activeId === s.id ? 'landing-guide__dot--active' : ''}`}
            />
          ))}
        </div>
      </div>

      {menuOpen && (
        <div className="landing-guide__menu">
          <p className="landing-guide__menu-title">Jump to section</p>
          <ul>
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => jump(s.id)}
                  className={activeId === s.id ? 'landing-guide__menu-item--active' : ''}
                >
                  {s.label}
                </button>
              </li>
            ))}
          </ul>
          <Link to="/submit" className="landing-guide__menu-cta" onClick={() => setMenuOpen(false)}>
            Get free preview →
          </Link>
        </div>
      )}
    </aside>
  );
}
