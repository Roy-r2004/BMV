/** Pure helpers for generation progress UI (elapsed, stalled, terminal). */

export interface ProgressSnapshot {
  stage: string;
  label: string;
  pct: number;
  detail: string;
  files_done: number;
  files_total: number;
  log: Array<{ t: number; msg: string }>;
  updated_at?: string;
  is_generating?: boolean;
  is_failed?: boolean;
  request_status?: string;
}

export const TERMINAL_STAGES = new Set([
  'done',
  'failed',
  'ready',
  'refine_done',
  'refine_failed',
  'refine_reverted',
]);

/** How long without progress updates before we show a "still working" reassurance. */
export const STALL_MS = 90_000;

export function isTerminalStage(stage: string | undefined | null): boolean {
  return TERMINAL_STAGES.has(String(stage || '').trim());
}

export function isFailedProgress(progress: ProgressSnapshot | null | undefined): boolean {
  if (!progress) return false;
  // Prefer API flag — intermediate stages like build_failed can heal and continue.
  if (typeof progress.is_failed === 'boolean') return progress.is_failed;
  if (progress.request_status === 'failed') return true;
  const stage = String(progress.stage || '').trim();
  return stage === 'failed' || stage === 'refine_failed';
}

export function formatElapsed(ms: number): string {
  const totalSec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  if (m <= 0) return `${s}s`;
  return `${m}m ${s.toString().padStart(2, '0')}s`;
}

export function isStalled(
  progress: ProgressSnapshot | null | undefined,
  nowMs: number,
  stallMs: number = STALL_MS,
): boolean {
  if (!progress || isTerminalStage(progress.stage) || isFailedProgress(progress)) {
    return false;
  }
  const updated = progress.updated_at ? Date.parse(progress.updated_at) : NaN;
  if (!Number.isFinite(updated)) return false;
  return nowMs - updated >= stallMs;
}
