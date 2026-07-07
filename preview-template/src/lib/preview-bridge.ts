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

export function setupPreviewBridge(
  onRoleChange: (roleId: string, path?: string) => void,
) {
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
