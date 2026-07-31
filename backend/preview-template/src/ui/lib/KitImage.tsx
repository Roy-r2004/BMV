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
    return (
      <div
        aria-hidden="true"
        className={cn(
          'bg-[linear-gradient(135deg,color-mix(in_srgb,var(--color-brand)_20%,transparent),transparent_72%)]',
          className
        )}
      />
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
