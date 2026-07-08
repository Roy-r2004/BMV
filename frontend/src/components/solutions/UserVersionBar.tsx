import type { SolutionOverlay } from '../../types/auth';
import { hasOverlayCustomizations } from '../../utils/mergeShowcaseOverlay';

interface Props {
  solutionName: string;
  overlay: SolutionOverlay;
  onEdit: () => void;
  onReset: () => void;
  resetting?: boolean;
}

export default function UserVersionBar({
  solutionName,
  overlay,
  onEdit,
  onReset,
  resetting,
}: Props) {
  const customized = hasOverlayCustomizations(overlay);

  return (
    <div className="user-version-bar mb-4 rounded-xl border border-cyan-400/30 bg-gradient-to-r from-cyan-500/15 via-blue-600/10 to-transparent px-4 py-3 sm:px-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-cyan-300 mb-1">
            Your personal copy
          </p>
          <p className="text-sm text-slate-200 leading-relaxed">
            {customized ? (
              <>
                Only <strong className="text-white">you</strong> see these edits on this {solutionName} demo.
                {overlay.businessName ? (
                  <span className="text-cyan-200/90"> · {overlay.businessName}</span>
                ) : null}
              </>
            ) : (
              <>
                This is <strong className="text-white">your</strong> workspace on the shared {solutionName} template.
                Edit with AI — other visitors still see the default demo.
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={onEdit}
            className="inline-flex items-center gap-1.5 rounded-full bg-cyan-500/20 border border-cyan-400/40 px-4 py-2 text-xs font-semibold text-cyan-100 hover:bg-cyan-500/30 transition-colors"
          >
            Edit with AI
          </button>
          {customized && (
            <button
              type="button"
              onClick={onReset}
              disabled={resetting}
              className="rounded-full border border-slate-500/40 px-3 py-2 text-xs font-medium text-slate-400 hover:text-slate-200 hover:border-slate-400/50 transition-colors disabled:opacity-50"
            >
              {resetting ? 'Resetting…' : 'Reset to template'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
