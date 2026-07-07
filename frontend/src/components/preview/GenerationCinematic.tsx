import { useEffect, useState, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { API_BASE } from '../../api/client';

/* ─── Types ─────────────────────────────────────────────────────────── */
interface ProgressSnapshot {
  stage: string;
  label: string;
  pct: number;
  detail: string;
  files_done: number;
  files_total: number;
  log: Array<{ t: number; msg: string }>;
}

interface Props {
  requestId?: number;
  businessName?: string;
  compact?: boolean;
  title?: string;
}

/* ─── Stage → step index ─────────────────────────────────────────────── */
const STAGE_TO_STEP: Record<string, number> = {
  starting: 0, analyze: 0,
  blueprint: 1, demo: 1,
  codegen: 2, architect: 2,
  critic: 3,
  build: 4, build_done: 4, build_failed: 4, tech: 4, proposal: 4, done: 5,
};

/* ─── SVG icon paths (Heroicons 24 outline, viewBox 0 0 24 24) ────────── */
const ICON_PATHS: Record<string, string> = {
  building:
    'M2.25 21h19.5M9 6.75h.008v.008H9V6.75zm0 3h.008v.008H9V9.75zm0 3h.008v.008H9v-.008zm6-6h.008v.008h-.008V6.75zm0 3h.008v.008h-.008V9.75zm0 3h.008v.008h-.008v-.008zM4.5 21V6.375a2.625 2.625 0 0 1 2.625-2.625h9.75A2.625 2.625 0 0 1 19.5 6.375V21',
  document:
    'M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z',
  lightning:
    'M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z',
  sparkles:
    'M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z',
  cog:
    'M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7 7 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.281Z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  chart:
    'M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z',
  check:
    'M4.5 12.75l6 6 9-13.5',
};

/* ─── 6 pipeline nodes ───────────────────────────────────────────────── */
const NODES = [
  { id: 'analyze',   label: 'Business',     iconKey: 'building',   step: 0 },
  { id: 'blueprint', label: 'Blueprint',    iconKey: 'document',   step: 1 },
  { id: 'codegen',   label: 'UX / UI',      iconKey: 'lightning',  step: 2 },
  { id: 'critic',    label: 'AI Review',    iconKey: 'sparkles',   step: 3 },
  { id: 'build',     label: 'Architecture', iconKey: 'cog',        step: 4 },
  { id: 'data',      label: 'Data',         iconKey: 'chart',      step: 0 },
];

// Angles (degrees) for nodes around the circle — matches reference image feel
const ANGLES = [270, 330, 30, 90, 150, 210];

/* ─── Real-progress polling hook ─────────────────────────────────────── */
function useRealProgress(requestId?: number) {
  const [progress, setProgress] = useState<ProgressSnapshot | null>(null);
  const ref = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!requestId) return;
    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/requests/${requestId}/progress`);
        if (res.ok) setProgress(await res.json());
      } catch { /* ignore */ }
    };
    poll();
    ref.current = setInterval(poll, 2500);
    return () => { if (ref.current) clearInterval(ref.current); };
  }, [requestId]);

  return progress;
}

/* ─── Main component ─────────────────────────────────────────────────── */
export default function GenerationCinematic({
  requestId,
  businessName,
  compact = false,
  title = 'Building your product',
}: Props) {
  const progress = useRealProgress(requestId);
  const activeStep = progress ? (STAGE_TO_STEP[progress.stage] ?? 0) : 0;
  const pct = progress?.pct ?? 0;
  const currentLabel = progress?.label ?? 'Starting…';
  const detail = progress?.detail ?? '';
  const filesDone = progress?.files_done ?? 0;
  const filesTotal = progress?.files_total ?? 0;
  const log = progress?.log ?? [];

  return (
    <div
      className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden"
      style={{ background: 'radial-gradient(ellipse 120% 80% at 50% 40%, #0a1628 0%, #050c18 60%, #020810 100%)' }}
    >
      {/* Grid overlay */}
      <GridOverlay />

      {/* Ambient glow orbs */}
      <div className="absolute w-[600px] h-[600px] rounded-full opacity-[0.07] pointer-events-none"
        style={{ background: 'radial-gradient(circle, #3b82f6 0%, transparent 70%)', top: '10%', left: '50%', transform: 'translateX(-50%)' }} />
      <div className="absolute w-[400px] h-[400px] rounded-full opacity-[0.05] pointer-events-none"
        style={{ background: 'radial-gradient(circle, #06b6d4 0%, transparent 70%)', top: '40%', left: '20%' }} />

      <div className="relative z-10 w-full max-w-5xl mx-auto px-4 py-10 flex flex-col items-center gap-8">

        {/* Title */}
        <motion.div
          initial={{ opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center"
        >
          <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-cyan-400 mb-2">AI at work</p>
          <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">{title}</h1>
          {businessName && (
            <p className="text-slate-400 text-sm mt-1">
              Crafting for <span className="text-cyan-300 font-medium">{businessName}</span>
            </p>
          )}
        </motion.div>

        {/* Node Graph */}
        <motion.div
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.15, duration: 0.7 }}
          className="relative flex items-center justify-center"
          style={{ width: compact ? 280 : 400, height: compact ? 280 : 400 }}
        >
          <NodeGraph activeStep={activeStep} pct={pct} businessName={businessName} compact={compact} />
        </motion.div>

        {/* Current action pill */}
        <AnimatePresence mode="wait">
          <motion.div
            key={currentLabel}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="flex items-center gap-3 px-5 py-2.5 rounded-full border border-cyan-500/30 bg-cyan-500/10 backdrop-blur"
          >
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse shrink-0" />
            <span className="text-cyan-200 text-sm font-mono font-medium">{currentLabel}</span>
          </motion.div>
        </AnimatePresence>

        {/* Codegen file progress */}
        {filesTotal > 0 && activeStep === 2 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center"
          >
            <p className="text-slate-400 text-xs font-mono mb-1.5">
              {filesDone} / {filesTotal} files generated
            </p>
            <div className="w-48 h-1 rounded-full bg-white/10 mx-auto overflow-hidden">
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-400"
                animate={{ width: filesTotal > 0 ? `${(filesDone / filesTotal) * 100}%` : '0%' }}
                transition={{ duration: 0.6 }}
              />
            </div>
          </motion.div>
        )}

        {/* Global progress bar */}
        <div className="w-full max-w-md">
          <div className="flex justify-between text-[10px] text-slate-500 mb-1.5">
            <span className="font-mono">pipeline progress</span>
            <span className="text-cyan-400 font-mono font-bold">{pct}%</span>
          </div>
          <div className="h-0.5 rounded-full bg-white/10 overflow-hidden">
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-blue-500 via-cyan-400 to-teal-400"
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
            />
          </div>
        </div>

        {/* Live log — last few events */}
        {!compact && log.length > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
            className="w-full max-w-lg bg-black/40 border border-white/10 rounded-xl p-4 font-mono text-xs"
          >
            <div className="space-y-1">
              {log.slice(-6).map((entry, i, arr) => (
                <div key={i} className={`flex gap-2 ${i === arr.length - 1 ? 'text-cyan-300' : 'text-slate-500'}`}>
                  <span className="shrink-0 text-slate-600">›</span>
                  <span className="truncate">{entry.msg}</span>
                </div>
              ))}
              {detail && (
                <div className="flex gap-2 text-slate-600">
                  <span className="shrink-0">·</span>
                  <span className="truncate italic">{detail}</span>
                </div>
              )}
            </div>
          </motion.div>
        )}

        <p className="text-center text-[11px] text-white/25 max-w-sm leading-relaxed">
          Keep this tab open — your live site, blueprint, technical plan, and proposal are being built simultaneously.
        </p>
      </div>
    </div>
  );
}

/* ─── Animated node graph (the centrepiece) ──────────────────────────── */
function NodeGraph({
  activeStep,
  pct,
  businessName,
  compact,
}: {
  activeStep: number;
  pct: number;
  businessName?: string;
  compact: boolean;
}) {
  const size = compact ? 280 : 400;
  const cx = size / 2;
  const cy = size / 2;
  const radius = compact ? 100 : 145;
  const nodeR = compact ? 28 : 36;

  const nodePositions = ANGLES.map((angleDeg) => {
    const rad = (angleDeg * Math.PI) / 180;
    return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) };
  });

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ overflow: 'visible' }}>
      <defs>
        {/* Glow filters */}
        <filter id="glow-cyan" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="glow-center" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="8" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        {/* Animated line gradient */}
        <linearGradient id="line-grad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.8" />
          <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.8" />
        </linearGradient>
        <radialGradient id="center-grad" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#1d4ed8" />
          <stop offset="60%" stopColor="#0f172a" />
          <stop offset="100%" stopColor="#020810" />
        </radialGradient>
      </defs>

      {/* Connecting lines */}
      {nodePositions.map((pos, i) => {
        const node = NODES[i];
        const isDone = activeStep > node.step;
        const isActive = activeStep === node.step;
        const opacity = isDone ? 0.85 : isActive ? 0.65 : 0.18;
        return (
          <g key={`line-${i}`}>
            {/* Base dim line */}
            <line
              x1={cx} y1={cy} x2={pos.x} y2={pos.y}
              stroke="#1e3a5f" strokeWidth="1"
            />
            {/* Lit line */}
            <motion.line
              x1={cx} y1={cy} x2={pos.x} y2={pos.y}
              stroke="url(#line-grad)"
              strokeWidth={isActive ? 2 : 1.5}
              strokeLinecap="round"
              animate={{ opacity }}
              transition={{ duration: 0.8 }}
            />
            {/* Travelling dot on active line */}
            {isActive && (
              <TravellingDot x1={cx} y1={cy} x2={pos.x} y2={pos.y} />
            )}
          </g>
        );
      })}

      {/* Center glow ring (outer) */}
      <motion.circle
        cx={cx} cy={cy} r={compact ? 46 : 62}
        fill="none"
        stroke="#3b82f6"
        strokeWidth="1"
        animate={{ opacity: [0.2, 0.5, 0.2], r: [compact ? 46 : 62, compact ? 50 : 66, compact ? 46 : 62] }}
        transition={{ duration: 2.8, repeat: Infinity, ease: 'easeInOut' }}
      />
      {/* Center glow ring (inner) */}
      <motion.circle
        cx={cx} cy={cy} r={compact ? 38 : 52}
        fill="none"
        stroke="#06b6d4"
        strokeWidth="0.8"
        animate={{ opacity: [0.3, 0.7, 0.3] }}
        transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut', delay: 0.4 }}
      />

      {/* Center node bg */}
      <circle cx={cx} cy={cy} r={compact ? 34 : 46} fill="url(#center-grad)" filter="url(#glow-center)" />
      <circle cx={cx} cy={cy} r={compact ? 34 : 46} fill="none" stroke="#3b82f6" strokeWidth="1.5" opacity="0.7" />

      {/* Real BMV logo in center */}
      {(() => {
        const logoSize = compact ? 44 : 60;
        return (
          <image
            href="/logo.png"
            x={cx - logoSize / 2}
            y={cy - logoSize / 2}
            width={logoSize}
            height={logoSize}
            preserveAspectRatio="xMidYMid meet"
          />
        );
      })()}

      {/* % underneath logo */}
      {pct > 0 && (
        <text x={cx} y={cy + (compact ? 34 : 46) + 14} textAnchor="middle" fill="#06b6d4" fontSize={compact ? 8 : 10} fontFamily="monospace" fontWeight="600">
          {pct}%
        </text>
      )}

      {/* Surrounding nodes */}
      {nodePositions.map((pos, i) => {
        const node = NODES[i];
        const isDone = activeStep > node.step;
        const isActive = activeStep === node.step;
        return (
          <SurroundingNode
            key={node.id}
            x={pos.x} y={pos.y} r={nodeR}
            iconKey={isDone ? 'check' : node.iconKey}
            label={node.label}
            isDone={isDone} isActive={isActive}
            compact={compact}
          />
        );
      })}
    </svg>
  );
}

/* ─── Animated dot travelling along a line ───────────────────────────── */
function TravellingDot({ x1, y1, x2, y2 }: { x1: number; y1: number; x2: number; y2: number }) {
  const [t, setT] = useState(0);
  const rafRef = useRef<number | null>(null);
  const startRef = useRef<number | null>(null);
  const DURATION = 1800;

  useEffect(() => {
    const animate = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      const elapsed = (ts - startRef.current) % DURATION;
      setT(elapsed / DURATION);
      rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, []);

  const px = x1 + (x2 - x1) * t;
  const py = y1 + (y2 - y1) * t;

  return (
    <circle cx={px} cy={py} r={3} fill="#38bdf8" opacity={0.9} filter="url(#glow-cyan)" />
  );
}

/* ─── Single surrounding node ────────────────────────────────────────── */
function SurroundingNode({
  x, y, r, iconKey, label, isDone, isActive, compact,
}: {
  x: number; y: number; r: number;
  iconKey: string; label: string;
  isDone: boolean; isActive: boolean; compact: boolean;
}) {
  const fillColor = isDone ? '#0f4c35' : isActive ? '#0c2a4d' : '#0a1628';
  const strokeColor = isDone ? '#10b981' : isActive ? '#38bdf8' : '#1e3a5f';
  const strokeWidth = isActive ? 2 : 1;
  const filterStr = isActive || isDone ? 'url(#glow-cyan)' : undefined;
  const labelSize = compact ? 8 : 10;
  // Icon drawn in a 24×24 viewBox, scaled to fit inside circle
  const iconScale = compact ? (r * 1.0) / 24 : (r * 1.1) / 24;
  const iconColor = isDone ? '#6ee7b7' : isActive ? '#38bdf8' : '#334155';

  return (
    <g filter={filterStr}>
      {/* Node bg */}
      <motion.circle cx={x} cy={y} r={r} fill={fillColor}
        animate={{ fill: fillColor }} transition={{ duration: 0.6 }} />
      <motion.circle cx={x} cy={y} r={r} fill="none"
        stroke={strokeColor} strokeWidth={strokeWidth}
        animate={{ stroke: strokeColor, strokeWidth }} transition={{ duration: 0.6 }} />

      {/* Pulse ring on active */}
      {isActive && (
        <motion.circle cx={x} cy={y} r={r + 4} fill="none" stroke="#38bdf8" strokeWidth="0.8"
          animate={{ opacity: [0.4, 0.9, 0.4], r: [r + 4, r + 8, r + 4] }}
          transition={{ duration: 1.5, repeat: Infinity }} />
      )}

      {/* Inline SVG icon — centred via transform */}
      <g transform={`translate(${x - 12 * iconScale}, ${y - 12 * iconScale}) scale(${iconScale})`}>
        <path
          d={ICON_PATHS[iconKey] ?? ICON_PATHS.building}
          fill="none"
          stroke={iconColor}
          strokeWidth={isDone ? 2.5 : 1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>

      {/* Label */}
      <text
        x={x} y={y + r + labelSize + 3}
        textAnchor="middle"
        fill={isDone ? '#6ee7b7' : isActive ? '#7dd3fc' : '#334155'}
        fontSize={labelSize}
        fontFamily="system-ui, sans-serif"
        fontWeight={isActive ? '600' : '400'}
      >
        {label}
      </text>
    </g>
  );
}

/* ─── Subtle grid background ─────────────────────────────────────────── */
function GridOverlay() {
  return (
    <div
      className="absolute inset-0 pointer-events-none opacity-[0.06]"
      style={{
        backgroundImage: `
          linear-gradient(to right, #38bdf8 1px, transparent 1px),
          linear-gradient(to bottom, #38bdf8 1px, transparent 1px)
        `,
        backgroundSize: '48px 48px',
      }}
    />
  );
}
