import { Link } from 'react-router-dom';
import type { RequestListItem } from '../types/request';
import RequestStatusBadge from './RequestStatusBadge';

interface Props {
  requests: RequestListItem[];
}

export default function RequestTable({ requests }: Props) {
  if (requests.length === 0) {
    return <p className="ac-empty">No requests in this filter.</p>;
  }

  return (
    <div className="ac-table-wrap">
      <table className="ac-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Business</th>
            <th>Industry</th>
            <th>Contact</th>
            <th>Status</th>
            <th>Fit</th>
            <th>Submitted</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {requests.map((r) => (
            <tr key={r.id}>
              <td className="ac-num">#{r.id}</td>
              <td>
                <span className="ac-strong">
                  {r.build_requested ? <span className="ac-build-dot" title="Build requested" /> : null}
                  {r.business_name}
                </span>
              </td>
              <td>{r.industry || '—'}</td>
              <td>
                <div className="ac-strong" style={{ fontSize: '0.82rem' }}>{r.email}</div>
                {r.whatsapp ? <div style={{ fontSize: '0.72rem' }}>{r.whatsapp}</div> : null}
              </td>
              <td>
                <RequestStatusBadge status={r.status} />
              </td>
              <td className="ac-num">{r.business_fit_score ?? '—'}</td>
              <td>
                {new Date(r.created_at).toLocaleDateString(undefined, {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </td>
              <td>
                <Link to={`/admin/requests/${r.id}`} className="ac-row-link">
                  Open →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
