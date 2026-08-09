import { SITE_DESIGN } from './site-design';

/**
 * Motion identity (3.10) — the recipe's temperament as animation values,
 * resolved once in Python and read here with the same discipline as the
 * variant axes: emitted design is data, so every field is runtime-guarded
 * and falls back to the kit's long-standing entrance constants.
 */
export interface MotionIdentity {
  identity: string;
  /** cubic-bezier control points, always 4 finite numbers. */
  ease: [number, number, number, number];
  staggerMs: number;
  /** Reveal travel distance, a CSS length. */
  travel: string;
  reveal: string;
}

/** The kit's pre-3.10 entrance feel — the fallback when design carries none. */
const DEFAULT_IDENTITY: MotionIdentity = {
  identity: 'entrance-only',
  ease: [0.22, 1, 0.36, 1],
  staggerMs: 90,
  travel: '18px',
  reveal: 'fade-up',
};

function isEase(value: unknown): value is [number, number, number, number] {
  return (
    Array.isArray(value) &&
    value.length === 4 &&
    value.every((n) => typeof n === 'number' && Number.isFinite(n))
  );
}

export function motionIdentity(): MotionIdentity {
  const raw = SITE_DESIGN.motion;
  if (!raw) return DEFAULT_IDENTITY;
  const staggerMs =
    typeof raw.stagger_ms === 'number' && Number.isFinite(raw.stagger_ms) && raw.stagger_ms > 0
      ? raw.stagger_ms
      : DEFAULT_IDENTITY.staggerMs;
  return {
    identity: typeof raw.identity === 'string' && raw.identity ? raw.identity : DEFAULT_IDENTITY.identity,
    ease: isEase(raw.ease) ? raw.ease : DEFAULT_IDENTITY.ease,
    staggerMs,
    travel: typeof raw.travel === 'string' && raw.travel ? raw.travel : DEFAULT_IDENTITY.travel,
    reveal: typeof raw.reveal === 'string' && raw.reveal ? raw.reveal : DEFAULT_IDENTITY.reveal,
  };
}
