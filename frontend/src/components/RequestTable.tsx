import { Link } from 'react-router-dom';
import type { RequestListItem } from '../types/request';
import RequestStatusBadge from './RequestStatusBadge';

interface Props {
  requests: RequestListItem[];
}

export default function RequestTable({ requests }: Props) {
  if (requests.length === 0) {
    return <p className="text-slate-500 text-center py-8">No requests found.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left">
            <th className="py-3 px-2 font-semibold">ID</th>
            <th className="py-3 px-2 font-semibold">Business</th>
            <th className="py-3 px-2 font-semibold">Industry</th>
            <th className="py-3 px-2 font-semibold">Email</th>
            <th className="py-3 px-2 font-semibold">Status</th>
            <th className="py-3 px-2 font-semibold">Score</th>
            <th className="py-3 px-2 font-semibold">Date</th>
            <th className="py-3 px-2 font-semibold">Actions</th>
          </tr>
        </thead>
        <tbody>
          {requests.map((r) => (
            <tr key={r.id} className="border-b border-slate-100 hover:bg-slate-50">
              <td className="py-3 px-2">{r.id}</td>
              <td className="py-3 px-2 font-medium">{r.business_name}</td>
              <td className="py-3 px-2 text-slate-600">{r.industry || '—'}</td>
              <td className="py-3 px-2 text-slate-600">{r.email}</td>
              <td className="py-3 px-2"><RequestStatusBadge status={r.status} /></td>
              <td className="py-3 px-2">{r.business_fit_score ?? '—'}</td>
              <td className="py-3 px-2 text-slate-500">{new Date(r.created_at).toLocaleDateString()}</td>
              <td className="py-3 px-2">
                <Link to={`/admin/requests/${r.id}`} className="text-accent hover:underline font-medium">
                  View
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
