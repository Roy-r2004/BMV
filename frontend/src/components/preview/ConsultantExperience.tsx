import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import type { PreviewResponse } from '../../types/request';
import type { BuildRequestContact } from '../../types/buildRequest';
import { API_BASE } from '../../api/client';
import { parseMarkdownSections } from '../../utils/parseMarkdownSections';
import {
  findSection,
  firstParagraph,
  firstSentence,
  parseListItems,
  splitFeatureLabel,
  splitH2Sections,
  splitH3Subsections,
  stripInlineMarkdown,
} from '../../utils/consultantMarkdown';
import AttractionImageGallery from './AttractionImageGallery';
import BlueprintShowcase from '../delivery/BlueprintShowcase';
import TechnicalShowcase from '../delivery/TechnicalShowcase';
import BuildRequestCTA from '../BuildRequestCTA';

const ease = [0.22, 1, 0.36, 1] as const;

/* ─── Tabs ───────────────────────────────────────────────────────────── */

type TabId = 'vision' | 'overview' | 'team' | 'blueprint' | 'technical' | 'build';

interface TabDef {
  id: TabId;
  label: string;
  show: (preview: PreviewResponse) => boolean;
}

const TABS: TabDef[] = [
  { id: 'vision', label: 'Vision', show: (p) => Boolean(p.generated_pages?.attraction_images?.length) },
  { id: 'overview', label: 'Overview', show: (p) => Boolean(p.preview_summary) },
  { id: 'team', label: 'AI Team', show: (p) => Boolean(p.ai_features?.length) },
  { id: 'blueprint', label: 'Blueprint', show: (p) => Boolean(p.mvp_blueprint) },
  { id: 'technical', label: 'Technical', show: (p) => Boolean(p.technical_plan) },
  { id: 'build', label: 'Start yours', show: () => true },
];

/* ─── Shared bits ────────────────────────────────────────────────────── */

/** Heroicons-24-outline paths shared by the deliverable pages. */
const UI_ICONS: Record<string, string> = {
  sparkle:
    'M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z',
  eye: 'M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  users:
    'M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z',
  chat: 'M12 20.25c4.97 0 9-3.694 9-8.25s-4.03-8.25-9-8.25S3 7.444 3 12c0 2.104.859 4.023 2.273 5.48.432.447.74 1.04.586 1.641a4.483 4.483 0 0 1-.923 1.785A5.969 5.969 0 0 0 6 21c1.282 0 2.47-.402 3.445-1.087.81.22 1.668.337 2.555.337Z',
  mail: 'M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75',
  bell: 'M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0',
  doc: 'M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z',
  shield:
    'M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z',
  flag: 'M3 3v1.5M3 21v-6m0 0 2.77-.693a9 9 0 0 1 6.208.682l.108.054a9 9 0 0 0 6.086.71l3.114-.732a48.524 48.524 0 0 1-.005-10.499l-3.11.732a9 9 0 0 1-6.085-.711l-.108-.054a9 9 0 0 0-6.208-.682L3 4.5M3 15V4.5',
  monitor:
    'M9 17.25v1.007a3 3 0 0 1-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0 1 15 18.257V17.25m6-12V15a2.25 2.25 0 0 1-2.25 2.25H5.25A2.25 2.25 0 0 1 3 15V5.25m18 0A2.25 2.25 0 0 0 18.75 3H5.25A2.25 2.25 0 0 0 3 5.25m18 0V12a2.25 2.25 0 0 1-2.25 2.25H5.25A2.25 2.25 0 0 1 3 12V5.25',
  cpu: 'M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a2.25 2.25 0 0 0 2.25-2.25V6.75a2.25 2.25 0 0 0-2.25-2.25H6.75A2.25 2.25 0 0 0 4.5 6.75v10.5a2.25 2.25 0 0 0 2.25 2.25Zm.75-12h9v9h-9v-9Z',
  layers:
    'M6.429 9.75 2.25 12l4.179 2.25m0-4.5 5.571 3 5.571-3m-11.142 0L2.25 7.5 12 2.25l9.75 5.25-4.179 2.25m0 0L21.75 12l-4.179 2.25m0 0 4.179 2.25L12 21.75 2.25 16.5l4.179-2.25m11.142 0-5.571 3-5.571-3',
  trophy:
    'M16.5 18.75h-9m9 0a3 3 0 0 1 3 3h-15a3 3 0 0 1 3-3m9 0v-3.375c0-.621-.503-1.125-1.125-1.125h-.871M7.5 18.75v-3.375c0-.621.504-1.125 1.125-1.125h.872m5.007 0H9.497m5.007 0a7.454 7.454 0 0 1-.982-3.172M9.497 14.25a7.454 7.454 0 0 0 .981-3.172M5.25 4.236c-.982.143-1.954.317-2.916.52A6.003 6.003 0 0 0 7.73 9.728M5.25 4.236V4.5c0 2.108.966 3.99 2.48 5.228M5.25 4.236V2.721C7.456 2.41 9.71 2.25 12 2.25c2.291 0 4.545.16 6.75.47v1.516M7.73 9.728a6.726 6.726 0 0 0 2.748 1.35m8.272-6.842V4.5c0 2.108-.966 3.99-2.48 5.228m2.48-5.492a46.32 46.32 0 0 1 2.916.52 6.003 6.003 0 0 1-5.395 4.972m0 0a6.726 6.726 0 0 1-2.749 1.35m0 0a6.772 6.772 0 0 1-3.044 0',
  grid: 'M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM3.75 15.75A2.25 2.25 0 0 1 6 13.5h2.25a2.25 2.25 0 0 1 2.25 2.25V18a2.25 2.25 0 0 1-2.25 2.25H6A2.25 2.25 0 0 1 3.75 18v-2.25ZM13.5 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 20.25 6v2.25A2.25 2.25 0 0 1 18 10.5h-2.25a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25A2.25 2.25 0 0 1 13.5 18v-2.25Z',
  user: 'M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z',
  check: 'M4.5 12.75l6 6 9-13.5',
  bolt: 'M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z',
  star: 'M11.48 3.499a.562.562 0 0 1 1.04 0l2.125 5.111a.563.563 0 0 0 .475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 0 0-.182.557l1.285 5.385a.562.562 0 0 1-.84.61l-4.725-2.885a.562.562 0 0 0-.586 0L6.982 21.08a.562.562 0 0 1-.84-.61l1.285-5.386a.562.562 0 0 0-.182-.557l-4.204-3.602a.562.562 0 0 1 .321-.988l5.518-.442a.563.563 0 0 0 .475-.345L11.48 3.5Z',
  calendar:
    'M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5',
  crosshair:
    'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0 0v-3.75m0-10.5V3m9 9h-3.75M6.75 12H3m12.75 0a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z',
};

function Icon({ path, className, strokeWidth = 1.7 }: { path: string; className?: string; strokeWidth?: number }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} className={className}>
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  );
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter((w) => /^[a-zA-Z]/.test(w))
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('');
}

function PageHeading({ eyebrow, title, subtitle }: { eyebrow: string; title: string; subtitle?: string }) {
  return (
    <div className="text-center max-w-2xl mx-auto mb-8 sm:mb-10 pt-8 sm:pt-10">
      <motion.p
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease }}
        className="text-[11px] font-bold uppercase tracking-[0.28em] mb-3 text-indigo-600"
      >
        {eyebrow}
      </motion.p>
      <motion.h2
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.06, duration: 0.55, ease }}
        className="text-2xl sm:text-[2.1rem] font-bold tracking-tight leading-tight text-slate-900"
      >
        {title}
      </motion.h2>
      {subtitle && (
        <motion.p
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.12, duration: 0.5, ease }}
          className="mt-3 text-sm sm:text-base leading-relaxed text-slate-500"
        >
          {subtitle}
        </motion.p>
      )}
    </div>
  );
}

/* ─── Pages ──────────────────────────────────────────────────────────── */

function VisionPage({ preview }: { preview: PreviewResponse }) {
  return (
    <div className="h-full min-h-0 flex flex-col px-2 sm:px-4 py-3">
      <AttractionImageGallery
        images={preview.generated_pages?.attraction_images ?? []}
        conceptName={preview.concept_name ?? undefined}
        businessName={preview.business_name}
      />
    </div>
  );
}

/** Small decorative vignettes cycled on the right of overview feature cards. */
function FeatureVignette({ variant }: { variant: number }) {
  switch (variant % 3) {
    case 0:
      return (
        <div className="flex flex-col items-end gap-2">
          <span className="rounded-lg bg-violet-100 px-2.5 py-1 text-[11px] font-bold text-violet-600">10:00 AM</span>
          <div className="relative h-2.5 w-28 rounded-full bg-violet-100 overflow-hidden">
            <div className="absolute inset-y-0 left-0 w-2/3 rounded-full bg-gradient-to-r from-violet-400 to-indigo-400" />
          </div>
        </div>
      );
    case 1:
      return (
        <div className="w-28 rounded-xl border border-slate-200/80 bg-slate-50/80 p-2.5">
          <div className="flex items-center gap-1.5 mb-2">
            <span className="w-5 h-5 rounded-md bg-violet-100 flex items-center justify-center text-violet-500">
              <Icon path={UI_ICONS.mail} className="w-3 h-3" strokeWidth={2} />
            </span>
            <span className="h-1.5 flex-1 rounded-full bg-slate-200" />
          </div>
          <div className="space-y-1.5">
            <span className="block h-1.5 w-full rounded-full bg-slate-200/80" />
            <span className="block h-1.5 w-2/3 rounded-full bg-slate-200/80" />
          </div>
        </div>
      );
    default:
      return (
        <div className="rounded-2xl border border-slate-200/80 bg-white px-4 py-2.5 shadow-sm flex items-center gap-1.5">
          {[0, 1, 2].map((d) => (
            <motion.span
              key={d}
              animate={{ opacity: [0.35, 1, 0.35] }}
              transition={{ duration: 1.4, repeat: Infinity, delay: d * 0.25 }}
              className="w-1.5 h-1.5 rounded-full bg-violet-400"
            />
          ))}
        </div>
      );
  }
}

const FEATURE_ICON_KEYS = ['calendar', 'bell', 'user', 'chat', 'grid'];

function OverviewPage({ preview }: { preview: PreviewResponse }) {
  const chips = (
    [
      [preview.industry, 'sparkle'],
      [`${preview.ai_features?.length ?? 0} AI employees`, 'users'],
      [`${preview.preview_features?.length ?? 0} core features`, 'star'],
    ] as Array<[string | null | undefined, string]>
  ).filter(([label]) => Boolean(label)) as Array<[string, string]>;
  const features = preview.preview_features ?? [];

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 pb-16">
      <motion.div
        initial={{ opacity: 0, y: 24, scale: 0.99 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.65, ease }}
        className="relative overflow-hidden rounded-[2rem] bg-slate-950 px-7 py-12 sm:px-14 sm:py-16 mt-6 sm:mt-10"
      >
        <motion.div
          aria-hidden
          animate={{ x: [0, 40, -20, 0], y: [0, -25, 15, 0] }}
          transition={{ duration: 18, repeat: Infinity, ease: 'easeInOut' }}
          className="absolute -top-28 -left-20 w-96 h-96 rounded-full bg-indigo-600/25 blur-3xl pointer-events-none"
        />
        <motion.div
          aria-hidden
          animate={{ x: [0, -35, 25, 0], y: [0, 20, -20, 0] }}
          transition={{ duration: 22, repeat: Infinity, ease: 'easeInOut' }}
          className="absolute -bottom-32 -right-16 w-[28rem] h-[28rem] rounded-full bg-fuchsia-600/20 blur-3xl pointer-events-none"
        />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_55%,rgba(2,6,23,0.7))] pointer-events-none" />

        {/* Orbit arcs + sparkles */}
        <div
          aria-hidden
          className="absolute -left-24 top-6 w-80 h-80 rounded-full border border-violet-400/15 pointer-events-none"
        />
        <div
          aria-hidden
          className="absolute -right-32 -bottom-16 w-96 h-96 rounded-full border border-fuchsia-400/15 pointer-events-none"
        />
        {[
          { className: 'top-10 left-[12%] w-3.5 h-3.5 text-violet-300/80', delay: 0 },
          { className: 'top-[30%] right-[8%] w-3 h-3 text-fuchsia-300/70', delay: 0.8 },
          { className: 'bottom-10 left-[22%] w-2.5 h-2.5 text-indigo-300/60', delay: 1.5 },
          { className: 'bottom-[26%] right-[20%] w-2.5 h-2.5 text-violet-200/60', delay: 2.1 },
        ].map((s, i) => (
          <motion.span
            key={i}
            aria-hidden
            animate={{ opacity: [0.2, 1, 0.2], scale: [0.8, 1.15, 0.8] }}
            transition={{ duration: 3.2, repeat: Infinity, delay: s.delay }}
            className={`absolute pointer-events-none ${s.className}`}
          >
            <Icon path={UI_ICONS.sparkle} className="w-full h-full" strokeWidth={1.4} />
          </motion.span>
        ))}

        <div className="relative max-w-3xl mx-auto text-center">
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.15, duration: 0.5 }}
            className="flex items-center justify-center gap-2 text-[11px] font-bold uppercase tracking-[0.32em] text-indigo-300 mb-5"
          >
            <Icon path={UI_ICONS.sparkle} className="w-4 h-4" strokeWidth={1.6} />
            The consulting verdict
          </motion.p>
          <motion.p
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.6, ease }}
            className="text-xl sm:text-2xl font-semibold text-slate-100 leading-relaxed sm:leading-relaxed"
          >
            {preview.preview_summary}
          </motion.p>
          {chips.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.32, duration: 0.5, ease }}
              className="mt-8 flex flex-wrap items-center justify-center gap-2"
            >
              {chips.map(([label, iconKey]) => (
                <span
                  key={label}
                  className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-1.5 text-xs font-semibold text-slate-300 backdrop-blur"
                >
                  <Icon path={UI_ICONS[iconKey]} className="w-3.5 h-3.5 text-violet-300" strokeWidth={1.8} />
                  {label}
                </span>
              ))}
            </motion.div>
          )}
        </div>
      </motion.div>

      {features.length > 0 && (
        <div className="mt-12 sm:mt-16">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4, duration: 0.5 }}
            className="flex items-center justify-center gap-4 mb-8"
          >
            <span aria-hidden className="h-px w-16 sm:w-28 bg-gradient-to-r from-transparent to-violet-300" />
            <span className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.28em] text-slate-500">
              <Icon path={UI_ICONS.sparkle} className="w-3.5 h-3.5 text-violet-400" strokeWidth={1.6} />
              Built in from day one
              <Icon path={UI_ICONS.sparkle} className="w-3.5 h-3.5 text-violet-400" strokeWidth={1.6} />
            </span>
            <span aria-hidden className="h-px w-16 sm:w-28 bg-gradient-to-l from-transparent to-violet-300" />
          </motion.div>
          <div className="grid sm:grid-cols-2 gap-4">
            {features.map((feature, i) => {
              const { title, sub } = splitFeatureLabel(feature);
              const lastOdd = i === features.length - 1 && features.length % 2 === 1;
              return (
                <motion.div
                  key={feature}
                  initial={{ opacity: 0, y: 18 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.45 + i * 0.08, duration: 0.5, ease }}
                  className={`flex items-center gap-5 rounded-3xl border border-slate-200/70 bg-white px-6 py-5 shadow-[0_16px_44px_-26px_rgba(15,23,42,0.35)] ${
                    lastOdd ? 'sm:col-span-2' : ''
                  }`}
                >
                  <span className="relative shrink-0 w-14 h-14 rounded-2xl bg-gradient-to-br from-violet-600 to-indigo-700 flex items-center justify-center text-white shadow-lg shadow-violet-600/25">
                    <Icon path={UI_ICONS[FEATURE_ICON_KEYS[i % FEATURE_ICON_KEYS.length]]} className="w-7 h-7" strokeWidth={1.6} />
                    <span className="absolute -bottom-1 -right-1 w-5 h-5 rounded-full bg-violet-500 ring-2 ring-white flex items-center justify-center">
                      <Icon path={UI_ICONS.check} className="w-3 h-3 text-white" strokeWidth={3} />
                    </span>
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[15px] font-bold text-slate-900 leading-snug">{title}</span>
                    {sub && <span className="mt-1 block text-sm text-slate-500 leading-relaxed">{sub}</span>}
                  </span>
                  <span className="hidden lg:block shrink-0">
                    <FeatureVignette variant={i} />
                  </span>
                </motion.div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/** Per-employee accent kit (literal class strings — Tailwind JIT needs them whole). */
const TEAM_ACCENTS = [
  {
    tile: 'from-indigo-500 via-violet-500 to-fuchsia-500',
    eyebrow: 'text-violet-300',
    card: 'border-violet-500/25 shadow-[0_0_90px_-26px_rgba(139,92,246,0.55)]',
    tint: 'from-violet-600/[0.14]',
    panel: 'border-violet-400/40 bg-violet-500/[0.06]',
    iconColor: '#c4b5fd',
    dot: 'bg-violet-400',
    iconKey: 'calendar',
  },
  {
    tile: 'from-emerald-400 via-teal-500 to-cyan-500',
    eyebrow: 'text-teal-300',
    card: 'border-teal-400/25 shadow-[0_0_90px_-26px_rgba(20,184,166,0.55)]',
    tint: 'from-teal-500/[0.14]',
    panel: 'border-teal-400/40 bg-teal-400/[0.06]',
    iconColor: '#5eead4',
    dot: 'bg-teal-400',
    iconKey: 'megaphone',
  },
  {
    tile: 'from-amber-400 via-orange-500 to-rose-500',
    eyebrow: 'text-amber-300',
    card: 'border-amber-400/25 shadow-[0_0_90px_-26px_rgba(245,158,11,0.5)]',
    tint: 'from-amber-500/[0.14]',
    panel: 'border-amber-400/40 bg-amber-400/[0.06]',
    iconColor: '#fcd34d',
    dot: 'bg-amber-400',
    iconKey: 'chart',
  },
  {
    tile: 'from-sky-400 via-blue-500 to-indigo-500',
    eyebrow: 'text-sky-300',
    card: 'border-sky-400/25 shadow-[0_0_90px_-26px_rgba(56,189,248,0.55)]',
    tint: 'from-sky-500/[0.14]',
    panel: 'border-sky-400/40 bg-sky-400/[0.06]',
    iconColor: '#7dd3fc',
    dot: 'bg-sky-400',
    iconKey: 'chat',
  },
];

const TEAM_ICON_PATHS: Record<string, string> = {
  calendar:
    'M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5m-9-6h.008v.008H12v-.008ZM12 15h.008v.008H12V15Zm0 2.25h.008v.008H12v-.008ZM9.75 15h.008v.008H9.75V15Zm0 2.25h.008v.008H9.75v-.008ZM7.5 15h.008v.008H7.5V15Zm0 2.25h.008v.008H7.5v-.008Zm6.75-4.5h.008v.008h-.008v-.008Zm0 2.25h.008v.008h-.008V15Zm0 2.25h.008v.008h-.008v-.008Zm2.25-4.5h.008v.008H16.5v-.008Zm0 2.25h.008v.008H16.5V15Z',
  megaphone:
    'M10.34 15.84c-.688-.06-1.386-.09-2.09-.09H7.5a4.5 4.5 0 1 1 0-9h.75c.704 0 1.402-.03 2.09-.09m0 9.18c.253.962.584 1.892.985 2.783.247.55.06 1.21-.463 1.511l-.657.38c-.551.318-1.26.117-1.527-.461a20.845 20.845 0 0 1-1.44-4.282m3.102.069a18.03 18.03 0 0 1-.59-4.59c0-1.586.205-3.124.59-4.59m0 9.18a23.848 23.848 0 0 1 8.835 2.535M10.34 6.66a23.847 23.847 0 0 0 8.835-2.535m0 0A23.74 23.74 0 0 0 18.795 3m.38 1.125a23.91 23.91 0 0 1 1.014 5.395m-1.014 8.855c-.118.38-.245.754-.38 1.125m.38-1.125a23.91 23.91 0 0 0 1.014-5.395m0-3.46c.495.413.811 1.035.811 1.73 0 .695-.316 1.317-.811 1.73m0-3.46a24.347 24.347 0 0 1 0 3.46',
  chart:
    'M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z',
  chat:
    'M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 0 1-.825-.242m9.345-8.334a2.126 2.126 0 0 0-.476-.095 48.64 48.64 0 0 0-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0 0 11.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155',
};

const TEAM_BENEFITS = [
  {
    title: '24/7 coverage',
    sub: 'Never miss a moment.',
    icon: 'M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
    chip: 'bg-indigo-100 text-indigo-600',
  },
  {
    title: 'Always on',
    sub: 'Working while you sleep.',
    icon: 'M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z',
    chip: 'bg-emerald-100 text-emerald-600',
  },
  {
    title: 'Included',
    sub: 'Built in. No extra cost.',
    icon: 'M4.5 12.75l6 6 9-13.5',
    chip: 'bg-sky-100 text-sky-600',
  },
];

function TeamPage({ preview }: { preview: PreviewResponse }) {
  const employees = preview.ai_features ?? [];

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 pb-16 pt-8 sm:pt-12">
      <div className="grid lg:grid-cols-[300px_1fr] gap-10 xl:gap-14 items-start">
        {/* Sticky intro column */}
        <div className="relative lg:sticky lg:top-6">
          <motion.p
            initial={{ opacity: 0, x: -14 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, ease }}
            className="text-[11px] font-bold uppercase tracking-[0.28em] text-indigo-600 mb-4"
          >
            Your new team
          </motion.p>
          <motion.h2
            initial={{ opacity: 0, x: -18 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.06, duration: 0.55, ease }}
            className="text-3xl sm:text-[2.6rem] font-bold tracking-tight leading-[1.08] text-slate-900"
          >
            Meet your
            <br />
            AI employees
          </motion.h2>
          <motion.div
            initial={{ opacity: 0, scaleX: 0 }}
            animate={{ opacity: 1, scaleX: 1 }}
            transition={{ delay: 0.2, duration: 0.45, ease }}
            className="origin-left mt-5 w-11 h-1 rounded-full bg-violet-500"
          />
          <motion.p
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.18, duration: 0.5, ease }}
            className="mt-5 text-[15px] leading-relaxed text-slate-500"
          >
            They start working for {preview.business_name} the day your product goes live — and they
            never clock out.
          </motion.p>

          <div className="mt-8 space-y-3">
            {TEAM_BENEFITS.map((benefit, i) => (
              <motion.div
                key={benefit.title}
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 + i * 0.1, duration: 0.5, ease }}
                className="flex items-center gap-3.5 rounded-2xl border border-slate-200/70 bg-white px-4 py-3 shadow-[0_10px_28px_-18px_rgba(15,23,42,0.25)]"
              >
                <span className={`shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${benefit.chip}`}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-5 h-5">
                    <path strokeLinecap="round" strokeLinejoin="round" d={benefit.icon} />
                  </svg>
                </span>
                <span>
                  <span className="block text-sm font-bold text-slate-900">{benefit.title}</span>
                  <span className="block text-xs text-slate-500">{benefit.sub}</span>
                </span>
              </motion.div>
            ))}
          </div>

          <div
            aria-hidden
            className="hidden lg:block mt-10 h-24 w-40 opacity-40 [background-image:radial-gradient(circle,#94a3b8_1px,transparent_1px)] [background-size:12px_12px]"
          />
        </div>

        {/* Employee cards with connector */}
        <div className="relative lg:pl-12 space-y-7">
          {employees.length > 1 && (
            <div
              aria-hidden
              className="hidden lg:block absolute left-2.5 top-24 bottom-24 w-px bg-slate-300/80"
            />
          )}
          {employees.map((emp, i) => {
            const accent = TEAM_ACCENTS[i % TEAM_ACCENTS.length];
            return (
              <motion.article
                key={emp.id}
                initial={{ opacity: 0, x: 40 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.2 + i * 0.16, duration: 0.65, ease }}
                className={`relative ${i % 2 === 1 ? 'lg:ml-8' : 'lg:mr-8'}`}
              >
                {/* Connector dot */}
                <span
                  aria-hidden
                  className={`hidden lg:block absolute top-[4.5rem] w-3.5 h-3.5 rounded-full ring-4 ring-[#f8fafc] ${accent.dot} ${
                    i % 2 === 1 ? '-left-[4.25rem]' : '-left-[3.25rem]'
                  }`}
                />
                <div className={`relative rounded-3xl border bg-slate-950 ${accent.card}`}>
                  <div className="absolute inset-0 rounded-3xl overflow-hidden pointer-events-none">
                    <div className={`absolute inset-0 bg-gradient-to-br ${accent.tint} via-transparent to-transparent`} />
                  </div>
                  <div className="relative flex items-stretch gap-6 p-6 sm:p-8">
                    <div className="flex-1 min-w-0 flex items-start gap-5">
                      <motion.div
                        initial={{ opacity: 0, scale: 0.7 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ delay: 0.32 + i * 0.16, duration: 0.5, ease }}
                        className={`sm:-ml-14 shrink-0 w-16 h-16 sm:w-20 sm:h-20 rounded-2xl bg-gradient-to-br ${accent.tile} flex items-center justify-center text-white font-bold text-xl sm:text-2xl shadow-xl`}
                      >
                        {initials(emp.name) || 'AI'}
                      </motion.div>
                      <div className="min-w-0">
                        <p className={`text-[11px] font-bold uppercase tracking-[0.24em] mb-1.5 ${accent.eyebrow}`}>
                          Employee {String(i + 1).padStart(2, '0')}
                        </p>
                        <h3 className="text-xl sm:text-2xl font-bold text-white tracking-tight">{emp.name}</h3>
                        <p className="mt-3 text-[15px] text-slate-400 leading-relaxed">{emp.description}</p>
                        <div className="mt-5 flex items-center gap-2">
                          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-400/10 border border-emerald-400/20 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-emerald-300">
                            <span className="relative flex h-1.5 w-1.5">
                              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
                              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-400" />
                            </span>
                            Always on
                          </span>
                          <span className="rounded-full bg-white/5 border border-white/10 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                            Included
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Neon icon panel */}
                    <div className="hidden md:flex shrink-0 items-center">
                      <div
                        className={`w-40 h-40 xl:w-44 xl:h-44 rounded-2xl border ${accent.panel} flex items-center justify-center`}
                      >
                        <svg
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke={accent.iconColor}
                          strokeWidth={1.1}
                          className="w-20 h-20"
                          style={{ filter: `drop-shadow(0 0 12px ${accent.iconColor}66)` }}
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" d={TEAM_ICON_PATHS[accent.iconKey]} />
                        </svg>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.article>
            );
          })}
        </div>
      </div>
    </div>
  );
}

const JOURNEY_ICON_KEYS = ['chat', 'bolt', 'doc', 'mail', 'bell'];
const SCOPE_ICON_KEYS = ['calendar', 'mail', 'user', 'chat', 'sparkle'];

/** Highlights the concept name inside a prose string. */
function ConceptProse({ text, conceptName }: { text: string; conceptName?: string | null }) {
  if (!conceptName || !text.includes(conceptName)) {
    return <>{text}</>;
  }
  const parts = text.split(conceptName);
  return (
    <>
      {parts.map((part, i) => (
        <span key={i}>
          {i > 0 && <span className="font-semibold text-violet-600">{conceptName}</span>}
          {part}
        </span>
      ))}
    </>
  );
}

function DocCard({
  icon,
  iconClass,
  eyebrow,
  eyebrowClass,
  children,
  className = '',
  delay = 0,
}: {
  icon: string;
  iconClass: string;
  eyebrow: string;
  eyebrowClass: string;
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.55, ease }}
      className={`rounded-3xl border border-slate-200/70 bg-white p-6 sm:p-7 shadow-[0_16px_44px_-28px_rgba(15,23,42,0.35)] ${className}`}
    >
      <div className="flex items-center gap-3.5 mb-4">
        <span className={`shrink-0 w-11 h-11 rounded-full flex items-center justify-center ${iconClass}`}>
          <Icon path={icon} className="w-5.5 h-5.5 w-[22px] h-[22px]" strokeWidth={1.7} />
        </span>
        <p className={`text-[11px] font-bold uppercase tracking-[0.22em] ${eyebrowClass}`}>{eyebrow}</p>
      </div>
      {children}
    </motion.div>
  );
}

function BlueprintPage({ preview }: { preview: PreviewResponse }) {
  const md = preview.mvp_blueprint ?? '';
  const secs = useMemo(() => splitH2Sections(md), [md]);
  const vision = findSection(secs, /vision/);
  const employeesSec = findSection(secs, /employee/);
  const featuresSec = findSection(secs, /feature/);
  const journeySec = findSection(secs, /experience|customer/);
  const winsSec = findSection(secs, /win/);

  // Unstructured document (old generations) — fall back to the generic showcase.
  if (!vision && !employeesSec) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 pb-16">
        <PageHeading
          eyebrow="Strategic blueprint"
          title="Your MVP blueprint — full detail"
          subtitle="The complete product thinking behind the visuals: vision, journeys, and why this wins."
        />
        <BlueprintShowcase
          sections={parseMarkdownSections(md)}
          conceptName={preview.concept_name}
          fitScore={preview.business_fit_score}
        />
      </div>
    );
  }

  const employees = employeesSec ? splitH3Subsections(employeesSec.body) : [];
  const employeeCards = employees.length
    ? employees
    : (preview.ai_features ?? []).map((f) => ({ title: f.name, text: f.description ?? '' }));
  const journeySteps = journeySec ? parseListItems(journeySec.body) : [];
  const winsIntro = winsSec ? firstParagraph(winsSec.body) : '';
  const winsChecks = winsSec ? parseListItems(winsSec.body) : [];
  const scopeItems = featuresSec ? parseListItems(featuresSec.body) : [];
  const scopeCards = scopeItems.length
    ? scopeItems.map((item) => {
        if (item.title) return { title: item.title, text: item.text };
        const { title, sub } = splitFeatureLabel(item.text);
        return { title, text: sub };
      })
    : (preview.preview_features ?? []).map((f) => {
        const { title, sub } = splitFeatureLabel(f);
        return { title, text: sub };
      });
  const visionText = vision ? stripInlineMarkdown(vision.body.replace(/\n+/g, ' ')) : '';

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 pb-16">
      <PageHeading
        eyebrow="Strategic blueprint"
        title="Your MVP blueprint — full detail"
        subtitle="The complete product thinking behind the visuals: vision, journeys, and why this wins."
      />

      {/* Hero banner */}
      <motion.div
        initial={{ opacity: 0, y: 22 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease }}
        className="relative overflow-hidden rounded-[2rem] bg-slate-950 px-7 py-10 sm:px-12 sm:py-12 mb-6"
      >
        <div aria-hidden className="absolute -top-20 -right-10 w-80 h-80 rounded-full bg-violet-600/20 blur-3xl pointer-events-none" />
        <div className="relative grid md:grid-cols-[1fr_auto] gap-8 items-center">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3.5 py-1.5 text-[10px] font-bold uppercase tracking-[0.22em] text-slate-300 mb-6">
              <span className="w-1.5 h-1.5 rounded-full bg-violet-400" />
              Strategic blueprint
            </span>
            <h3 className="text-3xl sm:text-[2.6rem] font-bold tracking-tight text-white leading-tight">
              {preview.concept_name ?? preview.business_name}
            </h3>
            <p className="mt-4 max-w-lg text-[15px] text-slate-400 leading-relaxed">
              {firstSentence(visionText) || preview.preview_summary}
            </p>
          </div>
          <div aria-hidden className="hidden md:block relative w-44 h-44 mr-2">
            <motion.div
              animate={{ scale: [1, 1.06, 1], opacity: [0.7, 1, 0.7] }}
              transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
              className="absolute inset-0 rounded-full bg-gradient-to-tr from-indigo-500/50 via-fuchsia-400/40 to-violet-500/50 blur-xl"
            />
            <div className="absolute inset-3 rounded-full bg-slate-900 ring-2 ring-violet-400/40 shadow-[0_0_60px_-10px_rgba(139,92,246,0.7)] flex items-center justify-center">
              <Icon path={UI_ICONS.sparkle} className="w-16 h-16 text-white" strokeWidth={1.2} />
            </div>
            <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-60 h-24 rounded-[100%] border border-violet-400/25 rotate-[-14deg]" />
          </div>
        </div>
      </motion.div>

      {/* The vision */}
      {visionText && (
        <DocCard
          icon={UI_ICONS.eye}
          iconClass="bg-violet-50 border border-violet-100 text-violet-500"
          eyebrow="The vision"
          eyebrowClass="text-violet-600"
          delay={0.1}
          className="mb-10"
        >
          <p className="text-[15px] text-slate-700 leading-relaxed">
            <ConceptProse text={visionText} conceptName={preview.concept_name} />
          </p>
        </DocCard>
      )}

      {/* AI employees */}
      {employeeCards.length > 0 && (
        <div className="mb-10">
          <p className="text-[11px] font-bold uppercase tracking-[0.24em] text-violet-600 mb-4">
            Your AI employees
          </p>
          <div className="relative grid md:grid-cols-2 gap-6">
            <div aria-hidden className="hidden md:flex absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 items-center gap-1.5 z-10">
              <span className="w-1.5 h-1.5 rounded-full bg-violet-300" />
              <span className="w-2 h-2 rounded-full bg-violet-400" />
              <span className="w-1.5 h-1.5 rounded-full bg-violet-300" />
            </div>
            {employeeCards.map((emp, i) => {
              const accent = TEAM_ACCENTS[i % TEAM_ACCENTS.length];
              return (
                <motion.div
                  key={emp.title}
                  initial={{ opacity: 0, y: 22 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.15 + i * 0.12, duration: 0.55, ease }}
                  className={`relative rounded-3xl border bg-slate-950 p-6 sm:p-7 ${accent.card}`}
                >
                  <div className="absolute inset-0 rounded-3xl overflow-hidden pointer-events-none">
                    <div className={`absolute inset-0 bg-gradient-to-br ${accent.tint} via-transparent to-transparent`} />
                  </div>
                  <div className="relative">
                    <div className="flex items-start gap-4 mb-4">
                      <span className={`shrink-0 w-14 h-14 rounded-2xl bg-gradient-to-br ${accent.tile} flex items-center justify-center text-white font-bold text-lg shadow-lg`}>
                        {initials(emp.title) || 'AI'}
                      </span>
                      <span>
                        <span className="block text-[10px] font-bold tracking-[0.22em] text-slate-500 mb-1">
                          {String(i + 1).padStart(2, '0')}
                        </span>
                        <span className={`block text-sm font-bold uppercase tracking-[0.14em] ${accent.eyebrow}`}>
                          {emp.title}
                        </span>
                      </span>
                    </div>
                    <p className="text-sm text-slate-400 leading-relaxed">{emp.text}</p>
                    <div className="mt-5 flex items-center gap-2">
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-400/10 border border-emerald-400/20 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-emerald-300">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                        Always on
                      </span>
                      <span className="rounded-full bg-white/5 border border-white/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Included
                      </span>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      )}

      {/* Journey + why this wins */}
      {(journeySteps.length > 0 || winsIntro) && (
        <div className="grid lg:grid-cols-2 gap-6 mb-12 items-start">
          {journeySteps.length > 0 && (
            <DocCard
              icon={UI_ICONS.users}
              iconClass="bg-violet-50 border border-violet-100 text-violet-500"
              eyebrow="How your customers will experience it"
              eyebrowClass="text-violet-600"
              delay={0.25}
            >
              <div className="relative space-y-5 pt-1">
                <span aria-hidden className="absolute left-[17px] top-3 bottom-3 w-px bg-violet-100" />
                {journeySteps.map((step, i) => (
                  <div key={i} className="relative flex items-start gap-4">
                    <span className="relative z-10 shrink-0 w-9 h-9 rounded-full bg-violet-600 text-white flex items-center justify-center shadow-md shadow-violet-600/30">
                      <Icon path={UI_ICONS[JOURNEY_ICON_KEYS[i % JOURNEY_ICON_KEYS.length]]} className="w-4.5 h-4.5 w-[18px] h-[18px]" strokeWidth={1.8} />
                    </span>
                    <p className="text-sm text-slate-700 leading-relaxed pt-1.5">{step.text || step.title}</p>
                  </div>
                ))}
              </div>
            </DocCard>
          )}
          {winsIntro && (
            <DocCard
              icon={UI_ICONS.trophy}
              iconClass="bg-emerald-50 border border-emerald-100 text-emerald-500"
              eyebrow="Why this wins"
              eyebrowClass="text-emerald-600"
              delay={0.3}
            >
              <p className="text-sm text-slate-700 leading-relaxed">
                <ConceptProse text={winsIntro} conceptName={preview.concept_name} />
              </p>
              {winsChecks.length > 0 && (
                <div className="mt-5">
                  {winsChecks.map((check, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-3.5 py-3 border-b border-slate-100 last:border-0"
                    >
                      <span className="shrink-0 w-6 h-6 rounded-full bg-emerald-500 flex items-center justify-center">
                        <Icon path={UI_ICONS.check} className="w-3.5 h-3.5 text-white" strokeWidth={3} />
                      </span>
                      <p className="text-sm font-medium text-slate-800">{check.text || check.title}</p>
                    </div>
                  ))}
                </div>
              )}
            </DocCard>
          )}
        </div>
      )}

      {/* Features & scope */}
      {scopeCards.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-5">
            <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.24em] text-violet-600">
              <Icon path={UI_ICONS.crosshair} className="w-4 h-4" strokeWidth={1.8} />
              Features &amp; scope
            </p>
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-violet-500">
              {scopeCards.length} included
            </p>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
            {scopeCards.map((card, i) => (
              <motion.div
                key={card.title}
                initial={{ opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.35 + i * 0.08, duration: 0.5, ease }}
                className="rounded-2xl border border-slate-200/70 bg-white p-5 shadow-[0_14px_36px_-26px_rgba(15,23,42,0.35)]"
              >
                <div className="flex items-start justify-between mb-4">
                  <span className="w-7 h-7 rounded-full bg-violet-100 text-violet-700 text-xs font-bold flex items-center justify-center">
                    {i + 1}
                  </span>
                  <Icon path={UI_ICONS[SCOPE_ICON_KEYS[i % SCOPE_ICON_KEYS.length]]} className="w-8 h-8 text-violet-500" strokeWidth={1.3} />
                </div>
                <p className="text-sm font-bold text-slate-900 leading-snug">{card.title}</p>
                {card.text && <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">{card.text}</p>}
              </motion.div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const PHASE_ICON_KEYS = ['monitor', 'cpu', 'calendar', 'grid', 'bell'];

function TechnicalPage({ preview }: { preview: PreviewResponse }) {
  const md = preview.technical_plan ?? '';
  const secs = useMemo(() => splitH2Sections(md), [md]);
  const arch = findSection(secs, /architecture/);
  const blocks = findSection(secs, /building blocks|components/);
  const aiWork = findSection(secs, /employees work|how the ai/);
  const implPhases = findSection(secs, /implementation/);
  const security = findSection(secs, /security|data/);

  if (!arch && !blocks && !aiWork) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 pb-16">
        <PageHeading
          eyebrow="Engineering plan"
          title="How your product comes to life"
          subtitle="Architecture, AI employee mechanics, and delivery phases — explained in plain language."
        />
        <TechnicalShowcase content={md} conceptName={preview.concept_name} />
      </div>
    );
  }

  const archText = arch ? stripInlineMarkdown(arch.body.replace(/\n+/g, ' ')) : '';
  const aiRows = aiWork
    ? (() => {
        const subs = splitH3Subsections(aiWork.body);
        if (subs.length) return subs;
        return parseListItems(aiWork.body).map((item) =>
          item.title ? item : { title: '', text: item.text },
        );
      })()
    : [];
  const securityRows = security ? parseListItems(security.body) : [];
  const buildPhases = blocks ? parseListItems(blocks.body).slice(0, 5) : [];
  const timeline = implPhases
    ? parseListItems(implPhases.body).map((item) => {
        if (item.title) return item;
        const split = item.text.match(/^(Phase\s*\d+[:.]?\s*[^:.]+)[:.]\s*(.*)$/i);
        return split ? { title: split[1].trim(), text: split[2].trim() } : item;
      })
    : [];

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 pb-16">
      <PageHeading
        eyebrow="Engineering plan"
        title="How your product comes to life"
        subtitle="Architecture, AI employee mechanics, and delivery phases — explained in plain language."
      />

      {/* Build plan banner */}
      <motion.div
        initial={{ opacity: 0, y: 22 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease }}
        className="relative overflow-hidden rounded-[2rem] bg-slate-950 px-7 py-9 sm:px-10 mb-6"
      >
        <div aria-hidden className="absolute -bottom-24 -right-10 w-96 h-64 rounded-full bg-violet-600/20 blur-3xl pointer-events-none" />
        <div className="relative flex items-center justify-between gap-8">
          <div className="flex items-center gap-5">
            <span className="shrink-0 w-14 h-14 rounded-full border border-violet-400/40 bg-violet-500/10 text-violet-300 flex items-center justify-center">
              <Icon path={UI_ICONS.layers} className="w-7 h-7" strokeWidth={1.5} />
            </span>
            <div>
              <p className="text-[11px] font-bold uppercase tracking-[0.24em] text-violet-300 mb-1.5">Build plan</p>
              <h3 className="text-xl sm:text-2xl font-bold tracking-tight text-white">
                {preview.concept_name ?? preview.business_name} — how it gets built
              </h3>
            </div>
          </div>
          {/* Stacked isometric plates */}
          <div aria-hidden className="hidden lg:block relative w-48 h-28 shrink-0">
            {[
              'bottom-0 right-0 w-44 h-24 bg-gradient-to-tr from-violet-700/40 to-fuchsia-600/30',
              'bottom-4 right-5 w-40 h-20 bg-gradient-to-tr from-indigo-600/50 to-violet-500/40',
              'bottom-8 right-10 w-36 h-16 bg-gradient-to-tr from-indigo-500/60 to-sky-500/50',
            ].map((cls, i) => (
              <div
                key={i}
                className={`absolute rounded-xl border border-white/10 backdrop-blur-sm ${cls}`}
                style={{ transform: 'skewY(-8deg)' }}
              />
            ))}
            <motion.span
              animate={{ opacity: [0.4, 1, 0.4] }}
              transition={{ duration: 2.6, repeat: Infinity }}
              className="absolute top-0 right-2 text-white"
            >
              <Icon path={UI_ICONS.sparkle} className="w-4 h-4" strokeWidth={1.6} />
            </motion.span>
          </div>
        </div>
      </motion.div>

      {/* Architecture overview */}
      {archText && (
        <DocCard
          icon={UI_ICONS.doc}
          iconClass="bg-violet-50 border border-violet-100 text-violet-500"
          eyebrow="Architecture overview"
          eyebrowClass="text-violet-600"
          delay={0.1}
          className="mb-6"
        >
          <p className="text-[15px] text-slate-700 leading-relaxed">
            <ConceptProse text={archText} conceptName={preview.concept_name} />
          </p>
        </DocCard>
      )}

      {/* AI employees mechanics + security */}
      {(aiRows.length > 0 || securityRows.length > 0) && (
        <div className="grid lg:grid-cols-2 gap-6 mb-6 items-start">
          {aiRows.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.18, duration: 0.55, ease }}
              className="rounded-3xl border border-slate-200/70 bg-white overflow-hidden shadow-[0_16px_44px_-28px_rgba(15,23,42,0.35)]"
            >
              <div className="flex items-center gap-3 bg-gradient-to-r from-amber-400 to-orange-500 px-6 py-4">
                <span className="w-9 h-9 rounded-xl bg-white/20 text-white flex items-center justify-center">
                  <Icon path={UI_ICONS.bolt} className="w-5 h-5" strokeWidth={1.8} />
                </span>
                <p className="text-[15px] font-bold text-white">How the AI Employees Work</p>
              </div>
              <div className="px-6 py-2 divide-y divide-slate-100">
                {aiRows.map((row, i) => {
                  const accent = TEAM_ACCENTS[i % TEAM_ACCENTS.length];
                  // Some generations format each employee's mechanics as a
                  // nested bullet list (Channels / Decisions / Logging) —
                  // re-parse the raw sub-body so those render as labeled
                  // rows instead of one paragraph with stray "*" markers.
                  const facets = row.raw ? parseListItems(row.raw) : [];
                  return (
                    <div key={i} className="flex items-start gap-4 py-5">
                      <span className={`shrink-0 w-11 h-11 rounded-xl bg-gradient-to-br ${accent.tile} flex items-center justify-center text-white font-bold text-sm shadow-md`}>
                        {initials(row.title) || 'AI'}
                      </span>
                      <span className="min-w-0 flex-1">
                        {row.title && <span className="block text-sm font-bold text-slate-900 mb-1.5">{row.title}</span>}
                        {facets.length > 0 ? (
                          <dl className="space-y-1.5">
                            {facets.map((facet, j) => (
                              <div key={j} className="flex gap-1.5 text-sm leading-relaxed">
                                {facet.title && (
                                  <dt className="shrink-0 font-semibold text-slate-500">{facet.title}:</dt>
                                )}
                                <dd className="text-slate-600">{facet.text}</dd>
                              </div>
                            ))}
                          </dl>
                        ) : (
                          <span className="block text-sm text-slate-600 leading-relaxed">{row.text}</span>
                        )}
                      </span>
                    </div>
                  );
                })}
              </div>
            </motion.div>
          )}
          {securityRows.length > 0 && (
            <DocCard
              icon={UI_ICONS.shield}
              iconClass="bg-emerald-50 border border-emerald-100 text-emerald-500"
              eyebrow="Data, security & reliability"
              eyebrowClass="text-emerald-600"
              delay={0.24}
            >
              <div className="space-y-4 pt-1">
                {securityRows.map((row, i) => (
                  <div key={i} className="flex items-start gap-3.5">
                    <span className="mt-0.5 shrink-0 w-5.5 h-5.5 w-[22px] h-[22px] rounded-full bg-emerald-500 flex items-center justify-center">
                      <Icon path={UI_ICONS.check} className="w-3 h-3 text-white" strokeWidth={3} />
                    </span>
                    <p className="text-sm text-slate-700 leading-relaxed">{row.text || row.title}</p>
                  </div>
                ))}
              </div>
            </DocCard>
          )}
        </div>
      )}

      {/* Build phases stepper */}
      {buildPhases.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3, duration: 0.55, ease }}
          className="rounded-3xl border border-slate-200/70 bg-white p-6 sm:p-8 mb-6 shadow-[0_16px_44px_-28px_rgba(15,23,42,0.35)]"
        >
          <p className="text-[11px] font-bold uppercase tracking-[0.24em] text-violet-600 mb-8">Build phases</p>
          <div className="relative grid grid-cols-2 md:grid-cols-5 gap-x-4 gap-y-8">
            <span aria-hidden className="hidden md:block absolute top-[18px] left-[10%] right-[10%] h-px bg-violet-100" />
            {buildPhases.map((phase, i) => (
              <div key={i} className="relative flex flex-col items-center text-center">
                <span className="relative z-10 w-9 h-9 rounded-full bg-violet-600 text-white text-sm font-bold flex items-center justify-center ring-4 ring-white shadow-md shadow-violet-600/30">
                  {i + 1}
                </span>
                <span className="mt-4 w-12 h-12 rounded-full bg-violet-50 border border-violet-100 text-violet-500 flex items-center justify-center">
                  <Icon path={UI_ICONS[PHASE_ICON_KEYS[i % PHASE_ICON_KEYS.length]]} className="w-6 h-6" strokeWidth={1.5} />
                </span>
                <p className="mt-3 text-sm font-bold text-slate-900 leading-snug">{phase.title || `Component ${i + 1}`}</p>
                <p className="mt-1.5 text-xs text-slate-500 leading-relaxed max-w-[170px]">{firstSentence(phase.text)}</p>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Implementation phases timeline */}
      {timeline.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.36, duration: 0.55, ease }}
          className="rounded-3xl border border-slate-200/70 bg-white p-6 sm:p-8 shadow-[0_16px_44px_-28px_rgba(15,23,42,0.35)]"
        >
          <p className="text-[11px] font-bold uppercase tracking-[0.24em] text-violet-600 mb-7">Implementation phases</p>
          <div className="relative space-y-7">
            <span aria-hidden className="absolute left-[5px] top-3 bottom-3 w-px bg-violet-200 border-l border-dashed border-violet-200" />
            {timeline.map((phase, i) => (
              <div key={i} className="relative grid sm:grid-cols-[auto_auto_1fr] items-start gap-4 sm:gap-6">
                <span className="relative z-10 mt-3 w-3 h-3 rounded-full bg-violet-600 ring-4 ring-white" />
                <span className="flex items-center gap-3.5">
                  <span className="w-11 h-11 rounded-xl bg-violet-50 border border-violet-100 text-violet-500 flex items-center justify-center">
                    <Icon path={UI_ICONS.flag} className="w-5 h-5" strokeWidth={1.6} />
                  </span>
                  <span className="text-sm font-bold text-slate-900 sm:w-64">{phase.title || phase.text}</span>
                </span>
                {phase.title && (
                  <p className="text-sm text-slate-600 leading-relaxed sm:pt-2.5">{phase.text}</p>
                )}
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}

function BuildPage({
  preview,
  onRequestBuild,
  demoView,
}: {
  preview: PreviewResponse;
  onRequestBuild: (contact: BuildRequestContact) => Promise<void>;
  demoView: boolean;
}) {
  const roleLabels = [
    ...new Set((preview.generated_pages?.attraction_images ?? []).map((img) => img.role_label)),
  ];
  const hasDeckData = Boolean(preview.mvp_blueprint || preview.ai_features?.length);
  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 pb-16">
      <PageHeading
        eyebrow="The next step"
        title="Make it real"
        subtitle={`Everything you just saw was designed for ${preview.business_name}. Ask us to build it, and we get to work.`}
      />

      {hasDeckData && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15, duration: 0.5, ease }}
          className="mb-8 flex justify-center"
        >
          <a
            href={`${API_BASE}/api/requests/${preview.id}/export/pptx`}
            className="group inline-flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-3.5 shadow-[0_10px_28px_-18px_rgba(15,23,42,0.3)] transition-all hover:border-indigo-200 hover:shadow-[0_14px_34px_-16px_rgba(79,70,229,0.35)]"
          >
            <span className="shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-orange-500 to-red-500 flex items-center justify-center text-white shadow-md">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-4.5 h-4.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
              </svg>
            </span>
            <span className="text-left">
              <span className="block text-sm font-bold text-slate-900">Export as presentation</span>
              <span className="block text-xs text-slate-500">A PowerPoint recap — your vision, images, and next steps</span>
            </span>
          </a>
        </motion.div>
      )}

      <BuildRequestCTA
        requestId={preview.id}
        conceptName={preview.concept_name}
        businessName={preview.business_name}
        industry={preview.industry}
        mainProblem={preview.main_problem}
        desiredOutcome={preview.desired_outcome}
        previewFeatures={preview.preview_features}
        aiFeatures={preview.ai_features}
        roleLabels={roleLabels}
        buildPlans={preview.build_plans}
        onRequestBuild={onRequestBuild}
        buildRequested={preview.build_requested}
        demoView={demoView}
      />
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4, duration: 0.7 }}
        className="text-center pt-10"
      >
        <div className="inline-flex flex-col items-center gap-1.5 rounded-2xl border border-slate-200 bg-white px-8 py-5 shadow-sm">
          <p className="text-[10px] font-bold uppercase tracking-[0.3em] text-slate-400">
            Prepared exclusively for
          </p>
          <p className="text-base font-bold text-slate-900 tracking-tight">{preview.business_name}</p>
          {preview.concept_name && (
            <p className="text-xs font-semibold text-indigo-600">{preview.concept_name}</p>
          )}
        </div>
      </motion.div>
    </div>
  );
}

/* ─── Experience shell ───────────────────────────────────────────────── */

interface Props {
  preview: PreviewResponse;
  onRequestBuild: (contact: BuildRequestContact) => Promise<void>;
  demoView: boolean;
}

export default function ConsultantExperience({ preview, onRequestBuild, demoView }: Props) {
  const tabs = TABS.filter((t) => t.show(preview));

  const initialTab = ((): TabId => {
    const fromHash = window.location.hash.replace('#', '') as TabId;
    return tabs.some((t) => t.id === fromHash) ? fromHash : (tabs[0]?.id ?? 'vision');
  })();
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);

  useEffect(() => {
    window.history.replaceState(null, '', `#${activeTab}`);
  }, [activeTab]);

  return (
    <div className="flex flex-col h-[calc(100dvh-3.6rem)] min-h-0">
      {/* Fixed switcher bar */}
      <div className="shrink-0 z-30 border-b border-slate-200/70 bg-white/85 backdrop-blur-xl">
        <div className="max-w-5xl mx-auto flex items-center justify-between gap-3 px-3 sm:px-6 py-2.5">
          {preview.concept_name ? (
            <span className="hidden md:block text-sm font-bold text-slate-900 tracking-tight truncate max-w-[180px]">
              {preview.concept_name}
            </span>
          ) : (
            <span className="hidden md:block" />
          )}
          <nav className="flex-1 md:flex-none flex items-center justify-center gap-1 overflow-x-auto scrollbar-none">
            {tabs.map((tab, i) => {
              const active = tab.id === activeTab;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className={`relative shrink-0 px-3.5 sm:px-4 py-1.5 rounded-full text-xs sm:text-[13px] font-semibold transition-colors duration-200 ${
                    active ? 'text-white' : 'text-slate-500 hover:text-slate-900'
                  }`}
                >
                  {active && (
                    <motion.span
                      layoutId="consultant-active-tab"
                      transition={{ type: 'spring', stiffness: 400, damping: 34 }}
                      className="absolute inset-0 rounded-full bg-slate-900 shadow-lg shadow-slate-900/20"
                    />
                  )}
                  <span className="relative flex items-center gap-1.5">
                    <span className={`text-[9px] font-bold ${active ? 'text-slate-400' : 'text-slate-300'}`}>
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    {tab.label}
                  </span>
                </button>
              );
            })}
          </nav>
          <span className="hidden md:block w-[180px]" />
        </div>
      </div>

      {/* Page area */}
      <div className="flex-1 min-h-0 relative">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.32, ease }}
            className={`absolute inset-0 ${activeTab === 'vision' ? 'overflow-hidden' : 'overflow-y-auto'}`}
          >
            {activeTab === 'vision' && <VisionPage preview={preview} />}
            {activeTab === 'overview' && <OverviewPage preview={preview} />}
            {activeTab === 'team' && <TeamPage preview={preview} />}
            {activeTab === 'blueprint' && <BlueprintPage preview={preview} />}
            {activeTab === 'technical' && <TechnicalPage preview={preview} />}
            {activeTab === 'build' && (
              <BuildPage preview={preview} onRequestBuild={onRequestBuild} demoView={demoView} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
