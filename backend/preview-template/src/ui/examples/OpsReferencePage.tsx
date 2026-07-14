import { useMemo, useState } from 'react';

import {
  ActivityFeed,
  Badge,
  Button,
  ChartCard,
  DataTable,
  Dialog,
  FilterBar,
  MotionPage,
  OpsShell,
  PageHeader,
  RiskQueue,
  StatCard,
  ToastHost,
  composeSkeletonLayout,
  getSkeleton,
  toast,
} from '@/ui';

const SKELETON_ID = 'ops-dashboard' as const;

/** Reference soft SaaS ops dashboard — main column + activity rail. */
export default function OpsReferencePage() {
  const skeleton = getSkeleton(SKELETON_ID);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<'all' | 'confirmed' | 'risk'>('all');
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);

  const todayLabel = new Date().toLocaleDateString('en-US', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });

  const rows = useMemo(
    () =>
      [
        { time: '09:00', client: 'Maya R.', service: 'Hydrafacial', status: 'Confirmed', chair: 'A1' },
        { time: '09:45', client: 'Sam T.', service: 'Consult', status: 'Checked in', chair: 'B2' },
        { time: '10:30', client: 'Jordan K.', service: 'Laser', status: 'Confirmed', chair: 'A2' },
        { time: '11:15', client: 'Elena V.', service: 'Membership', status: 'Pending SMS', chair: 'C1' },
        { time: '12:00', client: 'Priya N.', service: 'Injectables', status: 'Confirmed', chair: 'A1' },
        { time: '13:30', client: 'Chris L.', service: 'Hydrafacial', status: 'No-show risk', chair: 'B1' },
        { time: '14:15', client: 'Ava M.', service: 'Consult', status: 'Confirmed', chair: 'B2' },
        { time: '15:00', client: 'Noah P.', service: 'Laser', status: 'Checked in', chair: 'A2' },
        { time: '15:45', client: 'Mia S.', service: 'Aftercare', status: 'Confirmed', chair: 'C1' },
        { time: '16:30', client: 'Owen D.', service: 'Membership', status: 'Pending SMS', chair: 'A1' },
      ].filter((row) => {
        const matchesQuery =
          !query ||
          row.client.toLowerCase().includes(query.toLowerCase()) ||
          row.service.toLowerCase().includes(query.toLowerCase());
        const matchesStatus =
          status === 'all' ||
          (status === 'confirmed' && row.status === 'Confirmed') ||
          (status === 'risk' && row.status.toLowerCase().includes('risk'));
        return matchesQuery && matchesStatus;
      }),
    [query, status]
  );

  const slots = useMemo(
    () => ({
      header: (
        <PageHeader
          title="Hello, floor lead"
          description="Live bookings, chair utilization, and risk flags for all three studios."
          meta={<p className="text-sm font-medium text-muted">{todayLabel}</p>}
          actions={
            <Button
              size="sm"
              variant="secondary"
              onClick={() => toast.success('Floor refreshed', 'Bookings and risk flags are up to date.')}
            >
              Refresh
            </Button>
          }
        />
      ),
      kpis: (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard label="Bookings today" value="28" delta="+12%" hint="vs last Monday" />
          <StatCard label="Utilization" value="81%" delta="+4%" hint="Chair hours filled" />
          <StatCard label="No-show risk" value="3" delta="-1" hint="Needs confirmation SMS" />
        </div>
      ),
      risk: (
        <RiskQueue
          heading="Needs attention"
          items={[
            {
              id: 'r1',
              title: 'Chris L. · Hydrafacial 13:30',
              detail: 'No confirmation in 41 minutes. Chair B1 still held.',
              severity: 'high',
              actionLabel: 'Send SMS',
            },
            {
              id: 'r2',
              title: 'Elena V. · Membership 11:15',
              detail: 'Pending SMS — reminder queued but not acknowledged.',
              severity: 'medium',
              actionLabel: 'Resend',
            },
            {
              id: 'r3',
              title: 'Owen D. · Membership 16:30',
              detail: 'Second reminder window opens in 90 minutes.',
              severity: 'low',
              actionLabel: 'Watch',
            },
          ]}
          onAction={(id) => toast.success('Action queued', `Risk item ${id} handed to floor SMS.`)}
        />
      ),
      chart: (
        <ChartCard
          title="Performance"
          description="Confirmed appointments across studios"
          insight="Friday is pacing +27% vs last week — protect two overflow chairs after 15:00."
          type="area"
          adjustable
          valueFormat="compact"
          xKey="day"
          dataKey="bookings"
          data={[
            { day: 'Mon', bookings: 18 },
            { day: 'Tue', bookings: 22 },
            { day: 'Wed', bookings: 25 },
            { day: 'Thu', bookings: 21 },
            { day: 'Fri', bookings: 28 },
            { day: 'Sat', bookings: 16 },
          ]}
        />
      ),
      filters: (
        <FilterBar
          searchPlaceholder="Search client or service"
          searchValue={query}
          onSearchChange={setQuery}
          filters={[
            { id: 'all', label: 'All', active: status === 'all', onSelect: () => setStatus('all') },
            {
              id: 'confirmed',
              label: 'Confirmed',
              active: status === 'confirmed',
              onSelect: () => setStatus('confirmed'),
            },
            { id: 'risk', label: 'Risk', active: status === 'risk', onSelect: () => setStatus('risk') },
          ]}
          actions={
            <Dialog
              title="Export day sheet"
              description="Fixed Dialog contract."
              triggerLabel="Export"
              footer={
                <Button size="sm" onClick={() => toast.show('Export queued')}>
                  Download CSV
                </Button>
              }
            >
              Includes confirmed bookings and no-show risk flags.
            </Dialog>
          }
        />
      ),
      table: (
        <DataTable
          columns={[
            { key: 'time', header: 'Time' },
            { key: 'client', header: 'Client' },
            { key: 'service', header: 'Service' },
            {
              key: 'status',
              header: 'Status',
              render: (row) => {
                const value = String(row.status ?? '');
                const tone = value.toLowerCase().includes('risk')
                  ? 'destructive'
                  : value === 'Confirmed'
                    ? 'default'
                    : 'secondary';
                return <Badge variant={tone}>{value}</Badge>;
              },
            },
            { key: 'chair', header: 'Chair' },
          ]}
          rows={rows}
          onRowSelect={setSelected}
        />
      ),
      activity: (
        <ActivityFeed
          heading="Activity"
          items={[
            { id: '1', title: 'SMS sent', detail: 'Elena V. confirmation for 11:15 Membership.', time: '2m ago' },
            { id: '2', title: 'Checked in', detail: 'Sam T. arrived for Consult on chair B2.', time: '18m ago' },
            { id: '3', title: 'Risk flag', detail: 'Chris L. has not confirmed Hydrafacial.', time: '41m ago' },
            { id: '4', title: 'Inventory note', detail: 'Laser gel stock below weekly threshold.', time: '1h ago' },
          ]}
        />
      ),
    }),
    [query, rows, skeleton.id, status, todayLabel]
  );

  const { main, rail } = useMemo(
    () => composeSkeletonLayout(SKELETON_ID, slots),
    [slots]
  );

  return (
    <MotionPage>
      <ToastHost />
      <OpsShell
        brandName="Lumina Ops"
        appearance="soft"
        adjustableSidebar
        rail={rail}
        navItems={[
          { id: 'overview', label: 'Overview', href: '/_catalogue/ops', active: true },
          { id: 'bookings', label: 'Bookings', href: '/_catalogue/ops' },
          { id: 'clients', label: 'Clients', href: '/_catalogue/ops' },
        ]}
        topbar={
          <>
            <p className="text-sm font-medium text-muted">Today · clinic floor</p>
            <p className="hidden text-xs text-muted xl:block">Soft workspace · activity stays in the rail</p>
          </>
        }
      >
        <div data-skeleton={skeleton.id}>{main}</div>
      </OpsShell>

      <Dialog
        showTrigger={false}
        open={Boolean(selected)}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        title={selected ? `${String(selected.client)} · ${String(selected.time)}` : 'Booking detail'}
        description="Row drill — fixed Dialog contract."
        footer={
          <Button
            size="sm"
            onClick={() => {
              toast.success('Note saved', 'Floor note attached to booking.');
              setSelected(null);
            }}
          >
            Save note
          </Button>
        }
      >
        {selected ? (
          <dl className="space-y-3">
            <div className="flex justify-between gap-4">
              <dt className="text-muted">Service</dt>
              <dd className="font-medium">{String(selected.service)}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-muted">Status</dt>
              <dd className="font-medium">{String(selected.status)}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-muted">Chair</dt>
              <dd className="font-mono">{String(selected.chair)}</dd>
            </div>
          </dl>
        ) : null}
      </Dialog>
    </MotionPage>
  );
}
