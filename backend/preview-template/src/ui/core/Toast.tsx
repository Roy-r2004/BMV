import { Toaster, toast as sonnerToast } from 'sonner';

export type ToastTone = 'default' | 'success' | 'error';

export interface ToastOptions {
  description?: string;
  tone?: ToastTone;
}

/** Local toast API — pages never import sonner directly. */
export const toast = {
  show(message: string, options: ToastOptions = {}) {
    const { description, tone = 'default' } = options;
    if (tone === 'success') {
      sonnerToast.success(message, { description });
      return;
    }
    if (tone === 'error') {
      sonnerToast.error(message, { description });
      return;
    }
    sonnerToast(message, { description });
  },
  success(message: string, description?: string) {
    this.show(message, { description, tone: 'success' });
  },
  error(message: string, description?: string) {
    this.show(message, { description, tone: 'error' });
  },
};

export function ToastHost() {
  return (
    <Toaster
      position="bottom-right"
      toastOptions={{
        className: 'font-sans',
        style: {
          borderRadius: '0.85rem',
          border: '1px solid var(--color-border-subtle)',
          background: 'var(--color-card)',
          color: 'var(--color-foreground)',
        },
      }}
    />
  );
}
