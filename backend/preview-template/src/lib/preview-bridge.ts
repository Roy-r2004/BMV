type RoleHandler = (roleId: string, path?: string) => void;
type NavigateHandler = (path: string) => void;

let navigateHandler: NavigateHandler | null = null;
let linkGuardInstalled = false;

export function notifyParent(path: string, canBack = false, canForward = false) {
  try {
    window.parent.postMessage(
      { type: 'preview-url', path, canBack, canForward },
      '*',
    );
  } catch {
    /* iframe only */
  }
}

/**
 * Register React Router navigate so absolute <a href="/owner/..."> clicks can be
 * rewritten under the preview basename instead of escaping to the API host.
 */
export function registerPreviewNavigate(navigate: NavigateHandler) {
  navigateHandler = navigate;
  installPreviewLinkGuard();
}

function installPreviewLinkGuard() {
  if (linkGuardInstalled || typeof document === 'undefined') return;
  linkGuardInstalled = true;

  document.addEventListener(
    'click',
    (event) => {
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

      const target = event.target;
      if (!(target instanceof Element)) return;
      const anchor = target.closest('a');
      if (!(anchor instanceof HTMLAnchorElement)) return;
      if (anchor.target && anchor.target !== '' && anchor.target !== '_self') return;
      if (anchor.hasAttribute('download')) return;

      const hrefAttr = anchor.getAttribute('href');
      if (!hrefAttr || hrefAttr.startsWith('#')) return;
      if (/^(mailto|tel|sms):/i.test(hrefAttr)) return;

      let url: URL;
      try {
        url = new URL(hrefAttr, window.location.href);
      } catch {
        return;
      }
      if (url.origin !== window.location.origin) return;

      const base = String(import.meta.env.BASE_URL || '/').replace(/\/$/, '');
      const path = url.pathname;

      // Already under the preview mount — leave alone.
      if (base && (path === base || path.startsWith(`${base}/`))) return;

      // Escaped root-relative app path (e.g. /owner/dashboard on API host).
      if (!path.startsWith('/') || path.startsWith('/api/')) return;
      if (!navigateHandler) return;

      event.preventDefault();
      navigateHandler(`${path}${url.search}${url.hash}`);
    },
    true,
  );
}

export function setupPreviewBridge(onRoleChange: RoleHandler) {
  installPreviewLinkGuard();
  window.addEventListener('message', (event) => {
    const data = event.data;
    if (!data || typeof data !== 'object') return;
    if (data.type === 'preview-set-role') {
      const roleId = typeof data.roleId === 'string' ? data.roleId : '';
      const path = typeof data.path === 'string' ? data.path : undefined;
      onRoleChange(roleId, path);
    }
  });
}
