import * as React from 'react';

import { Button, type ButtonProps } from './Button.js';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from './Modal.js';
import { cn } from '../lib/cn.js';

export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  confirmLabel?: React.ReactNode;
  cancelLabel?: React.ReactNode;
  onConfirm?: () => void;
  confirmVariant?: ButtonProps['variant'];
  confirmDisabled?: boolean;
  children?: React.ReactNode;
  contentClassName?: string;
}

export function ConfirmDialog({
  cancelLabel = 'Cancel',
  children,
  confirmDisabled,
  confirmLabel = 'Confirm',
  confirmVariant = 'primary',
  contentClassName,
  description,
  onConfirm,
  onOpenChange,
  open,
  title,
}: ConfirmDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn('rounded-[1.75rem] p-0', contentClassName)}>
        <div className="p-6 pr-14">
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
          {children ? <div className="mt-4 text-sm leading-6 text-slate-600">{children}</div> : null}
        </div>
        <div className="flex flex-col-reverse gap-3 border-t border-slate-200 px-6 py-4 sm:flex-row sm:justify-end">
          <Button asChild variant="ghost">
            <DialogClose>{cancelLabel}</DialogClose>
          </Button>
          <Button variant={confirmVariant} disabled={confirmDisabled} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
