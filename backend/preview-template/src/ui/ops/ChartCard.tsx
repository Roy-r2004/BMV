import * as React from 'react';
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
export type ChartCardDensity = 'compact' | 'comfortable';
export type ChartCardValueFormat = 'number' | 'currency' | 'compact';

export interface ChartCardProps {
  title: string;
  data: ChartCardRow[];
  dataKey: string;
  xKey: string;
  description?: string;
  insight?: string;
  type?: ChartCardType;
  /** When true, operator can switch chart type and density. */
  adjustable?: boolean;
  density?: ChartCardDensity;
  valueFormat?: ChartCardValueFormat;
  className?: string;
}

function formatTick(value: number, valueFormat: ChartCardValueFormat) {
  if (valueFormat === 'currency') {
    if (Math.abs(value) >= 1000) return `$${(value / 1000).toFixed(value % 1000 === 0 ? 0 : 1)}k`;
    return `$${value}`;
  }
  if (valueFormat === 'compact') {
    if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(value % 1000 === 0 ? 0 : 1)}k`;
    return String(value);
  }
  return String(value);
}

export function ChartCard({
  adjustable = false,
  className,
  data,
  dataKey,
  density: densityProp = 'comfortable',
  description,
  insight,
  title,
  type: typeProp = 'area',
  valueFormat = 'number',
  xKey,
}: ChartCardProps) {
  const [type, setType] = React.useState<ChartCardType>(typeProp);
  const [density, setDensity] = React.useState<ChartCardDensity>(densityProp);

  React.useEffect(() => setType(typeProp), [typeProp]);
  React.useEffect(() => setDensity(densityProp), [densityProp]);

  const height = density === 'compact' ? 208 : 256;

  const chart = (
    <ResponsiveContainer width="100%" height="100%">
      {type === 'area' ? (
        <AreaChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
          <CartesianGrid vertical={false} stroke="var(--color-border-subtle)" strokeDasharray="3 3" />
          <XAxis
            dataKey={xKey}
            axisLine={false}
            tickLine={false}
            tickMargin={10}
            tick={{ fill: 'var(--color-muted)', fontSize: 12 }}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tickMargin={8}
            width={44}
            tick={{ fill: 'var(--color-muted)', fontSize: 12 }}
            tickFormatter={(value: number) => formatTick(value, valueFormat)}
          />
          <Tooltip
            formatter={(value: number) => formatTick(value, valueFormat)}
            contentStyle={{
              borderRadius: '0.75rem',
              border: '1px solid var(--color-border-subtle)',
              background: 'var(--color-card)',
              color: 'var(--color-foreground)',
            }}
          />
          <Area
            type="monotone"
            dataKey={dataKey}
            stroke="var(--color-chart)"
            fill="var(--color-chart)"
            strokeWidth={2}
            fillOpacity={0.14}
          />
        </AreaChart>
      ) : (
        <BarChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
          <CartesianGrid vertical={false} stroke="var(--color-border-subtle)" strokeDasharray="3 3" />
          <XAxis
            dataKey={xKey}
            axisLine={false}
            tickLine={false}
            tickMargin={10}
            tick={{ fill: 'var(--color-muted)', fontSize: 12 }}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tickMargin={8}
            width={44}
            tick={{ fill: 'var(--color-muted)', fontSize: 12 }}
            tickFormatter={(value: number) => formatTick(value, valueFormat)}
          />
          <Tooltip
            formatter={(value: number) => formatTick(value, valueFormat)}
            contentStyle={{
              borderRadius: '0.75rem',
              border: '1px solid var(--color-border-subtle)',
              background: 'var(--color-card)',
              color: 'var(--color-foreground)',
            }}
          />
          <Bar dataKey={dataKey} fill="var(--color-chart)" fillOpacity={0.9} radius={[6, 6, 2, 2]} />
        </BarChart>
      )}
    </ResponsiveContainer>
  );

  return (
    <div className={cn('rounded-[calc(var(--radius-ui)+0.25rem)] border border-border-subtle bg-card p-5 shadow-sm', className)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold tracking-tight text-foreground">{title}</h3>
          {description ? <p className="mt-1 text-xs leading-5 text-muted">{description}</p> : null}
        </div>
        {adjustable ? (
          <div className="flex flex-wrap items-center gap-1.5">
            {(['bar', 'area'] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setType(option)}
                className={cn(
                  'rounded-md px-2 py-1 text-[10px] font-semibold tracking-wide uppercase transition',
                  type === option ? 'bg-foreground text-background' : 'bg-background text-muted hover:text-foreground'
                )}
              >
                {option}
              </button>
            ))}
            {(['compact', 'comfortable'] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setDensity(option)}
                className={cn(
                  'rounded-md px-2 py-1 text-[10px] font-semibold tracking-wide uppercase transition',
                  density === option ? 'bg-foreground text-background' : 'bg-background text-muted hover:text-foreground'
                )}
              >
                {option === 'compact' ? 'Compact' : 'Roomy'}
              </button>
            ))}
          </div>
        ) : (
          <span className="rounded-md bg-foreground/6 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-muted uppercase">
            {type}
          </span>
        )}
      </div>
      <div className="mt-5 text-foreground" style={{ height }}>
        {chart}
      </div>
      {insight ? (
        <p className="mt-4 border-t border-border-subtle pt-3 text-xs leading-5 text-muted">
          <span className="font-semibold tracking-[0.08em] text-foreground uppercase">Insight · </span>
          {insight}
        </p>
      ) : null}
    </div>
  );
}
