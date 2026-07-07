import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { getChatHistory, sendChatMessage } from '../api/requests';
import type { ChatMessage, ChatSendResponse, PreviewResponse } from '../types/request';
import { useAiStatus } from '../hooks/useAiStatus';

const WELCOME_MESSAGE =
  "This is your draft preview. Tell me what to change — colors, headlines, features, tab layout, home page sections, inbox copy, anything. We'll keep refining until you're happy. No limits.";

const SUGGESTIONS = [
  'Use a darker header with gold accents',
  'Put features before programs on the home page',
  'Rename the tabs for my coaching brand',
  'Add a habit-tracking feature',
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
  const aiStatus = useAiStatus(12000);
  const modelsPulling = aiStatus?.provider === 'ollama' && !aiStatus.ready;
  const modelsReady = !modelsPulling;
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const history = await getChatHistory(requestId);
        if (!active) return;
        setMessages(history);
      } catch {
        if (active) setError('Could not load chat history.');
      } finally {
        if (active) setLoadingHistory(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [requestId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, open, expanded]);

  const applyPreviewUpdate = (result: ChatSendResponse) => {
    if (!result.preview_updated) return;
    onPreviewUpdate({
      concept_name: result.concept_name ?? undefined,
      preview_summary: result.preview_summary ?? undefined,
      preview_features: result.preview_features ?? undefined,
      business_fit_score: result.business_fit_score ?? undefined,
      visual_demo: result.visual_demo ?? undefined,
    });
  };

  const handleSend = async (text?: string) => {
    const message = (text ?? input).trim();
    if (!message || loading) return;

    setInput('');
    setError('');
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
      if (result.preview_updated) {
        await onRefetchPreview?.();
      }
    } catch {
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      setError('Something went wrong. Please try again.');
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

  const panelClass = expanded
    ? 'fixed inset-4 sm:inset-auto sm:right-6 sm:bottom-6 sm:w-[min(520px,calc(100vw-3rem))] sm:h-[min(720px,calc(100dvh-6rem))]'
    : 'fixed right-4 bottom-4 w-[min(420px,calc(100vw-2rem))] h-[min(560px,calc(100dvh-6rem))]';

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
                  {loading && (
                    <div className="flex items-center gap-2 text-sm text-slate-400">
                      <span className="w-4 h-4 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
                      Updating your preview...
                    </div>
                  )}
                </>
              )}
              <div ref={bottomRef} />
            </div>

            {messages.length === 0 && !loadingHistory && (
              <div className="px-4 pb-2 flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => handleSend(s)}
                    disabled={loading}
                    className="text-xs px-3 py-1.5 rounded-full border border-white/10 bg-white/5 text-slate-300 hover:text-white hover:border-cyan-400/40 hover:bg-cyan-500/10 transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {error && (
              <div className="px-4 pb-2">
                <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>
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
                  disabled={loading || loadingHistory || !modelsReady}
                  placeholder={modelsReady ? "Describe what you'd like to change..." : 'Waiting for AI models to finish downloading...'}
                  className="preview-chat-input flex-1 resize-none rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none focus:border-cyan-400/50 focus:ring-2 focus:ring-cyan-400/15"
                />
                <button
                  type="button"
                  onClick={() => handleSend()}
                  disabled={loading || loadingHistory || !input.trim() || !modelsReady}
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
