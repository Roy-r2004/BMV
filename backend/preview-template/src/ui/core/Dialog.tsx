import * as React from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';

import { cn } from '../lib/cn';

export interface DialogProps {
  title: string;
  children: React.ReactNode;
  description?: string;
  triggerLabel?: string;
  /** When false, dialog is opened only via controlled `open` (row drill, etc.). */
  showTrigger?: boolean;
  footer?: React.ReactNode;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}

export function Dialog({
  children,
  className,
  defaultOpen,
  description,
  footer,
  onOpenChange,
  open,
  showTrigger = true,
  title,
  triggerLabel = 'Open',
}: DialogProps) {
  return (
    <DialogPrimitive.Root open={open} defaultOpen={defaultOpen} onOpenChange={onOpenChange}>
      {showTrigger ? (
        <DialogPrimitive.Trigger className="inline-flex h-9 items-center justify-center rounded-[var(--radius-ui)] border border-border-subtle bg-card px-3 text-sm font-semibold text-foreground hover:bg-background">
          {triggerLabel}
        </DialogPrimitive.Trigger>
      ) : null}
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-foreground/40" />
        <DialogPrimitive.Content
          className={cn(
            'fixed left-1/2 top-1/2 z-50 w-[min(92vw,28rem)] -translate-x-1/2 -translate-y-1/2 rounded-[calc(var(--radius-ui)+0.25rem)] border border-border-subtle bg-card p-6 shadow-[var(--shadow-ui)] outline-none',
            className
          )}
        >
          <DialogPrimitive.Title className="text-lg font-semibold text-foreground">{title}</DialogPrimitive.Title>
          {description ? (
            <DialogPrimitive.Description className="mt-2 text-sm leading-6 text-muted">{description}</DialogPrimitive.Description>
          ) : null}
          <div className="mt-4 text-sm text-foreground">{children}</div>
          {footer ? <div className="mt-6 flex justify-end gap-2">{footer}</div> : null}
          <DialogPrimitive.Close
            className="absolute right-4 top-4 inline-flex h-8 w-8 items-center justify-center rounded-full text-muted hover:bg-background hover:text-foreground"
            aria-label="Close dialog"
          >
            ×
          </DialogPrimitive.Close>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
