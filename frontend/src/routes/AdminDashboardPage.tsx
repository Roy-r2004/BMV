import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listRequests } from '../api/admin';
import type { RequestListItem } from '../types/request';
import { STATUS_OPTIONS } from '../types/request';
import RequestTable from '../components/RequestTable';

export default function AdminDashboardPage() {
  const navigate = useNavigate();
  const [requests, setRequests] = useState<RequestListItem[]>([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!sessionStorage.getItem('admin_password')) {
      navigate('/admin/login');
      return;
    }
    loadRequests();
  }, [filter, navigate]);

  const loadRequests = async () => {
    setLoading(true);
    try {
      const data = await listRequests(filter);
      setRequests(data);
    } catch {
      navigate('/admin/login');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Requests</h1>
        <span className="text-sm text-slate-500">{requests.length} total</span>
      </div>

      <div className="flex flex-wrap gap-2 mb-6">
        {STATUS_OPTIONS.map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium capitalize transition-colors ${
              filter === s ? 'bg-accent text-white' : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      <div className="card p-4">
        {loading ? (
          <p className="text-center py-8 text-slate-500">Loading...</p>
        ) : (
          <RequestTable requests={requests} />
        )}
      </div>
    </div>
  );
}
