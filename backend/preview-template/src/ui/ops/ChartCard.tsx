import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { cn } from '../lib/cn';

export interface ChartCardRow {
  [key: string]: string | number;
}

export type ChartCardType = 'area' | 'bar';

export interface ChartCardProps {
  title: string;
  data: ChartCardRow[];
  dataKey: string;
  xKey: string;
  description?: string;
  type?: ChartCardType;
  className?: string;
}

export function ChartCard({
  className,
  data,
  dataKey,
  description,
  title,
  type = 'area',
  xKey,
}: ChartCardProps) {
  return (
    <div className={cn('rounded-[calc(var(--radius-ui)+0.25rem)] border border-border-subtle bg-card p-6 shadow-sm', className)}>
      <div>
        <h3 className="text-base font-semibold text-foreground">{title}</h3>
        {description ? <p className="mt-1 text-sm text-muted">{description}</p> : null}
      </div>
      <div className="mt-6 h-72 text-brand">
        <ResponsiveContainer width="100%" height="100%">
          {type === 'area' ? (
            <AreaChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="currentColor" strokeDasharray="3 3" opacity={0.12} />
              <XAxis dataKey={xKey} axisLine={false} tickLine={false} tickMargin={10} stroke="currentColor" opacity={0.45} />
              <YAxis axisLine={false} tickLine={false} tickMargin={10} stroke="currentColor" opacity={0.45} />
              <Tooltip contentStyle={{ borderRadius: '0.75rem', border: '1px solid var(--color-border-subtle)' }} />
              <Area type="monotone" dataKey={dataKey} stroke="currentColor" fill="currentColor" strokeWidth={2} fillOpacity={0.16} />
            </AreaChart>
          ) : (
            <BarChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="currentColor" strokeDasharray="3 3" opacity={0.12} />
              <XAxis dataKey={xKey} axisLine={false} tickLine={false} tickMargin={10} stroke="currentColor" opacity={0.45} />
              <YAxis axisLine={false} tickLine={false} tickMargin={10} stroke="currentColor" opacity={0.45} />
              <Tooltip contentStyle={{ borderRadius: '0.75rem', border: '1px solid var(--color-border-subtle)' }} />
              <Bar dataKey={dataKey} fill="currentColor" fillOpacity={0.85} radius={[8, 8, 2, 2]} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
