import * as React from 'react';

import { cn } from './cn';

export type KitImageProps = React.ImgHTMLAttributes<HTMLImageElement>;

/**
 * An `<img>` that degrades to the brand gradient instead of an empty rectangle.
 *
 * Request 45's gallery shipped ten cards and a blank grey box: one remote photo
 * failed to load, and every image in the kit rendered a missing-`src` fallback
 * but nothing for a `src` that does not resolve. A single dead URL is not worth a
 * hole in the page — the tinted placeholder reads as a deliberate crop.
 */
export function KitImage({ alt, className, onError, src, ...rest }: KitImageProps) {
  const [failed, setFailed] = React.useState(false);

  // A new src deserves a fresh attempt — the same slot is reused across items.
  React.useEffect(() => {
    setFailed(false);
  }, [src]);

  if (!src || failed) {
    // Unmistakably deliberate. At 20% over the card's own tint this read as a
    // plain grey box — request 47's gallery showed two of them beside six
    // paintings, which is worse than a crop and worse than nothing.
    return (
      <div
        aria-hidden="true"
        className={cn(
          'relative overflow-hidden',
          'bg-[linear-gradient(140deg,color-mix(in_srgb,var(--color-brand)_38%,var(--color-background))_0%,color-mix(in_srgb,var(--color-brand)_16%,var(--color-background))_55%,color-mix(in_srgb,var(--color-brand)_28%,var(--color-background))_100%)]',
          className
        )}
      >
        <span className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_50%_at_30%_25%,rgba(255,255,255,0.22),transparent_70%)]" />
      </div>
    );
  }

  return (
    <img
      {...rest}
      src={src}
      alt={alt ?? ''}
      className={className}
      onError={(event) => {
        setFailed(true);
        onError?.(event);
      }}
    />
  );
}
