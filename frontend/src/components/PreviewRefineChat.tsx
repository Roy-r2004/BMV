import { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  getChatHistory,
  getGenerationProgress,
  getPreview,
  sendChatMessage,
  type GenerationProgress,
} from '../api/requests';
import type { ChatMessage, ChatSendResponse, PreviewResponse } from '../types/request';
import { useAiStatus } from '../hooks/useAiStatus';

const WELCOME_MESSAGE =
  'Tell me what to change — pages, colors, roles, booking, copy, or the product name — and I’ll rebuild the live preview.';

const SUGGESTIONS = [
  { label: 'Darker, premium colors', prompt: 'Make the colors darker and more premium' },
  { label: 'Denser sample data', prompt: 'Add denser sample data on every list' },
  { label: 'Add online booking', prompt: 'Add online booking to the customer flow' },
  { label: 'Rename + new headline', prompt: 'Rename the product and refresh the headline' },
];

interface Props {
  requestId: number;
  onPreviewUpdate: (updates: Partial<PreviewResponse>) => void;
  onRefetchPreview?: () => Promise<void>;
}

export default function PreviewRefineChat({ requestId, onPreviewUpdate, onRefetchPreview }: Props) {
  const [open, setOpen] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia('(min-width: 768px)').matches : false,
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [error, setError] = useState('');
  const [rebuilding, setRebuilding] = useState(false);
  const [progress, setProgress] = useState<GenerationProgress | null>(null);
  const [lastFailedMessage, setLastFailedMessage] = useState('');
  const aiStatus = useAiStatus(12000);
  const modelsPulling = aiStatus?.provider === 'ollama' && !aiStatus.ready;
  const modelsReady = !modelsPulling;
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const pollActiveRef = useRef(false);

  const applyPreviewUpdate = useCallback((result: ChatSendResponse) => {
    if (!result.preview_updated && !result.preview_rebuild_started) return;
    onPreviewUpdate({
      concept_name: result.concept_name ?? undefined,
      preview_summary: result.preview_summary ?? undefined,
      preview_features: result.preview_features ?? undefined,
      business_fit_score: result.business_fit_score ?? undefined,
      visual_demo: result.visual_demo ?? undefined,
    });
  }, [onPreviewUpdate]);

  const pollUntilRebuildDone = useCallback(async () => {
    if (pollActiveRef.current) return;
    pollActiveRef.current = true;
    setRebuilding(true);
    setError('');
    try {
      for (let i = 0; i < 180; i += 1) {
        try {
          const snap = await getGenerationProgress(requestId);
          setProgress(snap);
        } catch {
          /* progress is best-effort */
        }
        await new Promise((r) => setTimeout(r, 2000));
        const preview = await getPreview(requestId);
        onPreviewUpdate({
          generated_pages: preview.generated_pages,
          concept_name: preview.concept_name ?? undefined,
          preview_summary: preview.preview_summary ?? undefined,
          preview_features: preview.preview_features ?? undefined,
          business_fit_score: preview.business_fit_score ?? undefined,
          visual_demo: preview.visual_demo ?? undefined,
        });
        const status = preview.generated_pages?.preview_app?.status;
        const refineErr = preview.generated_pages?.preview_app?.last_refinement_error;
        if (status === 'ready' || status === 'failed') {
          const history = await getChatHistory(requestId);
          setMessages(history);
          await onRefetchPreview?.();
          if (status === 'failed' || refineErr) {
            setError(
              refineErr
                ? `Edit issue: ${refineErr}`
                : 'Rebuild failed. Try a smaller change, or tap Retry.',
            );
          }
          break;
        }
        if (i === 179) {
          setError('Rebuild is taking longer than expected. Refresh the page or try again with a smaller change.');
        }
      }
    } catch {
      setError('Lost connection while rebuilding. Refresh to check status, or Retry.');
    } finally {
      setRebuilding(false);
      setProgress(null);
      pollActiveRef.current = false;
    }
  }, [onPreviewUpdate, onRefetchPreview, requestId]);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const history = await getChatHistory(requestId);
        if (!active) return;
        setMessages(history);
        const preview = await getPreview(requestId);
        if (!active) return;
        if (preview.generated_pages?.preview_app?.status === 'rebuilding') {
          onPreviewUpdate({ generated_pages: preview.generated_pages });
          void pollUntilRebuildDone();
        }
      } catch {
        if (active) setError('Could not load chat history.');
      } finally {
        if (active) setLoadingHistory(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [requestId, onPreviewUpdate, pollUntilRebuildDone]);

  useEffect(() => {
    if (!open) return;
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, rebuilding, open, progress]);

  useEffect(() => {
    document.documentElement.classList.toggle('refine-chat-open', open);
    return () => document.documentElement.classList.remove('refine-chat-open');
  }, [open]);

  const handleSend = async (text?: string) => {
    const message = (text ?? input).trim();
    if (!message || loading || rebuilding) return;

    setInput('');
    setError('');
    setLastFailedMessage(message);
    setLoading(true);

    const optimistic: ChatMessage = {
      id: Date.now(),
      role: 'user',
      content: message,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);

    try {
      const result = await sendChatMessage(requestId, message);
      const history = await getChatHistory(requestId);
      setMessages(history);
      applyPreviewUpdate(result);
      setLastFailedMessage('');
      if (result.preview_rebuild_started) {
        const preview = await getPreview(requestId);
        onPreviewUpdate({ generated_pages: preview.generated_pages });
        void pollUntilRebuildDone();
      } else if (result.preview_updated) {
        await onRefetchPreview?.();
      }
    } catch (err: unknown) {
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      const detail =
        typeof err === 'object' && err && 'response' in err
          ? String((err as { response?: { data?: { detail?: string } } }).response?.data?.detail || '')
          : '';
      setError(detail || 'Something went wrong. Please try again.');
      setInput(message);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const busy = loading || rebuilding;
  const progressLabel =
    progress?.label ||
    (rebuilding ? 'Rebuilding your live preview…' : loading ? 'AI is typing…' : '');
  const progressPct = typeof progress?.pct === 'number' ? progress.pct : null;
  const showSuggestions = !loadingHistory && messages.length === 0 && !busy;

  return (
    <>
      <AnimatePresence>
        {!open && (
          <motion.button
            initial={{ opacity: 0, scale: 0.92, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.92, y: 10 }}
            type="button"
            onClick={() => setOpen(true)}
            className="preview-chat-fab fixed right-4 bottom-4 z-50 inline-flex items-center gap-2.5 px-5 py-3.5 rounded-2xl bg-gradient-to-r from-blue-600 to-cyan-500 text-white font-semibold shadow-2xl shadow-blue-500/30"
          >
            <ChatIcon />
            Refine with AI
            {rebuilding && <span className="w-2 h-2 rounded-full bg-white animate-pulse" />}
          </motion.button>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {open && (
          <motion.aside
            initial={{ opacity: 0, x: 28 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 28 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            className="preview-refine-dock z-50 flex flex-col"
            aria-label="Refine preview chat"
          >
            <header className="preview-refine-dock__head shrink-0">
              <div className="min-w-0">
                <p className="preview-refine-dock__eyebrow">
                  <span className="preview-refine-dock__live" />
                  Unlimited revisions
                </p>
                <h3 className="preview-refine-dock__title">Refine preview</h3>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="preview-refine-dock__close"
                aria-label="Close chat"
              >
                <MinimizeIcon />
              </button>
            </header>

            <div className="preview-refine-dock__thread min-h-0 flex-1 overflow-y-auto overscroll-contain">
              {!modelsReady && (
                <div className="preview-refine-dock__banner">
                  AI models still downloading ({aiStatus?.models_ready_count ?? 0}/
                  {aiStatus?.models_required_count ?? 3}). Chat unlocks when ready.
                </div>
              )}

              {loadingHistory ? (
                <p className="preview-refine-dock__loading">Loading conversation…</p>
              ) : (
                <>
                  <MessageBubble role="assistant" content={WELCOME_MESSAGE} />
                  {messages.map((msg) => (
                    <MessageBubble key={msg.id} role={msg.role} content={msg.content} />
                  ))}
                  {busy && (
                    <TypingStatus label={progressLabel} pct={progressPct} detail={progress?.detail} />
                  )}
                  {showSuggestions && (
                    <div className="preview-refine-dock__suggestions">
                      <p className="preview-refine-dock__hint">Try one</p>
                      <div className="preview-refine-dock__suggestion-grid">
                        {SUGGESTIONS.map((s) => (
                          <button
                            key={s.prompt}
                            type="button"
                            onClick={() => handleSend(s.prompt)}
                            disabled={busy || !modelsReady}
                            className="preview-refine-dock__chip"
                          >
                            {s.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
              <div ref={bottomRef} />
            </div>

            {error && (
              <div className="preview-refine-dock__error shrink-0">
                <p>{error}</p>
                {lastFailedMessage && !busy && (
                  <button type="button" onClick={() => handleSend(lastFailedMessage)}>
                    Retry last message
                  </button>
                )}
              </div>
            )}

            <footer className="preview-refine-dock__composer shrink-0">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                rows={2}
                disabled={busy || loadingHistory || !modelsReady}
                placeholder={
                  rebuilding
                    ? progressLabel || 'Rebuilding…'
                    : modelsReady
                      ? 'Describe a change…'
                      : 'Waiting for AI models…'
                }
                className="preview-refine-dock__input"
              />
              <button
                type="button"
                onClick={() => handleSend()}
                disabled={busy || loadingHistory || !input.trim() || !modelsReady}
                className="preview-refine-dock__send"
                aria-label="Send message"
              >
                {busy ? <span className="preview-refine-dock__spinner" /> : <SendIcon />}
              </button>
            </footer>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
}

function TypingStatus({
  label,
  pct,
  detail,
}: {
  label: string;
  pct: number | null;
  detail?: string | null;
}) {
  return (
    <div className="preview-refine-dock__typing" role="status" aria-live="polite">
      <div className="preview-refine-dock__typing-row">
        <span className="preview-typing-dot" />
        <span className="preview-typing-dot" />
        <span className="preview-typing-dot" />
        <span className="preview-refine-dock__typing-label">{label || 'AI is typing…'}</span>
        {pct != null && <span className="preview-refine-dock__typing-pct">{pct}%</span>}
      </div>
      {detail && <p className="preview-refine-dock__typing-detail">{detail}</p>}
      {pct != null && (
        <div className="preview-refine-dock__typing-bar">
          <div style={{ width: `${Math.max(4, Math.min(100, pct))}%` }} />
        </div>
      )}
    </div>
  );
}

function MessageBubble({ role, content }: { role: 'user' | 'assistant'; content: string }) {
  const isUser = role === 'user';
  return (
    <div className={`preview-refine-dock__msg ${isUser ? 'is-user' : 'is-ai'}`}>
      <div className="preview-refine-dock__bubble">{content}</div>
    </div>
  );
}

function ChatIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function MinimizeIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M5 12h14" strokeLinecap="round" />
    </svg>
  );
}
