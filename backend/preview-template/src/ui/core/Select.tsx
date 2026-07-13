import * as SelectPrimitive from '@radix-ui/react-select';

import { cn } from '../lib/cn';

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps {
  options: SelectOption[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  'aria-label'?: string;
}

export function Select({
  className,
  defaultValue,
  disabled,
  onValueChange,
  options,
  placeholder = 'Select…',
  value,
  ...rest
}: SelectProps) {
  return (
    <SelectPrimitive.Root value={value} defaultValue={defaultValue} onValueChange={onValueChange} disabled={disabled}>
      <SelectPrimitive.Trigger
        aria-label={rest['aria-label']}
        className={cn(
          'flex h-10 w-full items-center justify-between gap-2 rounded-[var(--radius-ui)] border border-border-subtle bg-card px-3 text-sm text-foreground outline-none focus:ring-4 focus:ring-[color:var(--color-ring)]/15 disabled:opacity-50',
          className
        )}
      >
        <SelectPrimitive.Value placeholder={placeholder} />
        <SelectPrimitive.Icon className="text-muted">▾</SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content className="z-50 overflow-hidden rounded-[var(--radius-ui)] border border-border-subtle bg-card shadow-[var(--shadow-ui)]" position="popper" sideOffset={6}>
          <SelectPrimitive.Viewport className="p-1">
            {options.map((option) => (
              <SelectPrimitive.Item
                key={option.value}
                value={option.value}
                className="cursor-pointer rounded-lg px-3 py-2 text-sm text-foreground outline-none data-[highlighted]:bg-background"
              >
                <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
