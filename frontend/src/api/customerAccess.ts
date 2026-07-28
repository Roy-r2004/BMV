// Customer preview-access token storage.
//
// Generic to the request/preview flow. Previously lived in api/expandedPreview.ts,
// which was removed along with preview generator v2 — the Expanded Preview feature
// was built entirely on the v2 Tier 1 -> Tier 2 orchestration.
const ACCESS_KEY = (requestId: number) => `bmv_request_access_${requestId}`;

export function storeRequestAccessToken(requestId: number, token: string | null | undefined) {
  if (!token) return;
  try {
    sessionStorage.setItem(ACCESS_KEY(requestId), token);
  } catch {
    /* ignore */
  }
}

export function getRequestAccessToken(requestId: number): string | null {
  try {
    return sessionStorage.getItem(ACCESS_KEY(requestId));
  } catch {
    return null;
  }
}
