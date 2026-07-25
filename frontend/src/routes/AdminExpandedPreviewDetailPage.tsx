import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  approveExpandedPreview,
  getExpandedPreviewAdmin,
  publishExpandedPreview,
  rejectExpandedPreview,
  reviewExpandedPreview,
  startExpandedPreviewGeneration,
  type ExpandedPreviewAdminView,
} from '../api/expandedPreview';

export default function AdminExpandedPreviewDetailPage() {
  const { id } = useParams();
  const expandedId = Number(id);
  const [view, setView] = useState<ExpandedPreviewAdminView | null>(null);
  const [notes, setNotes] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!expandedId) return;
    const data = await getExpandedPreviewAdmin(expandedId);
    setView(data);
  }, [expandedId]);

  useEffect(() => {
    void load().catch(() => setError('Failed to load Expanded Preview.'));
    const t = window.setInterval(() => {
      void load().catch(() => undefined);
    }, 10000);
    return () => window.clearInterval(t);
  }, [load]);

  const run = async (fn: () => Promise<ExpandedPreviewAdminView>) => {
    setBusy(true);
    setError('');
    try {
      setView(await fn());
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || 'Action failed';
      setError(String(detail));
    } finally {
      setBusy(false);
    }
  };

  if (!view) {
    return <div className="ac-page">{error || 'Loading…'}</div>;
  }

  return (
    <div className="ac-page">
      <header className="ac-page__header">
        <div>
          <Link to="/admin/expanded-previews" className="ac-panel__link">
            ← Queue
          </Link>
          <h1 className="ac-page__title">Expanded Preview #{view.id}</h1>
          <p className="ac-page__lead">
            {view.business_name} · request{' '}
            <Link to={`/admin/requests/${view.request_id}`}>
              #{view.request_id}
            </Link>{' '}
            · {view.current_status}
          </p>
        </div>
      </header>

      {error ? <p className="ac-error">{error}</p> : null}

      <div className="ac-panel" style={{ marginBottom: '1rem' }}>
        <h2 className="ac-panel__title">Customer request</h2>
        <p>
          <strong>Reason:</strong> {view.customer_reason || '—'}
        </p>
        <p>
          <strong>Requested changes:</strong> {view.requested_changes || '—'}
        </p>
        <p>
          <strong>Contact preference:</strong> {view.contact_preference || '—'}
        </p>
        <p>
          <strong>Email:</strong> {view.customer_email || '—'}
        </p>
        {view.tier_1_preview_url ? (
          <p>
            <a
              className="ac-row-link"
              href={view.tier_1_preview_url}
              target="_blank"
              rel="noreferrer"
            >
              Open Tier 1 preview
            </a>
          </p>
        ) : null}
      </div>

      <div className="ac-panel" style={{ marginBottom: '1rem' }}>
        <h2 className="ac-panel__title">Tier 2 review surface</h2>
        <p>Phase 4: {view.phase4_status || '—'}</p>
        <p>Phase 5: {view.phase5_status || '—'}</p>
        <p>Screenshots: {view.screenshot_count}</p>
        <p>
          Warnings / blocking: {view.warning_count} / {view.blocking_finding_count}
        </p>
        <p>Tier 2 revision: {view.tier_2_candidate_revision_id || '—'}</p>
        {view.generation_error ? (
          <p className="ac-error">{view.generation_error}</p>
        ) : null}
        {view.published_preview_url ? (
          <p>
            <a
              className="ac-row-link"
              href={view.published_preview_url}
              target="_blank"
              rel="noreferrer"
            >
              Published customer URL
            </a>
          </p>
        ) : null}
      </div>

      <div className="ac-panel" style={{ marginBottom: '1rem' }}>
        <h2 className="ac-panel__title">Actions</h2>
        <label className="ac-field">
          <span>Reason</span>
          <input value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <label className="ac-field">
          <span>Internal notes</span>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <div className="ac-actions" style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {view.current_status === 'requested' ? (
            <>
              <button
                type="button"
                className="ac-btn ac-btn--primary"
                disabled={busy}
                onClick={() =>
                  void run(() =>
                    approveExpandedPreview(view.id, {
                      reason: reason || undefined,
                      internal_notes: notes || undefined,
                    }),
                  )
                }
              >
                Approve
              </button>
              <button
                type="button"
                className="ac-btn"
                disabled={busy}
                onClick={() => {
                  if (!reason.trim()) {
                    setError('Rejection requires a reason.');
                    return;
                  }
                  if (!window.confirm('Reject this Expanded Preview request?')) return;
                  void run(() =>
                    rejectExpandedPreview(view.id, {
                      reason: reason.trim(),
                      internal_notes: notes || undefined,
                    }),
                  );
                }}
              >
                Reject
              </button>
            </>
          ) : null}
          {view.current_status === 'approved' ? (
            <button
              type="button"
              className="ac-btn ac-btn--primary"
              disabled={busy}
              onClick={() => {
                if (!window.confirm('Start Tier 2 generation now?')) return;
                void run(() =>
                  startExpandedPreviewGeneration(view.id, {
                    reason: reason || undefined,
                    confirm: true,
                  }),
                );
              }}
            >
              Start Tier 2 generation
            </button>
          ) : null}
          {view.current_status === 'generation_completed' ? (
            <>
              <button
                type="button"
                className="ac-btn ac-btn--primary"
                disabled={busy}
                onClick={() => {
                  if (!window.confirm('Accept Tier 2 review?')) return;
                  void run(() =>
                    reviewExpandedPreview(view.id, {
                      outcome: 'review_accepted',
                      reason: reason || undefined,
                      internal_notes: notes || undefined,
                      confirm: true,
                    }),
                  );
                }}
              >
                Accept review
              </button>
              <button
                type="button"
                className="ac-btn"
                disabled={busy}
                onClick={() => {
                  if (!window.confirm('Reject Tier 2 review?')) return;
                  void run(() =>
                    reviewExpandedPreview(view.id, {
                      outcome: 'review_rejected',
                      reason: reason || undefined,
                      internal_notes: notes || undefined,
                      confirm: true,
                    }),
                  );
                }}
              >
                Reject review
              </button>
            </>
          ) : null}
          {view.current_status === 'review_accepted' ? (
            <button
              type="button"
              className="ac-btn ac-btn--primary"
              disabled={busy}
              onClick={() => {
                if (!window.confirm('Publish Expanded Preview to the customer?')) return;
                void run(() =>
                  publishExpandedPreview(view.id, {
                    reason: reason || undefined,
                    confirm: true,
                  }),
                );
              }}
            >
              Publish to customer
            </button>
          ) : null}
        </div>
      </div>

      <div className="ac-panel">
        <h2 className="ac-panel__title">Audit timeline</h2>
        <ul className="ac-list">
          {view.timeline.map((event) => (
            <li key={event.id}>
              <strong>{event.to_status}</strong> · {event.actor_id} ·{' '}
              {new Date(event.created_at).toLocaleString()}
              {event.reason ? ` — ${event.reason}` : ''}
              {event.internal_notes ? ` [${event.internal_notes}]` : ''}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
