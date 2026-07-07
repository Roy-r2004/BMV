import { apiClient } from './client';
import type { DemoListResponse } from '../types/demo';

export async function listDemos(): Promise<DemoListResponse> {
  try {
    const { data } = await apiClient.get<DemoListResponse>('/api/requests/demos');
    return data;
  } catch {
    const { data } = await apiClient.get<DemoListResponse>('/api/demos');
    return data;
  }
}
