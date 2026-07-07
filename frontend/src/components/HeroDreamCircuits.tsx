/** Dreamy circuit traces — pure SVG/CSS, no WebGL */
export default function HeroDreamCircuits() {
  return (
    <div className="hero-dream-circuits" aria-hidden>
      <div className="hero-dream-orb hero-dream-orb--a" />
      <div className="hero-dream-orb hero-dream-orb--b" />
      <div className="hero-dream-orb hero-dream-orb--c" />

      <svg
        className="hero-dream-circuits__svg"
        viewBox="0 0 1440 900"
        preserveAspectRatio="xMidYMid slice"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient id="hero-circuit-stroke" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.15" />
            <stop offset="50%" stopColor="#60a5fa" stopOpacity="0.45" />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity="0.2" />
          </linearGradient>
          <radialGradient id="hero-node-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#67e8f9" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
          </radialGradient>
          <filter id="hero-circuit-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <g className="hero-dream-circuits__layer hero-dream-circuits__layer--drift">
          {/* Right cluster — near visual panel */}
          <path className="hero-circuit-path hero-circuit-path--flow" d="M920 120 H1100 V220 H980 V340 H1150" />
          <path className="hero-circuit-path hero-circuit-path--flow hero-circuit-path--delay-1" d="M1050 80 H1280 V180 H1120 V280 H1300 V420" />
          <path className="hero-circuit-path hero-circuit-path--flow hero-circuit-path--delay-2" d="M880 400 H1020 V520 H900 V640 H1080" />
          <rect className="hero-circuit-chip" x="1096" y="216" width="12" height="12" rx="2" />
          <rect className="hero-circuit-chip" x="896" y="516" width="10" height="10" rx="2" />
          <circle className="hero-circuit-node" cx="1100" cy="120" r="4" />
          <circle className="hero-circuit-node hero-circuit-node--delay-1" cx="1150" cy="340" r="3.5" />
          <circle className="hero-circuit-node hero-circuit-node--delay-2" cx="1080" cy="640" r="3" />

          {/* Top arc */}
          <path className="hero-circuit-path hero-circuit-path--flow hero-circuit-path--delay-3" d="M200 100 H420 V200 H320 V60 H600" />
          <path className="hero-circuit-path hero-circuit-path--dim" d="M600 60 H820 V160 H700 V260" />
          <circle className="hero-circuit-node hero-circuit-node--delay-3" cx="420" cy="100" r="3" />
          <circle className="hero-circuit-node" cx="700" cy="260" r="2.5" />

          {/* Bottom whisper */}
          <path className="hero-circuit-path hero-circuit-path--flow hero-circuit-path--delay-2" d="M120 620 H280 V720 H180 V800 H400" />
          <path className="hero-circuit-path hero-circuit-path--dim" d="M400 800 H560 V700 H480 V600 H640" />
          <circle className="hero-circuit-node hero-circuit-node--delay-1" cx="280" cy="620" r="3" />
        </g>

        {/* Floating particles */}
        <g className="hero-dream-circuits__layer hero-dream-circuits__layer--float">
          <circle className="hero-circuit-particle" cx="75%" cy="28%" r="2" />
          <circle className="hero-circuit-particle hero-circuit-particle--delay-1" cx="62%" cy="45%" r="1.5" />
          <circle className="hero-circuit-particle hero-circuit-particle--delay-2" cx="88%" cy="55%" r="2" />
          <circle className="hero-circuit-particle hero-circuit-particle--delay-3" cx="55%" cy="22%" r="1.5" />
          <circle className="hero-circuit-particle" cx="30%" cy="70%" r="1.5" />
        </g>
      </svg>
    </div>
  );
}
