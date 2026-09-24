/** A business's name as a headline can carry it: whole when it fits, its
 *  first two words when it would wrap a display line on its own. */
export function shortName(name: string | null | undefined): string {
  const n = (name ?? '').trim();
  if (!n) return 'your business';
  if (n.length <= 26) return n;
  return n.split(/\s+/).slice(0, 2).join(' ');
}
