import { motion } from 'framer-motion';
import type { ReactNode } from 'react';

interface Props {
  url: string;
  children: ReactNode;
  badge?: string;
  className?: string;
  glow?: boolean;
}

export default function BrowserFrame({ url, children, badge = 'LIVE PREVIEW', className = '', glow = true }: Props) {
  return (
    <div className={`live-site-frame relative ${className}`}>
      {glow && (
        <>
          <div className="absolute -inset-6 rounded-[2rem] bg-gradient-to-br from-blue-500/25 via-cyan-400/15 to-indigo-500/20 blur-3xl opacity-80 pointer-events-none" />
          <div className="absolute -inset-2 rounded-[1.75rem] bg-gradient-to-br from-blue-400/10 to-cyan-300/10 blur-xl pointer-events-none" />
        </>
      )}
      <motion.div
        initial={{ opacity: 0, y: 24, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        className="relative rounded-[1.25rem] sm:rounded-[1.5rem] border border-white/10 bg-white shadow-2xl shadow-blue-900/20 overflow-hidden"
        style={{ transform: 'perspective(1400px) rotateX(1deg)' }}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-100 bg-slate-50/90 backdrop-blur-sm">
          <div className="flex gap-1.5 shrink-0">
            <span className="w-3 h-3 rounded-full bg-red-400 shadow-sm" />
            <span className="w-3 h-3 rounded-full bg-amber-400 shadow-sm" />
            <span className="w-3 h-3 rounded-full bg-emerald-400 shadow-sm" />
          </div>
          <div className="flex-1 min-w-0 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white border border-slate-200/80 text-xs text-slate-500 font-mono truncate">
            <span className="text-emerald-500 shrink-0">🔒</span>
            <span className="truncate">{url}</span>
          </div>
          {badge && (
            <span className="shrink-0 text-[10px] font-bold tracking-wider text-cyan-700 bg-cyan-50 px-2.5 py-1 rounded-full border border-cyan-200/80 flex items-center gap-1.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-60" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-cyan-500" />
              </span>
              {badge}
            </span>
          )}
        </div>
        <div className="live-site-viewport">{children}</div>
      </motion.div>
    </div>
  );
}
