/** How a capacity picture is said out loud: times as an owner says them,
 *  counts with separators, and the one-line headline under the drawing. */
import type { CapacityPicture } from '../api/consultant';

export function sayTime(t: string | null | undefined): string {
  if (!t) return '';
  const [h, m] = t.split(':').map(Number);
  if (Number.isNaN(h)) return t;
  const suffix = h < 12 ? 'am' : 'pm';
  const h12 = h % 12 || 12;
  return m ? `${h12}:${String(m).padStart(2, '0')}${suffix}` : `${h12}${suffix}`;
}

export function fmt(n: number | null | undefined): string {
  if (n == null) return '';
  return Number.isInteger(n) ? n.toLocaleString('en-US') : n.toLocaleString('en-US', { maximumFractionDigits: 1 });
}

/** The sentence under the drawing: what it says, in their units. */
export function weekHeadline(p: CapacityPicture): string {
  if (p.shape === 'total') {
    return p.taken != null
      ? `${fmt(p.taken)} of ${fmt(p.capacity)} ${p.unit_plural} used a ${p.period ?? 'week'}`
      : `${fmt(p.capacity)} ${p.unit_plural} a ${p.period ?? 'week'}`;
  }
  return p.taken != null
    ? `${fmt(p.taken)} of ${fmt(p.capacity)} ${p.unit_plural} taken every week`
    : `${fmt(p.capacity)} ${p.unit_plural} every week`;
}
