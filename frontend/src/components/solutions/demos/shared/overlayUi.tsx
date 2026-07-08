import type { ReactNode } from 'react';
import {
  resolveHeroLines,
  resolveHeroSub,
  resolveTagline,
  useOverlayCta,
  useShowcaseOverlay,
} from '../../../../context/ShowcaseOverlayContext';

type AccentTag = 'span' | 'em';

interface OverlayHeroTitleProps {
  className?: string;
  primary: string;
  accent?: string;
  accentTag?: AccentTag;
}

/** Hero H1 that swaps to the user's overlay headline when personalized */
export function OverlayHeroTitle({ className, primary, accent, accentTag = 'span' }: OverlayHeroTitleProps) {
  const { heroHeadline } = useShowcaseOverlay();
  const lines = resolveHeroLines(heroHeadline, primary, accent);
  const Accent = accentTag;

  if (lines.accent) {
    return (
      <h1 className={className}>
        {lines.primary}
        {' '}
        <Accent>{lines.accent}</Accent>
      </h1>
    );
  }

  return <h1 className={className}>{lines.primary}</h1>;
}

interface OverlayHeroSubProps {
  className?: string;
  children: string;
}

export function OverlayHeroSub({ className, children }: OverlayHeroSubProps) {
  const { heroSub } = useShowcaseOverlay();
  return <p className={className}>{resolveHeroSub(heroSub, children)}</p>;
}

interface OverlayPlainHeroProps {
  primary: string;
  accent?: string;
  accentTag?: AccentTag;
}

/** For heroes without a dedicated className on h1 */
export function OverlayPlainHero({ primary, accent, accentTag = 'em' }: OverlayPlainHeroProps) {
  const { heroHeadline } = useShowcaseOverlay();
  const lines = resolveHeroLines(heroHeadline, primary, accent);
  const Accent = accentTag;

  if (lines.accent) {
    return (
      <h1>
        {lines.primary}
        {' '}
        <Accent>{lines.accent}</Accent>
      </h1>
    );
  }

  return <h1>{lines.primary}</h1>;
}

interface OverlayPlainSubProps {
  className?: string;
  children: string;
}

export function OverlayPlainSub({ className, children }: OverlayPlainSubProps) {
  const { heroSub } = useShowcaseOverlay();
  const text = resolveHeroSub(heroSub, children);
  return className ? <p className={className}>{text}</p> : <p>{text}</p>;
}

interface OverlayEyebrowProps {
  className?: string;
  children: string;
}

export function OverlayEyebrow({ className, children }: OverlayEyebrowProps) {
  const { tagline } = useShowcaseOverlay();
  const text = resolveTagline(tagline, children);
  return <p className={className}>{text}</p>;
}

interface OverlayAiChipsProps {
  className: string;
  defaults: string[];
  'aria-label'?: string;
}

export function OverlayAiChips({ className, defaults, 'aria-label': ariaLabel }: OverlayAiChipsProps) {
  const { aiChips } = useShowcaseOverlay();
  const chips = aiChips?.length ? aiChips : defaults;
  return (
    <div className={className} aria-label={ariaLabel} data-overlay-target="ai-chips">
      {chips.map((chip) => (
        <span key={chip}>{chip}</span>
      ))}
    </div>
  );
}

interface OverlayCtaButtonProps {
  className: string;
  defaultLabel: string;
  slot?: 'primary' | 'secondary';
  onClick?: () => void;
  type?: 'button';
  children?: ReactNode;
}

export function OverlayCtaButton({
  className,
  defaultLabel,
  slot = 'primary',
  onClick,
  type = 'button',
  children,
}: OverlayCtaButtonProps) {
  const ctas = useOverlayCta(defaultLabel, defaultLabel);
  const label = slot === 'primary' ? ctas.primary : (ctas.secondary ?? defaultLabel);
  return (
    <button
      type={type}
      className={className}
      onClick={onClick}
      data-overlay-target={slot === 'primary' ? 'cta-primary' : 'cta-secondary'}
    >
      {children ?? label}
    </button>
  );
}

interface OverlayHeroStatsProps {
  className: string;
  statClassName?: string;
  defaults: { label: string; value: string }[];
}

export function OverlayHeroStats({ className, statClassName, defaults }: OverlayHeroStatsProps) {
  const { heroStats } = useShowcaseOverlay();
  const stats = heroStats?.length ? heroStats : defaults;
  const itemClass = statClassName ?? 'overlay-hero-stat';
  return (
    <div className={className} data-overlay-target="hero-stats">
      {stats.map((s) => (
        <div key={s.label} className={itemClass}>
          <strong>{s.value}</strong>
          <span>{s.label}</span>
        </div>
      ))}
    </div>
  );
}
