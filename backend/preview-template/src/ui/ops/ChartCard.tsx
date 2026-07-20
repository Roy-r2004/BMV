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

import { drawChart } from '../motion/anime';
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

function ChartTooltip({
  active,
  payload,
  label,
  valueFormat,
}: {
  active?: boolean;
  payload?: Array<{ value?: number }>;
  label?: string;
  valueFormat: ChartCardValueFormat;
}) {
  if (!active || !payload?.length) return null;
  const value = Number(payload[0]?.value ?? 0);
  return (
    <div className="rounded-[var(--radius-ui)] border border-border-subtle bg-card px-3 py-2 shadow-[var(--shadow-ui)]">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">{label}</p>
      <p className="mt-0.5 text-sm font-semibold tabular-nums text-foreground">
        {formatTick(value, valueFormat)}
      </p>
    </div>
  );
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
  const chartRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => setType(typeProp), [typeProp]);
  React.useEffect(() => setDensity(densityProp), [densityProp]);

  React.useEffect(() => {
    const el = chartRef.current;
    if (!el) return;
    const timer = window.setTimeout(() => {
      drawChart(el, { duration: 980 });
    }, 80);
    return () => window.clearTimeout(timer);
  }, [type, data, dataKey, density]);

  const height = density === 'compact' ? 200 : 248;
  const gradientId = React.useId().replace(/:/g, '');

  const chart = (
    <ResponsiveContainer width="100%" height="100%">
      {type === 'area' ? (
        <AreaChart data={data} margin={{ top: 10, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-chart)" stopOpacity={0.28} />
              <stop offset="100%" stopColor="var(--color-chart)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid
            vertical={false}
            stroke="var(--color-border-subtle)"
            strokeDasharray="2 6"
            strokeOpacity={0.85}
          />
          <XAxis
            dataKey={xKey}
            axisLine={false}
            tickLine={false}
            tickMargin={12}
            tick={{ fill: 'var(--color-muted)', fontSize: 11, fontWeight: 500 }}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tickMargin={6}
            width={40}
            tick={{ fill: 'var(--color-muted)', fontSize: 11, fontWeight: 500 }}
            tickFormatter={(value: number) => formatTick(value, valueFormat)}
          />
          <Tooltip
            cursor={{ stroke: 'var(--color-border-subtle)', strokeWidth: 1 }}
            content={<ChartTooltip valueFormat={valueFormat} />}
          />
          <Area
            type="monotone"
            dataKey={dataKey}
            stroke="var(--color-chart)"
            fill={`url(#${gradientId})`}
            strokeWidth={2.25}
            activeDot={{ r: 4, strokeWidth: 0, fill: 'var(--color-chart)' }}
            isAnimationActive={false}
          />
        </AreaChart>
      ) : (
        <BarChart data={data} margin={{ top: 10, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid
            vertical={false}
            stroke="var(--color-border-subtle)"
            strokeDasharray="2 6"
            strokeOpacity={0.85}
          />
          <XAxis
            dataKey={xKey}
            axisLine={false}
            tickLine={false}
            tickMargin={12}
            tick={{ fill: 'var(--color-muted)', fontSize: 11, fontWeight: 500 }}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tickMargin={6}
            width={40}
            tick={{ fill: 'var(--color-muted)', fontSize: 11, fontWeight: 500 }}
            tickFormatter={(value: number) => formatTick(value, valueFormat)}
          />
          <Tooltip
            cursor={{ fill: 'color-mix(in srgb, var(--color-brand) 6%, transparent)' }}
            content={<ChartTooltip valueFormat={valueFormat} />}
          />
          <Bar
            dataKey={dataKey}
            fill="var(--color-chart)"
            fillOpacity={0.92}
            radius={[5, 5, 2, 2]}
            isAnimationActive={false}
          />
        </BarChart>
      )}
    </ResponsiveContainer>
  );

  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-[calc(var(--radius-ui)+0.35rem)] border border-border-subtle bg-card p-5 shadow-[var(--shadow-ui)]',
        className
      )}
      data-chart-card=""
    >
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
                  type === option
                    ? 'bg-foreground text-background'
                    : 'bg-background text-muted hover:text-foreground'
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
                  density === option
                    ? 'bg-foreground text-background'
                    : 'bg-background text-muted hover:text-foreground'
                )}
              >
                {option === 'compact' ? 'Compact' : 'Roomy'}
              </button>
            ))}
          </div>
        ) : (
          <span className="rounded-md bg-foreground/5 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-muted uppercase">
            {type}
          </span>
        )}
      </div>
      <div ref={chartRef} className="mt-5 text-foreground" style={{ height }}>
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
