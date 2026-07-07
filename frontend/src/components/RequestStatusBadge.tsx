const STATUS_COLORS: Record<string, string> = {
  new: 'bg-blue-100 text-blue-700',
  reviewing: 'bg-yellow-100 text-yellow-700',
  'proposal sent': 'bg-purple-100 text-purple-700',
  accepted: 'bg-green-100 text-green-700',
  'in progress': 'bg-orange-100 text-orange-700',
  delivered: 'bg-teal-100 text-teal-700',
  lost: 'bg-red-100 text-red-700',
};

export default function RequestStatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] || 'bg-slate-100 text-slate-700';
  return (
    <span className={`px-2.5 py-1 rounded-full text-xs font-medium capitalize ${color}`}>
      {status}
    </span>
  );
}
