import { motion } from 'framer-motion';
import type { PreviewResponse } from '../../types/request';
import { parseMarkdownSections } from '../../utils/parseMarkdownSections';
import VisualDemoPreview from '../VisualDemoPreview';
import DeliveryNavigator from './DeliveryNavigator';
import { buildDeliveryNavItems } from './deliveryNavItems';
import DeliverySection from './DeliverySection';
import BlueprintShowcase from './BlueprintShowcase';
import ReferenceAnalysisShowcase from './ReferenceAnalysisShowcase';
import TechnicalShowcase from './TechnicalShowcase';
import ProposalShowcase from './ProposalShowcase';
import { hasReferenceAnalysis } from '../../utils/referenceAnalysis';

const ease = [0.22, 1, 0.36, 1] as const;

function OverviewCinematic({ preview }: { preview: PreviewResponse }) {
  const meta = [
    { label: 'Industry', value: preview.industry },
    { label: 'Timeline', value: preview.timeline },
    { label: 'Scope', value: preview.budget_range },
  ].filter((m) => m.value);

  const feats = preview.preview_features ?? [];

  return (
    <div className="space-y-6">
      {/* Problem / Goal split — cinematic */}
      {(preview.main_problem || preview.desired_outcome) && (
        <div className="grid sm:grid-cols-2 gap-4">
          {preview.main_problem && (
            <motion.div
              initial={{ opacity: 0, x: -24 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.55, ease }}
              className="rounded-3xl bg-slate-950 p-7 relative overflow-hidden"
            >
              <div className="absolute -top-10 -right-10 w-40 h-40 rounded-full bg-red-500/10 blur-2xl pointer-events-none" />
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-red-400 mb-3">The problem</p>
              <p className="text-base font-medium text-slate-200 leading-relaxed">{preview.main_problem}</p>
            </motion.div>
          )}
          {preview.desired_outcome && (
            <motion.div
              initial={{ opacity: 0, x: 24 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.55, ease }}
              className="rounded-3xl bg-emerald-950/60 border border-emerald-800/40 p-7 relative overflow-hidden"
            >
              <div className="absolute -top-10 -right-10 w-40 h-40 rounded-full bg-emerald-500/10 blur-2xl pointer-events-none" />
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-400 mb-3">Your goal</p>
              <p className="text-base font-medium text-emerald-100 leading-relaxed">{preview.desired_outcome}</p>
            </motion.div>
          )}
        </div>
      )}

      {/* Summary */}
      {preview.preview_summary && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1, duration: 0.55, ease }}
          className="rounded-3xl border border-violet-200/60 bg-gradient-to-br from-violet-50/80 to-indigo-50/40 p-7 sm:p-9"
        >
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-violet-600 mb-3">Product vision</p>
          <p className="text-lg sm:text-xl font-semibold text-slate-900 leading-relaxed">{preview.preview_summary}</p>
        </motion.div>
      )}

      {/* Top features — horizontal pills */}
      {feats.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.15, duration: 0.5, ease }}
        >
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400 mb-4">Top features</p>
          <div className="flex flex-wrap gap-2.5">
            {feats.map((f, i) => (
              <motion.span
                key={i}
                initial={{ opacity: 0, scale: 0.9 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: 0.15 + i * 0.05, duration: 0.35, ease }}
                className="inline-flex items-center gap-2 rounded-2xl bg-white border border-indigo-100 shadow-sm px-4 py-2.5 text-sm font-medium text-slate-800"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 shrink-0" />
                {f}
              </motion.span>
            ))}
          </div>
        </motion.div>
      )}

      {/* Meta chips */}
      {meta.length > 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.2, duration: 0.4, ease }}
          className="flex flex-wrap gap-3 pt-2 border-t border-slate-100"
        >
          {meta.map((m) => (
            <div key={m.label} className="flex items-center gap-2 text-sm">
              <span className="text-slate-400 font-medium">{m.label}:</span>
              <span className="font-semibold text-slate-900">{m.value}</span>
            </div>
          ))}
        </motion.div>
      )}
    </div>
  );
}

interface Props {
  preview: PreviewResponse;
  liveSiteAbove?: boolean;
  hideNavigator?: boolean;
}

export default function FullDeliveryPackage({ preview, liveSiteAbove = false, hideNavigator = false }: Props) {
  const blueprintSections = preview.mvp_blueprint
    ? parseMarkdownSections(preview.mvp_blueprint)
    : [];

  const hasAnalysis = hasReferenceAnalysis(preview);
  const navItems = buildDeliveryNavItems(preview, liveSiteAbove);

  let sectionNum = liveSiteAbove ? 2 : 1;
  const num = () => String(sectionNum++).padStart(2, '0');

  return (
    <div className="full-delivery-package space-y-5">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        className="text-center mb-2"
      >
        <p className="text-sm font-semibold text-indigo-600 mb-2">Everything included</p>
        <h2 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
          Your complete business version
        </h2>
        <p className="text-slate-500 mt-2 text-sm sm:text-base max-w-xl mx-auto leading-relaxed">
          Live product, strategic blueprint, technical roadmap, and build proposal — all custom for {preview.business_name}.
        </p>
      </motion.div>

      {!hideNavigator && <DeliveryNavigator items={navItems} />}

      {!liveSiteAbove && (
        <DeliverySection
          id="delivery-live-site"
          number={num()}
          eyebrow="Interactive product"
          title="Your full product preview"
          subtitle="Explore the site, booking flow, inbox, and admin dashboard inside the live window."
          defaultOpen
          accent="indigo"
        >
          <VisualDemoPreview demo={preview.visual_demo} businessName={preview.business_name} immersive mode="product" />
        </DeliverySection>
      )}

      <DeliverySection
        id="delivery-overview"
        number={num()}
        eyebrow="Executive summary"
        title="Your custom MVP concept"
        subtitle="Business-fit score, product promise, and the features that matter most."
        highlight
        defaultOpen
        accent="violet"
      >
        <OverviewCinematic preview={preview} />
      </DeliverySection>

      <DeliverySection
        id="delivery-analysis"
        number={num()}
        eyebrow="Reference intelligence"
        title="What we learned from your inspiration"
        subtitle="How we analyzed the tool you admire — and what we're adapting for your business."
        defaultOpen={hasAnalysis}
        accent="amber"
      >
        {hasAnalysis ? (
          <ReferenceAnalysisShowcase preview={preview} />
        ) : (
          <p className="text-sm text-slate-400 italic">No reference URL or screenshot was provided for this request.</p>
        )}
      </DeliverySection>

      <DeliverySection
        id="delivery-blueprint"
        number={num()}
        eyebrow="Strategic blueprint"
        title="Your MVP blueprint — full detail"
        subtitle="Every feature, screen, integration, journey, and timeline decision explained."
        defaultOpen
        accent="indigo"
      >
        {preview.mvp_blueprint ? (
          <BlueprintShowcase
            sections={blueprintSections}
            conceptName={preview.concept_name}
            fitScore={preview.business_fit_score}
          />
        ) : (
          <p className="text-sm text-slate-400 italic">Blueprint is still being generated.</p>
        )}
      </DeliverySection>

      <DeliverySection
        id="delivery-technical"
        number={num()}
        eyebrow="Product build plan"
        title="How your product comes to life"
        subtitle="Customer experience, owner tools, integrations, and build phases — explained clearly."
        defaultOpen={Boolean(preview.technical_plan)}
        accent="emerald"
      >
        {preview.technical_plan ? (
          <TechnicalShowcase content={preview.technical_plan} conceptName={preview.concept_name} />
        ) : (
          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-6 py-8 text-center">
            <p className="text-sm text-slate-500">Technical plan will appear here once generation completes.</p>
          </div>
        )}
      </DeliverySection>

      <DeliverySection
        id="delivery-proposal"
        number={num()}
        eyebrow="Ready to build"
        title="Your build proposal"
        subtitle="Scope, deliverables, timeline, and next steps — written specifically for you."
        defaultOpen
        highlight
        accent="violet"
      >
        {preview.proposal_draft ? (
          <ProposalShowcase content={preview.proposal_draft} conceptName={preview.concept_name} />
        ) : (
          <div className="rounded-xl border border-dashed border-indigo-200 bg-indigo-50/50 px-6 py-8 text-center">
            <p className="text-sm text-slate-500">Proposal will appear here once generation completes.</p>
          </div>
        )}
      </DeliverySection>
    </div>
  );
}
