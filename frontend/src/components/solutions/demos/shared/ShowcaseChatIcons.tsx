type IconProps = { className?: string };

export function IconChat({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconSend({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" aria-hidden>
      <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconClose({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M18 6 6 18M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconArrowRight({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconSparkle({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 2l1.2 4.2L17.5 7.5 13.2 8.7 12 13l-1.2-4.3L6.5 7.5l4.3-1.3L12 2zm7 9 1 3.5 3.5 1-3.5 1-1 3.5-1-3.5-3.5-1 3.5-1 1-3.5 3.5-1 1-3.5zM5 14l.8 2.8L8.6 18l-2.8.8L5 21.6l-.8-2.8L1.4 18l2.8-.8L5 14z" />
    </svg>
  );
}

export function StudioNineLogo({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden>
      <rect width="40" height="40" rx="9" fill="#c9a227" />
      <text x="20" y="27" textAnchor="middle" fontFamily="system-ui, sans-serif" fontSize="20" fontWeight="800" fill="#14110f">9</text>
    </svg>
  );
}

export function HarborLogo({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden>
      <rect width="40" height="40" rx="20" fill="rgba(255,255,255,0.18)" />
      <path d="M12 26c0-5.5 4-10 8-14 4 4 8 8.5 8 14" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M10 26h20" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="20" cy="11" r="2.5" fill="#67e8f9" />
    </svg>
  );
}

export function EmberLogo({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden>
      <rect width="40" height="40" rx="9" fill="#ea580c" />
      <path
        d="M20 8c-2 6-6 8-6 13a6 6 0 0 0 12 0c0-5-4-7-6-13z"
        fill="#fcd34d"
        stroke="#fff7ed"
        strokeWidth="1.2"
      />
      <path d="M20 16c-1 3-2.5 4-2.5 6.5a2.5 2.5 0 0 0 5 0C22.5 20 21 19 20 16z" fill="#fff" opacity="0.9" />
    </svg>
  );
}

export function NorthlineLogo({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden>
      <rect width="40" height="40" rx="9" fill="#4f46e5" />
      <path d="M10 28V14l10-6 10 6v14" stroke="#fff" strokeWidth="2" strokeLinejoin="round" />
      <path d="M16 28v-8h8v8" stroke="#c7d2fe" strokeWidth="2" strokeLinejoin="round" />
      <rect x="18" y="11" width="4" height="4" rx="1" fill="#a5b4fc" />
    </svg>
  );
}

export function PeakFormLogo({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden>
      <rect width="40" height="40" rx="9" fill="#059669" />
      <path d="M12 28V16l8-8 8 8v12" stroke="#fff" strokeWidth="2.2" strokeLinejoin="round" />
      <path d="M16 28v-6h8v6" stroke="#a7f3d0" strokeWidth="2" strokeLinejoin="round" />
      <circle cx="20" cy="14" r="2" fill="#6ee7b7" />
    </svg>
  );
}

export function ApexLogo({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden>
      <rect width="40" height="40" rx="9" fill="#334155" />
      <path d="M12 28V12l8-4 8 4v16" stroke="#fff" strokeWidth="2" strokeLinejoin="round" />
      <path d="M16 28v-6h8v6" stroke="#cbd5e1" strokeWidth="2" strokeLinejoin="round" />
      <circle cx="20" cy="10" r="2" fill="#94a3b8" />
    </svg>
  );
}

export function BrightFixLogo({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden>
      <rect width="40" height="40" rx="6" fill="#14171d" />
      <rect x="1.5" y="1.5" width="37" height="37" rx="5" stroke="#f97316" strokeWidth="1.5" />
      <path d="M14 28V16l6-3 6 3v12" stroke="#f4f5f7" strokeWidth="2" strokeLinejoin="round" />
      <path d="M17 28v-5h6v5" stroke="#f97316" strokeWidth="2" strokeLinejoin="round" />
      <path d="M20 10v4M18 12h4" stroke="#fb923c" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="20" cy="21" r="1.5" fill="#f97316" />
    </svg>
  );
}

export function SummitLogo({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden>
      <rect width="40" height="40" rx="9" fill="#0891b2" />
      <path d="M10 28L20 10l10 18" stroke="#fff" strokeWidth="2.2" strokeLinejoin="round" />
      <path d="M14 24h12" stroke="#a5f3fc" strokeWidth="2" strokeLinecap="round" />
      <circle cx="20" cy="8" r="2.5" fill="#67e8f9" />
    </svg>
  );
}

export function LumenLogo({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden>
      <rect width="40" height="40" rx="9" fill="#7c3aed" />
      <path d="M20 8v24" stroke="#ede9fe" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M14 14h12" stroke="#c4b5fd" strokeWidth="2" strokeLinecap="round" />
      <circle cx="20" cy="28" r="3" fill="#ddd6fe" />
      <path d="M12 20c2-4 6-6 8-6s6 2 8 6" stroke="#a78bfa" strokeWidth="1.8" strokeLinecap="round" fill="none" />
    </svg>
  );
}

export function MetroLogo({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden>
      <rect width="40" height="40" rx="9" fill="#1e3a5f" />
      <path d="M8 26h24" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M12 26c1-5 3.5-9 8-12 4.5 3 7 7 8 12" stroke="#e2e8f0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="15" cy="26" r="2.5" fill="#38bdf8" />
      <circle cx="25" cy="26" r="2.5" fill="#38bdf8" />
      <path d="M18 16h4" stroke="#93c5fd" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function RowLogo({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden>
      <rect width="40" height="40" rx="9" fill="#7a1f35" />
      <path d="M12 28V12h8.5c3.2 0 5.5 1.9 5.5 4.6 0 1.9-1.1 3.4-2.9 4.1L28 28h-4.2l-4.1-6.8H16V28H12z" fill="#f5e6d3" />
      <path d="M16 12v9.2h4.2c2.1 0 3.4-1.1 3.4-2.8S22.3 15.6 20.2 15.6H16V12z" fill="#d4a574" opacity="0.55" />
      <rect x="11" y="30" width="18" height="1.5" rx="0.75" fill="#d4a574" opacity="0.7" />
    </svg>
  );
}

export function HarborFundLogo({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden>
      <rect width="40" height="40" rx="9" fill="#166534" />
      <path
        d="M20 8c-1.5 4-5 6.5-5 11a5 5 0 0 0 10 0c0-4.5-3.5-7-5-11z"
        fill="#86efac"
        stroke="#dcfce7"
        strokeWidth="1.2"
      />
      <path d="M12 28c2-4 5-6 8-6s6 2 8 6" stroke="#bbf7d0" strokeWidth="2" strokeLinecap="round" />
      <circle cx="20" cy="22" r="2" fill="#fef3c7" />
    </svg>
  );
}
