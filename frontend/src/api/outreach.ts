/**
 * GCC outreach: Roy's list (admin sign-in) and a business's private report.
 * Both live on the consultation service, beside the consultation itself.
 */
import axios from 'axios';
import { getAdminHeaders } from './client';
import { CONSULTANT_API_BASE } from './consultant';

const client = axios.create({ baseURL: CONSULTANT_API_BASE });

// The same admin sign-in as the rest of the admin area.
const admin = () => ({ headers: getAdminHeaders() });

export type OutreachStatus =
  | 'queued'
  | 'sent'
  | 'replied'
  | 'call_booked'
  | 'not_interested'
  | 'skip'
  | 'removed';

export interface OutreachRow {
  id: number;
  name: string;
  city: string;
  kind: string;
  score: number;
  instagram: string | null;
  instagram_url: string | null;
  website: string | null;
  phone: string | null;
  what: string | null;
  reasons: string[];
  sources: string[];
  dm: string;
  followup: string;
  /** The report as chat messages, sent before the slides. */
  messages: string[];
  /** How many slides; each is at slides_url + its number, from 1. */
  slides: number;
  slides_url: string;
  report_url: string;
  status: OutreachStatus;
  queued_on: string | null;
  sent_at: string | null;
  opens: number;
  opened_first_at: string | null;
}

export interface OutreachList {
  rows: OutreachRow[];
  counts: Record<OutreachStatus, number>;
  spent: number;
  cap: number;
  running: boolean;
  daily: number;
  last_run: { day: string; found: number; queued: number; finished_at: string | null; stopped_because: string | null } | null;
}

export async function getOutreachList(status: OutreachStatus): Promise<OutreachList> {
  const { data } = await client.get<OutreachList>(`/api/outreach/list?status=${status}`, admin());
  return data;
}

export async function fillOutreach(): Promise<void> {
  await client.post('/api/outreach/fill', null, admin());
}

export async function setOutreachStatus(id: number, status: OutreachStatus): Promise<OutreachRow> {
  const { data } = await client.patch<OutreachRow>(`/api/outreach/${id}`, { status }, admin());
  return data;
}

/** Saves the business's slides, one file each (they need the admin sign-in, so they are fetched, not linked). */
export async function downloadOutreachSlides(row: OutreachRow): Promise<void> {
  for (let n = 1; n <= row.slides; n += 1) {
    const { data } = await client.get<Blob>(`${row.slides_url}${n}`, { ...admin(), responseType: 'blob' });
    const url = URL.createObjectURL(data);
    const a = document.createElement('a');
    a.href = url;
    a.download = `BMV for ${row.name} ${n}.png`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }
}

export interface OutreachReport {
  name: string;
  city: string;
  today: string;
  changes: { change: string; ai: string; day_to_day: string; difference: string }[];
  sources_note: string;
  sources: string[];
  email: string;
  book_subject: string;
  remove_subject: string;
}

export async function getOutreachReport(token: string, preview = false): Promise<OutreachReport> {
  const suffix = preview ? '?preview=1' : '';
  const { data } = await client.get<OutreachReport>(`/api/outreach/report/${encodeURIComponent(token)}${suffix}`);
  return data;
}

export function isForbidden(err: unknown): boolean {
  return axios.isAxiosError(err) && err.response?.status === 403;
}
