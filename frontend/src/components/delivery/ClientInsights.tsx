import { motion } from 'framer-motion';
import type { PreviewResponse } from '../../types/request';
import { parseMarkdownSections, highlightSections } from '../../utils/parseMarkdownSections';

interface Props {
  preview: PreviewResponse;
}

export default function ClientInsights({ preview }: Props) {
  const blueprintSections = preview.mvp_blueprint
    ? highlightSections(parseMarkdownSections(preview.mvp_blueprint), [
        'must-have',
        'ai features',
        'customer',
        'journey',
        'screens',
        'timeline',
      ])
    : [];

  return (
    <section className="py-16 sm:py-20 bg-white border-t border-slate-100">
      <div className="max-w-4xl mx-auto px-4 sm:px-6">
        <div className="text-center mb-10">
          <p className="text-sm font-semibold text-indigo-600 mb-2">What we designed for you</p>
          <h2 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
            Your product at a glance
          </h2>
          <p className="text-slate-600 mt-3 text-base leading-relaxed">
            {preview.preview_summary}
          </p>
        </div>

        {preview.business_fit_score !== null && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="flex justify-center mb-10"
          >
            <div className="inline-flex items-center gap-4 px-6 py-4 rounded-2xl border border-indigo-100 bg-indigo-50/50">
              <div className="text-center">
                <p className="text-4xl font-bold text-indigo-600">{preview.business_fit_score}%</p>
                <p className="text-xs text-slate-500 mt-0.5">Business-fit score</p>
              </div>
              <div className="w-px h-12 bg-indigo-200" />
              <div>
                <p className="font-semibold text-slate-900">{preview.concept_name}</p>
                <p className="text-sm text-slate-500">Custom concept for {preview.business_name}</p>
              </div>
            </div>
          </motion.div>
        )}

        {preview.preview_features.length > 0 && (
          <div className="grid sm:grid-cols-2 gap-3 mb-10">
            {preview.preview_features.map((feature, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.05 }}
                className="flex items-start gap-3 p-4 rounded-xl border border-slate-100 bg-slate-50/50"
              >
                <span className="w-6 h-6 rounded-lg bg-indigo-100 text-indigo-600 flex items-center justify-center text-xs font-bold shrink-0">
                  {i + 1}
                </span>
                <p className="text-sm text-slate-700 leading-relaxed">{feature}</p>
              </motion.div>
            ))}
          </div>
        )}

        {blueprintSections.length > 0 && (
          <div className="space-y-3">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider text-center mb-4">
              Strategic highlights
            </p>
            {blueprintSections.slice(0, 4).map((section, i) => (
              <motion.div
                key={section.title}
                initial={{ opacity: 0, y: 10 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.06 }}
                className="rounded-xl border border-slate-100 p-5 bg-white shadow-sm"
              >
                <h3 className="font-semibold text-slate-900 text-sm mb-2">{section.title}</h3>
                <p className="text-sm text-slate-600 leading-relaxed line-clamp-4 whitespace-pre-line">
                  {section.body.replace(/\*\*/g, '').slice(0, 280)}
                  {section.body.length > 280 ? '…' : ''}
                </p>
              </motion.div>
            ))}
          </div>
        )}

        {(preview.timeline || preview.desired_outcome) && (
          <div className="mt-8 grid sm:grid-cols-2 gap-4">
            {preview.timeline && (
              <div className="rounded-xl border border-slate-100 p-5 bg-slate-50/30">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Timeline</p>
                <p className="text-sm text-slate-800">{preview.timeline}</p>
              </div>
            )}
            {preview.desired_outcome && (
              <div className="rounded-xl border border-slate-100 p-5 bg-slate-50/30">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Your goal</p>
                <p className="text-sm text-slate-800">{preview.desired_outcome}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
