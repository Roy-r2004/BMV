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

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './Card.js';
import { cn } from '../lib/cn.js';

type ChartRow = Record<string, string | number>;

export interface ChartCardProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  title: React.ReactNode;
  description?: React.ReactNode;
  data: ChartRow[];
  dataKey: string;
  xKey: string;
  type?: 'area' | 'bar';
  chartClassName?: string;
}

export function ChartCard({
  chartClassName,
  className,
  data,
  dataKey,
  description,
  title,
  type = 'area',
  xKey,
  ...props
}: ChartCardProps) {
  const isArea = type === 'area';

  return (
    <Card className={cn('rounded-3xl border-slate-200 bg-white shadow-sm', className)} {...props}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className={cn('h-80 text-brand', chartClassName)}>
        <ResponsiveContainer width="100%" height="100%">
          {isArea ? (
            <AreaChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="currentColor" strokeDasharray="3 3" opacity={0.12} />
              <XAxis
                dataKey={xKey}
                axisLine={false}
                tickLine={false}
                tickMargin={10}
                stroke="currentColor"
                opacity={0.45}
              />
              <YAxis axisLine={false} tickLine={false} tickMargin={10} stroke="currentColor" opacity={0.45} />
              <Tooltip
                cursor={{ stroke: 'currentColor', strokeOpacity: 0.16 }}
                contentStyle={{
                  borderRadius: '1rem',
                  border: '1px solid rgba(148, 163, 184, 0.2)',
                  boxShadow: '0 14px 40px rgba(15, 23, 42, 0.12)',
                }}
              />
              <Area
                type="monotone"
                dataKey={dataKey}
                stroke="currentColor"
                fill="currentColor"
                strokeWidth={2.25}
                fillOpacity={0.18}
              />
            </AreaChart>
          ) : (
            <BarChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="currentColor" strokeDasharray="3 3" opacity={0.12} />
              <XAxis
                dataKey={xKey}
                axisLine={false}
                tickLine={false}
                tickMargin={10}
                stroke="currentColor"
                opacity={0.45}
              />
              <YAxis axisLine={false} tickLine={false} tickMargin={10} stroke="currentColor" opacity={0.45} />
              <Tooltip
                cursor={{ fill: 'currentColor', fillOpacity: 0.08 }}
                contentStyle={{
                  borderRadius: '1rem',
                  border: '1px solid rgba(148, 163, 184, 0.2)',
                  boxShadow: '0 14px 40px rgba(15, 23, 42, 0.12)',
                }}
              />
              <Bar dataKey={dataKey} fill="currentColor" fillOpacity={0.82} radius={[10, 10, 4, 4]} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
