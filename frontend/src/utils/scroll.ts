/** Fixed SiteNav height + breathing room */
export const SCROLL_OFFSET = 80;

export function scrollToTop(behavior: ScrollBehavior = 'auto') {
  window.scrollTo({ top: 0, left: 0, behavior });
}

export function scrollToId(id: string, behavior: ScrollBehavior = 'smooth'): boolean {
  const el = document.getElementById(id);
  if (!el) return false;

  const top = el.getBoundingClientRect().top + window.scrollY - SCROLL_OFFSET;
  window.scrollTo({ top: Math.max(0, top), left: 0, behavior });
  return true;
}

export function scrollToHash(hash: string, behavior: ScrollBehavior = 'smooth'): boolean {
  const id = hash.replace(/^#/, '');
  if (!id) return false;
  return scrollToId(id, behavior);
}

/** Retry until the target section exists (cross-route hash links). */
export function scrollToHashWhenReady(hash: string, maxAttempts = 12, intervalMs = 50) {
  if (!hash) {
    scrollToTop('auto');
    return () => {};
  }

  let attempts = 0;
  let cancelled = false;

  const tryScroll = () => {
    if (cancelled) return;
    if (scrollToHash(hash, 'smooth')) return;
    attempts += 1;
    if (attempts < maxAttempts) {
      window.setTimeout(tryScroll, intervalMs);
    }
  };

  requestAnimationFrame(() => {
    requestAnimationFrame(tryScroll);
  });

  return () => {
    cancelled = true;
  };
}
