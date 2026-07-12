import { Toaster as SonnerToaster, toast } from 'sonner';
import type { ToasterProps } from 'sonner';

const toastClassNames = {
  toast: 'rounded-2xl border border-slate-200 bg-white text-slate-900 shadow-xl shadow-slate-950/10',
  title: 'text-sm font-semibold',
  description: 'text-sm text-slate-500',
  actionButton: 'bg-brand text-white',
  cancelButton: 'bg-slate-100 text-slate-700',
} as const;

export function Toaster({ toastOptions, ...props }: ToasterProps) {
  return (
    <SonnerToaster
      closeButton
      position="top-right"
      richColors
      toastOptions={{
        ...toastOptions,
        classNames: {
          ...toastClassNames,
          ...toastOptions?.classNames,
        },
      }}
      {...props}
    />
  );
}

export { toast };

export default Toaster;
