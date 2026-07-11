import { useCallback, useState } from 'react';

interface Props {
  requestId: number;
  conceptName?: string | null;
  className?: string;
}

/** One-click share of the clean viewer link (`/share/{id}`). */
export default function ShareDemoButton({ requestId, conceptName, className = '' }: Props) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');

  const shareUrl = typeof window !== 'undefined'
    ? `${window.location.origin}/share/${requestId}`
    : `/share/${requestId}`;

  const title = conceptName?.trim() || 'Live product demo';

  const copyLink = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setError('');
      window.setTimeout(() => setCopied(false), 2200);
    } catch {
      setError('Could not copy — select and copy the link manually.');
    }
  }, [shareUrl]);

  const handleShare = useCallback(async () => {
    setError('');
    if (typeof navigator !== 'undefined' && typeof navigator.share === 'function') {
      try {
        await navigator.share({
          title,
          text: `Check out ${title} — a live product preview.`,
          url: shareUrl,
        });
        return;
      } catch (err) {
        // User cancelled share sheet — don't treat as failure.
        if (err instanceof DOMException && err.name === 'AbortError') return;
      }
    }
    await copyLink();
  }, [copyLink, shareUrl, title]);

  return (
    <div className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => void handleShare()}
        className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
        aria-label="Share this demo"
      >
        {copied ? (
          <>
            <CheckIcon />
            Link copied
          </>
        ) : (
          <>
            <ShareIcon />
            Share demo
          </>
        )}
      </button>
      {error && (
        <p className="absolute right-0 top-full mt-1 w-56 text-[10px] text-red-500 bg-white border border-red-100 rounded-md px-2 py-1 shadow-sm z-50">
          {error}
        </p>
      )}
    </div>
  );
}

function ShareIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="18" cy="5" r="3" />
      <circle cx="6" cy="12" r="3" />
      <circle cx="18" cy="19" r="3" />
      <path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4" strokeLinecap="round" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-3.5 h-3.5 text-emerald-600" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
      <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
