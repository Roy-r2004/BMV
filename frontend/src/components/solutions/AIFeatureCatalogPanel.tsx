import { useMemo, useState } from 'react';
import {
  getCatalogForSolution,
  isFeatureIntegrated,
  type AIFeatureCatalogItem,
} from '../../data/aiFeatureCatalog';
import { integrateAIFeature, removeAIFeature } from '../../api/solutionWorkspace';
import type { SolutionOverlay } from '../../types/auth';
import AIFeaturePreview from './AIFeaturePreview';

const CATEGORY_LABELS: Record<string, string> = {
  chat: 'Chat & Q&A',
  automation: 'Automation',
  scoring: 'Scoring',
  scheduling: 'Scheduling',
  reminders: 'Reminders',
  ops: 'Operations',
};

const ICONS: Record<string, string> = {
  spark: '✦',
  clock: '◷',
  zap: '⚡',
  chart: '▤',
  users: '◎',
  shield: '⛨',
};

interface Props {
  solutionId: string;
  overlay: SolutionOverlay;
  onOverlayUpdate: (overlay: SolutionOverlay) => void;
  onIntegrated?: (feature: AIFeatureCatalogItem, reply: string) => void;
  onRemoved?: (feature: AIFeatureCatalogItem, reply: string) => void;
}

export default function AIFeatureCatalogPanel({
  solutionId,
  overlay,
  onOverlayUpdate,
  onIntegrated,
  onRemoved,
}: Props) {
  const features = useMemo(() => getCatalogForSolution(solutionId), [solutionId]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [justAddedId, setJustAddedId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<'all' | 'added' | 'available'>('all');

  const integratedCount = features.filter((f) => isFeatureIntegrated(overlay, f.id)).length;

  const visible = useMemo(() => {
    if (filter === 'added') return features.filter((f) => isFeatureIntegrated(overlay, f.id));
    if (filter === 'available') return features.filter((f) => !isFeatureIntegrated(overlay, f.id));
    return features;
  }, [features, filter, overlay]);

  const handleIntegrate = async (feature: AIFeatureCatalogItem) => {
    if (isFeatureIntegrated(overlay, feature.id) || busyId) return;
    setError('');
    setBusyId(feature.id);
    try {
      const result = await integrateAIFeature(solutionId, feature.id);
      onOverlayUpdate(result.overlay ?? {});
      setJustAddedId(feature.id);
      window.setTimeout(() => setJustAddedId(null), 3200);
      onIntegrated?.(feature, result.reply);
      setPreviewId(null);
    } catch {
      setError('Could not add this feature. Try again.');
    } finally {
      setBusyId(null);
    }
  };

  const handleRemove = async (feature: AIFeatureCatalogItem) => {
    if (!isFeatureIntegrated(overlay, feature.id) || busyId) return;
    setError('');
    setBusyId(feature.id);
    try {
      const result = await removeAIFeature(solutionId, feature.id);
      onOverlayUpdate(result.overlay ?? {});
      onRemoved?.(feature, result.reply);
      setPreviewId(null);
    } catch {
      setError('Could not remove this feature. Try again.');
    } finally {
      setBusyId(null);
    }
  };

  if (!features.length) {
    return (
      <div className="text-sm text-slate-500 py-8 text-center">
        No pre-built AI features for this industry yet.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 px-1">
        <p className="text-xs text-slate-400">
          Browse, preview, and add AI to <span className="text-cyan-300">your copy only</span>.
        </p>
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 shrink-0">
          {integratedCount}/{features.length}
        </span>
      </div>

      <div className="flex gap-1 p-1 rounded-lg bg-black/30 border border-white/10">
        {(['all', 'available', 'added'] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setFilter(key)}
            className={`flex-1 text-[10px] font-semibold uppercase tracking-wider py-1.5 rounded-md transition-colors ${
              filter === key ? 'bg-white/10 text-white' : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            {key === 'all' ? 'All' : key === 'added' ? 'Added' : 'Available'}
          </button>
        ))}
      </div>

      {error && (
        <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>
      )}

      <div className="grid gap-2">
        {visible.map((feature) => {
          const done = isFeatureIntegrated(overlay, feature.id);
          const busy = busyId === feature.id;
          const previewOpen = previewId === feature.id;
          const justAdded = justAddedId === feature.id;
          return (
            <div
              key={feature.id}
              className={`rounded-xl border transition-all ${
                justAdded
                  ? 'catalog-just-added border-emerald-400/50'
                  : done
                    ? 'border-emerald-500/30 bg-emerald-500/10'
                    : 'border-white/10 bg-white/5'
              }`}
            >
              <div className="px-3.5 py-3">
                <div className="flex items-start gap-3">
                  <span
                    className={`shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-sm ${
                      done ? 'bg-emerald-500/20 text-emerald-300' : 'bg-white/10 text-cyan-300'
                    }`}
                  >
                    {done ? '✓' : ICONS[feature.icon] ?? '✦'}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-white">{feature.title}</span>
                      <span className="text-[10px] uppercase tracking-wider text-slate-500">
                        {CATEGORY_LABELS[feature.category] ?? feature.category}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{feature.description}</p>
                    {!previewOpen && <AIFeaturePreview feature={feature} />}
                  </div>
                </div>

                {previewOpen && <AIFeaturePreview feature={feature} expanded />}

                <div className="flex items-center gap-2 mt-3 pt-3 border-t border-white/5">
                  <button
                    type="button"
                    onClick={() => setPreviewId(previewOpen ? null : feature.id)}
                    className="text-[10px] font-semibold uppercase tracking-wider px-2.5 py-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                  >
                    {previewOpen ? 'Hide preview' : 'Preview'}
                  </button>
                  {done ? (
                    <div className="ml-auto flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => onIntegrated?.(feature, '')}
                        className="text-[10px] font-bold uppercase tracking-wider px-3 py-1.5 rounded-lg border border-cyan-400/30 text-cyan-200 hover:bg-cyan-500/10 transition-colors"
                      >
                        View
                      </button>
                      <button
                        type="button"
                        disabled={!!busyId}
                        onClick={() => handleRemove(feature)}
                        className="text-[10px] font-bold uppercase tracking-wider px-3 py-1.5 rounded-lg border border-red-400/30 text-red-300 hover:bg-red-500/10 transition-colors disabled:opacity-40"
                      >
                        {busy ? '…' : 'Remove'}
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      disabled={!!busyId}
                      onClick={() => handleIntegrate(feature)}
                      className="ml-auto text-[10px] font-bold uppercase tracking-wider px-3 py-1.5 rounded-lg bg-cyan-500/20 text-cyan-200 border border-cyan-400/30 hover:bg-cyan-500/30 transition-colors disabled:opacity-40"
                    >
                      {busy ? 'Adding…' : justAdded ? 'Viewing ↓' : '+ Add'}
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
