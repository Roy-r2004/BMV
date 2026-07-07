import type { ReactNode } from 'react';

interface Props {
  children: ReactNode;
  className?: string;
  glow?: boolean;
}

export default function TiltCard({ children, className = '', glow = false }: Props) {
  return (
    <div className={`h-full ${className}`}>
      <div className={`card p-5 h-full transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md ${glow ? 'ring-2 ring-blue-500/20' : ''}`}>
        {children}
      </div>
    </div>
  );
}
