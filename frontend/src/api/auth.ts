import { apiClient } from './client';
import type { AuthResponse, UserPublic } from '../types/auth';

const TOKEN_KEY = 'bmv_user_token';

export function getUserToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setUserToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function getUserAuthHeaders() {
  const token = getUserToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function signup(name: string, email: string, password: string): Promise<AuthResponse> {
  const { data } = await apiClient.post<AuthResponse>('/api/auth/signup', { name, email, password });
  setUserToken(data.token);
  return data;
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const { data } = await apiClient.post<AuthResponse>('/api/auth/login', { email, password });
  setUserToken(data.token);
  return data;
}

export async function fetchMe(): Promise<UserPublic> {
  const { data } = await apiClient.get<{ user: UserPublic }>('/api/auth/me', {
    headers: getUserAuthHeaders(),
  });
  return data.user;
}

export async function logoutUser() {
  try {
    await apiClient.post('/api/auth/logout', null, { headers: getUserAuthHeaders() });
  } finally {
    setUserToken(null);
  }
}
