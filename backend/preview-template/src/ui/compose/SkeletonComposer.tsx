import * as React from 'react';

import { getSkeleton, type SkeletonId } from '../registry';

export type SkeletonSlots = Record<string, React.ReactNode>;

export interface SkeletonComposerProps {
  skeletonId: SkeletonId;
  /** Map of section id → rendered catalogue subtree. Composer decides order. */
  slots: SkeletonSlots;
}

export interface ComposedSkeletonLayout {
  main: React.ReactNode;
  /** Pass to OpsShell `rail` for ops-dashboard activity column. */
  rail?: React.ReactNode;
}

function assertRequiredSections(skeletonId: SkeletonId, slots: SkeletonSlots) {
  const skeleton = getSkeleton(skeletonId);
  const missingRequired = skeleton.requiredSections.filter((section) => {
    if (section === 'shell') return false;
    return slots[section] == null;
  });
  if (missingRequired.length > 0) {
    throw new Error(`Skeleton "${skeletonId}" missing required sections: ${missingRequired.join(', ')}`);
  }
  return skeleton;
}

/**
 * Drives page structure from the skeleton registry.
 * Pages supply content slots only; section order comes from recommendedOrder.
 */
export function SkeletonComposer({ skeletonId, slots }: SkeletonComposerProps) {
  const skeleton = assertRequiredSections(skeletonId, slots);

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

/**
 * Split ops-dashboard slots into main column + right rail (activity).
 * Other skeletons return a flat main tree (no rail).
 */
export function composeSkeletonLayout(
  skeletonId: SkeletonId,
  slots: SkeletonSlots
): ComposedSkeletonLayout {
  const skeleton = assertRequiredSections(skeletonId, slots);

  if (skeletonId === 'ops-dashboard' && slots.activity != null) {
    const mainOrder = skeleton.recommendedOrder.filter(
      (section) => section !== 'shell' && section !== 'activity' && slots[section] != null
    );
    return {
      main: (
        <div className="space-y-5">
          {mainOrder.map((section) => (
            <React.Fragment key={section}>{slots[section]}</React.Fragment>
          ))}
        </div>
      ),
      rail: <div className="space-y-4 xl:sticky xl:top-5">{slots.activity}</div>,
    };
  }

  return {
    main: <SkeletonComposer skeletonId={skeletonId} slots={slots} />,
  };
}

export { getSkeleton };
export type { SkeletonId };
