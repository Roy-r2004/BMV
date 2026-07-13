import * as React from 'react';
import * as TabsPrimitive from '@radix-ui/react-tabs';

import { cn } from '../lib/cn';

export interface TabsItem {
  value: string;
  label: string;
  content: React.ReactNode;
}

export interface TabsProps {
  items: TabsItem[];
  defaultValue?: string;
  value?: string;
  onValueChange?: (value: string) => void;
  className?: string;
}

export function Tabs({ className, defaultValue, items, onValueChange, value }: TabsProps) {
  const initial = defaultValue ?? items[0]?.value;
  return (
    <TabsPrimitive.Root
      className={cn('w-full', className)}
      defaultValue={value === undefined ? initial : undefined}
      value={value}
      onValueChange={onValueChange}
    >
      <TabsPrimitive.List className="inline-flex h-11 items-center gap-1 rounded-[var(--radius-ui)] border border-border-subtle bg-background p-1">
        {items.map((item) => (
          <TabsPrimitive.Trigger
            key={item.value}
            value={item.value}
            className="rounded-[calc(var(--radius-ui)-0.15rem)] px-3 py-2 text-sm font-medium text-muted outline-none transition focus-visible:ring-4 focus-visible:ring-[color:var(--color-ring)]/15 data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm"
          >
            {item.label}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {items.map((item) => (
        <TabsPrimitive.Content key={item.value} value={item.value} className="mt-4 outline-none">
          {item.content}
        </TabsPrimitive.Content>
      ))}
    </TabsPrimitive.Root>
  );
}
