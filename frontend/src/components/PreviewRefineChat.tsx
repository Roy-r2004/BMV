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
  "You can change anything here: the live preview app (pages, roles, colors, navigation), the experience plan, feature list, product name, summary, and marketing copy. Describe what you want — I'll rebuild the app and keep the plan in sync.";

const SUGGESTIONS = [
  'Make the colors darker and more premium',
  'Add denser sample data on every list',
  'Add online booking to the customer flow',
  'Rename the product and refresh the headline',
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
  const [expanded, setExpanded] = useState(false);
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
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, rebuilding, open, expanded, progress]);

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
    (rebuilding ? 'Rebuilding your live preview…' : loading ? 'Updating your preview...' : '');
  const progressPct = typeof progress?.pct === 'number' ? progress.pct : null;

  const panelClass = expanded
    ? 'fixed inset-4 sm:inset-auto sm:right-3 sm:bottom-3 sm:w-[min(280px,calc(100vw-1.5rem))] sm:h-[min(640px,calc(100dvh-4rem))]'
    : 'fixed right-3 bottom-3 w-[min(280px,calc(100vw-1.5rem))] h-[min(480px,calc(100dvh-4rem))]';

  return (
    <>
      <AnimatePresence>
        {!open && (
          <motion.button
            initial={{ opacity: 0, scale: 0.9, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 12 }}
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
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.96 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            className={`preview-chat-panel z-50 flex flex-col rounded-[1.75rem] border border-white/10 bg-deep/95 backdrop-blur-xl shadow-2xl shadow-blue-500/20 overflow-hidden ${panelClass}`}
          >
            <div className="preview-chat-header shrink-0 px-5 py-4 border-b border-white/10 bg-gradient-to-r from-blue-600/20 via-cyan-500/10 to-transparent">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-60" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-400" />
                    </span>
                    <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-300">Unlimited revisions</p>
                  </div>
                  <h3 className="text-lg font-bold text-white leading-tight">Refine your preview</h3>
                  <p className="text-xs text-slate-400 mt-1">Chat with AI to modify anything — no limits until you&apos;re satisfied.</p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    type="button"
                    onClick={() => setExpanded((v) => !v)}
                    className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                    aria-label={expanded ? 'Collapse chat' : 'Expand chat'}
                  >
                    {expanded ? <CollapseIcon /> : <ExpandIcon />}
                  </button>
                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                    aria-label="Minimize chat"
                  >
                    <MinimizeIcon />
                  </button>
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
              {!modelsReady && (
                <div className="rounded-xl border border-amber-400/25 bg-amber-500/10 px-4 py-3 text-xs text-amber-100 leading-relaxed">
                  AI models are still downloading ({aiStatus?.models_ready_count ?? 0}/{aiStatus?.models_required_count ?? 3} ready).
                  Chat refinements will work as soon as pulls finish.
                </div>
              )}
              {loadingHistory ? (
                <div className="flex items-center justify-center py-12 text-sm text-slate-500">Loading conversation...</div>
              ) : (
                <>
                  <MessageBubble role="assistant" content={WELCOME_MESSAGE} />
                  {messages.map((msg) => (
                    <MessageBubble key={msg.id} role={msg.role} content={msg.content} />
                  ))}
                  {busy && (
                    <div className="rounded-xl border border-cyan-400/20 bg-cyan-500/10 px-4 py-3 space-y-2">
                      <div className="flex items-center gap-2 text-sm text-cyan-100">
                        <span className="w-4 h-4 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin shrink-0" />
                        <span className="min-w-0 truncate">{progressLabel}</span>
                        {progressPct != null && (
                          <span className="ml-auto text-xs text-cyan-200/80 tabular-nums">{progressPct}%</span>
                        )}
                      </div>
                      {progress?.detail && (
                        <p className="text-[11px] text-cyan-200/70 truncate pl-6">{progress.detail}</p>
                      )}
                      {progressPct != null && (
                        <div className="h-1 rounded-full bg-white/10 overflow-hidden ml-6">
                          <div
                            className="h-full rounded-full bg-cyan-400 transition-all duration-500"
                            style={{ width: `${Math.max(4, Math.min(100, progressPct))}%` }}
                          />
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
              <div ref={bottomRef} />
            </div>

            {!loadingHistory && (
              <div className="px-4 pb-2 flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => handleSend(s)}
                    disabled={busy || !modelsReady}
                    className="text-xs px-3 py-1.5 rounded-full border border-white/10 bg-white/5 text-slate-300 hover:text-white hover:border-cyan-400/40 hover:bg-cyan-500/10 transition-colors disabled:opacity-40"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {error && (
              <div className="px-4 pb-2 space-y-2">
                <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>
                {lastFailedMessage && !busy && (
                  <button
                    type="button"
                    onClick={() => handleSend(lastFailedMessage)}
                    className="text-xs font-semibold text-cyan-300 hover:text-white transition-colors"
                  >
                    Retry last message
                  </button>
                )}
              </div>
            )}

            <div className="shrink-0 p-4 border-t border-white/10 bg-black/20">
              <div className="flex gap-2 items-end">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={onKeyDown}
                  rows={2}
                  disabled={busy || loadingHistory || !modelsReady}
                  placeholder={
                    rebuilding
                      ? progressLabel || 'Rebuilding live preview…'
                      : modelsReady
                        ? "Describe what you'd like to change..."
                        : 'Waiting for AI models to finish downloading...'
                  }
                  className="preview-chat-input flex-1 resize-none rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none focus:border-cyan-400/50 focus:ring-2 focus:ring-cyan-400/15"
                />
                <button
                  type="button"
                  onClick={() => handleSend()}
                  disabled={busy || loadingHistory || !input.trim() || !modelsReady}
                  className="shrink-0 w-11 h-11 rounded-xl bg-gradient-to-r from-blue-600 to-cyan-500 text-white flex items-center justify-center disabled:opacity-40 hover:shadow-lg hover:shadow-cyan-500/20 transition-all"
                  aria-label="Send message"
                >
                  <SendIcon />
                </button>
              </div>
              <p className="text-[10px] text-slate-500 mt-2 text-center">Press Enter to send · Shift+Enter for new line</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function MessageBubble({ role, content }: { role: 'user' | 'assistant'; content: string }) {
  const isUser = role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? 'bg-gradient-to-br from-blue-600 to-cyan-600 text-white rounded-br-md'
            : 'bg-white/8 border border-white/10 text-slate-200 rounded-bl-md'
        }`}
      >
        {content}
      </div>
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

function ExpandIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CollapseIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M4 14h6v6M14 4h6v6M14 10l7-7M3 21l7-7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
