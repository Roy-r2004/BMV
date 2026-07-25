import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  listExpandedPreviews,
  type ExpandedPreviewListItem,
} from '../api/expandedPreview';

const STATUSES = [
  '',
  'requested',
  'approved',
  'generation_started',
  'generation_completed',
  'review_accepted',
  'published',
  'rejected',
  'generation_failed',
  'review_rejected',
];

export default function AdminExpandedPreviewQueuePage() {
  const [status, setStatus] = useState('');
  const [items, setItems] = useState<ExpandedPreviewListItem[]>([]);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setError('');
      const data = await listExpandedPreviews({
        status: status || undefined,
        limit: 100,
      });
      setItems(data);
    } catch {
      setError('Could not load Expanded Preview queue.');
    }
  }, [status]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="ac-page">
      <header className="ac-page__header">
        <div>
          <h1 className="ac-page__title">Expanded Previews</h1>
          <p className="ac-page__lead">
            Customer requests for team-reviewed Tier 2 generation. This queue is
            separate from Phase 7 rollout controls.
          </p>
        </div>
        <label className="ac-field">
          <span>Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => (
              <option key={s || 'all'} value={s}>
                {s || 'All'}
              </option>
            ))}
          </select>
        </label>
      </header>

      {error ? <p className="ac-error">{error}</p> : null}

      <div className="ac-panel">
        <table className="ac-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Request</th>
              <th>Business</th>
              <th>Customer</th>
              <th>Status</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>
                  <Link
                    className="ac-row-link"
                    to={`/admin/expanded-previews/${item.id}`}
                  >
                    #{item.id}
                  </Link>
                </td>
                <td>
                  <Link
                    className="ac-row-link"
                    to={`/admin/requests/${item.request_id}`}
                  >
                    #{item.request_id}
                  </Link>
                </td>
                <td>{item.business_name || '—'}</td>
                <td>{item.customer_email || '—'}</td>
                <td>{item.current_status}</td>
                <td>{new Date(item.updated_at).toLocaleString()}</td>
              </tr>
            ))}
            {!items.length ? (
              <tr>
                <td colSpan={6}>No Expanded Preview requests.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
