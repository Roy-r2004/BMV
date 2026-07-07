import axios from 'axios';

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.PROD ? '' : 'http://localhost:8000');

export { API_BASE };

export const apiClient = axios.create({
  baseURL: API_BASE,
});

export function getAdminHeaders() {
  const password = sessionStorage.getItem('admin_password');
  return { 'X-Admin-Password': password || '' };
}

export const ROY_WHATSAPP = import.meta.env.VITE_ROY_WHATSAPP_NUMBER || '';

export function whatsappUrl(message: string) {
  const number = ROY_WHATSAPP.replace(/\D/g, '');
  return `https://wa.me/${number}?text=${encodeURIComponent(message)}`;
}
