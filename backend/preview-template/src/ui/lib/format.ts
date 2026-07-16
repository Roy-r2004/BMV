import { format, formatDistanceToNow, isValid, parseISO, type Locale } from 'date-fns';

function toValidDate(value: string | Date): Date | null {
  const date = typeof value === 'string' ? parseISO(value) : value;
  return isValid(date) ? date : null;
}

/** Local date helpers — pages never import date-fns directly. */
export function formatDate(value: string | Date, pattern = 'MMM d, yyyy', locale?: Locale): string {
  const date = toValidDate(value);
  if (!date) return typeof value === 'string' ? value : '';
  return format(date, pattern, locale ? { locale } : undefined);
}

export function formatRelative(value: string | Date): string {
  const date = toValidDate(value);
  if (!date) return typeof value === 'string' ? value : '';
  return formatDistanceToNow(date, { addSuffix: true });
}

export function formatTime(value: string | Date, pattern = 'HH:mm'): string {
  return formatDate(value, pattern);
}
