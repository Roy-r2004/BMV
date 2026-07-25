import { useCallback, useEffect, useState } from 'react';
import {
  getExpandedPreview,
  getRequestAccessToken,
  requestExpandedPreview,
  storeRequestAccessToken,
  type ExpandedPreviewCustomerView,
} from '../api/expandedPreview';

const STATUS_LABEL: Record<string, string> = {
  requested: 'Requested',
  under_review: 'Under review',
  approved: 'Approved',
  generating: 'Generating expanded preview',
  ready: 'Ready',
  rejected: 'Rejected',
  failed: 'Generation failed',
};

interface Props {
  requestId: number;
  accessToken?: string | null;
  demoView?: boolean;
}

export default function ExpandedPreviewRequestCard({
  requestId,
  accessToken,
  demoView = false,
}: Props) {
  const [view, setView] = useState<ExpandedPreviewCustomerView | null>(null);
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [changes, setChanges] = useState('');
  const [contact, setContact] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (accessToken) storeRequestAccessToken(requestId, accessToken);
  }, [accessToken, requestId]);

  const refresh = useCallback(async () => {
    if (demoView) return;
    if (!getRequestAccessToken(requestId) && !accessToken) return;
    try {
      const data = await getExpandedPreview(requestId);
      setView(data);
    } catch {
      /* no open request yet or unauthorized until token stored */
    }
  }, [accessToken, demoView, requestId]);

  useEffect(() => {
    void refresh();
    if (demoView) return;
    const t = window.setInterval(() => void refresh(), 15000);
    return () => window.clearInterval(t);
  }, [demoView, refresh]);

  const submit = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await requestExpandedPreview(requestId, {
        reason: reason.trim() || undefined,
        requested_changes: changes.trim() || undefined,
        contact_preference: contact.trim() || undefined,
      });
      setView(data);
      setOpen(false);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || 'Could not submit Expanded Preview request.';
      setError(String(detail));
    } finally {
      setLoading(false);
    }
  };

  if (demoView) return null;

  return (
    <section className="mt-10 rounded-2xl border border-slate-200 bg-white p-6 sm:p-8 shadow-sm">
      <h2 className="text-xl font-semibold text-slate-900 tracking-tight">
        Request Expanded Preview
      </h2>
      <p className="mt-2 text-sm text-slate-600 max-w-2xl leading-relaxed">
        Want a richer version with more workflows and pages? Submit a request and
        our team will review it before starting an expanded build. Expanded
        previews are reviewed before they are shared — this is not an automatic
        upgrade and does not imply a free build.
      </p>

      {view ? (
        <div className="mt-5 space-y-3">
          <div className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-800">
            Status: <strong>{STATUS_LABEL[view.status] || view.status}</strong>
          </div>
          {view.can_open_published && view.published_preview_url ? (
            <div>
              <a
                className="inline-flex items-center rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
                href={view.published_preview_url}
                target="_blank"
                rel="noreferrer"
              >
                Open published Expanded Preview
              </a>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="mt-5">
          {!open ? (
            <button
              type="button"
              className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800"
              onClick={() => setOpen(true)}
            >
              Request Expanded Preview
            </button>
          ) : (
            <div className="space-y-3 max-w-xl">
              <label className="block text-sm text-slate-700">
                Goals or reason
                <textarea
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  rows={3}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
              <label className="block text-sm text-slate-700">
                Requested changes
                <textarea
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  rows={3}
                  value={changes}
                  onChange={(e) => setChanges(e.target.value)}
                />
              </label>
              <label className="block text-sm text-slate-700">
                Contact preference (optional)
                <input
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  value={contact}
                  onChange={(e) => setContact(e.target.value)}
                  placeholder="Email or WhatsApp preference"
                />
              </label>
              {error ? <p className="text-sm text-red-600">{error}</p> : null}
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={loading}
                  className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                  onClick={() => void submit()}
                >
                  {loading ? 'Submitting…' : 'Submit request'}
                </button>
                <button
                  type="button"
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm"
                  onClick={() => setOpen(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
