import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';

import { cn } from '../lib/cn.js';

const buttonVariants = {
  primary: 'bg-brand text-white shadow-sm shadow-brand/20 hover:bg-brand-dark',
  secondary: 'border-slate-200 bg-white text-slate-900 shadow-sm hover:border-slate-300 hover:bg-slate-50',
  ghost: 'bg-transparent text-slate-700 hover:bg-slate-100 hover:text-slate-900',
  danger: 'bg-rose-600 text-white shadow-sm shadow-rose-600/20 hover:bg-rose-700',
} as const;

const buttonSizes = {
  sm: 'h-9 px-3.5 text-sm',
  md: 'h-10 px-4 text-sm',
} as const;

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  asChild?: boolean;
  size?: keyof typeof buttonSizes;
  variant?: keyof typeof buttonVariants;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ asChild = false, className, size = 'md', type, variant = 'primary', ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';

    return (
      <Comp
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl border border-transparent font-semibold transition-all duration-200 outline-none focus-visible:ring-4 focus-visible:ring-brand/10 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:h-4 [&_svg]:w-4 [&_svg]:shrink-0',
          buttonVariants[variant],
          buttonSizes[size],
          className
        )}
        {...(!asChild ? { type: type ?? 'button' } : undefined)}
        {...props}
      />
    );
  }
);

Button.displayName = 'Button';

export default Button;
