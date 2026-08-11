import * as React from 'react';

import { cn } from '../lib/cn';
import { KitImage } from '../lib/KitImage';

export interface AvatarCirclesProps {
  /** Face image URLs, overlapped in order. */
  avatarUrls: string[];
  /** Renders a "+N" chip after the faces when > 0. */
  numPeople?: number;
  className?: string;
}

/**
 * Overlapping avatar stack + "+N" social-proof chip for testimonial and
 * booking bands. Adapted from Magic UI `avatar-circles` (MIT) — see
 * PROVENANCE.json. Rewritten for the kit: borders ride `--color-card` and
 * the chip rides the brand tokens (upstream hardcoded white/black); the
 * upstream `href=""` dead anchors are gone — previews link nowhere real, so
 * these are presentational spans; images go through KitImage.
 */
export function AvatarCircles({ avatarUrls, numPeople = 0, className }: AvatarCirclesProps) {
  if (avatarUrls.length === 0 && numPeople <= 0) return null;
  return (
    <div className={cn('flex -space-x-4', className)}>
      {avatarUrls.map((url, index) => (
        <KitImage
          key={index}
          className="size-10 rounded-full border-2 border-card object-cover"
          src={url}
          width={40}
          height={40}
          alt=""
        />
      ))}
      {numPeople > 0 && (
        <span className="flex size-10 items-center justify-center rounded-full border-2 border-card bg-brand text-center text-xs font-medium text-white">
          +{numPeople}
        </span>
      )}
    </div>
  );
}
