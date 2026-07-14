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
  orientation?: 'horizontal' | 'vertical';
  className?: string;
}

export function Tabs({ className, defaultValue, items, onValueChange, orientation = 'horizontal', value }: TabsProps) {
  const initial = defaultValue ?? items[0]?.value;
  return (
    <TabsPrimitive.Root
      className={cn('w-full', orientation === 'vertical' && 'flex gap-6', className)}
      defaultValue={value === undefined ? initial : undefined}
      value={value}
      onValueChange={onValueChange}
      orientation={orientation}
    >
      <TabsPrimitive.List
        className={cn(
          'items-center gap-1 rounded-[var(--radius-ui)] border border-border-subtle bg-background p-1',
          orientation === 'vertical' ? 'flex h-fit shrink-0 flex-col' : 'inline-flex h-11'
        )}
      >
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
      <div className={cn(orientation === 'vertical' && 'min-w-0 flex-1')}>
        {items.map((item) => (
          <TabsPrimitive.Content
            key={item.value}
            value={item.value}
            className={cn('outline-none', orientation === 'horizontal' && 'mt-4')}
          >
            {item.content}
          </TabsPrimitive.Content>
        ))}
      </div>
    </TabsPrimitive.Root>
  );
}
