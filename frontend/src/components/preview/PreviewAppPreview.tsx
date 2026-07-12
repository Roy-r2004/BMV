import { useState, useRef, useEffect, useCallback } from 'react';
import type { ReactElement } from 'react';
import type { GeneratedPages, PreviewAppInfo } from '../../types/request';
import { API_BASE } from '../../api/client';

interface Props {
  pages: GeneratedPages;
  requestId: number;
  conceptName?: string;
  features?: string[];
}

const ROLE_ICONS: Record<string, ReactElement> = {
  users: (
    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  ),
  chart: (
    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  ),
};

function siteUrl(concept: string, path: string): string {
  const slug = concept.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'preview';
  return `${slug}.app${path || ''}`;
}

function resolvePreviewUrl(previewApp?: PreviewAppInfo | null): string | null {
  if (!previewApp?.url) return null;
  // Keep iframe up whenever we have a URL — including after refine errors that
  // leave status ready with last_refinement_error, or legacy failed+url cases.
  if (previewApp.status === 'failed' && !previewApp.url) return null;
  const path = previewApp.url.startsWith('/') ? previewApp.url : `/${previewApp.url}`;
  return `${API_BASE}${path}`;
}

/** Join preview base (`…/5/` or `…/5`) with an in-app path (`/owner/dashboard`). */
function previewSrcForPath(base: string, appPath: string): string {
  const root = base.endsWith('/') ? base.slice(0, -1) : base;
  if (!appPath || appPath === '/') return `${root}/`;
  return `${root}${appPath.startsWith('/') ? appPath : `/${appPath}`}`;
}

export default function PreviewAppPreview({ pages, requestId: _requestId, conceptName }: Props) {
  const previewApp = pages.preview_app;
  const roles = previewApp?.roles?.length ? previewApp.roles : pages.roles ?? [];
  const [activeRoleId, setActiveRoleId] = useState<string>(roles[0]?.id ?? '');
  const [currentPath, setCurrentPath] = useState(roles[0]?.defaultPath ?? '/');
  const rootRef = useRef<HTMLDivElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const previewBase = resolvePreviewUrl(previewApp);
  const activeRole = roles.find((r) => r.id === activeRoleId) ?? roles[0];
  // Only the role entry URL is baked into iframe src. In-app navigation stays
  // client-side via the preview bridge (changing src on every path would remount).
  const [iframeEntryPath, setIframeEntryPath] = useState(roles[0]?.defaultPath ?? '/');
  const iframeSrc = previewBase ? previewSrcForPath(previewBase, iframeEntryPath) : null;
  const isRebuilding = previewApp?.status === 'rebuilding';
  const refineError = previewApp?.last_refinement_error?.trim() || '';
  const accent = activeRole?.accent ?? '#6366f1';

  const postToApp = useCallback((msg: object) => {
    iframeRef.current?.contentWindow?.postMessage(msg, '*');
  }, []);

  const handleRoleChange = (roleId: string) => {
    if (roleId === activeRoleId) return;
    setActiveRoleId(roleId);
    const role = roles.find((r) => r.id === roleId);
    const nextPath = role?.defaultPath || '/';
    // Load under /api/preview-apps/{id}/… — never bare /owner/… on the API host
    // (that returns {"detail":"Not Found"} JSON).
    setIframeEntryPath(nextPath);
    setCurrentPath(nextPath);
    postToApp({ type: 'preview-set-role', roleId, path: nextPath });
  };

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const data = event.data;
      if (!data || typeof data !== 'object') return;
      if (data.type === 'preview-url') {
        setCurrentPath(data.path ?? '');
      }
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, []);

  const toggleFullscreen = async () => {
    if (!document.fullscreenElement) {
      await rootRef.current?.requestFullscreen?.();
      setIsFullscreen(true);
    } else {
      await document.exitFullscreen?.();
      setIsFullscreen(false);
    }
  };

  const url = siteUrl(conceptName ?? 'preview', currentPath);

  if (!iframeSrc) return null;

  return (
    <div ref={rootRef} className="rbp-root">
      <div className="rbp-header">
        <div className="rbp-header__left">
          {conceptName && <span className="rbp-concept-name">{conceptName}</span>}
          <span className="rbp-live-badge">
            <span className="rbp-live-dot" />
            
          </span>
        </div>

        <div className="rbp-role-switcher">
          {roles.map((role) => (
            <button
              key={role.id}
              type="button"
              onClick={() => handleRoleChange(role.id)}
              className={`rbp-role-chip ${activeRoleId === role.id ? 'rbp-role-chip--active' : ''}`}
              style={
                activeRoleId === role.id
                  ? { background: accent + '22', color: accent, borderColor: accent + '55' }
                  : undefined
              }
            >
              <span className="rbp-role-chip__icon">{ROLE_ICONS[role.icon ?? 'users'] ?? ROLE_ICONS.users}</span>
              {role.label}
            </button>
          ))}
        </div>

        <div className="rbp-header__right">
          <button type="button" className="rbp-fullscreen-btn" onClick={toggleFullscreen}>
            {isFullscreen ? 'Exit' : 'Fullscreen'}
          </button>
        </div>
      </div>

      <div className="rbp-browser">
        <div className="rbp-browser__chrome">
          <div className="rbp-chrome__left">
            <div className="rbp-dots">
              <span className="rbp-dot rbp-dot--red" />
              <span className="rbp-dot rbp-dot--yellow" />
              <span className="rbp-dot rbp-dot--green" />
            </div>
          </div>
          <div className="rbp-urlbar">
            <span className="rbp-url">{url}</span>
          </div>
          <div className="rbp-chrome__right">
            <span className="rbp-tab-role-hint" style={{ color: accent, fontSize: '0.65rem', fontWeight: 600 }}>
              {activeRole?.label}
            </span>
          </div>
        </div>

        <div className="rbp-viewport rbp-viewport--site relative min-h-[420px]">
          {refineError && !isRebuilding && (
            <div className="absolute top-0 inset-x-0 z-20 px-3 pt-3 pointer-events-none">
              <div className="mx-auto max-w-xl rounded-lg border border-amber-300/80 bg-amber-50 px-3 py-2 text-xs text-amber-900 shadow-sm pointer-events-auto">
                Last edit couldn&apos;t be applied safely — showing your previous version.
                <span className="block mt-0.5 text-amber-800/80 truncate">{refineError}</span>
              </div>
            </div>
          )}
          {isRebuilding && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm">
              <div className="text-center text-white px-4">
                <div className="w-10 h-10 border-2 border-white/30 border-t-white rounded-full animate-spin mx-auto mb-3" />
                <p className="text-sm font-medium">Applying your changes…</p>
              </div>
            </div>
          )}
          <iframe
            ref={iframeRef}
            key={`${iframeSrc}-${previewApp?.status ?? 'idle'}`}
            title={`${activeRole?.label ?? 'Preview'} — ${conceptName ?? 'Preview'}`}
            src={iframeSrc}
            className="rbp-iframe min-h-[420px]"
            allow="fullscreen"
          />
        </div>
      </div>

      {/* Features live in the delivery package below — keep the iframe tall */}
    </div>
  );
}

