import { apiClient } from './client';

export interface SiteChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export async function sendSiteChat(
  messages: SiteChatMessage[],
  pagePath?: string,
): Promise<string> {
  const { data } = await apiClient.post<{ reply: string }>(
    '/api/site-chat',
    { messages, page_path: pagePath || undefined },
    { timeout: 45000 },
  );
  return data.reply;
}
