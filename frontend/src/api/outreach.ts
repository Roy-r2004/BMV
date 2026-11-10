/**
 * GCC outreach: Roy's list (reviewer token) and a business's private report.
 * Both live on the consultation service, beside the consultation itself.
 */
import axios from 'axios';
import { CONSULTANT_API_BASE } from './consultant';

const client = axios.create({ baseURL: CONSULTANT_API_BASE });
const TOKEN_KEY = 'bmv_review_token';

export function getReviewToken(): string {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export function setReviewToken(token: string): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* a private window: the token is asked for again next time */
  }
}

const admin = () => ({ headers: { 'X-Review-Token': getReviewToken() } });

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
