import { useState } from 'react';
import { motion } from 'framer-motion';
import { parseMarkdownSections, extractListItems } from '../../utils/parseMarkdownSections';

const ease = [0.22, 1, 0.36, 1] as const;

type StructuredAiFeature = {
  id: string;
  name: string;
  description?: string;
  category?: string;
};

interface Props {
  content: string;
  conceptName?: string | null;
  aiFeatures?: StructuredAiFeature[];
}

export default function ProposalShowcase({ content, conceptName, aiFeatures: structuredAi }: Props) {
  const sections = parseMarkdownSections(content);

  const find = (...kws: string[]) =>
    sections.find((s) => kws.some((k) => s.title.toLowerCase().includes(k)));

  const goal       = find('client goal', 'goal', 'objective');
  const solution   = find('proposed solution', 'solution');
  const includes   = find('mvp will include', 'what is included', 'first mvp');
  const excludes   = find('not included', 'excluded', 'out of scope');
  const aiFeatures = find('ai feature', 'automation feature');
  const benefits   = find('expected benefit', 'benefit', 'outcome');
  const timeline   = find('timeline', 'estimated time');
  const pricing    = find('pricing', 'investment', 'cost');
  const nextSteps  = find('next step');
  const whatsapp   = find('whatsapp', 'follow-up', 'message');

  const structuredNames = (structuredAi ?? []).map((f) => f.name).filter(Boolean);
  const markdownAiItems = aiFeatures ? extractListItems(aiFeatures.body) : [];
  const aiItems = structuredNames.length > 0 ? structuredNames : markdownAiItems;

  const used = new Set(
    [goal, solution, includes, excludes, aiFeatures, benefits, timeline, pricing, nextSteps, whatsapp]
      .filter(Boolean)
      .map((s) => s!.title),
  );
  const rest = sections.filter((s) => !used.has(s.title)).slice(0, 4);

  return (
    <div className="space-y-5">

      {/* ── Header ── */}
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5, ease }}
        className="rounded-3xl bg-gradient-to-br from-indigo-950 to-violet-950 px-7 py-8 relative overflow-hidden"
      >
        <div className="absolute -top-16 -right-16 w-56 h-56 rounded-full bg-indigo-500/15 blur-3xl pointer-events-none" />
        <div className="absolute -bottom-12 -left-12 w-44 h-44 rounded-full bg-violet-500/15 blur-3xl pointer-events-none" />
        <div className="relative z-10">
          <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3.5 py-1.5 text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-300 mb-4">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
            Build proposal
          </span>
          <h2 className="text-2xl sm:text-3xl font-black text-white tracking-tight mb-1">
            {conceptName ?? 'Your custom MVP'}
          </h2>
          <p className="text-sm text-indigo-300/70">Prepared by Build My Version</p>
        </div>
      </motion.div>

      {/* ── Goal + Solution ── */}
      {(goal || solution) && (
        <div className="grid sm:grid-cols-2 gap-4">
          {goal && (
            <SectionCard delay={0.05} label="Client goal" accent="violet">
              <Prose body={goal.body} limit={180} />
            </SectionCard>
          )}
          {solution && (
            <SectionCard delay={0.08} label="Proposed solution" accent="indigo">
              <Prose body={solution.body} limit={180} />
            </SectionCard>
          )}
        </div>
      )}

      {/* ── Includes / Excludes ── */}
      {(includes || excludes) && (
        <div className="grid sm:grid-cols-2 gap-4">
          {includes && (
            <SectionCard delay={0.1} label="What's included in MVP v1" accent="emerald">
              <PillList items={extractListItems(includes.body)} variant="include" />
            </SectionCard>
          )}
          {excludes && (
            <SectionCard delay={0.12} label="Not in v1 (future phases)" accent="slate">
              <PillList items={extractListItems(excludes.body)} variant="exclude" />
            </SectionCard>
          )}
        </div>
      )}

      {/* ── AI features (structured inventory preferred over markdown sniffing) ── */}
      {aiItems.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1, duration: 0.5, ease }}
          className="rounded-3xl bg-gradient-to-r from-violet-50 to-indigo-50 border border-violet-200/60 p-6"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-xl bg-violet-100 flex items-center justify-center text-violet-600">
              <ZapIcon />
            </div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-violet-700">AI features</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {aiItems.slice(0, 8).map((item, i) => (
              <span key={i} className="inline-flex items-center gap-1.5 rounded-full bg-violet-600 text-white text-xs font-semibold px-3.5 py-1.5">
                <span className="w-1 h-1 rounded-full bg-violet-300" />
                {trunc(item, 60)}
              </span>
            ))}
          </div>
        </motion.div>
      )}

      {/* ── Benefits ── */}
      {benefits && (
        <SectionCard delay={0.12} label="Expected benefits">
          <BenefitGrid items={extractListItems(benefits.body)} />
        </SectionCard>
      )}

      {/* ── Timeline + Pricing ── */}
      {(timeline || pricing) && (
        <div className="grid sm:grid-cols-2 gap-4">
          {timeline && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.1, duration: 0.45, ease }}
              className="rounded-3xl border border-emerald-200/60 bg-emerald-50/50 p-6"
            >
              <div className="flex items-center gap-2.5 mb-3">
                <CalIcon />
                <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-700">Timeline</p>
              </div>
              <Prose body={timeline.body} limit={200} className="text-emerald-900" />
            </motion.div>
          )}
          {pricing && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.13, duration: 0.45, ease }}
              className="rounded-3xl border border-indigo-200/60 bg-indigo-50/50 p-6"
            >
              <div className="flex items-center gap-2.5 mb-3">
                <TagIcon />
                <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-700">Investment</p>
              </div>
              <Prose body={pricing.body} limit={200} className="text-indigo-900" />
            </motion.div>
          )}
        </div>
      )}

      {/* ── Next steps ── */}
      {nextSteps && (
        <SectionCard delay={0.14} label="Next steps" accent="indigo">
          <StepList items={extractListItems(nextSteps.body)} />
        </SectionCard>
      )}

      {/* ── Rest ── */}
      {rest.map((s, i) => (
        <SectionCard key={s.title} delay={i * 0.04} label={s.title}>
          <Prose body={s.body} limit={240} />
        </SectionCard>
      ))}

      {/* ── WhatsApp message ── */}
      {whatsapp && <WhatsAppCard body={whatsapp.body} />}
    </div>
  );
}

/* ── Section card wrapper ── */
function SectionCard({
  children,
  label,
  accent = 'indigo',
  delay = 0,
}: {
  children: React.ReactNode;
  label: string;
  accent?: 'indigo' | 'violet' | 'emerald' | 'slate';
  delay?: number;
}) {
  const labelColor = { indigo: 'text-indigo-600', violet: 'text-violet-600', emerald: 'text-emerald-600', slate: 'text-slate-500' }[accent];
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ delay, duration: 0.45, ease }}
      className="rounded-3xl border border-slate-200/60 bg-white p-6 shadow-sm"
    >
      <p className={`text-[10px] font-bold uppercase tracking-[0.2em] mb-4 ${labelColor}`}>{label}</p>
      {children}
    </motion.div>
  );
}

/* ── Prose — short, no walls ── */
function Prose({ body, limit = 200, className = '' }: { body: string; limit?: number; className?: string }) {
  const items = extractListItems(body);
  if (items.length > 0) {
    return (
      <ul className="space-y-2">
        {items.slice(0, 5).map((item, i) => (
          <li key={i} className={`flex items-start gap-2.5 text-sm leading-snug ${className || 'text-slate-700'}`}>
            <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-indigo-400 shrink-0" />
            <span className="line-clamp-2">{trunc(item, 120)}</span>
          </li>
        ))}
      </ul>
    );
  }
  const text = clean(body).slice(0, limit);
  return <p className={`text-sm leading-relaxed line-clamp-4 ${className || 'text-slate-700'}`}>{text}{body.length > limit ? '…' : ''}</p>;
}

/* ── Pill lists ── */
function PillList({ items, variant }: { items: string[]; variant: 'include' | 'exclude' }) {
  const isInclude = variant === 'include';
  return (
    <div className="flex flex-wrap gap-2">
      {items.slice(0, 8).map((item, i) => (
        <span
          key={i}
          className={`inline-flex items-center gap-1.5 rounded-full text-xs font-semibold px-3 py-1.5 ${
            isInclude
              ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
              : 'bg-slate-100 text-slate-500 border border-slate-200 line-through decoration-slate-400'
          }`}
        >
          {isInclude && <span className="text-emerald-500">✓</span>}
          {trunc(item, 55)}
        </span>
      ))}
    </div>
  );
}

/* ── Benefit grid ── */
function BenefitGrid({ items }: { items: string[] }) {
  return (
    <div className="grid sm:grid-cols-2 gap-3">
      {items.slice(0, 6).map((item, i) => (
        <div key={i} className="flex items-start gap-2.5 rounded-2xl bg-slate-50 border border-slate-100 px-4 py-3">
          <span className="mt-0.5 w-5 h-5 rounded-lg bg-indigo-100 text-indigo-600 flex items-center justify-center shrink-0 text-xs font-bold">{i + 1}</span>
          <p className="text-sm text-slate-700 leading-snug line-clamp-2">{trunc(item, 90)}</p>
        </div>
      ))}
    </div>
  );
}

/* ── Step list ── */
function StepList({ items }: { items: string[] }) {
  return (
    <ol className="space-y-3">
      {items.slice(0, 6).map((item, i) => (
        <li key={i} className="flex items-start gap-3">
          <span className="w-7 h-7 rounded-xl bg-indigo-600 text-white text-xs font-bold flex items-center justify-center shrink-0">{i + 1}</span>
          <p className="text-sm text-slate-700 leading-snug pt-1 line-clamp-2">{trunc(item, 120)}</p>
        </li>
      ))}
    </ol>
  );
}

/* ── WhatsApp card with copy ── */
function WhatsAppCard({ body }: { body: string }) {
  const [copied, setCopied] = useState(false);
  const text = clean(body);

  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ delay: 0.1, duration: 0.5, ease }}
      className="rounded-3xl border border-emerald-200/60 bg-gradient-to-br from-emerald-50/80 to-teal-50/40 p-6"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-emerald-500 flex items-center justify-center">
            <WaIcon />
          </div>
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-700">WhatsApp follow-up</p>
        </div>
        <button
          onClick={copy}
          className="flex items-center gap-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold px-3.5 py-2 transition-colors"
        >
          {copied ? <CheckIcon /> : <CopyIcon />}
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <div className="rounded-2xl bg-white border border-emerald-100 px-5 py-4">
        <p className="text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">{text.slice(0, 400)}{text.length > 400 ? '…' : ''}</p>
      </div>
    </motion.div>
  );
}

/* ── Icons ── */
function ZapIcon() {
  return <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={1.75}><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></svg>;
}
function CalIcon() {
  return <svg viewBox="0 0 24 24" className="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" strokeWidth={1.75}><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></svg>;
}
function TagIcon() {
  return <svg viewBox="0 0 24 24" className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" strokeWidth={1.75}><path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z" /><circle cx="7" cy="7" r="1.5" fill="currentColor" stroke="none" /></svg>;
}
function WaIcon() {
  return <svg viewBox="0 0 24 24" className="w-4 h-4 text-white" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M11.999 2C6.476 2 2 6.476 2 12c0 1.82.487 3.53 1.339 5.008L2 22l5.154-1.322A9.952 9.952 0 0012 22c5.524 0 10-4.476 10-10S17.524 2 12 2zm0 18.001a8.001 8.001 0 01-4.087-1.123l-.293-.174-3.057.784.806-2.98-.191-.307A8.001 8.001 0 1120.001 12a7.992 7.992 0 01-8.002 8.001z"/></svg>;
}
function CopyIcon() {
  return <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2}><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" /></svg>;
}
function CheckIcon() {
  return <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2.5}><path d="M20 6L9 17l-5-5" /></svg>;
}

/* ── Helpers ── */
function trunc(s: string, n: number) {
  const c = clean(s);
  return c.length > n ? c.slice(0, n).trimEnd() + '…' : c;
}

function clean(text: string) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^[-=]{3,}\s*$/gm, '')
    .replace(/^[-*]\s+/gm, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}
