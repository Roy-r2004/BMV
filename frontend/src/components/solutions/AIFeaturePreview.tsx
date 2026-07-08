import type { AIFeatureCatalogItem } from '../../data/aiFeatureCatalog';
import { getFeaturePreviewLines } from '../../data/aiFeatureCatalog';

const ICONS: Record<string, string> = {
  spark: '✦',
  clock: '◷',
  zap: '⚡',
  chart: '▤',
  users: '◎',
  shield: '⛨',
};

interface Props {
  feature: AIFeatureCatalogItem;
  expanded?: boolean;
}

export default function AIFeaturePreview({ feature, expanded = false }: Props) {
  const lines = getFeaturePreviewLines(feature);
  const chips = feature.patch.aiChips ?? [];
  const primaryCta = feature.patch.ctaPrimary;
  const secondaryCta = feature.patch.ctaSecondary;
  const section = feature.patch.sections?.[0];

  if (!expanded) {
    return (
      <div className="mt-2 flex flex-wrap gap-1">
        {chips.slice(0, 3).map((chip) => (
          <span
            key={chip}
            className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-500/15 text-cyan-200 border border-cyan-400/20"
          >
            {chip}
          </span>
        ))}
        {lines.length > 0 && (
          <span className="text-[10px] text-slate-500 self-center">
            +{lines.length - (chips.length ? 1 : 0)} more
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="mt-3 rounded-xl border border-white/10 bg-black/30 p-3 space-y-3">
      <div className="flex items-center gap-2">
        <span className="w-7 h-7 rounded-lg bg-white/10 flex items-center justify-center text-cyan-300 text-sm">
          {ICONS[feature.icon] ?? '✦'}
        </span>
        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Live preview</p>
      </div>

      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {chips.map((chip) => (
            <span
              key={chip}
              className="text-[10px] px-2.5 py-1 rounded-full bg-white/10 text-slate-200 border border-white/10"
            >
              {chip}
            </span>
          ))}
        </div>
      )}

      {(primaryCta || secondaryCta) && (
        <div className="flex flex-wrap gap-2">
          {primaryCta && (
            <span className="text-[10px] px-3 py-1.5 rounded-lg bg-blue-600/80 text-white font-semibold">
              {primaryCta}
            </span>
          )}
          {secondaryCta && (
            <span className="text-[10px] px-3 py-1.5 rounded-lg border border-white/20 text-slate-300">
              {secondaryCta}
            </span>
          )}
        </div>
      )}

      {section && (
        <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2.5">
          <p className="text-xs font-semibold text-white">{section.title}</p>
          {section.body && <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">{section.body}</p>}
        </div>
      )}

      {feature.patch.heroStats && feature.patch.heroStats.length > 0 && (
        <div className="grid grid-cols-3 gap-2">
          {feature.patch.heroStats.map((stat) => (
            <div key={stat.label} className="rounded-lg bg-white/5 border border-white/10 px-2 py-2 text-center">
              <p className="text-sm font-bold text-white">{stat.value}</p>
              <p className="text-[9px] text-slate-500 uppercase tracking-wide">{stat.label}</p>
            </div>
          ))}
        </div>
      )}

      <ul className="space-y-1 pt-1 border-t border-white/5">
        {lines.map((line) => (
          <li key={line} className="text-[11px] text-slate-400 flex gap-2">
            <span className="text-cyan-500 shrink-0">→</span>
            <span>{line}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
