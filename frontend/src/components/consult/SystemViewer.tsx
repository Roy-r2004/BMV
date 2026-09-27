/**
 * Your system, screen by screen.
 *
 * The server renders the client's system as one navigable HTML document — a
 * sidebar and every screen, with sample data — and prints that same document
 * to the proposal PDF. Here it runs live inside a sandboxed frame. Pick a
 * screen from the list beside it, or click the sidebar inside the frame: the
 * two stay in step over postMessage. The frame is laid out for 1280px and
 * scales itself to whatever width it is given; it tells us its content height
 * so we can size it with no scrollbar of its own.
 *
 * Full screen is a second frame of the same document in a dark overlay. It
 * opens on the screen the reader was looking at, not the first one.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import type { SystemPayload, SystemScreen } from '../../api/consultant';

/** The width the frame's HTML is laid out at; it scales itself from here. */
const DESIGN_WIDTH = 1280;

type FrameMessage =
  | { type: 'bmv:shown'; id: string }
  | { type: 'bmv:size'; height: number }
  /** Optional. A key pressed inside the frame never reaches the page; a frame
   *  that forwards Escape closes full screen like the page's own Escape does. */
  | { type: 'bmv:key'; key: string };

/** Only the messages the frame is allowed to send, shaped as promised. */
function readMessage(data: unknown): FrameMessage | null {
  if (!data || typeof data !== 'object') return null;
  const m = data as { type?: unknown; id?: unknown; height?: unknown; key?: unknown };
  if (m.type === 'bmv:shown' && typeof m.id === 'string') return { type: 'bmv:shown', id: m.id };
  if (m.type === 'bmv:size' && typeof m.height === 'number' && Number.isFinite(m.height) && m.height > 0) {
    return { type: 'bmv:size', height: m.height };
  }
  if (m.type === 'bmv:key' && typeof m.key === 'string') return { type: 'bmv:key', key: m.key };
  return null;
}

function Frame({
  html,
  title,
  activeId,
  designHeight,
  onShown,
  onSize,
  onKey,
}: {
  html: string;
  title: string;
  /** The page's choice. Pushed into the frame whenever it changes. */
  activeId: string | null;
  /** The frame's content height at its design width, as it reported it. */
  designHeight: number | null;
  onShown: (id: string) => void;
  onSize: (height: number) => void;
  onKey?: (key: string) => void;
}) {
  const ref = useRef<HTMLIFrameElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  // What this frame last told us it shows, and whether it has spoken yet.
  // Its first report is its load: we answer that with the page's choice
  // rather than adopting it, so a frame opened later (full screen) lands on
  // the screen the reader had, not on the first one.
  const shown = useRef<string | null>(null);
  const loaded = useRef(false);
  const activeRef = useRef(activeId);
  activeRef.current = activeId;

  const post = useCallback((id: string) => {
    ref.current?.contentWindow?.postMessage({ type: 'bmv:show', id }, '*');
  }, []);

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      // The frame has an opaque origin, so its identity is its window.
      if (!ref.current || e.source !== ref.current.contentWindow) return;
      const m = readMessage(e.data);
      if (!m) return;
      if (m.type === 'bmv:size') {
        onSize(m.height);
        return;
      }
      if (m.type === 'bmv:key') {
        onKey?.(m.key);
        return;
      }
      if (!loaded.current) {
        loaded.current = true;
        const want = activeRef.current;
        if (want && want !== m.id) {
          shown.current = want;
          post(want);
          return;
        }
        shown.current = m.id;
        if (!want) onShown(m.id);
        return;
      }
      shown.current = m.id;
      onShown(m.id);
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [onKey, onShown, onSize, post]);

  // The page's choice goes into the frame — unless the frame is where it came from.
  useEffect(() => {
    if (!activeId || !loaded.current || shown.current === activeId) return;
    shown.current = activeId;
    post(activeId);
  }, [activeId, post]);

  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setWidth(el.getBoundingClientRect().width);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Its height at our width. Until it has said, 16:10 from the stylesheet.
  const height = designHeight && width ? Math.round((designHeight * width) / DESIGN_WIDTH) : null;

  return (
    <div className="cx-sys-frame" ref={wrapRef}>
      <iframe
        ref={ref}
        className="cx-sys-iframe"
        title={title}
        sandbox="allow-scripts"
        srcDoc={html}
        style={height ? { height } : undefined}
        onLoad={() => {
          // Should the document never announce itself, still put it on the
          // page's screen. Harmless when it does: the same screen twice.
          const want = activeRef.current;
          if (want && !loaded.current) post(want);
        }}
      />
    </div>
  );
}

function ScreenList({ screens, activeId, onPick }: { screens: SystemScreen[]; activeId: string | null; onPick: (id: string) => void }) {
  return (
    <nav className="cx-sys-list" aria-label="Screens">
      {screens.map((s, i) => {
        const on = s.id === activeId;
        return (
          <button
            key={s.id}
            type="button"
            className={`cx-sys-row${on ? ' on' : ''}`}
            aria-current={on ? 'true' : undefined}
            onClick={() => onPick(s.id)}
          >
            <span className="n">{String(i + 1).padStart(2, '0')}</span>
            <span className="t">
              <b>{s.title}</b>
              {on && s.caption ? <small>{s.caption}</small> : null}
            </span>
          </button>
        );
      })}
    </nav>
  );
}

function Caption({ screen }: { screen: SystemScreen | null }) {
  return (
    <div className="cx-sys-cap">
      <span className="cx-chip cx-chip--dim">Sample data</span>
      {screen ? (
        <p>
          <b>{screen.title}.</b> {screen.caption}
        </p>
      ) : null}
    </div>
  );
}

export default function SystemViewer({
  system,
  businessName,
  onDownloadPdf,
  compact,
}: {
  system: SystemPayload;
  businessName: string;
  /** Prints the proposal PDF. Shown only when given and the server can print. */
  onDownloadPdf?: () => Promise<void>;
  /** A partner's view. Navigation and the PDF are theirs too; kept for parity
   *  with the package and for whatever the read-only view gates next. */
  readOnly?: boolean;
  /** Inside a tab, under someone else's heading: tighter. */
  compact?: boolean;
}) {
  const screens = system.screens;
  const html = system.html ?? '';
  const [activeId, setActiveId] = useState<string | null>(screens[0]?.id ?? null);
  const [designHeight, setDesignHeight] = useState<number | null>(null);
  const [full, setFull] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  // The overlay is fixed to the viewport, so it must escape the animated
  // section it sits in (a transform there would pin it) — but stay inside
  // .cx, where the tokens live.
  const [host, setHost] = useState<HTMLElement | null>(null);

  const active = screens.find((s) => s.id === activeId) ?? screens[0] ?? null;
  const name = system.product?.name || 'Your system';
  const title = `${name} for ${businessName}`;
  const canPdf = Boolean(onDownloadPdf) && system.pdf_available;

  const onShown = useCallback((id: string) => setActiveId(id), []);
  const onSize = useCallback((h: number) => setDesignHeight(h), []);
  // Escape pressed inside the full-screen frame, when the frame forwards it.
  const onOverlayKey = useCallback((key: string) => {
    if (key === 'Escape') setFull(false);
  }, []);

  useEffect(() => {
    setHost(rootRef.current?.closest<HTMLElement>('.cx') ?? document.body);
  }, []);

  useEffect(() => {
    if (!full) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFull(false);
    };
    window.addEventListener('keydown', onKey);
    closeRef.current?.focus();
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', onKey);
    };
  }, [full]);

  const downloadPdf = async () => {
    if (!onDownloadPdf) return;
    setPdfBusy(true);
    setPdfError(null);
    try {
      await onDownloadPdf();
    } catch {
      setPdfError('The PDF could not be prepared just now. Try again in a moment.');
    } finally {
      setPdfBusy(false);
    }
  };

  if (!html || !screens.length) return null;

  const pdfButton = canPdf ? (
    <button type="button" className="cx-btn cx-btn--blue cx-btn--sm" onClick={downloadPdf} disabled={pdfBusy}>
      {pdfBusy ? 'Preparing…' : 'Download as PDF'}
    </button>
  ) : null;

  return (
    <div className={`cx-sys${compact ? ' compact' : ''}`} ref={rootRef}>
      <div className="cx-sys-head">
        <p className="cx-sys-name">
          {name}
          {system.product?.tagline ? <span> — {system.product.tagline}</span> : null}
        </p>
        <div className="cx-sys-tools">
          <button type="button" className="cx-btn cx-btn--ghost cx-btn--sm" onClick={() => setFull(true)}>
            Open full screen
          </button>
          {pdfButton}
        </div>
      </div>
      {pdfError ? <p className="cx-error" role="alert">{pdfError}</p> : null}

      <div className="cx-sys-grid">
        <ScreenList screens={screens} activeId={active?.id ?? null} onPick={setActiveId} />
        <div className="cx-sys-stage">
          <Frame html={html} title={title} activeId={active?.id ?? null} designHeight={designHeight} onShown={onShown} onSize={onSize} />
          <Caption screen={active} />
        </div>
      </div>

      {full && host
        ? createPortal(
            <div
              className="cx-sys-over"
              role="dialog"
              aria-modal="true"
              aria-label={`${title}, full screen`}
              onClick={(e) => e.target === e.currentTarget && setFull(false)}
            >
              <div className="cx-sys-over-bar">
                <p>
                  {title}
                  <span className="cx-chip cx-chip--dim">Sample data</span>
                </p>
                <div className="cx-sys-tools">
                  {pdfButton}
                  <button ref={closeRef} type="button" className="cx-btn cx-btn--ghost cx-btn--sm" onClick={() => setFull(false)}>
                    Close
                  </button>
                </div>
              </div>
              <div className="cx-sys-over-body">
                <ScreenList screens={screens} activeId={active?.id ?? null} onPick={setActiveId} />
                <div className="cx-sys-over-stage">
                  <Frame html={html} title={`${title}, full screen`} activeId={active?.id ?? null} designHeight={designHeight} onShown={onShown} onSize={onSize} onKey={onOverlayKey} />
                  <Caption screen={active} />
                </div>
              </div>
            </div>,
            host,
          )
        : null}
    </div>
  );
}
