const OWN_REQUEST_PREFIX = 'bmv:own-request:';

export function markOwnRequest(requestId: number) {
  sessionStorage.setItem(`${OWN_REQUEST_PREFIX}${requestId}`, '1');
}

export function isOwnRequest(requestId: number): boolean {
  return sessionStorage.getItem(`${OWN_REQUEST_PREFIX}${requestId}`) === '1';
}
