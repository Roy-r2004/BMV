/** What a visitor typed into the landing page's question box, carried to the
 *  consultation's front door. Session-scoped. Read without clearing — a
 *  visitor who has to sign in first comes back to /demo and must still find
 *  it — and cleared once the conversation actually starts. */
const KEY = 'bmv_front_door';

export function saveFrontDoor(text: string): void {
  try {
    if (text.trim()) sessionStorage.setItem(KEY, text.trim().slice(0, 2000));
  } catch {
    /* private mode: the consultation simply starts empty */
  }
}

export function peekFrontDoor(): string {
  try {
    return sessionStorage.getItem(KEY) ?? '';
  } catch {
    return '';
  }
}

export function clearFrontDoor(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* nothing to clear */
  }
}
