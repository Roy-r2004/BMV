import axios from 'axios';

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.PROD ? '' : 'http://localhost:8001');

export { API_BASE };

export const apiClient = axios.create({
  baseURL: API_BASE,
});

export function getAdminHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const password = sessionStorage.getItem('admin_password');
  const adminToken = sessionStorage.getItem('admin_token');
  const userToken = localStorage.getItem('bmv_user_token');
  const token = adminToken || userToken;
  if (password) headers['X-Admin-Password'] = password;
  if (token) headers.Authorization = `Bearer ${token}`;
  // Legacy callers that only send password still work when password is set
  if (!headers['X-Admin-Password'] && !headers.Authorization) {
    headers['X-Admin-Password'] = '';
  }
  return headers;
}

export const ROY_WHATSAPP = import.meta.env.VITE_ROY_WHATSAPP_NUMBER || '';

/** The consultancy's inbox — the professional contact channel. Outbound
 *  CTAs build a prefilled mailto so the client sends one click and we get
 *  a subject line we can triage. */
export const CONSULTING_EMAIL = 'consulting@buildmyversion.com';

export function consultingEmailUrl(subject: string, body: string) {
  return `mailto:${CONSULTING_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

export function whatsappUrl(message: string) {
  const number = ROY_WHATSAPP.replace(/\D/g, '');
  return `https://wa.me/${number}?text=${encodeURIComponent(message)}`;
}
