import type { ReactNode, SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement> & { className?: string };

const base = {
  fill: 'none' as const,
  stroke: 'currentColor',
  strokeWidth: 1.75,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

export function IconBuilding({ className = 'w-5 h-5', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <path d="M3 21h18" /><path d="M5 21V7l8-4v18" /><path d="M19 21V11l-6-4" />
      <path d="M9 9h1" /><path d="M9 13h1" /><path d="M9 17h1" />
    </svg>
  );
}

export function IconTarget({ className = 'w-5 h-5', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" />
    </svg>
  );
}

export function IconInspiration({ className = 'w-5 h-5', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
      <path d="M12 2v2M12 20v2" />
    </svg>
  );
}

export function IconLayers({ className = 'w-5 h-5', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5" /><path d="M2 12l10 5 10-5" />
    </svg>
  );
}

export function IconSend({ className = 'w-5 h-5', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <path d="M22 2L11 13" /><path d="M22 2l-7 20-4-9-9-4 20-7z" />
    </svg>
  );
}

export function IconSparkles({ className = 'w-5 h-5', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3" />
      <path d="M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

export function IconGift({ className = 'w-5 h-5', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <rect x="3" y="8" width="18" height="4" rx="1" /><path d="M12 8v13" />
      <path d="M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7" />
      <path d="M7.5 8a2.5 2.5 0 0 1 0-5C9 3 12 8 12 8s3-5 4.5-5a2.5 2.5 0 0 1 0 5H7.5z" />
    </svg>
  );
}

export function IconSearch({ className = 'w-5 h-5', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
    </svg>
  );
}

export function IconLayout({ className = 'w-5 h-5', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18" /><path d="M9 21V9" />
    </svg>
  );
}

export function IconRocket({ className = 'w-5 h-5', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z" />
      <path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z" />
      <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0" /><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" />
    </svg>
  );
}

export function IconUpload({ className = 'w-5 h-5', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  );
}

export function IconFilm({ className = 'w-5 h-5', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <rect x="2" y="2" width="20" height="20" rx="2.18" /><line x1="7" y1="2" x2="7" y2="22" />
      <line x1="17" y1="2" x2="17" y2="22" /><line x1="2" y1="12" x2="22" y2="12" />
    </svg>
  );
}

export function IconClose({ className = 'w-4 h-4', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

export function IconArrowLeft({ className = 'w-4 h-4', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <line x1="19" y1="12" x2="5" y2="12" /><polyline points="12 19 5 12 12 5" />
    </svg>
  );
}

export function IconArrowRight({ className = 'w-4 h-4', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
    </svg>
  );
}

export function IconCheck({ className = 'w-4 h-4', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

export function IconClock({ className = 'w-4 h-4', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

export function IconCoins({ className = 'w-4 h-4', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
    </svg>
  );
}

export function IconBrain({ className = 'w-4 h-4', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z" />
      <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z" />
      <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4" />
    </svg>
  );
}

export function IconMinus({ className = 'w-4 h-4', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

export function IconShield({ className = 'w-4 h-4', ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base} {...props} aria-hidden>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

export const STEP_ICONS: ReactNode[] = [
  <IconBuilding key="business" />,
  <IconTarget key="challenge" />,
  <IconInspiration key="inspiration" />,
  <IconLayers key="project" />,
  <IconSend key="contact" />,
];

export const GENERATING_PHASES = [
  { Icon: IconBuilding, text: 'Understanding your business...' },
  { Icon: IconSearch, text: 'Studying your reference tool...' },
  { Icon: IconSparkles, text: 'Designing your custom version...' },
  { Icon: IconLayout, text: 'Building your visual preview...' },
  { Icon: IconRocket, text: 'Almost ready...' },
] as const;
