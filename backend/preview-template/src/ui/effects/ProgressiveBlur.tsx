import * as React from 'react';

import { cn } from '../lib/cn';

export interface ProgressiveBlurProps {
  /** Height of the blur band (CSS length or %). Ignored for position "both". */
  height?: string;
  position?: 'top' | 'bottom' | 'both';
  /** Backdrop blur radii in px, weakest to strongest. */
  blurLevels?: number[];
  className?: string;
}

/**
 * Stacked backdrop-filter band that melts an edge of whatever sits behind
 * it — the treatment that lets captions and nav float over imagery without
 * a hard panel.
 * Adapted from Magic UI `progressive-blur` (MIT) — see PROVENANCE.json.
 * Rewritten for the kit: the dead `children` prop and leftover
 * `gradient-blur` class dropped; static CSS only, so there is nothing to
 * guard for reduced motion; the rgba(0,0,0,x) stops are mask alpha
 * geometry, not palette.
 */
export function ProgressiveBlur({
  height = '30%',
  position = 'bottom',
  blurLevels = [0.5, 1, 2, 4, 8, 16, 32, 64],
  className,
}: ProgressiveBlurProps) {
  const middleLayers = Math.max(0, blurLevels.length - 2);

  const mask = (start: number, mid: number, end: number, fade: number): string => {
    if (position === 'both') {
      return 'linear-gradient(rgba(0,0,0,0) 0%, rgba(0,0,0,1) 5%, rgba(0,0,0,1) 95%, rgba(0,0,0,0) 100%)';
    }
    const direction = position === 'bottom' ? 'to bottom' : 'to top';
    return `linear-gradient(${direction}, rgba(0,0,0,0) ${start}%, rgba(0,0,0,1) ${mid}%, rgba(0,0,0,1) ${end}%, rgba(0,0,0,0) ${fade}%)`;
  };
  const edgeMask =
    position === 'both'
      ? 'linear-gradient(rgba(0,0,0,0) 0%, rgba(0,0,0,1) 5%, rgba(0,0,0,1) 95%, rgba(0,0,0,0) 100%)'
      : `linear-gradient(${position === 'bottom' ? 'to bottom' : 'to top'}, rgba(0,0,0,0) 87.5%, rgba(0,0,0,1) 100%)`;

  const layer = (blur: number, zIndex: number, maskImage: string): React.CSSProperties => ({
    zIndex,
    backdropFilter: `blur(${blur}px)`,
    WebkitBackdropFilter: `blur(${blur}px)`,
    maskImage,
    WebkitMaskImage: maskImage,
  });

  return (
    <div
      aria-hidden
      className={cn(
        'pointer-events-none absolute inset-x-0 z-10',
        position === 'top' ? 'top-0' : position === 'bottom' ? 'bottom-0' : 'inset-y-0',
        className,
      )}
      style={{ height: position === 'both' ? '100%' : height }}
    >
      <div className="absolute inset-0" style={layer(blurLevels[0], 1, mask(0, 12.5, 25, 37.5))} />
      {Array.from({ length: middleLayers }, (_, index) => {
        const start = (index + 1) * 12.5;
        return (
          <div
            key={index}
            className="absolute inset-0"
            style={layer(
              blurLevels[index + 1],
              index + 2,
              mask(start, start + 12.5, start + 25, start + 37.5),
            )}
          />
        );
      })}
      <div
        className="absolute inset-0"
        style={layer(blurLevels[blurLevels.length - 1], blurLevels.length, edgeMask)}
      />
    </div>
  );
}
