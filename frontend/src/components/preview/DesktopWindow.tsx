import { useRef } from 'react';
import type { ReactNode } from 'react';

interface Props {
  title: string;
  url: string;
  children: ReactNode;
  canGoBack?: boolean;
  canGoForward?: boolean;
  onBack?: () => void;
  onForward?: () => void;
}

export default function DesktopWindow({
  title,
  url,
  children,
  canGoBack = false,
  canGoForward = false,
  onBack,
  onForward,
}: Props) {
  const windowRef = useRef<HTMLDivElement>(null);

  const openFullscreen = () => {
    windowRef.current?.requestFullscreen?.();
  };

  return (
    <div className="desktop-window-wrap" ref={windowRef}>
      <div className="desktop-window">
        <div className="desktop-window-titlebar">
          <div className="desktop-window-lights">
            <span className="desktop-light desktop-light--red" />
            <span className="desktop-light desktop-light--yellow" />
            <span className="desktop-light desktop-light--green" />
          </div>
          <p className="desktop-window-title max-w-[42vw] sm:max-w-none mx-1">{title}</p>
          <div className="w-8 sm:w-16 shrink-0" />
        </div>

        <div className="desktop-window-toolbar gap-2 sm:gap-3">
          <div className="flex items-center gap-1 shrink-0">
            <ToolbarBtn disabled={!canGoBack} onClick={onBack} label="Back">
              <path d="M15 18l-6-6 6-6" />
            </ToolbarBtn>
            <ToolbarBtn disabled={!canGoForward} onClick={onForward} label="Forward">
              <path d="M9 18l6-6-6-6" />
            </ToolbarBtn>
          </div>
          <div className="desktop-window-url flex-1 min-w-0">
            <svg viewBox="0 0 24 24" className="w-3.5 h-3.5 text-emerald-500 shrink-0" fill="currentColor">
              <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z" />
            </svg>
            <span className="truncate">{url}</span>
          </div>
          <span className="desktop-live-badge hidden sm:inline-flex">
            <span className="desktop-live-dot" />
            Live
          </span>
          <button type="button" className="desktop-fullscreen-btn" onClick={openFullscreen}>
            <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
              <path d="M8 3H5a2 2 0 0 0-2 2v3" />
              <path d="M16 3h3a2 2 0 0 1 2 2v3" />
              <path d="M8 21H5a2 2 0 0 1-2-2v-3" />
              <path d="M16 21h3a2 2 0 0 0 2-2v-3" />
            </svg>
            <span className="hidden sm:inline">Fullscreen</span>
          </button>
        </div>

        <div className="desktop-window-content">{children}</div>
      </div>
    </div>
  );
}

function ToolbarBtn({
  children,
  disabled,
  onClick,
  label,
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="desktop-toolbar-btn"
    >
      <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2">
        {children}
      </svg>
    </button>
  );
}
