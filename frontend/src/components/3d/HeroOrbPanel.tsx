export default function HeroOrbPanel() {
  return (
    <div className="hero-orb-panel">
      <div className="hero-orb-panel__glow" aria-hidden />
      <div className="hero-orb-panel__aurora" aria-hidden />
      <div className="hero-orb-panel__inner">
        <div className="hero-flow" aria-hidden>
          <div className="hero-flow__panel hero-flow__panel--ref">
            <span className="hero-flow__tag">Tool you like</span>
            <div className="hero-flow__screen hero-flow__screen--ref">
              <span className="hero-flow__bar hero-flow__bar--wide" />
              <span className="hero-flow__bar" />
              <span className="hero-flow__bar" />
              <span className="hero-flow__bar hero-flow__bar--short" />
            </div>
          </div>

          <div className="hero-flow__bridge" aria-hidden>
            <svg viewBox="0 0 80 48" className="hero-flow__svg">
              <path
                id="hero-flow-path-a"
                d="M4 24 C20 8, 28 8, 40 24 S60 40, 76 24"
                fill="none"
                stroke="url(#hero-flow-grad)"
                strokeWidth="2"
                strokeLinecap="round"
                opacity="0.5"
              />
              <defs>
                <linearGradient id="hero-flow-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#64748b" />
                  <stop offset="50%" stopColor="#38bdf8" />
                  <stop offset="100%" stopColor="#22d3ee" />
                </linearGradient>
              </defs>
              <circle r="3" fill="#67e8f9" className="hero-flow__dot hero-flow__dot--a">
                <animateMotion dur="2.2s" repeatCount="indefinite" path="M4 24 C20 8, 28 8, 40 24 S60 40, 76 24" />
              </circle>
            </svg>
          </div>

          <div className="hero-flow__panel hero-flow__panel--ai">
            <span className="hero-flow__tag">BMV AI</span>
            <div className="hero-flow__ai-core">
              <span className="hero-flow__ai-ring" />
              <span className="hero-flow__ai-gem" />
            </div>
          </div>

          <div className="hero-flow__bridge hero-flow__bridge--flip" aria-hidden>
            <svg viewBox="0 0 80 48" className="hero-flow__svg">
              <path
                d="M4 24 C20 40, 28 40, 40 24 S60 8, 76 24"
                fill="none"
                stroke="url(#hero-flow-grad-b)"
                strokeWidth="2"
                strokeLinecap="round"
                opacity="0.55"
              />
              <defs>
                <linearGradient id="hero-flow-grad-b" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#22d3ee" />
                  <stop offset="100%" stopColor="#2563eb" />
                </linearGradient>
              </defs>
              <circle r="3" fill="#38bdf8" className="hero-flow__dot hero-flow__dot--b">
                <animateMotion dur="2s" repeatCount="indefinite" begin="0.4s" path="M4 24 C20 40, 28 40, 40 24 S60 8, 76 24" />
              </circle>
            </svg>
          </div>

          <div className="hero-flow__panel hero-flow__panel--out">
            <span className="hero-flow__tag">Your version</span>
            <div className="hero-flow__screen hero-flow__screen--out">
              <span className="hero-flow__block hero-flow__block--hero" />
              <span className="hero-flow__block" />
              <span className="hero-flow__block hero-flow__block--accent" />
              <span className="hero-flow__block hero-flow__block--wide" />
            </div>
          </div>
        </div>
      </div>
      <div className="hero-orb-panel__caption">
        <span className="hero-orb-panel__dot" />
        Tool you like → AI adapts → Your business version
      </div>
    </div>
  );
}
