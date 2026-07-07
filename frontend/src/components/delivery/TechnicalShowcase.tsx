import { motion } from 'framer-motion';
import { parseMarkdownSections, extractListItems } from '../../utils/parseMarkdownSections';

const ease = [0.22, 1, 0.36, 1] as const;

const SKIP = /folder structure|api endpoint|database table|backend api|file path|sqlalchemy|vite|typescript/i;

interface Props {
  content: string;
  conceptName?: string | null;
}

export default function TechnicalShowcase({ content, conceptName }: Props) {
  const sections = parseMarkdownSections(content).filter((s) => !SKIP.test(s.title));

  const overview    = sections.find((s) => /platform|overview|architecture/i.test(s.title));
  const customer    = sections.find((s) => /customer/i.test(s.title));
  const owner       = sections.find((s) => /owner|business|admin/i.test(s.title));
  const smart       = sections.find((s) => /smart|automation|ai|capabilit/i.test(s.title));
  const integrations= sections.find((s) => /integration/i.test(s.title));
  const trust       = sections.find((s) => /data|trust|security/i.test(s.title));
  const phases      = sections.find((s) => /phase|build/i.test(s.title));
  const timeline    = sections.find((s) => /complexity|timeline/i.test(s.title));
  const risks       = sections.find((s) => /risk|assumption/i.test(s.title));

  const used = new Set(
    [overview, customer, owner, smart, integrations, trust, phases, timeline, risks].filter(Boolean),
  );
  const rest = sections.filter((s) => !used.has(s)).slice(0, 3);

  return (
    <div className="space-y-5">

      {/* ── Header strip ── */}
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5, ease }}
        className="rounded-3xl bg-slate-950 px-7 py-6 flex items-center gap-4"
      >
        <div className="w-10 h-10 rounded-2xl bg-indigo-500/20 flex items-center justify-center shrink-0">
          <LayersIcon />
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-400 mb-0.5">Build plan</p>
          <h3 className="text-lg font-bold text-white leading-snug">
            {conceptName ?? 'Your product'} — how it gets built
          </h3>
        </div>
      </motion.div>

      {/* ── Overview one-liner ── */}
      {overview && (
        <SnapshotCard section={overview} color="indigo" delay={0.05} />
      )}

      {/* ── Experience cards grid ── */}
      {(customer || owner || smart) && (
        <div className="grid sm:grid-cols-3 gap-4">
          {customer    && <RoleCard section={customer}    icon="users"  color="violet" delay={0.08} />}
          {owner       && <RoleCard section={owner}       icon="chart"  color="emerald" delay={0.12} />}
          {smart       && <RoleCard section={smart}       icon="zap"    color="amber" delay={0.16} />}
        </div>
      )}

      {/* ── Integrations pills ── */}
      {integrations && <IntegrationsPills section={integrations} />}

      {/* ── Trust ── */}
      {trust && <SnapshotCard section={trust} color="emerald" delay={0.1} icon="shield" />}

      {/* ── Phase horizontal flow ── */}
      {phases && <PhaseFlow section={phases} />}

      {/* ── Timeline + Risks side by side ── */}
      {(timeline || risks) && (
        <div className="grid sm:grid-cols-2 gap-4">
          {timeline && <MiniCard section={timeline} icon="calendar" />}
          {risks    && <MiniCard section={risks}    icon="alert"    warn />}
        </div>
      )}

      {/* ── Remaining ── */}
      {rest.map((s, i) => (
        <SnapshotCard key={s.title} section={s} color="indigo" delay={i * 0.04} />
      ))}
    </div>
  );
}

/* ── Snapshot card: title + up to 4 bullets, NO prose paragraphs ── */
function SnapshotCard({
  section,
  color,
  delay = 0,
  icon,
}: {
  section: { title: string; body: string };
  color: 'indigo' | 'emerald' | 'violet' | 'amber';
  delay?: number;
  icon?: string;
}) {
  const items = extractListItems(section.body).slice(0, 4);
  const accent = colorMap[color];
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.45, delay, ease }}
      className="rounded-2xl border border-slate-200/60 bg-white p-5 sm:p-6 shadow-sm"
    >
      <div className="flex items-center gap-3 mb-4">
        {icon && (
          <span className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 ${accent.icon}`}>
            <BlockIcon name={icon} />
          </span>
        )}
        <p className={`text-[10px] font-bold uppercase tracking-[0.18em] ${accent.label}`}>
          {cleanTitle(section.title)}
        </p>
      </div>
      {items.length > 0 ? (
        <ul className="space-y-2">
          {items.map((item, i) => (
            <li key={i} className="flex items-start gap-2.5 text-sm text-slate-700 leading-snug">
              <span className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${accent.dot}`} />
              <span className="line-clamp-2">{trunc(item, 90)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-slate-600 leading-relaxed line-clamp-3">{trunc(humanize(section.body), 180)}</p>
      )}
    </motion.div>
  );
}

/* ── Role card: colored top bar, max 4 bullets ── */
function RoleCard({
  section,
  icon,
  color,
  delay = 0,
}: {
  section: { title: string; body: string };
  icon: string;
  color: 'violet' | 'emerald' | 'amber';
  delay?: number;
}) {
  const items = extractListItems(section.body).slice(0, 4);
  const bar = { violet: 'bg-violet-600', emerald: 'bg-emerald-600', amber: 'bg-amber-500' }[color];
  const iconBg = { violet: 'bg-violet-100 text-violet-700', emerald: 'bg-emerald-100 text-emerald-700', amber: 'bg-amber-100 text-amber-700' }[color];
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.5, delay, ease }}
      className="rounded-2xl border border-slate-200/60 bg-white overflow-hidden shadow-sm"
    >
      <div className={`${bar} px-5 py-4 flex items-center gap-3`}>
        <span className={`w-7 h-7 rounded-lg ${iconBg} flex items-center justify-center`}>
          <BlockIcon name={icon} />
        </span>
        <p className="text-sm font-bold text-white leading-tight line-clamp-1">{cleanTitle(section.title)}</p>
      </div>
      <div className="px-5 py-4">
        {items.length > 0 ? (
          <ul className="space-y-2.5">
            {items.map((item, i) => (
              <li key={i} className="flex items-start gap-2 text-[13px] text-slate-700 leading-snug">
                <span className="mt-1.5 w-1 h-1 rounded-full bg-slate-400 shrink-0" />
                <span className="line-clamp-2">{trunc(item, 70)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[13px] text-slate-600 line-clamp-3">{trunc(humanize(section.body), 140)}</p>
        )}
      </div>
    </motion.div>
  );
}

/* ── Integrations pills ── */
function IntegrationsPills({ section }: { section: { title: string; body: string } }) {
  const items = extractListItems(section.body).slice(0, 12);
  if (!items.length) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.4, ease }}
      className="rounded-2xl border border-slate-200/60 bg-white p-5 shadow-sm"
    >
      <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400 mb-4">Integrations</p>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <span key={item.slice(0, 40)} className="px-3 py-1.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-800 border border-indigo-100">
            {trunc(humanize(item), 40)}
          </span>
        ))}
      </div>
    </motion.div>
  );
}

/* ── Phase horizontal flow ── */
function PhaseFlow({ section }: { section: { title: string; body: string } }) {
  const items = extractListItems(section.body).slice(0, 5);
  if (!items.length) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.5, ease }}
      className="rounded-2xl border border-slate-200/60 bg-white p-5 sm:p-6 shadow-sm"
    >
      <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400 mb-5">Build phases</p>
      <div className="overflow-x-auto -mx-1 pb-1">
        <div className="flex items-start gap-0 w-max px-1">
          {items.map((item, i) => (
            <div key={i} className="flex items-start">
              <div className="flex flex-col items-center w-36 text-center">
                <div className="w-9 h-9 rounded-full bg-indigo-600 text-white text-sm font-bold flex items-center justify-center mb-2.5 z-10">
                  {i + 1}
                </div>
                <p className="text-xs text-slate-700 font-medium leading-snug line-clamp-3">{trunc(humanize(item), 60)}</p>
              </div>
              {i < items.length - 1 && (
                <div className="w-8 shrink-0 h-px bg-slate-200 mt-4.5 self-start" style={{ marginTop: '18px' }} />
              )}
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}

/* ── Mini card (timeline / risks) ── */
function MiniCard({ section, icon, warn = false }: { section: { title: string; body: string }; icon: string; warn?: boolean }) {
  const items = extractListItems(section.body).slice(0, 3);
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.4, ease }}
      className={`rounded-2xl border p-5 shadow-sm ${warn ? 'border-amber-200/60 bg-amber-50/50' : 'border-slate-200/60 bg-white'}`}
    >
      <div className="flex items-center gap-2.5 mb-3">
        <span className={`w-7 h-7 rounded-lg flex items-center justify-center ${warn ? 'bg-amber-100 text-amber-600' : 'bg-slate-100 text-slate-600'}`}>
          <BlockIcon name={icon} />
        </span>
        <p className={`text-[10px] font-bold uppercase tracking-[0.18em] ${warn ? 'text-amber-700' : 'text-slate-500'}`}>
          {cleanTitle(section.title)}
        </p>
      </div>
      {items.length > 0 ? (
        <ul className="space-y-1.5">
          {items.map((item, i) => (
            <li key={i} className={`text-xs leading-snug line-clamp-2 ${warn ? 'text-amber-900' : 'text-slate-700'}`}>
              {trunc(item, 80)}
            </li>
          ))}
        </ul>
      ) : (
        <p className={`text-xs leading-relaxed line-clamp-3 ${warn ? 'text-amber-900' : 'text-slate-700'}`}>
          {trunc(humanize(section.body), 120)}
        </p>
      )}
    </motion.div>
  );
}

/* ── Icons ── */
function LayersIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" strokeWidth={1.75}>
      <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
    </svg>
  );
}

function BlockIcon({ name }: { name: string }) {
  const cls = 'w-3.5 h-3.5';
  const s = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.75 } as const;
  switch (name) {
    case 'users':    return <svg viewBox="0 0 24 24" className={cls} {...s}><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /></svg>;
    case 'chart':    return <svg viewBox="0 0 24 24" className={cls} {...s}><path d="M3 3v18h18" /><path d="M7 16l4-6 4 3 5-8" /></svg>;
    case 'zap':      return <svg viewBox="0 0 24 24" className={cls} {...s}><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></svg>;
    case 'shield':   return <svg viewBox="0 0 24 24" className={cls} {...s}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></svg>;
    case 'calendar': return <svg viewBox="0 0 24 24" className={cls} {...s}><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></svg>;
    case 'alert':    return <svg viewBox="0 0 24 24" className={cls} {...s}><circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" /></svg>;
    default:         return <span className="w-2 h-2 rounded-full bg-current block" />;
  }
}

/* ── Color map ── */
const colorMap = {
  indigo:  { label: 'text-indigo-600',  dot: 'bg-indigo-400',  icon: 'bg-indigo-50  text-indigo-600'  },
  violet:  { label: 'text-violet-600',  dot: 'bg-violet-400',  icon: 'bg-violet-50  text-violet-600'  },
  emerald: { label: 'text-emerald-600', dot: 'bg-emerald-400', icon: 'bg-emerald-50 text-emerald-600' },
  amber:   { label: 'text-amber-600',   dot: 'bg-amber-400',   icon: 'bg-amber-50   text-amber-600'   },
};

/* ── Helpers ── */
function cleanTitle(t: string) {
  return t.replace(/\*\*/g, '').replace(/^\d+\.\s*/, '').trim();
}

function trunc(s: string, n: number) {
  return s.length > n ? s.slice(0, n).trimEnd() + '…' : s;
}

function humanize(text: string) {
  return text
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/^(GET|POST|PUT|DELETE|PATCH)\s+\/[^\s:]+:?\s*/gim, '')
    .replace(/\b\/api\/\S+/g, '')
    .replace(/^[-*]\s+/gm, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}
