import { motion } from 'framer-motion';
import type { PreviewResponse } from '../../types/request';
import { parseMarkdownSections, extractListItems } from '../../utils/parseMarkdownSections';
import { fixEncoding, getAiAnalysisText } from '../../utils/referenceAnalysis';

const ease = [0.22, 1, 0.36, 1] as const;

interface Props {
  preview: PreviewResponse;
}

export default function ReferenceAnalysisShowcase({ preview }: Props) {
  const aiText = getAiAnalysisText(preview);
  const sections = aiText ? parseMarkdownSections(preprocessAi(aiText)) : [];

  const headline = sections.find((s) => /what this tool|reference/i.test(s.title));
  const why = sections.find((s) => /resonates|why/i.test(s.title));
  const patterns = sections.find((s) => /pattern|experience/i.test(s.title));
  const adapt = sections.find((s) => /worth adapting|features worth/i.test(s.title));
  const customize = sections.find((s) => /custom|shapes your/i.test(s.title));
  const used = new Set([headline, why, patterns, adapt, customize].filter(Boolean));
  const rest = sections.filter((s) => !used.has(s) && !isMetadataDumpSection(s.body));

  const hasHero = preview.reference_url || preview.what_you_like;

  return (
    <div className="space-y-6">
      {hasHero && (
        <div className="grid sm:grid-cols-2 gap-4">
          {preview.reference_url && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.45, ease }}
              className="rounded-2xl border border-amber-200/80 bg-gradient-to-br from-amber-50 to-white p-5 sm:p-6"
            >
              <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-700 mb-2">
                Your inspiration
              </p>
              <a
                href={preview.reference_url}
                target="_blank"
                rel="noreferrer"
                className="text-lg font-semibold text-slate-900 hover:text-indigo-600"
              >
                {hostLabel(preview.reference_url)}
              </a>
              <p className="text-xs text-slate-500 mt-2">The product experience you want to emulate</p>
            </motion.div>
          )}
          {preview.what_you_like && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.45, delay: 0.05, ease }}
              className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-sm"
            >
              <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400 mb-2">
                What caught your eye
              </p>
              <p className="text-sm text-slate-700 leading-relaxed">
                &ldquo;{fixEncoding(preview.what_you_like)}&rdquo;
              </p>
            </motion.div>
          )}
        </div>
      )}

      {aiText ? (
        <>
          {headline && <NarrativeCard section={headline} accent="amber" />}
          {why && <NarrativeCard section={why} accent="violet" />}
          {patterns && (
            <InsightGrid title={patterns.title} items={extractListItems(patterns.body)} accent="indigo" />
          )}
          {adapt && (
            <InsightGrid title={adapt.title} items={extractListItems(adapt.body)} accent="emerald" />
          )}
          {customize && <NarrativeCard section={customize} accent="slate" />}
          {rest.map((s, i) => {
            const items = extractListItems(s.body);
            if (items.length >= 2) {
              return <InsightGrid key={s.title} title={s.title} items={items} accent="indigo" delay={i * 0.05} />;
            }
            return <NarrativeCard key={s.title} section={s} accent="slate" delay={i * 0.05} />;
          })}
        </>
      ) : (
        <FallbackInsights preview={preview} />
      )}
    </div>
  );
}

function FallbackInsights({ preview }: { preview: PreviewResponse }) {
  const bullets = [
    preview.what_you_like && `You value: ${fixEncoding(preview.what_you_like)}`,
    preview.desired_outcome && `Your goal: ${fixEncoding(preview.desired_outcome)}`,
    preview.concept_name && `We shaped ${preview.concept_name} around these patterns — customized for ${preview.business_name}.`,
  ].filter(Boolean) as string[];

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.45, ease }}
      className="rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50/60 to-white p-5 sm:p-6"
    >
      <h3 className="text-base font-bold text-slate-900 mb-4">How we used your inspiration</h3>
      <div className="space-y-3">
        {bullets.map((item) => (
          <div key={item.slice(0, 40)} className="flex gap-3">
            <span className="w-6 h-6 rounded-full bg-indigo-600 text-white text-xs font-bold flex items-center justify-center shrink-0">
              ✓
            </span>
            <p className="text-sm text-slate-600 leading-relaxed pt-0.5">{item}</p>
          </div>
        ))}
        <p className="text-sm text-slate-500 leading-relaxed pt-2 border-t border-indigo-100 mt-4">
          We studied this reference for booking flow, messaging tone, and simplicity — then built a version that fits your business, not a copy of their brand.
        </p>
      </div>
    </motion.div>
  );
}

function preprocessAi(text: string): string {
  return fixEncoding(text)
    .replace(/^#{1,6}\s+#+\s*/gm, '## ')
    .replace(/^\*\*Reference Analysis:.*\*\*\s*$/gm, '');
}

function isMetadataDumpSection(body: string): boolean {
  return /\*\*Reference tool:\*\*/i.test(body) || /\*\*Site title:\*\*/i.test(body);
}

function hostLabel(url: string) {
  try {
    const host = new URL(url).hostname.replace(/^www\./, '');
    return host.charAt(0).toUpperCase() + host.slice(1);
  } catch {
    return url;
  }
}

function NarrativeCard({
  section,
  accent,
  delay = 0,
}: {
  section: { title: string; body: string };
  accent: 'amber' | 'violet' | 'slate' | 'indigo';
  delay?: number;
}) {
  const border =
    accent === 'amber'
      ? 'border-amber-100 bg-amber-50/40'
      : accent === 'violet'
        ? 'border-violet-100 bg-violet-50/40'
        : 'border-slate-200 bg-slate-50/50';

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.45, delay, ease }}
      className={`rounded-2xl border p-5 sm:p-6 ${border}`}
    >
      <h3 className="text-base font-bold text-slate-900 mb-3">{cleanTitle(section.title)}</h3>
      <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-line">{humanize(section.body)}</p>
    </motion.div>
  );
}

function InsightGrid({
  title,
  items,
  accent,
  delay = 0,
}: {
  title: string;
  items: string[];
  accent: 'indigo' | 'emerald' | 'amber';
  delay?: number;
}) {
  if (!items.length) return null;
  const dot =
    accent === 'emerald' ? 'bg-emerald-500' : accent === 'amber' ? 'bg-amber-500' : 'bg-indigo-500';

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.45, delay, ease }}
    >
      <h3 className="text-sm font-bold text-slate-900 mb-3">{cleanTitle(title)}</h3>
      <div className="grid sm:grid-cols-2 gap-3">
        {items.map((item) => (
          <div
            key={item.slice(0, 40)}
            className="flex gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3.5 shadow-sm"
          >
            <span className={`w-2 h-2 rounded-full ${dot} shrink-0 mt-1.5`} />
            <p className="text-sm text-slate-600 leading-relaxed">{humanize(item)}</p>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

function cleanTitle(title: string) {
  return title.replace(/\*\*/g, '').replace(/^\d+\.\s*/, '').replace(/^#+\s*/, '').trim();
}

function humanize(text: string) {
  return fixEncoding(text)
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/^[-*]\s+/gm, '')
    .trim();
}
