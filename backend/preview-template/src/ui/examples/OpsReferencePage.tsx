import { useMemo, useState } from 'react';

import {
  ActivityFeed,
  Button,
  ChartCard,
  DataTable,
  Dialog,
  FilterBar,
  OpsShell,
  PageHeader,
  SkeletonComposer,
  StatCard,
  getSkeleton,
} from '@/ui';

const SKELETON_ID = 'ops-dashboard' as const;

/** Reference ops dashboard — structure driven by skeleton registry. */
export default function OpsReferencePage() {
  const skeleton = getSkeleton(SKELETON_ID);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<'all' | 'confirmed' | 'risk'>('all');

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
          title="Today on the floor"
          description="Live bookings, chair utilization, and risk flags for all three studios."
          actions={<Button size="sm" variant="secondary">Refresh</Button>}
        />
      ),
      kpis: (
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          <StatCard label="Bookings today" value="28" delta="+12%" hint="vs last Monday" />
          <StatCard label="Utilization" value="81%" delta="+4%" hint="Chair hours filled" />
          <StatCard label="No-show risk" value="3" hint="Needs confirmation SMS" />
        </div>
      ),
      chart: (
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <ChartCard
            title="Weekly bookings"
            description="Confirmed appointments across studios"
            type="area"
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
          <ChartCard
            title="Revenue by treatment"
            description="This week’s closed revenue"
            type="bar"
            xKey="name"
            dataKey="revenue"
            data={[
              { name: 'Facial', revenue: 4200 },
              { name: 'Injectables', revenue: 6100 },
              { name: 'Laser', revenue: 3800 },
              { name: 'Membership', revenue: 2500 },
            ]}
          />
        </div>
      ),
      filters: (
        <div className="mt-6">
          <FilterBar
            searchPlaceholder="Search client or service"
            searchValue={query}
            onSearchChange={setQuery}
            filters={[
              { id: 'all', label: 'All', active: status === 'all', onSelect: () => setStatus('all') },
              { id: 'confirmed', label: 'Confirmed', active: status === 'confirmed', onSelect: () => setStatus('confirmed') },
              { id: 'risk', label: 'Risk', active: status === 'risk', onSelect: () => setStatus('risk') },
            ]}
            actions={<Dialog title="Export day sheet" description="Fixed Dialog contract." triggerLabel="Export" footer={<Button size="sm">Download CSV</Button>}>Includes confirmed bookings and no-show risk flags.</Dialog>}
          />
        </div>
      ),
      table: (
        <div className="mt-4">
          <DataTable
            columns={[
              { key: 'time', header: 'Time' },
              { key: 'client', header: 'Client' },
              { key: 'service', header: 'Service' },
              { key: 'status', header: 'Status' },
              { key: 'chair', header: 'Chair' },
            ]}
            rows={rows}
          />
        </div>
      ),
      activity: (
        <div className="mt-6">
          <ActivityFeed
            heading="Floor activity"
            items={[
              { id: '1', title: 'SMS sent', detail: 'Elena V. confirmation for 11:15 Membership.', time: '2m ago' },
              { id: '2', title: 'Checked in', detail: 'Sam T. arrived for Consult on chair B2.', time: '18m ago' },
              { id: '3', title: 'Risk flag', detail: 'Chris L. has not confirmed Hydrafacial.', time: '41m ago' },
              { id: '4', title: 'Inventory note', detail: 'Laser gel stock below weekly threshold.', time: '1h ago' },
            ]}
          />
        </div>
      ),
    }),
    [query, rows, skeleton.id, status]
  );

  return (
    <OpsShell
      brandName="Lumina Ops"
      navItems={[
        { id: 'overview', label: 'Overview', href: '/_catalogue/ops', active: true },
        { id: 'bookings', label: 'Bookings', href: '/_catalogue/ops' },
        { id: 'clients', label: 'Clients', href: '/_catalogue/ops' },
      ]}
      topbar={
        <>
          <p className="text-sm font-medium text-muted">Today · clinic floor</p>
          <p className="text-xs text-muted xl:hidden">Open sidebar on desktop for full nav</p>
        </>
      }
    >
      <SkeletonComposer skeletonId={SKELETON_ID} slots={slots} />
    </OpsShell>
  );
}
