import * as React from 'react';

import { getSkeleton, type SkeletonId } from '../registry';

export type SkeletonSlots = Record<string, React.ReactNode>;

export interface SkeletonComposerProps {
  skeletonId: SkeletonId;
  /** Map of section id → rendered catalogue subtree. Composer decides order. */
  slots: SkeletonSlots;
}

/**
 * Drives page structure from the skeleton registry.
 * Pages supply content slots only; section order comes from recommendedOrder.
 */
export function SkeletonComposer({ skeletonId, slots }: SkeletonComposerProps) {
  const skeleton = getSkeleton(skeletonId);
  const missingRequired = skeleton.requiredSections.filter((section) => {
    if (section === 'shell') return false;
    return slots[section] == null;
  });

  if (missingRequired.length > 0) {
    throw new Error(`Skeleton "${skeletonId}" missing required sections: ${missingRequired.join(', ')}`);
  }

  const ordered = skeleton.recommendedOrder.filter((section) => {
    if (section === 'shell') return false;
    if (slots[section] != null) return true;
    return false;
  });

  return (
    <>
      {ordered.map((section) => (
        <React.Fragment key={section}>{slots[section]}</React.Fragment>
      ))}
    </>
  );
}

export { getSkeleton };
export type { SkeletonId };
