import { useEffect, useState, type ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import MarkdownProse from './MarkdownProse';

const ease = [0.22, 1, 0.36, 1] as const;

interface Props {
  id: string;
  number: string;
  eyebrow: string;
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  children?: ReactNode;
  markdown?: string;
  markdownVariant?: 'default' | 'proposal' | 'technical';
  defaultOpen?: boolean;
  highlight?: boolean;
  accent?: 'indigo' | 'violet' | 'emerald' | 'amber';
}

const accentMap = {
  indigo: 'from-indigo-500 to-violet-500',
  violet: 'from-violet-500 to-purple-500',
  emerald: 'from-emerald-500 to-teal-500',
  amber: 'from-amber-500 to-orange-500',
};

export default function DeliverySection({
  id,
  number,
  eyebrow,
  title,
  subtitle,
  icon,
  children,
  markdown,
  markdownVariant = 'default',
  defaultOpen = true,
  highlight = false,
  accent = 'indigo',
}: Props) {
  const [open, setOpen] = useState(defaultOpen);

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.sectionId === id) {
        setOpen(true);
        setTimeout(() => {
          document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100);
      }
    };
    window.addEventListener('delivery-navigate', handler);
    return () => window.removeEventListener('delivery-navigate', handler);
  }, [id]);

  return (
    <motion.section
      id={id}
      initial={{ opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-50px' }}
      transition={{ duration: 0.55, ease }}
      className={`delivery-section scroll-mt-32 ${highlight ? 'delivery-section--highlight' : ''}`}
    >
      <div className="delivery-section-inner">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full text-left flex items-start gap-4 sm:gap-5 group"
        >
          <div className={`delivery-section-number bg-gradient-to-br ${accentMap[accent]} shrink-0`}>
            {icon ?? <span>{number}</span>}
          </div>
          <div className="flex-1 min-w-0 pt-0.5">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-600 mb-1">{eyebrow}</p>
            <h2 className="text-xl sm:text-2xl font-bold text-slate-900 group-hover:text-indigo-700 transition-colors">
              {title}
            </h2>
            {subtitle && <p className="text-sm text-slate-500 mt-2 leading-relaxed max-w-2xl">{subtitle}</p>}
          </div>
          <span
            className={`shrink-0 mt-1 w-9 h-9 rounded-xl border border-slate-200 bg-slate-50 flex items-center justify-center text-slate-400 transition-all duration-300 group-hover:border-slate-300 ${open ? 'rotate-180 bg-indigo-50 text-indigo-600 border-indigo-200' : ''}`}
          >
            <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 9l6 6 6-6" />
            </svg>
          </span>
        </button>

        <AnimatePresence initial={false}>
          {open && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.4, ease }}
              className="overflow-hidden"
            >
              <div className="pt-6 sm:pt-8 pl-0 sm:pl-[4.25rem] border-t border-slate-100 mt-5 sm:mt-6">
                {children}
                {markdown && <MarkdownProse content={markdown} variant={markdownVariant} />}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.section>
  );
}

interface CardGridProps {
  sections: { title: string; body: string }[];
}

/** @deprecated Use BlueprintShowcase instead */
export function BlueprintCardGrid(_sections: CardGridProps['sections']) {
  return null;
}

export function ProposalDocument({ content, conceptName }: { content: string; conceptName?: string | null }) {
  return (
    <div className="rounded-2xl border border-indigo-100 bg-gradient-to-b from-indigo-50/80 to-white overflow-hidden shadow-sm">
      <div className="px-6 sm:px-8 py-6 border-b border-indigo-100/80 bg-white/60">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-600 mb-1">Build proposal</p>
        <h3 className="text-xl font-bold text-slate-900">{conceptName || 'Your custom MVP'}</h3>
        <p className="text-sm text-slate-500 mt-1">Prepared by Build My Version</p>
      </div>
      <div className="px-6 sm:px-8 py-6 sm:py-8">
        <MarkdownProse content={content} variant="proposal" />
      </div>
    </div>
  );
}

export function TechnicalDocument({ content }: { content: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-200 bg-slate-100/80 flex items-center gap-2">
        <span className="w-2.5 h-2.5 rounded-full bg-red-400" />
        <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
        <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
        <span className="text-xs text-slate-500 font-mono ml-2">technical-plan.md</span>
      </div>
      <div className="px-5 sm:px-6 py-5 sm:py-6">
        <MarkdownProse content={content} variant="technical" />
      </div>
    </div>
  );
}
