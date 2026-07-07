import type { AiStatus } from '../api/ai';

interface Props {
  status: AiStatus | null;
  compact?: boolean;
}

export default function AiModelsBanner({ status, compact = false }: Props) {
  if (!status || status.ready || status.provider !== 'ollama') return null;

  const progress = status.models_required_count
    ? Math.round((status.models_ready_count / status.models_required_count) * 100)
    : 0;

  if (compact) {
    return (
      <div className="rounded-xl border border-amber-400/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
        <span className="font-semibold">AI models still downloading</span>
        <span className="text-amber-200/80"> — {status.models_ready_count}/{status.models_required_count} ready. Preview and chat will work when pulls finish.</span>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-amber-400/20 bg-gradient-to-r from-amber-500/10 via-orange-500/5 to-transparent p-5 sm:p-6">
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-amber-300 mb-2">First-time setup</p>
          <h3 className="text-lg font-bold text-white mb-2">AI models are still downloading</h3>
          <p className="text-sm text-amber-100/80 leading-relaxed max-w-2xl">
            {status.message} You can keep browsing — this page will update automatically once models are ready.
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-2xl font-bold text-amber-200">{status.models_ready_count}/{status.models_required_count}</p>
          <p className="text-xs text-amber-200/70">models ready</p>
        </div>
      </div>

      <div className="mt-4 h-2 rounded-full bg-white/10 overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-amber-400 to-orange-400 transition-all duration-700"
          style={{ width: `${Math.max(progress, 4)}%` }}
        />
      </div>

      {status.required_models.length > 0 && (
        <ul className="mt-4 grid sm:grid-cols-3 gap-2">
          {status.required_models.map((model) => (
            <li
              key={model.id}
              className={`rounded-xl px-3 py-2 text-xs border ${
                model.present
                  ? 'border-teal-400/30 bg-teal-500/10 text-teal-100'
                  : 'border-white/10 bg-white/5 text-slate-300'
              }`}
            >
              <span className="font-semibold block">{model.label}</span>
              <span className="opacity-80">{model.present ? 'Ready' : `Pulling ${model.name}...`}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
