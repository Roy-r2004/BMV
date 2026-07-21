import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { hasAdminSession, listRequests } from '../api/admin';
import type { RequestListItem } from '../types/request';
import { STATUS_OPTIONS } from '../types/request';
import RequestTable from '../components/RequestTable';

export default function AdminDashboardPage() {
  const navigate = useNavigate();
  const [requests, setRequests] = useState<RequestListItem[]>([]);
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!hasAdminSession()) {
      navigate('/admin/login');
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const data = await listRequests(filter);
        if (!cancelled) setRequests(data);
      } catch {
        navigate('/admin/login');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [filter, navigate]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return requests;
    return requests.filter((r) =>
      [r.business_name, r.email, r.industry, r.whatsapp, String(r.id)]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q)),
    );
  }, [requests, query]);

  const buildCount = requests.filter((r) => r.build_requested).length;

  return (
    <div className="ac-page">
      <header className="ac-hero">
        <div>
          <p className="ac-hero__eyebrow">Pipeline</p>
          <h1 className="ac-hero__title">Requests</h1>
          <p className="ac-hero__sub">
            {filtered.length} shown
            {query ? ` · filtered from ${requests.length}` : ''}
            {buildCount ? ` · ${buildCount} build requested` : ''}
          </p>
        </div>
        <div className="ac-actions">
          <input
            className="ac-input"
            style={{ width: 'min(100%, 16rem)' }}
            placeholder="Search business, email, id…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </header>

      <div className="ac-filters">
        {STATUS_OPTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setFilter(s)}
            className={`ac-filter${filter === s ? ' is-active' : ''}`}
          >
            {s}
          </button>
        ))}
      </div>

      <section className="ac-panel">
        {loading ? <p className="ac-empty">Loading requests…</p> : <RequestTable requests={filtered} />}
      </section>
    </div>
  );
}
