const STATUS_CLASS: Record<string, string> = {
  new: 'ac-badge--new',
  reviewing: 'ac-badge--reviewing',
  'proposal sent': 'ac-badge--proposal',
  accepted: 'ac-badge--accepted',
  'in progress': 'ac-badge--progress',
  delivered: 'ac-badge--delivered',
  lost: 'ac-badge--lost',
};

export default function RequestStatusBadge({ status }: { status: string }) {
  const cls = STATUS_CLASS[status] || 'ac-badge--default';
  return <span className={`ac-badge ${cls}`}>{status}</span>;
}
