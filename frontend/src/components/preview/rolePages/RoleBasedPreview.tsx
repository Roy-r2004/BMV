import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import type { ReactElement } from 'react';
import type { GeneratedPages, GeneratedRole } from '../../../types/request';

interface Props {
  pages: GeneratedPages;
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

export default function RoleBasedPreview({ pages, conceptName, features }: Props) {
  const roles = pages.roles ?? [];
  const [activeRoleId, setActiveRoleId] = useState<string>(roles[0]?.id ?? '');
  const [currentPath, setCurrentPath] = useState('');
  const [canBack, setCanBack] = useState(false);
  const [canForward, setCanForward] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const activeRole: GeneratedRole | undefined = roles.find((r) => r.id === activeRoleId) ?? roles[0];

  const siteHtml = useMemo(() => {
    if (!activeRole) return '';
    if (activeRole.site_html) return activeRole.site_html;
    // Fallback: first page only if bundle missing
    return activeRole.pages?.[0]?.html ?? '';
  }, [activeRole]);

  const postToSite = useCallback((msg: object) => {
    iframeRef.current?.contentWindow?.postMessage(msg, '*');
  }, []);

  const handleRoleChange = (roleId: string) => {
    if (roleId === activeRoleId) return;
    setActiveRoleId(roleId);
    setCurrentPath('');
    setCanBack(false);
    setCanForward(false);
  };

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const data = event.data;
      if (!data || typeof data !== 'object') return;
      if (data.type === 'preview-url') {
        setCurrentPath(data.path ?? '');
        setCanBack(Boolean(data.canBack));
        setCanForward(Boolean(data.canForward));
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

  if (!roles.length || !activeRole) return null;

  const accent = activeRole.accent ?? '#6366f1';

  return (
    <div ref={rootRef} className="rbp-root">
      <div className="rbp-header">
        <div className="rbp-header__left">
          {conceptName && <span className="rbp-concept-name">{conceptName}</span>}
          <span className="rbp-live-badge">
            <span className="rbp-live-dot" />
            Live Preview
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
                  ? { background: role.accent + '22', color: role.accent, borderColor: role.accent + '55' }
                  : undefined
              }
            >
              <span className="rbp-role-chip__icon">{ROLE_ICONS[role.icon] ?? ROLE_ICONS.users}</span>
              {role.label}
            </button>
          ))}
        </div>

        <div className="rbp-header__right">
          <button type="button" className="rbp-fullscreen-btn" onClick={toggleFullscreen}>
            {isFullscreen ? (
              <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 9V4.5M9 9H4.5M9 15v4.5M9 15H4.5M15 9h4.5M15 9V4.5M15 15h4.5M15 15v4.5" />
              </svg>
            ) : (
              <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 8V4m0 0h4M4 4l5 5m11-5h-4m4 0v4m0 0l-5-5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
              </svg>
            )}
            <span>{isFullscreen ? 'Exit' : 'Fullscreen'}</span>
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
            <div className="rbp-navbtns">
              <button
                type="button"
                className="rbp-navbtn"
                disabled={!canBack}
                onClick={() => postToSite({ type: 'preview-back' })}
                aria-label="Back"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <button
                type="button"
                className="rbp-navbtn"
                disabled={!canForward}
                onClick={() => postToSite({ type: 'preview-forward' })}
                aria-label="Forward"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </button>
              <button
                type="button"
                className="rbp-navbtn"
                onClick={() => postToSite({ type: 'preview-go', pageId: activeRole.pages?.[0]?.id, pushHistory: false })}
                aria-label="Reload"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </button>
            </div>
          </div>

          <div className="rbp-urlbar">
            <svg className="rbp-lock" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <rect x="3" y="11" width="18" height="11" rx="2" />
              <path d="M7 11V7a5 5 0 0110 0v4" />
            </svg>
            <span className="rbp-url">{url}</span>
          </div>

          <div className="rbp-chrome__right">
            <span className="rbp-tab-role-hint" style={{ color: accent, fontSize: '0.65rem', fontWeight: 600 }}>
              {activeRole.label}
            </span>
          </div>
        </div>

        <div className="rbp-viewport rbp-viewport--site">
          {siteHtml ? (
            <iframe
              ref={iframeRef}
              key={activeRoleId}
              title={`${activeRole.label} — ${conceptName ?? 'Preview'}`}
              srcDoc={siteHtml}
              sandbox="allow-same-origin allow-scripts"
              className="rbp-iframe"
            />
          ) : (
            <div className="rbp-empty">
              <p>Website preview is being generated…</p>
            </div>
          )}
        </div>
      </div>

      {features && features.length > 0 && (
        <div className="rbp-features">
          <span className="rbp-features__label">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            Included in this MVP
          </span>
          <div className="rbp-features__list">
            {features.map((f) => (
              <span key={f} className="rbp-feature-chip">{f}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
