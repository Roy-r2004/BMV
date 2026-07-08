import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { getSolutionChat, sendSolutionChat } from '../../api/solutionWorkspace';
import type { SolutionEditMessage, SolutionOverlay } from '../../types/auth';
import type { AIFeatureCatalogItem } from '../../data/aiFeatureCatalog';
import type { PreviewEditSelection } from './SolutionShowcaseDemo';
import AIFeatureCatalogPanel from './AIFeatureCatalogPanel';

const WELCOME =
  'This is your personal copy of the template. Tell me what to change — only you will see it. Other users and visitors still get the default demo.';

const SUGGESTIONS = [
  'Add a pricing section with 3 tiers as HTML',
  'Write CSS to make hero buttons round and gold #d4a853',
  'Add section "Our guarantee" with a money-back promise',
];

type EditTab = 'chat' | 'catalog';

interface Props {
  solutionId: string;
  solutionName: string;
  open: boolean;
  overlay: SolutionOverlay;
  onClose: () => void;
  onOverlayUpdate: (overlay: SolutionOverlay) => void;
  onFocusInPreview?: (feature: AIFeatureCatalogItem) => void;
  selectedEditTarget?: PreviewEditSelection | null;
}

export default function SolutionEditChat({
  solutionId,
  solutionName,
  open,
  overlay,
  onClose,
  onOverlayUpdate,
  onFocusInPreview,
  selectedEditTarget,
}: Props) {
  const [tab, setTab] = useState<EditTab>('catalog');
  const [messages, setMessages] = useState<SolutionEditMessage[]>([]);
  const [input, setInput] = useState('');
  const [attachment, setAttachment] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    let active = true;
    (async () => {
      setLoadingHistory(true);
      try {
        const data = await getSolutionChat(solutionId);
        if (!active) return;
        setMessages(data.messages);
        onOverlayUpdate(data.overlay ?? {});
      } catch {
        if (active) setError('Could not load your workspace.');
      } finally {
        if (active) setLoadingHistory(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [solutionId, open, onOverlayUpdate]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, open]);

  useEffect(() => {
    if (!open || !selectedEditTarget) return;
    setTab('chat');
    setInput(selectedEditTarget.prompt);
    requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.setSelectionRange(selectedEditTarget.prompt.length, selectedEditTarget.prompt.length);
    });
  }, [open, selectedEditTarget]);

  const handleSend = async (text?: string) => {
    const message = (text ?? input).trim();
    if (!message || loading) return;

    setInput('');
    setError('');
    setLoading(true);

    const optimistic: SolutionEditMessage = {
      id: Date.now(),
      role: 'user',
      content: attachment ? `${message}\n📎 ${attachment.name}` : message,
      attachment_name: attachment?.name ?? null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);
    const file = attachment;
    setAttachment(null);

    try {
      const result = await sendSolutionChat(solutionId, message, file);
      const history = await getSolutionChat(solutionId);
      setMessages(history.messages);
      onOverlayUpdate(result.overlay ?? {});
    } catch {
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      setError('Something went wrong. Please try again.');
      setInput(message);
      if (file) setAttachment(file);
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

  const refreshMessages = async () => {
    const history = await getSolutionChat(solutionId);
    setMessages(history.messages);
  };

  const handleFeatureIntegrated = (feature: AIFeatureCatalogItem) => {
    setExpanded(false);
    onFocusInPreview?.(feature);
  };

  const panelClass = expanded
    ? 'fixed inset-4 sm:inset-auto sm:right-6 sm:bottom-6 sm:w-[min(520px,calc(100vw-3rem))] sm:h-[min(720px,calc(100dvh-6rem))]'
    : 'fixed right-4 bottom-4 w-[min(420px,calc(100vw-2rem))] h-[min(560px,calc(100dvh-6rem))]';

  if (!open) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 24, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 24, scale: 0.96 }}
        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
        className={`preview-chat-panel z-[70] flex flex-col rounded-[1.75rem] border border-white/10 bg-deep/95 backdrop-blur-xl shadow-2xl shadow-blue-500/20 overflow-hidden ${panelClass}`}
      >
        <div className="preview-chat-header shrink-0 px-5 py-4 border-b border-white/10 bg-gradient-to-r from-blue-600/20 via-cyan-500/10 to-transparent">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-60" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-400" />
                </span>
                <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-300">Your version only</p>
              </div>
              <h3 className="text-lg font-bold text-white leading-tight">Edit {solutionName} with AI</h3>
              <p className="text-xs text-slate-400 mt-1">Click anything in the live preview to target it, then describe the change.</p>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                aria-label={expanded ? 'Collapse chat' : 'Expand chat'}
              >
                {expanded ? '⊟' : '⊞'}
              </button>
              <button
                type="button"
                onClick={onClose}
                className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                aria-label="Close chat"
              >
                ✕
              </button>
            </div>
          </div>
          <div className="flex gap-1 mt-3 p-1 rounded-xl bg-black/30 border border-white/10">
            <TabButton active={tab === 'catalog'} onClick={() => setTab('catalog')}>
              AI catalog
            </TabButton>
            <TabButton active={tab === 'chat'} onClick={() => setTab('chat')}>
              Chat
            </TabButton>
          </div>
        </div>

        {tab === 'catalog' ? (
          <div className="flex-1 overflow-y-auto px-4 py-4">
            <AIFeatureCatalogPanel
              solutionId={solutionId}
              overlay={overlay}
              onOverlayUpdate={onOverlayUpdate}
              onIntegrated={handleFeatureIntegrated}
              onRemoved={() => refreshMessages()}
            />
          </div>
        ) : (
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {loadingHistory ? (
            <div className="flex items-center justify-center py-12 text-sm text-slate-500">Loading your workspace…</div>
          ) : (
            <>
              <MessageBubble role="assistant" content={WELCOME} />
              {messages.map((msg) => (
                <MessageBubble key={msg.id} role={msg.role} content={msg.content} />
              ))}
              {loading && (
                <div className="flex items-center gap-2 text-sm text-slate-400">
                  <span className="w-4 h-4 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
                  Applying your changes…
                </div>
              )}
            </>
          )}
          <div ref={bottomRef} />
        </div>
        )}

        {tab === 'chat' && messages.length === 0 && !loadingHistory && (
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

        {tab === 'chat' && error && (
          <div className="px-4 pb-2">
            <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>
          </div>
        )}

        {tab === 'chat' && (
        <div className="shrink-0 p-4 border-t border-white/10 bg-black/20">
          {attachment && (
            <div className="mb-2 flex items-center gap-2 text-xs text-cyan-200 bg-cyan-500/10 border border-cyan-400/20 rounded-lg px-3 py-2">
              <span className="truncate flex-1">📎 {attachment.name}</span>
              <button type="button" onClick={() => setAttachment(null)} className="text-slate-400 hover:text-white">
                Remove
              </button>
            </div>
          )}
          <div className="flex gap-2 items-end">
            <input
              ref={fileRef}
              type="file"
              className="hidden"
              accept="image/*,.pdf,.txt,.doc,.docx"
              onChange={(e) => setAttachment(e.target.files?.[0] ?? null)}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={loading || loadingHistory}
              className="shrink-0 p-2.5 rounded-xl border border-white/10 text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
              aria-label="Attach file"
            >
              📎
            </button>
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              rows={2}
              disabled={loading || loadingHistory}
              placeholder="Describe your changes…"
              className="flex-1 resize-none rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none focus:border-cyan-400/50 focus:ring-1 focus:ring-cyan-400/30"
            />
            <button
              type="button"
              onClick={() => handleSend()}
              disabled={loading || loadingHistory || !input.trim()}
              className="shrink-0 px-4 py-3 rounded-xl bg-gradient-to-r from-blue-600 to-cyan-500 text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Send
            </button>
          </div>
        </div>
        )}
      </motion.div>
    </AnimatePresence>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 text-xs font-semibold py-2 rounded-lg transition-colors ${
        active ? 'bg-cyan-500/20 text-cyan-200' : 'text-slate-400 hover:text-white hover:bg-white/5'
      }`}
    >
      {children}
    </button>
  );
}

function MessageBubble({ role, content }: { role: 'user' | 'assistant'; content: string }) {
  const isUser = role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? 'bg-blue-600/80 text-white rounded-br-md'
            : 'bg-white/8 text-slate-200 border border-white/10 rounded-bl-md'
        }`}
      >
        {content}
      </div>
    </div>
  );
}
